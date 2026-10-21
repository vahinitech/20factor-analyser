# SPDX-License-Identifier: AGPL-3.0-only
"""Operator lookups and key audit rows, with a synthetic ledger only."""

import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import entitlements
from server import subscription_admin


class SubscriptionAdminTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = self.folder.name + "/entitlements.sqlite"
        entitlements.initialize(self.db)
        self.env = patch.dict(os.environ, {"VAHINI_ENTITLEMENTS_DB": self.db})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.customer = entitlements.create_customer(self.db)
        self.key_id, self.token = entitlements.issue_key(
            self.db, self.customer
        )

    def cli(self, *argv):
        """Run the tool in-process; returns exit code, stdout, stderr."""
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with patch.object(
            sys, "argv", ["subscription_admin", "--db", self.db, *argv]
        ), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                subscription_admin.main()
            except SystemExit as stop:
                code = stop.code or 0
        return code, out.getvalue(), err.getvalue()

    def secret_file(self, text, mode=0o600):
        path = self.folder.name + "/key"
        with contextlib.suppress(FileNotFoundError):
            os.unlink(path)
        Path(path).write_text(text, encoding="ascii")
        os.chmod(path, mode)
        return path

    def audit(self):
        with contextlib.closing(sqlite3.connect(self.db)) as connection:
            return [
                row[0]
                for row in connection.execute(
                    "SELECT action FROM audit WHERE customer_id=? ORDER BY id",
                    (self.customer,),
                )
            ]

    def test_issue_and_revoke_are_audited_by_key_id_only(self):
        entitlements.revoke_key(self.db, self.key_id)
        self.assertEqual(
            self.audit(),
            [f"key:issue:{self.key_id}", f"key:revoke:{self.key_id}"],
        )
        with contextlib.closing(sqlite3.connect(self.db)) as connection:
            (digest,) = connection.execute(
                "SELECT digest FROM api_keys WHERE id=?", (self.key_id,)
            ).fetchone()
            dump = "\n".join(connection.iterdump())
        self.assertNotIn(self.token, dump)
        self.assertEqual(dump.count(digest), 1)  # the api_keys row only
        with self.assertRaises(ValueError):
            entitlements.revoke_key(self.db, "key_unknown")

    def test_failed_delivery_audits_issue_then_revoke(self):
        target = self.folder.name + "/missing-dir/key"
        with self.assertRaises(OSError):
            subscription_admin.write_customer_key(
                self.db, self.customer, target
            )
        self.assertEqual(len(self.audit()), 1)  # no key was issued
        with patch.object(
            subscription_admin.os, "fsync", side_effect=OSError("disk")
        ), self.assertRaises(OSError):
            subscription_admin.write_customer_key(
                self.db, self.customer, self.folder.name + "/newkey"
            )
        actions = self.audit()[1:]
        self.assertEqual(
            [a.split(":")[1] for a in actions], ["issue", "revoke"]
        )
        self.assertEqual(actions[0].split(":")[2], actions[1].split(":")[2])

    def test_show_customer_matches_access_for(self):
        end = int(time.time()) + 3600
        entitlements.set_subscription(
            self.db, self.customer, "pro", "cancelled", end
        )
        second, _ = entitlements.issue_key(self.db, self.customer)
        entitlements.revoke_key(self.db, second)
        code, out, _ = self.cli("show-customer", self.customer)
        self.assertEqual(code, 0)
        shown = json.loads(out)
        live = entitlements.access_for("Bearer " + self.token)
        for field in (
            "customer_id",
            "tier",
            "plan_tier",
            "subscription_status",
            "expires_at",
        ):
            self.assertEqual(shown["effective"][field], live[field])
        self.assertEqual(shown["effective"]["tier"], "pro")
        self.assertEqual(
            (shown["tier"], shown["status"]), ("pro", "cancelled")
        )
        self.assertEqual(
            {k["key_id"]: k["revoked"] for k in shown["keys"]},
            {self.key_id: False, second: True},
        )
        self.assertEqual(
            [entry["action"] for entry in shown["audit"]],
            [
                f"key:issue:{self.key_id}",
                f"subscription:pro:cancelled:{end}",
                f"key:issue:{second}",
                f"key:revoke:{second}",
            ],
        )
        self.assertNotIn("digest", out)

    def test_show_customer_reports_expiry_like_access_for(self):
        with patch.object(entitlements.time, "time", return_value=1000):
            entitlements.set_subscription(
                self.db, self.customer, "pro", "active", 2000
            )
        shown = entitlements.describe_customer(self.db, self.customer)
        self.assertEqual(shown["effective"]["tier"], "free")
        self.assertEqual(shown["effective"]["subscription_status"], "expired")
        code, _, err = self.cli("show-customer", "cus_unknown")
        self.assertEqual(code, 1)
        self.assertIn("Unknown customer", err)

    def test_lookups_never_write(self):
        before = Path(self.db).read_bytes()
        self.cli("show-customer", self.customer)
        self.cli("check-key", "--secret-file", self.secret_file(self.token))
        self.assertEqual(Path(self.db).read_bytes(), before)
        os.chmod(self.db, 0o400)  # a read-only ledger still answers
        code, _, _ = self.cli("show-customer", self.customer)
        self.assertEqual(code, 0)

    def test_check_key_maps_secret_without_printing_it(self):
        entitlements.set_subscription(
            self.db, self.customer, "pro", "active", int(time.time()) + 60
        )
        code, out, err = self.cli(
            "check-key", "--secret-file", self.secret_file(self.token + "\n")
        )
        self.assertEqual(code, 0)
        self.assertNotIn(self.token, out + err)
        self.assertNotIn(self.token[3:20], out + err)
        result = json.loads(out)
        self.assertTrue(result["found"])
        self.assertEqual(result["key_id"], self.key_id)
        self.assertEqual(result["customer_id"], self.customer)
        self.assertEqual(result["access"]["tier"], "pro")

    def test_check_key_revoked_and_unknown(self):
        entitlements.revoke_key(self.db, self.key_id)
        code, out, _ = self.cli(
            "check-key", "--secret-file", self.secret_file(self.token)
        )
        result = json.loads(out)
        self.assertEqual(code, 0)
        self.assertTrue(result["revoked"])
        self.assertIsNone(result["access"])
        code, out, _ = self.cli(
            "check-key", "--secret-file", self.secret_file("vh_notakey")
        )
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out), {"found": False})

    def test_check_key_refuses_unsafe_files(self):
        loose = self.secret_file(self.token, mode=0o644)
        code, out, err = self.cli("check-key", "--secret-file", loose)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("0600", err)
        self.assertNotIn(self.token, err)
        link = self.folder.name + "/link"
        os.symlink(self.secret_file(self.token), link)
        code, _, err = self.cli("check-key", "--secret-file", link)
        self.assertEqual(code, 1)
        self.assertNotIn(self.token, err)
        junk = self.secret_file("not a key at all")
        code, _, err = self.cli("check-key", "--secret-file", junk)
        self.assertEqual(code, 1)
        self.assertNotIn("not a key at all", err)
        code, _, _ = self.cli(
            "check-key", "--secret-file", self.folder.name + "/absent"
        )
        self.assertEqual(code, 1)

    def test_secret_is_never_an_argument(self):
        with patch.object(
            sys, "argv", ["x", "--db", self.db, "check-key", self.token]
        ), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(
            SystemExit
        ):
            subscription_admin.main()


