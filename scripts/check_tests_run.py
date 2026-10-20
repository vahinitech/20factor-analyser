# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Fail when a Python test file runs in no CI workflow.

    python scripts/check_tests_run.py --check

ci.yml runs `python -m coverage run --branch -m unittest discover -v -s
backend/tests -t .` (discovery under coverage.py, #232), so every
backend/tests/test_*.py runs without being listed anywhere. Before #228 the
job ran a hand-written list of modules and eight test files (the scan-slot
and capacity tests among them) ran nowhere, so a change that broke them
still passed.

This checks three things:

- ci.yml still runs that discovery command;
- backend/tests/ is a package (discovery with `-t .` needs its __init__.py),
  and so is every folder under it that holds a test file;
- every file there gives unittest a test to run: a TestCase with test
  methods, or, for a file written as plain test_* functions, a last line
  `FunctionTests = function_tests(globals())` (backend/tests/__init__.py),
  since discovery collects TestCase classes only and six files once ran
  nothing although they were discovered;
- a test_*.py anywhere else in the repository is named by some workflow in
  .github/workflows/, by path or by module name.

Standard library only: it runs before anything is installed.
"""

import argparse
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join("backend", "tests")
WORKFLOWS = os.path.join(".github", "workflows")
DISCOVER = "-m unittest discover -v -s backend/tests -t ."
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}


def test_files(root):
    """Every test_*.py under root, as paths relative to it."""
    found = []
    for here, dirs, files in os.walk(root):
        dirs[:] = sorted(
            d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")
        )
        for name in sorted(files):
            if name.startswith("test_") and name.endswith(".py"):
                found.append(os.path.relpath(os.path.join(here, name), root))
    return found


def workflow_text(root):
    """All workflow files joined, for looking names up."""
    folder = os.path.join(root, WORKFLOWS)
    parts = {}
    for name in sorted(os.listdir(folder)):
        if name.endswith((".yml", ".yaml")):
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                parts[name] = fh.read()
    return parts


def discovered(path, root):
    """True when unittest discovery from backend/tests reaches path."""
    folder = os.path.dirname(path)
    if os.path.commonpath([folder, TESTS]) != TESTS:
        return False
    while True:
        if not os.path.isfile(os.path.join(root, folder, "__init__.py")):
            return False
        if folder == TESTS:
            return True
        folder = os.path.dirname(folder)


def collects_nothing(path, root):
    """Why unittest would run no test from path, or None."""
    with open(os.path.join(root, path), encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source, path)
    funcs = (ast.FunctionDef, ast.AsyncFunctionDef)
    loose = [
        node.name
        for node in tree.body
        if isinstance(node, funcs) and node.name.startswith("test_")
    ]
    if loose:
        if "function_tests(globals())" in source:
            return None
        return (
            f"has test functions outside a TestCase ({loose[0]}, ...),"
            " which unittest never runs: end the file with"
            " `FunctionTests = function_tests(globals())`"
        )
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and any(
            isinstance(item, funcs) and item.name.startswith("test")
            for item in node.body
        ):
            return None
    return "defines no TestCase with a test method"


def problems(root=ROOT):
    """What is wrong, one line each; empty when every test file runs."""
    out = []
    flows = workflow_text(root)
    if DISCOVER not in flows.get("ci.yml", ""):
        out.append(f"ci.yml no longer runs `{DISCOVER}`")
    if not os.path.isfile(os.path.join(root, TESTS, "__init__.py")):
        out.append(f"{TESTS}/__init__.py is missing; discovery needs it")
    every = "\n".join(flows.values())
    for path in test_files(root):
        if discovered(path, root):
            why = collects_nothing(path, root)
            if why:
                out.append(f"{path.replace(os.sep, '/')} {why}")
            continue
        module = path[: -len(".py")].replace(os.sep, ".")
        posix = path.replace(os.sep, "/")
        if posix in every or module in every:
            continue
        out.append(
            f"{posix} runs in no workflow: move it to {TESTS}/ or name it"
            f" in a job under {WORKFLOWS}/"
        )
    return out


def main(argv=None):
    """Print each problem and exit 1, or say how many files run."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="exit 1 on any problem"
    )
    args = parser.parse_args(argv)
    found = problems()
    for line in found:
        print(f"::error::{line}" if args.check else line)
    if found:
        return 1 if args.check else 0
    print(f"{len(test_files(ROOT))} test files, each runs in a workflow")
    return 0


if __name__ == "__main__":
    sys.exit(main())
