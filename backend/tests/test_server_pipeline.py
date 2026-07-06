# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
# Integration test for the server post-processing pipeline (classifier + factor
# regions + 20-factor scoring) WITHOUT paddle/torch installed. We load the
# hyphen-named server module by path and stub the paddle runner so the real
# /report-python endpoint runs end to end on a synthetic mixed page.
import io
import os
import sys
import time
import unittest
import importlib.util
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
sys.path.insert(0, SERVER_DIR)

# White-box tests deliberately reach into module-private helpers below.
# pylint: disable=protected-access


def _load_server():
    path = os.path.join(SERVER_DIR, "ppocr-server.py")
    spec = importlib.util.spec_from_file_location(
        "ppocr_server_under_test", path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _printed_strip(w, h):
    img = np.full((h, w, 3), 255, np.uint8)
    x = 6
    while x < w - 6:
        img[6 : h - 6, x : x + 3] = 0  # constant stroke + height = printed
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
        img[top:bot, x : x + sw] = 0
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

        def fake_collect(_arr_in, _lang):
            def rect(x, y, w, h):
                return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]

            lines = [
                {
                    "text": "Patient Name :",
                    "score": 0.99,
                    "box": [10, 20, 360, 40],
                    "poly": rect(10, 20, 360, 40),
                    "lang": "en",
                },
                {
                    "text": "ramu kumar",
                    "score": 0.72,
                    "box": [10, 150, 360, 40],
                    "poly": rect(10, 150, 360, 40),
                    "lang": "en",
                },
            ]
            return lines, "", "paddle", {}

        # recognizer is a sys.modules singleton shared with the other test
        # files in this package: restore the real collect_lines when this
        # class is done, or the stub leaks into every later test module.
        cls.addClassCleanup(
            setattr,
            cls.mod.recognizer,
            "collect_lines",
            cls.mod.recognizer.collect_lines,
        )
        cls.mod.recognizer.collect_lines = fake_collect

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
        for name in ("paddle", "trocr", "surya"):
            self.assertIn(name, j["backends"])
        self.assertIn("printed_threshold", j)

    def test_proc_dims_present(self):
        j = self._post("/report-python").json()
        self.assertEqual(j.get("proc_w"), self.W)
        self.assertEqual(j.get("proc_h"), self.H)

    def test_guarded_refinement_accepts_similar_rejects_hallucination(self):
        # The refiner must accept a stronger engine's text when it agrees
        # with paddle (real correction) or is itself confident, and reject
        # a divergent, low-confidence hallucination.
        mod = self.mod
        proc = np.full((100, 300, 3), 255, np.uint8)
        buf = io.BytesIO()
        Image.fromarray(proc).save(buf, format="PNG")
        raw = buf.getvalue()
        orig = mod.ocr_backends.get_backend

        class _Fake:
            def __init__(self, out, conf=0.0):
                self._out = out
                self._conf = conf

            def available(self):
                return True, ""

            def recognize_crop(self, _crop):
                return self._out, self._conf

        try:
            mod.ocr_backends.get_backend = lambda n: _Fake("management")
            hl = [{"text": "manay ment", "box": [10, 10, 200, 30]}]
            mod.recognizer.refine_handwriting_text(raw, proc, hl, "trocr")
            self.assertEqual(
                hl[0]["text"], "management"
            )  # similar -> accepted

            mod.ocr_backends.get_backend = lambda n: _Fake(
                "Transportation legislation", conf=0.2
            )
            hl = [{"text": "Hypothyoidum", "box": [10, 10, 200, 30]}]
            mod.recognizer.refine_handwriting_text(raw, proc, hl, "trocr")
            self.assertEqual(
                hl[0]["text"], "Hypothyoidum"
            )  # divergent + low confidence -> rejected
        finally:
            mod.ocr_backends.get_backend = orig

    def test_refinement_trusts_a_confident_specialist_over_paddle(self):
        # Paddle is not a handwriting specialist: on genuinely hard writing
        # its own reading can itself be wrong, so requiring agreement with a
        # wrong baseline would throw away a real correction. A confident
        # specialist reading is accepted even when it disagrees with paddle.
        mod = self.mod
        proc = np.full((100, 300, 3), 255, np.uint8)
        buf = io.BytesIO()
        Image.fromarray(proc).save(buf, format="PNG")
        raw = buf.getvalue()
        orig = mod.ocr_backends.get_backend

        class _Fake:
            def available(self):
                return True, ""

            def recognize_crop(self, _crop):
                return "ambulance", 0.92  # disagrees with paddle, but sure

        try:
            mod.ocr_backends.get_backend = lambda n: _Fake()
            hl = [{"text": "anhulane", "box": [10, 10, 200, 30]}]
            mod.recognizer.refine_handwriting_text(raw, proc, hl, "trocr")
            self.assertEqual(hl[0]["text"], "ambulance")
        finally:
            mod.ocr_backends.get_backend = orig

    def test_hybrid_mode_routes_by_script_trocr_english_surya_indic(self):
        # Hybrid mode must route each handwriting line to the
        # script-appropriate specialist: English -> trocr, Telugu -> surya.
        mod = self.mod
        proc = np.full((100, 300, 3), 255, np.uint8)
        buf = io.BytesIO()
        Image.fromarray(proc).save(buf, format="PNG")
        raw = buf.getvalue()
        orig = mod.ocr_backends.get_backend

        class _Fake:
            def __init__(self, out, conf):
                self._out, self._conf = out, conf

            def available(self):
                return True, ""

            def recognize_crop(self, _crop):
                return self._out, self._conf

        backends = {
            "trocr": _Fake("english word", 0.9),
            "surya": _Fake("తెలుగు పదం", 0.9),
        }
        try:
            mod.ocr_backends.get_backend = backends.get
            hl = [
                {"text": "garbled en", "box": [10, 10, 200, 30], "lang": "en"},
                {"text": "garbled te", "box": [10, 50, 200, 30], "lang": "te"},
            ]
            mod.recognizer.refine_handwriting_text(raw, proc, hl, "hybrid")
            self.assertEqual(hl[0]["text"], "english word")
            self.assertEqual(hl[0]["refined_by"], "trocr")
            self.assertEqual(hl[1]["text"], "తెలుగు పదం")
            self.assertEqual(hl[1]["refined_by"], "surya")
        finally:
            mod.ocr_backends.get_backend = orig

    def test_recognition_summary_proves_which_engine_refined_lines(self):
        # analysis.recognition.refined_by/refined_lines is the report's
        # verifiable proof that a specialist engine actually touched a
        # line -- not just that hybrid/trocr mode was requested. Setting
        # VAHINI_OCR_BACKEND=hybrid alone proves nothing if the specialist
        # was never installed or never accepted; this field is computed
        # from hand_lines' real per-line "refined_by" markers.
        mod = self.mod

        def fake_collect_hybrid(_arr_in, _lang):
            def rect(x, y, w, h):
                return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]

            lines = [
                {
                    "text": "garbled hand",
                    "score": 0.60,
                    "box": [10, 150, 360, 40],
                    "poly": rect(10, 150, 360, 40),
                    "lang": "en",
                },
            ]
            return lines, "", "hybrid", {"strategy": "hybrid"}

        class _Fake:
            def available(self):
                return True, ""

            def recognize_crop(self, _crop):
                return "clear word", 0.95

        # /report-python caches by (image bytes, lang, expected_text,
        # configured backend) -- reusing cls.png would return an earlier
        # test's cached response instead of exercising this one, since none
        # of those vary here. A one-pixel tweak gives a fresh cache key.
        arr2 = self.arr.copy()
        arr2[0, 0] = [254, 254, 254]
        buf = io.BytesIO()
        Image.fromarray(arr2).save(buf, format="PNG")
        png2 = buf.getvalue()

        orig_collect = mod.recognizer.collect_lines
        orig_get_backend = mod.ocr_backends.get_backend
        orig_memo = dict(mod.ocr_backends._SPEED_MEMO)
        mod.ocr_backends._SPEED_MEMO.clear()
        try:
            mod.recognizer.collect_lines = fake_collect_hybrid
            mod.ocr_backends.get_backend = lambda n: _Fake()
            r = self.client.post(
                "/report-python",
                files={"image": ("page.png", png2, "image/png")},
                data={"lang": "auto"},
            )
            j = r.json()
            rec = j["analysis"]["recognition"]
            self.assertEqual(rec["refined_by"], {"trocr": 1})
            self.assertEqual(rec["refined_lines"], 1)
        finally:
            mod.recognizer.collect_lines = orig_collect
            mod.ocr_backends.get_backend = orig_get_backend
            mod.ocr_backends._SPEED_MEMO.clear()
            mod.ocr_backends._SPEED_MEMO.update(orig_memo)

    def test_refinement_measures_speed_and_skips_a_slow_engine(self):
        # A real, measured latency on THIS machine decides whether hybrid
        # mode keeps using a specialist — not a synthetic benchmark. A
        # fresh engine gets one real measurement; once it is slow, later
        # lines (and later calls) skip it entirely without invoking it.
        mod = self.mod
        proc = np.full((100, 300, 3), 255, np.uint8)
        buf = io.BytesIO()
        Image.fromarray(proc).save(buf, format="PNG")
        raw = buf.getvalue()
        orig_get_backend = mod.ocr_backends.get_backend
        orig_memo = dict(mod.ocr_backends._SPEED_MEMO)
        mod.ocr_backends._SPEED_MEMO.clear()

        calls = []

        class _SlowFake:
            def available(self):
                return True, ""

            def recognize_crop(self, _crop):
                calls.append(1)
                time.sleep(0.02)  # stand-in for a genuinely slow engine
                return "corrected", 0.95

        try:
            mod.ocr_backends.get_backend = lambda n: _SlowFake()
            # Force the "too slow" verdict directly (real hardware would
            # take real elapsed time to prove this; the memo is what
            # subsequent lines/calls actually consult).
            mod.ocr_backends.record_engine_speed("trocr", 9000.0)
            hl = [{"text": "manay ment", "box": [10, 10, 200, 30]}]
            mod.recognizer.refine_handwriting_text(raw, proc, hl, "trocr")
            self.assertEqual(hl[0]["text"], "manay ment")  # untouched
            self.assertEqual(calls, [])  # engine was never even called
        finally:
            mod.ocr_backends.get_backend = orig_get_backend
            mod.ocr_backends._SPEED_MEMO.clear()
            mod.ocr_backends._SPEED_MEMO.update(orig_memo)

    def test_pdf_restricted_to_first_page(self):
        # A multi-page PDF must decode to page 1 ONLY. Page 1 is 200x120,
        # page 2 is a different 400x300, so the decoded size proves which page.
        if importlib.util.find_spec("pypdfium2") is None:
            self.skipTest("pypdfium2 not installed")
        p1 = Image.new("RGB", (200, 120), "white")
        p2 = Image.new("RGB", (400, 300), "white")
        buf = io.BytesIO()
        p1.save(buf, format="PDF", save_all=True, append_images=[p2])
        img = self.mod._decode_image(buf.getvalue())
        # Rendered at 150 DPI, so aspect ratio (not exact px) identifies page 1.
        self.assertAlmostEqual(img.size[0] / img.size[1], 200 / 120, places=1)

    def test_concurrent_analyses_run_in_parallel_not_serialized(self):
        # Several users (or tabs) analysing at the same time must not fully
        # queue up behind one slow request: /report-python offloads its heavy
        # work via run_in_threadpool, so the event loop stays free to
        # dispatch the others while it runs.
        orig_collect = self.mod.recognizer.collect_lines
        delay = 0.35

        def slow_collect(arr_in, lang):
            time.sleep(delay)
            return orig_collect(arr_in, lang)

        self.mod.recognizer.collect_lines = slow_collect
        try:
            n = 5

            def call(i):
                r = self.client.post(
                    "/report-python",
                    files={"image": ("page.png", self.png, "image/png")},
                    data={"lang": "auto", "expected_text": f"passage-{i}"},
                )
                return i, r

            t0 = time.perf_counter()
            with ThreadPoolExecutor(max_workers=n) as ex:
                results = list(ex.map(call, range(n)))
            elapsed = time.perf_counter() - t0

            for i, r in results:
                self.assertEqual(r.status_code, 200)
                j = r.json()
                self.assertTrue(j.get("ok"), j)
                # Each response must carry back its OWN request's data,
                # not another concurrent request's: proves no cross-talk.
                self.assertEqual(j.get("expected_text"), f"passage-{i}")

            # Serialized would take n * delay (>=1.75s here); truly
            # concurrent work lands well under that even with scheduling
            # overhead.
            self.assertLess(elapsed, n * delay * 0.7)
        finally:
            self.mod.recognizer.collect_lines = orig_collect


if __name__ == "__main__":
    unittest.main()
