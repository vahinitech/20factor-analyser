# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The privacy results file for the website's status page
(scripts/privacy_results.py): pass and fail only, nothing guessed for a
test that did not run, and nothing but ids, results and a time."""

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


class PrivacyResultsTests(unittest.TestCase):
    """What the status page is told about each privacy test."""

    def test_success_is_pass_and_failure_is_fail(self):
        data = privacy_results.record(
            ["privacy-card=success", "who-checks=failure"], NOW
        )
        self.assertEqual(
            data,
            {
                "version": 1,
                "finished_at": "2026-11-25T05:42:20Z",
                "results": {"privacy-card": "pass", "who-checks": "fail"},
            },
        )

    def test_a_test_that_did_not_run_has_no_result(self):
        data = privacy_results.record(
            [
                "print-popup=skipped",
                "check-page-who=cancelled",
                "identifiers=",
            ],
            NOW,
        )
        self.assertEqual(data["results"], {})

    def test_an_unknown_id_is_refused(self):
        with self.assertRaises(ValueError):
            privacy_results.results(["keep-pages=success"])
        with self.assertRaises(ValueError):
            privacy_results.results(["privacy-card"])

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
        for test_id in privacy_results.TESTS:
            self.assertEqual(named.count(f"{test_id}="), 1, test_id)
        gate = "if: always() && github.event_name == 'push'"
        self.assertEqual(ci.count(gate), 4, "record and upload, two jobs")

    def test_the_file_holds_ids_results_and_a_time_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "privacy-tests.json")
            code = privacy_results.main(
                ["--out", out, "identifiers=success", "who-checks=success"]
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
