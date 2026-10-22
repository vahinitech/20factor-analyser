# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# features.py - the measurements (fx) the factor formulas read: line
# boxes, word gaps, letter sizes, ink variance and what the ink inside
# the lines shows (letter_geometry.py, ink_geometry.py).

import math
import re

import numpy as np

from vision.baseline_track import track_rows
from vision import letter_geometry
from vision import computer_vision
from vision import ink_geometry
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


# Margin Discipline (factor 10): a row that starts more than this share
# of the page width right of the other rows' median start is a centred
# title, a date or a signature, not a line that missed the margin (#201).
MARGIN_OUTLIER = 0.15


def _margin_spread(lefts):
    """How far the rows' starts stray from the margin: the mean distance
    from the median start, as a share of the page width, leaving out
    starts far right of the median (MARGIN_OUTLIER).

    The coefficient of variation it replaces divides by the mean start,
    so the same spread scored worse the nearer the writing sat to the
    page's edge, and one date at the right took a page to 0 (#201). The
    median of the distances would ignore one indented line among four,
    so their mean is taken around the median instead."""
    if not lefts:
        return 0.0
    mid = float(np.median(lefts))
    kept = [x for x in lefts if x - mid <= MARGIN_OUTLIER]
    mid = float(np.median(kept))
    return mean([abs(x - mid) for x in kept])


# Spacing (factors 8 and 9, #197): a gap more than ODD_GAP times the
# usual one stands out, and so does a word gap under NARROW_WORD_GAP of
# the page's median word gap (a planted gap a quarter as wide is still
# wider than the gaps between letters, so it is compared with the other
# word gaps). Letter gaps under GAP_FLOOR small letters are too small to
# compare by ratio: most letter gaps are a few pixels, and one pixel
# more would double them.
ODD_GAP = 2.0
NARROW_WORD_GAP = 0.5
GAP_FLOOR = 0.10


def _word_spacing(gaps):
    """How far the word gaps stray from their median, as a share of it,
    and the share of gaps that stand out (narrower than NARROW_WORD_GAP
    or wider than ODD_GAP times the median).

    The coefficient of variation it replaces squared every distance, so
    one odd gap and an evenly uneven page looked alike, and a scale
    loose enough for neat writing lost a planted gap (#197). The mean
    distance from the median keeps every gap counted, as Margin
    Discipline does (_margin_spread), and an odd gap is scored on its
    own. (0.0, 0.0) below three gaps, where the factor is not measured."""
    if len(gaps) < 3:
        return 0.0, 0.0
    mid = float(np.median(gaps))
    if mid <= 1e-9:
        return 0.0, 0.0
    odd = sum(
        1 for g in gaps if g < NARROW_WORD_GAP * mid or g > ODD_GAP * mid
    )
    return mean([abs(g - mid) / mid for g in gaps]), odd / len(gaps)


def _letter_spacing(words):
    """Letter Spacing from each word's letter gaps, in small letters:
    (spread, odd share, words spaced off), or (None, None, None) with
    fewer than five gaps.

    - spread: the median distance of a gap from its own word's median
      gap, as a share of that median (at least GAP_FLOOR), over the
      words with two gaps or more. A word compared with itself is not
      moved by a writer who spaces one word wider than another, and one
      gap read wrongly cannot set it;
    - odd share: the gaps more than ODD_GAP times their word's median;
    - words spaced off: the words whose median gap is more than ODD_GAP
      times the page's, a word written with its letters apart, which a
      comparison inside the word cannot see."""
    gaps = [g for wg in words for g in wg]
    if len(gaps) < 5:
        return None, None, None
    devs, odd = [], 0
    for wg in words:
        if len(wg) < 2:
            continue
        mid = float(np.median(wg))
        base = max(mid, GAP_FLOOR)
        devs.extend(abs(g - mid) / base for g in wg)
        odd += sum(1 for g in wg if g > ODD_GAP * base)
    if not devs:
        return None, None, None
    page = max(float(np.median(gaps)), GAP_FLOOR)
    mids = [float(np.median(wg)) for wg in words if wg]
    off = sum(1 for m in mids if m > ODD_GAP * page) / len(mids)
    return float(np.median(devs)), odd / len(devs), off


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
    word_spread, word_odd = _word_spacing(word_gaps)

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
        "left_spread": _margin_spread(lefts),
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
        "word_gap_spread": word_spread,
        "word_gaps_odd": word_odd,
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
    spread, odd = _word_spacing(ink["gaps"])
    out = {
        "line_slope_abs": mean(ink["angles"]),
        "line_slope_std": _std(ink["angles"]),
        "line_slope_signed_med": (
            float(np.median(ink["signed"])) if ink["signed"] else 0.0
        ),
        "baseline_rows_tracked": 0,
        "baseline_wave_med": None,
        "word_gap_cv": _cv(ink["gaps"]),
        "word_gap_spread": spread,
        "word_gaps_odd": odd,
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
    spread, odd, spaced_off = _letter_spacing(
        [wd["letter_gaps"] for g in lines for wd in g["words"]]
    )
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
        "letter_gap_spread": spread,
        "letter_gaps_odd": odd,
        "words_spaced_off": spaced_off,
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
