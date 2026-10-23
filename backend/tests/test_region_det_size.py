# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Line recovery's crops are detected near their own size (stage crash,
23 October 2026). The engine's page setting raised every crop's short side
to 2048 pixels, up to Paddle's 4000-pixel cap: a phone photo spent 42 of
its 47 seconds there, and one photo ran the analyser out of its memory
limit. The page itself is still detected with the engine's own setting."""

import os
import sys
import unittest
from unittest import mock

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from reading import ocr_backends  # noqa: E402

# White-box tests reach into module-private helpers below.
# pylint: disable=protected-access


class Engine:
    """A PaddleOCR stand-in that records each call's options."""

    def __init__(self):
        self.calls = []

    def ocr(self, img, **options):
        self.calls.append((img.shape, options))
        return [
            {
                "rec_texts": ["little Vahini writes"],
                "rec_polys": [[[0, 0], [60, 0], [60, 20], [0, 20]]],
                "rec_scores": [0.95],
            }
        ]


def det_size(crop):
    """The detector's input size for a crop, as Paddle resizes it."""
    options = ocr_backends._region_det_options(crop)
    assert options["text_det_limit_type"] == "resize_long"
    long_side = max(crop.shape[:2])
    ratio = options["text_det_limit_side_len"] / long_side
    return [round(s * ratio) for s in crop.shape[:2]]


class TestRegionDetSize(unittest.TestCase):
    def test_a_wide_line_is_never_blown_up_to_the_page_size(self):
        # 1300x150 became 4000x460 under the page setting.
        h, w = det_size(np.zeros((150, 1300, 3), np.uint8))
        self.assertLessEqual(max(h, w), ocr_backends.REGION_DET_LONG_SIDE)
        self.assertGreaterEqual(w, 1300)

    def test_a_short_crop_is_scaled_up_at_most_twice(self):
        # 400x150 became 4000x1500, the largest memory step.
        h, w = det_size(np.zeros((150, 400, 3), np.uint8))
        self.assertEqual((h, w), (300, 800))

    def test_a_crop_wider_than_the_cap_keeps_its_size(self):
        h, w = det_size(np.zeros((180, 2400, 3), np.uint8))
        self.assertEqual((h, w), (180, 2400))

    def test_read_region_passes_the_crop_size_and_run_keeps_the_page_one(self):
        engine = Engine()
        crop = np.full((120, 900, 3), 255, np.uint8)
        with mock.patch.object(ocr_backends, "get_engine", lambda _l: engine):
            got = ocr_backends.read_region(crop, "en")
        self.assertEqual(got[0]["text"], "little Vahini writes")
        self.assertEqual(
            engine.calls[-1][1], ocr_backends._region_det_options(crop)
        )
        ocr_backends.run(engine, crop, "en")
        self.assertEqual(engine.calls[-1][1], {})


if __name__ == "__main__":
    unittest.main()
