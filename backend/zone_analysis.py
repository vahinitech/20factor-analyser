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
#   3. a dense contiguous row band is the MIDDLE zone: its top edge is
#      the midline, its bottom edge the baseline (of several, the one
#      overlapping the detected line; the padded crop can hold the
#      lines above and below)
#   4. the median reach of the line's tall and hanging letters (ink
#      blobs spanning the band) gives the ascender and descender extents
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

try:
    import cv2
except ImportError:  # pragma: no cover - cv2 ships in core
    cv2 = None

import languages
from geometry import clamp_box

# The coach's rule: reach two x-heights up and down.
ZONE_TARGET_REACH = 2.0
# Full credit within this error; zero credit beyond ZONE_ZERO_ERR.
ZONE_FULL_ERR = 0.35
ZONE_ZERO_ERR = 1.00
# Over-emphasis ("heavy importance to a zone") beyond this reach.
ZONE_HEAVY_REACH = 3.2
# One line whose tall letters (or tails) run long against the page's
# other lines (#194): points lost per x-height of the lines' mean
# distance from the page's median reach, up to LINE_DEV_MAX. Apart from
# the line-to-line spread penalty, which is capped at 2 points and so
# no longer moves on a page whose lines already vary.
LINE_DEV_RATE = 6.0
LINE_DEV_MAX = 3.0
# A line needs a middle band at least this tall (pixels) to be usable.
MIN_XHEIGHT_PX = 6
# Row-density fractions defining the bands.
DENSE_FRAC = 0.40
INK_FRAC = 0.08
# A blob is one of the line's tall (or hanging) letters when it clears
# the x-height band by at least this share of the x-height.
REACH_MIN_FRAC = 0.5

# Which letters rise above the small letters, drop below the line, and
# count as letters: the language pack (backend/languages, #206).
_PACK = languages.language()
_ASCENDER_RE = re.compile(_PACK.char_class("ascender"))
_DESCENDER_RE = re.compile(_PACK.char_class("descender"))
_LATIN_RE = re.compile(_PACK.char_class("letter"))


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


def _own_band(profile, box_top, box_bottom):
    """This line's middle-zone band in a padded crop: of the dense row
    runs (as in dense_band) at least MIN_XHEIGHT_PX tall, the one
    overlapping the detected box the most, then the longest. The longest run alone can be the x-height
    of the line above or below, which the padding takes in on closely
    written pages; every reach on the line was then measured from the
    wrong line."""
    peak = float(profile.max())
    dense = list(profile >= (peak * DENSE_FRAC))
    best, best_key, start = None, None, None
    for i, d in enumerate(dense + [False]):
        if d and start is None:
            start = i
        elif not d and start is not None:
            end = i - 1
            overlap = max(0, min(end, box_bottom) - max(start, box_top) + 1)
            # A run too short to be an x-height (a t-bar row) only wins
            # when there is nothing else.
            tall_enough = end - start + 1 >= MIN_XHEIGHT_PX
            key = (tall_enough, overlap, end - start)
            if best_key is None or key > best_key:
                best, best_key = (start, end), key
            start = None
    return best


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

    band = _own_band(profile, y - y0, y - y0 + h - 1)
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
    limits = _neighbour_bands(profile, midline, baseline)
    own = _own_ink_reach(ink, midline, baseline, limits)
    every = (h_u, h_l)
    if own is not None:
        # The padded crop reaches into the lines above and below on
        # closely ruled paper; their descenders and ascenders read as
        # this line's reach (4.0x on tests' handwriting-sample.jpg).
        h_u, h_l = own
        every = _own_ink_reach(ink, midline, baseline, limits, True)

    return {
        "h_m": int(h_m),
        "h_u": int(h_u),
        "h_l": int(h_l),
        "asc_reach": (h_u + h_m) / float(h_m),
        "desc_reach": (h_l + h_m) / float(h_m),
        # With the tall letters that touch a neighbouring line too
        # (clipped at its band), for comparing this line with the page's
        # others (#194).
        "asc_reach_all": (every[0] + h_m) / float(h_m),
        "desc_reach_all": (every[1] + h_m) / float(h_m),
    }


def _neighbour_bands(profile, midline, baseline):
    """Where the x-height bands of the lines above and below start, as
    rows of this crop: the nearest dense runs at least half an x-height
    tall on either side of this line's band. (top limit, bottom limit),
    either None when the crop does not reach a neighbour. A t-bar row
    can be dense but is never that tall."""
    peak = float(profile.max())
    dense = list(profile >= (peak * DENSE_FRAC))
    need = 0.5 * (baseline - midline + 1)
    runs, start = [], None
    for i, d in enumerate(dense + [False]):
        if d and start is None:
            start = i
        elif not d and start is not None:
            if i - start >= need:
                runs.append((start, i - 1))
            start = None
    above = [b for a, b in runs if b < midline]
    below = [a for a, b in runs if a > baseline]
    return (max(above) if above else None, min(below) if below else None)


