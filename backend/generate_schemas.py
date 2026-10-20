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

from entitlements import FREE_FACTORS, STATUSES, TIERS
from practice_catalog import AVOID_WORDS, MODELS, STEPS_MAX, UNITS
from report_contract import FACTOR_IDS, SENSOR_LIMITATIONS

OUT = Path(__file__).resolve().parent / "schemas"
BASE = "https://vahinitech.com/schemas/analyser/v2/"
DRAFT = "http://json-schema.org/draft-07/schema#"
COMMON = "common.schema.json#/definitions/"
ACCESS = "access-customer.schema.json#/definitions/"
IDS = list(FACTOR_IDS)
FREE = sorted(FREE_FACTORS)
LOCKED = [n for n in range(1, 21) if n not in FREE_FACTORS]
SENSOR = sorted(SENSOR_LIMITATIONS)
NUMBER_KEY = "^([1-9]|1[0-9]|20)$"


def ref(name):
    return {"$ref": COMMON + name}


def nullable(kind, **extra):
    return {"type": [kind, "null"], **extra}


# The request's `lang`: auto, or BCP 47 tags separated by commas. A tag is
# a language subtag, then an optional script (Latn, Telu) and an optional
# region (IN, GB): en, te-Telu-IN, en-Latn-GB,te. The language subtag
# takes 2 to 8 letters, as the old pattern `^([a-z]{2,8}|auto)$` did and
# BCP 47 allows, so a PaddleOCR language name a server loads (latin,
# korean) stays valid. lang_tags.py maps each tag to its engine code.
_LANG_TAG = "[a-z]{2,8}(-[A-Z][a-z]{3})?(-[A-Z]{2})?"
LANG_PATTERN = f"^(auto|{_LANG_TAG}(,{_LANG_TAG})*)$"


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
                    "Keyed by factor number as a string. Present only when "
                    "evidence is requested: all twenty factors for Pro, the "
                    "five Free factors otherwise. Sensor-only factors carry status "
                    "'unavailable' with an empty url."
                ),
                "propertyNames": {"pattern": NUMBER_KEY},
                "additionalProperties": {
                    "type": "object",
                    "required": ["url", "caption"],
                    "properties": {
                        "url": {
                            "type": "string",
                            "pattern": "^(data:image/(jpeg|png|webp);base64,|$)",
                        },
                        "caption": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["measurement", "context", "unavailable"],
                        },
                        "bbox": {
                            "type": ["array", "null"],
                            "items": {"type": "number"},
                            "minItems": 4,
                            "maxItems": 4,
                        },
                        "source_size": {
                            "type": ["array", "null"],
                            "items": {"type": "integer", "minimum": 1},
                            "minItems": 2,
                            "maxItems": 2,
                        },
                        "coordinate_space": {
                            "type": "string",
                            "enum": ["processed-image"],
                        },
                        "region_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "selection_method": {"type": "string"},
                        "places": {
                            "type": "array",
                            "description": (
                                "Free skills 1, 5, 7, 8 and 18: up to three "
                                "measurements that stand apart from the "
                                "page ('look') and at most one closest to "
                                "it ('keep'), each with its box. Ranked by "
                                "deviation, which is not a probability. "
                                "backend/marked_places.py."
                            ),
                            "maxItems": 4,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "bbox",
                                    "kind",
                                    "role",
                                    "region_id",
                                    "measure",
                                    "value",
                                    "reference",
                                    "deviation",
                                    "direction",
                                    "line_confidence",
                                ],
                                "properties": {
                                    "bbox": {
                                        "type": "array",
                                        "items": {"type": "integer"},
                                        "minItems": 4,
                                        "maxItems": 4,
                                    },
                                    "kind": {"enum": ["line", "word", "gap"]},
                                    "role": {"enum": ["look", "keep"]},
                                    "region_id": {"type": "string"},
                                    "measure": {
                                        "enum": [
                                            "line_height",
                                            "word_xheight",
                                            "line_angle",
                                            "read_confidence",
                                            "word_gap",
                                        ]
                                    },
                                    "value": {"type": "number"},
                                    "reference": {"type": "number"},
                                    "deviation": {
                                        "type": "number",
                                        "minimum": 0,
                                    },
                                    "direction": {
                                        "enum": [
                                            "taller",
                                            "shorter",
                                            "even",
                                            "tilted",
                                            "level",
                                            "unclear",
                                            "clear",
                                            "wider",
                                            "narrower",
                                        ]
                                    },
                                    "line_confidence": {
                                        "type": "number",
                                        "minimum": 0,
                                        "maximum": 1,
                                    },
                                    "from_factor": {"enum": [1, 5, 7, 8]},
                                },
                            },
                        },
                        "location_url": {
                            "type": "string",
                            "pattern": "^(data:image/(jpeg|png|webp);base64,|$)",
                        },
                        "marks": {
                            "type": "array",
                            "description": (
                                "Where this factor was measured, in the "
                                "uploaded photo's pixels (evidence "
                                "photo_width x photo_height; scale by "
                                "your copy's width / photo_width). "
                                "Boxes are [x, y, w, h], lines two "
                                "[x, y] points. Roles: region (the "
                                "evidence crop), look and keep (places), "
                                "baseline and midline (a fitted line), "
                                "usual_start (the usual left edge), "
                                "hardest_line, underline and letter (the "
                                "line and letters the reader was least "
                                "sure of). Absent when the photo's size "
                                "is unknown. backend/comparison_data.py."
                            ),
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["shape", "role"],
                                "properties": {
                                    "shape": {"enum": ["box", "line"]},
                                    "role": {
                                        "enum": [
                                            "region",
                                            "look",
                                            "keep",
                                            "baseline",
                                            "midline",
                                            "usual_start",
                                            "hardest_line",
                                            "underline",
                                            "letter",
                                        ]
                                    },
                                    "measure": {"type": "string"},
                                    "box": {
                                        "type": "array",
                                        "items": {"type": "number"},
                                        "minItems": 4,
                                        "maxItems": 4,
                                    },
                                    "points": {
                                        "type": "array",
                                        "minItems": 2,
                                        "maxItems": 2,
                                        "items": {
                                            "type": "array",
                                            "items": {"type": "number"},
                                            "minItems": 2,
                                            "maxItems": 2,
                                        },
                                    },
                                },
                                "allOf": [
                                    {
                                        "if": {
                                            "properties": {
                                                "shape": {"const": "box"}
                                            }
                                        },
                                        "then": {"required": ["box"]},
                                        "else": {"required": ["points"]},
                                    }
                                ],
                            },
                        },
                    },
                    "if": {"properties": {"url": {"const": ""}}},
                    "then": {
                        "properties": {"status": {"const": "unavailable"}},
                        "required": ["status"],
                    },
                },
            },
            "sectionScore": closed(
                {
                    "id": ref("sectionId"),
                    "name": {"type": "string"},
                    "score": ref("scoreOutOfTen"),
                    "normalized": nullable("integer", minimum=0, maximum=100),
                    "weight": {"type": "number", "minimum": 0, "maximum": 1},
                    "factor_count": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 20,
                    },
                    "scored_factor_count": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 20,
                    },
                },
                description=(
                    "One of the four sections as the engine scored it "
                    "(scoring.build_analysis): the mean of its measured "
                    "factors, 0-10 with one decimal, null when none was "
                    "measured. weight is what the overall score used "
                    "(0 for a section with no score). Pro only, since the "
                    "mean includes factors Free cannot see."
                ),
            ),
            "comparability": closed(
                {
                    "lines": {"type": "integer", "minimum": 0},
                    "words": nullable("integer", minimum=0),
                    "characters": nullable("integer", minimum=0),
                    "script": {
                        "type": ["string", "null"],
                        "enum": [
                            "latin",
                            "telugu",
                            "devanagari",
                            "mixed",
                            "other",
                            None,
                        ],
                    },
                    "languages": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "uniqueItems": True,
                    },
                    "printed_lines": {"type": "integer", "minimum": 0},
                    "page": {
                        "type": "string",
                        "enum": ["handwriting", "handwriting_with_print"],
                    },
                    "reading": {
                        "$ref": COMMON + "recognitionMetadata/properties/level"
                    },
                    "passage_aligned": {"type": "boolean"},
                },
                description=(
                    "Facts that say whether two pages can be compared: "
                    "handwriting lines scored, words and non-space "
                    "characters read (null when nothing was read), the "
                    "script of the letters read, the reading engine "
                    "languages, printed lines found and left out, the "
                    "reading level and whether a copied passage was "
                    "matched. Counts only: no text or identifier. Every "
                    "tier, successful reports only."
                ),
            ),
            "recognitionMetadata": recognition,
            "limitations": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": 1,
            },
        },
    }


