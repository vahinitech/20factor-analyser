# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# structure.py - the Structure section's formulas, factors 1 to 6:
# letter shapes, size and control. Factor 6 may be rescored from
# measured zones afterwards (advisory.apply_zone_score).

from scoring_parts.stats import _clamp10

# Full marks for Loop Closure when this share of the bowls read is
# closed (a few open at small sizes are normal).
BOWL_FULL = 0.9


def add_scores(fx, s):
    """Adds factors 1 to 6 to s, the page's scores by factor number."""
    s[1] = _clamp10(
        (fx["avg_score"] * 7.2) + ((1.0 - min(1.0, fx["height_cv"])) * 2.8)
    )
    s[2] = _clamp10(
        5.4 + (1.0 - min(1.0, fx["char_w_cv"])) * 2.6 + (fx["avg_score"] * 2.0)
    )
    # Factors 3, 7, 9, 11 and 17 are measured from the ink inside the
    # lines (_stroke_features); the older stand-ins below are kept only
    # for a page too small to measure. Scales set on the planted pages
    # (scripts/factor_tests.py, docs/02-how-a-scan-works.md section 13).
    if fx.get("bowl_share") is not None:
        s[3] = _clamp10(min(1.0, fx["bowl_share"] / BOWL_FULL) * 10.0)
    else:
        s[3] = _clamp10((min(1.0, fx["loop_ratio"] / 0.28)) * 10.0)
    s[4] = _clamp10((1.0 - min(1.0, fx["width_cv"] / 0.8)) * 10.0)
    # Word x-heights vary less than line boxes did, so their full scale is
    # 0.60 (a clean planted page scores about 7.8, as line boxes did).
    size_scale = (
        0.60 if fx.get("size_basis") in ("words", "letter groups") else 0.65
    )
    # Less up to 2 points as the share of words whose small letters are
    # 30% or more off the page's usual reaches 10% (the same words the
    # report marks, marked_places.py): one oversized word moved the
    # spread of 30 words too little to see.
    s[5] = _clamp10(
        (1.0 - min(1.0, fx.get("size_cv", fx["height_cv"]) / size_scale))
        * 10.0
        - 2.0 * min(1.0, (fx.get("words_off_size") or 0.0) / 0.10)
    )
    s[6] = _clamp10(
        (1.0 - min(1.0, abs(fx["tall_ratio"] - 0.34) / 0.34)) * 10.0
    )
