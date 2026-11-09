# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The benchmarks run only when a change can move them
(scripts/score_closure.py). The file lists come from the imports, so the
test that matters is that the replay loads nothing outside them: a module
loaded by name, or a new entry point, would otherwise let a pull request
skip a benchmark it could move."""

import ast
import contextlib
import io
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

# pylint: disable=wrong-import-position
import score_closure  # noqa: E402

# One page of every benchmark set, replayed as `benchmark.py check` does;
# prints every module file the process loaded.
REPLAY = r"""
import importlib.util, json, os, subprocess, sys
spec = importlib.util.spec_from_file_location("benchmark", "scripts/benchmark.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
sets = subprocess.run(
    [sys.executable, "backend/languages/registry.py", "--benchmark-sets"],
    capture_output=True, text=True, check=True).stdout.split()
for name in sets:
    folder, meta = bench._load_set(name)
    bench._apply_settings(meta)
    page = bench._pages(folder)[0]
    raw, arr = bench._image(folder, page, meta)
    if bench._ink_mode(meta):
        bench._score_ink(arr, page, meta)
    else:
        with open(os.path.join(folder, "reader", page + ".json"), encoding="utf-8") as f:
            bench._score(arr, raw, json.load(f), meta)
print(json.dumps(sorted(
    m.__file__ for m in list(sys.modules.values()) if getattr(m, "__file__", None))))
"""


def _repo_paths(files):
    out = set()
    for path in files:
        rel = os.path.relpath(os.path.realpath(path), ROOT)
        if rel.startswith(score_closure.SEARCH) and rel.endswith(".py"):
            out.add(rel.replace(os.sep, "/"))
    return out


class ReplayStaysInsideTheClosure(unittest.TestCase):
    def test_the_replay_loads_nothing_outside_the_scores_group(self):
        done = subprocess.run(
            [sys.executable, "-c", REPLAY],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=600,
        )
        loaded = _repo_paths(json.loads(done.stdout.splitlines()[-1]))
        self.assertIn("backend/scoring.py", loaded)
        outside = sorted(loaded - score_closure.closure("scores"))
        self.assertEqual(
            outside,
            [],
            "the replay loads files the scores group does not list; add "
            "their entry or data to GROUPS in scripts/score_closure.py",
        )


class TheReaderStopsAtTheScorer(unittest.TestCase):
    def test_the_scorer_is_not_in_the_reader_group(self):
        reader = score_closure.closure("reader")
        self.assertIn("backend/reading/recognizer.py", reader)
        self.assertIn("backend/reading/ocr_backends.py", reader)
        self.assertFalse(
            [p for p in reader if p.startswith(("backend/scoring",))]
        )

    def test_no_reader_module_imports_the_scorer_at_load_time(self):
        # The stop holds while the reader reaches the scorer only inside a
        # function (computer_vision's evidence boxes). A top-level import
        # would mean the reading itself may run scorer code.
        for path in sorted(score_closure.closure("reader")):
            with open(os.path.join(ROOT, path), encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in tree.body:
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                with self.subTest(module=path):
                    self.assertFalse(
                        [n for n in names if n.split(".")[0] == "scoring"]
                    )


class WhatRunsForWhichChange(unittest.TestCase):
    CASES = {
        "backend/server/app.py": (False, False),
        "backend/report/practice_catalog.py": (False, False),
        "frontend/src/report/report-render.js": (False, False),
        "backend/tests/test_calibrate.py": (False, False),
        "backend/scoring_parts/spatial.py": (True, False),
        "benchmarks/factors/expected.json": (True, False),
        "backend/reading/detector.py": (True, True),
        "backend/requirements/core.txt": (True, True),
        "deployment/Dockerfile": (False, True),
        "scripts/score_closure.py": (True, True),
    }

    def test_each_change_runs_what_it_can_move(self):
        files = {g: score_closure.closure(g) for g in score_closure.GROUPS}
        for path, (scores, reader) in self.CASES.items():
            with self.subTest(change=path):
                got = tuple(
                    bool(score_closure.touches(g, [path], files[g]))
                    for g in ("scores", "reader")
                )
                self.assertEqual(got, (scores, reader))

    def test_every_entry_exists(self):
        for group, spec in score_closure.GROUPS.items():
            for path in spec["entries"]:
                with self.subTest(group=group, entry=path):
                    self.assertTrue(os.path.isfile(os.path.join(ROOT, path)))

    def test_no_change_skips_both(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = score_closure.main(["changed", "HEAD"])
        self.assertEqual(code, 0)
        self.assertEqual(
            out.getvalue().split(), ["scores:", "skip", "reader:", "skip"]
        )


if __name__ == "__main__":
    unittest.main()
