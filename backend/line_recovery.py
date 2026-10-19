# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Handwriting the line detector did not find, read again.

PP-OCR's detector sometimes misses a whole written line, or the middle of
one, on closely spaced handwriting: on the UJI test pages it found three
of four lines on several pages and none of a line's middle words on
another. The scorer only measures the lines it is given, so a missed line
silently drops out of every factor. This finds that writing from the ink
and has the scan's own recogniser read it:

1. Ink: an adaptive threshold of the page, scaled to the found lines'
   height, without ruled lines (long horizontal or vertical runs) and
   specks.
2. Ink outside every found line's box, joined into word-sized blobs,
   is a candidate when it is at least MIN_WIDTH line heights wide and
   MIN_HEIGHT tall: a missed word, not the tail of a found line's letter.
   A blob taller than SPLIT_HEIGHT lines (a tail touching the next line)
   is cut at its emptiest row.
3. Each candidate, with the ink strokes it is part of, is cropped and
   read again by the scan's own reader (detection and recognition: on a
   crop around one line it finds the words the page-wide pass missed).
   A word of at least MIN_LETTERS letters at MIN_SCORE confidence or
   more, whose middle lies in the candidate and outside every found
   line, is kept; anything else is left out, as before. A second round
   reads what the first left unread.

detector.join_row_pieces then joins a recovered piece to the rest of its
line. Everything here depends only on the photo and the found lines, so
the same photo gives the same lines.
"""

import re

import numpy as np

import detector

try:
    import cv2
except ImportError:  # pragma: no cover - cv2 ships in core
    cv2 = None

MIN_WIDTH = 1.2  # line heights
MIN_HEIGHT = 0.25
MAX_HEIGHT = 3.0
SPLIT_HEIGHT = 1.3
STROKE_REACH = 0.35
MIN_SCORE = 0.60
MIN_LETTERS = 2
MAX_READS = 12
ROUNDS = 2
# A word this much inside a found line is that line, read again.
WORD_OVERLAP = 0.40
MAX_WORD_HEIGHT = 1.5  # line heights
RULE_LENGTH = 0.25  # of the page width or height


def _ink(gray, line_h):
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    block = max(15, int(round(line_h * 0.6)) | 1)
    ink = cv2.adaptiveThreshold(
        blur,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        block,
        12,
    )
    h, w = ink.shape
    rules = (
        (max(3, int(w * RULE_LENGTH)), 1),
        (1, max(3, int(h * RULE_LENGTH))),
    )
    for size in rules:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, size)
        rule = cv2.morphologyEx(ink, cv2.MORPH_OPEN, kernel)
        ink = cv2.subtract(ink, rule)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    min_area = max(6, int((0.06 * line_h) ** 2))
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
    return keep[labels]


def _readable(line):
    """A found line that really holds writing: a garbage reading over a
    line (one letter at low confidence) must not hide it from recovery."""
    text = str(line.get("text") or "")
    return (
        float(line.get("score", 0.0) or 0.0) >= MIN_SCORE
        and len(re.findall(r"\w", text)) >= MIN_LETTERS
    )


def _rows(part, line_h):
    """Row ranges of a candidate, one per written line: a candidate
    taller than SPLIT_HEIGHT line heights (a tail joining two lines) is
    cut at its emptiest row, at least half a line from either edge."""
    h = part.shape[0]
    if h <= SPLIT_HEIGHT * line_h:
        return [(0, h)]
    edge = int(round(0.5 * line_h))
    profile = part.sum(axis=1).astype(np.float64)
    k = max(3, int(round(line_h * 0.1)) | 1)
    profile = np.convolve(profile, np.ones(k) / k, mode="same")
    cut = edge + int(np.argmin(profile[edge : h - edge]))
    upper = _rows(part[:cut], line_h)
    lower = _rows(part[cut:], line_h)
    return upper + [(a + cut, b + cut) for a, b in lower]


def missed_regions(arr, lines):
    """Candidate places of writing outside every found line, top to
    bottom: [{"box": [x, y, w, h], "points": Nx2 ink pixels}] in page
    pixels.
    The box covers the ink strokes the uncovered ink belongs to."""
    lines = [l for l in lines if l.get("box") and _readable(l)]
    if cv2 is None or not lines:
        return []
    heights = [float(l["box"][3]) for l in lines if l.get("box")]
    if not heights:
        return []
    line_h = float(np.median(heights))
    if line_h < 8:
        return []
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    ink = _ink(gray, line_h)
    page_h, page_w = ink.shape
    covered = np.zeros_like(ink)
    for l in lines:
        x, y, w, h = [int(round(float(v))) for v in l["box"][:4]]
        covered[max(0, y) : max(0, y + h), max(0, x) : max(0, x + w)] = True
    loose = (ink & ~covered).astype(np.uint8)
    kx = max(3, int(round(line_h * 0.5)))
    joined = cv2.dilate(
        loose, cv2.getStructuringElement(cv2.MORPH_RECT, (kx, 3))
    )
    n, labels, stats, _ = cv2.connectedComponentsWithStats(joined, 8)
    _count, strokes = cv2.connectedComponents(ink.astype(np.uint8), 8)
    reach = int(round(STROKE_REACH * line_h))
    found = []
    for i in range(1, n):
        x, y, w, h = (int(v) for v in stats[i, :4])
        if w < MIN_WIDTH * line_h or h < MIN_HEIGHT * line_h:
            continue
        if h > MAX_HEIGHT * line_h:
            continue
        part = (labels[y : y + h, x : x + w] == i) & (
            loose[y : y + h, x : x + w] > 0
        )
        for r0, r1 in _rows(part, line_h):
            rows = part[r0:r1]
            cols = np.nonzero(rows.any(axis=0))[0]
            if cols.size == 0 or cols[-1] - cols[0] + 1 < MIN_WIDTH * line_h:
                continue
            ids = np.unique(strokes[y + r0 : y + r1, x : x + w][rows])
            ids = ids[ids > 0]
            # The strokes the loose ink belongs to, kept to the rows
            # around it so a tail into the next line cannot stretch it.
            y_lo, y_hi = max(0, y + r0 - reach), min(page_h, y + r1 + reach)
            x_lo, x_hi = max(0, x - kx), min(page_w, x + w + kx)
            mask = np.isin(strokes[y_lo:y_hi, x_lo:x_hi], ids)
            ys, xs = np.nonzero(mask)
            if xs.size == 0:
                continue
            xs, ys = xs + x_lo, ys + y_lo
            found.append(
                {
                    "box": [
                        int(xs.min()),
                        int(ys.min()),
                        int(xs.max() - xs.min() + 1),
                        int(ys.max() - ys.min() + 1),
                    ],
                    "points": np.stack([xs, ys], axis=1),
                }
            )
    found.sort(key=lambda r: (r["box"][1], r["box"][0]))
    return found


def _inside(point, box):
    x, y, w, h = box
    return x <= point[0] <= x + w and y <= point[1] <= y + h


def recover_lines(arr, lines, read, lang="en"):
    """Words read from the writing the detector missed (missed_regions),
    each shaped like a reader's line and marked "recovered";
    detector.join_row_pieces joins them into lines. read(crop, lang)
    returns the reader's lines in crop pixels, or None (see
    ocr_backends.read_region). A word counts when its middle lies in the
    missed region, outside every found line, read with MIN_SCORE
    confidence or more, holding at least MIN_LETTERS letters (a smudge
    reads as "22" or "-"), and at most MAX_WORD_HEIGHT lines tall."""
    if read is None:
        return []
    out = []
    page_h, page_w = arr.shape[:2]
    heights = [float(l["box"][3]) for l in lines if _readable(l)]
    line_h = float(np.median(heights)) if heights else float(page_h)
    for region in missed_regions(arr, lines)[:MAX_READS]:
        x, y, w, h = region["box"]
        pad = max(4, int(round(h * 0.15)))
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(page_w, x + w + pad), min(page_h, y + h + pad)
        got = read(np.ascontiguousarray(arr[y0:y1, x0:x1]), lang) or []
        for word in got:
            text = str(word.get("text") or "").strip()
            score = float(word.get("score") or 0.0)
            poly = [[px + x0, py + y0] for px, py in word.get("poly") or []]
            letters = sum(1 for ch in text if ch.isalpha())
            if score < MIN_SCORE or letters < MIN_LETTERS:
                continue
            if word.get("whole_crop"):
                # Read as one line: its outline is the ink's, so a sloping
                # line keeps its slope.
                pts = region["points"]
                poly = detector.outline(pts[:: len(pts) // 4000 + 1])
            if len(poly) < 3:
                continue
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            box = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
            if box[3] > MAX_WORD_HEIGHT * line_h:
                continue  # one box over two lines of writing
            middle = (box[0] + box[2] / 2.0, box[1] + box[3] / 2.0)
            if not _inside(middle, region["box"]):
                continue
            if any(
                _inside(middle, l["box"])
                or detector.overlap_share(box, l["box"]) >= WORD_OVERLAP
                for l in lines
                if _readable(l)
            ):
                continue
            out.append(
                {
                    "text": text,
                    "poly": poly,
                    "box": box,
                    "score": score,
                    "lang": lang,
                    "printed_hint": detector.looks_printed(text, score, box),
                    "recovered": True,
                }
            )
    return out


def add_missed(arr, lines, read, lang="en"):
    """lines plus the words recover_lines reads, once each (repeated
    readings from overlapping crops dropped by detector.merge_lines). A
    found line that is not readable (a garbage reading) gives way to the
    recovered words covering at least half its width. ROUNDS passes: a
    crop read only in part leaves the rest for a tighter crop."""
    for _ in range(ROUNDS):
        found = recover_lines(arr, lines, read, lang)
        if not found:
            break
        found = detector.merge_lines(found)
        kept = [l for l in lines if _readable(l) or not _covered(l, found)]
        lines = sorted(kept + found, key=lambda l: (l["box"][1], l["box"][0]))
    return lines


def _covered(line, found):
    inside = [
        f
        for f in found
        if _inside(
            (f["box"][0] + f["box"][2] / 2, f["box"][1] + f["box"][3] / 2),
            line["box"],
        )
    ]
    return sum(f["box"][2] for f in inside) >= 0.5 * max(1.0, line["box"][2])
