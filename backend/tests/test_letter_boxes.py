# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Placing the reader's characters on the page (backend/vision/letter_boxes.py)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vision import (
    letter_boxes,
)  # noqa: E402  pylint: disable=wrong-import-position

# A level line 400 px wide from x=100, y=50 to 90, read over 40 columns.
POLY = [[100, 50], [500, 50], [500, 90], [100, 90]]
# The shape PaddleOCR returns: (text, [col_num, words, cols, kinds]).
REC = (
    "ab cd",
    [
        40.0,
        [["a", "b"], [" "], ["c", "d"]],
        [[3, 7], [12], [20, 24]],
        ["en", "sp", "en"],
    ],
)


class LetterBoxes(unittest.TestCase):
    def test_columns_read_in_order(self):
        chars, cols = letter_boxes.recognise_columns(REC)
        self.assertEqual(cols, 40.0)
        self.assertEqual(
            chars, [("a", 3), ("b", 7), (" ", 12), ("c", 20), ("d", 24)]
        )

    def test_letters_land_on_their_columns(self):
        chars, cols = letter_boxes.recognise_columns(REC)
        out = letter_boxes.letter_boxes(POLY, chars, cols)
        self.assertEqual([o["char"] for o in out], ["a", "b", "c", "d"])
        # Column 3 of 40 is (2.75 / 40) of the way along: x = 100 + 27.5.
        self.assertEqual(out[0]["x"], 127.5)
        for o in out:
            x, y, w, h = o["bbox"]
            self.assertTrue(x <= o["x"] <= x + w)
            self.assertEqual((y, h), (50, 40))
        # Neighbours meet half-way; a space does not widen them.
        a, b, c = out[0]["bbox"], out[1]["bbox"], out[2]["bbox"]
        self.assertEqual(a[0] + a[2], b[0])
        self.assertLess(b[0] + b[2], c[0])

    def test_tilted_line_follows_its_outline(self):
        poly = [[0, 0], [400, 40], [400, 80], [0, 40]]
        out = letter_boxes.letter_boxes(poly, [("a", 19), ("b", 20)], 40.0)
        # Half-way along, the top edge has dropped half of 40 px.
        self.assertLessEqual(abs(out[0]["bbox"][1] - 20), 1)

    def test_nothing_read_places_nothing(self):
        self.assertEqual(letter_boxes.recognise_columns(("abc", 0.9)), ([], 0))
        self.assertEqual(letter_boxes.recognise_columns(None), ([], 0))
        self.assertFalse(letter_boxes.letter_boxes(POLY, [], 0))
        self.assertFalse(letter_boxes.letter_boxes(None, [("a", 1)], 10.0))


if __name__ == "__main__":
    unittest.main()
