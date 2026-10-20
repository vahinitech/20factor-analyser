# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The profiling job's marks (scripts/profile_benchmark.py, #231): which
rows it flags against the last run on main, and the tables it writes.
The profile itself runs in .github/workflows/profile.yml."""

import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
spec = importlib.util.spec_from_file_location(
    "profile_benchmark", os.path.join(ROOT, "scripts", "profile_benchmark.py")
)
prof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prof)


def fn(rank, key, share):
    return {
        "rank": rank,
        "function": key + ":1",
        "key": key,
        "calls": 1,
        "cumulative_s": share * 10,
        "self_s": 0.0,
        "share": share,
    }


def site(rank, key, mib):
    return {
        "rank": rank,
        "site": key,
        "code": "x = np.zeros(n)",
        "key": key,
        "size_mib": mib,
        "blocks": 1,
    }


class TestProfileMarks(unittest.TestCase):
    def test_a_function_that_entered_the_top_ten_is_marked(self):
        rows = [fn(3, "a", 0.2)]
        prof.compare(rows, [fn(14, "a", 0.2)], "share")
        self.assertTrue(rows[0]["marked"])
        self.assertIn("entered top 10", rows[0]["change"])

    def test_a_new_function_in_the_top_ten_is_marked(self):
        rows = [fn(1, "b", 0.5)]
        prof.compare(rows, [fn(1, "a", 0.5)], "share")
        self.assertTrue(rows[0]["marked"])
        self.assertTrue(rows[0]["change"].startswith("**new"))

    def test_growth_over_a_quarter_is_marked_and_under_is_not(self):
        rows = [fn(20, "a", 0.13), fn(21, "b", 0.12)]
        prof.compare(rows, [fn(20, "a", 0.1), fn(21, "b", 0.1)], "share")
        self.assertTrue(rows[0]["marked"])
        self.assertIn("+30%", rows[0]["change"])
        self.assertFalse(rows[1]["marked"])
        self.assertEqual(rows[1]["change"], "+20%")

    def test_memory_sites_compare_by_size(self):
        rows = [site(2, "backend/x.py:zeros", 40.0)]
        prof.compare(rows, [site(2, "backend/x.py:zeros", 10.0)], "size_mib")
        self.assertTrue(rows[0]["marked"])
        self.assertIn("+300%", rows[0]["change"])

    def test_paths_are_short(self):
        self.assertEqual(
            prof._short(  # pylint: disable=W0212
                os.path.join(ROOT, "backend", "scoring.py")
            ),
            os.path.join("backend", "scoring.py"),
        )
        self.assertEqual(
            prof._short(  # pylint: disable=W0212
                "/usr/lib/python3/site-packages/numpy/core/numeric.py"
            ),
            "numpy/core/numeric.py",
        )

    def test_both_tables_are_written_with_and_without_a_baseline(self):
        result = {
            "sets": ["uji-clean"],
            "commit": "0123456789abcdef",
            "python": "3.11.9",
            "baseline": None,
            "time": {
                "pages": 20,
                "wall_s": 12.0,
                "total_s": 11.0,
                "functions": [fn(1, "a|b", 1.0)],
            },
            "memory": {
                "pages": 20,
                "peak_mib": 210.0,
                "snapshot_mib": 205.0,
                "sites": [site(1, "backend/x.py:3", 50.0)],
            },
        }
        text = prof.markdown(result, "No baseline.")
        self.assertIn("### Time: top 30 functions", text)
        self.assertIn("### Memory: top 20 places", text)
        self.assertIn("a\\|b", text)
        self.assertNotIn("Change", text)
        result["baseline"] = "fedcba"
        prof.compare(result["time"]["functions"], [], "share")
        prof.compare(result["memory"]["sites"], [], "size_mib")
        self.assertIn("| Change |", prof.markdown(result, "Compared."))


if __name__ == "__main__":
    unittest.main()
