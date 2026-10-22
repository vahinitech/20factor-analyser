# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# Tests for style_analysis.py (cursive / print / mixed classification
# by connected components per word) and finishing_letters.py (the ten
# finishing letters tip). Synthetic words are drawn with known
# connectivity: a cursive word is one joined stroke, a print word is
# one stroke per letter, so the classification is checked against
# ground truth by construction.

import os
import sys

import numpy as np

from backend.tests import function_tests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vision import style_analysis  # noqa: E402
from vision.finishing_letters import analyze_finishing_letters  # noqa: E402
from vision.style_analysis import analyze_style  # noqa: E402

H_M = 16


def _blank_page(width=520):
    return np.full((120, width), 245, dtype=np.uint8)


def _draw_word(page, y_mid, x, letters, joined):
    """One synthetic word: `letters` wide strokes of x-height H_M, 6 px
    apart. joined=True links them with a thin baseline stroke (cursive:
    one component); joined=False leaves them separate (print: one
    component per letter). Letter strokes are wide and the connector
    thin so the dense-band finder still sees the full x-height as the
    middle zone. Returns the width used."""
    lw, gap = 8, 6
    for i in range(letters):
        lx = x + i * (lw + gap)
        page[y_mid : y_mid + H_M, lx : lx + lw] = 20
    if joined:
        page[
            y_mid + H_M - 1 : y_mid + H_M,
            x : x + letters * (lw + gap) - gap,
        ] = 20
    return letters * (lw + gap) - gap


def _make_page(word_specs, text):
    """word_specs: list of (letters, joined). Words separated by 2
    x-heights so the cluster splitter sees them as words."""
    page = _blank_page()
    x = 30
    for letters, joined in word_specs:
        used = _draw_word(page, 40, x, letters, joined)
        x += used + 2 * H_M
    lines = [
        {
            "text": text,
            "score": 0.9,
            "box": [30, 40, x - 30, H_M],
        }
    ]
    return page, lines


# --- style classification against constructed connectivity ------------------


def test_cursive_page_is_classified_cursive_and_good():
    page, lines = _make_page(
        [(5, True), (4, True), (5, True), (6, True)],
        "these words flow joined",
    )
    out = analyze_style(page, lines)
    assert out["available"] is True
    assert out["verdict"] == "cursive"
    assert out["quality"] == "good"


def test_print_page_is_classified_print_and_good():
    page, lines = _make_page(
        [(5, False), (4, False), (5, False), (6, False)],
        "these words stay apart",
    )
    out = analyze_style(page, lines)
    assert out["available"] is True
    assert out["verdict"] == "print"
    assert out["quality"] == "good"


def test_mixed_page_needs_change_with_advice():
    page, lines = _make_page(
        [(5, True), (4, False), (5, True), (6, False)],
        "these words keep switching",
    )
    out = analyze_style(page, lines)
    assert out["available"] is True
    assert out["verdict"] == "mixed"
    assert out["quality"] == "needs-change"
    assert "sign if i cant" in out["advice"]


def test_sparse_page_is_unavailable():
    page = _blank_page()
    lines = [{"text": "hi", "score": 0.9, "box": [30, 40, 40, H_M]}]
    out = analyze_style(page, lines)
    assert out["available"] is False


# --- cv2 components match the flood fill they replaced (#231) ----------------


def _line_crops():
    """Ink masks shaped like line crops: the drawn words, the same with
    specks below MIN_COMPONENT_PX, diagonal-only joins (8-connected,
    not 4) and seeded random ink at a few densities."""
    page, _ = _make_page(
        [(5, True), (4, False), (5, True), (6, False)], "a b c d"
    )
    crops = [page[20:80, :] < 128]
    specked = crops[0].copy()
    specked[5, 5] = specked[50, 300] = True  # 1 px
    specked[10:12, 100:102] = True  # 4 px
    specked[30:32, 480:483] = True  # 6 px, counts
    crops.append(specked)
    diag = np.zeros((24, 40), dtype=bool)
    for i in range(12):
        diag[2 + i, 3 + i] = True  # one 12 px stroke, corner to corner
        diag[20 - i, 20 + i] = True
    crops.append(diag)
    rng = np.random.default_rng(231)
    for density in (0.05, 0.2, 0.45, 0.6):
        crops.append(rng.random((40, 160)) < density)
    return crops


def test_cv2_components_match_flood_fill():
    assert style_analysis.cv2 is not None  # the fast path is tested
    fast = style_analysis._components
    flood = style_analysis._components_flood
    for ink in _line_crops():
        assert fast(ink) == flood(ink)
        # word crops are column slices of the line, so not contiguous
        assert fast(ink[:, 3:-3]) == flood(ink[:, 3:-3])


def test_line_word_styles_same_with_and_without_cv2():
    page, lines = _make_page(
        [(5, True), (4, False), (5, True), (6, False)],
        "these words keep switching",
    )
    box, text = lines[0]["box"], lines[0]["text"]
    fast = style_analysis.line_word_styles(page, box, text)
    saved = style_analysis.cv2
    style_analysis.cv2 = None
    try:
        slow = style_analysis.line_word_styles(page, box, text)
    finally:
        style_analysis.cv2 = saved
    assert fast and fast == slow


# --- the ten finishing letters ----------------------------------------------


def test_finishing_letters_tip_with_examples():
    lines = [
        {"text": "my hand can hold it"},
        {"text": "the sun is warm"},
    ]
    out = analyze_finishing_letters(lines)
    assert out["available"] is True
    # hand(d), can(n), hold(d), it(t), sun(n), warm(m) all qualify
    assert out["wordCount"] == 6
    assert "hand" in [e.lower() for e in out["examples"]]
    tip = out["tip"]
    assert tip["title"] == "The 10 letters that improve your handwriting"
    assert "small upward stroke" in tip["text"]
    assert "'hand'" in tip["text"].lower()


def test_no_qualifying_words_is_unavailable():
    lines = [{"text": "go see ozzy"}]  # o/e/y are not finishing letters
    out = analyze_finishing_letters(lines)
    assert out["available"] is False


def test_single_letter_words_a_and_i_qualify():
    # "a" and "I" are common one-letter words ending in finishing
    # letters; the tokenizer must not drop them just for being short.
    lines = [{"text": "I saw a dog run by"}]
    out = analyze_finishing_letters(lines)
    assert out["available"] is True
    examples_lower = [e.lower() for e in out["examples"]]
    assert "a" in examples_lower
    assert "i" in examples_lower


# --- integration ------------------------------------------------------------


def test_build_analysis_reports_style_and_tips():
    from scoring import build_analysis

    page, lines = _make_page(
        [(5, True), (4, False), (5, True), (6, False)],
        "my hand kept switching styles",
    )
    rgb = np.stack([page] * 3, axis=-1)
    d = build_analysis(rgb, lines, layout={}).to_dict()
    assert "styleProfile" in d
    assert "coachTips" in d
    tips = d["coachTips"]
    assert isinstance(tips, list)
    ids = [tp["id"] for tp in tips]
    # 'hand' gates the finishing-letters tip on this page
    assert "finishing-letters" in ids
    if d["styleProfile"].get("verdict") == "mixed":
        assert "one-style-only" in ids
        f15 = [r for r in d["results"] if r["n"] == 15][0]
        assert "Style check" in f15["evidence"]


# unittest discovery collects TestCase classes only (#228).
FunctionTests = function_tests(globals())
