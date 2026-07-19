# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The ten finishing letters - a coach's tip surfaced in the report.

The rule (coach lesson, Jul 2026): ten of the 26 letters - A, D, H,
I, L, M, N, R, T, U - share an ending on a downstroke. Whenever a
WORD ends with one of them, finish with a small exit stroke (a gentle
upward flick); never stop abruptly on the bare vertical. "Hand"
should not end on a dead 'd' stem - it earns the small finishing
stroke.

Detecting the exit stroke itself needs character segmentation, which
the pipeline does not have yet - so this module is honest about being
a TEXT-GATED TIP: it finds the words on the page where the rule
applies and puts the coaching advice in the report, addressed to the
writer's own words. Stroke-level verification lands with character
segmentation, and the method field says so.
"""

import re

FINISHING_LETTERS = set("adhilmnrtu")

_WORD_RE = re.compile(r"[A-Za-z]{2,}")

TIP_ID = "finishing-letters"
TIP_TITLE = "The 10 letters that improve your handwriting"


def analyze_finishing_letters(lines):
    """Find the words where the finishing-stroke rule applies.

    lines: OCR line dicts with 'text'. Returns a dict with the
    qualifying-word count, up to three examples from the writer's own
    page, and the report tip - or available=False when no word on the
    page ends in one of the ten letters."""
    qualifying = []
    for l in lines:
        for w in _WORD_RE.findall(str(l.get("text", "") or "")):
            if w[-1].lower() in FINISHING_LETTERS:
                qualifying.append(w)
    if not qualifying:
        return {
            "available": False,
            "reason": "no words ending in the ten finishing letters",
        }

    examples = []
    for w in qualifying:
        lw = w.lower()
        if lw not in (e.lower() for e in examples):
            examples.append(w)
        if len(examples) == 3:
            break

    return {
        "available": True,
        "letters": "A D H I L M N R T U",
        "wordCount": len(qualifying),
        "examples": examples,
        "method": (
            "text-gated tip; stroke-level exit detection lands with "
            "character segmentation"
        ),
        "tip": {
            "id": TIP_ID,
            "title": TIP_TITLE,
            "text": (
                "Ten letters - A, D, H, I, L, M, N, R, T, U - end on a "
                "downstroke. When a word ends with one of them "
                + (
                    "(on this page: "
                    + ", ".join(f"'{e}'" for e in examples)
                    + ") "
                )
                + "finish it with a small upward stroke instead of "
                "stopping dead on the vertical. 'Hand' should not end "
                "abruptly on the 'd' stem - the small finishing flick "
                "is what makes the word look complete."
            ),
        },
    }
