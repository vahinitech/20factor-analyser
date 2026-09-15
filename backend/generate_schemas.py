# SPDX-License-Identifier: AGPL-3.0-only
"""Generate the draft-07 JSON Schema files in backend/schemas.

The schemas are derived from the server's own constants (factor ids and
numbers, the Free factor list, the still-image limitations) so they cannot
drift from the code. ``python backend/generate_schemas.py`` rewrites the
files; ``--check`` exits non-zero when the committed files differ, and
``backend/tests/test_schemas.py`` runs that check in CI.
"""

import json
import sys
from pathlib import Path

from entitlements import FREE_FACTORS
from report_contract import FACTOR_IDS, SENSOR_LIMITATIONS

OUT = Path(__file__).resolve().parent / "schemas"
BASE = "https://vahinitech.com/schemas/analyser/v2/"
DRAFT = "http://json-schema.org/draft-07/schema#"
COMMON = "common.schema.json#/definitions/"
IDS = list(FACTOR_IDS)
FREE = sorted(FREE_FACTORS)
LOCKED = [n for n in range(1, 21) if n not in FREE_FACTORS]
SENSOR = sorted(SENSOR_LIMITATIONS)
NUMBER_KEY = "^([1-9]|1[0-9]|20)$"


def ref(name):
    return {"$ref": COMMON + name}


def nullable(kind, **extra):
    return {"type": [kind, "null"], **extra}


def closed(properties, required=None, **extra):
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(required if required is not None else properties),
        "properties": properties,
        **extra,
    }


