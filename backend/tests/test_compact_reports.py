# SPDX-License-Identifier: AGPL-3.0-only
"""Compact wire contract, access controls and evidence-work regression tests."""

import copy
import json
import unittest
from unittest.mock import patch, AsyncMock

from backend.tests import test_report_access as base
import compact_reports
import computer_vision
import numpy as np

sample = base.sample


class CompactTests(unittest.TestCase):
    def test_scores_and_statuses_are_preserved_without_prose_or_crops(self):
        payload = sample()
        before = copy.deepcopy(payload)
        report = compact_reports.build_compact(payload, {"tier": "pro"})
        self.assertEqual(len(report["factors"]), 20)
        self.assertEqual([f["s"] for f in report["factors"]], [6] * 20)
        self.assertEqual(report["factors"][13]["st"], "p")
        self.assertNotIn("PRIVATE", json.dumps(report))
        self.assertEqual(payload, before)
        self.assertLess(len(json.dumps(report)), 2000)

    def test_free_gets_evidence_only_for_its_five_factors(self):
        result = compact_reports.build_compact(
            sample(), {"tier": "free"}, {"inputs", "coaching", "evidence"}
        )
        self.assertEqual([f["n"] for f in result["factors"]], [1, 5, 7, 8, 18])
        self.assertEqual(len(result["locked"]), 15)
        # Crops of the Free factors, so a visitor can see what each score
        # refers to on their own page; never a locked factor's crop.
        self.assertEqual(
            sorted(result["evidence"]["factor_regions"], key=int),
            ["1", "5", "7", "8", "18"],
        )
        self.assertNotIn("inputs", result)
        self.assertNotIn("coaching", result)
        without_crops = dict(result, evidence=None)
        self.assertNotIn("PRIVATE", json.dumps(without_crops))

    def test_pro_evidence_covers_all_twenty_factors(self):
        result = compact_reports.build_compact(
            sample(), {"tier": "pro"}, {"evidence"}
        )
        self.assertEqual(len(result["evidence"]["factor_regions"]), 20)

    def test_missing_score_is_not_zero(self):
        payload = sample()
        payload["analysis"]["results"][0]["score"] = None
        result = compact_reports.build_compact(payload, {"tier": "free"})
        self.assertIsNone(result["factors"][0]["s"])
        self.assertEqual(result["factors"][0]["st"], "u")

    def test_basic_mode_does_not_build_evidence_images(self):
        image = np.full((100, 100, 3), 255, dtype=np.uint8)
        with patch.object(
            computer_vision,
            "_build_region_previews",
            side_effect=AssertionError("crop work should be skipped"),
        ), patch.object(
            computer_vision,
            "_factor_region_map",
            side_effect=AssertionError("factor crops should be skipped"),
        ):
            result = computer_vision.vl_analyze(
                image, [], include_evidence=False
            )
        self.assertEqual(result["factor_regions"], {})


class CompactHTTPTests(unittest.TestCase):
    setUp = base.ReportAccessTests.setUp
    pro = base.ReportAccessTests.pro

    def test_dictionary_and_response_mode(self):
        import importlib.util
        from pathlib import Path
        from fastapi.testclient import TestClient

        spec = importlib.util.spec_from_file_location(
            "compact_test_server",
            Path(__file__).resolve().parents[1] / "ppocr-server.py",
        )
        server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server)
        with TestClient(server.app) as client, patch.object(
            server, "_report_payload", new=AsyncMock(return_value=sample())
        ) as scorer:
            response = client.post(
                "/api/v2/reports?format=compact",
                files={"image": ("test.png", b"synthetic")},
            )
            data = response.json()
            self.assertEqual(len(data["factors"]), 5)
            self.assertEqual(
                scorer.call_args.kwargs, {"include_evidence": False}
            )
            self.assertEqual(response.headers["cache-control"], "no-store")
            url = "/api/v2/catalog/" + data["catalog_version"]
            dictionary = client.get(url)
            self.assertIn("immutable", dictionary.headers["cache-control"])
            self.assertNotIn("PRIVATE", dictionary.text)
            self.assertEqual(
                client.get(
                    url, headers={"If-None-Match": dictionary.headers["etag"]}
                ).status_code,
                304,
            )
            self.assertEqual(
                client.get(
                    url,
                    headers={
                        "If-None-Match": "W/" + dictionary.headers["etag"]
                    },
                ).status_code,
                304,
            )
            free_evidence = client.post(
                "/api/v2/reports?format=compact&include=text,evidence",
                files={"image": ("test.png", b"synthetic")},
            )
            self.assertEqual(free_evidence.status_code, 200)
            self.assertEqual(
                scorer.call_args.kwargs, {"include_evidence": True}
            )
            self.assertEqual(
                len(free_evidence.json()["evidence"]["factor_regions"]), 5
            )
            denied = client.post(
                "/api/v2/reports?format=compact&include=inputs",
                files={"image": ("test.png", b"synthetic")},
            )
            self.assertEqual(denied.status_code, 403)
            self.pro()
            paid = client.post(
                "/api/v2/reports?format=compact&include=inputs",
                files={"image": ("test.png", b"synthetic")},
                headers={"Authorization": self.header},
            )
            self.assertEqual(len(paid.json()["factors"]), 20)
            self.assertIn("inputs", paid.json())
            self.assertNotIn("evidence", paid.json())
