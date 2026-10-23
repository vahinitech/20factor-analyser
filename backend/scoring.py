# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies. Server-side handwriting/print recognition.
# Third-party: PaddleOCR (Apache-2.0). See /THIRD-PARTY-NOTICES.md and backend/README.md
#
# scoring.py — the 20-factor handwriting-analysis model.
#
# Turns OCR lines + layout signals into the FactorScore/SectionScore/
# AnalysisResult dataclasses the /report-python endpoint serializes. Nothing
# here knows about OCR engines, HTTP, or image decoding; it only consumes
# the `lines`/`layout` shapes computer_vision.py and the recognizer produce.
#
# This file is the entry point and holds the factor catalogue (_SECTIONS,
# _FACTOR_META, _FACTOR_EXTRAS) and build_analysis. vahini-web's
# tools/gen-factor-pages.mjs reads _FACTOR_META and _FACTOR_EXTRAS from
# this file as literal assignments, so they stay here, written out. The
# measurements and formulas are in scoring_parts/ (see its __init__.py).

import numpy as np

from server import perf
from report.plain_groups import build_coach_view, build_plain_groups
from scoring_parts import (
    advisory,
    availability,
    dynamics,
    spatial,
    structure,
    style,
)

# Names other modules and tests import from scoring.
from scoring_parts.availability import _MIN_WORD_GAPS, _UNMEASURED_REASONS
from scoring_parts.dynamics import WORD_LETTERS
from scoring_parts.features import (
    BOWL_LETTERS,
    MIN_BOWLS,
    SIZE_OFF,
    _extract_features,
    _ink_features,
    _stroke_features,
    cv2,
)
from scoring_parts.page import (
    _detilted_left_x,
    _group_lines_by_rows,
    _page_tilt_degrees,
)
from scoring_parts.results import AnalysisResult, FactorScore, SectionScore
from scoring_parts.spatial import (
    LETTER_GAP_SCALE,
    WAVE_SCALE,
    WORD_GAP_SCALE,
)
from scoring_parts.stats import _band, _clamp10, _cv, _std, mean
from scoring_parts.structure import BOWL_FULL
from scoring_parts.style import SLANT_SCALE

__all__ = [
    "AnalysisResult",
    "BOWL_FULL",
    "BOWL_LETTERS",
    "FactorScore",
    "LETTER_GAP_SCALE",
    "MIN_BOWLS",
    "SIZE_OFF",
    "SLANT_SCALE",
    "SectionScore",
    "WAVE_SCALE",
    "WORD_GAP_SCALE",
    "WORD_LETTERS",
    "_MIN_WORD_GAPS",
    "_UNMEASURED_REASONS",
    "_band",
    "_clamp10",
    "_cv",
    "_detilted_left_x",
    "_extract_features",
    "_group_lines_by_rows",
    "_ink_features",
    "_page_tilt_degrees",
    "_score_factor_map",
    "_std",
    "_stroke_features",
    "build_analysis",
    "cv2",
    "mean",
]

_SECTIONS = [
    {
        "id": "structure",
        "name": "Structure",
        "weight": 0.30,
        "blurb": "Letter shapes, size & control",
    },
    {
        "id": "spatial",
        "name": "Spatial",
        "weight": 0.30,
        "blurb": "Spacing, baseline & layout",
    },
    {
        "id": "dynamics",
        "name": "Dynamics",
        "weight": 0.20,
        "blurb": "Speed, pressure & flow",
    },
    {
        "id": "style",
        "name": "Style & Readability",
        "weight": 0.20,
        "blurb": "Slant, legibility & neatness",
    },
]

# The overall score out of 100, as points per factor (owner, 23 October
# 2026, #304): only the five measurements that hold up on neat photos of
# real pages count. The other factors are still scored and shown as
# practice findings; each comes back into the overall once it passes the
# neat-page test in docs/history/neat-pages-score-2026-10-23.md. A factor
# not measured on a page is left out and the rest are scaled to 100.
_OVERALL_POINTS = {1: 40, 7: 20, 5: 20, 11: 10, 17: 10}
# Size Consistency counts in the overall only when measured on at least
# this many words (or letter groups): from 3 words its score was 2 or
# more points off the page's own in 20% of draws, from 10 in 8% (owner,
# 23 October 2026, #305). It is still scored and shown below that.
_OVERALL_MIN_SIZE_WORDS = 10

