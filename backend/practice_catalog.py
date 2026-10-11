# SPDX-License-Identifier: AGPL-3.0-only
# pylint: disable=too-many-lines
# (data module: the exercises and tips are most of it)
"""The practice catalogue: exercises and tips for every factor.

Practice is data, not renderer code (docs/PRACTICE-FRAMEWORK.md, approved
by the owner on 2026-10-11 in #122). Each factor is one development area
with exercises ordered by level and short tips. The score band sets how
many tries a day (DOSAGE), and the tier sets how many skills, exercises
and tips one report shows (TIERS). The versioned factor catalogue
(``compact_reports.dictionary``) serves this module's content, and
``/api/v2/me`` returns the visitor's tier numbers from ``limits``.

Everything here is checked when the module is imported, so a bad entry
stops the server and CI instead of reaching a child's report.

Only the standard library is used: ``frontend/build_bundle.py`` imports
this module to give the browser the same catalogue for the sample report.
"""

import re
from pathlib import Path

UNITS = ("row", "sentence", "word", "line", "letter", "page")

# Stage names by score band (scoring._band thresholds). The report shows
# the stage, never the band id.
STAGES = (
    {"id": "learning", "label": "Learning", "band": "focus", "minimum": 0},
    {"id": "improving", "label": "Improving", "band": "dev", "minimum": 4.5},
    {"id": "mastering", "label": "Mastering", "band": "good", "minimum": 7},
    {"id": "strong", "label": "Strong", "band": "strong", "minimum": 8.5},
)

# One try is doing an exercise once, in its unit (1 try = 1 row). A week
# of tries, then a fresh check. "exercises" is how many exercises the band
# asks for; the tier caps it.
DOSAGE = {
    "focus": {
        "tries": 15,
        "per": "day",
        "days": 7,
        "recheck_days": 7,
        "exercises": 2,
    },
    "dev": {
        "tries": 10,
        "per": "day",
        "days": 7,
        "recheck_days": 7,
        "exercises": 2,
    },
    "good": {
        "tries": 5,
        "per": "day",
        "days": 7,
        "recheck_days": 7,
        "exercises": 1,
    },
    "strong": {
        "tries": 10,
        "per": "week",
        "days": 28,
        "recheck_days": 28,
        "exercises": 1,
    },
}

# How much one report shows, per tier. The one place these numbers live:
# /api/v2/me returns them for the visitor's tier and the browser uses
# them, falling back to the catalogue's copy.
TIERS = {
    "free": {"areas_max": 3, "exercises_max": 1, "tips_max": 1},
    "pro": {"areas_max": 3, "exercises_max": 2, "tips_max": 2},
}

# Children read the report. These words judge the child instead of
# describing the writing, so no catalogue text may use them; the
# renderer's strings are held to the same list by a test.
AVOID_WORDS = (
    "weak",
    "poor",
    "bad",
    "wrong",
    "problem",
    "inadequate",
    "fail",
    "lowest",
    "mistake",
)

STEPS_MAX = 140


def avoid_pattern():
    """Matches an avoided word with its usual endings (mistakes, failed),
    but not a longer word that starts the same way (badge)."""
    words = "|".join(AVOID_WORDS)
    return re.compile(r"\b(" + words + r")(s|ed|ing|ly|ness|er|est)?\b", re.I)


# Factors a photo cannot score; their exercises need the pen.
PEN_FACTORS = (13, 14, 15, 16)

# The spelling row: shown only when the limited spelling check found a
# word, extra to the skill rows.
SPELLING = {
    "exercises": (
        {
            "id": "spell.look-cover-write",
            "level": 1,
            "title": "Look, cover, write",
            "unit": "word",
            "script": "latin",
            "needs": "photo",
            "worksheet": None,
            "steps": (
                "Look at the word, cover it, write it from memory, then"
                " check. Use it in one sentence."
            ),
            "example": "",
            "check": "Does your word match the one you looked at?",
        },
    ),
    "tips": (
        {
            "id": "spell.say-it",
            "text": (
                "Say the word slowly and listen for each sound as you"
                " write it."
            ),
        },
        {
            "id": "spell.small-parts",
            "text": (
                "Split a long word into small parts and learn one part"
                " at a time."
            ),
        },
    ),
}

