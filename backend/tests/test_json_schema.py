# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""One JSON Schema draft and one validator (report/json_schema.py): every
schema file declares draft-07 and is a valid draft-07 schema, the module
refuses any other draft, and no other code builds its own validator."""

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(SERVER_DIR)
sys.path.insert(0, SERVER_DIR)

# pylint: disable=wrong-import-position
from report import contract_schemas  # noqa: E402
from report import json_schema  # noqa: E402
from languages import profile  # noqa: E402

# A validator class from jsonschema, by name or through validator_for.
OWN_VALIDATOR = re.compile(r"\bDraft\d+Validator\b|\bvalidator_for\b")
THE_MODULE = os.path.join("backend", "report", "json_schema.py")


def tracked(*patterns):
    out = subprocess.run(
        ["git", "ls-files", *patterns],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [os.path.join(ROOT, p) for p in out]


class EverySchemaIsDraft7(unittest.TestCase):
    def test_every_schema_file_declares_draft_07_and_is_valid(self):
        files = tracked("*.schema.json")
        self.assertGreaterEqual(len(files), 19)
        for path in files:
            with self.subTest(schema=os.path.relpath(path, ROOT)):
                with open(path, encoding="utf-8") as f:
                    schema = json.load(f)
                self.assertEqual(schema.get("$schema"), json_schema.DRAFT)
                json_schema.check(schema)
                self.assertNotIn("$defs", json.dumps(schema))


# Next to a $ref, draft-07 reads nothing but notes: any other keyword there
# is silently skipped (draft 2019-09 and later apply it). Rules beside a
# $ref go in an allOf with it.
NOTES = {"description", "$comment", "title"}
ROOT_KEYS = {"$schema", "$id", "definitions"}


def refs_with_rules(node, path="", out=None, root=True):
    out = [] if out is None else out
    if isinstance(node, dict):
        if "$ref" in node:
            allowed = NOTES | (ROOT_KEYS if root else set())
            extra = sorted(set(node) - {"$ref"} - allowed)
            if extra:
                out.append(f"{path or '/'}: {', '.join(extra)}")
        for key, value in node.items():
            refs_with_rules(value, f"{path}/{key}", out, False)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            refs_with_rules(value, f"{path}/{i}", out, False)
    return out


class NoRuleBesideARef(unittest.TestCase):
    def test_no_schema_puts_a_rule_beside_a_ref(self):
        for path in tracked("*.schema.json"):
            with open(path, encoding="utf-8") as f:
                schema = json.load(f)
            with self.subTest(schema=os.path.relpath(path, ROOT)):
                self.assertEqual(refs_with_rules(schema), [])

    def test_the_check_finds_one(self):
        schema = {"items": {"$ref": "#/definitions/x", "minItems": 1}}
        self.assertEqual(refs_with_rules(schema), ["/items: minItems"])


class OneValidator(unittest.TestCase):
    def test_another_draft_or_none_is_refused(self):
        for declared in (
            "https://json-schema.org/draft/2020-12/schema",
            "http://json-schema.org/draft-04/schema#",
            None,
        ):
            schema = {"type": "object"}
            if declared:
                schema["$schema"] = declared
            with self.subTest(declared=declared):
                with self.assertRaises(ValueError):
                    json_schema.validator(schema)

    def test_no_other_code_builds_a_validator(self):
        code = tracked("backend/*.py", "scripts/*.py", "frontend/*.py")
        for path in code:
            rel = os.path.relpath(path, ROOT)
            if rel == THE_MODULE or rel.startswith("backend/tests/"):
                continue
            with open(path, encoding="utf-8") as f:
                found = OWN_VALIDATOR.findall(f.read())
            with self.subTest(module=rel):
                self.assertEqual(
                    found, [], f"{rel}: build validators with {THE_MODULE}"
                )

    def test_a_definition_keeps_its_neighbours_in_reach(self):
        with open(profile.SCHEMA_PATH, encoding="utf-8") as f:
            schema = json.load(f)
        name = next(iter(schema["definitions"]))
        checker = json_schema.validator(schema, name)
        self.assertIn("definitions", checker.schema)
        self.assertEqual(checker.schema["$schema"], json_schema.DRAFT)

    def test_contract_refs_resolve_between_files(self):
        # report-compact names common.schema.json: the registry resolves it
        # offline, so a wrong shape fails on the referenced definition.
        self.assertTrue(contract_schemas.errors("report-compact", {}))

    def test_first_error_is_none_for_valid_data(self):
        checker = json_schema.validator(
            {"$schema": json_schema.DRAFT, "type": "integer"}
        )
        self.assertIsNone(json_schema.first_error(checker, 3))
        self.assertIsNotNone(json_schema.first_error(checker, "3"))


class ContractCommandLine(unittest.TestCase):
    """python backend/report/contract_schemas.py <schema> <file|->"""

    def run_main(self, argv, stdin=""):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)):
            with contextlib.redirect_stdout(out):
                code = contract_schemas.main(argv)
        return code, out.getvalue()

    def test_a_valid_message_from_a_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "error.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"detail": "Not found"}, f)
            code, out = self.run_main(["x", "error", path])
        self.assertEqual((code, out.strip().splitlines()[-1]), (0, "valid"))

    def test_problems_from_stdin(self):
        code, out = self.run_main(["x", "error", "-"], stdin="{}")
        self.assertEqual(code, 1)
        self.assertIn("problem(s)", out)

    def test_wrong_arguments_print_the_usage(self):
        code, out = self.run_main(["x"])
        self.assertEqual(code, 2)
        self.assertIn("contract_schemas.py", out)


if __name__ == "__main__":
    unittest.main()
