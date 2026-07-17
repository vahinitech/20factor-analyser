# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# plain_groups.py — the plain-language layer over the 20 factors.
#
# One canonical grouping serves three consumers (issues #12 and #21):
#   1. the PDF report's "your writing in plain words" page,
#   2. the coach-view: the eight-aspect self-assessment protocol
#      handwriting coaches use, so a reader's own marks out of 10 are
#      directly comparable with the analyser's,
#   3. the endurance trend across a multi-page assessment.
#
# Design rules (from the accepted proposal on issue #12):
#   - groups are named after what the writer sees on their own page,
#     phrased as a question a teacher would say out loud;
#   - the technical factor names stay attached underneath every group,
#     so every headline still traces to real measurements;
#   - presentation only: the 4 weighted sections in scoring.py keep
#     driving the overall score; this module never rescores anything.
#
# The report renderer mirrors PLAIN_GROUPS in a fallback table
# (frontend/src/report/report-render.js). Change one, change both.

import math

# Every factor number 1..20 appears in exactly one group
# (pinned by backend/tests/test_plain_groups.py).
PLAIN_GROUPS = [
    {
        "id": "shapes",
        "label": "Letter shapes",
        "question": "Are my letters the right shape, and closed where they should be?",
        "factors": [1, 2, 3, 19],
    },
    {
        "id": "sizes",
        "label": "Letter sizes",
        "question": "Are my letters the same size? Do tall letters stand tall and tails hang below?",
        "factors": [5, 6],
    },
    {
        "id": "spaces",
        "label": "Spaces and gaps",
        "question": "Do my words and letters have enough room? Did I leave a margin?",
        "factors": [8, 9, 10],
    },
    {
        "id": "line",
        "label": "Staying on the line",
        "question": "Does my writing sit on the line and stay straight across the page?",
        "factors": [7, 11, 12],
    },
    {
        "id": "pen",
        "label": "Pen control",
        "question": "Are my strokes smooth and steady, not shaky or pressed too hard?",
        "factors": [4, 13, 14, 15, 16],
    },
    {
        "id": "read",
        "label": "Easy to read",
        "question": "Can someone else read my page easily?",
        "factors": [17, 18, 20],
    },
]

# The two aspects of the coaches' eight-question self-test that a single
# scanned page cannot score. They appear in the coach view with an honest
# note instead of a number, never a made-up value.
COACH_EXTRA_ASPECTS = [
    {
        "id": "posture",
        "label": "Posture",
        "question": "How do I sit and hold the pen while writing?",
        "note": "Not visible in a scan. The Vahini pen senses it through pen-angle steadiness.",
    },
    {
        "id": "pages",
        "label": "Page to page",
        "question": "Does my writing stay the same, or change after two or three pages?",
        "note": "Scan 2-3 pages as one assessment to measure this (endurance).",
    },
]

# Must track scoring.py's _band() thresholds.
def _band(score):
    if score >= 8.5:
        return "strong"
    if score >= 7.0:
        return "good"
    if score >= 4.5:
        return "dev"
    return "focus"


def _factor_field(f, key, default=None):
    """Accept both FactorScore objects and their to_dict() form."""
    if isinstance(f, dict):
        return f.get(key, default)
    return getattr(f, key, default)


def build_plain_groups(results):
    """Fold 20 FactorScores into the 6 plain-language groups.

    Presentation-only aggregation: a group's score is the plain mean of
    its member factors' 0-10 scores. Members the scan could not measure
    (unmeasured=True) are left out of the mean but still listed, so the
    small print never hides anything. A group is flagged estimated when
    any member is a proxy rather than a direct measurement.
    """
    by_n = {int(_factor_field(f, "n")): f for f in results}
    groups = []
    for g in PLAIN_GROUPS:
        members = []
        live_scores = []
        estimated = False
        for n in g["factors"]:
            f = by_n.get(n)
            if f is None:
                continue
            unmeasured = bool(_factor_field(f, "unmeasured", False))
            score = float(_factor_field(f, "score", 0.0))
            members.append(
                {
                    "n": n,
                    "name": _factor_field(f, "name", ""),
                    "score": None if unmeasured else round(score, 1),
                    "band": None if unmeasured else _factor_field(f, "band"),
                    "unmeasured": unmeasured,
                }
            )
            if not unmeasured:
                live_scores.append(score)
            if _factor_field(f, "conf", "measured") != "measured":
                estimated = True
        avg = (sum(live_scores) / len(live_scores)) if live_scores else None
        groups.append(
            {
                "id": g["id"],
                "label": g["label"],
                "question": g["question"],
                "score": round(avg, 1) if avg is not None else None,
                "score100": int(round(avg * 10)) if avg is not None else None,
                "band": _band(avg) if avg is not None else None,
                "estimated": estimated,
                "factors": members,
                "measuredCount": len(live_scores),
            }
        )
    return groups


