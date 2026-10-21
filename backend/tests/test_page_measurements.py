# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Letter size from word heights (#135) and the page measurements the
report draws (#137), on planted pages with drawn letters."""

import importlib.util
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import computer_vision as vision  # noqa: E402
import marked_places  # noqa: E402
import scoring  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
spec = importlib.util.spec_from_file_location(
    "planted_pages", os.path.join(ROOT, "scripts", "planted_pages.py")
)
planted = importlib.util.module_from_spec(spec)
spec.loader.exec_module(planted)


def zigzag(ch):
    h = 2.0 if ch in planted.TALL or ch in planted.LOW else 1.0
    xs = np.linspace(0, 0.5, 6)
    return [
        np.array(list(zip(xs, [0.0 if i % 2 == 0 else h for i in range(6)])))
    ]


LETTERS = {
    ch: [zigzag(ch)] for ch in set("".join(planted.SENTENCES).replace(" ", ""))
}


def page(kind, seed=0):
    rng = np.random.default_rng(seed)
    img, lines, _truth = planted.build_page(LETTERS, rng, kind, "plain")
    return img, lines


def size_score(img, lines):
    result = scoring.build_analysis(img, [dict(l) for l in lines], {})
    return next(f for f in result.to_dict()["results"] if f["n"] == 5)


class TestLetterSize(unittest.TestCase):
    def setUp(self):
        if vision.cv2 is None:
            self.skipTest("OpenCV unavailable")

    def test_size_is_measured_from_words(self):
        f = size_score(*page("clean"))
        self.assertTrue(f["basedOn"].endswith("words"))

    def test_a_sloping_line_does_not_lower_letter_size(self):
        # Averaged over six pages: one page's words shift by a column or
        # two either way, and a single seed sat on the limit.
        diffs = [
            size_score(*page("clean", seed=seed))["score"]
            - size_score(*page("tilted_line", seed=seed))["score"]
            for seed in range(6)
        ]
        self.assertLess(abs(sum(diffs) / len(diffs)), 0.3)
        self.assertLess(max(abs(d) for d in diffs), 0.8)


class TestPageMeasurements(unittest.TestCase):
    def setUp(self):
        if vision.cv2 is None:
            self.skipTest("OpenCV unavailable")

    def measure(self, kind, seed=0):
        img, lines = page(kind, seed)
        return vision.vl_analyze(img, lines)["measurements"]

    def test_every_measurement_is_present(self):
        m = self.measure("clean")
        self.assertEqual(m["lines"], 4)
        for key in ("slope", "size", "margin"):
            self.assertIn(key, m)
        band = m["size"]["line"]
        self.assertLess(band["midline"][0][1], band["baseline"][0][1])

    def test_slope_is_the_steepest_line(self):
        m = self.measure("tilted_line")
        self.assertEqual(m["slope"]["line"]["region_id"], "line_4")
        self.assertAlmostEqual(
            m["slope"]["line"]["angle"], planted.TILT_DEG, delta=0.6
        )

    def test_same_page_same_measurements(self):
        self.assertEqual(
            self.measure("low_word", 2), self.measure("low_word", 2)
        )

    def test_the_hardest_line_is_a_line_of_letters(self):
        lines = [
            {
                "text": "/////////",
                "score": 0.30,
                "box": [10, 10, 200, 30],
                "evidence_id": "line_1",
            },
            {
                "text": "1234567890",
                "score": 0.40,
                "box": [10, 50, 200, 30],
                "evidence_id": "line_2",
            },
            {
                "text": "vahini writes",
                "score": 0.70,
                "box": [10, 90, 200, 30],
                "evidence_id": "line_3",
            },
            {
                "text": "bheema reads",
                "score": 0.90,
                "box": [10, 130, 200, 30],
                "evidence_id": "line_4",
            },
        ]
        arr = np.full((200, 260, 3), 255, np.uint8)
        m = marked_places.page_measurements(arr, lines)
        self.assertEqual(m["reading"]["line"]["region_id"], "line_3")


if __name__ == "__main__":
    unittest.main()
