# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Stage timings and call budgets (backend/perf.py, #229).

A scan answers with a Server-Timing header of stage names and
milliseconds, /health keeps each stage's p50 and p95 and still matches
its schema, a page over a budget is reported and fails the CI check,
and no text, name or address reaches the header, /health or the log
line. Measuring never changes a result: the same page gives the same
answer timed or not (#112).
"""

import contextlib
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(SERVER_DIR)
sys.path.insert(0, SERVER_DIR)
sys.path.insert(0, HERE)

import computer_vision  # noqa: E402
import contract_schemas  # noqa: E402
import line_recovery  # noqa: E402
import perf  # noqa: E402
import recognizer  # noqa: E402
from test_escalation import _Fake, _line, _noise_page  # noqa: E402
from test_server_pipeline import _hand_strip, _load_server  # noqa: E402

# White-box tests deliberately reach into module-private helpers below.
# pylint: disable=protected-access

# What a visitor's page may hold, which must never be recorded.
NAME = "Quokkasundari"
ADDRESS = "203.0.113.77"
_TOKEN = re.compile(r"^[a-z0-9._-]+$")
_HEADER = re.compile(
    r"^[a-z0-9._-]+;dur=\d+\.\d(, [a-z0-9._-]+;dur=\d+\.\d)*$"
)


def _quiet(line, flush=False):  # pylint: disable=unused-argument
    return None


class _Batch(_Fake):  # pylint: disable=too-few-public-methods
    """An engine that reads a page's lines in one call."""

    def recognize_crops(self, crops):
        return [self.recognize_crop(crop) for crop in crops]


def _numbers_only(test, value, where):
    """Every key is a name token and every leaf a number, or a name
    token where a breach names its budget and stage."""
    if isinstance(value, dict):
        for key, item in value.items():
            test.assertRegex(key, _TOKEN, where)
            _numbers_only(test, item, where)
    elif isinstance(value, list):
        for item in value:
            _numbers_only(test, item, where)
    elif not isinstance(value, (int, float)):
        test.assertRegex(str(value), _TOKEN, where)


class TestStages(unittest.TestCase):
    def test_outside_a_scan_nothing_is_recorded(self):
        with perf.stage("decode", pixels=10) as step:
            step.size(pixels=12)
            perf.count("reader_calls")
        self.assertIs(step, perf._NO_STAGE)

    def test_a_stage_keeps_time_sizes_and_counts(self):
        with perf.scan() as record:
            with perf.stage("decode", bytes=100) as step:
                step.size(pixels=np.int64(12))
                perf.count("reader_calls")
                perf.count("reader_calls", 2)
            with perf.stage("decode"):
                pass
        row = record.summary()["decode"]
        self.assertEqual(row["runs"], 2)
        self.assertEqual(row["sizes"], {"bytes": 100, "pixels": 12})
        self.assertEqual(row["counts"], {"reader_calls": 3})
        self.assertGreaterEqual(row["wall_ms"], 0.0)
        self.assertGreaterEqual(row["cpu_ms"], 0.0)

    def test_only_numbers_are_kept(self):
        with perf.scan() as record:
            with perf.stage(
                "Passage Check",
                text=NAME,
                words=[NAME],
                flag=True,
                nothing=None,
                nan=float("nan"),
                lines=3,
            ):
                pass
        summary = record.summary()
        self.assertEqual(list(summary), ["passage-check"])
        self.assertEqual(summary["passage-check"]["sizes"], {"lines": 3})
        self.assertNotIn(NAME, json.dumps(summary))

    def test_an_error_passes_through_and_the_stage_is_kept(self):
        with perf.scan() as record:
            with self.assertRaises(KeyError):
                with perf.stage("scoring"):
                    raise KeyError("raised by the scorer")
        self.assertEqual(record.summary()["scoring"]["runs"], 1)

    def test_memory_change_where_the_container_reports_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "memory.current")
            with open(path, "w", encoding="ascii") as f:
                f.write("1048576\n")
            with mock.patch.object(perf, "MEMORY_CURRENT", path):
                with perf.scan() as record:
                    with perf.stage("decode"):
                        with open(path, "w", encoding="ascii") as f:
                            f.write("3145728\n")
            self.assertEqual(record.summary()["decode"]["mem_mb"], 2.0)
        with mock.patch.object(perf, "MEMORY_CURRENT", path):
            with perf.scan() as record:
                with perf.stage("decode"):
                    pass
        self.assertNotIn("mem_mb", record.summary()["decode"])

    def test_rolling_p50_and_p95(self):
        rolling = perf.Rolling(window=4)
        for ms in (10.0, 20.0, 30.0, 40.0, 50.0):
            rolling.add({"decode": {"wall_ms": ms, "cpu_ms": ms / 2}})
        rolling.add({}, [{"budget": "cpu_ms", "stage": "decode"}])
        snap = rolling.snapshot()
        self.assertEqual(snap["scans"], 6)
        self.assertEqual(
            snap["stages"]["decode"],
            {
                "samples": 4,
                "wall_ms_p50": 30.0,
                "wall_ms_p95": 50.0,
                "cpu_ms_p50": 15.0,
                "cpu_ms_p95": 25.0,
            },
        )
        self.assertEqual(snap["budget_breaches"], {"cpu_ms:decode": 1})

    def test_only_a_scan_is_logged_and_kept(self):
        rolling, lines = perf.Rolling(), []

        def emit(line, flush=False):  # pylint: disable=unused-argument
            lines.append(line)

        with perf.scan() as record:
            with perf.stage("practice"):
                pass
        header = perf.finish(record, 4.0, rolling=rolling, emit=emit)
        self.assertRegex(header, _HEADER)
        self.assertTrue(header.endswith("total;dur=4.0"))
        self.assertEqual((lines, rolling.snapshot()["scans"]), ([], 0))
        with perf.scan() as record:
            with perf.stage("decode", pixels=4):
                pass
        perf.finish(record, rolling=rolling, emit=emit)
        self.assertEqual(rolling.snapshot()["scans"], 1)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("[perf] "))

    def test_a_measuring_fault_never_reaches_the_visitor(self):
        with perf.scan() as record:
            with perf.stage("decode"):
                pass
        with mock.patch.object(perf, "breaches", side_effect=OSError):
            self.assertEqual(perf.finish(record, emit=_quiet), "")


