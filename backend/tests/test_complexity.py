# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The growth check (scripts/complexity.py, #230) catches what it is for.

A function written to be quadratic, declared linear, must fail the check;
declared quadratic, it passes, and a linear one declared linear passes.
These functions live here, never in backend/perf/complexity.json. The
real table is checked for shape only: the CI job `complexity` measures it.
"""

import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
spec = importlib.util.spec_from_file_location(
    "complexity", os.path.join(ROOT, "scripts", "complexity.py")
)
complexity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(complexity)


def build_quadratic(k):
    """Every pair of k items compared: k * k steps."""
    items = list(range(k))

    def run():
        total = 0
        for a in items:
            for b in items:
                total += a ^ b
        return total

    return k, run


def build_linear(k):
    items = list(range(k * 200))
    return k, lambda: sum(i ^ 7 for i in items)


def _table(declared, base):
    return {
        "tolerance": 0.3,
        "repeats": 5,
        "functions": {
            "planted": {
                "n": "items",
                "declared": declared,
                "base": base,
                "why": "a test function",
            }
        },
    }


class TestGrowthCheck(unittest.TestCase):
    def test_a_quadratic_function_declared_linear_fails(self):
        rows, failed = complexity.check(
            _table("O(n)", 150), {"planted": build_quadratic}
        )
        self.assertEqual(failed, 1)
        self.assertFalse(rows[0]["passed"])
        self.assertGreater(rows[0]["slope"], 1.3)
        self.assertIn("too steep", complexity.markdown(rows))

    def test_the_same_function_declared_quadratic_passes(self):
        rows, failed = complexity.check(
            _table("O(n^2)", 150), {"planted": build_quadratic}
        )
        self.assertEqual(failed, 0, rows)

    def test_a_linear_function_declared_linear_passes(self):
        rows, failed = complexity.check(
            _table("O(n)", 100), {"planted": build_linear}
        )
        self.assertEqual(failed, 0, rows)

    def test_the_slope_of_exact_powers(self):
        sizes = [100, 200, 400, 800]
        for power in (0, 1, 2, 3):
            times = [n**power / 1e6 for n in sizes]
            self.assertAlmostEqual(complexity.slope(sizes, times), power)

    def test_class_slopes(self):
        sizes = [100, 200, 400, 800]
        self.assertEqual(complexity.class_slope("O(n)", sizes), 1.0)
        self.assertEqual(complexity.class_slope("O(n^2)", sizes), 2.0)
        n_log_n = complexity.class_slope("O(n log n)", sizes)
        self.assertGreater(n_log_n, 1.0)
        self.assertLess(n_log_n, 1.2)
        times = [n * complexity.math.log(n) for n in sizes]
        self.assertAlmostEqual(
            complexity.slope(sizes, times), n_log_n, places=2
        )
        with self.assertRaises(ValueError):
            complexity.class_slope("O(2^n)", sizes)


class TestTable(unittest.TestCase):
    def test_every_function_has_an_input_and_every_input_an_entry(self):
        table = complexity.load_table()
        self.assertEqual(complexity.table_problems(table), [])

    def test_above_n_log_n_needs_a_reason(self):
        table = _table("O(n^2)", 10)
        del table["functions"]["planted"]["why"]
        self.assertEqual(
            complexity.table_problems(table, {"planted": build_quadratic}),
            ["planted: above O(n log n) without a why"],
        )

    def test_a_listed_function_without_an_input_is_reported(self):
        table = _table("O(n)", 10)
        self.assertEqual(
            complexity.table_problems(table, {}),
            ["planted: no synthetic input in this script"],
        )

    def test_passage_alignment_is_declared_quadratic(self):
        entry = complexity.load_table()["functions"][
            "recognizer.align_to_expected"
        ]
        self.assertEqual(entry["declared"], "O(n^2)")
        self.assertEqual(entry["n"], "graphemes")


if __name__ == "__main__":
    unittest.main()
