# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Where each scan's time and memory go: stage timings and call budgets.

Design: docs/21-performance-and-coverage.md, sections 2 and 3 (#229).

    with perf.scan() as record:                # one per request
        with perf.stage("decode", bytes=len(raw)) as step:
            arr = decode(raw)
            step.size(pixels=arr.shape[0] * arr.shape[1])
        with perf.stage("read." + rung_id, lines=len(todo)):
            perf.count("reader_calls")         # inside a stage

Each stage records its wall time, the CPU time of the thread it ran on
(work a library does on its own threads, as Paddle does, shows in the
wall time only), the change in the container's memory.current (skipped
where that file does not exist), its input sizes and its call counts. A
stage outside a scan records nothing, so tests and scripts call the
pipeline as before.

The numbers go three places: a Server-Timing header (stage names and
milliseconds), a rolling p50 and p95 per stage in /health (in memory,
reset on restart), and one log line per scan. budgets.json in perf/ says
how much one page may cost; in CI a benchmark page over a budget fails
(scripts/perf_budgets.py), in production a breach is only counted.

Two rules hold everywhere here:
- Measuring never decides. Nothing in the pipeline reads these numbers
  back: no timer or budget changes which engine runs or what a page
  scores (#112). A stage never raises from its own measuring; an
  exception from the code inside it passes through unchanged.
- Numbers only. A stage keeps its name, which comes from the code or the
  committed stage table, and numbers. A size or count that is not a
  number is dropped, so text, crops, a profile, a name or an address can
  never be recorded.
"""

import collections
import contextlib
import contextvars
import json
import math
import numbers
import os
import re
import threading
import time

BUDGETS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "perf",
    "budgets.json",
)
MEMORY_CURRENT = "/sys/fs/cgroup/memory.current"
# Scans kept per stage for /health's p50 and p95, and how many stage
# names /health keeps at most (the names come from the code and the
# stage table, so this is never reached; it only bounds the memory).
WINDOW = 512
MAX_STAGES = 64
_NAME = re.compile(r"[^a-z0-9._-]")

_SCAN = contextvars.ContextVar("vahini_perf_scan", default=None)
_STAGE = contextvars.ContextVar("vahini_perf_stage", default=None)


def _name(name):
    """A stage, size or count name as an HTTP token: a-z 0-9 . _ -"""
    return _NAME.sub("-", str(name).lower())[:48] or "stage"


def _number(value):
    """value as a plain int or float, or None when it is not a finite
    number (text, a bool, a crop, None)."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return None
    if isinstance(value, numbers.Integral):
        return int(value)
    value = float(value)
    return value if math.isfinite(value) else None


def _memory_bytes():
    try:
        with open(MEMORY_CURRENT, encoding="ascii") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


class Stage:
    """One run of one stage: what it was given and what it cost."""

    __slots__ = ("name", "sizes", "counts", "wall_ms", "cpu_ms", "mem_mb")

    def __init__(self, name):
        self.name = name
        self.sizes = {}
        self.counts = {}
        self.wall_ms = 0.0
        self.cpu_ms = 0.0
        self.mem_mb = None

    def size(self, **sizes):
        """Record input sizes (pixels, lines, words, graphemes...).
        Anything that is not a number is dropped."""
        for key, value in sizes.items():
            value = _number(value)
            if value is not None:
                self.sizes[_name(key)] = value

    def count(self, name, n=1):
        n = _number(n)
        if n is not None:
            key = _name(name)
            self.counts[key] = self.counts.get(key, 0) + n


class _NoStage:
    """What stage() gives outside a scan: records nothing."""

    def size(self, **_sizes):
        return None

    def count(self, _name_, _n=1):
        return None


_NO_STAGE = _NoStage()


class Scan:
    """Every stage one request ran, in the order they finished."""

    def __init__(self):
        self._lock = threading.Lock()
        self._stages = []

    def add(self, step):
        with self._lock:
            self._stages.append(step)

    def summary(self):
        """{stage name: totals over its runs}, in the order each stage
        first finished: runs, wall_ms, cpu_ms, mem_mb (when the container
        reports memory), and the summed sizes and counts."""
        with self._lock:
            steps = list(self._stages)
        out = {}
        for step in steps:
            row = out.setdefault(
                step.name,
                {
                    "runs": 0,
                    "wall_ms": 0.0,
                    "cpu_ms": 0.0,
                    "sizes": {},
                    "counts": {},
                },
            )
            row["runs"] += 1
            row["wall_ms"] += step.wall_ms
            row["cpu_ms"] += step.cpu_ms
            if step.mem_mb is not None:
                row["mem_mb"] = row.get("mem_mb", 0.0) + step.mem_mb
            for part in ("sizes", "counts"):
                for key, value in getattr(step, part).items():
                    row[part][key] = row[part].get(key, 0) + value
        for row in out.values():
            for key in ("wall_ms", "cpu_ms", "mem_mb"):
                if key in row:
                    row[key] = round(row[key], 1)
        return out


@contextlib.contextmanager
def scan():
    """Collect the stages of one request. Work handed to another thread
    keeps the request's context when it is run with
    contextvars.copy_context(), as scan_slots.run does."""
    record = Scan()
    token = _SCAN.set(record)
    try:
        yield record
    finally:
        _SCAN.reset(token)


@contextlib.contextmanager
def stage(name, **sizes):
    """Time the block as one run of the named stage of the current scan.
    Outside a scan it does nothing. Yields the Stage, for sizes known
    only inside the block (step.size(pixels=...))."""
    record = _SCAN.get()
    if record is None:
        yield _NO_STAGE
        return
    step = Stage(_name(name))
    step.size(**sizes)
    token = _STAGE.set(step)
    mem0 = _memory_bytes()
    cpu0 = time.thread_time()
    t0 = time.perf_counter()
    try:
        yield step
    finally:
        step.wall_ms = (time.perf_counter() - t0) * 1000.0
        step.cpu_ms = (time.thread_time() - cpu0) * 1000.0
        mem1 = _memory_bytes()
        if mem0 is not None and mem1 is not None:
            step.mem_mb = (mem1 - mem0) / 1048576.0
        _STAGE.reset(token)
        record.add(step)


def count(name, n=1):
    """Add n to a call count of the innermost open stage, if any."""
    step = _STAGE.get()
    if step is not None:
        step.count(name, n)


def load_budgets(path=BUDGETS_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


BUDGETS = load_budgets()


def breaches(summary, budgets=None):
    """The budgets one page broke, each as {budget, stage, value, limit}:
    names and numbers only. Empty when the page kept within them all."""
    budgets = BUDGETS if budgets is None else budgets
    out = []

    def over(budget, name, value, limit):
        if value > limit:
            out.append(
                {
                    "budget": budget,
                    "stage": name,
                    "value": round(float(value), 1),
                    "limit": limit,
                }
            )

    def counted(name, key):
        return summary.get(name, {}).get("counts", {}).get(key, 0)

    reads = [name for name in summary if name.startswith("read.")]
    if reads:
        ladder = summary.get("ladder", {}).get("sizes", {})
        lines_rungs = ladder.get("lines", 0) * ladder.get("rungs", 0)
        over(
            "reader_calls",
            "read",
            sum(counted(name, "reader_calls") for name in reads),
            lines_rungs * budgets["reader_calls_per_line_and_rung"],
        )
        for name in reads:
            over(
                "model_calls",
                name,
                counted(name, "model_calls"),
                budgets["model_calls_per_rung"],
            )
    for name, row in summary.items():
        if name == "decode" or name.startswith("decode."):
            over(
                "decoded_pixels",
                name,
                row["sizes"].get("pixels", 0),
                budgets["decoded_megapixels"] * 1000000,
            )
    if "recovery" in summary:
        over(
            "recovery_reader_calls",
            "recovery",
            counted("recovery", "reader_calls"),
            budgets["recovery_reader_calls"],
        )
    for name, cap in budgets["cpu_ms"].items():
        if name in summary:
            over("cpu_ms", name, summary[name]["cpu_ms"], cap)
    return out


def _percentile(values, share):
    """Nearest rank: the smallest value with at least share of the
    values at or below it."""
    ordered = sorted(values)
    rank = max(1, math.ceil(share * len(ordered)))
    return round(ordered[rank - 1], 1)


class Rolling:
    """The last WINDOW scans' time per stage, and how often each budget
    was broken since the process started. In memory only."""

    def __init__(self, window=WINDOW, max_stages=MAX_STAGES):
        self.window = window
        self.max_stages = max_stages
        self._lock = threading.Lock()
        self._wall = {}
        self._cpu = {}
        self._scans = 0
        self._breaches = collections.Counter()

    def add(self, summary, broken=()):
        with self._lock:
            self._scans += 1
            for name, row in summary.items():
                if name not in self._wall:
                    if len(self._wall) >= self.max_stages:
                        continue
                    self._wall[name] = collections.deque(maxlen=self.window)
                    self._cpu[name] = collections.deque(maxlen=self.window)
                self._wall[name].append(row["wall_ms"])
                self._cpu[name].append(row["cpu_ms"])
            for item in broken:
                self._breaches[f"{item['budget']}:{item['stage']}"] += 1

    def snapshot(self):
        """/health's stage_timings."""
        with self._lock:
            wall = {name: list(v) for name, v in self._wall.items()}
            cpu = {name: list(v) for name, v in self._cpu.items()}
            scans = self._scans
            broken = dict(sorted(self._breaches.items()))
        return {
            "scans": scans,
            "window": self.window,
            "stages": {
                name: {
                    "samples": len(wall[name]),
                    "wall_ms_p50": _percentile(wall[name], 0.50),
                    "wall_ms_p95": _percentile(wall[name], 0.95),
                    "cpu_ms_p50": _percentile(cpu[name], 0.50),
                    "cpu_ms_p95": _percentile(cpu[name], 0.95),
                }
                for name in wall
            },
            "budget_breaches": broken,
        }


ROLLING = Rolling()


def server_timing(summary, total_ms=None):
    """The Server-Timing header: stage names and milliseconds only."""
    parts = [
        f"{name};dur={row['wall_ms']:.1f}" for name, row in summary.items()
    ]
    if total_ms is not None:
        parts.append(f"total;dur={float(total_ms):.1f}")
    return ", ".join(parts)


def log_line(summary, broken=()):
    """One line for the server log: stage names, size and count names,
    and numbers."""
    body = {"stages": summary}
    if broken:
        body["breaches"] = list(broken)
    return "[perf] " + json.dumps(body, separators=(",", ":"))


def finish(record, total_ms=None, rolling=None, emit=print):
    """End a request: when it scanned a page (it decoded one; a cached
    answer did not), check the budgets, add it to /health and write its
    log line. Returns the Server-Timing header, "" when nothing was
    timed. Never raises: a measuring fault must not cost the visitor
    their report."""
    try:
        summary = record.summary()
        if not summary:
            return ""
        if "decode" in summary:
            broken = breaches(summary)
            (rolling or ROLLING).add(summary, broken)
            emit(log_line(summary, broken), flush=True)
        return server_timing(summary, total_ms)
    except Exception:  # pylint: disable=broad-except
        return ""
