# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies. Printed-vs-handwriting classification.
#
# classify.py — decide, per detected text region, whether it is PRINTED
# (machine font: form labels, headers, footers) or HANDWRITING.
#
# This is the root fix for the analyser's biggest accuracy problem: on a page
# that mixes printed text and handwriting (prescriptions, forms, exam answer
# sheets) the recognition text, the orange word boxes, and the per-factor
# reference crops were all polluted with printed text. The 20 handwriting
# factors must be measured on HANDWRITING only.
#
# Approach (CPU-only, no training required) — combine signals that separate a
# machine font from a pen:
#   * stroke-width coefficient of variation  (printed ≈ uniform, low CV)
#   * per-glyph height variance              (printed ≈ constant, low)
#   * edge / contour straightness            (printed ≈ crisp straight edges)
#   * OCR confidence                         (printed ≈ very high, > ~0.97)
#   * text cues                              (form keywords / all-caps / digits)
# Each signal votes; the weighted vote becomes a printed-probability in [0,1].
# Neat handwriting can pass all of these, so a line they call printed is
# set aside only when a second sign agrees (#202): the line reader sees
# print, or the ink repeats like a font (font_evidence).
# We bias toward KEEPING handwriting when uncertain so genuine pen strokes are
# never silently dropped.

import os
import re

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover - cv2 optional
    cv2 = None

from vision.geometry import (
    clamp_box,
)  # noqa: E402 (after the optional cv2 import)
import languages  # noqa: E402
from languages import graphemes  # noqa: E402
from reading import print_hand  # noqa: E402


def _env_f(name, default):
    try:
        return float(os.environ.get(name, default))
    except Exception:
        return float(default)


# Decision threshold: printed if printed_prob >= this. Higher = keep more as
# handwriting (fail-open). Default leans slightly toward keeping handwriting.
PRINTED_THRESHOLD = _env_f("VAHINI_PRINTED_THRESHOLD", 0.58)
# A page is taken as printed (a form, a letterhead) when this many of the
# reader's lines look strongly printed, and at least 15% of them. One
# crisp line is not enough: on a page of neat handwriting it pulled
# borderline lines to print and set the top tenth aside as letterhead
# (#202). Lines that are clearly printed on their own are set aside on
# any page.
PAGE_PRINT_MIN_LINES = 2
PAGE_PRINT_SHARE = 0.15
# Signs of a font in the ink (font_evidence): repeated letters overlap
# this well, or the small letters keep one bottom line and one height
# to within these shares of the letter height.
FONT_REPEAT_MATCH = 0.80
FONT_BASE_DEV = 0.03
FONT_HEIGHT_DEV = 0.04

# Words that mark a printed form, letters and capitals: the language
# pack (backend/languages, #206).
_PACK = languages.language()
_FORM_KW = re.compile(
    r"\b(" + _PACK.any_of("form_words") + r")\b", re.IGNORECASE
)
_LETTER_RE = re.compile(_PACK.char_class("letter"))
_UPPER_RE = re.compile(_PACK.char_class("upper"))
_CAPS_WORD_RE = re.compile(_PACK.char_class("upper") + "{5,}")


def _gray(arr):
    if arr.ndim == 2:
        return arr.astype(np.uint8)
    if cv2 is not None:
        return cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    return np.dot(arr[..., :3], [0.299, 0.587, 0.114]).astype(np.uint8)


def _ink_mask(gray):
    """Ink mask with polarity inferred from the region border.

    Reverse-print headings have light glyphs on a dark panel. Counting the
    panel as ink turns all letters into one component and destroys the print
    signals. Require a predominantly dark border before reversing polarity.
    """
    if gray.size == 0:
        return np.zeros_like(gray, dtype=np.uint8)
    if cv2 is not None:
        _t, th = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
        mask = (th > 0).astype(np.uint8)
    else:
        mask = (gray < float(np.mean(gray)) - 12.0).astype(np.uint8)
    border = np.concatenate((mask[0], mask[-1], mask[:, 0], mask[:, -1]))
    gray_border = np.concatenate((gray[0], gray[-1], gray[:, 0], gray[:, -1]))
    if (
        border.mean() >= 0.6 or gray_border.mean() < 128
    ) and mask.mean() > 0.5:
        mask = 1 - mask
    return mask


