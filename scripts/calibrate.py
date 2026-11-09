# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Propose score scales from neat reference handwriting (#197).

Most factors are a straight line from a measured spread to a score,
score = 10 x (1 - spread / scale), with the scale set by hand in
backend/scoring_parts/. How high neat writing scores is that setting,
not a question of accuracy. This tool:

- replays every page of a neat reference set (a benchmark set whose
  set.json has "role": "neat-reference") the way `benchmark.py check`
  does, from the kept reader output, and keeps each page's measurements;
- for each factor with a scale, proposes the tightest scale that puts
  the set's median at the target (9.0) and its 10th percentile in the
  Strong band (8.5 and above);
- scores the planted-mistake pages of scripts/factor_tests.py with the
  proposed scales and checks every mistake is still caught at least as
  often as benchmarks/factors/expected.json requires.

A factor that cannot meet both is reported with its numbers, never
forced. Nothing here changes a scale.

    python scripts/calibrate.py [--neat SET ...] [--json OUT]
    python scripts/calibrate.py --neat uji-clean --tool-test   # CI only
    python scripts/calibrate.py --write [PATH]

--write keeps the passing proposals in a file (default
backend/score_scales.json) that the scoring code may read in a later
change, once the owner has reviewed the table; it refuses a --tool-test
run. docs/18-benchmark.md says how to add a neat set and read the table.
"""

# Scripts here print their results; the analyser modules are imported
# from backend/ after the set's settings are in the environment. The
# benchmark's own helpers are reused rather than copied.
# pylint: disable=import-outside-toplevel,protected-access

import argparse
import collections
import contextlib
import importlib
import importlib.util
import io
import json
import math
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(ROOT, "backend")
NEAT = "neat-reference"
TARGET = 9.0
STRONG = 8.5
# Scales tried: from a tenth of today's to ten times it, in steps of
# about 0.6%, each kept to three significant figures.
SPAN = 10.0
STEPS = 400
WRITE_PATH = os.path.join(BACKEND, "score_scales.json")
WARNING = (
    "**Tool test only.** These pages are not neat writing: the UJI page "
    "maker spaces letters with plus or minus 30% random gaps (#197). The "
    "proposals below show the tool works end to end and must not be "
    "applied to any scale."
)

# The factors whose score is a spread over a scale. "feature" is the
# measurement (features.py) the scale divides; "constant" names the
# module constant holding the scale, and "value" is the scale written
# into the formula when there is no constant. "rises" is False when a
# larger scale lowers the score (Loop Closure: share / BOWL_FULL).
# "quiet" sets a factor's other terms to nothing for the check that the
# score stops falling exactly at the scale held here (probe below).
# The penalty terms (words off their line or size) keep their settings.
SCALES = {
    3: {
        "feature": "bowl_share",
        "part": "structure",
        "constant": "BOWL_FULL",
        "rises": False,
    },
    4: {"feature": "width_cv", "part": "structure", "value": 0.8},
    # Word x-heights; a page measured by line boxes uses 0.65, which
    # moves in proportion.
    5: {
        "feature": "size_cv",
        "part": "structure",
        "value": 0.60,
        "label": "size_scale 0.60 (lines 0.65)",
        "quiet": {"words_off_size": 0.0, "size_basis": "words"},
    },
    7: {
        "feature": "line_slope_abs",
        "part": "spatial",
        "value": 8.0,
        "quiet": {"words_off_line": 0.0},
    },
    # Spacing and margins measure the distance to the median since #197
    # and #201; the odd-gap terms keep their settings.
    8: {
        "feature": "word_gap_spread",
        "part": "spatial",
        "constant": "WORD_GAP_SCALE",
        "quiet": {"word_gaps_odd": 0.0},
    },
    9: {
        "feature": "letter_gap_spread",
        "part": "spatial",
        "constant": "LETTER_GAP_SCALE",
        "quiet": {"letter_gaps_odd": 0.0, "words_spaced_off": 0.0},
    },
    10: {
        "feature": "left_spread",
        "part": "spatial",
        "constant": "MARGIN_SCALE",
    },
    # The line's wave; its slope term (/ 10) keeps its setting.
    11: {
        "feature": "line_wave",
        "part": "spatial",
        "constant": "WAVE_SCALE",
        "quiet": {"line_slope_abs": 0.0},
    },
    12: {"feature": "line_slope_std", "part": "spatial", "value": 10.0},
    17: {"feature": "slant_std", "part": "style", "constant": "SLANT_SCALE"},
}
# Legibility and Overall Neatness blend other factors (style.py): they
# move when the passing proposals are applied together.
BLENDS = (18, 20)
# Reported with its numbers and never proposed for.
PARKED = {6: ("abs(tall_ratio - 0.34) / 0.34", "parked: unstable, #194")}

OK = "ok"
LOSES = "loses a planted mistake"
SHORT = "planted check short before any change"
OUT_OF_REACH = "target out of reach"
NOT_LIMITED = "not limited by the neat set"
NOT_MEASURED = "not measured on the neat pages"


def _load_script(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, "scripts", name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def label(n):
    """How factor n's scale appears in the table."""
    spec = SCALES[n]
    if spec.get("label"):
        return spec["label"]
    if spec.get("constant"):
        return spec["constant"]
    return f"{spec['feature']} / {spec['value']}"


