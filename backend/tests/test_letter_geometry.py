# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Word and letter measurements inside a line (letter_geometry.py), on
pages from scripts/planted_pages.py written with drawn boxes for
letters, so no download is needed."""

import importlib.util
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import letter_geometry as lg  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
spec = importlib.util.spec_from_file_location(
    "planted_pages", os.path.join(ROOT, "scripts", "planted_pages.py")
)
planted = importlib.util.module_from_spec(spec)
spec.loader.exec_module(planted)


def box_letter(ch):
    """A zigzag filling the letter's height, like an m or a w: its ink is
    spread evenly from top to bottom, as in a real letter's body."""
    h = 2.0 if ch in planted.TALL or ch in planted.LOW else 1.0
    xs = np.linspace(0, 0.5, 6)
    ys = [0.0 if i % 2 == 0 else h for i in range(6)]
    return [np.array(list(zip(xs, ys)))]


LETTERS = {
    ch: [box_letter(ch)]
    for ch in set("".join(planted.SENTENCES).replace(" ", ""))
}


def page(kind, seed=0):
    rng = np.random.default_rng(seed)
    img, lines, truth = planted.build_page(LETTERS, rng, kind, "plain")
    for i, line in enumerate(lines):
        line["evidence_id"] = f"line_{i + 1}"
    return img, lines, truth, lg.measure_page(img, lines)


