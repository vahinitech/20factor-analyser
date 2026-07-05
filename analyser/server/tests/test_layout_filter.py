# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
# Pure-Python tests for the document-layout negative pre-filter. These do
# NOT download or build a real PP-DocLayout model (network is not assumed
# available in CI); model construction and .predict() are mocked, so these
# tests exercise the real filtering/tier-selection logic against synthetic
# layout results.
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
sys.path.insert(0, SERVER_DIR)

import ocr_backends  # noqa: E402
import layout_filter  # noqa: E402

# White-box tests deliberately reach into module-private helpers below.
# pylint: disable=protected-access,too-few-public-methods


class TestLayoutFilterGeometry(unittest.TestCase):
    def test_overlap_fraction_full_containment_is_one(self):
        box = [10, 10, 20, 20]  # x, y, w, h -> [10,10]-[30,30]
        region = [0, 0, 100, 100]
        self.assertAlmostEqual(
            layout_filter._overlap_fraction(box, region), 1.0
        )

    def test_overlap_fraction_disjoint_is_zero(self):
        box = [0, 0, 10, 10]
        region = [50, 50, 100, 100]
        self.assertEqual(layout_filter._overlap_fraction(box, region), 0.0)

    def test_overlap_fraction_partial(self):
        box = [0, 0, 10, 10]  # area 100, [0,0]-[10,10]
        region = [5, 5, 15, 15]  # intersection [5,5]-[10,10] = area 25
        self.assertAlmostEqual(
            layout_filter._overlap_fraction(box, region), 0.25
        )

    def test_filter_excluded_regions_drops_only_overlapping_lines(self):
        lines = [
            {"text": "inside figure", "box": [12, 12, 5, 5]},
            {"text": "elsewhere on page", "box": [200, 200, 30, 10]},
        ]
        regions = [[0, 0, 30, 30]]  # a figure box in the top-left
        kept = layout_filter.filter_excluded_regions(lines, regions)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["text"], "elsewhere on page")

    def test_filter_excluded_regions_noop_without_regions(self):
        lines = [{"text": "a", "box": [0, 0, 5, 5]}]
        self.assertEqual(
            layout_filter.filter_excluded_regions(lines, []), lines
        )

    def test_partial_edge_touch_is_kept(self):
        # A caption box mostly outside a figure region (only a sliver
        # overlaps) must survive — only mostly-contained lines are dropped.
        lines = [{"text": "figure 1: caption", "box": [95, 0, 20, 10]}]
        regions = [[0, 0, 100, 100]]  # overlap is 5/20 = 0.25 of the box
        kept = layout_filter.filter_excluded_regions(lines, regions)
        self.assertEqual(len(kept), 1)


class TestLayoutTierSelection(unittest.TestCase):
    def setUp(self):
        self._orig_memo = dict(ocr_backends._SPEED_MEMO)
        ocr_backends._SPEED_MEMO.clear()

    def tearDown(self):
        ocr_backends._SPEED_MEMO.clear()
        ocr_backends._SPEED_MEMO.update(self._orig_memo)

    def test_first_call_prefers_m(self):
        tier_key, model_name = layout_filter._select_tier()
        self.assertEqual(
            (tier_key, model_name), ("layout_m", "PP-DocLayout-M")
        )

    def test_slow_m_falls_back_to_s(self):
        ocr_backends.record_engine_speed("layout_m", 5000.0)  # measured slow
        tier_key, model_name = layout_filter._select_tier()
        self.assertEqual(
            (tier_key, model_name), ("layout_s", "PP-DocLayout-S")
        )

    def test_slow_m_and_s_disables_filtering(self):
        ocr_backends.record_engine_speed("layout_m", 5000.0)
        ocr_backends.record_engine_speed("layout_s", 5000.0)
        tier_key, model_name = layout_filter._select_tier()
        self.assertIsNone(tier_key)
        self.assertIsNone(model_name)

    def test_fast_m_keeps_using_m(self):
        ocr_backends.record_engine_speed("layout_m", 40.0)
        tier_key, _model_name = layout_filter._select_tier()
        self.assertEqual(tier_key, "layout_m")


class TestExcludedRegionsIntegration(unittest.TestCase):
    def setUp(self):
        self._orig_memo = dict(ocr_backends._SPEED_MEMO)
        self._orig_models = dict(layout_filter._MODELS)
        ocr_backends._SPEED_MEMO.clear()
        layout_filter._MODELS.clear()

    def tearDown(self):
        ocr_backends._SPEED_MEMO.clear()
        ocr_backends._SPEED_MEMO.update(self._orig_memo)
        layout_filter._MODELS.clear()
        layout_filter._MODELS.update(self._orig_models)

    def test_excluded_regions_extracts_only_excluded_labels(self):
        class _FakeModel:
            def predict(
                self, _arr, batch_size=1
            ):  # pylint: disable=unused-argument
                return [
                    {
                        "boxes": [
                            {"label": "text", "coordinate": [0, 0, 10, 10]},
                            {
                                "label": "figure",
                                "coordinate": [20, 20, 50, 50],
                            },
                            {"label": "seal", "coordinate": [60, 60, 80, 80]},
                            {
                                "label": "formula",
                                "coordinate": [0, 90, 10, 100],
                            },
                        ]
                    }
                ]

        with mock.patch.object(
            layout_filter, "_build", return_value=_FakeModel()
        ), mock.patch.object(
            layout_filter, "available", return_value=(True, "")
        ):
            import numpy as np

            regions = layout_filter.excluded_regions(
                np.zeros((100, 100, 3), dtype=np.uint8)
            )
        self.assertEqual(
            sorted(tuple(r) for r in regions),
            [(20.0, 20.0, 50.0, 50.0), (60.0, 60.0, 80.0, 80.0)],
        )

    def test_disabled_returns_empty_without_building_model(self):
        with mock.patch.object(layout_filter, "_ENABLED", False):
            with mock.patch.object(layout_filter, "_build") as build_mock:
                import numpy as np

                out = layout_filter.excluded_regions(
                    np.zeros((10, 10, 3), dtype=np.uint8)
                )
        self.assertEqual(out, [])
        build_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
