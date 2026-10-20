# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Graphemes (backend/languages/graphemes.py, #209): the unit a reader
sees as one letter. A Telugu or Devanagari akshara is one unit however
many code points it takes; Latin is one letter per unit.

The expected counts below were written down letter by letter, with each
word split into its aksharas in the comment beside it. A reader of each
script should confirm them before the counts are treated as settled:
a reader of Telugu for the Telugu lines, a reader of Hindi for the Hindi
lines. The strings are written as escapes so that the exact code points
are in the test; the comments show the words as written."""

import os
import sys
import unicodedata
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
sys.path.insert(0, SERVER_DIR)

from languages import graphemes  # noqa: E402

# నేను తెలుగులో రాస్తాను ("I write in Telugu"):
# నే ను | తె లు గు లో | రా స్తా ను = 2 + 4 + 3 = 9
TELUGU_LINE = (
    "\u0c28\u0c47\u0c28\u0c41 "
    "\u0c24\u0c46\u0c32\u0c41\u0c17\u0c41\u0c32\u0c4b "
    "\u0c30\u0c3e\u0c38\u0c4d\u0c24\u0c3e\u0c28\u0c41"
)
TELUGU_LINE_COUNT = 9

# मैं हिंदी में लिखता हूँ ("I write in Hindi"):
# मैं | हिं दी | में | लि ख ता | हूँ = 1 + 2 + 1 + 3 + 1 = 8
HINDI_LINE = (
    "\u092e\u0948\u0902 "
    "\u0939\u093f\u0902\u0926\u0940 "
    "\u092e\u0947\u0902 "
    "\u0932\u093f\u0916\u0924\u093e "
    "\u0939\u0942\u0901"
)
HINDI_LINE_COUNT = 8

# పిల్లి ("cat"): పి ల్లి
PILLI = "\u0c2a\u0c3f\u0c32\u0c4d\u0c32\u0c3f"
# లక్ష్మి: ల క్ష్మి (two viramas, three consonants, one akshara)
LAKSHMI = "\u0c32\u0c15\u0c4d\u0c37\u0c4d\u0c2e\u0c3f"
# स्त्री ("woman"): one akshara, स्त्री
STRI = "\u0938\u094d\u0924\u094d\u0930\u0940"
# क्षत्रिय: क्ष त्रि य
KSHATRIYA = "\u0915\u094d\u0937\u0924\u094d\u0930\u093f\u092f"


class TestAksharas(unittest.TestCase):
    def test_a_telugu_line(self):
        self.assertEqual(graphemes.count(TELUGU_LINE), TELUGU_LINE_COUNT)

    def test_a_hindi_line(self):
        self.assertEqual(graphemes.count(HINDI_LINE), HINDI_LINE_COUNT)

    def test_conjuncts_stay_one_unit(self):
        self.assertEqual(
            graphemes.split(PILLI),
            ["\u0c2a\u0c3f", "\u0c32\u0c4d\u0c32\u0c3f"],
        )
        self.assertEqual(graphemes.count(LAKSHMI), 2)
        self.assertEqual(graphemes.split(STRI), [STRI])
        self.assertEqual(graphemes.count(KSHATRIYA), 3)

    def test_units_put_back_together_are_the_text(self):
        for text in (TELUGU_LINE, HINDI_LINE, PILLI, "Hello, world"):
            self.assertEqual("".join(graphemes.split(text)), text)

    def test_a_vowel_sign_belongs_to_its_letter(self):
        # పాలు and పాల differ by the u sign on the last letter only.
        self.assertEqual(
            graphemes.split("\u0c2a\u0c3e\u0c32\u0c41"),
            ["\u0c2a\u0c3e", "\u0c32\u0c41"],
        )
        self.assertEqual(
            graphemes.split("\u0c2a\u0c3e\u0c32"), ["\u0c2a\u0c3e", "\u0c32"]
        )

    def test_a_zero_width_non_joiner_stops_the_conjunct(self):
        # ka, virama, zero width non-joiner, ssa: the writer asked for ka
        # with its virama shown, not the conjunct.
        self.assertEqual(
            graphemes.split("\u0c15\u0c4d\u200c\u0c37"),
            ["\u0c15\u0c4d\u200c", "\u0c37"],
        )

    def test_a_zero_width_joiner_keeps_it(self):
        self.assertEqual(graphemes.count("\u0915\u094d\u200d\u0937"), 1)

    def test_a_virama_does_not_join_two_scripts(self):
        self.assertEqual(graphemes.count("\u0c15\u0c4d\u0915"), 2)


class TestOtherScripts(unittest.TestCase):
    def test_latin_is_one_unit_per_character(self):
        text = "The quick brown fox, 42."
        self.assertEqual(graphemes.split(text), list(text))

    def test_a_decomposed_accent_is_one_unit(self):
        self.assertEqual(
            graphemes.split("cafe\u0301"), list("caf") + ["e\u0301"]
        )
        self.assertEqual(
            graphemes.count(unicodedata.normalize("NFC", "cafe\u0301")), 4
        )

    def test_cr_lf_is_one_unit_and_controls_stand_alone(self):
        self.assertEqual(graphemes.split("a\r\nb"), ["a", "\r\n", "b"])
        self.assertEqual(graphemes.split("a\t\u0301"), ["a", "\t", "\u0301"])

    def test_hangul_jamo_make_one_syllable(self):
        self.assertEqual(graphemes.count("\u1112\u1161\u11ab"), 1)
        self.assertEqual(graphemes.count("\ud55c\uae00"), 2)

    def test_flags_pair_up(self):
        india = "\U0001f1ee\U0001f1f3"
        self.assertEqual(graphemes.split(india + india), [india, india])

    def test_empty_and_none(self):
        self.assertEqual(graphemes.split(""), [])
        self.assertEqual(graphemes.split(None), [])
        self.assertEqual(graphemes.count("   "), 0)


if __name__ == "__main__":
    unittest.main()
