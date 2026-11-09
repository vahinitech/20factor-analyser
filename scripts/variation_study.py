# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""How much a factor's score moves between two pages by the same writer.

A before/after comparison should call a change real only when it is
bigger than the change two ordinary pages by the same writer show. This
tool measures that from pairs of saved version-2 reports and proposes a
band per factor: the 90th percentile of the absolute score difference
across pairs (method "p90-abs-delta"). It refuses to propose a band from
too little data. docs/19-comparison-data.md has the method, the
collection plan and what the data we have today can and cannot show.

    # Real pairs: a JSON list of {"writer", "first", "second"}, the two
    # being report files (compact or expanded). Writer is a study code.
    python scripts/variation_study.py reports pairs.json

    # The synthetic floor: planted pages from the UJI letters, two pages
    # of the same passage per writer. Never a band (see the doc).
    python scripts/variation_study.py uji ujipenchars2.txt --pairs 5
"""

import argparse
import importlib.util
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
METHOD = "p90-abs-delta"
PERCENTILE = 90
# A band needs this many pairs of scored pages, from this many writers.
MIN_PAIRS = 30
MIN_WRITERS = 30
# Pages are comparable only in the same script, with word counts within
# this ratio, and neither page holding print that was left out.
MAX_WORD_RATIO = 1.25


def factor_scores(report):
    """{factor number: score out of ten or None} from a compact (2.1) or
    expanded (2.0) version-2 report."""
    out = {}
    for factor in report.get("factors") or []:
        if "n" in factor:
            out[factor["n"]] = factor.get("s")
        else:
            out[factor["number"]] = (factor.get("score") or {}).get("value")
    return out


def not_comparable(first, second):
    """Why two reports should not be paired, or None. Reports without
    comparability facts (saved before it existed) are not checked."""
    a, b = first.get("comparability"), second.get("comparability")
    if not a or not b:
        return None
    if a.get("script") != b.get("script"):
        return "script"
    if a.get("page") != "handwriting" or b.get("page") != "handwriting":
        return "print"
    words = [a.get("words"), b.get("words")]
    if all(isinstance(w, int) and w > 0 for w in words):
        if max(words) / min(words) > MAX_WORD_RATIO:
            return "length"
    return None


def summarise(pairs, band=True):
    """pairs: [(writer, scores_a, scores_b)]. Per factor: how many pairs
    and writers had both scores, the median, 90th percentile and largest
    absolute difference, and the proposed band (the 90th percentile)
    when there is enough data, else null with the reason."""
    rows = {}
    for writer, first, second in pairs:
        for n in sorted(set(first) & set(second)):
            if first[n] is None or second[n] is None:
                continue
            rows.setdefault(n, []).append(
                (writer, abs(float(first[n]) - float(second[n])))
            )
    factors = {}
    for n, items in sorted(rows.items()):
        deltas = np.array([d for _, d in items])
        writers = len({w for w, _ in items})
        entry = {
            "pairs": len(items),
            "writers": writers,
            "median": round(float(np.median(deltas)), 2),
            "p90": round(float(np.percentile(deltas, PERCENTILE)), 2),
            "max": round(float(deltas.max()), 2),
        }
        if band:
            short = []
            if len(items) < MIN_PAIRS:
                short.append(f"{len(items)} pairs, need {MIN_PAIRS}")
            if writers < MIN_WRITERS:
                short.append(f"{writers} writers, need {MIN_WRITERS}")
            entry["band"] = None if short else entry["p90"]
            if short:
                entry["reason"] = "; ".join(short)
        factors[str(n)] = entry
    return {"method": METHOD, "factors": factors}


def from_reports(manifest):
    """Pairs from a manifest of report files, skipping pages that are not
    comparable (counted by reason)."""
    base = os.path.dirname(os.path.abspath(manifest))
    with open(manifest, encoding="utf-8") as f:
        entries = json.load(f)
    pairs, skipped = [], {}
    for entry in entries:
        reports = []
        for key in ("first", "second"):
            with open(os.path.join(base, entry[key]), encoding="utf-8") as f:
                reports.append(json.load(f))
        why = not_comparable(*reports)
        if why:
            skipped[why] = skipped.get(why, 0) + 1
            continue
        pairs.append((entry["writer"], *(factor_scores(r) for r in reports)))
    out = summarise(pairs)
    out["skipped"] = skipped
    return out


def _planted():
    spec = importlib.util.spec_from_file_location(
        "planted_pages", os.path.join(ROOT, "scripts", "planted_pages.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_pairs(writers, count, planted=None, ruled=False):
    """Two clean planted pages per pair, the same four sentences on both
    (a copied passage), drawn from one writer's letters with different
    seeds, on printed ruling when ruled. Scores from the real scorer,
    without OCR."""
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    import scoring  # pylint: disable=import-outside-toplevel

    planted = planted or _planted()
    passage = list(planted.SENTENCES[:4])
    saved, planted.SENTENCES = planted.SENTENCES, passage
    pairs = []
    try:
        for writer, letters in sorted(writers.items()):
            for k in range(count):
                scores = []
                for seed in (2 * k + 1, 2 * k + 2):
                    img, lines, _ = planted.build_page(
                        letters,
                        np.random.default_rng(seed),
                        "clean",
                        ruled=ruled,
                    )
                    analysis = scoring.build_analysis(img, lines, {})
                    scores.append(
                        {
                            r["n"]: None if r["unmeasured"] else r["score"]
                            for r in analysis.to_dict()["results"]
                        }
                    )
                pairs.append((writer, *scores))
    finally:
        planted.SENTENCES = saved
    return pairs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    real = sub.add_parser("reports", help="pairs of saved reports")
    real.add_argument("manifest")
    uji = sub.add_parser("uji", help="synthetic planted pages (no band)")
    uji.add_argument("uji_file")
    uji.add_argument("--pairs", type=int, default=5)
    args = parser.parse_args(argv)
    if args.mode == "reports":
        out = from_reports(args.manifest)
    else:
        planted = _planted()
        writers = planted.parse(planted.fetch(args.uji_file))
        out = summarise(
            synthetic_pairs(writers, args.pairs, planted), band=False
        )
        out["source"] = (
            "synthetic planted pages (UJI letters, generated layout, "
            "no OCR): an engine check, not a writer's variation"
        )
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
