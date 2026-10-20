# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# features.py - the measurements (fx) the factor formulas read: line
# boxes, word gaps, letter sizes, ink variance and what the ink inside
# the lines shows (letter_geometry.py, ink_geometry.py).

import math
import re

import numpy as np

from baseline_track import track_rows
import letter_geometry
import computer_vision
import ink_geometry
import languages
from scoring_parts.page import (
    _detilted_left_x,
    _group_lines_by_rows,
    _page_tilt_degrees,
)
from scoring_parts.stats import _cv, _std, mean

try:
    import cv2
except Exception:
    cv2 = None

# Letter facts come from the language pack (backend/languages, #206):
# the letters counted, those that close a loop, and the tall ones that
# rise above the small letters or drop below the line.
_PACK = languages.language()
_LETTER_RE = re.compile(_PACK.char_class("letter"))
_LOOP_RE = re.compile(_PACK.char_class("loop"))
_TALL_RE = re.compile(
    _PACK.char_class("ascender") + "|" + _PACK.char_class("descender")
)


def _extract_features(arr: np.ndarray, lines, layout):
    h, w = arr.shape[:2]
    boxes = [l.get("box") or [0, 0, 0, 0] for l in lines]
    widths = [float(max(1.0, b[2])) for b in boxes]
    heights = [float(max(1.0, b[3])) for b in boxes]
    # See _detilted_left_x's docstring: corrects for camera tilt before
    # margin consistency is measured, so Margin Discipline (factor 10)
    # scores the handwriting and not the photo angle.
    tilt_deg = _page_tilt_degrees(lines)
    # One left edge per row: a piece of a line left on its own to the
    # right (words the reader never found between) is not a line start,
    # and counting its edge as one scored Margin Discipline 0 on two UJI
    # test pages.
    lefts = [
        _detilted_left_x(l.get("box") or [0, 0, 0, 0], tilt_deg, w, h)
        / max(1.0, float(w))
        for l in computer_vision.line_starts(arr, lines)
    ]
    scores = [float(l.get("score", 0.0)) for l in lines]
    texts = [str(l.get("text", "") or "") for l in lines]
    n_lines = len(lines)

    n_words = sum(len(re.findall(r"\S+", t)) for t in texts)
    n_chars = sum(len(re.sub(r"\s+", "", t)) for t in texts)
    char_w = (
        [
            widths[i] / max(1, len(re.sub(r"\s+", "", texts[i])))
            for i in range(n_lines)
        ]
        if n_lines
        else []
    )

    y_centers = [float(b[1] + b[3] * 0.5) / max(1.0, float(h)) for b in boxes]
    line_spacing = []
    if len(y_centers) >= 2:
        ys = sorted(y_centers)
        line_spacing = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)]

    slopes = []
    signed_slopes = []
    for l in lines:
        poly = l.get("poly") or []
        if len(poly) >= 2:
            x0, y0 = float(poly[0][0]), float(poly[0][1])
            x1, y1 = float(poly[1][0]), float(poly[1][1])
            dx = max(1e-6, x1 - x0)
            ang = math.degrees(math.atan2(y1 - y0, dx))
            slopes.append(abs(ang))
            signed_slopes.append(ang)
        # Lines without a usable poly are skipped entirely (not given a
        # fake 0.0) so they don't silently pull line_slope_abs toward
        # "level" while being excluded from line_slope_signed_med.

    rows = _group_lines_by_rows(lines)
    # Kalman-smoothed baseline per row (issue #31): every word informs
    # the slope, instead of the first two vertices of one OCR polygon.
    # Rows under 3 words are skipped; the poly-based estimate below
    # remains the fallback so sparse pages behave exactly as before.
    kf = track_rows(rows)
    # Word gaps inside each line, from its ink. Gaps between two OCR
    # boxes on one row are not measured: after detector.join_row_pieces
    # the only boxes left side by side are further apart than any word
    # gap (a column, or words the reader never found), and one such
    # "gap" of seven line heights scored Word Spacing 0 on four of the
    # UJI test pages. Without ink gaps a page read as one box per line
    # had none at all, and _cv([]) == 0 scored a perfect 10.
    word_gaps = []
    for l in lines:
        line_gaps = computer_vision.line_word_gaps(arr, l)
        if line_gaps:
            line_h = float(max(1.0, (l.get("box") or [0, 0, 0, 1])[3]))
            word_gaps.extend(g / line_h for g in line_gaps)

    full = " ".join(texts)
    digits_ratio = (
        len(re.findall(r"\d", full)) / max(1, len(full)) if full else 0.0
    )
    # Loop, tall and letter totals come from what the reader saw in the
    # ink. With a copied passage the line's text is the passage, and
    # counting its letters gave loops and tall letters the ink never
    # showed (#209, #200's fallback). The expected bowl count below
    # (_stroke_features) stays on the passage: it says what should be
    # there, the ink says what is.
    seen = " ".join(
        str(l.get("text_as_read", l.get("text", "")) or "") for l in lines
    )
    loop_chars = len(_LOOP_RE.findall(seen))
    alpha_chars = len(_LETTER_RE.findall(seen))
    loop_ratio = (loop_chars / max(1, alpha_chars)) if alpha_chars else 0.0
    tall_chars = len(_TALL_RE.findall(seen))
    tall_ratio = (tall_chars / max(1, alpha_chars)) if alpha_chars else 0.0

    ink_cv = 0.0
    if cv2 is not None:
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        vals = []
        for b in boxes[:80]:
            x, y, bw, bh = [int(round(v)) for v in b]
            x0 = max(0, x)
            y0 = max(0, y)
            x1 = min(w, x + max(1, bw))
            y1 = min(h, y + max(1, bh))
            if x1 <= x0 or y1 <= y0:
                continue
            patch = gray[y0:y1, x0:x1]
            if patch.size:
                vals.append(float(np.std(patch.astype(np.float32))))
        ink_cv = _cv(vals) if vals else 0.0

    # Letter size from the small-letter height of each word, measured along
    # its line's own baseline (letter_geometry.py). Line box heights grow
    # with a line's slope, so they counted tilt as size (#135); they remain
    # the fallback when fewer than three words can be measured.
    geo = letter_geometry.measure_page(arr, lines)
    word_xh = [
        wd["xheight"] for g in geo if g for wd in g["words"] if wd["xheight"]
    ]
    size_by_words = len(word_xh) >= 3
    xh_med = float(np.median(word_xh)) if word_xh else 0.0
    words_off_size = (
        sum(1 for v in word_xh if abs(v / xh_med - 1.0) >= SIZE_OFF)
        / len(word_xh)
        if size_by_words and xh_med > 0
        else None
    )

    fx = {
        **_stroke_features(geo, texts),
        "size_cv": _cv(word_xh) if size_by_words else _cv(heights),
        "size_basis": "words" if size_by_words else "lines",
        "words_off_size": words_off_size,
        "size_count": len(word_xh) if size_by_words else n_lines,
        "n_lines": n_lines,
        "n_words": n_words,
        "n_chars": n_chars,
        "avg_score": mean(scores),
        "height_cv": _cv(heights),
        "width_cv": _cv(widths),
        "char_w_cv": _cv(char_w),
        "left_cv": _cv(lefts),
        "line_slope_abs": mean(slopes),
        "line_slope_std": _std(slopes),
        # median SIGNED line angle: >0 means lines descend left-to-right
        # (image y grows downward), i.e. the writing sinks below the rule
        "line_slope_signed_med": (
            float(np.median(kf["slopes_deg"]))
            if kf["rows_used"]
            else (float(np.median(signed_slopes)) if signed_slopes else 0.0)
        ),
        "baseline_wave_med": (
            float(np.median(kf["waviness"])) if kf["rows_used"] else None
        ),
        "baseline_rows_tracked": kf["rows_used"],
        "line_spacing_cv": _cv(line_spacing),
        "word_gap_cv": _cv(word_gaps),
        "word_gap_count": len(word_gaps),
        # Latin letters recognised on the page. Loops (3) and letter zones
        # (6) count Latin letters only, so a page in another script, such
        # as Telugu, has none to measure.
        "latin_letters": alpha_chars,
        "digits_ratio": digits_ratio,
        "loop_ratio": loop_ratio,
        "tall_ratio": tall_ratio,
        "ink_cv": ink_cv,
        "layout_complexity": float(
            layout.get("layout_complexity", 0.0) or 0.0
        ),
    }
    if lines and all(l.get("ink_row") for l in lines):
        fx.update(_ink_features(arr, lines))
    return fx


