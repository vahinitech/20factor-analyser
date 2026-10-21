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
from scoring_parts.features import (  # noqa: E402
    _letter_spacing,
    _margin_spread,
    _word_spacing,
)

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
    "word_gap_spread": 0.1,
    "word_gaps_odd": 0.0,
    "word_gap_count": 10,
    "left_cv": 0.02,
    "left_spread": 0.002,
    "ink_cv": 0.2,
    "n_chars": 100,
    "n_words": 20,
    "digits_ratio": 0.0,
    "bowl_share": 1.0,
    "letter_gap_cv": 0.5,
    "letter_gap_spread": 0.05,
    "letter_gaps_odd": 0.0,
    "words_spaced_off": 0.0,
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
        self.assertLess(score(9, letter_gap_spread=0.2), score(9) - 1.5)

    def test_odd_letter_gaps_and_spaced_words_lower_letter_spacing(self):
        self.assertLess(score(9, letter_gaps_odd=0.05), score(9) - 0.2)
        self.assertLess(score(9, words_spaced_off=0.04), score(9) - 1.0)

    def test_uneven_word_gaps_lower_word_spacing(self):
        self.assertLess(score(8, word_gap_spread=0.6), score(8) - 4.0)
        # One odd gap among twenty costs a point.
        self.assertAlmostEqual(score(8, word_gaps_odd=0.05), score(8) - 1.0)

    def test_a_wavy_line_lowers_line_straightness(self):
        self.assertLess(score(11, line_wave=0.2), score(11) - 3.0)

    def test_uneven_lean_lowers_slant_consistency(self):
        self.assertLess(score(17, slant_std=15.0), score(17) - 2.0)

    def test_stand_ins_when_too_little_to_measure(self):
        for key, n in (
            ("bowl_share", 3),
            ("letter_gap_spread", 9),
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


class TestMarginSpread(unittest.TestCase):
    """Margin Discipline (factor 10) from the rows' starts (#201)."""

    def test_an_even_margin_scores_full_marks(self):
        self.assertEqual(_margin_spread([0.1, 0.1, 0.1, 0.1]), 0.0)
        self.assertEqual(score(10, left_spread=0.0), 10.0)

    def test_one_indented_line_among_four_is_counted(self):
        spread = _margin_spread([0.1, 0.1, 0.1, 0.143])
        self.assertAlmostEqual(spread, 0.043 / 4)
        self.assertLess(score(10, left_spread=spread), 9.0)

    def test_a_date_or_title_far_right_is_left_out(self):
        self.assertEqual(_margin_spread([0.1, 0.1, 0.1, 0.7]), 0.0)
        self.assertEqual(_margin_spread([0.1, 0.5]), 0.0)

    def test_a_line_starting_left_of_the_margin_is_counted(self):
        self.assertAlmostEqual(_margin_spread([0.1, 0.1, 0.1, 0.0]), 0.025)

    def test_the_margin_position_does_not_change_the_spread(self):
        near = _margin_spread([0.02, 0.03, 0.02, 0.04])
        far = _margin_spread([0.32, 0.33, 0.32, 0.34])
        self.assertAlmostEqual(near, far)

    def test_no_rows_is_no_spread(self):
        self.assertEqual(_margin_spread([]), 0.0)
        self.assertEqual(_margin_spread([0.3]), 0.0)

    def test_the_score_falls_with_the_spread(self):
        self.assertEqual(score(10, left_spread=0.025), 5.0)
        self.assertEqual(score(10, left_spread=0.2), 0.0)


if __name__ == "__main__":
    unittest.main()


class TestSpacing(unittest.TestCase):
    """Word and Letter Spacing (factors 8 and 9) from the gaps (#197)."""

    def test_even_word_gaps_have_no_spread(self):
        self.assertEqual(_word_spacing([0.2, 0.2, 0.2, 0.2]), (0.0, 0.0))

    def test_word_spread_is_the_mean_distance_from_the_median(self):
        spread, odd = _word_spacing([0.16, 0.2, 0.24, 0.2])
        self.assertAlmostEqual(spread, 0.1)
        self.assertEqual(odd, 0.0)

    def test_a_narrow_or_wide_word_gap_stands_out(self):
        even = [0.2] * 9
        self.assertAlmostEqual(_word_spacing(even + [0.05])[1], 0.1)
        self.assertAlmostEqual(_word_spacing(even + [0.6])[1], 0.1)
        # A gap a little narrower is not odd.
        self.assertEqual(_word_spacing(even + [0.12])[1], 0.0)

    def test_too_few_word_gaps_measure_nothing(self):
        self.assertEqual(_word_spacing([0.2, 0.9]), (0.0, 0.0))
        self.assertEqual(_word_spacing([0.0, 0.0, 0.0]), (0.0, 0.0))

    def test_even_letter_gaps_score_full_marks(self):
        spread, odd, off = _letter_spacing([[0.2, 0.2, 0.2]] * 3)
        self.assertEqual((spread, odd, off), (0.0, 0.0, 0.0))

    def test_a_word_compared_with_itself(self):
        # Each word even, one spaced a little wider than the other: no
        # spread, nothing odd, no word off.
        spread, odd, off = _letter_spacing([[0.2, 0.2, 0.2], [0.3, 0.3]])
        self.assertEqual((spread, odd, off), (0.0, 0.0, 0.0))

    def test_one_wide_gap_inside_a_word_is_odd(self):
        spread, odd, _off = _letter_spacing([[0.2, 0.2, 0.2, 0.6], [0.2] * 4])
        self.assertAlmostEqual(odd, 1 / 8)
        # One gap cannot set the spread; it is counted as odd instead.
        self.assertEqual(spread, 0.0)

    def test_a_word_written_with_its_letters_apart(self):
        words = [[0.2, 0.2, 0.2]] * 4 + [[0.6, 0.6, 0.6]]
        self.assertAlmostEqual(_letter_spacing(words)[2], 0.2)

    def test_tiny_gaps_are_compared_with_the_floor(self):
        # Touching letters (gaps 0 and 0.02) are not a doubling.
        spread, odd, _off = _letter_spacing([[0.0, 0.02, 0.01]] * 2)
        self.assertLess(spread, 0.2)
        self.assertEqual(odd, 0.0)

    def test_too_few_letter_gaps_measure_nothing(self):
        self.assertEqual(_letter_spacing([[0.2], [0.2, 0.2]]), (None,) * 3)
        # Five gaps, but no word with two: nothing to compare inside.
        self.assertEqual(_letter_spacing([[0.2]] * 5), (None,) * 3)
