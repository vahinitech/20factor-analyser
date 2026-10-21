# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# spatial.py - the Spatial section's formulas, factors 7 to 12:
# spacing, baseline and layout.

from scoring_parts.stats import _clamp10

# Word Spacing: the word gaps' mean distance from their median, as a
# share of it, that loses all marks; Letter Spacing: the letter gaps'
# median distance from their own word's median gap, the same way
# (features._word_spacing, _letter_spacing, #197). Set so the 20 UJI
# benchmark pages keep about the median they had; how high neat writing
# scores is set later from neat pages (scripts/calibrate.py).
WORD_GAP_SCALE = 1.05
LETTER_GAP_SCALE = 0.37
# Line Straightness: the wander off the baseline, in small letters,
# that loses its 5 points.
WAVE_SCALE = 0.25
# Margin Discipline: how far, as a share of the page width, the rows'
# starts stray from the margin on average before every mark is lost.
MARGIN_SCALE = 0.05


def add_scores(fx, s):
    """Adds factors 7 to 12 to s, the page's scores by factor number."""
    # Less up to 5 points as the share of words sitting off their line
    # reaches 25%: one sunken word does not turn a line.
    s[7] = _clamp10(
        (1.0 - min(1.0, fx["line_slope_abs"] / 8.0)) * 10.0
        - 5.0 * min(1.0, (fx.get("words_off_line") or 0.0) / 0.25)
    )
    # Less up to 2 points as the share of word gaps that stand out (under
    # half or over twice the median) reaches 10%: one odd gap among
    # twenty costs a point, as one word off size does for Size.
    s[8] = _clamp10(
        (1.0 - min(1.0, fx["word_gap_spread"] / WORD_GAP_SCALE)) * 10.0
        - 2.0 * min(1.0, (fx.get("word_gaps_odd") or 0.0) / 0.10)
    )
    if fx.get("letter_gap_spread") is not None:
        # Less up to 1 point as the share of letter gaps over twice their
        # word's reaches 20%, and up to 3 as the share of words written
        # with their letters apart reaches 10%.
        spread = fx["letter_gap_spread"] / LETTER_GAP_SCALE
        s[9] = _clamp10(
            (1.0 - min(1.0, spread)) * 10.0
            - 1.0 * min(1.0, (fx.get("letter_gaps_odd") or 0.0) / 0.20)
            - 3.0 * min(1.0, (fx.get("words_spaced_off") or 0.0) / 0.10)
        )
    else:
        s[9] = _clamp10((1.0 - min(1.0, fx["char_w_cv"] / 1.2)) * 10.0)
    s[10] = _clamp10((1.0 - min(1.0, fx["left_spread"] / MARGIN_SCALE)) * 10.0)
    # A straight line is level and does not wave: the slope, less up to 5
    # points as the most wandering line's letters drift a quarter of a
    # small letter off their baseline.
    s[11] = _clamp10(
        (1.0 - min(1.0, fx["line_slope_abs"] / 10.0)) * 10.0
        - 5.0 * min(1.0, (fx.get("line_wave") or 0.0) / WAVE_SCALE)
    )
    s[12] = _clamp10((1.0 - min(1.0, fx["line_slope_std"] / 10.0)) * 10.0)
