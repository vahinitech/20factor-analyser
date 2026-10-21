# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Work counts per benchmark page (scripts/perf_budgets.py, #250): how a
page's stage summary becomes counts, and that a page calling a reader
twice fails with the page, the counter and both numbers."""

import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
spec = importlib.util.spec_from_file_location(
    "perf_budgets", os.path.join(ROOT, "scripts", "perf_budgets.py")
)
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)


def summary(reader_calls=3, lines=4):
    """A stage summary as backend/server/perf.py's Scan.summary() gives it."""
    return {
        "decode": {
            "runs": 1,
            "wall_ms": 12.0,
            "cpu_ms": 11.0,
            "sizes": {"bytes": 1000, "pixels": 600},
            "counts": {},
        },
        "recovery": {
            "runs": 1,
            "wall_ms": 40.0,
            "cpu_ms": 39.0,
            "sizes": {"lines": lines},
            "counts": {"reader_calls": reader_calls},
        },
    }


class TestWork(unittest.TestCase):
    def test_counts_not_times(self):
        self.assertEqual(
            script.work(summary()),
            {
                "decode.bytes": 1000,
                "decode.pixels": 600,
                "decode.runs": 1,
                "recovery.lines": 4,
                "recovery.reader_calls": 3,
                "recovery.runs": 1,
            },
        )

    def test_a_reader_called_twice_is_a_rise_with_both_numbers(self):
        kept = {"P1": script.work(summary(reader_calls=3))}
        now = {"P1": script.work(summary(reader_calls=6))}
        rises, falls = script.work_changes(now, kept)
        self.assertEqual(rises, ["| P1 | recovery.reader_calls | 3 | 6 |"])
        self.assertEqual(falls, [])

    def test_a_new_count_rises_from_zero_and_a_gone_one_falls(self):
        kept = {"P1": {"a.runs": 1}}
        now = {"P1": {"b.runs": 1}}
        rises, falls = script.work_changes(now, kept)
        self.assertEqual(rises, ["| P1 | b.runs | 0 | 1 |"])
        self.assertEqual(falls, ["| P1 | a.runs | 1 | 0 |"])


class TestWorkReport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=R1732
        self.addCleanup(self.tmp.cleanup)
        self.folder = self.tmp.name

    def keep(self, pages):
        script._write_work(  # pylint: disable=protected-access
            os.path.join(self.folder, "work.json"), pages
        )

    def test_without_work_json_it_says_how_to_make_one(self):
        lines, rose = script.work_report(self.folder, {"P1": {"a.runs": 1}})
        self.assertFalse(rose)
        self.assertIn("update-work", "\n".join(lines))

    def test_a_rise_fails_and_names_the_page(self):
        self.keep({"P1": script.work(summary(reader_calls=3))})
        now = {"P1": script.work(summary(reader_calls=6))}
        lines, rose = script.work_report(self.folder, now)
        self.assertTrue(rose)
        text = "\n".join(lines)
        self.assertIn("1 work count(s) rose", text)
        self.assertIn("| P1 | recovery.reader_calls | 3 | 6 |", text)

    def test_a_fall_passes_and_asks_for_an_update(self):
        self.keep({"P1": script.work(summary(lines=5))})
        lines, rose = script.work_report(
            self.folder, {"P1": script.work(summary(lines=4))}
        )
        self.assertFalse(rose)
        self.assertIn("fell", "\n".join(lines))

    def test_the_same_work_matches(self):
        self.keep({"P1": script.work(summary())})
        lines, rose = script.work_report(
            self.folder, {"P1": script.work(summary())}
        )
        self.assertFalse(rose)
        self.assertIn("matches work.json", "\n".join(lines))
        with open(
            os.path.join(self.folder, "work.json"), encoding="utf-8"
        ) as f:
            self.assertEqual(json.load(f)["P1"]["recovery.runs"], 1)


if __name__ == "__main__":
    unittest.main()
