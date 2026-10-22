# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The request's optional age band (#212): the writer's age as two whole
years, the first below the second, such as ``6-7``.

Never a birth date and never a single exact age: a band says which norms
a page could be compared with (docs/20-languages.md, section 9) and
nothing more about the child. It is checked, echoed in the report and
not stored. No score uses it yet; the norm bands that will read it are
#216, and until they exist every band scores the same.
"""

import re

YOUNGEST, OLDEST = 3, 18
_AGE = "([3-9]|1[0-8])"
# The band in a report. The order of the two ages is checked in parse(),
# since a pattern cannot compare numbers.
BAND_PATTERN = f"^{_AGE}-{_AGE}$"
# The request field: empty means not given.
PATTERN = f"^({_AGE}-{_AGE})?$"
ERROR_CODE = "age_band_invalid"


def parse(text):
    """The band as sent, or None when none was given. ValueError says
    what is wrong, never repeating more than the field's own format."""
    text = (text or "").strip()
    if not text:
        return None
    if not re.fullmatch(BAND_PATTERN, text):
        raise ValueError(
            "age_band is two whole-year ages from "
            f"{YOUNGEST} to {OLDEST}, such as 6-7"
        )
    low, high = (int(x) for x in text.split("-"))
    if low >= high:
        raise ValueError("age_band's first age must be below the second")
    return f"{low}-{high}"
