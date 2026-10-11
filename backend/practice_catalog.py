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

Every exercise and tip also carries its translations in ``i18n``
(Telugu today, draft wording until a native speaker has checked it; see
TELUGU_EXERCISES and TELUGU_TIPS), served with the catalogue so a report
printed in Telugu ("Print in") uses the same exercises in that language.

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

# The same words in Telugu (and close forms), for the Telugu text in this
# catalogue and the report's Telugu string table. Telugu joins endings on
# to a word, so these match anywhere inside one: wrong and mistake
# (tappu, porapatu), weak (balaheena), poor (pelava), bad (chedu,
# chedda), problem (samasya), inadequate (sariponi), fail (vifala,
# feyil) and lowest (ati takkuva, atyalpa). Draft list, for the native
# speaker's review with the rest of the Telugu.
AVOID_WORDS_TE = (
    "తప్పు",
    "పొరపాటు",
    "బలహీన",
    "పేలవ",
    "చెడు",
    "చెడ్డ",
    "సమస్య",
    "సరిపోని",
    "విఫల",
    "ఫెయిల్",
    "అతి తక్కువ",
    "అత్యల్ప",
)

# Languages the catalogue is translated into. Every exercise and tip
# carries each of them in ``i18n``; a missing one stops the import.
LANGUAGES = ("te",)


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