def practice_limits():
    count = {"type": "integer", "minimum": 0, "maximum": 20}
    return closed(
        {"areas_max": count, "exercises_max": count, "tips_max": count},
        description=(
            "How many skills get practice in one report, and how many "
            "exercises and tips each shows, for the caller's tier "
            "(practice_catalog.TIERS)."
        ),
    )


def me():
    return closed(
        {
            "schema_version": {"const": "2.0"},
            "access": ref("access"),
            "practice": practice_limits(),
        },
        title="GET /api/v2/me response",
    )


def translations(fields, optional=()):
    """Per-language text of one exercise or tip: ``i18n.<lang>``."""
    text = {"type": "string", "minLength": 1}
    entry = closed(
        {
            **{field: text for field in fields},
            **{field: {"type": "string"} for field in optional},
        },
        required=fields,
    )
    return {
        "type": "object",
        "additionalProperties": False,
        "patternProperties": {"^[a-z]{2}$": entry},
        "description": (
            "Translations by language code. A missing language or field "
            "falls back to the English text. Latin practice text stays "
            "as written, so 'example' is translated only when it is not "
            "Latin practice."
        ),
    }


def helps_map():
    """``helps``: which skills an exercise or tip develops, by factor
    number, its own at 1.0 (docs/10-practice-framework.md, "Many-to-many
    selection")."""
    return {
        "type": "object",
        "additionalProperties": False,
        "patternProperties": {
            "^([1-9]|1[0-9]|20)$": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            }
        },
        "description": (
            "How much this entry develops each skill, 0 to 1, by factor "
            "number. Its own factor is 1.0 and every other weight is "
            "lower. Empty for the spelling row. Catalogues before "
            "version 2026-10-11 carry no helps."
        ),
    }


