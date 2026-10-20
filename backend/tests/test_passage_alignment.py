# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Passage alignment by graphemes (recognizer.align_to_expected, #209).

When the writer copies a known passage, each line read is compared with
its passage line. The comparison used to drop every combining mark
(Python's \\w does not match them), so a Telugu or Hindi line with a
vowel sign missing matched its passage perfectly. It now compares
grapheme by grapheme with the marks kept; English matches must not move.

The passage says what should have been written; only the ink says what
was (docs/20-languages.md, sections 7 and 19, gap 8). So for each factor
that counts letters from the text, adding a passage must not raise its
score on a page whose ink is the same. These go through the public
scoring.build_analysis, as the server does."""

import copy
import difflib
import os
import re
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
sys.path.insert(0, SERVER_DIR)

import recognizer  # noqa: E402
import scoring  # noqa: E402

# పిల్లి పాలు తాగింది ("the cat drank milk") and the same line with the
# u sign of పాలు left off: పాల.
CAT = "\u0c2a\u0c3f\u0c32\u0c4d\u0c32\u0c3f"
DRANK = "\u0c24\u0c3e\u0c17\u0c3f\u0c02\u0c26\u0c3f"
TELUGU_PASSAGE = f"{CAT} \u0c2a\u0c3e\u0c32\u0c41 {DRANK}"
TELUGU_NO_U_SIGN = f"{CAT} \u0c2a\u0c3e\u0c32 {DRANK}"
# मैं हिंदी में लिखता हूँ, and the same line with हिंद for हिंदी.
HINDI_PASSAGE = (
    "\u092e\u0948\u0902 \u0939\u093f\u0902\u0926\u0940 \u092e\u0947\u0902 "
    "\u0932\u093f\u0916\u0924\u093e \u0939\u0942\u0901"
)
HINDI_NO_II_SIGN = HINDI_PASSAGE.replace("\u0926\u0940", "\u0926")


def _old_norm(s):
    """The comparison before #209, kept here to show English is
    unchanged."""
    return re.sub(
        r"\s+", " ", re.sub(r"[^\w ]", "", str(s or "").lower())
    ).strip()


def _line(text, y=50, lang="en"):
    x, w, h = 10, 620, 50
    return {
        "text": text,
        "score": 0.8,
        "box": [x, y, w, h],
        "poly": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
        "lang": lang,
    }


def _align(reading, passage, lang="en"):
    line = _line(reading, lang=lang)
    summary = recognizer.align_to_expected([line], passage)
    return line, summary


class TestIndicMarksCount(unittest.TestCase):
    def test_a_missing_telugu_vowel_sign_lowers_the_match(self):
        whole, _ = _align(TELUGU_PASSAGE, TELUGU_PASSAGE, "te")
        missing, _ = _align(TELUGU_NO_U_SIGN, TELUGU_PASSAGE, "te")
        self.assertEqual(whole["match"], 1.0)
        self.assertLess(missing["match"], 1.0)
        # Nine aksharas, one of them different.
        self.assertAlmostEqual(missing["match"], round(16 / 18, 3))
        # Before #209 the two lines compared as the same consonants.
        self.assertEqual(
            _old_norm(TELUGU_NO_U_SIGN), _old_norm(TELUGU_PASSAGE)
        )

    def test_a_missing_hindi_vowel_sign_lowers_the_match(self):
        whole, _ = _align(HINDI_PASSAGE, HINDI_PASSAGE, "hi")
        missing, _ = _align(HINDI_NO_II_SIGN, HINDI_PASSAGE, "hi")
        self.assertEqual(whole["match"], 1.0)
        self.assertLess(missing["match"], 1.0)

    def test_the_known_line_still_replaces_the_reading(self):
        line, summary = _align(TELUGU_NO_U_SIGN, TELUGU_PASSAGE, "te")
        self.assertEqual(line["text"], TELUGU_PASSAGE)
        self.assertEqual(line["expected"], TELUGU_PASSAGE)
        self.assertEqual(summary["aligned"], 1)


class TestEnglishUnchanged(unittest.TestCase):
    PAIRS = (
        ("The quick brwn fox.", "The quick brown fox"),
        ("hello  world!!", "Hello, world"),
        ("ths is a tst\tline", "This is a test line"),
        ("my_name is 42", "My name is 42."),
        ("zzzz qqqq", "The cat sat on the mat"),
    )

    def test_matches_are_what_they_were(self):
        for reading, passage in self.PAIRS:
            old = difflib.SequenceMatcher(
                None, _old_norm(reading), _old_norm(passage)
            ).ratio()
            line, _ = _align(reading, passage)
            with self.subTest(reading=reading):
                if old >= 0.45:
                    self.assertEqual(line["match"], round(old, 3))
                    self.assertEqual(line["text"], passage)
                else:
                    self.assertNotIn("match", line)
                    self.assertEqual(line["text"], reading)

    def test_an_accent_compares_the_same_composed_or_not(self):
        # The one change for Latin text: a decomposed accent (e and a
        # combining acute) used to lose its mark, so it matched a plain e
        # and not the accented one. After NFC both spellings are the same
        # letter.
        passage = "Caf\u00e9 au lait"
        composed, _ = _align("caf\u00e9 au lait", passage)
        decomposed, _ = _align("cafe\u0301 au lait", passage)
        self.assertEqual(composed["match"], 1.0)
        self.assertEqual(decomposed["match"], 1.0)


def _flat_page():
    """One row of ink letters, every one the same height and filled in:
    no letter rises above the others or drops below the line, and none
    has a closed bowl. Whatever the text says, the ink shows no tall
    letters and no loops."""
    arr = np.full((160, 640, 3), 255, np.uint8)
    x = 20
    for _word in range(4):
        for _letter in range(3):
            arr[62:88, x : x + 10] = 0
            x += 16
        x += 34
    return arr


PAGE = _flat_page()


def _scores(reading, passage=None):
    """Factor scores for PAGE read as reading, with the passage aligned
    the way the server does it (ppocr-server.py keeps the reading as
    text_as_read, then aligns)."""
    line = _line(reading)
    line.setdefault("text_as_read", line["text"])
    if passage is not None:
        recognizer.align_to_expected([line], passage)
        assert line.get("expected") == passage, "the passage must align"
    result = scoring.build_analysis(PAGE, [copy.deepcopy(line)], {})
    return {r["n"]: r["score"] for r in result.to_dict()["results"]}


class TestPassageCannotRaiseLetterCounts(unittest.TestCase):
    """How many letters were expected may come from the passage; that
    they were written comes only from the ink. Each case reads the same
    ink once without and once with a passage that aligns to it."""

    def assert_not_raised(self, n, reading, passage):
        read = _scores(reading)[n]
        with_passage = _scores(reading, passage)[n]
        self.assertLessEqual(
            with_passage,
            read,
            f"factor {n}: the passage raised {read} to {with_passage}",
        )

    def test_bowls_expected_from_the_passage_need_bowls_in_the_ink(self):
        # Factor 3 (Loop Closure): the passage adds bowl letters to
        # expect; the closed bowls are counted in the ink.
        self.assert_not_raised(3, "we see one moon", "we see the good moon")

    @unittest.expectedFailure
    def test_loop_share_without_enough_bowls_comes_from_the_ink(self):
        # Factor 3 with fewer than three bowl letters falls back to the
        # share of loop letters in the text. With a passage that text is
        # the passage, so its a's count as loops the ink never showed.
        # Expected to fail until scoring counts this share from
        # text_as_read (the PR for #209 describes the change).
        self.assert_not_raised(3, "i im it it", "i am at it")

    @unittest.expectedFailure
    def test_tall_letter_share_comes_from_the_ink(self):
        # Factor 6 (Letter Zones) on a page too short for zone bands is
        # the share of tall letters in the text. With a passage, the t
        # and h of "the" count though the ink has no tall letter.
        # Expected to fail until scoring counts this share from
        # text_as_read (the PR for #209 describes the change).
        self.assert_not_raised(6, "we see one", "we see the")


if __name__ == "__main__":
    unittest.main()
