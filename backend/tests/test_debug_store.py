# SPDX-License-Identifier: AGPL-3.0-only
"""Stage-only debug storage (debug_store.py).

Off, which is every deployment but a provisioned stage, nothing is
written. On, each answered upload leaves its photo and its answer.
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, SERVER_DIR)

from server import (
    debug_store,
)  # noqa: E402  pylint: disable=wrong-import-position
from server.daily_limit import (  # noqa: E402  pylint: disable=wrong-import-position
    DailyLimit,
)

# White-box tests reach into the server module's helpers.
# pylint: disable=protected-access

PNG = b"\x89PNG\r\n\x1a\n" + b"page of handwriting"


def files_under(folder):
    found = []
    for root, _dirs, names in os.walk(folder):
        found += [os.path.join(root, name) for name in names]
    return sorted(found)


class SwitchTests(unittest.TestCase):
    def test_off_unless_both_settings_are_given(self):
        off = [
            {},
            {"VAHINI_DEBUG_STORE_DIR": "/data/debug"},
            {"VAHINI_DEBUG_STORE": "1"},
            {"VAHINI_DEBUG_STORE": "1", "VAHINI_DEBUG_STORE_DIR": " "},
            {"VAHINI_DEBUG_STORE": "0", "VAHINI_DEBUG_STORE_DIR": "/d"},
            {"VAHINI_DEBUG_STORE": "true", "VAHINI_DEBUG_STORE_DIR": "/d"},
        ]
        for env in off:
            self.assertFalse(debug_store.DebugStore.from_env(env).enabled, env)
        on = debug_store.DebugStore.from_env(
            {"VAHINI_DEBUG_STORE": "1", "VAHINI_DEBUG_STORE_DIR": "/d"}
        )
        self.assertTrue(on.enabled)

    def test_extension_comes_from_the_bytes(self):
        self.assertEqual(debug_store.extension(b"\xff\xd8\xff\xe0.."), "jpg")
        self.assertEqual(debug_store.extension(PNG), "png")
        self.assertEqual(debug_store.extension(b"RIFF\0\0\0\0WEBPVP8"), "webp")
        self.assertEqual(debug_store.extension(b"%PDF-1.7"), "pdf")
        self.assertEqual(debug_store.extension(b"GIF89a"), "bin")


class EndpointTests(unittest.TestCase):
    """The real app, with the scan itself stubbed."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "ppocr_server_debug_store",
            os.path.join(SERVER_DIR, "server/app.py"),
        )
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)
        from fastapi.testclient import (  # pylint: disable=import-outside-toplevel
            TestClient,
        )

        cls.client = TestClient(cls.mod.app)

    def setUp(self):
        self.saved_store = debug_store.STORE
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=R1732
        self.folder = self.tmp.name
        self.mod.DAILY = DailyLimit(limit=0, exempt="")
        self.mod._cache_get = lambda _key: None
        self.mod._cache_set = lambda _key, _payload: None
        self.answer = {"ok": True, "rec_texts": ["the cat sat"]}

        async def decode(raw):
            return raw

        self.mod._decode_upload = decode
        self.mod._ocr_process = lambda _arr, _raw, _lang: dict(self.answer)
        self.mod._report_python_process = lambda *_args: {
            "ok": True,
            "analysis": {"results": [{"id": 1}]},
        }

    def tearDown(self):
        debug_store.STORE = self.saved_store
        self.tmp.cleanup()

    def switch(self, value):
        debug_store.STORE = debug_store.DebugStore.from_env(
            {
                "VAHINI_DEBUG_STORE": value,
                "VAHINI_DEBUG_STORE_DIR": self.folder,
            }
        )

    def post(self, route="/ocr", name="Vahini-Rao-class-2.png"):
        return self.client.post(
            route,
            files={"image": (name, PNG, "image/png")},
            data={"lang": "en"},
        )

    def kept(self):
        files = files_under(self.folder)
        photos = [f for f in files if f.endswith(".png")]
        records = [f for f in files if f.endswith(".json")]
        return files, photos, records

    def test_off_writes_nothing(self):
        self.switch("0")
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.post("/report-python").status_code, 200)
        self.assertEqual(files_under(self.folder), [])
        self.assertIs(self.mod.health()["debug_store"], False)

    def test_on_keeps_the_photo_and_the_answer(self):
        self.switch("1")
        res = self.post()
        self.assertEqual(res.status_code, 200)
        files, photos, records = self.kept()
        self.assertEqual((len(photos), len(records)), (1, 1), files)
        day = os.path.dirname(photos[0])
        self.assertEqual(
            os.path.dirname(day), os.path.join(self.folder, "analyser")
        )
        with open(photos[0], "rb") as fh:
            self.assertEqual(fh.read(), PNG)
        with open(records[0], encoding="utf-8") as fh:
            record = json.load(fh)
        self.assertEqual(record["route"], "/ocr")
        self.assertEqual(record["lang"], "en")
        self.assertEqual(record["photo"], os.path.basename(photos[0]))
        self.assertEqual(record["response"], res.json())
        self.assertIs(self.mod.health()["debug_store"], True)

    def test_on_keeps_refusals_answered_with_200_and_reports(self):
        self.switch("1")
        self.answer = {"ok": False, "error": "no handwriting"}
        self.assertEqual(self.post().status_code, 200)
        report = self.post("/report-python")
        self.assertEqual(report.status_code, 200)
        _files, photos, records = self.kept()
        self.assertEqual((len(photos), len(records)), (2, 2))
        responses = []
        for path in records:
            with open(path, encoding="utf-8") as fh:
                responses.append(json.load(fh)["response"])
        self.assertIn(self.answer, responses)
        self.assertIn(report.json(), responses)

    def test_the_visitors_file_name_is_never_written(self):
        self.switch("1")
        self.post(name="Vahini-Rao-class-2.png")
        for path in files_under(self.folder):
            self.assertNotIn("Vahini", path)
            with open(path, "rb") as fh:
                self.assertNotIn(b"Vahini", fh.read())

    def test_a_rejected_upload_is_not_kept(self):
        self.switch("1")

        async def unreadable(_raw):
            raise self.mod.HTTPException(422, "Upload a valid image or PDF.")

        self.mod._decode_upload = unreadable
        self.assertEqual(self.post().status_code, 422)
        self.assertEqual(files_under(self.folder), [])

    def test_a_failed_write_never_fails_the_scan(self):
        blocker = os.path.join(self.folder, "not-a-folder")
        with open(blocker, "w", encoding="utf-8") as fh:
            fh.write("x")
        debug_store.STORE = debug_store.DebugStore(blocker)
        res = self.post()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["rec_texts"], ["the cat sat"])
        self.assertEqual(files_under(self.folder), [blocker])


if __name__ == "__main__":
    unittest.main()
