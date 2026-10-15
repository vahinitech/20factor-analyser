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


if __name__ == "__main__":
    unittest.main()
