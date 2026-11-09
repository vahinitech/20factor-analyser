# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Where a line's words break (computer_vision.line_word_breaks, #142).

When every letter stands apart, the text says where each word ends, so a
word gap narrower than the gaps between its letters is still found;
otherwise the widest gaps are the word breaks, as before."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from vision import computer_vision  # noqa: E402


def letters(*xs, w=10):
    """One ink blob per letter, starting at each x."""
    return [(x, 0, w, 20) for x in xs]


def breaks(text, comps):
    line = {"text": text, "box": [0, 0, 200, 20]}
    return computer_vision.line_word_breaks(None, line, comps=comps)


class TestWordBreaks(unittest.TestCase):
    def test_a_narrow_word_gap_is_found_from_the_text(self):
        # a b | c d: letters 4 apart, the words only 3.
        comps = letters(0, 14, 27, 41)
        self.assertEqual(breaks("ab cd", comps), [(3, 24, 27)])

    def test_every_word_end_is_placed(self):
        comps = letters(0, 14, 30, 44, 58, 75)
        self.assertEqual(breaks("ab cde f", comps), [(7, 68, 75), (6, 24, 30)])

    def test_without_a_letter_per_blob_the_widest_gaps_are_taken(self):
        # Five letters read, four blobs: joined writing.
        comps = letters(0, 14, 27, 41)
        self.assertEqual(breaks("ab cde", comps), [(4, 10, 14)])

    def test_a_word_without_letters_falls_back_to_the_widest_gaps(self):
        comps = letters(0, 14, 27, 41)
        self.assertEqual(breaks("ab - cd", comps), [(4, 10, 14), (4, 37, 41)])

    def test_one_word_has_no_break(self):
        self.assertIsNone(breaks("abcd", letters(0, 14, 27, 41)))

    def test_word_gaps_follow_the_same_breaks(self):
        line = {"text": "ab cd", "box": [0, 0, 200, 20]}
        comps = letters(0, 14, 27, 41)
        got = computer_vision.line_word_breaks(None, line, 2, comps)
        self.assertEqual([g for g, _l, _r in got], [3])


if __name__ == "__main__":
    unittest.main()
