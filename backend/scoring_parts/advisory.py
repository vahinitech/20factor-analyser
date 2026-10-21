# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# advisory.py - the checks build_analysis merges into the report beside
# the 20 formulas: measured zones (which may rescore factor 6), cross-
# bars, writing style and finishing letters, the baseline drift note and
# the coach tips. Apart from factor 6's zone score, none of this changes
# a score; it adds evidence and coaching.

import numpy as np

from coach_tips import pillar_summary, select_tips
from finishing_letters import analyze_finishing_letters
from style_analysis import analyze_style
from tbar_analysis import analyze_tbars
from zone_analysis import analyze_zones, zone_score

try:
    import cv2
except Exception:
    cv2 = None


def run_checks(arr, lines):
    """Zones, cross-bars, writing style and finishing letters for this
    page. A check that fails gives None (zones: why it failed), never an
    error."""
    # Three-zone letter-size rule (the coaches' 1:2 proportion): when the
    # page supports it, Factor 6 is scored from measured zone geometry
    # instead of the tall-letter-share proxy. zone_analysis.py.
    zones = None
    try:
        if cv2 is not None:
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        else:
            # Same RGB->gray weights as classify.py's _gray, so zone
            # measurement stays consistent whether or not cv2 is
            # available in the environment.
            gray = np.dot(
                np.asarray(arr[..., :3], dtype=np.float64),
                [0.299, 0.587, 0.114],
            ).astype(np.uint8)
        zones = analyze_zones(gray, lines)
    except Exception as e:
        # Keep the failure honest: zoneProfile.method should say WHY
        # the proxy was used instead of silently swallowing it.
        zones = {
            "available": False,
            "reason": f"zone analysis failed: {e}",
        }
    # Cross-bar craft rule (double-t shared bar, t-bar overshoot):
    # advisory observations from tbar_analysis.py - they feed evidence
    # on factors 16 and 1, never silently change a score.
    tbars = None
    try:
        tbars = analyze_tbars(gray, lines)
    except Exception:
        tbars = None
    # Writing-style classification (cursive / print / mixed) and the
    # ten-finishing-letters tip - both coach lessons, both advisory.
    style = None
    try:
        style = analyze_style(gray, lines)
    except Exception:
        style = None
    finishing = None
    try:
        finishing = analyze_finishing_letters(lines)
    except Exception:
        finishing = None
    return {
        "zones": zones,
        "tbars": tbars,
        "style": style,
        "finishing": finishing,
    }


def apply_zone_score(zones, scores):
    """Rescores factor 6 from measured zones when the page supports it;
    True when it did."""
    zone_based = bool(zones and zones.get("available"))
    if zone_based:
        zs = zone_score(zones)
        if zs is not None:
            scores[6] = round(float(zs), 1)
        else:
            zone_based = False
    return zone_based


def factor_evidence(n, evidence, checks, zone_based):
    """Factor n's evidence line with what the checks found added: the
    zone bands replace factor 6's, the style check follows 15's and the
    cross-bar check follows 16's and 1's."""
    zones = checks["zones"]
    tbars = checks["tbars"]
    style = checks["style"]
    tbar_ok = bool(tbars and tbars.get("available"))
    style_ok = bool(style and style.get("available"))
    if n == 6 and zone_based:
        parts = []
        if zones.get("ascReach") is not None:
            parts.append(f"ascenders reach {zones['ascReach']:.1f}x")
        if zones.get("descReach") is not None:
            parts.append(f"descenders reach {zones['descReach']:.1f}x")
        source = (
            "Measured against the printed guide lines"
            if zones.get("ruled")
            else "Measured zone bands"
        )
        evidence = (
            f"{source} over "
            f"{zones['linesUsed']} lines: {', '.join(parts)} the "
            "x-height (the 1:2 rule targets 2.0x)."
        )
        if zones.get("flags"):
            evidence += f" Flags: {', '.join(zones['flags'])}."
    if n == 15 and style_ok:
        sh = style["shares"]
        evidence += (
            f" Style check: {style['verdict']} "
            f"(cursive {int(sh['cursive'] * 100)}%, print "
            f"{int(sh['print'] * 100)}%, mixed "
            f"{int(sh['mixed'] * 100)}% of words)."
        )
        if style["verdict"] == "mixed":
            evidence += (
                " Joining in places and lifting in others makes "
                "words break apart - pick cursive or print and "
                "stay with it."
            )
    if n == 16 and tbar_ok and (tbars["sharedBars"] or tbars["separateBars"]):
        evidence += (
            " Cross-bar check: "
            f"{tbars['sharedBars']} shared double-t bar(s), "
            f"{tbars['separateBars']} crossed with separate "
            "lifts (one extended bar per side-by-side tt saves "
            "a pen lift)."
        )
    if n == 1 and tbar_ok and tbars["overshoots"]:
        evidence += (
            f" Cross-bar check: {tbars['overshoots']} t-bar(s) "
            "ride over the neighbouring tall letter - limit the "
            "bar to the t stem."
        )
    return evidence


