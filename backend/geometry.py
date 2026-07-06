# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Tiny geometry helpers shared across the recognition server modules.

Extracted because the same float-box -> clamped-integer-bounds arithmetic
was duplicated verbatim in classify.py, ocr_backends.py and
ppocr-server.py; keeping one copy means the three crop paths can't drift
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
