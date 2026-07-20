# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# Tests for zone_analysis.py: the coaches' three-zone 1:2 letter-size
# rule measured from ink. Synthetic pages are drawn with known zone
# geometry, so every assertion checks the algorithm against ground
# truth: correct 1:2 writing scores high, one-zone writing scores low,
# and the coach's three named mistakes are flagged.

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zone_analysis import (  # noqa: E402
    ZONE_TARGET_REACH,
    analyze_zones,
    line_zone_bands,
    zone_score,
)


def _draw_line(page, x, y_mid_top, h_m, h_u, h_l, width):
    """Draw one synthetic text line: a dense x-height band with sparse
    ascender/descender strokes, like real writing's projection profile.
    y_mid_top is the midline row; baseline = y_mid_top + h_m - 1."""
    # middle zone: dense ink across the width (letter bodies)
    for col in range(x, x + width):
        if (col // 3) % 2 == 0:  # ~half the columns inked
            page[y_mid_top : y_mid_top + h_m, col] = 20
    # ascender strokes: a few columns reaching h_u above the midline
    if h_u > 0:
        for col in range(x + 6, x + width, 24):
            page[y_mid_top - h_u : y_mid_top + h_m, col : col + 2] = 20
    # descender strokes: a few columns hanging h_l below the baseline
    if h_l > 0:
        for col in range(x + 14, x + width, 30):
            page[
                y_mid_top : y_mid_top + h_m + h_l,
                col : col + 2,
            ] = 20


def _page_with_lines(n_lines, h_m, h_u, h_l, text):
    """White page with n_lines synthetic lines; returns (gray, lines)."""
    width = 320
    pitch = (h_m + h_u + h_l) * 3 + 30
    page = np.full((pitch * (n_lines + 1), 400), 245, dtype=np.uint8)
    lines = []
    for i in range(n_lines):
        y_mid = pitch * (i + 1)
        _draw_line(page, 30, y_mid, h_m, h_u, h_l, width)
        # detector-style box around the middle band (tight, like OCR)
        lines.append(
            {
                "text": text,
                "score": 0.9,
                "box": [30, y_mid - h_u, width, h_m + h_u + h_l],
            }
        )
    return page, lines


GOOD_TEXT = "the quick fog jumped by that lazy dog height"  # asc + desc


# --- band detection against ground truth ------------------------------------


def test_line_bands_recover_known_geometry():
    page, lines = _page_with_lines(1, h_m=20, h_u=20, h_l=20, text=GOOD_TEXT)
    z = line_zone_bands(page, lines[0]["box"])
    assert z is not None
    assert abs(z["h_m"] - 20) <= 3
    assert abs(z["asc_reach"] - 2.0) <= 0.25
    assert abs(z["desc_reach"] - 2.0) <= 0.25


def test_unusable_crop_returns_none():
    page = np.full((60, 60), 245, dtype=np.uint8)  # blank paper
    assert line_zone_bands(page, [5, 5, 40, 20]) is None


# --- the 1:2 rule scored ------------------------------------------------------


def test_correct_one_to_two_writing_scores_high():
    page, lines = _page_with_lines(3, h_m=20, h_u=20, h_l=20, text=GOOD_TEXT)
    z = analyze_zones(page, lines)
    assert z["available"] is True
    assert z["flags"] == []
    assert zone_score(z) >= 8.0


def test_single_zone_writing_scores_low_and_is_flagged():
    # the coach's first mistake: everything squashed into one zone
    page, lines = _page_with_lines(3, h_m=20, h_u=2, h_l=2, text=GOOD_TEXT)
    z = analyze_zones(page, lines)
    assert z["available"] is True
    assert "single-zone" in z["flags"]
    assert zone_score(z) <= 3.0


def test_upper_heavy_writing_is_flagged():
    # the coach's second mistake: heavy importance to the upper zone
    page, lines = _page_with_lines(3, h_m=14, h_u=36, h_l=14, text=GOOD_TEXT)
    z = analyze_zones(page, lines)
    assert z["available"] is True
    assert "upper-heavy" in z["flags"]
    assert zone_score(z) < 8.0


def test_target_is_the_coaches_rule():
    assert ZONE_TARGET_REACH == 2.0


# --- honest fallbacks ----------------------------------------------------------


def test_non_latin_page_is_unavailable_with_reason():
    page, lines = _page_with_lines(3, h_m=20, h_u=20, h_l=20, text="123 456")
    z = analyze_zones(page, lines)
    assert z["available"] is False
    assert "Latin" in z["reason"]


def test_too_few_lines_is_unavailable():
    page, lines = _page_with_lines(1, h_m=20, h_u=20, h_l=20, text=GOOD_TEXT)
    z = analyze_zones(page, lines)
    assert z["available"] is False


# --- integration: factor 6 uses the measurement -------------------------------


def test_build_analysis_scores_factor6_from_zones():
    import scoring

    h_m, h_u, h_l = 20, 20, 20
    page, lines = _page_with_lines(4, h_m, h_u, h_l, GOOD_TEXT)
    rgb = np.stack([page] * 3, axis=2)
    # polys keep the other factors happy
    for l in lines:
        x, y, w, h = l["box"]
        l["poly"] = [[x, y], [x + w, y]]
    a = scoring.build_analysis(rgb, lines, {})
    d = a.to_dict()
    f6 = next(r for r in d["results"] if r["n"] == 6)
    assert "Measured zone bands" in f6["evidence"]
    assert f6["score"] >= 8.0
    zp = d["zoneProfile"]
    assert zp["method"].startswith("measured")
    assert abs(zp["ascenderReach"] - 2.0) <= 0.3
