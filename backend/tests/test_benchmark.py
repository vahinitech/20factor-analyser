# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The benchmark's own rules (scripts/benchmark.py), and the left margin
it caught at 0 on two UJI pages (computer_vision.line_starts)."""

import importlib.util
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import computer_vision  # noqa: E402
from test_line_pieces import line, page_with_lines  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
spec = importlib.util.spec_from_file_location(
    "benchmark", os.path.join(ROOT, "scripts", "benchmark.py")
)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

SENTENCES = [
    "pihu sings while tara reads a story",
    "the quick brown fox jumps over the lazy dog",
]


def result(overall, f5=8.0, lines=("pihu sings",)):
    scores = {str(n): 9.0 for n in bench.SCORED}
    scores["5"] = f5
    return {
        "overall": overall,
        "scores": scores,
        "lines": list(lines),
        "sentences_found": 1,
        "repeats": 0,
        "unmatched": 0,
    }


class TestBenchmarkRules(unittest.TestCase):
    def test_a_line_read_twice_is_a_repeat(self):
        found, repeats, other = bench._line_check(  # pylint: disable=W0212
            [
                "seeta pihu sings while tara reads",
                "pihu sings while tara reads a stoy",
                "the quick brown fox",
                "xq",
            ],
            SENTENCES,
        )
        self.assertEqual((found, repeats, other), (2, 1, 1))

    def test_every_moved_score_is_listed(self):
        expected = {"pages": {"A": result(90), "B": result(80)}}
        now = {"A": result(90), "B": result(82, f5=7.1)}
        table = bench.diff_table(expected, now)
        self.assertIn("| B | overall | 80 | 82 |", table)
        self.assertIn("| B | factor 5 | 8.0 | 7.1 |", table)
        self.assertNotIn("| A |", table)
        self.assertEqual(bench.diff_table(expected, expected["pages"]), "")

    def test_limits_cannot_be_updated_away(self):
        meta = {"floor_sentences_found": 2, "eye_ranking": []}
        zero = result(70)
        zero["scores"]["8"] = 0.0
        twice = result(80)
        twice["repeats"] = 1
        problems = bench._limits(  # pylint: disable=W0212
            meta, {"A": zero, "B": twice}, {}
        )
        self.assertTrue(any("score 0" in p for p in problems))
        self.assertTrue(any("scored twice" in p for p in problems))
        self.assertFalse(any("floor" in p for p in problems))
        meta["floor_sentences_found"] = 3
        problems = bench._limits(meta, {"A": result(1)}, {})  # noqa
        self.assertTrue(any("under the floor" in p for p in problems))

    def test_agreement_with_the_eye(self):
        meta = {"eye_ranking": ["A", "B", "C"]}
        good = {"A": result(90), "B": result(80), "C": result(70)}
        bad = {"A": result(70), "B": result(80), "C": result(90)}
        self.assertEqual(bench.eye_agreement(meta, good), 1.0)
        self.assertEqual(bench.eye_agreement(meta, bad), -1.0)
        problems = bench._limits(  # pylint: disable=W0212
            {"floor_sentences_found": 0, **meta}, bad, {"eye_agreement": 1.0}
        )
        self.assertTrue(any("by eye" in p for p in problems))


class TestLineStarts(unittest.TestCase):
    def setUp(self):
        if computer_vision.cv2 is None:
            self.skipTest("OpenCV unavailable")

    def test_a_piece_with_unread_writing_before_it_is_not_a_start(self):
        # Row 2's words were not read except the last one; its left edge
        # is not where row 2 starts.
        arr = page_with_lines(
            [
                (60, [(80, 300), (330, 600), (630, 900)]),
                (140, [(80, 300), (330, 600), (630, 900)]),
                (220, [(80, 300), (330, 600), (630, 900)]),
            ]
        )
        lines = [
            line("the quick brown", [75, 52, 830, 46]),
            line("over", [625, 132, 280, 46]),
            line("seetha and rama", [75, 212, 830, 46]),
        ]
        starts = computer_vision.line_starts(arr, lines)
        self.assertEqual(
            [l["text"] for l in starts], [lines[0]["text"], lines[2]["text"]]
        )

    def test_a_piece_beside_its_line_is_not_a_start(self):
        arr = np.full((300, 1200, 3), 240, np.uint8)
        lines = [
            line("vahini and bheema", [80, 60, 700, 60]),
            line("day", [1100, 62, 80, 58]),
            line("pihu sings", [82, 160, 600, 60]),
        ]
        starts = computer_vision.line_starts(arr, lines)
        self.assertNotIn("day", [l["text"] for l in starts])

    def test_an_indented_line_with_blank_paper_before_it_is_a_start(self):
        arr = page_with_lines([(60, [(80, 300)]), (140, [(200, 400)])])
        lines = [
            line("dear pihu", [75, 52, 230, 46]),
            line("thank you", [195, 132, 210, 46]),
        ]
        starts = computer_vision.line_starts(arr, lines)
        self.assertEqual(len(starts), 2)


if __name__ == "__main__":
    unittest.main()
