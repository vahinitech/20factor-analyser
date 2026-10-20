# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Every benchmark page within its budgets (#229).

Replays each page of a benchmark set through the server's own scan, the
body of /report-python (_report_python_process), from the reader's kept
output as scripts/benchmark.py does, with backend/perf.py recording.
Then it builds the Pro report (the practice stage) and checks the page
against every budget in backend/perf/budgets.json:

    python scripts/perf_budgets.py check [--set uji-clean]

It prints each stage's CPU time over the pages (the most any page took,
and the cap) to stdout and to the job summary, and exits 1 when a page
broke a budget or was not scored. A stage's cap is set from this table:
five times the slowest page on GitHub's runners, at least 100 ms, so a
stage that becomes several times slower fails while runner noise does
not. Scores are not checked here; the benchmark job checks them.
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


def check(name, limit=None):
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
    cpu, wall, problems = {}, {}, []
    for page in pages:
        summary, scored = _replay(server, folder, page, meta)
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
    return out, len(problems)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["check"])
    parser.add_argument("--set", default="uji-clean")
    args = parser.parse_args(argv)
    lines, failed = check(args.set)
    text = "\n".join(lines) + "\n"
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
