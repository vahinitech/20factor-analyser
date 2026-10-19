# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Lines, baselines, letter sizes and word gaps from the ink alone.

For handwriting the reader cannot read. On 20 pages of real Telugu
handwriting PP-OCRv5's detector found 7 of 80 written lines
(docs/18-benchmark.md), so nothing was measured that a parent could
trust. The geometry of the writing does not need the words read:

1. Rows (find_rows). The page's letter-sized ink blobs, counted row by
   row, give the row middles; every blob, small strokes included, goes
   to the nearest middle. A line sinking across the page stays one row,
   and a consonant written below the line (a vattu) stays with its row.
2. Baseline (measure_row): a straight line through the bottoms of the
   row's letters, without the strokes lying wholly below the row's
   middle (Telugu writes vottulu apart). Theil-Sen, so one odd letter
   cannot tilt it.
3. Size: each letter's height is its blob's; the median of every
   LETTER_GROUP letters is compared, as one letter alone varies with its
   shape.
4. Words (measure_page): ink blobs overlapping left to right are
   clusters. With each row's number of words known (the passage copied),
   the widest gaps are the word gaps, as for English. Otherwise word
   gaps are set only when the page's gaps fall into two clear groups
   (word_gap_split); some writers space letters as widely as words.
   Scoring (page_features) uses word gaps only when every row's words
   are known, so Word Spacing is not measured without a passage.

Everything is in processed-image pixels and deterministic. The server
uses it for the languages named in VAHINI_INK_GEOMETRY_LANGS.
"""

import math

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - cv2 ships in core
    cv2 = None

import computer_vision
import detector
from letter_geometry import _theil_sen

ROW_MIN_WIDTH = 0.15  # of the page width
ROW_SPACING = 0.7  # line heights between two row middles, at least
WORD_GAP_SPLIT = 1.4  # the step between the two groups of gaps
MIN_WORD_SHARE = 0.1
MAX_WORD_SHARE = 0.6
MIN_WORDS_FOR_GAPS = 3
LETTER_GROUP = 5


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
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= max(6, (0.05 * line_h) ** 2)
    return keep[labels]


def _line_height(arr):
    """A first guess of a written line's height: the median height of
    the page's ink pieces (computer_vision.fallback_line_regions)."""
    pieces = computer_vision.fallback_line_regions(arr)
    if not pieces:
        return None
    return float(np.median([p["box"][3] for p in pieces]))


def _page_ink(arr):
    """The page's ink blobs: {"line_h", "gray", "labels", "stats"}, or
    None. find_rows and measure_page share it, so a row's blob numbers
    mean the same blobs in both."""
    if cv2 is None:
        return None
    line_h = _line_height(arr)
    if not line_h or line_h < 8:
        return None
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    ink = _ink(gray, line_h).astype(np.uint8)
    _n, labels, stats, _c = cv2.connectedComponentsWithStats(ink, 8)
    return {"line_h": line_h, "gray": gray, "labels": labels, "stats": stats}