def practice_entries():
    """Exercise and tip lists, as the catalogue serves them."""
    text = {"type": "string", "minLength": 1}
    exercise = closed(
        {
            "id": {"type": "string", "pattern": "^[a-z]+\\.[a-z0-9-]+$"},
            "level": {"type": "integer", "minimum": 1},
            "title": text,
            "unit": {"type": "string", "enum": list(UNITS)},
            "script": {"type": "string", "enum": ["any", "latin"]},
            "needs": {"type": "string", "enum": ["photo", "pen"]},
            "worksheet": nullable("string", pattern="^[a-z0-9-]+$"),
            "steps": {
                "type": "string",
                "minLength": 1,
                "maxLength": STEPS_MAX,
            },
            "example": {"type": "string"},
            "check": text,
            "model": {
                "type": "string",
                "enum": list(MODELS),
                "description": (
                    "The drawing the report shows under 'Copy this'."
                ),
            },
            "helps": helps_map(),
            "i18n": translations(("title", "steps", "check"), ("example",)),
        },
        required=(
            "id",
            "level",
            "title",
            "unit",
            "script",
            "needs",
            "worksheet",
            "steps",
            "example",
            "check",
        ),
    )
    tip = closed(
        {
            "id": {"type": "string", "pattern": "^[a-z]+\\.[a-z0-9-]+$"},
            "text": text,
            "helps": helps_map(),
            "i18n": translations(("text",)),
        },
        required=("id", "text"),
    )
    return (
        {"type": "array", "items": exercise},
        {"type": "array", "items": tip},
    )


