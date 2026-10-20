# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Where the benchmark replay spends its time and memory (#231).

    python scripts/profile_benchmark.py --out profile-out \
        [--set uji-clean ...] [--baseline old/profile.json]

Replays the benchmark pages exactly as `benchmark.py check` does (Layer A:
the kept reader output through the scoring path, no models), twice: once
under cProfile and once under tracemalloc. It writes to --out:

    profile.prof   the raw cProfile data (open with pstats or snakeviz)
    profile.json   both tables as data, the next run's baseline
    profile.md     both tables as markdown, for the job summary

The time table is the top 30 functions by cumulative time. The memory
table is the top 20 places in this repository's code holding memory at
the run's peak: each allocation is charged to the innermost frame in
backend/ or scripts/, so a numpy call shows up as the line that made it.

With --baseline (an earlier run's profile.json), each row says how it
moved. A function is marked when it entered the top 10, or when its share
of the run's time grew by more than a quarter: shares, not seconds, so a
slower runner does not mark everything. Memory sites are compared by
their source text, so a line that only moved in the file still matches.

Timings never fail the run; shared runners are too noisy for that. The
script exits non-zero only when it cannot run. Standard library only,
apart from what the replay itself imports. docs/18-benchmark.md says how
to read it.
"""

# The analyser modules are imported after the set's settings are in the
# environment, as benchmark.py does.
# pylint: disable=import-outside-toplevel

import argparse
import cProfile
import importlib.util
import json
import linecache
import os
import platform
import pstats
import subprocess
import sys
import threading
import time
import tracemalloc

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOP_TIME = 30
TOP_MEMORY = 20
TOP_MARK = 10
GROWTH = 0.25
# How deep tracemalloc records each allocation, to find our own frame
# under numpy's and OpenCV's Python wrappers.
FRAMES = 16
# The peak sampler: how often it looks, and how much memory must grow
# past the last snapshot before it takes another.
SAMPLE_SEC = 0.002
SNAPSHOT_STEP = 1.02
SNAPSHOT_MIN_STEP = 4 * 1024 * 1024
OURS = (
    os.path.join(ROOT, "backend") + os.sep,
    os.path.join(ROOT, "scripts") + os.sep,
)
MIB = 1024 * 1024


def _bench():
    spec = importlib.util.spec_from_file_location(
        "benchmark", os.path.join(ROOT, "scripts", "benchmark.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prepare(bench, sets):
    """Settings in the environment and the analyser imported, so neither
    the import time nor the import's memory lands in the tables."""
    for name in sets:
        _folder, meta = bench._load_set(name)  # pylint: disable=W0212
        bench._apply_settings(meta)  # pylint: disable=W0212
    import classify  # noqa: F401 pylint: disable=unused-import
    import computer_vision  # noqa: F401 pylint: disable=unused-import
    import ink_geometry  # noqa: F401 pylint: disable=unused-import
    import layout_filter  # noqa: F401 pylint: disable=unused-import
    import recognizer  # noqa: F401 pylint: disable=unused-import
    import scoring  # noqa: F401 pylint: disable=unused-import


def _replay(bench, sets):
    """Layer A, as `benchmark.py check` runs it; returns the page count.
    A page that no longer matches expected.json is the benchmark job's
    business, not this one's: only an exception stops the profile."""
    pages = 0
    for name in sets:
        _meta, results, _problems = bench.run_set(name)
        pages += len(results)
    return pages


def _short(path):
    """A path as a reader wants it: repository-relative, the part after
    site-packages for a library, the file name for the standard library."""
    if path.startswith(ROOT + os.sep):
        return os.path.relpath(path, ROOT)
    for marker in ("site-packages" + os.sep, "dist-packages" + os.sep):
        if marker in path:
            return path.split(marker, 1)[1]
    if os.sep in path:
        return "stdlib/" + os.path.basename(path)
    return path


def _function(key):
    filename, line, func = key
    if filename == "~":
        return func, func
    where = _short(filename)
    return f"{where}:{line}({func})", f"{where}:{func}"


def time_table(stats, total):
    """The top functions by cumulative time from a pstats.Stats."""
    rows = []
    for key, (_cc, calls, own, cum, _callers) in stats.stats.items():
        label, ident = _function(key)
        if "_lsprof.Profiler" in label:
            continue
        rows.append(
            {
                "function": label,
                "key": ident,
                "calls": calls,
                "cumulative_s": round(cum, 4),
                "self_s": round(own, 4),
                "share": round(cum / total, 4) if total else 0.0,
            }
        )
    rows.sort(key=lambda r: (-r["cumulative_s"], r["function"]))
    for rank, row in enumerate(rows[:TOP_TIME], 1):
        row["rank"] = rank
    return rows[:TOP_TIME]


def profile_time(bench, sets, out):
    profiler = cProfile.Profile()
    start = time.perf_counter()
    profiler.enable()
    pages = _replay(bench, sets)
    profiler.disable()
    wall = time.perf_counter() - start
    profiler.dump_stats(os.path.join(out, "profile.prof"))
    stats = pstats.Stats(profiler)
    return {
        "pages": pages,
        "wall_s": round(wall, 3),
        "total_s": round(stats.total_tt, 3),
        "functions": time_table(stats, stats.total_tt),
    }


class PeakSampler(threading.Thread):
    """Takes a tracemalloc snapshot each time the traced memory grows a
    step past the last one, so the last snapshot is the run's peak (to
    within one sampling interval)."""

    def __init__(self):
        super().__init__(daemon=True)
        self.stop = threading.Event()
        self.snapshot = None
        self.size = 0

    def run(self):
        while not self.stop.wait(SAMPLE_SEC):
            current, _peak = tracemalloc.get_traced_memory()
            if current > max(
                self.size * SNAPSHOT_STEP, self.size + SNAPSHOT_MIN_STEP
            ):
                self.snapshot = tracemalloc.take_snapshot()
                self.size = current


def _site(traceback):
    """The innermost frame of an allocation that is our code, or the
    innermost frame when none is (a library's own cache)."""
    for frame in reversed(traceback):
        if frame.filename.startswith(OURS):
            return frame
    return traceback[-1]


def memory_table(snapshot):
    """The places in our code holding the most memory in a snapshot."""
    snapshot = snapshot.filter_traces(
        [
            tracemalloc.Filter(False, tracemalloc.__file__),
            tracemalloc.Filter(False, os.path.abspath(__file__)),
        ]
    )
    sites = {}
    for trace in snapshot.traces:
        frame = _site(trace.traceback)
        key = (frame.filename, frame.lineno)
        size, blocks = sites.get(key, (0, 0))
        sites[key] = (size + trace.size, blocks + 1)
    rows = []
    for (filename, line), (size, blocks) in sites.items():
        code = linecache.getline(filename, line).strip()
        where = _short(filename)
        rows.append(
            {
                "site": f"{where}:{line}",
                "code": code,
                "key": f"{where}:{code}",
                "size_mib": round(size / MIB, 3),
                "blocks": blocks,
            }
        )
    rows.sort(key=lambda r: (-r["size_mib"], r["site"]))
    for rank, row in enumerate(rows[:TOP_MEMORY], 1):
        row["rank"] = rank
    return rows[:TOP_MEMORY]


def profile_memory(bench, sets):
    tracemalloc.start(FRAMES)
    sampler = PeakSampler()
    sampler.start()
    try:
        pages = _replay(bench, sets)
    finally:
        sampler.stop.set()
        sampler.join()
        _current, peak = tracemalloc.get_traced_memory()
        snapshot = sampler.snapshot or tracemalloc.take_snapshot()
        tracemalloc.stop()
    return {
        "pages": pages,
        "peak_mib": round(peak / MIB, 2),
        "snapshot_mib": round(sampler.size / MIB, 2),
        "sites": memory_table(snapshot),
    }


def _pct(new, old):
    if not old:
        return None
    return (new - old) / old


def compare(rows, old_rows, value):
    """Mark each row against the baseline's rows: entered the top 10, or
    its value grew by more than GROWTH. Sets row["change"] (text) and
    row["marked"]; rows without a baseline get neither."""
    old = {}
    for row in old_rows:
        old.setdefault(row["key"], row)
    for row in rows:
        before = old.get(row["key"])
        notes = []
        if row["rank"] <= TOP_MARK and (
            before is None or before["rank"] > TOP_MARK
        ):
            notes.append(f"entered top {TOP_MARK}")
        if before is None:
            change = "new"
        else:
            grew = _pct(row[value], before[value])
            change = "same" if grew is None else f"{grew:+.0%}"
            if grew is not None and grew > GROWTH:
                notes.append(f"grew more than {GROWTH:.0%}")
        row["marked"] = bool(notes)
        row["change"] = (
            f"**{change} ({', '.join(notes)})**" if notes else change
        )


def _cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def markdown(result, baseline_note):
    t, m = result["time"], result["memory"]
    has_change = result.get("baseline") is not None
    out = [
        "## Profile of the benchmark replay",
        "",
        f"Sets: {', '.join(result['sets'])}; {t['pages']} pages, each "
        "replayed twice as `benchmark.py check` does. Commit "
        f"`{result['commit'][:12]}`, Python {result['python']}.",
        "",
        baseline_note,
        "",
        f"### Time: top {TOP_TIME} functions by cumulative time",
        "",
        f"Under cProfile the replay took {t['wall_s']:.1f} s. Share is "
        "the function's cumulative time over the whole run; the change "
        "compares shares, so a slower runner alone marks nothing. "
        "Timings are for reading, never for passing or failing.",
        "",
    ]
    head = "| # | Function | Calls | Cumulative s | Self s | Share |"
    rule = "|---:|---|---:|---:|---:|---:|"
    if has_change:
        head += " Change |"
        rule += "---|"
    out += [head, rule]
    for r in t["functions"]:
        cells = [
            r["rank"],
            f"`{_cell(r['function'])}`",
            r["calls"],
            f"{r['cumulative_s']:.3f}",
            f"{r['self_s']:.3f}",
            f"{r['share']:.1%}",
        ]
        if has_change:
            cells.append(r.get("change", ""))
        out.append("| " + " | ".join(str(c) for c in cells) + " |")
    out += [
        "",
        f"### Memory: top {TOP_MEMORY} places holding memory at the peak",
        "",
        f"Under tracemalloc the replay's traced memory peaked at "
        f"{m['peak_mib']:.1f} MiB; the snapshot below was taken at "
        f"{m['snapshot_mib']:.1f} MiB. Each allocation is charged to the "
        "innermost line of our own code that led to it. This is Python's "
        "view of one replay, not the server's resident memory: that is "
        "`backend/load_test.py` on stage.",
        "",
    ]
    head = "| # | Site | Code | MiB | Blocks |"
    rule = "|---:|---|---|---:|---:|"
    if has_change:
        head += " Change |"
        rule += "---|"
    out += [head, rule]
    for r in m["sites"]:
        cells = [
            r["rank"],
            f"`{_cell(r['site'])}`",
            f"`{_cell(r['code'][:70])}`" if r["code"] else "",
            f"{r['size_mib']:.2f}",
            r["blocks"],
        ]
        if has_change:
            cells.append(r.get("change", ""))
        out.append("| " + " | ".join(str(c) for c in cells) + " |")
    return "\n".join(out) + "\n"


def _commit():
    try:
        return subprocess.run(
            ["git", "-C", ROOT, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return os.environ.get("GITHUB_SHA", "unknown")


def _load_baseline(path):
    """The earlier run's profile.json, and a sentence saying what it is."""
    if not path:
        return None, "No baseline given, so nothing is marked."
    if not os.path.exists(path):
        return None, (
            "No earlier successful run on `main` to compare with, so "
            "nothing is marked."
        )
    with open(path, encoding="utf-8") as f:
        old = json.load(f)
    return old, (
        f"Compared with the last successful run on `main`, commit "
        f"`{old.get('commit', 'unknown')[:12]}`. Marked: entered the top "
        f"{TOP_MARK}, or grew by more than {GROWTH:.0%}."
    )


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n", maxsplit=1)[0]
    )
    ap.add_argument(
        "--set",
        dest="sets",
        action="append",
        help="a set to replay; repeat for more (default uji-clean)",
    )
    ap.add_argument("--out", default="profile-out")
    ap.add_argument("--baseline", help="an earlier run's profile.json")
    args = ap.parse_args(argv)
    sets = args.sets or ["uji-clean"]
    os.makedirs(args.out, exist_ok=True)

    bench = _bench()
    _prepare(bench, sets)
    timing = profile_time(bench, sets, args.out)
    memory = profile_memory(bench, sets)

    old, note = _load_baseline(args.baseline)
    if old is not None:
        compare(timing["functions"], old["time"]["functions"], "share")
        compare(memory["sites"], old["memory"]["sites"], "size_mib")
    result = {
        "sets": sets,
        "commit": _commit(),
        "python": platform.python_version(),
        "baseline": None if old is None else old.get("commit"),
        "time": timing,
        "memory": memory,
    }
    text = markdown(result, note)
    with open(
        os.path.join(args.out, "profile.json"), "w", encoding="utf-8"
    ) as f:
        json.dump(result, f, indent=1)
        f.write("\n")
    with open(
        os.path.join(args.out, "profile.md"), "w", encoding="utf-8"
    ) as f:
        f.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
