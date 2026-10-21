# SPDX-License-Identifier: AGPL-3.0-only
"""Internal access API: guards, routes and contract, on a synthetic ledger."""

import contextlib
import importlib.util
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from server import access_api
from report import contract_schemas
from server import entitlements

BASE = access_api.PREFIX
TOKEN = "t" * 40
SERVER = None


def load_server():
    """Import server/app.py once; it is slow and has no side effects."""
    global SERVER  # pylint: disable=global-statement
    if SERVER is None:
        spec = importlib.util.spec_from_file_location(
            "access_api_test_server",
            Path(__file__).resolve().parents[1] / "server/app.py",
        )
        SERVER = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(SERVER)
    return SERVER


class LedgerRules(unittest.TestCase):
    """check_state and grant, without HTTP."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = self.folder.name + "/entitlements.sqlite"
        entitlements.initialize(self.db)

    def test_check_state(self):
        later = int(time.time()) + 60
        for good in (
            ("pro", "active", later),
            ("pro", "cancelled", later),
            ("free", "active", None),
            ("free", "revoked", later),
        ):
            entitlements.check_state(*good)
        for bad in (
            ("trial", "active", later),
            ("pro", "paused", later),
            ("pro", "active", None),
            ("pro", "active", 0),
            ("pro", "active", True),
            ("pro", "active", float(later)),
            ("pro", "active", str(later)),
            ("free", "active", -5),
            ("free", "active", "soon"),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                entitlements.check_state(*bad)

    def test_grant_writes_everything_or_nothing(self):
        end = int(time.time()) + 3600
        made = entitlements.grant(self.db, end)
        self.assertEqual(made["expires_at"], end)
        with patch.dict(os.environ, {"VAHINI_ENTITLEMENTS_DB": self.db}):
            access = entitlements.access_for("Bearer " + made["key"])
        self.assertEqual(access["tier"], "pro")
        self.assertEqual(access["customer_id"], made["customer_id"])
        shown = entitlements.describe_customer(self.db, made["customer_id"])
        self.assertEqual(
            [entry["action"] for entry in shown["audit"]],
            [
                f"key:issue:{made['key_id']}",
                f"subscription:pro:active:{end}",
            ],
        )
        for bad in (None, 0, int(time.time()) - 1, "x"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                entitlements.grant(self.db, bad)
        with patch.object(
            entitlements.secrets, "token_hex", return_value="0" * 24
        ):
            entitlements.grant(self.db, end)  # first one with that id
            with self.assertRaises(sqlite3.IntegrityError):  # id collides
                entitlements.grant(self.db, end)
        with contextlib.closing(sqlite3.connect(self.db)) as connection:
            counts = [
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[
                    0
                ]
                for table in ("customers", "api_keys", "audit")
            ]
        self.assertEqual(counts, [2, 2, 4])  # failed grants left nothing

    def test_revoke_key_returns_its_customer(self):
        made = entitlements.grant(self.db, int(time.time()) + 60)
        self.assertEqual(
            entitlements.revoke_key(self.db, made["key_id"]),
            made["customer_id"],
        )


class AccessAPITests(unittest.TestCase):
    """The HTTP routes, through the real server application."""

    @classmethod
    def setUpClass(cls):
        cls.server = load_server()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = self.folder.name + "/entitlements.sqlite"
        entitlements.initialize(self.db)
        self.token_file = self.folder.name + "/access-token"
        Path(self.token_file).write_text(TOKEN + "\n", encoding="ascii")
        env = patch.dict(
            os.environ,
            {
                "VAHINI_ENTITLEMENTS_DB": self.db,
                access_api.TOKEN_FILE_ENV: self.token_file,
            },
        )
        env.start()
        self.addCleanup(env.stop)
        self.client = TestClient(self.server.app)
        self.auth = {"Authorization": "Bearer " + TOKEN}
        self.responses = []

    def send(self, method, path, schema=None, status=200, **kwargs):
        headers = {**self.auth, **kwargs.pop("headers", {})}
        response = self.client.request(
            method, BASE + path, headers=headers, **kwargs
        )
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        body = response.json()
        self.assertEqual(
            contract_schemas.errors(schema or "error", body), [], body
        )
        self.responses.append(response.text)
        return body

    def grant(self, seconds=3600):
        end = int(time.time()) + seconds
        body = {"expires_at": end}
        self.assertEqual(contract_schemas.errors("access-request", body), [])
        return self.send("POST", "/grants", "access-key", 201, json=body)

    def me(self, key):
        return self.client.get(
            "/api/v2/me", headers={"Authorization": "Bearer " + key}
        )

    def digests(self):
        with contextlib.closing(sqlite3.connect(self.db)) as connection:
            return [
                row[0]
                for row in connection.execute("SELECT digest FROM api_keys")
            ]

    def test_off_without_a_usable_token_file(self):
        cases = (
            {access_api.TOKEN_FILE_ENV: ""},
            {access_api.TOKEN_FILE_ENV: self.folder.name + "/absent"},
            {access_api.TOKEN_FILE_ENV: self.folder.name},
        )
        short = self.folder.name + "/short"
        Path(short).write_text("s" * 31, encoding="ascii")
        cases += ({access_api.TOKEN_FILE_ENV: short},)
        for env in cases:
            with self.subTest(env=env), patch.dict(os.environ, env):
                for method, path in (
                    ("POST", "/grants"),
                    ("GET", "/customers/cus_x"),
                    ("DELETE", "/grants"),
                    ("GET", "/nothing-here"),
                ):
                    response = self.client.request(
                        method,
                        BASE + path,
                        headers=self.auth,
                        content=b"{not json",
                    )
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(response.json(), {"detail": "Not Found"})
        with patch.dict(os.environ):
            del os.environ[access_api.TOKEN_FILE_ENV]
            self.assertIsNone(access_api.configured_token())

    def test_proxied_requests_are_not_found(self):
        for header in (
            "X-Forwarded-For",
            "X-Real-IP",
            "Forwarded",
            "CF-Connecting-IP",
            "x-forwarded-for",
        ):
            with self.subTest(header=header):
                response = self.client.post(
                    BASE + "/grants",
                    headers={**self.auth, header: "203.0.113.9"},
                    json={"expires_at": int(time.time()) + 60},
                )
                self.assertEqual(response.status_code, 404)
        self.assertEqual(self.digests(), [])

    def test_wrong_or_missing_token_is_401(self):
        for headers in (
            {},
            {"Authorization": "Bearer " + TOKEN[:-1]},
            {"Authorization": "Bearer " + TOKEN + "x"},
            {"Authorization": TOKEN},
            {"Authorization": "Basic " + TOKEN},
            {"Authorization": "Bearer vh_" + "a" * 40},
        ):
            with self.subTest(headers=headers):
                response = self.client.post(
                    BASE + "/grants",
                    headers=headers,
                    json={"expires_at": int(time.time()) + 60},
                )
                self.assertEqual(response.status_code, 401)
                self.assertEqual(
                    response.headers["www-authenticate"], "Bearer"
                )
                self.assertEqual(
                    contract_schemas.errors("error", response.json()), []
                )
        self.assertEqual(self.digests(), [])

    def test_token_file_is_read_per_request(self):
        self.send("GET", "/customers/cus_unknown", status=404)
        Path(self.token_file).write_text("n" * 32, encoding="ascii")
        self.send("GET", "/customers/cus_unknown", status=401)

    def test_grant_gives_pro_through_access_for(self):
        made = self.grant()
        self.assertTrue(made["key"].startswith("vh_"))
        access = entitlements.access_for("Bearer " + made["key"])
        self.assertEqual(access["tier"], "pro")
        self.assertEqual(access["customer_id"], made["customer_id"])
        me = self.me(made["key"])
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["access"]["tier"], "pro")
        shown = self.send(
            "GET", f"/customers/{made['customer_id']}", "access-customer"
        )
        self.assertEqual(shown["effective"]["tier"], "pro")
        self.assertEqual(
            [k["key_id"] for k in shown["keys"]], [made["key_id"]]
        )
        self.send(
            "POST", "/grants", status=422, json={"expires_at": 1}
        )  # in the past

    def test_subscription_changes(self):
        made = self.grant()
        path = f"/customers/{made['customer_id']}/subscription"
        end = int(time.time()) + 7200
        changes = (
            ({"tier": "pro", "status": "cancelled", "expires_at": end}, "pro"),
            ({"tier": "pro", "status": "expired", "expires_at": end}, "free"),
            ({"tier": "free", "status": "active"}, "free"),
            ({"tier": "pro", "status": "active", "expires_at": end}, "pro"),
        )
        for body, tier in changes:
            with self.subTest(body=body):
                self.assertEqual(
                    contract_schemas.errors("access-request", body), []
                )
                shown = self.send("PUT", path, "access-customer", json=body)
                self.assertEqual(shown["effective"]["tier"], tier)
                self.assertEqual(shown["tier"], body["tier"])
                self.assertEqual(shown["status"], body["status"])
                self.assertEqual(
                    self.me(made["key"]).json()["access"]["tier"], tier
                )
        self.send(
            "PUT",
            path,
            status=422,
            json={"tier": "pro", "status": "active"},
        )
        self.send(
            "PUT",
            "/customers/cus_unknown/subscription",
            status=404,
            json={"tier": "free", "status": "active"},
        )

    def test_new_key_and_revoke(self):
        made = self.grant()
        second = self.send(
            "POST",
            f"/customers/{made['customer_id']}/keys",
            "access-key",
            201,
        )
        self.assertNotEqual(second["key"], made["key"])
        self.assertEqual(second["expires_at"], made["expires_at"])
        self.assertEqual(
            self.me(second["key"]).json()["access"]["tier"], "pro"
        )
        shown = self.send(
            "POST", f"/keys/{made['key_id']}/revoke", "access-customer"
        )
        self.assertEqual(
            {k["key_id"]: k["revoked"] for k in shown["keys"]},
            {made["key_id"]: True, second["key_id"]: False},
        )
        self.assertEqual(
            shown["audit"][-1]["action"], "key:revoke:" + made["key_id"]
        )
        self.assertEqual(self.me(made["key"]).status_code, 401)
        self.assertEqual(self.me(second["key"]).status_code, 200)
        self.send("POST", "/customers/cus_unknown/keys", status=404)
        self.send("POST", "/keys/key_unknown/revoke", status=404)

    def test_lookup(self):
        made = self.grant()
        found = self.send(
            "POST",
            "/keys/lookup",
            "access-key-lookup",
            json={"key": made["key"]},
        )
        self.assertEqual(found["key_id"], made["key_id"])
        self.assertEqual(found["customer_id"], made["customer_id"])
        self.assertEqual(found["access"]["tier"], "pro")
        self.send("POST", f"/keys/{made['key_id']}/revoke", "access-customer")
        found = self.send(
            "POST",
            "/keys/lookup",
            "access-key-lookup",
            json={"key": made["key"]},
        )
        self.assertTrue(found["revoked"])
        self.assertIsNone(found["access"])
        missing = self.send(
            "POST", "/keys/lookup", status=404, json={"key": "vh_" + "b" * 43}
        )
        self.assertEqual(missing, {"detail": "Unknown API key"})
        self.assertNotIn(made["key"], "".join(self.responses[1:]))

    def test_unknown_customer_is_404(self):
        self.send("GET", "/customers/cus_unknown", status=404)

    def test_bodies_are_closed(self):
        later = int(time.time()) + 60
        for path, method, body in (
            ("/grants", "POST", {"expires_at": later, "tier": "pro"}),
            ("/grants", "POST", {"expires_at": str(later)}),
            ("/grants", "POST", {"expires_at": True}),
            ("/grants", "POST", {}),
            ("/keys/lookup", "POST", {"key": "vh_x", "customer_id": "x"}),
            ("/keys/lookup", "POST", {"key": 5}),
            (
                "/customers/cus_x/subscription",
                "PUT",
                {"tier": "trial", "status": "active"},
            ),
            (
                "/customers/cus_x/subscription",
                "PUT",
                {"tier": "free", "status": "active", "note": "x"},
            ),
        ):
            with self.subTest(path=path, body=body):
                self.send(method, path, status=422, json=body)
                self.assertNotEqual(
                    contract_schemas.errors("access-request", body), []
                )
        self.assertEqual(self.digests(), [])

    def test_ledger_failures_are_503(self):
        with patch.dict(os.environ, {"VAHINI_ENTITLEMENTS_DB": ""}):
            self.send("GET", "/customers/cus_x", status=503)
        with patch.dict(
            os.environ,
            {"VAHINI_ENTITLEMENTS_DB": self.folder.name + "/none.sqlite"},
        ):
            self.send("GET", "/customers/cus_x", status=503)
            self.send(
                "POST",
                "/grants",
                status=503,
                json={"expires_at": int(time.time()) + 60},
            )

    def test_no_digest_in_any_response(self):
        made = self.grant()
        customer = made["customer_id"]
        self.send("POST", f"/customers/{customer}/keys", "access-key", 201)
        self.send("GET", f"/customers/{customer}", "access-customer")
        self.send(
            "POST",
            "/keys/lookup",
            "access-key-lookup",
            json={"key": made["key"]},
        )
        self.send("POST", f"/keys/{made['key_id']}/revoke", "access-customer")
        digests = self.digests()
        self.assertEqual(len(digests), 2)
        text = "".join(self.responses)
        for digest in digests:
            self.assertNotIn(digest, text)
        self.assertNotIn("digest", text)


if __name__ == "__main__":
    unittest.main()