def build_coach_view(plain_groups):
    """The eight-aspect coach protocol: the 6 measured groups plus the
    two aspects a single scan cannot score (posture, page-to-page),
    each carried with its question so a reader's own marks out of 10
    line up row for row with the analyser's."""
    rows = []
    for g in plain_groups:
        rows.append(
            {
                "id": g["id"],
                "label": g["label"],
                "question": g["question"],
                "score": g["score"],
                "band": g["band"],
                "measurable": True,
                "note": "estimated from the photo" if g["estimated"] else None,
            }
        )
    for a in COACH_EXTRA_ASPECTS:
        rows.append(
            {
                "id": a["id"],
                "label": a["label"],
                "question": a["question"],
                "score": None,
                "band": None,
                "measurable": False,
                "note": a["note"],
            }
        )
    measured = [r["score"] for r in rows if r["score"] is not None]
    return {
        "rows": rows,
        # out of 10 per aspect: totals compare with a coach-style
        # self-test summed over the SAME measured aspects only
        "measuredTotal": round(sum(measured), 1) if measured else None,
        "measuredOutOf": 10 * len(measured),
    }


# ---------------------------------------------------------------------------
# Endurance: the coaches' sharpest question, "does the handwriting change
# after two or three pages?" (issue #21). Pure aggregation over per-page
# analyses; the caller scores each page with build_analysis as usual.

# Per-page group-score change (0-10 points per page) that separates the
# trend classes. A whole band is 1.5-2.5 points, so 0.35/page across a
# 3-page test is a visible, real drift.
ENDURANCE_STABLE_LIMIT = 0.35
ENDURANCE_DEGRADE_LIMIT = 0.80


def _slope_per_page(scores):
    """Least-squares slope of score vs page index (points per page)."""
    pts = [(i, s) for i, s in enumerate(scores) if s is not None]
    if len(pts) < 2:
        return 0.0
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    den = sum((p[0] - mx) ** 2 for p in pts)
    if den <= 0:
        return 0.0
    return sum((p[0] - mx) * (p[1] - my) for p in pts) / den


def _classify(slope):
    if slope <= -ENDURANCE_DEGRADE_LIMIT:
        return "degrading"
    if slope <= -ENDURANCE_STABLE_LIMIT:
        return "drifting"
    if slope >= ENDURANCE_STABLE_LIMIT:
        return "improving"
    return "stable"


def build_endurance(page_plain_groups):
    """Trend across a multi-page assessment.

    page_plain_groups: list (one entry per page, in writing order) of
    build_plain_groups() outputs. Returns per-group trends plus an
    overall verdict and, when quality degrades, the page where the drop
    becomes visible (first page more than one point below page 1).
    """
    n_pages = len(page_plain_groups)
    if n_pages < 2:
        return {
            "pages": n_pages,
            "available": False,
            "note": "Endurance needs at least two pages scanned as one assessment.",
        }

    per_group = []
    for gi, meta in enumerate(PLAIN_GROUPS):
        series = [
            page[gi]["score"] if gi < len(page) else None
            for page in page_plain_groups
        ]
        slope = _slope_per_page(series)
        trend = _classify(slope)
        onset = None
        first = next((s for s in series if s is not None), None)
        if first is not None:
            for pi, s in enumerate(series):
                if s is not None and (first - s) > 1.0:
                    onset = pi + 1  # 1-based page number
                    break
        per_group.append(
            {
                "id": meta["id"],
                "label": meta["label"],
                "scores": series,
                "slopePerPage": round(slope, 2),
                "trend": trend,
                "dropsFromPage": onset,
            }
        )

    worst = min(per_group, key=lambda g: g["slopePerPage"])
    overall_slope = _slope_per_page(
        [
            (
                sum(p["score"] for p in page if p["score"] is not None)
                / max(1, sum(1 for p in page if p["score"] is not None))
            )
            for page in page_plain_groups
        ]
    )
    return {
        "pages": n_pages,
        "available": True,
        "overallTrend": _classify(overall_slope),
        "overallSlopePerPage": round(overall_slope, 2),
        "groups": per_group,
        "worstGroup": worst["id"] if worst["trend"] in ("drifting", "degrading") else None,
    }
