# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Factor 6 measured against a page's printed ruling (#194).

When a worksheet or a four-line notebook has printed guide lines, each
line's small-letter band comes from the ruling instead of from the
writing, so it does not move with whatever else changes in the line.
Pages without ruling keep the measurement from the ink.

Drawn pages only: no download, no real handwriting."""

import importlib.util
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import zone_analysis as za  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, "scripts", f"{name}.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PAPER, RULE, INK = 235, 150, 30


def _rule(page, y, dashed=False):
    cols = np.arange(page.shape[1])
    on = (cols >= 10) & (cols < page.shape[1] - 10)
    if dashed:
        on &= cols % 18 < 12
    page[y : y + 2, on] = RULE


def _ruled_line(page, base, x_h=20, asc=2.0, desc=2.0, drift=0):
    """Four rules for a line on `base`, small letters filling the band
    (shifted `drift` rows from the ruling) and tall letters and tails
    reaching asc and desc x-heights."""
    _rule(page, base - 2 * x_h)
    _rule(page, base - x_h, dashed=True)
    _rule(page, base)
    _rule(page, base + x_h)
    top = base - x_h + drift
    for col in range(30, 330):
        if (col // 3) % 2 == 0:
            page[top : base + drift, col] = INK
    for col in range(36, 330, 24):
        page[base - int(asc * x_h) : base, col : col + 2] = INK
    for col in range(48, 330, 48):
        page[base - x_h : base - x_h + int(desc * x_h), col : col + 2] = INK


def _page(**line):
    page = np.full((260, 360), PAPER, dtype=np.uint8)
    for base in (70, 150, 230):
        _ruled_line(page, base, **line)
    lines = [
        {"box": [30, base - 50, 300, 80], "text": "the dog likes big hills"}
        for base in (70, 150, 230)
    ]
    return page, lines


class FindRulingTests(unittest.TestCase):
    def test_solid_and_dashed_rules_are_found(self):
        page, _lines = _page()
        rules, mask = za.find_ruling(page, 30, 330)
        self.assertEqual(len(rules), 12)
        self.assertTrue(mask[70, 100])

    def test_handwriting_alone_is_not_ruling(self):
        page = np.full((260, 360), PAPER, dtype=np.uint8)
        for col in range(30, 330):
            if (col // 3) % 2 == 0:
                page[50:70, col] = INK
        for col in range(36, 330, 24):
            page[30:70, col : col + 2] = INK
        for start in (40, 140, 250):
            page[60:62, start : start + 30] = INK  # joins inside words
        rules, mask = za.find_ruling(page, 30, 330)
        self.assertEqual(rules, [])
        self.assertIsNone(mask)


class RuledBandTests(unittest.TestCase):
    def test_reach_is_measured_from_the_rules(self):
        page, lines = _page(asc=2.0, desc=2.0)
        z = za.analyze_zones(page, lines)
        self.assertTrue(z["available"])
        self.assertTrue(z["ruled"])
        self.assertEqual(z["xHeightPx"], 20)
        self.assertLessEqual(abs(z["ascReach"] - 2.0), 0.1)
        self.assertLessEqual(abs(z["descReach"] - 2.0), 0.1)

    def test_long_ascenders_reach_further(self):
        page, lines = _page(asc=3.0)
        z = za.analyze_zones(page, lines)
        self.assertGreaterEqual(z["ascReach"], 2.8)

    def test_the_band_stays_on_the_ruling_when_the_ink_shifts(self):
        # Small letters written two rows high of the ruling: the band is
        # still the ruled one, so the reach does not move.
        steady, lines = _page()
        shifted, _lines = _page(drift=-2)
        a = za.analyze_zones(steady, lines)
        b = za.analyze_zones(shifted, lines)
        self.assertEqual(a["xHeightPx"], b["xHeightPx"])
        self.assertLessEqual(abs(a["ascReach"] - b["ascReach"]), 0.1)

    def test_one_dotted_rule_per_line_is_not_enough(self):
        # A notebook's single baseline: no rule at the small letters'
        # top, so the page keeps the measurement from the ink.
        page = np.full((260, 360), PAPER, dtype=np.uint8)
        for base in (70, 150, 230):
            _rule(page, base, dashed=True)
            for col in range(30, 330):
                if (col // 3) % 2 == 0:
                    page[base - 20 : base, col] = INK
            for col in range(36, 330, 24):
                page[base - 40 : base, col : col + 2] = INK
        lines = [
            {"box": [30, b - 30, 300, 40], "text": "the dog likes big hills"}
            for b in (70, 150, 230)
        ]
        z = za.analyze_zones(page, lines)
        self.assertNotIn("ruled", z)

    def test_a_line_off_the_ruling_is_left_to_the_ink(self):
        page, _lines = _page()
        rules, mask = za.find_ruling(page, 30, 330)
        # A box over empty paper between two groups of rules.
        self.assertIsNone(
            za.ruled_zone_bands(page, [30, 92, 300, 10], rules, mask)
        )


class RuledSamePassageTests(unittest.TestCase):
    def test_same_passage_pages_on_ruling_score_factor_6_alike(self):
        # As #157's stability test: two pages of the same passage by one
        # writer (drawn zigzag letters), now on printed ruling.
        planted = _load("planted_pages")
        study = _load("variation_study")

        def zigzag(ch, lean):
            h = 2.0 if ch in planted.TALL or ch in planted.LOW else 1.0
            xs = np.linspace(0, 0.5 + lean, 6)
            ys = [0.0 if i % 2 == 0 else h for i in range(6)]
            return [np.array(list(zip(xs, ys)))]

        chars = set("".join(planted.SENTENCES).replace(" ", ""))
        letters = {ch: [zigzag(ch, 0.0), zigzag(ch, 0.15)] for ch in chars}
        pairs = study.synthetic_pairs({"w01": letters}, 6, planted, True)
        moves = [abs(a[6] - b[6]) for _w, a, b in pairs]
        self.assertEqual(len(moves), 6)
        self.assertLessEqual(max(moves), 1.0, moves)


if __name__ == "__main__":
    unittest.main()
