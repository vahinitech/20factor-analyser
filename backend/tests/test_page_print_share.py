# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""A page is taken as printed only when at least two of its lines look
strongly printed (classify.PAGE_PRINT_MIN_LINES, #202).

On real phone photos one crisp line on a page of neat handwriting was
enough: borderline lines were then pulled to print and the top tenth of
the page was set aside as letterhead, so neat pages lost their best
lines. The line probabilities are fixed here, so only the page rule is
tested."""

import os
import sys
import unittest
from unittest import mock

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import classify  # noqa: E402

TOP = "my best day"
CRISP = "Name of the school"
BORDERLINE = ["we went to", "the big park", "and saw a", "small brown dog"]


class TestPagePrintShare(unittest.TestCase):
    def setUp(self):
        self.probs = {}
        for name, fake in (
            ("printed_probability", self.probability),
            ("_reader_says_print", lambda _crop: None),
        ):
            patcher = mock.patch.object(classify, name, side_effect=fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    def probability(self, _crop, text, _score, _box):
        # Even strokes, as neat handwriting and print both have.
        return self.probs[text], {"sw_cv": 0.2}

    def classify(self, rows):
        """rows: (text, reader confidence, printed probability), one per
        line, top to bottom. Returns {text: printed}."""
        self.probs = {text: prob for text, _sc, prob in rows}
        lines = [
            {"text": text, "score": sc, "box": [20, 10 + 90 * i, 300, 24]}
            for i, (text, sc, _prob) in enumerate(rows)
        ]
        arr = np.full((600, 400, 3), 245, np.uint8)
        classify.classify_lines(arr, lines)
        return {l["text"]: l["printed_hint"] for l in lines}

    def test_one_crisp_line_does_not_make_a_page_printed(self):
        got = self.classify(
            [(TOP, 0.7, 0.3), (CRISP, 0.99, 0.75)]
            + [(t, 0.7, 0.5) for t in BORDERLINE]
        )
        self.assertTrue(got[CRISP])
        self.assertFalse(got[TOP], "the top line is not letterhead")
        for text in BORDERLINE:
            self.assertFalse(got[text], text)

    def test_a_mostly_printed_page_still_pulls_borderline_lines(self):
        printed = [(f"Printed form label {i}", 0.99, 0.75) for i in range(4)]
        got = self.classify(
            [(TOP, 0.7, 0.3)] + printed + [(BORDERLINE[0], 0.7, 0.5)]
        )
        self.assertTrue(got[TOP], "the top band of a form is letterhead")
        self.assertTrue(got[BORDERLINE[0]])

    def test_two_crisp_lines_are_enough(self):
        printed = [(f"Printed form label {i}", 0.99, 0.75) for i in range(2)]
        rest = [(t, 0.7, 0.5) for t in BORDERLINE] + [(TOP, 0.7, 0.2)]
        got = self.classify(printed + rest)
        for text in BORDERLINE:
            self.assertTrue(got[text], text)
        self.assertFalse(got[TOP])
        self.assertEqual(classify.PAGE_PRINT_MIN_LINES, 2)


if __name__ == "__main__":
    unittest.main()