def common():
    identity = [
        {"properties": {"number": {"const": n}, "id": {"const": IDS[n - 1]}}}
        for n in range(1, 21)
    ]
    access = closed(
        {
            "customer_id": nullable(
                "string",
                minLength=1,
                description=(
                    "Opaque ledger identity; the provisioner issues "
                    "cus_ plus 24 hex characters."
                ),
            ),
            "authenticated": {"type": "boolean"},
            "tier": ref("tier"),
            "plan_tier": ref("tier"),
            "subscription_status": ref("subscriptionStatus"),
            "expires_at": ref("unixSeconds"),
            "capabilities": ref("capabilities"),
        }
    )
    access["allOf"] = [
        {
            "if": {"properties": {"authenticated": {"const": False}}},
            "then": {
                "properties": {
                    "customer_id": {"type": "null"},
                    "tier": {"const": "free"},
                    "subscription_status": {"const": "anonymous"},
                }
            },
        },
        {
            "if": {"properties": {"authenticated": {"const": True}}},
            "then": {
                "properties": {
                    "customer_id": {"type": "string"},
                    "subscription_status": {"not": {"const": "anonymous"}},
                }
            },
        },
        {
            "if": {"properties": {"tier": {"const": "pro"}}},
            "then": {
                "properties": {
                    "expires_at": {"type": "integer"},
                    "plan_tier": {"const": "pro"},
                    "capabilities": {
                        "properties": {
                            "factor_numbers": {"minItems": 20},
                            "detailed_evidence": {"const": True},
                            "coaching": {"const": True},
                            "personalised_worksheets": {"const": True},
                        }
                    },
                }
            },
            "else": {
                "properties": {
                    "capabilities": {
                        "properties": {
                            "factor_numbers": ref("freeFactorNumbers"),
                            "detailed_evidence": {"const": False},
                            "coaching": {"const": False},
                            "personalised_worksheets": {"const": False},
                        }
                    }
                }
            },
        },
    ]
    recognition = {
        "type": "object",
        "properties": {
            "backend": nullable("string"),
            "ocr_error": nullable("string"),
            "hand_lines": nullable("integer", minimum=0),
            "printed_lines": nullable("integer", minimum=0),
            "reliable_lines": nullable("integer", minimum=0),
            "mean_confidence": nullable("number", minimum=0, maximum=1),
            "confidence_pct": nullable("integer", minimum=0, maximum=100),
            "refined_by": {
                "type": "object",
                "additionalProperties": {"type": "integer", "minimum": 0},
            },
            "refined_lines": {"type": "integer", "minimum": 0},
            "level": {
                "type": ["string", "null"],
                "enum": [
                    "passage-verified",
                    "high",
                    "moderate",
                    "low",
                    "unavailable",
                    None,
                ],
            },
            "assistive_only": nullable("boolean"),
            "passage_aligned": nullable("boolean"),
            "passage_match": {},
            "note": {"type": "string"},
        },
    }
    return {
        "title": "Shared definitions for the Vahini report API, version 2",
        "description": (
            "Referenced by the endpoint schemas with $ref. Generated by "
            "backend/generate_schemas.py from report_contract.FACTOR_IDS, "
            "entitlements.FREE_FACTORS and report_contract."
            "SENSOR_LIMITATIONS; do not edit by hand."
        ),
        "definitions": {
            "factorNumber": {"type": "integer", "minimum": 1, "maximum": 20},
            "factorId": {"type": "string", "enum": IDS},
            "factorIdentity": {
                "description": "number and id must name the same factor.",
                "oneOf": identity,
            },
            "freeFactorNumbers": {
                "type": "array",
                "items": {"type": "integer", "enum": FREE},
                "minItems": len(FREE),
                "maxItems": len(FREE),
                "uniqueItems": True,
            },
            "lockedFactorNumber": {"type": "integer", "enum": LOCKED},
            "tier": {"type": "string", "enum": ["free", "pro"]},
            "subscriptionStatus": {
                "type": "string",
                "enum": [
                    "anonymous",
                    "active",
                    "cancelled",
                    "expired",
                    "revoked",
                ],
            },
            "unixSeconds": nullable("integer", minimum=0),
            "sectionId": {
                "type": "string",
                "enum": ["structure", "spatial", "dynamics", "style"],
            },
            "band": {
                "type": "string",
                "enum": ["strong", "good", "dev", "focus"],
            },
            "status": {
                "type": "string",
                "enum": ["estimated", "proxy", "measured", "unavailable"],
            },
            "statusCode": {"type": "string", "enum": ["e", "p", "m", "u"]},
            "scoreOutOfTen": nullable(
                "number",
                minimum=0,
                maximum=10,
                description="Original score. null means no score, never 0.",
            ),
            "scoreOutOfHundred": nullable("number", minimum=0, maximum=100),
            "catalogVersion": {
                "type": "string",
                "pattern": "^[0-9a-f]{20}$",
                "description": (
                    "First 20 hex characters of the SHA-256 of the "
                    "catalogue body without its version field."
                ),
            },
            "capabilities": closed(
                {
                    "factor_numbers": {
                        "type": "array",
                        "items": ref("factorNumber"),
                        "uniqueItems": True,
                        "minItems": len(FREE),
                        "maxItems": 20,
                    },
                    "detailed_evidence": {"type": "boolean"},
                    "coaching": {"type": "boolean"},
                    "personalised_worksheets": {"type": "boolean"},
                }
            ),
            "access": access,
            "coachingCard": {
                "type": "object",
                "required": ["id", "kind", "pillar", "title", "text", "why"],
                "properties": {
                    "id": {"type": "string"},
                    "kind": {"type": "string", "enum": ["coach", "fun"]},
                    "pillar": {"type": "string"},
                    "title": {"type": "string"},
                    "text": {"type": "string"},
                    "why": {"type": "string"},
                    "examples": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
            "factorRegions": {
                "type": "object",
                "description": (
                    "Keyed by factor number as a string. "
                    "Present only with Pro evidence."
                ),
                "propertyNames": {"pattern": NUMBER_KEY},
                "additionalProperties": {
                    "type": "object",
                    "required": ["url", "caption"],
                    "properties": {
                        "url": {
                            "type": "string",
                            "pattern": "^data:image/(jpeg|png|webp);base64,",
                        },
                        "caption": {"type": "string"},
                    },
                },
            },
            "recognitionMetadata": recognition,
            "limitations": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": 1,
            },
        },
    }


def me():
    return closed(
        {"schema_version": {"const": "2.0"}, "access": ref("access")},
        title="GET /api/v2/me response",
    )


def expanded():
    score = closed(
        {
            "value": ref("scoreOutOfTen"),
            "minimum": {"const": 0},
            "maximum": {"const": 10},
            "normalized": nullable("integer", minimum=0, maximum=100),
            "normalized_maximum": {"const": 100},
            "higher_is_better": {"const": True},
            "band": {"anyOf": [ref("band"), {"type": "null"}]},
        }
    )
    score["if"] = {"properties": {"value": {"type": "null"}}}
    score["then"] = {
        "properties": {
            "normalized": {"type": "null"},
            "band": {"type": "null"},
        }
    }
    score["else"] = {
        "properties": {
            "normalized": {"type": "integer"},
            "band": {"type": "string"},
        }
    }
    factor = closed(
        {
            "id": ref("factorId"),
            "number": ref("factorNumber"),
            "name": nullable("string"),
            "section_id": {"anyOf": [ref("sectionId"), {"type": "null"}]},
            "status": ref("status"),
            "score": score,
            "reason": closed(
                {
                    "summary": nullable("string"),
                    "basis": nullable("string"),
                    "scoring_inputs": {"type": "object"},
                    "unavailable_reason": nullable("string"),
                },
                required=["summary"],
            ),
            "measurement": closed(
                {
                    "method": {
                        "type": "string",
                        "enum": ["image_heuristic", "sensor"],
                    },
                    "source_label": nullable("string"),
                    "confidence_probability": {
                        "type": "null",
                        "description": (
                            "Always null: the model produces no "
                            "calibrated probability."
                        ),
                    },
                    "display_value": {"type": ["string", "number", "null"]},
                    "limitations": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                required=["method", "confidence_probability", "limitations"],
            ),
            "practice": closed(
                {
                    "target_description": nullable("string"),
                    "instruction": nullable("string"),
                    "exercise_group": nullable("string"),
                }
            ),
        },
        required=[
            "id",
            "number",
            "name",
            "section_id",
            "status",
            "score",
            "reason",
            "measurement",
        ],
    )
    factor["allOf"] = [
        ref("factorIdentity"),
        {
            "if": {"properties": {"status": {"const": "unavailable"}}},
            "then": {
                "properties": {
                    "score": {"properties": {"value": {"type": "null"}}}
                }
            },
            "else": {
                "properties": {
                    "score": {"properties": {"value": {"type": "number"}}}
                }
            },
        },
        {
            "if": {"properties": {"status": {"const": "measured"}}},
            "then": {
                "properties": {
                    "measurement": {
                        "properties": {"method": {"const": "sensor"}}
                    }
                }
            },
        },
        {
            "description": (
                "Factors 2, 13, 14 and 16 cannot be 'estimated' from a "
                "still image; they are proxy, measured or unavailable."
            ),
            "if": {
                "properties": {
                    "number": {"enum": SENSOR},
                    "status": {"const": "estimated"},
                },
                "required": ["number", "status"],
            },
            "then": False,
        },
    ]
    free_factor = {
        "properties": {
            "number": {"enum": FREE},
            "practice": False,
            "reason": {
                "properties": {"summary": {}},
                "additionalProperties": False,
                "required": ["summary"],
            },
            "measurement": {
                "properties": {"display_value": False, "source_label": False}
            },
        }
    }
    pro_factor = {
        "required": ["practice"],
        "properties": {
            "reason": {
                "required": [
                    "summary",
                    "basis",
                    "scoring_inputs",
                    "unavailable_reason",
                ]
            },
            "measurement": {
                "required": [
                    "method",
                    "source_label",
                    "confidence_probability",
                    "display_value",
                    "limitations",
                ]
            },
        },
    }
    locked = closed(
        {
            "number": ref("factorNumber"),
            "id": ref("factorId"),
            "required_tier": {"const": "pro"},
        },
        allOf=[ref("factorIdentity")],
    )
    schema = closed(
        {
            "schema_version": {"const": "2.0"},
            "scoring_version": {"const": "legacy-python-20factor"},
            "ok": {"type": "boolean"},
            "summary": closed(
                {
                    "score": ref("scoreOutOfHundred"),
                    "maximum": {"const": 100},
                    "expected_factor_count": {"const": 20},
                    "returned_factor_count": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 20,
                    },
                    "scored_factor_count": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 20,
                    },
                    "proxy_factor_count": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 20,
                    },
                    "score_basis": {"type": "string"},
                }
            ),
            "factors": {
                "type": "array",
                "items": factor,
                "maxItems": 20,
                "description": (
                    "Sorted by number; one entry per allowed factor."
                ),
            },
            "locked_factors": {
                "type": "array",
                "maxItems": len(LOCKED),
                "uniqueItems": True,
                "items": locked,
            },
            "recognition": {
                "type": "object",
                "required": ["text"],
                "properties": {
                    "text": {"type": "string"},
                    "metadata": ref("recognitionMetadata"),
                },
            },
            "limitations": ref("limitations"),
            "access": ref("access"),
            "coaching": {"type": "array", "items": ref("coachingCard")},
            "evidence": {
                "type": "object",
                "required": ["image_width", "image_height", "factor_regions"],
                "properties": {
                    "image_width": nullable("integer", minimum=1),
                    "image_height": nullable("integer", minimum=1),
                    "factor_regions": ref("factorRegions"),
                },
            },
            "worksheets": {
                "type": "array",
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "required": ["id", "title", "pdf_path", "factor_number"],
                    "properties": {
                        "id": {"type": "string", "pattern": "^[a-z0-9-]+$"},
                        "title": {"type": "string"},
                        "pdf_path": {
                            "type": "string",
                            "pattern": "^/assets/worksheets/[a-z0-9-]+\\.pdf$",
                        },
                        "factor_number": ref("factorNumber"),
                    },
                },
            },
            "error": closed(
                {
                    "code": {"type": "string", "minLength": 1},
                    "message": {"type": "string"},
                }
            ),
        },
        required=[
            "schema_version",
            "scoring_version",
            "ok",
            "summary",
            "factors",
            "recognition",
            "limitations",
            "access",
            "locked_factors",
        ],
        title="POST /api/v2/reports response, expanded format (schema 2.0)",
        description=(
            "Default format. The server projects fields from an allowlist "
            "per access tier; Free bodies never contain practice, evidence, "
            "coaching or worksheets."
        ),
    )
    schema["allOf"] = [
        {
            "if": {"properties": {"ok": {"const": False}}},
            "then": {"required": ["error"]},
            "else": {"properties": {"error": False}},
        },
        {
            "if": {
                "properties": {
                    "access": {"properties": {"tier": {"const": "free"}}}
                }
            },
            "then": {
                "properties": {
                    "coaching": False,
                    "evidence": False,
                    "worksheets": False,
                    "factors": {"maxItems": len(FREE), "items": free_factor},
                    "locked_factors": {
                        "minItems": len(LOCKED),
                        "items": {
                            "properties": {"number": ref("lockedFactorNumber")}
                        },
                    },
                    "recognition": {
                        "properties": {"text": {}},
                        "additionalProperties": False,
                    },
                }
            },
            "else": {
                "required": ["coaching", "evidence", "worksheets"],
                "properties": {
                    "factors": {"items": pro_factor},
                    "locked_factors": {"maxItems": 0},
                    "recognition": {"required": ["text", "metadata"]},
                },
            },
        },
    ]
    return schema


