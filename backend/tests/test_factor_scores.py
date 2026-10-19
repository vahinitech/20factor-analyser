# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Each factor measured from the ink moves with what it is named for
(scoring._score_factor_map), and falls back to its older stand-in only
when the page is too small to measure. The planted-page check of the
same factors is scripts/factor_tests.py."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import scoring  # noqa: E402

BASE = {
    "avg_score": 0.9,
    "height_cv": 0.1,
    "char_w_cv": 0.2,
    "loop_ratio": 0.3,
    "width_cv": 0.1,
    "size_cv": 0.1,
    "size_basis": "words",
    "words_off_size": 0.0,
    "tall_ratio": 0.34,
    "line_slope_abs": 0.5,
    "line_slope_std": 0.5,
    "word_gap_cv": 0.3,
    "word_gap_count": 10,
    "left_cv": 0.02,
    "ink_cv": 0.2,
    "n_chars": 100,
    "n_words": 20,
    "digits_ratio": 0.0,
    "bowl_share": 1.0,
    "letter_gap_cv": 0.5,
    "line_wave": 0.01,
    "slant_std": 6.0,
    "words_off_line": 0.0,
}


def score(n, **change):
    return scoring._score_factor_map(  # pylint: disable=protected-access
        {**BASE, **change}
    )[n]


class TestFactorScores(unittest.TestCase):
    def test_open_bowls_lower_loop_closure(self):
        self.assertEqual(score(3), 10.0)
        self.assertLess(score(3, bowl_share=0.6), 7.0)

    def test_a_sunken_word_lowers_baseline_alignment(self):
        self.assertLess(score(7, words_off_line=0.05), score(7) - 0.5)

    def test_one_word_off_size_lowers_size_consistency(self):
        self.assertLess(score(5, words_off_size=0.04), score(5) - 0.5)

    def test_uneven_letter_gaps_lower_letter_spacing(self):
        self.assertLess(score(9, letter_gap_cv=1.0), score(9) - 1.5)

    def test_a_wavy_line_lowers_line_straightness(self):
        self.assertLess(score(11, line_wave=0.2), score(11) - 3.0)

    def test_uneven_lean_lowers_slant_consistency(self):
        self.assertLess(score(17, slant_std=15.0), score(17) - 2.0)

    def test_stand_ins_when_too_little_to_measure(self):
        for key, n in (
            ("bowl_share", 3),
            ("letter_gap_cv", 9),
            ("slant_std", 17),
        ):
            self.assertEqual(
                score(n, **{key: None}),
                scoring._score_factor_map(  # pylint: disable=W0212
                    {**BASE, key: None}
                )[n],
            )
        # Loop closure falls back to the share of loop letters read.
        self.assertEqual(score(3, bowl_share=None, loop_ratio=0.14), 5.0)


if __name__ == "__main__":
    unittest.main()
