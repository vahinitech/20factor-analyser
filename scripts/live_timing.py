# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Live reader speed and memory against main (#252).

Inside an analyser container, once per side:

    python live_timing.py run --checkout /repo --set uji-clean --out t.json

On the runner, after every side has run:

    python scripts/live_timing.py compare --main m1.json m2.json \
        --pr p1.json p2.json [--report-only]

`run` reads every page of a benchmark set with the real models and
scores it, as `benchmark.py live` does, with the checkout's own code. It
records each page's wall time and the container's memory peak after it
(cgroup v2 memory.peak, the number the container's memory limit is held
to). One page is read first and not timed, so loading the models is not
charged to a page.

`compare` takes each page's fastest time over the passes given for a
side, since a slow moment on a shared runner only ever adds time, and the
highest memory peak. It fails when the pull request's 95th percentile
page time is more than TIME_LIMIT above main's, its memory peak more than
MEMORY_LIMIT above main's, or any page passes the production limit of
2500 MiB. With --report-only it writes the same table and never fails:
the weekly run compares main with its own last weekly run.

Measuring never decides anything in the analyser. Standard library only,
apart from what the reading imports.
"""

# The analyser modules are imported from the checkout under test after
# the set's settings are in the environment, as benchmark.py does.
# pylint: disable=protected-access

import argparse
import importlib.util
import json
import math
import os
import resource
import sys
import time

TIME_LIMIT = 0.15
MEMORY_LIMIT = 0.10
# The analyser container's limit in production (docker-compose on the
# host, docs/13-api-and-capacity.md): 2500m, no swap.
PRODUCTION_BYTES = 2500 * 1024 * 1024
MIB = 1024 * 1024
CGROUP = "/sys/fs/cgroup"


def _bench(checkout):
    """The checkout's own scripts/benchmark.py, which puts that
    checkout's backend/ on the import path."""
    spec = importlib.util.spec_from_file_location(
        "benchmark", os.path.join(checkout, "scripts", "benchmark.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def memory_peak(root=CGROUP):
    """The container's memory peak in bytes: cgroup v2 memory.peak, or
    this process's own peak where the kernel has no such file."""
    try:
        with open(os.path.join(root, "memory.peak"), encoding="ascii") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


def memory_limit(root=CGROUP):
    """The container's memory limit in bytes, None when there is none."""
    try:
        with open(os.path.join(root, "memory.max"), encoding="ascii") as f:
            text = f.read().strip()
    except OSError:
        return None
    return None if text == "max" else int(text)


def run(checkout, name):
    """Every page of the set read and scored with the checkout's code:
    wall seconds and the memory peak after each page."""
    bench = _bench(checkout)
    folder, meta = bench._load_set(name)
    bench._apply_settings(meta)
    server = bench._server()
    pages = bench._pages(folder)

    def scan(page):
        reader = bench.read_page(server, folder, page, meta)
        raw, arr = bench._image(folder, page, meta)
        bench._score(arr, raw, reader, meta)

    scan(pages[0])
    out = {}
    for page in pages:
        start = time.perf_counter()
        scan(page)
        out[page] = {
            "seconds": round(time.perf_counter() - start, 3),
            "peak_bytes": memory_peak(),
        }
        print(f"{page}: {out[page]['seconds']} s", flush=True)
    return {"set": name, "limit_bytes": memory_limit(), "pages": out}


def p95(values):
    """The 95th percentile, nearest rank."""
    ordered = sorted(values)
    if not ordered:
        return None
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def combine(passes):
    """One side from its passes: each page's fastest time and highest
    memory peak. Only pages every pass read are kept."""
    common = set.intersection(*(set(p["pages"]) for p in passes))
    pages = {}
    for page in sorted(common):
        pages[page] = {
            "seconds": min(p["pages"][page]["seconds"] for p in passes),
            "peak_bytes": max(p["pages"][page]["peak_bytes"] for p in passes),
        }
    return pages


def verdict(main, pr):
    """The problems that fail a pull request, from combined sides."""
    problems = []
    shared = sorted(set(main) & set(pr))
    old = p95([main[p]["seconds"] for p in shared])
    new = p95([pr[p]["seconds"] for p in shared])
    if old and new > old * (1 + TIME_LIMIT):
        problems.append(
            f"95th percentile page time {new:.2f} s is "
            f"{(new / old - 1) * 100:.0f}% above main's {old:.2f} s "
            f"(limit {TIME_LIMIT * 100:.0f}%)"
        )
    old = max((main[p]["peak_bytes"] for p in shared), default=0)
    new = max((pr[p]["peak_bytes"] for p in shared), default=0)
    if old and new > old * (1 + MEMORY_LIMIT):
        problems.append(
            f"memory peak {new / MIB:.0f} MiB is "
            f"{(new / old - 1) * 100:.0f}% above main's {old / MIB:.0f} MiB "
            f"(limit {MEMORY_LIMIT * 100:.0f}%)"
        )
    for page in sorted(pr):
        if pr[page]["peak_bytes"] > PRODUCTION_BYTES:
            problems.append(
                f"{page}: memory peak {pr[page]['peak_bytes'] / MIB:.0f} "
                f"MiB is over the production limit of "
                f"{PRODUCTION_BYTES / MIB:.0f} MiB"
            )
    return problems


def _ratio(new, old):
    return f"{new / old:.2f}" if old else "n/a"


def table(main, pr, base="main"):
    """Markdown: p95 time and memory peak, then every page."""
    shared = sorted(set(main) & set(pr))
    old_t = p95([main[p]["seconds"] for p in shared]) or 0
    new_t = p95([pr[p]["seconds"] for p in shared]) or 0
    old_m = max((main[p]["peak_bytes"] for p in shared), default=0)
    new_m = max((pr[p]["peak_bytes"] for p in shared), default=0)
    out = [
        f"| | {base} | this run | ratio |",
        "|---|---|---|---|",
        f"| p95 page time (s) | {old_t:.2f} | {new_t:.2f} "
        f"| {_ratio(new_t, old_t)} |",
        f"| memory peak (MiB) | {old_m / MIB:.0f} | {new_m / MIB:.0f} "
        f"| {_ratio(new_m, old_m)} |",
        "",
        f"| Page | {base} s | this run s | {base} MiB | this run MiB |",
        "|---|---|---|---|---|",
    ]
    for page in shared:
        a, b = main[page], pr[page]
        out.append(
            f"| {page} | {a['seconds']:.2f} | {b['seconds']:.2f} "
            f"| {a['peak_bytes'] / MIB:.0f} | {b['peak_bytes'] / MIB:.0f} |"
        )
    return "\n".join(out)


def _load(paths):
    passes = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            passes.append(json.load(f))
    return passes


def _report(text):
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def compare(main_paths, pr_paths, report_only=False, base="main"):
    """The job summary; returns the exit code."""
    main = combine(_load(main_paths))
    pr = combine(_load(pr_paths))
    problems = verdict(main, pr)
    _report(f"## Live reader speed and memory against {base}\n")
    _report(
        "Each page read and scored with the real models in the analyser "
        f"container, held to {PRODUCTION_BYTES / MIB:.0f} MiB with no "
        f"swap. Time is each page's fastest of {len(pr_paths)} pass(es); "
        "memory is the container's peak after the page.\n"
    )
    _report(table(main, pr, base))
    for p in problems:
        _report(f"- {p}")
    if not problems:
        _report(
            f"\nWithin {TIME_LIMIT * 100:.0f}% on time and "
            f"{MEMORY_LIMIT * 100:.0f}% on memory."
        )
    return 0 if report_only or not problems else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n", maxsplit=1)[0]
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--checkout", required=True)
    r.add_argument("--set", default="uji-clean")
    r.add_argument("--out", required=True)
    c = sub.add_parser("compare")
    c.add_argument("--main", nargs="+", required=True)
    c.add_argument("--pr", nargs="+", required=True)
    c.add_argument("--report-only", action="store_true")
    c.add_argument("--base", default="main", help="what --main is")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        result = run(os.path.abspath(args.checkout), args.set)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
        return 0
    return compare(args.main, args.pr, args.report_only, args.base)


if __name__ == "__main__":
    sys.exit(main())
