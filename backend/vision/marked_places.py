# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The places a report circles for the five free skills.

Each place is one measurement that went into the skill's score: a line
whose height, angle or reading confidence stands apart from the rest of
the page, or one word gap measured from the ink. Nothing here measures
anything new; it keeps the position of numbers the scorer already uses,
so a circle can say "this is part of why" and nothing more.

Every place is a dict in processed-image pixels:

    bbox        [x, y, w, h] of the line or the gap
    kind        "line" or "gap"
    role        "look" (stands apart) or "keep" (closest to the page's
                usual, the writing to keep doing)
    region_id   the handwriting line it is in ("line_3")
    measure     what was compared: line_height, line_angle,
                read_confidence, word_gap
    value       the measurement (pixels, degrees, 0-1 confidence, or a
                gap divided by its line's height)
    reference   what it was compared with: the page median, level (0
                degrees) or the 0.85 confidence the report calls reliable
    deviation   how far value is from reference, as a share of the
                reference (or of the score's full scale for angles).
                This ranks places; it is not a probability.
    direction   taller/shorter, wider/narrower, tilted/level,
                unclear/clear
    line_confidence  the OCR confidence of the line the place is in

Selection is deterministic: sorted by deviation, then top, then left.
docs/02-how-a-scan-works.md, section 7, explains each rule.
"""

import re

import numpy as np

from vision import computer_vision
from vision import letter_boxes
from vision import letter_geometry

MAX_LOOK = 3
# A line is "taller" or "shorter" when its height is this share away
# from the page's median line height; "keep" when within KEEP_SHARE.
SIZE_LOOK_SHARE = 0.20
# A word's small letters 30% taller or shorter than the page's usual.
WORD_SIZE_LOOK_SHARE = 0.30
# Lines tilted at least this many degrees. Factor 7 loses its full 10
# points at 8 degrees, so 2 degrees costs a quarter of the scale.
ANGLE_LOOK_DEG = 2.0
ANGLE_KEEP_DEG = 1.0
ANGLE_FULL_SCALE_DEG = 8.0
# The recognition level the report calls high (server/app.py).
RELIABLE_READ = 0.85
# A word gap at least half again, or half as much, as the usual gap.
GAP_LOOK_SHARE = 0.50
KEEP_SHARE = 0.10
GAP_KEEP_SHARE = 0.15
# Word Spacing is unmeasured below three gaps (scoring._MIN_WORD_GAPS).
MIN_GAPS = 3
MIN_LINES = 3
# Legibility (18) blends 1, 5, 8 and 7 in this order of weight.
LEGIBILITY_PARTS = ("1", "5", "8", "7")


def _place(
    item, bbox, kind, role, measure, value, reference, deviation, direction
):
    return {
        "bbox": [int(round(v)) for v in bbox],
        "kind": kind,
        "role": role,
        "region_id": item["evidence_id"],
        "measure": measure,
        "value": round(float(value), 3),
        "reference": round(float(reference), 3),
        "deviation": round(float(deviation), 3),
        "direction": direction,
        "line_confidence": round(float(item.get("score", 0) or 0), 3),
    }


def _order(entries):
    """entries: (deviation, item, bbox, ...). Largest deviation first,
    then top to bottom, then left to right."""
    return sorted(entries, key=lambda e: (-e[0], e[2][1], e[2][0]))


def _word_size_places(lines, geo):
    """Words whose small-letter height is far from the page's usual one
    (letter_geometry.py), the measurement Letter size is scored from."""
    words = [
        (item, wd)
        for item, g in zip(lines, geo)
        if g
        for wd in g["words"]
        if wd["xheight"]
    ]
    if len(words) < MIN_LINES:
        return None
    median = float(np.median([wd["xheight"] for _, wd in words]))
    if median <= 0:
        return None
    rows = _order(
        [
            (abs(wd["xheight"] - median) / median, item, wd["bbox"], wd)
            for item, wd in words
        ]
    )
    out = [
        _place(
            item,
            box,
            "word",
            "look",
            "word_xheight",
            wd["xheight"],
            median,
            dev,
            "taller" if wd["xheight"] > median else "shorter",
        )
        for dev, item, box, wd in rows
        if dev >= WORD_SIZE_LOOK_SHARE
    ][:MAX_LOOK]
    dev, item, box, wd = rows[-1]
    if dev <= KEEP_SHARE:
        out.append(
            _place(
                item,
                box,
                "word",
                "keep",
                "word_xheight",
                wd["xheight"],
                median,
                dev,
                "even",
            )
        )
    return out


def _size_places(lines):
    if len(lines) < MIN_LINES:
        return []
    heights = [float(l["box"][3]) for l in lines]
    median = float(np.median(heights))
    if median <= 0:
        return []
    rows = _order(
        [
            (abs(h - median) / median, l, l["box"], h)
            for l, h in zip(lines, heights)
        ]
    )
    out = [
        _place(
            l,
            box,
            "line",
            "look",
            "line_height",
            h,
            median,
            dev,
            "taller" if h > median else "shorter",
        )
        for dev, l, box, h in rows
        if dev >= SIZE_LOOK_SHARE
    ][:MAX_LOOK]
    dev, l, box, h = rows[-1]
    if dev <= KEEP_SHARE:
        out.append(
            _place(
                l, box, "line", "keep", "line_height", h, median, dev, "even"
            )
        )
    return out


def _line_angle(item):
    poly = item.get("poly") or []
    if len(poly) < 2:
        return None
    dx = max(1e-6, float(poly[1][0]) - float(poly[0][0]))
    angle = abs(
        float(
            np.degrees(np.arctan2(float(poly[1][1]) - float(poly[0][1]), dx))
        )
    )
    return angle if np.isfinite(angle) else None


def _angle_places(lines):
    angled = [(l, a) for l in lines if (a := _line_angle(l)) is not None]
    if len(angled) < 2:
        return []
    rows = _order(
        [(a / ANGLE_FULL_SCALE_DEG, l, l["box"], a) for l, a in angled]
    )
    out = [
        _place(l, box, "line", "look", "line_angle", a, 0.0, dev, "tilted")
        for dev, l, box, a in rows
        if a >= ANGLE_LOOK_DEG
    ][:MAX_LOOK]
    dev, l, box, a = rows[-1]
    if a <= ANGLE_KEEP_DEG:
        out.append(
            _place(l, box, "line", "keep", "line_angle", a, 0.0, dev, "level")
        )
    return out


def _wordy(item):
    """A line of letters: three or more, and more letters than anything
    else (not a row of slashes or a row of digits; #140)."""
    text = re.sub(r"\s+", "", str(item.get("text") or ""))
    letters = sum(1 for ch in text if ch.isalpha())
    return letters >= 3 and letters > len(text) / 2


def _reading_places(lines):
    read = [l for l in lines if _wordy(l)]
    if len(read) < 2:
        return []
    rows = _order(
        [
            (
                (RELIABLE_READ - float(l.get("score", 0) or 0))
                / RELIABLE_READ,
                l,
                l["box"],
            )
            for l in read
        ]
    )
    out = [
        _place(
            l,
            box,
            "line",
            "look",
            "read_confidence",
            l.get("score", 0) or 0,
            RELIABLE_READ,
            dev,
            "unclear",
        )
        for dev, l, box in rows
        if dev > 0
    ][:MAX_LOOK]
    dev, l, box = rows[-1]
    if dev <= 0:
        out.append(
            _place(
                l,
                box,
                "line",
                "keep",
                "read_confidence",
                l.get("score", 0) or 0,
                RELIABLE_READ,
                0.0,
                "clear",
            )
        )
    return out


def _gap_places(arr, lines, _rows):
    """Every gap the scorer counts for Word Spacing, with its place: the
    ink gaps inside each line, each divided by the line's height. The
    space between two boxes on one row is not a word gap (scoring.py)."""
    gaps = []
    for l in lines:
        breaks = computer_vision.line_word_breaks(arr, l)
        for px, x0, x1 in breaks or []:
            _x, y, _w, h = l["box"]
            gaps.append((px / max(1.0, h), l, [x0, y, x1 - x0, h]))
    if len(gaps) < MIN_GAPS:
        return []
    median = float(np.median([g for g, _, _ in gaps]))
    if median <= 0:
        return []
    rows_ = _order(
        [(abs(g - median) / median, l, box, g) for g, l, box in gaps]
    )
    out = [
        _place(
            l,
            box,
            "gap",
            "look",
            "word_gap",
            g,
            median,
            dev,
            "wider" if g > median else "narrower",
        )
        for dev, l, box, g in rows_
        if dev >= GAP_LOOK_SHARE and box[2] > 0
    ][:MAX_LOOK]
    dev, l, box, g = rows_[-1]
    if dev <= GAP_KEEP_SHARE and box[2] > 0:
        out.append(
            _place(l, box, "gap", "keep", "word_gap", g, median, dev, "even")
        )
    return out


def _legibility_places(places):
    """The look places of the skills Legibility blends, taken in turn by
    weight, one place per line or gap."""
    out, seen = [], set()
    queues = [
        [p for p in places.get(n, []) if p["role"] == "look"]
        for n in LEGIBILITY_PARTS
    ]
    for depth in range(MAX_LOOK):
        for n, queue in zip(LEGIBILITY_PARTS, queues):
            if depth < len(queue) and len(out) < MAX_LOOK:
                p = queue[depth]
                key = (p["kind"], tuple(p["bbox"]))
                if key not in seen:
                    seen.add(key)
                    out.append({**p, "from_factor": int(n)})
    return out


def free_skill_places(arr, accepted, rows):
    """{"1": [...], "5": [...], "7": [...], "8": [...], "18": [...]} for
    accepted handwriting lines (computer_vision._factor_region_map's
    list, already numbered). Skills that need reading get no places when
    nothing was read (the cv-fallback path)."""
    read = any(str(l.get("text") or "").strip() for l in accepted)
    geo = letter_geometry.measure_page(arr, accepted)
    by_word = _word_size_places(accepted, geo)
    places = {"5": by_word if by_word is not None else _size_places(accepted)}
    if read:
        places["1"] = _reading_places(accepted)
        places["7"] = _angle_places(accepted)
        places["8"] = _gap_places(arr, accepted, rows)
        places["18"] = _legibility_places(places)
    return places


def _point_pairs(pts):
    return [[round(float(x), 1), round(float(y), 1)] for x, y in pts]


def page_measurements(arr, accepted, read_letters=None):
    """What was measured on the page, as geometry to draw beside the
    scores (the report's "What we measured on your page"): the steepest
    line's fitted baseline, one line's small-letter band, the usual
    starting edge and the lines that start off it, and the line the
    reader found hardest. Coordinates are processed-image pixels. Holds
    measurements only, never a score, so every tier may receive it."""
    if not accepted:
        return {}
    width = float(arr.shape[1])
    geo = letter_geometry.measure_page(arr, accepted)
    out = {"lines": len(accepted)}
    # The slope drawn is the one Writing on the line is scored from: each
    # line's outline from the reader (its top edge gives the angle,
    # scoring.py), drawn along the outline's bottom edge. A fitted
    # baseline can catch a neighbouring line where outlines overlap.
    angled = [
        (item, a)
        for item in accepted
        if (a := _line_angle(item)) is not None
        and len(item.get("poly") or []) >= 4
    ]
    if angled:
        item, angle = sorted(angled, key=lambda p: (-p[1], p[0]["box"][1]))[0]
        poly = item["poly"]
        out["slope"] = {
            "mean_deg": round(float(np.mean([a for _, a in angled])), 2),
            "line": {
                "region_id": item["evidence_id"],
                "bbox": [int(v) for v in item["box"]],
                "angle": round(float(angle), 2),
                "baseline": _point_pairs([poly[3], poly[2]]),
            },
        }
    banded = [
        (item, g)
        for item, g in zip(accepted, geo)
        if g and len(g["words"]) >= 3
    ]
    if banded:
        median = float(np.median([g["xheight"] for _, g in banded]))
        item, g = sorted(
            banded,
            key=lambda p: (
                abs(p[1]["xheight"] - median),
                -len(p[1]["words"]),
                p[0]["box"][1],
            ),
        )[0]
        out["size"] = {
            "line": {
                "region_id": item["evidence_id"],
                "bbox": [int(v) for v in item["box"]],
                "baseline": _point_pairs(g["baseline"]),
                "midline": _point_pairs(g["midline"]),
            },
        }
    lefts = [float(item["box"][0]) for item in accepted]
    if len(lefts) >= MIN_LINES:
        usual = float(np.median(lefts))
        off = sorted(
            [
                item
                for item in accepted
                if abs(float(item["box"][0]) - usual) >= 0.04 * width
            ],
            key=lambda item: (
                -abs(float(item["box"][0]) - usual),
                item["box"][1],
            ),
        )[:2]
        out["margin"] = {
            "usual_x": round(usual, 1),
            "top": int(min(i["box"][1] for i in accepted)),
            "bottom": int(max(i["box"][1] + i["box"][3] for i in accepted)),
            "off": [
                {
                    "region_id": i["evidence_id"],
                    "bbox": [int(v) for v in i["box"]],
                }
                for i in off
            ],
        }
    read = [item for item in accepted if _wordy(item)]
    if len(read) >= 2:
        item = sorted(
            read, key=lambda i: (float(i.get("score", 0) or 0), i["box"][1])
        )[0]
        line = {
            "region_id": item["evidence_id"],
            "bbox": [int(v) for v in item["box"]],
        }
        poly = item.get("poly") or []
        if len(poly) >= 4:
            line["underline"] = _point_pairs([poly[3], poly[2]])
            # The letters the reader found hardest on that line, when the
            # scan's recogniser can read it again (letter_boxes.py).
            if read_letters is not None:
                letters = letter_boxes.hardest_letters(arr, item, read_letters)
                if letters:
                    line["letters"] = letters
        out["reading"] = {
            "confidence_pct": int(
                round(
                    100
                    * float(
                        np.mean([float(i.get("score", 0) or 0) for i in read])
                    )
                )
            ),
            "line": line,
        }
    return out
