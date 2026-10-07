# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Capacity plan: slots from memory, cores and GPUs, and engine copies."""

import os
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

from backend.tests import test_report_access  # noqa: F401  (sys.path)
import capacity  # backend/ is on sys.path once the test helpers load
import ocr_backends

CONST = {
    "base_mb": 1100,
    "scan_mb": 600,
    "replica_mb": 200,
    "threads_per_scan": 2,
    "scans_per_gpu": 2,
    "queue_per_slot": 4,
}


class PlanTests(unittest.TestCase):
    def test_deploy_box_runs_one_scan(self):
        # 4 cores, 2.5 GB container: measured to fit one scan, not two.
        p = capacity.plan(2500, 4, 0, CONST)
        self.assertEqual((p["active"], p["queued"]), (1, 4))
        self.assertEqual(p["limited_by"], "memory")

    def test_more_memory_on_four_cores_allows_two(self):
        p = capacity.plan(3500, 4, 0, CONST)
        self.assertEqual(p["active"], 2)
        self.assertEqual(p["threads_per_engine"], 2)
        self.assertEqual(p["limited_by"], "cpu")

    def test_bigger_cpu_host_scales_with_cores(self):
        p = capacity.plan(12000, 8, 0, CONST)
        self.assertEqual(p["active"], 4)
        self.assertEqual(p["queued"], 16)
        self.assertEqual(p["threads_per_engine"], 2)

    def test_gpu_host_counts_gpus_not_cores(self):
        p = capacity.plan(30000, 8, 2, CONST)
        self.assertEqual(p["active"], 4)
        self.assertEqual(p["limited_by"], "gpu")
        self.assertIsNone(p["threads_per_engine"])

    def test_hard_cap_and_floor(self):
        self.assertEqual(capacity.plan(10**6, 256, 0, CONST)["active"], 16)
        self.assertEqual(capacity.plan(500, 1, 0, CONST)["active"], 1)


class DetectTests(unittest.TestCase):
    def _files(self, tree):
        root = tempfile.mkdtemp()
        for rel, text in tree.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="ascii") as f:
                f.write(text)
        return root

    def test_memory_from_cgroup_v2_then_host(self):
        root = self._files(
            {"cg/memory.max": str(2500 * 2**20), "meminfo": "x"}
        )
        self.assertEqual(
            capacity.memory_limit_mb(root + "/cg", root + "/meminfo"),
            (2500, "cgroup memory.max"),
        )
        root = self._files(
            {
                "cg/memory.max": "max",
                "meminfo": "MemTotal: 8000000 kB\nMemAvailable: 2048000 kB\n",
            }
        )
        self.assertEqual(
            capacity.memory_limit_mb(root + "/cg", root + "/meminfo"),
            (2000, "host MemAvailable"),
        )

    def test_cpu_quota_caps_cores(self):
        root = self._files({"cpu.max": "200000 100000"})
        with patch.object(os, "sched_getaffinity", return_value=set(range(8))):
            self.assertEqual(capacity.usable_cores(root), 2)

    def test_explicit_override_wins(self):
        with patch.dict(
            os.environ,
            {"VAHINI_MAX_ACTIVE_SCANS": "3", "VAHINI_MAX_QUEUED_SCANS": "7"},
        ):
            p = capacity.detect_plan()
        self.assertEqual((p["active"], p["queued"]), (3, 7))
        self.assertEqual(p["limited_by"], "VAHINI_MAX_ACTIVE_SCANS")


class EngineCopyTests(unittest.TestCase):
    def test_each_scan_thread_gets_its_own_engine(self):
        built = []

        class FakeOCR:
            def __init__(self, **kwargs):
                built.append(kwargs)

        fake = types.ModuleType("paddleocr")
        fake.PaddleOCR = FakeOCR
        engines = {}

        def grab(name):
            def run():
                engines.setdefault(name, []).append(
                    ocr_backends.get_engine("en")
                )

            t = threading.Thread(target=run, name=name)
            t.start()
            t.join()

        with patch.dict(sys.modules, {"paddleocr": fake}), patch.dict(
            ocr_backends._PADDLE_CFG, {"cpu_threads": 2}
        ):
            ocr_backends._build_engine_cached.cache_clear()
            ocr_backends._build_engine_replica.cache_clear()
            ocr_backends._ENGINE_FAIL_CACHE.clear()
            for name in ("scan_0", "scan_1", "scan_1", "other"):
                grab(name)
            ocr_backends._build_engine_cached.cache_clear()
            ocr_backends._build_engine_replica.cache_clear()

        self.assertIs(engines["scan_1"][0], engines["scan_1"][1])
        self.assertIsNot(engines["scan_0"][0], engines["scan_1"][0])
        self.assertIs(engines["scan_0"][0], engines["other"][0])
        self.assertEqual(len(built), 2)
        self.assertTrue(all(k.get("cpu_threads") == 2 for k in built))


if __name__ == "__main__":
    unittest.main()
