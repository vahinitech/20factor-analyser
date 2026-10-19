# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The real-handwriting benchmark: does a change move any page's score?

A benchmark set (benchmarks/<set>/) holds real handwritten pages, the
reader's output for each page and the scores the analyser gave. Reading a
page needs the OCR models and takes seconds; everything after it (merging
and joining lines, the printed check, scoring) is fast and deterministic.
So the reader's output is kept, and every change is checked by replaying
it through the current code:

    python scripts/benchmark.py check            # every PR, no models
    python scripts/benchmark.py update           # accept new scores
    python scripts/benchmark.py capture          # analyser image: read again
    python scripts/benchmark.py live             # analyser image: compare
    python scripts/benchmark.py planted [--update]  # planted mistakes
    python scripts/benchmark.py factors [--update]  # each factor's own

check fails when any score, line or text differs from expected.json, and
prints a table of what moved. Accepting a change is running update and
committing expected.json, so the PR diff shows every score that moved.
Some limits cannot be updated away (LIMITS below). live reads every page
again with the real models and reports how far the reader moved from the
kept output; capture keeps the new reading. docs/18-benchmark.md says
when to use which.
"""

# Scripts here print their results; the analyser modules are imported
# from backend/ after the settings are in the environment.
# pylint: disable=import-outside-toplevel

import argparse
import contextlib
import difflib
import glob
import hashlib
import importlib.util
import io
import json
import os
import unicodedata
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(ROOT, "backend")
# Where the sets are. A set whose pages may not be published (a licence
# not yet confirmed) lives outside the repository: --root points at it.
SETS = [os.path.join(ROOT, "benchmarks")]
SCORED = tuple(range(1, 13)) + tuple(range(17, 21))  # 13-16 need the pen
FREE = (1, 5, 7, 8, 18)

# Limits a change may not cross, whatever expected.json says.
LIMITS = {
    # Share of written lines scored, against the set's own floor.
    "lines_found_min": "floor in set.json",
    # A written line scored twice, or a measured score of exactly 0.
    "repeats": 0,
    "measured_zero": 0,
    # The same page replayed twice must give the same result.
    "repeatable": True,
    # Agreement with the owner's ranking by eye may fall by at most this.
    "eye_drop": 0.05,
}
# How far a live reading may move a score before it is reported as a
# change of the reader (CPUs and library builds round differently).
LIVE_TOLERANCE = 0.3


def _load_set(name):
    folder = os.path.join(SETS[0], name)
    with open(os.path.join(folder, "set.json"), encoding="utf-8") as f:
        meta = json.load(f)
    return folder, meta


def _apply_settings(meta):
    """The reader settings the set was captured with, before any analyser
    module reads the environment."""
    for key, value in meta["settings"].items():
        os.environ[key] = str(value)
    if BACKEND not in sys.path:
        sys.path.insert(0, BACKEND)


def _pages(folder):
    return sorted(
        os.path.splitext(os.path.basename(p))[0]
        for p in glob.glob(os.path.join(folder, "pages", "*.jpg"))
    )


def _crop_key(crop):
    return hashlib.sha1(crop.tobytes() + str(crop.shape).encode()).hexdigest()


def _image(folder, page, meta):
    import computer_vision

    with open(os.path.join(folder, "pages", page + ".jpg"), "rb") as f:
        raw = f.read()
    side = int(meta["settings"]["VAHINI_OCR_MAX_SIDE"])
    return raw, computer_vision.to_numpy(raw, max_side=side)


class MissingRead(Exception):
    """The current code asked the reader about a crop the kept output
    does not hold: only a live run can say what the reader sees there."""


def _ink_mode(meta):
    """Whether the set's language is measured from the ink, as the server
    does when VAHINI_INK_GEOMETRY_LANGS names it (ink_geometry.py)."""
    langs = meta["settings"].get("VAHINI_INK_GEOMETRY_LANGS", "")
    on = {x.strip() for x in langs.split(",") if x.strip()}
    return bool(on) and meta.get("lang") in on


def _score_ink(arr, page, meta):
    """One page measured from the ink, as the server's ink mode does;
    with "passage" set, the page's written text is the passage copied."""
    import classify
    import computer_vision
    import ink_geometry
    import scoring

    rows = ink_geometry.find_rows(arr)
    classify.classify_lines(arr, rows)
    hand = [r for r in rows if not r.get("printed_hint")]
    if meta.get("passage"):
        text = meta.get("page_text", {}).get(page) or []
        ink_geometry.expect_words(hand, "\n".join(text))
    layout = computer_vision.vl_analyze(arr, hand, False)["layout"]
    analysis = scoring.build_analysis(arr, hand, layout).to_dict()
    results = {r["n"]: r for r in analysis["results"]}
    return {
        "overall": analysis["overall"],
        "scores": {
            str(n): None if results[n]["unmeasured"] else results[n]["score"]
            for n in SCORED
        },
        "lines": ["" for _ in hand],
    }