def practice_block():
    exercises, tips = practice_entries()
    count = {"type": "integer", "minimum": 0}
    dose = closed(
        {
            "tries": {"type": "integer", "minimum": 1},
            "per": {"type": "string", "enum": ["day", "week"]},
            "days": {"type": "integer", "minimum": 1},
            "recheck_days": {"type": "integer", "minimum": 1},
            "exercises": count,
        }
    )
    return closed(
        {
            "stages": {
                "type": "array",
                "minItems": 4,
                "maxItems": 4,
                "items": closed(
                    {
                        "id": {
                            "type": "string",
                            "enum": [
                                "learning",
                                "improving",
                                "mastering",
                                "strong",
                            ],
                        },
                        "label": {"type": "string", "minLength": 1},
                        "band": ref("band"),
                        "minimum": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 10,
                        },
                    }
                ),
            },
            "dosage": closed(
                {band: dose for band in ("focus", "dev", "good", "strong")}
            ),
            "tiers": closed(
                {"free": practice_limits(), "pro": practice_limits()}
            ),
            "units": {
                "type": "array",
                "items": {"type": "string", "enum": list(UNITS)},
            },
            "spelling": closed({"exercises": exercises, "tips": tips}),
        },
        description=(
            "Practice settings (docs/10-practice-framework.md): stage names "
            "by band, tries by band, tier defaults and the spelling "
            "exercise. Text avoids the words " + ", ".join(AVOID_WORDS) + "."
        ),
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
            "sections": {
                "type": "array",
                "maxItems": 4,
                "items": ref("sectionScore"),
            },
            "comparability": ref("comparability"),
            "evidence": {
                "type": "object",
                "required": ["image_width", "image_height", "factor_regions"],
                "properties": {
                    "image_width": nullable("integer", minimum=1),
                    "image_height": nullable("integer", minimum=1),
                    "photo_width": nullable("integer", minimum=1),
                    "photo_height": nullable("integer", minimum=1),
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
            "then": {
                "required": ["error"],
                "properties": {"comparability": False},
            },
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
                    "sections": False,
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
            "comparability": ref("comparability"),
            "sections": {
                "type": "array",
                "maxItems": 4,
                "description": (
                    "Pro only: the engine's section scores in short form. "
                    "s is the score out of ten (null when the section has "
                    "no measured factor), w the weight the overall score "
                    "used. Names come from the catalogue's sections."
                ),
                "items": closed(
                    {
                        "id": ref("sectionId"),
                        "s": ref("scoreOutOfTen"),
                        "w": {"type": "number", "minimum": 0, "maximum": 1},
                    }
                ),
            },
            "evidence": closed(
                {
                    "width": nullable("integer", minimum=1),
                    "height": nullable("integer", minimum=1),
                    "photo_width": nullable("integer", minimum=1),
                    "photo_height": nullable("integer", minimum=1),
                    "factor_regions": ref("factorRegions"),
                    "measurements": {
                        "type": "object",
                        "additionalProperties": False,
                        "description": (
                            "What was measured on the page, as geometry "
                            "to draw beside the scores, in processed-image "
                            "pixels; never a score, so every tier gets it "
                            "(backend/marked_places.page_measurements)."
                        ),
                        "properties": {
                            "lines": {"type": "integer", "minimum": 0},
                            "slope": {"type": "object"},
                            "size": {"type": "object"},
                            "margin": {"type": "object"},
                            "reading": {"type": "object"},
                        },
                    },
                },
                # The photo's size arrived later; saved reports lack it.
                required=["width", "height", "factor_regions", "measurements"],
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
            "then": {
                "required": ["error"],
                "properties": {"comparability": False},
            },
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
                    "sections": False,
                    "evidence": {
                        "properties": {
                            "factor_regions": {
                                "propertyNames": {
                                    "enum": [str(n) for n in FREE]
                                }
                            }
                        }
                    },
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
    exercises, tips = practice_entries()
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
            "why": {
                "type": "string",
                "minLength": 1,
                "description": "Why the skill helps, one short sentence.",
            },
            "win": {
                "type": "string",
                "minLength": 1,
                "description": (
                    "A small win the child can see, finishing "
                    "\"You'll know it's working when ...\"."
                ),
            },
            "page": {
                "type": "string",
                "pattern": "^handwriting-[a-z-]+$",
                "description": (
                    "The skill's page on vahinitech.com, without '.html'."
                ),
            },
            "i18n": translations(("why", "win")),
            "exercises": exercises,
            "tips": tips,
        },
        # Catalogues from before the practice catalogue (archived versions)
        # carry neither list, and those before 2026-10-11 no why, win,
        # page or i18n.
        required=[
            "n",
            "id",
            "name",
            "section",
            "reason",
            "exercise",
            "target",
            "instruction",
            "limitation",
        ],
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
            "practice": practice_block(),
            "version": ref("catalogVersion"),
        },
        required=[
            "schema_version",
            "language",
            "score_scale",
            "normalized_scale",
            "statuses",
            "bands",
            "factors",
            "sections",
            "limitations",
            "version",
        ],
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
                        "type": "object",
                        "description": (
                            "429: the free tier's daily checks for this "
                            "connection are used (daily_limit.py)."
                        ),
                        "required": ["error_code", "error", "limit"],
                        "additionalProperties": False,
                        "properties": {
                            "error_code": {"const": "daily_limit"},
                            "error": {"type": "string", "minLength": 1},
                            "limit": {"type": "integer", "minimum": 1},
                        },
                    },
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
        title=(
            "HTTP error body for /api/v2/* (401, 403, 404, 413, 422, 429, "
            "503) and /internal/access/v1/* (401, 404, 422, 503)"
        ),
        description=(
            "FastAPI's HTTPException shape. 401 invalid or revoked "
            "credential, 403 paid include= fields requested by Free, 404 "
            "unknown catalogue version, 413 upload too large, 422 "
            "unsupported include field or invalid form/query, 429 the free "
            "tier's daily checks for this connection are used (a Pro key "
            "is never limited; Retry-After gives the seconds to midnight, "
            "India time), 503 "
            "subscription service not configured or unavailable. Analysis "
            "failures are not HTTP errors: they return 200 with ok:false "
            "and an error block in the report schema. The internal access "
            "API answers 404 Not Found when it is switched off or the "
            "request came through a proxy, 401 for a wrong token, 404 for "
            "an unknown customer, key id or secret, 422 for a body it "
            "refuses (unknown field, wrong type, Pro without an expiry) and "
            "503 when the ledger is not configured or unavailable."
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
                "maximum": 5 * 1024 * 1024,
                "description": (
                    "5 MiB per upload; the whole request body must stay "
                    "under 6 MiB."
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
                        "pattern": LANG_PATTERN,
                        "description": (
                            "auto, or BCP 47 tags separated by commas: "
                            "en, en,te, te-Telu-IN. The server reads each "
                            "tag by its language subtag, so te-Telu-IN "
                            "reads as te."
                        ),
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
            "recognition": closed(
                {
                    "stages_sha256": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{64}$",
                        "description": (
                            "sha256 of backend/languages/stages.json, "
                            "the table every recognition route comes from."
                        ),
                    },
                    "devices": {
                        "type": "object",
                        "description": (
                            "The device each registered engine resolved "
                            "to; null until the engine is built."
                        ),
                        "additionalProperties": nullable("string"),
                    },
                }
            ),
            "debug_store": {
                "type": "boolean",
                "description": (
                    "true only on stage with debug storage provisioned: "
                    "photos and answers are being kept (SECURITY.md)."
                ),
            },
            "layout_filter": closed(
                {
                    "enabled": {"type": "boolean"},
                    "built_tiers": {"type": "array"},
                }
            ),
        },
    }


