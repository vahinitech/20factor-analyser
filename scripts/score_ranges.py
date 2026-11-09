# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""How each factor scores on neat, ordinary and poor writing (#197).

Four groups of pages, each scored by today's code:

- neat: every set whose set.json has "role": "neat-reference"
  (benchmarks/neat-penmanship: engraved model pages, 1915-1925),
  replayed from the kept reader output as `benchmark.py check` does;
- uji: the 20 UJI benchmark pages (benchmarks/uji-clean), the same way;
- clean: the 20 planted-page writers with nothing planted
  (scripts/planted_pages.py, seed 0);
- poor: the same writers and letters with every mistake in
  planted_pages.POOR on one page.

Clean and poor pages are measured without the reader, as
`benchmark.py factors` measures them: each line is given a reading
confidence of 0.9, so Letter Formation (1), Stroke Order (2) and
Character Distinction (19), and part of Legibility (18), do not tell
those two groups apart. For each factor and the overall score the
table has the median, the mean and the range. It changes nothing.

    python scripts/score_ranges.py [--json OUT]
"""

# The analyser modules are imported from backend/ after the set's
# settings are in the environment, as benchmark.py does.
# pylint: disable=import-outside-toplevel,protected-access

import argparse
import contextlib
import importlib.util
import io
import json
import math
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NEAT = "neat-reference"
GROUPS = ("neat", "uji", "clean", "poor")
# Factors scored from the reader's confidence: clean and poor pages,
# read by no reader, cannot differ on them.
FROM_READER = (1, 2, 19)


def _load_script(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, "scripts", name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------
# The numbers: plain Python, tested on their own
# (backend/tests/test_score_ranges.py).


def stats(values):
    """Median, mean, lowest and highest of the values that were measured
    (None left out), and how many; None when nothing was measured."""
    xs = sorted(float(v) for v in values if v is not None)
    if not xs:
        return None
    mid = len(xs) // 2
    median = xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2.0
    return {
        "n": len(xs),
        "median": median,
        "mean": sum(xs) / len(xs),
        "min": xs[0],
        "max": xs[-1],
    }


def ranges(groups, factors):
    """{row: {group: stats}} for each factor and "overall", from groups
    {group: [page]}, each page {"scores": {"n": score}, "overall": n}."""
    out = {}
    for n in factors:
        out[str(n)] = {
            g: stats(p["scores"].get(str(n)) for p in pages)
            for g, pages in groups.items()
        }
    out["overall"] = {
        g: stats(p.get("overall") for p in pages)
        for g, pages in groups.items()
    }
    return out


def _cell(s):
    if s is None:
        return "-"
    if s["min"] == s["max"]:
        return f"{s['median']:.1f}"
    return f"{s['median']:.1f} ({s['min']:.1f} to {s['max']:.1f})"


def table(rows, names, counts):
    """Markdown: one row per factor, one column per group, each cell the
    median with the range in brackets; then the means."""
    groups = [g for g in GROUPS if g in counts]
    head = " | ".join(f"{g} ({counts[g]} pages)" for g in groups)
    out = [
        f"| Factor | {head} |",
        "|---|" + "---|" * len(groups),
    ]
    for key, by in rows.items():
        name = "Overall" if key == "overall" else f"{key} {names.get(key, '')}"
        if key.isdigit() and int(key) in FROM_READER:
            name += " (reader)"
        out.append(
            f"| {name} | "
            + " | ".join(_cell(by.get(g)) for g in groups)
            + " |"
        )
    out += [
        "",
        "Mean of the factors measured on every page of the group "
        "(overall excluded):",
        "",
        "| " + " | ".join(groups) + " |",
        "|" + "---|" * len(groups),
        "| "
        + " | ".join(_fmt(_factor_mean(rows, g)) for g in groups)
        + " |",
    ]
    return "\n".join(out)


def _factor_mean(rows, group):
    means = [
        by[group]["mean"]
        for key, by in rows.items()
        if key != "overall" and by.get(group)
    ]
    return sum(means) / len(means) if means else None


def _fmt(v):
    return "-" if v is None or math.isnan(v) else f"{v:.2f}"


# ---------------------------------------------------------------------
# The pages.


def _replayed(bm, name, problems):
    """Every page of a set, replayed from its kept reader output."""
    folder, meta = bm._load_set(name)
    bm._apply_settings(meta)
    pages = []
    for page in bm._pages(folder):
        raw, arr = bm._image(folder, page, meta)
        with open(
            os.path.join(folder, "reader", page + ".json"), encoding="utf-8"
        ) as f:
            reader = json.load(f)
        try:
            result = bm._score(arr, raw, reader, meta)
        except bm.MissingRead:
            problems.append(f"{name}/{page}: a kept crop is missing; left out")
            continue
        pages.append({"page": f"{name}/{page}", **result})
    return pages


def neat_sets(bm):
    """The sets marked as a neat reference."""
    root = bm.SETS[0]
    out = []
    for d in sorted(os.listdir(root)):
        path = os.path.join(root, d, "set.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            if json.load(f).get("role") == NEAT:
                out.append(d)
    return out


def _planted_score(img, hand_lines, _ocr):
    import scoring

    result = scoring.build_analysis(img, hand_lines, {}).to_dict()
    return {
        "scores": {
            str(r["n"]): None if r["unmeasured"] else r["score"]
            for r in result["results"]
        },
        "overall": result["overall"],
    }


def planted_groups(uji):
    """The clean and poor planted pages, one each per writer."""
    ft = _load_script("factor_tests")
    pp = _load_script("planted_pages")
    ft.score_page = _planted_score
    with contextlib.redirect_stderr(io.StringIO()):
        rows = ft.run(uji, [pp.POOR], False)
    return [r["clean"] for r in rows], [r["planted"] for r in rows]


def run(uji):
    bm = _load_script("benchmark")
    problems = []
    names = neat_sets(bm)
    neat = [p for name in names for p in _replayed(bm, name, problems)]
    ordinary = _replayed(bm, "uji-clean", problems)
    clean, poor = planted_groups(uji)
    import scoring

    groups = {"neat": neat, "uji": ordinary, "clean": clean, "poor": poor}
    groups = {g: pages for g, pages in groups.items() if pages}
    names_by_n = {str(n): m[1] for n, m in scoring._FACTOR_META.items()}
    return {
        "neat_sets": names,
        "counts": {g: len(p) for g, p in groups.items()},
        "names": names_by_n,
        "rows": ranges(groups, bm.SCORED),
        "problems": problems,
    }


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
    ap.add_argument("--json", help="write the report here")
    args = ap.parse_args(argv)
    report = run(args.uji)
    text = "\n".join(
        [
            "## Factor scores on neat, ordinary and poor writing",
            "",
            "Median (lowest to highest). Neat: engraved model pages, "
            "1915-1925 (a reference for the ideal end, not children's "
            "writing). Clean and poor: planted pages measured without the "
            "reader, so factors marked (reader) cannot tell them apart.",
            "",
            table(report["rows"], report["names"], report["counts"]),
        ]
        + [f"- {p}" for p in report["problems"]]
    )
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1)
            f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
