import io
import importlib.util
import sys
import types
import unittest
from pathlib import Path
import numpy as np

try:
    from PIL import Image, ImageDraw
except Exception:
    Image = None
    ImageDraw = None

try:
    from fastapi.testclient import TestClient
except Exception:
    TestClient = None


SERVER_FILE = Path(__file__).resolve().parents[1] / "ppocr-server.py"


class _FakePaddleEngine:
    def __init__(self, lang="en", **_kwargs):
        self.lang = lang

    def ocr(self, arr):
        h, w = arr.shape[:2]
        return [
            {
                "rec_texts": ["Dear Sir", "This is a functional test"],
                "rec_polys": [
                    [[10.0, 10.0], [w * 0.72, 10.0], [w * 0.72, 34.0], [10.0, 34.0]],
                    [[10.0, 44.0], [w * 0.92, 44.0], [w * 0.92, 76.0], [10.0, 76.0]],
                ],
                "rec_scores": [0.99, 0.97],
            }
        ]

    def predict(self, arr):
        return self.ocr(arr)


class _FakePaddleOCR:
    def __new__(cls, *args, **kwargs):
        return _FakePaddleEngine(*args, **kwargs)


def _load_server_module():
    fake = types.ModuleType("paddleocr")
    fake.PaddleOCR = _FakePaddleOCR
    sys.modules["paddleocr"] = fake

    spec = importlib.util.spec_from_file_location("vahini_ppocr_server_test", str(SERVER_FILE))
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load ppocr-server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Force deterministic local test languages.
    module.OCR_LANGS = ["en", "te"]

    return module


