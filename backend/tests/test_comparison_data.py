# SPDX-License-Identifier: AGPL-3.0-only
"""Data the paid before/after comparison reads from a version-2 report.

Built from the synthetic case-study pages in docs/examples, whose
analysis is real scorer output (docs/09-case-studies.md); no real
handwriting, names or keys.
"""

import copy
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compact_reports
import comparison_data
import contract_schemas
import entitlements
import computer_vision as vision
import scoring
from report_contract import public_report

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "docs" / "examples"
_spec = importlib.util.spec_from_file_location(
    "planted_pages", ROOT / "scripts" / "planted_pages.py"
)
planted = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(planted)
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


def zigzag(ch):
    h = 2.0 if ch in planted.TALL or ch in planted.LOW else 1.0
    xs = np.linspace(0, 0.5, 6)
    return [
        np.array(list(zip(xs, [0.0 if i % 2 == 0 else h for i in range(6)])))
    ]


LETTERS = {
    ch: [zigzag(ch)] for ch in set("".join(planted.SENTENCES).replace(" ", ""))
}


def scanned_payload(kind="tilted_line", seed=3, zoom=2):
    """A planted page (drawn letters, no real handwriting) through the
    real evidence and measurement code, as if the photo had been `zoom`
    times larger than the analyser's working copy."""
    img, lines, _truth = planted.build_page(
        LETTERS, np.random.default_rng(seed), kind, "plain"
    )
    vl = vision.vl_analyze(img, lines)
    height, width = img.shape[:2]
    return {
        "ok": True,
        "full_text": "\n".join(l["text"] for l in lines),
        "hand_lines": lines,
        "proc_w": width,
        "proc_h": height,
        "photo_w": width * zoom,
        "photo_h": height * zoom,
        "analysis": scoring.build_analysis(img, lines, {}).to_dict(),
        "factor_regions": vl["factor_regions"],
        "measurements": vl["measurements"],
    }


class FactorMarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if vision.cv2 is None:
            raise unittest.SkipTest("OpenCV unavailable")
        cls.payload = scanned_payload()

    def marks(self, numbers=range(1, 21)):
        return comparison_data.factor_marks(self.payload, set(numbers))

    def test_marks_are_in_the_photos_pixels(self):
        marks = self.marks()
        for n in range(1, 21):
            region = self.payload["factor_regions"][str(n)]
            if region["status"] == "unavailable":
                continue
            first = marks[str(n)][0]
            self.assertEqual(first["role"], "region")
            self.assertEqual(first["box"], [2 * v for v in region["bbox"]])

    def test_baseline_line_follows_the_measured_slope(self):
        slope = self.payload["measurements"]["slope"]["line"]["baseline"]
        line = next(m for m in self.marks()["7"] if m["role"] == "baseline")
        self.assertEqual(line["shape"], "line")
        self.assertEqual(
            line["points"],
            [[round(2 * x, 1), round(2 * y, 1)] for x, y in slope],
        )

    def test_size_band_and_margin_are_drawn_for_their_factors(self):
        marks = self.marks()
        roles5 = {m["role"] for m in marks["5"]}
        self.assertTrue({"baseline", "midline"} <= roles5)
        start = next(m for m in marks["10"] if m["role"] == "usual_start")
        margin = self.payload["measurements"]["margin"]
        self.assertEqual(
            start["points"][0][0], round(2 * margin["usual_x"], 1)
        )

    def test_places_keep_their_role_and_measure(self):
        places = self.payload["factor_regions"]["5"].get("places") or []
        self.assertTrue(places)
        boxes = [m for m in self.marks()["5"] if m.get("measure")]
        self.assertEqual(len(boxes), len(places))
        self.assertEqual(
            [m["role"] for m in boxes], [p["role"] for p in places]
        )

    def test_sensor_factors_have_no_marks(self):
        marks = self.marks()
        for n in (13, 14, 15, 16):
            self.assertEqual(marks[str(n)], [])

    def test_reports_carry_marks_and_the_photo_size(self):
        pro = public_report(self.payload, PRO)
        self.assertEqual(
            pro["evidence"]["photo_width"], self.payload["photo_w"]
        )
        self.assertIn("marks", pro["evidence"]["factor_regions"]["7"])
        free = compact_reports.build_compact(self.payload, FREE, {"evidence"})
        regions = free["evidence"]["factor_regions"]
        self.assertEqual(sorted(regions, key=int), ["1", "5", "7", "8", "18"])
        self.assertTrue(all("marks" in r for r in regions.values()))
        self.assertNotIn("data:", json.dumps(self.marks()))

    def test_reports_with_marks_match_the_schemas(self):
        for tier in ("free", "pro"):
            access = entitlements.access_for(None)
            if tier == "pro":
                access = dict(
                    access,
                    customer_id="cus_" + "0" * 24,
                    authenticated=True,
                    tier="pro",
                    plan_tier="pro",
                    subscription_status="active",
                    expires_at=1900000000,
                )
            fields = (
                compact_reports.OPTIONAL_FIELDS
                if tier == "pro"
                else {"text", "evidence"}
            )
            compact = compact_reports.build_compact(
                self.payload, access, fields
            )
            self.assertEqual(
                contract_schemas.errors("report-compact", compact), []
            )
            if tier == "pro":
                expanded = public_report(self.payload, access)
                self.assertEqual(
                    contract_schemas.errors("report-expanded", expanded), []
                )

    def test_unknown_photo_size_gives_no_marks(self):
        payload = dict(self.payload)
        del payload["photo_w"]
        self.assertIsNone(comparison_data.factor_marks(payload, {7}))
        body = compact_reports.build_compact(payload, PRO, {"evidence"})
        self.assertNotIn("marks", body["evidence"]["factor_regions"]["7"])

    def test_same_page_same_marks(self):
        again = scanned_payload()
        self.assertEqual(
            comparison_data.factor_marks(again, set(range(1, 21))),
            self.marks(),
        )


def jpeg(width, height, orientation=None):
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(
        buffer, "JPEG", exif=exif.tobytes()
    )
    return buffer.getvalue()


class PhotoSizeTests(unittest.TestCase):
    def test_size_as_a_viewer_shows_it(self):
        self.assertEqual(vision.photo_size(jpeg(300, 200)), (300, 200))
        # Orientation 6: stored landscape, shown portrait.
        self.assertEqual(vision.photo_size(jpeg(300, 200, 6)), (200, 300))
        self.assertEqual(vision.photo_size(jpeg(300, 200, 3)), (300, 200))

    def test_matches_the_decoded_page(self):
        raw = jpeg(320, 240, 8)
        shown = vision.decode_image(raw)
        self.assertEqual(vision.photo_size(raw), shown.size)

    def test_unreadable_upload_gives_none(self):
        self.assertIsNone(vision.photo_size(b"not an image"))


if __name__ == "__main__":
    unittest.main()
