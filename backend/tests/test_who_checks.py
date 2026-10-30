# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Who is checking (who_checks.py, DPDP Rules 2025 rule 10): where it is
required, every scan route answers 422 before reading the photo or
counting a free check; a Pro key is not asked; the answer is never
echoed; and where it is not required, nothing changes."""

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import who_checks  # noqa: E402
from report import contract_schemas  # noqa: E402
from backend.tests.test_comparison_data import read_payload  # noqa: E402

ROUTES = (
    "/api/v2/reports",
    "/api/v2/reports?format=compact",
    "/report-python",
    "/ocr",
    "/analyze-vl",
)


def load_server():
    path = Path(__file__).resolve().parents[1] / "server/app.py"
    spec = importlib.util.spec_from_file_location("who_server", path)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    return server


class Check(unittest.TestCase):
    def test_each_answer_is_taken(self):
        with patch.dict(os.environ, {"VAHINI_REQUIRE_WHO": "1"}):
            for value in who_checks.VALUES:
                self.assertEqual(who_checks.check(value), value)
                self.assertEqual(who_checks.check(f" {value.upper()} "), value)

    def test_missing_is_refused_only_where_required_and_without_pro(self):
        with patch.dict(os.environ, {"VAHINI_REQUIRE_WHO": "1"}):
            for text in ("", "  ", None):
                with self.assertRaises(ValueError):
                    who_checks.check(text)
                self.assertIsNone(who_checks.check(text, pro=True))
        with patch.dict(os.environ, {"VAHINI_REQUIRE_WHO": "0"}):
            self.assertIsNone(who_checks.check(""))

    def test_anything_else_is_refused_everywhere(self):
        for env in ("0", "1"):
            with patch.dict(os.environ, {"VAHINI_REQUIRE_WHO": env}):
                for text in ("child", "kid", "admin", "parent,teacher", "1"):
                    with self.assertRaises(ValueError, msg=text):
                        who_checks.check(text)

    def test_there_is_no_answer_for_a_child_alone(self):
        # A student is sent only with an adult's tick (report-share.js);
        # there is no value meaning "a child, on their own".
        self.assertEqual(
            set(who_checks.VALUES),
            {"parent", "teacher", "self", "student", "sample"},
        )


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = load_server()

    def setUp(self):
        self.fake = AsyncMock(return_value=read_payload("a cat"))
        self.read = AsyncMock(side_effect=AssertionError("photo was read"))
        for name, mock in (
            ("_report_payload", self.fake),
            ("_read_upload", self.read),
        ):
            p = patch.object(self.server, name, new=mock)
            p.start()
            self.addCleanup(p.stop)
        env = patch.dict(
            os.environ,
            {"VAHINI_OCR_PRELOAD_ON_START": "0", "VAHINI_REQUIRE_WHO": "1"},
        )
        env.start()
        self.addCleanup(env.stop)

    def post(self, route, who=None, headers=None):
        data = {} if who is None else {"who": who}
        with TestClient(self.server.app) as client:
            return client.post(
                route,
                files={"image": ("test.png", b"synthetic")},
                data=data,
                headers=headers or {},
            )

    def test_a_free_check_without_an_answer_stops_before_the_photo(self):
        for route in ROUTES:
            for who in (None, "", "child"):
                answer = self.post(route, who)
                self.assertEqual(answer.status_code, 422, (route, who))
                detail = answer.json()["detail"]
                self.assertEqual(detail["error_code"], who_checks.ERROR_CODE)
                self.assertEqual(detail["field"], "who")
                self.assertEqual(
                    contract_schemas.errors("error", answer.json()), []
                )
        self.fake.assert_not_called()
        self.read.assert_not_called()

    def test_an_answer_lets_the_report_routes_run_and_is_not_echoed(self):
        for route in ROUTES[:3]:
            for who in who_checks.VALUES:
                answer = self.post(route, who)
                self.assertEqual(answer.status_code, 200, (route, who))
                body = json.dumps(answer.json())
                self.assertNotIn('"who"', body)
        self.assertTrue(self.fake.called)

    def test_a_pro_key_is_not_asked(self):
        pro = AsyncMock(return_value=True)
        access = {"tier": "pro", "plan_tier": "pro"}
        with patch.object(self.server, "_is_pro", new=pro), patch.object(
            self.server.entitlements,
            "access_for",
            return_value={
                **self.server.entitlements.access_for(None),
                **access,
            },
        ):
            answer = self.post(
                "/api/v2/reports?format=compact",
                headers={"Authorization": "Bearer vh_test_x"},
            )
            self.assertEqual(answer.status_code, 200)
            answer = self.post("/report-python")
            self.assertEqual(answer.status_code, 200)

    def test_not_required_means_older_clients_still_work(self):
        with patch.dict(os.environ, {"VAHINI_REQUIRE_WHO": "0"}):
            for route in ROUTES[:3]:
                self.assertEqual(self.post(route).status_code, 200, route)


if __name__ == "__main__":
    unittest.main()
