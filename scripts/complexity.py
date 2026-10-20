# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Each per-page function's growth, measured against what is declared.

Design: docs/21-performance-and-coverage.md, section 4 (#230).
backend/perf/complexity.json lists every function that runs once per page,
what its n is, and how fast it may grow (its big O). This builds a
deterministic synthetic input for each at four sizes (n, 2n, 4n, 8n),
runs the function five times at each, takes the median CPU time
(time.process_time), and fits the slope of log time against log n. A
slope near 1 is linear, near 2 quadratic. The check fails when a slope is
more than the tolerance (0.3) above the declared class:

    python scripts/complexity.py check [--summary FILE] [--out FILE]

Shared runners are noisy, so only slopes are compared, never times.
Model inference is not here: its cost is fixed per crop, and the call
counts of backend/perf.py (#229) show how many crops a page had.
"""

# The analyser modules are imported from backend/ inside each builder.
# pylint: disable=import-outside-toplevel

import argparse
import json
import math
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
TABLE = os.path.join(BACKEND, "perf", "complexity.json")
STEPS = (1, 2, 4, 8)

# Growth classes: the slope each gives over n..8n. log factors are
# measured over the sizes actually run, so O(n log n) is a little over 1.
CLASSES = ("O(1)", "O(log n)", "O(n)", "O(n log n)", "O(n^2)", "O(n^3)")


def class_slope(declared, sizes):
    """The slope of log time against log n the declared class gives over
    these sizes."""
    if declared not in CLASSES:
        raise ValueError(f"unknown growth class {declared!r}")
    lo, hi = float(sizes[0]), float(sizes[-1])
    span = math.log(hi / lo)
    log_part = math.log(math.log(hi) / math.log(lo)) / span
    return {
        "O(1)": 0.0,
        "O(log n)": log_part,
        "O(n)": 1.0,
        "O(n log n)": 1.0 + log_part,
        "O(n^2)": 2.0,
        "O(n^3)": 3.0,
    }[declared]


def slope(sizes, times):
    """Least-squares slope of log(time) against log(n)."""
    xs = [math.log(float(n)) for n in sizes]
    ys = [math.log(max(float(t), 1e-9)) for t in times]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den


def median_cpu(call, repeats, inner=1):
    """Median process CPU seconds of `inner` calls of call(), over
    `repeats` runs. inner > 1 lifts a function that takes well under a
    millisecond above the clock's noise."""
    times = []
    for _ in range(repeats):
        t0 = time.process_time()
        for _ in range(inner):
            call()
        times.append(time.process_time() - t0)
    return statistics.median(times)


def measure(build, base, repeats=5, inner=1):
    """(sizes, median times): build(k) gives (n, call) for the k-th size,
    k = base, 2*base, 4*base, 8*base; n is the input measure, call runs
    the function once on a fresh copy of the input."""
    sizes, times = [], []
    for step in STEPS:
        n, call = build(base * step)
        call()  # first run: imports, caches and tables read once
        sizes.append(n)
        times.append(median_cpu(call, repeats, inner))
    return sizes, times


def verdict(measured, declared, sizes, tolerance):
    """(allowed slope, passed)."""
    allowed = class_slope(declared, sizes) + tolerance
    return allowed, measured <= allowed


# --------------------------------------------------------------------------
# Synthetic inputs. Every builder is deterministic: the same size gives the
# same input on every run. A builder takes k (the size step) and returns
# (n, call); call copies whatever the function changes, so each run gets
# the same input.
# --------------------------------------------------------------------------


def _backend():
    if BACKEND not in sys.path:
        sys.path.insert(0, BACKEND)


def _strip(rng, width, height):
    """A handwriting-like strip: dark strokes of uneven width and height,
    as backend/tests/test_server_pipeline.py draws them."""
    import numpy as np

    img = np.full((height, width, 3), 255, np.uint8)
    x = 6
    while x < width - 12:
        sw = int(rng.integers(2, 9))
        top = int(rng.integers(3, max(4, height // 3)))
        bot = height - int(rng.integers(3, max(4, height // 3)))
        img[top:bot, x : x + sw] = 0
        x += sw + int(rng.integers(5, 10))
    return img


ROW_H, ROW_GAP, PAGE_W, MARGIN = 40, 30, 640, 20


def _page(rows, seed=7):
    """(page, lines): a white page with `rows` written rows, and a
    reader-shaped line for each."""
    import numpy as np

    rng = np.random.default_rng(seed)
    height = 2 * MARGIN + rows * (ROW_H + ROW_GAP)
    page = np.full((height, PAGE_W, 3), 255, np.uint8)
    lines = []
    words = ["write", "neat", "round", "letters", "slowly", "with", "care"]
    for i in range(rows):
        y = MARGIN + i * (ROW_H + ROW_GAP)
        w = PAGE_W - 2 * MARGIN
        page[y : y + ROW_H, MARGIN : MARGIN + w] = _strip(rng, w, ROW_H)
        text = " ".join(words[(i + j) % len(words)] for j in range(5))
        lines.append(_line(text, [MARGIN, y, w, ROW_H]))
    return page, lines


def _line(text, box, score=0.72):
    x, y, w, h = box
    return {
        "text": text,
        "score": score,
        "box": [x, y, w, h],
        "poly": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
        "lang": "en",
    }


def _copies(lines):
    return [dict(l) for l in lines]


def build_merge_lines(k):
    _backend()
    import detector

    lines = [
        _line(f"line {i} word {i * 7}", [20, 20 + 30 * i, 500, 24])
        for i in range(k)
    ]
    return k, lambda: detector.merge_lines(_copies(lines))


def build_region_filter_lines(k):
    _backend()
    import detector

    lines = [
        _line(f"line {i} word", [20, 20 + 30 * i, 500, 24]) for i in range(k)
    ]
    shape = (40 + 30 * k, 640, 3)
    return k, lambda: detector.region_filter_lines(_copies(lines), shape)


def build_join_row_pieces(k):
    """k pieces, four to a written line: the reader's pieces of k / 4
    lines."""
    _backend()
    import detector

    pieces = []
    for i in range(k):
        row, col = divmod(i, 4)
        pieces.append(
            _line(f"piece{i}", [20 + 150 * col, 20 + 40 * row, 130, 26])
        )
    return k, lambda: detector.join_row_pieces(_copies(pieces))


def build_classify_lines(k):
    _backend()
    import classify

    page, lines = _page(k)
    return k, lambda: classify.classify_lines(page, _copies(lines))


def build_find_rows(k):
    _backend()
    import ink_geometry

    page, _lines = _page(k)
    return page.shape[0] * page.shape[1], lambda: ink_geometry.find_rows(page)


def build_missed_regions(k):
    """Rows found by the reader over their left half only, so the right
    half of every row is writing the detector missed."""
    _backend()
    import line_recovery

    page, lines = _page(k)
    for line in lines:
        line["box"][2] = line["box"][2] // 2
    return (
        page.shape[0] * page.shape[1],
        lambda: line_recovery.missed_regions(page, _copies(lines)),
    )


def build_vl_analyze(k):
    _backend()
    import computer_vision

    page, lines = _page(k)
    return k, lambda: computer_vision.vl_analyze(page, _copies(lines), True)


def build_build_analysis(k):
    _backend()
    import computer_vision
    import scoring

    page, lines = _page(k)
    layout = computer_vision.vl_analyze(page, lines, False)["layout"]
    return k, lambda: scoring.build_analysis(page, _copies(lines), layout)


def build_align_to_expected(k):
    """One line read with every fifth letter wrong against its passage
    line, k graphemes long."""
    _backend()
    import recognizer

    letters = "abcdefghijklmnopqrstuvwxyz"
    passage = "".join(
        " " if i % 6 == 5 else letters[(i * 7) % 26] for i in range(k)
    )
    read = "".join(
        ch if i % 5 else letters[(i * 3) % 26] for i, ch in enumerate(passage)
    )
    lines = [_line(read, [20, 20, 600, 30])]
    return k, lambda: recognizer.align_to_expected(_copies(lines), passage)


class _Engine:
    """A rung that answers every crop at once, the same answer each
    time: model inference is out of scope, the loop around it is not."""

    model_name = None

    @staticmethod
    def available():
        return True, ""

    @staticmethod
    def recognize_crop(_crop):
        return "write neat letters", 0.9

    @staticmethod
    def recognize_crops(crops):
        return [("write neat letters", 0.9) for _ in crops]


def build_climb(k):
    """k lines up the trocr-mode ladder, each with its own small crop."""
    _backend()
    import numpy as np

    import escalation

    lines = [
        _line(f"line {i}", [20, 20 + 30 * i, 500, 24], score=0.5)
        for i in range(k)
    ]
    crops = {}
    for i in range(k):
        crop = np.full((24, 64, 3), 255, np.uint8)
        crop[i % 24, (i // 24) % 64] = i % 251
        crops[i] = crop

    def run():
        # A new engine each run: answers are cached per engine object.
        engine = _Engine()
        todo = _copies(lines)
        index = {id(l): i for i, l in enumerate(todo)}
        escalation.climb(
            todo,
            "trocr",
            lambda l: crops[index[id(l)]],
            lambda _lower, _text, _conf: True,
            get_backend=lambda _name: engine,
        )

    return k, run


def build_to_numpy(k):
    """A PNG of a page with k rows, decoded."""
    _backend()
    import io

    from PIL import Image

    import computer_vision

    page, _lines = _page(k)
    buf = io.BytesIO()
    Image.fromarray(page).save(buf, format="PNG")
    raw = buf.getvalue()
    return (
        page.shape[0] * page.shape[1],
        lambda: computer_vision.to_numpy(raw, max_side=100000),
    )


BUILDERS = {
    "detector.merge_lines": build_merge_lines,
    "detector.region_filter_lines": build_region_filter_lines,
    "detector.join_row_pieces": build_join_row_pieces,
    "classify.classify_lines": build_classify_lines,
    "ink_geometry.find_rows": build_find_rows,
    "line_recovery.missed_regions": build_missed_regions,
    "computer_vision.to_numpy": build_to_numpy,
    "computer_vision.vl_analyze": build_vl_analyze,
    "scoring.build_analysis": build_build_analysis,
    "recognizer.align_to_expected": build_align_to_expected,
    "escalation.climb": build_climb,
}


def load_table(path=TABLE):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def table_problems(table, builders=None):
    """Entries that cannot be checked: no builder, an unknown class, or a
    class above O(n log n) with no reason given."""
    builders = BUILDERS if builders is None else builders
    problems = []
    for name, entry in table["functions"].items():
        if name not in builders:
            problems.append(f"{name}: no synthetic input in this script")
        if entry.get("declared") not in CLASSES:
            problems.append(f"{name}: unknown class {entry.get('declared')}")
        elif CLASSES.index(entry["declared"]) > CLASSES.index(
            "O(n log n)"
        ) and not str(entry.get("why") or "").strip():
            problems.append(f"{name}: above O(n log n) without a why")
    for name in builders:
        if name not in table["functions"]:
            problems.append(f"{name}: measured but not in complexity.json")
    return problems


def check(table, builders=None, names=None):
    """Measure every function; returns (rows, failed). Each row is a dict
    with the function, its n, the declared class, the measured slope,
    the most allowed, the sizes, the median times and whether it passed."""
    builders = BUILDERS if builders is None else builders
    tolerance = float(table.get("tolerance", 0.3))
    repeats = int(table.get("repeats", 5))
    rows, failed = [], 0
    for name, entry in table["functions"].items():
        if names and name not in names:
            continue
        sizes, times = measure(
            builders[name],
            int(entry["base"]),
            repeats,
            int(entry.get("inner", 1)),
        )
        got = slope(sizes, times)
        allowed, ok = verdict(got, entry["declared"], sizes, tolerance)
        failed += not ok
        rows.append(
            {
                "function": name,
                "n": entry["n"],
                "declared": entry["declared"],
                "slope": round(got, 2),
                "allowed": round(allowed, 2),
                "sizes": sizes,
                "ms": [round(t * 1000.0, 2) for t in times],
                "passed": ok,
            }
        )
    return rows, failed


def markdown(rows):
    out = [
        "### Growth per function (backend/perf/complexity.json)",
        "",
        "| Function | n | Declared | Measured slope | Most allowed "
        "| n sizes | Median CPU ms | |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        out.append(
            f"| `{row['function']}` | {row['n']} | {row['declared']} "
            f"| {row['slope']:.2f} | {row['allowed']:.2f} "
            f"| {', '.join(str(n) for n in row['sizes'])} "
            f"| {', '.join(f'{t:.1f}' for t in row['ms'])} "
            f"| {'ok' if row['passed'] else '**too steep**'} |"
        )
    return "\n".join(out) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["check"])
    parser.add_argument("--summary", help="append the table to this file")
    parser.add_argument("--out", help="write the table and rows here")
    parser.add_argument("--only", nargs="*", help="these functions only")
    args = parser.parse_args(argv)
    table = load_table()
    problems = table_problems(table)
    if problems:
        print("\n".join(problems))
        return 1
    rows, failed = check(table, names=args.only)
    text = markdown(rows)
    print(text)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as f:
            f.write(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n```json\n" + json.dumps(rows, indent=1))
            f.write("\n```\n")
    if failed:
        print(f"{failed} function(s) grow faster than declared.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
