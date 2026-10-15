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
