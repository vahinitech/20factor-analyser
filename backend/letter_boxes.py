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