def compact():
    recognition_keys = [
        "backend",
        "level",
        "confidence_pct",
        "mean_confidence",
        "hand_lines",
        "printed_lines",
        "reliable_lines",
        "assistive_only",
        "passage_aligned",
    ]
    factor = closed(
        {
            "n": ref("factorNumber"),
            "s": ref("scoreOutOfTen"),
            "st": ref("statusCode"),
        }
    )
    factor["allOf"] = [
        {
            "if": {"properties": {"st": {"const": "u"}}},
            "then": {"properties": {"s": {"type": "null"}}},
            "else": {"properties": {"s": {"type": "number"}}},
        },
        {
            "if": {"properties": {"n": {"enum": SENSOR}}},
            "then": {"properties": {"st": {"enum": ["p", "m", "u"]}}},
            "else": {"properties": {"st": {"enum": ["e", "m", "u"]}}},
        },
    ]
    schema = closed(
        {
            "schema_version": {"const": "2.1"},
            "format": {"const": "compact"},
            "catalog_version": ref("catalogVersion"),
            "ok": {"type": "boolean"},
            "access": closed(
                {
                    "tier": ref("tier"),
                    "plan_tier": ref("tier"),
                    "subscription_status": ref("subscriptionStatus"),
                    "expires_at": ref("unixSeconds"),
                }
            ),
            "summary": closed(
                {
                    "score": ref("scoreOutOfHundred"),
                    "factor_count": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 20,
                    },
                }
            ),
            "factors": {"type": "array", "maxItems": 20, "items": factor},
            "locked": {
                "type": "array",
                "items": ref("factorNumber"),
                "uniqueItems": True,
                "maxItems": len(LOCKED),
            },
            "text": {"type": "string"},
            "counts": closed({"lines": {"type": "integer", "minimum": 0}}),
            "recognition": closed(
                {
                    key: {
                        "$ref": COMMON
                        + "recognitionMetadata/properties/"
                        + key
                    }
                    for key in recognition_keys
                }
            ),
            "inputs": {
                "type": "object",
                "propertyNames": {"pattern": NUMBER_KEY},
                "additionalProperties": closed(
                    {
                        "evidence": nullable("string"),
                        "basis": nullable("string"),
                        "values": nullable("object"),
                    }
                ),
            },
            "coaching": {"type": "array", "items": ref("coachingCard")},
            "evidence": closed(
                {
                    "width": nullable("integer", minimum=1),
                    "height": nullable("integer", minimum=1),
                    "factor_regions": ref("factorRegions"),
                }
            ),
            "error": closed({"code": {"type": "string", "minLength": 1}}),
        },
        required=[
            "schema_version",
            "format",
            "catalog_version",
            "ok",
            "access",
            "summary",
            "factors",
            "locked",
        ],
        title="POST /api/v2/reports?format=compact response (schema 2.1)",
        description=(
            "Scores only; names, explanations and bands come from "
            "GET /api/v2/catalog/{catalog_version}. Optional blocks appear "
            "only when requested with include= and allowed by the tier."
        ),
    )
    schema["dependencies"] = {
        "counts": ["text"],
        "recognition": ["text"],
        "text": ["counts", "recognition"],
    }
    schema["allOf"] = [
        {
            "if": {"properties": {"ok": {"const": False}}},
            "then": {"required": ["error"]},
            "else": {"properties": {"error": False}},
        },
        {
            "if": {
                "properties": {
                    "access": {"properties": {"tier": {"const": "free"}}}
                }
            },
            "then": {
                "properties": {
                    "inputs": False,
                    "coaching": False,
                    "evidence": False,
                    "factors": {
                        "maxItems": len(FREE),
                        "items": {"properties": {"n": {"enum": FREE}}},
                    },
                    "locked": {
                        "minItems": len(LOCKED),
                        "items": ref("lockedFactorNumber"),
                    },
                }
            },
            "else": {"properties": {"locked": {"maxItems": 0}}},
        },
    ]
    return schema


