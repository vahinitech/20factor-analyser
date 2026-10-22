# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The request's `lang` as BCP 47 tags (#212): the schema accepts `auto`,
short codes, tags with a script and a region, and comma lists of them; the
server reads `te-Telu-IN` exactly as `te`, and the two share a cache
entry. Every value the old pattern allowed keeps working the same way."""

import copy
import hashlib
import importlib.util
import io
import os
import sys
import unittest

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
sys.path.insert(0, SERVER_DIR)

# pylint: disable=wrong-import-position
from server import cache  # noqa: E402
from report import contract_schemas  # noqa: E402
from languages import tags as lang_tags  # noqa: E402
from reading import recognizer  # noqa: E402
from languages import stages  # noqa: E402

from backend.tests.test_server_pipeline import _hand_strip  # noqa: E402
from backend.tests.test_telugu_not_read import (  # noqa: E402
    LATIN_ONLY,
    READ_TELUGU,
)

# pylint: enable=wrong-import-position

# Values the old pattern `^([a-z]{2,8}|auto)$` allowed. The 4 to 8 letter
# ones are PaddleOCR language names a self-hosted server can load.
OLD_VALUES = ["auto", "en", "te", "hi", "latin", "korean", "japan"]
NEW_VALUES = [
    "en,te",
    "te-Telu-IN",
    "en-Latn-IN",
    "en-Latn-GB,te",
    "en-IN",
    "en-Latn-GB,te-Telu-IN",
]
REFUSED = ["EN", "en_US", "en-latn", "", "en,", ",te", "en, te", "te-IN-x"]


def _request(lang):
    return {
        "headers": {},
        "query": {"format": "compact", "include": "text"},
        "form": {"lang": lang, "expected_text": ""},
        "image": {
            "content_type": "image/png",
            "size_bytes": 20000,
            "width": 380,
            "height": 240,
        },
    }


class TestEngineLangs(unittest.TestCase):
    def test_a_tag_reads_as_its_language_subtag(self):
        self.assertEqual(lang_tags.engine_lang("te-Telu-IN"), "te")
        self.assertEqual(lang_tags.engine_lang("en-Latn-IN"), "en")
        self.assertEqual(lang_tags.engine_lang("en-IN"), "en")

    def test_a_list_reads_tag_by_tag(self):
        self.assertEqual(
            lang_tags.engine_langs("en-Latn-GB,te-Telu-IN"), "en,te"
        )
        self.assertEqual(lang_tags.engine_langs("en-Latn-GB,te"), "en,te")

    def test_every_old_value_comes_back_unchanged(self):
        for lang in OLD_VALUES + ["en,te", ""]:
            self.assertEqual(lang_tags.engine_langs(lang), lang, lang)

    def test_case_spaces_and_empty_entries_as_before(self):
        # resolve_langs lowered the case and dropped empty entries before
        # this mapping existed; the mapping does the same.
        self.assertEqual(lang_tags.engine_langs(" EN , te ,"), "en,te")
        self.assertEqual(lang_tags.engine_langs(None), "")


class TestRequestPattern(unittest.TestCase):
    def test_old_and_new_values_are_accepted(self):
        for lang in OLD_VALUES + NEW_VALUES:
            self.assertEqual(
                contract_schemas.errors("report-request", _request(lang)),
                [],
                lang,
            )

    def test_malformed_tags_are_refused(self):
        for lang in REFUSED:
            self.assertTrue(
                contract_schemas.errors("report-request", _request(lang)),
                lang,
            )


class TestCacheKey(unittest.TestCase):
    def test_a_tag_and_its_short_code_share_an_entry(self):
        key = cache.cache_key
        self.assertEqual(
            key("report-python", b"page", "te-Telu-IN", "x"),
            key("report-python", b"page", "te", "x"),
        )
        self.assertEqual(
            key("ocr", b"page", "en-Latn-GB,te-Telu-IN"),
            key("ocr", b"page", "en,te"),
        )
        self.assertNotEqual(
            key("ocr", b"page", "te"), key("ocr", b"page", "en")
        )
        self.assertNotEqual(
            key("ocr", b"page", "auto"), key("ocr", b"page", "te")
        )

    def test_old_values_key_as_before(self):
        digest = hashlib.sha1(b"page").hexdigest()
        for lang in OLD_VALUES + ["en,te"]:
            self.assertEqual(
                cache.cache_key("ocr", b"page", lang, "e"),
                f"ocr|{lang}|e|{digest}",
            )


class TestResolveLangs(unittest.TestCase):
    def setUp(self):
        cfg = recognizer._CFG  # pylint: disable=protected-access
        self.addCleanup(cfg.update, copy.deepcopy(cfg))
        recognizer.configure(ocr_langs=["en", "te"])

    def test_tags_resolve_like_their_short_codes(self):
        resolve = recognizer.resolve_langs
        self.assertEqual(resolve("te-Telu-IN"), resolve("te"))
        self.assertEqual(resolve("te-Telu-IN"), ["te"])
        self.assertEqual(resolve("en-Latn-GB,te-Telu-IN"), ["en", "te"])

    def test_old_values_resolve_as_before(self):
        resolve = recognizer.resolve_langs
        self.assertEqual(resolve("auto"), ["en", "te"])
        self.assertEqual(resolve("en"), ["en"])
        self.assertEqual(resolve("en,te"), ["en", "te"])
        self.assertEqual(resolve("latin"), ["en", "te"])

    def test_the_telugu_check_reads_the_tag(self):
        self.assertEqual(
            recognizer.telugu_not_read("te-Telu-IN", LATIN_ONLY),
            recognizer.telugu_not_read("te", LATIN_ONLY),
        )
        self.assertIsNotNone(
            recognizer.telugu_not_read("te-Telu-IN", LATIN_ONLY)
        )
        self.assertIsNone(
            recognizer.telugu_not_read("en-Latn-IN,te-Telu-IN", LATIN_ONLY)
        )


class TestStageTable(unittest.TestCase):
    # The stage table (#208) matches engine codes exactly; the endpoints
    # hand it the mapped code, so a tag routes like its short code.
    def test_a_tag_routes_like_its_short_code(self):
        route = stages.table().refine_engine
        for tag, code in (("te-Telu-IN", "te"), ("en-Latn-GB", "en")):
            self.assertEqual(route(lang_tags.engine_lang(tag)), route(code))


def _load_server():
    spec = importlib.util.spec_from_file_location(
        "ppocr_server_lang_tags", os.path.join(SERVER_DIR, "server/app.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _png(mark):
    # Its own pixel row, so no other test's cached photo answers these.
    arr = np.full((240, 380, 3), 255, np.uint8)
    arr[1, mark] = 249
    arr[40:80, 10:370] = _hand_strip(360, 40)
    arr[140:180, 10:370] = _hand_strip(360, 40)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


class TestEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # pylint: disable=import-outside-toplevel
        from fastapi.testclient import TestClient

        cls.mod = _load_server()
        cls.client = TestClient(cls.mod.app)
        cls.addClassCleanup(
            setattr,
            cls.mod.recognizer,
            "collect_lines",
            cls.mod.recognizer.collect_lines,
        )

    def _stub(self, lines):
        asked = []

        def fake_collect(_arr, lang):
            asked.append(lang)
            return [dict(l) for l in lines], "", "paddle", {}

        self.mod.recognizer.collect_lines = fake_collect
        return asked

    def _post(self, url, lang, mark):
        return self.client.post(
            url,
            files={"image": ("page.png", _png(mark), "image/png")},
            data={"lang": lang},
        )

    def test_a_tag_reads_and_answers_as_its_short_code(self):
        asked = self._stub(LATIN_ONLY)
        for mark, url in enumerate(("/report-python", "/analyze-vl", "/ocr")):
            j = self._post(url, "te-Telu-IN", 10 + mark).json()
            self.assertEqual(j.get("error_code"), "handwriting_not_read", url)
            self.assertEqual(j.get("lang"), "te", url)
        self.assertEqual(set(asked), {"te"})

    def test_ink_mode_reads_the_tag(self):
        saved = self.mod.INK_LANGS
        self.addCleanup(setattr, self.mod, "INK_LANGS", saved)
        self.mod.INK_LANGS = {"te"}
        mode = self.mod._ink_mode  # pylint: disable=protected-access
        self.assertTrue(mode("te-Telu-IN"))
        self.assertTrue(mode("te"))
        self.assertFalse(mode("en-Latn-IN,te-Telu-IN"))
        self.assertFalse(mode("auto"))

    def test_a_tag_and_its_short_code_share_the_cached_report(self):
        asked = self._stub(READ_TELUGU)
        first = self._post("/report-python", "te", 20).json()
        reads = len(asked)
        again = self._post("/report-python", "te-Telu-IN", 20).json()
        self.assertTrue(first.get("ok"), first.get("error"))
        self.assertEqual(first["_meta"]["cache"], "miss")
        self.assertEqual(again["_meta"]["cache"], "hit")
        self.assertEqual(again["lang"], "te")
        self.assertEqual(len(asked), reads)


if __name__ == "__main__":
    unittest.main()
