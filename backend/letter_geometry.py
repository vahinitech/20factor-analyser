# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Word and letter geometry inside one handwriting line, from the ink.

The scorer measures size and baseline from whole line boxes, which cannot
see one oversized letter or one word that drops below the line, and which
count a sloping line as a taller one (docs/how-a-scan-works.md, sections 4
and 8). This measures inside the line instead:

1. Binarise the line (zone_analysis.binarise) and take its ink blobs,
   keeping those whose middle lies inside the line's box.
2. Merge blobs that overlap left to right (a dotted i, a crossed t) into
   spans: one per letter in print, one per word in joined writing.
3. Split the spans into words at the widest gaps, as many as the text
   has word breaks (the same rule as computer_vision.line_word_gaps).
4. For each word, the densest band of rows is its small-letter zone
   (zone_analysis.dense_band): its height is the word's x-height and its
   bottom is the word's baseline.
5. A straight baseline through the words' baselines (Theil-Sen: the
   median of the slopes between every pair, so one sunken word cannot
   tilt it) gives the line's slope, and each word's distance from it.
6. When every letter of a word stands apart and the text is known, each
   small letter (a, c, e, m, n, o, r, s, u, v, w, x, z) is compared with
   the word's x-height: the one letter-level size measurement.

Everything is in processed-image pixels and deterministic.
"""

import math
import re

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - cv2 ships in core
    cv2 = None

from geometry import clamp_box
from zone_analysis import binarise, dense_band

SMALL_LETTERS = set("acemnorsuvwxz")
MIN_XHEIGHT_PX = 4


def _spans(comps):
    """Letters (in print) or words (joined writing) from ink blobs
    (x, y, w, h). Each blob is its own span, even when it leans over its
    neighbour; small pieces (the dot of an i, a stray mark) join the
    nearest span. Each span is [x0, y0, x1, y1, blobs], left to right."""
    if not comps:
        return []
    areas = [c[2] * c[3] for c in comps]
    small = 0.15 * float(np.median(areas))
    big = [c for c, a in zip(comps, areas) if a >= small] or list(comps)
    spans = [
        [c[0], c[1], c[0] + c[2], c[1] + c[3], [c]]
        for c in sorted(big, key=lambda c: (c[0], c[1]))
    ]
    for c in comps:
        if any(c is b for b in big):
            continue
        s = min(spans, key=lambda s, c=c: (_distance(s, c), s[0]))
        s[0] = min(s[0], c[0])
        s[1] = min(s[1], c[1])
        s[2] = max(s[2], c[0] + c[2])
        s[3] = max(s[3], c[1] + c[3])
        s[4].append(c)
    return spans


def _distance(span, comp):
    return abs((span[0] + span[2]) / 2.0 - (comp[0] + comp[2] / 2.0))


def _theil_sen(xs, ys):
    """Median pairwise slope and the matching intercept."""
    slopes = [
        (ys[j] - ys[i]) / (xs[j] - xs[i])
        for i in range(len(xs))
        for j in range(i + 1, len(xs))
        if xs[j] != xs[i]
    ]
    if not slopes:
        return 0.0, float(np.median(ys))
    slope = float(np.median(slopes))
    return slope, float(np.median([y - slope * x for x, y in zip(xs, ys)]))


def _xheight(mask, mx0, y0, slope, icpt):
    """Height of the small-letter zone of a mask (columns starting at page
    x mx0, rows at page y y0), after shifting each column so the fitted
    baseline is level. The row profile is smoothed over a few rows, as
    thin strokes make single rows spiky."""
    h, w = mask.shape
    if w == 0:
        return None
    level = np.zeros((h * 2, w), bool)
    for c in range(w):
        base = slope * (mx0 + c) + icpt - y0
        shift = int(round(h - base))
        col = mask[:, c]
        lo, hi = max(0, shift), min(2 * h, shift + h)
        level[lo:hi, c] = col[lo - shift : hi - shift]
    profile = level.sum(axis=1).astype(np.float64)
    if profile.max() <= 0:
        return None
    k = max(3, int(round(h * 0.06)) | 1)
    profile = np.convolve(profile, np.ones(k) / k, mode="same")
    band = dense_band(profile)
    if band is None:
        return None
    xh = float(band[1] - band[0] + 1)
    return xh if xh >= MIN_XHEIGHT_PX else None


def _line_ink(gray, line):
    """The line's ink: (x0, y0, mask, blobs) for the padded line box, with
    only the blobs whose middle lies inside the line's own box, or None.
    gray: full-page uint8 grayscale."""
    x, y, w, h = [int(round(float(v))) for v in (line.get("box") or [])[:4]]
    if w < 6 or h < 12:
        return None
    pad = max(4, h // 2)
    bounds = clamp_box(
        x, y - pad, w, h + 2 * pad, gray.shape[1], gray.shape[0]
    )
    if bounds is None:
        return None
    x0, y0, x1, y1 = bounds
    ink = binarise(gray[y0:y1, x0:x1]).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    min_area = max(4.0, (0.06 * h) ** 2)
    comps, keep = [], []
    for i in range(1, n):
        cx, cy, cw, ch, area = (int(v) for v in stats[i])
        middle = y0 + cy + ch / 2.0
        if area < min_area or not y <= middle <= y + h:
            continue
        comps.append((x0 + cx, y0 + cy, cw, ch))
        keep.append(i)
    if not comps:
        return None
    return x0, y0, np.isin(labels, keep), comps


def measure_line(gray, line):  # pylint: disable=too-many-locals
    """Word and letter geometry for one line, or None when the line is too
    small or has no usable ink. gray: full-page uint8 grayscale."""
    if cv2 is None:
        return None
    ink = _line_ink(gray, line)
    if ink is None:
        return None
    x0, y0, mask, comps = ink
    spans = _spans(comps)

    text = str(line.get("text") or "")
    text_words = [t for t in re.split(r"\s+", text.strip()) if t]
    gaps = sorted(
        range(len(spans) - 1),
        key=lambda i: (-(spans[i + 1][0] - spans[i][2]), i),
    )
    n_breaks = max(0, len(text_words) - 1) if text_words else 0
    if n_breaks > len(gaps):
        n_breaks = 0
    breaks = sorted(gaps[:n_breaks])
    # When every letter stands apart (one span per letter), the text says
    # exactly where each word ends, so a word gap narrower than the gaps
    # between letters is still found.
    counts = [len([c for c in t if c.isalnum()]) for t in text_words]
    counted = len(text_words) >= 2 and sum(counts) == len(spans)
    if counted:
        breaks = list(np.cumsum(counts)[:-1] - 1)
    groups, start = [], 0
    for b in breaks + [len(spans) - 1]:
        groups.append(spans[start : b + 1])
        start = b + 1

    # Baseline: a straight line through the bottoms of every span. Most
    # letters stand on it; tails (g, p, y) are a minority the median
    # pairwise slope ignores.
    xs = [(sp[0] + sp[2]) / 2.0 for sp in spans]
    bottoms = [float(sp[3]) for sp in spans]
    slope, icpt = _theil_sen(xs, bottoms)
    line_xh = _xheight(mask, x0, y0, slope, icpt)
    if line_xh is None:
        return None

    words = []
    for group in groups:
        if not group:
            continue
        drops = [
            sp[3] - (slope * (sp[0] + sp[2]) / 2.0 + icpt) for sp in group
        ]
        wx0 = min(sp[0] for sp in group)
        wx1 = max(sp[2] for sp in group)
        top = min(sp[1] for sp in group)
        bottom = max(sp[3] for sp in group)
        words.append(
            {
                "bbox": [wx0, top, wx1 - wx0, bottom - top],
                "drop": float(np.median(drops)),
                "xheight": _xheight(
                    mask[:, wx0 - x0 : wx1 - x0], wx0, y0, slope, icpt
                ),
                "spans": group,
            }
        )

    letters = []
    if len(text_words) == len(words):
        for wd, word in zip(words, text_words):
            chars = [c for c in word if c.isalnum()]
            if len(chars) != len(wd["spans"]):
                continue
            for c, s in zip(chars, wd["spans"]):
                if c not in SMALL_LETTERS:
                    continue
                letters.append(
                    {
                        "bbox": [s[0], s[1], s[2] - s[0], s[3] - s[1]],
                        "char": c,
                        "ratio": (s[3] - s[1]) / line_xh,
                    }
                )
    for wd in words:
        del wd["spans"]
    gaps_out = []
    if counted:
        for left, right in zip(words, words[1:]):
            x_l = left["bbox"][0] + left["bbox"][2]
            x_r = right["bbox"][0]
            top = min(left["bbox"][1], right["bbox"][1])
            bot = max(
                left["bbox"][1] + left["bbox"][3],
                right["bbox"][1] + right["bbox"][3],
            )
            gaps_out.append(
                {
                    "bbox": [x_l, top, max(1, x_r - x_l), bot - top],
                    "gap": max(0.0, float(x_r - x_l)) / line_xh,
                }
            )
    left = float(min(sp[0] for sp in spans))
    right = float(max(sp[2] for sp in spans))
    base_l, base_r = slope * left + icpt, slope * right + icpt
    return {
        "gaps": gaps_out,
        # The fitted baseline and the small-letter line above it, as two
        # points each, for drawing the measurement on the page.
        "baseline": [[left, base_l], [right, base_r]],
        "midline": [[left, base_l - line_xh], [right, base_r - line_xh]],
        "angle": (
            abs(math.degrees(math.atan(slope))) if len(spans) >= 3 else None
        ),
        "xheight": line_xh,
        "words": words,
        "letters": letters,
    }


# The middle of a placed letter's slot: its edges are half-way points
# to the neighbours, so their outer fifths can hold a neighbour's stroke.
SLOT_CORE = 0.6
# Inside the slot, ink pieces narrower than this share of it are a
# neighbour's stroke leaning in (the stem of an l or a t), not the letter.
SLOT_PIECE = 0.4
# A line needs this many measured small letters for a typical height.
MIN_PEERS = 4
# A letter is compared with its own kind when the page has this many of
# it: writers make some letters bigger by habit (an a half as tall again
# as their n), and that is their style, not a size change.
MIN_SAME = 3


def _slot_height(mask, c0, c1):
    """Top and bottom row of the letter's ink between columns c0 and c1:
    the pieces of ink that reach across most of the slot."""
    sub = mask[:, c0:c1].astype(np.uint8)
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(sub, 8)
    if n <= 1:
        return None
    width = c1 - c0
    pieces = [stats[i] for i in range(1, n)]
    keep = [st for st in pieces if st[2] >= SLOT_PIECE * width]
    if not keep:
        keep = [max(pieces, key=lambda st: st[4])]
    top = min(int(st[1]) for st in keep)
    bottom = max(int(st[1] + st[3]) for st in keep)
    return top, bottom


def placed_letter_heights(gray, line, placed):
    """Small letters the reader placed on one line (letter_boxes.py),
    each with the height of its ink and that height over the line's
    typical small letter (the median of the line's measured small
    letters). Joined writing included: the slot comes from the reader,
    not from gaps in the ink. Empty when the line has fewer than
    MIN_PEERS measured small letters."""
    if cv2 is None or not placed:
        return []
    ink = _line_ink(gray, line)
    if ink is None:
        return []
    x0, y0, mask, _comps = ink
    found = []
    for p in placed:
        if p["char"] not in SMALL_LETTERS:
            continue
        bx, _by, bw, _bh = p["bbox"]
        trim = bw * (1.0 - SLOT_CORE) / 2.0
        c0 = max(0, int(round(bx + trim)) - x0)
        c1 = min(mask.shape[1], int(round(bx + bw - trim)) - x0)
        if c1 - c0 < 2:
            continue
        rows = _slot_height(mask, c0, c1)
        if rows is None:
            continue
        top, bottom = y0 + rows[0], y0 + rows[1]
        found.append((p["char"], [bx, top, bw, bottom - top]))
    if len(found) < MIN_PEERS:
        return []
    typical = float(np.median([b[3] for _c, b in found]))
    return [
        {
            "char": c,
            "bbox": b,
            "height": b[3],
            "typical": typical,
            "ratio": b[3] / typical,
        }
        for c, b in found
    ]


def same_letter_ratios(letters):
    """Re-measure each letter of a page (placed_letter_heights, all
    lines) against the other copies of the same letter, in place, when
    the page has MIN_SAME of it; otherwise it keeps its line's ratio.
    Sets "reference" to "same letter" or "line"."""
    heights = {}
    for let in letters:
        heights.setdefault(let["char"], []).append(let["height"])
    for let in letters:
        same = heights[let["char"]]
        if len(same) >= MIN_SAME:
            rest = list(same)
            rest.remove(let["height"])
            let["ratio"] = let["height"] / float(np.median(rest))
            let["reference"] = "same letter"
        else:
            let["reference"] = "line"
    return letters


def measure_page(arr, lines):
    """measure_line for every line, in the order given (None kept)."""
    if cv2 is None:
        return [None] * len(lines)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    return [measure_line(gray, l) for l in lines]


# Marks. A small letter this far from the line's x-height, a word whose
# baseline sits this far off the line (both in x-heights), a line this
# steep. Set on planted pages with seed 1; reported on seed 0.
LETTER_LOOK = 0.55
WORD_DROP_LOOK = 0.35
ANGLE_LOOK_DEG = 2.0
ANGLE_FULL_SCALE_DEG = 8.0
MAX_LOOK = 3


def _mark(item, bbox, kind, measure, value, reference, deviation, direction):
    return {
        "bbox": [int(round(v)) for v in bbox],
        "kind": kind,
        "role": "look",
        "region_id": item.get("evidence_id", ""),
        "measure": measure,
        "value": round(float(value), 3),
        "reference": round(float(reference), 3),
        "deviation": round(float(deviation), 3),
        "direction": direction,
        "line_confidence": round(float(item.get("score", 0) or 0), 3),
    }


def _ranked(marks):
    return sorted(
        marks, key=lambda m: (-m["deviation"], m["bbox"][1], m["bbox"][0])
    )[:MAX_LOOK]


def size_marks(lines, geo):
    """Small letters whose height is far from their line's x-height."""
    out = []
    for item, g in zip(lines, geo):
        for let in (g or {}).get("letters", []):
            dev = abs(let["ratio"] - 1.0)
            if dev >= LETTER_LOOK:
                out.append(
                    _mark(
                        item,
                        let["bbox"],
                        "letter",
                        "letter_height",
                        let["ratio"],
                        1.0,
                        dev,
                        "taller" if let["ratio"] > 1 else "shorter",
                    )
                )
    return _ranked(out)