def _score(arr, raw, reader, meta):
    """One page through the pipeline after the reader, from its kept
    output. Returns the result kept in expected.json."""
    import computer_vision
    import layout_filter
    import recognizer
    import scoring

    recognizer.configure(
        ocr_langs=meta["settings"]["VAHINI_OCR_LANGS"].split(","),
        ocr_backend=meta["settings"]["VAHINI_OCR_BACKEND"],
    )
    regions = reader["regions"]
    real_regions = layout_filter.excluded_regions
    layout_filter.excluded_regions = lambda _arr: regions
    reads = reader["reads"]

    def read_region(crop, _lang):
        key = _crop_key(crop)
        if key not in reads:
            raise MissingRead(key)
        return reads[key]

    try:
        lines = [dict(l) for l in reader["raw_lines"]]
        _all, hand = recognizer.extract_hand_lines(
            arr, lines, raw_bytes=raw, read_region=read_region
        )
    finally:
        layout_filter.excluded_regions = real_regions
    layout = computer_vision.vl_analyze(arr, hand, False)["layout"]
    analysis = scoring.build_analysis(arr, hand, layout).to_dict()
    results = {r["n"]: r for r in analysis["results"]}
    return {
        "overall": analysis["overall"],
        "scores": {
            str(n): None if results[n]["unmeasured"] else results[n]["score"]
            for n in SCORED
        },
        "lines": [str(l.get("text") or "") for l in hand],
    }


def _norm(text):
    """Letters only, in any script (Telugu vowel signs included)."""
    return "".join(
        ch
        for ch in text.lower()
        if ch.isalpha() or unicodedata.category(ch).startswith("M")
    )


def _line_check(lines, sentences):
    """Each scored line matched to the written sentence it reads best:
    which sentences were found, and how many lines repeat one."""
    found, repeats, other = set(), 0, 0
    for text in lines:
        sims = [
            difflib.SequenceMatcher(None, _norm(text), _norm(s)).ratio()
            for s in sentences
        ]
        best = int(max(range(len(sims)), key=sims.__getitem__))
        if sims[best] < 0.4:
            other += 1
        elif best in found:
            repeats += 1
        else:
            found.add(best)
    return len(found), repeats, other


def _spearman(a, b):
    """Rank agreement of two orderings of the same pages, -1 to 1."""
    n = len(a)
    if n < 3:
        return None
    rank_b = {p: i for i, p in enumerate(b)}
    d2 = sum((i - rank_b[p]) ** 2 for i, p in enumerate(a))
    return 1 - 6 * d2 / (n * (n * n - 1))


def run_set(name):
    """Replay every page of a set; returns (results, problems)."""
    folder, meta = _load_set(name)
    _apply_settings(meta)
    results, problems = {}, []
    for page in _pages(folder):
        raw, arr = _image(folder, page, meta)
        if _ink_mode(meta):
            first = _score_ink(arr, page, meta)
            again = _score_ink(arr, page, meta)
            if first != again:
                problems.append(f"{page}: two runs gave different results")
            # Rows have no text: count them against the written lines.
            n = len(first["lines"])
            want = meta["lines_per_page"]
            first.update(
                {
                    "sentences_found": min(n, want),
                    "repeats": max(0, n - want),
                    "unmatched": 0,
                }
            )
            results[page] = first
            continue
        with open(
            os.path.join(folder, "reader", page + ".json"), encoding="utf-8"
        ) as f:
            reader = json.load(f)
        try:
            first = _score(arr, raw, reader, meta)
            again = _score(arr, raw, reader, meta)
        except MissingRead:
            problems.append(
                f"{page}: the code reads a crop the kept reader output does "
                "not hold; run `benchmark.py live` in the analyser image"
            )
            continue
        if first != again:
            problems.append(f"{page}: two replays gave different results")
        written = meta.get("page_text", {}).get(page, meta.get("sentences"))
        found, repeats, other = _line_check(first["lines"], written)
        first.update(
            {"sentences_found": found, "repeats": repeats, "unmatched": other}
        )
        results[page] = first
    return meta, results, problems