def _stroke_width_cv(mask):
    """Coefficient of variation of stroke width.

    Distance transform gives, at every ink pixel, the radius to the nearest
    background pixel. The ridge values (local maxima ≈ half stroke width) tell us
    how consistent the pen/print stroke is. Printed fonts: tight distribution
    (low CV). Handwriting: pressure & speed vary → wider distribution.
    """
    if mask.sum() < 20:
        return 0.0
    if cv2 is not None:
        dist = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 3)
    else:
        # crude fallback: column-run thickness
        dist = mask.astype(np.float32)
    vals = dist[dist > 0.5]
    if vals.size < 12:
        return 0.0
    # Keep the upper half (ridge-ish) so background-adjacent thin pixels don't
    # dominate and flatten the signal.
    thr = np.percentile(vals, 55)
    ridge = vals[vals >= thr]
    if ridge.size < 8:
        ridge = vals
    m = float(np.mean(ridge))
    if m <= 1e-6:
        return 0.0
    return float(np.std(ridge) / m)


def _glyph_height_cv(mask):
    """CV of connected-component heights inside the region.

    Printed glyphs share a near-constant cap/x-height; handwriting wanders.
    """
    if cv2 is None or mask.sum() < 20:
        return 0.0
    num, _lab, stats, _c = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    if num <= 2:
        return 0.0
    heights = []
    H = mask.shape[0]
    for i in range(1, num):
        h = int(stats[i, cv2.CC_STAT_HEIGHT])
        a = int(stats[i, cv2.CC_STAT_AREA])
        # ignore specks and full-height noise
        if a < 6 or h < max(3, int(0.12 * H)) or h > H:
            continue
        heights.append(h)
    if len(heights) < 3:
        return 0.0
    m = float(np.mean(heights))
    if m <= 1e-6:
        return 0.0
    return float(np.std(heights) / m)


def _edge_straightness(gray, mask):
    """Fraction of ink edge that is axis-aligned/straight.

    Printed type has crisp, mostly straight contours; pen strokes curve. We use
    the ratio of strong-gradient edge pixels to ink pixels as a crispness proxy.
    """
    if cv2 is None or mask.sum() < 20:
        return 0.0
    edges = cv2.Canny(gray, 60, 160)
    ink = float(mask.sum())
    if ink <= 0:
        return 0.0
    return float((edges > 0).sum()) / ink


def _letter_boxes(mask):
    """Connected components big enough to be letters (or joined words):
    (x, y, w, h) for each, left to right."""
    if cv2 is None or mask.sum() < 20:
        return [], None
    num, labels, stats, _c = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    floor = max(4, int(0.2 * mask.shape[0]))
    boxes = []
    for i in range(1, num):
        x, y, w, h, area = (int(v) for v in stats[i])
        if area >= 8 and h >= floor and w >= 2:
            boxes.append((x, y, w, h, i))
    boxes.sort()
    return boxes, labels


def _shape_match(labels, a, b):
    """Overlap of two letters' ink (intersection over union) at the best
    shift of up to one pixel. A font prints the same letter from one
    outline, so two copies overlap almost exactly; a pen never writes
    the same letter twice."""
    ax, ay, aw, ah, ai = a
    bx, by, bw, bh, bi = b
    w, h = max(aw, bw) + 2, max(ah, bh) + 2
    pa = np.zeros((h, w), bool)
    pa[1 : 1 + ah, 1 : 1 + aw] = labels[ay : ay + ah, ax : ax + aw] == ai
    glyph = labels[by : by + bh, bx : bx + bw] == bi
    best = 0.0
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            if dy + bh > h or dx + bw > w:
                continue
            pb = np.zeros((h, w), bool)
            pb[dy : dy + bh, dx : dx + bw] = glyph
            union = np.logical_or(pa, pb).sum()
            if union:
                best = max(best, np.logical_and(pa, pb).sum() / union)
    return float(best)


