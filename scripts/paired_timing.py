# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Paired timing: is this pull request's code slower than main's? (#251)

    python scripts/paired_timing.py --main <main checkout> \
        --pr <PR checkout> [--rounds 7] [--set uji-clean ...] [--json out]

GitHub's shared runners give the same code different times from one run
to the next, often by tens of percent, so a limit in seconds either fails
at random or catches nothing. This compares like with like: main's code
and the PR's code on the same runner in the same job. Each round replays
every benchmark page once with each checkout (Layer A, the kept reader
output, no models), each in a fresh process, and the two take turns going
first. The runner's speed cancels out of the ratio.

It records CPU time (time.process_time) per page and per step: decoding
the photo, finding the hand lines from the kept reading, the layout pass
and scoring. A step's time leaves out any other step it calls.

It fails when the PR's median total over the rounds is more than LIMIT
above main's, and the PR was slower than main in each of the last AGREE
rounds too, so one slow minute on the runner is not enough. The job
summary gets a table per step: main, PR and the ratio.

Measuring never decides anything in the analyser: this only reads the
clock around the same calls `benchmark.py check` makes. Standard library
only, apart from what the replay imports. docs/18-benchmark.md says how
to read it.
"""

# The analyser modules are imported from the checkout under test after
# the set's settings are in the environment, as benchmark.py does.
# pylint: disable=import-outside-toplevel,protected-access

import argparse
import importlib
import importlib.util
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time

HERE = os.path.abspath(__file__)
ROOT = os.path.dirname(os.path.dirname(HERE))
ROUNDS = 7
# The PR fails when its median total is more than this share above main's.
LIMIT = 0.10
# ...and it was slower than main in each of this many last rounds.
AGREE = 3
# The steps timed, as (name, module, function). Each is looked up on its
# module when called, as the replay calls it, so wrapping it there counts
# every call the replay makes.
STEPS = (
    ("decode", "computer_vision", "to_numpy"),
    ("hand lines", "recognizer", "extract_hand_lines"),
    ("ink rows", "ink_geometry", "find_rows"),
    ("layout", "computer_vision", "vl_analyze"),
    ("scoring", "scoring", "build_analysis"),
)
OTHER = "other"
# One thread for the maths libraries on both sides: idle threads spinning
# while they wait add CPU time that says nothing about the code.
THREADS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")


class Clock:
    """CPU time per step. A step's own time leaves out the time of any
    other timed step it calls, so the steps add up to no more than the
    page."""

    def __init__(self):
        self.spent = {}
        self._inner = []

    def wrap(self, name, fn):
        """fn, timed under name."""

        def timed(*args, **kwargs):
            start = time.process_time()
            self._inner.append(0.0)
            try:
                return fn(*args, **kwargs)
            finally:
                took = time.process_time() - start
                inner = self._inner.pop()
                self.spent[name] = self.spent.get(name, 0.0) + took - inner
                if self._inner:
                    self._inner[-1] += took

        timed.__wrapped__ = fn
        return timed


def _bench(checkout):
    """The checkout's own scripts/benchmark.py, which puts that
    checkout's backend/ on the import path."""
    spec = importlib.util.spec_from_file_location(
        "benchmark", os.path.join(checkout, "scripts", "benchmark.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wrap_steps(clock):
    for name, module_name, func in STEPS:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        if hasattr(module, func):
            setattr(module, func, clock.wrap(name, getattr(module, func)))


def _page_runner(bench, folder, meta, page):
    """A function that replays one page as `benchmark.py check` does,
    with the kept reading already loaded so reading the file is not
    timed. None when the page cannot be replayed."""
    if bench._ink_mode(meta):
        return lambda: bench._score_ink(
            bench._image(folder, page, meta)[1], page, meta
        )
    with open(
        os.path.join(folder, "reader", page + ".json"), encoding="utf-8"
    ) as f:
        reader = json.load(f)

    def run():
        raw, arr = bench._image(folder, page, meta)
        return bench._score(arr, raw, reader, meta)

    return run


def worker(checkout, sets):
    """One pass over every page of the sets with the checkout's code:
    CPU seconds per page and per step."""
    bench = _bench(checkout)
    plan = []
    for name in sets:
        folder, meta = bench._load_set(name)
        bench._apply_settings(meta)
        plan += [(name, folder, meta, p) for p in bench._pages(folder)]
    # Import the analyser before the clock starts, as the server has it
    # loaded before any scan.
    for module in ("computer_vision", "recognizer", "scoring"):
        importlib.import_module(module)
    clock = Clock()
    _wrap_steps(clock)
    pages, skipped = {}, []
    for index, (name, folder, meta, page) in enumerate(plan):
        bench._apply_settings(meta)
        run = _page_runner(bench, folder, meta, page)
        if index == 0:
            # One untimed page first: the libraries' own first-call setup
            # belongs to no page.
            try:
                run()
            except bench.MissingRead:
                pass
            clock.spent.clear()
        start = time.process_time()
        try:
            run()
        except bench.MissingRead:
            # The benchmark job reports it; there is nothing to time.
            skipped.append(f"{name}/{page}")
            continue
        pages[f"{name}/{page}"] = time.process_time() - start
    total = sum(pages.values())
    steps = dict(clock.spent)
    steps[OTHER] = max(0.0, total - sum(steps.values()))
    return {"total": total, "pages": pages, "steps": steps, "skip": skipped}


def _run_worker(checkout, sets):
    """worker() in a fresh process, so the two sides never share
    imported modules."""
    env = dict(os.environ)
    for key in THREADS:
        env[key] = "1"
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "times.json")
        cmd = [sys.executable, HERE, "worker", "--checkout", checkout]
        cmd += ["--out", out] + [x for s in sets for x in ("--set", s)]
        subprocess.run(cmd, check=True, env=env, cwd=checkout)
        with open(out, encoding="utf-8") as f:
            return json.load(f)


def rounds(main_dir, pr_dir, count, sets, run=None):
    """count rounds, each timing main and the PR once; who goes first
    alternates. Pages either side skipped are left out of both."""
    run = run or _run_worker
    history = []
    for i in range(count):
        order = [("main", main_dir), ("pr", pr_dir)]
        if i % 2:
            order.reverse()
        got = {side: run(path, sets) for side, path in order}
        common = set(got["main"]["pages"]) & set(got["pr"]["pages"])
        for side in got.values():
            side["pages"] = {p: side["pages"][p] for p in sorted(common)}
            side["total"] = sum(side["pages"].values())
        history.append(got)
        print(
            f"round {i + 1}: main {got['main']['total']:.2f} s, "
            f"PR {got['pr']['total']:.2f} s",
            flush=True,
        )
    return history


def _median(history, side, pick):
    return statistics.median(pick(r[side]) for r in history)


def verdict(history, limit=LIMIT, agree=AGREE):
    """(failed, median ratio of PR to main, ratio in each round)."""
    each = [
        r["pr"]["total"] / r["main"]["total"] if r["main"]["total"] else 1.0
        for r in history
    ]
    main = _median(history, "main", lambda s: s["total"])
    ratio = _median(history, "pr", lambda s: s["total"]) / main if main else 1
    last = each[-agree:]
    failed = (
        ratio > 1 + limit and len(last) == agree and all(x > 1.0 for x in last)
    )
    return failed, ratio, each


def _ratio(new, old):
    return f"{new / old:.2f}" if old else "n/a"


def table(history, limit=LIMIT, agree=AGREE):
    """The job summary, as markdown."""
    failed, ratio, each = verdict(history, limit, agree)
    names = [s[0] for s in STEPS] + [OTHER]
    seen = set()
    for r in history:
        for side in r.values():
            seen |= set(side["steps"])
    out = [
        "## Paired timing against main\n",
        f"{len(history)} rounds, each replaying "
        f"{len(history[0]['pr']['pages'])} pages once with main's code "
        "and once with this PR's, on this runner. Median CPU seconds.\n",
        "| Step | main | PR | PR / main |",
        "|---|---|---|---|",
    ]
    for name in names:
        if name not in seen:
            continue
        old = _median(history, "main", lambda s, n=name: s["steps"].get(n, 0))
        new = _median(history, "pr", lambda s, n=name: s["steps"].get(n, 0))
        out.append(f"| {name} | {old:.2f} | {new:.2f} | {_ratio(new, old)} |")
    old = _median(history, "main", lambda s: s["total"])
    new = _median(history, "pr", lambda s: s["total"])
    out.append(f"| **total** | {old:.2f} | {new:.2f} | **{ratio:.2f}** |")
    out.append(
        "\nPR / main by round: " + ", ".join(f"{x:.2f}" for x in each) + "."
    )
    if failed:
        out.append(
            f"\n**Slower than main**: the median total is "
            f"{(ratio - 1) * 100:.0f}% above main's (limit "
            f"{limit * 100:.0f}%) and each of the last {agree} rounds was "
            "slower. The steps above show where."
        )
    elif ratio > 1 + limit:
        out.append(
            f"\nThe median total is {(ratio - 1) * 100:.0f}% above main's, "
            f"but the last {agree} rounds do not all agree, so this is "
            "taken as the runner, not the code."
        )
    else:
        out.append(f"\nWithin {limit * 100:.0f}% of main.")
    pages = sorted(history[0]["pr"]["pages"])
    out += [
        "\n<details><summary>Per page</summary>\n",
        "| Page | main | PR | PR / main |",
        "|---|---|---|---|",
    ]
    for page in pages:
        old = _median(history, "main", lambda s, p=page: s["pages"][p])
        new = _median(history, "pr", lambda s, p=page: s["pages"][p])
        out.append(f"| {page} | {old:.3f} | {new:.3f} | {_ratio(new, old)} |")
    out.append("\n</details>")
    return failed, "\n".join(out)


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
    sub = ap.add_subparsers(dest="cmd")
    w = sub.add_parser("worker", help="one timed pass (used internally)")
    w.add_argument("--checkout", required=True)
    w.add_argument("--out", required=True)
    w.add_argument("--set", action="append", dest="sets")
    ap.add_argument("--main", help="a checkout of main")
    ap.add_argument("--pr", help="a checkout of the pull request")
    ap.add_argument("--rounds", type=int, default=ROUNDS)
    ap.add_argument("--set", action="append", dest="sets")
    ap.add_argument("--json", help="write every round's times here")
    args = ap.parse_args(argv)
    sets = args.sets or ["uji-clean"]
    if args.cmd == "worker":
        result = worker(os.path.abspath(args.checkout), sets)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f)
        return 0
    if not args.main or not args.pr:
        ap.error("--main and --pr are required")
    history = rounds(
        os.path.abspath(args.main), os.path.abspath(args.pr), args.rounds, sets
    )
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=1)
    failed, text = table(history)
    _report(text)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
