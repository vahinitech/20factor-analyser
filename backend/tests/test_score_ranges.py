# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The neat, ordinary and poor comparison (scripts/score_ranges.py,
#197): its statistics and its table, on numbers made up here."""

import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
spec = importlib.util.spec_from_file_location(
    "score_ranges", os.path.join(ROOT, "scripts", "score_ranges.py")
)
sr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sr)

NAMES = {"1": "Letter Formation", "8": "Word Spacing"}


def page(overall, **scores):
    return {
        "overall": overall,
        "scores": {k[1:]: v for k, v in scores.items()},
    }


class TestScoreRanges(unittest.TestCase):
    def test_stats_leave_out_what_was_not_measured(self):
        s = sr.stats([9.0, None, 7.0, 8.0])
        self.assertEqual(
            s, {"n": 3, "median": 8.0, "mean": 8.0, "min": 7.0, "max": 9.0}
        )

    def test_median_of_an_even_count(self):
        self.assertEqual(sr.stats([1, 2, 3, 4])["median"], 2.5)

    def test_nothing_measured(self):
        self.assertIsNone(sr.stats([None, None]))
        self.assertIsNone(sr.stats([]))

    def test_ranges_by_factor_and_group(self):
        groups = {
            "neat": [page(95, f8=9.5), page(93, f8=9.1)],
            "poor": [page(60, f8=4.0), page(55, f8=None)],
        }
        rows = sr.ranges(groups, [8])
        self.assertAlmostEqual(rows["8"]["neat"]["median"], 9.3)
        self.assertEqual(rows["8"]["poor"]["n"], 1)
        self.assertEqual(rows["overall"]["poor"]["mean"], 57.5)

    def test_table_has_a_row_per_factor_and_the_means(self):
        groups = {
            "neat": [page(95, f1=9.0, f8=9.5)],
            "uji": [page(85, f1=8.0, f8=8.0), page(80, f1=8.0, f8=7.0)],
        }
        rows = sr.ranges(groups, [1, 8])
        text = sr.table(rows, NAMES, {"neat": 1, "uji": 2})
        self.assertIn("| Factor | neat (1 pages) | uji (2 pages) |", text)
        self.assertIn("| 1 Letter Formation (reader) | 9.0 | 8.0 |", text)
        self.assertIn("| 8 Word Spacing | 9.5 | 7.5 (7.0 to 8.0) |", text)
        self.assertIn("| Overall | 95.0 | 82.5 (80.0 to 85.0) |", text)
        # The mean of the factor means: (9.0 + 9.5) / 2, (8.0 + 7.5) / 2.
        self.assertIn("| 9.25 | 7.75 |", text)

    def test_a_group_with_nothing_measured_shows_a_dash(self):
        rows = sr.ranges({"neat": [page(90, f8=None)]}, [8])
        text = sr.table(rows, {}, {"neat": 1})
        self.assertIn("| 8  | - |", text)
        self.assertEqual(text.splitlines()[-1], "| - |")
