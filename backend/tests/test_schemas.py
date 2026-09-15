# SPDX-License-Identifier: AGPL-3.0-only
"""The JSON Schema contract must match what the server actually emits."""

import copy
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compact_reports
import contract_schemas
import entitlements
from fastapi import HTTPException
from report_contract import FACTOR_IDS, public_report

ROOT = Path(__file__).resolve().parents[1]
CARD = {
    "id": "print-or-cursive",
    "kind": "coach",
    "pillar": "technique",
    "title": "Cursive or print - never both",
    "text": "Pick one style for a whole page.",
    "why": "Mixed styles break rhythm.",
    "examples": ["aaaa", "oooo"],
}
REGION = {"url": "data:image/jpeg;base64,/9j/4AAQ", "caption": "evidence"}


def realistic_payload(ok=True):
    """A scorer payload shaped like a live run, without OCR or real ink."""
    factors = []
    for n in range(1, 21):
        factors.append(
            {
                "n": n,
                "sec": ["structure", "spatial", "dynamics", "style"][n % 4],
                "name": f"Factor {n}",
                "score": 6.0,
                "score100": 60,
                "band": "dev",
                "conf": "measured",
                "value": "6.0",
                "evidence": f"evidence {n}",
                "tip": f"tip {n}",
                "target": "target",
                "ex": "round",
                "basedOn": "20 letters",
                "scoringInputs": {"n_chars": 20},
            }
        )
    factors[2].update(score=None, unmeasured=True, unmeasuredReason="none")
    return {
        "ok": ok,
        "full_text": "Practice sample",
        "hand_lines": [{"text": "Practice sample", "score": 0.9}],
        "proc_w": 1200,
        "proc_h": 1600,
        "analysis": {
            "results": factors,
            "overall": 60,
            "sections": [{"id": "structure", "name": "Structure"}],
            "coachTips": [CARD],
            "recognition": {
                "backend": "paddle",
                "ocr_error": None,
                "hand_lines": 1,
                "printed_lines": 0,
                "reliable_lines": 1,
                "mean_confidence": 0.9,
                "confidence_pct": 90,
                "refined_by": {},
                "refined_lines": 0,
                "level": "high",
                "assistive_only": True,
                "passage_aligned": False,
                "passage_match": None,
                "note": "note",
            },
        },
        "factor_regions": {str(n): dict(REGION) for n in range(1, 21)},
        "error_code": None if ok else "no_handwriting",
    }


class SchemaFileTests(unittest.TestCase):
    def test_every_schema_is_valid_draft_07(self):
        for name in contract_schemas.NAMES:
            schema = contract_schemas.load(name)
            self.assertEqual(
                schema["$schema"], "http://json-schema.org/draft-07/schema#"
            )
            contract_schemas.validator(name)

    def test_shared_definitions_track_server_constants(self):
        common = contract_schemas.load("common")["definitions"]
        self.assertEqual(common["factorId"]["enum"], list(FACTOR_IDS))
        self.assertEqual(
            common["freeFactorNumbers"]["items"]["enum"],
            list(entitlements.FREE_FACTORS),
        )

    def test_committed_examples_and_catalogues_validate(self):
        for example in ("free-report", "pro-report"):
            body = json.loads((ROOT / f"examples/{example}.json").read_text())
            self.assertEqual(
                contract_schemas.errors("report-expanded", body), []
            )
        for path in (ROOT / "catalogs").glob("*.json"):
            catalogue = json.loads(path.read_text())
            self.assertEqual(contract_schemas.errors("catalog", catalogue), [])
            self.assertEqual(catalogue["version"], path.stem)
        self.assertEqual(
            contract_schemas.errors("catalog", compact_reports.dictionary()),
            [],
        )


class LiveShapeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = self.folder.name + "/entitlements.sqlite"
        entitlements.initialize(self.db)
        self.env = patch.dict(os.environ, {"VAHINI_ENTITLEMENTS_DB": self.db})
        self.env.start()
        self.addCleanup(self.env.stop)
        customer = entitlements.create_customer(self.db)
        _, token = entitlements.issue_key(self.db, customer)
        entitlements.set_subscription(
            self.db, customer, "pro", "active", int(time.time()) + 3600
        )
        self.free = entitlements.access_for(None)
        self.pro = entitlements.access_for("Bearer " + token)

    def identity(self, access):
        return {
            "schema_version": "2.0",
            "access": {
                **access,
                "capabilities": entitlements.capabilities(access),
            },
        }

    def test_identity_responses(self):
        for access in (self.free, self.pro):
            self.assertEqual(
                contract_schemas.errors("me", self.identity(access)), []
            )

    def test_expanded_reports_for_both_tiers_and_failure(self):
        for access in (self.free, self.pro):
            body = public_report(realistic_payload(), access)
            self.assertEqual(
                contract_schemas.errors("report-expanded", body), []
            )
            failed = public_report(realistic_payload(ok=False), access)
            self.assertEqual(
                contract_schemas.errors("report-expanded", failed), []
            )

    def test_compact_reports_with_every_include(self):
        fields = compact_reports.OPTIONAL_FIELDS
        for access in (self.free, self.pro):
            body = compact_reports.build_compact(
                realistic_payload(), access, fields
            )
            self.assertEqual(
                contract_schemas.errors("report-compact", body), []
            )
            failed = compact_reports.build_compact(
                realistic_payload(ok=False), access
            )
            self.assertEqual(
                contract_schemas.errors("report-compact", failed), []
            )

    def test_http_errors_use_the_detail_shape(self):
        with self.assertRaises(HTTPException) as error:
            entitlements.access_for("Bearer vh_not-a-real-key")
        body = {"detail": error.exception.detail}
        self.assertEqual(contract_schemas.errors("error", body), [])
        validation = {
            "detail": [{"loc": ["query", "format"], "msg": "x", "type": "e"}]
        }
        self.assertEqual(contract_schemas.errors("error", validation), [])

    def test_request_model(self):
        request = {
            "headers": {"authorization": "Bearer vh_" + "a" * 43},
            "query": {"format": "compact", "include": "text,inputs"},
            "form": {"lang": "auto", "expected_text": ""},
            "image": {
                "content_type": "image/jpeg",
                "size_bytes": 250000,
                "width": 1200,
                "height": 1600,
            },
        }
        self.assertEqual(
            contract_schemas.errors("report-request", request), []
        )
        bad = copy.deepcopy(request)
        bad["query"]["include"] = "text,everything"
        self.assertTrue(contract_schemas.errors("report-request", bad))
        bad = copy.deepcopy(request)
        bad["query"]["key"] = "vh_leaked"
        self.assertTrue(contract_schemas.errors("report-request", bad))


class RejectionTests(unittest.TestCase):
    """The schemas must refuse the leaks and lies they exist to catch."""

    def setUp(self):
        self.free = entitlements.access_for(None)

    def test_free_compact_cannot_carry_pro_factors_or_blocks(self):
        body = compact_reports.build_compact(realistic_payload(), self.free)
        leaked = copy.deepcopy(body)
        leaked["factors"].append({"n": 2, "s": 6.0, "st": "p"})
        self.assertTrue(contract_schemas.errors("report-compact", leaked))
        leaked = copy.deepcopy(body)
        leaked["coaching"] = [CARD]
        self.assertTrue(contract_schemas.errors("report-compact", leaked))

    def test_missing_score_cannot_masquerade_as_zero(self):
        body = compact_reports.build_compact(realistic_payload(), self.free)
        body["factors"][0].update(s=0, st="u")
        self.assertTrue(contract_schemas.errors("report-compact", body))

    def test_failure_needs_an_error_block(self):
        body = compact_reports.build_compact(realistic_payload(), self.free)
        body["ok"] = False
        self.assertTrue(contract_schemas.errors("report-compact", body))

    def test_free_expanded_cannot_include_practice(self):
        body = public_report(realistic_payload(), self.free)
        body["factors"][0]["practice"] = {"instruction": "x"}
        self.assertTrue(contract_schemas.errors("report-expanded", body))

    def test_validate_raises_with_paths(self):
        with self.assertRaises(ValueError) as error:
            contract_schemas.validate("me", {"schema_version": "2.0"})
        self.assertIn("access", str(error.exception))


if __name__ == "__main__":
    unittest.main()
