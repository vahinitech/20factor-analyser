# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# availability.py - which factors this page cannot measure, and the
# "Not measured" wording, reason and scoring_inputs each one reports.
# What each factor needs lives in factor_needs.py (#207); this adds the
# two rules it does not hold: Word Spacing's three gaps and Margin
# Discipline's three line starts.

from scoring_parts import needs as factor_needs

_MIN_WORD_GAPS = 3
# Why a factor is not measured, by the kind its missing need gives
# (factor_needs.py).
_UNMEASURED_REASONS = {
    "imu": "Requires time-series data from the sensor pen.",
    "ocr": "Requires recognised text from the page.",
    "insufficient": "Needs at least three measurable word gaps.",
    "script": "Reads English letters; not measured on this script.",
    # Joined cursive (#277): the reason code is the scoring_inputs
    # method, letters_joined. Words for families wait for the owner's
    # approval (docs/12-report-rules.md), so none are given yet.
    "joined": None,
}
# Margin Discipline's own wording for "insufficient" (#201).
_FEW_STARTS_REASON = "Needs at least three lines starting at the margin."
_FEW_STARTS_EVIDENCE = (
    "Fewer than three lines start at the left margin on this page."
)
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
    "insufficient", "script" or "joined"), or None when it is
    measured."""
    # The one check (factor_needs.py): which need, if any, this page
    # did not supply for this factor.
    lacking = factor_needs.missing_kind(n, supplied)
    if lacking is not None:
        return lacking
    if n == 8 and fx.get("word_gap_count", 0) < _MIN_WORD_GAPS:
        return "insufficient"
    if n == 10 and fx.get("left_spread", 0.0) is None:
        return "insufficient"
    return None


def unmeasured_reason(kind, n=None):
    if kind == "insufficient" and n == 10:
        return _FEW_STARTS_REASON
    return _UNMEASURED_REASONS.get(kind)


def unmeasured_evidence(kind, n=None):
    if kind == "insufficient" and n == 10:
        return _FEW_STARTS_EVIDENCE
    return _UNMEASURED_EVIDENCE.get(kind) or ""


def unmeasured_inputs(kind, fx, n=None):
    """The scoring_inputs an unmeasured factor reports."""
    if kind == "imu":
        return {"method": "sensor_required", "features": {}}
    if kind == "ocr":
        return {"method": "recognition_required", "features": {}}
    if kind == "script":
        return {
            "method": "script_not_supported",
            "features": {"latin_letters": 0},
        }
    if kind == "joined":
        return {"method": "letters_joined", "features": {"style": "cursive"}}
    if n == 10:
        return {
            "method": "insufficient_data",
            "features": {"margin_rows": fx.get("margin_rows", 0)},
        }
    return {
        "method": "insufficient_data",
        "features": {"word_gap_count": fx.get("word_gap_count", 0)},
    }
