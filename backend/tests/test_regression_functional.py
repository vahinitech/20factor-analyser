import io
import importlib.util
import math
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


SERVER_DIR = Path(__file__).resolve().parents[1]
SERVER_FILE = SERVER_DIR / "ppocr-server.py"
sys.path.insert(0, str(SERVER_DIR))

import detector  # noqa: E402  pylint: disable=wrong-import-position

# White-box tests deliberately reach into module-private helpers below.
# pylint: disable=protected-access


class _FakePaddleEngine:
    def __init__(self, lang="en", **_kwargs):
        self.lang = lang

    def ocr(self, arr):
        _h, w = arr.shape[:2]
        return [
            {
                "rec_texts": ["Dear Sir", "This is a functional test"],
                "rec_polys": [
                    [
                        [10.0, 10.0],
                        [w * 0.72, 10.0],
                        [w * 0.72, 34.0],
                        [10.0, 34.0],
                    ],
                    [
                        [10.0, 44.0],
                        [w * 0.92, 44.0],
                        [w * 0.92, 76.0],
                        [10.0, 76.0],
                    ],
                ],
                # Handwriting-typical confidences. Machine type reads at
                # 0.96+, and the classifier (correctly) refuses pages where
                # everything reads that cleanly — these fakes simulate PEN
                # writing, so they must read like pen writing.
                "rec_scores": [0.78, 0.72],
            }
        ]

    def predict(self, arr):
        return self.ocr(arr)


class _FakePaddleOCR:  # pylint: disable=too-few-public-methods
    def __new__(cls, *args, **kwargs):
        return _FakePaddleEngine(*args, **kwargs)


