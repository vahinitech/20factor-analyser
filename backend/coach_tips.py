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
# Each entry: id, title, relevant(ctx), priority(ctx), text(ctx), why(ctx),
# and optional examples(ctx) - short practice words/strokes the report
# renders in a handwriting-style face, so every tip is EXPLAINED with a
# written example, not just described.
# ctx keys: scores {n: score}, style (styleProfile), finishing
# (finishing-letters analysis), text (OCR text). All optional; entries
# must guard.


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


def _distinct_c_family(ctx):
    """How many of the five c-built letters (a d g q o) the page uses."""
    text = str(ctx.get("text", "") or "").lower()
    return sum(1 for c in "adgqo" if c in text)


def _is_cursive_page(ctx):
    s = ctx.get("style")
    return bool(
        s and s.get("available") and s.get("verdict") in ("cursive", "mixed")
    )


def _avg_present(ctx):
    """Average of the scores actually measured (missing page = strong)."""
    scores = [float(v) for v in (ctx.get("scores") or {}).values()]
    return sum(scores) / len(scores) if scores else 10.0


# --- the TIP diagnosis -------------------------------------------------------
# Handwriting is a skill, and skills stand on three legs - the coach's
# acronym: T-echniques, I-nterest, P-ractice. Each tip declares the
# pillar it strengthens, and pillar_summary() reads the measured
# factors to say which leg is short for THIS page. Honesty rule:
# interest cannot be measured from a photograph, and the summary says
# so instead of pretending.

PILLARS = ("technique", "interest", "practice")

# Which measured factors evidence each pillar. Technique = the craft
# of the forms (Letter Formation F1, Consistency F3, Stroke Continuity
# F15, t-bar craft F16); Practice = automaticity under time (Speed
# Consistency F13).
_PILLAR_FACTORS = {"technique": (1, 3, 15, 16), "practice": (13,)}


def pillar_summary(ctx):
    """Diagnose the short TIP leg from the measured factor scores.

    Returns {acronym, focus, pillars:{technique, interest, practice}}.
    Each pillar carries measured (bool) and score (worst measured
    factor of that pillar, or None). focus is the weaker measured
    pillar - technique wins ties, because a technique fault is usually
    the cheapest to fix. Interest is never scored from a photo."""
    scores = ctx.get("scores", {}) or {}
    pillars = {}
    for pillar, ns in _PILLAR_FACTORS.items():
        present = [float(scores[n]) for n in ns if n in scores]
        pillars[pillar] = {
            "measured": bool(present),
            "score": round(min(present), 1) if present else None,
        }
    pillars["interest"] = {
        "measured": False,
        "score": None,
        "note": "not measurable from a photo - only you know this one",
    }
    measured = {
        p: d["score"] for p, d in pillars.items() if d["score"] is not None
    }
    focus = (
        min(measured, key=lambda p: (measured[p], p != "technique"))
        if measured
        else None
    )
    return {
        "acronym": "TIP - Techniques, Interest, Practice",
        "focus": focus,
        "pillars": pillars,
    }


