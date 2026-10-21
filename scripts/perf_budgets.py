# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Every benchmark page within its budgets (#229).

Replays each page of a benchmark set through the server's own scan, the
body of /report-python (_report_python_process), from the reader's kept
output as scripts/benchmark.py does, with backend/perf.py recording.
Then it builds the Pro report (the practice stage) and checks the page
against every budget in backend/perf/budgets.json:

    python scripts/perf_budgets.py check [--set uji-clean] [--results d]
    python scripts/perf_budgets.py update-work [--set uji-clean]

It prints each stage's CPU time over the pages (the most any page took,
and the cap) to stdout and to the job summary, and exits 1 when a page
broke a budget or was not scored. A stage's cap is set from this table:
five times the slowest page on GitHub's runners, at least 100 ms, so a
stage that becomes several times slower fails while runner noise does
not. Scores are not checked here; the benchmark job checks them.

It also counts each page's work (#250): every stage's runs, sizes and
call counts (reader calls, model calls, pixels decoded, lines and words
measured). Unlike time these are the same on every run of the same code,
so `check` compares them with benchmarks/<set>/work.json and fails when
any count on any page rises. A fall passes and asks for an update.
`update-work` writes work.json; `--results` writes the counts this run
found to <d>/<set>/work.json, so CI can hand them back.
"""

# Scripts here print their results; the analyser modules are imported
# from backend/ after the set's settings are in the environment.
# pylint: disable=import-outside-toplevel,protected-access

import argparse
import importlib.util
import json
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import benchmark  # pylint: disable=wrong-import-position

CAP_FACTOR = 5
CAP_FLOOR_MS = 100


def _load_server():
    path = os.path.join(benchmark.BACKEND, "ppocr-server.py")
    spec = importlib.util.spec_from_file_location("ppocr_server_perf", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _replay(server, folder, page, meta):
    """(stage summary, scored) for one page through the server's scan,
    the reader's kept output in place of the models."""
    with open(
        os.path.join(folder, "reader", page + ".json"), encoding="utf-8"
    ) as f:
        reader = json.load(f)
    with open(os.path.join(folder, "pages", page + ".jpg"), "rb") as f:
        raw = f.read()
    reads, regions = reader["reads"], reader["regions"]
    backend = meta["settings"]["VAHINI_OCR_BACKEND"]

    def read_region(crop, _lang):
        key = benchmark._crop_key(crop)
        if key not in reads:
            raise benchmark.MissingRead(key)
        return reads[key]

    def collect_lines(_arr, _lang):
        return [dict(l) for l in reader["raw_lines"]], "", backend, {}

    # recognizer and layout_filter are shared modules: put the real
    # functions back after the page, so nothing else runs on the stubs.
    stubs = (
        (server.recognizer, "collect_lines", collect_lines),
        (server.layout_filter, "excluded_regions", lambda _a: regions),
        (server, "_READ_REGION", read_region),
    )
    real = [(owner, name, getattr(owner, name)) for owner, name, _ in stubs]
    for owner, name, stub in stubs:
        setattr(owner, name, stub)
    try:
        return _scan(server, raw, page, meta)
    finally:
        for owner, name, value in real:
            setattr(owner, name, value)


def _scan(server, raw, page, meta):
    """Decode, the /report-python body with the page's written text as
    the passage, and the Pro report, inside one perf scan."""
    written = meta.get("page_text", {}).get(page, meta.get("sentences"))
    pro = {
        **server.entitlements.access_for(None),
        "tier": "pro",
        "plan_tier": "pro",
    }
    perf = server.perf
    with perf.scan() as record:
        arr = server._to_numpy(raw)
        payload = server._report_python_process(
            arr,
            raw,
            meta.get("lang", "auto"),
            "\n".join(written or []),
            True,
            server.profiles.resolve(),
        )
        scored = bool(payload.get("ok"))
        if scored:
            with perf.stage("practice"):
                server.report_contract.public_report(payload, pro)
    return record.summary(), scored


def _cap(slowest_ms):
    step = 50
    return max(
        CAP_FLOOR_MS, int(math.ceil(CAP_FACTOR * slowest_ms / step)) * step
    )


def work(summary):
    """One page's work from its stage summary, as flat counts: each
    stage's runs, its sizes and its call counts."""
    out = {}
    for stage, row in summary.items():
        out[f"{stage}.runs"] = row["runs"]
        for part in ("sizes", "counts"):
            for key, value in row[part].items():
                out[f"{stage}.{key}"] = value
    return dict(sorted(out.items()))


def work_changes(now, kept):
    """(rises, falls): markdown rows for every count that moved against
    work.json, page by page. A count a page did not have is 0."""
    rises, falls = [], []
    for page in sorted(set(now) | set(kept)):
        new, old = now.get(page, {}), kept.get(page, {})
        for key in sorted(set(new) | set(old)):
            a, b = old.get(key, 0), new.get(key, 0)
            if b > a:
                rises.append(f"| {page} | {key} | {a} | {b} |")
            elif b < a:
                falls.append(f"| {page} | {key} | {a} | {b} |")
    return rises, falls


