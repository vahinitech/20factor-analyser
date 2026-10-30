# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Blank what could identify the writer in the text read from a page.

A page often carries the child's name, a phone number, a school or a roll
number. The scores never need them (they measure the ink), so before a
scan's answer is cached or sent back, every place the page's text appears
has them replaced with a plain word in brackets: [name], [phone],
[email], [school], [roll number]. The DPDP Act's section 6(1): process
only the data the purpose needs.

Two passes, because the report also lists the page word by word (the
spelling section): the first finds what identifies someone in the whole
text, the second blanks those words wherever the page's text appears.

What it catches is what a page usually says about its writer: "My name
is ...", "Name: ...", "I am ..." followed by capitalised words, an email
address, a phone number (ten digits or more), "Roll no ..." and a school
name ending in School, Vidyalaya, Vidyalayam, Academy or College. It is
a safety net, not a promise: a name written alone on a line cannot be
told from any other word. The photo itself is never stored
(SECURITY.md)."""

import re

# Keys whose values are the page's own words, wherever they sit in a
# scan's payload: whole text, line text, OCR texts and the spelling and
# grammar tokens (reading/language_check.py).
TEXT_KEYS = frozenset(
    {
        "full_text",
        "text",
        "text_as_read",
        "rec_texts",
        "word",
        "suggestion",
        "meant",
        "expected_text",
    }
)

_CAP = r"[A-Z][a-zA-Z'.-]+"
_NAME = re.compile(
    r"(?:\b[Mm]y\s+name\s+is|\b[Nn]ame\s*[:\-]|\bI\s+am|\bI'm)\s+"
    rf"({_CAP}(?:\s+{_CAP}){{0,2}})"
)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
# Ten or more digits, allowing spaces, dots, dashes and a leading +.
_PHONE = re.compile(r"(?<!\w)\+?\d(?:[\s.-]?\d){9,}(?!\w)")
_ROLL = re.compile(
    r"\b([Rr]oll\s*(?:[Nn]o\.?|[Nn]umber|#)?\s*[:\-]?\s*)([A-Za-z]?\d[\w/-]*)"
)
_SCHOOL = re.compile(
    rf"\b((?:{_CAP}\s+){{1,5}}(?:Public\s+|High\s+|Primary\s+|Model\s+)?"
    r"(?:School|Vidyalaya|Vidyalayam|Academy|College))\b"
)
# Capitalised words after "I am" that are not names.
_NOT_NAMES = frozenset(
    {
        "A",
        "An",
        "The",
        "In",
        "At",
        "On",
        "Not",
        "So",
        "Very",
        "Happy",
        "Sad",
        "Good",
        "Fine",
        "Going",
        "Learning",
        "Writing",
        "From",
    }
)


def _names(text):
    found = set()
    for m in _NAME.finditer(text):
        for word in m.group(1).split():
            word = word.strip(".'-")
            if len(word) > 1 and word not in _NOT_NAMES:
                found.add(word)
    return found


def find(text):
    """What identifies the writer in text: {"names", "schools", "rolls"},
    each a set of the exact strings read."""
    text = text or ""
    return {
        "names": _names(text),
        "schools": {m.group(1) for m in _SCHOOL.finditer(text)},
        "rolls": {m.group(2) for m in _ROLL.finditer(text)},
    }


def _word(text, word, label):
    return re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", label, text)


def blank(text, found=None):
    """text with emails, phone numbers and everything in `found` replaced
    by a word in brackets."""
    if not isinstance(text, str) or not text:
        return text
    found = found if found is not None else find(text)
    out = _EMAIL.sub("[email]", text)
    out = _PHONE.sub("[phone]", out)
    for school in sorted(found["schools"], key=len, reverse=True):
        out = out.replace(school, "[school]")
    out = _ROLL.sub(lambda m: m.group(1) + "[roll number]", out)
    for roll in found["rolls"]:
        out = _word(out, roll, "[roll number]")
    for name in sorted(found["names"], key=len, reverse=True):
        out = _word(out, name, "[name]")
    return out


def _texts(node, out):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in TEXT_KEYS:
                if isinstance(value, str):
                    out.append(value)
                elif isinstance(value, list):
                    out.extend(v for v in value if isinstance(v, str))
            _texts(value, out)
    elif isinstance(node, list):
        for value in node:
            _texts(value, out)


def _blank_node(node, found):
    if isinstance(node, dict):
        return {
            key: (
                blank(value, found)
                if key in TEXT_KEYS and isinstance(value, str)
                else (
                    _blank_list(value, found)
                    if key in TEXT_KEYS and isinstance(value, list)
                    else _blank_node(value, found)
                )
            )
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_blank_node(v, found) for v in node]
    return node


def _blank_list(values, found):
    return [
        blank(v, found) if isinstance(v, str) else _blank_node(v, found)
        for v in values
    ]


def blank_payload(payload):
    """A copy of a scan's payload with what identifies the writer blanked
    in every text it holds. Scores, boxes and counts are untouched."""
    if not isinstance(payload, dict):
        return payload
    texts = []
    _texts(payload, texts)
    return _blank_node(payload, find("\n".join(texts)))