def _limits(meta, results, expected):
    problems = []
    found = sum(r["sentences_found"] for r in results.values())
    if found < meta["floor_sentences_found"]:
        problems.append(
            f"{found} written lines scored, under the floor of "
            f"{meta['floor_sentences_found']}"
        )
    for page, r in results.items():
        if r["repeats"]:
            problems.append(f"{page}: {r['repeats']} line(s) scored twice")
        zeros = [n for n, s in r["scores"].items() if s == 0.0]
        if zeros:
            problems.append(f"{page}: measured score 0 for factor(s) {zeros}")
    eye = eye_agreement(meta, results)
    if eye is not None and expected.get("eye_agreement") is not None:
        if eye < expected["eye_agreement"] - LIMITS["eye_drop"]:
            problems.append(
                f"agreement with the ranking by eye fell from "
                f"{expected['eye_agreement']:.2f} to {eye:.2f}"
            )
    return problems


def eye_agreement(meta, results):
    order = meta.get("eye_ranking") or []
    if not order:
        return None
    ours = sorted(order, key=lambda p: -results[p]["overall"])
    return round(_spearman(ours, order), 3)


def _fmt(v):
    return "not measured" if v is None else f"{v}"


def diff_table(expected, results):
    """Markdown rows for every page and number that moved."""
    rows = []
    for page in sorted(set(expected["pages"]) | set(results)):
        old = expected["pages"].get(page)
        new = results.get(page)
        if old is None or new is None:
            rows.append(
                f"| {page} | page | {'kept' if old else 'none'} "
                f"| {'scored' if new else 'not scored'} |"
            )
            continue
        if old["overall"] != new["overall"]:
            rows.append(
                f"| {page} | overall | {old['overall']} | {new['overall']} |"
            )
        for n in map(str, SCORED):
            if old["scores"].get(n) != new["scores"].get(n):
                rows.append(
                    f"| {page} | factor {n} | {_fmt(old['scores'].get(n))} "
                    f"| {_fmt(new['scores'].get(n))} |"
                )
        for key in ("sentences_found", "repeats", "unmatched"):
            if old[key] != new[key]:
                rows.append(f"| {page} | {key} | {old[key]} | {new[key]} |")
        if old["lines"] != new["lines"]:
            rows.append(
                f"| {page} | lines | {len(old['lines'])} read "
                f"| {len(new['lines'])} read, text changed |"
            )
    if not rows:
        return ""
    return "| Page | What | Expected | Now |\n|---|---|---|---|\n" + "\n".join(
        rows
    )


def summary(meta, results):
    """The free factors and overall per page, as markdown."""
    head = ["Page", "Lines", "Overall"] + [f"F{n}" for n in FREE]
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for page, r in results.items():
        cells = [
            page,
            f"{r['sentences_found']}/{meta['lines_per_page']}",
            str(r["overall"]),
        ] + [_fmt(r["scores"][str(n)]) for n in FREE]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def _report(text):
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def cmd_check(args):
    meta, results, problems = run_set(args.set)
    folder = os.path.join(SETS[0], args.set)
    with open(os.path.join(folder, "expected.json"), encoding="utf-8") as f:
        expected = json.load(f)
    problems += _limits(meta, results, expected)
    table = diff_table(expected, results)
    _report(f"## Benchmark `{args.set}`\n")
    found = sum(r["sentences_found"] for r in results.values())
    total = meta["lines_per_page"] * len(results)
    _report(f"Written lines scored: {found} of {total}.")
    eye = eye_agreement(meta, results)
    if eye is not None:
        _report(f"Agreement with the ranking by eye: {eye:.2f}.")
    if table:
        _report(
            "\nScores that differ from expected.json. If the change is "
            "meant, run `python scripts/benchmark.py update` and commit "
            "expected.json; the diff shows every move.\n\n" + table
        )
    for p in problems:
        _report(f"- {p}")
    if not table and not problems:
        _report("Every page matches expected.json.")
    _report("\n" + summary(meta, results))
    return 1 if (table or problems) else 0