def catalog():
    entry = closed(
        {
            "n": ref("factorNumber"),
            "id": ref("factorId"),
            "name": {"type": "string", "minLength": 1},
            "section": ref("sectionId"),
            "reason": {"type": "string"},
            "exercise": {"type": "string"},
            "target": {"type": "string"},
            "instruction": {"type": "string"},
            "limitation": nullable("string"),
        }
    )
    entry["allOf"] = [
        {
            "if": {"properties": {"n": {"const": n}}},
            "then": {"properties": {"id": {"const": IDS[n - 1]}}},
        }
        for n in range(1, 21)
    ]
    return closed(
        {
            "schema_version": {"const": "2.1"},
            "language": {
                "type": "string",
                "pattern": "^[a-z]{2}(-[A-Za-z0-9]+)*$",
            },
            "score_scale": {"const": [0, 10]},
            "normalized_scale": {"const": [0, 100]},
            "statuses": closed(
                {
                    "e": {"const": "estimated"},
                    "p": {"const": "proxy"},
                    "m": {"const": "measured"},
                    "u": {"const": "unavailable"},
                }
            ),
            "bands": {
                "type": "array",
                "minItems": 4,
                "maxItems": 4,
                "items": closed(
                    {
                        "id": ref("band"),
                        "minimum": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 10,
                        },
                    }
                ),
            },
            "factors": {
                "type": "array",
                "minItems": 20,
                "maxItems": 20,
                "uniqueItems": True,
                "items": entry,
                "description": "Exactly one entry for each factor 1 to 20.",
                "allOf": [
                    {"contains": {"properties": {"n": {"const": n}}}}
                    for n in range(1, 21)
                ],
            },
            "sections": {
                "type": "array",
                "minItems": 4,
                "maxItems": 4,
                "items": closed(
                    {
                        "id": ref("sectionId"),
                        "name": {"type": "string"},
                        "weight": {
                            "type": "number",
                            "exclusiveMinimum": 0,
                            "maximum": 1,
                        },
                    }
                ),
            },
            "limitations": ref("limitations"),
            "version": ref("catalogVersion"),
        },
        title="GET /api/v2/catalog/{version} response (schema 2.1)",
        description=(
            "Public, immutable presentation dictionary. Contains no scores "
            "or customer data. Clients cache it by version and must fetch "
            "an unknown version before rendering."
        ),
    )


