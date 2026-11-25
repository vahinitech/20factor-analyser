# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Two facing pages in one photo: keep the first page with writing.

A notebook photographed open (from the camera or the gallery) holds two
pages side by side. Read as one page, the lines of both are measured
together: margins, slope and spacing come from two pages at once, and
the report describes neither. The owner's decision (2026-11-25): score
one page only, the first one with writing, left to right.

The photo is first stood upright (page_turn.py), so the two pages lie
left and right. The binding between them is a band down the middle of
the picture that is darker than the paper on both sides and runs most of
the page's height: a spiral's rings and holes, or the shadow where two
bound pages meet. Handwriting never does that: a column through the
writing crosses each line's strokes for a moment and is paper the rest
of the way. The band must also be wide (a ring, a fold), which keeps a
single printed rule down a worksheet from counting, and the picture
must be wider than tall, as two upright pages side by side are.

When a binding is found, the page used is the left one, or the right
one when the left has no writing. Everything else on the photo is
painted the colour of that page's paper, so the photo keeps its size
and every box, mark and size in the report stays in the photo's own
pixels. A photo with one page is left exactly as it was: no pixel
changes, so its scores cannot move.

Everything here is counting on a copy at most WORK_SIDE pixels on its
long side: deterministic for the same pixels, no model of its own.
"""

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image

try:
    import cv2
except ImportError:  # pragma: no cover - cv2 ships in core
    cv2 = None

WORK_SIDE = 1200
# Two upright pages side by side are wider than tall; one upright page
# (the usual check) is not, so it is never looked at.
MIN_ASPECT = 1.05
# Where a binding may be: the middle of the picture, as a share of its
# width.
BAND = (0.30, 0.70)
# How much darker than the paper on both sides the binding column is,
# as a share of the paper's brightness: over the whole height, and in
# one strip.
MIN_DROP = 0.08
STRIP_DROP = 0.06
# The page is cut into this many strips across; the binding is the
# darkest column, within NEAR of the same place, in MIN_RUN of them.
STRIPS = 16
NEAR = 0.012
MIN_RUN = 0.7
# How far the binding may lean, across per down: a photo a few degrees
# off straight, not a diagonal stroke.
MAX_SLOPE = 0.12
# The binding's width, as a share of the picture's width: a ring or a
# fold, not a printed rule or a single stroke, and not a dark panel.
MIN_WIDTH = 0.012
MIN_BAND = 0.006
MAX_WIDTH = 0.10
# A page has writing when this share of its area is ink.
MIN_INK = 0.002


@dataclass(frozen=True)
class Facing:
    """Two facing pages were found. used: "left" or "right", the page
    scored. box: (x, y, w, h) of the page scored, as shares of the
    upright photo's width and height. gutter: the binding's middle, as a
    share of the width. The rest is what the call was made from."""

    used: str
    box: tuple
    gutter: float
    drop: float
    run: float

    def as_dict(self, width, height):
        """The answer for a report: the page used and its box in the
        upright photo's pixels."""
        x, y, w, h = self.box
        return {
            "found": 2,
            "used": self.used,
            "box": [
                int(round(x * width)),
                int(round(y * height)),
                int(round(w * width)),
                int(round(h * height)),
            ],
        }


def _small(rgb):
    h, w = rgb.shape[:2]
    scale = min(1.0, WORK_SIDE / float(max(h, w)))
    if scale < 1.0:
        rgb = cv2.resize(
            rgb,
            (max(1, int(w * scale)), max(1, int(h * scale))),
            interpolation=cv2.INTER_AREA,
        )
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def _paper_rows(gray, paper):
    """The rows the pages cover: where most of the picture is paper."""
    share = (gray >= paper * 0.8).mean(axis=1)
    rows = np.flatnonzero(share >= 0.5)
    if rows.size == 0:
        return 0, gray.shape[0]
    return int(rows[0]), int(rows[-1]) + 1


def _profile(rows, width):
    """Each column's mean brightness over these rows, smoothed over the
    binding's width so a stroke or a printed rule averages away. The
    mean, not the median: a spiral is bright rings with dark gaps
    between them, and only the mean counts the gaps."""
    return np.convolve(rows.mean(axis=0), np.ones(width) / width, mode="same")


def _contrast(prof, width, side, lo, hi):
    """For each column from lo to hi: how much darker it is than the
    paper on both sides (the dimmer side's mean over side - width
    columns, beyond a gap of width), as a share of that paper. A
    gradient across the page has no contrast; a binding does."""
    total = np.concatenate(([0.0], np.cumsum(prof)))
    xs = np.arange(lo, hi)
    l0 = np.clip(xs - side, 0, len(prof))
    l1 = np.clip(xs - width, 1, len(prof))
    r0 = np.clip(xs + width, 0, len(prof) - 1)
    r1 = np.clip(xs + side, 1, len(prof))
    left = (total[l1] - total[l0]) / np.maximum(1, l1 - l0)
    right = (total[r1] - total[r0]) / np.maximum(1, r1 - r0)
    around = np.minimum(left, right)
    return (around - prof[lo:hi]) / np.maximum(1.0, around)