def cmd_update(args):
    meta, results, problems = run_set(args.set)
    folder = os.path.join(SETS[0], args.set)
    if problems:
        for p in problems:
            print(p)
        return 1
    out = {
        "set": args.set,
        "eye_agreement": eye_agreement(meta, results),
        "pages": results,
    }
    hard = _limits(meta, results, {})
    with open(
        os.path.join(folder, "expected.json"), "w", encoding="utf-8"
    ) as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    for p in hard:
        print(f"over a limit, so check will still fail: {p}")
    print(summary(meta, results))
    return 1 if hard else 0


def _server():
    """The analyser exactly as the server sets it up (settings, reader
    registry), loaded from backend/ppocr-server.py."""
    spec = importlib.util.spec_from_file_location(
        "benchmark_server", os.path.join(BACKEND, "ppocr-server.py")
    )
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    return server


def read_page(server, folder, page, meta):
    """The reader's output for one page, as the server makes it: raw
    lines, layout regions, and every crop the line recovery reads."""
    import layout_filter
    import recognizer

    raw, arr = _image(folder, page, meta)
    raw_lines, err, _backend, _meta = recognizer.collect_lines(
        arr, meta["lang"]
    )
    if err and not raw_lines:
        raise RuntimeError(f"{page}: the reader failed: {err}")
    reads = {}

    def read_region(crop, lang):
        got = server._READ_REGION(crop, lang)  # pylint: disable=W0212
        reads[_crop_key(crop)] = got
        return got

    recognizer.extract_hand_lines(
        arr,
        [dict(l) for l in raw_lines],
        raw_bytes=raw,
        read_region=read_region,
    )
    return {
        "page": page,
        "shape": list(arr.shape),
        "raw_lines": raw_lines,
        "regions": layout_filter.excluded_regions(arr),
        "reads": reads,
    }


def _dump(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=0, sort_keys=True, default=float)
        f.write("\n")


def cmd_capture(args):
    folder, meta = _load_set(args.set)
    _apply_settings(meta)
    server = _server()
    out = args.out or os.path.join(folder, "reader")
    os.makedirs(out, exist_ok=True)
    for page in _pages(folder):
        _dump(
            os.path.join(out, page + ".json"),
            read_page(server, folder, page, meta),
        )
        print(f"read {page}")
    return 0


def cmd_live(args):
    """Read every page again with the real models and compare the scores
    with expected.json, within LIVE_TOLERANCE."""
    folder, meta = _load_set(args.set)
    _apply_settings(meta)
    server = _server()
    with open(os.path.join(folder, "expected.json"), encoding="utf-8") as f:
        expected = json.load(f)
    rows, moved_reader = [], 0
    for page in _pages(folder):
        reader = read_page(server, folder, page, meta)
        if args.out:
            os.makedirs(args.out, exist_ok=True)
            _dump(os.path.join(args.out, page + ".json"), reader)
        with open(
            os.path.join(folder, "reader", page + ".json"), encoding="utf-8"
        ) as f:
            kept = json.load(f)
        if [l["text"] for l in reader["raw_lines"]] != [
            l["text"] for l in kept["raw_lines"]
        ]:
            moved_reader += 1
        raw, arr = _image(folder, page, meta)
        now = _score(arr, raw, reader, meta)
        old = expected["pages"][page]
        for n in ["overall"] + list(map(str, SCORED)):
            a = old["overall"] if n == "overall" else old["scores"][n]
            b = now["overall"] if n == "overall" else now["scores"][n]
            scale = 10.0 if n == "overall" else 1.0
            if (a is None) != (b is None) or (
                a is not None and abs(a - b) > LIVE_TOLERANCE * scale
            ):
                rows.append(f"| {page} | {n} | {_fmt(a)} | {_fmt(b)} |")
    _report(f"## Live reading of `{args.set}`\n")
    _report(
        f"The reader read {moved_reader} of {len(_pages(folder))} pages "
        "differently from the kept output."
    )
    if rows:
        _report(
            "\nScores that moved by more than the tolerance:\n\n"
            "| Page | Factor | Expected | Live |\n|---|---|---|---|\n"
            + "\n".join(rows)
        )
    else:
        _report("Every score is within tolerance of expected.json.")
    return 1 if rows else 0


