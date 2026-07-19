# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Writing-style classification: cursive, print, or mixed.

The coach's rule (Telugu lesson transcript, Jul 2026): English can be
written three ways - cursive, non-cursive (print), or semi-cursive.
Cursive is correct. Print is also good. But NEVER mix the two in one
word: lifting the hand in some places and joining in others turns
"significant" into what reads as "sign if i cant" - inconsistent
joins create false word breaks for every reader, human or machine.

Measurement: within each detected line, ink is split into word
clusters by column gaps (letter gaps are small fractions of the
x-height, word gaps are around one x-height or more). Each word
cluster's ink is labelled into connected components; the ratio of
components to the word's letter count tells the style:

    ratio <= CURSIVE_MAX_RATIO  -> written in one or two strokes: cursive
    ratio >= PRINT_MIN_RATIO    -> roughly one stroke per letter: print
    in between                  -> joined in places, lifted in others: mixed

Pure numpy (no cv2/scipy - components via a small flood fill on the
word crop only). Same honesty contract as zone/tbar analysis.
"""

from collections import deque

import numpy as np

from zone_analysis import MIN_XHEIGHT_PX, _binarise, _dense_band

# Word-cluster segmentation: column gaps below the letter-gap ceiling
# are bridged; gaps at or above the word-gap floor split words.
LETTER_GAP_XH = 0.35
WORD_GAP_XH = 0.9
# Components smaller than this many pixels are dots/noise (i-dots,
# specks) and are not counted as pen lifts.
MIN_COMPONENT_PX = 6
# Style ratio boundaries (components per letter).
CURSIVE_MAX_RATIO = 0.45
PRINT_MIN_RATIO = 0.80
# Page verdict: a style must own this share of words to be the verdict.
DOMINANT_SHARE = 0.65


def _components(ink):
    """Count 8-connected ink components of at least MIN_COMPONENT_PX."""
    h, w = ink.shape
    seen = np.zeros((h, w), dtype=bool)
    count = 0
    for r0 in range(h):
        for c0 in range(w):
            if not ink[r0, c0] or seen[r0, c0]:
                continue
            size = 0
            q = deque([(r0, c0)])
            seen[r0, c0] = True
            while q:
                r, c = q.popleft()
                size += 1
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        rr, cc = r + dr, c + dc
                        if (
                            0 <= rr < h
                            and 0 <= cc < w
                            and ink[rr, cc]
                            and not seen[rr, cc]
                        ):
                            seen[rr, cc] = True
                            q.append((rr, cc))
            if size >= MIN_COMPONENT_PX:
                count += 1
    return count


def _word_clusters(ink, h_m):
    """Column spans of word-sized ink clusters in a line crop."""
    occ = ink.any(axis=0)
    cols = np.nonzero(occ)[0]
    if cols.size == 0:
        return []
    gaps = np.diff(cols)
    word_gap = max(3, int(h_m * WORD_GAP_XH))
    spans = []
    start = cols[0]
    prev = cols[0]
    for c, g in zip(cols[1:], gaps):
        if g >= word_gap:
            spans.append((int(start), int(prev)))
            start = c
        prev = c
    spans.append((int(start), int(prev)))
    return spans


def line_word_styles(gray, box, text):
    """Per-word style ratios for one detected line.

    Returns a list of (ratio, letters) per ink word cluster, using the
    OCR words for letter counts (aligned by order when the counts
    match, the line's mean letters-per-word otherwise)."""
    h_img, w_img = gray.shape[:2]
    x, y, w, h = [int(round(float(v))) for v in box[:4]]
    pad = max(4, h // 2)
    y0, y1 = max(0, y - pad), min(h_img, y + h + pad)
    x0, x1 = max(0, x), min(w_img, x + max(1, w))
    if y1 - y0 < MIN_XHEIGHT_PX or x1 <= x0:
        return []

    ink = _binarise(gray[y0:y1, x0:x1])
    profile = ink.sum(axis=1).astype(np.float64)
    if float(profile.max()) < 3.0:
        return []
    band = _dense_band(profile)
    if band is None:
        return []
    midline, baseline = band
    h_m = baseline - midline + 1
    if h_m < MIN_XHEIGHT_PX:
        return []

    words = [
        w_ for w_ in str(text or "").split() if any(c.isalpha() for c in w_)
    ]
    if not words:
        return []
    clusters = _word_clusters(ink, h_m)
    if not clusters:
        return []
    mean_letters = max(1.0, sum(len(w_) for w_ in words) / float(len(words)))

    out = []
    for i, (c0, c1) in enumerate(clusters):
        if (c1 - c0) < h_m:  # too narrow to be a word
            continue
        letters = (
            float(len(words[i]))
            if len(clusters) == len(words)
            else mean_letters
        )
        comps = _components(ink[:, c0 : c1 + 1])
        if comps == 0:
            continue
        out.append((comps / letters, letters))
    return out


def analyze_style(gray, lines):
    """Classify the page's writing style: cursive, print, or mixed.

    gray: uint8 grayscale page. lines: OCR line dicts with 'box' and
    'text'. Returns availability honestly, per the coach's framing:
    cursive is correct, print is also good, mixing the two is the
    mistake to fix."""
    ratios = []
    for l in lines:
        b = l.get("box")
        if not b:
            continue
        ratios.extend(
            r for r, _ in line_word_styles(gray, b, l.get("text", ""))
        )
    if len(ratios) < 3:
        return {
            "available": False,
            "reason": "too few measurable words to classify the style",
        }

    n = float(len(ratios))
    cursive = sum(1 for r in ratios if r <= CURSIVE_MAX_RATIO)
    print_ = sum(1 for r in ratios if r >= PRINT_MIN_RATIO)
    mixed = len(ratios) - cursive - print_

    shares = {
        "cursive": round(cursive / n, 2),
        "print": round(print_ / n, 2),
        "mixed": round(mixed / n, 2),
    }
    if shares["cursive"] >= DOMINANT_SHARE:
        verdict, quality = "cursive", "good"
    elif shares["print"] >= DOMINANT_SHARE:
        verdict, quality = "print", "good"
    else:
        verdict, quality = "mixed", "needs-change"

    out = {
        "available": True,
        "wordsUsed": len(ratios),
        "shares": shares,
        "verdict": verdict,
        "quality": quality,
    }
    if verdict == "mixed":
        out["advice"] = (
            "Pick one style and stay with it. Cursive (no lifts inside "
            "a word) is correct; print (every letter separate, evenly "
            "spaced) is also good; joining in some places and lifting "
            "in others makes words break apart for the reader - the "
            "coach's example: 'significant' reads as 'sign if i cant'."
        )
    return out
