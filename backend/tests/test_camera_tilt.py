# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Line angles are measured against the page, not the photo's edges
(#304): a phone turned a few degrees must not cost level writing its
Baseline and Line Straightness, and one line off the others still must."""

import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import scoring
from scoring_parts import features
from vision import marked_places


def _lines(angles):
    """One line per angle (degrees, positive sinking to the right), each
    600 px long, 80 px apart."""
    out = []
    for i, deg in enumerate(angles):
        x0, y0 = 40.0, 40.0 + 80 * i
        dy = 600 * math.tan(math.radians(deg))
        poly = [[x0, y0], [x0 + 600, y0 + dy], [x0 + 600, y0 + dy + 30]]
        poly.append([x0, y0 + 30])
        top, bottom = min(y0, y0 + dy), max(y0, y0 + dy) + 30
        out.append(
            {
                "text": "level writing here",
                "score": 0.9,
                "box": [x0, top, 600.0, bottom - top],
                "poly": poly,
            }
        )
    return out


def _slope(angles):
    arr = np.full((480, 720, 3), 255, dtype=np.uint8)
    return scoring._extract_features(arr, _lines(angles), {})["line_slope_abs"]


class CameraTilt(unittest.TestCase):
    def test_only_the_tilt_beyond_one_degree_is_the_cameras(self):
        self.assertEqual(features._camera_tilt(0.6), 0.0)
        self.assertEqual(features._camera_tilt(-1.0), 0.0)
        self.assertAlmostEqual(features._camera_tilt(3.0), 2.0)
        self.assertAlmostEqual(features._camera_tilt(-4.5), -3.5)

    def test_a_turned_photo_of_level_lines_reads_nearly_level(self):
        self.assertAlmostEqual(_slope([0, 0, 0, 0]), 0.0, places=3)
        # Every line at 3 degrees: the camera, less the first degree.
        self.assertAlmostEqual(_slope([3, 3, 3, 3]), 1.0, places=2)
        self.assertAlmostEqual(_slope([-6, -6, -6, -6]), 1.0, places=2)

    def test_one_line_off_the_others_still_counts(self):
        # Straight photo, last line sinking 4 degrees: as before the fix.
        self.assertAlmostEqual(_slope([0, 0, 0, 4]), 1.0, places=2)
        # The same page turned 3 degrees: the sinking line still shows.
        self.assertGreater(_slope([3, 3, 3, 7]), 1.5)


def _marked(angles):
    """The slope measurement and the factor-7 marks the report gets."""
    arr = np.full((480, 720, 3), 255, dtype=np.uint8)
    lines = _lines(angles)
    for i, l in enumerate(lines, 1):
        l["evidence_id"] = f"line_{i}"
    slope = marked_places.page_measurements(arr, lines)["slope"]
    look = [
        p["region_id"]
        for p in marked_places._angle_places(lines)
        if p["role"] == "look"
    ]
    return slope, look


class MarksAgreeWithTheScore(unittest.TestCase):
    """The report's slope row and line marks measure against the page,
    as Baseline and Line Straightness do since this fix."""

    def test_a_turned_photo_of_level_lines(self):
        slope, look = _marked([4, 4, 4, 4])
        self.assertAlmostEqual(slope["mean_deg"], 1.0, places=1)
        self.assertLess(slope["line"]["angle"], 1.1)
        self.assertEqual(look, [])

    def test_one_sinking_line_on_a_turned_photo(self):
        slope, look = _marked([3, 3, 3, 7])
        self.assertEqual(slope["line"]["region_id"], "line_4")
        self.assertAlmostEqual(slope["line"]["angle"], 5.0, places=1)
        self.assertEqual(look, ["line_4"])

    def test_a_straight_photo_is_as_before(self):
        slope, look = _marked([0, 0, 0, 4])
        self.assertAlmostEqual(slope["line"]["angle"], 4.0, places=1)
        self.assertEqual(look, ["line_4"])


if __name__ == "__main__":
    unittest.main()
