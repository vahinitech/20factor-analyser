# SPDX-License-Identifier: AGPL-3.0-only
"""The one JSON Schema validator in the analyser.

Every schema here is JSON Schema draft-07: the version-2 API contracts in
``backend/schemas/`` and the pack, stage, ladder and profile schemas in
``backend/languages/``. Every caller builds its validator here, so a
schema written for another draft, or a caller reaching for another
draft's validator, fails instead of being checked by different rules
(backend/tests/test_json_schema.py holds both).
"""

from jsonschema import Draft7Validator
from jsonschema.exceptions import best_match
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

DRAFT = "http://json-schema.org/draft-07/schema#"


def check(schema):
    """Return schema when it declares draft-07 and is a valid draft-07
    schema; raise ValueError when it declares another draft or none."""
    declared = schema.get("$schema")
    if declared != DRAFT:
        name = schema.get("$id") or schema.get("title") or "a schema"
        raise ValueError(
            f"{name} declares $schema {declared!r}; every schema in the "
            f"analyser is draft-07 ({DRAFT})"
        )
    Draft7Validator.check_schema(schema)
    return schema


def registry(schemas):
    """An offline registry of schemas by their $id, so $ref links between
    files resolve without the network."""
    return Registry().with_resources(
        (s["$id"], Resource.from_contents(s, default_specification=DRAFT7))
        for s in schemas
    )


def validator(schema, definition=None, schemas=()):
    """A draft-07 validator for schema, or for one of its definitions
    (which keeps the others in reach of its $ref links). schemas are the
    other files its $ref links name."""
    check(schema)
    if definition is not None:
        defs = schema["definitions"]
        schema = {"$schema": DRAFT, **defs[definition], "definitions": defs}
    if schemas:
        return Draft7Validator(schema, registry=registry(schemas))
    return Draft7Validator(schema)


def first_error(checker, instance):
    """The most relevant error for instance, or None when it is valid."""
    return best_match(checker.iter_errors(instance))
