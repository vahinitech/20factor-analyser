# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Synchronize the source SPDX inventory with npm and Python manifests."""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SBOM = ROOT / "sbom.spdx.json"
APP = "SPDXRef-Package-Vahini"


def synchronize(document):
    """Preserve manual service/font metadata; refresh manifest packages."""
    for package in document["packages"]:
        if package.get("primaryPackagePurpose") == "FONT":
            package["primaryPackagePurpose"] = "OTHER"
    lock = json.loads((ROOT / "package-lock.json").read_text())
    removed = {
        p["SPDXID"]
        for p in document["packages"]
        if p["SPDXID"].startswith("SPDXRef-npm-")
        or p["name"] in ("playwright", "http-server")
    }
    document["packages"] = [
        p for p in document["packages"] if p["SPDXID"] not in removed
    ]
    document["relationships"] = [
        r
        for r in document["relationships"]
        if r["spdxElementId"] not in removed
        and r["relatedSpdxElement"] not in removed
    ]
    for path, entry in sorted(lock["packages"].items()):
        if not path:
            continue
        name = path.rsplit("node_modules/", 1)[-1]
        identifier = "SPDXRef-npm-" + re.sub(r"[^A-Za-z0-9.-]", "-", path)
        package = {
            "SPDXID": identifier,
            "name": name,
            "versionInfo": entry["version"],
            "downloadLocation": entry.get("resolved", "NOASSERTION"),
            "filesAnalyzed": False,
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": entry.get("license", "NOASSERTION"),
            "copyrightText": "NOASSERTION",
            "externalRefs": [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": f"pkg:npm/{name.replace('@', '%40')}@{entry['version']}",
                }
            ],
            "comment": f"Generated from package-lock.json: {path}. Includes transitive dependencies.",
        }
        integrity = entry.get("integrity", "")
        if integrity.startswith(("sha512-", "sha256-", "sha1-")):
            algorithm, digest = integrity.split("-", 1)
            package["checksums"] = [
                {
                    "algorithm": algorithm.upper(),
                    "checksumValue": base64.b64decode(digest).hex(),
                }
            ]
        document["packages"].append(package)
        document["relationships"].append(
            {
                "spdxElementId": identifier,
                "relationshipType": (
                    "DEV_DEPENDENCY_OF"
                    if entry.get("dev")
                    else "RUNTIME_DEPENDENCY_OF"
                ),
                "relatedSpdxElement": APP,
            }
        )
    for filename in ("requirements-core.txt", "requirements-paddle.txt"):
        for line in (ROOT / "backend" / filename).read_text().splitlines():
            match = re.match(
                r"^([A-Za-z0-9_-]+)(?:\[[^]]+\])?([<>=!~].*)$", line
            )
            if not match:
                continue
            name, constraint = match.groups()
            package = next(
                (
                    p
                    for p in document["packages"]
                    if p["name"].lower() == name.lower()
                ),
                None,
            )
            if package is None:
                package = {
                    "SPDXID": f"SPDXRef-Package-{name}",
                    "name": name,
                    "downloadLocation": f"https://pypi.org/project/{name}/",
                    "filesAnalyzed": False,
                    "licenseConcluded": "NOASSERTION",
                    "licenseDeclared": "NOASSERTION",
                    "copyrightText": "NOASSERTION",
                }
                document["packages"].append(package)
            if constraint.startswith("=="):
                package["versionInfo"] = constraint[2:]
            else:
                package.pop("versionInfo", None)
            package["comment"] = (
                f"Declared in backend/{filename}: {name}{constraint}. Resolved container versions require a build SBOM."
            )
            identifier = package["SPDXID"]
            document["relationships"] = [
                r
                for r in document["relationships"]
                if not (
                    {r["spdxElementId"], r["relatedSpdxElement"]}
                    == {APP, identifier}
                )
            ]
            document["relationships"].append(
                {
                    "spdxElementId": identifier,
                    "relationshipType": (
                        "DEV_DEPENDENCY_OF"
                        if name in ("black", "pylint", "httpx")
                        else "RUNTIME_DEPENDENCY_OF"
                    ),
                    "relatedSpdxElement": APP,
                }
            )
    pdf_version = re.search(
        r"pdfjs-dist@([0-9.]+)/",
        (ROOT / "frontend/src/app/app.js").read_text(),
    ).group(1)
    pdf = next(
        p
        for p in document["packages"]
        if p["SPDXID"] == "SPDXRef-Package-PdfJs"
    )
    pdf["versionInfo"] = pdf_version
    pdf["downloadLocation"] = (
        f"https://cdn.jsdelivr.net/npm/pdfjs-dist@{pdf_version}/build/pdf.min.mjs"
    )
    pdf["externalRefs"][0][
        "referenceLocator"
    ] = f"pkg:npm/pdfjs-dist@{pdf_version}"
    pdf["comment"] = (
        "Optional browser PDF reader, lazy-loaded as an ES module from jsDelivr. Version-pinned worker; released after each upload."
    )
    app = next(p for p in document["packages"] if p["SPDXID"] == APP)
    app["comment"] = (
        "First-party browser client and report renderer; scoring runs on the Python server. Some scores use OCR/layout proxies."
    )
    document["comment"] = (
        "Source dependency inventory: exact npm lockfile packages (including transitive dev tooling), pinned CDN PDF.js, "
        "and declared Python core/default-engine dependencies. Unresolved Python ranges are recorded in comments, not as installed versions. "
        "This is not a complete container SBOM: Python transitive packages, OS libraries, model weights and optional OCR tiers require an inventory from the built image. "
        "Rolling font and hosted-service entries describe runtime integrations."
    )
    document["packages"].sort(key=lambda p: p["SPDXID"])
    document["relationships"].sort(
        key=lambda r: (
            r["spdxElementId"],
            r["relationshipType"],
            r["relatedSpdxElement"],
        )
    )
    return document


def main():
    """Write updates, or fail CI when the tracked inventory is stale."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    original = json.loads(SBOM.read_text())
    updated = synchronize(json.loads(json.dumps(original)))
    if updated == original:
        print("SBOM matches dependency manifests.")
        return
    if args.check:
        raise SystemExit("SBOM is stale: run python backend/update_sbom.py")
    updated["creationInfo"]["created"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    updated["creationInfo"]["creators"] = [
        "Organization: Vahini Technologies",
        "Tool: backend/update_sbom.py",
    ]
    digest = hashlib.sha256(
        json.dumps(updated, sort_keys=True).encode()
    ).hexdigest()[:20]
    updated["documentNamespace"] = (
        f"https://vahinitech.com/spdx/vahini-analyser-{digest}"
    )
    SBOM.write_text(json.dumps(updated, indent=2) + "\n")
    print(f"Updated {len(updated['packages'])} source inventory entries.")


if __name__ == "__main__":
    main()
