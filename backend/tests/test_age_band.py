# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The request's optional age band (age_band.py, #212): which values it
takes, that a refused one answers before the scan, that a valid one is
echoed in every report shape and schema, and that no score reads it."""

import importlib.util
import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import age_band  # noqa: E402
import compact_reports  # noqa: E402
import contract_schemas  # noqa: E402
import entitlements  # noqa: E402
from report_contract import public_report  # noqa: E402
from backend.tests.test_comparison_data import read_payload  # noqa: E402
from backend.tests.test_schemas import realistic_payload  # noqa: E402


def load_server():
    path = Path(__file__).resolve().parents[1] / "ppocr-server.py"
    spec = importlib.util.spec_from_file_location("age_band_server", path)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    return server


class Parse(unittest.TestCase):
    def test_two_whole_year_ages_in_order(self):
        for text in ("6-7", "3-4", "5-8", "17-18", " 9-10 "):
            self.assertEqual(age_band.parse(text), text.strip())

    def test_nothing_sent_is_none(self):
        for text in ("", "  ", None):
            self.assertIsNone(age_band.parse(text))

    def test_birth_dates_single_ages_and_reversed_bands_are_refused(self):
        refused = (
            "2019-05-01",
            "2019-05",
            "7",
            "7-7",
            "8-6",
            "2-3",
            "18-19",
            "6 - 7",
            "06-07",
            "6-7 years",
        )
        for text in refused:
            with self.assertRaises(ValueError, msg=text):
                age_band.parse(text)

    def test_the_schema_patterns_take_the_same_ages(self):
        ages = range(0, 30)
        taken = [
            a
            for a in ages
            if re.fullmatch(age_band.BAND_PATTERN, f"{a}-{a}") is not None
        ]
        self.assertEqual(taken, list(range(age_band.YOUNGEST, 19)))
        self.assertEqual(age_band.OLDEST, 18)
        self.assertIsNotNone(re.fullmatch(age_band.PATTERN, ""))
        self.assertIsNone(re.fullmatch(age_band.BAND_PATTERN, ""))


class RequestField(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = load_server()

    def setUp(self):
        self.fake = AsyncMock(return_value=read_payload("a cat"))
        scan = patch.object(self.server, "_report_payload", new=self.fake)
        scan.start()
        self.addCleanup(scan.stop)
        # No engine warm-up at start-up: its thread would build (and,
        # without paddleocr, cache a failed) engine while later test
        # files count how often an engine is built.
        quiet = patch.dict(os.environ, {"VAHINI_OCR_PRELOAD_ON_START": "0"})
        quiet.start()
        self.addCleanup(quiet.stop)

    def post(self, band):
        """The same band to every report route and shape."""
        answers = []
        with TestClient(self.server.app) as client:
            for route in (
                "/api/v2/reports",
                "/api/v2/reports?format=compact",
                "/report-python",
            ):
                answers.append(
                    client.post(
                        route,
                        files={"image": ("test.png", b"synthetic")},
                        data={"age_band": band},
                    )
                )
        return answers

    def test_a_refused_band_answers_before_the_scan(self):
        for band in ("2019-05-01", "7-6", "7"):
            for answer in self.post(band):
                self.assertEqual(answer.status_code, 422)
                detail = answer.json()["detail"]
                self.assertEqual(detail["error_code"], age_band.ERROR_CODE)
                self.assertEqual(detail["field"], "age_band")
                self.assertEqual(
                    contract_schemas.errors("error", answer.json()), []
                )
        self.fake.assert_not_called()

    def test_a_valid_band_is_echoed_and_changes_nothing_else(self):
        plain = [a.json() for a in self.post("")]
        banded = [a.json() for a in self.post("6-7")]
        for before, after in zip(plain, banded):
            self.assertNotIn("age_band", before)
            self.assertEqual(after.pop("age_band"), "6-7")
            for key in ("_meta", "elapsed_ms"):
                before.pop(key, None)
                after.pop(key, None)
            self.assertEqual(before, after)

    def test_the_cached_payload_is_not_changed(self):
        self.post("6-7")
        self.assertNotIn("age_band", self.fake.return_value)


class Schemas(unittest.TestCase):
    def test_both_report_shapes_accept_the_echo(self):
        free = entitlements.access_for(None)
        payload = dict(realistic_payload(ok=True), age_band="6-7")
        expanded = public_report(payload, free)
        compact = compact_reports.build_compact(payload, free)
        for name, report in (
            ("report-expanded", expanded),
            ("report-compact", compact),
        ):
            self.assertEqual(report["age_band"], "6-7")
            self.assertEqual(contract_schemas.errors(name, report), [])
            report["age_band"] = "2019-05"
            self.assertNotEqual(contract_schemas.errors(name, report), [])

    def test_without_a_band_there_is_no_field(self):
        free = entitlements.access_for(None)
        payload = realistic_payload(ok=True)
        self.assertNotIn("age_band", public_report(payload, free))
        self.assertNotIn(
            "age_band", compact_reports.build_compact(payload, free)
        )

    def test_the_request_schema_takes_the_field(self):
        form = contract_schemas.load("report-request")["properties"]["form"]
        field = form["properties"]["age_band"]
        self.assertEqual(field["pattern"], age_band.PATTERN)
        self.assertEqual(field["default"], "")


if __name__ == "__main__":
    unittest.main()