class TestBudgets(unittest.TestCase):
    def test_the_budgets_file_matches_the_code(self):
        budgets = perf.load_budgets()
        self.assertEqual(
            budgets["decoded_megapixels"] * 1000000,
            computer_vision.MAX_DECODE_PIXELS,
        )
        self.assertEqual(
            budgets["recovery_reader_calls"],
            line_recovery.MAX_READS * line_recovery.ROUNDS,
        )
        self.assertTrue(all(cap > 0 for cap in budgets["cpu_ms"].values()))

    def test_reading_every_word_breaks_the_reader_budget(self):
        with perf.scan() as record:
            with perf.stage("ladder", lines=2, rungs=2):
                with perf.stage("read.trocr-latn-cpu", lines=2):
                    for _word in range(6):
                        perf.count("reader_calls")
        broken = perf.breaches(record.summary())
        self.assertEqual(
            broken,
            [
                {
                    "budget": "reader_calls",
                    "stage": "read",
                    "value": 6.0,
                    "limit": 4,
                }
            ],
        )

    def test_two_batched_calls_on_one_rung_break_the_model_budget(self):
        with perf.scan() as record:
            with perf.stage("ladder", lines=4, rungs=2):
                for _call in range(2):
                    with perf.stage("read.llm-latn-remote", lines=2):
                        perf.count("reader_calls")
                        perf.count("model_calls")
        broken = perf.breaches(record.summary())
        self.assertEqual(
            [(b["budget"], b["stage"]) for b in broken],
            [("model_calls", "read.llm-latn-remote")],
        )

    def test_size_recovery_and_cpu_budgets(self):
        budgets = dict(perf.BUDGETS, cpu_ms={"scoring": -1})
        with perf.scan() as record:
            with perf.stage("decode", pixels=24000001):
                pass
            with perf.stage("recovery"):
                perf.count("reader_calls", 25)
            with perf.stage("scoring"):
                pass
        broken = perf.breaches(record.summary(), budgets)
        self.assertEqual(
            [b["budget"] for b in broken],
            ["decoded_pixels", "recovery_reader_calls", "cpu_ms"],
        )

    def _climb(self, engine):
        raw, arr = _noise_page()
        lines = [_line(f"line {i}", i) for i in range(3)]
        with mock.patch.object(
            recognizer.ocr_backends, "get_backend", {"trocr": engine}.get
        ):
            with perf.scan() as record:
                recognizer.refine_handwriting_text(raw, arr, lines, "trocr")
        return record.summary()

    def test_a_climb_one_line_at_a_time_is_within_budget(self):
        summary = self._climb(_Fake([("a b", 0.9)] * 3))
        self.assertEqual(summary["ladder"]["sizes"], {"lines": 3, "rungs": 2})
        self.assertEqual(
            summary["read.trocr-latn-cpu"]["counts"], {"reader_calls": 3}
        )
        self.assertEqual(perf.breaches(summary), [])

    def test_a_batched_climb_is_one_model_call(self):
        summary = self._climb(_Batch([("a b", 0.9)] * 3))
        self.assertEqual(
            summary["read.trocr-latn-cpu"]["counts"],
            {"reader_calls": 1, "model_calls": 1},
        )
        self.assertEqual(perf.breaches(summary), [])

    def test_the_ci_check_fails_on_a_benchmark_page_over_budget(self):
        spec = importlib.util.spec_from_file_location(
            "perf_budgets", os.path.join(ROOT, "scripts", "perf_budgets.py")
        )
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        tight = dict(perf.BUDGETS, cpu_ms={"decode": -1})
        quiet = contextlib.redirect_stdout(io.StringIO())
        with mock.patch.dict(os.environ), quiet:
            os.environ.pop("GITHUB_STEP_SUMMARY", None)
            with mock.patch.object(perf, "BUDGETS", tight):
                lines, failed = script.check("uji-clean", limit=1)
            for answer in (1, 0):
                with mock.patch.object(
                    script, "check", return_value=(["x"], answer)
                ):
                    self.assertEqual(script.main(["check"]), answer)
        self.assertGreaterEqual(failed, 1)
        self.assertIn("| cpu_ms | decode |", "\n".join(lines))
        # The page's stubs were put back.
        name = getattr(recognizer.collect_lines, "__qualname__", "")
        self.assertFalse(name.startswith("_replay"))