def access_ref(name):
    return {"$ref": ACCESS + name}


def access_definitions():
    """Shared pieces of the internal access API messages."""
    return {
        "customerId": {
            "type": "string",
            "pattern": "^cus_[0-9a-f]{24}$",
            "description": "Opaque ledger identity.",
        },
        "keyId": {
            "type": "string",
            "pattern": "^key_[0-9a-f]{24}$",
            "description": "Names a key; never the secret or its digest.",
        },
        "secret": {
            "type": "string",
            "pattern": "^vh_[A-Za-z0-9_-]{16,}$",
            "maxLength": 200,
            "description": (
                "Customer API key. Shown once when issued; only its "
                "SHA-256 digest is stored."
            ),
        },
        "expiry": {
            "type": "integer",
            "minimum": 1,
            "description": "UTC Unix seconds.",
        },
        "effective": closed(
            {
                "customer_id": access_ref("customerId"),
                "tier": ref("tier"),
                "plan_tier": ref("tier"),
                "subscription_status": {
                    "type": "string",
                    "enum": list(STATUSES),
                },
                "expires_at": ref("unixSeconds"),
            },
            description=(
                "The access the stored plan gives now, computed by the "
                "same function /api/v2/me uses (effective_access)."
            ),
        ),
        "grant": closed(
            {"expires_at": access_ref("expiry")},
            title="POST /internal/access/v1/grants request",
            description=(
                "A new customer with Pro until expires_at (in the future) "
                "and its first key, in one transaction."
            ),
        ),
        "subscription": closed(
            {
                "tier": {"type": "string", "enum": list(TIERS)},
                "status": {"type": "string", "enum": list(STATUSES)},
                "expires_at": {
                    "oneOf": [access_ref("expiry"), {"type": "null"}]
                },
            },
            required=["tier", "status"],
            title=(
                "PUT /internal/access/v1/customers/{id}/subscription request"
            ),
            description=(
                "Pro needs an explicit expiry. cancelled keeps access until "
                "it; expired and revoked give Free at once."
            ),
        ),
        "keyLookup": closed(
            {"key": access_ref("secret")},
            title="POST /internal/access/v1/keys/lookup request",
            description="The secret travels in the body, never in a URL.",
        ),
    }


