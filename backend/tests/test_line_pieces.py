# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Every handwritten line is scored once: repeated readings dropped,
pieces of a line joined, the first line of a page kept, and writing the
detector missed read again (detector.py, line_recovery.py).

The cases are the ones found on the UJI test pages on 19 October 2026:
UPV_W18 read one line twice ("seeta ..." and "seetha ...") and lost two,
UPV_W42 gave ten pieces for four lines."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import classify  # noqa: E402
import detector  # noqa: E402
import line_recovery  # noqa: E402
import recognizer  # noqa: E402


def line(text, box, score=0.9, **extra):
    x, y, w, h = box
    return {
        "text": text,
        "box": [float(v) for v in box],
        "poly": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
        "score": score,
        "lang": "en",
        "printed_hint": False,
        **extra,
    }


class TestRepeatedReadings(unittest.TestCase):
    def test_a_line_read_twice_with_different_letters_is_kept_once(self):
        # UPV_W18: the two image variants read the same line.
        out = detector.merge_lines(
            [
                line(
                    "seeta and rama practise slowly with care",
                    [71, 132, 1026, 100],
                    0.920,
                ),
                line(
                    "seetha and rama practise slowly with care",
                    [72, 135, 1025, 96],
                    0.927,
                ),
                line(
                    "pihu sings while tara reads a story",
                    [70, 209, 835, 100],
                    0.920,
                ),
            ]
        )
        self.assertEqual(
            [l["text"] for l in out],
            [
                "seetha and rama practise slowly with care",
                "pihu sings while tara reads a story",
            ],
        )

    def test_a_word_read_alone_gives_way_to_its_whole_line(self):
        whole = line(
            "vahini and bheema write letters every day",
            [65, 281, 1198, 113],
            0.97,
        )
        piece = line("day", [1118, 299, 140, 92], 1.0)
        out = detector.merge_lines([piece, whole])
        self.assertEqual([l["text"] for l in out], [whole["text"]])

    def test_a_confident_piece_does_not_hide_its_whole_line(self):
        # UPV_W42: the piece was read more confidently than the line.
        out = detector.merge_lines(
            [
                line(
                    "vahini and bheema write lettersevery",
                    [70, 139, 1235, 82],
                    0.97,
                ),
                line("bheema write letterseve", [373, 141, 856, 81], 0.99),
                line("vahini and", [73, 146, 318, 71], 0.98),
            ]
        )
        self.assertEqual(
            [l["text"] for l in out], ["vahini and bheema write lettersevery"]
        )

    def test_two_lines_one_above_the_other_both_stay(self):
        out = detector.merge_lines(
            [
                line("seetha and rama", [72, 135, 1025, 96]),
                line("pihu sings while", [70, 209, 835, 100]),
            ]
        )
        self.assertEqual(len(out), 2)


class TestFirstLine(unittest.TestCase):
    def test_a_handwritten_first_line_near_the_top_is_kept(self):
        # A wide, confident line in the top 14% was dropped as a header on
        # most UJI pages.
        first = line(
            "vidhya draws big round letters on the line",
            [67, 51, 971, 105],
            0.79,
        )
        out = detector.region_filter_lines([first], (900, 1400, 3))
        self.assertEqual(out, [first])

    def test_a_printed_header_is_still_dropped(self):
        header = line(
            "ST MARY'S SCHOOL ANNUAL REPORT 2026",
            [60, 20, 1200, 60],
            0.99,
            printed_hint=True,
        )
        written = line("my pain started yesterday", [60, 300, 600, 60])
        out = detector.region_filter_lines([header, written], (900, 1400, 3))
        self.assertEqual(out, [written])


