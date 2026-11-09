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

try:
    import cv2
except ImportError:  # pragma: no cover - cv2 ships in core
    cv2 = None

import languages
from vision.geometry import clamp_box

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
    own = _own_ink_extent(ink, midline, baseline)
    if own is not None:
        # The padded crop reaches into the lines above and below on
        # closely ruled paper; their descenders and ascenders read as
        # this line's reach (4.0x on tests' handwriting-sample.jpg).
        asc_top, desc_bot = own
    h_u = max(0, midline - asc_top)
    h_l = max(0, desc_bot - baseline)

    return {
        "h_m": int(h_m),
        "h_u": int(h_u),
        "h_l": int(h_l),
        "asc_reach": (h_u + h_m) / float(h_m),
        "desc_reach": (h_l + h_m) / float(h_m),
    }


def _own_ink_extent(ink, midline, baseline):
    """Top and bottom rows of the ink blobs that belong to this line:
    those covering at least half of its x-height band. A neighbour's
    tail can dip into the band's edge but does not span it. None when
    cv2 is unavailable or no blob qualifies."""
    if cv2 is None:
        return None
    n, _, stats, _ = cv2.connectedComponentsWithStats(
        (ink > 0).astype(np.uint8), connectivity=8
    )
    need = 0.5 * (baseline - midline + 1)
    tops, bottoms = [], []
    for i in range(1, n):
        top = int(stats[i, cv2.CC_STAT_TOP])
        bottom = top + int(stats[i, cv2.CC_STAT_HEIGHT]) - 1
        if min(bottom, baseline) - max(top, midline) + 1 >= need:
            tops.append(top)
            bottoms.append(bottom)
    if not tops:
        return None
    return min(tops), max(bottoms)


# Printed ruling (#194): a worksheet's guide lines, or a notebook's
# four-line ruling, give each line's small-letter band from the paper
# instead of from the writing, so the band no longer moves with
# whatever else changes in the line. A rule is a row of pixels at least
# RULE_DARK grey levels darker than the paper RULE_THICK rows above and
# below it (thin, so a letter's stroke does not count), on at least
# RULE_COVER of the columns where the paper above and below is clear (a
# dashed midline counts), on rows clear across 30% of the writing.
RULE_DARK = 40
RULE_THICK = 4
RULE_COVER = 0.45
# A line is on the ruling when one gap between two rules holds this
# many times the ink per row of the gaps either side (_ruled_band).
RULE_DENSE = 1.5
# The page is measured against the ruling when at least this share of
# its measurable lines is on it, and at least two lines are.
RULED_SHARE = 0.5


def find_ruling(gray, x0, x1):
    """Printed ruling across columns x0 to x1 of the page: (rows, mask),
    the rule rows (each the middle of its run of rows) and the rule's
    pixels, to take out of the ink. ([], None) when there is none.

    A pixel is on a rule when it is RULE_DARK darker than the pixels
    RULE_THICK rows above and below it, and those two are paper. Only
    such columns are counted: where a letter stands on or crosses the
    rule, the column says nothing either way. The top and bottom edges
    of a line of writing are not rules: one side of them is ink."""
    if cv2 is None or x1 - x0 < 20:
        return [], None
    crop = np.ascontiguousarray(gray[:, x0:x1])
    k = RULE_THICK
    c = crop.astype(np.int16)
    up = np.full_like(c, 255)
    up[k:] = c[:-k]
    down = np.full_like(c, 255)
    down[:-k] = c[k:]
    paper = cv2.dilate(crop, np.ones((2 * k + 1, 15), np.uint8))
    light = paper.astype(np.int16) - RULE_DARK // 2
    clear = (up >= light) & (down >= light)
    thin = clear & (c < np.minimum(up, down) - RULE_DARK)
    near = thin.copy()
    near[1:] |= thin[:-1]
    near[:-1] |= thin[1:]
    counted = clear.sum(axis=1)
    cover = near.sum(axis=1) / np.maximum(1, counted)
    width = x1 - x0
    rows = np.nonzero((cover >= RULE_COVER) & (counted >= 0.3 * width))[0]
    if rows.size == 0:
        return [], None
    runs, start = [], rows[0]
    for a, b in zip(rows, list(rows[1:]) + [None]):
        if b is None or b != a + 1:
            runs.append((int(start), int(a)))
            start = b
    centres = [(a + b) / 2.0 for a, b in runs]
    # The rule's pixels: dark ones on its rows with paper above and
    # below, so a letter crossing or ending on the rule keeps its ink.
    dark = c < paper.astype(np.int16) - RULE_DARK
    stroke = (up < light) | (down < light)
    mask = np.zeros(gray.shape[:2], dtype=bool)
    for a, b in runs:
        lo, hi = max(0, a - 1), min(gray.shape[0], b + 2)
        mask[lo:hi, x0:x1] = dark[lo:hi] & ~stroke[lo:hi]
    return centres, mask


