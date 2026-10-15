# SPDX-License-Identifier: AGPL-3.0-only
"""Data the paid before/after comparison reads from a version-2 report.

Built from the synthetic case-study pages in docs/examples, whose
analysis is real scorer output (docs/09-case-studies.md); no real
handwriting, names or keys.
"""

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compact_reports
import comparison_data
from report_contract import public_report

EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "examples"
PRO = {"tier": "pro"}
FREE = {"tier": "free"}


def case_payload(name="case1-baseline-before"):
    analysis = json.loads((EXAMPLES / f"{name}.json").read_text())
    return {
        "ok": True,
        "full_text": "the quick brown fox jumps over the lazy dog",
        "analysis": analysis,
    }


class SectionScoreTests(unittest.TestCase):
    def test_sections_are_the_engines_own_averages(self):
        payload = case_payload()
        sections = comparison_data.section_scores(payload["analysis"])
        self.assertEqual(
            [s["id"] for s in sections],
            ["structure", "spatial", "dynamics", "style"],
        )
        for mine, engine in zip(sections, payload["analysis"]["sections"]):
            self.assertEqual(mine["score"], engine["avg"])
            self.assertEqual(mine["normalized"], engine["avg100"])
            self.assertEqual(mine["weight"], engine["weight"])
            self.assertEqual(
                mine["scored_factor_count"], engine["scoredCount"]
            )

    def test_overall_is_rebuilt_from_the_published_sections(self):
        for name in ("case1-baseline-before", "case3-size-margin-after"):
            payload = case_payload(name)
            sections = comparison_data.section_scores(payload["analysis"])
            rebuilt = sum(
                (s["normalized"] or 0) * s["weight"] for s in sections
            )
            self.assertEqual(
                round(rebuilt), payload["analysis"]["overall"], name
            )

    def test_unmeasured_section_is_null_not_zero(self):
        sections = comparison_data.section_scores(case_payload()["analysis"])
        dynamics = next(s for s in sections if s["id"] == "dynamics")
        self.assertIsNone(dynamics["score"])
        self.assertIsNone(dynamics["normalized"])
        self.assertEqual(dynamics["weight"], 0)

    def test_pro_gets_sections_in_both_formats_free_in_neither(self):
        expanded = public_report(case_payload(), PRO)
        compact = compact_reports.build_compact(case_payload(), PRO)
        self.assertEqual(len(expanded["sections"]), 4)
        self.assertEqual(
            [(s["id"], s["s"]) for s in compact["sections"]],
            [(s["id"], s["score"]) for s in expanded["sections"]],
        )
        self.assertNotIn("sections", public_report(case_payload(), FREE))
        self.assertNotIn(
            "sections", compact_reports.build_compact(case_payload(), FREE)
        )

    def test_builders_leave_the_cached_payload_alone(self):
        payload = case_payload()
        before = copy.deepcopy(payload)
        public_report(payload, PRO)
        compact_reports.build_compact(payload, PRO, {"evidence", "text"})
        self.assertEqual(payload, before)


def read_payload(text, level="high", printed=0, langs=("en",)):
    payload = case_payload()
    payload["full_text"] = text
    payload["rec_langs"] = list(langs)
    payload["analysis"]["recognition"] = {
        "level": level,
        "hand_lines": text.count("\n") + 1,
        "printed_lines": printed,
        "passage_aligned": level == "passage-verified",
    }
    return payload


class ComparabilityTests(unittest.TestCase):
    def test_counts_words_and_characters_without_the_text(self):
        payload = read_payload("Pihu can fly\nBheema reads a book")
        facts = comparison_data.comparability(payload)
        self.assertEqual(facts["lines"], 2)
        self.assertEqual(facts["words"], 7)
        self.assertEqual(facts["characters"], 26)
        self.assertEqual(facts["script"], "latin")
        self.assertEqual(facts["languages"], ["en"])
        self.assertEqual(facts["page"], "handwriting")
        self.assertNotIn("Pihu", json.dumps(facts))

    def test_script_follows_the_letters_read(self):
        telugu = comparison_data.comparability(
            read_payload("అమ్మ ఆవు", langs=("te",))
        )
        self.assertEqual(telugu["script"], "telugu")
        mixed = comparison_data.comparability(
            read_payload("Tara అమ్మ ఆవు Vahini", langs=("te", "en"))
        )
        self.assertEqual(mixed["script"], "mixed")
        self.assertEqual(mixed["languages"], ["en", "te"])
        digits = comparison_data.comparability(read_payload("12 + 30"))
        self.assertEqual(digits["script"], "other")

    def test_nothing_read_gives_null_counts_not_zero(self):
        facts = comparison_data.comparability(
            read_payload("", level="unavailable")
        )
        self.assertIsNone(facts["words"])
        self.assertIsNone(facts["characters"])
        self.assertIsNone(facts["script"])
        self.assertEqual(facts["reading"], "unavailable")

    def test_print_left_out_of_scoring_is_reported(self):
        facts = comparison_data.comparability(
            read_payload("Vidhya writes", printed=3)
        )
        self.assertEqual(facts["printed_lines"], 3)
        self.assertEqual(facts["page"], "handwriting_with_print")

    def test_every_tier_gets_it_on_success_only(self):
        payload = read_payload("Seetha and Rama")
        for access in (FREE, PRO):
            self.assertEqual(
                public_report(payload, access)["comparability"]["words"], 3
            )
            compact = compact_reports.build_compact(payload, access)
            self.assertEqual(compact["comparability"]["words"], 3)
        payload["ok"] = False
        self.assertNotIn("comparability", public_report(payload, FREE))
        self.assertNotIn(
            "comparability", compact_reports.build_compact(payload, PRO)
        )

    def test_same_payload_same_facts(self):
        payload = read_payload("Chinnu draws a cat")
        self.assertEqual(
            comparison_data.comparability(payload),
            comparison_data.comparability(copy.deepcopy(payload)),
        )


if __name__ == "__main__":
    unittest.main()