FACTORS = {
    1: {
        "exercises": (
            {
                "id": "shapes.slow-copy",
                "level": 1,
                "title": "Slow copy",
                "unit": "row",
                "script": "any",
                "needs": "photo",
                "worksheet": "letter-shapes",
                "steps": (
                    "Copy five letters slowly from a model. Check each shape"
                    " before writing the next."
                ),
                "example": "a d g q o",
                "check": "Does each letter look like the model?",
            },
            {
                "id": "shapes.letter-families",
                "level": 2,
                "title": "Letter families",
                "unit": "row",
                "script": "latin",
                "needs": "photo",
                "worksheet": "letter-shapes",
                "steps": (
                    "Write the round family c a d g q o in one row, starting"
                    " each one the same way."
                ),
                "example": "c a d g q o",
                "check": "Do all round letters start at the same point?",
            },
            {
                "id": "shapes.trace-then-write",
                "level": 3,
                "title": "Trace, then write",
                "unit": "word",
                "script": "any",
                "needs": "photo",
                "worksheet": "letter-shapes",
                "steps": (
                    "Trace a word once, then write it twice on your own"
                    " without looking."
                ),
                "example": "garden",
                "check": "Is your own copy as clear as the traced one?",
            },
        ),
        "tips": (
            {
                "id": "shapes.start-at-top",
                "text": (
                    "Start most letters at the top, so every copy of a letter"
                    " is built the same way."
                ),
            },
            {
                "id": "shapes.slow-is-clear",
                "text": (
                    "Slow down for one line: neat shapes come first, speed"
                    " comes later."
                ),
            },
        ),
    },
    2: {
        "exercises": (
            {
                "id": "order.say-the-strokes",
                "level": 1,
                "title": "Say the strokes",
                "unit": "letter",
                "script": "any",
                "needs": "photo",
                "worksheet": None,
                "steps": (
                    "Say each stroke out loud as you write it: down, up and"
                    " round."
                ),
                "example": "b d p",
                "check": "Did you start each letter at the top?",
            },
            {
                "id": "order.start-dots",
                "level": 2,
                "title": "Start dots",
                "unit": "row",
                "script": "any",
                "needs": "photo",
                "worksheet": None,
                "steps": (
                    "Put a small dot where each letter starts, then write the"
                    " row starting on the dots."
                ),
                "example": "a b c d e",
                "check": "Did every letter begin on its dot?",
            },
        ),
        "tips": (
            {
                "id": "order.top-down",
                "text": (
                    "Pull strokes down rather than pushing them up; it is"
                    " easier to control."
                ),
            },
            {
                "id": "order.same-every-time",
                "text": (
                    "Use the same start point for a letter every time, even in"
                    " a hurry."
                ),
            },
        ),
    },
    3: {
        "exercises": (
            {
                "id": "loops.close-the-circle",
                "level": 1,
                "title": "Close the circle",
                "unit": "row",
                "script": "any",
                "needs": "photo",
                "worksheet": "letter-shapes",
                "steps": (
                    "Write a row of o and a. Join the end of each round back"
                    " to its start."
                ),
                "example": "o a o a o a",
                "check": "Is every round letter closed, with no gap?",
            },
            {
                "id": "loops.gap-hunt",
                "level": 2,
                "title": "Gap hunt",
                "unit": "sentence",
                "script": "any",
                "needs": "photo",
                "worksheet": "letter-shapes",
                "steps": (
                    "Write one sentence, then look for open a, d, g and o."
                    " Rewrite any word with a gap."
                ),
                "example": "a good dog",
                "check": "Could an a be read as a u?",
            },
            {
                "id": "loops.tall-loops",
                "level": 3,
                "title": "Tall loops",
                "unit": "row",
                "script": "latin",
                "needs": "photo",
                "worksheet": None,
                "steps": (
                    "In joined writing, write l, b and k with narrow, closed"
                    " loops."
                ),
                "example": "l b k l b k",
                "check": "Are the loops closed and the same width?",
            },
        ),
        "tips": (
            {
                "id": "loops.close-the-door",
                "text": (
                    "Think of each round letter as a door: close it before you"
                    " walk on."
                ),
            },
            {
                "id": "loops.go-back-over",
                "text": (
                    "Go back over the top of a and d before the tail; that"
                    " closes the gap."
                ),
            },
        ),
    },
    4: {
        "exercises": (
            {
                "id": "strokes.long-lines",
                "level": 1,
                "title": "Long smooth lines",
                "unit": "row",
                "script": "any",
                "needs": "photo",
                "worksheet": "smooth-strokes",
                "steps": (
                    "Draw slow straight lines and gentle waves across the page"
                    " without lifting the pencil."
                ),
                "example": "~~~~ ||||",
                "check": "Are the lines smooth, without wobbles?",
            },
            {
                "id": "strokes.light-grip",
                "level": 2,
                "title": "Light grip",
                "unit": "row",
                "script": "any",
                "needs": "photo",
                "worksheet": "smooth-strokes",
                "steps": (
                    "Hold the pencil lightly and write l and c slowly. Relax"
                    " your hand between letters."
                ),
                "example": "l c l c l c",
                "check": "Is each stroke one clean line?",
            },
        ),
        "tips": (
            {
                "id": "strokes.relax-grip",
                "text": (
                    "If your fingers turn white, the grip is too tight. Loosen"
                    " it and shake out your hand."
                ),
            },
            {
                "id": "strokes.sharp-pencil",
                "text": (
                    "A sharp pencil or a smooth pen gives cleaner lines than a"
                    " blunt one."
                ),
            },
        ),
    },
    5: {
        "exercises": (
            {
                "id": "size.two-line-ladder",
                "level": 1,
                "title": "Two-line ladder",
                "unit": "row",
                "script": "any",
                "needs": "photo",
                "worksheet": "letter-size",
                "steps": (
                    "Between two light guide lines, write a o e c n m. Every"
                    " letter touches both lines."
                ),
                "example": "a o e c n m",
                "check": "Do all small letters touch both lines?",
            },
            {
                "id": "size.size-twins",
                "level": 2,
                "title": "Size twins",
                "unit": "row",
                "script": "latin",
                "needs": "photo",
                "worksheet": "letter-size",
                "steps": (
                    "Write moon and came. Make all their small letters the"
                    " same height."
                ),
                "example": "moon came",
                "check": "Are the small letters one height?",
            },
            {
                "id": "size.fade-the-guide",
                "level": 3,
                "title": "Fade the guide",
                "unit": "sentence",
                "script": "any",
                "needs": "photo",
                "worksheet": "letter-size",
                "steps": (
                    "Write a sentence with guide lines, then the same sentence"
                    " on plain paper."
                ),
                "example": "we can see the sea",
                "check": "Did the size stay even without the lines?",
            },
        ),
        "tips": (
            {
                "id": "size.match-the-x",
                "text": (
                    "Match every small letter to the height of the first x or"
                    " o on the line."
                ),
            },
            {
                "id": "size.paper-close",
                "text": (
                    "Keep the paper straight in front of you; letters grow"
                    " when the hand reaches."
                ),
            },
        ),
    },
    6: {
        "exercises": (
            {
                "id": "zones.tall-and-tails",
                "level": 1,
                "title": "Tall and tails",
                "unit": "row",
                "script": "latin",
                "needs": "photo",
                "worksheet": "letter-size",
                "steps": (
                    "Write h, l, g and y. Make h and l tall; let g and y go"
                    " below the line."
                ),
                "example": "h l g y",
                "check": "Do tall letters reach up and tails go down?",
            },
            {
                "id": "zones.three-zones",
                "level": 2,
                "title": "Three zones",
                "unit": "word",
                "script": "latin",
                "needs": "photo",
                "worksheet": "letter-size",
                "steps": (
                    "On four-line paper, write words with tall letters and"
                    " tails, using all three zones."
                ),
                "example": "jelly baby",
                "check": "Is each part of the letter in its zone?",
            },
        ),
        "tips": (
            {
                "id": "zones.three-floors",
                "text": (
                    "Think of three floors: tall letters visit the top floor,"
                    " tails visit the basement."
                ),
            },
            {
                "id": "zones.tall-twice",
                "text": (
                    "Make tall letters about twice the height of small ones."
                ),
            },
        ),
    },
    7: {
        "exercises": (
            {
                "id": "line.sit-on-the-line",
                "level": 1,
                "title": "Sit on the line",
                "unit": "sentence",
                "script": "any",
                "needs": "photo",
                "worksheet": "baseline",
                "steps": (
                    "Write one sentence. Circle any letter that floats or"
                    " dips, then write that word again."
                ),
                "example": "keep words on the line",
                "check": "Does every letter sit on the line?",
            },
            {
                "id": "line.underline-check",
                "level": 2,
                "title": "Underline check",
                "unit": "sentence",
                "script": "any",
                "needs": "photo",
                "worksheet": "baseline",
                "steps": (
                    "Write a sentence, then draw a ruler line under it. Look"
                    " for gaps above the ruler line."
                ),
                "example": "the sun is up",
                "check": "Is there an even gap above the ruler line?",
            },
            {
                "id": "line.highlight-the-line",
                "level": 3,
                "title": "Bold writing line",
                "unit": "line",
                "script": "any",
                "needs": "photo",
                "worksheet": "baseline",
                "steps": (
                    "Go over the writing line in colour so it is easy to see,"
                    " then write two lines on it."
                ),
                "example": "",
                "check": "Do your words stay on the coloured line?",
            },
        ),
        "tips": (
            {
                "id": "line.feel-the-line",
                "text": (
                    "Let the pencil touch the line at the bottom of every"
                    " small letter."
                ),
            },
            {
                "id": "line.dark-line",
                "text": (
                    "On plain paper, put a dark lined sheet underneath so the"
                    " lines show through."
                ),
            },
        ),
    },
    8: {
        "exercises": (
            {
                "id": "space.finger-spaces",
                "level": 1,
                "title": "Finger spaces",
                "unit": "sentence",
                "script": "any",
                "needs": "photo",
                "worksheet": "word-spacing",
                "steps": (
                    "Write a short sentence. Put one finger after each word"
                    " before you start the next."
                ),
                "example": "I like to read",
                "check": "Are the gaps about one finger wide?",
            },
            {
                "id": "space.dot-the-gaps",
                "level": 2,
                "title": "Dot the gaps",
                "unit": "sentence",
                "script": "any",
                "needs": "photo",
                "worksheet": "word-spacing",
                "steps": (
                    "Copy the cat sat on a mat. Put a small dot in each gap:"
                    " are the dots the same distance apart?"
                ),
                "example": "the cat sat on a mat",
                "check": "Are all the gaps the same size?",
            },
            {
                "id": "space.spaced-copy",
                "level": 3,
                "title": "Spaced copy",
                "unit": "sentence",
                "script": "any",
                "needs": "photo",
                "worksheet": "word-spacing",
                "steps": (
                    "Copy two lines from a book, keeping its word gaps,"
                    " without using your finger."
                ),
                "example": "",
                "check": "Can someone read it at a glance?",
            },
        ),
        "tips": (
            {
                "id": "space.finger-or-pencil",
                "text": (
                    "A finger or the width of a pencil is a good gap for"
                    " children."
                ),
            },
            {
                "id": "space.read-aloud",
                "text": (
                    "If the gaps are right, you can read the line aloud"
                    " without stopping."
                ),
            },
        ),
    },
    9: {
        "exercises": (
            {
                "id": "letters.room-to-breathe",
                "level": 1,
                "title": "Room inside words",
                "unit": "word",
                "script": "any",
                "needs": "photo",
                "worksheet": "word-spacing",
                "steps": (
                    "Write the word letter. Leave the same small gap between"
                    " every pair of letters."
                ),
                "example": "letter",
                "check": "Do any letters touch or crowd?",
            },
            {
                "id": "letters.even-rows",
                "level": 2,
                "title": "Even letter rows",
                "unit": "row",
                "script": "any",
                "needs": "photo",
                "worksheet": "word-spacing",
                "steps": (
                    "Write m i n i m in one row. The gaps inside the word"
                    " should look the same."
                ),
                "example": "minim",
                "check": "Are the letters evenly spread?",
            },
        ),
        "tips": (
            {
                "id": "letters.no-touching",
                "text": "Letters inside a word sit close but do not touch.",
            },
            {
                "id": "letters.same-gap",
                "text": (
                    "Look at the gap after each letter as you write the next"
                    " one."
                ),
            },
        ),
    },
    10: {
        "exercises": (
            {
                "id": "margin.start-at-the-margin",
                "level": 1,
                "title": "Start at the margin",
                "unit": "line",
                "script": "any",
                "needs": "photo",
                "worksheet": "page-layout",
                "steps": (
                    "Draw a light left margin. Start three short lines right"
                    " beside it."
                ),
                "example": "",
                "check": "Do all lines start at the margin?",
            },
            {
                "id": "margin.plan-the-line",
                "level": 2,
                "title": "Plan the line end",
                "unit": "line",
                "script": "any",
                "needs": "photo",
                "worksheet": "page-layout",
                "steps": (
                    "Before writing a long word near the right edge, check it"
                    " fits; if not, start it on the next line."
                ),
                "example": "",
                "check": "Did any word squeeze at the right edge?",
            },
        ),
        "tips": (
            {
                "id": "margin.fold",
                "text": (
                    "Fold the paper once lengthways and open it; the fold"
                    " makes a quick margin."
                ),
            },
            {
                "id": "margin.finger-start",
                "text": (
                    "Put a finger at the margin and start each line next"
                    " to it."
                ),
            },
        ),
    },
    11: {
        "exercises": (
            {
                "id": "straight.level-sentence",
                "level": 1,
                "title": "Level sentence",
                "unit": "sentence",
                "script": "any",
                "needs": "photo",
                "worksheet": "baseline",
                "steps": (
                    "Write a sentence along a ruled line. Keep it level to the"
                    " end."
                ),
                "example": "we walk to school",
                "check": "Does the end of the line drift up or down?",
            },
            {
                "id": "straight.paper-position",
                "level": 2,
                "title": "Steady paper",
                "unit": "line",
                "script": "any",
                "needs": "photo",
                "worksheet": "baseline",
                "steps": (
                    "Tilt the paper slightly and hold it with your other hand."
                    " Write two lines without moving it."
                ),
                "example": "",
                "check": "Are the lines straighter than before?",
            },
        ),
        "tips": (
            {
                "id": "straight.paper-anchor",
                "text": (
                    "Hold the paper with the other hand and move it up as you"
                    " go down the page."
                ),
            },
            {
                "id": "straight.look-ahead",
                "text": "Look at the end of the line, not just at the pencil.",
            },
        ),
    },
    12: {
        "exercises": (
            {
                "id": "upright.tall-strokes",
                "level": 1,
                "title": "Matching tall strokes",
                "unit": "row",
                "script": "latin",
                "needs": "photo",
                "worksheet": "baseline",
                "steps": (
                    "Write l and h in a row. Keep their tall strokes at the"
                    " same angle."
                ),
                "example": "l h l h l h",
                "check": "Are all the tall strokes parallel?",
            },
            {
                "id": "upright.line-up",
                "level": 2,
                "title": "Line up the starts",
                "unit": "line",
                "script": "any",
                "needs": "photo",
                "worksheet": "baseline",
                "steps": (
                    "Write three short lines, each starting exactly under the"
                    " line above."
                ),
                "example": "",
                "check": "Do the line starts form a straight edge?",
            },
        ),
        "tips": (
            {
                "id": "upright.same-angle",
                "text": "Tilt the paper the same way every time you write.",
            },
            {
                "id": "upright.check-stems",
                "text": (
                    "Look at the tall stems of l, d and h: they should look"
                    " like a fence."
                ),
            },
        ),
    },
    13: {
        "exercises": (
            {
                "id": "pace.steady-count",
                "level": 1,
                "title": "Steady count",
                "unit": "row",
                "script": "any",
                "needs": "pen",
                "worksheet": None,
                "steps": (
                    "Write one letter on each count of a slow, even beat."
                ),
                "example": "a a a a a",
                "check": (
                    "Did the letters stay the same while you kept the beat?"
                ),
            },
        ),
        "tips": (
            {
                "id": "pace.not-too-fast",
                "text": "Write at a speed where letters still look the same.",
            },
            {
                "id": "pace.short-bursts",
                "text": (
                    "Short, regular bursts of writing beat one long rushed"
                    " one."
                ),
            },
        ),
    },
    14: {
        "exercises": (
            {
                "id": "pressure.light-dark-light",
                "level": 1,
                "title": "Light touch",
                "unit": "row",
                "script": "any",
                "needs": "pen",
                "worksheet": None,
                "steps": (
                    "Write a row pressing lightly, then a row pressing"
                    " normally. Keep the lighter one."
                ),
                "example": "o o o o",
                "check": "Is the line the same darkness all the way?",
            },
        ),
        "tips": (
            {
                "id": "pressure.see-the-back",
                "text": (
                    "Turn the page over: if you can feel the writing, press"
                    " more lightly."
                ),
            },
            {
                "id": "pressure.soft-pencil",
                "text": "A softer pencil needs less pressure.",
            },
        ),
    },
    15: {
        "exercises": (
            {
                "id": "flow.joined-pairs",
                "level": 1,
                "title": "Joined pairs",
                "unit": "row",
                "script": "latin",
                "needs": "pen",
                "worksheet": "smooth-strokes",
                "steps": (
                    "In joined writing, write in, an and un without lifting"
                    " the pencil."
                ),
                "example": "in an un",
                "check": "Did the pencil stay on the paper inside each pair?",
            },
        ),
        "tips": (
            {
                "id": "flow.plan-the-join",
                "text": (
                    "Know where the next letter starts before you finish this"
                    " one."
                ),
            },
            {
                "id": "flow.relaxed-wrist",
                "text": (
                    "Rest the side of your hand on the table and let the wrist"
                    " move."
                ),
            },
        ),
    },
    16: {
        "exercises": (
            {
                "id": "lifts.one-lift-words",
                "level": 1,
                "title": "One-lift words",
                "unit": "word",
                "script": "latin",
                "needs": "pen",
                "worksheet": None,
                "steps": (
                    "Write short words lifting the pencil only at the end of"
                    " each word."
                ),
                "example": "mum run",
                "check": "Did you lift only at the end?",
            },
        ),
        "tips": (
            {
                "id": "lifts.word-at-a-time",
                "text": "Think a whole word, then write it in one go.",
            },
            {
                "id": "lifts.pause-not-lift",
                "text": (
                    "Pause between strokes with the pencil still on the paper."
                ),
            },
        ),
    },
    17: {
        "exercises": (
            {
                "id": "slant.same-lean",
                "level": 1,
                "title": "Same lean",
                "unit": "row",
                "script": "latin",
                "needs": "photo",
                "worksheet": "slant",
                "steps": "Write m, i and n slowly. Keep their lean the same.",
                "example": "m i n m i n",
                "check": "Do all letters lean the same way?",
            },
            {
                "id": "slant.slant-lines",
                "level": 2,
                "title": "Slant guides",
                "unit": "line",
                "script": "latin",
                "needs": "photo",
                "worksheet": "slant",
                "steps": (
                    "Draw light slant lines across the row, then write two"
                    " lines following them."
                ),
                "example": "",
                "check": "Do your downstrokes follow the guides?",
            },
        ),
        "tips": (
            {
                "id": "slant.paper-tilt",
                "text": (
                    "Right-handers usually tilt the paper a little left;"
                    " left-handers a little right."
                ),
            },
            {
                "id": "slant.pick-one",
                "text": "Upright or leaning, pick one and keep it.",
            },
        ),
    },
    18: {
        "exercises": (
            {
                "id": "read.read-it-back",
                "level": 1,
                "title": "Read it back",
                "unit": "sentence",
                "script": "any",
                "needs": "photo",
                "worksheet": None,
                "steps": (
                    "Write two sentences, then ask someone to read them aloud."
                    " Rewrite any word they stopped at."
                ),
                "example": "",
                "check": "Could they read every word first time?",
            },
            {
                "id": "read.slow-best",
                "level": 2,
                "title": "Best handwriting",
                "unit": "line",
                "script": "any",
                "needs": "photo",
                "worksheet": None,
                "steps": (
                    "Write two lines in your slowest, clearest handwriting."
                    " Compare them with your normal writing."
                ),
                "example": "",
                "check": "Which words became easier to read?",
            },
        ),
        "tips": (
            {
                "id": "read.stranger-test",
                "text": (
                    "If a classmate can read it without asking, it is legible."
                ),
            },
            {
                "id": "read.fix-one",
                "text": (
                    "Fix the one skill that stopped the reader, not everything"
                    " at once."
                ),
            },
        ),
    },
    19: {
        "exercises": (
            {
                "id": "distinct.look-alike-pairs",
                "level": 1,
                "title": "Look-alike pairs",
                "unit": "row",
                "script": "latin",
                "needs": "photo",
                "worksheet": "letter-distinction",
                "steps": (
                    "Write a next to o, then c next to e. Make each pair easy"
                    " to tell apart."
                ),
                "example": "a o c e",
                "check": "Could anyone mix up any pair?",
            },
            {
                "id": "distinct.n-and-h",
                "level": 2,
                "title": "n, h, r and u",
                "unit": "row",
                "script": "latin",
                "needs": "photo",
                "worksheet": "letter-distinction",
                "steps": (
                    "Write n h r u in a row. Make h tall, close the top of n,"
                    " and leave u open at the top."
                ),
                "example": "n h r u",
                "check": "Is each letter clearly itself?",
            },
        ),
        "tips": (
            {
                "id": "distinct.close-tops",
                "text": (
                    "Close the top of a, d, g and q so they do not look like u"
                    " or c."
                ),
            },
            {
                "id": "distinct.tall-h",
                "text": "Make h and k tall so they cannot be read as n or x.",
            },
        ),
    },
    20: {
        "exercises": (
            {
                "id": "neat.clean-page",
                "level": 1,
                "title": "Clean page",
                "unit": "page",
                "script": "any",
                "needs": "photo",
                "worksheet": "page-layout",
                "steps": (
                    "Write a short paragraph with a margin, even gaps and no"
                    " crossings-out; cross out with one line if you must."
                ),
                "example": "",
                "check": "Does the page look tidy from arm's length?",
            },
            {
                "id": "neat.copy-best",
                "level": 2,
                "title": "Best copy",
                "unit": "line",
                "script": "any",
                "needs": "photo",
                "worksheet": "page-layout",
                "steps": (
                    "Copy three lines of your own writing into a neat final"
                    " copy."
                ),
                "example": "",
                "check": "Is the final copy neater than the first?",
            },
        ),
        "tips": (
            {
                "id": "neat.one-line-cross",
                "text": (
                    "Cross out with one straight line instead of scribbling."
                ),
            },
            {
                "id": "neat.space-around",
                "text": (
                    "Leave a clear space between paragraphs and around the"
                    " page edges."
                ),
            },
        ),
    },
}


