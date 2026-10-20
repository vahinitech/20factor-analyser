# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# dynamics.py - the Dynamics section's formulas, factors 13 to 16:
# speed, pressure and flow. A photo has no pen data, so these are
# computed but reported "Not measured" (availability.py); the Vahini
# sensor pen is what measures them.

import languages
from scoring_parts.stats import _clamp10

# Factor 15's ideal word length, in letters.
WORD_LETTERS = languages.language().get("letters_per_word")


def add_scores(fx, s):
    """Adds factors 13 to 16 to s, the page's scores by factor number."""
    s[13] = _clamp10((1.0 - min(1.0, fx["width_cv"] / 0.85)) * 10.0)
    s[14] = _clamp10((1.0 - min(1.0, fx["ink_cv"] / 0.95)) * 10.0)
    word_len = fx["n_chars"] / max(1, fx["n_words"])
    s[15] = _clamp10(
        (1.0 - min(1.0, abs(word_len - WORD_LETTERS) / WORD_LETTERS)) * 10.0
    )
    s[16] = _clamp10((1.0 - min(1.0, fx["char_w_cv"] / 1.4)) * 10.0)