def joined_page(sentences, xh=24, pen=3):
    """Joined writing drawn as it looks: each small letter a round body
    one x-height tall, each tall letter (b, d, h, k, l, t) a narrow loop
    two x-heights tall beside its body, each tail (g, j, p, q, y) a loop
    hanging one below, letters joined along the baseline. Returns the
    page and one reader-shaped line per sentence."""
    img = np.full((80 + 90 * len(sentences), 1300, 3), 245, np.uint8)
    lines = []
    for li, sentence in enumerate(sentences):
        base = 80 + li * 90
        x = 60
        for word in sentence.split():
            start = x
            for ch in word:
                if ch in "bdhklt":
                    lg.cv2.ellipse(
                        img,
                        (x + 3, base - xh),
                        (3, xh),
                        0,
                        0,
                        360,
                        (40, 40, 40),
                        pen,
                    )
                if ch in "gjpqy":
                    lg.cv2.ellipse(
                        img,
                        (x + 3, base),
                        (3, xh),
                        0,
                        0,
                        360,
                        (40, 40, 40),
                        pen,
                    )
                lg.cv2.ellipse(
                    img,
                    (x + 9, base - xh // 2),
                    (6, xh // 2),
                    0,
                    0,
                    360,
                    (40, 40, 40),
                    pen,
                )
                x += 16
            lg.cv2.line(img, (start, base), (x - 4, base), (40, 40, 40), pen)
            x += 26
        top, bottom = base - 2 * xh - pen, base + xh + pen
        lines.append(
            {
                "text": sentence,
                "box": [55, top, x - 55, bottom - top],
                "poly": [[55, top], [x, top], [x, bottom], [55, bottom]],
                "score": 0.9,
            }
        )
    return img, lines


class TestLetterGeometry(unittest.TestCase):
    def setUp(self):
        if lg.cv2 is None:
            self.skipTest("OpenCV unavailable")

    def test_placed_letter_heights_find_the_tall_letter(self):
        # Letters placed where they really are (as a perfect reader
        # would), measured from the ink in each slot.
        rng = np.random.default_rng(0)
        truth = []
        img, lines, planted_box = planted.build_page(
            LETTERS, rng, "tall_letter", "plain", letters_out=truth
        )
        gray = lg.cv2.cvtColor(img, lg.cv2.COLOR_RGB2GRAY)
        geo = lg.measure_page(img, lines)
        sizes = []
        for li, (line, _g) in enumerate(zip(lines, geo)):
            placed = [
                {"char": t["ch"], "bbox": t["bbox"]}
                for t in truth
                if t["line"] == li
            ]
            sizes += lg.placed_letter_heights(gray, line, placed)
        self.assertTrue(sizes)
        lg.same_letter_ratios(sizes)
        self.assertTrue(all(s["char"] in lg.SMALL_LETTERS for s in sizes))
        top = max(sizes, key=lambda s: s["ratio"])
        x, y, w, h = top["bbox"]
        tx, ty, tw, th = planted_box
        self.assertTrue(tx <= x + w / 2 <= tx + tw)
        self.assertGreater(top["ratio"], 1.4)
        others = [s["ratio"] for s in sizes if s is not top]
        self.assertLess(abs(float(np.median(others)) - 1.0), 0.2)

    def test_placed_letter_heights_need_letters(self):
        img, lines, _truth, _geo = page("clean")
        gray = lg.cv2.cvtColor(img, lg.cv2.COLOR_RGB2GRAY)
        self.assertEqual(lg.placed_letter_heights(gray, lines[0], []), [])

    def test_level_lines_measure_level(self):
        _img, _lines, _truth, geo = page("clean")
        for g in geo:
            self.assertLess(g["angle"], 0.5)

    def test_sinking_line_angle_is_measured(self):
        _img, _lines, _truth, geo = page("tilted_line")
        self.assertAlmostEqual(geo[-1]["angle"], planted.TILT_DEG, delta=0.5)

    def test_tilt_barely_changes_x_height(self):
        # A sloping line's box grows by its width times the slope; the
        # x-height, measured along the fitted baseline, does not.
        _i, flat_lines, _t, flat = page("clean", seed=4)
        _i, tilted_lines, _t, tilted = page("tilted_line", seed=4)
        box_growth = tilted_lines[-1]["box"][3] / flat_lines[-1]["box"][3]
        xh_growth = tilted[-1]["xheight"] / flat[-1]["xheight"]
        self.assertGreater(box_growth, 1.2)
        self.assertLess(abs(xh_growth - 1), 0.15)

    def test_sunken_word_is_marked(self):
        _img, lines, truth, geo = page("low_word")
        marks = lg.baseline_marks(lines, geo)
        self.assertTrue(marks)
        self.assertEqual(marks[0]["kind"], "word")
        self.assertEqual(marks[0]["direction"], "below")
        self.assertGreaterEqual(planted._covers(marks[0]["bbox"], truth), 0.5)

    def test_tall_small_letter_stands_out_most(self):
        # Whether it is marked depends on LETTER_LOOK, set on real writers;
        # the measurement must rank it first either way.
        _img, _lines, truth, geo = page("tall_letter")
        letters = [let for g in geo for let in g["letters"]]
        top = max(letters, key=lambda let: abs(let["ratio"] - 1))
        self.assertGreaterEqual(planted._covers(top["bbox"], truth), 0.5)
        self.assertGreater(top["ratio"], 1.4)

    def test_narrow_word_gap_is_found_from_the_text(self):
        _img, lines, truth, geo = page("narrow_gap")
        marks = lg.spacing_marks(lines, geo)
        self.assertTrue(
            any(planted._covers(m["bbox"], truth) >= 0.5 for m in marks)
        )
        self.assertEqual(marks[0]["direction"], "narrower")

    def test_clean_page_has_no_marks(self):
        _img, lines, _truth, geo = page("clean")
        self.assertEqual(lg.size_marks(lines, geo), [])
        self.assertEqual(lg.baseline_marks(lines, geo), [])

    def test_tall_letters_do_not_make_a_word_look_bigger(self):
        # "the", "dog" and "day" scored as size changes on joined writing
        # (UPV_W57, 19 October 2026): the densest band of rows ran up into
        # their loops. Every word here has the same small-letter body.
        img, lines = joined_page(
            [
                "the little hill was on the dog",
                "a small ball fell on her head",
                "we use some more ink every day",
            ]
        )
        geo = lg.measure_page(img, lines)
        words = [
            (word, wd["xheight"])
            for line, g in zip(lines, geo)
            for word, wd in zip(line["text"].split(), g["words"])
        ]
        heights = [h for _w, h in words if h]
        self.assertEqual(len(heights), 21)
        median = float(np.median(heights))
        for word, h in words:
            self.assertIsNotNone(h, word)
            self.assertLess(abs(h - median) / median, 0.2, word)
        cv = float(np.std(heights, ddof=1) / np.mean(heights))
        self.assertLess(cv, 0.08)

    def test_a_word_s_lean_is_measured(self):
        for lean in (-20, 0, 25):
            mask = np.zeros((60, 200), np.uint8)
            t = np.tan(np.radians(lean))
            for x in range(20, 180, 20):
                # Upright strokes leaning by `lean` degrees.
                lg.cv2.line(mask, (x, 59), (int(round(x + 59 * t)), 0), 1, 3)
            got = lg._slant(mask.astype(bool))  # pylint: disable=W0212
            self.assertAlmostEqual(got, lean, delta=lg.SLANT_STEP)

    def test_closed_bowls_are_counted_and_open_ones_are_not(self):
        closed = np.zeros((60, 200), np.uint8)
        opened = np.zeros((60, 200), np.uint8)
        for x in (30, 80, 130):
            lg.cv2.circle(closed, (x, 35), 12, 1, 3)
            lg.cv2.ellipse(opened, (x, 35), (12, 12), 0, 40, 320, 1, 3)
        self.assertEqual(lg._bowls(closed.astype(bool), 30), 3)  # noqa
        self.assertEqual(lg._bowls(opened.astype(bool), 30), 0)  # noqa

    def test_a_wavy_line_wanders_off_its_baseline(self):
        flat = [[x, 70, x + 15, 100] for x in range(0, 300, 25)]
        wavy = [
            [x, 70, x + 15, 100 + int(round(8 * np.sin(i)))]
            for i, x in enumerate(range(0, 300, 25))
        ]
        tails = flat[:-2] + [[250, 70, 265, 130], [275, 70, 290, 130]]
        self.assertEqual(lg._wave(flat, 0.0, 100.0, 30), 0.0)  # noqa
        self.assertGreater(lg._wave(wavy, 0.0, 100.0, 30), 0.15)  # noqa
        # Tails hanging below the line are not wander.
        self.assertEqual(lg._wave(tails, 0.0, 100.0, 30), 0.0)  # noqa

    def test_same_page_same_measurements(self):
        a = page("low_word", seed=7)[3]
        b = page("low_word", seed=7)[3]
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
