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

Two tracks share the registry, split by ``kind``:

* ``"coach"`` (default) - real coaching, competes for the report's few
  coaching slots.
* ``"fun"``   - entertainment cards (old-school graphology lore),
  clearly labelled, English-gated, never using or touching a score,
  and selected on their OWN single slot so fun can never displace
  coaching. The disclaimer lives inside the card text itself.

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


def _latin_share(ctx):
    text = str(ctx.get("text", "") or "")
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    latin = sum(1 for c in letters if c.isascii())
    return latin / float(len(letters))


def _count_letter(ctx, letter):
    return str(ctx.get("text", "") or "").lower().count(letter)


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
    {
        "id": "magic-strokes",
        "title": "Two magic strokes behind every Indic script",
        # The letterforms of Telugu, Hindi, Tamil, Kannada and English
        # are all built from two circular strokes; drilling both
        # directions rebuilds the basic hand skill. Floats up when
        # Letter Formation (F1) or Smoothness-adjacent Stroke
        # Continuity (F15) is weak.
        "relevant": lambda ctx: True,
        "priority": lambda ctx: 2.0
        + (10.0 - min(_score(ctx, 1), _score(ctx, 15))) * 0.5,
        "text": lambda ctx: (
            "Telugu, Hindi, Tamil, Kannada and English letters are all "
            "built from just two magic strokes: an anticlockwise circle "
            "and a clockwise circle. When your hand is comfortable in "
            "both directions, every letterform gets easier. Practise "
            "anticlockwise circles, then clockwise; combine them into a "
            "capital S and a number 8; then make spring-coil strokes in "
            "each direction. Two to three minutes a day is enough to "
            "rebuild the basic hand skill."
        ),
        "why": lambda ctx: (
            "shown because Letter Formation scored "
            f"{_score(ctx, 1):.1f}/10 - circle drills rebuild it"
            if _score(ctx, 1) < 7.0
            else "shown as a daily warm-up habit for every script"
        ),
    },
    {
        "id": "graphology-n",
        "kind": "fun",
        "title": "Just for fun: what an old graphologist would read "
        "in your letter n",
        # Entertainment only: English pages with enough n's. Never
        # score-driven, never score-affecting; the honesty note is in
        # the card itself.
        "relevant": lambda ctx: _latin_share(ctx) >= 0.9
        and _count_letter(ctx, "n") >= 5,
        "priority": lambda ctx: 1.0,
        "text": lambda ctx: (
            "Old-school graphology claimed the letter n shows how you "
            "decide: sharp, pointed n's were read as a quick, decisive "
            "thinker; flat-topped or rounded n's as someone who "
            "gathers every fact before choosing. A fun mirror to hold "
            "up to your page - and only that: graphology is folklore, "
            "not science. None of your scores use it; the 20 factors "
            "measure the writing, never the writer. Enjoy it like a "
            "fortune cookie."
        ),
        "why": lambda ctx: (
            f"your page has {_count_letter(ctx, 'n')} letter n's - "
            "this card is for curiosity, not coaching"
        ),
    },
]


def select_tips(ctx, max_tips=MAX_TIPS):
    """Rank the relevant tips for this page, return the top few.

    Returns (selected, library_count): selected is a list of dicts
    {id, title, text, why}, at most max_tips long, highest priority
    first; library_count is the size of the whole registry so callers
    can say how much more coaching exists beyond the page."""
    coaching, fun = [], []
    for tip in TIP_LIBRARY:
        try:
            if not tip["relevant"](ctx):
                continue
            entry = (
                float(tip["priority"](ctx)),
                {
                    "id": tip["id"],
                    "kind": tip.get("kind", "coach"),
                    "title": tip["title"],
                    "text": tip["text"](ctx),
                    "why": tip["why"](ctx),
                },
            )
            if entry[1]["kind"] == "fun":
                fun.append(entry)
            else:
                coaching.append(entry)
        except Exception:
            continue  # a broken tip must never break the report
    coaching.sort(key=lambda pair: -pair[0])
    fun.sort(key=lambda pair: -pair[0])
    selected = [t for _, t in coaching[:max_tips]]
    # at most ONE fun card, after the coaching - it never displaces one
    selected.extend(t for _, t in fun[:1])
    return selected, len(TIP_LIBRARY)