def _repeat_match(boxes, labels):
    """How closely the line's repeated letters match: the median, over
    letters that have a same-size partner, of the best overlap with it.
    None when fewer than three letters have a partner (one pair
    of look-alike letters proves nothing)."""
    best = {}
    for i, a in enumerate(boxes):
        for j in range(i + 1, len(boxes)):
            b = boxes[j]
            if abs(a[2] - b[2]) > 1 or abs(a[3] - b[3]) > 1:
                continue
            if a[2] * a[3] < 30:
                continue
            m = _shape_match(labels, a, b)
            best[i] = max(best.get(i, 0.0), m)
            best[j] = max(best.get(j, 0.0), m)
    if len(best) < 3:
        return None
    return float(np.median(list(best.values())))


def _row_exactness(boxes):
    """How exactly the letters keep one bottom line and one height,
    relative to the letter height (0 = to the pixel). Letters whose
    bottom is near the line's (not descenders) and whose height is near
    the small-letter height count. None when fewer than four do.

    Print is cast from one size on one line, so in a straight crop its
    small letters share their bottom and height to a pixel or so; a pen
    wanders a few pixels however neat the writer."""
    if len(boxes) < 4:
        return None
    xs = np.array([x + w / 2.0 for x, _y, w, _h, _i in boxes])
    bottoms = np.array([y + h for _x, y, _w, h, _i in boxes], float)
    heights = np.array([h for _x, _y, _w, h, _i in boxes], float)
    unit = float(np.median(heights))
    if unit < 6:
        return None
    # Straighten a slanted line: fit the bottoms, then keep letters that
    # sit on the fit (descenders hang below it).
    slope, icpt = np.polyfit(xs, bottoms, 1) if len(set(xs)) > 1 else (0, 0)
    resid = bottoms - (slope * xs + icpt)
    on_line = np.abs(resid - np.median(resid)) <= 0.25 * unit
    small = np.abs(heights - np.median(heights[on_line])) <= 0.2 * unit
    keep = on_line & small
    if keep.sum() < 4:
        return None
    slope, icpt = np.polyfit(xs[keep], bottoms[keep], 1)
    resid = bottoms[keep] - (slope * xs[keep] + icpt)
    base = float(np.std(resid)) / unit
    height = float(np.std(heights[keep])) / unit
    return {"base": base, "height": height, "letters": int(keep.sum())}


def font_evidence(crop_rgb):
    """Ink signs that only a font leaves, measured on a line crop.

    Neat handwriting can have even strokes, even letters and read with
    high confidence, which is all the older signals look at. A font also
    repeats itself exactly: the same letter has the same shape to the
    pixel, and the small letters sit on one line at one height. Returns
    {"verdict": "font" | "hand" | "unsure", "repeat", "base", "height",
    "letters"}: "font" when either sign is there, "hand" when both were
    measurable and neither is, "unsure" when the line has too few
    separate letters to tell (short labels, joined writing)."""
    out = {"verdict": "unsure", "repeat": None, "base": None}
    if crop_rgb is None or not crop_rgb.size:
        return out
    mask = _ink_mask(_gray(crop_rgb))
    boxes, labels = _letter_boxes(mask)
    if not boxes:
        return out
    repeat = _repeat_match(boxes, labels)
    row = _row_exactness(boxes)
    out["repeat"] = None if repeat is None else round(repeat, 3)
    if row:
        out["base"] = round(row["base"], 3)
        out["height"] = round(row["height"], 3)
        out["letters"] = row["letters"]
    exact_row = row is not None and (
        row["base"] <= FONT_BASE_DEV and row["height"] <= FONT_HEIGHT_DEV
    )
    exact_repeat = repeat is not None and repeat >= FONT_REPEAT_MATCH
    if exact_row or exact_repeat:
        out["verdict"] = "font"
    elif repeat is not None and row is not None:
        out["verdict"] = "hand"
    return out