def _typical_reach(reaches, h_m, joined_too=False):
    """The usual reach of one line's tall (or hanging) letters.

    reaches: (pixels, joined) per blob, joined when the blob runs into
    the neighbouring line's x-height band. Takes the median over the
    blobs that clear the band by REACH_MIN_FRAC of the x-height, so one
    letter does not set the line: a single long f is outvoted by the
    line's other ascenders. A joined blob (a descender touching a letter
    on the line below) has no measurable end of its own, so it counts
    only when the line has no other tall letter, clipped at the
    neighbour's band. With no tall blob at all the line has no reach to
    speak of, and its largest overshoot is kept (the single-zone
    case). With joined_too the joined blobs count like the others: the
    line's reach for comparing it with the page's other lines, since
    a line of ascenders written too long reaches the line above (#194)."""
    tall = [(r, joined) for r, joined in reaches if r >= REACH_MIN_FRAC * h_m]
    free = [r for r, joined in tall if not joined or joined_too]
    if free or tall:
        return int(round(float(np.median(free or [r for r, _ in tall]))))
    return max([0] + [r for r, _ in reaches])


def _own_ink_reach(
    ink, midline, baseline, limits=(None, None), joined_too=False
):
    """Ascender and descender reach (pixels above the midline, below
    the baseline) of the ink blobs that belong to this line: those
    covering at least half of its x-height band. A neighbour's tail can
    dip into the band's edge but does not span it. A letter that touches
    the line above or below joins it into one blob; such a blob is
    marked joined and its reach stops at the neighbour's x-height band
    (limits, from _neighbour_bands). None when cv2 is unavailable or no
    blob qualifies."""
    if cv2 is None:
        return None
    n, _, stats, _ = cv2.connectedComponentsWithStats(
        (ink > 0).astype(np.uint8), connectivity=8
    )
    h_m = baseline - midline + 1
    need = 0.5 * h_m
    top_limit, bottom_limit = limits
    ups, downs = [], []
    for i in range(1, n):
        top = int(stats[i, cv2.CC_STAT_TOP])
        bottom = top + int(stats[i, cv2.CC_STAT_HEIGHT]) - 1
        if min(bottom, baseline) - max(top, midline) + 1 < need:
            continue
        joined_up = top_limit is not None and top <= top_limit
        joined_down = bottom_limit is not None and bottom >= bottom_limit
        if joined_up:
            top = top_limit + 1
        if joined_down:
            bottom = bottom_limit - 1
        ups.append((max(0, midline - top), joined_up))
        downs.append((max(0, bottom - baseline), joined_down))
    if not ups:
        return None
    return (
        _typical_reach(ups, h_m, joined_too),
        _typical_reach(downs, h_m, joined_too),
    )


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
    asc_all = [z["asc_reach_all"] for z in per_line]
    desc_all = [z["desc_reach_all"] for z in per_line]
    out = {
        "available": True,
        "linesUsed": len(per_line),
        "xHeightPx": _median([z["h_m"] for z in per_line]),
        "targetReach": ZONE_TARGET_REACH,
        "ascReach": round(_median(asc), 2) if has_asc else None,
        "descReach": round(_median(desc), 2) if has_desc else None,
        "ascReachCv": round(_cv(asc), 3) if has_asc else None,
        "descReachCv": round(_cv(desc), 3) if has_desc else None,
        "ascLineDev": round(_line_dev(asc_all), 3) if has_asc else None,
        "descLineDev": round(_line_dev(desc_all), 3) if has_desc else None,
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


def _line_dev(reaches):
    """How far the lines reach past the page's median reach, in
    x-heights, on average over the lines. Each line is measured against
    the page, so one line whose tall letters run long always adds to it;
    the mean, not the largest, so one line read badly does not set it.
    Only reach past the median counts: the mistake is letters written
    too long, and a short line is the spread penalty's to judge."""
    mid = _median(reaches)
    return sum(max(0.0, r - mid) for r in reaches) / len(reaches)


def _line_dev_penalty(dev):
    """Points lost for the lines' reach straying from the page's."""
    return min(LINE_DEV_MAX, dev * LINE_DEV_RATE)


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
    line, and up to LINE_DEV_MAX more as the lines' reach strays from
    the page's median (#194). Only call when z['available'] is True."""
    credits = []
    cvs = []
    devs = []
    for key in ("asc", "desc"):
        if z.get(key + "Reach") is None:
            continue
        credits.append(_reach_score(z[key + "Reach"]))
        cvs.append(z.get(key + "ReachCv") or 0.0)
        devs.append(z.get(key + "LineDev") or 0.0)
    if not credits:
        return None
    base = 10.0 * (sum(credits) / len(credits))
    penalty = min(2.0, (max(cvs) / 0.35) * 2.0) if cvs else 0.0
    penalty += _line_dev_penalty(max(devs)) if devs else 0.0
    return max(0.0, min(10.0, base - penalty))