class TestServerTimings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_server()
        from fastapi.testclient import TestClient

        cls.client = TestClient(cls.mod.app)
        cls.sent = 0

        def fake_collect(_arr_in, _lang):
            box = [10, 150, 360, 40]
            poly = [[10, 150], [370, 150], [370, 190], [10, 190]]
            return (
                [
                    {
                        "text": f"{NAME} wrote this",
                        "score": 0.72,
                        "box": box,
                        "poly": poly,
                        "lang": "en",
                    }
                ],
                "",
                "paddle",
                {},
            )

        cls.addClassCleanup(
            setattr,
            cls.mod.recognizer,
            "collect_lines",
            cls.mod.recognizer.collect_lines,
        )
        cls.mod.recognizer.collect_lines = fake_collect

    def _page(self):
        """A page no request has sent before, so the response cache
        never answers it and every request scans."""
        type(self).sent += 1
        arr = np.full((240, 380, 3), 255, np.uint8)
        arr[150:190, 10:370] = _hand_strip(360, 40)
        arr[5, 5] = 200 - self.sent
        buf = io.BytesIO()
        Image.fromarray(arr).save(buf, format="PNG")
        return buf.getvalue()

    def _report(self):
        out = io.StringIO()
        page = self._page()
        with contextlib.redirect_stdout(out):
            response = self.client.post(
                "/report-python",
                files={"image": ("page.png", page, "image/png")},
                data={
                    "lang": "en",
                    "expected_text": f"{NAME} wrote this",
                },
                headers={"X-Real-IP": ADDRESS, "X-Forwarded-For": ADDRESS},
            )
        return response, out.getvalue()

    def test_a_scan_has_a_server_timing_header(self):
        response, _log = self._report()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        header = response.headers["Server-Timing"]
        self.assertRegex(header, _HEADER)
        names = [part.split(";")[0] for part in header.split(", ")]
        for name in (
            "decode",
            "merge",
            "layout",
            "printed",
            "join",
            "ladder",
            "passage",
            "evidence",
            "features",
            "scoring",
            "total",
        ):
            self.assertIn(name, names)

    def test_health_keeps_p50_and_p95_and_matches_its_schema(self):
        self._report()
        body = self.client.get("/health").json()
        timings = body["stage_timings"]
        self.assertGreaterEqual(timings["scans"], 1)
        for name in ("decode", "scoring"):
            row = timings["stages"][name]
            self.assertLessEqual(row["wall_ms_p50"], row["wall_ms_p95"])
        self.assertEqual(contract_schemas.errors("health", body), [])

    def test_no_text_name_or_address_is_recorded(self):
        response, log = self._report()
        health = json.dumps(self.client.get("/health").json()["stage_timings"])
        perf_lines = [l for l in log.splitlines() if l.startswith("[perf] ")]
        self.assertTrue(perf_lines)
        for where, text in (
            ("Server-Timing", response.headers.get("Server-Timing", "")),
            ("/health", health),
            ("log", "\n".join(perf_lines)),
        ):
            self.assertNotIn(NAME.lower(), text.lower(), where)
            self.assertNotIn(ADDRESS, text, where)
            self.assertNotIn("wrote", text, where)
        for line in perf_lines:
            body = json.loads(line[len("[perf] ") :])
            _numbers_only(self, body, "log")

    def test_timing_never_changes_the_report(self):
        raw = self._page()
        mod = self.mod

        def run():
            arr = mod._to_numpy(raw)
            return mod._report_python_process(
                arr, raw, "en", "", True, mod.profiles.resolve()
            )

        untimed = run()
        with perf.scan() as record:
            timed = run()
        self.assertIn("scoring", record.summary())
        self.assertEqual(repr(timed), repr(untimed))


if __name__ == "__main__":
    unittest.main()
