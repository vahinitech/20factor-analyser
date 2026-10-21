# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""What each factor needs from a page, and the one check that marks a
factor "Not measured" when the page did not supply it (factor_needs.py,
docs/20-languages.md section 8, #207).

The check replaced three lists in scoring.py. These tests hold the old
behaviour: the same factors measured in each mode, and the same reasons
and scoring_inputs methods, word for word."""

import os
import sys
import unittest
from unittest import mock

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
sys.path.insert(0, SERVER_DIR)
import factor_needs  # noqa: E402
import ink_geometry  # noqa: E402
import scoring  # noqa: E402
from scoring_parts import advisory  # noqa: E402
from backend.tests.test_ink_geometry import SENTENCE, draw_page  # noqa: E402

# Measured from the line bands alone, on any page.
LINE_BANDS = {4, 5, 10}
FALLBACK = [{"text": "", "score": 0.0, "cv_fallback": True}]
INK_ROWS = [{"text": "", "score": 0.0, "cv_fallback": True, "ink_row": True}]
READ = [{"text": "hello world", "score": 0.9}]
TELUGU = "\u0c05\u0c2e\u0c4d\u0c2e \u0c28\u0c3e\u0c28\u0c4d\u0c28"


def measured(supplied):
    return {
        n
        for n in range(1, 21)
        if factor_needs.missing_kind(n, supplied) is None
    }


class TestNeedsTable(unittest.TestCase):
    def test_every_factor_has_needs_from_the_vocabulary(self):
        self.assertEqual(set(factor_needs.NEEDS), set(scoring._FACTOR_META))
        for n, alternatives in factor_needs.NEEDS.items():
            self.assertTrue(alternatives, n)
            for alt in alternatives:
                self.assertLessEqual(set(alt), set(factor_needs.VOCABULARY), n)

    def test_every_kind_has_its_reason(self):
        # "joined" has its entry with no words yet: they wait for the
        # owner's approval (availability.py, #277).
        for kind in set(factor_needs.KIND.values()):
            self.assertIn(kind, scoring._UNMEASURED_REASONS)
            if kind != "joined":
                self.assertTrue(scoring._UNMEASURED_REASONS[kind], kind)

    def test_pen_factors_need_the_sensor_and_only_they_do(self):
        for n, (sec, _name, _detail) in scoring._FACTOR_META.items():
            needs_sensor = any(
                "sensor" in alt for alt in factor_needs.NEEDS[n]
            )
            self.assertEqual(needs_sensor, sec == "dynamics", n)

    def test_a_photo_never_supplies_pen_data(self):
        for lines in (READ, FALLBACK, INK_ROWS):
            supplied = factor_needs.page_supplies(lines, 10, True)
            self.assertNotIn("sensor", supplied)
            for n in (13, 14, 15, 16):
                self.assertEqual(factor_needs.missing_kind(n, supplied), "imu")

    def test_a_read_page_measures_everything_but_the_pen(self):
        supplied = factor_needs.page_supplies(READ, 10, False)
        self.assertEqual(
            measured(supplied), set(range(1, 21)) - {13, 14, 15, 16}
        )

    def test_fallback_boxes_measure_only_the_line_bands(self):
        supplied = factor_needs.page_supplies(FALLBACK, 0, False)
        self.assertEqual(measured(supplied), LINE_BANDS)
        for n in (1, 2, 3, 6, 7, 8, 9, 11, 12, 17, 18, 19, 20):
            self.assertEqual(factor_needs.missing_kind(n, supplied), "ocr")

    def test_ink_rows_measure_exactly_7_8_11_12_and_20(self):
        supplied = factor_needs.page_supplies(INK_ROWS, 0, False)
        self.assertEqual(measured(supplied) - LINE_BANDS, {7, 8, 11, 12, 20})
        for n in (1, 2, 3, 6, 9, 17, 18, 19):
            self.assertEqual(factor_needs.missing_kind(n, supplied), "ocr")

    def test_one_read_line_counts_the_page_as_read(self):
        supplied = factor_needs.page_supplies(READ + INK_ROWS, 0, False)
        self.assertTrue(
            {"rows", "words", "graphemes", "confidence"} <= supplied
        )

    def test_no_latin_letters_leaves_loops_and_zones_unmeasured(self):
        supplied = factor_needs.page_supplies(READ, 0, False)
        self.assertEqual(
            measured(supplied), set(range(1, 21)) - {3, 6, 13, 14, 15, 16}
        )
        for n in (3, 6):
            self.assertEqual(factor_needs.missing_kind(n, supplied), "script")

    def test_zone_bands_measure_factor_6_on_any_page(self):
        for lines, latin in ((READ, 0), (FALLBACK, 0), (INK_ROWS, 0)):
            supplied = factor_needs.page_supplies(lines, latin, True)
            self.assertIsNone(factor_needs.missing_kind(6, supplied))

    def test_joined_cursive_leaves_only_letter_spacing_unmeasured(self):
        apart = factor_needs.page_supplies(READ, 10, False)
        joined = factor_needs.page_supplies(READ, 10, False, joined=True)
        self.assertEqual(measured(apart) - measured(joined), {9})
        self.assertEqual(factor_needs.missing_kind(9, joined), "joined")
        # Ink rows read nothing: that is the reason given, joined or not.
        rows = factor_needs.page_supplies(INK_ROWS, 0, False, joined=True)
        self.assertEqual(factor_needs.missing_kind(9, rows), "ocr")

    def test_nothing_read_is_reported_before_the_script(self):
        # Fallback boxes have no letters, Latin or not: the reason is
        # that nothing was read.
        supplied = factor_needs.page_supplies(FALLBACK, 0, False)
        for n in (3, 6):
            self.assertEqual(factor_needs.missing_kind(n, supplied), "ocr")


class TestNeedsOnPages(unittest.TestCase):
    def results(self, arr, lines):
        result = scoring.build_analysis(arr, lines, {}).to_dict()
        return {f["n"]: f for f in result["results"]}

    def test_a_telugu_page_in_ink_mode_measures_its_geometry(self):
        if ink_geometry.cv2 is None:
            self.skipTest("OpenCV unavailable")
        arr = draw_page([SENTENCE] * 4)
        rows = ink_geometry.find_rows(arr)
        ink_geometry.expect_words(rows, "\n".join(["అ ఆ ఇ ఈ"] * 4))
        by_n = self.results(arr, rows)
        got = {n for n, f in by_n.items() if not f["unmeasured"]}
        if by_n[6]["scoringInputs"]["method"] == "zone_geometry":
            got.discard(6)
        self.assertEqual(got - LINE_BANDS, {7, 8, 11, 12, 20})
        for n in (1, 2, 3, 9, 17, 18, 19):
            self.assertEqual(by_n[n]["unmeasuredKind"], "ocr", n)
            self.assertEqual(
                by_n[n]["scoringInputs"],
                {"method": "recognition_required", "features": {}},
            )
            self.assertEqual(
                by_n[n]["unmeasuredReason"],
                "Requires recognised text from the page.",
            )
            # A cross-bar note may follow (scoring.py adds it to 1).
            self.assertTrue(
                by_n[n]["evidence"].startswith(
                    "Text recognition did not read this page, so this "
                    "factor could not be measured."
                ),
                n,
            )
        for n in (13, 14, 15, 16):
            self.assertEqual(
                by_n[n]["scoringInputs"],
                {"method": "sensor_required", "features": {}},
            )
            self.assertEqual(
                by_n[n]["unmeasuredReason"],
                "Requires time-series data from the sensor pen.",
            )

    def test_a_page_with_no_latin_letters_says_so_for_3_and_6(self):
        arr = np.full((160, 300, 3), 255, dtype=np.uint8)
        lines = [
            {
                "text": "అమ్మ నాన్న",
                "score": 0.9,
                "box": [20, 30, 200, 30],
                "poly": [[20, 30], [220, 30], [220, 60], [20, 60]],
            }
        ]
        by_n = self.results(arr, lines)
        for n in (3, 6):
            f = by_n[n]
            self.assertTrue(f["unmeasured"], n)
            self.assertEqual(f["value"], "Not measured")
            self.assertEqual(f["unmeasuredKind"], "script")
            self.assertEqual(
                f["scoringInputs"],
                {
                    "method": "script_not_supported",
                    "features": {"latin_letters": 0},
                },
            )
            self.assertEqual(
                f["unmeasuredReason"],
                "Reads English letters; not measured on this script.",
            )
            self.assertEqual(
                f["evidence"],
                "This measure reads English letters, and none were "
                "recognised on this page.",
            )


def _style(verdict):
    share = {"cursive": 0.0, "print": 0.0, "mixed": 0.0, verdict: 1.0}
    return {
        "available": True,
        "wordsUsed": 3,
        "shares": share,
        "verdict": verdict,
        "quality": "good",
    }


def _state(factor):
    return factor["unmeasured"], factor["score"]


class TestJoinedCursive(unittest.TestCase):
    """Letter Spacing (9) on joined cursive: there are no gaps between
    letters, only pen lifts, so it is not measured (#277). The style
    check (style_analysis.py) decides; nothing else moves."""

    LINES = [
        {
            "text": "running minimum writing",
            "score": 0.9,
            "box": [20, 30, 260, 30],
            "poly": [[20, 30], [280, 30], [280, 60], [20, 60]],
        }
    ]

    def results(self, verdict):
        arr = np.full((160, 300, 3), 255, dtype=np.uint8)
        with mock.patch.object(
            advisory, "analyze_style", return_value=_style(verdict)
        ):
            result = scoring.build_analysis(arr, self.LINES, {}).to_dict()
        return {f["n"]: f for f in result["results"]}

    def test_a_cursive_page_leaves_letter_spacing_unmeasured(self):
        f = self.results("cursive")[9]
        self.assertTrue(f["unmeasured"])
        self.assertEqual(f["value"], "Not measured")
        self.assertEqual(f["unmeasuredKind"], "joined")
        self.assertIsNone(f["unmeasuredReason"])
        self.assertEqual(
            f["scoringInputs"],
            {"method": "letters_joined", "features": {"style": "cursive"}},
        )

    def test_only_letter_spacing_moves(self):
        joined = self.results("cursive")
        for verdict in ("print", "mixed"):
            other = self.results(verdict)
            moved = {n for n in other if _state(other[n]) != _state(joined[n])}
            self.assertEqual(moved, {9}, verdict)
            self.assertFalse(other[9]["unmeasured"], verdict)


if __name__ == "__main__":
    unittest.main()