def ruled_zone_bands(gray, box, rules, rule_mask):
    """Zone geometry for one line measured against the printed ruling:
    the two rules around its small letters (_ruled_band) are its
    midline and baseline, and its letters' reach is taken from them.
    None when the line is not written on the ruling."""
    h_img, w_img = gray.shape[:2]
    x, y, w, h = [int(round(float(v))) for v in box[:4]]
    pad = max(4, h // 2)
    clamped = clamp_box(x, y - pad, max(1, w), h + 2 * pad, w_img, h_img)
    if clamped is None:
        return None
    x0, y0, x1, y1 = clamped
    if y1 - y0 < MIN_XHEIGHT_PX:
        return None
    ink = binarise(gray[y0:y1, x0:x1]) & ~rule_mask[y0:y1, x0:x1]
    profile = ink.sum(axis=1).astype(np.float64)
    if float(profile.max()) < 3.0:
        return None
    band = _ruled_band(
        profile,
        [r - y0 for r in rules if y0 <= r < y1],
        (y - y0, y + h - y0),
    )
    if band is None:
        return None
    top, bottom = band
    h_m = bottom - top
    reach = _ruled_reach(ink, top, bottom)
    if reach is None:
        return None
    asc, desc = reach
    return {
        "h_m": int(round(h_m)),
        "h_u": int(round(((asc or 1.0) - 1.0) * h_m)),
        "h_l": int(round(((desc or 1.0) - 1.0) * h_m)),
        "asc_reach": asc,
        "desc_reach": desc,
    }


def _ruled_band(profile, rules, inside):
    """The line's small-letter band on the ruling: of the gaps between
    two neighbouring rules (at least MIN_XHEIGHT_PX apart) whose middle
    lies inside the line's box (inside: its top and bottom rows), the one
    with the most ink per row, when it holds RULE_DENSE times the ink per row
    of the gaps either side. (top, bottom) in the profile's rows, or
    None.

    Small letters fill their band; only tall letters and tails cross the
    bands above and below. Where one dotted rule runs under each line,
    each gap holds a whole line of writing and no gap stands out, so
    the page keeps the measurement from the ink. The band does not come
    from the ink's own densest rows: a line of long ascenders thickens
    the rows above the midline, and that band would leave the ruling."""
    rules = sorted(rules)
    gaps = [
        (a, b) for a, b in zip(rules, rules[1:]) if b - a >= MIN_XHEIGHT_PX
    ]
    dens = [
        float(profile[int(round(a)) : int(round(b))].mean()) for a, b in gaps
    ]
    mine = [
        i
        for i, (a, b) in enumerate(gaps)
        if inside[0] <= (a + b) / 2 <= inside[1]
    ]
    if not mine:
        return None
    best = max(mine, key=lambda i: (dens[i], -i))
    others = [dens[i] for i in (best - 1, best + 1) if 0 <= i < len(dens)]
    if dens[best] <= 0 or not others:
        return None
    if dens[best] < RULE_DENSE * max(others):
        return None
    return gaps[best]


# A letter rises above the ruled small-letter band (or hangs below it)
# when it passes the band by more than this share of it.
TALL_PAST = 0.5


def _ruled_reach(ink, top, bottom):
    """The line's ascender and descender reach against its ruled band
    (rows top to bottom of the crop): the median over the letters that
    rise above it, and over those that hang below, each in ruled
    x-heights; None for a side no letter reaches, which says nothing
    about how long that side's letters are. The line's own letters are the ink
    blobs covering at least half of the band (_own_ink_extent).

    The median, not the tallest letter: a tail from the line above that
    touches one of this line's ascenders makes one blob as tall as both,
    and whether it touches differs from one page of the same passage to
    the next. A line whose tall letters are all longer still moves."""
    if cv2 is None:
        return None
    n, _, stats, _ = cv2.connectedComponentsWithStats(
        ink.astype(np.uint8), connectivity=8
    )
    h_m = bottom - top
    need = 0.5 * h_m
    ups, downs, own = [], [], 0
    for i in range(1, n):
        y0 = int(stats[i, cv2.CC_STAT_TOP])
        y1 = y0 + int(stats[i, cv2.CC_STAT_HEIGHT]) - 1
        if min(y1, bottom) - max(y0, top) + 1 < need:
            continue
        own += 1
        if top - y0 > TALL_PAST * h_m:
            ups.append((bottom - y0) / h_m)
        if y1 - bottom > TALL_PAST * h_m:
            downs.append((y1 - top) / h_m)
    if not own:
        return None
    asc = float(np.median(ups)) if ups else None
    desc = float(np.median(downs)) if downs else None
    return asc, desc


def _ruled_lines(gray, lines):
    """Each line's zone bands measured against the page's printed
    ruling, or None when the page is not ruled (RULED_SHARE)."""
    boxes = [l.get("box") for l in lines if l.get("box")]
    if len(boxes) < 2:
        return None
    x0 = max(0, int(min(float(b[0]) for b in boxes)))
    x1 = min(gray.shape[1], int(max(float(b[0]) + float(b[2]) for b in boxes)))
    rules, mask = find_ruling(gray, x0, x1)
    if len(rules) < 2:
        return None
    per_line = [ruled_zone_bands(gray, b, rules, mask) for b in boxes]
    per_line = [z for z in per_line if z is not None]
    if len(per_line) < max(2, RULED_SHARE * len(boxes)):
        return None
    return per_line


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

    # On ruled paper the bands come from the printed lines; otherwise
    # from each line's own ink, as before.
    per_line = _ruled_lines(gray, lines)
    ruled = per_line is not None
    if not ruled:
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

    # A ruled line with no tall letter (or no tail) is left out of that
    # side; when no line has one, the letters stay in one zone (1.0).
    asc = [z["asc_reach"] for z in per_line if z["asc_reach"] is not None]
    desc = [z["desc_reach"] for z in per_line if z["desc_reach"] is not None]
    asc, desc = asc or [1.0], desc or [1.0]
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
    if ruled:
        out["ruled"] = True
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
