# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# Tests for plain_groups.py: the plain-language layer (issue #12) and the
# coach view / endurance trend (issue #21). The mapping table IS the
# contract between the backend, the report renderer's fallback and the
# website's self-test page, so these tests pin it row by row.

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from plain_groups import (  # noqa: E402
    COACH_EXTRA_ASPECTS,
    PLAIN_GROUPS,
    build_coach_view,
    build_endurance,
    build_plain_groups,
)


def _factor(n, score=8.0, conf="measured", unmeasured=False):
    return {
        "n": n,
        "name": f"Factor {n}",
        "score": score,
        "band": "good",
        "conf": conf,
        "unmeasured": unmeasured,
    }


def _full_results(score=8.0):
    return [_factor(n, score=score) for n in range(1, 21)]


# --- the mapping is total and disjoint -------------------------------------


def test_every_factor_in_exactly_one_group():
    seen = []
    for g in PLAIN_GROUPS:
        seen.extend(g["factors"])
    assert sorted(seen) == list(range(1, 21))


def test_six_groups_with_questions():
    assert len(PLAIN_GROUPS) == 6
    for g in PLAIN_GROUPS:
        assert g["question"].endswith("?")
        assert g["label"]


# --- group aggregation -------------------------------------------------------


def test_group_score_is_mean_of_members():
    results = _full_results(score=6.0)
    for r in results:
        if r["n"] in (5, 6):  # the "Letter sizes" group
            r["score"] = 9.0
    groups = build_plain_groups(results)
    sizes = next(g for g in groups if g["id"] == "sizes")
    assert sizes["score"] == 9.0
    assert sizes["band"] == "strong"
    shapes = next(g for g in groups if g["id"] == "shapes")
    assert shapes["score"] == 6.0
    assert shapes["band"] == "dev"


def test_unmeasured_members_listed_but_not_averaged():
    results = _full_results(score=8.0)
    for r in results:
        if r["n"] == 14:  # pressure needs the pen on some scans
            r["unmeasured"] = True
            r["score"] = 0.0
    groups = build_plain_groups(results)
    pen = next(g for g in groups if g["id"] == "pen")
    assert pen["score"] == 8.0            # the 0.0 never dilutes the mean
    assert pen["measuredCount"] == 4
    member = next(m for m in pen["factors"] if m["n"] == 14)
    assert member["unmeasured"] is True
    assert member["score"] is None        # never a made-up value


def test_estimated_flag_bubbles_up():
    results = _full_results()
    for r in results:
        if r["n"] == 13:
            r["conf"] = "estimated"
    groups = build_plain_groups(results)
    pen = next(g for g in groups if g["id"] == "pen")
    assert pen["estimated"] is True
    shapes = next(g for g in groups if g["id"] == "shapes")
    assert shapes["estimated"] is False


# --- coach view ----------------------------------------------------------------


def test_coach_view_has_eight_rows_six_measurable():
    view = build_coach_view(build_plain_groups(_full_results()))
    assert len(view["rows"]) == 8
    assert sum(1 for r in view["rows"] if r["measurable"]) == 6
    unmeasurable = [r for r in view["rows"] if not r["measurable"]]
    assert {r["id"] for r in unmeasurable} == {"posture", "pages"}
    for r in unmeasurable:
        assert r["score"] is None
        assert r["note"]                  # honest note, never a number


def test_coach_view_total_covers_measured_aspects_only():
    view = build_coach_view(build_plain_groups(_full_results(score=8.0)))
    assert view["measuredOutOf"] == 60    # 6 aspects x 10
    assert view["measuredTotal"] == 48.0


def test_coach_extra_aspects_are_the_protocol_gaps():
    ids = [a["id"] for a in COACH_EXTRA_ASPECTS]
    assert ids == ["posture", "pages"]


# --- endurance -------------------------------------------------------------------


def _pages(*page_scores):
    return [
        build_plain_groups(_full_results(score=s)) for s in page_scores
    ]


def test_endurance_needs_two_pages():
    e = build_endurance(_pages(8.0))
    assert e["available"] is False


def test_endurance_stable_across_pages():
    e = build_endurance(_pages(8.0, 8.1, 7.9))
    assert e["available"] is True
    assert e["overallTrend"] == "stable"
    assert e["worstGroup"] is None


def test_endurance_detects_degradation_and_onset():
    # the coach's case: fine for two pages, falls apart on the third
    e = build_endurance(_pages(8.0, 7.8, 5.5))
    assert e["overallTrend"] in ("drifting", "degrading")
    dropping = [g for g in e["groups"] if g["dropsFromPage"] == 3]
    assert dropping                        # the onset page is named
    assert e["worstGroup"] is not None


def test_endurance_improvement_is_recognised():
    e = build_endurance(_pages(5.0, 6.5, 8.0))
    assert e["overallTrend"] == "improving"
