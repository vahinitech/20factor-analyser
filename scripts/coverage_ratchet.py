# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Fail when test coverage drops under coverage-baseline.json.

    python scripts/coverage_ratchet.py backend coverage/backend.json --check
    python scripts/coverage_ratchet.py frontend \\
        coverage/frontend/coverage-summary.json --check
    python scripts/coverage_ratchet.py backend coverage/backend.json --update

The report is coverage.py's JSON (backend, `python -m coverage json`) or
c8's json-summary (frontend). Both are read the same way: a file's number
is its covered lines and branches over all its lines and branches, which
is what coverage.py prints with --branch.

The rules (#232, docs/21-performance-and-coverage.md section 6):

- the total and each file may not drop more than 0.5 points under the
  baseline;
- each file in backend/languages/ and backend/scoring_parts/ is at 90% or
  more, unless the baseline holds a dated exception for it, which then is
  that file's floor and can only go up;
- a file the baseline lists that still exists must still be measured.

`--update` writes this run's numbers into the baseline. It refuses while
the check fails, and it only raises numbers: lowering one is a hand edit
of coverage-baseline.json, so the lower number shows in the PR diff.
`--summary FILE` appends a per-file table (markdown) to FILE, for
$GITHUB_STEP_SUMMARY.

Standard library only.
"""

import argparse
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(ROOT, "coverage-baseline.json")
PARTS = ("backend", "frontend")
TOLERANCE = 0.5
FLOOR = 90.0
FLOOR_PATHS = ("backend/languages/", "backend/scoring_parts/")
LEAST = 10


def percent(covered, total):
    """Covered share in points, two decimals; a file with nothing to
    cover counts as fully covered."""
    if not total:
        return 100.0
    return round(100.0 * covered / total, 2)


def relative(name, root=ROOT):
    """Repository-relative posix path for a report key (c8 gives
    absolute paths, coverage.py relative ones)."""
    if os.path.isabs(name):
        name = os.path.relpath(name, root)
    return name.replace(os.sep, "/")


def read_report(path, root=ROOT):
    """{file: (covered, total)} from coverage.py JSON or c8 json-summary,
    where covered and total count lines and branches together."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    counts = {}
    if "files" in data and "totals" in data:
        for name, entry in data["files"].items():
            nums = entry["summary"]
            counts[relative(name, root)] = (
                nums["covered_lines"] + nums.get("covered_branches", 0),
                nums["num_statements"] + nums.get("num_branches", 0),
            )
        return counts
    for name, entry in data.items():
        if name == "total":
            continue
        counts[relative(name, root)] = (
            entry["lines"]["covered"] + entry["branches"]["covered"],
            entry["lines"]["total"] + entry["branches"]["total"],
        )
    return counts


def measure(counts):
    """(total percent, {file: percent}) from read_report's counts."""
    covered = sum(c for c, _ in counts.values())
    total = sum(t for _, t in counts.values())
    files = {name: percent(c, t) for name, (c, t) in counts.items()}
    return percent(covered, total), files


def floor_for(name, exceptions):
    """The lowest number allowed for name, or None when no floor applies."""
    if not name.startswith(FLOOR_PATHS):
        return None
    if name in exceptions:
        return min(FLOOR, exceptions[name]["percent"])
    return FLOOR


def problems(part, total, files, baseline, root=ROOT):
    """What breaks the rules, one line each; empty when nothing does."""
    base = baseline.get(part)
    if base is None:
        return [
            f"coverage-baseline.json has no {part} numbers: run"
            f" scripts/coverage_ratchet.py {part} <report> --update"
        ]
    out = []
    if total < base["total"] - TOLERANCE:
        out.append(
            f"{part} total is {total:.2f}%, more than {TOLERANCE} points"
            f" under the baseline {base['total']:.2f}%"
        )
    for name, was in sorted(base["files"].items()):
        now = files.get(name)
        if now is None:
            if os.path.exists(os.path.join(root, name)):
                out.append(f"{name} was {was:.2f}% and is no longer measured")
            continue
        if now < was - TOLERANCE:
            out.append(
                f"{name} is {now:.2f}%, more than {TOLERANCE} points under"
                f" the baseline {was:.2f}%"
            )
    exceptions = baseline.get("exceptions", {})
    for name, now in sorted(files.items()):
        floor = floor_for(name, exceptions)
        if floor is not None and now < floor:
            out.append(f"{name} is {now:.2f}%, under its floor {floor:.2f}%")
    return out


def updated(part, total, files, baseline, today, root=ROOT):
    """A new baseline with this run's numbers, never lower than before.
    The first baseline for a part records a dated exception for each
    floor file under the floor, at today's number."""
    new = json.loads(json.dumps(baseline))
    first = part not in new
    base = new.setdefault(part, {"total": 0.0, "files": {}})
    base["total"] = max(base["total"], total)
    kept = {
        name: was
        for name, was in base["files"].items()
        if name not in files and os.path.exists(os.path.join(root, name))
    }
    for name, now in files.items():
        kept[name] = max(now, base["files"].get(name, 0.0))
    base["files"] = dict(sorted(kept.items()))
    exceptions = new.setdefault("exceptions", {})
    for name, now in files.items():
        if not name.startswith(FLOOR_PATHS):
            continue
        if now >= FLOOR:
            exceptions.pop(name, None)
        elif name in exceptions:
            exceptions[name]["percent"] = max(exceptions[name]["percent"], now)
        elif first:
            exceptions[name] = {
                "percent": now,
                "since": today,
                "why": (
                    f"under {FLOOR:.0f}% when the floor came in (#232);"
                    " raise it, never lower it"
                ),
            }
    new["exceptions"] = dict(sorted(exceptions.items()))
    return new


def summary(part, total, files, baseline, found, counts):
    """Markdown for the job summary: total, problems, the least covered
    files and a table of every file against the baseline."""
    base = baseline.get(part, {"total": None, "files": {}})
    exceptions = baseline.get("exceptions", {})
    was = base["total"]
    head = f"### {part.capitalize()} coverage: {total:.2f}%"
    if was is not None:
        head += f" (baseline {was:.2f}%)"
    lines = [
        head,
        "",
        "Covered lines and branches over all lines and branches, per"
        f" file. A file or the total may not drop more than {TOLERANCE}"
        f" points under coverage-baseline.json; {' and '.join(FLOOR_PATHS)}"
        f" stay at {FLOOR:.0f}% or more"
        " (docs/21-performance-and-coverage.md section 6).",
        "",
    ]
    if found:
        lines += ["**Fails the ratchet:**", ""]
        lines += [f"- {line}" for line in found]
        lines.append("")
    measured = [n for n in files if counts[n][1]]
    least = sorted(measured, key=lambda n: (files[n], n))[:LEAST]
    lines.append(
        f"**{len(least)} least covered:** "
        + ", ".join(f"`{n}` {files[n]:.2f}%" for n in least)
    )
    lines += [
        "",
        "| File | Covered | Lines and branches | Baseline | Change |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in sorted(files):
        now = files[name]
        covered, all_ = counts[name]
        before = base["files"].get(name)
        note = " (exception)" if name in exceptions else ""
        if before is None:
            cells = "new | "
        else:
            cells = f"{before:.2f}% | {now - before:+.2f}"
        lines.append(
            f"| `{name}`{note} | {now:.2f}% | {covered} of {all_}"
            f" | {cells} |"
        )
    return "\n".join(lines) + "\n"


def load_baseline(path=BASELINE):
    """The committed baseline, or an empty one before the first."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    """Check, summarise or update one part's coverage."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("part", choices=PARTS)
    parser.add_argument("report", help="coverage.py JSON or c8 summary")
    parser.add_argument(
        "--check", action="store_true", help="exit 1 on any problem"
    )
    parser.add_argument(
        "--update", action="store_true", help="raise the baseline"
    )
    parser.add_argument("--summary", help="append a markdown table here")
    parser.add_argument("--baseline", default=BASELINE)
    args = parser.parse_args(argv)
    baseline = load_baseline(args.baseline)
    counts = read_report(args.report)
    total, files = measure(counts)
    found = problems(args.part, total, files, baseline)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as fh:
            fh.write(summary(args.part, total, files, baseline, found, counts))
    if args.update:
        if args.part in baseline and found:
            for line in found:
                print(line)
            print("not updated: fix the drop, or lower the number by hand")
            return 1
        today = datetime.date.today().isoformat()
        new = updated(args.part, total, files, baseline, today)
        with open(args.baseline, "w", encoding="utf-8") as fh:
            json.dump(new, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print(f"{args.part} baseline: total {total:.2f}%, {len(files)} files")
        return 0
    for line in found:
        print(f"::error::{line}" if args.check else line)
    if found:
        return 1 if args.check else 0
    print(f"{args.part} coverage {total:.2f}%, no drop under the baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
