# SPDX-License-Identifier: AGPL-3.0-only
"""Free checks per IP per day (daily_limit.py; owner decision 2026-10-09)."""

import importlib.util
import os
import sys
import unittest
from datetime import datetime
from types import SimpleNamespace

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, SERVER_DIR)

from starlette.exceptions import (  # noqa: E402  pylint: disable=wrong-import-position
    HTTPException,
)
from daily_limit import (  # noqa: E402  pylint: disable=wrong-import-position
    IST,
    DailyLimit,
)

# White-box tests reach into the server module's helpers.
# pylint: disable=protected-access


def request(peer, real_ip=None):
    headers = {"x-real-ip": real_ip} if real_ip else {}
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=IST).timestamp()


class DailyLimitTests(unittest.TestCase):
    def setUp(self):
        self.now = at("2026-10-09T10:00:00")
        self.limit = DailyLimit(
            limit=3, exempt="2a0d:f302:135:e2f4::1", clock=lambda: self.now
        )

    def use(self, req):
        self.limit.spend(self.limit.check(req))

    def test_three_a_day_then_429_until_midnight_india_time(self):
        visitor = request("172.18.0.5", "49.36.10.20")  # nginx -> analyser
        for _ in range(3):
            self.use(visitor)
        with self.assertRaises(HTTPException) as hit:
            self.limit.check(visitor)
        self.assertEqual(hit.exception.status_code, 429)
        self.assertEqual(hit.exception.detail["error_code"], "daily_limit")
        self.assertIn("Come back tomorrow", hit.exception.detail["error"])
        self.assertEqual(hit.exception.headers["Retry-After"], str(14 * 3600))
        self.now = at("2026-10-10T00:00:01")
        self.use(visitor)  # a new day in India: three again

    def test_addresses_are_counted_apart(self):
        for _ in range(3):
            self.use(request("172.18.0.5", "49.36.10.20"))
        self.use(request("172.18.0.5", "49.36.10.21"))

    def test_only_spent_checks_count(self):
        visitor = request("172.18.0.5", "49.36.10.20")
        for _ in range(10):
            self.limit.check(visitor)  # refused or failed checks: no spend
        self.use(visitor)

    def test_header_trusted_only_from_the_proxy(self):
        # From a public address the header is ignored: no forging a new IP.
        forged = [request("49.36.10.99", f"49.37.0.{i}") for i in range(4)]
        for req in forged[:3]:
            self.use(req)
        with self.assertRaises(HTTPException):
            self.limit.check(forged[3])

    def test_not_counted(self):
        self.assertIsNone(self.limit.client(request("127.0.0.1")))  # CI
        self.assertIsNone(self.limit.client(request("testclient")))
        self.assertIsNone(self.limit.client(request("172.18.0.5")))  # docker
        self.assertIsNone(
            self.limit.client(request("172.18.0.5", "192.168.1.4"))
        )
        self.assertIsNone(  # the server's own stage check
            self.limit.client(request("172.18.0.5", "2a0d:f302:135:e2f4::1"))
        )
        visitor = request("172.18.0.5", "49.36.10.20")
        for _ in range(5):
            self.assertIsNone(self.limit.check(visitor, exempt=True))  # Pro
        off = DailyLimit(limit=0, exempt="", clock=lambda: self.now)
        self.assertIsNone(off.check(visitor))


class EndpointTests(unittest.TestCase):
    """The real app: reports count, refusals do not, the 4th is a 429."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "ppocr_server_daily_limit",
            os.path.join(SERVER_DIR, "ppocr-server.py"),
        )
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)
        from fastapi.testclient import (  # pylint: disable=import-outside-toplevel
            TestClient,
        )

        cls.client = TestClient(cls.mod.app)

    def setUp(self):
        self.mod._is_pro = self._free

        # The test client is not a network peer; count it as one visitor.
        self.mod.DAILY = DailyLimit(limit=3, exempt="")
        self.mod.DAILY.client = lambda _request: "49.36.10.20"
        self.answers = []

        async def fake_report(*_args, **_kwargs):
            return self.answers.pop(0)

        self.mod._report_payload = fake_report

    @staticmethod
    async def _free(_authorization):
        return False

    def post(self):
        return self.client.post(
            "/report-python",
            files={"image": ("page.png", b"\x89PNG fake", "image/png")},
        )

    def test_paid_tier_is_never_limited(self):
        async def pro(_authorization):
            return True

        self.mod._is_pro = pro
        self.answers = [{"ok": True, "analysis": {"results": []}}] * 6
        codes = [self.post().status_code for _ in range(6)]
        self.assertEqual(codes, [200] * 6)

    def test_reports_count_refusals_do_not(self):
        refusal = {"ok": False, "error_code": "no_handwriting"}
        report = {"ok": True, "analysis": {"results": []}}
        self.answers = [refusal, refusal, report, report, refusal, report]
        codes = [self.post().status_code for _ in range(6)]
        self.assertEqual(codes, [200] * 6)  # two refusals cost nothing
        blocked = self.post()
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.json()["detail"]["error_code"], "daily_limit")
        self.assertTrue(int(blocked.headers["Retry-After"]) > 0)


if __name__ == "__main__":
    unittest.main()
