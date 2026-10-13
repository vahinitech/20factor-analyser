# SPDX-License-Identifier: AGPL-3.0-only
# pylint: disable=too-many-lines
# (data module: the exercises and tips are most of it)
"""The practice catalogue: exercises and tips for every factor.

Practice is data, not renderer code (docs/10-practice-framework.md, approved
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

# Simple English (owner, 2026-10-11): a step is at most three short
# sentences, one action each; no sentence in a step, check or tip runs
# over this many words.
STEP_SENTENCES_MAX = 3
WORDS_PER_SENTENCE_MAX = 14
HELPS_OTHERS_MAX = 3

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

# What a "Copy this" drawing shows (page 2 and page 1's practice box).
# One drawing per kind, made by the report renderer; an exercise names
# the kind that shows what its steps say.
MODELS = (
    "ladder",
    "zones",
    "baseline",
    "gaps",
    "letter-gaps",
    "margin",
    "slant",
    "loops",
    "trace",
    "start-dots",
    "pairs",
    "waves",
    "page",
)

# How much an exercise or tip helps a skill other than its own (its own
# skill is always 1.0): docs/10-practice-framework.md, "Many-to-many
# selection".
HELP_MIN = 0.3
HELP_MAX = 0.8


def _helps(own, others):
    """``{factor: weight}`` with the entry's own factor at 1.0, as the
    catalogue serves it (string keys, as in JSON)."""
    out = {str(own): 1.0} if own else {}
    out.update({str(n): float(w) for n, w in sorted(others.items())})
    return out


def _ex(own, eid, level, look, text, helps=None):
    """One exercise. ``look`` is (title, unit, script, worksheet, model)
    and ``text`` is (steps, example, check)."""
    title, unit, script, sheet, model = look
    steps, example, check = text
    return {
        "id": eid,
        "level": level,
        "title": title,
        "unit": unit,
        "script": script,
        "needs": "pen" if own in PEN_FACTORS else "photo",
        "worksheet": sheet,
        "model": model,
        "helps": _helps(own, helps or {}),
        "steps": steps,
        "example": example,
        "check": check,
    }


def _tip(own, tid, text, helps=None):
    return {"id": tid, "helps": _helps(own, helps or {}), "text": text}


# The spelling row: shown only when the limited spelling check found a
# word, extra to the skill rows. It belongs to no factor, so it helps
# none.
SPELLING = {
    "exercises": (
        _ex(
            0,
            "spell.look-cover-write",
            1,
            ("Look, cover, write", "word", "latin", None, "trace"),
            (
                "Look at the word. Cover it and write it from memory."
                " Then check it.",
                "",
                "My word matches the one I looked at.",
            ),
        ),
    ),
    "tips": (
        _tip(
            0,
            "spell.say-it",
            "Say the word slowly. Listen for each sound as you write.",
        ),
        _tip(
            0,
            "spell.small-parts",
            "Split a long word into small parts. Learn one part at a time.",
        ),
    ),
}

FACTORS = {
    1: {
        "exercises": (
            _ex(
                1,
                "shapes.slow-copy",
                1,
                ("Slow copy", "row", "any", "letter-shapes", "trace"),
                (
                    "Look at the model letters. Copy each letter slowly."
                    " Check it before you write the next one.",
                    "a d g q o",
                    "Each of my letters looks like the model.",
                ),
                {19: 0.6, 3: 0.4},
            ),
            _ex(
                1,
                "shapes.letter-families",
                2,
                (
                    "Round letters",
                    "row",
                    "latin",
                    "letter-shapes",
                    "start-dots",
                ),
                (
                    "Write c a d g q o in one row. Start each letter at the"
                    " same point, like a c.",
                    "c a d g q o",
                    "All my round letters start in the same place.",
                ),
                {3: 0.5, 2: 0.4},
            ),
            _ex(
                1,
                "shapes.trace-then-write",
                3,
                ("Trace, then write", "word", "any", "letter-shapes", "trace"),
                (
                    "Trace the grey word once. Then write it two times on"
                    " your own.",
                    "garden",
                    "My own word is as clear as the traced one.",
                ),
                {19: 0.4},
            ),
        ),
        "tips": (
            _tip(
                1,
                "shapes.start-at-top",
                "Start most letters at the top. Then they come out the same"
                " each time.",
                {2: 0.6},
            ),
            _tip(
                1,
                "shapes.slow-is-clear",
                "Write one line slowly. Neat first, fast later.",
                {4: 0.4},
            ),
        ),
    },
    2: {
        "exercises": (
            _ex(
                2,
                "order.say-the-strokes",
                1,
                ("Say the strokes", "letter", "any", None, "start-dots"),
                (
                    "Write b, d and p slowly. Say each stroke out loud: down,"
                    " up, round.",
                    "b d p",
                    "I started each letter at the top.",
                ),
                {1: 0.5},
            ),
            _ex(
                2,
                "order.start-dots",
                2,
                ("Start dots", "row", "any", None, "start-dots"),
                (
                    "Put a small dot where each letter starts. Start every"
                    " letter on its dot.",
                    "a b c d e",
                    "Every letter began on its dot.",
                ),
                {1: 0.5, 5: 0.3},
            ),
        ),
        "tips": (
            _tip(
                2,
                "order.top-down",
                "Pull your strokes down. Down strokes are easier to control.",
                {4: 0.5},
            ),
            _tip(
                2,
                "order.same-every-time",
                "Start a letter in the same place every time, even when you"
                " are quick.",
                {1: 0.6},
            ),
        ),
    },
    3: {
        "exercises": (
            _ex(
                3,
                "loops.close-the-circle",
                1,
                ("Close the circle", "row", "any", "letter-shapes", "loops"),
                (
                    "Write a row of o and a. Bring each round back to where"
                    " it started. Leave no gap.",
                    "o a o a o a",
                    "Every round letter is closed.",
                ),
                {19: 0.6, 1: 0.5},
            ),
            _ex(
                3,
                "loops.gap-hunt",
                2,
                ("Gap hunt", "sentence", "any", "letter-shapes", "loops"),
                (
                    "Write one sentence. Look for an open a, d, g or o."
                    " Write that word again.",
                    "a good dog",
                    "No a looks like a u.",
                ),
                {19: 0.6},
            ),
            _ex(
                3,
                "loops.tall-loops",
                3,
                ("Tall loops", "row", "latin", None, "loops"),
                (
                    "Write l, b and k in joined writing. Keep each loop thin"
                    " and closed.",
                    "l b k l b k",
                    "My loops are closed and the same size.",
                ),
                {6: 0.5},
            ),
        ),
        "tips": (
            _tip(
                3,
                "loops.close-the-door",
                "A round letter is like a door. Close it before you go on.",
                {19: 0.5},
            ),
            _tip(
                3,
                "loops.go-back-over",
                "For a and d, go back over the top before the tail.",
                {19: 0.6},
            ),
        ),
    },
    4: {
        "exercises": (
            _ex(
                4,
                "strokes.long-lines",
                1,
                ("Smooth lines", "row", "any", "smooth-strokes", "waves"),
                (
                    "Draw slow straight lines across the page. Then draw"
                    " gentle waves. Do not lift the pencil.",
                    "",
                    "My lines are smooth, with no wobbles.",
                ),
                {7: 0.3},
            ),
            _ex(
                4,
                "strokes.light-grip",
                2,
                ("Light grip", "row", "any", "smooth-strokes", "trace"),
                (
                    "Hold the pencil gently. Write l and c slowly. Relax your"
                    " hand after each letter.",
                    "l c l c l c",
                    "Each stroke is one clean line.",
                ),
                {1: 0.4},
            ),
        ),
        "tips": (
            _tip(
                4,
                "strokes.relax-grip",
                "If your fingers go white, hold the pencil more gently."
                " Shake out your hand.",
            ),
            _tip(
                4,
                "strokes.sharp-pencil",
                "Use a sharp pencil or a smooth pen. Lines come out cleaner.",
                {1: 0.3},
            ),
        ),
    },
    5: {
        "exercises": (
            _ex(
                5,
                "size.two-line-ladder",
                1,
                ("Two-line ladder", "row", "any", "letter-size", "ladder"),
                (
                    "Draw two light lines, a little apart. Write a o e c n m"
                    " between them. Each letter touches both lines.",
                    "a o e c n m",
                    "All my small letters touch both lines.",
                ),
                {6: 0.6},
            ),
            _ex(
                5,
                "size.size-twins",
                2,
                ("Size twins", "row", "latin", "letter-size", "ladder"),
                (
                    "Write moon and came. Make all the small letters the same"
                    " height.",
                    "moon came",
                    "My small letters are all one height.",
                ),
                {1: 0.3, 9: 0.3},
            ),
            _ex(
                5,
                "size.fade-the-guide",
                3,
                (
                    "Lines, then no lines",
                    "sentence",
                    "any",
                    "letter-size",
                    "ladder",
                ),
                (
                    "Write a sentence between two lines. Then write it again"
                    " on plain paper.",
                    "we can see the sea",
                    "My letters stayed the same size without lines.",
                ),
                {7: 0.5},
            ),
        ),
        "tips": (
            _tip(
                5,
                "size.match-the-x",
                "Make every small letter as tall as the first o.",
            ),
            _tip(
                5,
                "size.paper-close",
                "Keep the paper in front of you. Letters grow when your hand"
                " reaches far.",
                {11: 0.4},
            ),
        ),
    },
    6: {
        "exercises": (
            _ex(
                6,
                "zones.tall-and-tails",
                1,
                ("Tall and tails", "row", "latin", "letter-size", "zones"),
                (
                    "Write h, l, g and y. Make h and l tall. Let g and y hang"
                    " below the line.",
                    "h l g y",
                    "Tall letters go up and tails go down.",
                ),
                {5: 0.6},
            ),
            _ex(
                6,
                "zones.three-zones",
                2,
                ("Three floors", "word", "latin", "letter-size", "zones"),
                (
                    "Use paper with four lines. Write jelly and baby. Put"
                    " each part of a letter on its floor.",
                    "jelly baby",
                    "Each part of every letter is on its floor.",
                ),
                {5: 0.6, 7: 0.4},
            ),
        ),
        "tips": (
            _tip(
                6,
                "zones.three-floors",
                "Tall letters go up to the top floor. Tails go down to the"
                " basement.",
                {5: 0.4},
            ),
            _tip(
                6,
                "zones.tall-twice",
                "Make tall letters about two times as tall as small ones.",
                {5: 0.5},
            ),
        ),
    },
    7: {
        "exercises": (
            _ex(
                7,
                "line.sit-on-the-line",
                1,
                ("Sit on the line", "sentence", "any", "baseline", "baseline"),
                (
                    "Write one sentence on a line. Circle any letter that"
                    " floats up or drops down. Write that word again.",
                    "keep words on the line",
                    "Every letter sits on the line.",
                ),
                {11: 0.6, 5: 0.3},
            ),
            _ex(
                7,
                "line.underline-check",
                2,
                ("Ruler check", "sentence", "any", "baseline", "baseline"),
                (
                    "Write a sentence. Draw a ruler line under it. Look for"
                    " letters that do not touch the line.",
                    "the sun is up",
                    "My letters touch the ruler line.",
                ),
                {11: 0.5},
            ),
            _ex(
                7,
                "line.highlight-the-line",
                3,
                ("Bold writing line", "line", "any", "baseline", "baseline"),
                (
                    "Go over the writing line in colour. Write two lines on"
                    " it.",
                    "",
                    "My words stay on the coloured line.",
                ),
                {11: 0.6},
            ),
        ),
        "tips": (
            _tip(
                7,
                "line.feel-the-line",
                "Let each small letter touch the line at the bottom.",
                {5: 0.3},
            ),
            _tip(
                7,
                "line.dark-line",
                "On plain paper, put a lined sheet under it. The lines show"
                " through.",
                {11: 0.6},
            ),
        ),
    },
    8: {
        "exercises": (
            _ex(
                8,
                "space.finger-spaces",
                1,
                ("Finger spaces", "sentence", "any", "word-spacing", "gaps"),
                (
                    "Write a short sentence. After each word, put one finger"
                    " on the page. Start the next word after your finger.",
                    "I like to read",
                    "My gaps are about one finger wide.",
                ),
                {9: 0.4},
            ),
            _ex(
                8,
                "space.dot-the-gaps",
                2,
                ("Dot the gaps", "sentence", "any", "word-spacing", "gaps"),
                (
                    "Copy the cat sat on a mat. Put a small dot in each gap."
                    " Make the dots the same distance apart.",
                    "the cat sat on a mat",
                    "All my gaps are the same size.",
                ),
                {9: 0.3},
            ),
            _ex(
                8,
                "space.spaced-copy",
                3,
                ("Copy with gaps", "sentence", "any", "word-spacing", "gaps"),
                (
                    "Copy two lines from a book. Keep the same gaps as the"
                    " book. Do not use your finger.",
                    "",
                    "Someone can read my lines quickly.",
                ),
                {9: 0.5},
            ),
        ),
        "tips": (
            _tip(
                8,
                "space.finger-or-pencil",
                "A gap as wide as your finger or a pencil is just right.",
            ),
            _tip(
                8,
                "space.read-aloud",
                "Read your line out loud. Good gaps make it easy.",
                {9: 0.3},
            ),
        ),
    },
    9: {
        "exercises": (
            _ex(
                9,
                "letters.room-to-breathe",
                1,
                (
                    "Room inside words",
                    "word",
                    "any",
                    "word-spacing",
                    "letter-gaps",
                ),
                (
                    "Write the word letter. Leave the same small gap between"
                    " each letter.",
                    "letter",
                    "No letters touch or squeeze together.",
                ),
                {8: 0.4},
            ),
            _ex(
                9,
                "letters.even-rows",
                2,
                (
                    "Even letter gaps",
                    "row",
                    "any",
                    "word-spacing",
                    "letter-gaps",
                ),
                (
                    "Write minim in one row. Make the gaps inside the word"
                    " look the same.",
                    "minim",
                    "My letters are spread out evenly.",
                ),
                {5: 0.3, 1: 0.3},
            ),
        ),
        "tips": (
            _tip(
                9,
                "letters.no-touching",
                "Letters in a word sit close, but they do not touch.",
            ),
            _tip(
                9,
                "letters.same-gap",
                "Look at the last gap before you write the next letter.",
                {8: 0.3},
            ),
        ),
    },
    10: {
        "exercises": (
            _ex(
                10,
                "margin.start-at-the-margin",
                1,
                (
                    "Start at the margin",
                    "line",
                    "any",
                    "page-layout",
                    "margin",
                ),
                (
                    "Draw a light line down the left side. Start three lines"
                    " right next to it.",
                    "",
                    "All my lines start at the margin.",
                ),
                {12: 0.3},
            ),
            _ex(
                10,
                "margin.plan-the-line",
                2,
                ("Plan the line end", "line", "any", "page-layout", "margin"),
                (
                    "Look at the right edge before a long word. If it will"
                    " not fit, start it on the next line.",
                    "",
                    "No word is squeezed at the right edge.",
                ),
                {8: 0.3},
            ),
        ),
        "tips": (
            _tip(
                10,
                "margin.fold",
                "Fold the paper once and open it. The fold makes a margin.",
            ),
            _tip(
                10,
                "margin.finger-start",
                "Put a finger on the margin. Start each line next to it.",
                {12: 0.3},
            ),
        ),
    },
    11: {
        "exercises": (
            _ex(
                11,
                "straight.level-sentence",
                1,
                ("Level sentence", "sentence", "any", "baseline", "baseline"),
                (
                    "Write a sentence on a ruled line. Keep it level all the"
                    " way to the end.",
                    "we walk to school",
                    "My line does not go up or down at the end.",
                ),
                {7: 0.6},
            ),
            _ex(
                11,
                "straight.paper-position",
                2,
                ("Steady paper", "line", "any", "baseline", "baseline"),
                (
                    "Hold the paper with your other hand. Write two lines"
                    " without moving it.",
                    "",
                    "My lines are straighter than before.",
                ),
                {17: 0.4, 7: 0.4},
            ),
        ),
        "tips": (
            _tip(
                11,
                "straight.paper-anchor",
                "Hold the paper with your other hand. Move it up as you go"
                " down the page.",
                {7: 0.4},
            ),
            _tip(
                11,
                "straight.look-ahead",
                "Look at the end of the line, not only at your pencil.",
            ),
        ),
    },
    12: {
        "exercises": (
            _ex(
                12,
                "upright.tall-strokes",
                1,
                ("Matching tall strokes", "row", "latin", "baseline", "slant"),
                (
                    "Write l and h in a row. Keep all the tall lines leaning"
                    " the same way.",
                    "l h l h l h",
                    "All my tall lines point the same way.",
                ),
                {17: 0.6},
            ),
            _ex(
                12,
                "upright.line-up",
                2,
                ("Line up the starts", "line", "any", "baseline", "margin"),
                (
                    "Write three short lines. Start each one right under the"
                    " line above.",
                    "",
                    "My line starts make a straight edge.",
                ),
                {10: 0.6},
            ),
        ),
        "tips": (
            _tip(
                12,
                "upright.same-angle",
                "Tilt your paper the same way every time.",
                {17: 0.6},
            ),
            _tip(
                12,
                "upright.check-stems",
                "Look at the tall lines of l, d and h. They should look like"
                " a fence.",
                {17: 0.5},
            ),
        ),
    },
    13: {
        "exercises": (
            _ex(
                13,
                "pace.steady-count",
                1,
                ("Steady count", "row", "any", None, "trace"),
                (
                    "Clap a slow, even beat. Write one letter on each beat.",
                    "a a a a a",
                    "My letters stayed the same as I kept the beat.",
                ),
                {1: 0.3},
            ),
        ),
        "tips": (
            _tip(
                13,
                "pace.not-too-fast",
                "Write only as fast as your letters still look the same.",
                {1: 0.4},
            ),
            _tip(
                13,
                "pace.short-bursts",
                "Write in short, regular bursts. Do not rush one long one.",
            ),
        ),
    },
    14: {
        "exercises": (
            _ex(
                14,
                "pressure.light-dark-light",
                1,
                ("Light touch", "row", "any", None, "waves"),
                (
                    "Write a row pressing lightly. Then write a row pressing"
                    " as usual. Keep the light one.",
                    "o o o o",
                    "My line is the same darkness all the way.",
                ),
                {4: 0.5},
            ),
        ),
        "tips": (
            _tip(
                14,
                "pressure.see-the-back",
                "Turn the page over. If you can feel the writing, press more"
                " lightly.",
            ),
            _tip(
                14,
                "pressure.soft-pencil",
                "A soft pencil needs less pressure.",
                {4: 0.3},
            ),
        ),
    },
    15: {
        "exercises": (
            _ex(
                15,
                "flow.joined-pairs",
                1,
                ("Joined pairs", "row", "latin", "smooth-strokes", "trace"),
                (
                    "Write in, an and un in joined writing. Keep the pencil"
                    " on the paper in each pair.",
                    "in an un",
                    "My pencil stayed down inside each pair.",
                ),
                {4: 0.5},
            ),
        ),
        "tips": (
            _tip(
                15,
                "flow.plan-the-join",
                "Know where the next letter starts before you finish this"
                " one.",
            ),
            _tip(
                15,
                "flow.relaxed-wrist",
                "Rest the side of your hand on the table. Let your wrist"
                " move.",
                {4: 0.5},
            ),
        ),
    },
    16: {
        "exercises": (
            _ex(
                16,
                "lifts.one-lift-words",
                1,
                ("One-lift words", "word", "latin", None, "trace"),
                (
                    "Write short words. Lift the pencil only at the end of"
                    " each word.",
                    "mum run",
                    "I lifted my pencil only at the end.",
                ),
                {15: 0.6},
            ),
        ),
        "tips": (
            _tip(
                16,
                "lifts.word-at-a-time",
                "Think of the whole word. Then write it in one go.",
                {15: 0.4},
            ),
            _tip(
                16,
                "lifts.pause-not-lift",
                "To pause, keep the pencil on the paper.",
                {15: 0.4},
            ),
        ),
    },
    17: {
        "exercises": (
            _ex(
                17,
                "slant.same-lean",
                1,
                ("Same lean", "row", "latin", "slant", "slant"),
                (
                    "Write m, i and n slowly. Make them all lean the same"
                    " way.",
                    "m i n m i n",
                    "All my letters lean the same way.",
                ),
                {12: 0.6},
            ),
            _ex(
                17,
                "slant.slant-lines",
                2,
                ("Slant guides", "line", "latin", "slant", "slant"),
                (
                    "Draw light slanted lines across the row. Write two"
                    " lines. Follow the slanted lines.",
                    "",
                    "My down strokes follow the guides.",
                ),
                {12: 0.6},
            ),
        ),
        "tips": (
            _tip(
                17,
                "slant.paper-tilt",
                "Right-handers tilt the paper a little left. Left-handers"
                " tilt it a little right.",
                {12: 0.5},
            ),
            _tip(
                17,
                "slant.pick-one",
                "Straight up or leaning: pick one and keep it.",
                {12: 0.5},
            ),
        ),
    },
    18: {
        "exercises": (
            _ex(
                18,
                "read.read-it-back",
                1,
                ("Read it back", "sentence", "any", None, "page"),
                (
                    "Write two sentences. Ask someone to read them out loud."
                    " Write again any word they stopped at.",
                    "",
                    "They read every word the first time.",
                ),
                {1: 0.5, 8: 0.5},
            ),
            _ex(
                18,
                "read.slow-best",
                2,
                ("Best writing", "line", "any", None, "page"),
                (
                    "Write two lines very slowly and clearly. Put them next"
                    " to your usual writing.",
                    "",
                    "I can see which words got easier to read.",
                ),
                {1: 0.5, 5: 0.4},
            ),
        ),
        "tips": (
            _tip(
                18,
                "read.stranger-test",
                "If a friend can read it without asking, it is easy to read.",
            ),
            _tip(
                18,
                "read.fix-one",
                "Work on one skill at a time, not everything at once.",
            ),
        ),
    },
    19: {
        "exercises": (
            _ex(
                19,
                "distinct.look-alike-pairs",
                1,
                (
                    "Look-alike pairs",
                    "row",
                    "latin",
                    "letter-distinction",
                    "pairs",
                ),
                (
                    "Write a next to o. Then write c next to e. Make each one"
                    " easy to tell apart.",
                    "a o c e",
                    "Nobody could mix up my pairs.",
                ),
                {1: 0.6, 3: 0.4},
            ),
            _ex(
                19,
                "distinct.n-and-h",
                2,
                (
                    "n, h, r and u",
                    "row",
                    "latin",
                    "letter-distinction",
                    "pairs",
                ),
                (
                    "Write n h r u in a row. Make h tall and close the top of"
                    " n. Leave u open at the top.",
                    "n h r u",
                    "Each letter looks like itself.",
                ),
                {6: 0.5, 1: 0.4},
            ),
        ),
        "tips": (
            _tip(
                19,
                "distinct.close-tops",
                "Close the top of a, d, g and q. Then they do not look like u"
                " or c.",
                {3: 0.6},
            ),
            _tip(
                19,
                "distinct.tall-h",
                "Make h and k tall, so they do not look like n or x.",
                {6: 0.5},
            ),
        ),
    },
    20: {
        "exercises": (
            _ex(
                20,
                "neat.clean-page",
                1,
                ("Clean page", "page", "any", "page-layout", "page"),
                (
                    "Write a short paragraph with a margin and even gaps. To"
                    " change a word, cross it out with one line.",
                    "",
                    "My page looks tidy from far away.",
                ),
                {10: 0.5, 8: 0.4},
            ),
            _ex(
                20,
                "neat.copy-best",
                2,
                ("Best copy", "line", "any", "page-layout", "page"),
                (
                    "Copy three lines of your own writing. Make the new copy"
                    " neat.",
                    "",
                    "My new copy is neater than the first.",
                ),
                {1: 0.4, 5: 0.4},
            ),
        ),
        "tips": (
            _tip(
                20,
                "neat.one-line-cross",
                "To change a word, cross it out with one straight line.",
            ),
            _tip(
                20,
                "neat.space-around",
                "Leave space between paragraphs and around the edges.",
                {10: 0.5},
            ),
        ),
    },
}


# Telugu (DRAFT WORDING, 2026-10-11: written for this change and not yet
# checked by a native speaker; it must be checked before Telugu reaches
# production). Keyed by exercise or tip id; ``_attach_translations``
# puts each into its entry as ``i18n["te"]``. Latin practice letters and
# words stay as written: the child practises English letters, so no
# example is translated. Rewritten with the simple English of
# 2026-10-11: short sentences, one action each.
TELUGU_EXERCISES = {
    "shapes.slow-copy": {
        "title": "నెమ్మదిగా చూసి రాయడం",
        "steps": (
            "నమూనా అక్షరాలు చూడండి. ఒక్కో అక్షరం నెమ్మదిగా రాయండి. "
            "తర్వాతిది రాసే ముందు చూసుకోండి."
        ),
        "check": "నా ప్రతి అక్షరం నమూనాలాగే ఉంది.",
    },
    "shapes.letter-families": {
        "title": "గుండ్రని అక్షరాలు",
        "steps": (
            "c a d g q o ఒకే వరుసలో రాయండి. ప్రతి అక్షరం c లాగే "
            "ఒకే చోట మొదలుపెట్టండి."
        ),
        "check": "నా గుండ్రని అక్షరాలన్నీ ఒకే చోట మొదలయ్యాయి.",
    },
    "shapes.trace-then-write": {
        "title": "దిద్ది, తర్వాత రాయండి",
        "steps": (
            "బూడిద రంగు పదాన్ని ఒకసారి దిద్దండి. తర్వాత మీరే రెండుసార్లు "
            "రాయండి."
        ),
        "check": "నేను రాసిన పదం దిద్దినంత స్పష్టంగా ఉంది.",
    },
    "order.say-the-strokes": {
        "title": "గీతలు చెప్తూ రాయండి",
        "steps": (
            "b, d, p నెమ్మదిగా రాయండి. ప్రతి గీత పైకి చెప్పండి: కిందికి, "
            "పైకి, గుండ్రంగా."
        ),
        "check": "ప్రతి అక్షరాన్ని పైనుంచి మొదలుపెట్టాను.",
    },
    "order.start-dots": {
        "title": "మొదలు చుక్కలు",
        "steps": (
            "అక్షరం మొదలయ్యే చోట చిన్న చుక్క పెట్టండి. ప్రతి అక్షరం దాని "
            "చుక్క దగ్గర మొదలుపెట్టండి."
        ),
        "check": "ప్రతి అక్షరం దాని చుక్క దగ్గరే మొదలైంది.",
    },
    "loops.close-the-circle": {
        "title": "వలయం మూయండి",
        "steps": (
            "o, a ల వరుస రాయండి. ప్రతి గుండ్రాన్ని మొదలైన చోటికే తీసుకురండి. "
            "ఖాళీ వదలకండి."
        ),
        "check": "ప్రతి గుండ్రని అక్షరం మూసి ఉంది.",
    },
    "loops.gap-hunt": {
        "title": "ఖాళీ వెతకండి",
        "steps": (
            "ఒక వాక్యం రాయండి. తెరిచి ఉన్న a, d, g, o వెతకండి. ఆ పదం మళ్ళీ "
            "రాయండి."
        ),
        "check": "ఏ a కూడా u లాగా కనిపించడం లేదు.",
    },
    "loops.tall-loops": {
        "title": "పొడవైన లూప్‌లు",
        "steps": "l, b, k కలిపి రాయండి. ప్రతి లూప్ సన్నగా, మూసి ఉంచండి.",
        "check": "నా లూప్‌లు మూసి, ఒకే పరిమాణంలో ఉన్నాయి.",
    },
    "strokes.long-lines": {
        "title": "నునుపైన గీతలు",
        "steps": (
            "పేజీ అంతటా నెమ్మదిగా సరళ రేఖలు గీయండి. తర్వాత మెల్లని అలలు "
            "గీయండి. పెన్సిల్ ఎత్తకండి."
        ),
        "check": "నా గీతలు వణకకుండా నునుపుగా ఉన్నాయి.",
    },
    "strokes.light-grip": {
        "title": "తేలికైన పట్టు",
        "steps": (
            "పెన్సిల్‌ను మెల్లగా పట్టుకోండి. l, c నెమ్మదిగా రాయండి. ప్రతి "
            "అక్షరం తర్వాత చేతిని వదులు చేయండి."
        ),
        "check": "ప్రతి గీత ఒకే శుభ్రమైన గీత.",
    },
    "size.two-line-ladder": {
        "title": "రెండు గీతల నిచ్చెన",
        "steps": (
            "కొంచెం దూరంగా రెండు తేలికైన గీతలు గీయండి. వాటి మధ్య a o e c n m "
            "రాయండి. ప్రతి అక్షరం రెండు గీతలనూ తాకాలి."
        ),
        "check": "నా చిన్న అక్షరాలన్నీ రెండు గీతలనూ తాకుతున్నాయి.",
    },
    "size.size-twins": {
        "title": "ఒకే ఎత్తు జంటలు",
        "steps": "moon, came రాయండి. చిన్న అక్షరాలన్నీ ఒకే ఎత్తులో ఉంచండి.",
        "check": "నా చిన్న అక్షరాలన్నీ ఒకే ఎత్తు.",
    },
    "size.fade-the-guide": {
        "title": "గీతలతో, తర్వాత గీతలు లేకుండా",
        "steps": (
            "రెండు గీతల మధ్య ఒక వాక్యం రాయండి. తర్వాత అదే వాక్యం ఖాళీ "
            "కాగితంపై రాయండి."
        ),
        "check": "గీతలు లేకపోయినా నా అక్షరాలు అదే ఎత్తులో ఉన్నాయి.",
    },
    "zones.tall-and-tails": {
        "title": "పొడవు, తోకలు",
        "steps": (
            "h, l, g, y రాయండి. h, l పొడవుగా రాయండి. g, y గీత కిందికి "
            "వేలాడనివ్వండి."
        ),
        "check": "పొడవు అక్షరాలు పైకి, తోకలు కిందికి వెళ్ళాయి.",
    },
    "zones.three-zones": {
        "title": "మూడు అంతస్తులు",
        "steps": (
            "నాలుగు గీతల కాగితం వాడండి. jelly, baby రాయండి. అక్షరం ప్రతి భాగం "
            "దాని అంతస్తులో ఉంచండి."
        ),
        "check": "ప్రతి అక్షరం ప్రతి భాగం దాని అంతస్తులో ఉంది.",
    },
    "line.sit-on-the-line": {
        "title": "గీతపై కూర్చోండి",
        "steps": (
            "గీతపై ఒక వాక్యం రాయండి. పైకి తేలిన లేదా కిందికి జారిన అక్షరానికి "
            "సున్నా చుట్టండి. ఆ పదం మళ్ళీ రాయండి."
        ),
        "check": "ప్రతి అక్షరం గీతపై కూర్చుంది.",
    },
    "line.underline-check": {
        "title": "స్కేలు గీత పరీక్ష",
        "steps": (
            "ఒక వాక్యం రాయండి. దాని కింద స్కేలుతో గీత గీయండి. గీతను తాకని "
            "అక్షరాలు వెతకండి."
        ),
        "check": "నా అక్షరాలు స్కేలు గీతను తాకుతున్నాయి.",
    },
    "line.highlight-the-line": {
        "title": "ముదురు రాత గీత",
        "steps": "రాత గీతపై రంగుతో దిద్దండి. దానిపై రెండు వరుసలు రాయండి.",
        "check": "నా పదాలు రంగు గీతపైనే ఉన్నాయి.",
    },
    "space.finger-spaces": {
        "title": "వేలి ఖాళీలు",
        "steps": (
            "ఒక చిన్న వాక్యం రాయండి. ప్రతి పదం తర్వాత ఒక వేలు పెట్టండి. వేలి "
            "తర్వాత తదుపరి పదం మొదలుపెట్టండి."
        ),
        "check": "నా ఖాళీలు సుమారు ఒక వేలు వెడల్పు.",
    },
    "space.dot-the-gaps": {
        "title": "ఖాళీలకు చుక్కలు",
        "steps": (
            "the cat sat on a mat రాయండి. ప్రతి ఖాళీలో చిన్న చుక్క పెట్టండి. "
            "చుక్కల మధ్య దూరం ఒకేలా ఉంచండి."
        ),
        "check": "నా ఖాళీలన్నీ ఒకే పరిమాణం.",
    },
    "space.spaced-copy": {
        "title": "ఖాళీలతో రాయండి",
        "steps": (
            "పుస్తకం నుంచి రెండు వరుసలు రాయండి. పుస్తకంలో లాగే ఖాళీలు ఉంచండి. "
            "వేలు వాడకండి."
        ),
        "check": "నా వరుసలను ఎవరైనా త్వరగా చదవగలరు.",
    },
    "letters.room-to-breathe": {
        "title": "పదం లోపల చోటు",
        "steps": (
            "letter అనే పదం రాయండి. ప్రతి అక్షరం మధ్య ఒకే చిన్న ఖాళీ ఉంచండి."
        ),
        "check": "ఏ అక్షరాలూ తాకడం లేదు, ఇరుకుగా లేవు.",
    },
    "letters.even-rows": {
        "title": "సమానమైన అక్షర ఖాళీలు",
        "steps": "minim ఒక వరుసలో రాయండి. పదం లోపలి ఖాళీలు ఒకేలా ఉంచండి.",
        "check": "నా అక్షరాలు సమానంగా పరుచుకున్నాయి.",
    },
    "margin.start-at-the-margin": {
        "title": "మార్జిన్ దగ్గర మొదలు",
        "steps": (
            "ఎడమ వైపు కిందికి తేలికైన గీత గీయండి. దాని పక్కనే మూడు వరుసలు "
            "మొదలుపెట్టండి."
        ),
        "check": "నా వరుసలన్నీ మార్జిన్ దగ్గర మొదలయ్యాయి.",
    },
    "margin.plan-the-line": {
        "title": "వరుస చివర ముందే చూడండి",
        "steps": (
            "పొడవైన పదం ముందు కుడి అంచు చూడండి. సరిపోకపోతే తర్వాతి వరుసలో "
            "మొదలుపెట్టండి."
        ),
        "check": "కుడి అంచు దగ్గర ఏ పదమూ ఇరుకుగా లేదు.",
    },
    "straight.level-sentence": {
        "title": "సమతలంగా వాక్యం",
        "steps": (
            "గీత ఉన్న కాగితంపై ఒక వాక్యం రాయండి. చివరి వరకు సమతలంగా ఉంచండి."
        ),
        "check": "నా వరుస చివరలో పైకి గానీ కిందికి గానీ వెళ్ళలేదు.",
    },
    "straight.paper-position": {
        "title": "కదలని కాగితం",
        "steps": (
            "కాగితాన్ని మరో చేత్తో పట్టుకోండి. కదపకుండా రెండు వరుసలు రాయండి."
        ),
        "check": "నా వరుసలు ఇంతకుముందు కంటే నిటారుగా ఉన్నాయి.",
    },
    "upright.tall-strokes": {
        "title": "ఒకేలా పొడవు గీతలు",
        "steps": "l, h వరుసగా రాయండి. పొడవు గీతలన్నీ ఒకే వైపు వాలేలా ఉంచండి.",
        "check": "నా పొడవు గీతలన్నీ ఒకే వైపు చూపుతున్నాయి.",
    },
    "upright.line-up": {
        "title": "మొదళ్ళు వరుసలో",
        "steps": (
            "మూడు చిన్న వరుసలు రాయండి. ప్రతిది పై వరుస కిందే మొదలుపెట్టండి."
        ),
        "check": "నా వరుసల మొదళ్ళు ఒక సరళ అంచులా ఉన్నాయి.",
    },
    "pace.steady-count": {
        "title": "స్థిరమైన లెక్క",
        "steps": (
            "నెమ్మదిగా, సమానంగా చప్పట్లు కొట్టండి. ప్రతి చప్పట్టుకు ఒక అక్షరం "
            "రాయండి."
        ),
        "check": "తాళం వేస్తూ కూడా నా అక్షరాలు ఒకేలా ఉన్నాయి.",
    },
    "pressure.light-dark-light": {
        "title": "తేలికైన స్పర్శ",
        "steps": (
            "తేలికగా నొక్కి ఒక వరుస రాయండి. తర్వాత మామూలుగా ఒక వరుస రాయండి. "
            "తేలికైనదే కొనసాగించండి."
        ),
        "check": "నా గీత మొత్తం ఒకే ముదురుగా ఉంది.",
    },
    "flow.joined-pairs": {
        "title": "కలిపిన జంటలు",
        "steps": (
            "in, an, un కలిపి రాయండి. ప్రతి జంటలో పెన్సిల్ కాగితంపైనే ఉంచండి."
        ),
        "check": "ప్రతి జంటలో నా పెన్సిల్ కిందే ఉంది.",
    },
    "lifts.one-lift-words": {
        "title": "ఒకేసారి ఎత్తే పదాలు",
        "steps": "చిన్న పదాలు రాయండి. ప్రతి పదం చివరే పెన్సిల్ ఎత్తండి.",
        "check": "నేను చివరలో మాత్రమే పెన్సిల్ ఎత్తాను.",
    },
    "slant.same-lean": {
        "title": "ఒకే వాలు",
        "steps": "m, i, n నెమ్మదిగా రాయండి. అన్నీ ఒకే వైపు వాలేలా రాయండి.",
        "check": "నా అక్షరాలన్నీ ఒకే వైపు వాలాయి.",
    },
    "slant.slant-lines": {
        "title": "వాలు గీతలు",
        "steps": (
            "వరుస అంతటా తేలికైన వాలు గీతలు గీయండి. రెండు వరుసలు రాయండి. వాలు "
            "గీతలను అనుసరించండి."
        ),
        "check": "నా కిందికి గీతలు మార్గదర్శక గీతలను అనుసరించాయి.",
    },
    "read.read-it-back": {
        "title": "చదివి చూడండి",
        "steps": (
            "రెండు వాక్యాలు రాయండి. ఎవరినైనా పైకి చదవమనండి. వారు ఆగిన పదం "
            "మళ్ళీ రాయండి."
        ),
        "check": "వారు ప్రతి పదం మొదటిసారే చదివారు.",
    },
    "read.slow-best": {
        "title": "మీ ఉత్తమ రాత",
        "steps": (
            "రెండు వరుసలు చాలా నెమ్మదిగా, స్పష్టంగా రాయండి. మీ మామూలు రాత "
            "పక్కన పెట్టండి."
        ),
        "check": "ఏ పదాలు చదవడం సులువయ్యాయో చూడగలను.",
    },
    "distinct.look-alike-pairs": {
        "title": "ఒకేలా కనిపించే జంటలు",
        "steps": (
            "o పక్కన a రాయండి. తర్వాత e పక్కన c రాయండి. ప్రతి జంట సులువుగా "
            "వేరుగా తెలియాలి."
        ),
        "check": "నా జంటలను ఎవరూ కలగలపలేరు.",
    },
    "distinct.n-and-h": {
        "title": "n, h, r, u అక్షరాలు",
        "steps": (
            "n h r u వరుసగా రాయండి. h పొడవుగా, n పైభాగం మూసి రాయండి. u పైన "
            "తెరిచి ఉంచండి."
        ),
        "check": "ప్రతి అక్షరం దానిలాగే కనిపిస్తోంది.",
    },
    "neat.clean-page": {
        "title": "శుభ్రమైన పేజీ",
        "steps": (
            "మార్జిన్, సమాన ఖాళీలతో ఒక చిన్న పేరా రాయండి. పదం మార్చాలంటే ఒక "
            "గీతతో కొట్టేయండి."
        ),
        "check": "దూరం నుంచి నా పేజీ చక్కగా కనిపిస్తోంది.",
    },
    "neat.copy-best": {
        "title": "చక్కని ప్రతి",
        "steps": (
            "మీ రాతలో మూడు వరుసలు మళ్ళీ రాయండి. కొత్త ప్రతి చక్కగా రాయండి."
        ),
        "check": "నా కొత్త ప్రతి మొదటిదానికంటే చక్కగా ఉంది.",
    },
    "spell.look-cover-write": {
        "title": "చూడండి, మూయండి, రాయండి",
        "steps": (
            "పదాన్ని చూడండి. మూసి, గుర్తు నుంచి రాయండి. తర్వాత సరిచూసుకోండి."
        ),
        "check": "నేను రాసిన పదం చూసిన పదంలాగే ఉంది.",
    },
}

TELUGU_TIPS = {
    "shapes.start-at-top": {
        "text": (
            "చాలా అక్షరాలు పైనుంచి మొదలుపెట్టండి. అప్పుడు ప్రతిసారీ ఒకేలా "
            "వస్తాయి."
        )
    },
    "shapes.slow-is-clear": {
        "text": "ఒక వరుస నెమ్మదిగా రాయండి. ముందు చక్కగా, వేగం తర్వాత."
    },
    "order.top-down": {
        "text": "గీతలను కిందికి లాగండి. కిందికి గీతలు సులువుగా అదుపులో ఉంటాయి."
    },
    "order.same-every-time": {
        "text": "త్వరగా రాసినా, అక్షరం ప్రతిసారీ ఒకే చోట మొదలుపెట్టండి."
    },
    "loops.close-the-door": {
        "text": (
            "గుండ్రని అక్షరం ఒక తలుపు లాంటిది. ముందుకు వెళ్ళే ముందు మూయండి."
        )
    },
    "loops.go-back-over": {
        "text": "a, d కి తోక ముందు పైభాగం మీదుగా వెనక్కి వెళ్ళండి."
    },
    "strokes.relax-grip": {
        "text": (
            "వేళ్ళు తెల్లబడితే పెన్సిల్ మెల్లగా పట్టుకోండి. చేతిని "
            "విదిలించండి."
        )
    },
    "strokes.sharp-pencil": {
        "text": (
            "చెక్కిన పెన్సిల్ లేదా నునుపైన పెన్ వాడండి. గీతలు శుభ్రంగా "
            "వస్తాయి."
        )
    },
    "size.match-the-x": {
        "text": "ప్రతి చిన్న అక్షరం మొదటి o అంత ఎత్తు ఉంచండి."
    },
    "size.paper-close": {
        "text": "కాగితం మీ ముందే ఉంచండి. చేయి దూరం చాపితే అక్షరాలు పెరుగుతాయి."
    },
    "zones.three-floors": {
        "text": (
            "పొడవు అక్షరాలు పై అంతస్తుకు వెళ్తాయి. తోకలు కింది అంతస్తుకు "
            "వెళ్తాయి."
        )
    },
    "zones.tall-twice": {
        "text": "పొడవు అక్షరాలు చిన్నవాటికంటే సుమారు రెండింతలు ఉంచండి."
    },
    "line.feel-the-line": {
        "text": "ప్రతి చిన్న అక్షరం కింద గీతను తాకనివ్వండి."
    },
    "line.dark-line": {
        "text": "ఖాళీ కాగితం కింద గీతల కాగితం పెట్టండి. గీతలు కనిపిస్తాయి."
    },
    "space.finger-or-pencil": {
        "text": "వేలు లేదా పెన్సిల్ వెడల్పు ఖాళీ సరిగ్గా సరిపోతుంది."
    },
    "space.read-aloud": {
        "text": "మీ వరుసను పైకి చదవండి. మంచి ఖాళీలు చదవడం సులువు చేస్తాయి."
    },
    "letters.no-touching": {
        "text": "పదంలో అక్షరాలు దగ్గరగా ఉంటాయి, కానీ తాకవు."
    },
    "letters.same-gap": {"text": "తర్వాతి అక్షరం ముందు చివరి ఖాళీని చూడండి."},
    "margin.fold": {
        "text": "కాగితాన్ని ఒకసారి మడిచి తెరవండి. మడత మార్జిన్ అవుతుంది."
    },
    "margin.finger-start": {
        "text": (
            "మార్జిన్‌పై వేలు పెట్టండి. ప్రతి వరుస దాని పక్కనే మొదలుపెట్టండి."
        )
    },
    "straight.paper-anchor": {
        "text": (
            "కాగితాన్ని మరో చేత్తో పట్టుకోండి. కిందికి వెళ్తూ దాన్ని పైకి "
            "జరపండి."
        )
    },
    "straight.look-ahead": {
        "text": "పెన్సిల్‌నే కాదు, వరుస చివరను కూడా చూడండి."
    },
    "upright.same-angle": {"text": "ప్రతిసారీ కాగితాన్ని ఒకేలా వంచండి."},
    "upright.check-stems": {
        "text": "l, d, h పొడవు గీతలు చూడండి. అవి కంచెలా కనిపించాలి."
    },
    "pace.not-too-fast": {"text": "అక్షరాలు ఒకేలా ఉండేంత వేగంతోనే రాయండి."},
    "pace.short-bursts": {
        "text": "చిన్న, క్రమమైన విడతల్లో రాయండి. ఒకేసారి తొందరపడకండి."
    },
    "pressure.see-the-back": {
        "text": "పేజీ తిప్పండి. రాత వెనక తగిలితే తేలికగా నొక్కండి."
    },
    "pressure.soft-pencil": {
        "text": "మెత్తని పెన్సిల్‌కు తక్కువ ఒత్తిడి చాలు."
    },
    "flow.plan-the-join": {
        "text": "ఈ అక్షరం ముగించే ముందే తర్వాతిది ఎక్కడ మొదలో తెలుసుకోండి."
    },
    "flow.relaxed-wrist": {
        "text": "చేతి పక్కభాగం బల్లపై ఆనించండి. మణికట్టు కదలనివ్వండి."
    },
    "lifts.word-at-a-time": {
        "text": "పదం మొత్తం ఆలోచించండి. తర్వాత ఒకేసారి రాయండి."
    },
    "lifts.pause-not-lift": {"text": "ఆగాలంటే పెన్సిల్ కాగితంపైనే ఉంచండి."},
    "slant.paper-tilt": {
        "text": (
            "కుడిచేతి వారు కాగితం కొంచెం ఎడమకు, ఎడమచేతి వారు కొంచెం కుడికి "
            "వంచండి."
        )
    },
    "slant.pick-one": {
        "text": "నిటారుగా లేదా వాలుగా: ఒకటి ఎంచుకుని అదే ఉంచండి."
    },
    "read.stranger-test": {
        "text": "అడగకుండా స్నేహితులు చదవగలిగితే, అది చదవడం సులువు."
    },
    "read.fix-one": {
        "text": "ఒకేసారి అన్నీ కాదు, ఒక్కో నైపుణ్యం మీద పని చేయండి."
    },
    "distinct.close-tops": {
        "text": "a, d, g, q పైభాగం మూయండి. అప్పుడు అవి u లేదా c లా కనిపించవు."
    },
    "distinct.tall-h": {
        "text": "h, k పొడవుగా రాయండి. అప్పుడు అవి n లేదా x లా కనిపించవు."
    },
    "neat.one-line-cross": {
        "text": "పదం మార్చాలంటే ఒకే సరళ గీతతో కొట్టేయండి."
    },
    "neat.space-around": {"text": "పేరాల మధ్య, అంచుల చుట్టూ ఖాళీ వదలండి."},
    "spell.say-it": {
        "text": "పదాన్ని నెమ్మదిగా చెప్పండి. రాస్తూ ప్రతి శబ్దం వినండి."
    },
    "spell.small-parts": {
        "text": (
            "పొడవైన పదాన్ని చిన్న భాగాలుగా విడదీయండి. ఒక్కో భాగం నేర్చుకోండి."
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


# Why each skill helps and how a child sees it working (owner, 2026-10-11):
# page 2 prints them under each skill to grow, with the website's page for
# that skill. ``why`` is one short sentence about everyday life, ``win``
# finishes "You'll know it's working when ..." with a small win the child
# can see, and ``page`` is the skill's page on vahinitech.com (its path
# without ".html"). Encouraging words only: no claim to diagnose or cure
# anything (CLAIM_WORDS).
ABOUT = {
    1: (
        "Clear letter shapes make every word easy to read.",
        "your letters look like the ones in your book.",
        "handwriting-letter-formation",
    ),
    2: (
        "Starting each letter the same way makes writing smooth.",
        "each letter starts at the top without thinking.",
        "handwriting-stroke-order",
    ),
    3: (
        "Closed loops keep a, d and o easy to tell apart.",
        "your a, d, g and o have no gaps at the top.",
        "handwriting-loop-closure",
    ),
    4: (
        "Smooth strokes make your page look calm and clear.",
        "your lines flow without little wobbles.",
        "handwriting-line-quality",
    ),
    5: (
        "Same-size letters make your words easy to read.",
        "a, o and e line up like a fence.",
        "handwriting-size-consistency",
    ),
    6: (
        "Tall letters and tails help each word keep its shape.",
        "h and l reach up, and g and y hang down.",
        "handwriting-ascenders-and-descenders",
    ),
    7: (
        "Words on the line look neat and easy to follow.",
        "every small letter touches the line.",
        "handwriting-baseline-alignment",
    ),
    8: (
        "Even gaps help the eye find each word.",
        "you can read your line aloud without stopping.",
        "handwriting-word-spacing",
    ),
    9: (
        "Even gaps inside a word keep its letters together.",
        "letters in a word sit close but never touch.",
        "handwriting-letter-spacing",
    ),
    10: (
        "A straight margin gives your page a tidy frame.",
        "every line starts at the same edge.",
        "handwriting-margin-discipline",
    ),
    11: (
        "Level lines are easy to follow from left to right.",
        "your lines run straight across, even on plain paper.",
        "handwriting-line-straightness",
    ),
    12: (
        "Upright strokes help your letters stand tall and steady.",
        "the long strokes of h, l and t stand the same way.",
        "handwriting-vertical-alignment",
    ),
    13: (
        "A steady speed keeps letters the same from start to end.",
        "your last line looks as neat as your first.",
        "handwriting-writing-speed-consistency",
    ),
    14: (
        "Gentle, even pressure keeps your hand relaxed for longer.",
        "your lines look equally dark, with no deep dents.",
        "handwriting-pen-pressure",
    ),
    15: (
        "Flowing strokes help each word come out in one go.",
        "you write a short word without stopping in the middle.",
        "handwriting-stroke-continuity",
    ),
    16: (
        "Fewer pen lifts let your words flow faster.",
        "you finish a short word before lifting the pen.",
        "handwriting-pen-lifts",
    ),
    17: (
        "Letters that lean the same way look neat together.",
        "your tall letters lean like trees in one wind.",
        "handwriting-slant-consistency",
    ),
    18: (
        "Easy-to-read writing lets others enjoy what you wrote.",
        "a friend reads your page without asking about a word.",
        "handwriting-legibility",
    ),
    19: (
        "When each letter has its own shape, words read easily.",
        "nobody mixes up your a and u, or your n and h.",
        "handwriting-character-distinction",
    ),
    20: (
        "A neat page is a joy to read and to share.",
        "you feel proud to show your page to someone.",
        "handwriting-neatness",
    ),
}

# Telugu for ABOUT, draft wording like the rest (native speaker's check
# before Telugu reaches production). ``win`` is a whole sentence here: the
# Telugu label before it ends with a colon.
TELUGU_ABOUT = {
    1: {
        "why": "స్పష్టమైన అక్షరాల ఆకారాలతో ప్రతి పదం సులువుగా చదవచ్చు.",
        "win": "మీ అక్షరాలు మీ పుస్తకంలోని అక్షరాల్లాగే కనిపిస్తాయి.",
    },
    2: {
        "why": "ప్రతి అక్షరాన్ని ఒకేలా మొదలుపెడితే రాత సాఫీగా సాగుతుంది.",
        "win": "ఆలోచించకుండానే ప్రతి అక్షరం పై నుంచి మొదలవుతుంది.",
    },
    3: {
        "why": "మూసిన గుండ్రాలతో a, d, o సులువుగా గుర్తుపడతాం.",
        "win": "మీ a, d, g, o పైన ఖాళీ లేకుండా మూసుకుంటాయి.",
    },
    4: {
        "why": "నునుపైన గీతలతో మీ పేజీ ప్రశాంతంగా, స్పష్టంగా ఉంటుంది.",
        "win": "మీ గీతలు చిన్న వణుకులు లేకుండా సాగుతాయి.",
    },
    5: {
        "why": "ఒకే పరిమాణం అక్షరాలతో మీ పదాలు సులువుగా చదవచ్చు.",
        "win": "a, o, e కంచెలాగా ఒకే ఎత్తులో నిలుస్తాయి.",
    },
    6: {
        "why": "పొడవైన అక్షరాలు, తోకలు ప్రతి పదానికి ఆకారం ఇస్తాయి.",
        "win": "h, l పైకి చేరుతాయి, g, y కిందకు వేలాడతాయి.",
    },
    7: {
        "why": "గీతపై నిలిచిన పదాలు చక్కగా, సులువుగా చదివేలా ఉంటాయి.",
        "win": "ప్రతి చిన్న అక్షరం గీతను తాకుతుంది.",
    },
    8: {
        "why": "సమానమైన ఖాళీలు కంటికి ప్రతి పదాన్ని చూపిస్తాయి.",
        "win": "మీ వరుసను ఆగకుండా బిగ్గరగా చదవగలరు.",
    },
    9: {
        "why": "పదం లోపల సమాన ఖాళీలు అక్షరాలను కలిపి ఉంచుతాయి.",
        "win": "పదంలోని అక్షరాలు దగ్గరగా ఉంటాయి, కానీ తాకవు.",
    },
    10: {
        "why": "నిటారైన మార్జిన్ మీ పేజీకి చక్కని అంచు ఇస్తుంది.",
        "win": "ప్రతి వరుస ఒకే అంచు నుంచి మొదలవుతుంది.",
    },
    11: {
        "why": "తిన్నని వరుసలను ఎడమ నుంచి కుడికి సులువుగా చదవచ్చు.",
        "win": "తెల్ల కాగితంపై కూడా మీ వరుసలు తిన్నగా సాగుతాయి.",
    },
    12: {
        "why": "నిటారు గీతలతో మీ అక్షరాలు స్థిరంగా నిలుస్తాయి.",
        "win": "h, l, t ల పొడవైన గీతలు ఒకేలా నిలుస్తాయి.",
    },
    13: {
        "why": "స్థిరమైన వేగంతో మొదటి నుంచి చివరి దాకా అక్షరాలు ఒకేలా ఉంటాయి.",
        "win": "మీ చివరి వరుస మొదటి వరుసంత చక్కగా ఉంటుంది.",
    },
    14: {
        "why": "మెల్లని, సమానమైన ఒత్తిడితో చేయి ఎక్కువసేపు హాయిగా ఉంటుంది.",
        "win": "మీ గీతలన్నీ ఒకే ముదురుగా ఉంటాయి, లోతైన గుంటలు ఉండవు.",
    },
    15: {
        "why": "సాగే గీతలతో ప్రతి పదం ఒకే ఊపులో వస్తుంది.",
        "win": "చిన్న పదాన్ని మధ్యలో ఆగకుండా రాయగలరు.",
    },
    16: {
        "why": "తక్కువసార్లు పెన్ను ఎత్తితే పదాలు వేగంగా సాగుతాయి.",
        "win": "పెన్ను ఎత్తే ముందే చిన్న పదం పూర్తవుతుంది.",
    },
    17: {
        "why": "ఒకే వైపు వాలిన అక్షరాలు కలిసి చక్కగా కనిపిస్తాయి.",
        "win": "మీ పొడవైన అక్షరాలు ఒకే గాలికి వంగిన చెట్లలా వాలుతాయి.",
    },
    18: {
        "why": "సులువుగా చదివే రాతను అందరూ ఆనందంగా చదువుతారు.",
        "win": "మీ స్నేహితులు ఏ పదం గురించీ అడగకుండా మీ పేజీ చదువుతారు.",
    },
    19: {
        "why": "ప్రతి అక్షరానికి సొంత ఆకారం ఉంటే పదాలు సులువుగా చదవచ్చు.",
        "win": "మీ a, u లను, n, h లను ఎవరూ కలిపి చదవరు.",
    },
    20: {
        "why": "చక్కని పేజీ చదవడానికీ, చూపించడానికీ ఆనందంగా ఉంటుంది.",
        "win": "మీ పేజీని ఎవరికైనా గర్వంగా చూపిస్తారు.",
    },
}

# The website's factor pages (vahini-web's tools/gen-factor-pages.mjs
# writes them, one per factor): ``page`` must be one of these.
FACTOR_PAGES = tuple(ABOUT[n][2] for n in range(1, 21))

# Short, so they fit under the skill's name on page 2 without making its
# row taller than the practice beside it (tests/report-layout.mjs).
WHY_MAX = 60
WIN_MAX = 56

# Claims a report never makes, in any text: Vahini describes writing to
# help a child practise; it does not diagnose or treat anything, and it
# never reads personality from handwriting (owner's growth plan).
CLAIM_WORDS = ("cure", "overcome", "disorder", "diagnos")


def claim_pattern():
    """Matches a claim word with its endings (cured, overcoming,
    diagnosis), but not a longer word that holds one (secure)."""
    return re.compile(
        r"\b(cur(e|es|ed|ing)|overcom\w*|disorder\w*|diagnos\w*)\b", re.I
    )


def _attach_about():
    """Give every factor's area its ``why``, ``win``, ``page`` and the
    Telugu of the first two in ``i18n``."""
    for number, (why, win, page) in ABOUT.items():
        FACTORS[number].update(
            why=why,
            win=win,
            page=page,
            i18n={"te": dict(TELUGU_ABOUT.get(number, {}))},
        )


_attach_about()


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
    if ex.get("model") not in MODELS:
        found.append(f"{ex['id']}: unknown model {ex.get('model')}")
    if len(sentences(ex["steps"])) > STEP_SENTENCES_MAX:
        found.append(f"{ex['id']}: steps over {STEP_SENTENCES_MAX} sentences")
    if len(sentences(ex["check"])) != 1:
        found.append(f"{ex['id']}: check must be one sentence")
    return found


def sentences(text):
    """The sentences of a step, check or tip: the renderer numbers a
    step's sentences 1, 2, 3."""
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def _plain_english_problems(entry):
    """Short sentences a parent with basic English and a child of 8 can
    follow: at most WORDS_PER_SENTENCE_MAX words each."""
    found = []
    for text in _texts(entry):
        for sentence in sentences(text):
            if len(sentence.split()) > WORDS_PER_SENTENCE_MAX:
                found.append(f"{entry['id']}: long sentence {sentence!r}")
    if "text" in entry and len(sentences(entry["text"])) > 2:
        found.append(f"{entry['id']}: tip over 2 sentences")
    return found