class TestJoinPieces(unittest.TestCase):
    def test_pieces_on_one_baseline_become_one_line(self):
        # UPV_W42, line 3: four pieces of "vidhya draws big round letters
        # on the line".
        pieces = [
            line("drawsbig", [250, 204, 345, 113], 0.94),
            line("roundlettersonthe", [558, 208, 681, 97], 1.0),
            line("vidhya", [79, 224, 208, 70], 0.92),
            line("line", [1239, 241, 117, 43], 1.0),
        ]
        above = line(
            "vahini and bheema write lettersevery", [70, 139, 1235, 82], 0.97
        )
        out = detector.join_row_pieces(pieces + [above])
        self.assertEqual(len(out), 2)
        joined = out[1]
        self.assertEqual(
            joined["text"], "vidhya drawsbig roundlettersonthe line"
        )
        self.assertEqual(joined["joined_pieces"], 4)
        self.assertEqual(joined["box"][0], 79)
        self.assertEqual(joined["box"][0] + joined["box"][2], 1356)
        self.assertEqual(len(joined["poly"]), 4)
        self.assertIs(out[0], above)

    def test_two_columns_stay_apart(self):
        left = line("name of the child", [60, 100, 400, 60])
        right = line("date of the check", [60 + 400 + 5 * 60, 100, 400, 60])
        out = detector.join_row_pieces([left, right])
        self.assertEqual(len(out), 2)

    def test_lines_one_above_the_other_stay_apart(self):
        out = detector.join_row_pieces(
            [
                line("chinnu keeps each word", [67, 143, 1203, 78]),
                line("pihu sings while tara", [61, 212, 1084, 98]),
            ]
        )
        self.assertEqual(len(out), 2)

    def test_a_word_read_again_inside_a_line_is_dropped(self):
        whole = line(
            "seetha and rama practise slowly with cave", [65, 205, 1037, 106]
        )
        again = line("Care", [949, 236, 144, 55], 0.95)
        out = detector.join_row_pieces([whole, again])
        self.assertEqual([l["text"] for l in out], [whole["text"]])

    def test_a_tall_piece_does_not_make_the_line_two_lines_tall(self):
        out = detector.join_row_pieces(
            [
                line("the quick brown fox jumps over", [78, 143, 900, 80]),
                line("dog", [1000, 150, 120, 170]),
            ]
        )
        self.assertEqual(len(out), 1)
        self.assertLessEqual(out[0]["box"][3], 80 * 1.5 + 1)


def page_with_lines(rows, width=1200, height=520):
    """A page with a run of dark 'words' on each row: [(y, [x0, x1] ...)]."""
    arr = np.full((height, width, 3), 235, np.uint8)
    for y, words in rows:
        for x0, x1 in words:
            # Letters: short vertical bars with gaps, 30 px tall.
            for x in range(x0, x1, 12):
                arr[y : y + 30, x : x + 5] = 30
            arr[y + 26 : y + 30, x0:x1] = 30
    return arr