# Telugu (DRAFT WORDING, 2026-10-11: written for this change and not yet
# checked by a native speaker; it must be checked before Telugu reaches
# production). Keyed by exercise or tip id; ``_attach_translations``
# puts each into its entry as ``i18n["te"]``. Latin practice letters and
# words stay as written: the child practises English letters, so no
# example is translated.
TELUGU_EXERCISES = {
    "shapes.slow-copy": {
        "title": "నెమ్మదిగా చూసి రాయడం",
        "steps": (
            "నమూనా చూసి ఐదు అక్షరాలు నెమ్మదిగా రాయండి. తర్వాతి అక్షరం "
            "రాసే ముందు ప్రతి ఆకారాన్ని చూసుకోండి."
        ),
        "check": "ప్రతి అక్షరం నమూనాలాగే ఉందా?",
    },
    "shapes.letter-families": {
        "title": "అక్షరాల కుటుంబాలు",
        "steps": (
            "గుండ్రని కుటుంబం c a d g q o ని ఒకే వరుసలో రాయండి. ప్రతి "
            "అక్షరాన్ని ఒకే చోట మొదలుపెట్టండి."
        ),
        "check": "గుండ్రని అక్షరాలన్నీ ఒకే చోట మొదలయ్యాయా?",
    },
    "shapes.trace-then-write": {
        "title": "దిద్ది, తర్వాత రాయండి",
        "steps": (
            "ఒక పదాన్ని ఒకసారి దిద్దండి. తర్వాత చూడకుండా మీరే "
            "రెండుసార్లు రాయండి."
        ),
        "check": "మీరు రాసింది దిద్దినంత స్పష్టంగా ఉందా?",
    },
    "order.say-the-strokes": {
        "title": "గీతలు చెప్తూ రాయండి",
        "steps": "ప్రతి గీత రాస్తూ పైకి చెప్పండి: కిందికి, పైకి, గుండ్రంగా.",
        "check": "ప్రతి అక్షరాన్ని పైనుంచి మొదలుపెట్టారా?",
    },
    "order.start-dots": {
        "title": "మొదలు చుక్కలు",
        "steps": (
            "ప్రతి అక్షరం మొదలయ్యే చోట చిన్న చుక్క పెట్టండి. తర్వాత "
            "చుక్కల నుంచి మొదలుపెట్టి వరుస రాయండి."
        ),
        "check": "ప్రతి అక్షరం తన చుక్క దగ్గరే మొదలైందా?",
    },
    "loops.close-the-circle": {
        "title": "గుండ్రం మూయండి",
        "steps": (
            "o, a ల వరుస రాయండి. ప్రతి గుండ్రని ఆకారం చివరను దాని "
            "మొదలుకు కలపండి."
        ),
        "check": "ప్రతి గుండ్రని అక్షరం ఖాళీ లేకుండా మూసుకుందా?",
    },
    "loops.gap-hunt": {
        "title": "ఖాళీ వెతకండి",
        "steps": (
            "ఒక వాక్యం రాయండి. తెరిచి ఉన్న a, d, g, o కోసం చూడండి. ఖాళీ "
            "ఉన్న పదాన్ని మళ్ళీ రాయండి."
        ),
        "check": "ఏదైనా a ని u లా చదవొచ్చా?",
    },
    "loops.tall-loops": {
        "title": "పొడవైన చుట్లు",
        "steps": "కలిపి రాసే రాతలో l, b, k లను సన్నని, మూసిన చుట్లతో రాయండి.",
        "check": "చుట్లు మూసుకుని, ఒకే వెడల్పులో ఉన్నాయా?",
    },
    "strokes.long-lines": {
        "title": "పొడవైన నునుపైన గీతలు",
        "steps": (
            "పెన్సిల్ ఎత్తకుండా పేజీ అంతటా నెమ్మదిగా నిటారు గీతలు, "
            "మెల్లని అలలు గీయండి."
        ),
        "check": "గీతలు వణుకు లేకుండా నునుపుగా ఉన్నాయా?",
    },
    "strokes.light-grip": {
        "title": "తేలికైన పట్టు",
        "steps": (
            "పెన్సిల్\u200cను తేలికగా పట్టుకుని l, c లను నెమ్మదిగా "
            "రాయండి. అక్షరాల మధ్య చేతిని వదులు చేయండి."
        ),
        "check": "ప్రతి గీత ఒకే శుభ్రమైన గీతగా ఉందా?",
    },
    "size.two-line-ladder": {
        "title": "రెండు గీతల నిచ్చెన",
        "steps": (
            "రెండు లేత గీతల మధ్య a o e c n m రాయండి. ప్రతి అక్షరం రెండు "
            "గీతలనూ తాకాలి."
        ),
        "check": "చిన్న అక్షరాలన్నీ రెండు గీతలనూ తాకుతున్నాయా?",
    },
    "size.size-twins": {
        "title": "ఒకే ఎత్తు జంటలు",
        "steps": (
            "moon, came అని రాయండి. వాటిలోని చిన్న అక్షరాలన్నీ ఒకే "
            "ఎత్తులో ఉండాలి."
        ),
        "check": "చిన్న అక్షరాలన్నీ ఒకే ఎత్తులో ఉన్నాయా?",
    },
    "size.fade-the-guide": {
        "title": "గీతలు లేకుండా",
        "steps": (
            "ఒక వాక్యాన్ని గైడ్ గీతలతో రాయండి, తర్వాత అదే వాక్యాన్ని "
            "తెల్ల కాగితంపై రాయండి."
        ),
        "check": "గీతలు లేకపోయినా పరిమాణం సమానంగా ఉందా?",
    },
    "zones.tall-and-tails": {
        "title": "పొడవైనవి, తోకలు",
        "steps": (
            "h, l, g, y రాయండి. h, l పొడవుగా ఉండాలి; g, y గీత కిందికి "
            "వెళ్ళాలి."
        ),
        "check": "పొడవైన అక్షరాలు పైకి, తోకలు కిందికి వెళ్తున్నాయా?",
    },
    "zones.three-zones": {
        "title": "మూడు భాగాలు",
        "steps": (
            "నాలుగు గీతల కాగితంపై పొడవైన అక్షరాలు, తోకలు ఉన్న పదాలు "
            "రాయండి. మూడు భాగాలనూ వాడండి."
        ),
        "check": "అక్షరంలోని ప్రతి భాగం దాని చోటులో ఉందా?",
    },
    "line.sit-on-the-line": {
        "title": "గీతపై కూర్చోబెట్టండి",
        "steps": (
            "ఒక వాక్యం రాయండి. గీత పైకి లేచిన లేదా కిందికి దిగిన అక్షరం "
            "చుట్టూ వృత్తం గీసి, ఆ పదం మళ్ళీ రాయండి."
        ),
        "check": "ప్రతి అక్షరం గీతపై కూర్చుందా?",
    },
    "line.underline-check": {
        "title": "అడుగు గీత పరీక్ష",
        "steps": (
            "ఒక వాక్యం రాసి, దాని కింద స్కేలుతో గీత గీయండి. ఆ గీత పైన "
            "ఖాళీలు ఉన్నాయేమో చూడండి."
        ),
        "check": "స్కేలు గీత పైన ఖాళీ అంతటా సమానంగా ఉందా?",
    },
    "line.highlight-the-line": {
        "title": "ముదురు రాత గీత",
        "steps": (
            "రాసే గీతను రంగుతో దిద్దండి, అది బాగా కనిపిస్తుంది. తర్వాత "
            "దానిపై రెండు వరుసలు రాయండి."
        ),
        "check": "మీ పదాలు రంగు గీతపైనే ఉన్నాయా?",
    },
    "space.finger-spaces": {
        "title": "వేలు ఖాళీలు",
        "steps": (
            "ఒక చిన్న వాక్యం రాయండి. తర్వాతి పదం మొదలుపెట్టే ముందు "
            "ప్రతి పదం తర్వాత ఒక వేలు ఉంచండి."
        ),
        "check": "ఖాళీలు దాదాపు ఒక వేలు వెడల్పు ఉన్నాయా?",
    },
    "space.dot-the-gaps": {
        "title": "ఖాళీలకు చుక్కలు",
        "steps": (
            "the cat sat on a mat అని రాయండి. ప్రతి ఖాళీలో చిన్న చుక్క "
            "పెట్టండి: చుక్కల మధ్య దూరం సమానంగా ఉందా?"
        ),
        "check": "ఖాళీలన్నీ ఒకే పరిమాణంలో ఉన్నాయా?",
    },
    "space.spaced-copy": {
        "title": "ఖాళీలతో కాపీ",
        "steps": (
            "పుస్తకంలోని రెండు వరుసలను, వేలు వాడకుండా, అందులోని పదాల "
            "ఖాళీలతో అలాగే రాయండి."
        ),
        "check": "ఎవరైనా ఒక్క చూపులో చదవగలరా?",
    },
    "letters.room-to-breathe": {
        "title": "పదం లోపల చోటు",
        "steps": (
            "letter అనే పదం రాయండి. ప్రతి రెండు అక్షరాల మధ్య ఒకే చిన్న "
            "ఖాళీ ఉంచండి."
        ),
        "check": "ఏవైనా అక్షరాలు తాకుతున్నాయా, ఇరుకుగా ఉన్నాయా?",
    },
    "letters.even-rows": {
        "title": "సమానమైన అక్షరాల వరుస",
        "steps": (
            "m i n i m ని ఒక వరుసలో రాయండి. పదంలోని ఖాళీలన్నీ ఒకేలా "
            "కనిపించాలి."
        ),
        "check": "అక్షరాలు సమానంగా పరుచుకున్నాయా?",
    },
    "margin.start-at-the-margin": {
        "title": "మార్జిన్ దగ్గర మొదలు",
        "steps": (
            "ఎడమ వైపు లేత మార్జిన్ గీత గీయండి. దాని పక్కనే మూడు చిన్న "
            "వరుసలు మొదలుపెట్టండి."
        ),
        "check": "అన్ని వరుసలూ మార్జిన్ దగ్గరే మొదలయ్యాయా?",
    },
    "margin.plan-the-line": {
        "title": "వరుస చివర ఆలోచించండి",
        "steps": (
            "కుడి అంచు దగ్గర పొడవైన పదం రాసే ముందు అది పడుతుందో చూడండి; "
            "పట్టకపోతే తర్వాతి వరుసలో రాయండి."
        ),
        "check": "కుడి అంచు దగ్గర ఏదైనా పదం ఇరుక్కుందా?",
    },
    "straight.level-sentence": {
        "title": "తిన్నని వాక్యం",
        "steps": (
            "గీతలు ఉన్న కాగితంపై ఒక వాక్యం రాయండి. చివరి వరకు తిన్నగా "
            "ఉంచండి."
        ),
        "check": "వరుస చివర పైకి గానీ కిందికి గానీ జారిందా?",
    },
    "straight.paper-position": {
        "title": "కదలని కాగితం",
        "steps": (
            "కాగితాన్ని కొంచెం వంచి, మరో చేత్తో పట్టుకోండి. కదల్చకుండా "
            "రెండు వరుసలు రాయండి."
        ),
        "check": "వరుసలు ముందుకంటే తిన్నగా ఉన్నాయా?",
    },
    "upright.tall-strokes": {
        "title": "ఒకేలా పొడవైన గీతలు",
        "steps": (
            "l, h లను ఒక వరుసలో రాయండి. వాటి పొడవైన గీతలను ఒకే కోణంలో "
            "ఉంచండి."
        ),
        "check": "పొడవైన గీతలన్నీ సమాంతరంగా ఉన్నాయా?",
    },
    "upright.line-up": {
        "title": "మొదళ్ళు ఒక వరుసలో",
        "steps": (
            "మూడు చిన్న వరుసలు రాయండి. ప్రతి వరుస సరిగ్గా పై వరుస కిందే "
            "మొదలవ్వాలి."
        ),
        "check": "వరుసల మొదళ్ళు ఒక నిటారు అంచులా ఉన్నాయా?",
    },
    "pace.steady-count": {
        "title": "స్థిరమైన లెక్క",
        "steps": (
            "నెమ్మదిగా, సమానంగా లెక్కపెడుతూ, ప్రతి లెక్కకు ఒక అక్షరం "
            "రాయండి."
        ),
        "check": "లెక్క కొనసాగిస్తూ రాసినప్పుడు అక్షరాలు ఒకేలా ఉన్నాయా?",
    },
    "pressure.light-dark-light": {
        "title": "తేలికైన స్పర్శ",
        "steps": (
            "ఒక వరుస తేలికగా నొక్కుతూ, తర్వాత ఒక వరుస మామూలుగా నొక్కుతూ "
            "రాయండి. తేలికైనదాన్నే కొనసాగించండి."
        ),
        "check": "గీత మొదటి నుంచి చివరి వరకు ఒకే ముదురుగా ఉందా?",
    },
    "flow.joined-pairs": {
        "title": "కలిపిన జంటలు",
        "steps": "కలిపి రాసే రాతలో in, an, un లను పెన్సిల్ ఎత్తకుండా రాయండి.",
        "check": "ప్రతి జంటలో పెన్సిల్ కాగితంపైనే ఉందా?",
    },
    "lifts.one-lift-words": {
        "title": "ఒక్కసారి ఎత్తే పదాలు",
        "steps": (
            "చిన్న పదాలు రాయండి. ప్రతి పదం చివర మాత్రమే పెన్సిల్ " "ఎత్తండి."
        ),
        "check": "పదం చివర మాత్రమే ఎత్తారా?",
    },
    "slant.same-lean": {
        "title": "ఒకే వాలు",
        "steps": "m, i, n లను నెమ్మదిగా రాయండి. వాటి వాలు ఒకేలా ఉంచండి.",
        "check": "అక్షరాలన్నీ ఒకే వైపు వాలుతున్నాయా?",
    },
    "slant.slant-lines": {
        "title": "వాలు గీతలు",
        "steps": (
            "వరుస అంతటా లేత వాలు గీతలు గీసి, వాటి వెంట రెండు వరుసలు " "రాయండి."
        ),
        "check": "మీరు కిందికి గీసే గీతలు గైడ్ గీతల వెంటే ఉన్నాయా?",
    },
    "read.read-it-back": {
        "title": "చదివించండి",
        "steps": (
            "రెండు వాక్యాలు రాసి, ఎవరినైనా పైకి చదవమనండి. వాళ్ళు ఆగిన "
            "పదాన్ని మళ్ళీ రాయండి."
        ),
        "check": "వాళ్ళు ప్రతి పదాన్నీ మొదటిసారే చదవగలిగారా?",
    },
    "read.slow-best": {
        "title": "మీ అత్యుత్తమ రాత",
        "steps": (
            "రెండు వరుసలను మీ అతి నెమ్మదైన, అతి స్పష్టమైన రాతలో రాయండి. "
            "మీ మామూలు రాతతో పోల్చండి."
        ),
        "check": "ఏ పదాలు చదవడానికి సులువయ్యాయి?",
    },
    "distinct.look-alike-pairs": {
        "title": "ఒకేలా కనిపించే జంటలు",
        "steps": (
            "o పక్కన a, తర్వాత e పక్కన c రాయండి. ప్రతి జంటలో తేడా "
            "సులువుగా తెలిసేలా రాయండి."
        ),
        "check": "ఏ జంటనైనా ఎవరైనా ఒకటిగా అనుకోవచ్చా?",
    },
    "distinct.n-and-h": {
        "title": "n, h, r, u అక్షరాలు",
        "steps": (
            "n h r u ని ఒక వరుసలో రాయండి. h పొడవుగా, n పైభాగం మూసి, u "
            "పైభాగం తెరిచి రాయండి."
        ),
        "check": "ప్రతి అక్షరం స్పష్టంగా తనలాగే ఉందా?",
    },
    "neat.clean-page": {
        "title": "శుభ్రమైన పేజీ",
        "steps": (
            "మార్జిన్\u200cతో, సమానమైన ఖాళీలతో, కొట్టివేతలు లేకుండా ఒక "
            "చిన్న పేరా రాయండి; కొట్టేయాలంటే ఒకే గీతతో."
        ),
        "check": "చేయి చాచినంత దూరం నుంచి పేజీ చక్కగా కనిపిస్తోందా?",
    },
    "neat.copy-best": {
        "title": "మంచి ప్రతి",
        "steps": "మీ రాతలోని మూడు వరుసలను చక్కని చివరి ప్రతిగా రాయండి.",
        "check": "చివరి ప్రతి మొదటిదానికంటే చక్కగా ఉందా?",
    },
    "spell.look-cover-write": {
        "title": "చూడండి, మూయండి, రాయండి",
        "steps": (
            "పదాన్ని చూడండి, మూసేయండి, గుర్తు నుంచి రాయండి, తర్వాత "
            "సరిచూసుకోండి. దాన్ని ఒక వాక్యంలో వాడండి."
        ),
        "check": "మీరు రాసిన పదం, చూసిన పదంలాగే ఉందా?",
    },
}

