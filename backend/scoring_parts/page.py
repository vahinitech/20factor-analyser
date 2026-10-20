# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# page.py - the page as a whole: its camera tilt and its lines grouped
# into rows. computer_vision.py reuses these (through scoring) so the
# evidence follows the measurements that produced the report.

import math

import numpy as np

from scoring_parts.stats import mean


def _page_tilt_degrees(lines):
    """Median signed line angle in degrees: a robust estimate of how much
    the whole page is rotated in the photo (camera tilt), as distinct from
    any one line's own slant. A single mis-detected line can't skew a
    median the way it could skew a mean. Returns 0.0 when fewer than one
    usable line angle exists (e.g. a very sparse page), which makes the
    tilt correction that reads this a safe no-op rather than a guess."""
    angles = []
    for l in lines:
        poly = l.get("poly") or []
        if len(poly) >= 2:
            x0, y0 = float(poly[0][0]), float(poly[0][1])
            x1, y1 = float(poly[1][0]), float(poly[1][1])
            dx = max(1e-6, x1 - x0)
            angles.append(math.degrees(math.atan2(y1 - y0, dx)))
    if not angles:
        return 0.0
    return float(np.median(angles))


def _detilted_left_x(box, tilt_deg, w, h):
    """A line's left-edge, vertically-centred point, rotated back around
    the image centre by the page's own detected tilt. Undoes a uniform
    camera rotation before Margin Discipline measures how consistent the
    left margin actually is: without this, a page photographed at even a
    slight angle has every line's raw pixel left-x drift across the page
    from geometry alone, so a physically straight margin can measure as
    inconsistent. tilt_deg=0.0 (nothing detected, or a genuinely flat
    scan) leaves the point unchanged."""
    x, y, _bw, bh = box[0], box[1], box[2], box[3]
    lx = float(x)
    ly = float(y) + max(1.0, float(bh)) * 0.5
    cx, cy = float(w) * 0.5, float(h) * 0.5
    rad = -math.radians(tilt_deg)
    dx, dy = lx - cx, ly - cy
    cos_t, sin_t = math.cos(rad), math.sin(rad)
    return cx + dx * cos_t - dy * sin_t


def _group_lines_by_rows(lines):
    if not lines:
        return []
    hs = [max(1.0, float((l.get("box") or [0, 0, 0, 0])[3])) for l in lines]
    row_thr = max(14.0, mean(hs) * 0.75)
    ordered = sorted(
        lines, key=lambda l: float((l.get("box") or [0, 0, 0, 0])[1])
    )
    rows = []
    for l in ordered:
        b = l.get("box") or [0, 0, 0, 0]
        y = float(b[1])
        h = float(max(1.0, b[3]))
        cy = y + (h * 0.5)
        if not rows:
            rows.append({"cy": cy, "items": [l]})
            continue
        if abs(cy - rows[-1]["cy"]) <= row_thr:
            rows[-1]["items"].append(l)
            rows[-1]["cy"] = mean(
                [
                    float((x.get("box") or [0, 0, 0, 0])[1])
                    + float(max(1.0, (x.get("box") or [0, 0, 0, 0])[3])) * 0.5
                    for x in rows[-1]["items"]
                ]
            )
        else:
            rows.append({"cy": cy, "items": [l]})
    for r in rows:
        r["items"].sort(key=lambda x: float((x.get("box") or [0, 0, 0, 0])[0]))
    return rows
