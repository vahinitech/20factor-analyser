# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# Tests for tbar_analysis.py: the coach's cross-bar rule. Synthetic
# lines are drawn with known stem/bar geometry (ground truth by
# construction): a shared bar across a double-t is detected as the
# craft, two separate bars as extra lifts, a bar riding over a
# neighbouring l as an overshoot, and pages without the letter
# patterns are honestly unavailable.

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tbar_analysis import analyze_tbars, line_tbar_events  # noqa: E402

H_M = 16  # x-height in px
H_U = 16  # ascender rise above the midline


def _blank_line_page():
    """White page tall enough for one line with ascenders."""
    return np.full((120, 400), 245, dtype=np.uint8)


def _draw_body(page, y_mid, x, width):
    """Dense middle-zone band, like letter bodies (as in zone tests)."""
    for col in range(x, x + width):
        if (col // 3) % 2 == 0:
            page[y_mid : y_mid + H_M, col] = 20


def _draw_stem(page, y_mid, x):
    """A tall vertical stroke rising H_U above the midline."""
    page[y_mid - H_U : y_mid + H_M, x : x + 2] = 20


def _draw_bar(page, y_mid, x0, x1):
    """A horizontal cross bar high in the ascender band."""
    row = y_mid - int(H_U * 0.7)
    page[row : row + 2, x0:x1] = 20


def _line_box(x, width):
    # detector-style box: covers the ascender band + middle zone, like
    # the OCR boxes the zone tests use
    return [x, 40 - H_U, width, H_M + H_U]


def _make_line(bars, stems, text):
    """One synthetic line at y_mid=40 with given stems and bars.

    stems: list of x positions. bars: list of (x0, x1) spans."""
    page = _blank_line_page()
    _draw_body(page, 40, 30, 320)
    for sx in stems:
        _draw_stem(page, 40, sx)
    for b0, b1 in bars:
        _draw_bar(page, 40, b0, b1)
    return page, [{"text": text, "score": 0.9, "box": _line_box(30, 320)}]


# --- event geometry against ground truth ------------------------------------


def test_shared_bar_across_double_t_detected():
    # two stems 24 px apart, one bar spanning both
    page, lines = _make_line(
        bars=[(150, 200)], stems=[160, 184], text="a little bottle"
    )
    events = line_tbar_events(page, lines[0]["box"])
    assert "shared" in events


def test_two_separate_bars_detected_as_extra_lifts():
    page, lines = _make_line(
        bars=[(152, 170), (178, 196)],
        stems=[160, 184],
        text="a little bottle",
    )
    events = line_tbar_events(page, lines[0]["box"])
    assert "separate" in events
    assert "shared" not in events


def test_contained_bar_beside_tall_letter_is_clean():
    # t stem with a short bar, l stem with none: bar stays on the t
    page, lines = _make_line(
        bars=[(152, 168)], stems=[160, 200], text="at least"
    )
    events = line_tbar_events(page, lines[0]["box"])
    assert "contained" in events
    assert "overshoot" not in events


def test_bar_riding_over_the_l_is_an_overshoot():
    # bar starts on the t stem and runs most of the way to the l
    page, lines = _make_line(
        bars=[(152, 196)], stems=[160, 200], text="at least"
    )
    events = line_tbar_events(page, lines[0]["box"])
    assert "overshoot" in events


# --- page-level aggregation and honesty -------------------------------------


def test_page_without_patterns_is_unavailable():
    page, lines = _make_line(
        bars=[(150, 200)], stems=[160, 184], text="sunny morning"
    )
    out = analyze_tbars(page, lines)
    assert out["available"] is False
    assert "no double-t" in out["reason"]


def test_tt_text_but_no_geometry_is_unavailable():
    # text says tt, but the ink has no tall stems at all
    page = _blank_line_page()
    _draw_body(page, 40, 30, 320)
    lines = [{"text": "a little", "score": 0.9, "box": _line_box(30, 320)}]
    out = analyze_tbars(page, lines)
    assert out["available"] is False
    assert "not measurable" in out["reason"]


def test_shared_bar_page_flags_the_craft():
    page, lines = _make_line(
        bars=[(150, 200)], stems=[160, 184], text="a little bottle"
    )
    out = analyze_tbars(page, lines)
    assert out["available"] is True
    assert out["sharedBars"] >= 1
    assert "double-t-single-bar" in out["flags"]
    assert "double-t-extra-lifts" not in out["flags"]


def test_separate_bars_page_flags_extra_lifts():
    page, lines = _make_line(
        bars=[(152, 170), (178, 196)],
        stems=[160, 184],
        text="a little bottle",
    )
    out = analyze_tbars(page, lines)
    assert out["available"] is True
    assert out["separateBars"] >= 1
    assert "double-t-extra-lifts" in out["flags"]


def test_overshoot_page_flags_the_mistake():
    page, lines = _make_line(
        bars=[(152, 196)], stems=[160, 200], text="at least"
    )
    out = analyze_tbars(page, lines)
    assert out["available"] is True
    assert out["overshoots"] >= 1
    assert "t-bar-overshoot" in out["flags"]


def test_ll_cannot_masquerade_as_tt():
    # two tall stems, no bars, text without tt/tl patterns ("small"
    # has ll but the gate needs a t next to it) -> unavailable
    page, lines = _make_line(bars=[], stems=[160, 184], text="a small dog")
    out = analyze_tbars(page, lines)
    assert out["available"] is False


# --- full-pipeline integration ----------------------------------------------


def test_build_analysis_reports_tbar_profile():
    from scoring import build_analysis

    page, lines = _make_line(
        bars=[(150, 200)], stems=[160, 184], text="a little bottle"
    )
    rgb = np.stack([page] * 3, axis=-1)
    d = build_analysis(rgb, lines, layout={}).to_dict()
    assert "tbarProfile" in d
    tp = d["tbarProfile"]
    assert isinstance(tp, dict)
    # single-line synthetic pages may or may not clear every gate in
    # the wider pipeline; the contract is presence + honesty
    assert "available" in tp
    if tp["available"]:
        f16 = [r for r in d["results"] if r["n"] == 16][0]
        assert "Cross-bar check" in f16["evidence"]
