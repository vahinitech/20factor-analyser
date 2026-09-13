# SPDX-License-Identifier: AGPL-3.0-only
"""Small report messages and a public, immutable presentation dictionary."""

import hashlib
import json
import re
from pathlib import Path
from functools import lru_cache

import scoring
from entitlements import capabilities
from report_contract import FACTOR_IDS, SENSOR_LIMITATIONS, finite_score

STATUS_CODES = {
    "estimated": "e",
    "proxy": "p",
    "measured": "m",
    "unavailable": "u",
}
OPTIONAL_FIELDS = {"text", "inputs", "coaching", "evidence"}


@lru_cache(maxsize=1)
def dictionary():
    """Only public definitions, never scores, customer data or scan evidence."""
    factors = []
    for number, (section, name, reason) in scoring._FACTOR_META.items():
        exercise, target, instruction = scoring._FACTOR_EXTRAS[number]
        factors.append(
            {
                "n": number,
                "id": FACTOR_IDS[number - 1],
                "name": name,
                "section": section,
                "reason": reason,
                "exercise": exercise,
                "target": target,
                "instruction": instruction,
                "limitation": SENSOR_LIMITATIONS.get(number),
            }
        )
    body = {
        "schema_version": "2.1",
        "language": "en",
        "score_scale": [0, 10],
        "normalized_scale": [0, 100],
        "statuses": {v: k for k, v in STATUS_CODES.items()},
        "bands": [
            {"id": "strong", "minimum": 8.5},
            {"id": "good", "minimum": 7},
            {"id": "dev", "minimum": 4.5},
            {"id": "focus", "minimum": 0},
        ],
        "factors": factors,
        "sections": [
            {"id": s["id"], "name": s["name"], "weight": s["weight"]}
            for s in scoring._SECTIONS
        ],
        "limitations": [
            "Scores are heuristic practice feedback, not a diagnosis.",
            "Normalized scores are not accuracy or confidence percentages.",
            "The overall score can include image proxies.",
        ],
    }
    version = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:20]
    return {**body, "version": version}


@lru_cache(maxsize=1)
def dictionary_bytes():
    """Serialize shared text once per process, not once per scan."""
    return json.dumps(
        dictionary(), separators=(",", ":"), ensure_ascii=False
    ).encode()


@lru_cache(maxsize=16)
def catalog_bytes(version):
    """Retain archived definitions so older saved reports remain readable."""
    if not re.fullmatch(r"[a-f0-9]{20}", version):
        return None
    if version == dictionary()["version"]:
        return dictionary_bytes()
    path = Path(__file__).parent / "catalogs" / (version + ".json")
    return path.read_bytes() if path.is_file() else None


def build_compact(payload, access, include=()):
    """Project directly from scores without building a full verbose response."""
    analysis = payload.get("analysis") or {}
    rights = capabilities(access)
    allowed = set(rights["factor_numbers"])
    factors = []
    for factor in analysis.get("results", []):
        number = factor["n"]
        if number not in allowed:
            continue
        value = finite_score(factor.get("score"), 10)
        unavailable = factor.get("unmeasured") or value is None
        sensor = factor.get("imuMeasured") is True
        status = (
            "u"
            if unavailable
            else (
                "m" if sensor else "p" if number in SENSOR_LIMITATIONS else "e"
            )
        )
        factors.append(
            {"n": number, "s": None if unavailable else value, "st": status}
        )
    report = {
        "schema_version": "2.1",
        "format": "compact",
        "catalog_version": dictionary()["version"],
        "ok": payload.get("ok") is True,
        "access": {
            k: access.get(k)
            for k in ("tier", "plan_tier", "subscription_status", "expires_at")
        },
        "summary": {
            "score": finite_score(analysis.get("overall"), 100),
            "factor_count": len(factors),
        },
        "factors": sorted(factors, key=lambda f: f["n"]),
        "locked": [n for n in range(1, 21) if n not in allowed],
    }
    if "text" in include:
        report["text"] = payload.get("full_text", "")
        report["counts"] = {"lines": len(payload.get("hand_lines") or [])}
        recognition = analysis.get("recognition") or {}
        report["recognition"] = {
            key: recognition.get(key)
            for key in (
                "backend",
                "level",
                "confidence_pct",
                "mean_confidence",
                "hand_lines",
                "printed_lines",
                "reliable_lines",
                "assistive_only",
                "passage_aligned",
            )
        }
    if access["tier"] == "pro":
        if "inputs" in include:
            report["inputs"] = {
                str(f["n"]): {
                    "evidence": f.get("evidence"),
                    "basis": f.get("basedOn"),
                    "values": f.get("scoringInputs"),
                }
                for f in analysis.get("results", [])
                if f["n"] in allowed
            }
        if "coaching" in include:
            report["coaching"] = analysis.get("coachTips") or []
        if "evidence" in include:
            report["evidence"] = {
                "width": payload.get("proc_w"),
                "height": payload.get("proc_h"),
                "factor_regions": payload.get("factor_regions") or {},
            }
    if not report["ok"]:
        report["error"] = {
            "code": payload.get("error_code", "analysis_failed")
        }
    return report


if __name__ == "__main__":
    import sys

    destination = (
        Path(__file__).parent
        / "catalogs"
        / (dictionary()["version"] + ".json")
    )
    if "--check" in sys.argv:
        if (
            not destination.exists()
            or destination.read_bytes() != dictionary_bytes()
        ):
            raise SystemExit(
                "Catalogue is stale. Run python backend/compact_reports.py"
            )
    else:
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(dictionary_bytes())
