# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# zone_analysis.py — the three-zone letter-size rule, measured.
#
# Handwriting coaches teach letter size with one proportion rule: Latin
# letters live in three vertical zones (upper / middle / lower), and the
# proper reach is ONE-TO-TWO — a 't' stands two x-heights tall, a 'g'
# hangs two x-heights deep. The three classic mistakes are writing
# everything in one zone, over-reaching the upper zone, and over-reaching
# the lower zone.
#
# This module measures that rule directly from ink, per detected line:
#
#   1. binarise the line crop (iterative midpoint threshold, numpy only)
#   2. horizontal projection profile (ink pixels per row)
#   3. the densest contiguous row band is the MIDDLE zone: its top edge
#      is the midline, its bottom edge the baseline
#   4. topmost / bottommost rows with meaningful ink give the ascender
#      and descender extents
#   5. ascender reach = (upper + middle) / middle   (target 2.0)
#      descender reach = (lower + middle) / middle  (target 2.0)
#
# Aggregated over lines (medians, robust to one bad detection), the
# result scores Factor 6 from real geometry instead of the tall-letter
# share proxy, and fills the zoneProfile output with measured numbers.
# Latin-script only: zone conventions differ for Indic scripts (matras
# occupy the zones differently), so pages without enough Latin letters
# fall back to the proxy and say so.

import re

import numpy as np

from geometry import clamp_box

# The coach's rule: reach two x-heights up and down.
ZONE_TARGET_REACH = 2.0
# Full credit within this error; zero credit beyond ZONE_ZERO_ERR.
ZONE_FULL_ERR = 0.35
ZONE_ZERO_ERR = 1.00
# Over-emphasis ("heavy importance to a zone") beyond this reach.
ZONE_HEAVY_REACH = 3.2
# A line needs a middle band at least this tall (pixels) to be usable.
MIN_XHEIGHT_PX = 6
# Row-density fractions defining the bands.
DENSE_FRAC = 0.40
INK_FRAC = 0.08