def find_rows(arr):
    """The written rows of a page, top to bottom, shaped like reader
    lines with empty text and "ink_row" set.

    Row middles are the peaks of the page's letter-sized ink, counted
    row by row and smoothed over half a line; peaks closer than ROW_SPACING lines are
    one row. Each ink blob then belongs to the row whose middle is
    nearest its own: a line sinking across the page stays one row as
    long as it drops less than half the space between rows, and a
    consonant written below the line (a vattu) stays with its letter.
    Each row's outline is the smallest rotated rectangle around its ink.
    """
    page = _page_ink(arr)
    if page is None:
        return []
    line_h, labels, stats = page["line_h"], page["labels"], page["stats"]
    page_w = labels.shape[1]
    n = len(stats)
    blobs = [
        i
        for i in range(1, n)
        if stats[i, cv2.CC_STAT_HEIGHT] < 2.5 * line_h
        and stats[i, cv2.CC_STAT_WIDTH] < 0.5 * page_w
    ]
    if not blobs:
        return []
    # Row middles from the letter-sized blobs only: a consonant written
    # below the line is a small separate stroke, and a row of them made
    # a row of its own.
    tall = float(np.median([stats[i, cv2.CC_STAT_HEIGHT] for i in blobs]))
    letters = [i for i in blobs if stats[i, cv2.CC_STAT_HEIGHT] >= 0.5 * tall]
    keep = np.zeros(n, bool)
    keep[letters] = True
    profile = keep[labels].sum(axis=1).astype(np.float64)
    k = max(3, int(round(line_h * 0.5)) | 1)
    profile = np.convolve(profile, np.ones(k) / k, mode="same")
    peaks = _peaks(profile, int(round(ROW_SPACING * line_h)))
    if not peaks:
        return []
    groups = {p: [] for p in peaks}
    for i in blobs:
        cy = stats[i, cv2.CC_STAT_TOP] + stats[i, cv2.CC_STAT_HEIGHT] / 2.0
        groups[min(peaks, key=lambda p, cy=cy: abs(p - cy))].append(i)
    out = []
    for peak in peaks:
        ids = groups[peak]
        if not ids:
            continue
        mask = np.isin(labels, ids)
        ys, xs = np.nonzero(mask)
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        if x1 - x0 < ROW_MIN_WIDTH * page_w:
            continue
        pts = np.stack([xs, ys], axis=1)[:: max(1, len(xs) // 4000)]
        out.append(
            {
                "text": "",
                "box": [float(x0), float(y0), float(x1 - x0), float(y1 - y0)],
                "poly": detector.outline(pts),
                "score": 0.0,
                "lang": "",
                "printed_hint": False,
                "cv_fallback": True,
                "ink_row": True,
                "blobs": [int(i) for i in ids],
            }
        )
    return out


def _peaks(profile, spacing):
    """Row middles: local maxima of the profile at least a fifth of its
    highest, greedily from the highest, no two closer than spacing."""
    top = float(profile.max())
    if top <= 0:
        return []
    cands = [
        i
        for i in range(1, len(profile) - 1)
        if profile[i] >= profile[i - 1]
        and profile[i] >= profile[i + 1]
        and profile[i] >= 0.2 * top
    ]
    chosen = []
    for i in sorted(cands, key=lambda i: (-profile[i], i)):
        if all(abs(i - j) >= spacing for j in chosen):
            chosen.append(i)
    return sorted(chosen)


def measure_row(page, row):
    """Baseline, angle, letter height and ink clusters of one ink row, or
    None. page: _page_ink's result; row: find_rows's. Words and their
    gaps are set by measure_page, which splits gaps page-wide.

    The row's letters are its ink blobs at least half as tall as its
    typical blob, without those lying wholly below the row's middle
    (consonants written below the line, which Telugu writes as separate
    strokes). The baseline is a straight line through the letters'
    bottoms (Theil-Sen: one odd letter cannot tilt it); the bottoms of
    the lowest ink, used for English, follow those consonants and
    measured clean lines up to 9.5 degrees. A letter's height is its
    blob's: Telugu's body with the mark on top (talakattu) when joined,
    the same for every letter that has one."""
    stats = page["stats"]
    ids = [i for i in row.get("blobs", []) if 0 < i < len(stats)]
    if len(ids) < 2:
        return None
    heights = np.array([stats[i, cv2.CC_STAT_HEIGHT] for i in ids], float)
    big = [i for i, hh in zip(ids, heights) if hh >= 0.5 * np.median(heights)]
    mid = float(np.median([stats[i, 1] + stats[i, 3] / 2.0 for i in big]))
    letters = [i for i in big if stats[i, 1] < mid]
    if len(letters) < 2:
        return None
    xs = [stats[i, 0] + stats[i, 2] / 2.0 for i in letters]
    ys = [float(stats[i, 1] + stats[i, 3]) for i in letters]
    slope, icpt = _theil_sen(xs, ys)
    letter_h = float(np.median([stats[i, 3] for i in letters]))
    # Clusters: blobs overlapping left to right, one akshara or more.
    spans = []
    for i in sorted(ids, key=lambda i: stats[i, 0]):
        x0, x1 = int(stats[i, 0]), int(stats[i, 0] + stats[i, 2])
        if spans and x0 <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], x1)
            spans[-1][2].append(i)
        else:
            spans.append([x0, x1, [i]])
    spans = [s for s in spans if s[1] - s[0] >= 0.15 * letter_h] or spans
    left = float(min(stats[i, 0] for i in ids))
    right = float(max(stats[i, 0] + stats[i, 2] for i in ids))
    return {
        "baseline": [
            [left, slope * left + icpt],
            [right, slope * right + icpt],
        ],
        "angle": abs(math.degrees(math.atan(slope))),
        "signed_angle": math.degrees(math.atan(slope)),
        "letter_height": letter_h,
        "letters": [
            {
                "x": float(stats[i, 0] + stats[i, 2] / 2.0),
                "height": float(stats[i, 3]),
            }
            for i in letters
        ],
        "clusters": [[float(a), float(b)] for a, b, _ids in spans],
        "words": [],
        "gaps": [],
    }


def _split_words(g, split):
    """Words and word gaps of a measured row, given the page's split
    (in letter heights; None: every cluster gap is inside a word)."""
    clusters = g["clusters"]
    lh = g["letter_height"]
    words, gaps = [], []
    cur = list(clusters[0])
    for a, b in zip(clusters, clusters[1:]):
        gap = (b[0] - a[1]) / lh
        if split is not None and gap >= split:
            words.append(cur)
            gaps.append({"x0": a[1], "x1": b[0], "gap": gap})
            cur = list(b)
        else:
            cur[1] = b[1]
    words.append(cur)
    out = []
    for x0, x1 in words:
        hs = [let["height"] for let in g["letters"] if x0 <= let["x"] <= x1]
        out.append(
            {
                "x0": x0,
                "x1": x1,
                "body": float(np.median(hs)) if hs else None,
            }
        )
    g["words"], g["gaps"] = out, gaps


