# SPDX-License-Identifier: AGPL-3.0-only
"""Small report messages and a public, immutable presentation dictionary."""

import hashlib
import json
from pathlib import Path
from functools import lru_cache
import sys

# Run as a script (python backend/report/compact_reports.py): backend/ goes on
# the path so the other packages import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from report import comparison_data
from report import practice_catalog
import scoring
from server.entitlements import capabilities
from report.report_contract import FACTOR_IDS, SENSOR_LIMITATIONS, finite_score

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
                **practice_catalog.factor_practice(number),
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
        "practice": practice_catalog.practice_block(),
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
    if version == dictionary()["version"]:
        return dictionary_bytes()
    # Request values select an existing entry, never form a filesystem path.
    archives = {
        path.stem: path
        for path in (Path(__file__).resolve().parents[1] / "catalogs").glob(
            "*.json"
        )
    }
    path = archives.get(version)
    return path.read_bytes() if path is not None else None


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
        # Section means use every factor: Pro only, like the expanded form.
        report["sections"] = comparison_data.compact_sections(analysis)
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
        regions = payload.get("factor_regions") or {}
        report["evidence"] = {
            "width": payload.get("proc_w"),
            "height": payload.get("proc_h"),
            # The uploaded photo's size; each region's marks are in its
            # pixels, so a viewer can draw them on the family's own copy.
            "photo_width": payload.get("photo_w"),
            "photo_height": payload.get("photo_h"),
            "factor_regions": comparison_data.with_marks(
                {
                    str(k): v
                    for k, v in regions.items()
                    if str(k).isdigit() and int(k) in allowed
                },
                comparison_data.factor_marks(payload, allowed),
            ),
            # Geometry of what was measured, never a score: every tier
            # gets it, so a Free report can show the whole page was read.
            "measurements": payload.get("measurements") or {},
        }
    if payload.get("ruleset"):
        # The hash of the packs and the request's profile, never the
        # profile itself (languages/profile.py).
        report["ruleset"] = payload["ruleset"]
    if payload.get("age_band"):
        # Echoed as sent; no score reads it yet (#212, #216).
        report["age_band"] = payload["age_band"]
    if report["ok"]:
        # Counts only, no text, so every tier gets them.
        report["comparability"] = comparison_data.comparability(payload)
    else:
        report["error"] = {
            "code": payload.get("error_code", "analysis_failed")
        }
    return report


if __name__ == "__main__":
    import sys

    destination = (
        Path(__file__).resolve().parents[1]
        / "catalogs"
        / (dictionary()["version"] + ".json")
    )
    if "--check" in sys.argv:
        if (
            not destination.exists()
            or destination.read_bytes() != dictionary_bytes()
        ):
            raise SystemExit(
                "Catalogue is stale. Run python backend/report/compact_reports.py"
            )
    else:
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(dictionary_bytes())
