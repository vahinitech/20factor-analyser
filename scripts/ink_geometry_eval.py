# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""How well backend/vision/ink_geometry.py measures pages the reader cannot read.

Takes a folder of pages and its pages.json, as eval-tools/telugu_pages.py
writes them: each page has a kind (clean, tilted_line, wide_gap), the
truth box of its planted mistake and the written text of each line. The
pages are not in this repository (docs/18-benchmark.md, "Telugu").

    python scripts/ink_geometry_eval.py <pages dir> [--json out.json]

Reports, per kind: pages whose four rows were found; on clean pages the
slope of each row and how many rows read as sloping (false marks); on
tilted pages whether the sinking row is the steepest and over the mark;
the spread of body heights; and on wide-gap pages whether the widest
word gap is the planted one.
"""

import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from vision import (
    computer_vision,
)  # noqa: E402  pylint: disable=wrong-import-position
from vision import (
    ink_geometry,
)  # noqa: E402  pylint: disable=wrong-import-position

ANGLE_LOOK_DEG = 2.0
KNOWN_WORDS = False  # --known-words: the passage says how many words


def _covers(box, truth):
    x, y, w, h = box
    tx, ty, tw, th = truth
    ix = max(0, min(x + w, tx + tw) - max(x, tx))
    iy = max(0, min(y + h, ty + th) - max(y, ty))
    return ix * iy / max(1, tw * th)


def evaluate(folder):
    with open(os.path.join(folder, "pages.json"), encoding="utf-8") as f:
        pages = json.load(f)
    rows_out = []
    for p in pages:
        with open(os.path.join(folder, p["name"] + ".jpg"), "rb") as f:
            arr = computer_vision.to_numpy(f.read(), max_side=2600)
        rows = ink_geometry.find_rows(arr)
        known = (
            [len(t.split()) for t in p["text"]]
            if KNOWN_WORDS and len(p.get("text") or []) == len(rows)
            else None
        )
        geo = ink_geometry.measure_page(arr, rows, known)
        angles = [g["angle"] if g else None for g in geo]
        bodies = [h for g in geo if g for h in ink_geometry.letter_groups(g)]
        gaps = [
            (
                gp["gap"],
                [
                    gp["x0"],
                    int(r["box"][1]),
                    gp["x1"] - gp["x0"],
                    int(r["box"][3]),
                ],
            )
            for r, g in zip(rows, geo)
            if g
            for gp in g["gaps"]
        ]
        rows_out.append(
            {
                "name": p["name"],
                "kind": p["kind"],
                "truth": p.get("truth"),
                "rows": len(rows),
                "lines": len(p.get("text") or []),
                "angles": [None if a is None else round(a, 2) for a in angles],
                "body_cv": (
                    float(np.std(bodies, ddof=1) / np.mean(bodies))
                    if len(bodies) >= 3
                    else None
                ),
                "words": [len(g["words"]) if g else None for g in geo],
                "gaps": gaps,
                "row_boxes": [[int(v) for v in r["box"]] for r in rows],
            }
        )
    return rows_out


def _gap_has_word_after(r):
    tx, ty, tw, th = r["truth"]
    for x, y, w, h in r["row_boxes"]:
        if y <= ty + th / 2 <= y + h:
            return x + w > tx + tw + 10
    return False


def summarise(rows):
    out = {}
    for kind in sorted({r["kind"] for r in rows}):
        rs = [
            r
            for r in rows
            if r["kind"] == kind and (kind == "clean" or r["truth"])
        ]
        found = [r for r in rs if r["rows"] == r["lines"]]
        s = {"pages": len(rs), "rows_found": len(found)}
        angles = [a for r in found for a in r["angles"] if a is not None]
        if kind == "clean":
            s["angle_median"] = round(float(np.median(angles)), 2)
            s["angle_max"] = round(max(angles), 2)
            s["false_slope_marks_per_page"] = round(
                sum(a >= ANGLE_LOOK_DEG for a in angles) / max(1, len(found)),
                2,
            )
            cvs = [r["body_cv"] for r in found if r["body_cv"] is not None]
            s["body_cv_median"] = round(float(np.median(cvs)), 3)
            s["words_per_row"] = [r["words"] for r in found][:5]
            gaps_all = [g for r in found for g, _box in r["gaps"]]
            s["word_gaps_per_page"] = round(len(gaps_all) / len(found), 1)
        if kind == "tilted_line":
            hit = 0
            for r in found:
                last = r["angles"][-1]
                if last is None:
                    continue
                if last >= ANGLE_LOOK_DEG and last == max(
                    a for a in r["angles"] if a is not None
                ):
                    hit += 1
            s["sinking_row_found"] = hit
            s["sinking_angle_median"] = round(
                float(
                    np.median(
                        [
                            r["angles"][-1]
                            for r in found
                            if r["angles"][-1] is not None
                        ]
                    )
                ),
                2,
            )
        if kind == "wide_gap":
            # The page maker records the planted gap even when the next
            # word did not fit and the line ended there: only a gap with
            # writing after it on its row is a gap.
            found = [r for r in found if _gap_has_word_after(r)]
            s["planted_gap_real"] = len(found)
            hit = 0
            for r in found:
                if not r["gaps"]:
                    continue
                gap, box = max(r["gaps"], key=lambda g: g[0])
                med = float(np.median([g for g, _b in r["gaps"]]))
                if gap >= 1.5 * med and _covers(box, r["truth"]) >= 0.5:
                    hit += 1
            s["wide_gap_found"] = hit
        out[kind] = s
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n", maxsplit=1)[0]
    )
    ap.add_argument("folder")
    ap.add_argument("--json")
    ap.add_argument("--known-words", action="store_true")
    args = ap.parse_args(argv)
    global KNOWN_WORDS  # pylint: disable=global-statement
    KNOWN_WORDS = args.known_words
    rows = evaluate(args.folder)
    summary = summarise(rows)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "pages": rows}, f, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
