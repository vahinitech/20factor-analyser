# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""A key shows where it works (owner, 2026-10-22): the stage analyser
(VAHINI_ENVIRONMENT=stage) issues vh_test_ keys and production vh_ keys.
Production refuses a vh_test_ key with its own message; stage still takes
the plain vh_ keys it issued before."""

import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# pylint: disable=wrong-import-position
from server import entitlements  # noqa: E402

STAGE = {"VAHINI_ENVIRONMENT": "stage"}
PRODUCTION = {"VAHINI_ENVIRONMENT": ""}


class KeyPrefixTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = folder.name + "/entitlements.sqlite"
        entitlements.initialize(self.db)
        env = patch.dict(os.environ, {"VAHINI_ENTITLEMENTS_DB": self.db})
        env.start()
        self.addCleanup(env.stop)

    def pro_key(self, env):
        """A Pro customer's key issued in this environment."""
        with patch.dict(os.environ, env):
            made = entitlements.grant(self.db, int(time.time()) + 86400)
        return made["key"]

    def access(self, key, env):
        with patch.dict(os.environ, env):
            return entitlements.access_for("Bearer " + key)

    def test_production_issues_vh_keys(self):
        for env in (PRODUCTION, {}, {"VAHINI_ENVIRONMENT": "production"}):
            with self.subTest(env=env):
                with patch.dict(os.environ, env):
                    if not env:
                        os.environ.pop("VAHINI_ENVIRONMENT", None)
                    customer = entitlements.create_customer(self.db)
                    _, key = entitlements.issue_key(self.db, customer)
                self.assertTrue(key.startswith("vh_"))
                self.assertFalse(key.startswith("vh_test_"))
                self.assertEqual(len(key), len("vh_") + 43)

    def test_stage_issues_vh_test_keys(self):
        with patch.dict(os.environ, STAGE):
            customer = entitlements.create_customer(self.db)
            _, key = entitlements.issue_key(self.db, customer)
        self.assertTrue(key.startswith("vh_test_"))
        self.assertEqual(len(key), len("vh_test_") + 43)
        self.assertTrue(self.pro_key(STAGE).startswith("vh_test_"))

    def test_stage_spelled_any_case_counts(self):
        self.assertTrue(
            entitlements.on_stage({"VAHINI_ENVIRONMENT": " Stage "})
        )
        self.assertFalse(entitlements.on_stage({"VAHINI_ENVIRONMENT": "prod"}))
        self.assertFalse(entitlements.on_stage({}))

    def test_a_stage_key_unlocks_pro_on_stage(self):
        key = self.pro_key(STAGE)
        self.assertEqual(self.access(key, STAGE)["tier"], "pro")

    def test_production_refuses_a_stage_key_and_says_why(self):
        key = self.pro_key(STAGE)
        with self.assertRaises(HTTPException) as refused:
            self.access(key, PRODUCTION)
        self.assertEqual(refused.exception.status_code, 401)
        self.assertIn("stage.vahinitech.com", refused.exception.detail)

    def test_stage_still_takes_its_older_vh_keys(self):
        key = self.pro_key(PRODUCTION)
        self.assertFalse(key.startswith("vh_test_"))
        self.assertEqual(self.access(key, STAGE)["tier"], "pro")
        self.assertEqual(self.access(key, PRODUCTION)["tier"], "pro")


if __name__ == "__main__":
    unittest.main()
