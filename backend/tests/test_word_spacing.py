# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Word Spacing (factor 8) is a real score or "not measured", never 0
for a measurement that failed.

On 19 October 2026 four UJI test pages scored 0: the reader left the
middle words of a line unread, the two pieces either side stayed on one
row, and the space between them (seven line heights on UPV_W27) was
counted as one word gap."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import scoring  # noqa: E402
from test_letter_geometry import joined_page, lg  # noqa: E402

SENTENCES = [
    "seetha and rama practise slowly with care",
    "pihu sings while tara reads a story",
    "vahini and bheema write letters every day",
]


def word_spacing(arr, lines):
    result = scoring.build_analysis(arr, lines, {})
    return next(r for r in result.results if r.n == 8)


def piece(line, words, x0, x1):
    """Part of a line, as the reader gives it: its own box and text."""
    _x, y, _w, h = line["box"]
    return {
        "text": " ".join(words),
        "box": [x0, y, x1 - x0, h],
        "poly": [[x0, y], [x1, y], [x1, y + h], [x0, y + h]],
        "score": 0.9,
    }


class TestWordSpacing(unittest.TestCase):
    def setUp(self):
        if lg.cv2 is None:
            self.skipTest("OpenCV unavailable")
        self.arr, self.lines = joined_page(SENTENCES)

    def test_whole_lines_score_even_spacing_well(self):
        f8 = word_spacing(self.arr, self.lines)
        self.assertFalse(f8.unmeasured)
        self.assertGreater(f8.score, 7.0)

    def test_unread_middle_words_do_not_count_as_one_wide_gap(self):
        whole = word_spacing(self.arr, self.lines).score
        first = self.lines[0]
        # "seetha and" | (rama practise slowly unread) | "with care"
        split = [
            piece(first, ["seetha", "and"], 55, 245),
            piece(first, ["with", "care"], 640, 790),
        ] + self.lines[1:]
        f8 = word_spacing(self.arr, split)
        self.assertFalse(f8.unmeasured)
        self.assertGreater(f8.score, 6.0)
        self.assertLess(abs(f8.score - whole), 1.5)

    def test_no_measurable_gaps_is_not_measured(self):
        # One word per line: there is no gap to measure.
        arr, lines = joined_page(["hello", "world", "again"])
        f8 = word_spacing(arr, lines)
        self.assertTrue(f8.unmeasured)
        self.assertEqual(f8.unmeasured_kind, "insufficient")
        self.assertEqual(f8.value, "Not measured")


if __name__ == "__main__":
    unittest.main()