def _ink_features(arr, lines):
    """Size, line angle and word gaps for rows found from the ink
    (ink_geometry.py): the reader drew no box, so angles come from each
    row's fitted baseline and sizes from its letters."""
    ink = ink_geometry.page_features(arr, lines)
    out = {
        "line_slope_abs": mean(ink["angles"]),
        "line_slope_std": _std(ink["angles"]),
        "line_slope_signed_med": (
            float(np.median(ink["signed"])) if ink["signed"] else 0.0
        ),
        "baseline_rows_tracked": 0,
        "baseline_wave_med": None,
        "word_gap_cv": _cv(ink["gaps"]),
        "word_gap_count": len(ink["gaps"]),
        "n_words": ink["words"],
    }
    if len(ink["bodies"]) >= 3:
        out.update(
            {
                "size_cv": _cv(ink["bodies"]),
                "size_basis": "letter groups",
                "size_count": len(ink["bodies"]),
            }
        )
    return out


# A word's small letters this far from the page's usual are off size
# (marked_places.py marks the same words).
SIZE_OFF = 0.30
BOWL_LETTERS = _PACK.letter_set("bowl")
MIN_BOWLS = 3


def _stroke_features(geo, texts):
    """What the ink inside the lines shows (letter_geometry.py) for the
    factors whose names it measures: closed bowls against the letters
    read that have one (a, b, d, e, g, o, p, q) (3), how jagged the strokes are (4), how even the gaps
    between letters are (9), how far words wander off their line's
    baseline (11), and how much the words' lean varies (17). None where
    the page gives too little to measure."""
    lines = [g for g in geo if g]
    expected = sum(1 for t in texts for ch in t.lower() if ch in BOWL_LETTERS)
    bowls = sum(g["bowls"] for g in lines)
    gaps = [x for g in lines for x in g["letter_gaps"]]
    waves = [g["wave"] for g in lines if g.get("wave") is not None]
    offs = [abs(wd["off"]) for g in lines for wd in g["words"]]
    slants = [
        wd["slant"]
        for g in lines
        for wd in g["words"]
        if wd.get("slant") is not None
    ]
    return {
        "bowl_share": (bowls / expected if expected >= MIN_BOWLS else None),
        "letter_gap_cv": _cv(gaps) if len(gaps) >= 5 else None,
        "line_wave": float(np.max(waves)) if waves else None,
        # Share of words whose baseline sits WORD_OFF small letters or
        # more off their line's (letter_geometry.WORD_DROP_LOOK).
        "words_off_line": (
            sum(1 for o in offs if o >= letter_geometry.WORD_DROP_LOOK)
            / len(offs)
            if len(offs) >= 3
            else None
        ),
        "slant_std": _std(slants) if len(slants) >= 3 else None,
    }
