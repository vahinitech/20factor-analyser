# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Live reader speed and memory against main (scripts/live_timing.py,
#252): how the passes combine, when a pull request fails, and the table.
The reading itself runs in .github/workflows/benchmark-live.yml."""

import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
spec = importlib.util.spec_from_file_location(
    "live_timing", os.path.join(ROOT, "scripts", "live_timing.py")
)
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)

MIB = live.MIB


def side(seconds, mib=1000):
    return {
        f"p{i:02d}": {"seconds": s, "peak_bytes": mib * MIB}
        for i, s in enumerate(seconds)
    }


TWENTY = [2.0] * 18 + [3.0, 4.0]


class TestPercentile(unittest.TestCase):
    def test_nearest_rank(self):
        self.assertEqual(live.p95(TWENTY), 3.0)
        self.assertEqual(live.p95([5.0]), 5.0)
        self.assertIsNone(live.p95([]))


class TestCombine(unittest.TestCase):
    def test_fastest_time_and_highest_peak_of_pages_every_pass_read(self):
        one = {"pages": {"a": {"seconds": 3.0, "peak_bytes": 10}}}
        two = {
            "pages": {
                "a": {"seconds": 2.0, "peak_bytes": 30},
                "b": {"seconds": 1.0, "peak_bytes": 5},
            }
        }
        got = live.combine([one, two])
        self.assertEqual(got, {"a": {"seconds": 2.0, "peak_bytes": 30}})


class TestVerdict(unittest.TestCase):
    def test_same_speed_and_memory_passes(self):
        self.assertEqual(live.verdict(side(TWENTY), side(TWENTY)), [])

    def test_a_slower_tail_fails(self):
        slow = [2.0] * 18 + [3.6, 4.0]
        problems = live.verdict(side(TWENTY), side(slow))
        self.assertEqual(len(problems), 1)
        self.assertIn("95th percentile", problems[0])

    def test_a_slower_tail_inside_the_limit_passes(self):
        slow = [2.0] * 18 + [3.4, 4.0]
        self.assertEqual(live.verdict(side(TWENTY), side(slow)), [])

    def test_more_memory_fails(self):
        problems = live.verdict(side(TWENTY), side(TWENTY, mib=1110))
        self.assertEqual(len(problems), 1)
        self.assertIn("memory peak", problems[0])
        self.assertEqual(
            live.verdict(side(TWENTY), side(TWENTY, mib=1090)), []
        )

    def test_a_page_over_the_production_limit_fails(self):
        pr = side(TWENTY, mib=2400)
        pr["p03"]["peak_bytes"] = 2600 * MIB
        problems = live.verdict(side(TWENTY, mib=2500), pr)
        self.assertEqual(len(problems), 1)
        self.assertIn("p03", problems[0])
        self.assertIn("production limit", problems[0])


class TestMemory(unittest.TestCase):
    def test_cgroup_files_are_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, text in (("memory.peak", "123\n"), ("memory.max", "")):
                with open(os.path.join(tmp, name), "w", encoding="ascii") as f:
                    f.write(text or "456\n")
            self.assertEqual(live.memory_peak(tmp), 123)
            self.assertEqual(live.memory_limit(tmp), 456)
            with open(
                os.path.join(tmp, "memory.max"), "w", encoding="ascii"
            ) as f:
                f.write("max\n")
            self.assertIsNone(live.memory_limit(tmp))

    def test_without_cgroup_the_process_peak_is_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertGreater(live.memory_peak(tmp), 0)
            self.assertIsNone(live.memory_limit(tmp))


class TestCompare(unittest.TestCase):
    def files(self, tmp, name, pages):
        path = os.path.join(tmp, name + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"pages": pages}, f)
        return path

    def compare(self, main, pr, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.files(tmp, "m", main)
            p = self.files(tmp, "p", pr)
            out = io.StringIO()
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": ""}):
                with redirect_stdout(out):
                    code = live.compare([m], [p], **kwargs)
        return code, out.getvalue()

    def test_the_table_and_the_exit_code(self):
        code, text = self.compare(side(TWENTY), side(TWENTY))
        self.assertEqual(code, 0)
        self.assertIn("| p95 page time (s) | 3.00 | 3.00 | 1.00 |", text)
        self.assertIn("| p00 | 2.00 | 2.00 | 1000 | 1000 |", text)
        self.assertIn("Within 15% on time", text)

    def test_a_slower_pull_request_fails(self):
        code, text = self.compare(side(TWENTY), side([4.0] * 20))
        self.assertEqual(code, 1)
        self.assertIn("- 95th percentile", text)

    def test_the_weekly_run_only_reports(self):
        code, text = self.compare(
            side(TWENTY),
            side([4.0] * 20),
            report_only=True,
            base="last weekly run",
        )
        self.assertEqual(code, 0)
        self.assertIn("against last weekly run", text)
        self.assertIn("- 95th percentile", text)


if __name__ == "__main__":
    unittest.main()
