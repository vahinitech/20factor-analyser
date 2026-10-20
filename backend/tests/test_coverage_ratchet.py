# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The coverage ratchet (scripts/coverage_ratchet.py, #232): a drop of
more than half a point fails, a floor file under 90% fails unless it has
an exception, and --update only ever raises numbers."""

import importlib.util
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(HERE)), "scripts", "coverage_ratchet.py"
)
spec = importlib.util.spec_from_file_location("coverage_ratchet", SCRIPT)
ratchet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ratchet)

LANG = "backend/languages/registry.py"
PLAIN = "backend/scoring.py"


def baseline(total=80.0, files=None, exceptions=None):
    """A baseline holding the backend part only."""
    return {
        "backend": {
            "total": total,
            "files": files if files is not None else {PLAIN: 80.0},
        },
        "exceptions": exceptions or {},
    }


class RatchetTest(unittest.TestCase):
    """problems() and updated() against small made-up baselines."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        for name in (LANG, PLAIN):
            path = os.path.join(self.root, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("")

    def check(self, total, files, base):
        """problems() for the backend part, against the temp root."""
        return ratchet.problems("backend", total, files, base, self.root)

    def test_half_a_point_is_allowed(self):
        self.assertEqual(self.check(79.5, {PLAIN: 79.5}, baseline()), [])

    def test_a_bigger_drop_fails(self):
        found = self.check(79.4, {PLAIN: 79.4}, baseline())
        self.assertEqual(len(found), 2)
        self.assertIn("backend total", found[0])
        self.assertIn(PLAIN, found[1])

    def test_a_file_no_longer_measured_fails(self):
        found = self.check(80.0, {}, baseline())
        self.assertEqual(
            found, [f"{PLAIN} was 80.00% and is no longer measured"]
        )

    def test_a_deleted_file_is_dropped(self):
        os.remove(os.path.join(self.root, PLAIN))
        self.assertEqual(self.check(80.0, {}, baseline()), [])

    def test_a_floor_file_under_ninety_fails(self):
        found = self.check(80.0, {PLAIN: 80.0, LANG: 89.99}, baseline())
        self.assertEqual(found, [f"{LANG} is 89.99%, under its floor 90.00%"])

    def test_an_exception_is_that_files_floor(self):
        base = baseline(
            exceptions={LANG: {"percent": 70.0, "since": "2026-10-20"}}
        )
        self.assertEqual(self.check(80.0, {PLAIN: 80.0, LANG: 70.0}, base), [])
        found = self.check(80.0, {PLAIN: 80.0, LANG: 69.9}, base)
        self.assertEqual(found, [f"{LANG} is 69.90%, under its floor 70.00%"])

    def test_no_baseline_yet_fails(self):
        found = ratchet.problems("frontend", 50.0, {}, baseline(), self.root)
        self.assertIn("no frontend numbers", found[0])

    def test_update_only_raises(self):
        new = ratchet.updated(
            "backend",
            79.6,
            {PLAIN: 81.0},
            baseline(files={PLAIN: 80.0}),
            "2026-10-20",
            self.root,
        )
        self.assertEqual(new["backend"]["total"], 80.0)
        self.assertEqual(new["backend"]["files"][PLAIN], 81.0)

    def test_first_update_records_exceptions(self):
        new = ratchet.updated(
            "backend",
            75.0,
            {PLAIN: 60.0, LANG: 85.0},
            {},
            "2026-10-20",
            self.root,
        )
        self.assertEqual(new["exceptions"][LANG]["percent"], 85.0)
        self.assertEqual(new["exceptions"][LANG]["since"], "2026-10-20")
        self.assertNotIn(PLAIN, new["exceptions"])
        later = ratchet.updated(
            "backend",
            75.0,
            {PLAIN: 60.0, LANG: 92.0},
            new,
            "2026-11-01",
            self.root,
        )
        self.assertNotIn(LANG, later["exceptions"])

    def test_reads_both_report_formats(self):
        coverage_py = {
            "files": {
                PLAIN: {
                    "summary": {
                        "covered_lines": 8,
                        "num_statements": 10,
                        "covered_branches": 1,
                        "num_branches": 2,
                    }
                }
            },
            "totals": {},
        }
        c8 = {
            "total": {},
            os.path.join(self.root, "frontend/src/a.js"): {
                "lines": {"covered": 3, "total": 4},
                "branches": {"covered": 0, "total": 0},
            },
        }
        for data, name, counts in (
            (coverage_py, PLAIN, (9, 12)),
            (c8, "frontend/src/a.js", (3, 4)),
        ):
            path = os.path.join(self.root, "report.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
            self.assertEqual(
                ratchet.read_report(path, self.root), {name: counts}
            )
        self.assertEqual(
            ratchet.measure({PLAIN: (9, 12)}), (75.0, {PLAIN: 75.0})
        )


if __name__ == "__main__":
    unittest.main()