# ---------------------------------------------------------------------
# The fitting and the planted check: plain numbers, tested on their own
# (backend/tests/test_calibrate.py).


def quantile(values, q):
    """The q quantile of values, interpolated between the two nearest
    (numpy's default); None for no values."""
    xs = sorted(values)
    if not xs:
        return None
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def meets(scores, target=TARGET, strong=STRONG):
    """Whether the neat pages' median reaches the target and their 10th
    percentile the Strong band."""
    if not scores:
        return False
    return (
        quantile(scores, 0.5) >= target - 1e-9
        and quantile(scores, 0.1) >= strong - 1e-9
    )


def _sig(x, digits=3):
    return float(f"{x:.{digits - 1}e}")


def candidates(now, span=SPAN, steps=STEPS):
    """The scales tried, smallest first."""
    return sorted(
        {_sig(now * span ** (i / steps)) for i in range(-steps, steps + 1)}
    )


def fit(neat_at, now, rises=True, target=TARGET, strong=STRONG):
    """The tightest scale whose neat scores, neat_at(scale), meet the
    target: (scale, None). (now, NOT_LIMITED) when even the tightest
    scale tried meets it, (None, OUT_OF_REACH) when no scale does.

    Tightest is the scale that scores lowest: the smallest when the
    score rises with the scale, the largest otherwise. A looser scale
    than needed only makes planted mistakes harder to see."""
    order = candidates(now)
    if not rises:
        order.reverse()
    if meets(neat_at(order[0]), target, strong):
        return now, NOT_LIMITED
    for scale in order:
        if meets(neat_at(scale), target, strong):
            return scale, None
    return None, OUT_OF_REACH


def caught(rows, n, score_of, least):
    """The share of writers whose planted page scores at least `least`
    below its clean twin on factor n, counted as factor_tests.summarise
    counts it; None when no pair was measured."""
    pairs = [
        (score_of(r["clean"], n), score_of(r["planted"], n)) for r in rows
    ]
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    if not pairs:
        return None
    return round(sum(a - b >= least for a, b in pairs) / len(pairs), 2)


def planted_check(rows, expected, n, score_of, least):
    """Every planted mistake factor n must catch, with the share needed
    (benchmarks/factors/expected.json) and the share caught. Mistakes
    not run (--kinds) are left out."""
    out = []
    for kind, targets in sorted(expected.items()):
        if str(n) not in targets or kind not in rows:
            continue
        out.append(
            {
                "kind": kind,
                "needed": targets[str(n)],
                "rate": caught(rows[kind], n, score_of, least),
            }
        )
    return out


def losses(checks):
    """The checks caught less often than needed, as benchmark.py
    factors judges them."""
    return [c for c in checks if (c["rate"] or 0) < c["needed"]]


def _spread(pages, n):
    feature = SCALES[n]["feature"]
    return [
        {"page": p["page"], "value": float(p["fx"][feature])}
        for p in pages
        if p["scores"].get(str(n)) is not None
        and p["fx"].get(feature) is not None
    ]


