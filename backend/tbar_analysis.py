# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Cross-bar (t-bar) craft check, from a handwriting coach's lesson.

The rule being measured (coach transcript, Jul 2026), for the two
patterns this module actually gates on and classifies - a side-by-side
pair of tall stems close enough (within PAIR_GAP_XH) to plausibly
share a bar:

* Two t's side by side (bottle, little, butter): ONE extended cross
  bar across both stems is the craft - two separate bars means an
  unnecessary extra pen lift.
* A t beside another tall letter (at least -> "tl", or "th"/"tk"/"tb"
  and their mirror): the bar must stay on the t stem and not ride over
  the neighbouring ascender.

This does not attempt to verify t's that sit apart in a word (with no
adjacent tall-stem pair to examine, e.g. two t's separated by short
letters) - those are simply out of scope, not asserted as "crossed on
its own".

Pure numpy, same conventions as zone_analysis.py: gated on the OCR
text actually containing the letter patterns, honest availability
reporting, and advisory flags - the observations feed factor evidence
(pen lifts, letter formation) rather than silently changing scores.
"""

import re

import numpy as np

from zone_analysis import INK_FRAC, MIN_XHEIGHT_PX, binarise, dense_band

# Words where the rule applies, from the OCR text (lowercased).
_TT_RE = re.compile(r"tt")
_TL_RE = re.compile(r"t[lhkb]|[lhkb]t")

# A stem must rise at least this fraction of the ascender band to
# count as a tall stroke (a t or l trunk, not a rounded letter top).
STEM_RISE_FRAC = 0.55
# Maximum stem thickness relative to x-height (thicker = a blob).
STEM_MAX_W_FRAC = 0.6
# Two tall stems this close (centre distance in x-heights) are treated
# as a side-by-side pair (tt, tl); farther apart is separate letters.
PAIR_GAP_XH = 3.0
# A bar run must be at least this fraction of the x-height wide.
BAR_MIN_W_FRAC = 0.5
# Bar reaching beyond this fraction of the way toward the neighbouring
# stem counts as riding over it (the "limit it to your t stem" rule).
OVERSHOOT_FRAC = 0.6


def _stems(ink, asc_top, midline, h_m):
    """Tall vertical strokes in the ascender band.

    Returns a list of (centre_col, left, right). A stem is a run of
    columns whose ink occupies most of the rows between the ascender
    top and the midline."""
    band = ink[asc_top:midline, :]
    if band.shape[0] < 2:
        return []
    rise = band.sum(axis=0).astype(np.float64)
    tall = rise >= max(2.0, band.shape[0] * STEM_RISE_FRAC)
    stems = []
    in_run, start = False, 0
    cols = np.append(tall, False)
    for c, on in enumerate(cols):
        if on and not in_run:
            in_run, start = True, c
        elif not on and in_run:
            in_run = False
            if (c - start) <= max(2, int(h_m * STEM_MAX_W_FRAC)):
                stems.append(((start + c - 1) / 2.0, start, c - 1))
    return stems


def _bar_runs(ink, asc_top, midline, h_m):
    """Horizontal bar runs in the cross-bar band.

    The t-bar lives in the upper part of the ascender band. Collapse
    those rows to a column-occupancy vector and return ink runs at
    least half an x-height wide as (left, right) spans."""
    lo = asc_top
    hi = asc_top + max(2, int((midline - asc_top) * 0.7))
    band = ink[lo:hi, :]
    if band.shape[0] < 1:
        return []
    occ = band.any(axis=0)
    runs = []
    in_run, start = False, 0
    cols = np.append(occ, False)
    for c, on in enumerate(cols):
        if on and not in_run:
            in_run, start = True, c
        elif not on and in_run:
            in_run = False
            if (c - start) >= max(3, int(h_m * BAR_MIN_W_FRAC)):
                runs.append((start, c - 1))
    return runs


def _crosses(run, stem):
    return run[0] <= stem[0] <= run[1]


def line_tbar_events(gray, box):
    """Cross-bar events for one detected line.

    gray: full-page uint8 grayscale. box: [x, y, w, h]. Returns a list
    of event strings: "shared" (one bar across a stem pair),
    "separate" (a pair crossed by two distinct bars), "overshoot"
    (a bar from one stem riding over an uncrossed neighbour) and
    "contained" (a bar staying on its own stem beside a tall letter).
    Empty list when the geometry is not measurable."""
    h_img, w_img = gray.shape[:2]
    x, y, w, h = [int(round(float(v))) for v in box[:4]]
    pad = max(4, h // 2)
    y0, y1 = max(0, y - pad), min(h_img, y + h + pad)
    x0, x1 = max(0, x), min(w_img, x + max(1, w))
    if y1 - y0 < MIN_XHEIGHT_PX or x1 <= x0:
        return []

    ink = binarise(gray[y0:y1, x0:x1])
    profile = ink.sum(axis=1).astype(np.float64)
    if float(profile.max()) < 3.0:
        return []
    band = dense_band(profile)
    if band is None:
        return []
    midline, baseline = band
    h_m = baseline - midline + 1
    if h_m < MIN_XHEIGHT_PX:
        return []
    meaningful = profile >= max(2.0, float(profile.max()) * INK_FRAC)
    rows = np.nonzero(meaningful)[0]
    asc_top = int(rows[0])
    if (midline - asc_top) < int(h_m * 0.5):
        return []  # no real ascender band on this line

    stems = _stems(ink, asc_top, midline, h_m)
    bars = _bar_runs(ink, asc_top, midline, h_m)
    if len(stems) < 2 or not bars:
        return []

    events = []
    for s_a, s_b in zip(stems, stems[1:]):
        gap = s_b[0] - s_a[0]
        if gap > PAIR_GAP_XH * h_m:
            continue
        both = [r for r in bars if _crosses(r, s_a) and _crosses(r, s_b)]
        only_a = [r for r in bars if _crosses(r, s_a) and not _crosses(r, s_b)]
        only_b = [r for r in bars if _crosses(r, s_b) and not _crosses(r, s_a)]
        if both:
            events.append("shared")
        elif only_a and only_b:
            events.append("separate")
        elif only_a or only_b:
            # One stem carries a bar, the neighbour does not: the
            # tl-shape. Does the bar stay on its stem or ride over?
            run = (only_a or only_b)[0]
            if only_a:
                reach = (run[1] - s_a[0]) / max(1.0, gap)
            else:
                reach = (s_b[0] - run[0]) / max(1.0, gap)
            events.append(
                "overshoot" if reach >= OVERSHOOT_FRAC else "contained"
            )
    return events


def analyze_tbars(gray, lines):
    """Aggregate the cross-bar craft rule over a page.

    gray: uint8 grayscale page. lines: OCR line dicts with 'box' and
    'text'. Only lines whose OCR text contains a double-t or a
    t-beside-tall-letter pattern are examined, so an 'll' can never
    masquerade as a tt. Returns availability honestly."""
    tt_lines, tl_lines = [], []
    for l in lines:
        # Spaces are stripped before matching: the coach's own example
        # is "at least", where the t and the l sit in adjacent words
        # (and are commonly written joined). The pattern only decides
        # whether a line is WORTH examining - the ink geometry decides
        # the verdict - so an over-eager gate costs a look, never a
        # wrong flag.
        text = str(l.get("text", "") or "").lower().replace(" ", "")
        if _TT_RE.search(text):
            tt_lines.append(l)
        elif _TL_RE.search(text):
            tl_lines.append(l)
    if not tt_lines and not tl_lines:
        return {
            "available": False,
            "reason": "no double-t or t-beside-tall-letter words on page",
        }

    counts = {"shared": 0, "separate": 0, "overshoot": 0, "contained": 0}
    lines_used = 0
    for group, is_tl_gated in ((tt_lines, False), (tl_lines, True)):
        for l in group:
            b = l.get("box")
            if not b:
                continue
            events = line_tbar_events(gray, b)
            if events:
                lines_used += 1
            for e in events:
                if is_tl_gated and e == "shared":
                    # "shared" is only meaningful for a genuine adjacent
                    # double-t pair. A tl-gated line (t beside a tall,
                    # non-t letter) has no second t to legitimately
                    # share a bar with, so a bar that fully crosses
                    # both stems is really riding over the neighbour:
                    # an overshoot, not the double-t craft.
                    e = "overshoot"
                counts[e] += 1

    if sum(counts.values()) == 0:
        return {
            "available": False,
            "reason": "cross-bar geometry not measurable on this page",
        }

    flags = []
    if counts["shared"]:
        flags.append("double-t-single-bar")  # the craft, present
    if counts["separate"]:
        flags.append("double-t-extra-lifts")  # coach's efficiency tip
    if counts["overshoot"]:
        flags.append("t-bar-overshoot")  # bar riding over the next letter

    return {
        "available": True,
        "linesUsed": lines_used,
        "sharedBars": counts["shared"],
        "separateBars": counts["separate"],
        "overshoots": counts["overshoot"],
        "containedBars": counts["contained"],
        "flags": flags,
    }
