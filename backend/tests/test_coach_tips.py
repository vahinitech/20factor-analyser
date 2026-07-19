# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# Tests for the coach-tip engine: the library will hold hundreds of
# tips, so what matters is SELECTION - relevance gating, score-driven
# priority, the report cap, and the 'why' that names the measurement
# behind every chosen tip.

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from coach_tips import MAX_TIPS, TIP_LIBRARY, select_tips  # noqa: E402


def _ctx(scores=None, style=None, finishing=None):
    return {
        "scores": scores or {},
        "style": style,
        "finishing": finishing,
    }


MIXED_STYLE = {
    "available": True,
    "verdict": "mixed",
    "shares": {"cursive": 0.4, "print": 0.3, "mixed": 0.3},
    "advice": "Pick one style and stay with it.",
}

FINISHING = {
    "available": True,
    "wordCount": 5,
    "tip": {
        "id": "finishing-letters",
        "title": "The 10 letters that improve your handwriting",
        "text": "finish with a small upward stroke",
    },
}


def test_library_ids_are_unique():
    ids = [t["id"] for t in TIP_LIBRARY]
    assert len(ids) == len(set(ids))


def test_selection_never_exceeds_the_cap():
    selected, count = select_tips(
        _ctx(scores={13: 2.0}, style=MIXED_STYLE, finishing=FINISHING)
    )
    assert len(selected) <= MAX_TIPS
    assert count == len(TIP_LIBRARY)


def test_mixed_style_outranks_everything():
    selected, _ = select_tips(
        _ctx(scores={13: 2.0}, style=MIXED_STYLE, finishing=FINISHING)
    )
    assert selected[0]["id"] == "one-style-only"


def test_low_speed_score_floats_the_speed_tip():
    weak = select_tips(_ctx(scores={13: 2.0}))[0]
    strong = select_tips(_ctx(scores={13: 9.5}))[0]
    # relevant either way (practice helps everyone), but a weak page
    # ranks it first and says so in the why
    assert weak[0]["id"] == "speed-three-ways"
    assert "2.0/10" in weak[0]["why"]
    assert "general practice habit" in strong[0]["why"]


def test_irrelevant_tips_stay_silent():
    # clean style + no qualifying words: only the speed tip applies
    selected, _ = select_tips(_ctx(scores={13: 8.0}))
    ids = [t["id"] for t in selected]
    assert "one-style-only" not in ids
    assert "finishing-letters" not in ids


def test_every_selected_tip_carries_a_why():
    selected, _ = select_tips(
        _ctx(scores={1: 4.0, 13: 4.0}, finishing=FINISHING)
    )
    assert selected
    for tip in selected:
        assert tip["why"]
        assert tip["title"]
        assert tip["text"]


def test_weak_formation_boosts_the_finishing_tip():
    weak = select_tips(_ctx(scores={1: 2.0, 13: 9.0}, finishing=FINISHING))
    strong = select_tips(
        _ctx(scores={1: 9.5, 3: 9.5, 13: 9.0}, finishing=FINISHING)
    )
    weak_ids = [t["id"] for t in weak[0]]
    strong_ids = [t["id"] for t in strong[0]]
    # weak formation ranks the craft tip above the speed habit
    assert weak_ids.index("finishing-letters") < weak_ids.index(
        "speed-three-ways"
    )
    # strong page keeps it available but below the general habit
    assert strong_ids.index("speed-three-ways") < strong_ids.index(
        "finishing-letters"
    )


def test_a_broken_tip_never_breaks_the_report():
    bad = {
        "id": "explodes",
        "title": "boom",
        "relevant": lambda ctx: True,
        "priority": lambda ctx: 1 / 0,
        "text": lambda ctx: "never",
        "why": lambda ctx: "never",
    }
    TIP_LIBRARY.append(bad)
    try:
        selected, _ = select_tips(_ctx(scores={13: 5.0}))
        assert all(t["id"] != "explodes" for t in selected)
    finally:
        TIP_LIBRARY.remove(bad)


# --- the fun track (graphology) ---------------------------------------------


def _english_ctx(scores=None):
    return _ctx(
        scores=scores or {},
    ) | {"text": "running down nine lanes when nothing went wrong"}


def test_graphology_card_appears_on_english_pages_only():
    selected, _ = select_tips(_english_ctx())
    ids = [t["id"] for t in selected]
    assert "graphology-n" in ids
    card = [t for t in selected if t["id"] == "graphology-n"][0]
    assert card["kind"] == "fun"
    assert "folklore, not science" in card["text"]

    telugu = _ctx() | {"text": "చేతిరాత అందம" * 10}
    ids = [t["id"] for t in select_tips(telugu)[0]]
    assert "graphology-n" not in ids


def test_fun_card_never_displaces_coaching():
    # weakest possible page: every coaching tip fires at high priority
    ctx = _english_ctx(scores={1: 1.0, 13: 1.0, 15: 1.0})
    ctx["style"] = MIXED_STYLE
    ctx["finishing"] = FINISHING
    selected, _ = select_tips(ctx)
    coaching = [t for t in selected if t["kind"] == "coach"]
    fun = [t for t in selected if t["kind"] == "fun"]
    assert len(coaching) == MAX_TIPS  # full coaching allocation intact
    assert len(fun) == 1  # the fun card rides its own slot
    assert selected[-1]["id"] == "graphology-n"  # after the coaching


def test_magic_strokes_floats_on_weak_formation():
    selected, _ = select_tips(_ctx(scores={1: 2.0, 13: 9.0}))
    assert selected[0]["id"] == "magic-strokes"
    assert "circle drills rebuild it" in selected[0]["why"]
