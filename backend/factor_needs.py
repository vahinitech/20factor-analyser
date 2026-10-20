# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# factor_needs.py - what each of the 20 factors needs from a page, and
# the one check that says which factors this page can measure
# (docs/20-languages.md section 8, #207).
#
# A factor is measured when the page supplied every need of at least one
# of its alternatives. When none is met, the factor is "Not measured" and
# the missing need decides why: no pen data, nothing read, or letters the
# language pack does not know. This replaced three lists in scoring.py
# (_LATIN_ONLY, _NEEDS_RECOGNITION and _INK_MEASURED); the reasons and the
# scoring_inputs methods are the same words as before.

from languages import profile

# The vocabulary of section 8, in the order a missing need is reported:
# a factor missing pen data says so even when nothing was read either.
VOCABULARY = (
    "sensor",  # pen data (Vahini sensor pen); never in a photo
    "rows",  # ink rows with baselines
    "words",  # word boxes from the reader
    "graphemes",  # read letters with boxes
    "confidence",  # the reader's confidence
    "classes",  # letters the language pack sorts into classes
    "zones",  # the pack's zone model fitted to the page
)

# Each factor's alternatives: the factor is measured when any one of them
# is met in full. An empty alternative needs only the line bands every
# scored page has (height, width and left edge of each line).
NEEDS = {
    1: (("rows", "confidence"),),
    2: (("graphemes", "confidence"),),
    3: (("graphemes", "classes"),),
    4: ((),),
    5: ((),),
    # Zone bands when zone_analysis.py fitted them, else the share of the
    # pack's tall letters among the letters read.
    6: (("zones",), ("graphemes", "classes")),
    7: (("rows",),),
    # Gaps between the reader's word boxes, or between the words of an ink
    # row when the passage says how many it holds (ink_geometry.py).
    8: (("words",), ("rows",)),
    # Letter gaps are measured inside the letters read; ink rows do not
    # give them yet.
    9: (("graphemes",),),
    10: ((),),
    11: (("rows",),),
    12: (("rows",),),
    13: (("sensor",),),
    14: (("sensor",),),
    15: (("sensor",),),
    16: (("sensor",),),
    # Each word's lean; ink rows have no word boxes to lean.
    17: (("words",),),
    # Blends 1, 5, 7 and 8.
    18: (("rows", "confidence"),),
    19: (("graphemes", "confidence"),),
    # Blends 5, 8, 10, 11 and 17; where 17 is not measured its line-angle
    # stand-in, from the rows, takes its place.
    20: (("rows",),),
}

# The letter classes each factor counts letters of: loops and closed
# bowls for 3; tall letters for 6, by share and in the zone fit
# (zone_analysis.py). A school or class profile that empties one of these
# classes (languages/profile.py) leaves the factor "Not measured", never
# a higher score.
CLASSES = {
    3: ("bowl", "loop"),
    6: ("ascender", "descender"),
}

# The unmeasured kind (scoring._UNMEASURED_REASONS) a missing need gives.
KIND = {
    "sensor": "imu",
    "rows": "ocr",
    "words": "ocr",
    "graphemes": "ocr",
    "confidence": "ocr",
    "classes": "script",
    "zones": "script",
}


def _check():
    if set(NEEDS) != set(range(1, 21)):
        raise ValueError("factor needs: every factor 1 to 20 needs an entry")
    if set(KIND) != set(VOCABULARY):
        raise ValueError("factor needs: every need maps to a kind")
    for n, alternatives in NEEDS.items():
        if not alternatives:
            raise ValueError(f"factor needs: factor {n} has no alternative")
        for alt in alternatives:
            unknown = set(alt) - set(VOCABULARY)
            if unknown:
                raise ValueError(
                    f"factor needs: factor {n} needs {sorted(unknown)}"
                )
    for n in CLASSES:
        if not any("classes" in alt for alt in NEEDS[n]):
            raise ValueError(f"factor needs: factor {n} counts no class")
    counted = {name for names in CLASSES.values() for name in names}
    if counted & set(profile.MUST_KEEP):
        raise ValueError(
            "factor needs: a class a profile must keep cannot leave a "
            "factor unmeasured"
        )


_check()


def page_supplies(lines, latin_letters, zone_based):
    """The needs a photographed page supplied. Lines with "cv_fallback"
    were found without a reader: fallback boxes give nothing beyond line
    bands, and ink rows ("ink_row", ink_geometry.py) give rows with
    baselines. A photo never gives pen data."""
    read = not all(bool(ln.get("cv_fallback")) for ln in lines)
    ink_rows = bool(lines) and all(bool(ln.get("ink_row")) for ln in lines)
    got = set()
    if read:
        got.update(("rows", "words", "graphemes", "confidence"))
    elif ink_rows:
        got.add("rows")
    if latin_letters:
        got.add("classes")
    if zone_based:
        got.add("zones")
    return frozenset(got)


def emptied(n):
    """The classes factor n counts that the scan's profile emptied
    (profile.applied(); none without a profile)."""
    ruleset = profile.active()
    if ruleset is None:
        return ()
    return tuple(c for c in CLASSES.get(n, ()) if c in ruleset.emptied_classes)


def missing_need(n, supplied):
    """None when factor n can be measured from what was supplied, else the
    need to report: the first in VOCABULARY order missing from any of the
    factor's alternatives. A factor whose counted class the profile
    emptied lacks "classes" even when the page has letters."""
    alternatives = NEEDS[n]
    if any(set(alt) <= supplied for alt in alternatives):
        return "classes" if emptied(n) else None
    lacking = {need for alt in alternatives for need in alt} - supplied
    return next(need for need in VOCABULARY if need in lacking)


def missing_kind(n, supplied):
    """The unmeasured kind for factor n on this page, or None."""
    need = missing_need(n, supplied)
    return KIND[need] if need else None


# What the report says for a factor a profile left unmeasured; it
# replaces the script reason the scorer gives a missing "classes".
PROFILE_REASON = "The class profile says these letters are not taught yet."
PROFILE_EVIDENCE = (
    "The class profile says the letters this measure counts are not "
    "taught yet, so it waits until they are."
)


def explain(analysis, ruleset):
    """The scorer's output (AnalysisResult.to_dict()) with the profile's
    reason on each factor it left unmeasured. Words only: no score,
    section or overall changes here."""
    if ruleset is None or not ruleset.emptied_classes or not analysis:
        return analysis
    factors = list(analysis.get("results") or [])
    for section in analysis.get("sections") or []:
        factors.extend(section.get("factors") or [])
    for factor in factors:
        names = [
            c
            for c in CLASSES.get(factor.get("n"), ())
            if c in ruleset.emptied_classes
        ]
        if not names or not factor.get("unmeasured"):
            continue
        if factor.get("unmeasuredKind") != KIND["classes"]:
            continue
        factor["unmeasuredReason"] = PROFILE_REASON
        factor["evidence"] = PROFILE_EVIDENCE
        factor["scoringInputs"] = {
            "method": "profile_not_taught",
            "features": {"classes": names},
        }
    return analysis
