# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Does each factor notice the mistake it is about?

For each of the 20 UJI test writers, a clean page and, from the same
random numbers, one page per planted mistake (scripts/planted_pages.py,
KINDS and FACTOR_KINDS): the two pages differ only by the mistake. Both
are scored, and for each mistake this reports, over the writers:

- caught: the share of writers whose planted page scores at least
  CAUGHT lower than its clean twin on the factor the mistake is about;
- drop: the mean fall of that factor;
- side effects: the other factors that moved most (mean absolute
  change), which a mistake should not move.

    python scripts/factor_tests.py [--ocr] [--kinds a,b] [--json out]

Without --ocr the reader is replaced by each line's ink outline, as in
planted_pages.py, so only the measuring is tested and the factors made
from the reader's confidence (1, 2, 18, 19) cannot move; --ocr reads
every page with the real reader (analyser image).
"""

import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import planted_pages as pp  # noqa: E402  pylint: disable=C0413

CAUGHT = 0.1
# Raw measurements kept per page with --features, for setting scales.
FEATURES = []
TARGETS = {
    "tall_letter": ("5",),
    "big_word": ("5",),
    "tall_ascenders": ("6",),
    "open_loops": ("3",),
    "wide_letters": ("9",),
    "indented_line": ("10",),
    "wavy_line": ("11",),
    "slanted_line": ("17",),
    "shaky_line": ("4",),
    "messy_word": ("1", "2", "19", "18"),
    "low_word": ("7",),
    "tilted_line": ("7", "11", "12"),
    "wide_gap": ("8",),
    "narrow_gap": ("8",),
}
SCORED = [str(n) for n in list(range(1, 13)) + list(range(17, 21))]


def score_page(img, hand_lines, ocr):
    import scoring  # pylint: disable=import-outside-toplevel

    if ocr:
        recognizer = pp.real_reader()
        raw, _err, backend, _meta = recognizer.collect_lines(img, "auto")
        _found, hand_lines = recognizer.extract_hand_lines(
            img,
            raw,
            refine_backend=backend,
            read_region=pp._SERVER[0]._READ_REGION,  # pylint: disable=W0212
        )
        if not hand_lines:
            return None
    result = scoring.build_analysis(img, hand_lines, {}).to_dict()
    out = {
        str(r["n"]): (None if r["unmeasured"] else r["score"])
        for r in result["results"]
    }
    if FEATURES:
        fx = scoring._extract_features(  # pylint: disable=W0212
            img, hand_lines, {}
        )
        out["fx"] = {k: fx.get(k) for k in FEATURES}
    return out


def run(uji, kinds, ocr, seed=0, only=None, ruled=False):
    writers = pp.parse(pp.fetch(uji))
    rows = []
    for wi, writer in enumerate(sorted(writers)):
        if only is not None and wi != only:
            continue
        letters = writers[writer]
        if not all(
            ch in letters for s in pp.SENTENCES for ch in s.replace(" ", "")
        ):
            continue

        def page(kind, letters=letters, wi=wi):
            rng = np.random.default_rng([seed, wi])
            img, lines, _truth = pp.build_page(
                letters, rng, kind, "photo", ruled=ruled
            )
            return score_page(img, lines, ocr)

        clean = page("clean")
        for kind in kinds:
            rows.append(
                {
                    "writer": writer,
                    "kind": kind,
                    "clean": clean,
                    "planted": page(kind),
                }
            )
        print(f"{writer} done", file=sys.stderr, flush=True)
    return rows


def summarise(rows):
    out = {}
    for kind in sorted({r["kind"] for r in rows}):
        rs = [
            r
            for r in rows
            if r["kind"] == kind and r["clean"] and r["planted"]
        ]
        entry = {"writers": len(rs), "targets": {}}
        for n in TARGETS.get(kind, ()):
            pairs = [
                (r["clean"][n], r["planted"][n])
                for r in rs
                if r["clean"][n] is not None and r["planted"][n] is not None
            ]
            if not pairs:
                entry["targets"][n] = {"measured": 0}
                continue
            drops = [a - b for a, b in pairs]
            entry["targets"][n] = {
                "measured": len(pairs),
                "caught": round(
                    sum(d >= CAUGHT for d in drops) / len(pairs), 2
                ),
                "drop": round(float(np.mean(drops)), 2),
                "clean": round(float(np.mean([a for a, _ in pairs])), 2),
            }
        side = {}
        for n in SCORED:
            if n in TARGETS.get(kind, ()):
                continue
            d = [
                abs(r["clean"][n] - r["planted"][n])
                for r in rs
                if r["clean"][n] is not None and r["planted"][n] is not None
            ]
            if d and np.mean(d) >= 0.2:
                side[n] = round(float(np.mean(d)), 2)
        entry["side_effects"] = dict(
            sorted(side.items(), key=lambda kv: -kv[1])[:4]
        )
        out[kind] = entry
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n", maxsplit=1)[0]
    )
    ap.add_argument(
        "--uji",
        default=os.path.join(
            os.path.expanduser("~"), ".cache", "vahini", "ujipenchars2.txt"
        ),
    )
    ap.add_argument("--kinds", help="comma list (default: all)")
    ap.add_argument("--ocr", action="store_true")
    ap.add_argument("--json")
    ap.add_argument(
        "--only", type=int, help="one writer, by index (a fresh process each)"
    )
    ap.add_argument("--features", help="comma list of raw features to keep")
    args = ap.parse_args(argv)
    if args.features:
        FEATURES.extend(args.features.split(","))
    kinds = (
        args.kinds.split(",")
        if args.kinds
        else [k for k, _ in pp.KINDS if k != "clean"]
        + [k for k, _ in pp.FACTOR_KINDS]
    )
    rows = run(args.uji, kinds, args.ocr, only=args.only)
    summary = summarise(rows)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "rows": rows}, f, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
