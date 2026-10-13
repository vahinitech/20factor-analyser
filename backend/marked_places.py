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
docs/how-a-scan-works.md, section 7, explains each rule.
"""

import numpy as np

import computer_vision

MAX_LOOK = 3
# A line is "taller" or "shorter" when its height is this share away
# from the page's median line height; "keep" when within KEEP_SHARE.
SIZE_LOOK_SHARE = 0.20
# Lines tilted at least this many degrees. Factor 7 loses its full 10
# points at 8 degrees, so 2 degrees costs a quarter of the scale.
ANGLE_LOOK_DEG = 2.0
ANGLE_KEEP_DEG = 1.0
ANGLE_FULL_SCALE_DEG = 8.0
# The recognition level the report calls high (ppocr-server.py).
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


def _reading_places(lines):
    read = [l for l in lines if str(l.get("text") or "").strip()]
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


def _gap_places(arr, lines, rows):
    """Every gap the scorer counts for Word Spacing, with its place: the
    ink gaps inside each line and the gaps between line boxes on one
    row, each divided by the line's (or row's) height."""
    gaps = []
    for row in rows:
        items = row["items"]
        row_h = float(np.mean([l["box"][3] for l in items]))
        for left, right in zip(items, items[1:]):
            x0 = left["box"][0] + left["box"][2]
            px = max(0, right["box"][0] - x0)
            y0 = min(left["box"][1], right["box"][1])
            y1 = max(
                left["box"][1] + left["box"][3],
                right["box"][1] + right["box"][3],
            )
            gaps.append((px / max(1.0, row_h), left, [x0, y0, px, y1 - y0]))
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
    places = {"5": _size_places(accepted)}
    if read:
        places["1"] = _reading_places(accepted)
        places["7"] = _angle_places(accepted)
        places["8"] = _gap_places(arr, accepted, rows)
        places["18"] = _legibility_places(places)
    return places