TIP_LIBRARY = [
    {
        "id": "one-style-only",
        "pillar": "technique",
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
        "examples": lambda ctx: [
            "and, the, said - joined every time",
            "and, the, said - printed every time",
        ],
    },
    {
        "id": "finishing-letters",
        "pillar": "technique",
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
        "examples": lambda ctx: [
            "A D H I L M N R T U",
            "sun  hat  pearl  drum",
        ],
    },
    {
        "id": "speed-three-ways",
        "pillar": "practice",
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
        "examples": lambda ctx: [
            "read the whole line - look away - write it",
        ],
    },
    {
        "id": "magic-strokes",
        "pillar": "practice",
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
        "examples": lambda ctx: [
            "o o o   c c c   S   8   spring coils",
        ],
    },
    {
        "id": "letter-x-two-curves",
        "pillar": "technique",
        "title": "The letter x: two curves, not two sticks",
        # Craft tip for pages that actually write x. A stick-built x is
        # the first letter to collapse under speed (toward an n, or a
        # shape from no alphabet), so urgency rises when Letter
        # Formation (F1) is weak - and when Speed Consistency (F13)
        # is, because hurry is exactly what exposes it.
        "relevant": lambda ctx: _latin_share(ctx) >= 0.9
        and _count_letter(ctx, "x") >= 1,
        "priority": lambda ctx: 2.2
        + (10.0 - min(_score(ctx, 1), _score(ctx, 13))) * 0.55,
        "text": lambda ctx: (
            "Most students build a lowercase x from two crossing "
            "sticks. Written slowly it looks fine, but in a hurry the "
            "crossing drifts apart and the x collapses into something "
            "like an n - or a shape from no alphabet at all. Build it "
            "from two curves instead: write a reverse e first, then "
            "without lifting the pen extend into an ordinary e. The "
            "two curves sit back to back and the x appears on its own. "
            "Because the hand never lifts, the shape survives any "
            "speed - and it joins both ways: the letter before flows "
            "into the first curve, and the second curve flows straight "
            "out into the letter after."
        ),
        "why": lambda ctx: (
            "shown because this page writes the letter x "
            f"{_count_letter(ctx, 'x')} time(s)"
            + (
                f" and Letter Formation scored {_score(ctx, 1):.1f}/10"
                if _score(ctx, 1) < 7.0
                else ""
            )
        ),
        "examples": lambda ctx: [
            "x = reverse e + e",
            "box  taxi  exam",
        ],
    },
    {
        "id": "letter-r-vs-s",
        "pillar": "technique",
        "title": "r and s: twins until the finish",
        # In words like Mars the two letters blur together because both
        # start with the same entry stroke. Gated to pages that write
        # r directly next to s - the exact place the confusion shows.
        "relevant": lambda ctx: _latin_share(ctx) >= 0.9
        and "rs" in str(ctx.get("text", "") or "").lower(),
        "priority": lambda ctx: 2.1
        + (10.0 - min(_score(ctx, 1), _score(ctx, 3))) * 0.5,
        "text": lambda ctx: (
            "In words like Mars, r and s often come out looking like "
            "twins - both letters start with the same small entry "
            "stroke, so at speed they blur into each other. The whole "
            "difference is in the finish: for r, bring the stroke down "
            "and stop level with the height of the opening loop. For "
            "s, come down like a backslash and close with a soft curve "
            "at the bottom. Write Mars slowly a few times watching "
            "only those two finishes, and the twins separate for good."
        ),
        "why": lambda ctx: (
            "shown because this page writes r directly before s "
            f"{str(ctx.get('text', '') or '').lower().count('rs')} "
            "time(s) - the exact spot the two letters blur"
        ),
        "examples": lambda ctx: [
            "Mars  cars  verse",
            "r stops high - s slides low",
        ],
    },
    {
        "id": "c-family-rhythm",
        "pillar": "technique",
        "title": "Five letters, one c: the rhythm secret",
        # a, d, g, q and o are all built on the same c. Identical c's
        # across them read as rhythm; varied c's unsettle the word.
        # Gated to pages using at least three of the five.
        "relevant": lambda ctx: _latin_share(ctx) >= 0.9
        and _distinct_c_family(ctx) >= 3,
        "priority": lambda ctx: 2.3
        + (10.0 - min(_score(ctx, 1), _score(ctx, 3))) * 0.6,
        "text": lambda ctx: (
            "Five letters - a, d, g, q and o - are all built on the "
            "same c. When each of them carries an identically shaped "
            "c, the word gains a rhythm the eye reads as beautiful; "
            "when the c inside d is fatter than the c inside a, the "
            "same word looks unsettled. Practise one honest c, then "
            "extend that exact c into a, into d, into g, into q, and "
            "close it into o. Keep the c the same size and shape "
            "across all five and the rhythm takes care of itself."
        ),
        "why": lambda ctx: (
            f"shown because this page uses {_distinct_c_family(ctx)} "
            "of the five c-built letters (a d g q o)"
        ),
        "examples": lambda ctx: [
            "c -> a  d  g  q  o",
            "dog  quad  good",
        ],
    },
    {
        "id": "letter-z-easy-build",
        "pillar": "technique",
        "title": "The easiest lowercase z",
        # The last letter, but not least: gated to pages that write z.
        # Like the x tip, hurry exposes a badly built z, so weak Speed
        # Consistency (F13) raises it alongside weak formation.
        "relevant": lambda ctx: _latin_share(ctx) >= 0.9
        and _count_letter(ctx, "z") >= 1,
        "priority": lambda ctx: 2.0
        + (10.0 - min(_score(ctx, 1), _score(ctx, 13))) * 0.5,
        "text": lambda ctx: (
            "The lowercase z takes more wrong turns than almost any "
            "letter. The easy build: think of the number 3, drawn as "
            "two reverse c curves - make the first one small and "
            "compact, the second a little wider - then finish with a "
            "descending tail that ends the way g, j and y do. On "
            "ruled paper, keep the first curve clear of the line, let "
            "the second reach about halfway into the line below, and "
            "lean the tail slightly left as it closes."
        ),
        "why": lambda ctx: (
            "shown because this page writes the letter z "
            f"{_count_letter(ctx, 'z')} time(s)"
        ),
        "examples": lambda ctx: [
            "z = small 3 + a g-style tail",
            "zoo  size  zigzag",
        ],
    },
    {
        "id": "joining-s-outside",
        "pillar": "technique",
        "title": "Join into s from the outside, never the inside",
        # Cursive-specific: an inside join collapses the s. Gated to
        # pages that actually join their letters; urgency follows
        # Stroke Continuity (F15), the factor joins live in.
        "relevant": lambda ctx: _latin_share(ctx) >= 0.9
        and _is_cursive_page(ctx)
        and _count_letter(ctx, "s") >= 1,
        "priority": lambda ctx: 2.4 + (10.0 - _score(ctx, 15)) * 0.6,
        "text": lambda ctx: (
            "When joining into a lowercase s in cursive, never enter "
            "it from the inside - an inside join collapses the letter "
            "and drags down every word that contains it. Bring the "
            "connector up and over, entering the s from the outside, "
            "and the letter keeps its shape at any speed. Practise "
            "with save and sum: watch only the entry into the s, "
            "nothing else, until the outside entry is automatic."
        ),
        "why": lambda ctx: (
            "shown because this page joins its letters and writes "
            f"{_count_letter(ctx, 's')} s's - the letter that "
            "suffers most from an inside join"
        ),
        "examples": lambda ctx: [
            "save  sum  so",
            "enter the s over the top, not from inside",
        ],
    },
    {
        "id": "no-calligraphy-fonts",
        "pillar": "technique",
        "title": "Handwriting is not calligraphy",
        # General guidance, deliberately low priority: it surfaces on
        # pages with room in the report, and floats a little when
        # Speed Consistency (F13) is weak - fancy letterforms are a
        # common hidden cause of slow, tiring writing.
        "relevant": lambda ctx: True,
        "priority": lambda ctx: 1.6 + (10.0 - _score(ctx, 13)) * 0.3,
        "text": lambda ctx: (
            "Handwriting and calligraphy are different crafts. "
            "Italic, Chancery and Lucida-style lettering looks "
            "beautiful, but used for everyday writing it moves the "
            "effort from the content to the letterforms - the hand "
            "tires quickly, and answers do not finish in the allotted "
            "time. Keep a plain cursive or print hand for daily "
            "writing and exams, where the content is the point, and "
            "save artistic lettering for what it is made for: project "
            "titles, invitations and greeting cards."
        ),
        "why": lambda ctx: (
            "shown because Speed Consistency scored "
            f"{_score(ctx, 13):.1f}/10 - ornate letterforms are a "
            "common hidden cause of slow, tiring writing"
            if _score(ctx, 13) < 7.0
            else "shown as general guidance on choosing a daily hand"
        ),
        "examples": lambda ctx: [
            "daily hand: plain cursive or print",
            "fancy lettering: cards and titles only",
        ],
    },
    {
        "id": "skill-not-subject",
        "pillar": "interest",
        "title": "Handwriting is a skill, not a subject",
        # The TIP mindset card: floats up when the whole page is weak,
        # because a low report reads like a verdict unless someone
        # says out loud that skills are learnable.
        "relevant": lambda ctx: True,
        "priority": lambda ctx: 1.8 + (10.0 - _avg_present(ctx)) * 0.35,
        "text": lambda ctx: (
            "Handwriting is not a school subject - it is a skill, "
            "like cycling or swimming, and anybody at any age can "
            "improve it. Skills stand on three legs, and TIP is the "
            "acronym: T for Techniques (was the method you were "
            "taught actually sound?), I for Interest (the skills you "
            "cared about are the ones you mastered), and P for "
            "Practice (the hours your other skills got and "
            "handwriting did not). When one leg is short, the page "
            "shows it; when all three are justified, the handwriting "
            "comes up to the mark. This report's job is to point at "
            "the short leg."
        ),
        "why": lambda ctx: (
            "shown because the average measured score is "
            f"{_avg_present(ctx):.1f}/10 - a skill gap, never a "
            "talent gap"
            if _avg_present(ctx) < 6.0
            else "shown as the lens for every card in this corner"
        ),
        "examples": lambda ctx: [
            "T techniques   I interest   P practice",
        ],
    },
    {
        "id": "write-every-day",
        "pillar": "practice",
        "title": "Write every day - the oldest rule on the poster",
        # The practice pillar's habit card, paraphrasing the habit
        # rules every classroom writing poster agrees on.
        "relevant": lambda ctx: True,
        "priority": lambda ctx: 1.7 + (10.0 - _score(ctx, 13)) * 0.4,
        "text": lambda ctx: (
            "The oldest rule on every classroom writing poster is the "
            "truest one for handwriting too: if you write every day, "
            "you get better at writing every day. Make it a routine - "
            "the same ten minutes at the same table beats an hour "
            "once a week. Keep a notebook and a spare pen within "
            "reach so the routine never has an excuse, and write "
            "about anything at all: walks, dishes, the day. The "
            "scores in this report move with the pages you fill."
        ),
        "why": lambda ctx: (
            "shown because Speed Consistency scored "
            f"{_score(ctx, 13):.1f}/10 - daily minutes are what "
            "make a hand automatic"
            if _score(ctx, 13) < 7.0
            else "shown as the practice habit behind every skill"
        ),
        "examples": lambda ctx: [
            "ten minutes  same table  every day",
            "notebook + spare pen, always",
        ],
    },
    {
        "id": "orwell-six-rules",
        "pillar": "technique",
        "title": "Orwell's six rules are speed rules for your hand",
        # Word craft meets hand craft: shorter, plainer sentences are
        # literally fewer strokes. English-prose advice, so gated to
        # Latin pages.
        "relevant": lambda ctx: _latin_share(ctx) >= 0.9,
        "priority": lambda ctx: 1.5 + (10.0 - _score(ctx, 13)) * 0.25,
        "text": lambda ctx: (
            "George Orwell's famous rules for writers are also speed "
            "rules for your hand: never use a long word where a short "
            "one will do; if a word can be cut, cut it; prefer the "
            "active voice; skip worn-out figures of speech and "
            "needless jargon - and break any of these rules before "
            "writing something ugly. Every sentence you shorten is "
            "strokes your hand never has to make, so plain wording "
            "shows up on paper as faster, fresher handwriting - "
            "especially against an exam clock."
        ),
        "why": lambda ctx: (
            "shown because Speed Consistency scored "
            f"{_score(ctx, 13):.1f}/10 - shorter words are the "
            "cheapest speed you will ever buy"
            if _score(ctx, 13) < 7.0
            else "shown as word-craft that quietly helps the hand"
        ),
        "examples": lambda ctx: [
            "short words - active voice - cut the extra",
        ],
    },
    {
        "id": "graphology-n",
        "pillar": "interest",
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
        "examples": lambda ctx: [
            "n with sharp peaks - n with round tops",
        ],
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
            card = {
                "id": tip["id"],
                "kind": tip.get("kind", "coach"),
                "pillar": tip.get("pillar", "technique"),
                "title": tip["title"],
                "text": tip["text"](ctx),
                "why": tip["why"](ctx),
            }
            if "examples" in tip:
                # short practice samples the report draws in a
                # handwriting-style face
                card["examples"] = [str(e) for e in tip["examples"](ctx)]
            entry = (float(tip["priority"](ctx)), card)
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
