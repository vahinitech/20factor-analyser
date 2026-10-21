# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# availability.py - which factors this page cannot measure, and the
# "Not measured" wording, reason and scoring_inputs each one reports.
# What each factor needs lives in factor_needs.py (#207); this adds the
# one rule it does not hold, Word Spacing's three gaps.

import factor_needs

_MIN_WORD_GAPS = 3
# A page whose rows were found from the ink (ink_geometry.py: a language
# whose letters the reader cannot read yet) shows its layout only: size,
# baseline, word spacing, margin, line straightness and neatness. The
# factors that read letters, and the line-band stand-ins for stroke
# smoothness (4) and lean (12), wait for that language's reader.
INK_LAYOUT = (5, 7, 8, 10, 11, 20)
# Why a factor is not measured, by the kind its missing need gives
# (factor_needs.py).
_UNMEASURED_REASONS = {
    "imu": "Requires time-series data from the sensor pen.",
    "ocr": "Requires recognised text from the page.",
    "insufficient": "Needs at least three measurable word gaps.",
    "script": "Reads English letters; not measured on this script.",
    "letters_later": "Reads the letters; this language's are not read yet.",
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


def page_supplies(lines, fx, zone_based):
    """The needs this page supplied (factor_needs.page_supplies)."""
    # Lines from computer_vision.fallback_line_regions() (no OCR engine
    # produced any line) carry empty text, a placeholder 0.0 confidence
    # and level rectangles. Factors that read those inputs would publish
    # 0.0 for letter formation and a perfect 10.0 for line angle that the
    # page never produced, so they are reported as not measured instead.
    return factor_needs.page_supplies(
        lines, fx.get("latin_letters", 0), zone_based
    )


def missing_kind(n, fx, supplied):
    """Why factor n is not measured on this page ("imu", "ocr",
    "insufficient", "script" or "letters_later"), or None when it is
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
    return None


def unmeasured_evidence(kind):
    return _UNMEASURED_EVIDENCE[kind]


def unmeasured_inputs(kind, fx):
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
    return {
        "method": "insufficient_data",
        "features": {"word_gap_count": fx.get("word_gap_count", 0)},
    }
