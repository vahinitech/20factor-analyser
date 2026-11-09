# SPDX-License-Identifier: AGPL-3.0-only
"""No server or script code that nothing in the product calls.

Coverage says which lines the tests ran, and its ratchet only fails when a
number falls, so a file at 0% can never fail it. The report's old role
table, score ring and trajectory chart sat unused in report-render.js for
months that way. vulture finds the Python names nothing uses;
tests/unused-code.test.mjs does the same for the browser sources.

A test is not a use: a function only a test calls still never runs for a
visitor. A name kept on purpose goes in KEEP with the reason, and KEEP is
checked too, so an entry goes once the name is used or deleted. Route
handlers and middleware are called by FastAPI through their decorators,
so those are skipped.
"""

import os
import unittest

import vulture

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PATHS = ["backend", "scripts", os.path.join("frontend", "build_bundle.py")]
EXCLUDE = [os.path.join("*", "backend", "tests", "*")]
DECORATORS = ["@app.*", "@router.*"]
MIN_CONFIDENCE = 60

# name -> why it stays although nothing in the product uses it.
KEEP = {
    "child_entry": (
        "server/scan_worker.py: the scan worker's command line calls it "
        "by name, in a string vulture cannot read"
    ),
    "clear_cache": (
        "languages/registry.py: tests reset the language-pack cache "
        "between cases"
    ),
    "validate": (
        "report/contract_schemas.py: the schema and store tests check "
        "API bodies with it"
    ),
    "split_lines": (
        "reading/classify.py: tests classify a page in one call; the "
        "server calls classify_lines"
    ),
    "engine_speed_verdict": (
        "reading/ocr_backends.py: tests read one engine's speed record; "
        "/health reads engine_speed_snapshot"
    ),
    "rungs_for_lang": (
        "languages/ladders.py: tests read a ladder by language code"
    ),
    "_refine_engine_for_line": (
        "reading/recognizer.py: tests compare the stage table's routing "
        "with the routing before #208"
    ),
    "build_endurance": (
        "report/plain_groups.py: the trend across a multi-page check, "
        "tested but not in a report yet (the OT report, #291)"
    ),
    "PILLARS": (
        "report/coach_tips.py: names the three legs pillar_summary "
        "reports on; test_coach_tips checks them"
    ),
    "CLAIM_WORDS": (
        "report/practice_catalog.py: the claim words, which "
        "tests/report-words.test.mjs reads from the source"
    ),
    "_manager": (
        "reading/ocr_backends.py: holds Surya's inference manager for "
        "the predictor built from it"
    ),
    "row_factory": "server/entitlements.py: sqlite3 reads it",
    "model_config": "server/access_api.py: pydantic reads it",
    "__wrapped__": "scripts/paired_timing.py: inspect reads it",
}


def unused(ignore_names=None):
    """vulture's report for the product code, as Item objects."""
    here = os.getcwd()
    os.chdir(REPO)
    try:
        finder = vulture.Vulture(
            ignore_names=ignore_names, ignore_decorators=DECORATORS
        )
        finder.scavenge(PATHS, exclude=EXCLUDE)
        return finder.get_unused_code(min_confidence=MIN_CONFIDENCE)
    finally:
        os.chdir(here)


class UnusedCodeTest(unittest.TestCase):
    def test_nothing_unused(self):
        found = [item.get_report() for item in unused(list(KEEP))]
        self.assertEqual(
            found,
            [],
            "Delete these, or add them to KEEP in this file with the "
            "reason:\n" + "\n".join(found),
        )

    def test_keep_is_current(self):
        still_unused = {item.name for item in unused()}
        stale = sorted(set(KEEP) - still_unused)
        self.assertEqual(
            stale,
            [],
            "These are used or gone now; take them out of KEEP: "
            + ", ".join(stale),
        )

    def test_the_check_sees_tests_out(self):
        files = {os.path.relpath(item.filename, REPO) for item in unused()}
        self.assertFalse(
            [
                f
                for f in files
                if f.startswith(os.path.join("backend", "tests"))
            ]
        )


if __name__ == "__main__":
    unittest.main()