def _stats(scores):
    return {
        "pages": len(scores),
        "median": quantile(scores, 0.5),
        "p10": quantile(scores, 0.1),
    }


# What judge() works from:
# - neat: the neat pages, each {"page", "scores", "fx"};
# - rows: the planted pages by mistake, [{"clean": page, "planted": page}];
# - expected: benchmarks/factors/expected.json;
# - score(page, n, scales): the page's factor-n score with the scales
#   given ({factor: scale}, today's for the rest), None when the page
#   does not measure factor n;
# - target, strong: what the neat median and 10th percentile must reach;
# - least: the fall that counts as caught (factor_tests.CAUGHT).
Inputs = collections.namedtuple(
    "Inputs", "neat rows expected score target strong least"
)


def _neat(inp, n, scales):
    found = (inp.score(p, n, scales) for p in inp.neat)
    return [v for v in found if v is not None]


def _planted(inp, n, scales):
    return planted_check(
        inp.rows,
        inp.expected,
        n,
        lambda page, k: inp.score(page, k, scales),
        inp.least,
    )


def judge(n, now, inp):
    """One factor's row: the proposal, the neat set before and after,
    the planted check before and after, and the verdict."""

    def neat_at(scale):
        return _neat(inp, n, {n: scale})

    row = {
        "n": n,
        "scale": label(n),
        "part": SCALES[n]["part"],
        "current": now,
        "spread": _spread(inp.neat, n),
        "before": _stats(neat_at(now)),
        "planted_before": _planted(inp, n, {}),
        "proposed": None,
        "after": None,
        "planted_after": None,
    }
    if not row["before"]["pages"]:
        row["verdict"] = NOT_MEASURED
        return row
    rises = SCALES[n].get("rises", True)
    proposed, why = fit(neat_at, now, rises, inp.target, inp.strong)
    if proposed is None:
        row["verdict"] = why
        return row
    row["proposed"] = proposed
    row["after"] = _stats(neat_at(proposed))
    row["planted_after"] = _planted(inp, n, {n: proposed})
    if losses(row["planted_before"]):
        row["verdict"] = SHORT
    elif losses(row["planted_after"]):
        row["verdict"] = LOSES
    else:
        row["verdict"] = why or OK
    return row


def judge_blend(n, passed, inp):
    """A blended factor with every passing proposal applied together."""
    row = {
        "n": n,
        "scale": "blend of other factors",
        "part": "style",
        "current": None,
        "proposed": None,
        "spread": [],
        "before": _stats(_neat(inp, n, {})),
        "after": _stats(_neat(inp, n, passed)),
        "planted_before": _planted(inp, n, {}),
        "planted_after": _planted(inp, n, passed),
    }
    if not passed:
        row["verdict"] = "no proposal passed, nothing to blend"
    elif losses(row["planted_after"]) and not losses(row["planted_before"]):
        row["verdict"] = "the passing proposals together " + LOSES
    else:
        row["verdict"] = OK
    return row


def judge_parked(n, inp):
    """A parked factor: today's numbers only."""
    scale, why = PARKED[n]
    return {
        "n": n,
        "scale": scale,
        "part": "structure",
        "current": None,
        "proposed": None,
        "spread": [],
        "before": _stats(_neat(inp, n, {})),
        "after": None,
        "planted_before": _planted(inp, n, {}),
        "planted_after": None,
        "verdict": why,
    }


def calibrate(inp, now):
    """Every factor's row, in factor order. now holds today's scales."""
    out = [judge(n, now[n], inp) for n in sorted(SCALES)]
    passed = {r["n"]: r["proposed"] for r in out if r["verdict"] == OK}
    out += [judge_blend(n, passed, inp) for n in BLENDS]
    out += [judge_parked(n, inp) for n in PARKED]
    return sorted(out, key=lambda r: r["n"])