_FACTOR_META = {
    1: ("structure", "Letter Formation Accuracy", "shape regularity proxy"),
    2: ("structure", "Stroke Order Consistency", "stroke order proxy"),
    3: ("structure", "Loop Closure", "loop-bearing character consistency"),
    4: ("structure", "Line Quality (Smoothness)", "stroke smoothness proxy"),
    5: ("structure", "Size Consistency", "letter-height consistency"),
    6: ("structure", "Ascender / Descender Control", "zone balance"),
    7: ("spatial", "Baseline Alignment", "baseline drift"),
    8: ("spatial", "Word Spacing", "inter-word spacing regularity"),
    9: ("spatial", "Letter Spacing", "intra-word spacing proxy"),
    10: ("spatial", "Margin Discipline", "left margin consistency"),
    11: ("spatial", "Line Straightness", "line slope stability"),
    12: ("spatial", "Vertical Alignment", "stroke tilt stability"),
    13: (
        "dynamics",
        "Speed Consistency",
        "speed proxy from stroke regularity",
    ),
    14: (
        "dynamics",
        "Pressure Consistency",
        "pressure proxy from ink variance",
    ),
    15: (
        "dynamics",
        "Stroke Continuity",
        "continuity proxy from word morphology",
    ),
    16: ("dynamics", "Pen Lift Frequency", "pen-lift proxy from segmentation"),
    17: ("style", "Slant Consistency", "slant variation"),
    18: ("style", "Legibility Score", "composite readability"),
    19: ("style", "Character Distinction", "character separability proxy"),
    20: ("style", "Overall Neatness", "layout neatness composite"),
}

# Per-factor rendering extras consumed by the report renderer (report-render.js):
#   ex     — drill group the Exercises page prescribes for this factor
#   target — the "good hand" band shown as the card's Target
#   tip     — the one-line practice suggestion
# These mirror the values that used to live in the browser scorer (factors.js);
# the scoring maths stays in _score_factor_map — this only labels the output so a
# report rendered purely from the server response reads the same as before.
_FACTOR_EXTRAS = {
    1: (
        "round",
        "shape dist ≤0.10",
        "Slow block-writing drills for the letters that deviate most (a, o, b rows).",
    ),
    2: (
        "round",
        "edit dist ≤2",
        "Guided stroke-tracing sheets for letters built in the wrong order.",
    ),
    3: (
        "round",
        "≥95% closed",
        "Loop drills — rows of oooo and aaaa keeping every counter closed.",
    ),
    4: (
        "slant",
        "jitter ≤0.5 px",
        "Straight-line and curve control drills — llll then cccc, slowly.",
    ),
    5: (
        "round",
        "height CV ≤0.12",
        "Write inside two guide-lines so every letter reaches the same height.",
    ),
    6: (
        "round",
        "ratio err ≤0.15",
        "Tall–short pattern drills (bl bl bl) to train ascenders and descenders.",
    ),
    7: (
        "frame",
        "RMS ≤0.08 x-h",
        "Underline / baseline tracing on ruled sheets.",
    ),
    8: (
        "rhythm",
        "≈1.0 x-h, CV ≤0.25",
        "“word␣␣word” spacing drill — one finger gap between words.",
    ),
    9: (
        "rhythm",
        "gap CV ≤0.30",
        "Spaced-letter slow writing — a matchstick gap between letters.",
    ),
    10: (
        "frame",
        "left CV ≤0.05",
        "Margin-box writing — keep an even left edge down the page.",
    ),
    11: (
        "frame",
        "drift ≤1°",
        "Ruled-sheet practice; pause at the right margin to reset to the line.",
    ),
    12: (
        "slant",
        "tilt CV ≤0.20",
        "Straight-stroke drills — l l l l kept upright.",
    ),
    13: (
        "wave",
        "velocity CV ≤0.20",
        "Slow-writing timing drill; write to a steady 1-2-3 count.",
    ),
    14: (
        "wave",
        "CV ≤0.20",
        "Same-pressure line drills; keep one steady, relaxed force.",
    ),
    15: (
        "rhythm",
        "0 unintended breaks",
        "Cursive joining practice — connect letters within a word.",
    ),
    16: (
        "rhythm",
        "≤0.3 lifts/char",
        "Continuous-word writing without lifting mid-word.",
    ),
    17: (
        "slant",
        "angle CV low",
        "Slant rails — rows of / at one steady angle, then \\.",
    ),
    18: (
        "round",
        "even & clear",
        "Lift your two lowest factors first — legibility rises with them.",
    ),
    19: (
        "round",
        "clear letter pairs",
        "Practise easily-confused pairs side by side until each is unmistakable.",
    ),
    20: (
        "frame",
        "weighted variance",
        "Keep the page tidy — even size, even spacing, straight lines.",
    ),
}


def _score_factor_map(fx):
    """The 20 factor scores by number, section by section in factor
    order: Style last, since Legibility and Neatness blend the others."""
    s = {}
    structure.add_scores(fx, s)
    spatial.add_scores(fx, s)
    dynamics.add_scores(fx, s)
    style.add_scores(fx, s)
    return s


