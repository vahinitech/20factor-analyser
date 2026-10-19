# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
# A page asked for as Telugu whose reading came back mostly as Latin letters
# is refused, not scored. On 60 handwritten Telugu pages (2026-10-19) the
# Telugu reader returned "es aons", "aase" and the like, and every page
# still got a 20-factor report. The readings below are copied from that run.
# English and "auto" scans never take this check.
import io
import os
import sys
import unittest
import importlib.util

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
sys.path.insert(0, SERVER_DIR)

import recognizer  # noqa: E402  pylint: disable=wrong-import-position

from backend.tests.test_server_pipeline import (  # noqa: E402
    _hand_strip,
)  # pylint: disable=wrong-import-position


def _load_server():
    path = os.path.join(SERVER_DIR, "ppocr-server.py")
    spec = importlib.util.spec_from_file_location(
        "ppocr_server_telugu_not_read", path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _line(text, y, score=0.7, lang="te"):
    x, w, h = 10, 360, 40
    return {
        "text": text,
        "score": score,
        "box": [x, y, w, h],
        "poly": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
        "lang": lang,
    }


def _png(mark=0):
    # A different pixel per test: the server caches a repeated photo.
    arr = np.full((240, 380, 3), 255, np.uint8)
    arr[0, mark] = 250
    arr[40:80, 10:370] = _hand_strip(360, 40)
    arr[140:180, 10:370] = _hand_strip(360, 40)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


# w10_p1_clean and w13_p1_clean: no Telugu letter read at all.
LATIN_ONLY = [_line("es aons", 40), _line("foer oase ed", 140)]
# w12_p3_tilted_line: half Telugu, half invented Latin.
HALF = [_line("aew eew", 40), _line("సoప సంపతి", 140)]
# w12_p4_clean: the reading that came closest to Telugu, at 0.61. The page
# says "గమనించారు సబ్జెక్టులో ఇంటర్" on that line.
MOSTLY_TELUGU = [
    _line("గవం నింబారు", 40, 0.61),
    _line("స బ్దై )0wరు", 140, 0.61),
]
# zz_printed_control: printed Telugu, read at 0.96 to 1.0.
READ_TELUGU = [
    _line("క్రీస్తుశకం ఉదర బస్సుల", 40, 0.985),
    _line("గోకవరం తపన ఔచిత్యవంతమైన", 140, 0.999),
]


class TestTeluguRule(unittest.TestCase):
    def test_latin_reading_of_a_telugu_page_is_refused(self):
        got = recognizer.telugu_not_read("te", LATIN_ONLY)
        self.assertEqual(
            got,
            {
                "telugu_letters": 0,
                "latin_letters": 16,
                "reading_confidence": 0.7,
            },
        )

    def test_half_latin_reading_is_refused(self):
        self.assertIsNotNone(recognizer.telugu_not_read("te", HALF))

    def test_unsure_telugu_reading_is_refused(self):
        self.assertIsNotNone(recognizer.telugu_not_read("te", MOSTLY_TELUGU))

    def test_sure_telugu_reading_passes(self):
        self.assertIsNone(recognizer.telugu_not_read("te", READ_TELUGU))

    def test_english_and_auto_requests_are_never_checked(self):
        for lang in ("en", "auto", "", "en,te", None):
            self.assertIsNone(recognizer.telugu_not_read(lang, LATIN_ONLY))

    def test_no_lines_keeps_its_own_path(self):
        self.assertIsNone(recognizer.telugu_not_read("te", []))

    def test_lines_found_without_reading_keep_their_own_path(self):
        # cv-fallback rows, and rows found from the ink (#170), carry no
        # text: nothing was read, so there is no reading to judge.
        self.assertIsNone(recognizer.telugu_not_read("te", [_line("", 40)]))

    def test_digits_alone_are_not_a_reading(self):
        # w10_p2_wide_gap read only "2".
        self.assertIsNotNone(
            recognizer.telugu_not_read("te", [_line("2", 40)])
        )


class TestTeluguRefusalEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_server()
        from fastapi.testclient import TestClient

        cls.client = TestClient(cls.mod.app)
        cls.addClassCleanup(
            setattr,
            cls.mod.recognizer,
            "collect_lines",
            cls.mod.recognizer.collect_lines,
        )

    def _stub(self, lines):
        def fake_collect(_arr, _lang):
            return [dict(l) for l in lines], "", "paddle", {}

        self.mod.recognizer.collect_lines = fake_collect

    def _post(self, url, lang, mark):
        return self.client.post(
            url,
            files={"image": ("page.png", _png(mark), "image/png")},
            data={"lang": lang},
        )

    def test_every_route_refuses_an_unread_telugu_page(self):
        self._stub(LATIN_ONLY)
        for url in ("/report-python", "/analyze-vl", "/ocr"):
            r = self._post(url, "te", 1)
            self.assertEqual(r.status_code, 200, url)
            j = r.json()
            self.assertIs(j.get("ok"), False, url)
            self.assertEqual(j.get("error_code"), "handwriting_not_read", url)
            self.assertEqual(j.get("rec_texts"), [], url)
            self.assertIsNone(j.get("analysis"), url)
            self.assertEqual(j.get("latin_letters"), 16, url)

    def test_v2_report_carries_the_refusal_code(self):
        self._stub(LATIN_ONLY)
        r = self.client.post(
            "/api/v2/reports?format=compact&include=text",
            files={"image": ("page.png", _png(2), "image/png")},
            data={"lang": "te"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["error"]["code"], "handwriting_not_read")

    def test_the_same_reading_under_auto_is_still_scored(self):
        self._stub(LATIN_ONLY)
        j = self._post("/report-python", "auto", 3).json()
        self.assertTrue(j.get("ok"), j.get("error"))
        self.assertEqual(len(j["analysis"]["results"]), 20)

    def test_a_sure_telugu_reading_is_scored(self):
        self._stub(READ_TELUGU)
        j = self._post("/report-python", "te", 4).json()
        self.assertTrue(j.get("ok"), j.get("error"))


if __name__ == "__main__":
    unittest.main()
