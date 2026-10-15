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


def _photo_scale(payload):
    """(x, y) from processed-image pixels to the uploaded photo's own
    pixels, or None when the payload does not know the photo's size."""
    sizes = [
        payload.get(k) for k in ("photo_w", "photo_h", "proc_w", "proc_h")
    ]
    if not all(
        isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in sizes
    ):
        return None
    return sizes[0] / sizes[2], sizes[1] / sizes[3]


def _valid(values, count):
    return (
        isinstance(values, (list, tuple))
        and len(values) == count
        and all(_number(v) is not None for v in values)
    )


# What page_measurements drew, by the factor whose score it shows:
# slope -> 7 Baseline Alignment, size band -> 5 Size Consistency, the
# usual starting edge -> 10 Margin Discipline, the hardest line to read
# -> 1 Letter Formation and 19 Character Distinction (both read from the
# reader's confidence, scoring.py).
def _measurement_marks(measurements, box, point):
    out = {}

    def add(numbers, mark):
        for n in numbers:
            out.setdefault(n, []).append(mark)

    def line(numbers, role, points):
        if isinstance(points, list) and len(points) == 2:
            if all(_valid(p, 2) for p in points):
                add(
                    numbers,
                    {
                        "shape": "line",
                        "role": role,
                        "points": [point(p) for p in points],
                    },
                )

    slope = (measurements.get("slope") or {}).get("line") or {}
    line(("7",), "baseline", slope.get("baseline"))
    size = (measurements.get("size") or {}).get("line") or {}
    line(("5",), "baseline", size.get("baseline"))
    line(("5",), "midline", size.get("midline"))
    margin = measurements.get("margin") or {}
    if all(
        _number(margin.get(k)) is not None
        for k in ("usual_x", "top", "bottom")
    ):
        line(
            ("10",),
            "usual_start",
            [
                [margin["usual_x"], margin["top"]],
                [margin["usual_x"], margin["bottom"]],
            ],
        )
        for item in margin.get("off") or []:
            if _valid(item.get("bbox"), 4):
                add(
                    ("10",),
                    {"shape": "box", "role": "look", "box": box(item["bbox"])},
                )
    reading = (measurements.get("reading") or {}).get("line") or {}
    if _valid(reading.get("bbox"), 4):
        add(
            ("1", "19"),
            {
                "shape": "box",
                "role": "hardest_line",
                "box": box(reading["bbox"]),
            },
        )
    line(("1", "19"), "underline", reading.get("underline"))
    for letter in reading.get("letters") or []:
        if _valid(letter.get("bbox"), 4):
            add(
                ("1", "19"),
                {"shape": "box", "role": "letter", "box": box(letter["bbox"])},
            )
    return out


def factor_marks(payload, numbers):
    """Where each factor was measured, in the uploaded photo's pixels:
    {"7": [{"shape": "line", "role": "baseline", "points": [[x, y],
    [x, y]]}, {"shape": "box", "role": "region", "box": [x, y, w, h]},
    ...]}. Built only from the evidence regions, their places and the
    page measurements the scan already made; no image. None when the
    photo's size is unknown (a payload cached before it was recorded)."""
    scale = _photo_scale(payload)
    if scale is None:
        return None
    sx, sy = scale

    def box(b):
        return [
            round(b[0] * sx, 1),
            round(b[1] * sy, 1),
            round(b[2] * sx, 1),
            round(b[3] * sy, 1),
        ]

    def point(p):
        return [round(p[0] * sx, 1), round(p[1] * sy, 1)]

    regions = payload.get("factor_regions") or {}
    measured = _measurement_marks(
        payload.get("measurements") or {}, box, point
    )
    out = {}
    for n in sorted(numbers):
        key = str(n)
        region = regions.get(key)
        marks = []
        if (
            isinstance(region, dict)
            and region.get("status") != "unavailable"
            and _valid(region.get("bbox"), 4)
        ):
            marks.append(
                {"shape": "box", "role": "region", "box": box(region["bbox"])}
            )
            for place in region.get("places") or []:
                if _valid(place.get("bbox"), 4):
                    marks.append(
                        {
                            "shape": "box",
                            "role": place.get("role"),
                            "measure": place.get("measure"),
                            "box": box(place["bbox"]),
                        }
                    )
        out[key] = marks + measured.get(key, [])
    return out


def with_marks(regions, marks):
    """Copies of the evidence regions, each with its factor's marks."""
    out = {}
    for key, region in regions.items():
        if isinstance(region, dict) and marks is not None:
            region = {**region, "marks": marks.get(str(key), [])}
        out[key] = region
    return out
