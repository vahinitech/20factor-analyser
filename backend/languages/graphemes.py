# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Split text into graphemes: the units a reader sees as one letter.

Counting code points is wrong for Indic scripts. పిల్లి is six code
points (ప, the i sign, ల, the virama, ల, the i sign) but two written
letters, పి and ల్లి. Design: docs/20-languages.md, section 7 (#209).

``split`` follows Unicode extended grapheme clusters (UAX #29) with the
akshara rule for Telugu and Devanagari: a consonant, then any number of
virama plus consonant, then its vowel signs and other marks, stay one
unit. That rule is GB9c, added in Unicode 15.1. ``unicodedata`` has no
grapheme break property (and Python 3.11 ships Unicode 14), so the rules
are written out here from the general category and code point ranges,
with the standard library only.

Two simplifications, neither of which touches Telugu, Devanagari or
Latin: Prepend characters (a few Arabic and Brahmi signs written before
their letter) start their own unit, and Extended_Pictographic (emoji) is
approximated by the emoji blocks.
"""

import unicodedata

_CR, _LF = "\r", "\n"
_ZWNJ, _ZWJ = "\u200c", "\u200d"

# Consonants and the virama of each script with the akshara rule.
# InCB=Consonant and InCB=Linker in Unicode 15.1 DerivedCoreProperties.
AKSHARA = {
    "Telu": {
        "consonants": ((0x0C15, 0x0C28), (0x0C2A, 0x0C39), (0x0C58, 0x0C5A)),
        "virama": "\u0c4d",
    },
    "Deva": {
        "consonants": ((0x0915, 0x0939), (0x0958, 0x095F), (0x0978, 0x097F)),
        "virama": "\u094d",
    },
}
_VIRAMAS = {facts["virama"]: script for script, facts in AKSHARA.items()}

# Hangul jamo (GB6 to GB8).
_L = ((0x1100, 0x115F), (0xA960, 0xA97C))
_V = ((0x1160, 0x11A7), (0xD7B0, 0xD7C6))
_T = ((0x11A8, 0x11FF), (0xD7CB, 0xD7FB))
_SYLLABLES = (0xAC00, 0xD7A3)
# Emoji skin tone modifiers extend the emoji before them.
_EMOJI_MODIFIERS = (0x1F3FB, 0x1F3FF)
_REGIONAL = (0x1F1E6, 0x1F1FF)
_PICTOGRAPHIC = ((0x2600, 0x27BF), (0x1F000, 0x1FAFF))


def _within(cp, ranges):
    return any(lo <= cp <= hi for lo, hi in ranges)


def _consonant_script(ch):
    cp = ord(ch)
    for script, facts in AKSHARA.items():
        if _within(cp, facts["consonants"]):
            return script
    return None


def _hangul(ch):
    cp = ord(ch)
    if _within(cp, _L):
        return "L"
    if _within(cp, _V):
        return "V"
    if _within(cp, _T):
        return "T"
    if _SYLLABLES[0] <= cp <= _SYLLABLES[1]:
        return "LV" if (cp - _SYLLABLES[0]) % 28 == 0 else "LVT"
    return None


def _control(ch):
    if ch in (_ZWNJ, _ZWJ):
        return False
    return unicodedata.category(ch) in ("Cc", "Zl", "Zp", "Cf")


def _extends(ch):
    """True for a character that never starts a unit of its own: marks,
    the joiners and emoji modifiers (GB9, GB9a)."""
    return (
        unicodedata.category(ch).startswith("M")
        or ch in (_ZWNJ, _ZWJ)
        or _within(ord(ch), (_EMOJI_MODIFIERS,))
    )


_HANGUL_JOINS = {
    "L": ("L", "V", "LV", "LVT"),
    "V": ("V", "T"),
    "LV": ("V", "T"),
    "T": ("T",),
    "LVT": ("T",),
}


class _Cluster:
    """The state of the unit being built."""

    def __init__(self, first):
        self.chars = [first]
        self.hangul = _hangul(first)
        # The script whose consonant anchors this unit, and whether a
        # virama has come since its last consonant (GB9c).
        self.akshara = _consonant_script(first)
        self.linked = False
        self.pictographic = _within(ord(first), _PICTOGRAPHIC)
        self.zwj_after_picture = False
        self.regional = 1 if _within(ord(first), (_REGIONAL,)) else 0

    def joins(self, ch):
        """True when ch belongs to this unit, not the start of the next."""
        prev = self.chars[-1]
        if prev == _CR:
            return ch == _LF
        if _control(prev) or _control(ch):
            return False
        if self.hangul and _hangul(ch) in _HANGUL_JOINS[self.hangul]:
            return True
        if _extends(ch):
            return True
        if self.akshara and self.linked:
            return _consonant_script(ch) == self.akshara
        # An emoji joined to the one before by a zero width joiner (GB11),
        # and the second of a pair of regional indicators: a flag (GB12).
        cp = ord(ch)
        emoji = self.zwj_after_picture and _within(cp, _PICTOGRAPHIC)
        flag = self.regional == 1 and _within(cp, (_REGIONAL,))
        return emoji or flag

    def add(self, ch):
        self.chars.append(ch)
        hangul = _hangul(ch)
        self.hangul = hangul if self.hangul and hangul else None
        if _within(ord(ch), (_REGIONAL,)):
            self.regional += 1
        if self.akshara:
            if _consonant_script(ch) == self.akshara:
                self.linked = False
            elif _VIRAMAS.get(ch) == self.akshara:
                self.linked = True
            elif ch == _ZWJ or unicodedata.category(ch) == "Mn":
                pass  # a nukta or a joiner keeps the link
            else:
                self.linked = False
        if _within(ord(ch), _PICTOGRAPHIC):
            self.pictographic = True
            self.zwj_after_picture = False
        elif ch == _ZWJ:
            self.zwj_after_picture = self.pictographic
        elif not _extends(ch):
            self.zwj_after_picture = False


def split(text):
    """The graphemes of text, in order, as strings. Spaces are units too;
    nothing is normalised here (callers that compare text apply NFC
    first)."""
    units = []
    cluster = None
    for ch in str(text or ""):
        if cluster is not None and cluster.joins(ch):
            cluster.add(ch)
            continue
        if cluster is not None:
            units.append("".join(cluster.chars))
        cluster = _Cluster(ch)
    if cluster is not None:
        units.append("".join(cluster.chars))
    return units


def count(text):
    """How many graphemes text holds, spaces left out."""
    return sum(1 for unit in split(text) if not unit.isspace())
