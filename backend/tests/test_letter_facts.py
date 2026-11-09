# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""No scoring module writes out its own letter facts (#206).

Which letters close a loop, rise above the line or count as Latin live in
the language packs (backend/languages). A module that writes a letter
list, [A-Za-z], a Unicode script range or isascii() decides for itself
what a script is, and the next language then needs a set of exceptions
(docs/20-languages.md, section 1). This test reads the source of each
scoring module and fails on any of them.

recognizer.py and ocr_backends.py still pick a reader by script range;
they join the list when the recognition registry replaces that (#208).
"""

import ast
import os
import re
import unittest

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCORING_MODULES = (
    "scoring.py",
    "scoring_parts/advisory.py",
    "scoring_parts/availability.py",
    "scoring_parts/dynamics.py",
    "scoring_parts/features.py",
    "scoring_parts/page.py",
    "scoring_parts/results.py",
    "scoring_parts/spatial.py",
    "scoring_parts/stats.py",
    "scoring_parts/structure.py",
    "scoring_parts/style.py",
    "scoring_parts/needs.py",
    "vision/zone_analysis.py",
    "vision/letter_geometry.py",
    "vision/tbar_analysis.py",
    "vision/finishing_letters.py",
    "vision/style_analysis.py",
    "report/coach_tips.py",
    "reading/classify.py",
    "vision/computer_vision.py",
    "reading/line_recovery.py",
)

# Three or more letters standing for a set: "adgqo", [bdfhklt].
LETTERS = re.compile(r"[A-Za-z]{3,}")
# A regex class of three or more letters, digits allowed: [bdfhklt],
# [abdegopq0689].
LETTER_CLASS = re.compile(r"\[(?=(?:[0-9]*[A-Za-z]){3})[A-Za-z0-9]+\]")
# A letter range inside a regex class: [A-Za-z], [a-z0-9].
LETTER_RANGE = re.compile(r"\[[^\]]*[A-Za-z]-[A-Za-z][^\]]*\]")
# A range of characters past ASCII inside a regex class, as decoded
# characters ("[\u0C00-\u0C7F]") or, in a raw string, as escapes.
SCRIPT_RANGE = re.compile(r"\[[^\]]*[^\x00-\x7f]-[^\x00-\x7f][^\]]*\]")
ESCAPE = re.compile(r"\\(u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|N\{)")
ORDER = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)


def _letters(node):
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and bool(LETTERS.fullmatch(node.value))
    )


def _past_ascii(node):
    """One character past ASCII, as in "\u0c00" <= c."""
    value = getattr(node, "value", None)
    return (
        isinstance(node, ast.Constant)
        and isinstance(value, str)
        and len(value) == 1
        and ord(value) > 0x7F
    )


def _code_point(node):
    """A number past ASCII, as in 0x0C00 <= ord(c)."""
    value = getattr(node, "value", None)
    return (
        isinstance(node, ast.Constant)
        and isinstance(value, int)
        and not isinstance(value, bool)
        and value > 0x7F
    )


def _is_ord(node):
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ord"
    )


def _string_facts(node):
    found = []
    if LETTER_RANGE.search(node.value):
        found.append("a letter range such as [A-Za-z]")
    if LETTER_CLASS.search(node.value):
        found.append("a letter list in a regex")
    if SCRIPT_RANGE.search(node.value) or ESCAPE.search(node.value):
        found.append("a Unicode script range")
    return found


def _call_facts(node):
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "isascii":
        return ["isascii()"]
    if (
        isinstance(func, ast.Name)
        and func.id in ("set", "frozenset")
        and node.args
        and _letters(node.args[0])
    ):
        return ["a letter list"]
    return []


def _compare_facts(node):
    found = []
    for op, right in zip(node.ops, node.comparators):
        if isinstance(op, (ast.In, ast.NotIn)) and _letters(right):
            found.append("a letter list")
    sides = [node.left] + list(node.comparators)
    if any(isinstance(op, ORDER) for op in node.ops) and (
        any(_past_ascii(side) for side in sides)
        or (
            any(_is_ord(side) for side in sides)
            and any(_code_point(side) for side in sides)
        )
    ):
        found.append("a Unicode script range")
    return found


def letter_facts(source):
    """(line, what) for each letter fact written into Python source."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            what = _string_facts(node)
        elif isinstance(node, ast.Call):
            what = _call_facts(node)
        elif isinstance(node, ast.Compare):
            what = _compare_facts(node)
        elif isinstance(node, (ast.For, ast.comprehension)):
            what = ["a letter list"] if _letters(node.iter) else []
        else:
            what = []
        if what:
            line = getattr(node, "lineno", None) or node.iter.lineno
            found.extend((line, w) for w in what)
    return sorted(set(found))


class LetterFactsLiveInPacks(unittest.TestCase):
    def test_scoring_modules_ask_the_pack(self):
        for name in SCORING_MODULES:
            with open(os.path.join(BACKEND, name), encoding="utf-8") as f:
                found = letter_facts(f.read())
            with self.subTest(module=name):
                self.assertEqual(
                    found,
                    [],
                    f"{name} writes letter facts; move them to a language "
                    "pack in backend/languages (docs/20-languages.md)",
                )


class TheCheckFindsThem(unittest.TestCase):
    """The patterns this test exists to catch, and code it must allow."""

    def test_finds_letter_facts(self):
        caught = {
            'BOWL = set("abdegopq")': "a letter list",
            'S = frozenset("acemnorsuvwxz")': "a letter list",
            'n = sum(1 for c in "adgqo" if c in t)': "a letter list",
            'ok = c in "aeiou"': "a letter list",
            'R = re.compile(r"[bdfhklt]")': "a letter list in a regex",
            'R = re.compile(r"[abdegopq0689]")': "a letter list in a regex",
            'R = re.compile(r"[A-Za-z]+")': "a letter range such as [A-Za-z]",
            'R = re.compile(r"[a-z0-9]")': "a letter range such as [A-Za-z]",
            "ok = c.isascii() and c.isalpha()": "isascii()",
            'R = re.compile(r"[\\u0C00-\\u0C7F]")': "a Unicode script range",
            'ok = "\\u0c00" <= c <= "\\u0c7f"': "a Unicode script range",
            "ok = 0x0C00 <= ord(c) <= 0x0C7F": "a Unicode script range",
            'T = re.compile("[\\u0C00-\\u0C7F]")': "a Unicode script range",
            'V = r"\\N{TELUGU SIGN VIRAMA}"': "a Unicode script range",
        }
        for source, what in caught.items():
            with self.subTest(source=source):
                self.assertIn(what, [w for _, w in letter_facts(source)])

    def test_allows_pack_lookups_and_plain_text(self):
        allowed = [
            'R = re.compile(PACK.char_class("letter") + "+")',
            'BOWL = PACK.letter_set("bowl")',
            'ok = "rs" in text and c.isalpha()',
            'n = text.lower().count("x")',
            'tip = "Write the t-bar across the stem [shown below]"',
            'R = re.compile(r"[^\\w ]")',
            'R = re.compile(r"[0-9]+[.,][0-9]")',
            'kind = "print" if ratio > 0.8 else "cursive"',
            "big = len(lines) > 0x200 and side >= 2600",
            "ok = ord(c) > 64",
        ]
        for source in allowed:
            with self.subTest(source=source):
                self.assertEqual(letter_facts(source), [])


if __name__ == "__main__":
    unittest.main()
