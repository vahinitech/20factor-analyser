# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The history of main and the slow-drift check (scripts/bench_history.py,
#254): what a line holds, when a pull request fails or is flagged against
the last main runs, and the trend table."""

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
    "bench_history", os.path.join(ROOT, "scripts", "bench_history.py")
)
hist = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hist)


def line(**change):
    out = {
        "set": "uji-clean",
        "sha": "abc",
        "date": "2026-10-21T00:00:00Z",
        "cpu_s": 16.0,
        "peak_mib": 400.0,
        "work_total": 1000,
        "cer": 9.54,
        "sentences_found": 77,
        "overall_mean": 85.0,
        "eye": None,
        "catch": {"indented_line/10": 1.0, "tall_ascenders/6": 0.75},
    }
    out.update(change)
    return out


class TestCompare(unittest.TestCase):
    def test_no_history_passes(self):
        self.assertEqual(hist.compare(line(), []), ([], []))

    def test_the_same_numbers_pass(self):
        self.assertEqual(hist.compare(line(), [line()] * 10), ([], []))

    def test_creep_is_flagged_not_failed(self):
        fails, flags = hist.compare(line(cpu_s=19.0), [line()] * 10)
        self.assertEqual(fails, [])
        self.assertEqual(len(flags), 1)
        self.assertIn("replay CPU s 19.0 is 19% above", flags[0])

    def test_the_median_of_the_last_ten_is_the_reference(self):
        past = [line(cpu_s=30.0)] * 20 + [line(cpu_s=16.0)] * 10
        _fails, flags = hist.compare(line(cpu_s=18.0), past)
        self.assertEqual(flags, [])

    def test_every_fall_in_accuracy_fails(self):
        worse = line(
            cer=9.8,
            sentences_found=76,
            eye=0.5,
            catch={"indented_line/10": 0.9, "tall_ascenders/6": 0.75},
        )
        fails, _flags = hist.compare(worse, [line(eye=0.6)] * 10)
        self.assertEqual(len(fails), 4)
        self.assertIn("reading error rose", fails[0])
        self.assertIn("indented_line/10", fails[3])

    def test_a_fall_accepted_in_its_pull_request_is_flagged(self):
        now = line(catch={"indented_line/10": 0.9, "tall_ascenders/6": 0.7})
        ok = {"indented_line/10": {"rate": 0.9, "pr": 1, "why": "meant"}}
        fails, flags = hist.compare(now, [line()] * 10, ok)
        self.assertEqual(len(fails), 1)
        self.assertIn("tall_ascenders/6", fails[0])
        self.assertIn("accepted in #1, meant", flags[0])

    def test_a_fall_below_the_accepted_rate_still_fails(self):
        now = line(catch={"indented_line/10": 0.8, "tall_ascenders/6": 0.75})
        ok = {"indented_line/10": {"rate": 0.9, "pr": 1, "why": "meant"}}
        fails, _flags = hist.compare(now, [line()] * 10, ok)
        self.assertEqual(len(fails), 1)

    def test_accepted_falls_name_a_rate_a_pull_request_and_why(self):
        for key, ok in hist.accepted_falls().items():
            self.assertEqual(set(ok), {"rate", "pr", "why"}, key)
            self.assertIn(key, hist.catch_rates())
        self.assertEqual(hist.accepted_falls(os.path.join(HERE, "none")), {})

    def test_small_reading_moves_inside_the_gate_pass(self):
        fails, _flags = hist.compare(line(cer=9.7), [line()] * 10)
        self.assertEqual(fails, [])

    def test_missing_numbers_are_skipped(self):
        now = line(work_total=None, cer=None, eye=None)
        self.assertEqual(hist.compare(now, [line(work_total=None)]), ([], []))


class TestTrend(unittest.TestCase):
    def test_bars_go_from_lowest_to_highest(self):
        self.assertEqual(hist.spark([1, 2, 3, None, 8]), "▁▂▃ █")
        self.assertEqual(hist.spark([5, 5]), "▁▁")
        self.assertEqual(hist.spark([None]), "")

    def test_the_table_has_a_row_per_number_with_values(self):
        text = hist.trend([line(cpu_s=15.0), line()], line(cpu_s=17.0))
        self.assertIn("| replay CPU s | `▁▅█` | 17.0 |", text)
        self.assertNotIn("eye agreement", text)

    def test_an_empty_history_says_so(self):
        self.assertIn("No history yet", hist.trend([]))


class TestFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=R1732
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": ""})
        env.start()
        self.addCleanup(env.stop)

    def test_append_then_read(self):
        hist.append(self.tmp.name, line(sha="a"))
        hist.append(self.tmp.name, line(sha="b"))
        got = hist.history(self.tmp.name, "uji-clean")
        self.assertEqual([g["sha"] for g in got], ["a", "b"])
        self.assertEqual(hist.history(self.tmp.name, "other"), [])

    def test_catch_rates_come_from_the_committed_floors(self):
        rates = hist.catch_rates()
        self.assertEqual(rates["indented_line/10"], 1.0)
        missing = os.path.join(self.tmp.name, "x")
        self.assertEqual(hist.catch_rates(missing), {})

    def test_work_total_sums_every_count(self):
        folder = os.path.join(self.tmp.name, "w", "uji-clean")
        os.makedirs(folder)
        counts = {"P1": {"a.runs": 1, "b.lines": 4}, "P2": {"a.runs": 2}}
        path = os.path.join(folder, "work.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(counts, f)
        work = os.path.join(self.tmp.name, "w")
        self.assertEqual(hist.work_total("uji-clean", work), 7)
        self.assertIsNone(hist.work_total("uji-clean", None))

    def test_collect_reads_the_pages_results(self):
        path = os.path.join(ROOT, "benchmarks", "uji-clean", "expected.json")
        with open(path, encoding="utf-8") as f:
            pages = json.load(f)["pages"]
        got = hist.collect("uji-clean", cpu=(16.0, 400.0), pages=pages)
        self.assertEqual(got["cpu_s"], 16.0)
        self.assertGreaterEqual(got["sentences_found"], 77)
        self.assertIsInstance(got["cer"], float)
        self.assertIn("indented_line/10", got["catch"])
        self.assertIsNone(got["work_total"])

    def test_check_and_append_commands(self):
        now = os.path.join(self.tmp.name, "now.json")
        with open(now, "w", encoding="utf-8") as f:
            json.dump(line(), f)
        folder = os.path.join(self.tmp.name, "h")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(hist.main(["check", "--history", folder, now]), 0)
            self.assertEqual(
                hist.main(["append", "--history", folder, now]), 0
            )
            with open(now, "w", encoding="utf-8") as f:
                json.dump(line(sentences_found=70), f)
            self.assertEqual(hist.main(["check", "--history", folder, now]), 1)
        self.assertIn("written lines scored fell", out.getvalue())


if __name__ == "__main__":
    unittest.main()