TELUGU_TIPS = {
    "shapes.start-at-top": {
        "text": (
            "చాలా అక్షరాలను పైనుంచి మొదలుపెట్టండి. అప్పుడు ఒకే అక్షరం "
            "ప్రతిసారీ ఒకేలా వస్తుంది."
        )
    },
    "shapes.slow-is-clear": {
        "text": "ఒక వరుస నెమ్మదిగా రాయండి: ముందు చక్కని ఆకారాలు, వేగం తర్వాత."
    },
    "order.top-down": {
        "text": (
            "గీతలను పైకి నెట్టడం కంటే కిందికి లాగండి; అలా చేయి సులువుగా "
            "అదుపులో ఉంటుంది."
        )
    },
    "order.same-every-time": {
        "text": "తొందరలో ఉన్నా, ఒక అక్షరాన్ని ప్రతిసారీ ఒకే చోట మొదలుపెట్టండి."
    },
    "loops.close-the-door": {
        "text": (
            "ప్రతి గుండ్రని అక్షరాన్ని ఒక తలుపులా అనుకోండి: ముందుకు "
            "వెళ్ళే ముందు దాన్ని మూసేయండి."
        )
    },
    "loops.go-back-over": {
        "text": (
            "a, d లకు తోక రాసే ముందు పైభాగం మీదుగా మళ్ళీ వెళ్ళండి; "
            "అప్పుడు ఖాళీ మూసుకుంటుంది."
        )
    },
    "strokes.relax-grip": {
        "text": (
            "వేళ్ళు తెల్లబడితే పట్టు గట్టిగా ఉందని అర్థం. పట్టు వదులు "
            "చేసి చేతిని విదిలించండి."
        )
    },
    "strokes.sharp-pencil": {
        "text": (
            "మొద్దుబారిన పెన్సిల్ కంటే చెక్కిన పెన్సిల్ లేదా నునుపైన "
            "పెన్ శుభ్రమైన గీతలు ఇస్తుంది."
        )
    },
    "size.match-the-x": {
        "text": (
            "వరుసలోని ప్రతి చిన్న అక్షరాన్ని మొదటి x లేదా o ఎత్తుతో "
            "సరిపోల్చండి."
        )
    },
    "size.paper-close": {
        "text": (
            "కాగితాన్ని మీ ముందు నిటారుగా ఉంచండి; చేయి దూరంగా సాగితే "
            "అక్షరాలు పెద్దవవుతాయి."
        )
    },
    "zones.three-floors": {
        "text": (
            "మూడు అంతస్తులు అనుకోండి: పొడవైన అక్షరాలు పై అంతస్తుకు, "
            "తోకలు కింది అంతస్తుకు వెళ్తాయి."
        )
    },
    "zones.tall-twice": {
        "text": (
            "పొడవైన అక్షరాలను చిన్న అక్షరాల కంటే దాదాపు రెండింతలు "
            "ఎత్తుగా రాయండి."
        )
    },
    "line.feel-the-line": {
        "text": "ప్రతి చిన్న అక్షరం అడుగున పెన్సిల్ గీతను తాకేలా రాయండి."
    },
    "line.dark-line": {
        "text": (
            "తెల్ల కాగితం కింద ముదురు గీతల కాగితం పెట్టండి; గీతలు పైకి "
            "కనిపిస్తాయి."
        )
    },
    "space.finger-or-pencil": {
        "text": "పిల్లలకు ఒక వేలు లేదా పెన్సిల్ వెడల్పు మంచి ఖాళీ."
    },
    "space.read-aloud": {
        "text": "ఖాళీలు సరిగ్గా ఉంటే, ఆ వరుసను ఆగకుండా పైకి చదవగలరు."
    },
    "letters.no-touching": {
        "text": "పదంలోని అక్షరాలు దగ్గరగా ఉంటాయి, కానీ ఒకదాన్నొకటి తాకవు."
    },
    "letters.same-gap": {
        "text": (
            "తర్వాతి అక్షరం రాసేటప్పుడు, ముందు అక్షరం తర్వాతి ఖాళీని "
            "చూడండి."
        )
    },
    "margin.fold": {
        "text": (
            "కాగితాన్ని పొడవుగా ఒకసారి మడిచి తెరవండి; ఆ మడతే తేలికైన "
            "మార్జిన్."
        )
    },
    "margin.finger-start": {
        "text": (
            "మార్జిన్ దగ్గర ఒక వేలు పెట్టి, ప్రతి వరుసను దాని పక్కనే "
            "మొదలుపెట్టండి."
        )
    },
    "straight.paper-anchor": {
        "text": (
            "మరో చేత్తో కాగితాన్ని పట్టుకోండి; పేజీలో కిందికి వెళ్తున్న "
            "కొద్దీ దాన్ని పైకి జరపండి."
        )
    },
    "straight.look-ahead": {
        "text": "పెన్సిల్\u200cనే కాదు, వరుస చివరను కూడా చూడండి."
    },
    "upright.same-angle": {
        "text": "రాసే ప్రతిసారీ కాగితాన్ని ఒకే వైపు వంచండి."
    },
    "upright.check-stems": {
        "text": "l, d, h ల పొడవైన కాడలను చూడండి: అవి కంచెలా కనిపించాలి."
    },
    "pace.not-too-fast": {
        "text": "అక్షరాలు ఒకేలా కనిపించేంత వేగంతోనే రాయండి."
    },
    "pace.short-bursts": {
        "text": (
            "ఒకేసారి హడావిడిగా ఎక్కువసేపు రాయడం కంటే, చిన్న విడతలుగా "
            "క్రమంగా రాయడం మేలు."
        )
    },
    "pressure.see-the-back": {
        "text": (
            "పేజీ తిప్పి చూడండి: వెనక రాత చేతికి తగిలితే, ఇంకా తేలికగా "
            "నొక్కండి."
        )
    },
    "pressure.soft-pencil": {
        "text": "మెత్తని పెన్సిల్\u200cకు తక్కువ ఒత్తిడి చాలు."
    },
    "flow.plan-the-join": {
        "text": (
            "ఈ అక్షరం పూర్తయ్యే ముందే తర్వాతి అక్షరం ఎక్కడ మొదలవుతుందో "
            "తెలుసుకోండి."
        )
    },
    "flow.relaxed-wrist": {
        "text": "చేతి పక్కభాగాన్ని బల్లపై ఆనించి, మణికట్టును కదలనివ్వండి."
    },
    "lifts.word-at-a-time": {
        "text": "పదం మొత్తం ముందు మనసులో అనుకుని, ఒకేసారి రాయండి."
    },
    "lifts.pause-not-lift": {
        "text": "గీతల మధ్య ఆగండి, కానీ పెన్సిల్\u200cను కాగితంపైనే ఉంచండి."
    },
    "slant.paper-tilt": {
        "text": (
            "కుడిచేతి వాళ్ళు సాధారణంగా కాగితాన్ని కొంచెం ఎడమకు, ఎడమచేతి "
            "వాళ్ళు కొంచెం కుడికి వంచుతారు."
        )
    },
    "slant.pick-one": {
        "text": "నిటారుగా గానీ, వాలుగా గానీ, ఒకటి ఎంచుకుని అదే కొనసాగించండి."
    },
    "read.stranger-test": {
        "text": (
            "తోటి విద్యార్థి అడగకుండానే చదవగలిగితే, రాత స్పష్టంగా " "ఉన్నట్టే."
        )
    },
    "read.fix-one": {
        "text": (
            "అన్నీ ఒకేసారి కాదు; చదివేవారిని ఆపిన ఒక్క నైపుణ్యాన్నే "
            "సరిచేయండి."
        )
    },
    "distinct.close-tops": {
        "text": (
            "a, d, g, q ల పైభాగం మూయండి; అప్పుడు అవి u లేదా c లా " "కనిపించవు."
        )
    },
    "distinct.tall-h": {
        "text": "h, k లను పొడవుగా రాయండి; అప్పుడు వాటిని n లేదా x గా చదవరు."
    },
    "neat.one-line-cross": {
        "text": "గీకి పడేయకుండా, ఒకే నిటారు గీతతో కొట్టేయండి."
    },
    "neat.space-around": {
        "text": "పేరాల మధ్య, పేజీ అంచుల చుట్టూ స్పష్టమైన ఖాళీ వదలండి."
    },
    "spell.say-it": {
        "text": (
            "పదాన్ని నెమ్మదిగా పలుకుతూ, రాసేటప్పుడు ప్రతి శబ్దాన్ని " "వినండి."
        )
    },
    "spell.small-parts": {
        "text": (
            "పొడవైన పదాన్ని చిన్న భాగాలుగా విడదీసి, ఒక్కో భాగం " "నేర్చుకోండి."
        )
    },
}

