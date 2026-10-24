# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Which way up a photographed page is, from its writing (#297).

A phone photo of a notebook taken sideways, with no EXIF orientation tag
(phones and WhatsApp often drop it), was scored as it was: 3 lines found
on an 18-line page and Line alignment 8.0 from sideways text. This module
finds the turn from the page itself, before anything is read, so the
reader, the 20 factors and every evidence crop see the page upright.

1. Line direction. The ink is smeared along one axis by about a letter's
   size: along the lines, letters and words join into long thin strips;
   across them, they do not. Two counts compare the axes, how elongated
   the smeared pieces are and how long the smeared runs are; their sum is
   `across` (positive: lines run across the picture). Every handwritten
   page in the benchmarks scores 2 or more upright, so a page turned a
   quarter scores -2 or less, and DIRECTION_SURE sits far from both.
2. Which way up, once the lines run across (`up`, positive: upright):
   - letters reach further above the small-letter band than below it
     (b d f h k l t and capitals against g j p q y);
   - lines start at one margin and end ragged, so their left ends line
     up better than their right ends.
3. When a reader is given (the scan's own recogniser), a turn is checked
   on a few line crops: upright text reads with clearly higher
   confidence than the same crop upside down.

The decision is lopsided on purpose, because turning a page that was
upright is worse than leaving a turned one:
- lines across: the page is turned over (180) only when the signs lean
  upside down and the reader agrees. Otherwise it is left as it is, as
  before; with no reader it is never turned over.
- lines up and down: turned a quarter only when the reader or the signs
  (over at least MIN_LINES lines) say which way, and they do not
  disagree; otherwise `unsure`, and the server refuses the page rather
  than score it.
- no clear direction: left as it is, as before.
- not Latin script (Telugu): marks above and below the line sit
  differently, so the signs are not trusted. Lines up and down are
  refused, and a page is never turned over.

Everything here is counting on a copy at most WORK_SIDE pixels on its
long side: deterministic for the same pixels, no model of its own.
"""

from dataclasses import dataclass

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - cv2 ships in core
    cv2 = None

WORK_SIDE = 1200
# The smear, as a share of the page's typical letter size.
SMEAR = 0.75
# Lines run across when `across` is above this, up and down when below
# minus this; in between the page is left as it is.
DIRECTION_SURE = 1.0
# Which way up from the signs alone.
UP_SURE = 0.2  # a quarter turn's way
FLIP_HINT = 0.15  # worth asking the reader about turning over
# The reader's mean confidence must differ by this much to count.
READ_MARGIN = 0.08
READ_LINES = 2
MIN_INK = 400
MIN_LINES = 3


@dataclass(frozen=True)
class Verdict:
    """turn: degrees the photo is turned clockwise to stand upright (0,
    90, 180 or 270). unsure: the lines run up and down but which way is
    up is not clear, so the page must not be scored. The rest is what
    the call was made from, for tests and the scan's log."""

    turn: int = 0
    unsure: bool = False
    across: float = 0.0
    up: float = 0.0
    read: tuple = ()

    def as_dict(self):
        return {
            "turn": self.turn,
            "unsure": self.unsure,
            "across": round(self.across, 3),
            "up": round(self.up, 3),
            "read": [round(v, 3) for v in self.read],
        }


UPRIGHT = Verdict()


def turned(arr, turn):
    """`arr` (rows, columns, ...) turned `turn` degrees clockwise."""
    k = (turn // 90) % 4
    return np.ascontiguousarray(np.rot90(arr, -k)) if k else arr


def _small(rgb):
    h, w = rgb.shape[:2]
    scale = min(1.0, WORK_SIDE / float(max(h, w)))
    if scale < 1.0:
        rgb = cv2.resize(
            rgb,
            (max(1, int(w * scale)), max(1, int(h * scale))),
            interpolation=cv2.INTER_AREA,
        )
    return rgb


def _ink(gray):
    """Writing as a 0/1 mask: dark against its surroundings, without
    specks, long rules and margin lines (pieces over a quarter of the
    page) or dark background around the page."""
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    ink = cv2.adaptiveThreshold(
        blur,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        12,
    )
    h, w = ink.shape
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
    keep = (
        (stats[:, cv2.CC_STAT_AREA] >= 6)
        & (stats[:, cv2.CC_STAT_WIDTH] < 0.25 * w)
        & (stats[:, cv2.CC_STAT_HEIGHT] < 0.25 * h)
    )
    keep[0] = False
    return (keep[labels] if n > 1 else np.zeros_like(ink, bool)).astype(
        np.uint8
    )


def _letter_size(ink):
    """The pieces' longer side, the median by ink: a letter, or a
    joined word's height. The same whichever way the page lies."""
    _n, _l, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
    stats = stats[1:]
    if stats.size == 0:
        return 0.0
    side = np.maximum(
        stats[:, cv2.CC_STAT_WIDTH], stats[:, cv2.CC_STAT_HEIGHT]
    ).astype(float)
    area = stats[:, cv2.CC_STAT_AREA].astype(float)
    order = np.argsort(side)
    cum = np.cumsum(area[order])
    return float(side[order][np.searchsorted(cum, cum[-1] / 2.0)])


def _smeared(ink, d):
    return cv2.morphologyEx(
        ink,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (d, 1)),
    )


def _elongation(smeared):
    """Mean log of width over height of the smeared pieces, by ink."""
    _n, _l, stats, _ = cv2.connectedComponentsWithStats(smeared, 8)
    stats = stats[1:]
    stats = stats[stats[:, cv2.CC_STAT_AREA] >= 12]
    if stats.size == 0:
        return 0.0
    ratio = stats[:, cv2.CC_STAT_WIDTH] / np.maximum(
        1, stats[:, cv2.CC_STAT_HEIGHT]
    )
    return float(
        np.average(
            np.log(np.maximum(ratio, 1e-3)),
            weights=stats[:, cv2.CC_STAT_AREA],
        )
    )


def _run_length(smeared):
    """Mean length of the smeared rows' runs, a long run counting by
    its length."""
    pad = np.zeros((smeared.shape[0], 1), np.int8)
    step = np.diff(np.hstack([pad, smeared.astype(np.int8), pad]), axis=1)
    runs = (np.nonzero(step == -1)[1] - np.nonzero(step == 1)[1]).astype(float)
    return float((runs * runs).sum() / max(1.0, runs.sum()))


def _across(ink, d):
    """Positive when the lines run across the picture, negative when
    they run up and down; about 0 when the ink has no direction."""
    rows, cols = _smeared(ink, d), _smeared(ink.T.copy(), d)
    shape = _elongation(rows) - _elongation(cols)
    runs = np.log(max(1.0, _run_length(rows)) / max(1.0, _run_length(cols)))
    return shape + float(runs)


def _band_signs(piece):
    """(ink above, ink below) the small-letter band of one written line:
    the densest rows, found across short stretches, so a sloping or wavy
    line still has one band."""
    above = below = 0.0
    h, w = piece.shape
    step = max(8, 3 * h)
    for c in range(0, w, step):
        counts = piece[:, c : c + step].sum(axis=1).astype(float)
        if counts.sum() < 20:
            continue
        band = counts >= 0.5 * counts.max()
        peak = int(np.argmax(counts))
        top = bottom = peak
        while top > 0 and band[top - 1]:
            top -= 1
        while bottom < h - 1 and band[bottom + 1]:
            bottom += 1
        above += float(counts[:top].sum())
        below += float(counts[bottom + 1 :].sum())
    return above, below


def _lines(ink, d):
    """(up, lines, boxes) for a page whose lines run across: `up` in
    -1.5..1.5, positive when it reads upright; how many written lines
    were found, and their boxes (x0, y0, x1, y1), longest first."""
    smeared = _smeared(ink, d)
    _n, labels, stats, _ = cv2.connectedComponentsWithStats(smeared, 8)
    pieces = [
        (i, *stats[i, :4])
        for i in range(1, len(stats))
        if stats[i, 2] >= 3 * stats[i, 3]
        and stats[i, 2] >= 3 * d
        and stats[i, 3] >= 4
    ]
    if not pieces:
        return 0.0, 0, []
    usual = min(float(np.median([p[4] for p in pieces])), 1.5 * d / SMEAR)
    above = below = 0.0
    found = []
    for i, x, y, w, h in pieces:
        mask = (labels[y : y + h, x : x + w] == i) & (
            ink[y : y + h, x : x + w] > 0
        )
        # Lines touching through a tall letter smear into one piece: cut
        # it into as many lines as its height holds.
        parts = max(1, int(round(h / usual)))
        cuts = np.linspace(0, h, parts + 1).astype(int)
        for top, bottom in zip(cuts[:-1], cuts[1:]):
            part = mask[top:bottom]
            cols = np.nonzero(part.any(axis=0))[0]
            if part.sum() < 20 or cols.size == 0:
                continue
            up, down = _band_signs(part)
            above += up
            below += down
            found.append([y + top, y + bottom, x + cols[0], x + cols[-1]])
    letters = (above - below) / (above + below) if above + below else 0.0
    # Pieces at one height are one written line.
    lines = []
    for y0, y1, x0, x1 in sorted(found):
        if lines and y0 < lines[-1][1] - 0.3 * (y1 - y0):
            last = lines[-1]
            lines[-1] = [last[0], max(last[1], y1), min(last[2], x0)]
            lines[-1].append(max(last[3], x1))
        else:
            lines.append([y0, y1, x0, x1])
    edges = 0.0
    if len(lines) >= MIN_LINES:
        lefts = np.array([l[2] for l in lines], float)
        rights = np.array([l[3] for l in lines], float)
        left = float(np.median(np.abs(lefts - np.median(lefts))))
        right = float(np.median(np.abs(rights - np.median(rights))))
        edges = (right - left) / (right + left) if right + left else 0.0
    boxes = sorted(
        ((l[2], l[0], l[3], l[1]) for l in lines),
        key=lambda b: (-(b[2] - b[0]), b[1]),
    )
    return letters + 0.5 * edges, len(lines), boxes


def _reading(small, boxes, read, lang):
    """The reader's mean confidence on up to READ_LINES line crops of
    `small` as it lies, and the same crops turned over."""
    if read is None or not boxes:
        return None
    h = small.shape[0]
    scores = ([], [])
    for x0, y0, x1, y1 in boxes[:READ_LINES]:
        pad = int(0.3 * (y1 - y0))
        crop = small[
            max(0, y0 - pad) : min(h, y1 + pad), max(0, x0 - pad) : x1 + pad
        ]
        for side, piece in enumerate((crop, turned(crop, 180))):
            found = read(np.ascontiguousarray(piece), lang) or []
            scores[side].append(
                max([float(l.get("score") or 0.0) for l in found] or [0.0])
            )
    return float(np.mean(scores[0])), float(np.mean(scores[1]))


def _prefers(reading):
    """+1 when the reader prefers the crops as they lie, -1 turned
    over, 0 when it cannot tell."""
    if reading is None:
        return 0
    gap = reading[0] - reading[1]
    return int(gap >= READ_MARGIN) - int(gap <= -READ_MARGIN)


def measure(rgb, latin=True, read=None, lang="en"):
    """The Verdict for an RGB page (numpy array, any size). read(crop,
    lang) -> lines with "score" is the scan's recogniser, or None."""
    if cv2 is None or rgb is None or rgb.ndim != 3:
        return UPRIGHT
    small = _small(rgb)
    ink = _ink(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY))
    if int(ink.sum()) < MIN_INK:
        return UPRIGHT
    d = max(3, int(round(SMEAR * _letter_size(ink))))
    across = _across(ink, d)
    if across > -DIRECTION_SURE:
        if not latin or across < DIRECTION_SURE:
            return Verdict(across=across)
        up, _count, boxes = _lines(ink, d)
        if up > -FLIP_HINT:
            return Verdict(across=across, up=up)
        # Turned over only when the reader agrees: with no reader to ask,
        # the page is left as it is.
        reading = _reading(small, boxes, read, lang)
        return Verdict(
            turn=180 if _prefers(reading) < 0 else 0,
            across=across,
            up=up,
            read=reading or (),
        )
    if not latin:
        return Verdict(unsure=True, across=across)
    # Lines run up and down: look at the page turned a quarter clockwise,
    # then decide whether that or the opposite quarter is upright. The
    # signs count only over MIN_LINES lines; the reader overrules them
    # only when they are not sure, never when they disagree.
    up, count, boxes = _lines(turned(ink, 90), d)
    signs = 0
    if count >= MIN_LINES:
        signs = int(up >= UP_SURE) - int(up <= -UP_SURE)
    reading = _reading(turned(small, 90), boxes, read, lang)
    reader = _prefers(reading)
    way = reader or signs
    unsure = way == 0 or (reader and signs and reader != signs)
    return Verdict(
        turn=90 if way >= 0 else 270,
        unsure=bool(unsure),
        across=across,
        up=up,
        read=reading or (),
    )
