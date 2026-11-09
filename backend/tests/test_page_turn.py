# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""A page photographed sideways or upside down is read upright, or refused
(vision/page_turn.py, #297).

On 23 October 2026 a school photographed a notebook page sideways, with
no EXIF turn, and the report scored the sideways text: 3 lines on an
18-line page, Line alignment 8.0. These tests turn the analyser's own
sample page and the committed benchmark pages (never a child's photo)
and check that:
- a page that is already upright is never turned, so the benchmark
  pages cannot move;
- a quarter turn either way comes back upright, and the turned photo
  gives exactly the pixels and the scores of the upright one;
- a page is turned over only when the reader agrees;
- Telugu is never turned over, and a sideways Telugu page is refused;
- the server refuses a page it cannot set upright, and says how far it
  turned one it could.
"""

import glob
import importlib.util
import io
import os
import sys
import unittest

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from vision import computer_vision  # noqa: E402
from vision import page_turn  # noqa: E402
from backend.tests.test_not_writing_page import SENTENCES  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
BENCH = os.path.join(ROOT, "benchmarks")
SAMPLE = os.path.join(ROOT, "tests", "fixtures", "handwriting-sample.jpg")
UJI = sorted(glob.glob(os.path.join(BENCH, "uji-clean", "pages", "*.jpg")))
UPRIGHT = (
    UJI
    + sorted(glob.glob(os.path.join(BENCH, "*", "pages", "*.jpg")))
    + sorted(
        p
        for p in glob.glob(os.path.join(ROOT, "tests", "fixtures", "*", "*"))
        if p.endswith((".jpg", ".png"))
    )
    + [SAMPLE]
)
SIDE = 2600  # the benchmark sets' VAHINI_OCR_MAX_SIDE
MEASURE = page_turn.measure


def _raw(path):
    with open(path, "rb") as f:
        return f.read()


def _photo(path, taken):
    """The page photographed turned `taken` degrees clockwise, as a PNG
    (lossless, no EXIF turn): what a phone held sideways sends."""
    page = np.array(computer_vision.decode_image(_raw(path)))
    buf = io.BytesIO()
    Image.fromarray(page_turn.turned(page, taken)).save(buf, format="PNG")
    return buf.getvalue()


def _back(taken):
    return (360 - taken) % 360


def _never(_crop, _lang):
    raise AssertionError("an upright page must not need the reader")


def _undecided(_crop, _lang):
    return [{"score": 0.7}]


def _reader(prefers_over):
    """A stand-in for the scan's recogniser: _reading asks about each
    crop as it lies, then turned over. Reads the one it is told to
    prefer at 0.9 and the other at 0.5."""
    calls = []

    def read(_crop, _lang):
        over = len(calls) % 2 == 1
        calls.append(over)
        return [{"score": 0.9 if over == prefers_over else 0.5}]

    read.calls = calls
    return read


class TestUprightPagesStay(unittest.TestCase):
    def test_no_upright_page_is_turned(self):
        # The benchmark pages, the neat penmanship scans, the printed and
        # mixed samples and the sample page: none is turned, with no
        # reader or with one that cannot tell.
        for path in UPRIGHT:
            arr = computer_vision.to_numpy(_raw(path), max_side=SIDE)
            for read in (None, _undecided):
                verdict = page_turn.measure(arr, read=read)
                self.assertEqual(verdict.turn, 0, path)
                self.assertFalse(verdict.unsure, path)

    def test_handwritten_pages_do_not_ask_the_reader(self):
        # The UJI pages and the sample page lean upright on their own;
        # a one-line penmanship specimen may ask (zaner-090), and is
        # still turned only if the reader prefers it turned over.
        for path in UJI + [SAMPLE]:
            arr = computer_vision.to_numpy(_raw(path), max_side=SIDE)
            self.assertEqual(page_turn.measure(arr, read=_never).turn, 0)

    def test_a_blank_or_tiny_page_is_left_alone(self):
        blank = np.full((400, 300, 3), 255, np.uint8)
        self.assertEqual(page_turn.measure(blank), page_turn.UPRIGHT)
        self.assertEqual(page_turn.measure(None), page_turn.UPRIGHT)


class TestQuarterTurns(unittest.TestCase):
    def test_sideways_pages_come_back_upright(self):
        # Either way round, with no reader to ask: the signs alone.
        for path in UJI + [SAMPLE]:
            for taken in (90, 270):
                arr = computer_vision.to_numpy(
                    _photo(path, taken), max_side=SIDE
                )
                verdict = page_turn.measure(arr)
                self.assertEqual(
                    (verdict.turn, verdict.unsure),
                    (_back(taken), False),
                    (path, taken, verdict.as_dict()),
                )

    def test_the_reader_decides_when_the_signs_cannot(self):
        # The sample page on its side (it needs a quarter turn clockwise),
        # with its signs taken away: the reader's preference sets the way.
        arr = computer_vision.to_numpy(_photo(SAMPLE, 270), max_side=SIDE)
        real = page_turn.UP_SURE
        page_turn.UP_SURE = 99.0
        try:
            self.assertTrue(page_turn.measure(arr).unsure)
            as_lies = page_turn.measure(arr, read=_reader(False))
            over = page_turn.measure(arr, read=_reader(True))
        finally:
            page_turn.UP_SURE = real
        self.assertEqual((as_lies.turn, as_lies.unsure), (90, False))
        self.assertEqual((over.turn, over.unsure), (270, False))

    def test_reader_and_signs_disagreeing_is_unsure(self):
        arr = computer_vision.to_numpy(_photo(SAMPLE, 270), max_side=SIDE)
        agree = page_turn.measure(arr, read=_reader(False))
        self.assertEqual((agree.turn, agree.unsure), (90, False))
        verdict = page_turn.measure(arr, read=_reader(True))
        self.assertTrue(verdict.unsure, verdict.as_dict())


class TestTurnedOver(unittest.TestCase):
    def test_turned_over_only_when_the_reader_agrees(self):
        for path in UJI[:5] + [SAMPLE]:
            arr = computer_vision.to_numpy(_photo(path, 180), max_side=SIDE)
            alone = page_turn.measure(arr)
            self.assertEqual(alone.turn, 0, path)
            agrees = page_turn.measure(arr, read=_reader(True))
            self.assertEqual(agrees.turn, 180, (path, agrees.as_dict()))
            refuses = page_turn.measure(arr, read=_reader(False))
            self.assertEqual(refuses.turn, 0, path)


def _joined_list(words_per_line, x_h, asc):
    """An upright list in joined-up writing, drawn: each word one stroke,
    a wave one x-height tall with a loop above every third letter, one or
    two words to a line, 64 px apart. Every word is one piece of ink, as
    when a child joins each word up."""
    rng = np.random.default_rng(3)
    page = np.full((1600, 1200), 255, np.uint8)
    for y in range(120, 1500, 64):
        x = 80.0
        for _ in range(words_per_line):
            letters = 6 + int(rng.integers(-2, 3))
            t = np.arange(letters * 8 + 1) / 8.0
            ys = y - x_h / 2 * (1 - np.cos(t * 2 * np.pi))
            loop = (t.astype(int) % 3 == 1) * np.maximum(
                0, np.sin((t % 1) * np.pi)
            )
            ys = ys - asc * x_h * loop
            pts = np.stack([x + t * x_h * 0.9, ys], axis=1).astype(np.int32)
            cv2.polylines(page, [pts], False, 0, 3, cv2.LINE_AA)
            x += letters * x_h * 0.9 + x_h * 1.3
    return np.dstack([page] * 3)


class TestJoinedUpWriting(unittest.TestCase):
    """A short list in joined-up writing is upright. With each word one
    piece of ink, the letter size was a whole word, the smear stacked the
    lines into columns, and the page was refused as on its side."""

    def test_an_upright_joined_up_list_is_left_alone(self):
        for words, x_h, asc in ((1, 22, 0.4), (2, 16, 0.8)):
            page = _joined_list(words, x_h, asc)
            for taken in (0, 180):
                for latin, read in (
                    (True, None),
                    (True, _undecided),
                    (False, None),
                ):
                    verdict = page_turn.measure(
                        page_turn.turned(page, taken), latin=latin, read=read
                    )
                    self.assertEqual(
                        (verdict.turn, verdict.unsure),
                        (0, False),
                        (words, taken, latin, verdict.as_dict()),
                    )


class TestTelugu(unittest.TestCase):
    """The up-or-down signs are measured on Latin writing: for another
    script a page is never turned over, and lines running up and down
    are refused rather than guessed (#297)."""

    def test_never_turned_over_and_sideways_refused(self):
        for path in UJI[:3] + [SAMPLE]:
            for taken, want in ((0, (0, False)), (180, (0, False))):
                arr = computer_vision.to_numpy(
                    _photo(path, taken), max_side=SIDE
                )
                verdict = page_turn.measure(
                    arr, latin=False, read=_reader(True)
                )
                self.assertEqual((verdict.turn, verdict.unsure), want, path)
            arr = computer_vision.to_numpy(_photo(path, 90), max_side=SIDE)
            verdict = page_turn.measure(arr, latin=False, read=_never)
            self.assertTrue(verdict.unsure, path)


class TestSameScores(unittest.TestCase):
    """The turned photo, set upright, is the upright photo: the same
    working pixels, the same full-size crops, the same scores."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "benchmark_turn", os.path.join(ROOT, "scripts", "benchmark.py")
        )
        cls.bench = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.bench)

    def test_pixels_match_the_upright_photo(self):
        for path in UJI + [SAMPLE]:
            upright = computer_vision.to_numpy(_raw(path), max_side=SIDE)
            full = np.array(computer_vision.decode_image(_raw(path)))
            for taken in (90, 180, 270):
                raw = _photo(path, taken)
                turned = computer_vision.to_numpy(
                    raw, max_side=SIDE, turn=_back(taken)
                )
                self.assertTrue(np.array_equal(turned, upright), path)
                again = computer_vision.decode_image(raw, _back(taken))
                self.assertTrue(np.array_equal(np.array(again), full), path)
                self.assertEqual(
                    computer_vision.photo_size(raw, _back(taken)),
                    computer_vision.photo_size(_raw(path)),
                )

    def test_scores_match_the_upright_photo(self):
        # The benchmark replay (kept reader output, no models), run on
        # the upright photo and on each turned photo set upright: the
        # full-size crops the line recovery reads come from the turned
        # photo, so they match the kept ones only if the turn reached
        # them too.
        from reading import recognizer

        real = recognizer.extract_hand_lines
        for name in ("sample-page", "uji-clean"):
            folder, meta = self.bench._load_set(name)  # pylint: disable=W0212
            for page in self.bench._pages(folder)[:3]:  # pylint: disable=W0212
                path = os.path.join(folder, "pages", page + ".jpg")
                reader = self.bench.json.load(
                    open(
                        os.path.join(folder, "reader", page + ".json"),
                        encoding="utf-8",
                    )
                )
                raw = _raw(path)
                arr = computer_vision.to_numpy(raw, max_side=SIDE)
                want = self.bench._score(  # pylint: disable=W0212
                    arr, raw, reader, meta
                )
                for taken in (90, 270):
                    photo = _photo(path, taken)
                    found = page_turn.measure(
                        computer_vision.to_numpy(photo, max_side=SIDE)
                    )
                    self.assertEqual(found.turn, _back(taken), page)
                    upright = computer_vision.to_numpy(
                        photo, max_side=SIDE, turn=found.turn
                    )

                    def with_turn(*args, _turn=found.turn, **kwargs):
                        return real(*args, turn=_turn, **kwargs)

                    recognizer.extract_hand_lines = with_turn
                    try:
                        got = self.bench._score(  # pylint: disable=W0212
                            upright, photo, reader, meta
                        )
                    finally:
                        recognizer.extract_hand_lines = real
                    self.assertEqual(got, want, (name, page, taken))


def _load_server():
    path = os.path.join(os.path.dirname(HERE), "server", "app.py")
    spec = importlib.util.spec_from_file_location(
        "ppocr_server_page_turn", path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        cls.mod = _load_server()
        cls.client = TestClient(cls.mod.app)
        # CI has no reading models: the reader finds lines of sentences.
        real = cls.mod.recognizer.collect_lines
        cls.addClassCleanup(setattr, cls.mod.recognizer, "collect_lines", real)
        cls.mod.recognizer.collect_lines = lambda _arr, _lang: (
            [dict(l) for l in SENTENCES],
            "",
            "paddle",
            {},
        )
        cls.addClassCleanup(setattr, cls.mod.page_turn, "measure", MEASURE)

    def _post(self, url, raw, lang="auto"):
        return self.client.post(
            url,
            files={"image": ("page.png", raw, "image/png")},
            data={"lang": lang},
        )

    def test_a_page_it_cannot_set_upright_is_refused(self):
        unsure = page_turn.Verdict(turn=90, unsure=True, across=-3.0)
        self.mod.page_turn.measure = lambda *_a, **_k: unsure
        try:
            raw = _photo(SAMPLE, 90)
            for url in ("/report-python", "/analyze-vl", "/ocr"):
                j = self._post(url, raw).json()
                self.assertIs(j.get("ok"), False, url)
                self.assertEqual(j.get("error_code"), "turned_page", url)
                self.assertEqual(j.get("rec_texts"), [], url)
                self.assertIsNone(j.get("analysis"), url)
                self.assertNotIn("turned", j, url)
            r = self.client.post(
                "/api/v2/reports?format=compact&include=text",
                files={"image": ("page.png", raw, "image/png")},
                data={"lang": "auto"},
            )
            self.assertEqual(r.json()["error"]["code"], "turned_page")
        finally:
            self.mod.page_turn.measure = MEASURE

    def test_a_turned_page_says_how_far(self):
        # The sample page on its side: read upright and reported as
        # turned 90 degrees, in its upright size, in both formats.
        raw = _photo(SAMPLE, 270)
        seen = []

        def measure(arr, **kwargs):
            seen.append(kwargs)
            return MEASURE(arr, **kwargs)

        self.mod.page_turn.measure = measure
        try:
            j = self._post("/report-python", raw).json()
            self.assertEqual(j.get("turned"), 90, j.get("error"))
            self.assertEqual((j["photo_w"], j["photo_h"]), (960, 1280))
            self.assertGreater(j["proc_h"], j["proc_w"])
            for fmt in ("compact", "expanded"):
                r = self.client.post(
                    f"/api/v2/reports?format={fmt}&include=evidence",
                    files={"image": ("page.png", raw, "image/png")},
                    data={"lang": "auto"},
                )
                self.assertEqual(r.json().get("turned"), 90, fmt)
        finally:
            self.mod.page_turn.measure = MEASURE
        self.assertTrue(seen and all(k.get("latin") for k in seen))

    def test_an_upright_page_carries_no_turn(self):
        j = self._post("/report-python", _raw(SAMPLE)).json()
        self.assertTrue(j.get("ok"), j.get("error"))
        self.assertNotIn("turned", j)

    def test_telugu_is_measured_without_the_reader(self):
        seen = []

        def measure(arr, **kwargs):
            seen.append(kwargs)
            return page_turn.UPRIGHT

        self.mod.page_turn.measure = measure
        try:
            self._post("/report-python", _photo(SAMPLE, 0), lang="te")
        finally:
            self.mod.page_turn.measure = MEASURE
        self.assertEqual(seen, [{"latin": False, "read": None}])


if __name__ == "__main__":
    unittest.main()
