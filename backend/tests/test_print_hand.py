# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The print-or-handwriting line reader (print_hand.py) and its part in
classify.py, on crops of the committed sample pages."""

import os
import sys
import unittest

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import classify  # noqa: E402
import print_hand  # noqa: E402

FIXTURES = os.path.join(
    os.path.dirname(os.path.dirname(HERE)), "tests", "fixtures"
)


def page(name):
    return np.array(Image.open(os.path.join(FIXTURES, name)).convert("RGB"))


def gray(arr, box):
    x, y, w, h = box
    crop = arr[y : y + h, x : x + w].astype(np.float32)
    return (crop @ [0.299, 0.587, 0.114]).astype(np.uint8)


SAMPLE = "handwriting-sample.jpg"
RECEIPT = os.path.join("samples", "handwritten_printed_mixed_1.jpg")
# Neat handwriting on the sample page: PaddleOCR's box and the
# confidence it read the line with (0.93 and above, so the old override
# turned each into print).
HAND_LINES = [
    ("The quick brown fox jumps over", [167, 421, 539, 46], 0.932),
    ("Dabe has a big blue bag and a small", [174, 522, 545, 67], 0.952),
    ("Dodo and Piku write letters like bdfqm", [162, 641, 608, 63], 0.942),
]


class TestPrintHand(unittest.TestCase):
    def setUp(self):
        if print_hand.cv2 is None or print_hand.load() is None:
            self.skipTest("OpenCV or the weights are missing")

    def test_handwriting_reads_as_handwriting(self):
        arr = page(SAMPLE)
        for text, box, _score in HAND_LINES:
            p = print_hand.print_probability(gray(arr, box))
            self.assertLess(p, classify.READER_HAND_BELOW, text)

    def test_printed_heading_reads_as_print(self):
        arr = page(RECEIPT)
        p = print_hand.print_probability(gray(arr, [80, 62, 331, 34]))
        self.assertGreater(p, 0.5)

    def test_blank_crop_is_not_judged(self):
        blank = np.full((40, 300), 235, np.uint8)
        self.assertIsNone(print_hand.print_probability(blank))

    def test_same_crop_same_answer(self):
        crop = gray(page(SAMPLE), HAND_LINES[0][1])
        a = print_hand.print_probability(crop)
        b = print_hand.print_probability(crop.copy())
        self.assertEqual(a, b)

    def test_confident_neat_handwriting_stays_handwriting(self):
        # Read at 0.93-0.95, these lines were turned into print by the
        # high-confidence override before the reader could veto it.
        arr = page(SAMPLE)
        lines = [
            {"text": t, "score": sc, "box": b, "poly": []}
            for t, b, sc in HAND_LINES
        ]
        hand, printed = classify.split_lines(arr, lines)
        self.assertEqual(
            len(hand), len(HAND_LINES), [l["printed_prob"] for l in printed]
        )

    def test_without_weights_the_reader_has_no_say(self):
        self.assertIsNone(print_hand.load("/nonexistent/print_hand.json"))
        self.assertFalse(classify._reader_hand({"_model": None}))
        self.assertTrue(classify._reader_hand({"_model": 0.05}))


if __name__ == "__main__":
    unittest.main()