# The features each formula reads, reported in its scoring_inputs.
_INPUT_FEATURES = {
    1: ("avg_score", "height_cv"),
    2: ("char_w_cv", "avg_score"),
    3: ("bowl_share", "loop_ratio"),
    4: ("width_cv",),
    5: ("size_cv", "words_off_size"),
    6: ("tall_ratio",),
    7: ("line_slope_abs", "words_off_line"),
    8: ("word_gap_spread", "word_gaps_odd", "word_gap_count"),
    9: (
        "letter_gap_spread",
        "letter_gaps_odd",
        "words_spaced_off",
        "char_w_cv",
    ),
    10: ("left_spread",),
    11: ("line_slope_abs", "line_wave"),
    12: ("line_slope_std",),
    13: ("width_cv",),
    14: ("ink_cv",),
    15: ("n_chars", "n_words"),
    16: ("char_w_cv",),
    17: ("slant_std", "line_slope_std"),
    18: (),
    19: ("avg_score", "digits_ratio"),
    20: (),
}


def build_analysis(arr: np.ndarray, lines, layout) -> AnalysisResult:
    if not lines:
        raise ValueError("No handwriting regions available to score")
    with perf.stage("features", lines=len(lines)) as step:
        fx = _extract_features(arr, lines, layout)
        step.size(words=fx.get("n_words"), letters=fx.get("n_chars"))
    with perf.stage("scoring", lines=len(lines)):
        return _analysis(arr, lines, fx)


def _analysis(arr, lines, fx) -> AnalysisResult:
    """The 20 factors, sections and advice from the page's features."""
    scores = _score_factor_map(fx)
    checks = advisory.run_checks(arr, lines)
    zone_based = advisory.apply_zone_score(checks["zones"], scores)
    supplied = availability.page_supplies(
        lines, fx, zone_based, checks["style"]
    )
    basis = _based_on(fx)
    results = [
        _factor_result(n, fx, scores, supplied, basis, checks, zone_based)
        for n in range(1, 21)
    ]
    sections, overall = _section_scores(results, _left_out(fx))
    measured_results = [r for r in results if not r.unmeasured]
    ranked = sorted(measured_results, key=lambda r: float(r.score))
    top_weak = ranked[:3]
    top_strong = sorted(
        measured_results, key=lambda r: float(r.score), reverse=True
    )[:4]
    baseline_drift = advisory.add_baseline_drift(fx, results)
    zone_profile = advisory.zone_profile(checks["zones"], zone_based, scores)

    # Plain-language layer (issue #12) + the coaches' eight-aspect view
    # (issue #21). Presentation only: nothing above rescored.
    plain = build_plain_groups(results)
    coach = build_coach_view(plain)
    coach_tips, tip_pillars = advisory.coach_tips(
        measured_results, checks, lines
    )

    return AnalysisResult(
        results=results,
        sections=sections,
        overall=overall,
        overall_measured=overall,
        measured_count=len(measured_results),
        top_weak=top_weak,
        top_strong=top_strong,
        plain_groups=plain,
        coach_view=coach,
        baseline_drift=baseline_drift,
        zone_profile=zone_profile,
        tbar_profile=advisory.profile(checks["tbars"]),
        style_profile=advisory.profile(checks["style"]),
        coach_tips=coach_tips,
        tip_pillars=tip_pillars,
    )


def _based_on(fx):
    """What each factor's measurement counted, for its basedOn line."""
    return {
        1: f"{fx['n_chars']} letters",
        2: f"{fx['n_words']} words",
        3: f"{fx['n_chars']} letters",
        4: f"{fx['n_lines']} lines",
        5: (
            f"{fx['size_count']} {fx['size_basis']}"
            if fx.get("size_basis") in ("words", "letter groups")
            else f"{fx['n_lines']} lines"
        ),
        6: f"{fx['n_chars']} letters",
        7: f"{fx['n_lines']} lines",
        8: f"{fx['n_words']} words",
        9: f"{fx['n_chars']} letters",
        10: f"{fx['n_lines']} lines",
        11: f"{fx['n_lines']} lines",
        12: f"{fx['n_lines']} lines",
        13: f"{fx['n_lines']} lines",
        14: f"{fx['n_lines']} lines",
        15: f"{fx['n_words']} words",
        16: f"{fx['n_words']} words",
        17: f"{fx['n_lines']} lines",
        18: f"{fx['n_lines']} lines",
        19: f"{fx['n_chars']} letters",
        20: f"{fx['n_lines']} lines",
    }


