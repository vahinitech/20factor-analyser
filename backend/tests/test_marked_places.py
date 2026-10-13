# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The places the report circles for the free skills (marked_places.py)."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import computer_vision as vision


def line(x, y, w, h, rise=0, text="sample words", score=0.9):
    return {
        "box": [x, y, w, h],
        "text": text,
        "score": score,
        "poly": [[x, y], [x + w, y + rise], [x + w, y + h], [x, y + h]],
    }


def ink_line(arr, y, gaps, h=30, word=60, x0=20):
    """Draw solid ink 'words' separated by the given gaps; return the
    OCR-style line record covering them."""
    x = x0
    for gap in list(gaps) + [0]:
        arr[y : y + h, x : x + word] = 20
        x += word + gap
    text = " ".join(["word"] * (len(gaps) + 1))
    return line(x0 - 5, y - 5, x - x0 + 10, h + 10, text=text)


def places(result, n, role="look"):
    return [p for p in result[n].get("places", []) if p["role"] == role]


class TestMarkedPlaces(unittest.TestCase):
    def test_size_circles_the_lines_furthest_from_the_median(self):
        arr = np.full((400, 500, 3), 255, np.uint8)
        lines = [line(30, 10 + i * 40, 300, 30) for i in range(5)]
        lines.append(line(30, 230, 100, 12))
        lines.append(line(30, 280, 300, 50))
        result = vision._factor_region_map(arr, [], lines)
        look = places(result, "5")
        self.assertEqual(
            [p["bbox"] for p in look], [[30, 280, 300, 50], [30, 230, 100, 12]]
        )
        self.assertEqual([p["direction"] for p in look], ["taller", "shorter"])
        self.assertEqual(look[0]["reference"], 30.0)
        self.assertEqual(look[0]["deviation"], 0.667)
        self.assertEqual(look[1]["deviation"], 0.6)
        keep = places(result, "5", "keep")
        self.assertEqual(len(keep), 1)
        self.assertEqual(keep[0]["direction"], "even")

    def test_even_page_gets_no_size_circle(self):
        arr = np.full((300, 500, 3), 255, np.uint8)
        lines = [line(30, 10 + i * 40, 300, 30) for i in range(5)]
        result = vision._factor_region_map(arr, [], lines)
        self.assertEqual(places(result, "5"), [])

    def test_angle_circles_tilted_lines_only(self):
        arr = np.full((400, 700, 3), 255, np.uint8)
        lines = [line(30, 10 + i * 50, 500, 30) for i in range(4)]
        lines.append(line(30, 250, 500, 30, rise=35))  # about 4 degrees
        lines.append(line(30, 320, 500, 30, rise=9))  # about 1 degree
        result = vision._factor_region_map(arr, [], lines)
        look = places(result, "7")
        self.assertEqual(len(look), 1)
        self.assertEqual(look[0]["region_id"], "line_5")
        self.assertGreater(look[0]["value"], 3.9)
        self.assertEqual(places(result, "7", "keep")[0]["value"], 0.0)

    def test_reading_marks_lines_below_reliable_confidence(self):
        arr = np.full((300, 500, 3), 255, np.uint8)
        lines = [
            line(30, 10, 300, 30, score=0.95),
            line(30, 60, 300, 30, score=0.60),
            line(30, 110, 300, 30, score=0.80),
        ]
        result = vision._factor_region_map(arr, [], lines)
        look = places(result, "1")
        self.assertEqual([p["region_id"] for p in look], ["line_2", "line_3"])
        self.assertEqual(look[0]["line_confidence"], 0.6)
        self.assertEqual(places(result, "1", "keep")[0]["region_id"], "line_1")

    def test_word_gaps_inside_a_line_are_circled_exactly(self):
        if vision.cv2 is None:
            self.skipTest("OpenCV unavailable")
        arr = np.full((160, 700, 3), 255, np.uint8)
        lines = [ink_line(arr, 40, (20, 20, 70, 20))]
        result = vision._factor_region_map(arr, [], lines)
        look = places(result, "8")
        self.assertEqual(len(look), 1)
        gap = look[0]
        self.assertEqual(gap["kind"], "gap")
        self.assertEqual(gap["direction"], "wider")
        # The third word ends at 20 + 3*60 + 2*20 = 240 and the fourth
        # starts 70 px later.
        self.assertEqual(gap["bbox"][0], 240)
        self.assertEqual(gap["bbox"][2], 70)
        # The crop moves from the whole page to the line holding it.
        self.assertEqual(
            result["8"]["selection_method"], "ink-word-gap-deviation"
        )
        self.assertEqual(result["8"]["status"], "measurement")
        # The gaps are the scorer's gaps.
        self.assertEqual(
            sorted(vision.line_word_gaps(arr, lines[0])),
            [20.0, 20.0, 20.0, 70.0],
        )

    def test_legibility_takes_places_from_its_parts(self):
        arr = np.full((400, 700, 3), 255, np.uint8)
        lines = [line(30, 10 + i * 50, 500, 30) for i in range(4)]
        lines.append(line(30, 250, 500, 30, rise=35, score=0.5))
        lines.append(line(30, 320, 200, 10))
        result = vision._factor_region_map(arr, [], lines)
        merged = result["18"]["places"]
        self.assertTrue(1 <= len(merged) <= 3)
        self.assertEqual(merged[0]["from_factor"], 1)
        self.assertTrue(all(p["role"] == "look" for p in merged))
        self.assertEqual(len({tuple(p["bbox"]) for p in merged}), len(merged))

    def test_nothing_read_means_no_reading_places(self):
        arr = np.full((300, 500, 3), 255, np.uint8)
        lines = [
            line(30, 10 + i * 40, 300, 30, text="", score=0.0)
            for i in range(4)
        ]
        result = vision._factor_region_map(arr, [], lines)
        for n in ("1", "7", "8", "18"):
            self.assertNotIn("places", result[n])
        self.assertIn("places", result["5"])

    def test_same_page_same_places(self):
        if vision.cv2 is None:
            self.skipTest("OpenCV unavailable")
        arr = np.full((260, 700, 3), 255, np.uint8)
        lines = [
            ink_line(arr, 40, (20, 60, 20)),
            ink_line(arr, 140, (25, 20, 15, 20)),
        ]
        first = vision._factor_region_map(arr, [], [dict(l) for l in lines])
        second = vision._factor_region_map(arr, [], [dict(l) for l in lines])
        for n in ("1", "5", "7", "8", "18"):
            self.assertEqual(first[n].get("places"), second[n].get("places"))


if __name__ == "__main__":
    unittest.main()
