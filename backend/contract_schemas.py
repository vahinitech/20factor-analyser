# SPDX-License-Identifier: AGPL-3.0-only
"""Validate API messages against the JSON Schema (draft-07) contract files.

The schemas in ``backend/schemas`` describe the version-2 HTTP contract.
Use this module from tests, from client repositories that vendor the same
files, or from the command line::

    python backend/contract_schemas.py report-compact response.json
    curl -s https://stage.vahinitech.com/api/v2/me \\
        | python backend/contract_schemas.py me -

Validation checks shape and access invariants; it never grants access.
"""

import json
import sys
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft7Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
NAMES = (
    "common",
    "me",
    "report-request",
    "report-expanded",
    "report-compact",
    "catalog",
    "error",
    "health",
)


def load(name):
    """Read one schema by short name, for example ``report-compact``."""
    if name not in NAMES:
        raise KeyError(f"Unknown schema {name!r}; choose from {NAMES}")
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text())


@lru_cache(maxsize=None)
def validator(name):
    """Build a draft-07 validator whose $ref links resolve offline."""
    resources = []
    for other in NAMES:
        schema = load(other)
        resources.append(
            (
                schema["$id"],
                Resource.from_contents(schema, default_specification=DRAFT7),
            )
        )
    schema = load(name)
    Draft7Validator.check_schema(schema)
    registry = Registry().with_resources(resources)
    return Draft7Validator(schema, registry=registry)


def errors(name, instance):
    """Return human-readable validation errors, empty when valid."""
    found = sorted(
        validator(name).iter_errors(instance), key=lambda e: list(e.path)
    )
    return [
        "/".join(str(part) for part in error.absolute_path)
        + ": "
        + error.message
        for error in found
    ]


def validate(name, instance):
    """Raise ``ValueError`` listing every problem, or return the instance."""
    problems = errors(name, instance)
    if problems:
        raise ValueError(
            f"{name} contract violated:\n  " + "\n  ".join(problems)
        )
    return instance


def main(argv):
    """Command-line entry: schema name and a JSON file path or ``-``."""
    if len(argv) != 3:
        print(__doc__)
        return 2
    _, name, source = argv
    text = sys.stdin.read() if source == "-" else Path(source).read_text()
    problems = errors(name, json.loads(text))
    for problem in problems:
        print(problem)
    print("valid" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
