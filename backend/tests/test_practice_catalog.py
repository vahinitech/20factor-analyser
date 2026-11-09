# SPDX-License-Identifier: AGPL-3.0-only
"""The practice catalogue: its rules, the versioned catalogue that serves
it and the tier numbers /api/v2/me returns (docs/10-practice-framework.md)."""

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
from report import compact_reports
from report import contract_schemas
from server import entitlements
from report import practice_catalog
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
            ("model", "circus", "unknown model"),
            ("steps", "One. Two. Three. Four.", "over 3 sentences"),
            ("check", "Look. Then look again.", "one sentence"),
            (
                "steps",
                "Write one long row of very small letters and then write"
                " another one below it slowly.",
                "long sentence",
            ),
            ("helps", {"1": 0.9}, "own factor 1 at 1.0"),
            ("helps", {"1": 1.0, "5": 0.95}, "helps 5 at 0.95"),
            ("helps", {"1": 1.0, "21": 0.5}, "unknown factor 21"),
            (
                "helps",
                {"1": 1.0, "3": 0.5, "5": 0.5, "7": 0.5, "8": 0.5},
                "over 3 other factors",
            ),
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

    def test_every_factor_says_why_it_helps_and_the_win(self):
        """Page 2 prints ``why``, ``win`` and the website page under each
        skill (owner, 2026-10-11), with their Telugu."""
        pages = set()
        for number in range(1, 21):
            area = practice_catalog.FACTORS[number]
            for field in ("why", "win"):
                text = area[field]
                self.assertTrue(text.endswith("."), (number, field))
                self.assertEqual(len(practice_catalog.sentences(text)), 1)
                self.assertTrue(area["i18n"]["te"][field].strip())
            self.assertLessEqual(len(area["why"]), practice_catalog.WHY_MAX)
            self.assertLessEqual(len(area["win"]), practice_catalog.WIN_MAX)
            self.assertTrue(area["page"].startswith("handwriting-"))
            pages.add(area["page"])
        self.assertEqual(len(pages), 20, "one website page per factor")
        self.assertEqual(
            practice_catalog.FACTORS[5]["why"],
            "Same-size letters make your words easy to read.",
        )
        self.assertEqual(
            practice_catalog.FACTORS[8]["win"],
            "you can read your line aloud without stopping.",
        )

    def test_no_claim_to_diagnose_or_cure(self):
        claims = practice_catalog.claim_pattern()
        for word in ("cure", "overcomes", "a disorder", "diagnosis"):
            self.assertTrue(claims.search(word), word)
        self.assertIsNone(claims.search("keep it secure"))
        for text in strings_of(practice_catalog.browser_catalog()):
            self.assertIsNone(claims.search(text), text)

    def test_the_why_and_win_rules_catch_a_bad_entry(self):
        cases = [
            ("why", "Practice will cure messy writing.", "avoid word in why"),
            ("why", "x" * 61 + ".", "why over 60"),
            ("win", "you write. Then you smile.", "win must be one"),
            ("win", "", "no win"),
            ("page", "handwriting-magic", "unknown page"),
        ]
        for field, value, message in cases:
            factors = copy.deepcopy(practice_catalog.FACTORS)
            factors[5][field] = value
            with patch.object(practice_catalog, "FACTORS", factors):
                found = practice_catalog.problems()
            self.assertTrue(any(message in f for f in found), (field, found))
        factors = copy.deepcopy(practice_catalog.FACTORS)
        factors[7]["i18n"]["te"]["win"] = ""
        with patch.object(practice_catalog, "FACTORS", factors):
            found = practice_catalog.problems()
        self.assertIn("factor 7: te win missing", found)

    def test_every_entry_says_which_skills_it_helps(self):
        """Many-to-many: every exercise and tip helps its own factor at
        1.0, so its highest-weight factor is always its own, and others
        only between HELP_MIN and HELP_MAX."""
        for number, area in practice_catalog.FACTORS.items():
            for entry in (*area["exercises"], *area["tips"]):
                helps = entry["helps"]
                self.assertEqual(helps[str(number)], 1.0, entry["id"])
                top = max(helps.items(), key=lambda kv: kv[1])[0]
                self.assertEqual(top, str(number), entry["id"])
                for key, weight in helps.items():
                    if key != str(number):
                        self.assertGreaterEqual(weight, 0.3, entry["id"])
                        self.assertLessEqual(weight, 0.8, entry["id"])
        ladder = practice_catalog.FACTORS[5]["exercises"][0]
        self.assertEqual(ladder["helps"], {"5": 1.0, "6": 0.6})

    def test_selection_passes_composite_need_by_scoring_weights(self):
        """practice-select.js hands a composite's need to the factors it
        is made of, with the weights backend/scoring_parts/style.py
        blends them by."""
        scoring = (ROOT / "backend" / "scoring_parts" / "style.py").read_text(
            "utf-8"
        )
        select = (
            ROOT / "frontend" / "src" / "report" / "practice-select.js"
        ).read_text("utf-8")
        for number in (18, 20):
            start = scoring.index(f"s[{number}] = _clamp10(")
            # s[20] is the file's last statement: it ends with the file.
            ends = [
                scoring.find(mark, start + 1)
                for mark in ("\n    s[", "\n    return")
            ] + [len(scoring)]
            statement = scoring[start : min(e for e in ends if e > 0)]
            parts = {
                int(n): float(w)
                for n, w in re.findall(r"\((\d+), ([0-9.]+)\)", statement)
            }
            self.assertTrue(parts, number)
            js = re.search(rf"{number}: \{{([^}}]*)\}}", select)
            self.assertIsNotNone(js, number)
            mine = {
                int(n): float(w)
                for n, w in re.findall(r"(\d+):([0-9.]+)", js[1])
            }
            self.assertEqual(mine, parts, number)

    def test_every_exercise_names_its_drawing(self):
        for area in practice_catalog.FACTORS.values():
            for ex in area["exercises"]:
                self.assertIn(ex["model"], practice_catalog.MODELS)
        self.assertEqual(
            practice_catalog.FACTORS[8]["exercises"][0]["model"], "gaps"
        )

    def test_steps_are_short_simple_sentences(self):
        """A parent with basic English and a child of 8 can follow them:
        at most three sentences, each of at most 14 words."""
        for area in (
            *practice_catalog.FACTORS.values(),
            practice_catalog.SPELLING,
        ):
            for ex in area["exercises"]:
                steps = practice_catalog.sentences(ex["steps"])
                self.assertLessEqual(len(steps), 3, ex["id"])
                for sentence in steps + [ex["check"]]:
                    self.assertLessEqual(len(sentence.split()), 14, sentence)
        self.assertEqual(
            practice_catalog.sentences(
                practice_catalog.FACTORS[5]["exercises"][0]["steps"]
            ),
            [
                "Draw two light lines, a little apart.",
                "Write a o e c n m between them.",
                "Each letter touches both lines.",
            ],
        )

    def test_every_exercise_and_tip_has_telugu(self):
        for area in (
            *practice_catalog.FACTORS.values(),
            practice_catalog.SPELLING,
        ):
            for ex in area["exercises"]:
                te = ex["i18n"]["te"]
                for field in ("title", "steps", "check"):
                    self.assertTrue(te[field].strip(), (ex["id"], field))
                    self.assertRegex(te[field], "[\u0c00-\u0c7f]")
                # The child practises English letters: examples stay Latin.
                self.assertNotIn("example", te, ex["id"])
            for tip in area["tips"]:
                self.assertRegex(tip["i18n"]["te"]["text"], "[\u0c00-\u0c7f]")

    def test_telugu_rules_catch_a_bad_translation(self):
        first = practice_catalog.FACTORS[1]["exercises"][0]
        cases = [
            ({"title": "తప్పు రాత"}, "avoid word in te title"),
            ({"steps": "రాయండి — మళ్ళీ"}, "em dash in te steps"),
            ({"check": "అ" * 200}, "te check too long"),
            ({"check": ""}, "te check missing"),
            ({"note": "అ"}, "unknown te field"),
        ]
        for change, message in cases:
            factors = copy.deepcopy(practice_catalog.FACTORS)
            entry = factors[1]["exercises"][0]
            entry["i18n"]["te"] = {**first["i18n"]["te"], **change}
            with patch.object(practice_catalog, "FACTORS", factors):
                found = practice_catalog.problems()
            self.assertTrue(any(message in f for f in found), (change, found))
        factors = copy.deepcopy(practice_catalog.FACTORS)
        del factors[2]["tips"][0]["i18n"]["te"]
        with patch.object(practice_catalog, "FACTORS", factors):
            found = " ".join(practice_catalog.problems())
        self.assertIn("order.top-down: no te translation", found)
        extra = dict(practice_catalog.TELUGU_TIPS, **{"x.gone": {"text": "అ"}})
        with patch.object(
            practice_catalog,
            "TRANSLATIONS",
            {"te": (practice_catalog.TELUGU_EXERCISES, extra)},
        ):
            found = " ".join(practice_catalog.problems())
        self.assertIn("translation for unknown id x.gone", found)

    def test_spelling_pattern_rules_catch_a_bad_pattern(self):
        cases = [
            ({"exercise": "spell.none"}, "unknown exercise"),
            ({"words": ("write", "Know")}, "words must be plain words"),
            ({"rule": "Fix the wrong letters."}, "avoid word"),
            (
                {
                    "rule": "Some letters are never heard when you say the"
                    " word out loud to a friend at school."
                },
                "long sentence",
            ),
            ({"i18n": {}}, "no te translation"),
        ]
        for change, message in cases:
            spelling = copy.deepcopy(practice_catalog.SPELLING)
            first = dict(spelling["patterns"][0], **change)
            spelling["patterns"] = (first, *spelling["patterns"][1:])
            with patch.object(practice_catalog, "SPELLING", spelling):
                found = practice_catalog.problems()
            self.assertTrue(any(message in f for f in found), (change, found))
        ids = tuple(reversed(practice_catalog.PATTERN_IDS))
        with patch.object(practice_catalog, "PATTERN_IDS", ids):
            found = " ".join(practice_catalog.problems())
        self.assertIn("the last spelling pattern must be other", found)

    def test_the_telugu_avoid_list_covers_every_english_word(self):
        # One Telugu word or more for each English one (draft, for review).
        self.assertGreaterEqual(
            len(practice_catalog.AVOID_WORDS_TE),
            len(practice_catalog.AVOID_WORDS),
        )
        for text in strings_of(practice_catalog.browser_catalog()):
            for word in practice_catalog.AVOID_WORDS_TE:
                self.assertNotIn(word, text)

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
        tips = body["practice"]["spelling"]["tips"]
        self.assertTrue(all("te" in tip["i18n"] for tip in tips))
        self.assertTrue(
            all(
                "te" in entry["i18n"]
                for factor in body["factors"]
                for entry in (*factor["exercises"], *factor["tips"])
            )
        )
        for factor in body["factors"]:
            area = practice_catalog.FACTORS[factor["n"]]
            for key in ("why", "win", "page"):
                self.assertEqual(factor[key], area[key])
            self.assertEqual(factor["i18n"]["te"], area["i18n"]["te"])
        committed = ROOT / "backend" / "catalogs" / (body["version"] + ".json")
        self.assertTrue(committed.exists(), "run compact_reports.py")

    def test_the_schema_refuses_a_malformed_exercise(self):
        body = copy.deepcopy(compact_reports.dictionary())
        body["factors"][0]["exercises"][0]["unit"] = "minute"
        self.assertTrue(contract_schemas.errors("catalog", body))
        body = copy.deepcopy(compact_reports.dictionary())
        body["practice"]["tiers"]["free"]["extra"] = 1
        self.assertTrue(contract_schemas.errors("catalog", body))
        body = copy.deepcopy(compact_reports.dictionary())
        body["factors"][0]["exercises"][0]["i18n"]["te"]["note"] = "x"
        self.assertTrue(contract_schemas.errors("catalog", body))
        body = copy.deepcopy(compact_reports.dictionary())
        del body["factors"][0]["tips"][0]["i18n"]["te"]["text"]
        self.assertTrue(contract_schemas.errors("catalog", body))
        body = copy.deepcopy(compact_reports.dictionary())
        body["factors"][0]["page"] = "https://example.com"
        self.assertTrue(contract_schemas.errors("catalog", body))
        body = copy.deepcopy(compact_reports.dictionary())
        body["factors"][0]["i18n"]["te"]["note"] = "x"
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
        path = Path(__file__).resolve().parents[1] / "server/app.py"
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
