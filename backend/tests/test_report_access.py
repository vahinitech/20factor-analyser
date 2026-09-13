# SPDX-License-Identifier: AGPL-3.0-only
"""Access-boundary tests with synthetic data, without OCR or real accounts."""

import copy
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import entitlements
from report_contract import factor_output, public_report, legacy_report
from fastapi import HTTPException
from fastapi.testclient import TestClient


def sample():
    factors = [
        {
            "n": n,
            "sec": "structure",
            "name": f"Factor {n}",
            "score": 6.0,
            "score100": 60,
            "band": "dev",
            "conf": "measured",
            "evidence": f"PRIVATE-EVIDENCE-{n}",
            "tip": f"PRIVATE-TIP-{n}",
            "target": "PRIVATE-TARGET",
            "basedOn": "20 letters",
        }
        for n in range(1, 21)
    ]
    return {
        "ok": True,
        "full_text": "Practice sample",
        "analysis": {
            "results": factors,
            "overall": 60,
            "sections": [{"id": "structure", "name": "Structure"}],
            "coachTips": ["PRIVATE-COACH"],
        },
        "factor_regions": {str(n): "PRIVATE-CROP" for n in range(1, 21)},
    }


class ReportAccessTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = self.folder.name + "/entitlements.sqlite"
        entitlements.initialize(self.db)
        self.env = patch.dict(
            os.environ,
            {"VAHINI_ENTITLEMENTS_DB": self.db, "VAHINI_ENFORCE_TIERS": "1"},
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.customer = entitlements.create_customer(self.db)
        self.key_id, self.token = entitlements.issue_key(
            self.db, self.customer
        )
        self.header = "Bearer " + self.token

    def pro(self):
        entitlements.set_subscription(
            self.db, self.customer, "pro", "active", int(time.time()) + 3600
        )
        return entitlements.access_for(self.header)

    def test_hash_only_and_revocation(self):
        self.assertNotIn(self.token.encode(), Path(self.db).read_bytes())
        self.assertEqual(self.pro()["tier"], "pro")
        entitlements.revoke_key(self.db, self.key_id)
        with self.assertRaises(HTTPException) as error:
            entitlements.access_for(self.header)
        self.assertEqual(error.exception.status_code, 401)

    def test_cancelled_expired_and_revoked(self):
        for status, expiry, expected in [
            ("cancelled", int(time.time()) + 100, "pro"),
            ("active", 1, "free"),
            ("revoked", int(time.time()) + 100, "free"),
        ]:
            entitlements.set_subscription(
                self.db, self.customer, "pro", status, expiry
            )
            self.assertEqual(
                entitlements.access_for(self.header)["tier"], expected
            )

    def test_no_self_upgrade_or_missing_database(self):
        with self.assertRaises(HTTPException):
            entitlements.access_for("Bearer pro")
        with patch.dict(
            os.environ, {"VAHINI_ENTITLEMENTS_DB": self.db + ".missing"}
        ):
            with self.assertRaises(HTTPException) as error:
                entitlements.access_for(self.header)
            self.assertEqual(error.exception.status_code, 503)

    def test_free_allowlist_and_cache_isolation(self):
        payload = sample()
        original = copy.deepcopy(payload)
        self.assertEqual(
            len(public_report(payload, self.pro())["factors"]), 20
        )
        free = entitlements.access_for()
        for response in [
            public_report(payload, free),
            legacy_report(payload, free),
        ]:
            self.assertNotIn("PRIVATE", str(response))
            self.assertEqual(len(response["locked_factors"]), 15)
        self.assertEqual(
            [f["number"] for f in public_report(payload, free)["factors"]],
            [1, 5, 7, 8, 18],
        )
        self.assertEqual(payload, original)

    def test_invalid_and_proxy_scores(self):
        factor = sample()["analysis"]["results"][13]
        self.assertEqual(factor_output(factor)["status"], "proxy")
        self.assertIsNone(
            factor_output(factor)["measurement"]["confidence_probability"]
        )
        for value in (None, float("nan"), float("inf"), -1, 11, True):
            factor["score"] = value
            self.assertIsNone(factor_output(factor)["score"]["value"])

    def test_http_projection_and_recheck(self):
        path = Path(__file__).resolve().parents[1] / "ppocr-server.py"
        spec = importlib.util.spec_from_file_location(
            "access_test_server", path
        )
        server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server)
        self.pro()
        with TestClient(server.app) as client, patch.object(
            server, "_report_payload", new=AsyncMock(return_value=sample())
        ):
            for route in ("/api/v2/reports", "/report-python"):
                free = client.post(
                    route,
                    files={"image": ("test.png", b"synthetic")},
                    data={"tier": "pro", "customer_id": self.customer},
                )
                self.assertEqual(free.status_code, 200)
                self.assertEqual(free.json()["access"]["tier"], "free")
                self.assertNotIn("PRIVATE", free.text)
                self.assertEqual(free.headers["cache-control"], "no-store")
                paid = client.post(
                    route,
                    files={"image": ("test.png", b"synthetic")},
                    headers={"Authorization": self.header},
                )
                self.assertEqual(paid.json()["access"]["tier"], "pro")
            denied = client.post(
                "/analyze-vl", files={"image": ("test.png", b"synthetic")}
            )
            self.assertEqual(denied.status_code, 403)
            entitlements.revoke_key(self.db, self.key_id)
            denied = client.get(
                "/api/v2/me", headers={"Authorization": self.header}
            )
            self.assertEqual(denied.status_code, 401)

    def test_expiry_during_inference(self):
        path = Path(__file__).resolve().parents[1] / "ppocr-server.py"
        spec = importlib.util.spec_from_file_location(
            "expiry_test_server", path
        )
        server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server)
        self.pro()

        async def expire(*_args):
            entitlements.set_subscription(
                self.db, self.customer, "pro", "expired", 1
            )
            return sample()

        with TestClient(server.app) as client, patch.object(
            server, "_report_payload", new=expire
        ):
            response = client.post(
                "/api/v2/reports",
                files={"image": ("test.png", b"synthetic")},
                headers={"Authorization": self.header},
            )
            self.assertEqual(response.json()["access"]["tier"], "free")
            self.assertNotIn("PRIVATE", response.text)


if __name__ == "__main__":
    unittest.main()
