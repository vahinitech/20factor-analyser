# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The cursive reference pages by letter-model family (#342):
scripts/benchmark.py families, and the sets it reads."""

import importlib.util
import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
spec = importlib.util.spec_from_file_location(
    "benchmark", os.path.join(ROOT, "scripts", "benchmark.py")
)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def row(family, verdict, pieces, missing, rows=3):
    return {
        "family": family,
        "set": family,
        "verdict": verdict,
        "shares": None,
        "words": 0,
        "lean": None,
        "letter_style": None,
        "lines": rows,
        "rows": rows,
        "in_pieces": pieces,
        "not_measured": missing,
    }


class TestFamilies(unittest.TestCase):
    def test_every_family_set_names_a_known_family(self):
        sets = bench._family_sets()  # pylint: disable=W0212
        self.assertTrue(sets)
        for family, name in sets:
            self.assertIn(family, bench.FAMILIES)
            folder = os.path.join(bench.SETS[0], name)
            self.assertTrue(os.path.exists(os.path.join(folder, "source.md")))
            with open(os.path.join(folder, "set.json"), encoding="utf-8") as f:
                meta = json.load(f)
            # Every page carries its slant as written, and its text.
            for page in bench._pages(folder):  # pylint: disable=W0212
                self.assertIn(page, meta["page_style"], name)
                self.assertIn(
                    meta["page_style"][page]["slant"],
                    ("upright", "slanted", "not recorded"),
                )
                if "sentences" not in meta:
                    self.assertIn(page, meta["page_text"], name)

    def test_the_kept_numbers_cover_every_family_set(self):
        path = os.path.join(bench.SETS[0], bench.FAMILIES_FILE)
        with open(path, encoding="utf-8") as f:
            kept = json.load(f)
        names = {name for _f, name in bench._family_sets()}  # noqa
        self.assertEqual({r["set"] for r in kept["pages"].values()}, names)

    def test_a_family_without_pages_says_so(self):
        data = {"families": {}, "pages": {}}
        table = bench.families_table(data)
        for label in bench.FAMILIES.values():
            self.assertIn(f"| {label} | 0, no licensed pages yet", table)

    def test_every_move_of_a_family_is_listed(self):
        old = {
            "families": {
                "breaks": {"pages": 2, "pages_in_pieces": 1},
            },
            "pages": {"a/p1": row("breaks", "mixed", True, [10])},
        }
        new = {
            "families": {
                "breaks": {"pages": 2, "pages_in_pieces": 0},
                "french": {"pages": 1},
            },
            "pages": {"a/p1": row("breaks", "cursive", False, [])},
        }
        moves = bench._family_moves(old, new)  # pylint: disable=W0212
        self.assertIn("breaks: pages_in_pieces 1 -> 0", moves)
        self.assertIn("french: added", moves)
        self.assertIn("page a/p1 changed", moves)
        self.assertEqual(bench._family_moves(new, new), [])  # noqa


if __name__ == "__main__":
    unittest.main()