def _work_path(folder):
    return os.path.join(folder, "work.json")


def _write_work(path, pages):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pages, f, indent=1, sort_keys=True)
        f.write("\n")


def work_report(folder, pages):
    """Markdown lines comparing the run's counts with work.json, and
    whether any count rose."""
    path = _work_path(folder)
    if not os.path.exists(path):
        return [
            "No work.json for this set yet; `perf_budgets.py update-work` "
            "writes one.",
            "",
        ], False
    with open(path, encoding="utf-8") as f:
        kept = json.load(f)
    rises, falls = work_changes(pages, kept)
    head = ["| Page | Count | work.json | Now |", "|---|---|---|---|"]
    out = []
    if rises:
        out += [
            f"**{len(rises)} work count(s) rose.** Each is an extra call, "
            "rung or pass on a page. If it is meant, run `perf_budgets.py "
            "update-work`, commit work.json and say why in the pull request.",
            "",
            *head,
            *rises,
            "",
        ]
    if falls:
        out += [
            f"{len(falls)} work count(s) fell; run `perf_budgets.py "
            "update-work` to keep the lower numbers.",
            "",
            *head,
            *falls,
            "",
        ]
    if not rises and not falls:
        out += ["Every page's work matches work.json.", ""]
    return out, bool(rises)


def check(name, limit=None, results=None):
    """Replay every page of the set (the first `limit` pages, when
    given); returns (markdown lines, number of problems)."""
    folder, meta = benchmark._load_set(name)
    if benchmark._ink_mode(meta):
        return [f"{name}: measured from the ink, no kept reading; skipped"], 0
    benchmark._apply_settings(meta)
    os.environ.setdefault("VAHINI_OCR_PRELOAD_ON_START", "0")
    server = _load_server()
    perf = server.perf
    pages = benchmark._pages(folder)[:limit]
    # The first scan in a process pays for imports and tables read once;
    # it is replayed once before anything is measured.
    _replay(server, folder, pages[0], meta)
    cpu, wall, problems, counted = {}, {}, [], {}
    for page in pages:
        summary, scored = _replay(server, folder, page, meta)
        counted[page] = work(summary)
        if not scored:
            problems.append(f"| {page} | not scored | | | |")
        for item in perf.breaches(summary):
            problems.append(
                f"| {page} | {item['budget']} | {item['stage']} "
                f"| {item['value']} | {item['limit']} |"
            )
        for stage, row in summary.items():
            cpu.setdefault(stage, []).append(row["cpu_ms"])
            wall.setdefault(stage, []).append(row["wall_ms"])
    caps = perf.BUDGETS["cpu_ms"]
    out = [
        f"### Stage budgets, {name} ({len(pages)} pages)",
        "",
        "| Stage | Median CPU ms | Slowest CPU ms | Slowest wall ms "
        "| Cap | 5x slowest |",
        "|---|---|---|---|---|---|",
    ]
    for stage, values in cpu.items():
        out.append(
            f"| {stage} | {statistics.median(values):.1f} "
            f"| {max(values):.1f} | {max(wall[stage]):.1f} "
            f"| {caps.get(stage, 'none')} | {_cap(max(values))} |"
        )
    out += ["", f"{len(problems)} page budget(s) broken.", ""]
    if problems:
        out += [
            "| Page | Budget | Stage | Value | Limit |",
            "|---|---|---|---|---|",
            *problems,
        ]
    if results:
        _write_work(os.path.join(results, name, "work.json"), counted)
    if limit is None:
        lines, rose = work_report(folder, counted)
        out += ["", f"### Work per page, {name}", "", *lines]
        return out, len(problems) + int(rose)
    return out, len(problems)


def update_work(name):
    """Replay the set and write its work.json."""
    folder, meta = benchmark._load_set(name)
    benchmark._apply_settings(meta)
    os.environ.setdefault("VAHINI_OCR_PRELOAD_ON_START", "0")
    server = _load_server()
    pages = benchmark._pages(folder)
    _replay(server, folder, pages[0], meta)
    counted = {}
    for page in pages:
        summary, _scored = _replay(server, folder, page, meta)
        counted[page] = work(summary)
    _write_work(_work_path(folder), counted)
    return [f"Wrote {_work_path(folder)} ({len(pages)} pages)."], 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["check", "update-work"])
    parser.add_argument("--set", default="uji-clean")
    parser.add_argument(
        "--results", help="also write this run's counts to <dir>/<set>/"
    )
    args = parser.parse_args(argv)
    if args.command == "update-work":
        lines, failed = update_work(args.set)
    else:
        lines, failed = check(args.set, results=args.results)
    text = "\n".join(lines) + "\n"
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
