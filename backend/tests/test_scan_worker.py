# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The scan worker (#299): the server outlives a scan the kernel kills.

These start a real child process, with a small stand-in for app.py whose
functions die by SIGKILL as the OOM killer would kill them, so what is
tested is the restart, the one retry on the same path, and /health
answering throughout."""

import importlib.util
import os
import pathlib
import shutil
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from unittest.mock import patch

import httpx

from backend.tests.test_server_pipeline import _load_server
from server import (  # backend/ is on sys.path once the helpers load
    perf,
    scan_worker,
)

STUB_NAME = "scan_worker_stub"
STUB = textwrap.dedent("""
    import os
    import signal
    import threading
    import time

    from server import perf


    def _model_health():
        return {
            "backends": {"stub": {"ready": True, "reason": ""}},
            "adaptive_engine_speed": {},
            "devices": {"stub": "cpu"},
            "built_tiers": ["layout_m"],
        }


    def add(a, b):
        with perf.stage("decode", pixels=a * b) as step:
            step.count("reader_calls")
        return a + b


    def refuse():
        raise ValueError("unreadable page")


    def unpicklable():
        return threading.Lock()


    def die():
        os.kill(os.getpid(), signal.SIGKILL)


    def die_once(flag):
        if not os.path.exists(flag):
            open(flag, "w").close()
            os.kill(os.getpid(), signal.SIGKILL)
        return "read on the second try"


    def wait_for(flag):
        deadline = time.monotonic() + 10
        while not os.path.exists(flag) and time.monotonic() < deadline:
            time.sleep(0.02)
        return "done"


    def facts():
        with open("/proc/self/oom_score_adj") as f:
            oom = f.read().strip()
        return {"oom_score_adj": oom, "thread": threading.current_thread().name}
    """)


def _wait(predicate, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class ScanWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.stub_path = os.path.join(cls.tmp, "stub_app.py")
        with open(cls.stub_path, "w", encoding="utf-8") as f:
            f.write(STUB)
        spec = importlib.util.spec_from_file_location(STUB_NAME, cls.stub_path)
        cls.stub = importlib.util.module_from_spec(spec)
        sys.modules[STUB_NAME] = cls.stub
        spec.loader.exec_module(cls.stub)

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop(STUB_NAME, None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.worker = scan_worker.Supervisor(STUB_NAME, self.stub_path, 2)
        self.addCleanup(self.worker.stop)
        self.worker.start()
        self.assertTrue(_wait(lambda: self.worker.stats()["state"] == "ready"))

    def flag(self, name):
        return os.path.join(self.tmp, f"{self.id()}-{name}")

    def test_runs_in_the_child_and_brings_back_its_timings(self):
        with perf.scan() as record:
            self.assertEqual(self.worker.call(self.stub.add, 3, 4), 7)
        summary = record.summary()
        self.assertEqual(summary["decode"]["sizes"], {"pixels": 12})
        self.assertEqual(summary["decode"]["counts"], {"reader_calls": 1})
        self.assertEqual(self.worker.stats()["restarts"], 0)

    def test_the_child_is_the_one_the_kernel_kills(self):
        facts = self.worker.call(self.stub.facts)
        if os.path.exists("/proc/self/oom_score_adj"):
            self.assertEqual(facts["oom_score_adj"], "1000")
        # One engine copy per slot thread (ocr_backends._replica_index).
        self.assertRegex(facts["thread"], r"^scan_\d+$")

    def test_errors_come_back_as_raised(self):
        with self.assertRaisesRegex(ValueError, "unreadable page"):
            self.worker.call(self.stub.refuse)
        # An answer that will not pickle still comes back as an error.
        with self.assertRaisesRegex(RuntimeError, "lock"):
            self.worker.call(self.stub.unpicklable)
        self.assertEqual(self.worker.call(self.stub.add, 1, 1), 2)

    def test_a_killed_scan_runs_once_more_on_a_new_child(self):
        flag = self.flag("died")
        self.assertEqual(
            self.worker.call(self.stub.die_once, flag),
            "read on the second try",
        )
        stats = self.worker.stats()
        self.assertEqual(stats["restarts"], 1)
        self.assertEqual(stats["last_exit"], -9)

    def test_lost_twice_is_scan_lost_and_the_next_scan_runs(self):
        with self.assertRaises(scan_worker.ScanLost):
            self.worker.call(self.stub.die)
        self.assertEqual(self.worker.stats()["restarts"], 2)
        self.assertEqual(self.worker.call(self.stub.add, 2, 2), 4)

    def test_health_answers_while_a_scan_runs(self):
        flag = self.flag("go")
        result = {}
        running = threading.Thread(
            target=lambda: result.update(
                done=self.worker.call(self.stub.wait_for, flag)
            )
        )
        running.start()
        try:
            health = self.worker.health()
            self.assertEqual(health["built_tiers"], ["layout_m"])
        finally:
            pathlib.Path(flag).touch()
            running.join(10)
        self.assertEqual(result, {"done": "done"})

    def test_a_scan_beside_the_killed_one_runs_once_more_too(self):
        # Two slots: the child dies running one scan while it runs a
        # second. Both are run once more on the next child.
        flag = self.flag("go")
        result = {}
        beside = threading.Thread(
            target=lambda: result.update(
                done=self.worker.call(self.stub.wait_for, flag)
            )
        )
        beside.start()
        self.assertEqual(
            self.worker.call(self.stub.die_once, self.flag("died")),
            "read on the second try",
        )
        pathlib.Path(flag).touch()
        beside.join(20)
        self.assertEqual(result, {"done": "done"})
        self.assertEqual(self.worker.stats()["restarts"], 1)

    def test_health_is_none_while_the_child_starts(self):
        fresh = scan_worker.Supervisor(STUB_NAME, self.stub_path, 1)
        self.assertEqual(fresh.stats()["state"], "starting")
        self.assertIsNone(fresh.health())


class ChildPartsTests(unittest.TestCase):
    """The child's pieces, run in this process so coverage sees them."""

    def test_run_sends_the_answer_and_the_stages(self):
        sent = []

        def work():
            with perf.stage("layout", lines=3):
                pass
            return {"ok": True}

        # pylint: disable-next=protected-access
        scan_worker._run(sent.append, 7, work, ())
        kind, call_id, ok, value, rows = sent[0]
        self.assertEqual(
            (kind, call_id, ok, value), ("result", 7, True, {"ok": True})
        )
        self.assertEqual([r["name"] for r in rows], ["layout"])

    def test_adopt_outside_a_scan_does_nothing(self):
        perf.adopt([{"name": "decode", "wall_ms": 1.0}])  # no error

    def test_adopt_drops_what_is_not_a_number(self):
        with perf.scan() as record:
            perf.adopt(
                [
                    {
                        "name": "Decode Page",
                        "sizes": {"pixels": 10, "text": "a name"},
                        "counts": {"reader_calls": 2},
                        "wall_ms": 5.0,
                        "cpu_ms": "slow",
                        "mem_mb": None,
                    }
                ]
            )
        row = record.summary()["decode-page"]
        self.assertEqual(row["sizes"], {"pixels": 10})
        self.assertEqual(row["cpu_ms"], 0.0)


class ScanLostHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_scan_lost_twice_is_ocr_unavailable_not_502(self):
        server = _load_server()

        async def lost(*_args):
            raise scan_worker.ScanLost("scan worker ended (exit -9)")

        transport = httpx.ASGITransport(app=server.app)
        with patch.object(server.scan_slots, "run", side_effect=lost):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                res = await client.post(
                    "/api/v2/reports?format=compact",
                    files={"image": ("lost.png", b"page-lost", "image/png")},
                )
                self.assertEqual(res.status_code, 503)
                self.assertEqual(
                    res.json()["detail"]["error_code"], "ocr_unavailable"
                )
                self.assertEqual(
                    res.headers["retry-after"],
                    str(server.OCR_UNAVAILABLE_RETRY_SEC),
                )
                # Not cached: the same photo is scanned again.
                again = await client.post(
                    "/api/v2/reports?format=compact",
                    files={"image": ("lost.png", b"page-lost", "image/png")},
                )
                self.assertEqual(again.status_code, 503)

    async def test_health_reports_the_worker(self):
        server = _load_server()
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            body = (await client.get("/ocr/health")).json()
        self.assertEqual(body["scan_worker"], {"enabled": False})
        self.assertIn("paddle", body["backends"])

    async def test_health_with_the_worker_starting(self):
        server = _load_server()
        fake = scan_worker.Supervisor("x", "x.py", 1)
        transport = httpx.ASGITransport(app=server.app)
        with patch.object(scan_worker, "SUPERVISOR", fake), patch.dict(
            os.environ, {"VAHINI_SCAN_WORKER": "1"}
        ):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                body = (await client.get("/ocr/health")).json()
        self.assertEqual(body["scan_worker"]["state"], "starting")
        self.assertEqual(body["backends"], {})
        self.assertEqual(body["layout_filter"]["built_tiers"], [])


if __name__ == "__main__":
    unittest.main()