def baseline_marks(lines, geo):
    """Words off their line's baseline, and lines whose baseline slopes."""
    out = []
    for item, g in zip(lines, geo):
        if not g:
            continue
        if g["angle"] is not None and g["angle"] >= ANGLE_LOOK_DEG:
            out.append(
                _mark(
                    item,
                    item["box"],
                    "line",
                    "baseline_angle",
                    g["angle"],
                    0.0,
                    g["angle"] / ANGLE_FULL_SCALE_DEG,
                    "tilted",
                )
            )
        for wd in g["words"]:
            off = wd["drop"] / g["xheight"]
            if abs(off) >= WORD_DROP_LOOK:
                out.append(
                    _mark(
                        item,
                        wd["bbox"],
                        "word",
                        "word_baseline",
                        off,
                        0.0,
                        abs(off),
                        "below" if off > 0 else "above",
                    )
                )
    return _ranked(out)


GAP_LOOK = 0.50


def spacing_marks(lines, geo):
    """Word gaps, where the text placed them, far from the page's median
    gap (as a share of it)."""
    gaps = [(item, gp) for item, g in zip(lines, geo) if g for gp in g["gaps"]]
    if len(gaps) < 3:
        return []
    median = float(np.median([gp["gap"] for _, gp in gaps]))
    if median <= 0:
        return []
    out = []
    for item, gp in gaps:
        dev = abs(gp["gap"] - median) / median
        if dev >= GAP_LOOK:
            out.append(
                _mark(
                    item,
                    gp["bbox"],
                    "gap",
                    "word_gap",
                    gp["gap"],
                    median,
                    dev,
                    "wider" if gp["gap"] > median else "narrower",
                )
            )
    return _ranked(out)