def _texts(entry):
    keys = ("title", "steps", "example", "check", "text")
    return [entry[k] for k in keys if isinstance(entry.get(k), str)]


def _worksheet_ids():
    """Ids in the website's worksheet catalogue, or None without it."""
    path = (
        Path(__file__).resolve().parent.parent
        / "frontend"
        / "src"
        / "report"
        / "worksheet-catalog.js"
    )
    if not path.exists():
        return None
    return set(re.findall(r'"id":\s*"([\w-]+)"', path.read_text("utf-8")))


EM_DASH = "\u2014"


def _exercise_problems(ex, photo, sheets):
    found = []
    if len(ex["steps"]) > STEPS_MAX:
        found.append(f"{ex['id']}: steps over {STEPS_MAX} chars")
    if ex["unit"] not in UNITS:
        found.append(f"{ex['id']}: unknown unit {ex['unit']}")
    if ex["script"] not in ("any", "latin"):
        found.append(f"{ex['id']}: unknown script")
    if ex["needs"] != ("photo" if photo else "pen"):
        found.append(f"{ex['id']}: needs does not match factor")
    sheet = ex["worksheet"]
    if sheet is not None and sheets is not None and sheet not in sheets:
        found.append(f"{ex['id']}: unknown worksheet {sheet}")
    return found


