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
    sample   Vahini's own sample page, and only that page: the photo's
             bytes must be the bundled sample's (SAMPLE_SHA256), or the
             answer counts as missing

The check page offers nothing pre-selected, and "student" is sent only
after the adult's tick (frontend/src/report/report-share.js).

A Pro key belongs to a school, clinic or therapist who agreed to the
terms for their own pupils or clients, so a keyed request is not asked.
Required only where VAHINI_REQUIRE_WHO=1, so an open-source install and
older clients keep working until they send it. Stage is to set it first;
production sets it later, once the Android app asks too.

The answer is checked and forgotten: it is not stored, logged, cached or
echoed, and it changes nothing in the scan or the report."""

import hashlib
import os

VALUES = ("parent", "teacher", "self", "student", "sample")
ERROR_CODE = "who_required"
FIELD = "who"
MESSAGE = (
    "Say who is checking this page: parent, teacher, self (18 or over), "
    "student (with an adult's yes) or sample."
)

# sha256 of frontend/assets/samples/handwriting-sample.jpg, which the check
# page's "Try a sample" sends unchanged (app.js, loadBundledSample).
# test_who_checks.py fails when the file and this line disagree.
SAMPLE_SHA256 = (
    "a4a105757e43f86101e9b3f86d28897a408db1f885fb0137970fdcd3290ba9ef"
)


def is_sample(image):
    """True when the photo's bytes are Vahini's bundled sample page."""
    return bool(image) and hashlib.sha256(image).hexdigest() == SAMPLE_SHA256


def required():
    """True where every free check must say who is checking."""
    return os.environ.get("VAHINI_REQUIRE_WHO") == "1"


def check(text, pro=False, image=None):
    """The answer as sent, or None when none is needed. ValueError when
    the answer is missing where required, or is not one of VALUES.
    "sample" with any photo but the bundled sample (image, the upload's
    bytes) counts as missing, so it cannot stand in for a real answer."""
    text = (text or "").strip().lower()
    if text == "sample" and not is_sample(image):
        text = ""
    if not text:
        if required() and not pro:
            raise ValueError(MESSAGE)
        return None
    if text not in VALUES:
        raise ValueError(MESSAGE)
    return text
