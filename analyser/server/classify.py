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
# We bias toward KEEPING handwriting when uncertain so genuine pen strokes are
# never silently dropped.

import os
import re

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover - cv2 optional
    cv2 = None

from geometry import clamp_box  # noqa: E402 (after the optional cv2 import)


def _env_f(name, default):
    try:
        return float(os.environ.get(name, default))
    except Exception:
        return float(default)


# Decision threshold: printed if printed_prob >= this. Higher = keep more as
# handwriting (fail-open). Default leans slightly toward keeping handwriting.
PRINTED_THRESHOLD = _env_f("VAHINI_PRINTED_THRESHOLD", 0.58)

_FORM_KW = re.compile(
    r"\b(name|address|adress|date|age|sex|gender|case|doctor|dr|diagnosis|admission|"
    r"discharge|procedure|phone|mobile|id|form|hospital|patient|summary|findings|"
    r"consultant|fir|ip|op|investigation|investgation|results|dob|dod|d\.o\.b|d\.o\.d|"
    r"reg|no|ref|signature|sign|amount|total|qty|rate)\b",
    re.IGNORECASE,
)


def _gray(arr):
    if arr.ndim == 2:
        return arr.astype(np.uint8)
    if cv2 is not None:
        return cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    return np.dot(arr[..., :3], [0.299, 0.587, 0.114]).astype(np.uint8)


def _ink_mask(gray):
    """Binary mask, 1 = ink. Otsu when cv2 is present, else mean-offset."""
    if gray.size == 0:
        return np.zeros_like(gray, dtype=np.uint8)
    if cv2 is not None:
        _t, th = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
        return (th > 0).astype(np.uint8)
    thr = float(np.mean(gray)) - 12.0
    return (gray < thr).astype(np.uint8)


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


def region_features(crop_rgb):
    """Per-region structural features (no text/score)."""
    gray = _gray(crop_rgb)
    mask = _ink_mask(gray)
    ink_ratio = float(mask.mean()) if mask.size else 0.0
    return {
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
    alpha = len(re.findall(r"[A-Za-z]", t))
    upper_ratio = (
        (len(re.findall(r"[A-Z]", t)) / max(1, alpha)) if alpha else 0.0
    )
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
    # glyph-height uniformity
    if gh and gh <= 0.16:
        s += 0.22
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
        return p >= 0.70 or (sc >= 0.96 and len(t) >= 6)

    strong_count = sum(
        1 for ln, p in zip(lines, probs) if _is_strong_printed(ln, p)
    )
    page_has_print = strong_count >= max(1, int(0.15 * len(lines)))

    # Position relative to the DETECTED TEXT BLOCK, not the image — a phone photo
    # often frames the page in the middle, so image-relative position is useless.
    tops, bots = [], []
    for ln in lines:
        b = ln.get("box") or [0, 0, 0, 0]
        if len(b) >= 4:
            tops.append(float(b[1]))
            bots.append(float(b[1]) + float(b[3]))
    content_y0 = min(tops) if tops else 0.0
    content_span = max(1.0, (max(bots) if bots else 1.0) - content_y0)

    for ln in lines:
        prob = ln.get("printed_prob", 0.0)
        feat = ln.get("_feat", {}) or {}
        sw = feat.get("sw_cv", 1.0)
        text = str(ln.get("text", "") or "").strip()
        sc = float(ln.get("score", 0.0) or 0.0)
        clean = len(re.sub(r"[^\w]", "", text)) / max(1, len(text))
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
        # reads this cleanly. Skip the override only when stroke width is clearly
        # variable, which protects exceptionally neat handwriting.
        if (
            sc >= 0.96
            and len(text) >= 6
            and clean >= 0.6
            and (not sw or sw < 0.5)
        ):
            prob = max(prob, 0.85)

        ln["printed_prob"] = round(prob, 3)
        ln["printed_hint"] = bool(prob >= threshold)
        ln.pop("_feat", None)
    return lines


def split_lines(arr, lines, threshold=None):
    """Return (handwriting_lines, printed_lines) after classification."""
    classify_lines(arr, lines, threshold=threshold)
    hand = [l for l in lines if not l.get("printed_hint")]
    printed = [l for l in lines if l.get("printed_hint")]
    return hand, printed