def _load_server_module():
    fake = types.ModuleType("paddleocr")
    fake.PaddleOCR = _FakePaddleOCR
    sys.modules["paddleocr"] = fake

    spec = importlib.util.spec_from_file_location(
        "vahini_ppocr_server_test", str(SERVER_FILE)
    )
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
            raise unittest.SkipTest(
                "fastapi/testclient not available; install server requirements first"
            )
        if Image is None or ImageDraw is None:
            raise unittest.SkipTest(
                "Pillow not available; install server requirements first"
            )
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
        for key in [
            "rec_texts",
            "rec_polys",
            "rec_scores",
            "full_text",
            "engine",
        ]:
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
        self.assertGreaterEqual(
            float(layout.get("layout_complexity", 0.0)), 0.0
        )
        self.assertLessEqual(float(layout.get("layout_complexity", 1.0)), 1.0)
        self.assertGreaterEqual(int(layout.get("cc_count", 0)), 0)

        # Region extraction previews for frontend display.
        self.assertGreater(len(j["regions"]), 0)
        self.assertTrue(
            j["regions"][0]
            .get("preview", "")
            .startswith("data:image/jpeg;base64,")
        )

        # Backend-first factor evidence crops should cover all 20 factors.
        fmap = j["factor_regions"]
        self.assertEqual(len(fmap), 20)
        self.assertIn("1", fmap)
        self.assertIn("20", fmap)
        self.assertTrue(
            str(fmap["1"].get("url", "")).startswith("data:image/jpeg;base64,")
        )

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

        # Renderer-completeness: the browser is render-only now, so every factor
        # must arrive with the rendering extras (drill group, target band, tip)
        # the report cards / exercises page read.
        valid_ex = {"round", "slant", "rhythm", "frame", "wave"}
        for r in a["results"]:
            self.assertIn(
                r.get("ex"),
                valid_ex,
                msg=f"factor {r.get('n')} ex={r.get('ex')!r}",
            )
            self.assertTrue(
                str(r.get("target") or "").strip(),
                msg=f"factor {r.get('n')} has no target",
            )
            self.assertTrue(
                str(r.get("tip") or "").strip(),
                msg=f"factor {r.get('n')} has no tip",
            )

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
        # OCR_LANGS/AUTO_MIN_LINES/VARIANT_MIN_LINES are snapshotted into
        # recognizer._CFG once at startup (recognizer.configure(...)); the
        # dispatch loop reads that config, not the ppocr-server module
        # attributes, so reconfigure recognizer directly here.
        old_cfg = dict(self.mod.recognizer._CFG)
        orig_run = self.mod.ocr_backends.run
        calls = {"n": 0}

        def counted_run(engine, arr, lang):
            calls["n"] += 1
            return orig_run(engine, arr, lang)

        try:
            self.mod.recognizer.configure(
                ocr_langs=["en", "te", "hi"],
                auto_min_lines=1,
                variant_min_lines=1,
            )
            self.mod.ocr_backends.run = counted_run
            files = {"image": ("sample.png", self.image_bytes, "image/png")}
            r = self.client.post(
                "/report-python",
                files=files,
                data={"lang": "auto", "expected_text": "x"},
            )
            self.assertEqual(r.status_code, 200)
            j = r.json()
            self.assertTrue(j.get("ok"), msg=j.get("error"))
            # One run is enough to satisfy both variant and language thresholds.
            self.assertLessEqual(calls["n"], 1)
        finally:
            self.mod.ocr_backends.run = orig_run
            self.mod.recognizer._CFG.update(old_cfg)

    def test_opencv_path_does_not_fail_when_unavailable(self):
        # The layout/context CV now lives in computer_vision.py, which owns
        # its own cv2 binding; that's the one the endpoint actually uses.
        original_cv2 = self.mod.computer_vision.cv2
        self.mod.computer_vision.cv2 = None
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
            self.mod.computer_vision.cv2 = original_cv2

    def test_twenty_factor_pipeline_contract_compat(self):
        files = {"image": ("sample.png", self.image_bytes, "image/png")}
        r = self.client.post("/analyze-vl", files=files, data={"lang": "en"})
        self.assertEqual(r.status_code, 200)
        j = r.json()

        # The Python server is the 20-factor scorer; /analyze-vl must still expose the
        # OCR keys the browser render layer consumes without breaking that contract.
        for key in [
            "rec_texts",
            "rec_polys",
            "rec_scores",
            "full_text",
            "printed_hints",
        ]:
            self.assertIn(key, j)

        self.assertEqual(len(j["rec_texts"]), len(j["rec_polys"]))
        self.assertEqual(len(j["rec_texts"]), len(j["rec_scores"]))

    def test_factor_region_selection_heuristics(self):
        arr = np.full((220, 640, 3), 255, dtype=np.uint8)
        regions = [
            {
                "preview": "p0",
                "bbox": [5.0, 10.0, 60.0, 24.0],
                "text": "Hi",
                "score": 0.96,
            },
            {
                "preview": "p1",
                "bbox": [80.0, 42.0, 300.0, 28.0],
                "text": "this is spaced words",
                "score": 0.95,
            },
            {
                "preview": "p2",
                "bbox": [120.0, 82.0, 110.0, 30.0],
                "text": "letters",
                "score": 0.94,
            },
            {
                "preview": "p3",
                "bbox": [260.0, 120.0, 70.0, 45.0],
                "text": "Tall",
                "score": 0.97,
            },
            {
                "preview": "p4",
                "bbox": [340.0, 160.0, 30.0, 18.0],
                "text": "a",
                "score": 0.98,
            },
        ]

        fmap = self.mod.computer_vision._factor_region_map(arr, regions)

        self.assertEqual(
            fmap["8"]["url"], "p1"
        )  # word spacing -> multi-word line
        self.assertEqual(fmap["10"]["url"], "p0")  # margin -> left-most region
        self.assertEqual(
            fmap["9"]["url"], "p2"
        )  # letter spacing -> single-word region
        self.assertEqual(
            fmap["12"]["url"], "p3"
        )  # vertical alignment -> taller region

        # full-page factors intentionally use whole-page fallback, not line crops
        self.assertTrue(
            str(fmap["18"]["url"]).startswith("data:image/jpeg;base64,")
        )
        self.assertTrue(
            str(fmap["20"]["url"]).startswith("data:image/jpeg;base64,")
        )

    def test_margin_evidence_uses_true_leftmost_line_not_area_ranked_pool(
        self,
    ):
        # Regression for a real bug report: on a busy page (more lines than
        # _build_region_previews' area-ranked pool cap of 8), the actual
        # left-most line can be short and get excluded from that pool before
        # factor 10's "left-most in the pool" pick ever runs, so the shown
        # evidence silently becomes an arbitrary large line instead of the
        # true margin. 9 wide lines all start at x=100; one short line
        # starts at x=5, the true left margin, but its small area guarantees
        # it sorts last and is dropped by the pool's max_regions=8 cap.
        arr = np.full((450, 700, 3), 255, dtype=np.uint8)
        lines = [
            {
                "box": [100.0, 20.0 + i * 40.0, 500.0, 30.0],
                "text": "wide line",
                "score": 0.9,
            }
            for i in range(9)
        ]
        lines.append(
            {"box": [5.0, 400.0, 40.0, 20.0], "text": "hi", "score": 0.9}
        )

        cv = self.mod.computer_vision
        regions = cv._build_region_previews(arr, lines)
        # Confirms the setup actually reproduces the exclusion this test guards against.
        self.assertNotIn(
            5.0,
            [r["bbox"][0] for r in regions],
            "test setup didn't reproduce the pool exclusion; fix the fixture",
        )

        fmap = cv._factor_region_map(arr, regions, lines)
        leftmost_crop = cv._to_data_url(
            cv._crop_rgb(arr, [5.0, 400.0, 40.0, 20.0]), quality=90
        )
        self.assertEqual(fmap["10"]["url"], leftmost_crop)

    def test_margin_score_survives_camera_tilt_on_a_straight_margin(self):
        # Regression for a real bug report: Margin Discipline scored a
        # visually-fine left margin as "Needs support" on a page photographed
        # at an angle. Root cause: left_cv measured each line's raw pixel
        # left-x, which drifts across the page under a uniform camera tilt
        # even when the physical margin is perfectly straight, because
        # rotating a point shifts its x by an amount that grows with how
        # far down the page it is.
        #
        # This builds 8 lines whose TRUE (pre-photo) left edge is identical
        # (local x=200 at 8 different heights), then rotates each line's
        # reference point AND its own poly slope by a shared 6 degree tilt
        # around the image centre, simulating exactly that kind of photo.
        # Before the fix, left_cv on the rotated positions is large; after
        # it, the detilt correction should recover the original, near-zero
        # variance.
        w, h = 1000, 1000
        cx, cy = w / 2.0, h / 2.0
        tilt_deg = 6.0
        rad = math.radians(tilt_deg)
        cos_t, sin_t = math.cos(rad), math.sin(rad)

        def rotate(x, y):
            dx, dy = x - cx, y - cy
            return (
                cx + dx * cos_t - dy * sin_t,
                cy + dx * sin_t + dy * cos_t,
            )

        true_left = 200.0
        line_len = 300.0
        box_h = 30.0
        lines = []
        raw_lefts = []
        for true_y in (150.0, 250.0, 350.0, 450.0, 550.0, 650.0, 750.0, 850.0):
            rx0, ry0 = rotate(true_left, true_y)
            rx1, ry1 = rotate(true_left + line_len, true_y)
            raw_lefts.append(rx0 / w)
            lines.append(
                {
                    "box": [rx0, ry0 - box_h / 2.0, line_len, box_h],
                    "poly": [[rx0, ry0], [rx1, ry1]],
                    "text": "tilted line",
                    "score": 0.9,
                }
            )

        scoring = self.mod.scoring
        arr = np.full((h, w, 3), 255, dtype=np.uint8)
        fx = scoring._extract_features(arr, lines, {})

        # The setup must actually reproduce a tilt-inflated raw CV, or this
        # test isn't exercising the bug it guards against.
        raw_cv = scoring._cv(raw_lefts)
        self.assertGreater(
            raw_cv,
            0.1,
            "test setup didn't reproduce tilt-inflated left_cv; fix the fixture",
        )

        self.assertLess(fx["left_cv"], 0.02)
        self.assertGreaterEqual(scoring._score_factor_map(fx)[10], 9.5)

    @staticmethod
    def _print_style_line_image(w=600, h=80, n_blobs=14):
        # Disconnected letters: separate blobs with real gaps between them,
        # one blob per (simulated) letter.
        img = Image.new("RGB", (w, h), "white")
        d = ImageDraw.Draw(img)
        blob_w, gap, x = 20, 15, 20
        for _ in range(n_blobs):
            d.rectangle([x, 20, x + blob_w, 60], fill="black")
            x += blob_w + gap
        return np.array(img)

    @staticmethod
    def _cursive_style_line_image(w=600, h=80):
        # Joined letters: one continuous zigzag stroke end to end, so the
        # whole "word" is a single connected ink blob.
        img = Image.new("RGB", (w, h), "white")
        d = ImageDraw.Draw(img)
        pts = [(20 + i * 25, 20 if i % 2 == 0 else 60) for i in range(23)]
        d.line(pts, fill="black", width=10, joint="curve")
        return np.array(img)

    def test_writing_style_print_vs_cursive_from_ink_connectivity(self):
        # Regression/feature check: writing style is read from how many
        # separate ink blobs a line's letters actually form (many blobs
        # close to the letter count = print; few blobs = letters are
        # joined = cursive), never from asking an OCR/VLM engine to guess
        # and never scored, only shown as descriptive context.
        cv = self.mod.computer_vision
        fourteen_letters = "abcdefghijklmn"

        print_arr = self._print_style_line_image()
        print_style = cv.infer_writing_style(
            print_arr, [{"box": [0, 0, 600, 80], "text": fourteen_letters}]
        )
        self.assertEqual(print_style["style"], "print")

        cursive_arr = self._cursive_style_line_image()
        cursive_style = cv.infer_writing_style(
            cursive_arr, [{"box": [0, 0, 600, 80], "text": fourteen_letters}]
        )
        self.assertEqual(cursive_style["style"], "cursive")

    def test_writing_style_withholds_a_verdict_without_enough_evidence(self):
        cv = self.mod.computer_vision
        arr = np.full((80, 400, 3), 255, dtype=np.uint8)
        style = cv.infer_writing_style(
            arr, [{"box": [0, 0, 400, 80], "text": "hi"}]
        )
        self.assertIsNone(style["style"])
        self.assertEqual(style["confidence"], 0.0)

    def test_factor_regions_reference_image_for_all_20(self):
        # EVERY analysis must carry a usable reference image for each of
        # the 20 factors (a line crop or the whole-page fallback).
        files = {"image": ("sample.png", self.image_bytes, "image/png")}
        r = self.client.post(
            "/report-python",
            files=files,
            data={"lang": "en", "expected_text": "ref-image-check"},
        )
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertTrue(j.get("ok"), msg=j.get("error"))
        fmap = j["factor_regions"]
        self.assertEqual(len(fmap), 20)
        for n in range(1, 21):
            entry = fmap.get(str(n)) or {}
            self.assertTrue(
                str(entry.get("url", "")).startswith(
                    "data:image/jpeg;base64,"
                ),
                msg=f"factor {n} has no reference image",
            )
            self.assertTrue(
                str(entry.get("caption") or "").strip(),
                msg=f"factor {n} has no caption",
            )

    def test_scan_survives_engine_init_failure(self):
        # get_engine raising at request time (e.g. first-use model download
        # on a blocked/offline network) previously killed the whole scan.
        # The report must still be produced from CV geometry, with a
        # reference image for every one of the 20 factors, and recognition
        # honestly reported as unavailable.
        ob = self.mod.ocr_backends
        orig_engine = ob.get_engine
        orig_safe = ob.get_engine_safe

        def _boom(_lang):
            raise RuntimeError("model download blocked (offline)")

        ob.get_engine = _boom
        ob.get_engine_safe = _boom
        try:
            files = {"image": ("sample.png", self.image_bytes, "image/png")}
            r = self.client.post(
                "/report-python",
                files=files,
                data={"lang": "en", "expected_text": "engine-init-failure"},
            )
            self.assertEqual(r.status_code, 200)
            j = r.json()
            self.assertTrue(j.get("ok"), msg=j.get("error"))
            a = j["analysis"]
            self.assertEqual(len(a.get("results", [])), 20)
            self.assertEqual(
                a.get("recognition", {}).get("level"), "unavailable"
            )
            self.assertEqual(j.get("selected_backend"), "cv-fallback")
            fmap = j["factor_regions"]
            self.assertEqual(len(fmap), 20)
            for n in range(1, 21):
                self.assertTrue(
                    str((fmap.get(str(n)) or {}).get("url", "")).startswith(
                        "data:image/jpeg;base64,"
                    ),
                    msg=f"factor {n} lost its reference image in fallback",
                )
        finally:
            ob.get_engine = orig_engine
            ob.get_engine_safe = orig_safe

    def test_collect_lines_paddle_engine_failure_returns_error(self):
        # The recognizer must catch engine-construction failures and hand
        # back (no lines, reason) instead of raising.
        ob = self.mod.ocr_backends
        orig_engine = ob.get_engine
        orig_safe = ob.get_engine_safe

        def _boom(_lang):
            raise RuntimeError("no model source available")

        ob.get_engine = _boom
        ob.get_engine_safe = _boom
        try:
            arr = np.full((120, 320, 3), 255, dtype=np.uint8)
            lines, err = self.mod.recognizer.collect_lines_paddle(arr, "en")
            self.assertEqual(lines, [])
            self.assertIn("no model source available", err)
        finally:
            ob.get_engine = orig_engine
            ob.get_engine_safe = orig_safe

    def test_engine_failure_memo_fails_fast_until_ttl(self):
        # A failed engine build (slow: the model download walks several
        # hosters before giving up) must be remembered, so the next scan
        # fails over to the CV fallback instantly instead of re-paying the
        # download timeout — then retries after the cooldown.
        ob = self.mod.ocr_backends
        orig_build = ob._build_engine_cached
        calls = {"n": 0}

        def _boom_build(_lang):
            calls["n"] += 1
            raise RuntimeError("download timed out")

        ob._build_engine_cached = _boom_build
        ob._ENGINE_FAIL_CACHE.clear()
        try:
            for _ in range(3):
                with self.assertRaises(RuntimeError):
                    ob.get_engine("zz")
            self.assertEqual(calls["n"], 1)  # only the first call builds

            # After the TTL the build is attempted again.
            ts, err = ob._ENGINE_FAIL_CACHE[("normal", "zz")]
            ob._ENGINE_FAIL_CACHE[("normal", "zz")] = (
                ts - ob._ENGINE_FAIL_TTL - 1,
                err,
            )
            with self.assertRaises(RuntimeError):
                ob.get_engine("zz")
            self.assertEqual(calls["n"], 2)
        finally:
            ob._build_engine_cached = orig_build
            ob._ENGINE_FAIL_CACHE.clear()

    def test_fallback_line_regions_detects_synthetic_lines(self):
        cvis = self.mod.computer_vision
        arr = np.array(Image.open(io.BytesIO(self.image_bytes)))
        got = cvis.fallback_line_regions(arr)
        self.assertGreater(len(got), 0)
        for l in got:
            self.assertEqual(l.get("text"), "")
            self.assertEqual(len(l.get("box", [])), 4)
            self.assertEqual(len(l.get("poly", [])), 4)
            self.assertFalse(l.get("printed_hint"))

        # The OpenCV-free path must work too (cv2 can be missing).
        orig_cv2 = cvis.cv2
        cvis.cv2 = None
        try:
            got_np = cvis.fallback_line_regions(arr)
            self.assertGreater(len(got_np), 0)
        finally:
            cvis.cv2 = orig_cv2

    def test_prefer_handwritten_filter(self):
        lines = [
            {
                "text": "SCHOOL NAME",
                "score": 0.995,
                "printed_hint": True,
                "box": [10, 10, 260, 28],
            },
            {
                "text": "Class 8",
                "score": 0.992,
                "printed_hint": True,
                "box": [10, 42, 130, 24],
            },
            {
                "text": "my handwriting line",
                "score": 0.91,
                "printed_hint": False,
                "box": [10, 84, 360, 30],
            },
            {
                "text": "second line written",
                "score": 0.90,
                "printed_hint": False,
                "box": [10, 122, 340, 30],
            },
        ]
        out = detector.prefer_handwritten(lines)
        texts = [x.get("text", "") for x in out]
        self.assertIn("my handwriting line", texts)
        self.assertIn("second line written", texts)
        self.assertNotIn("SCHOOL NAME", texts)

    def test_printed_form_lines_are_suppressed_in_mixed_content(self):
        lines = [
            {
                "text": "HOSPITAL DISCHARGE SUMMARY",
                "score": 0.997,
                "printed_hint": True,
                "box": [30, 20, 560, 26],
            },
            {
                "text": "Patient Name:",
                "score": 0.992,
                "printed_hint": True,
                "box": [32, 62, 180, 22],
            },
            {
                "text": "Age: 31 Sex: M",
                "score": 0.989,
                "printed_hint": True,
                "box": [240, 62, 220, 22],
            },
            {
                "text": "complaint of pain since 2 days",
                "score": 0.90,
                "printed_hint": False,
                "box": [35, 120, 480, 28],
            },
            {
                "text": "advised rest and followup",
                "score": 0.89,
                "printed_hint": False,
                "box": [35, 158, 360, 28],
            },
        ]
        out = detector.prefer_handwritten(lines)
        texts = [x.get("text", "") for x in out]
        self.assertIn("complaint of pain since 2 days", texts)
        self.assertIn("advised rest and followup", texts)
        self.assertNotIn("HOSPITAL DISCHARGE SUMMARY", texts)
        self.assertNotIn("Patient Name:", texts)

    def test_printed_keywords_excluded_even_with_low_confidence(self):
        lines = [
            {
                "text": "Patient Name:",
                "score": 0.73,
                "printed_hint": True,
                "box": [30, 22, 180, 22],
            },
            {
                "text": "Date:",
                "score": 0.70,
                "printed_hint": True,
                "box": [30, 52, 88, 22],
            },
            {
                "text": "pain started yesterday",
                "score": 0.81,
                "printed_hint": False,
                "box": [34, 110, 280, 30],
            },
            {
                "text": "taking tablets",
                "score": 0.79,
                "printed_hint": False,
                "box": [34, 150, 190, 30],
            },
        ]
        out = detector.prefer_handwritten(lines)
        texts = [x.get("text", "") for x in out]
        self.assertIn("pain started yesterday", texts)
        self.assertIn("taking tablets", texts)
        self.assertNotIn("Patient Name:", texts)
        self.assertNotIn("Date:", texts)

    def test_region_filter_drops_noise_headers_and_ids(self):
        lines = [
            {
                "text": "H",
                "score": 0.72,
                "printed_hint": False,
                "box": [12, 10, 8, 10],
            },
            {
                "text": "IP No: 7817",
                "score": 0.96,
                "printed_hint": True,
                "box": [420, 12, 180, 20],
            },
            {
                "text": "my pain started yesterday",
                "score": 0.86,
                "printed_hint": False,
                "box": [36, 126, 300, 28],
            },
            {
                "text": "taking tablets",
                "score": 0.83,
                "printed_hint": False,
                "box": [38, 162, 180, 28],
            },
        ]
        out = detector.region_filter_lines(lines, (500, 700, 3))
        texts = [x.get("text", "") for x in out]
        self.assertIn("my pain started yesterday", texts)
        self.assertIn("taking tablets", texts)
        self.assertNotIn("H", texts)
        self.assertNotIn("IP No: 7817", texts)


if __name__ == "__main__":
    unittest.main()