def _sample_image_bytes():
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow is required for regression tests")
    img = Image.new("RGB", (640, 240), "white")
    d = ImageDraw.Draw(img)
    d.text((20, 20), "Dear Sir", fill="black")
    d.text((20, 64), "This is a functional test", fill="black")
    d.text((20, 108), "Vahini regression", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class RegressionFunctionalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if TestClient is None:
            raise unittest.SkipTest("fastapi/testclient not available; install server requirements first")
        if Image is None or ImageDraw is None:
            raise unittest.SkipTest("Pillow not available; install server requirements first")
        cls.mod = _load_server_module()
        cls.client = TestClient(cls.mod.app)
        cls.image_bytes = _sample_image_bytes()

    def test_health_endpoint(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertTrue(j.get("ok"))
        self.assertIn("engine", j)

    def test_ocr_endpoint_regression_contract(self):
        files = {"image": ("sample.png", self.image_bytes, "image/png")}
        data = {"lang": "en", "det": "true", "rec": "true"}
        r = self.client.post("/ocr", files=files, data=data)
        self.assertEqual(r.status_code, 200)
        j = r.json()

        # Core OCR fields used by frontend normalization.
        for key in ["rec_texts", "rec_polys", "rec_scores", "full_text", "engine"]:
            self.assertIn(key, j)

        self.assertGreater(len(j["rec_texts"]), 0)
        self.assertEqual(len(j["rec_texts"]), len(j["rec_scores"]))
        self.assertEqual(len(j["rec_texts"]), len(j["rec_polys"]))
        self.assertIsInstance(j.get("printed_hints", []), list)

    def test_analyze_vl_endpoint_functional(self):
        files = {"image": ("sample.png", self.image_bytes, "image/png")}
        data = {"lang": "en"}
        r = self.client.post("/analyze-vl", files=files, data=data)
        self.assertEqual(r.status_code, 200)
        j = r.json()

        self.assertTrue(j.get("ok"), msg=j.get("error"))
        self.assertIn("document_context", j)
        self.assertIn("layout", j)
        self.assertIn("regions", j)
        self.assertIn("factor_regions", j)

        # OCR payload compatibility still present.
        self.assertIn("rec_texts", j)
        self.assertIn("rec_scores", j)
        self.assertEqual(len(j["rec_texts"]), len(j["rec_scores"]))

        # Vision/layout regression checks.
        layout = j["layout"]
        self.assertGreaterEqual(float(layout.get("line_density", 0.0)), 0.0)
        self.assertLessEqual(float(layout.get("line_density", 1.0)), 1.0)
        self.assertGreaterEqual(float(layout.get("layout_complexity", 0.0)), 0.0)
        self.assertLessEqual(float(layout.get("layout_complexity", 1.0)), 1.0)
        self.assertGreaterEqual(int(layout.get("cc_count", 0)), 0)

        # Region extraction previews for frontend display.
        self.assertGreater(len(j["regions"]), 0)
        self.assertTrue(j["regions"][0].get("preview", "").startswith("data:image/jpeg;base64,"))

        # Backend-first factor evidence crops should cover all 20 factors.
        fmap = j["factor_regions"]
        self.assertEqual(len(fmap), 20)
        self.assertIn("1", fmap)
        self.assertIn("20", fmap)
        self.assertTrue(str(fmap["1"].get("url", "")).startswith("data:image/jpeg;base64,"))

    def test_report_python_endpoint_contract(self):
        files = {"image": ("sample.png", self.image_bytes, "image/png")}
        data = {"lang": "en", "expected_text": "Dear Sir"}
        r = self.client.post("/report-python", files=files, data=data)
        self.assertEqual(r.status_code, 200)
        j = r.json()

        self.assertTrue(j.get("ok"), msg=j.get("error"))
        self.assertIn("analysis", j)
        a = j["analysis"]
        self.assertIsInstance(a.get("results"), list)
        self.assertIsInstance(a.get("sections"), list)
        self.assertEqual(len(a.get("results", [])), 20)
        self.assertGreaterEqual(int(a.get("overall", 0)), 0)
        self.assertLessEqual(int(a.get("overall", 100)), 100)
        self.assertEqual(a.get("source"), "python")
        self.assertGreaterEqual(int(a.get("measuredCount", 0)), 20)

    def test_report_python_cache_hit(self):
        files = {"image": ("sample.png", self.image_bytes, "image/png")}
        data = {"lang": "en", "expected_text": "Dear Sir"}

        r1 = self.client.post("/report-python", files=files, data=data)
        self.assertEqual(r1.status_code, 200)
        j1 = r1.json()
        self.assertTrue(j1.get("ok"), msg=j1.get("error"))
        self.assertEqual(((j1.get("_meta") or {}).get("cache")), "miss")

        r2 = self.client.post("/report-python", files=files, data=data)
        self.assertEqual(r2.status_code, 200)
        j2 = r2.json()
        self.assertTrue(j2.get("ok"), msg=j2.get("error"))
        self.assertEqual(((j2.get("_meta") or {}).get("cache")), "hit")

    def test_auto_short_circuit_limits_variant_calls(self):
        old_langs = list(self.mod.OCR_LANGS)
        old_auto = self.mod.AUTO_MIN_LINES
        old_variant = self.mod.VARIANT_MIN_LINES
        orig_run = self.mod._run
        calls = {"n": 0}

        def counted_run(engine, arr, lang):
            calls["n"] += 1
            return orig_run(engine, arr, lang)

        try:
            self.mod.OCR_LANGS = ["en", "te", "hi"]
            self.mod.AUTO_MIN_LINES = 1
            self.mod.VARIANT_MIN_LINES = 1
            self.mod._run = counted_run
            files = {"image": ("sample.png", self.image_bytes, "image/png")}
            r = self.client.post("/report-python", files=files, data={"lang": "auto", "expected_text": "x"})
            self.assertEqual(r.status_code, 200)
            j = r.json()
            self.assertTrue(j.get("ok"), msg=j.get("error"))
            # One run is enough to satisfy both variant and language thresholds.
            self.assertLessEqual(calls["n"], 1)
        finally:
            self.mod._run = orig_run
            self.mod.OCR_LANGS = old_langs
            self.mod.AUTO_MIN_LINES = old_auto
            self.mod.VARIANT_MIN_LINES = old_variant

    def test_opencv_path_does_not_fail_when_unavailable(self):
        original_cv2 = self.mod.cv2
        self.mod.cv2 = None
        try:
            files = {"image": ("sample.png", self.image_bytes, "image/png")}
            data = {"lang": "en"}
            r = self.client.post("/analyze-vl", files=files, data=data)
            self.assertEqual(r.status_code, 200)
            j = r.json()
            self.assertTrue(j.get("ok"), msg=j.get("error"))
            self.assertIn("layout", j)
            self.assertIn("layout_complexity", j["layout"])
        finally:
            self.mod.cv2 = original_cv2

    def test_twenty_factor_pipeline_contract_compat(self):
        files = {"image": ("sample.png", self.image_bytes, "image/png")}
        r = self.client.post("/analyze-vl", files=files, data={"lang": "en"})
        self.assertEqual(r.status_code, 200)
        j = r.json()

        # The JS 20-factor engine is still the scorer. Backend must preserve OCR keys
        # consumed by frontend without breaking the existing scoring pipeline.
        for key in ["rec_texts", "rec_polys", "rec_scores", "full_text", "printed_hints"]:
            self.assertIn(key, j)

        self.assertEqual(len(j["rec_texts"]), len(j["rec_polys"]))
        self.assertEqual(len(j["rec_texts"]), len(j["rec_scores"]))

    def test_factor_region_selection_heuristics(self):
        arr = np.full((220, 640, 3), 255, dtype=np.uint8)
        regions = [
            {"preview": "p0", "bbox": [5.0, 10.0, 60.0, 24.0], "text": "Hi", "score": 0.96},
            {"preview": "p1", "bbox": [80.0, 42.0, 300.0, 28.0], "text": "this is spaced words", "score": 0.95},
            {"preview": "p2", "bbox": [120.0, 82.0, 110.0, 30.0], "text": "letters", "score": 0.94},
            {"preview": "p3", "bbox": [260.0, 120.0, 70.0, 45.0], "text": "Tall", "score": 0.97},
            {"preview": "p4", "bbox": [340.0, 160.0, 30.0, 18.0], "text": "a", "score": 0.98},
        ]

        fmap = self.mod._factor_region_map(arr, regions)

        self.assertEqual(fmap["8"]["url"], "p1")   # word spacing -> multi-word line
        self.assertEqual(fmap["10"]["url"], "p0")  # margin -> left-most region
        self.assertEqual(fmap["9"]["url"], "p2")   # letter spacing -> single-word region
        self.assertEqual(fmap["12"]["url"], "p3")  # vertical alignment -> taller region

        # full-page factors intentionally use whole-page fallback, not line crops
        self.assertTrue(str(fmap["18"]["url"]).startswith("data:image/jpeg;base64,"))
        self.assertTrue(str(fmap["20"]["url"]).startswith("data:image/jpeg;base64,"))

    def test_prefer_handwritten_filter(self):
        lines = [
            {"text": "SCHOOL NAME", "score": 0.995, "printed_hint": True, "box": [10, 10, 260, 28]},
            {"text": "Class 8", "score": 0.992, "printed_hint": True, "box": [10, 42, 130, 24]},
            {"text": "my handwriting line", "score": 0.91, "printed_hint": False, "box": [10, 84, 360, 30]},
            {"text": "second line written", "score": 0.90, "printed_hint": False, "box": [10, 122, 340, 30]},
        ]
        out = self.mod._prefer_handwritten(lines)
        texts = [x.get("text", "") for x in out]
        self.assertIn("my handwriting line", texts)
        self.assertIn("second line written", texts)
        self.assertNotIn("SCHOOL NAME", texts)

    def test_printed_form_lines_are_suppressed_in_mixed_content(self):
        lines = [
            {"text": "HOSPITAL DISCHARGE SUMMARY", "score": 0.997, "printed_hint": True, "box": [30, 20, 560, 26]},
            {"text": "Patient Name:", "score": 0.992, "printed_hint": True, "box": [32, 62, 180, 22]},
            {"text": "Age: 31 Sex: M", "score": 0.989, "printed_hint": True, "box": [240, 62, 220, 22]},
            {"text": "complaint of pain since 2 days", "score": 0.90, "printed_hint": False, "box": [35, 120, 480, 28]},
            {"text": "advised rest and followup", "score": 0.89, "printed_hint": False, "box": [35, 158, 360, 28]},
        ]
        out = self.mod._prefer_handwritten(lines)
        texts = [x.get("text", "") for x in out]
        self.assertIn("complaint of pain since 2 days", texts)
        self.assertIn("advised rest and followup", texts)
        self.assertNotIn("HOSPITAL DISCHARGE SUMMARY", texts)
        self.assertNotIn("Patient Name:", texts)

    def test_printed_keywords_excluded_even_with_low_confidence(self):
        lines = [
            {"text": "Patient Name:", "score": 0.73, "printed_hint": True, "box": [30, 22, 180, 22]},
            {"text": "Date:", "score": 0.70, "printed_hint": True, "box": [30, 52, 88, 22]},
            {"text": "pain started yesterday", "score": 0.81, "printed_hint": False, "box": [34, 110, 280, 30]},
            {"text": "taking tablets", "score": 0.79, "printed_hint": False, "box": [34, 150, 190, 30]},
        ]
        out = self.mod._prefer_handwritten(lines)
        texts = [x.get("text", "") for x in out]
        self.assertIn("pain started yesterday", texts)
        self.assertIn("taking tablets", texts)
        self.assertNotIn("Patient Name:", texts)
        self.assertNotIn("Date:", texts)

    def test_region_filter_drops_noise_headers_and_ids(self):
        lines = [
            {"text": "H", "score": 0.72, "printed_hint": False, "box": [12, 10, 8, 10]},
            {"text": "IP No: 7817", "score": 0.96, "printed_hint": True, "box": [420, 12, 180, 20]},
            {"text": "my pain started yesterday", "score": 0.86, "printed_hint": False, "box": [36, 126, 300, 28]},
            {"text": "taking tablets", "score": 0.83, "printed_hint": False, "box": [38, 162, 180, 28]},
        ]
        out = self.mod._region_filter_lines(lines, (500, 700, 3))
        texts = [x.get("text", "") for x in out]
        self.assertIn("my pain started yesterday", texts)
        self.assertIn("taking tablets", texts)
        self.assertNotIn("H", texts)
        self.assertNotIn("IP No: 7817", texts)


if __name__ == "__main__":
    unittest.main()