def region_features(crop_rgb):
    """Per-region structural features (no text/score)."""
    gray = _gray(crop_rgb)
    mask = _ink_mask(gray)
    ink_ratio = float(mask.mean()) if mask.size else 0.0
    dark_border = (
        np.concatenate((gray[0], gray[-1], gray[:, 0], gray[:, -1]))
        if gray.size
        else np.array([255])
    )
    glyph_count = 0
    if cv2 is not None and mask.size:
        _n, _labels, stats, _centers = cv2.connectedComponentsWithStats(mask)
        glyph_count = sum(
            1
            for x, y, w, h, area in stats[1:]
            if area >= 6 and h >= max(3, 0.12 * mask.shape[0])
        )
    return {
        "light_on_dark": bool(dark_border.mean() < 128 and gray.mean() < 128),
        "glyph_count": glyph_count,
        "sw_cv": _stroke_width_cv(mask),
        "gh_cv": _glyph_height_cv(mask),
        "edge_ratio": _edge_straightness(gray, mask),
        "ink_ratio": ink_ratio,
    }


def _text_printed_score(text, score, box):
    """Text/score/shape cues → 0..1 printed-ness."""
    t = (text or "").strip()
    if not t:
        return 0.0
    low = t.lower()
    alpha = len(_LETTER_RE.findall(t))
    upper_ratio = (len(_UPPER_RE.findall(t)) / max(1, alpha)) if alpha else 0.0
    digit_ratio = len(re.findall(r"\d", t)) / max(1, len(t))
    has_kw = bool(_FORM_KW.search(low))
    aspect = 0.0
    if box and len(box) >= 4:
        aspect = float(max(1.0, box[2])) / float(max(1.0, box[3]))

    s = 0.0
    # OCR confidence is the single most reliable printed signal on photographed
    # forms: machine type reads at 0.95-0.999, while messy/medical handwriting
    # reads lower and is often garbled. Weight it decisively.
    if score >= 0.96:
        s += 0.55
    elif score >= 0.92:
        s += 0.38
    elif score >= 0.86:
        s += 0.20
    if has_kw:
        s += 0.22
    if upper_ratio >= 0.65 and alpha >= 5:
        s += 0.18
    if ":" in t and has_kw:
        s += 0.15
    if digit_ratio >= 0.5 and len(t) >= 5:
        s += 0.12
    if aspect >= 10.0 and len(t) >= 12:
        s += 0.10
    return float(min(1.0, s))


def _structural_printed_score(feat):
    """Structural features → 0..1 printed-ness.

    Lower stroke-width CV, lower glyph-height CV, higher edge crispness all push
    toward 'printed'. Thresholds are deliberately generous so noisy crops drift
    toward 'handwriting' (fail-open).
    """
    sw = feat.get("sw_cv", 0.0)
    gh = feat.get("gh_cv", 0.0)
    edge = feat.get("edge_ratio", 0.0)

    s = 0.0
    # stroke-width uniformity (the strongest single structural cue). Thresholds
    # are loosened a little because phone-photo blur inflates the CV of crisp
    # printed type; only clearly-variable strokes (>=0.62) count as handwriting.
    if sw and sw <= 0.26:
        s += 0.40
    elif sw and sw <= 0.40:
        s += 0.22
    elif sw and sw >= 0.62:
        s -= 0.18  # clearly variable → handwriting
    # glyph-height uniformity. 0.16-0.40 used to be a dead zone (neither
    # bonus nor penalty), which under-scored real print with ascenders and
    # descenders (mixed-case labels naturally have more height variance than
    # an all-caps header) — give it partial credit instead of nothing.
    if gh and gh <= 0.16:
        s += 0.22
    elif gh and gh <= 0.28:
        s += 0.12
    elif gh and gh >= 0.40:
        s -= 0.12
    # edge crispness
    if edge and edge >= 0.85:
        s += 0.16
    elif edge and edge <= 0.45:
        s -= 0.08
    return float(max(0.0, min(1.0, s)))


