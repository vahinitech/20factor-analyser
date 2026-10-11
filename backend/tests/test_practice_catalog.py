# SPDX-License-Identifier: AGPL-3.0-only
"""The practice catalogue: its rules, the versioned catalogue that serves
it and the tier numbers /api/v2/me returns (docs/PRACTICE-FRAMEWORK.md)."""

import copy
import importlib.util
import os
import re
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
import practice_catalog
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
PHOTO_FACTORS = [n for n in range(1, 21) if n not in (13, 14, 15, 16)]


def strings_of(value):
    """Every string inside a nested structure."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings_of(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from strings_of(item)


class CatalogueRules(unittest.TestCase):
    def test_the_committed_catalogue_breaks_no_rule(self):
        self.assertEqual(practice_catalog.problems(), [])

    def test_every_photo_factor_has_two_exercises_and_two_tips(self):
        for number in PHOTO_FACTORS:
            area = practice_catalog.FACTORS[number]
            self.assertGreaterEqual(len(area["exercises"]), 2, number)
            self.assertGreaterEqual(len(area["tips"]), 2, number)

    def test_ids_are_unique(self):
        ids = [
            entry["id"]
            for area in (
                *practice_catalog.FACTORS.values(),
                practice_catalog.SPELLING,
            )
            for entry in (*area["exercises"], *area["tips"])
        ]
        self.assertEqual(len(ids), len(set(ids)))

    def test_worksheets_exist_in_the_worksheet_catalogue(self):
        path = ROOT / "frontend" / "src" / "report" / "worksheet-catalog.js"
        sheets = set(re.findall(r'"id":\s*"([\w-]+)"', path.read_text()))
        used = {
            ex["worksheet"]
            for area in practice_catalog.FACTORS.values()
            for ex in area["exercises"]
            if ex["worksheet"]
        }
        self.assertTrue(used)
        self.assertLessEqual(used, sheets)

    def test_words_for_children(self):
        banned = practice_catalog.avoid_pattern()
        self.assertTrue(banned.search("Fix the mistakes."))
        self.assertIsNone(banned.search("a badge"))
        for text in strings_of(practice_catalog.browser_catalog()):
            self.assertIsNone(banned.search(text), text)
            self.assertNotIn("—", text)
        for area in practice_catalog.FACTORS.values():
            for ex in area["exercises"]:
                self.assertLessEqual(len(ex["steps"]), 140, ex["id"])

    def test_each_rule_catches_a_bad_entry(self):
        cases = [
            ("steps", "x" * 141, "steps over"),
            ("steps", "Fix the wrong letters.", "avoid word"),
            ("title", "Slow — copy", "em dash"),
            ("worksheet", "no-such-sheet", "unknown worksheet"),
            ("unit", "minute", "unknown unit"),
            ("needs", "pen", "needs does not match"),
        ]
        for field, value, message in cases:
            factors = copy.deepcopy(practice_catalog.FACTORS)
            first = dict(factors[1]["exercises"][0], **{field: value})
            factors[1]["exercises"] = (first, *factors[1]["exercises"][1:])
            with patch.object(practice_catalog, "FACTORS", factors):
                found = practice_catalog.problems()
            self.assertTrue(any(message in f for f in found), (field, found))
        factors = copy.deepcopy(practice_catalog.FACTORS)
        factors[5]["exercises"] = factors[5]["exercises"][:1]
        factors[8]["tips"] = factors[8]["tips"][:1]
        factors[7]["tips"] = (
            factors[7]["tips"][0],
            dict(factors[7]["tips"][1], id=factors[7]["tips"][0]["id"]),
        )
        with patch.object(practice_catalog, "FACTORS", factors):
            found = " ".join(practice_catalog.problems())
        self.assertIn("factor 5: fewer than 2 exercises", found)
        self.assertIn("factor 8: fewer than 2 tips", found)
        self.assertIn("duplicate id", found)

    def test_tier_numbers_come_from_one_table(self):
        self.assertEqual(
            practice_catalog.limits("free"),
            {"areas_max": 3, "exercises_max": 1, "tips_max": 1},
        )
        self.assertEqual(
            practice_catalog.limits("pro"),
            {"areas_max": 3, "exercises_max": 2, "tips_max": 2},
        )
        # Anything that is not Pro gets Free's numbers.
        self.assertEqual(
            practice_catalog.limits("unknown"), practice_catalog.limits("free")
        )

    def test_stages_follow_the_score_bands(self):
        bands = compact_reports.dictionary()["bands"]
        stages = practice_catalog.STAGES
        self.assertEqual(
            {s["band"]: s["minimum"] for s in stages},
            {b["id"]: b["minimum"] for b in bands},
        )
        self.assertEqual(
            [s["label"] for s in stages],
            ["Learning", "Improving", "Mastering", "Strong"],
        )
        self.assertEqual(
            {b: d["tries"] for b, d in practice_catalog.DOSAGE.items()},
            {"focus": 15, "dev": 10, "good": 5, "strong": 10},
        )


class ServedCatalogue(unittest.TestCase):
    def test_the_versioned_catalogue_carries_practice(self):
        body = compact_reports.dictionary()
        self.assertEqual(contract_schemas.errors("catalog", body), [])
        for factor in body["factors"]:
            area = practice_catalog.FACTORS[factor["n"]]
            self.assertEqual(
                [e["id"] for e in factor["exercises"]],
                [e["id"] for e in area["exercises"]],
            )
            self.assertEqual(
                [t["id"] for t in factor["tips"]],
                [t["id"] for t in area["tips"]],
            )
        self.assertEqual(body["practice"], practice_catalog.practice_block())
        committed = ROOT / "backend" / "catalogs" / (body["version"] + ".json")
        self.assertTrue(committed.exists(), "run compact_reports.py")

    def test_the_schema_refuses_a_malformed_exercise(self):
        body = copy.deepcopy(compact_reports.dictionary())
        body["factors"][0]["exercises"][0]["unit"] = "minute"
        self.assertTrue(contract_schemas.errors("catalog", body))
        body = copy.deepcopy(compact_reports.dictionary())
        body["practice"]["tiers"]["free"]["extra"] = 1
        self.assertTrue(contract_schemas.errors("catalog", body))


class IdentityPractice(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = folder.name + "/entitlements.sqlite"
        entitlements.initialize(self.db)
        env = patch.dict(os.environ, {"VAHINI_ENTITLEMENTS_DB": self.db})
        env.start()
        self.addCleanup(env.stop)

    def test_me_returns_the_tier_numbers(self):
        path = Path(__file__).resolve().parents[1] / "ppocr-server.py"
        spec = importlib.util.spec_from_file_location("practice_server", path)
        server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server)
        customer = entitlements.create_customer(self.db)
        _key, token = entitlements.issue_key(self.db, customer)
        entitlements.set_subscription(
            self.db, customer, "pro", "active", int(time.time()) + 3600
        )
        with TestClient(server.app) as client:
            free = client.get("/api/v2/me").json()
            pro = client.get(
                "/api/v2/me", headers={"Authorization": "Bearer " + token}
            ).json()
            catalogue = client.get(
                "/api/v2/catalog/" + compact_reports.dictionary()["version"]
            ).json()
        self.assertEqual(contract_schemas.errors("me", free), [])
        self.assertEqual(contract_schemas.errors("me", pro), [])
        self.assertEqual(free["practice"], practice_catalog.limits("free"))
        self.assertEqual(pro["practice"], practice_catalog.limits("pro"))
        self.assertEqual(
            catalogue["practice"]["tiers"]["pro"], pro["practice"]
        )
        self.assertEqual(len(catalogue["factors"][4]["exercises"]), 3)


if __name__ == "__main__":
    unittest.main()
