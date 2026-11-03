# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# reading.py - how surely each word can be read (#193), for Letter
# Formation (1), Legibility (18) and Character Distinction (19): the
# reader's confidence word by word, the ink check for tangled words and,
# with a copied passage, the words not read as written.

import difflib
import math
import re

import numpy as np

from scoring_parts.stats import mean

# Tangled words (#193). A word's tangle is how many strokes its columns
# cross in its small-letter band times how much its outline turns, each
# against the page's usual word (letter_geometry._crossings, _turning).
# The most tangled word of a page reached 1.18 to 1.47 on the 20 real
# benchmark pages (benchmarks/uji-clean) and 1.16 to 1.53 on the clean
# planted pages; a scribbled word (scripts/factor_tests.py, messy_word)
# 1.27 to 1.83. A word loses nothing up to TANGLE_START and is counted
# as unreadable at TANGLE_FULL. The median needs MIN_TANGLE_WORDS words.
TANGLE_START = 1.35
TANGLE_FULL = 1.9
MIN_TANGLE_WORDS = 6
# Letter Formation loses up to this many points for its most tangled word.
TANGLE_POINTS = 2.5


def _norm_words(text):
    return re.sub(r"[^\w ]", "", str(text or "").lower()).split()


def _word_tangles(geo):
    """Per line, each measured word's share of the way from TANGLE_START
    to TANGLE_FULL (0 to 1), and the page's most tangled word's ratio.
    Lines with too little ink to measure give []."""
    words = [
        wd
        for g in geo
        if g
        for wd in g["words"]
        if wd.get("crossings") and wd.get("turning")
    ]
    if len(words) < MIN_TANGLE_WORDS:
        return [[] for _ in geo], None
    cross_med = float(np.median([wd["crossings"] for wd in words]))
    turn_med = float(np.median([wd["turning"] for wd in words]))

    def tangle(wd):
        return (wd["crossings"] / cross_med) * (wd["turning"] / turn_med)

    out = []
    for g in geo:
        out.append(
            [
                min(
                    1.0,
                    max(0.0, tangle(wd) - TANGLE_START)
                    / (TANGLE_FULL - TANGLE_START),
                )
                for wd in (g["words"] if g else [])
                if wd.get("crossings") and wd.get("turning")
            ]
        )
    return out, max(tangle(wd) for wd in words)


def _reading_features(lines, geo):
    """How surely each word can be read (#193). The reader gives one
    confidence per line, so each word starts at its line's; a word whose
    ink is tangled (_word_tangles) loses that share of it, and when the
    writer copied a known passage (recognizer.align_to_expected), each
    copied word the reader did not read as written counts 0. ``reading``
    is the mean over the words with the least sure quarter counted
    twice: one scribbled word among 30 moved the plain mean too little
    to see."""
    tangles, worst = _word_tangles(geo)
    sure, copied, read_right = [], 0, 0
    for line, pens in zip(lines, tangles):
        text = str(line.get("text") or "")
        conf = float(line.get("score", 0.0) or 0.0)
        expected = _norm_words(line.get("expected")) if "match" in line else []
        n = len(expected) or len(_norm_words(text))
        if not n:
            continue
        pens = sorted(pens, reverse=True)[:n] + [0.0] * max(0, n - len(pens))
        words = sorted(conf * (1.0 - p) for p in pens)
        if expected:
            as_read = _norm_words(line.get("text_as_read", text))
            found = sum(
                b.size
                for b in difflib.SequenceMatcher(
                    None, as_read, expected, autojunk=False
                ).get_matching_blocks()
            )
            missed = max(0, len(expected) - found)
            words[:missed] = [0.0] * missed
            copied += len(expected)
            read_right += len(expected) - missed
        sure.extend(words)
    if not sure:
        return {
            "reading": None,
            "conf_low": None,
            "words_read": None,
            "tangle_worst": worst,
            "tangle_points": 0.0,
        }
    sure.sort()
    low = sure[: max(1, math.ceil(len(sure) / 4))]
    return {
        "reading": 0.5 * mean(sure) + 0.5 * mean(low),
        "conf_low": mean(low),
        "words_read": read_right / copied if copied else None,
        "tangle_worst": worst,
        "tangle_points": TANGLE_POINTS
        * max([p for pens in tangles for p in pens] or [0.0]),
    }