def access_request():
    return {
        "title": "Internal access API request bodies",
        "description": (
            "One of the three request bodies of /internal/access/v1. Validate "
            "a body against its own definition in access-customer.schema."
            "json (grant, subscription, keyLookup); this file accepts any of "
            "them. Bodies are closed: an unknown field is refused with 422. "
            "POST /customers/{id}/keys and POST /keys/{key_id}/revoke take "
            "no body."
        ),
        "oneOf": [
            access_ref("grant"),
            access_ref("subscription"),
            access_ref("keyLookup"),
        ],
    }


def access_customer():
    key = closed(
        {
            "key_id": access_ref("keyId"),
            "revoked": {"type": "boolean"},
            "created_at": access_ref("expiry"),
        }
    )
    audit = closed(
        {
            "action": {
                "type": "string",
                "pattern": "^(subscription|key):",
                "description": (
                    "subscription:<tier>:<status>:<expiry>, "
                    "key:issue:<key id> or key:revoke:<key id>."
                ),
            },
            "created_at": access_ref("expiry"),
        }
    )
    return {
        **closed(
            {
                "customer_id": access_ref("customerId"),
                "tier": {"type": "string", "enum": list(TIERS)},
                "status": {"type": "string", "enum": list(STATUSES)},
                "expires_at": ref("unixSeconds"),
                "updated_at": access_ref("expiry"),
                "effective": access_ref("effective"),
                "keys": {"type": "array", "items": key},
                "audit": {"type": "array", "items": audit},
            },
            title=(
                "Internal access API customer record: GET /customers/{id}, "
                "PUT /customers/{id}/subscription, POST /keys/{id}/revoke"
            ),
            description=(
                "Stored plan, effective access, every key with its revoked "
                "flag and the audit history. Never a key secret or digest. "
                "Also holds the definitions the other access-* files use."
            ),
        ),
        "definitions": access_definitions(),
    }


def access_key():
    return closed(
        {
            "customer_id": access_ref("customerId"),
            "key_id": access_ref("keyId"),
            "key": access_ref("secret"),
            "expires_at": ref("unixSeconds"),
        },
        title=(
            "Internal access API new key: POST /grants and POST "
            "/customers/{id}/keys (201)"
        ),
        description=(
            "The only answer that carries a secret. Deliver it to the person "
            "and do not store or log it; it cannot be shown again. "
            "expires_at is the customer's stored expiry."
        ),
    )


def access_key_lookup():
    return closed(
        {
            "key_id": access_ref("keyId"),
            "customer_id": access_ref("customerId"),
            "revoked": {"type": "boolean"},
            "created_at": access_ref("expiry"),
            "access": {
                "oneOf": [access_ref("effective"), {"type": "null"}],
                "description": "null for a revoked key, which is refused.",
            },
        },
        title="Internal access API key lookup: POST /keys/lookup",
        description=(
            "Which key and customer a secret belongs to. An unknown secret "
            "is 404. Never echoes the secret."
        ),
        allOf=[
            {
                "if": {"properties": {"revoked": {"const": True}}},
                "then": {"properties": {"access": {"type": "null"}}},
                "else": {"properties": {"access": {"type": "object"}}},
            }
        ],
    )


BUILDERS = {
    "common": common,
    "me": me,
    "report-request": request,
    "report-expanded": expanded,
    "report-compact": compact,
    "catalog": catalog,
    "error": error,
    "health": health,
    "access-request": access_request,
    "access-customer": access_customer,
    "access-key": access_key,
    "access-key-lookup": access_key_lookup,
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
