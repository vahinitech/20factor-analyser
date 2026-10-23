# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Which words Size Consistency compares, and with what (#304): scraps,
impossible readings and numbers left out, each word against the size
expected where it sits on the page."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from vision import letter_geometry as lg

PAGE_H = 1000


def _line(y, xheight, words, box_h=60.0):
    """A line at page row y: its box, and its measured geometry with one
    word per (small-letter height, has a digit) pair."""
    line = {"box": [50.0, float(y), 600.0, box_h]}
    geo = {
        "xheight": xheight,
        "words": [
            {"xheight": h, "bbox": [60 + 100 * i, y, 80, box_h], "digits": d}
            for i, (h, d) in enumerate(words)
        ],
    }
    return line, geo


def _sizes(rows):
    lines = [l for l, _ in rows]
    geo = [g for _, g in rows]
    return [
        round(wd["xheight"] / want, 2)
        for _, wd, want in lg.size_words(lines, geo, PAGE_H)
    ]


EVEN = [(20.0, False)] * 3


class SizeWords(unittest.TestCase):
    def test_even_words_measure_even(self):
        rows = [_line(100 * i, 20.0, EVEN) for i in range(1, 5)]
        self.assertEqual(_sizes(rows), [1.0] * 12)

    def test_a_scrap_is_not_a_line(self):
        rows = [_line(100 * i, 20.0, EVEN) for i in range(1, 5)]
        rows.append(_line(600, 6.0, [(6.0, False)], box_h=12.0))
        self.assertEqual(len(_sizes(rows)), 12)

    def test_a_band_taller_than_its_box_is_left_out(self):
        rows = [_line(100 * i, 20.0, EVEN) for i in range(1, 5)]
        rows.append(_line(600, 90.0, [(90.0, False)] * 3))
        self.assertEqual(len(_sizes(rows)), 12)

    def test_numbers_are_left_out(self):
        rows = [_line(100 * i, 20.0, EVEN) for i in range(1, 5)]
        rows.append(_line(600, 20.0, [(32.0, True), (20.0, False)]))
        self.assertEqual(_sizes(rows), [1.0] * 13)

    def test_a_camera_angle_is_taken_out(self):
        # Small letters grow steadily down the page, as a phone held at an
        # angle makes them: every word is as expected where it sits.
        rows = [
            _line(100 * i, 12.0 + 4.0 * i, [(12.0 + 4.0 * i, False)] * 3)
            for i in range(1, 6)
        ]
        self.assertEqual(_sizes(rows), [1.0] * 15)

    def test_one_big_word_still_stands_out(self):
        rows = [_line(100 * i, 20.0, EVEN) for i in range(1, 5)]
        rows.append(_line(600, 20.0, [(20.0, False), (32.0, False)]))
        self.assertEqual(max(_sizes(rows)), 1.6)

    def test_too_few_words_measure_nothing(self):
        rows = [_line(100, 20.0, [(20.0, False)] * 2)]
        self.assertEqual(_sizes(rows), [])


if __name__ == "__main__":
    unittest.main()