def printed_probability(crop_rgb, text, score, box):
    """Fuse structural + textual evidence into P(printed) in [0,1]."""
    feat = (
        region_features(crop_rgb)
        if crop_rgb is not None and crop_rgb.size
        else {}
    )
    struct = _structural_printed_score(feat)
    textual = _text_printed_score(text, float(score or 0.0), box)
    # Weight structure a touch higher than text cues; both must agree to push high.
    prob = 0.58 * struct + 0.42 * textual
    # Reverse-print capital headings need multiple separate, same-height,
    # uniform-width glyphs as well as readable OCR. Not a keyword blacklist.
    if (
        feat.get("light_on_dark")
        and feat.get("glyph_count", 0) >= 4
        and 0 < feat.get("sw_cv", 1) <= 0.30
        and feat.get("gh_cv", 1) <= 0.12
        and float(score or 0) >= 0.86
        and _CAPS_WORD_RE.fullmatch(str(text or "").strip())
    ):
        prob = max(prob, 0.80)
    return float(max(0.0, min(1.0, prob))), feat


def _crop(arr, box):
    if arr is None or not box:
        return None
    height, width = arr.shape[:2]
    x, y, w, h = box[:4]
    box_px = clamp_box(x, y, w, h, width, height)
    if box_px is None:
        return None
    x0, y0, x1, y1 = box_px
    return arr[y0:y1, x0:x1]


# The line reader's answer counts as "handwriting" below this, and as
# "print" from READER_PRINT_FROM up.
READER_HAND_BELOW = 0.1
READER_PRINT_FROM = 0.5
# A page where this share of the reader's lines show a second sign of
# print is a printed page: there the rules alone set a line aside.
PAGE_SECOND_SIGN_SHARE = 2 / 3
# Up to this many letters and digits, a line is too short for either
# second sign; on a page where this share of the lines show one (a
# form), the rules alone set it aside.
SHORT_LABEL_CHARS = 4
SHORT_LABEL_PAGE_SHARE = 0.25


def _reader_says_print(crop):
    """print_hand.py's probability of print for an RGB crop, or None."""
    if crop is None or not crop.size or cv2 is None:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    return print_hand.print_probability(gray)


def _reader_has_say(ln):
    """Whether the line reader can judge the line. It learned from Latin
    print and handwriting only, and gives printed Telugu 0.001 to 0.01
    (#171), so on a line whose letters are mostly outside the pack's
    Latin letter class it has no say."""
    if ln.get("_model") is None:
        return False
    text = str(ln.get("text") or "")
    return not (any(c.isalpha() for c in text) and _PACK.share(text) < 0.5)


def _reader_hand(ln):
    """True when the line reader calls the line handwriting."""
    return _reader_has_say(ln) and ln["_model"] < READER_HAND_BELOW


def _second_sign(arr, ln):
    """The sign of print that does not come from the rules (#202): the
    line reader sees print ("reader") or the ink repeats like a font
    ("font_ink"); "rules" where the reader has no say (no OpenCV, a
    script it never learned), so the rules decide alone as before;
    None when neither sees print. Kept on the line while classifying."""
    if "_sign" not in ln:
        if not _reader_has_say(ln):
            sign = "rules"
        elif ln["_model"] >= READER_PRINT_FROM:
            sign = "reader"
        elif font_evidence(_crop(arr, ln.get("box")))["verdict"] == "font":
            sign = "font_ink"
        else:
            sign = None
        ln["_sign"] = sign
    return ln["_sign"]


def _clean_share(text):
    """Share of the line's characters that are letters or digits, with
    the marks written on them: a grapheme that starts with a word
    character counts whole. re's \\w leaves out vowel signs and the
    virama, which put clean printed Telugu at 0.54 to 0.65 (#171)."""
    if not text:
        return 0.0
    kept = sum(len(g) for g in graphemes.split(text) if re.match(r"\w", g))
    return kept / len(text)


