# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The calibration tool's own rules (scripts/calibrate.py, #197): the
scale it fits from synthetic neat pages, and its refusal of a scale that
would stop a planted mistake being caught."""

import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
ROOT = os.path.dirname(os.path.dirname(HERE))
spec = importlib.util.spec_from_file_location(
    "calibrate", os.path.join(ROOT, "scripts", "calibrate.py")
)
cal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cal)


def linear(spreads):
    """The neat scores of pages with these spreads at a scale, as a
    factor scores them: 10 x (1 - spread / scale), to one decimal."""

    def neat_at(scale):
        return [
            round(max(0.0, 10.0 * (1.0 - min(1.0, x / scale))), 1)
            for x in spreads
        ]

    return neat_at


def page(name, x):
    return {"page": name, "scores": {"9": 5.0}, "fx": {"letter_gap_cv": x}}


def step_score(planted_when_loose):
    """A factor that scores 8 under scale 3 and 10 above it, and a
    planted page 7 under it and planted_when_loose above it."""

    def score(p, n, scales):
        if p["scores"].get(str(n)) is None:
            return None
        loose = scales.get(n, 2.5) > 3.0
        if p["page"].endswith("planted"):
            return planted_when_loose if loose else 7.0
        return 10.0 if loose else 8.0

    return score


def inputs(score):
    neat = [page(f"neat/{i}", 0.5) for i in range(10)]
    rows = {
        "narrow_gap": [
            {
                "clean": page(f"{w} clean", 0.5),
                "planted": page(f"{w} planted", 1.0),
            }
            for w in range(20)
        ],
    }
    expected = {"narrow_gap": {"9": 1.0}}
    return cal.Inputs(neat, rows, expected, score, 9.0, 8.5, 0.1)


class TestQuantile(unittest.TestCase):
    def test_interpolates_as_numpy_does(self):
        xs = list(range(1, 11))
        self.assertAlmostEqual(cal.quantile(xs, 0.5), 5.5)
        self.assertAlmostEqual(cal.quantile(xs, 0.1), 1.9)
        self.assertIsNone(cal.quantile([], 0.5))

    def test_meets_needs_median_and_tenth_percentile(self):
        self.assertTrue(cal.meets([9.0] * 10))
        # Median 9.5, but the 10th percentile is 7.25: not Strong.
        self.assertFalse(cal.meets([5.0, 7.5] + [9.5] * 8))
        self.assertFalse(cal.meets([]))


class TestFit(unittest.TestCase):
    def test_tightest_scale_that_puts_the_median_at_nine(self):
        neat_at = linear([0.5] * 10)
        scale, why = cal.fit(neat_at, 2.5)
        self.assertIsNone(why)
        self.assertGreaterEqual(cal.quantile(neat_at(scale), 0.5), 9.0)
        # The grid steps by less than 1%: a scale 1% tighter misses.
        self.assertFalse(cal.meets(neat_at(scale * 0.99)))
        self.assertGreater(scale, 2.5)

    def test_tightens_a_scale_looser_than_the_neat_set_needs(self):
        neat_at = linear([0.05] * 10)
        scale, why = cal.fit(neat_at, 2.5)
        self.assertIsNone(why)
        self.assertLess(scale, 2.5)
        self.assertTrue(cal.meets(neat_at(scale)))

    def test_the_tenth_percentile_can_set_the_scale(self):
        spreads = [0.1] * 8 + [0.6, 0.6]
        neat_at = linear(spreads)
        scale, _ = cal.fit(neat_at, 2.5)
        scores = neat_at(scale)
        self.assertGreaterEqual(cal.quantile(scores, 0.1), 8.5)
        self.assertGreater(cal.quantile(scores, 0.5), 9.0)
        self.assertFalse(cal.meets(neat_at(scale * 0.99)))

    def test_a_scale_the_neat_set_does_not_limit_is_kept(self):
        self.assertEqual(
            cal.fit(linear([0.0] * 10), 2.5), (2.5, cal.NOT_LIMITED)
        )

    def test_a_target_no_scale_reaches_is_reported_not_forced(self):
        self.assertEqual(
            cal.fit(lambda _scale: [6.0] * 10, 2.5),
            (None, cal.OUT_OF_REACH),
        )

    def test_a_score_that_falls_as_the_scale_grows(self):
        # Loop Closure: 10 x min(1, share / BOWL_FULL).
        def neat_at(full):
            return [round(10.0 * min(1.0, 0.8 / full), 1)] * 10

        scale, why = cal.fit(neat_at, 0.9, rises=False)
        self.assertIsNone(why)
        self.assertLess(scale, 0.9)
        self.assertTrue(cal.meets(neat_at(scale)))
        self.assertFalse(cal.meets(neat_at(scale * 1.01)))


class TestPlantedCheck(unittest.TestCase):
    def test_caught_counts_as_factor_tests_does(self):
        rows = [
            {"clean": {"v": 8.0}, "planted": {"v": 7.0}},
            {"clean": {"v": 8.0}, "planted": {"v": 8.0}},
            {"clean": {"v": None}, "planted": {"v": 1.0}},
        ]
        rate = cal.caught(rows, 9, lambda p, _n: p["v"], 0.1)
        self.assertEqual(rate, 0.5)
        self.assertIsNone(cal.caught([], 9, lambda p, _n: 1.0, 0.1))

    def test_a_proposal_that_loses_a_planted_mistake_is_refused(self):
        row = cal.judge(9, 2.5, inputs(step_score(planted_when_loose=10.0)))
        self.assertGreater(row["proposed"], 3.0)
        self.assertEqual(row["after"]["median"], 10.0)
        self.assertEqual(row["planted_before"][0]["rate"], 1.0)
        self.assertEqual(row["planted_after"][0]["rate"], 0.0)
        self.assertEqual(row["verdict"], cal.LOSES)

    def test_a_proposal_that_keeps_every_mistake_passes(self):
        row = cal.judge(9, 2.5, inputs(step_score(planted_when_loose=9.0)))
        self.assertEqual(row["planted_after"][0]["rate"], 1.0)
        self.assertEqual(row["verdict"], cal.OK)

    def test_a_refused_proposal_is_not_written_or_blended(self):
        inp = inputs(step_score(planted_when_loose=10.0))
        report = {
            "tool_test": False,
            "neat_sets": ["neat"],
            "target": 9.0,
            "strong": 8.5,
            "factors": [cal.judge(9, 2.5, inp)],
        }
        self.assertEqual(cal.writable(report)["scales"], {})
        blend = cal.judge_blend(18, {}, inp)
        self.assertEqual(
            blend["verdict"], "no proposal passed, nothing to blend"
        )

    def test_a_tool_test_is_never_written(self):
        inp = inputs(step_score(planted_when_loose=9.0))
        report = {
            "tool_test": True,
            "neat_sets": ["uji-clean"],
            "target": 9.0,
            "strong": 8.5,
            "pages": 10,
            "planted_writers": 20,
            "factors": [cal.judge(9, 2.5, inp)],
            "problems": [],
        }
        with self.assertRaises(ValueError):
            cal.writable(report)
        text = cal.table(report)
        self.assertIn("not neat writing", text)
        self.assertIn("must not be", text)
        report["tool_test"] = False
        self.assertIn("9", cal.writable(report)["scales"])


class TestScalesMatchTheScorer(unittest.TestCase):
    def test_each_scale_divides_a_feature_its_factor_reads(self):
        import scoring  # pylint: disable=import-outside-toplevel

        for n, spec_n in cal.SCALES.items():
            self.assertIn(
                spec_n["feature"],
                scoring._INPUT_FEATURES[n],  # pylint: disable=W0212
                f"factor {n}",
            )


if __name__ == "__main__":
    unittest.main()
