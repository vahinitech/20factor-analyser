# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Lines, baselines, letter sizes and word gaps from the ink alone
(ink_geometry.py), for handwriting the reader cannot read, on drawn
pages shaped like Telugu: round letter bodies, some with a stroke
written below the line as a separate mark (a vattu). And joined cursive
read in pieces (#277), on drawn pages written one stroke a word."""

import contextlib
import importlib.util
import os
import sys
import unittest
from unittest import mock

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
sys.path.insert(0, SERVER_DIR)
import ink_geometry as ig  # noqa: E402
import scoring  # noqa: E402

cv2 = ig.cv2
BODY = 40


def draw_page(rows, tilt_last=0.0, wide_after=None):
    """rows: words per row, each word a number of letters. Every third
    letter has a vattu under it. tilt_last: degrees the last row sinks.
    wide_after: (row, word) after which the gap is three times wider."""
    img = np.full((140 + 150 * len(rows), 1500, 3), 236, np.uint8)
    for ri, words in enumerate(rows):
        base = 120 + ri * 150
        x = 80
        for wi, letters in enumerate(words):
            for li in range(letters):
                cx = x + 18
                drop = 0
                if tilt_last and ri == len(rows) - 1:
                    drop = int(
                        round((cx - 80) * np.tan(np.radians(tilt_last)))
                    )
                cy = base - BODY // 2 + drop
                cv2.ellipse(
                    img, (cx, cy), (15, BODY // 2), 0, 0, 360, (40, 30, 90), 3
                )
                if (li + wi) % 3 == 0:  # a vattu, apart, under the letter
                    cv2.line(
                        img,
                        (cx - 10, base + 16 + drop),
                        (cx + 12, base + 26 + drop),
                        (40, 30, 90),
                        3,
                    )
                x += 44
            gap = 70
            if wide_after == (ri, wi):
                gap *= 3
            x += gap
    return img


SENTENCE = [3, 4, 3, 2]
LETTER_W = 28


def draw_cursive(rows=4, words=4, letters=7):
    """Joined cursive: each word one unbroken stroke, a garland of
    letters, so the pen never lifts inside a word. Returns the page and
    each row's word boxes."""
    img = np.full((140 + 150 * rows, 1200, 3), 236, np.uint8)
    boxes = []
    for ri in range(rows):
        base = 120 + ri * 150
        x = 80
        row = []
        for _ in range(words):
            width = letters * LETTER_W
            xs = np.arange(x, x + width + 1)
            phase = 2 * np.pi * (xs - x) / LETTER_W
            ys = base - BODY / 2.0 * (1 + np.cos(phase))
            pts = np.stack([xs, ys], axis=1).round().astype(np.int32)
            stroke = pts.reshape(-1, 1, 2)
            cv2.polylines(img, [stroke], False, (40, 30, 90), 3)
            row.append([x, base - BODY - 2, width, BODY + 4])
            x += width + 60
        boxes.append(row)
    return img, boxes


def reader_line(box, text):
    x, y, w, h = box
    return {
        "text": text,
        "score": 0.6,
        "box": [float(v) for v in box],
        "poly": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
        "lang": "en",
        "printed_hint": False,
    }


def pieces(boxes):
    """The reader's lines on a joined page, as PP-OCRv5 reads it: the
    first word of each row, the rest of the row unread."""
    return [reader_line(row[0], "minimum") for row in boxes]


def whole_lines(boxes):
    """The same rows read whole, one box a row."""
    out = []
    for row in boxes:
        x0, y0 = row[0][0], row[0][1]
        x1 = row[-1][0] + row[-1][2]
        box = [x0, y0, x1 - x0, row[0][3]]
        out.append(reader_line(box, "minimum " * 4))
    return out


class TestInkGeometry(unittest.TestCase):
    def setUp(self):
        if cv2 is None:
            self.skipTest("OpenCV unavailable")

    def test_every_row_is_found_once(self):
        arr = draw_page([SENTENCE] * 4)
        rows = ig.find_rows(arr)
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(r["ink_row"] and r["text"] == "" for r in rows))

    def test_a_sinking_row_stays_one_row_and_measures_its_slope(self):
        arr = draw_page([SENTENCE] * 4, tilt_last=4.0)
        rows = ig.find_rows(arr)
        self.assertEqual(len(rows), 4)
        geo = ig.measure_page(arr, rows)
        self.assertAlmostEqual(geo[-1]["angle"], 4.0, delta=0.6)
        for g in geo[:-1]:
            self.assertLess(g["angle"], 0.5)

    def test_strokes_below_the_line_do_not_move_the_baseline(self):
        arr = draw_page([SENTENCE] * 3)
        geo = ig.measure_page(arr, ig.find_rows(arr))
        for ri, g in enumerate(geo):
            (_x0, y0), (_x1, y1) = g["baseline"]
            base = 120 + ri * 150
            self.assertLess(abs(y0 - base), 6)
            self.assertLess(abs(y1 - base), 6)

    def test_known_word_counts_find_the_words_and_the_wide_gap(self):
        arr = draw_page([SENTENCE] * 3, wide_after=(1, 1))
        rows = ig.find_rows(arr)
        geo = ig.measure_page(arr, rows, [4, 4, 4])
        self.assertEqual([len(g["words"]) for g in geo], [4, 4, 4])
        gaps = [gp["gap"] for gp in geo[1]["gaps"]]
        self.assertEqual(gaps.index(max(gaps)), 1)
        self.assertGreater(max(gaps), 2.5 * min(gaps))

    def test_words_are_not_guessed_when_gaps_do_not_split(self):
        self.assertIsNone(ig.word_gap_split([30, 34, 38, 41, 45, 50, 55]))
        split = ig.word_gap_split([5, 6, 7, 6, 5, 20, 22, 6, 5, 21])
        self.assertTrue(7 < split < 20)

    def test_a_passage_gives_each_row_its_words(self):
        rows = [{"box": [0, 0, 10, 10]}, {"box": [0, 20, 10, 10]}]
        ig.expect_words(rows, "ఒకటి రెండు\nమూడు నాలుగు ఐదు\n")
        self.assertEqual([r["words_expected"] for r in rows], [2, 3])
        rows = [{"box": [0, 0, 10, 10]}]
        ig.expect_words(rows, "one line\nanother line")
        self.assertNotIn("words_expected", rows[0])

    def test_same_page_same_measurements(self):
        arr = draw_page([SENTENCE] * 3, tilt_last=2.0)
        a = ig.measure_page(arr, ig.find_rows(arr))
        b = ig.measure_page(arr, ig.find_rows(arr))
        self.assertEqual(a, b)


class TestInkScores(unittest.TestCase):
    def setUp(self):
        if cv2 is None:
            self.skipTest("OpenCV unavailable")

    def factors(self, arr, rows):
        result = scoring.build_analysis(arr, rows, {})
        return {r.n: r for r in result.results}

    def test_geometry_is_measured_and_reading_is_not(self):
        arr = draw_page([SENTENCE] * 4)
        f = self.factors(arr, ig.find_rows(arr))
        for n in (5, 7, 11, 12, 20):
            self.assertFalse(f[n].unmeasured, n)
        for n in (1, 2, 3, 9, 17, 18, 19):
            self.assertTrue(f[n].unmeasured, n)
        self.assertGreater(f[7].score, 9.0)
        self.assertTrue(f[5].based_on.endswith("letter groups"))
        # Words are not known without a passage.
        self.assertTrue(f[8].unmeasured)

    def test_a_sinking_row_lowers_baseline_alignment(self):
        level = draw_page([SENTENCE] * 4)
        sinking = draw_page([SENTENCE] * 4, tilt_last=4.0)
        a = self.factors(level, ig.find_rows(level))[7].score
        b = self.factors(sinking, ig.find_rows(sinking))[7].score
        self.assertGreater(a - b, 0.8)

    def test_a_passage_measures_word_spacing(self):
        even = draw_page([SENTENCE] * 4)
        wide = draw_page([SENTENCE] * 4, wide_after=(2, 1))
        scores = []
        for arr in (even, wide):
            rows = ig.find_rows(arr)
            ig.expect_words(rows, "\n".join(["అ ఆ ఇ ఈ"] * 4))
            f8 = self.factors(arr, rows)[8]
            self.assertFalse(f8.unmeasured)
            scores.append(f8.score)
        self.assertGreater(scores[0] - scores[1], 1.0)


class TestReadInPieces(unittest.TestCase):
    """Joined cursive read in pieces is measured from the ink (#277)."""

    def setUp(self):
        if cv2 is None:
            self.skipTest("OpenCV unavailable")
        self.arr, self.boxes = draw_cursive()

    def test_a_page_read_in_pieces_is_found(self):
        rows, cover = ig.fragment_rows(self.arr, pieces(self.boxes))
        self.assertEqual(len(rows), 4)
        self.assertTrue(cover["fragments"])
        self.assertLess(cover["cover"], ig.FRAGMENT_COVER)

    def test_the_same_page_read_whole_stays_on_the_reader(self):
        rows, cover = ig.fragment_rows(self.arr, whole_lines(self.boxes))
        self.assertEqual(rows, [])
        self.assertFalse(cover["fragments"])
        # Plainly whole: the ink is not looked at.
        self.assertFalse(cover["looked"])
        _rows, cover = ig.reader_rows(self.arr, whole_lines(self.boxes))
        self.assertFalse(ig.read_in_fragments(cover))
        self.assertGreater(cover["cover"], 0.95)
        self.assertEqual(cover["per_row"], 1)
        self.assertEqual(cover["short"], 0)

    def test_the_rows_are_whole_and_keep_the_readers_text(self):
        rows, _cover = ig.fragment_rows(self.arr, pieces(self.boxes))
        for row, words in zip(rows, self.boxes):
            right = words[-1][0] + words[-1][2]
            self.assertLess(abs(row["box"][0] - words[0][0]), 4)
            self.assertLess(abs(row["box"][0] + row["box"][2] - right), 4)
            self.assertEqual(row["text"], "minimum")
            self.assertFalse(row.get("ink_row"))

    def test_many_pieces_on_a_row_or_short_pieces_count(self):
        whole = {"rows": 4, "cover": 0.96, "per_row": 1, "short": 0.0}
        self.assertFalse(ig.read_in_fragments(whole))
        self.assertTrue(ig.read_in_fragments({**whole, "cover": 0.5}))
        self.assertTrue(ig.read_in_fragments({**whole, "per_row": 3}))
        self.assertTrue(ig.read_in_fragments({**whole, "short": 0.5}))
        # One row is too little to tell.
        one_row = {**whole, "rows": 1, "cover": 0}
        self.assertFalse(ig.read_in_fragments(one_row))
        # A box with no size is left out.
        rows, cover = ig.reader_rows(self.arr, [{"box": [0, 0, 0, 0]}])
        self.assertEqual((rows, cover["rows"]), ([], 0))

    def test_joined_letters_leave_letter_spacing_unmeasured(self):
        rows, _cover = ig.fragment_rows(self.arr, pieces(self.boxes))
        result = scoring.build_analysis(self.arr, rows, {})
        self.assertEqual(result.style_profile.get("verdict"), "cursive")
        f = {r.n: r for r in result.results}
        self.assertTrue(f[9].unmeasured)
        self.assertEqual(f[9].value, "Not measured")
        self.assertEqual(f[9].unmeasured_kind, "joined")
        for n in (1, 5, 7, 10, 11, 12):
            self.assertFalse(f[n].unmeasured, n)

    def test_same_page_same_decision(self):
        a = ig.fragment_rows(self.arr, pieces(self.boxes))
        b = ig.fragment_rows(self.arr, pieces(self.boxes))
        self.assertEqual(a, b)


def _load_server(env):
    with mock.patch.dict(os.environ, env):
        spec = importlib.util.spec_from_file_location(
            "ink_server", os.path.join(SERVER_DIR, "ppocr-server.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


class TestSettings(unittest.TestCase):
    def test_setting_is_read_and_empty_by_default(self):
        import config  # pylint: disable=import-outside-toplevel

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VAHINI_INK_GEOMETRY_LANGS", None)
            self.assertEqual(config.load().ink_geometry_langs, [])
        with mock.patch.dict(
            os.environ, {"VAHINI_INK_GEOMETRY_LANGS": " TE, hi "}
        ):
            self.assertEqual(config.load().ink_geometry_langs, ["te", "hi"])


class TestInkMode(unittest.TestCase):
    # The server reads VAHINI_INK_GEOMETRY_LANGS once, at start-up
    # (config.py); the tests set what it read.
    def setUp(self):
        self.server = _load_server({})

    def test_off_unless_set(self):
        self.server.INK_LANGS = set()
        self.assertFalse(self.server._ink_mode("te"))  # pylint: disable=W0212

    def test_only_for_named_languages(self):
        self.server.INK_LANGS = {"te"}
        mode = self.server._ink_mode  # pylint: disable=protected-access
        self.assertTrue(mode("te"))
        self.assertFalse(mode("auto"))
        self.assertFalse(mode("en"))
        self.assertFalse(mode("en,te"))
        self.assertFalse(mode(""))


def _kept(_arr, _rows):
    return None


class TestServerReadInPieces(unittest.TestCase):
    """Through the server's scan: a page read in pieces is measured from
    the ink and says so (recognition.ink_reason); the text is still the
    reader's. The same rows read whole stay on the reader's lines."""

    @classmethod
    def setUpClass(cls):
        if cv2 is None:
            raise unittest.SkipTest("OpenCV unavailable")
        cls.server = _load_server({})
        cls.arr, cls.boxes = draw_cursive()

    def scan(self, lines):
        server = self.server

        def collect(_arr, _lang):
            return [dict(l) for l in lines], "", "paddle", {}

        def extract(_arr, raw_lines, **_kw):
            return list(raw_lines), [dict(l) for l in raw_lines]

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(server.recognizer, "collect_lines", collect)
            )
            stack.enter_context(
                mock.patch.object(
                    server.recognizer, "extract_hand_lines", extract
                )
            )
            # The printed check is not what is tested here, and no OCR
            # engine reads the least-sure letters again (a failed engine
            # load would stay failed for the tests after this one).
            stack.enter_context(
                mock.patch.object(server.classify, "classify_lines", _kept)
            )
            stack.enter_context(mock.patch.object(server, "_READ_LETTERS", None))
            scan = getattr(server, "_report_python_process")
            return scan(self.arr, b"", "en", "")

    def test_pieces_are_measured_from_the_ink(self):
        out = self.scan(pieces(self.boxes))
        self.assertTrue(out["ok"], out)
        rec = out["analysis"]["recognition"]
        self.assertTrue(rec["ink_rows"])
        self.assertEqual(rec["ink_reason"], "read_in_fragments")
        self.assertEqual(out["rec_texts"], ["minimum"] * 4)
        f9 = [r for r in out["analysis"]["results"] if r["n"] == 9][0]
        self.assertTrue(f9["unmeasured"])

    def test_whole_lines_stay_on_the_reader(self):
        out = self.scan(whole_lines(self.boxes))
        self.assertTrue(out["ok"], out)
        rec = out["analysis"]["recognition"]
        self.assertFalse(rec["ink_rows"])
        self.assertIsNone(rec["ink_reason"])


if __name__ == "__main__":
    unittest.main()