def add_baseline_drift(fx, results):
    """The baseline drift note, also added to factor 7's evidence."""
    # Baseline drift DIRECTION (issue #21): coaches teach climbing vs
    # sinking, not just "misaligned". Positive signed angle = the lines
    # descend left-to-right (sinking below the rule). A tilted photo
    # shows the same signature, so the wording carries that caveat.
    drift_deg = float(fx.get("line_slope_signed_med", 0.0))
    if drift_deg > 0.8:
        drift_dir = "sinking"
    elif drift_deg < -0.8:
        drift_dir = "climbing"
    else:
        drift_dir = "level"
    baseline_drift = {
        "direction": drift_dir,
        "degrees": round(abs(drift_deg), 1),
        "note": (
            "Lines stay level across the page."
            if drift_dir == "level"
            else (
                f"Lines tend to keep {drift_dir} by about "
                f"{abs(drift_deg):.1f} degrees left to right. "
                "(A tilted photo shows the same sign: scan flat to be sure.)"
            )
        ),
    }
    for r in results:
        if r.n == 7 and drift_dir != "level":
            r.evidence = (
                f"{r.evidence} Direction: {drift_dir} "
                f"~{abs(drift_deg):.1f} deg across the page."
            )
        if r.n == 7 and fx.get("baseline_rows_tracked"):
            wave = fx.get("baseline_wave_med")
            r.evidence += (
                " Baseline tracked word-by-word across "
                f"{fx['baseline_rows_tracked']} line(s) with a smoothing "
                "filter (issue #31)"
                + (
                    f"; word baselines scatter about the track by "
                    f"{wave * 100:.0f}% of the line height."
                    if wave is not None
                    else "."
                )
            )
    return baseline_drift


def zone_profile(zones, zone_based, scores):
    """The zone profile: measured bands when the page supported them,
    else the proxy."""
    # Zone profile (issue #21): the two things a coach actually checks —
    # upper/lower reach (factor 6, Ascender/Descender Control) and
    # middle-zone stability (factor 5, Size Consistency, i.e. letter-
    # height consistency used as the proxy for a steady x-height band).
    # Measured projection-profile zone bands are used when the page
    # supports them, the proxy otherwise - the method field always says
    # which one produced the numbers.
    # Both branches always populate the same key set (measured keys are
    # null/empty in the proxy case) so API consumers don't have to
    # special-case the schema on zone_based; upperLowerReach is kept in
    # both for backward compatibility with pre-measurement consumers.
    if zone_based:
        how = (
            "the printed guide lines"
            if zones.get("ruled")
            else "per-line ink projection profiles"
        )
        return {
            "upperLowerReach": round(float(scores.get(6, 0.0)), 1),
            "ascenderReach": zones.get("ascReach"),
            "descenderReach": zones.get("descReach"),
            "targetReach": zones.get("targetReach"),
            "xHeightPx": zones.get("xHeightPx"),
            "flags": zones.get("flags", []),
            "middleStability": round(float(scores.get(5, 0.0)), 1),
            "method": (
                f"measured: {how} -> zone "
                f"bands over {zones['linesUsed']} lines (1:2 rule)"
            ),
        }
    return {
        "upperLowerReach": round(float(scores.get(6, 0.0)), 1),
        "ascenderReach": None,
        "descenderReach": None,
        "targetReach": None,
        "xHeightPx": None,
        "flags": [],
        "middleStability": round(float(scores.get(5, 0.0)), 1),
        "method": (
            "proxy from tall-letter share and letter-height "
            "statistics"
            + (
                f" ({zones['reason']})"
                if zones and zones.get("reason")
                else ""
            )
        ),
    }


def coach_tips(measured_results, checks, lines):
    """The coach tips for this page and the TIP diagnosis."""
    # Coach tips: the library will hold hundreds of lesson-derived
    # tips, so the engine (coach_tips.py) ranks them by this page's
    # measured scores and keeps only the top few - each with a 'why'
    # naming the measurement that earned it the slot. Advisory report
    # content, never a score input.
    tip_ctx = {
        "scores": {r.n: r.score for r in measured_results},
        "style": checks["style"],
        "finishing": checks["finishing"],
        "text": " ".join(str(l.get("text", "") or "") for l in lines),
    }
    tips, _tip_library = select_tips(tip_ctx)
    # The TIP diagnosis (Techniques / Interest / Practice): which leg
    # of the skill is short on THIS page, from the measured factors.
    return tips, pillar_summary(tip_ctx)


def profile(result):
    """A check's result as the report carries it."""
    if result is not None:
        return result
    return {"available": False, "reason": "analysis unavailable"}