_ASCENDER_RE = re.compile(r"[bdfhklt]")
_DESCENDER_RE = re.compile(r"[gjpqy]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def binarise(crop):
    """Iterative midpoint threshold (Ridler-Calvard style), numpy only.
    Returns a boolean ink mask (True = ink)."""
    lo, hi = float(crop.min()), float(crop.max())
    if hi - lo < 8.0:
        return np.zeros(crop.shape, dtype=bool)
    thr = 0.5 * (lo + hi)
    for _ in range(6):
        dark = crop[crop <= thr]
        light = crop[crop > thr]
        if dark.size == 0 or light.size == 0:
            break
        new = 0.5 * (float(dark.mean()) + float(light.mean()))
        if abs(new - thr) < 0.5:
            break
        thr = new
    return crop <= thr


def dense_band(profile):
    """Longest contiguous run of rows at >= DENSE_FRAC of peak density:
    the middle-zone (x-height) band."""
    peak = float(profile.max())
    dense = profile >= (peak * DENSE_FRAC)
    best = (0, -1)
    start = None
    for i, d in enumerate(list(dense) + [False]):
        if d and start is None:
            start = i
        elif not d and start is not None:
            if i - start > best[1] - best[0] + 1 or best[1] < best[0]:
                best = (start, i - 1)
            start = None
    return best if best[1] >= best[0] else None


def line_zone_bands(gray, box):
    """Zone geometry for one detected line.

    gray: full-page uint8 grayscale array. box: [x, y, w, h].
    Returns dict with pixel heights (middle, upper, lower) and the
    reach ratios, or None when the crop is unusable."""
    h_img, w_img = gray.shape[:2]
    x, y, w, h = [int(round(float(v))) for v in box[:4]]
    # pad by half the detected box height above and below: ascenders/
    # descenders often poke past the detector's tight box
    pad = max(4, h // 2)
    clamped = clamp_box(x, y - pad, max(1, w), h + 2 * pad, w_img, h_img)
    if clamped is None:
        return None
    x0, y0, x1, y1 = clamped
    if y1 - y0 < MIN_XHEIGHT_PX:
        return None

    ink = binarise(gray[y0:y1, x0:x1])
    profile = ink.sum(axis=1).astype(np.float64)
    if float(profile.max()) < 3.0:
        return None

    band = dense_band(profile)
    if band is None:
        return None
    midline, baseline = band
    h_m = baseline - midline + 1
    if h_m < MIN_XHEIGHT_PX:
        return None

    meaningful = profile >= max(2.0, float(profile.max()) * INK_FRAC)
    rows = np.nonzero(meaningful)[0]
    asc_top, desc_bot = int(rows[0]), int(rows[-1])
    h_u = max(0, midline - asc_top)
    h_l = max(0, desc_bot - baseline)

    return {
        "h_m": int(h_m),
        "h_u": int(h_u),
        "h_l": int(h_l),
        "asc_reach": (h_u + h_m) / float(h_m),
        "desc_reach": (h_l + h_m) / float(h_m),
    }


def _median(vals):
    return float(np.median(np.asarray(vals, dtype=np.float64)))


def _cv(vals):
    arr = np.asarray(vals, dtype=np.float64)
    if arr.size < 2 or abs(arr.mean()) < 1e-9:
        return 0.0
    return float(arr.std() / arr.mean())


def analyze_zones(gray, lines):
    """Aggregate the three-zone rule over a page.

    gray: uint8 grayscale page. lines: OCR line dicts with 'box' and
    'text'. Returns a dict; available=False (with a reason) when the
    page cannot support the measurement, so callers can fall back to
    the proxy honestly."""
    text = " ".join(str(l.get("text", "") or "") for l in lines)
    latin = len(_LATIN_RE.findall(text))
    has_asc = bool(_ASCENDER_RE.search(text.lower()))
    has_desc = bool(_DESCENDER_RE.search(text.lower()))
    if latin < 12 or not (has_asc or has_desc):
        return {
            "available": False,
            "reason": "not enough Latin letters to apply the zone rule",
        }

    per_line = []
    for l in lines:
        b = l.get("box")
        if not b:
            continue
        z = line_zone_bands(gray, b)
        if z is not None:
            per_line.append(z)
    if len(per_line) < 2:
        return {
            "available": False,
            "reason": "too few measurable lines for zone bands",
        }

    asc = [z["asc_reach"] for z in per_line]
    desc = [z["desc_reach"] for z in per_line]
    out = {
        "available": True,
        "linesUsed": len(per_line),
        "xHeightPx": _median([z["h_m"] for z in per_line]),
        "targetReach": ZONE_TARGET_REACH,
        "ascReach": round(_median(asc), 2) if has_asc else None,
        "descReach": round(_median(desc), 2) if has_desc else None,
        "ascReachCv": round(_cv(asc), 3) if has_asc else None,
        "descReachCv": round(_cv(desc), 3) if has_desc else None,
    }
    # The coach's three mistakes, named.
    flags = []
    for key, present in (("ascReach", has_asc), ("descReach", has_desc)):
        r = out[key]
        if not present or r is None:
            continue
        if r < 1.0 + ZONE_FULL_ERR:
            flags.append("single-zone")  # everything squashed into one zone
        elif r > ZONE_HEAVY_REACH:
            flags.append("upper-heavy" if key == "ascReach" else "lower-heavy")
    out["flags"] = sorted(set(flags))
    return out


def _reach_score(reach):
    """0..1 credit for one zone's reach against the 1:2 rule."""
    err = abs(reach - ZONE_TARGET_REACH)
    if err <= ZONE_FULL_ERR:
        return 1.0
    if err >= ZONE_ZERO_ERR:
        return 0.0
    return 1.0 - (err - ZONE_FULL_ERR) / (ZONE_ZERO_ERR - ZONE_FULL_ERR)


def zone_score(z):
    """Factor-6 score (0-10) from a measured zone analysis.

    Mean reach credit over the zones the text actually uses, minus a
    consistency penalty (up to 2 points) when reach varies line to
    line. Only call when z['available'] is True."""
    credits = []
    cvs = []
    if z.get("ascReach") is not None:
        credits.append(_reach_score(z["ascReach"]))
        cvs.append(z.get("ascReachCv") or 0.0)
    if z.get("descReach") is not None:
        credits.append(_reach_score(z["descReach"]))
        cvs.append(z.get("descReachCv") or 0.0)
    if not credits:
        return None
    base = 10.0 * (sum(credits) / len(credits))
    penalty = min(2.0, (max(cvs) / 0.35) * 2.0) if cvs else 0.0
    return max(0.0, min(10.0, base - penalty))
