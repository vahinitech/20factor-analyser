# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""scripts/planted_pages.py plants each mistake where it says it did.

Uses drawn rectangles instead of the UJI letters, so it needs no
download."""

import importlib.util
import os
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
spec = importlib.util.spec_from_file_location(
    "planted_pages", os.path.join(ROOT, "scripts", "planted_pages.py")
)
planted = importlib.util.module_from_spec(spec)
spec.loader.exec_module(planted)


def box_letter(ch):
    """A letter as an outline: tall letters twice the small height,
    tails hanging below."""
    h = 2.0 if ch in planted.TALL or ch in planted.LOW else 1.0
    return [np.array([[0, 0], [0.8, 0], [0.8, h], [0, h], [0, 0]])]


LETTERS = {
    ch: [box_letter(ch), box_letter(ch)]
    for ch in set("".join(planted.SENTENCES).replace(" ", ""))
}


class TestPlantedPages(unittest.TestCase):
    def page(self, kind, seed=0):
        rng = np.random.default_rng(seed)
        return planted.build_page(LETTERS, rng, kind)

    def test_every_mistake_has_a_box_on_the_page(self):
        for kind, _skill in planted.KINDS:
            img, lines, truth = self.page(kind)
            self.assertEqual(len(lines), 4)
            if kind == "clean":
                self.assertIsNone(truth)
                continue
            x, y, w, h = truth
            self.assertGreater(w * h, 0, kind)
            self.assertTrue(
                0 <= x and x + w <= img.shape[1] and y + h <= img.shape[0],
                kind,
            )

    def test_small_letters_share_one_height(self):
        self.assertAlmostEqual(planted.writer_scale(LETTERS) * 1.0, planted.X)

    def test_wide_gap_is_three_word_gaps(self):
        _img, _lines, truth = self.page("wide_gap")
        # The letter gap before it varies by 30%, and boxes round outward.
        self.assertAlmostEqual(truth[2], 3 * planted.WORD_GAP, delta=3)

    def test_tall_letter_is_taller(self):
        _img, _lines, truth = self.page("tall_letter")
        self.assertAlmostEqual(truth[3], 1.7 * planted.X, delta=2)

    def test_tilted_line_is_the_last_and_its_outline_slopes(self):
        _img, lines, _truth = self.page("tilted_line")
        (x0, y0), (x1, y1) = lines[-1]["poly"][:2]
        angle = np.degrees(np.arctan2(y1 - y0, x1 - x0))
        self.assertAlmostEqual(angle, planted.TILT_DEG, delta=0.5)

    def test_same_seed_same_page(self):
        a = self.page("low_word", seed=3)
        b = self.page("low_word", seed=3)
        self.assertTrue(np.array_equal(a[0], b[0]))
        self.assertEqual(a[2], b[2])

    def test_covers_measures_the_planted_box_inside_the_mark(self):
        self.assertEqual(planted._covers([0, 0, 10, 10], [2, 2, 4, 4]), 1.0)
        self.assertEqual(planted._covers([0, 0, 10, 10], [8, 0, 4, 10]), 0.5)


if __name__ == "__main__":
    unittest.main()


SPREAD = ("wavy_line", "slanted_line", "shaky_line", "indented_line")


class TestPoorPages(unittest.TestCase):
    """Several mistakes on one page (planted_pages.POOR, #197)."""

    def test_one_mistake_stays_on_its_line(self):
        self.assertEqual(
            planted.mistake_lines(("wavy_line",), 2, 4), {"wavy_line": 2}
        )
        self.assertEqual(
            planted.mistake_lines(("tilted_line",), 3, 4),
            {"tilted_line": 3},
        )

    def test_line_mistakes_spread_over_the_other_lines(self):
        kinds = ("narrow_gap",) + SPREAD + ("tilted_line",)
        at = planted.mistake_lines(kinds, 1, 4)
        self.assertEqual(at["narrow_gap"], 1)
        self.assertEqual(at["tilted_line"], 3)
        self.assertEqual([at[k] for k in SPREAD], [0, 2, 3, 0])

    def test_a_poor_page_is_built_with_no_single_box(self):
        img, lines, truth = planted.build_page(
            LETTERS, np.random.default_rng(0), planted.POOR
        )
        self.assertEqual(len(lines), 4)
        self.assertIsNone(truth)
        clean, _lines, _truth = planted.build_page(
            LETTERS, np.random.default_rng(0), "clean"
        )
        self.assertNotEqual(img.tobytes(), clean.tobytes())

    def test_one_mistake_as_a_tuple_is_the_same_page(self):
        a = planted.build_page(LETTERS, np.random.default_rng(3), "wide_gap")
        b = planted.build_page(
            LETTERS, np.random.default_rng(3), ("wide_gap",)
        )
        self.assertEqual(a[0].tobytes(), b[0].tobytes())
        self.assertEqual(a[2], b[2])


class TestRuledPages(unittest.TestCase):
    """Pages on a printed four-line ruling (#194)."""

    def test_the_ruling_changes_the_paper_not_the_writing(self):
        plain = planted.build_page(LETTERS, np.random.default_rng(5), "clean")
        ruled = planted.build_page(
            LETTERS, np.random.default_rng(5), "clean", ruled=True
        )
        self.assertEqual(plain[1], ruled[1])
        self.assertNotEqual(plain[0].tobytes(), ruled[0].tobytes())

    def test_four_rules_under_each_line(self):
        rules = planted.ruling([100.0, 180.0], 600)
        self.assertEqual(len(rules), 8)
        ys = [r[0] for r in rules[:4]]
        self.assertEqual(ys, [100 - 2 * planted.X, 100 - planted.X, 100, 124])
        self.assertTrue(rules[1][3])  # the midline is dashed
        mask = planted._rule_mask(rules, 600, 300)
        self.assertEqual(mask[100, 300], planted.RULE_ALPHA)
        self.assertEqual(mask[100, 10], 0.0)