def _gutter(gray, paper):
    """(x0, x1, drop, run) of the binding, or None. The page is cut into
    STRIPS strips across; in each, the column in the middle band with
    the most contrast against the paper on both sides is found. A
    binding puts that column on one straight, nearly upright line in
    most strips (run), even when the photo is a little tilted. Writing
    makes a column dark in one strip and not the next."""
    h, w = gray.shape
    top, bottom = _paper_rows(gray, paper)
    body = gray[top:bottom].astype(np.float32)
    if body.shape[0] < STRIPS * 4:
        return None
    width = max(3, int(round(MIN_WIDTH * w)))
    lo, hi = int(BAND[0] * w), int(BAND[1] * w)
    side = max(width * 3, int(0.06 * w))
    near = max(width, int(NEAR * w))
    found = []
    for k, strip in enumerate(np.array_split(body, STRIPS, axis=0)):
        prof = _profile(strip, width)
        con = _contrast(prof, width, side, lo, hi)
        i = int(np.argmax(con))
        if con[i] < STRIP_DROP:
            continue
        # The band's edges in this strip: the whole run of columns still
        # clearly darker than the paper, so a spiral with a shadow or the
        # desk beside it is one band and the page ends before all of it.
        half = min(con[i] * 0.5, STRIP_DROP)
        a, b = i, i
        while a > 0 and con[a - 1] >= half:
            a -= 1
        while b < len(con) - 1 and con[b + 1] >= half:
            b += 1
        found.append((k + 0.5, lo + i, lo + a, lo + b + 1, float(con[i])))
    if len(found) < MIN_RUN * STRIPS:
        return None
    rows = np.array(found)
    # A straight line through the strips' binding columns, refitted on
    # the strips that lie on it.
    keep = np.ones(len(rows), bool)
    for _ in range(2):
        fit = np.polyfit(rows[keep, 0], rows[keep, 1], 1)
        keep = np.abs(np.polyval(fit, rows[:, 0]) - rows[:, 1]) <= near
        if keep.sum() < 2:
            return None
    slope = abs(fit[0]) * STRIPS / max(1.0, body.shape[0])
    run = keep.sum() / float(STRIPS)
    drop = float(np.median(rows[keep, 4]))
    if run < MIN_RUN or drop < MIN_DROP or slope > MAX_SLOPE:
        return None
    x0, x1 = int(rows[keep, 2].min()), int(rows[keep, 3].max())
    widths = rows[keep, 3] - rows[keep, 2]
    if not MIN_BAND * w <= float(np.median(widths)) <= MAX_WIDTH * w:
        return None
    return x0, x1, drop, run


def _ink_share(gray, paper):
    """The share of the page that is ink: marks clearly darker than the
    paper around them. The table, a hand or a shadow beyond the page
    edge is not paper, so it does not count as writing."""
    if gray.size == 0:
        return 0.0
    size = max(15, (min(gray.shape) // 20) | 1)
    around = cv2.medianBlur(gray, size).astype(np.float32)
    on_paper = around >= paper * 0.8
    if not on_paper.any():
        return 0.0
    ink = (gray.astype(np.float32) < around * 0.6) & on_paper
    return float(ink.sum()) / float(on_paper.sum())


def find(rgb):
    """The Facing for an upright RGB photo (numpy array, any size), or
    None when it shows one page."""
    if cv2 is None or rgb is None or rgb.ndim != 3:
        return None
    gray = _small(rgb)
    h, w = gray.shape
    if w < MIN_ASPECT * h:
        return None
    paper = float(np.percentile(gray, 90))
    if paper < 60:
        return None
    found = _gutter(gray, paper)
    if found is None:
        return None
    x0, x1, drop, run = found
    # A margin of a few pixels keeps the binding's shadow off the page.
    pad = max(2, int(0.005 * w))
    left = (0, x0 - pad)
    right = (x1 + pad, w)
    if left[1] - left[0] < 0.2 * w or right[1] - right[0] < 0.2 * w:
        return None
    # Each page against its own paper: light from one side leaves one
    # page dimmer than the other.
    pages = {"left": gray[:, left[0] : left[1]], "right": gray[:, right[0] :]}
    ink = {
        k: _ink_share(v, float(np.percentile(v, 90))) for k, v in pages.items()
    }
    used, (a, b) = "left", left
    if ink["left"] < MIN_INK and ink["right"] >= MIN_INK:
        used, (a, b) = "right", right
    return Facing(
        used=used,
        box=(a / w, 0.0, (b - a) / w, 1.0),
        gutter=round((x0 + x1) / 2.0 / w, 4),
        drop=round(drop, 4),
        run=round(run, 4),
    )


def keep_page(rgb, facing):
    """A copy of the upright RGB photo with everything outside the page
    used painted that page's paper colour. Same size, so every box and
    mark stays in the photo's own pixels."""
    w = rgb.shape[1]
    x, _, bw, _ = facing.box
    a = max(0, min(w, int(round(x * w))))
    b = max(a, min(w, int(round((x + bw) * w))))
    page = rgb[:, a:b]
    gray = page.mean(axis=2)
    light = page[gray >= np.percentile(gray, 60)]
    paper = (
        np.median(light, axis=0)
        if light.size
        else np.array([255, 255, 255], dtype=np.float64)
    )
    out = rgb.copy()
    fill = paper.astype(rgb.dtype)
    out[:, :a] = fill
    out[:, b:] = fill
    return out


def page_photo(rgb, facing):
    """keep_page as a lossless PNG, to stand in for the upload from here
    on: the reader's full-resolution crops are cut from it, so they see
    the same one page. Upright already, so it is read with no turn."""
    buf = io.BytesIO()
    Image.fromarray(keep_page(rgb, facing)).save(
        buf, format="PNG", compress_level=1
    )
    return buf.getvalue()
