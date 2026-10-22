# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""School, class and child profiles on the language packs
(languages/profile.py, docs/20-languages.md section 18.1, #220).

The resolver's set, add and remove; what a profile may never hold or do;
the ruleset hash; a class a profile empties leaving its factor "Not
measured" through the public scorer; and the request field, the cache key
and comparability. No real handwriting and no real names."""

import asyncio
import copy
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np
from fastapi import UploadFile
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from report import comparison_data  # noqa: E402
from report import compact_reports  # noqa: E402
from report import contract_schemas  # noqa: E402
from server import entitlements  # noqa: E402
from scoring_parts import needs as factor_needs  # noqa: E402
import scoring  # noqa: E402
from languages import profile, registry  # noqa: E402
from report.report_contract import public_report  # noqa: E402
from backend.tests.test_comparison_data import (  # noqa: E402
    FREE,
    read_payload,
)
from backend.tests.test_language_packs import PackTree  # noqa: E402
from backend.tests.test_schemas import realistic_payload  # noqa: E402

EN = registry.language()
# Every letter of the loop and bowl classes, and of the tall ones, read
# from the pack so this file writes no letter list of its own.
LOOPS = sorted(EN.letter_set("loop") | EN.letter_set("bowl"))
TALL = sorted(EN.letter_set("ascender") | EN.letter_set("descender"))
# A test language with reviewed letter models and forms: the real packs
# have none yet, and these tests must not invent any for them.
TEST_PACK = {
    "id": "xx",
    "kind": "language",
    "extends": "Latn",
    "set": {
        "name": "Test",
        "level": 0,
        "letter_models": ["print", "cursive"],
        "variants": {"a": ["one-storey", "two-storey"], "k": ["looped"]},
    },
}


def untaught(letters):
    return {"variants": {"set": {c: [] for c in letters}}}


def refused(test, layers, code, pack=None):
    text = layers if isinstance(layers, str) else json.dumps(layers)
    with test.assertRaises(profile.ProfileError) as caught:
        profile.from_request(text, pack)
    test.assertEqual(caught.exception.code, code, str(caught.exception))
    return caught.exception


class Refusals(unittest.TestCase):
    def test_an_empty_field_is_the_packs_alone(self):
        for text in ("", "   ", None):
            ruleset = profile.from_request(text)
            self.assertEqual(ruleset.hash, EN.hash)
            self.assertEqual(ruleset.emptied_classes, frozenset())

    def test_a_forbidden_field_is_refused(self):
        cases = (
            {"class": {"health": {"set": "asthma"}}},
            {"class": {"diagnosis": {"set": "none"}}},
            {"school": {"ability": {"set": "low"}}},
            {"class": {"child_name": {"set": "Tara"}}},
            {"class": {"regex": {"set": "^a+$"}}},
            {"teacher": {"letter_model": {"set": "print"}}},
            # A child's profile may only say the letter model taught.
            {"child": {"exceptions": {"add": {"words": ["Tara"]}}}},
        )
        for layers in cases:
            with self.subTest(layers=list(layers)):
                error = refused(self, layers, "profile_field_not_allowed")
                self.assertEqual(error.status, 422)
                self.assertNotIn("asthma", str(error))
                self.assertNotIn("Tara", str(error))

    def test_a_pattern_is_kept_as_a_literal_word(self):
        words = ["(a+)+$", ".*", "[A-Z]*"]
        ruleset = profile.from_request(
            json.dumps({"class": {"exceptions": {"add": {"words": words}}}})
        )
        self.assertEqual(ruleset.rules()["exceptions"]["words"], sorted(words))
        other = profile.from_request(
            json.dumps({"class": {"exceptions": {"add": {"words": ["a"]}}}})
        )
        self.assertNotEqual(ruleset.hash, other.hash)

    def test_a_word_with_a_space_is_refused(self):
        refused(
            self,
            {"class": {"exceptions": {"add": {"words": ["two words"]}}}},
            "profile_invalid",
        )

    def test_an_oversized_list_is_refused(self):
        many = [f"w{i}" for i in range(201)]
        error = refused(
            self,
            {"class": {"exceptions": {"add": {"words": many}}}},
            "profile_list_too_long",
        )
        self.assertEqual(error.field, "class.exceptions.add.words")
        self.assertEqual(error.status, 422)

    def test_layers_together_keep_the_list_limit(self):
        school = [f"s{i}" for i in range(150)]
        klass = [f"c{i}" for i in range(60)]
        error = refused(
            self,
            {
                "school": {"exceptions": {"add": {"words": school}}},
                "class": {"exceptions": {"add": {"words": klass}}},
            },
            "profile_list_too_long",
        )
        self.assertEqual(error.field, "ruleset.exceptions.words")

    def test_an_oversized_profile_is_refused(self):
        layers = {"class": {"word_lists": {"set": {}}}}
        text = json.dumps(layers) + " " * profile.MAX_BYTES
        error = refused(self, text, "profile_too_large")
        self.assertEqual(error.status, 413)

    def test_text_that_is_not_json_is_refused(self):
        for text in ("{", "NaN", '{"class": NaN}', "[" * 5000):
            with self.subTest(text=text[:10]):
                refused(self, text, "profile_not_json")

    def test_a_letter_model_must_be_one_the_pack_lists(self):
        layers = {"class": {"letter_model": {"set": "print"}}}
        refused(self, layers, "profile_not_in_pack")
        tree = PackTree(TEST_PACK)
        self.addCleanup(tree.close)
        pack = tree.resolve("xx")
        self.assertEqual(
            profile.resolve(layers, pack).rules()["letter_model"], "print"
        )
        refused(
            self,
            {"class": {"letter_model": {"set": "italic"}}},
            "profile_not_in_pack",
            pack,
        )

    def test_letter_forms_come_from_the_pack(self):
        tree = PackTree(TEST_PACK)
        self.addCleanup(tree.close)
        pack = tree.resolve("xx")
        ruleset = profile.resolve(
            {"class": {"variants": {"set": {"a": ["one-storey"]}}}}, pack
        )
        self.assertEqual(ruleset.rules()["variants"], {"a": ["one-storey"]})
        refused(
            self,
            {"class": {"variants": {"set": {"a": ["squiggle"]}}}},
            "profile_not_in_pack",
            pack,
        )
        # A letter outside the pack's letters, even with no form named.
        refused(
            self,
            {"class": {"variants": {"set": {"అ": []}}}},
            "profile_not_in_pack",
        )

    def test_every_letter_or_every_small_letter_cannot_be_emptied(self):
        for name in profile.MUST_KEEP:
            with self.subTest(name=name):
                refused(
                    self,
                    {"class": untaught(EN.letters(name))},
                    "profile_empties_class",
                )


class Merging(unittest.TestCase):
    def test_school_then_class_then_child(self):
        tree = PackTree(TEST_PACK)
        self.addCleanup(tree.close)
        layers = {
            "child": {"letter_model": {"set": "cursive"}},
            "school": {
                "letter_model": {"set": "print"},
                "ruling": {"set": "four_line"},
                "exceptions": {
                    "add": {"words": ["Vahini", "Bheema"], "skip": ["digits"]}
                },
                "word_lists": {"set": {"week-7": ["because", "friend"]}},
            },
            "class": {
                "exceptions": {
                    "add": {"words": ["Pihu"]},
                    "remove": {"skip": ["digits"]},
                },
                "word_lists": {"add": {"week-7": ["school"]}},
                "checks": {"set": {"spelling": "word_list"}},
            },
        }
        rules = profile.resolve(layers, tree.resolve("xx")).rules()
        self.assertEqual(rules["letter_model"], "cursive")
        self.assertEqual(rules["ruling"], "four_line")
        self.assertEqual(
            rules["exceptions"],
            {"words": ["Bheema", "Pihu", "Vahini"], "skip": []},
        )
        self.assertEqual(
            rules["word_lists"], {"week-7": ["because", "friend", "school"]}
        )
        self.assertEqual(rules["checks"], {"spelling": "word_list"})

    def test_set_replaces_remove_takes_out(self):
        layers = {
            "school": {"word_lists": {"set": {"week-1": ["cat", "dog"]}}},
            "class": {
                "word_lists": {
                    "set": {"week-1": ["sun"]},
                    "remove": {"week-2": ["moon"]},
                }
            },
        }
        refused(self, layers, "profile_invalid")
        del layers["class"]["word_lists"]["remove"]
        rules = profile.from_request(json.dumps(layers)).rules()
        self.assertEqual(rules["word_lists"], {"week-1": ["sun"]})

    def test_adding_what_is_there_or_removing_what_is_not_is_refused(self):
        twice = {
            "school": {"exceptions": {"add": {"words": ["Tara"]}}},
            "class": {"exceptions": {"add": {"words": ["Tara"]}}},
        }
        error = refused(self, twice, "profile_invalid")
        self.assertNotIn("Tara", str(error))
        missing = {"class": {"exceptions": {"remove": {"words": ["Tara"]}}}}
        refused(self, missing, "profile_invalid")

    def test_one_key_under_two_operations_is_refused(self):
        refused(
            self,
            {
                "class": {
                    "word_lists": {
                        "set": {"week-1": ["cat"]},
                        "add": {"week-1": ["dog"]},
                    }
                }
            },
            "profile_invalid",
        )


class RulesetHash(unittest.TestCase):
    def test_a_profile_that_changes_nothing_hashes_as_the_packs(self):
        layers = {"class": {"profile": "class-3b", "version": 4}}
        self.assertEqual(profile.resolve(layers).hash, EN.hash)
        empty = {"class": {"word_lists": {"set": {}}}}
        self.assertEqual(profile.resolve(empty).hash, EN.hash)

    def test_order_of_a_list_does_not_change_the_hash(self):
        first = {"class": {"exceptions": {"add": {"words": ["Pihu", "Tara"]}}}}
        second = copy.deepcopy(first)
        second["class"]["exceptions"]["add"]["words"].reverse()
        self.assertEqual(
            profile.resolve(first).hash, profile.resolve(second).hash
        )

    def test_a_changed_profile_changes_the_hash(self):
        one = {"class": {"exceptions": {"add": {"words": ["Pihu"]}}}}
        two = {"class": {"exceptions": {"add": {"words": ["Tara"]}}}}
        self.assertNotEqual(profile.resolve(one).hash, EN.hash)
        self.assertNotEqual(
            profile.resolve(one).hash, profile.resolve(two).hash
        )

    def test_the_repr_never_shows_the_profile(self):
        ruleset = profile.resolve(
            {"class": {"exceptions": {"add": {"words": ["Pihu"]}}}}
        )
        self.assertNotIn("Pihu", repr(ruleset))
        self.assertIn(ruleset.hash[:12], repr(ruleset))


def page():
    arr = np.full((200, 600, 3), 255, dtype=np.uint8)
    lines = []
    for i, text in enumerate(("a good dog ran up", "the big hill today")):
        top, bottom = 30 + i * 60, 70 + i * 60
        corners = [[20, top], [540, top], [540, bottom], [20, bottom]]
        lines.append(
            {
                "text": text,
                "score": 0.9,
                "box": [20, top, 520, 40],
                "poly": corners,
            }
        )
    return arr, lines


def score(ruleset):
    """The public scorer on the test page, with the profile's reasons."""
    arr, lines = page()
    with profile.applied(ruleset):
        analysis = scoring.build_analysis(arr, lines, {}).to_dict()
    return factor_needs.explain(analysis, ruleset)


def by_number(analysis):
    return {f["n"]: f for f in analysis["results"]}


class EmptiedClasses(unittest.TestCase):
    def test_no_profile_scores_exactly_as_before(self):
        arr, lines = page()
        before = scoring.build_analysis(arr, lines, {}).to_dict()
        self.assertEqual(score(profile.from_request("")), before)
        self.assertEqual(score(None), before)

    def test_untaught_loop_letters_leave_factor_3_unmeasured(self):
        before = by_number(score(None))
        self.assertFalse(before[3]["unmeasured"])
        ruleset = profile.resolve({"class": untaught(LOOPS)})
        self.assertLessEqual({"bowl", "loop"}, ruleset.emptied_classes)
        after = score(ruleset)
        got = by_number(after)
        three = got[3]
        self.assertTrue(three["unmeasured"])
        self.assertEqual(three["value"], "Not measured")
        self.assertEqual(three["score"], 0.0)
        reason = factor_needs.PROFILE_REASON
        self.assertEqual(three["unmeasuredReason"], reason)
        self.assertEqual(three["evidence"], factor_needs.PROFILE_EVIDENCE)
        inputs = {"classes": ["bowl", "loop"]}
        self.assertEqual(
            three["scoringInputs"],
            {"method": "profile_not_taught", "features": inputs},
        )
        # The section copy says the same, and factor 3 counts nowhere.
        in_section = [
            f for s in after["sections"] for f in s["factors"] if f["n"] == 3
        ]
        self.assertEqual(in_section, [three])
        self.assertNotIn(3, [f["n"] for f in after["topStrong"]])
        # Every other factor scores exactly as it did.
        for n, factor in got.items():
            if n != 3:
                self.assertEqual(factor["score"], before[n]["score"], n)
                self.assertEqual(
                    factor["unmeasured"], before[n]["unmeasured"], n
                )

    def test_untaught_tall_letters_leave_factor_6_unmeasured(self):
        before = by_number(score(None))
        self.assertFalse(before[6]["unmeasured"])
        got = by_number(score(profile.resolve({"class": untaught(TALL)})))
        self.assertTrue(got[6]["unmeasured"])
        self.assertEqual(got[6]["value"], "Not measured")
        self.assertFalse(got[3]["unmeasured"])

    def test_some_untaught_letters_change_no_score(self):
        ruleset = profile.resolve({"class": untaught(LOOPS[:3])})
        self.assertEqual(ruleset.emptied_classes, frozenset())
        self.assertEqual(score(ruleset), score(None))

    def test_same_page_same_profile_same_scores_whatever_ran_between(self):
        ruleset = profile.resolve({"class": untaught(LOOPS)})
        first = score(ruleset)
        score(None)
        score(profile.resolve({"class": untaught(TALL)}))
        self.assertEqual(score(ruleset), first)
        self.assertIsNone(profile.active())


def load_server():
    path = Path(__file__).resolve().parents[1] / "server/app.py"
    spec = importlib.util.spec_from_file_location("profile_test_server", path)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    return server


class RequestField(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = load_server()

    def setUp(self):
        self.fake = AsyncMock(return_value=read_payload("a cat"))
        scan = patch.object(self.server, "_report_payload", new=self.fake)
        scan.start()
        self.addCleanup(scan.stop)

    def post(self, text):
        """The same profile to both report routes."""
        answers = []
        with TestClient(self.server.app) as client:
            for route in ("/api/v2/reports", "/report-python"):
                answer = client.post(
                    route,
                    files={"image": ("test.png", b"synthetic")},
                    data={"profile": text},
                )
                answers.append(answer)
        return answers

    def test_a_refused_profile_answers_before_the_scan(self):
        cases = (
            (json.dumps({"class": {"health": {"set": "x"}}}), 422),
            ("{", 422),
            ("x" * (profile.MAX_BYTES + 1), 413),
        )
        for text, status in cases:
            for answer in self.post(text):
                self.assertEqual(answer.status_code, status)
                code = answer.json()["detail"]["error_code"]
                self.assertTrue(code.startswith("profile_"), code)
        self.fake.assert_not_called()

    def test_a_valid_profile_reaches_the_scan_as_its_ruleset(self):
        layers = {"class": {"exceptions": {"add": {"words": ["Pihu"]}}}}
        for answer in self.post(json.dumps(layers)):
            self.assertEqual(answer.status_code, 200)
            self.assertNotIn("Pihu", answer.text)
        for call in self.fake.await_args_list:
            ruleset = call.args[4]
            self.assertEqual(ruleset.hash, profile.resolve(layers).hash)


class CacheAndComparability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = load_server()

    def setUp(self):
        server = self.server
        server.cache._CACHE.clear()
        self.addCleanup(server.cache._CACHE.clear)
        self.scans = []
        self.kept = []
        patches = (
            patch.dict(server.cache._CFG, {"ttl_sec": 180}),
            patch.object(server, "_to_numpy", return_value=np.zeros((4, 4))),
            patch.object(server, "_report_python_process", new=self.scan),
            patch.object(server, "_cache_set", new=self.keep),
        )
        for one in patches:
            one.start()
            self.addCleanup(one.stop)

    def scan(self, *args):
        # (arr, raw, lang, expected_text, include_evidence, ruleset)
        self.scans.append(args[5])
        return read_payload("a good dog")

    def keep(self, key, payload):
        self.kept.append(key)
        self.server.cache.cache_set(key, payload)

    def report(self, ruleset):
        """One scan of the same photo; the cache keys it stored."""
        before = len(self.kept)
        upload = UploadFile(file=io.BytesIO(b"the same photo"))
        payload = asyncio.run(
            self.server._report_payload(upload, "en", "", True, ruleset)
        )
        return payload, self.kept[before:]

    def test_same_photo_and_profile_hit_the_cache(self):
        layers = {"class": untaught(LOOPS)}
        first, keys = self.report(profile.resolve(layers))
        second, again = self.report(profile.resolve(layers))
        self.assertEqual(first["_meta"]["cache"], "miss")
        self.assertEqual(second["_meta"]["cache"], "hit")
        self.assertEqual(len(self.scans), 1)
        self.assertEqual(len(keys), 1)
        self.assertEqual(again, [])
        self.assertEqual(first["ruleset"], second["ruleset"])

    def test_a_changed_profile_misses_and_says_so(self):
        plain, plain_keys = self.report(profile.resolve())
        layers = {"class": {"exceptions": {"add": {"words": ["Pihu"]}}}}
        custom, custom_keys = self.report(profile.resolve(layers))
        self.assertEqual(custom["_meta"]["cache"], "miss")
        self.assertEqual(len(self.scans), 2)
        self.assertNotEqual(plain_keys, custom_keys)
        self.assertEqual(plain["ruleset"], EN.hash)
        self.assertEqual(custom["ruleset"], profile.resolve(layers).hash)
        for p in (plain, custom):
            facts = comparison_data.comparability(p)
            self.assertEqual(facts["ruleset"], p["ruleset"])
        for p in (plain, custom):
            expanded = public_report(p, FREE)
            compact = compact_reports.build_compact(p, FREE)
            for report in (expanded, compact):
                self.assertEqual(report["ruleset"], p["ruleset"])
                self.assertEqual(
                    report["comparability"]["ruleset"], p["ruleset"]
                )
            self.assertNotIn("Pihu", json.dumps(expanded))

    def test_reports_and_refusals_match_the_contract(self):
        free = entitlements.access_for(None)
        ruleset = profile.resolve({"class": untaught(TALL)})
        for ok in (True, False):
            payload = realistic_payload(ok=ok)
            payload["ruleset"] = ruleset.hash
            expanded = public_report(payload, free)
            compact = compact_reports.build_compact(payload, free)
            self.assertEqual(expanded["ruleset"], payload["ruleset"])
            self.assertEqual(
                contract_schemas.errors("report-expanded", expanded), []
            )
            self.assertEqual(
                contract_schemas.errors("report-compact", compact), []
            )
        error = refused(
            self, {"class": {"health": {}}}, "profile_field_not_allowed"
        )
        self.assertEqual(
            contract_schemas.errors("error", {"detail": error.detail()}), []
        )


if __name__ == "__main__":
    unittest.main()
