# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The overall score out of 100 (owner, 23 October 2026, #304): points
for factors 1, 7, 5, 11 and 17 only; every other factor is a practice
finding and cannot move it."""

import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import scoring


def _results(scores, unmeasured=()):
    """Twenty factors, each scoring scores.get(n, 5.0) out of ten."""
    return [
        SimpleNamespace(
            n=n,
            sec=scoring._FACTOR_META[n][0],
            score=0.0 if n in unmeasured else scores.get(n, 5.0),
            unmeasured=n in unmeasured,
        )
        for n in range(1, 21)
    ]


PHOTO = (13, 14, 15, 16)  # Dynamics: not measured from a photo


class OverallScore(unittest.TestCase):
    def test_the_points_add_up_to_100(self):
        self.assertEqual(sum(scoring._OVERALL_POINTS.values()), 100)
        self.assertEqual(
            scoring._OVERALL_POINTS, {1: 40, 7: 20, 5: 20, 11: 10, 17: 10}
        )

    def test_each_factor_carries_its_points(self):
        # 10 on one counted factor and 0 on the other four gives its points.
        for n, points in scoring._OVERALL_POINTS.items():
            scores = {k: 0.0 for k in scoring._OVERALL_POINTS}
            scores[n] = 10.0
            _, overall = scoring._section_scores(_results(scores, PHOTO))
            self.assertEqual(overall, points, n)

    def test_practice_findings_do_not_move_it(self):
        base = {1: 8.0, 7: 7.0, 5: 6.0, 11: 9.0, 17: 5.0}
        _, overall = scoring._section_scores(_results(base, PHOTO))
        self.assertEqual(overall, 72)
        for n in (2, 3, 4, 6, 8, 9, 10, 12, 18, 19, 20):
            for score in (0.0, 10.0):
                scores = {**base, n: score}
                _, moved = scoring._section_scores(_results(scores, PHOTO))
                self.assertEqual(moved, overall, (n, score))

    def test_an_unmeasured_factor_is_scaled_out(self):
        scores = {1: 8.0, 7: 6.0, 5: 6.0, 11: 6.0, 17: 6.0}
        _, overall = scoring._section_scores(_results(scores, PHOTO + (17,)))
        # (40 * 8 + 20 * 6 + 20 * 6 + 10 * 6) / 90 points, out of 100.
        self.assertEqual(overall, round((320 + 120 + 120 + 60) / 90 * 10))

    def test_section_weights_are_shares_of_the_overall(self):
        sections, _ = scoring._section_scores(_results({}, PHOTO))
        weights = {s.id: s.weight for s in sections}
        self.assertEqual(
            weights,
            {"structure": 0.6, "spatial": 0.3, "dynamics": 0.0, "style": 0.1},
        )

    def test_size_on_too_few_words_is_left_out(self):
        scores = {1: 8.0, 7: 6.0, 5: 0.0, 11: 6.0, 17: 6.0}
        results = _results(scores, PHOTO)
        _, with_size = scoring._section_scores(results)
        _, without = scoring._section_scores(results, (5,))
        self.assertEqual(with_size, round((320 + 120 + 0 + 60 + 60) / 10))
        self.assertEqual(without, round((320 + 120 + 60 + 60) / 80 * 10))

    def test_the_word_minimum(self):
        least = scoring._OVERALL_MIN_SIZE_WORDS
        self.assertEqual(least, 10)
        for basis in ("words", "letter groups"):
            few = {"size_basis": basis, "size_count": least - 1}
            enough = {"size_basis": basis, "size_count": least}
            self.assertEqual(scoring._left_out(few), (5,))
            self.assertEqual(scoring._left_out(enough), ())
        # Line heights are the stand-in when under three words measured.
        lines = {"size_basis": "lines", "size_count": 30}
        self.assertEqual(scoring._left_out(lines), (5,))

    def test_with_none_of_the_five_it_falls_back_to_every_factor(self):
        none = tuple(scoring._OVERALL_POINTS) + PHOTO
        sections, overall = scoring._section_scores(_results({}, none))
        self.assertEqual(overall, 50)
        self.assertEqual(
            round(sum(s.weight for s in sections), 4),
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