def _helps_problems(entry, own):
    """``helps``: the entry's own factor at 1.0, other factors it truly
    helps between HELP_MIN and HELP_MAX, so its highest-weight factor is
    always its own (the report only prints practice for flagged skills)."""
    helps = entry.get("helps")
    eid = entry["id"]
    if not isinstance(helps, dict):
        return [f"{eid}: no helps"]
    if not own:
        return [f"{eid}: spelling helps no factor"] if helps else []
    found = []
    if helps.get(str(own)) != 1.0:
        found.append(f"{eid}: helps its own factor {own} at 1.0")
    others = {k: w for k, w in helps.items() if k != str(own)}
    if len(others) > HELPS_OTHERS_MAX:
        found.append(f"{eid}: helps over {HELPS_OTHERS_MAX} other factors")
    for key, weight in others.items():
        if key not in {str(n) for n in range(1, 21)}:
            found.append(f"{eid}: helps unknown factor {key}")
        elif not HELP_MIN <= weight <= HELP_MAX:
            found.append(f"{eid}: helps {key} at {weight}")
    return found


def _word_problems(entry):
    banned = avoid_pattern()
    claims = claim_pattern()
    found = []
    for text in _texts(entry):
        if banned.search(text):
            found.append(f"{entry['id']}: avoid word in {text!r}")
        if claims.search(text):
            found.append(f"{entry['id']}: claim word in {text!r}")
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
            if claim_pattern().search(value):
                found.append(f"{entry['id']}: claim word in {lang} {field}")
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