def _factor_result(n, fx, scores, supplied, basis, checks, zone_based):
    """Factor n as the report shows it: its score, or why it is not
    measured, with its evidence and the inputs its score came from."""
    sec, name, detail = _FACTOR_META[n]
    ex, target, tip = _FACTOR_EXTRAS.get(
        n,
        (
            "round",
            "python-server estimate",
            "Practice this factor with short daily drills and rescan after 3-5 days.",
        ),
    )
    missing_kind = availability.missing_kind(n, fx, supplied)
    if missing_kind is None:
        score = round(float(scores.get(n, 0.0)), 1)
        value = f"{round(score * 10):.0f}%"
        evidence = f"Server-side OCR/layout heuristic based on {detail}."
    else:
        score = 0.0
        value = "Not measured"
        evidence = availability.unmeasured_evidence(missing_kind)
    evidence = advisory.factor_evidence(n, evidence, checks, zone_based)
    if missing_kind is not None:
        scoring_inputs = availability.unmeasured_inputs(missing_kind, fx)
    elif n == 6 and zone_based:
        scoring_inputs = {
            "method": "zone_geometry",
            "profile": checks["zones"],
        }
    else:
        scoring_inputs = {
            "method": "image_heuristic",
            "features": {key: fx[key] for key in _INPUT_FEATURES[n]},
            "component_scores": {
                str(key): scores[key]
                for key in {
                    18: (1, 5, 8, 7),
                    20: (5, 8, 10, 11, 17),
                }.get(n, ())
            },
        }
    return FactorScore(
        n=n,
        sec=sec,
        name=name,
        ex=ex,
        target=target,
        tip=tip,
        score=score,
        score100=int(round(score * 10)),
        band=_band(score),
        value=value,
        evidence=evidence,
        based_on=None if missing_kind else basis.get(n),
        conf=missing_kind or "measured",
        unmeasured=missing_kind is not None,
        unmeasured_reason=_UNMEASURED_REASONS.get(missing_kind),
        unmeasured_kind=missing_kind,
        scoring_inputs=scoring_inputs,
    )


def _left_out(fx):
    """Measured factors the overall leaves out on this page: Size when
    it rests on too few words (_OVERALL_MIN_SIZE_WORDS)."""
    few = (
        fx.get("size_basis") not in ("words", "letter groups")
        or int(fx.get("size_count") or 0) < _OVERALL_MIN_SIZE_WORDS
    )
    return (5,) if few else ()


def _section_scores(results, left_out=()):
    """The four sections and the overall score. A section's score is the
    mean of its measured factors; the overall is the points-weighted mean
    of the measured factors in _OVERALL_POINTS, less those in left_out."""
    sections = []
    for sec_meta in _SECTIONS:
        fs = [r for r in results if r.sec == sec_meta["id"]]
        measured = [r for r in fs if not r.unmeasured]
        avg = mean([r.score for r in measured]) if measured else 0.0
        sections.append(
            SectionScore(
                id=sec_meta["id"],
                name=sec_meta["name"],
                weight=sec_meta["weight"],
                blurb=sec_meta["blurb"],
                factors=fs,
                avg=round(avg, 1) if measured else None,
                avg100=int(round(avg * 10)) if measured else None,
            )
        )

    counted = [
        r
        for r in results
        if r.n in _OVERALL_POINTS and not r.unmeasured and r.n not in left_out
    ]
    if not counted:
        # None of the five on this page (a script whose letters the
        # reader cannot read): the old blend of every measured factor,
        # so a page that has scores still gets a headline.
        return sections, _all_factor_overall(sections)
    total = float(sum(_OVERALL_POINTS[r.n] for r in counted))
    # The serialized weights are each section's share of the overall:
    # the points of its counted factors on this page, out of those
    # counted, 0 for a section with none.
    for section in sections:
        section.weight = round(
            sum(_OVERALL_POINTS[r.n] for r in counted if r.sec == section.id)
            / total,
            4,
        )
    overall = int(
        round(
            sum(_OVERALL_POINTS[r.n] * float(r.score) for r in counted)
            / total
            * 10
        )
    )
    return sections, overall


def _all_factor_overall(sections):
    """The overall before 23 October 2026: the section means weighted by
    _SECTIONS, renormalised over the sections with a measured factor.
    Sets each section's serialized weight to the share it used."""
    live = [s for s in sections if s.avg100 is not None]
    wsum = sum(float(s.weight) for s in live) or 1.0
    for section in sections:
        section.weight = (
            round(float(section.weight) / wsum, 4)
            if section.avg100 is not None
            else 0.0
        )
    return int(
        round(sum(float(s.avg100 or 0) * float(s.weight) for s in live))
    )
