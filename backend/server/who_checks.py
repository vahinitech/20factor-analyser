# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Who is checking a page, asked before the page is read.

India's DPDP Rules 2025, rule 10: a child's personal data is processed
only after a parent's consent. A photo of a child's page is the child's
data when it carries a name, a school or a roll number, and reading it
for a few seconds is processing. So the free check asks first, as one
word sent with the photo:

    parent   a parent or guardian of the writer
    teacher  the writer's teacher
    self     someone 18 or over checking their own writing
    student  a student, with a parent, guardian or teacher there saying yes
    sample   Vahini's own sample page

The check page offers nothing pre-selected, and "student" is sent only
after the adult's tick (frontend/src/report/report-share.js).

A Pro key belongs to a school, clinic or therapist who agreed to the
terms for their own pupils or clients, so a keyed request is not asked.
Required only where VAHINI_REQUIRE_WHO=1 (the hosted stage and production
set it), so an open-source install and older clients keep working until
they send it.

The answer is checked and forgotten: it is not stored, logged, cached or
echoed, and it changes nothing in the scan or the report."""

import os

VALUES = ("parent", "teacher", "self", "student", "sample")
ERROR_CODE = "who_required"
FIELD = "who"
MESSAGE = (
    "Say who is checking this page: parent, teacher, self (18 or over), "
    "student (with an adult's yes) or sample."
)


def required():
    """True where every free check must say who is checking."""
    return os.environ.get("VAHINI_REQUIRE_WHO") == "1"


def check(text, pro=False):
    """The answer as sent, or None when none is needed. ValueError when
    the answer is missing where required, or is not one of VALUES."""
    text = (text or "").strip().lower()
    if not text:
        if required() and not pro:
            raise ValueError(MESSAGE)
        return None
    if text not in VALUES:
        raise ValueError(MESSAGE)
    return text
