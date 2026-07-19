# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The coach-tip engine: a growing tip library, a small report.

There will be hundreds of coaching tips (they arrive lesson by
lesson), and the report already runs many pages - so tips are never
dumped wholesale. Every tip in the registry declares two things:

* ``relevant(ctx)``  - does this tip apply to THIS page at all?
* ``priority(ctx)``  - how urgently does THIS writer need it, driven
  by the measured factor scores (a weak Speed Consistency score makes
  the speed tip float up; a mixed-style verdict makes the one-style
  rule near-mandatory).

``select_tips`` ranks the relevant tips and returns only the top few,
each carrying a plain-language ``why`` naming the measurement that
earned it a slot - the reader always knows a tip was chosen for them,
not pasted for everyone. The rest of the library stays silent until a
page needs it.

Adding a tip = appending one registry entry. Nothing else changes.
"""

MAX_TIPS = 3


def _score(ctx, n, default=10.0):
    """Factor n's score from the context (0..10; missing = strong)."""
    return float(ctx.get("scores", {}).get(n, default))


# --- the library -------------------------------------------------------------
# Each entry: id, title, relevant(ctx), priority(ctx), text(ctx), why(ctx).
# ctx keys: scores {n: score}, style (styleProfile), finishing
# (finishing-letters analysis). All optional; entries must guard.


def _finishing_relevant(ctx):
    f = ctx.get("finishing")
    return bool(f and f.get("available"))


def _finishing_text(ctx):
    return ctx["finishing"]["tip"]["text"]


def _style_relevant(ctx):
    s = ctx.get("style")
    return bool(s and s.get("available") and s.get("verdict") == "mixed")


TIP_LIBRARY = [
    {
        "id": "one-style-only",
        "title": "Cursive or print - never both",
        "relevant": _style_relevant,
        # The coach calls mixing the one real mistake: it must outrank
        # every habit tip whenever it triggers (base above the highest
        # any other tip can reach), sharpened further when Stroke
        # Continuity (F15) is weak.
        "priority": lambda ctx: 15.0 + (10.0 - _score(ctx, 15)) * 0.5,
        "text": lambda ctx: ctx["style"]["advice"],
        "why": lambda ctx: (
            "shown because this page mixes cursive and print "
            f"({int(ctx['style']['shares']['mixed'] * 100)}% of words "
            "switch style)"
        ),
    },
    {
        "id": "finishing-letters",
        "title": "The 10 letters that improve your handwriting",
        "relevant": _finishing_relevant,
        # A craft tip: floats up when Letter Formation (F1) or letter
        # consistency (F3) is weak; on a strong page it ranks below
        # the general practice habits.
        "priority": lambda ctx: 2.5
        + (10.0 - min(_score(ctx, 1), _score(ctx, 3))) * 0.6,
        "text": _finishing_text,
        "why": lambda ctx: (
            "shown because this page has "
            f"{ctx['finishing']['wordCount']} words ending in the ten "
            "finishing letters"
        ),
    },
    {
        "id": "speed-three-ways",
        "title": "Improve your writing speed",
        # Speed practice applies to every writer; urgency scales with
        # the measured Speed Consistency score (F13).
        "relevant": lambda ctx: True,
        "priority": lambda ctx: 3.0 + (10.0 - _score(ctx, 13)) * 0.9,
        "text": lambda ctx: (
            "Three habits that build real speed. One: when copying or "
            "making notes, do not write word-by-word with your eyes on "
            "the source - read the whole sentence, then write it from "
            "memory without looking back; this trains the mind-to-"
            "fingers link that speed comes from. Two: set a timer for "
            "5, 10 or 15 minutes and write as fast as you can for just "
            "that window - short daily sprints make speed a habit. "
            "Three: read as many books as you can; words you have seen "
            "often live in your mind as pictures, and a word you can "
            "picture is a word your hand writes without hesitating."
        ),
        "why": lambda ctx: (
            "shown because Speed Consistency scored "
            f"{_score(ctx, 13):.1f}/10 on this page"
            if _score(ctx, 13) < 7.0
            else "shown as a general practice habit for every writer"
        ),
    },
]


def select_tips(ctx, max_tips=MAX_TIPS):
    """Rank the relevant tips for this page, return the top few.

    Returns (selected, library_count): selected is a list of dicts
    {id, title, text, why}, at most max_tips long, highest priority
    first; library_count is the size of the whole registry so callers
    can say how much more coaching exists beyond the page."""
    ranked = []
    for tip in TIP_LIBRARY:
        try:
            if not tip["relevant"](ctx):
                continue
            ranked.append(
                (
                    float(tip["priority"](ctx)),
                    {
                        "id": tip["id"],
                        "title": tip["title"],
                        "text": tip["text"](ctx),
                        "why": tip["why"](ctx),
                    },
                )
            )
        except Exception:
            continue  # a broken tip must never break the report
    ranked.sort(key=lambda pair: -pair[0])
    return [t for _, t in ranked[:max_tips]], len(TIP_LIBRARY)
