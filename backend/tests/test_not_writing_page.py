# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
# A page read as mostly numbers and sums (a maths or science notebook page)
# is refused with not_writing_page, not scored: the factors measure
# letters, words and word gaps. Pages written in sentences, in English or
# Telugu, keep their path.
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

from reading import (
    recognizer,
)  # noqa: E402  pylint: disable=wrong-import-position

from backend.tests.test_server_pipeline import (  # noqa: E402
    _hand_strip,
)  # pylint: disable=wrong-import-position


def _load_server():
    path = os.path.join(SERVER_DIR, "server/app.py")
    spec = importlib.util.spec_from_file_location(
        "ppocr_server_not_writing_page", path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _line(text, y, score=0.8, lang="en"):
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


# A times-table and a sum, as the reader writes them back.
MATHS = [_line("3x4=12 5x6=30", 40), _line("Q2) 144÷12=12 25+17=42", 140)]
# A science page of formulas: F=ma, v=u+at, with the numbers filled in.
FORMULAS = [_line("F=ma=2x10=20N", 40), _line("v=u+at=0+5x4=20", 140)]
# The fixture's sentences, with a date and a page number in them.
SENTENCES = [
    _line("The sun is bright today. 20/10/2026", 40),
    _line("We play in the green garden. Page 3", 140),
]
# Telugu with vowel signs and a virama: the marks are letters here.
TELUGU = [
    _line("క్రీస్తుశకం ఉదర బస్సుల", 40, lang="te"),
    _line("గోకవరం తపన 12", 140, lang="te"),
]


class TestNumbersRule(unittest.TestCase):
    def test_a_times_table_is_not_a_writing_page(self):
        got = recognizer.not_writing_page(MATHS)
        self.assertEqual(got["page_kind"], "maths")
        self.assertGreater(got["numbers_read"], got["letters_read"])

    def test_filled_in_formulas_are_not_a_writing_page(self):
        self.assertIsNotNone(recognizer.not_writing_page(FORMULAS))

    def test_sentences_with_a_date_are_a_writing_page(self):
        self.assertIsNone(recognizer.not_writing_page(SENTENCES))

    def test_telugu_vowel_signs_count_as_letters(self):
        self.assertIsNone(recognizer.not_writing_page(TELUGU))

    def test_too_little_read_to_judge(self):
        self.assertIsNone(recognizer.not_writing_page([_line("2+2=4", 40)]))

    def test_lines_without_a_reading_are_not_judged(self):
        # cv-fallback rows and rows found from the ink carry no text.
        self.assertIsNone(recognizer.not_writing_page([_line("", 40)] * 5))

    def test_the_share_at_the_threshold_is_refused(self):
        # 13 letters and 7 digits: exactly 35% numbers.
        line = _line("abcdefghijklm 1234567", 40)
        self.assertIsNotNone(recognizer.not_writing_page([line]))
        line = _line("abcdefghijklmn 1234567", 40)
        self.assertIsNone(recognizer.not_writing_page([line]))


class TestNotWritingPageEndpoints(unittest.TestCase):
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

    def _post(self, url, mark, lang="auto"):
        return self.client.post(
            url,
            files={"image": ("page.png", _png(mark), "image/png")},
            data={"lang": lang},
        )

    def test_every_route_refuses_a_maths_page(self):
        self._stub(MATHS)
        for url in ("/report-python", "/analyze-vl", "/ocr"):
            r = self._post(url, 11)
            self.assertEqual(r.status_code, 200, url)
            j = r.json()
            self.assertIs(j.get("ok"), False, url)
            self.assertEqual(j.get("error_code"), "not_writing_page", url)
            self.assertEqual(j.get("page_kind"), "maths", url)
            self.assertEqual(j.get("rec_texts"), [], url)
            self.assertIsNone(j.get("analysis"), url)

    def test_the_refusal_is_the_same_every_time(self):
        self._stub(MATHS)
        first = self._post("/report-python", 12).json()
        again = self._post("/report-python", 12).json()
        self.assertEqual(first.get("error_code"), again.get("error_code"))
        self.assertEqual(first.get("numbers_read"), again.get("numbers_read"))

    def test_v2_report_carries_the_refusal_code(self):
        self._stub(MATHS)
        r = self.client.post(
            "/api/v2/reports?format=compact&include=text",
            files={"image": ("page.png", _png(13), "image/png")},
            data={"lang": "auto"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["error"]["code"], "not_writing_page")

    def test_a_page_of_sentences_is_still_scored(self):
        self._stub(SENTENCES)
        j = self._post("/report-python", 14).json()
        self.assertTrue(j.get("ok"), j.get("error"))
        self.assertEqual(len(j["analysis"]["results"]), 20)


if __name__ == "__main__":
    unittest.main()
