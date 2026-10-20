# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Paired timing against main (scripts/paired_timing.py, #251): when it
calls a pull request slower, how it charges time to steps, and the table
it writes. The timing itself runs in ci.yml's paired-timing job."""

import importlib.util
import os
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
spec = importlib.util.spec_from_file_location(
    "paired_timing", os.path.join(ROOT, "scripts", "paired_timing.py")
)
paired = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paired)


def side(total, steps=None):
    return {
        "total": total,
        "pages": {"set/a": total / 2, "set/b": total / 2},
        "steps": steps or {"scoring": total * 0.8, "other": total * 0.2},
    }


def history(pairs):
    return [{"main": side(m), "pr": side(p)} for m, p in pairs]


class TestVerdict(unittest.TestCase):
    def test_same_code_passes(self):
        failed, ratio, _ = paired.verdict(history([(10, 10)] * 7))
        self.assertFalse(failed)
        self.assertAlmostEqual(ratio, 1.0)

    def test_slower_in_every_round_fails(self):
        failed, ratio, each = paired.verdict(history([(10, 12)] * 7))
        self.assertTrue(failed)
        self.assertAlmostEqual(ratio, 1.2)
        self.assertEqual(len(each), 7)

    def test_slow_median_but_last_rounds_disagree_passes(self):
        rows = [(10, 12)] * 5 + [(10, 9), (10, 12)]
        failed, ratio, _ = paired.verdict(history(rows))
        self.assertGreater(ratio, 1.1)
        self.assertFalse(failed)

    def test_under_the_limit_passes_even_when_always_slower(self):
        failed, _, _ = paired.verdict(history([(10, 10.9)] * 7))
        self.assertFalse(failed)

    def test_fewer_rounds_than_agree_never_fails(self):
        failed, _, _ = paired.verdict(history([(10, 20)] * 2))
        self.assertFalse(failed)


class TestClock(unittest.TestCase):
    def test_a_step_leaves_out_the_steps_it_calls(self):
        clock = paired.Clock()

        def busy(sec):
            end = time.process_time() + sec
            while time.process_time() < end:
                pass

        inner = clock.wrap("inner", lambda: busy(0.05))

        def outer_fn():
            busy(0.02)
            inner()

        outer = clock.wrap("outer", outer_fn)
        outer()
        self.assertGreaterEqual(clock.spent["inner"], 0.05)
        self.assertLess(clock.spent["outer"], 0.05)
        self.assertGreaterEqual(clock.spent["outer"], 0.02)

    def test_the_wrapped_function_still_answers_and_raises(self):
        clock = paired.Clock()
        self.assertEqual(clock.wrap("x", lambda a: a + 1)(1), 2)

        def boom():
            raise ValueError("no")

        with self.assertRaises(ValueError):
            clock.wrap("y", boom)()
        self.assertIn("y", clock.spent)


class TestRounds(unittest.TestCase):
    def test_sides_alternate_and_pages_are_shared(self):
        calls = []

        def run(path, _sets):
            calls.append(path)
            pages = {"s/a": 1.0, "s/b": 2.0}
            if path == "pr":
                pages["s/c"] = 5.0  # main could not replay this page
            return {"total": 0, "pages": pages, "steps": {}, "skip": []}

        got = paired.rounds("main", "pr", 3, ["s"], run=run)
        self.assertEqual(calls, ["main", "pr", "pr", "main", "main", "pr"])
        self.assertEqual(got[0]["pr"]["total"], 3.0)
        self.assertEqual(sorted(got[0]["pr"]["pages"]), ["s/a", "s/b"])


class TestTable(unittest.TestCase):
    def test_a_slow_pull_request_says_so_with_each_step(self):
        failed, text = paired.table(history([(10, 13)] * 7))
        self.assertTrue(failed)
        self.assertIn("| scoring | 8.00 | 10.40 | 1.30 |", text)
        self.assertIn("**1.30**", text)
        self.assertIn("Slower than main", text)
        self.assertIn("| set/a |", text)

    def test_a_noisy_runner_is_named_as_such(self):
        rows = [(10, 12)] * 6 + [(10, 9)]
        failed, text = paired.table(history(rows))
        self.assertFalse(failed)
        self.assertIn("taken as the runner", text)

    def test_an_unchanged_pull_request_is_within_the_limit(self):
        failed, text = paired.table(history([(10, 10.2)] * 7))
        self.assertFalse(failed)
        self.assertIn("Within 10% of main", text)


if __name__ == "__main__":
    unittest.main()
