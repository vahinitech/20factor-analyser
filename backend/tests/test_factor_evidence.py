# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Regressions for locating factor evidence in the source handwriting."""

import base64
import io
import os
import sys
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import computer_vision as vision


def line(x, y, w, h, rise=0, text="sample words"):
    return {
        "box": [x, y, w, h],
        "text": text,
        "score": 0.9,
        "poly": [[x, y], [x + w, y + rise], [x + w, y + h], [x, y + h]],
    }


class TestFactorEvidence(unittest.TestCase):
    def test_tilted_short_line_not_lost_to_preview_cap(self):
        arr = np.full((500, 700, 3), 255, np.uint8)
        lines = [line(100, 20 + i * 40, 500, 30) for i in range(9)]
        lines.append(line(30, 410, 80, 25, rise=15))
        regions = vision._build_region_previews(arr, lines)
        self.assertEqual(len(regions), 8)
        result = vision._factor_region_map(arr, regions, lines)
        for n in ("7", "11"):
            self.assertEqual(result[n]["bbox"], [30, 410, 80, 25])
            self.assertEqual(result[n]["region_ids"], ["line_10"])
            self.assertEqual(result[n]["status"], "measurement")
            self.assertEqual(result[n]["coordinate_space"], "processed-image")
            self.assertEqual(result[n]["source_size"], [700, 500])
            self.assertTrue(result[n]["location_url"])

    def test_small_height_outlier_selected_instead_of_tallest(self):
        arr = np.full((300, 500, 3), 255, np.uint8)
        lines = [line(30, 10 + i * 40, 300, 30) for i in range(5)]
        lines.append(line(30, 230, 100, 8))
        result = vision._factor_region_map(arr, [], lines)
        self.assertEqual(result["5"]["bbox"], [30, 230, 100, 8])

    def test_word_spacing_selects_observed_gap_pair(self):
        arr = np.full((220, 600, 3), 255, np.uint8)
        lines = [
            line(20, 20, 50, 20),
            line(80, 20, 50, 20),
            line(140, 20, 50, 20),
            line(300, 20, 50, 20),
        ]
        result = vision._factor_region_map(arr, [], lines)
        self.assertEqual(result["8"]["bbox"], [140, 20, 210, 20])
        self.assertEqual(result["8"]["region_ids"], ["line_3", "line_4"])
        self.assertEqual(result["8"]["status"], "measurement")

    def test_clipped_box_metadata_matches_encoded_pixels(self):
        arr = np.full((100, 100, 3), 255, np.uint8)
        arr[20:40, :30] = 0
        result = vision._factor_region_map(arr, [], [line(-10, 20, 40, 20)])
        entry = result["5"]
        crop = Image.open(
            io.BytesIO(base64.b64decode(entry["url"].split(",")[1]))
        )
        self.assertEqual(entry["bbox"], [0, 20, 30, 20])
        self.assertEqual(crop.size, (30, 20))

    def test_context_does_not_claim_exact_loop_or_motion_fault(self):
        arr = np.full((100, 300, 3), 255, np.uint8)
        result = vision._factor_region_map(arr, [], [line(20, 20, 100, 25)])
        self.assertEqual(result["3"]["status"], "context")
        self.assertIn("not localized", result["3"]["caption"])
        for n in range(13, 17):
            self.assertEqual(result[str(n)]["status"], "unavailable")
            self.assertFalse(result[str(n)]["url"])

    def test_component_coordinates_use_the_clamped_crop_origin(self):
        if vision.cv2 is None:
            self.skipTest("OpenCV unavailable")
        arr = np.full((100, 100, 3), 255, np.uint8)
        arr[10:25, 5:15] = 0
        clipped = vision._line_ink_components(arr, [-10, -5, 80, 40])
        visible = vision._line_ink_components(arr, [0, 0, 70, 35])
        self.assertTrue(visible)
        self.assertEqual(clipped, visible)

    def test_no_handwriting_does_not_fall_back_to_raw_page(self):
        arr = np.zeros((100, 300, 3), np.uint8)
        result = vision._factor_region_map(arr, [], [])
        self.assertTrue(all(not entry["url"] for entry in result.values()))


if __name__ == "__main__":
    unittest.main()
