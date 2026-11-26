# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Two facing pages in one photo: only the first page with writing,
left to right, is read and scored (vision/facing_pages.py).

An open notebook photographed whole, from the camera or the gallery,
put the lines of two pages into one report. These tests build two-page
spreads from the committed benchmark pages (never a child's photo),
joined by a spiral binding or the shadow of a bound book, straight, a
few degrees off and in uneven light, and check that:
- no single page is ever taken for two, upright or turned a quarter, so
  the benchmark pages and their scores cannot move;
- a spread is found, and the left page is kept, or the right one when
  the left has no writing;
- the kept photo has the same size, the kept page's pixels unchanged
  and the other page painted its paper colour;
- the server reads only the kept page and says which page it scored,
  with its box, in both report formats; a one-page photo carries no
  facing_pages and reaches the reader as it was.
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
from vision import facing_pages  # noqa: E402
from vision import page_turn  # noqa: E402
from backend.tests.test_not_writing_page import SENTENCES  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
BENCH = os.path.join(ROOT, "benchmarks")
SAMPLE = os.path.join(ROOT, "tests", "fixtures", "handwriting-sample.jpg")
UJI = sorted(glob.glob(os.path.join(BENCH, "uji-clean", "pages", "*.jpg")))
FRENCH = sorted(
    glob.glob(os.path.join(BENCH, "cursive-french", "pages", "*.jpg"))
)
ONE_PAGE = (
    sorted(glob.glob(os.path.join(BENCH, "*", "pages", "*.jpg")))
    + sorted(
        p
        for p in glob.glob(os.path.join(ROOT, "tests", "fixtures", "*", "*"))
        if p.endswith((".jpg", ".png"))
    )
    + [SAMPLE]
)
TABLE = 60  # the desk around the notebook


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def _page(path):
    return np.array(computer_vision.decode_image(_read(path)))


def _spread(left, right, binding="spiral"):
    """(photo, left page's right edge as a share of the width): two pages
    side by side, joined by a spiral (bright rings, dark gaps) or the
    soft shadow of a bound book, on a dark desk."""
    h = min(left.shape[0], right.shape[0])
    a = cv2.resize(left, (int(left.shape[1] * h / left.shape[0]), h))
    b = cv2.resize(right, (int(right.shape[1] * h / right.shape[0]), h))
    g = int(0.04 * a.shape[1])
    mid = np.full((h, g, 3), 245, np.uint8)
    if binding == "spiral":
        mid[:] = 70
        step = max(2, h // 22)
        for y in range(0, h, step):
            mid[y : y + step // 2] = 200
    else:
        for i in range(g):
            mid[:, i] = int(245 - 110 * (1 - abs(i - g / 2) / (g / 2)))
    pages = np.concatenate([a, mid, b], axis=1)
    photo = np.full((h + 80, pages.shape[1] + 80, 3), TABLE, dtype=np.uint8)
    photo[40:-40, 40:-40] = pages
    return photo, (a.shape[1] + 40) / photo.shape[1]


def _tilt(img, deg):
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1)
    return cv2.warpAffine(img, m, (w, h), borderValue=(TABLE,) * 3)


def _light(img):
    shade = np.linspace(0.7, 1.05, img.shape[1])[None, :, None]
    return np.clip(img * shade, 0, 255).astype(np.uint8)


def _portrait(page):
    """A notebook page is taller than wide: the left 62% of a page."""
    return page[:, : int(page.shape[1] * 0.62)]


def _pairs():
    for pages in (UJI, FRENCH):
        for i in range(0, len(pages) - 1, 2):
            yield pages[i], pages[i + 1]


class TestOnePageStays(unittest.TestCase):
    def test_no_single_page_is_taken_for_two(self):
        self.assertGreater(len(ONE_PAGE), 40)
        for path in ONE_PAGE:
            page = _page(path)
            for taken in (0, 90):
                arr = page_turn.turned(page, taken)
                self.assertIsNone(facing_pages.find(arr), (path, taken))

    def test_the_same_photo_gives_the_same_answer(self):
        photo, _ = _spread(_page(UJI[0]), _page(UJI[1]))
        self.assertEqual(facing_pages.find(photo), facing_pages.find(photo))


class TestSpreads(unittest.TestCase):
    def _check(self, photo, edge, what):
        found = facing_pages.find(photo)
        self.assertIsNotNone(found, what)
        self.assertEqual(found.used, "left", what)
        x, _, w, _ = found.box
        self.assertAlmostEqual(x + w, edge, delta=0.04, msg=what)

    def test_spreads_keep_the_left_page(self):
        for left, right in _pairs():
            for binding in ("spiral", "shadow"):
                photo, edge = _spread(_page(left), _page(right), binding)
                for name, img in (
                    ("straight", photo),
                    ("tilted", _tilt(photo, 3)),
                    ("uneven light", _light(photo)),
                ):
                    self._check(img, edge, (left, binding, name))

    def test_portrait_notebook_pages(self):
        for left, right in _pairs():
            for binding in ("spiral", "shadow"):
                photo, edge = _spread(
                    _portrait(_page(left)), _portrait(_page(right)), binding
                )
                for img in (photo, _tilt(photo, -3), _light(photo)):
                    self._check(img, edge, (left, binding))

    def test_a_blank_left_page_keeps_the_right(self):
        photo, edge = _spread(_page(UJI[0]), _page(UJI[1]))
        cut = int(edge * photo.shape[1])
        photo[40:-40, 40:cut] = np.percentile(photo[40:-40, 40:cut], 90)
        found = facing_pages.find(photo)
        self.assertEqual(found.used, "right")
        self.assertGreater(found.box[0], edge)

    def test_the_other_page_is_painted_paper(self):
        photo, edge = _spread(_page(UJI[0]), _page(UJI[1]))
        found = facing_pages.find(photo)
        kept = facing_pages.keep_page(photo, found)
        self.assertEqual(kept.shape, photo.shape)
        cut = int(round((found.box[0] + found.box[2]) * photo.shape[1]))
        np.testing.assert_array_equal(kept[:, :cut], photo[:, :cut])
        rest = kept[:, cut:].reshape(-1, 3)
        self.assertEqual(len(np.unique(rest, axis=0)), 1)
        self.assertGreater(int(rest[0].mean()), 150)
        raw = facing_pages.page_photo(photo, found)
        back = np.array(Image.open(io.BytesIO(raw)).convert("RGB"))
        np.testing.assert_array_equal(back, kept)

    def test_the_answer_gives_the_box_in_pixels(self):
        photo, _ = _spread(_page(UJI[0]), _page(UJI[1]))
        found = facing_pages.find(photo)
        h, w = photo.shape[:2]
        answer = found.as_dict(w, h)
        self.assertEqual(answer["found"], 2)
        self.assertEqual(answer["used"], "left")
        x, y, bw, bh = answer["box"]
        self.assertEqual((x, y, bh), (0, 0, h))
        self.assertLess(bw, w * 0.6)


def _load_server():
    path = os.path.join(os.path.dirname(HERE), "server", "app.py")
    spec = importlib.util.spec_from_file_location(
        "ppocr_server_facing_pages", path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _png(arr):
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


class TestServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        cls.mod = _load_server()
        cls.client = TestClient(cls.mod.app)
        cls.seen = []
        # CI has no reading models: the reader finds lines of sentences,
        # and keeps the picture it was given.
        real = cls.mod.recognizer.collect_lines
        cls.addClassCleanup(setattr, cls.mod.recognizer, "collect_lines", real)

        def collect(arr, _lang):
            cls.seen.append(arr)
            return [dict(l) for l in SENTENCES], "", "paddle", {}

        cls.mod.recognizer.collect_lines = collect
        sample = _page(SAMPLE)
        cls.spread, cls.edge = _spread(sample, sample.copy())

    def setUp(self):
        self.seen.clear()

    def _post(self, url, raw):
        return self.client.post(
            url,
            files={"image": ("page.png", raw, "image/png")},
            data={"lang": "auto"},
        )

    def test_a_spread_is_read_as_its_left_page(self):
        raw = _png(self.spread)
        h, w = self.spread.shape[:2]
        for url in ("/report-python", "/analyze-vl", "/ocr"):
            self.seen.clear()
            j = self._post(url, raw).json()
            facing = j.get("facing_pages")
            self.assertEqual(facing and facing["used"], "left", url)
            x, y, bw, bh = facing["box"]
            self.assertEqual((x, y, bh), (0, 0, h), url)
            self.assertAlmostEqual(bw / w, self.edge, delta=0.04)
            # The reader saw the left page and paper where the right was.
            arr = self.seen[-1]
            right = arr[:, int(arr.shape[1] * (self.edge + 0.05)) :]
            self.assertEqual(len(np.unique(right.reshape(-1, 3), axis=0)), 1)
        j = self._post("/report-python", raw).json()
        self.assertEqual((j["photo_w"], j["photo_h"]), (w, h))
        for fmt in ("compact", "expanded"):
            r = self.client.post(
                f"/api/v2/reports?format={fmt}&include=evidence",
                files={"image": ("page.png", raw, "image/png")},
                data={"lang": "auto"},
            )
            self.assertEqual(r.json()["facing_pages"]["used"], "left", fmt)

    def test_one_page_reaches_the_reader_as_it_was(self):
        raw = _read(SAMPLE)
        j = self._post("/report-python", raw).json()
        self.assertNotIn("facing_pages", j)
        want = computer_vision.to_numpy(raw, max_side=self.mod.MAX_OCR_SIDE)
        np.testing.assert_array_equal(self.seen[-1], want)
        r = self.client.post(
            "/api/v2/reports?format=compact&include=evidence",
            files={"image": ("page.jpg", raw, "image/jpeg")},
            data={"lang": "auto"},
        )
        self.assertNotIn("facing_pages", r.json())


if __name__ == "__main__":
    unittest.main()