def _word_problems(entry):
    banned = avoid_pattern()
    found = []
    for text in _texts(entry):
        if banned.search(text):
            found.append(f"{entry['id']}: avoid word in {text!r}")
        if EM_DASH in text:
            found.append(f"{entry['id']}: em dash in {text!r}")
    return found


def _area_problems(name, area, number):
    photo = number not in PEN_FACTORS
    found = []
    if photo and number and len(area["exercises"]) < 2:
        found.append(f"{name}: fewer than 2 exercises")
    if photo and len(area["tips"]) < 2:
        found.append(f"{name}: fewer than 2 tips")
    levels = [e["level"] for e in area["exercises"]]
    if levels != sorted(levels):
        found.append(f"{name}: exercises out of level order")
    return found


def problems():
    """Every rule the catalogue breaks, as readable lines (none is good)."""
    found = []
    sheets = _worksheet_ids()
    seen = set()
    areas = [(n, f"factor {n}", FACTORS.get(n)) for n in range(1, 21)]
    areas.append((0, "spelling", SPELLING))
    for number, name, area in areas:
        if not area:
            found.append(f"{name}: missing")
            continue
        found += _area_problems(name, area, number)
        for entry in (*area["exercises"], *area["tips"]):
            if entry["id"] in seen:
                found.append(f"{name}: duplicate id {entry['id']}")
            seen.add(entry["id"])
            found += _word_problems(entry)
        for ex in area["exercises"]:
            found += _exercise_problems(ex, number not in PEN_FACTORS, sheets)
    if set(DOSAGE) != {s["band"] for s in STAGES}:
        found.append("dosage must cover every band")
    if set(TIERS) != {"free", "pro"}:
        found.append("tiers must be free and pro")
    return found


def limits(tier):
    """How many skills, exercises and tips a report shows for a tier."""
    return dict(TIERS["pro" if tier == "pro" else "free"])


def _plain(entries):
    return [dict(e) for e in entries]


def factor_practice(number):
    """The exercises and tips the catalogue serves for one factor."""
    area = FACTORS[number]
    return {
        "exercises": _plain(area["exercises"]),
        "tips": _plain(area["tips"]),
    }


def practice_block():
    """The top-level ``practice`` block of the versioned catalogue."""
    return {
        "stages": _plain(STAGES),
        "dosage": {band: dict(d) for band, d in DOSAGE.items()},
        "tiers": {tier: dict(t) for tier, t in TIERS.items()},
        "units": list(UNITS),
        "spelling": {
            "exercises": _plain(SPELLING["exercises"]),
            "tips": _plain(SPELLING["tips"]),
        },
    }


def browser_catalog():
    """What the browser bundle carries for reports made without a server
    catalogue (the sample report): the block plus every factor's lists."""
    return {
        **practice_block(),
        "factors": {str(n): factor_practice(n) for n in range(1, 21)},
    }


_PROBLEMS = problems()
if _PROBLEMS:
    raise ValueError("Practice catalogue: " + "; ".join(_PROBLEMS))