def page_features(geo):
    """Candidate inputs for Size Consistency and Baseline Alignment."""
    words = [wd for g in geo if g for wd in g["words"]]
    xh = [wd["xheight"] for wd in words if wd["xheight"]]
    letters = [let["ratio"] for g in geo if g for let in g["letters"]]
    angles = [g["angle"] for g in geo if g and g["angle"] is not None]
    offs = [
        abs(wd["drop"]) / g["xheight"] for g in geo if g for wd in g["words"]
    ]

    def cv(v):
        return float(np.std(v, ddof=1) / np.mean(v)) if len(v) >= 2 else None

    xh_cv = cv(xh)
    angle = float(np.mean(angles)) if angles else None
    off_share = sum(1 for o in offs if o >= WORD_DROP_LOOK) / max(1, len(offs))
    return {
        # Candidate scores, shown beside today's; not used by the report.
        # Size: today's formula on word x-heights instead of line boxes,
        # with a 0.40 full scale (word x-heights vary less than lines).
        "size_score": (
            None
            if xh_cv is None
            else round(max(0.0, (1 - min(1.0, xh_cv / 0.40)) * 10), 1)
        ),
        # Baseline: today's formula on the fitted baseline's angle, less up
        # to 5 points as the share of words off the line reaches 25%.
        "baseline_score": (
            None
            if angle is None
            else round(
                max(
                    0.0,
                    (1 - min(1.0, angle / 8.0)) * 10
                    - 5 * min(1.0, off_share / 0.25),
                ),
                1,
            )
        ),
        "word_xheight_cv": xh_cv,
        "letter_height_cv": cv(letters) if len(letters) >= 8 else None,
        "baseline_angle": angle,
        "words_off_line": sum(1 for o in offs if o >= WORD_DROP_LOOK),
        "words": len(offs),
    }
