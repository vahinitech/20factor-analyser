# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# style.py - the Style & Readability section's formulas, factors 17 to
# 20: slant, legibility and neatness. Legibility (18) and Overall
# Neatness (20) blend scores of the other sections, so these run last.
# frontend/src/report/practice-select.js holds the same blend weights
# (backend/tests/test_practice_catalog.py keeps the two in step).

from scoring_parts.availability import _MIN_WORD_GAPS
from scoring_parts.stats import _clamp10

# Slant Consistency: the spread of the words' lean, in degrees, that
# loses all marks.
SLANT_SCALE = 40.0


def add_scores(fx, s):
    """Adds factors 17 to 20 to s, which already holds factors 1 to 16."""
    if fx.get("slant_std") is not None:
        s[17] = _clamp10(
            (1.0 - min(1.0, fx["slant_std"] / SLANT_SCALE)) * 10.0
        )
    else:
        s[17] = _clamp10((1.0 - min(1.0, fx["line_slope_std"] / 12.0)) * 10.0)

    # Composites leave Word Spacing out, and reweight the rest, when too
    # few word gaps were measured for it to mean anything.
    def _blend(parts):
        live = [(w, s[k]) for k, w in parts if k != 8 or spacing_ok]
        return sum(w * v for w, v in live) / sum(w for w, _ in live)

    spacing_ok = fx.get("word_gap_count", 3) >= _MIN_WORD_GAPS
    s[18] = _clamp10(_blend(((1, 0.35), (5, 0.25), (8, 0.20), (7, 0.20))))
    s[19] = _clamp10(
        (fx["avg_score"] * 7.5)
        + ((1.0 - min(1.0, fx["digits_ratio"] / 0.5)) * 2.5)
    )
    s[20] = _clamp10(
        _blend(((5, 0.30), (8, 0.20), (10, 0.20), (11, 0.15), (17, 0.15)))
    )
