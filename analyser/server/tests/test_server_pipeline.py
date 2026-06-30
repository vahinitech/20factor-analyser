# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
# Integration test for the server post-processing pipeline (classifier + factor
# regions + 20-factor scoring) WITHOUT paddle/torch installed. We load the
# hyphen-named server module by path and stub the paddle runner so the real
# /report-python endpoint runs end to end on a synthetic mixed page.
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


def _load_server():
    path = os.path.join(SERVER_DIR, "ppocr-server.py")
    spec = importlib.util.spec_from_file_location("ppocr_server_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _printed_strip(w, h):
    img = np.full((h, w, 3), 255, np.uint8)
    x = 6
    while x < w - 6:
        img[6:h - 6, x:x + 3] = 0          # constant stroke + height = printed
        x += 11
    return img


def _hand_strip(w, h):
    rng = [3, 7, 2, 9, 4, 6, 2, 8, 5, 3, 7, 4]
    img = np.full((h, w, 3), 255, np.uint8)
    x = 6
    i = 0
    while x < w - 12:
        sw = rng[i % len(rng)]
        top = 4 + (i * 3) % 12
        bot = h - 4 - (i * 2) % 10
        img[top:bot, x:x + sw] = 0
        x += sw + 6 + (i % 4)
        i += 1
    return img


class TestServerPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_server()
        from fastapi.testclient import TestClient
        cls.client = TestClient(cls.mod.app)

        # Build a mixed page: printed band on top, handwriting band lower.
        cls.W, cls.H = 380, 240
        arr = np.full((cls.H, cls.W, 3), 255, np.uint8)
        arr[20:60, 10:370] = _printed_strip(360, 40)
        arr[150:190, 10:370] = _hand_strip(360, 40)
        cls.arr = arr
        buf = io.BytesIO()
        Image.fromarray(arr).save(buf, format="PNG")
        cls.png = buf.getvalue()

        def fake_collect(arr_in, lang):
            def rect(x, y, w, h):
                return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
            lines = [
                {"text": "Patient Name :", "score": 0.99,
                 "box": [10, 20, 360, 40], "poly": rect(10, 20, 360, 40), "lang": "en"},
                {"text": "ramu kumar", "score": 0.72,
                 "box": [10, 150, 360, 40], "poly": rect(10, 150, 360, 40), "lang": "en"},
            ]
            return lines, "", "paddle", {}

        cls.mod._collect_lines = fake_collect

    def _post(self, url):
        return self.client.post(
            url,
            files={"image": ("page.png", self.png, "image/png")},
            data={"lang": "auto"},
        )

    def test_report_excludes_printed_keeps_handwriting(self):
        r = self._post("/report-python")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertTrue(j.get("ok"), j)
        texts = [t.strip().lower() for t in j.get("rec_texts", [])]
        self.assertIn("ramu kumar", texts)
        self.assertNotIn("patient name :", texts)

    def test_report_has_20_factors_and_regions(self):
        j = self._post("/report-python").json()
        analysis = j.get("analysis") or {}
        self.assertEqual(len(analysis.get("results", [])), 20)
        self.assertEqual(len(j.get("factor_regions", {})), 20)
        self.assertIsInstance(analysis.get("overall"), int)
        self.assertGreaterEqual(analysis["overall"], 0)
        self.assertLessEqual(analysis["overall"], 100)

    def test_health_lists_all_backends(self):
        j = self.client.get("/health").json()
        self.assertIn("backends", j)
        for name in ("paddle", "trocr", "surya", "chandra"):
            self.assertIn(name, j["backends"])
        self.assertIn("printed_threshold", j)

    def test_proc_dims_present(self):
        j = self._post("/report-python").json()
        self.assertEqual(j.get("proc_w"), self.W)
        self.assertEqual(j.get("proc_h"), self.H)

    def test_guarded_refinement_accepts_similar_rejects_hallucination(self):
        # The refiner must accept a stronger engine's text only when it agrees
        # with paddle (real correction) and reject divergent hallucinations.
        mod = self.mod
        proc = np.full((100, 300, 3), 255, np.uint8)
        buf = io.BytesIO()
        Image.fromarray(proc).save(buf, format="PNG")
        raw = buf.getvalue()
        orig = mod.ocr_backends.get_backend

        class _Fake:
            def __init__(self, out):
                self._out = out

            def available(self):
                return True, ""

            def recognize_crop(self, crop):
                return self._out

        try:
            mod.ocr_backends.get_backend = lambda n: _Fake("management")
            hl = [{"text": "manay ment", "box": [10, 10, 200, 30]}]
            mod._refine_handwriting_text(raw, proc, hl, "trocr")
            self.assertEqual(hl[0]["text"], "management")  # similar -> accepted

            mod.ocr_backends.get_backend = lambda n: _Fake("Transportation legislation")
            hl = [{"text": "Hypothyoidum", "box": [10, 10, 200, 30]}]
            mod._refine_handwriting_text(raw, proc, hl, "trocr")
            self.assertEqual(hl[0]["text"], "Hypothyoidum")  # divergent -> rejected
        finally:
            mod.ocr_backends.get_backend = orig


    def test_pdf_restricted_to_first_page(self):
        # A multi-page PDF must decode to page 1 ONLY. Page 1 is 200x120,
        # page 2 is a different 400x300, so the decoded size proves which page.
        try:
            import pypdfium2  # noqa: F401
        except Exception:
            self.skipTest("pypdfium2 not installed")
        p1 = Image.new("RGB", (200, 120), "white")
        p2 = Image.new("RGB", (400, 300), "white")
        buf = io.BytesIO()
        p1.save(buf, format="PDF", save_all=True, append_images=[p2])
        img = self.mod._decode_image(buf.getvalue())
        # Rendered at 150 DPI, so aspect ratio (not exact px) identifies page 1.
        self.assertAlmostEqual(img.size[0] / img.size[1], 200 / 120, places=1)


if __name__ == "__main__":
    unittest.main()
