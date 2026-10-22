# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Tiny geometry helpers shared across the recognition server modules.

Extracted because the same float-box -> clamped-integer-bounds arithmetic
was duplicated verbatim in classify.py, ocr_backends.py and
server/app.py; keeping one copy means the three crop paths can't drift
out of sync.
"""


def clamp_box(x, y, w, h, max_w, max_h):
    """Clamp a float (x, y, w, h) box to integer pixel bounds within an
    image of size max_w x max_h.

    Returns (x0, y0, x1, y1) or None if the box has zero-or-negative area
    after clamping (fully outside the image, or degenerate).
    """
    x0 = max(0, int(round(x)))
    y0 = max(0, int(round(y)))
    x1 = min(max_w, int(round(x + w)))
    y1 = min(max_h, int(round(y + h)))
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


# A reader line's outline gives its band only when it is shaped like a
# line: at least this many times as long as it is thick. The rotated
# rectangle around a short word or two letters ("ps") can lean by twenty
# degrees with the letters' shapes, which says nothing about the line.
LINE_SHAPE = 3.0


def _band_at(pts, x):
    xs = [p[0] for p in pts]
    x = min(max(float(x), min(xs)), max(xs))
    ys = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        if min(x0, x1) <= x <= max(x0, x1):
            if x1 == x0:
                ys.extend((y0, y1))
            else:
                ys.append(y0 + (y1 - y0) * (x - x0) / (x1 - x0))
    return min(ys), max(ys)


def line_band(line, x):
    """(top, bottom) of a reader line at page column x: where the edges of
    its outline ("poly") cross that column, so the band follows a sloping
    line. A column past either end of the outline takes that end's band.
    A line whose outline is not line-shaped (LINE_SHAPE), or has under
    three points, is its box.

    The box of a line sloping by a few degrees is much taller than the
    line: on the analyser's own sample page a line at 4.5 degrees has a
    box 126 px tall around a line 75 px tall, with parts of the rows
    above and below it inside.
    """
    _bx, by, _bw, bh = [float(v) for v in line["box"][:4]]
    pts = [(float(p[0]), float(p[1])) for p in line.get("poly") or []]
    if len(pts) < 3:
        return by, by + bh
    xs = [p[0] for p in pts]
    top, bottom = _band_at(pts, (min(xs) + max(xs)) / 2.0)
    if max(xs) - min(xs) < LINE_SHAPE * (bottom - top):
        return by, by + bh
    return _band_at(pts, x)
