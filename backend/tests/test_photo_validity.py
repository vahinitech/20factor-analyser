# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Photo inputs must not fabricate measurements or lose orientation."""

import io
import os
import sys
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageOps

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import computer_vision
import scoring
from backend.tests.test_server_pipeline import _load_server


class TestPhotoValidity(unittest.TestCase):
    def test_empty_regions_cannot_be_scored_directly(self):
        with self.assertRaisesRegex(ValueError, "No handwriting"):
            scoring.build_analysis(np.full((40, 80, 3), 255, np.uint8), [], {})

    def test_photo_excludes_motion_from_scores_and_rankings(self):
        arr = np.full((160, 300, 3), 255, dtype=np.uint8)
        lines = [
            {
                "text": "hello world",
                "score": 0.9,
                "box": [20, 30, 200, 30],
                "poly": [[20, 30], [220, 30], [220, 60], [20, 60]],
            }
        ]
        result = scoring.build_analysis(arr, lines, {}).to_dict()
        self.assertEqual(len(result["results"]), 20)
        self.assertEqual(result["measuredCount"], 16)
        for factor in result["results"][12:16]:
            self.assertTrue(factor["unmeasured"])
            self.assertEqual(factor["conf"], "imu")
            self.assertFalse(factor["imuMeasured"])
            self.assertTrue(factor["unmeasuredReason"])
        dynamics = result["sections"][2]
        self.assertIsNone(dynamics["avg"])
        self.assertIsNone(dynamics["avg100"])
        self.assertEqual(dynamics["scoredCount"], 0)
        live = [s for s in result["sections"] if s["scoredCount"]]
        expected = round(
            sum(s["avg100"] * s["weight"] for s in live)
            / sum(s["weight"] for s in live)
        )
        self.assertEqual(result["overall"], expected)
        self.assertEqual(result["overallMeasured"], expected)
        self.assertTrue(
            all(
                not r["unmeasured"]
                for r in result["topWeak"] + result["topStrong"]
            )
        )
        pen = next(g for g in result["plainGroups"] if g["id"] == "pen")
        self.assertEqual(pen["measuredCount"], 1)

    def test_blank_page_refused_with_or_without_ocr_error(self):
        server = _load_server()
        arr = np.full((160, 300, 3), 255, dtype=np.uint8)
        for error in ("", "OCR unavailable"):
            with self.subTest(error=error), patch.object(
                server.recognizer,
                "collect_lines",
                return_value=([], error, "paddle", {}),
            ), patch.object(
                server.recognizer, "extract_hand_lines", return_value=([], [])
            ), patch.object(
                server.scoring, "build_analysis"
            ) as build:
                result = server._report_python_process(arr, b"", "en", "")
                self.assertFalse(result["ok"])
                self.assertEqual(result["error_code"], "no_handwriting")
                self.assertIsNone(result["analysis"])
                self.assertEqual(result["factor_regions"], {})
                self.assertNotIn("fully printed", result["error"])
                build.assert_not_called()

    def test_image_exif_orientation_applied_before_resizing(self):
        arr = np.full((40, 80, 3), 255, dtype=np.uint8)
        arr[:20, :40] = [255, 0, 0]
        for orientation in range(1, 9):
            with self.subTest(orientation=orientation):
                exif = Image.Exif()
                exif[274] = orientation
                buf = io.BytesIO()
                Image.fromarray(arr).save(buf, format="PNG", exif=exif)
                raw = buf.getvalue()
                expected = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
                actual = computer_vision.decode_image(raw)
                np.testing.assert_array_equal(
                    np.array(actual), np.array(expected)
                )
                resized = computer_vision.to_numpy(raw, max_side=40)
                self.assertEqual(
                    resized.shape[:2],
                    (expected.height // 2, expected.width // 2),
                )


if __name__ == "__main__":
    unittest.main()
