# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""A line the printed rules call print is set aside only when a second
sign agrees: the line reader sees print, or the ink repeats like a font
(classify.font_evidence, #202).

Neat handwriting has even strokes, even letters and reads confidently,
which is all the rules look at, so on real phone photos they set aside a
share of the neatest pages. Every picture here is drawn by the test: a
line rendered in Pillow's own font, and neat handwriting-like lines of
separate letters drawn as strokes, each letter a little different in
shape, size and position, as a pen makes them. The line reader is
replaced by a fixed answer, so each test checks one sign at a time."""

import os
import sys
import unittest
from unittest import mock

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from reading import classify  # noqa: E402

# White-box tests reach into the module's private helpers.
# pylint: disable=protected-access

# The reader's answer when it cannot tell: neither handwriting (below
# READER_HAND_BELOW) nor print (READER_PRINT_FROM and up).
READER_UNSURE = 0.3
READER_PRINT = 0.9


def font_line(text, size=28):
    """One line of text in Pillow's built-in font."""
    font = ImageFont.load_default(size=size)
    image = Image.new("RGB", (16 * len(text) + 40, int(size * 1.8)), "white")
    ImageDraw.Draw(image).text(
        (10, int(size * 0.3)), text, font=font, fill=(20, 20, 20)
    )
    return np.array(image)


def hand_line(seed, letters=10, x_height=22):
    """Neat handwriting-like ink: separate letters (o, a, n, l shapes)
    drawn as strokes, each with its own small changes in size, slant,
    pen width, shape and position on the line, as a pen makes them."""
    rng = np.random.default_rng(seed)
    width = letters * int(x_height * 1.3) + 40
    image = np.full((int(x_height * 3.2), width, 3), 250, np.uint8)
    x, base = 14, int(x_height * 2.4)
    for i in range(letters):
        h = x_height * rng.uniform(0.9, 1.1)
        w = x_height * rng.uniform(0.7, 0.95)
        bottom = base + rng.normal(0, 1.2) + 1.5 * np.sin(i / 2.0)
        slant = rng.uniform(0.05, 0.25)
        u, v = LETTERS["oanl"[i % 4]](rng)
        # The pen drifts a little along the stroke.
        u = u + np.cumsum(rng.normal(0, 0.03, len(u)))
        v = v + np.cumsum(rng.normal(0, 0.03, len(v)))
        pts = np.stack(
            [x + w * u + slant * h * (1 - v), bottom - h * (1 - v)], 1
        )
        cv2.polylines(
            image,
            [pts.astype(np.int32).reshape(-1, 1, 2)],
            False,
            (30, 30, 40),
            int(rng.integers(2, 4)),
            cv2.LINE_AA,
        )
        x += int(w + x_height * rng.uniform(0.3, 0.5))
    return image


def _oval(rng, stem=False):
    t = np.linspace(0.3, 0.3 + 2 * np.pi * rng.uniform(0.85, 1.0), 40)
    u, v = 0.5 + 0.5 * np.cos(t), 0.5 + 0.5 * np.sin(t)
    if stem:
        u, v = np.append(u, [1.0, 1.0]), np.append(v, [0.0, 1.0])
    return u, v


def _arch(_rng):
    t = np.linspace(np.pi, 0, 30)
    u = np.concatenate([[0, 0], 0.5 + 0.5 * np.cos(t), [1.0]])
    v = np.concatenate([[1, 0.2], 0.4 - 0.4 * np.sin(t), [1.0]])
    return u, v


def _loop(_rng):
    u = np.array([0.4, 0.5, 0.55, 0.5, 0.35, 0.45, 0.8])
    v = np.array([1.0, 0.3, -0.4, -0.9, -0.5, 0.6, 1.0])
    return u, v


# Letter shapes in a unit box (u across, v down from the top of the
# small letters; below 0 is an ascender).
LETTERS = {
    "o": _oval,
    "a": lambda rng: _oval(rng, stem=True),
    "n": _arch,
    "l": _loop,
}


def page(crops):
    """Lay the crops on one white page, one under the other; returns the
    page and each crop's box."""
    width = max(c.shape[1] for c in crops) + 40
    height = sum(c.shape[0] + 30 for c in crops) + 30
    arr = np.full((height, width, 3), 250, np.uint8)
    boxes, y = [], 30
    for c in crops:
        arr[y : y + c.shape[0], 20 : 20 + c.shape[1]] = c
        boxes.append([20, y, c.shape[1], c.shape[0]])
        y += c.shape[0] + 30
    return arr, boxes


def classify_page(rows, rules=None):
    """rows: (crop, text, reader confidence, line reader's answer), top
    to bottom. rules: {text: printed probability} to fix what the rules
    say for those lines; the ink is measured as usual. Returns the
    classified lines."""
    arr, boxes = page([crop for crop, _t, _s, _r in rows])
    lines = [
        {"text": text, "score": score, "box": box}
        for (_c, text, score, _r), box in zip(rows, boxes)
    ]
    answers = iter([reader for _c, _t, _s, reader in rows])
    real = classify.printed_probability

    def probability(crop, text, score, box):
        prob, feat = real(crop, text, score, box)
        return (rules or {}).get(text, prob), feat

    with mock.patch.object(
        classify, "_reader_says_print", side_effect=lambda _c: next(answers)
    ), mock.patch.object(
        classify, "printed_probability", side_effect=probability
    ):
        classify.classify_lines(arr, lines)
    return lines


def form_rows(count):
    """Printed form labels the reader is sure of."""
    return [
        (font_line(f"Form label {i}"), f"Form label {i}", 0.99, READER_PRINT)
        for i in range(count)
    ]


def hand_rows(seeds, text="we went to", score=0.7):
    return [(hand_line(seed), text, score, READER_UNSURE) for seed in seeds]


class TestFontEvidence(unittest.TestCase):
    def test_a_font_line_shows_a_font(self):
        for text in ("Name of the school", "Date of admission", "Received"):
            for size in (16, 20, 28, 40):
                ink = classify.font_evidence(font_line(text, size))
                self.assertEqual(ink["verdict"], "font", (text, size, ink))

    def test_neat_handwriting_is_not_a_font(self):
        verdicts = [
            classify.font_evidence(hand_line(seed))["verdict"]
            for seed in range(20)
        ]
        self.assertNotIn("font", verdicts)
        # Some lines have enough same-size letters to be measured.
        self.assertIn("hand", verdicts)

    def test_too_few_letters_is_unsure(self):
        ink = classify.font_evidence(hand_line(0, letters=2))
        self.assertEqual(ink["verdict"], "unsure")
        blank = np.full((40, 200, 3), 250, np.uint8)
        self.assertEqual(classify.font_evidence(blank)["verdict"], "unsure")


class TestSecondSign(unittest.TestCase):
    def test_neat_handwriting_read_confidently_stays_handwriting(self):
        # A confident, clean reading of six or more characters reaches
        # the override (0.85); with no second sign the line is kept.
        for line in classify_page(
            hand_rows(range(4), "we went to the park", 0.99)
        ):
            self.assertGreaterEqual(
                line["printed_prob"], classify.PRINTED_THRESHOLD
            )
            self.assertFalse(line["printed_hint"])
            self.assertEqual(line["print_check"], "kept_no_second_sign")

    def test_a_font_line_stays_printed_when_the_reader_is_unsure(self):
        label = "Name of the school"
        rows = [(font_line(label), label, 0.99, READER_UNSURE)]
        lines = classify_page(rows + hand_rows(range(3)))
        self.assertTrue(lines[0]["printed_hint"])
        self.assertEqual(lines[0]["print_check"], "font_ink")
        for line in lines[1:]:
            self.assertFalse(line["printed_hint"])

    def test_the_reader_seeing_print_is_a_second_sign(self):
        rows = [(hand_line(0), "we went to the park", 0.99, READER_PRINT)]
        lines = classify_page(rows + hand_rows(range(1, 4)))
        self.assertTrue(lines[0]["printed_hint"])
        self.assertEqual(lines[0]["print_check"], "reader")

    def test_on_a_printed_page_the_rules_decide(self):
        # Most lines show a second sign: the page is printed, and a line
        # the rules call print is set aside without one of its own.
        rows = form_rows(4) + hand_rows([0], "Signature of parent", 0.99)
        lines = classify_page(rows)
        self.assertTrue(lines[-1]["printed_hint"])
        self.assertEqual(lines[-1]["print_check"], "printed_page")

    def test_a_short_label_follows_the_rules_on_a_form(self):
        # "No." is too short for the reader or the ink to judge. On a
        # page where a quarter of the lines show print, the rules decide.
        rows = form_rows(2) + hand_rows(range(4))
        rows.append((font_line("No."), "No.", 0.99, READER_UNSURE))
        lines = classify_page(rows, rules={"No.": 0.7})
        self.assertTrue(lines[-1]["printed_hint"])
        self.assertEqual(lines[-1]["print_check"], "short_on_form")

    def test_a_short_word_on_a_handwriting_page_is_kept(self):
        rows = hand_rows(range(5))
        rows.append((hand_line(9, letters=3), "day", 0.99, READER_UNSURE))
        lines = classify_page(rows, rules={"day": 0.7})
        self.assertEqual(lines[-1]["printed_prob"], 0.7)
        self.assertFalse(lines[-1]["printed_hint"])
        self.assertEqual(lines[-1]["print_check"], "kept_no_second_sign")

    def test_the_summary_says_why(self):
        lines = classify_page(hand_rows(range(2), "we went to the park", 0.99))
        summary = classify.classification_summary(lines, lines)
        for row in summary["handwritten"]:
            self.assertEqual(row["print_check"], "kept_no_second_sign")


if __name__ == "__main__":
    unittest.main()
