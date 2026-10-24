# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Line recovery's second round does not read again a place the first
round read without keeping a word (23 October 2026: 27 of 41 second-round
reads on the stage photos, 63 seconds, none of them keeping a word)."""

import os
import sys
import unittest
from unittest import mock

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from reading import line_recovery  # noqa: E402

ARR = np.full((400, 1200, 3), 255, np.uint8)
FOUND = [{"text": "little Vahini writes", "box": [40, 40, 600, 40], "score": 0.95}]
EMPTY = {"box": [700, 150, 300, 40], "points": np.array([[700, 150], [999, 189]])}
WORD = {"box": [40, 250, 340, 40], "points": np.array([[40, 250], [339, 289]])}
# Round two finds the empty place again, a pixel off, and a new one.
EMPTY_AGAIN = {"box": [701, 150, 299, 40], "points": EMPTY["points"]}
NEW = {"box": [400, 320, 340, 40], "points": np.array([[400, 320], [739, 359]])}


def word(text, w, h):
    return {"text": text, "score": 0.9, "poly": [[5, 5], [w - 5, 5], [w - 5, h - 5], [5, h - 5]]}


class TestRecoveryRepeats(unittest.TestCase):
    def run_rounds(self):
        rounds = iter([[EMPTY, WORD], [EMPTY_AGAIN, NEW]])
        calls = []

        def read(crop, _lang):
            calls.append(crop.shape[:2])
            h, w = crop.shape[:2]
            # The empty place's crop is the narrow one; the others hold a word.
            return [] if w < 330 else [word("Bheema", w, h)]

        with mock.patch.object(line_recovery, "missed_regions", lambda _a, _l: next(rounds, [])):
            lines = line_recovery.add_missed(ARR, [dict(l) for l in FOUND], read, "en")
        return calls, lines

    def test_a_place_read_for_nothing_is_not_read_again(self):
        calls, lines = self.run_rounds()
        # Round one reads EMPTY (nothing) and WORD; round two only NEW.
        self.assertEqual(len(calls), 3)
        self.assertEqual(sum(1 for l in lines if l.get("recovered")), 2)

    def test_same_place_is_overlap(self):
        self.assertGreater(line_recovery._same_place(EMPTY["box"], EMPTY_AGAIN["box"]), 0.95)
        self.assertEqual(line_recovery._same_place(EMPTY["box"], NEW["box"]), 0.0)


if __name__ == "__main__":
    unittest.main()