def classify_lines(arr, lines, threshold=None):
    """Annotate each line with `printed_prob` and `printed_hint`.

    Returns the same list (mutated) so callers can filter on `printed_hint`.
    Page-adaptive: if a clear cluster of very-printed regions exists, regions
    near that cluster are nudged toward printed, which sharpens mixed pages.
    """
    if threshold is None:
        threshold = PRINTED_THRESHOLD
    if not lines:
        return lines

    probs = []
    for ln in lines:
        crop = _crop(arr, ln.get("box"))
        prob, feat = printed_probability(
            crop, ln.get("text", ""), ln.get("score", 0.0), ln.get("box")
        )
        ln["printed_prob"] = round(prob, 3)
        ln["_feat"] = feat
        ln["_model"] = _reader_says_print(crop)
        probs.append(prob)

    # Page-adaptive nudge: when the page clearly contains printed structure
    # (some regions > 0.7), pull borderline regions that share low stroke-width
    # variation toward printed too.
    # "Is this a printed form?" — count both structurally-printed lines AND
    # high-OCR-confidence clean lines. The latter matters because phone-photo
    # blur flattens the structural signal, yet a page full of crisp 0.96+ lines
    # is unmistakably a printed form (so the letterhead band can be suppressed).
    def _is_strong_printed(ln, p):
        sc = float(ln.get("score", 0.0) or 0.0)
        t = str(ln.get("text", "") or "").strip()
        confident = sc >= 0.96 and len(t) >= 6 and not _reader_hand(ln)
        return p >= 0.70 or confident

    # The page's context comes from the reader's own lines. Words read
    # again where the detector missed writing (line_recovery.py) are judged
    # in that context but do not change it: a run of recovered handwriting
    # must not dilute a printed form's share of print, or move the top of
    # the text block, and so let its letterhead through.
    found = [
        (ln, p) for ln, p in zip(lines, probs) if not ln.get("recovered")
    ] or list(zip(lines, probs))
    strong_count = sum(1 for ln, p in found if _is_strong_printed(ln, p))
    need = max(PAGE_PRINT_MIN_LINES, int(PAGE_PRINT_SHARE * len(found)))
    page_has_print = strong_count >= need

    # Position relative to the DETECTED TEXT BLOCK, not the image — a phone photo
    # often frames the page in the middle, so image-relative position is useless.
    tops, bots = [], []
    for ln, _p in found:
        b = ln.get("box") or [0, 0, 0, 0]
        if len(b) >= 4:
            tops.append(float(b[1]))
            bots.append(float(b[1]) + float(b[3]))
    content_y0 = min(tops) if tops else 0.0
    content_span = max(1.0, (max(bots) if bots else 1.0) - content_y0)

    signs = sum(
        1
        for ln, _p in found
        if _second_sign(arr, ln) in ("reader", "font_ink")
    )
    printed_page = signs >= max(
        PAGE_PRINT_MIN_LINES, PAGE_SECOND_SIGN_SHARE * len(found)
    )
    form_page = signs >= max(
        PAGE_PRINT_MIN_LINES, SHORT_LABEL_PAGE_SHARE * len(found)
    )

    for ln in lines:
        prob = ln.get("printed_prob", 0.0)
        feat = ln.get("_feat", {}) or {}
        sw = feat.get("sw_cv", 1.0)
        text = str(ln.get("text", "") or "").strip()
        sc = float(ln.get("score", 0.0) or 0.0)
        clean = _clean_share(text)
        box = ln.get("box") or [0, 0, 0, 0]
        y_center = (
            (float(box[1]) + float(box[3]) / 2.0) if len(box) >= 4 else 0.0
        )
        y_ratio = (y_center - content_y0) / content_span

        if page_has_print and 0.45 <= prob < threshold and sw and sw <= 0.30:
            prob = min(1.0, prob + 0.12)

        # Letterhead / logo band: on a printed form the top strip is letterhead
        # (logo, address, and a stylised TAGLINE that reads like cursive
        # handwriting — "Life Begins in safe hands"). Suppress that whole band
        # when the page is clearly a printed form, so it can't pose as evidence.
        if page_has_print and y_ratio < 0.10:
            prob = max(prob, 0.80)

        # Decisive override: a clean, high-confidence, multi-character line is
        # printed (letterhead, address, form labels) — handwriting almost never
        # reads this cleanly. 0.93, not 0.96: a photographed/aged page reads
        # genuine print at 0.90-0.96, not just 0.96+, so requiring 0.96 missed
        # real letterheads on worn paper. Skip the override only when stroke
        # width is clearly variable, which protects exceptionally neat
        # handwriting.
        # Neat handwriting reads at 0.93 too (docs/02-how-a-scan-works.md,
        # section 8); the line reader (print_hand.py) vetoes the override
        # when it sees handwriting, and has no say when it cannot judge.
        if (
            sc >= 0.93
            and len(text) >= 6
            and clean >= 0.6
            and (not sw or sw < 0.5)
            and not _reader_hand(ln)
        ):
            prob = max(prob, 0.85)

        ln["printed_prob"] = round(prob, 3)
        ln["printed_hint"] = bool(prob >= threshold)
        if ln["printed_hint"]:
            # The rules lean on what neat handwriting shares with print:
            # even strokes, even letters, a confident reading. On 173
            # GNHK phone photos (CC BY 4.0) they set aside 12.6% of the
            # handwritten words, 277 of 448 lost lines through the
            # confident-reading override above. So outside a printed
            # page a line is set aside only when a second sign agrees;
            # when none does it stays handwriting, since excluding a
            # child's own writing is the worse mistake.
            # A label of a few characters is too short for either sign
            # (the reader and font_evidence need several letters), so
            # on a page that holds print the rules decide it alone.
            short = len(re.findall(r"\w", text)) <= SHORT_LABEL_CHARS
            sign = (
                _second_sign(arr, ln)
                or ("printed_page" if printed_page else None)
                or ("short_on_form" if short and form_page else None)
            )
            ln["printed_hint"] = sign is not None
            ln["print_check"] = sign or "kept_no_second_sign"
        ln.pop("_feat", None)
        ln.pop("_sign", None)
        ln.pop("_model", None)
    return lines