TRANSLATIONS = {"te": (TELUGU_EXERCISES, TELUGU_TIPS)}


def _all_entries():
    for area in (*FACTORS.values(), SPELLING):
        yield from area["exercises"]
        yield from area["tips"]


def _attach_translations():
    """Give every exercise and tip its ``i18n`` block from TRANSLATIONS."""
    for entry in _all_entries():
        kind = 0 if "steps" in entry else 1
        entry["i18n"] = {
            lang: dict(tables[kind][entry["id"]])
            for lang, tables in TRANSLATIONS.items()
            if entry["id"] in tables[kind]
        }


_attach_translations()


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


def translation_limit(english):
    """How long a translation may be: about 1.5 times the English, with
    room for short titles (Telugu takes more letters than English)."""
    return max(round(1.5 * len(english)), len(english) + 12)


def _translation_problems(entry):
    fields = ("title", "steps", "check") if "steps" in entry else ("text",)
    banned = avoid_pattern()
    found = []
    for lang in LANGUAGES:
        text = entry.get("i18n", {}).get(lang)
        if not text:
            found.append(f"{entry['id']}: no {lang} translation")
            continue
        for field in fields:
            value = text.get(field)
            if not isinstance(value, str) or not value.strip():
                found.append(f"{entry['id']}: {lang} {field} missing")
                continue
            if len(value) > translation_limit(entry[field]):
                found.append(f"{entry['id']}: {lang} {field} too long")
            if EM_DASH in value:
                found.append(f"{entry['id']}: em dash in {lang} {field}")
            if banned.search(value) or any(w in value for w in AVOID_WORDS_TE):
                found.append(f"{entry['id']}: avoid word in {lang} {field}")
        for field in set(text) - set(fields) - {"example"}:
            found.append(f"{entry['id']}: unknown {lang} field {field}")
    return found


def _orphan_translations():
    ids = {entry["id"] for entry in _all_entries()}
    return [
        f"{lang}: translation for unknown id {key}"
        for lang, tables in TRANSLATIONS.items()
        for table in tables
        for key in table
        if key not in ids
    ]


def problems():
    """Every rule the catalogue breaks, as readable lines (none is good)."""
    found = _orphan_translations()
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
            found += _translation_problems(entry)
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