def cmd_planted(args):
    """The planted-mistake pages (scripts/planted_pages.py, seed 0): how
    often each mistake is marked and how many false marks a clean page
    gets may not get worse without an update."""
    spec = importlib.util.spec_from_file_location(
        "planted_pages", os.path.join(ROOT, "scripts", "planted_pages.py")
    )
    planted = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(planted)
    path = os.path.join(SETS[0], "planted", "expected.json")
    tmp = os.path.join(SETS[0], "planted", ".last.json")
    with contextlib.redirect_stdout(io.StringIO()):
        planted.main(["--uji", args.uji, "--json", tmp])
    with open(tmp, encoding="utf-8") as f:
        result = json.load(f)
    os.remove(tmp)
    now = {
        kind: {
            "marked": row["marked"],
            "letter_marked": result["by_kind_letter_level"][kind]["marked"],
            "marks_per_page": row["marks_per_page"],
            "score_mean": row["score_mean"],
        }
        for kind, row in result["by_kind"].items()
    }
    if args.update:
        _dump(path, now)
        return 0
    with open(path, encoding="utf-8") as f:
        old = json.load(f)
    problems = []
    for kind, row in now.items():
        for key in ("marked", "letter_marked"):
            if row[key] < old[kind][key]:
                problems.append(
                    f"{kind}: {key} fell from {old[kind][key]} to {row[key]}"
                )
        if kind == "clean":
            for n, v in row["marks_per_page"].items():
                if v > old[kind]["marks_per_page"][n] + 0.1:
                    problems.append(
                        f"clean pages: false marks for {n} rose from "
                        f"{old[kind]['marks_per_page'][n]} to {v}"
                    )
    changed = now != old
    _report("## Planted mistakes\n")
    for p in problems:
        _report(f"- {p}")
    if changed and not problems:
        _report(
            "Numbers moved without getting worse; run `benchmark.py "
            "planted --update` to keep them."
        )
    if not changed:
        _report("Every rate matches benchmarks/planted/expected.json.")
    return 1 if (problems or changed) else 0


def cmd_factors(args):
    """Every factor against a mistake planted for it (scripts/
    factor_tests.py): how often each catches its mistake may not fall
    below benchmarks/factors/expected.json."""
    spec = importlib.util.spec_from_file_location(
        "factor_tests", os.path.join(ROOT, "scripts", "factor_tests.py")
    )
    ft = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ft)
    kinds = list(ft.TARGETS)
    with contextlib.redirect_stderr(io.StringIO()):
        rows = ft.run(args.uji, kinds, False)
    now = {
        kind: {n: t.get("caught") for n, t in v["targets"].items()}
        for kind, v in ft.summarise(rows).items()
    }
    path = os.path.join(SETS[0], "factors", "expected.json")
    if args.update:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _dump(path, now)
        return 0
    with open(path, encoding="utf-8") as f:
        old = json.load(f)
    problems, lines = [], []
    for kind, targets in sorted(now.items()):
        for n, caught in sorted(targets.items()):
            was = old.get(kind, {}).get(n)
            lines.append(f"| {kind} | {n} | {was} | {caught} |")
            if was is not None and (caught or 0) < was:
                problems.append(
                    f"{kind}: factor {n} caught {caught}, was {was}"
                )
    _report(
        "## Each factor against its planted mistake\n\n"
        "| Mistake | Factor | Expected | Now |\n|---|---|---|---|\n"
        + "\n".join(lines)
    )
    for p in problems:
        _report(f"- {p}")
    if not problems and now != old:
        _report("Rates moved without falling; `factors --update` keeps them.")
    return 1 if problems or now != old else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n", maxsplit=1)[0]
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "update", "capture", "live"):
        p = sub.add_parser(name)
        p.add_argument("--set", default="uji-clean")
        p.add_argument(
            "--root",
            help="a folder of sets outside the repository (default benchmarks/)",
        )
        if name in ("capture", "live"):
            p.add_argument("--out", help="write the reading here")
    for name in ("planted", "factors"):
        p = sub.add_parser(name)
        p.add_argument(
            "--uji",
            default=os.path.join(
                os.path.expanduser("~"), ".cache", "vahini", "ujipenchars2.txt"
            ),
        )
        p.add_argument("--update", action="store_true")
    args = ap.parse_args(argv)
    if getattr(args, "root", None):
        SETS[0] = os.path.abspath(args.root)
    return {
        "check": cmd_check,
        "update": cmd_update,
        "capture": cmd_capture,
        "live": cmd_live,
        "planted": cmd_planted,
        "factors": cmd_factors,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