def word_gap_split(widths):
    """The width that separates gaps between words from gaps inside
    them, when the page shows one: the widest step between neighbouring
    sorted gap widths, the wider side holding between MIN_WORD_SHARE
    and MAX_WORD_SHARE of the gaps, the step at least WORD_GAP_SPLIT.
    Else None: the gaps do not fall into two groups (some writers space
    the letters of a word as widely as their words), and words cannot be
    told apart from the ink."""
    ws = sorted(float(w) for w in widths if w > 0)
    if len(ws) < MIN_WORDS_FOR_GAPS:
        return None
    best_step, best_cut = 0.0, None
    for i in range(1, len(ws)):
        share = (len(ws) - i) / len(ws)
        if not MIN_WORD_SHARE <= share <= MAX_WORD_SHARE:
            continue
        step = ws[i] / max(1e-6, ws[i - 1])
        if step > best_step:
            best_step, best_cut = step, (ws[i - 1] + ws[i]) / 2.0
    if best_cut is None or best_step < WORD_GAP_SPLIT:
        return None
    return best_cut


def measure_page(arr, rows, words_per_row=None):
    """measure_row for every row, in order (None kept), with each row's
    words set. When the number of words in each row is known
    (words_per_row: from the reader, or the passage the child copied),
    the widest gaps of the row are its word gaps, as for English
    (computer_vision.line_word_breaks). Otherwise every gap between
    clusters on the page, in letter heights, is split where
    word_gap_split finds two groups; with none, no word gaps are set."""
    page = _page_ink(arr)
    if page is None:
        return [None] * len(rows)
    geo = [measure_row(page, r) for r in rows]
    if words_per_row is not None:
        for g, n in zip(geo, words_per_row):
            if g and n:
                _split_known(g, n)
        return geo
    widths = [
        (b[0] - a[1]) / g["letter_height"]
        for g in geo
        if g
        for a, b in zip(g["clusters"], g["clusters"][1:])
    ]
    split = word_gap_split(widths)
    for g in geo:
        if g:
            _split_words(g, split)
    return geo


def _split_known(g, n_words):
    """Split a row into n_words words at its widest cluster gaps."""
    clusters = g["clusters"]
    widths = [b[0] - a[1] for a, b in zip(clusters, clusters[1:])]
    if len(widths) < n_words - 1:
        _split_words(g, None)
        return
    order = sorted(range(len(widths)), key=lambda i: (-widths[i], i))
    cut = min(widths[i] for i in order[: n_words - 1]) if n_words > 1 else None
    _split_words(g, None if cut is None else cut / g["letter_height"] - 1e-9)


def expect_words(rows, expected_text):
    """Give each row its number of words from the passage the child
    copied, when the passage has exactly one line per row (in order);
    otherwise leave them unknown."""
    lines = [
        t.strip() for t in (expected_text or "").splitlines() if t.strip()
    ]
    if not rows or len(lines) != len(rows):
        return
    for row, text in zip(rows, lines):
        row["words_expected"] = len(text.split())


def letter_groups(g):
    """A row's letter heights, as the median of every LETTER_GROUP
    letters left to right: the size the eye compares, steady whether or
    not the words are known (one letter alone varies with its shape)."""
    hs = [let["height"] for let in sorted(g["letters"], key=lambda l: l["x"])]
    return [
        float(np.median(hs[i : i + LETTER_GROUP]))
        for i in range(0, len(hs) - LETTER_GROUP + 1, LETTER_GROUP)
    ]


def page_features(arr, rows):
    """The features scoring.py reads, measured from ink rows: each word's
    letter height (Size), each row's baseline angle (Baseline Alignment
    and the factors on line angle), and the word gaps when the number of
    words is known (Word Spacing)."""
    known = [r.get("words_expected") for r in rows]
    geo = measure_page(arr, rows, known if all(known) else None)
    bodies = [h for g in geo if g for h in letter_groups(g)]
    angles = [g["angle"] for g in geo if g]
    signed = [g["signed_angle"] for g in geo if g]
    gaps = [gp["gap"] for g in geo if g for gp in g["gaps"]]
    words = sum(len(g["words"]) for g in geo if g) if all(known) else 0
    return {
        "geo": geo,
        "words": words,
        "bodies": bodies,
        "angles": angles,
        "signed": signed,
        "gaps": gaps if all(known) else [],
    }
