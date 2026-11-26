# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The privacy results file for the website's status page
(scripts/privacy_results.py): pass and fail only, nothing guessed for a
test that did not run, and nothing but ids, results and a time. Python
files are read from the discovery run's log, so nothing runs twice."""

import datetime
import importlib.util
import json
import os
import re
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(ROOT, "scripts", "privacy_results.py")
spec = importlib.util.spec_from_file_location("privacy_results", SCRIPT)
privacy_results = importlib.util.module_from_spec(spec)
spec.loader.exec_module(privacy_results)

NOW = datetime.datetime(2026, 11, 25, 5, 42, 20, tzinfo=datetime.timezone.utc)

# A -v discovery log as CI writes it: results, perf lines in between, and
# the summary. test_page_turn fails, an import error stops
# test_telugu_not_read, and test_benchmark never ran.
LOG = """\
test_ok (backend.tests.test_identifiers.T.test_ok) ... ok
test_ok (backend.tests.test_who_checks.T.test_ok) ... [perf] {"x":1}
ok
test_turn (backend.tests.test_page_turn.T.test_turn) ... FAIL
test_ok (backend.tests.test_not_writing_page.T.test_ok) ... ok
test_ok (backend.tests.test_handwriting_only.T.test_ok) ... ok
test_engine (backend.tests.test_regression_functional.T.test_engine) ... ok
test_telugu_not_read (unittest.loader._FailedTest.test_telugu_not_read) \
... ERROR

======================================================================
ERROR: test_telugu_not_read (unittest.loader._FailedTest.test_telugu_not_read)
----------------------------------------------------------------------
ImportError: Failed to import test module: test_telugu_not_read

======================================================================
FAIL: test_turn (backend.tests.test_page_turn.T.test_turn)
----------------------------------------------------------------------
Ran 7 tests in 1.000s

FAILED (failures=1, errors=1)
"""


class PrivacyResultsTests(unittest.TestCase):
    """What the status page is told about each privacy test."""

    def test_success_is_pass_and_failure_is_fail(self):
        data = privacy_results.record(
            ["privacy-card=success", "print-popup=failure"], now=NOW
        )
        self.assertEqual(
            data,
            {
                "version": 1,
                "finished_at": "2026-11-25T05:42:20Z",
                "results": {"privacy-card": "pass", "print-popup": "fail"},
            },
        )

    def test_a_test_that_did_not_run_has_no_result(self):
        data = privacy_results.record(
            ["print-popup=skipped", "check-page-who=cancelled"], now=NOW
        )
        self.assertEqual(data["results"], {})

    def test_an_unknown_id_is_refused(self):
        with self.assertRaises(ValueError):
            privacy_results.results(["keep-pages=success"])
        with self.assertRaises(ValueError):
            privacy_results.results(["privacy-card"])
        with self.assertRaises(ValueError):
            privacy_results.results(["identifiers=success"])  # from the log

    def test_python_files_are_read_from_the_log(self):
        self.assertEqual(
            privacy_results.unittest_results(LOG),
            {
                "identifiers": "pass",
                "who-checks": "pass",
                "reader-down": "pass",
                "page-turn": "fail",
                "handwriting-only": "pass",
                "not-writing-page": "pass",
                "telugu-not-read": "fail",
            },
        )

    def test_an_unfinished_run_gives_no_results(self):
        cut = LOG[: LOG.index("Ran 7")]
        self.assertEqual(privacy_results.unittest_results(cut), {})
        self.assertEqual(privacy_results.unittest_results(""), {})

    def test_every_test_file_exists(self):
        for path in privacy_results.TESTS.values():
            self.assertTrue(os.path.isfile(os.path.join(ROOT, path)), path)

    def test_ci_records_every_test_on_main_only(self):
        with open(
            os.path.join(ROOT, ".github", "workflows", "ci.yml"),
            encoding="utf-8",
        ) as handle:
            ci = handle.read()
        calls = re.findall(r"privacy_results\.py --out[^\n]*", ci)
        self.assertEqual(len(calls), 2, "one record step per job")
        named = " ".join(calls)
        self.assertIn("--unittest-log unittest.log", named)
        self.assertIn("| tee unittest.log", ci)
        self.assertIn("set -o pipefail", ci)
        for test_id, path in privacy_results.TESTS.items():
            want = 0 if privacy_results.module_of(path) else 1
            self.assertEqual(named.count(f"{test_id}="), want, test_id)
        gate = "if: always() && github.event_name == 'push'"
        self.assertEqual(ci.count(gate), 4, "record and upload, two jobs")

    def test_the_file_holds_ids_results_and_a_time_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "privacy-tests.json")
            code = privacy_results.main(
                ["--out", out, "--unittest-log", os.path.join(tmp, "no.log")]
                + ["privacy-card=success", "print-popup=success"]
            )
            self.assertEqual(code, 0)
            with open(out, encoding="utf-8") as handle:
                data = json.load(handle)
        self.assertEqual(sorted(data), ["finished_at", "results", "version"])
        self.assertRegex(
            data["finished_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$"
        )
        self.assertEqual(set(data["results"].values()), {"pass"})

    def test_main_exits_2_on_an_unknown_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "privacy-tests.json")
            self.assertEqual(privacy_results.main(["--out", out, "x=y"]), 2)
            self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