class ListCustomersTests(unittest.TestCase):
    """list-customers: every plan at a glance, read-only, no key ids."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = self.folder.name + "/entitlements.sqlite"
        entitlements.initialize(self.db)
        now = int(time.time())
        self.soon = entitlements.create_customer(self.db)
        entitlements.set_subscription(
            self.db, self.soon, "pro", "active", now + 3 * 86400
        )
        self.later = entitlements.create_customer(self.db)
        entitlements.set_subscription(
            self.db, self.later, "pro", "cancelled", now + 60 * 86400
        )
        self.lapsed = entitlements.create_customer(self.db)
        entitlements.set_subscription(
            self.db, self.lapsed, "pro", "active", now - 10
        )
        self.free = entitlements.create_customer(self.db)
        self.key_id, self.token = entitlements.issue_key(self.db, self.soon)
        second, _ = entitlements.issue_key(self.db, self.soon)
        entitlements.revoke_key(self.db, second)

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with patch.object(
            sys, "argv", ["subscription_admin", "--db", self.db, *argv]
        ), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                subscription_admin.main()
            except SystemExit as stop:
                code = stop.code or 0
        return code, out.getvalue(), err.getvalue()

    def test_lists_every_customer_with_effective_access(self):
        code, out, _ = self.cli("list-customers")
        self.assertEqual(code, 0)
        listed = json.loads(out)
        self.assertEqual(listed["count"], 4)
        by_id = {c["customer_id"]: c for c in listed["customers"]}
        self.assertEqual(by_id[self.soon]["effective_tier"], "pro")
        self.assertEqual(
            (
                by_id[self.soon]["keys_active"],
                by_id[self.soon]["keys_revoked"],
            ),
            (1, 1),
        )
        self.assertEqual(by_id[self.later]["effective_tier"], "pro")
        self.assertEqual(by_id[self.lapsed]["effective_tier"], "free")
        self.assertEqual(by_id[self.lapsed]["subscription_status"], "expired")
        self.assertEqual(by_id[self.free]["effective_tier"], "free")
        # Soonest expiry first, customers with no expiry last.
        self.assertEqual(listed["customers"][-1]["customer_id"], self.free)
        self.assertNotIn(self.key_id, out)
        self.assertNotIn(self.token, out)
        self.assertNotIn("digest", out)

    def test_filters(self):
        _, out, _ = self.cli("list-customers", "--tier", "pro")
        self.assertEqual(
            {c["customer_id"] for c in json.loads(out)["customers"]},
            {self.soon, self.later},
        )
        _, out, _ = self.cli("list-customers", "--expiring-within-days", "7")
        self.assertEqual(
            [c["customer_id"] for c in json.loads(out)["customers"]],
            [self.soon],
        )
        code, _, err = self.cli(
            "list-customers", "--expiring-within-days", "-1"
        )
        self.assertEqual(code, 1)
        self.assertIn("0 or more", err)

    def test_listing_never_writes(self):
        before = Path(self.db).read_bytes()
        self.cli("list-customers")
        self.assertEqual(Path(self.db).read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