def _about_problems(number, area):
    """``why``, ``win`` and ``page`` of one factor: one short sentence
    each in plain, encouraging words, a known website page, and their
    Telugu."""
    name = f"factor {number}"
    found = []
    if area.get("page") not in FACTOR_PAGES:
        found.append(f"{name}: unknown page {area.get('page')}")
    banned, claims = avoid_pattern(), claim_pattern()
    for field, most in (("why", WHY_MAX), ("win", WIN_MAX)):
        text = area.get(field)
        if not isinstance(text, str) or not text.strip():
            found.append(f"{name}: no {field}")
            continue
        if len(text) > most:
            found.append(f"{name}: {field} over {most} chars")
        if len(sentences(text)) != 1 or not text.endswith("."):
            found.append(f"{name}: {field} must be one sentence")
        if len(text.split()) > WORDS_PER_SENTENCE_MAX:
            found.append(f"{name}: long {field}")
        if banned.search(text) or claims.search(text) or EM_DASH in text:
            found.append(f"{name}: avoid word in {field}")
        for lang in LANGUAGES:
            local = area.get("i18n", {}).get(lang, {}).get(field)
            if not isinstance(local, str) or not local.strip():
                found.append(f"{name}: {lang} {field} missing")
                continue
            if len(local) > translation_limit(text):
                found.append(f"{name}: {lang} {field} too long")
            if (
                EM_DASH in local
                or claims.search(local)
                or any(w in local for w in AVOID_WORDS_TE)
            ):
                found.append(f"{name}: avoid word in {lang} {field}")
    return found


def problems():
    """Every rule the catalogue breaks, as readable lines (none is good)."""
    found = _orphan_translations()
    for number in range(1, 21):
        if number in FACTORS:
            found += _about_problems(number, FACTORS[number])
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
            found += _plain_english_problems(entry)
            found += _helps_problems(entry, number)
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
    """What the catalogue serves for one factor: why it helps, the win to
    look for, its website page, and its exercises and tips."""
    area = FACTORS[number]
    return {
        "why": area["why"],
        "win": area["win"],
        "page": area["page"],
        "i18n": {lang: dict(t) for lang, t in area["i18n"].items()},
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
