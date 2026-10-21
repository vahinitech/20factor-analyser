# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Factor 6 (Ascender/Descender Control) stays put between two pages of
the same passage by the same writer.

The normal-variation run (scripts/variation_study.py uji) found factor 6
moving by up to 9.1 points between two such pages. Three things in
zone_analysis.py did it, each tested here on drawn ink:

- the padded line crop takes in the line above or below, and the
  longest dense run of rows (the x-height search) could be that line's;
- the line's reach was its single tallest blob, so one long letter set
  the whole line;
- a descender touching a letter on the next line joins it into one blob
  whose "reach" is the gap between the lines.

Drawn letters only: no download, no real handwriting."""

import importlib.util
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import zone_analysis  # noqa: E402
from zone_analysis import line_zone_bands  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, "scripts", f"{name}.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


study = _load("variation_study")
planted = _load("planted_pages")

PAPER, INK = 245, 20


def _band(page, x, midline, h_m, width):
    """A dense x-height band: every other pair of columns inked."""
    for col in range(x, x + width):
        if (col // 3) % 2 == 0:
            page[midline : midline + h_m, col] = INK


def _stroke(page, x, top, bottom):
    page[top : bottom + 1, x : x + 2] = INK


class OwnBandTests(unittest.TestCase):
    def test_the_line_above_is_not_taken_for_this_lines_x_height(self):
        # The line above writes bigger, and its band sits inside this
        # line's padded crop. The longest dense run is the line above's.
        page = np.full((220, 400), PAPER, dtype=np.uint8)
        _band(page, 30, 46, 30, 320)  # line above, x-height 30
        _band(page, 30, 100, 18, 320)  # this line, x-height 18
        for col in range(36, 340, 24):
            _stroke(page, col, 82, 117)  # ascenders 18 above
        z = line_zone_bands(page, [30, 70, 320, 50])
        self.assertIsNotNone(z)
        self.assertLessEqual(abs(z["h_m"] - 18), 2)
        self.assertLessEqual(abs(z["asc_reach"] - 2.0), 0.2)


class TypicalReachTests(unittest.TestCase):
    def test_one_long_letter_does_not_set_the_line(self):
        page = np.full((240, 400), PAPER, dtype=np.uint8)
        _band(page, 30, 120, 20, 320)
        for col in range(36, 340, 24):
            _stroke(page, col, 100, 139)  # ascenders reaching 2.0
        _stroke(page, 340, 60, 139)  # one f four x-heights tall
        z = line_zone_bands(page, [30, 100, 320, 40])
        self.assertLessEqual(abs(z["asc_reach"] - 2.0), 0.15)

    def test_a_descender_touching_the_next_line_is_not_its_reach(self):
        # Ruled tight: this line's g runs into a letter on the line below,
        # and the two read as one blob down to that line's baseline.
        page = np.full((260, 400), PAPER, dtype=np.uint8)
        _band(page, 30, 80, 20, 320)  # this line
        _band(page, 30, 140, 20, 320)  # the line below
        for col in range(44, 300, 30):
            _stroke(page, col, 80, 119)  # descenders reaching 2.0
        _stroke(page, 314, 80, 159)  # the joined one
        z = line_zone_bands(page, [30, 80, 320, 40])
        self.assertLessEqual(abs(z["desc_reach"] - 2.0), 0.15)

    def test_a_line_with_only_joined_descenders_still_measures(self):
        # Nothing else to go by: the joined blob counts, stopped at the
        # next line's x-height, rather than the line reading single-zone.
        page = np.full((260, 400), PAPER, dtype=np.uint8)
        _band(page, 30, 80, 20, 320)
        _band(page, 30, 140, 20, 320)
        _stroke(page, 314, 80, 159)
        z = line_zone_bands(page, [30, 80, 320, 40])
        self.assertGreaterEqual(z["desc_reach"], 2.5)


def _zones(asc, dev=None):
    """A measured page whose lines reach these ascender heights."""
    if dev is None:
        dev = zone_analysis._line_dev(asc)  # pylint: disable=W0212
    return {
        "available": True,
        "ascReach": zone_analysis._median(asc),  # pylint: disable=W0212
        "descReach": None,
        "ascReachCv": 0.0,
        "ascLineDev": dev,
    }


class OneLongLineTests(unittest.TestCase):
    def test_a_line_that_runs_long_costs_points_on_its_own(self):
        even = zone_analysis.zone_score(_zones([2.0, 2.0, 2.0, 2.0]))
        long = zone_analysis.zone_score(_zones([2.0, 2.0, 2.0, 2.5]))
        self.assertEqual(even, 10.0)
        self.assertAlmostEqual(long, 10.0 - 0.125 * 3.0)

    def test_it_counts_where_the_spread_penalty_is_spent(self):
        # Lines that already vary use up the capped spread penalty; one
        # line running longer still costs more.
        uneven = [1.5, 2.5, 1.6, 2.4]
        longer = [1.5, 2.5, 1.6, 3.4]
        before = dict(_zones(uneven), ascReachCv=0.5)
        after = dict(_zones(longer), ascReachCv=0.6)
        drop = zone_analysis.zone_score(before) - zone_analysis.zone_score(after)
        self.assertGreater(drop, 0.1)

    def test_the_penalty_has_a_ceiling(self):
        z = _zones([2.0, 2.0, 2.0, 2.0], dev=5.0)
        penalty = 10.0 - zone_analysis.zone_score(z)
        self.assertAlmostEqual(penalty, zone_analysis.LINE_DEV_MAX)


def _zigzag(ch, lean, tall):
    """A letter as a zigzag; tall and hanging letters `tall` x-heights,
    long enough that tails touch the next line on planted pages."""
    h = tall if ch in planted.TALL or ch in planted.LOW else 1.0
    xs = np.linspace(0, 0.5 + lean, 6)
    return [
        np.array(list(zip(xs, [0.0 if i % 2 == 0 else h for i in range(6)])))
    ]


class SameWriterSpreadTests(unittest.TestCase):
    def test_same_passage_pages_score_factor_6_alike(self):
        # Two planted pages per pair: the same four sentences in another
        # order, one writer's two versions of each letter picked at
        # random. Before the fix this writer's factor 6 moved by 8.0
        # points between such pages (8.3 against 0.0); the UJI run moved
        # by up to 9.1 (docs/19-comparison-data.md).
        chars = set("".join(planted.SENTENCES).replace(" ", ""))
        letters = {
            ch: [_zigzag(ch, 0.0, 2.4), _zigzag(ch, 0.15, 2.4)] for ch in chars
        }
        pairs = study.synthetic_pairs({"w01": letters}, 6, planted)
        deltas = [abs(a[6] - b[6]) for _, a, b in pairs]
        self.assertEqual(len(deltas), 6)
        self.assertLessEqual(max(deltas), 1.0, deltas)


if __name__ == "__main__":
    unittest.main()
