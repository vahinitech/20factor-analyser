# SPDX-License-Identifier: AGPL-3.0-only
"""Versioned report data for app clients, independent of access policy.

This adapter never determines entitlements. An authenticated API boundary
must apply the agreed field policy before returning this internal object.
"""

import math
import copy
import json
from pathlib import Path

from entitlements import capabilities

FACTOR_IDS = (
    "letter_formation",
    "stroke_order",
    "loop_closure",
    "line_quality",
    "size_consistency",
    "ascender_descender_control",
    "baseline_alignment",
    "word_spacing",
    "letter_spacing",
    "margin_discipline",
    "line_straightness",
    "vertical_alignment",
    "speed_consistency",
    "pressure_consistency",
    "stroke_continuity",
    "pen_lift_frequency",
    "slant_consistency",
    "legibility",
    "character_distinction",
    "overall_neatness",
)

SENSOR_LIMITATIONS = {
    2: "A still image does not record the order of pen strokes.",
    13: "A still image does not record writing speed or timing.",
    14: "Ink darkness is not a direct measurement of pen pressure.",
    16: "A still image does not record pen lifts over time.",
}


def finite_score(value, maximum):
    """Keep missing/invalid scores distinct from a genuine zero."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or not 0 <= value <= maximum:
        return None
    return value


def factor_output(factor):
    """Preserve scorer evidence without inventing diagnostic confidence."""
    number = factor.get("n")
    if type(number) is not int or not 1 <= number <= 20:
        raise ValueError("Factor number must be an integer from 1 to 20")
    value = finite_score(factor.get("score"), 10)
    unavailable = bool(factor.get("unmeasured")) or value is None
    sensor = factor.get("imuMeasured") is True
    limitation = SENSOR_LIMITATIONS.get(number) if not sensor else None
    method = "sensor" if sensor else "image_heuristic"
    status = "unavailable" if unavailable else "estimated"
    if sensor and not unavailable:
        status = "measured"
    if limitation and not unavailable:
        status = "proxy"
    score = None if unavailable else value
    return {
        "id": FACTOR_IDS[number - 1],
        "number": number,
        "name": factor.get("name"),
        "section_id": factor.get("sec"),
        "status": status,
        "score": {
            "value": score,
            "minimum": 0,
            "maximum": 10,
            "normalized": round(score * 10) if score is not None else None,
            "normalized_maximum": 100,
            "higher_is_better": True,
            "band": factor.get("band") if score is not None else None,
        },
        "reason": {
            "summary": factor.get("evidence") or None,
            "basis": factor.get("basedOn") or None,
            "scoring_inputs": copy.deepcopy(factor.get("scoringInputs") or {}),
            "unavailable_reason": (
                factor.get("unmeasuredReason") if unavailable else None
            ),
        },
        "measurement": {
            "method": method,
            "source_label": factor.get("conf"),
            "confidence_probability": None,
            "display_value": factor.get("value") if not unavailable else None,
            "limitations": [limitation] if limitation else [],
        },
        "practice": {
            "target_description": factor.get("target") or None,
            "instruction": factor.get("tip") or None,
            "exercise_group": factor.get("ex") or None,
        },
    }


def structured_report(payload):
    """Build a fresh canonical report without mutating cached scorer data."""
    analysis = payload.get("analysis") or {}
    factors = [factor_output(item) for item in analysis.get("results", [])]
    ids = [item["id"] for item in factors]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate factor numbers in report")
    factors.sort(key=lambda item: item["number"])
    available = [
        item for item in factors if item["score"]["value"] is not None
    ]
    return {
        "schema_version": "2.0",
        "scoring_version": "legacy-python-20factor",
        "ok": payload.get("ok") is True,
        "summary": {
            "score": finite_score(analysis.get("overall"), 100),
            "maximum": 100,
            "expected_factor_count": 20,
            "returned_factor_count": len(factors),
            "scored_factor_count": len(available),
            "proxy_factor_count": sum(f["status"] == "proxy" for f in factors),
            "score_basis": "Existing weighted section score, including image proxies.",
        },
        "factors": factors,
        "recognition": {
            "text": payload.get("full_text", ""),
            "metadata": dict(analysis.get("recognition") or {}),
        },
        "limitations": [
            "Scores are heuristic practice feedback, not a diagnosis.",
            "Normalized scores are not accuracy or confidence percentages.",
            "The legacy overall score can include proxy factors.",
        ],
    }


def public_report(payload, access):
    """Project from an allowlist so cached Pro evidence cannot leak to Free."""
    report = structured_report(payload)
    rights = capabilities(access)
    report["access"] = {**access, "capabilities": rights}
    allowed = set(rights["factor_numbers"])
    report["locked_factors"] = [
        {"number": n, "id": FACTOR_IDS[n - 1], "required_tier": "pro"}
        for n in range(1, 21)
        if n not in allowed
    ]
    report["factors"] = [
        f for f in report["factors"] if f["number"] in allowed
    ]
    report["summary"]["returned_factor_count"] = len(report["factors"])
    if access["tier"] != "pro":
        report["recognition"] = {"text": report["recognition"]["text"]}
        for factor in report["factors"]:
            factor.pop("practice")
            factor["reason"] = {
                "summary": (
                    "No score is available."
                    if factor["score"]["value"] is None
                    else f"This factor is in the {factor['score']['band']} band under the current scoring model."
                )
            }
            factor["measurement"].pop("display_value")
            factor["measurement"].pop("source_label")
    else:
        report["coaching"] = copy.deepcopy(
            (payload.get("analysis") or {}).get("coachTips") or []
        )
        report["evidence"] = {
            "image_width": payload.get("proc_w"),
            "image_height": payload.get("proc_h"),
            "factor_regions": copy.deepcopy(
                payload.get("factor_regions") or {}
            ),
        }
        # Read the shared generated catalogue used by the browser.
        catalog_file = (
            Path(__file__).resolve().parents[1]
            / "frontend/src/report/worksheet-catalog.js"
        )
        catalog = json.loads(
            catalog_file.read_text().split(" = ", 1)[1].rstrip(";\n")
        )
        selected = []
        for factor in sorted(
            report["factors"],
            key=lambda f: (
                f["score"]["value"] if f["score"]["value"] is not None else 11
            ),
        ):
            value = factor["score"]["value"]
            if (
                value is None
                or value >= 7
                or factor["status"] in ("unavailable", "proxy")
            ):
                continue
            sheet = next(
                (w for w in catalog if factor["number"] in w["factors"]), None
            )
            if sheet and sheet["id"] not in [w["id"] for w in selected]:
                selected.append(
                    {
                        "id": sheet["id"],
                        "title": sheet["title"],
                        "pdf_path": "/assets/worksheets/"
                        + sheet["id"]
                        + ".pdf",
                        "factor_number": factor["number"],
                    }
                )
            if len(selected) == 3:
                break
        report["worksheets"] = selected
    if not payload.get("ok"):
        report["error"] = {
            "code": payload.get("error_code", "analysis_failed"),
            "message": "The image could not be analysed. Try a clear handwriting sample.",
        }
    return report


def legacy_report(payload, access):
    """Apply the same boundary to the older browser contract."""
    if access["tier"] == "pro":
        output = copy.deepcopy(payload)
        output["access"] = {**access, "capabilities": capabilities(access)}
        return output
    report = public_report(payload, access)
    original = payload.get("analysis") or {}
    allowed = set(capabilities(access)["factor_numbers"])
    factors = []
    for source in original.get("results", []):
        if source["n"] not in allowed:
            continue
        item = {
            key: source.get(key)
            for key in (
                "n",
                "sec",
                "name",
                "score",
                "score100",
                "band",
                "conf",
                "unmeasured",
                "imuMeasured",
            )
        }
        item.update(
            ex="", target="", tip="", value="", evidence="", basedOn=None
        )
        item["evidence"] = (
            f"{source.get('name', 'This factor')} is in the {source.get('band', 'unavailable')} band under the image scoring model."
        )
        factors.append(item)
    sections = []
    for section in original.get("sections", []):
        members = [f for f in factors if f["sec"] == section["id"]]
        if not members:
            continue
        average = sum(f["score"] for f in members) / len(members)
        sections.append(
            {
                "id": section["id"],
                "name": section["name"],
                "weight": section.get("weight", 1),
                "blurb": "",
                "factors": members,
                "avg": average,
                "avg100": round(average * 10),
                "scoredCount": len(members),
            }
        )
    output = {
        key: copy.deepcopy(payload.get(key))
        for key in (
            "ok",
            "engine",
            "full_text",
            "rec_texts",
            "rec_polys",
            "rec_scores",
            "proc_w",
            "proc_h",
        )
    }
    output["access"] = report["access"]
    output["locked_factors"] = report["locked_factors"]
    output["analysis"] = (
        {
            "results": factors,
            "sections": sections,
            "overall": original.get("overall", 0),
            "overallMeasured": original.get("overallMeasured", 0),
            "measuredCount": len(factors),
            "topWeak": sorted(factors, key=lambda f: f["score"])[:3],
            "topStrong": sorted(factors, key=lambda f: -f["score"])[:4],
            "source": "python",
            "coachTips": [],
            "plainGroups": [],
        }
        if payload.get("ok")
        else None
    )
    if not payload.get("ok"):
        output.update(
            error_code=report["error"]["code"],
            error=report["error"]["message"],
        )
    if output.get("analysis"):
        output["analysis"]["access"] = output["access"]
    return output
