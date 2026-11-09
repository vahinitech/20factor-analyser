# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# availability.py - which factors this page cannot measure, and the
# "Not measured" wording, reason and scoring_inputs each one reports.
# What each factor needs lives in factor_needs.py (#207); this adds the
# two rules it does not hold: Word Spacing's three gaps, Loop
# Closure's five letters with a bowl and Margin Discipline's three
# line starts.

from scoring_parts import needs as factor_needs

_MIN_WORD_GAPS = 3
# A page whose rows were found from the ink (ink_geometry.py: a language
# whose letters the reader cannot read yet) shows its layout only: size,
# baseline, word spacing, margin, line straightness and neatness. The
# factors that read letters, and the line-band stand-in for lean (12),
# wait for that language's reader.
INK_LAYOUT = (5, 7, 8, 10, 11, 20)
# Loop Closure needs this many letters with a bowl on lines measured in
# the ink (features._stroke_features); with fewer, one open bowl moves
# the score by a fifth or more.
MIN_BOWLS = 5
# The ink-row factors scored from row slopes. A row of fewer than six
# letters has no slope (ink_geometry.MIN_SLOPE_LETTERS): with no row
# measured, line_slope_abs is a stand-in 0.0 and would read as level.
SLOPE_FACTORS = (7, 11)
_NEEDS_SLOPE = "Needs at least one line of six or more letters."
_NO_SLOPE_EVIDENCE = (
    "Every line on this page has fewer than six letters, too few to "
    "show which way the line runs."
)
# Why a factor is not measured, by the kind its missing need gives
# (factor_needs.py).
_UNMEASURED_REASONS = {
    "imu": "Requires time-series data from the sensor pen.",
    "ocr": "Requires recognised text from the page.",
    "insufficient": "Needs at least three measurable word gaps.",
    "script": "Reads English letters; not measured on this script.",
    "letters_later": "Reads the letters; this language's are not read yet.",
    # Joined cursive (#277): the reason code is the scoring_inputs
    # method, letters_joined. Words for families wait for the owner's
    # approval (docs/12-report-rules.md), so none are given yet.
    "joined": None,
}
# Factors whose "insufficient" has its own reason and evidence:
# Loop Closure (#200) and Margin Discipline (#201).
_FACTOR_REASONS = {
    3: f"Needs at least {MIN_BOWLS} letters with a bowl on measured lines.",
    10: "Needs at least three lines starting at the margin.",
    7: _NEEDS_SLOPE,
    11: _NEEDS_SLOPE,
}
_FACTOR_EVIDENCE = {
    3: (
        f"Fewer than {MIN_BOWLS} letters with a bowl (a, b, d, e, g, o, "
        "p, q) were found on lines measured in the ink."
    ),
    10: "Fewer than three lines start at the left margin on this page.",
    7: _NO_SLOPE_EVIDENCE,
    11: _NO_SLOPE_EVIDENCE,
}
# The evidence line an unmeasured factor shows, by kind.
_UNMEASURED_EVIDENCE = {
    "imu": "A still photo cannot measure pen motion or pressure.",
    "script": (
        "This measure reads English letters, and none were "
        "recognised on this page."
    ),
    "insufficient": (
        "Fewer than three gaps between words could be measured on "
        "this page."
    ),
    "ocr": (
        "Text recognition did not read this page, so this factor "
        "could not be measured."
    ),
    "letters_later": (
        "This page was measured from the shape of its writing. Reading "
        "its letters comes next, and this score comes with it."
    ),
}


def page_supplies(lines, fx, zone_based, style=None):
    """The needs this page supplied (factor_needs.page_supplies). style:
    the style check (style_analysis.analyze_style); a page it calls
    cursive has its letters joined."""
    # Lines from computer_vision.fallback_line_regions() (no OCR engine
    # produced any line) carry empty text, a placeholder 0.0 confidence
    # and level rectangles. Factors that read those inputs would publish
    # 0.0 for letter formation and a perfect 10.0 for line angle that the
    # page never produced, so they are reported as not measured instead.
    joined = bool(
        style and style.get("available") and style["verdict"] == "cursive"
    )
    return factor_needs.page_supplies(
        lines, fx.get("latin_letters", 0), zone_based, joined
    )


def missing_kind(n, fx, supplied):
    """Why factor n is not measured on this page ("imu", "ocr",
    "insufficient", "script", "joined" or "letters_later"), or None when it is
    measured."""
    # The one check (factor_needs.py): which need, if any, this page
    # did not supply for this factor.
    lacking = factor_needs.missing_kind(n, supplied)
    if fx.get("ink_rows") and n not in INK_LAYOUT and lacking != "imu":
        return "letters_later"
    if lacking is not None:
        return lacking
    if n == 8 and fx.get("word_gap_count", 0) < _MIN_WORD_GAPS:
        return "insufficient"
    if n == 3 and fx.get("bowl_share") is None:
        return "insufficient"
    if n == 10 and fx.get("left_spread", 0.0) is None:
        return "insufficient"
    if n in SLOPE_FACTORS and fx.get("line_slope_count", 1) == 0:
        return "insufficient"
    return None


# What a photo cannot show, for the Structure factors only the sensor
# pen measures (needs.py, #192); the Dynamics keep the line above.
_PEN_EVIDENCE = {
    2: "A still photo shows the finished letter, not the order its "
    "strokes were made in.",
    4: "At photo size a shaky stroke looks like the letters' own curves, "
    "so smoothness is measured by the sensor pen.",
}


def unmeasured_reason(kind, n=None):
    if kind == "insufficient" and n in _FACTOR_REASONS:
        return _FACTOR_REASONS[n]
    return _UNMEASURED_REASONS.get(kind)


def unmeasured_evidence(kind, n=None):
    if kind == "imu" and n in _PEN_EVIDENCE:
        return _PEN_EVIDENCE[n]
    if kind == "insufficient" and n in _FACTOR_EVIDENCE:
        return _FACTOR_EVIDENCE[n]
    return _UNMEASURED_EVIDENCE.get(kind) or ""


def unmeasured_inputs(kind, fx, n=None):
    """The scoring_inputs an unmeasured factor reports."""
    if kind == "imu":
        return {"method": "sensor_required", "features": {}}
    if kind == "ocr":
        return {"method": "recognition_required", "features": {}}
    if kind == "letters_later":
        return {"method": "reader_coming", "features": {}}
    if kind == "script":
        return {
            "method": "script_not_supported",
            "features": {"latin_letters": 0},
        }
    if kind == "joined":
        return {"method": "letters_joined", "features": {"style": "cursive"}}
    if n == 3:
        return {
            "method": "insufficient_data",
            "features": {"bowl_letters": fx.get("bowl_letters", 0)},
        }
    if n == 10:
        return {
            "method": "insufficient_data",
            "features": {"margin_rows": fx.get("margin_rows", 0)},
        }
    if n in SLOPE_FACTORS:
        return {
            "method": "insufficient_data",
            "features": {"line_slope_count": fx.get("line_slope_count", 0)},
        }
    return {
        "method": "insufficient_data",
        "features": {"word_gap_count": fx.get("word_gap_count", 0)},
    }
