# SPDX-License-Identifier: AGPL-3.0-only
"""Which files can change a benchmark, so a pull request that changes none
of them skips the benchmarks (docs/18-benchmark.md, "When the benchmarks
run").

    python scripts/score_closure.py groups               # each group's files
    python scripts/score_closure.py changed BASE         # run or skip, per group
    python scripts/score_closure.py changed BASE --github-output

Two groups, each the files its entry scripts import, followed through
backend/ and scripts/ by reading the source (ast; nothing is run), plus
the data the code reads by name:

- scores: everything the replay, the factor and calibration tests, the
  paired timing and the history import. A change here can move a score.
- reader: everything the reader imports, stopping at the scorer, plus the
  image, the models and the engine requirements. A change here can change
  what the live reader reads. The scorer is a stop on purpose: the reading
  (lines and text) never comes from it; vision/computer_vision.py imports
  it only to place evidence boxes, and a scoring change is caught by the
  replay of the kept reading. test_score_closure.py holds the stop.

`changed` compares BASE with HEAD and writes scores=true|false and
reader=true|false. On a pull request the checkout is GitHub's merge
commit, whose first parent is the base branch, so BASE is HEAD^1 and
the difference is exactly the pull request's changes. Any change to this file,
to a workflow or to a file that is not Python is matched by prefix
against the group's data list.
"""

import ast
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEARCH = ("backend", "scripts")

GROUPS = {
    "scores": {
        "entries": (
            "scripts/benchmark.py",
            "scripts/factor_tests.py",
            "scripts/planted_pages.py",
            "scripts/calibrate.py",
            "scripts/score_ranges.py",
            "scripts/variation_study.py",
            "scripts/paired_timing.py",
            "scripts/bench_history.py",
        ),
        "stop": (),
        "data": (
            "benchmarks/",
            "backend/languages/",
            "backend/models/",
            "backend/perf/",
            "backend/requirements.txt",
            "backend/requirements/",
            "scripts/score_closure.py",
            ".github/actions/changes/",
            ".github/workflows/ci.yml",
            ".github/workflows/factor-tests.yml",
        ),
    },
    "reader": {
        "entries": (
            "backend/reading/recognizer.py",
            "backend/warmup_models.py",
            "scripts/live_timing.py",
        ),
        "stop": ("backend/scoring.py", "backend/scoring_parts/"),
        "data": (
            "deployment/",
            "backend/models/",
            "backend/languages/",
            "backend/config.py",
            "backend/requirements.txt",
            "backend/requirements/",
            "benchmarks/uji-clean/",
            "scripts/benchmark.py",
            "scripts/score_closure.py",
            ".github/actions/changes/",
            ".github/workflows/benchmark-live.yml",
        ),
    },
}


def _module_file(name):
    parts = name.split(".")
    for base in SEARCH:
        path = os.path.join(base, *parts)
        if os.path.isfile(os.path.join(ROOT, path + ".py")):
            return path + ".py"
        init = os.path.join(path, "__init__.py")
        if os.path.isfile(os.path.join(ROOT, init)):
            return init
    return None


def _imports(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        tree = ast.parse(f.read(), path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.level:
                continue
            yield node.module
            for alias in node.names:
                yield f"{node.module}.{alias.name}"


def closure(group):
    """The Python files a group's entries import, as repository paths."""
    spec = GROUPS[group]
    seen, todo = set(), [p for p in spec["entries"] if _exists(p)]
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        if path.startswith(spec["stop"]) and path not in spec["entries"]:
            continue
        seen.add(path)
        for name in _imports(path):
            # Importing a.b.c runs a/__init__.py and a/b/__init__.py too.
            parts = name.split(".")
            for i in range(1, len(parts) + 1):
                found = _module_file(".".join(parts[:i]))
                if found and found not in seen:
                    todo.append(found)
    return seen


def _exists(path):
    return os.path.isfile(os.path.join(ROOT, path))


def touches(group, changed, files=None):
    """The changed paths that can change this group's benchmarks."""
    files = closure(group) if files is None else files
    data = GROUPS[group]["data"]
    return [p for p in changed if p in files or p.startswith(data)]


def changed_since(base):
    out = subprocess.run(
        ["git", "diff", "--name-only", base, "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["groups"]:
        for group in GROUPS:
            files = sorted(closure(group))
            print(f"{group}: {len(files)} Python files")
            for path in files:
                print(f"  {path}")
        return 0
    if len(args) >= 2 and args[0] == "changed":
        changed = changed_since(args[1])
        lines = []
        for group in GROUPS:
            hit = touches(group, changed)
            run = "true" if hit else "false"
            lines.append(f"{group}={run}")
            why = ", ".join(hit[:5]) + (" ..." if len(hit) > 5 else "")
            print(
                f"{group}: {'run' if hit else 'skip'}"
                + (f" ({why})" if hit else "")
            )
        if "--github-output" in args and os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