def split_lines(arr, lines, threshold=None):
    """Return (handwriting_lines, printed_lines) after classification."""
    classify_lines(arr, lines, threshold=threshold)
    hand = [l for l in lines if not l.get("printed_hint")]
    printed = [l for l in lines if l.get("printed_hint")]
    return hand, printed


def classification_summary(lines, hand_lines=None):
    """Presentation-only streams; never feed printed text into scoring."""
    included = {id(line) for line in (hand_lines or [])}
    result = {"handwritten": [], "printed": [], "unclassified": []}
    for index, line in enumerate(lines, 1):
        score = line.get("printed_prob")
        classified = score is not None
        kind = (
            ("printed" if line.get("printed_hint") else "handwritten")
            if classified
            else "unclassified"
        )
        granularity = line.get("classification_granularity", "line")
        if granularity not in ("letter", "word", "line"):
            granularity = "line"
        result[kind].append(
            {
                "id": f"text_{index}",
                # The same accepted line is numbered line_N in factor
                # evidence; carry that id so a renderer can match them.
                "evidence_id": line.get("evidence_id"),
                "text": str(line.get("text_as_read", line.get("text")) or ""),
                "bbox": line.get("box"),
                "granularity": granularity,
                "classification": kind,
                "printed_score": float(score) if classified else None,
                # Set when the rules called the line printed: the sign
                # that agreed ("reader", "font_ink", "printed_page",
                # "short_on_form", "rules"), or "kept_no_second_sign"
                # when none did (#202).
                "print_check": line.get("print_check"),
                "included_in_scoring": id(line) in included,
            }
        )
    result["note"] = (
        "Labels apply to detected regions. Word or letter labels appear only "
        "when separately classified at that level. A line containing both "
        "print and handwriting may receive one label. The printed-likeness "
        "score is a heuristic, not a calibrated confidence or accuracy percentage."
    )
    return result
