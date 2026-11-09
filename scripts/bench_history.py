# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""A history of main's benchmark numbers, and a slow-drift check (#254).

Each gate compares a pull request with main. A run of pull requests that
are each 3% slower passes every one of them and still doubles the time
in a month. This keeps one line per set for every push to main and
compares a pull request with the median of the last RECENT lines:

    python scripts/bench_history.py collect --set uji-clean \
        [--work <dir>] --out now.json
    python scripts/bench_history.py append --history <dir> now.json
    python scripts/bench_history.py check --history <dir> now.json

`collect` measures this checkout: the replay's CPU seconds (the median
of PASSES passes of scripts/paired_timing.py's worker) and its memory
peak (the largest resident size of those passes), and replays the set as
`benchmark.py check` does for the reading's character error rate, the
written lines scored, the mean overall score and the agreement with the
ranking by eye. It adds each planted mistake's
catch rate from benchmarks/factors/expected.json and, when given
`--work` (perf_budgets.py --results, #250), the page's total work count.

`check` fails when accuracy falls against the median of the last RECENT
main lines: the error rate up by more than CER_RISE points, fewer
written lines scored, the eye agreement down by more than EYE_DROP, or a
lower catch rate. A catch rate a pull request lowers on purpose is
named, with the pull request and the reason, in
benchmarks/factors/accepted.json: a fall no lower than the rate given
there is reported, not failed, until main's own lines carry it. Time,
memory and work up by more than CREEP are flagged in the summary and as
a warning, not failed: the lines come from different runners, whose
speeds differ by tens of percent, and the paired timing gate (#251)
already compares each pull request with main on one runner. Both
commands write the trend of every number over the last TREND lines to
the job summary.

Lines are kept on the `bench-history` branch as history/<set>.jsonl,
numbers only. Standard library only, apart from what the replay imports.
"""

# pylint: disable=protected-access

import argparse
import datetime
import importlib.util
import json
import os
import resource
import statistics
import subprocess
import sys
import tempfile

HERE = os.path.abspath(__file__)
ROOT = os.path.dirname(os.path.dirname(HERE))
RECENT = 10
TREND = 50
PASSES = 3
CREEP = 0.15
CER_RISE = 0.2
EYE_DROP = 0.05
BARS = "▁▂▃▄▅▆▇█"
# (key, label, higher is better)
TRACKED = (
    ("cpu_s", "replay CPU s", False),
    ("peak_mib", "replay memory MiB", False),
    ("work_total", "work counts", False),
    ("cer", "reading error %", False),
    ("sentences_found", "lines scored", True),
    ("overall_mean", "mean overall", None),
    ("eye", "eye agreement", True),
)


def _module(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, "scripts", name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def measure(name, passes=PASSES):
    """(median CPU seconds, peak MiB) of the replay of one set, each
    pass in a fresh process, as paired_timing.py's worker runs it."""
    totals = []
    worker = os.path.join(ROOT, "scripts", "paired_timing.py")
    env = dict(os.environ)
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        env[key] = "1"
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(passes):
            out = os.path.join(tmp, f"{i}.json")
            cmd = [sys.executable, worker, "worker", "--checkout", ROOT]
            cmd += ["--out", out, "--set", name]
            subprocess.run(cmd, check=True, cwd=ROOT, env=env)
            totals.append(_load(out)["total"])
    # ru_maxrss of the largest child so far, in KiB on Linux.
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
    return round(statistics.median(totals), 2), round(peak, 1)


def scored(name, pages=None):
    """Error rate, lines scored, mean overall and eye agreement of the
    set's pages: replayed as `benchmark.py check` does, unless given."""
    bench = _module("benchmark")
    if pages is None:
        meta, pages, _problems = bench.run_set(name)
    else:
        _folder, meta = bench._load_set(name)
    out = {
        "sentences_found": sum(p["sentences_found"] for p in pages.values()),
        "overall_mean": round(
            statistics.mean(p["overall"] for p in pages.values()), 2
        ),
        "eye": bench.eye_agreement(meta, pages),
        "cer": None,
    }
    if not bench._ink_mode(meta):
        out["cer"] = bench.reading(meta, pages)["cer"]
    return out


def catch_rates(path=None):
    """Each planted mistake's catch rate, as "mistake/factor": rate."""
    path = path or os.path.join(ROOT, "benchmarks", "factors", "expected.json")
    if not os.path.exists(path):
        return {}
    rates = {}
    for kind, factors in _load(path).items():
        for n, rate in factors.items():
            if rate is not None:
                rates[f"{kind}/{n}"] = rate
    return dict(sorted(rates.items()))


def accepted_falls(path=None):
    """Catch rates lowered on purpose, as "mistake/factor": {"rate", "pr",
    "why"}: the lowest rate each may fall to (benchmarks/factors/
    accepted.json, edited by hand in the pull request that lowers it)."""
    path = path or os.path.join(ROOT, "benchmarks", "factors", "accepted.json")
    if not os.path.exists(path):
        return {}
    return _load(path)


def work_total(name, work):
    path = os.path.join(work, name, "work.json") if work else ""
    if not path or not os.path.exists(path):
        return None
    return sum(sum(page.values()) for page in _load(path).values())


def _git(*args):
    try:
        return subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def collect(name, work=None, cpu=None, pages=None):
    """One history line for the set at this checkout."""
    if cpu is None:
        cpu = measure(name)
    line = {
        "set": name,
        "sha": os.environ.get("GITHUB_SHA") or _git("rev-parse", "HEAD"),
        "date": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "cpu_s": cpu[0],
        "peak_mib": cpu[1],
        "work_total": work_total(name, work),
        "catch": catch_rates(),
    }
    line.update(scored(name, pages))
    return line


def history(folder, name):
    path = os.path.join(folder, "history", f"{name}.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(row) for row in f if row.strip()]


def append(folder, line):
    path = os.path.join(folder, "history", f"{line['set']}.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")


def _median(past, key):
    values = [p[key] for p in past if p.get(key) is not None]
    return statistics.median(values) if values else None


def compare(now, past, accepted=None):
    """(failures, flags) of a line against the median of past lines;
    accepted: accepted_falls()."""
    fails, flags = [], []
    past = past[-RECENT:]
    if not past:
        return fails, flags
    for key, label, _better in TRACKED[:3]:
        old = _median(past, key)
        new = now.get(key)
        if old and new is not None and new > old * (1 + CREEP):
            flags.append(
                f"{label} {new} is {(new / old - 1) * 100:.0f}% above the "
                f"median of the last {len(past)} main runs ({old})"
            )
    old, new = _median(past, "cer"), now.get("cer")
    if old is not None and new is not None and new > old + CER_RISE:
        fails.append(f"reading error rose to {new}% from a median {old}%")
    old, new = _median(past, "sentences_found"), now.get("sentences_found")
    if old is not None and new is not None and new < old:
        fails.append(f"written lines scored fell to {new} from {old}")
    old, new = _median(past, "eye"), now.get("eye")
    if old is not None and new is not None and new < old - EYE_DROP:
        fails.append(f"agreement with the eye fell to {new} from {old}")
    for key, rate in (now.get("catch") or {}).items():
        values = [p["catch"][key] for p in past if key in p.get("catch", {})]
        if not values or rate >= statistics.median(values):
            continue
        text = (
            f"{key} caught on {rate} of writers, median "
            f"{statistics.median(values)}"
        )
        ok = (accepted or {}).get(key)
        if ok and rate >= ok["rate"]:
            flags.append(f"{text}: accepted in #{ok['pr']}, {ok['why']}")
        else:
            fails.append(text)
    return fails, flags


def spark(values):
    """A row of bars, lowest to highest, for the numbers given."""
    nums = [v for v in values if v is not None]
    if not nums:
        return ""
    lo, hi = min(nums), max(nums)
    out = []
    for v in values:
        if v is None:
            out.append(" ")
        elif hi == lo:
            out.append(BARS[0])
        else:
            out.append(BARS[round((v - lo) / (hi - lo) * (len(BARS) - 1))])
    return "".join(out)


def trend(lines, now=None):
    """Markdown: every tracked number over the last TREND lines."""
    rows = lines[-TREND:] + ([now] if now else [])
    if not rows:
        return "No history yet: the first push to main starts it."
    out = [
        f"| Number | Last {len(rows)} runs, oldest first | Latest |",
        "|---|---|---|",
    ]
    for key, label, _better in TRACKED:
        values = [r.get(key) for r in rows]
        if all(v is None for v in values):
            continue
        out.append(f"| {label} | `{spark(values)}` | {values[-1]} |")
    return "\n".join(out)


def _report(text):
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n", maxsplit=1)[0]
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--set", default="uji-clean")
    c.add_argument("--work", help="perf_budgets.py --results folder")
    c.add_argument("--out", required=True)
    for name in ("append", "check"):
        p = sub.add_parser(name)
        p.add_argument("--history", required=True)
        p.add_argument("line")
    args = ap.parse_args(argv)
    if args.cmd == "collect":
        line = collect(args.set, args.work)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(line, f, sort_keys=True)
        return 0
    line = _load(args.line)
    past = history(args.history, line["set"])
    if args.cmd == "append":
        append(args.history, line)
        _report(f"## History of main, `{line['set']}`\n")
        _report(trend(past, line))
        return 0
    fails, flags = compare(line, past, accepted_falls())
    _report(f"## Against the last {RECENT} main runs, `{line['set']}`\n")
    _report(trend(past, line))
    for text in fails:
        _report(f"- **{text}**")
    for text in flags:
        _report(f"- {text} (flagged, not failed)")
        print(f"::warning::{text}")
    if past and not fails and not flags:
        _report(
            f"\nWithin the last {min(len(past), RECENT)} main runs on every "
            "number."
        )
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
