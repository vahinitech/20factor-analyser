# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Letter Formation, Legibility and Character Distinction notice a word
that cannot be read (#193), and Stroke Order and Line Quality are left to
the sensor pen (#192).

The planted pages here are drawn from box letters
(test_planted_pages.LETTERS), so they need no download; the UJI check is
scripts/factor_tests.py (benchmarks/factors/expected.json)."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import scoring  # noqa: E402
import test_planted_pages as tpp  # noqa: E402
from test_factor_scores import BASE  # noqa: E402

# pylint: disable=protected-access


def line(text, conf, **extra):
    return {"text": text, "score": conf, **extra}


def word(crossings=2.0, turning=3.0):
    return {"crossings": crossings, "turning": turning}


def analysis(kind, seed=3):
    img, lines, _truth = tpp.planted.build_page(
        tpp.LETTERS, np.random.default_rng(seed), kind
    )
    result = scoring.build_analysis(img, lines, {}).to_dict()
    return {r["n"]: r for r in result["results"]}, result


class TestReadingFeatures(unittest.TestCase):
    def test_least_sure_quarter_counts_twice(self):
        lines = [line("one two three four", 0.95)] * 3 + [
            line("five six seven eight", 0.55)
        ]
        fx = scoring._reading_features(lines, [None] * 4)
        plain = (3 * 0.95 + 0.55) / 4
        self.assertAlmostEqual(fx["conf_low"], 0.55)
        self.assertAlmostEqual(fx["reading"], 0.5 * plain + 0.5 * 0.55)
        self.assertLess(fx["reading"], plain - 0.1)

    def test_a_copied_word_not_read_counts_zero(self):
        copied = {
            "expected": "the cat sat on the mat",
            "match": 0.9,
        }
        right = line(
            "the cat sat on the mat",
            0.9,
            text_as_read="the cat sat on the mat",
            **copied,
        )
        wrong = line(
            "the cat sat on the mat",
            0.9,
            text_as_read="the cat sxq on the mat",
            **copied,
        )
        good = scoring._reading_features([right], [None])
        bad = scoring._reading_features([wrong], [None])
        self.assertEqual(good["words_read"], 1.0)
        self.assertAlmostEqual(bad["words_read"], 5 / 6)
        self.assertLess(bad["reading"], good["reading"] - 0.1)

    def test_no_passage_no_words_read(self):
        fx = scoring._reading_features([line("a b c", 0.9)], [None])
        self.assertIsNone(fx["words_read"])

    def test_one_tangled_word_is_unsure_and_costs_formation(self):
        geo = [{"words": [word() for _ in range(4)]} for _ in range(3)]
        texts = [line("a b c d", 0.9) for _ in range(3)]
        clean = scoring._reading_features(texts, geo)
        geo[1]["words"][2] = word(crossings=3.4, turning=3.6)
        tangled = scoring._reading_features(texts, geo)
        self.assertEqual(clean["tangle_points"], 0.0)
        self.assertAlmostEqual(clean["tangle_worst"], 1.0)
        self.assertGreater(tangled["tangle_worst"], scoring.TANGLE_FULL)
        self.assertEqual(tangled["tangle_points"], scoring.TANGLE_POINTS)
        self.assertLess(tangled["reading"], clean["reading"] - 0.05)

    def test_too_few_words_for_a_usual_word(self):
        geo = [{"words": [word(), word(5.0, 9.0)]}]
        fx = scoring._reading_features([line("a b", 0.9)], geo)
        self.assertIsNone(fx["tangle_worst"])
        self.assertEqual(fx["tangle_points"], 0.0)


def score(n, **change):
    return scoring._score_factor_map({**BASE, **change})[n]


class TestReadingScores(unittest.TestCase):
    def test_formation_falls_with_the_least_sure_words(self):
        self.assertLess(score(1, reading=0.7), score(1, reading=0.9) - 1.0)

    def test_formation_loses_the_tangle_points(self):
        self.assertAlmostEqual(
            score(1, tangle_points=2.0), score(1) - 2.0, places=1
        )

    def test_legibility_reads_the_page_directly(self):
        # Reading moves Legibility beyond what it moves Letter Formation.
        f1_drop = score(1) - score(1, reading=0.6)
        drop = score(18) - score(18, reading=0.6)
        self.assertGreater(drop, 0.30 * f1_drop + 0.5)

    def test_digits_are_not_a_penalty(self):
        self.assertEqual(score(19, digits_ratio=0.4), score(19))

    def test_without_word_readings_the_line_mean_stands(self):
        self.assertEqual(score(19), round(BASE["avg_score"] * 10, 1))


class TestPlantedScribble(unittest.TestCase):
    def test_a_scribbled_word_lowers_formation_and_legibility(self):
        clean, _ = analysis("clean")
        messy, _ = analysis("messy_word")
        self.assertLess(messy[1]["score"], clean[1]["score"] - 1.0)
        self.assertLess(messy[18]["score"], clean[18]["score"] - 0.3)
        self.assertLess(messy[19]["score"], clean[19]["score"] - 0.1)
        self.assertIn("most tangled word", messy[1]["evidence"])
        self.assertNotIn("most tangled word", clean[1]["evidence"])

    def test_same_page_same_scores(self):
        first, _ = analysis("messy_word")
        again, _ = analysis("messy_word")
        self.assertEqual(
            {n: r["score"] for n, r in first.items()},
            {n: r["score"] for n, r in again.items()},
        )


class TestPenOnlyStructure(unittest.TestCase):
    def test_stroke_order_and_smoothness_need_the_pen(self):
        results, _ = analysis("clean")
        for n in (2, 4, 13, 14, 15, 16):
            r = results[n]
            self.assertTrue(r["unmeasured"], n)
            self.assertEqual(r["unmeasuredKind"], "imu", n)
            self.assertEqual(
                r["scoringInputs"],
                {"method": "sensor_required", "features": {}},
            )
            self.assertIsNone(r["basedOn"], n)
        self.assertIn("order", results[2]["evidence"])
        self.assertIn("sensor pen", results[4]["evidence"])

    def test_structure_averages_only_what_a_photo_measures(self):
        results, result = analysis("clean")
        structure = next(
            s for s in result["sections"] if s["id"] == "structure"
        )
        measured = [results[n]["score"] for n in (1, 3, 5, 6)]
        self.assertEqual(structure["scoredCount"], 4)
        self.assertAlmostEqual(
            structure["avg"], round(sum(measured) / 4, 1), places=1
        )
        weights = {s["id"]: s["weight"] for s in result["sections"]}
        self.assertEqual(weights["dynamics"], 0.0)
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=3)
        self.assertNotIn(2, [r["n"] for r in result["topWeak"]])
        self.assertNotIn(4, [r["n"] for r in result["topStrong"]])

    def test_no_photo_evidence_for_pen_skills(self):
        from vision import computer_vision  # pylint: disable=C0415

        arr = np.full((100, 300, 3), 255, np.uint8)
        lines = [{"box": [20, 20, 100, 25], "text": "ab", "score": 0.9}]
        regions = computer_vision._factor_region_map(arr, [], lines)
        for n in ("2", "4"):
            self.assertEqual(regions[n]["status"], "unavailable")
            self.assertFalse(regions[n]["url"])


if __name__ == "__main__":
    unittest.main()