def writable(report):
    """The scales --write keeps: the factors whose verdict is ok.
    Refuses a tool test, whose pages are not neat writing."""
    if report["tool_test"]:
        raise ValueError(
            "a --tool-test run is not neat writing; its scales are never "
            "written"
        )
    return {
        "about": (
            "Score scales proposed by scripts/calibrate.py from neat "
            "reference handwriting (#197). The scoring code does not "
            "read this file yet."
        ),
        "neat_sets": report["neat_sets"],
        "target": report["target"],
        "strong": report["strong"],
        "scales": {
            str(r["n"]): {
                "scale": r["proposed"],
                "was": r["current"],
                "name": r.get("name"),
                "formula": r["scale"],
                "file": f"backend/scoring_parts/{r['part']}.py",
            }
            for r in report["factors"]
            if r["n"] in SCALES and r["verdict"] == OK
        },
    }


# ---------------------------------------------------------------------
# The table.


def _num(v):
    return "-" if v is None else f"{v:.3g}"


def _moved(before, after, key):
    if before is None or before.get(key) is None:
        return "-"
    if after is None or after.get(key) is None:
        return f"{before[key]:.2f}"
    return f"{before[key]:.2f} → {after[key]:.2f}"


def _planted_cell(row):
    before = {c["kind"]: c for c in row["planted_before"]}
    after = {c["kind"]: c for c in row["planted_after"] or []}
    parts = []
    for kind, c in sorted(before.items()):
        now = _num(c["rate"])
        if kind in after:
            now += " → " + _num(after[kind]["rate"])
        parts.append(f"{kind} {now} (needs {_num(c['needed'])})")
    return "; ".join(parts) or "none planted"