def error():
    return closed(
        {
            "detail": {
                "oneOf": [
                    {"type": "string", "minLength": 1},
                    {
                        "type": "array",
                        "minItems": 1,
                        "description": "FastAPI request validation errors.",
                        "items": {
                            "type": "object",
                            "required": ["loc", "msg", "type"],
                            "properties": {
                                "loc": {
                                    "type": "array",
                                    "items": {"type": ["string", "integer"]},
                                },
                                "msg": {"type": "string"},
                                "type": {"type": "string"},
                                "input": {},
                                "ctx": {"type": "object"},
                            },
                        },
                    },
                ]
            }
        },
        title="HTTP error body for /api/v2/* (401, 403, 404, 413, 422, 503)",
        description=(
            "FastAPI's HTTPException shape. 401 invalid or revoked "
            "credential, 403 paid include= fields requested by Free, 404 "
            "unknown catalogue version, 413 upload too large, 422 "
            "unsupported include field or invalid form/query, 503 "
            "subscription service not configured or unavailable. Analysis "
            "failures are not HTTP errors: they return 200 with ok:false "
            "and an error block in the report schema."
        ),
    )


def request():
    opt = "text|inputs|coaching|evidence"
    image = closed(
        {
            "filename": {"type": "string"},
            "content_type": {
                "type": "string",
                "enum": [
                    "image/jpeg",
                    "image/png",
                    "image/webp",
                    "application/pdf",
                ],
            },
            "size_bytes": {
                "type": "integer",
                "minimum": 1,
                "maximum": 30 * 1024 * 1024,
                "description": (
                    "30 MiB per upload; the whole request body must stay "
                    "under 32 MiB."
                ),
            },
            "width": {"type": "integer", "minimum": 1, "maximum": 24000000},
            "height": {"type": "integer", "minimum": 1, "maximum": 24000000},
            "pdf_pages": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "description": "Only the first page is analysed.",
            },
        },
        required=["content_type", "size_bytes"],
        description=(
            "Metadata of the uploaded file, not its bytes. width x height "
            "must not exceed 24,000,000 pixels; check that product in "
            "code, JSON Schema cannot multiply."
        ),
    )
    image["if"] = {
        "properties": {"content_type": {"const": "application/pdf"}}
    }
    image["then"] = {"required": ["pdf_pages"]}
    return closed(
        {
            "headers": {
                "type": "object",
                "description": (
                    "HTTP header names are case-insensitive; either "
                    "spelling of Authorization is accepted."
                ),
                "additionalProperties": False,
                "maxProperties": 1,
                "patternProperties": {
                    "^[Aa]uthorization$": {
                        "type": "string",
                        "pattern": "^Bearer vh_[A-Za-z0-9_-]{16,}$",
                        "maxLength": 200,
                        "description": (
                            "Operator-issued customer key. Absent means "
                            "anonymous Free."
                        ),
                    }
                },
            },
            "query": closed(
                {
                    "format": {
                        "type": "string",
                        "enum": ["expanded", "compact"],
                        "default": "expanded",
                    },
                    "include": {
                        "type": "string",
                        "pattern": f"^((({opt})(,({opt}))*)?)$",
                        "default": "",
                        "description": (
                            "Comma-separated. inputs, coaching and evidence "
                            "need Pro; the server answers 403 before "
                            "inference otherwise."
                        ),
                    },
                },
                required=[],
            ),
            "form": closed(
                {
                    "lang": {
                        "type": "string",
                        "default": "auto",
                        "pattern": "^([a-z]{2,8}|auto)$",
                    },
                    "expected_text": {
                        "type": "string",
                        "default": "",
                        "maxLength": 20000,
                        "description": (
                            "Optional copied reference passage for "
                            "passage-verified recognition."
                        ),
                    },
                },
                required=[],
            ),
            "image": image,
        },
        required=["form", "image"],
        title="POST /api/v2/reports request",
        description=(
            "Model of one multipart request as an object, for clients that "
            "validate what they are about to send and for contract tests. "
            "The wire format is multipart/form-data; let the HTTP library "
            "set the boundary. Never put the credential in the query string."
        ),
    )


