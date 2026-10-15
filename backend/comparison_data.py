# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Facts a before/after comparison needs, taken from one scan's payload.

The paid comparison (20factor-analyser-pro) sets two saved version-2
reports side by side. It needs more than the factor scores: the section
scores the engine already computes, and facts that say whether two pages
can be compared at all. This module only reads what the scorer and the
recogniser produced; it measures nothing new and stores nothing.
docs/17-comparison-data.md explains each field.
"""

import math
import re

# Letters by Unicode block. A page is one script when at least
# SCRIPT_SHARE of its letters are in that block, otherwise "mixed".
SCRIPTS = (
    ("latin", re.compile(r"[A-Za-z\u00C0-\u024F]")),
    ("telugu", re.compile(r"[\u0C00-\u0C7F]")),
    ("devanagari", re.compile(r"[\u0900-\u097F]")),
)
SCRIPT_SHARE = 0.9


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def section_scores(analysis):
    """The four section scores exactly as scoring.build_analysis made
    them: the mean of each section's measured factors (0-10, one
    decimal), and the weight the overall score actually used. A section
    with no measured factor (Dynamics from a photo) has a null score and
    weight 0. Uses every factor, so only Pro reports carry it."""
    out = []
    for section in (analysis or {}).get("sections") or []:
        if not isinstance(section, dict) or "avg" not in section:
            continue
        factors = section.get("factors") or []
        value = _number(section.get("avg"))
        out.append(
            {
                "id": section.get("id"),
                "name": section.get("name"),
                "score": value,
                "normalized": (
                    _number(section.get("avg100"))
                    if value is not None
                    else None
                ),
                "weight": _number(section.get("weight")) or 0,
                "factor_count": len(factors),
                "scored_factor_count": int(section.get("scoredCount") or 0),
            }
        )
    return out


def compact_sections(analysis):
    """The same section scores in the compact report's short form."""
    return [
        {"id": s["id"], "s": s["score"], "w": s["weight"]}
        for s in section_scores(analysis)
    ]


def _script(text):
    counts = {name: len(rx.findall(text)) for name, rx in SCRIPTS}
    total = sum(counts.values())
    if not total:
        return "other"
    name, count = max(counts.items(), key=lambda item: item[1])
    return name if count >= SCRIPT_SHARE * total else "mixed"


def comparability(payload):
    """Facts that say whether two pages can be compared: how much was
    written, in which script, and whether print was found on the page
    and left out. Counts come from the text as the report read it (a
    copied passage's words when the page was matched to one); with
    nothing read they are null. No text, identifier or personal data."""
    analysis = (payload or {}).get("analysis") or {}
    recognition = analysis.get("recognition") or {}
    text = str(payload.get("full_text") or "")
    read = recognition.get("level") != "unavailable" and bool(text.strip())
    lines = recognition.get("hand_lines")
    if not isinstance(lines, int) or isinstance(lines, bool):
        lines = len(payload.get("hand_lines") or [])
    printed = recognition.get("printed_lines")
    if not isinstance(printed, int) or isinstance(printed, bool):
        printed = 0
    return {
        "lines": lines,
        "words": len(text.split()) if read else None,
        "characters": (sum(not c.isspace() for c in text) if read else None),
        "script": _script(text) if read else None,
        "languages": sorted(
            {
                lang
                for lang in payload.get("rec_langs") or []
                if isinstance(lang, str) and lang
            }
        ),
        "printed_lines": printed,
        "page": "handwriting_with_print" if printed else "handwriting",
        "reading": recognition.get("level"),
        "passage_aligned": recognition.get("passage_aligned") is True,
    }