def table(report):
    """The report as markdown: a warning for a tool test, then one row
    per factor."""
    sets = ", ".join(f"`{s}`" for s in report["neat_sets"])
    out = [
        f"## Calibration on {sets}"
        + (" (tool test)" if report["tool_test"] else ""),
        "",
    ]
    if report["tool_test"]:
        out += [WARNING, ""]
    out += [
        f"{report['pages']} neat pages; target median {report['target']}, "
        f"10th percentile at or above {report['strong']}; planted "
        f"mistakes: {report['planted_writers']} writers.",
        "",
        "| Factor | Scale | Current | Proposed | Neat spread (median) "
        "| Neat median | Neat p10 | Planted caught | Verdict |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in report["factors"]:
        spread = quantile([s["value"] for s in r["spread"]], 0.5)
        out.append(
            f"| {r['n']} {r.get('name', '')} | `{r['scale']}` "
            f"| {_num(r['current'])} | {_num(r['proposed'])} "
            f"| {_num(spread)} "
            f"| {_moved(r['before'], r['after'], 'median')} "
            f"| {_moved(r['before'], r['after'], 'p10')} "
            f"| {_planted_cell(r)} | {r['verdict']} |"
        )
    for p in report["problems"]:
        out.append(f"- {p}")
    return "\n".join(out)


# ---------------------------------------------------------------------
# The analyser side: pages replayed, measurements kept, scores again.


@contextlib.contextmanager
def keep_features():
    """Every feature dict the scorer measures inside the block, copied
    as measured: build_analysis calls scoring._extract_features."""
    import scoring

    real = scoring._extract_features
    kept = []

    def keep(*args, **kwargs):
        fx = real(*args, **kwargs)
        kept.append(dict(fx))
        return fx

    scoring._extract_features = keep
    try:
        yield kept
    finally:
        scoring._extract_features = real


def _set_meta(bm, name):
    with open(
        os.path.join(bm.SETS[0], name, "set.json"), encoding="utf-8"
    ) as f:
        return json.load(f)


def neat_set_names(bm, names, tool_test):
    """The sets to calibrate on: those named, or every set marked as a
    neat reference. A named set must be marked unless this is a tool
    test."""
    if not names:
        names = [
            d
            for d in sorted(os.listdir(bm.SETS[0]))
            if os.path.exists(os.path.join(bm.SETS[0], d, "set.json"))
            and _set_meta(bm, d).get("role") == NEAT
        ]
    for name in names:
        if not tool_test and _set_meta(bm, name).get("role") != NEAT:
            raise SystemExit(
                f'{name}: set.json has no "role": "{NEAT}"; only neat '
                "reference sets set scales (--tool-test to try the tool)"
            )
    return names


def neat_pages(bm, name, problems):
    """Every page of a set replayed as `benchmark.py check` does, with
    its scores and the measurements they came from."""
    folder, meta = bm._load_set(name)
    bm._apply_settings(meta)
    pages = []
    for page in bm._pages(folder):
        raw, arr = bm._image(folder, page, meta)
        with keep_features() as kept:
            try:
                if bm._ink_mode(meta):
                    result = bm._score_ink(arr, page, meta)
                else:
                    with open(
                        os.path.join(folder, "reader", page + ".json"),
                        encoding="utf-8",
                    ) as f:
                        reader = json.load(f)
                    result = bm._score(arr, raw, reader, meta)
            except bm.MissingRead:
                problems.append(
                    f"{name}/{page}: the kept reader output is missing a "
                    "crop; left out"
                )
                continue
        pages.append(
            {
                "set": name,
                "page": f"{name}/{page}",
                "scores": result["scores"],
                "fx": kept[-1],
            }
        )
    return pages


def _planted_score(img, hand_lines, _ocr):
    """factor_tests.score_page without the reader, keeping the
    measurements."""
    import scoring

    with keep_features() as kept:
        result = scoring.build_analysis(img, hand_lines, {}).to_dict()
    return {
        "page": "planted",
        "scores": {
            str(r["n"]): None if r["unmeasured"] else r["score"]
            for r in result["results"]
        },
        "fx": kept[-1],
    }


def planted_rows(uji, kinds=None):
    """The planted-mistake pages of factor_tests.py (seed 0), by kind:
    [{"clean": page, "planted": page}], and its CAUGHT."""
    ft = _load_script("factor_tests")
    ft.score_page = _planted_score
    with contextlib.redirect_stderr(io.StringIO()):
        rows = ft.run(uji, kinds or list(ft.TARGETS), False)
    out = {}
    for r in rows:
        r["clean"]["page"] = f"planted/{r['writer']} clean"
        r["planted"]["page"] = f"planted/{r['writer']} {r['kind']}"
        out.setdefault(r["kind"], []).append(r)
    return out, ft.CAUGHT


def current_scales():
    """Today's scale of every factor in SCALES, from its module when it
    is a named constant."""
    out = {}
    for n, spec in SCALES.items():
        if spec.get("constant"):
            part = importlib.import_module("scoring_parts." + spec["part"])
            out[n] = float(getattr(part, spec["constant"]))
        else:
            out[n] = float(spec["value"])
    return out


def _scaled(fx, n, scale, now):
    """fx as factor n would see it with `scale` in place of `now`:
    spread / scale is (spread x now / scale) / now."""
    feature = SCALES[n]["feature"]
    out = dict(fx)
    if out.get(feature) is not None:
        out[feature] = float(out[feature]) * now / scale
    return out


def scorer(now):
    """score(page, n, scales) for judge(), from the real formulas.

    Each factor is scored with only its own measurement rescaled, since
    Baseline Alignment and Line Straightness share the line slope; the
    blends are then taken from those scores as style.py takes them."""
    import scoring
    from scoring_parts import style

    def factor(fx, n, scales):
        if n in scales:
            fx = _scaled(fx, n, scales[n], now[n])
        return scoring._score_factor_map(fx)[n]

    def score(page, n, scales):
        if page["scores"].get(str(n)) is None:
            return None
        if n in PARKED:
            return page["scores"][str(n)]
        fx = page["fx"]
        if n not in BLENDS:
            return round(float(factor(fx, n, scales)), 1)
        s = scoring._score_factor_map(fx)
        for k in scales:
            s[k] = factor(fx, k, scales)
        if 17 in scales:
            fx = _scaled(fx, 17, scales[17], now[17])
        style.add_scores(fx, s)
        return round(float(s[n]), 1)

    return score


def reproduces(pages, score):
    """Where the tool, at today's scales, does not give the score the
    scorer gave: the tool would then be judging other formulas."""
    problems = []
    for p in pages:
        for n in list(SCALES) + list(BLENDS):
            want = p["scores"].get(str(n))
            if want is None:
                continue
            got = score(p, n, {})
            if abs(got - want) > 1e-9:
                problems.append(
                    f"{p['page']}: factor {n} is {got} by the tool, "
                    f"{want} by the scorer"
                )
    return problems


def probe(fx, now):
    """Factors whose score does not stop falling exactly at the scale
    held here: SCALES is out of step with scoring_parts/."""
    import scoring

    problems = []
    for n, spec in SCALES.items():
        base = dict(fx)
        base.update(spec.get("quiet", {}))

        def at(x, n=n, base=base, feature=spec["feature"]):
            f = dict(base)
            f[feature] = x
            return float(scoring._score_factor_map(f)[n])

        c = now[n]
        if at(c) != at(1.5 * c) or at(0.98 * c) == at(c):
            problems.append(
                f"factor {n}: its score does not end at {spec['feature']} "
                f"= {c}; SCALES in scripts/calibrate.py is out of step"
            )
    return problems


def run(args):
    """The whole calibration; returns the report."""
    bm = _load_script("benchmark")
    if args.root:
        bm.SETS[0] = os.path.abspath(args.root)
    problems = []
    names = neat_set_names(bm, args.neat, args.tool_test)
    if not names:
        raise SystemExit(
            f'no set marked "role": "{NEAT}"; docs/18-benchmark.md says '
            "how to add one"
        )
    neat = []
    for name in names:
        neat += neat_pages(bm, name, problems)
    if not neat:
        raise SystemExit("the neat sets have no pages")
    import scoring

    now = current_scales()
    score = scorer(now)
    problems += probe(neat[0]["fx"], now)
    rows, least = planted_rows(
        args.uji, args.kinds.split(",") if args.kinds else None
    )
    planted = [
        p
        for rs in rows.values()
        for r in rs
        for p in (r["clean"], r["planted"])
    ]
    out_of_step = reproduces(neat + planted, score)
    problems += out_of_step[:10]
    if len(out_of_step) > 10:
        problems.append(f"and {len(out_of_step) - 10} more")
    with open(
        os.path.join(ROOT, "benchmarks", "factors", "expected.json"),
        encoding="utf-8",
    ) as f:
        expected = json.load(f)
    inp = Inputs(neat, rows, expected, score, args.target, args.strong, least)
    factors = calibrate(inp, now)
    for r in factors:
        r["name"] = scoring._FACTOR_META[r["n"]][1]
    return {
        "tool_test": bool(args.tool_test),
        "warning": WARNING if args.tool_test else None,
        "neat_sets": names,
        "pages": len(neat),
        "planted_writers": max((len(v) for v in rows.values()), default=0),
        "target": args.target,
        "strong": args.strong,
        "factors": factors,
        "problems": problems,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n", maxsplit=1)[0]
    )
    ap.add_argument(
        "--neat",
        action="append",
        help="a neat reference set (default: every set marked as one)",
    )
    ap.add_argument(
        "--root",
        help="a folder of sets outside the repository (default benchmarks/)",
    )
    ap.add_argument(
        "--tool-test",
        action="store_true",
        help="calibrate on sets not marked neat, to prove the tool runs",
    )
    ap.add_argument("--target", type=float, default=TARGET)
    ap.add_argument("--strong", type=float, default=STRONG)
    ap.add_argument(
        "--uji",
        default=os.path.join(
            os.path.expanduser("~"), ".cache", "vahini", "ujipenchars2.txt"
        ),
    )
    ap.add_argument("--kinds", help="planted mistakes, comma list")
    ap.add_argument("--json", help="write the report here")
    ap.add_argument(
        "--write",
        nargs="?",
        const=WRITE_PATH,
        help=f"keep the passing scales (default {WRITE_PATH})",
    )
    args = ap.parse_args(argv)
    if args.write and args.tool_test:
        ap.error("--write refuses a --tool-test run")
    report = run(args)
    text = table(report)
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
    if args.write:
        with open(args.write, "w", encoding="utf-8") as f:
            json.dump(writable(report), f, indent=1, sort_keys=True)
            f.write("\n")
    return 1 if report["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
