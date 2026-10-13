# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Where each letter of a line is, from the reading engine itself.

PaddleOCR's recogniser reads a line as a row of narrow columns and
decides one character per column (CTC). With ``return_word_box`` it
reports, for every character it kept, the column it came from; PaddleOCR
then groups those into word boxes and drops the columns. This module
keeps them: each character's column, mapped back along the line's
outline, gives the letter's position on the page, and the half-way
points between neighbouring letters give its left and right edges.

Nothing here runs a model. ``recognise_columns`` takes the recogniser's
own ``rec_text`` result (text, then [column count, words, columns per
word, kinds]); ``letter_boxes`` places the letters on the page.
How well this works is measured on planted pages by
scripts/letter_boxes_eval.py (docs/how-a-scan-works.md, section 11).
"""

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - cv2 ships in core
    cv2 = None

# A character's column fires a little after the letter's centre: on the
# planted pages (scripts/letter_boxes_eval.py) a quarter of a column
# back puts the median centre error closest to zero.
COL_SHIFT = -0.25


def recognise_columns(rec_text):
    """[(char, column), ...] and the column count from the recogniser's
    rec_text with word boxes: (text, [col_num, words, cols, kinds])."""
    if not isinstance(rec_text, (tuple, list)) or len(rec_text) < 2:
        return [], 0
    info = rec_text[1]
    if not isinstance(info, (list, tuple)) or len(info) < 3:
        return [], 0
    col_num = float(info[0] or 0)
    chars = []
    for word, cols in zip(info[1], info[2]):
        for ch, col in zip(word, cols):
            chars.append((str(ch), int(col)))
    return chars, col_num


def _along(poly, frac):
    """The point a fraction of the way along the line's outline, between
    its top edge (poly[0] to poly[1]) and bottom edge (poly[3] to
    poly[2]): (x, top y, bottom y)."""
    p = np.asarray(poly, dtype=float)
    top = p[0] + frac * (p[1] - p[0])
    bottom = p[3] + frac * (p[2] - p[3])
    return float((top[0] + bottom[0]) / 2), float(top[1]), float(bottom[1])


def letter_boxes(poly, chars, col_num):
    """Letters of one line on the page: [{"char", "x", "bbox"}, ...] for
    every letter or digit, with x its centre and bbox [x, y, w, h] in
    page pixels. Spaces and marks only shape their neighbours' edges."""
    if not chars or col_num <= 0 or poly is None or len(poly) < 4:
        return []
    centres = [
        _along(poly, min(1.0, max(0.0, (col + COL_SHIFT) / col_num)))
        for _, col in chars
    ]
    xs = [c[0] for c in centres]
    steps = [b - a for a, b in zip(xs, xs[1:]) if b > a]
    half = 0.5 * (float(np.median(steps)) if steps else 0.0)
    out = []
    for i, ((ch, _col), (x, top, bottom)) in enumerate(zip(chars, centres)):
        if not ch.isalnum():
            continue
        left = (xs[i - 1] + x) / 2 if i > 0 else x - half
        right = (x + xs[i + 1]) / 2 if i + 1 < len(xs) else x + half
        # A space beside a letter is not part of it.
        if i > 0 and not chars[i - 1][0].strip():
            left = max(left, x - half)
        if i + 1 < len(chars) and not chars[i + 1][0].strip():
            right = min(right, x + half)
        # Round the edges, not the width, so neighbours still meet.
        left, right = int(round(left)), int(round(right))
        top, bottom = int(round(top)), int(round(bottom))
        out.append(
            {
                "char": ch,
                "x": round(x, 1),
                "bbox": [
                    left,
                    top,
                    max(1, right - left),
                    max(1, bottom - top),
                ],
            }
        )
    return out


# Circles for the letters that were hardest to read: at most this many,
# each in a different word, and only letters the recogniser was less
# sure of than HARD_BELOW (on planted pages, under 0.7 holds about half
# the letters it named wrongly and one in seven of the right ones).
HARD_MAX = 2
HARD_BELOW = 0.7
HARD_MIN_LETTERS = 3


def crop_line(arr, poly):
    """The line's four-corner outline straightened into its own image."""
    if cv2 is None or poly is None or len(poly) < 4:
        return None
    pts = np.asarray(poly[:4], dtype=np.float32)
    w = int(
        round(
            max(
                np.linalg.norm(pts[0] - pts[1]),
                np.linalg.norm(pts[3] - pts[2]),
            )
        )
    )
    h = int(
        round(
            max(
                np.linalg.norm(pts[0] - pts[3]),
                np.linalg.norm(pts[1] - pts[2]),
            )
        )
    )
    if w < 4 or h < 4:
        return None
    m = cv2.getPerspectiveTransform(
        pts, np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    )
    return cv2.warpPerspective(arr, m, (w, h), borderMode=cv2.BORDER_REPLICATE)


def hardest_letters(arr, line, read):
    """Up to HARD_MAX letters of one line that the recogniser was least
    sure of, each in a different word, as [{"bbox": [x, y, w, h]}] in page
    pixels; [] when the line cannot be read again or has too few letters.
    read(crop, lang) is ocr_backends.read_line_letters."""
    poly = line.get("poly")
    crop = crop_line(arr, poly)
    if crop is None:
        return []
    got = read(crop, line.get("lang"))
    if not got:
        return []
    rec_text, probs = got
    chars, col_num = recognise_columns(rec_text)
    words = []
    for wi, word in enumerate(rec_text[1][1]):
        words.extend([wi] * len(word))
    placed = letter_boxes(poly, chars, col_num)
    kept = [
        (col, word) for (ch, col), word in zip(chars, words) if ch.isalnum()
    ]
    if len(placed) < HARD_MIN_LETTERS or len(kept) != len(placed):
        return []
    ranked = sorted(
        (
            (float(probs[col]), item["x"], word, item)
            for item, (col, word) in zip(placed, kept)
            if col < len(probs)
        ),
        key=lambda r: (r[0], r[1]),
    )
    out, used = [], set()
    for conf, _x, word, item in ranked:
        if conf >= HARD_BELOW or len(out) >= HARD_MAX:
            break
        if word in used:
            continue
        used.add(word)
        out.append({"bbox": item["bbox"]})
    return out