def health():
    return {
        "title": "GET /health response",
        "type": "object",
        "required": [
            "ok",
            "engine",
            "ocr_backend",
            "active_backend",
            "backends",
            "gpu",
            "gpu_detected",
            "langs",
            "ocr_version",
        ],
        "properties": {
            "ok": {"const": True},
            "engine": {"type": "string"},
            "ocr_backend": {"type": "string"},
            "active_backend": {"type": "string"},
            "backends": {
                "type": "object",
                "additionalProperties": closed(
                    {
                        "ready": {"type": "boolean"},
                        "reason": nullable("string"),
                    }
                ),
            },
            "gpu": {"type": "boolean"},
            "gpu_detected": {"type": "boolean"},
            "gpu_note": nullable("string"),
            "langs": {
                "type": ["array", "string"],
                "items": {"type": "string"},
            },
            "variants": {"type": "integer", "minimum": 0},
            "ocr_version": nullable(
                "string",
                description=(
                    "null when VAHINI_OCR_VERSION is set to an empty value."
                ),
            ),
            "det_model": nullable("string"),
            "rec_model_map": {"type": ["object", "string", "null"]},
            "det_limit_side_len": nullable("integer"),
            "printed_threshold": {"type": "number"},
            "adaptive_engine_speed": {"type": "object"},
            "layout_filter": closed(
                {
                    "enabled": {"type": "boolean"},
                    "built_tiers": {"type": "array"},
                }
            ),
        },
    }


BUILDERS = {
    "common": common,
    "me": me,
    "report-request": request,
    "report-expanded": expanded,
    "report-compact": compact,
    "catalog": catalog,
    "error": error,
    "health": health,
}


def render(name):
    """The exact file content for one schema, newline terminated."""
    body = {"$schema": DRAFT, "$id": BASE + name + ".schema.json"}
    body.update(BUILDERS[name]())
    return json.dumps(body, indent=2, ensure_ascii=False) + "\n"


def stale():
    """Names whose committed file differs from the generated content."""
    return [
        name
        for name in BUILDERS
        if not (OUT / f"{name}.schema.json").exists()
        or (OUT / f"{name}.schema.json").read_text() != render(name)
    ]


def main(argv):
    if "--check" in argv:
        names = stale()
        if names:
            print("Stale schema files: " + ", ".join(names))
            print("Run python backend/generate_schemas.py")
            return 1
        print("Schemas match the generator.")
        return 0
    OUT.mkdir(exist_ok=True)
    for name in BUILDERS:
        (OUT / f"{name}.schema.json").write_text(render(name))
    print(f"Wrote {len(BUILDERS)} schema files to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