class TestRecovery(unittest.TestCase):
    def setUp(self):
        if line_recovery.cv2 is None:
            self.skipTest("OpenCV unavailable")
        self.arr = page_with_lines(
            [
                (60, [(80, 300), (330, 600), (630, 900)]),
                (140, [(80, 300), (330, 600), (630, 900)]),
                (220, [(80, 300), (330, 600), (630, 900)]),
            ]
        )
        # The reader found lines one and two; line three was missed.
        self.found = [
            line("the quick brown", [75, 52, 830, 46]),
            line("fox jumps over", [75, 132, 830, 46]),
        ]
        self.crops = []

    def read(self, crop, _lang):
        """A stand-in reader: one word over each run of ink in the crop,
        named by its place on the crop."""
        self.crops.append(crop.shape)
        ink = (crop[..., 0] < 128).any(axis=0)
        words, start = [], None
        for x, on in enumerate(list(ink) + [False]):
            if on and start is None:
                start = x
            if not on and start is not None:
                if x - start > 40:
                    h = crop.shape[0]
                    words.append(
                        {
                            "text": f"word{start // 100}",
                            "poly": [
                                [start, 2],
                                [x, 2],
                                [x, h - 2],
                                [start, h - 2],
                            ],
                            "score": 0.9,
                        }
                    )
                start = None
        return words

    def test_the_missed_line_is_found_and_read(self):
        regions = line_recovery.missed_regions(self.arr, self.found)
        self.assertEqual(len(regions), 3)
        for r in regions:
            _x, y, _w, h = r["box"]
            self.assertTrue(200 <= y and y + h <= 260, r["box"])
        out = line_recovery.add_missed(self.arr, self.found, self.read)
        texts = [l["text"] for l in out]
        self.assertEqual(len(out), 5)
        self.assertEqual(texts[:2], ["the quick brown", "fox jumps over"])
        self.assertTrue(all(l.get("recovered") for l in out[2:]))
        joined = detector.join_row_pieces(out)
        self.assertEqual(len(joined), 3)

    def test_a_word_inside_a_found_line_is_not_added_again(self):
        found = self.found + [line("seetha and rama", [75, 212, 830, 46])]
        self.assertEqual(line_recovery.missed_regions(self.arr, found), [])
        out = line_recovery.add_missed(self.arr, found, self.read)
        self.assertEqual(len(out), 3)
        self.assertEqual(self.crops, [])

    def test_a_garbage_reading_does_not_hide_a_line(self):
        # UPV_W51: " n" at 0.43 sat over the whole first line.
        found = self.found + [line(" n", [75, 212, 830, 46], 0.43)]
        out = line_recovery.add_missed(self.arr, found, self.read)
        self.assertNotIn(" n", [l["text"] for l in out])
        self.assertEqual(sum(1 for l in out if l.get("recovered")), 3)

    def test_an_unreadable_crop_adds_nothing(self):
        out = line_recovery.add_missed(
            self.arr, self.found, lambda crop, lang: None
        )
        self.assertEqual(out, self.found)

    def test_same_page_same_lines(self):
        a = line_recovery.add_missed(self.arr, self.found, self.read)
        b = line_recovery.add_missed(self.arr, self.found, self.read)
        self.assertEqual(
            [(l["text"], l["box"]) for l in a],
            [(l["text"], l["box"]) for l in b],
        )

    def test_extract_hand_lines_reads_the_missed_line(self):
        raw = [dict(l) for l in self.found]
        _all, hand = recognizer.extract_hand_lines(
            self.arr, raw, read_region=self.read
        )
        self.assertEqual(len(hand), 3)
        self.assertEqual(len(hand[2]["text"].split()), 3)
        self.assertEqual(hand[2]["joined_pieces"], 3)
        _all, without = recognizer.extract_hand_lines(
            self.arr, [dict(l) for l in self.found]
        )
        self.assertEqual(len(without), 2)


class TestRecoveredWordsKeepThePageContext(unittest.TestCase):
    def test_recovered_words_do_not_let_a_letterhead_through(self):
        # A printed form: confident lines, the top one a letterhead number.
        # Many recovered words below must not dilute the page's print.
        arr = np.full((1300, 800, 3), 240, np.uint8)
        found = [
            line("4309", [460, 28, 60, 27], 0.998),
            line("COUNTY BOROUGH POLICE", [80, 62, 330, 34], 0.97),
            line("CHIEF CONSTABLE'S OFFICE", [380, 115, 175, 14], 0.98),
            line("Received from", [130, 186, 140, 22], 0.97),
        ]
        recovered = [
            line("dear sir", [80, 250 + 40 * i, 200, 30], 0.78, recovered=True)
            for i in range(24)
        ]
        alone = classify.classify_lines(arr, [dict(l) for l in found])
        both = classify.classify_lines(
            arr, [dict(l) for l in found + recovered]
        )
        self.assertTrue(alone[0]["printed_hint"])
        self.assertEqual(
            [l["printed_hint"] for l in both[: len(found)]],
            [l["printed_hint"] for l in alone],
        )


if __name__ == "__main__":
    unittest.main()
