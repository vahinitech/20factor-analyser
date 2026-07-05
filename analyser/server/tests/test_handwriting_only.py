# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
# Regression suite for the analyser's rule of thumb: PRINTED TEXT IS NEVER
# ANALYSED. Only pen handwriting may reach the 20-factor measurements, the
# reference crops, the recognition showcase and the recognised text.
#
# The fixtures in tests/fixtures/samples/ are real pages of three kinds:
#   handwritten_letter_*   genuine pen handwriting        -> analysed
#   handwritten_printed_*  machine-printed pages          -> refused
#   *_mixed_*              printed form + pen entries     -> handwriting only
#
# PaddleOCR is not installed in CI, so recognizer.collect_lines is stubbed
# with the text/confidence/boxes such pages produce; everything downstream
# (the printed-vs-handwriting classifier on the REAL image crops, the strict
# handwriting filter, the endpoints' refusal paths, scoring and the factor
# regions) is the real production code.
import io
import os
import sys
import unittest
import importlib.util

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(os.path.dirname(SERVER_DIR))
SAMPLES_DIR = os.path.join(REPO_ROOT, "tests", "fixtures", "samples")
sys.path.insert(0, SERVER_DIR)

# White-box tests deliberately reach into module-private helpers below.
# pylint: disable=protected-access

SAMPLE_FILES = [
    "handwritten_letter_1.jpg",
    "handwritten_letter_2.jpg",
    "handwritten_script_1.jpg",
    "handwritten_printed_1.jpg",
    "handwritten_printed_2.jpg",
    "handwritten_printed_3.png",
    "handwritten_printed_mixed_1.jpg",
    "printed_signature_1.jpg",
]


def _load_server():
    path = os.path.join(SERVER_DIR, "ppocr-server.py")
    spec = importlib.util.spec_from_file_location(
        "ppocr_server_handwriting_only", path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rect(x, y, w, h):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _line(text, score, x, y, w, h):
    return {
        "text": text,
        "score": score,
        "box": [x, y, w, h],
        "poly": _rect(x, y, w, h),
        "lang": "en",
    }


def _png_bytes(arr):
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def _load_sample(name):
    return np.array(Image.open(os.path.join(SAMPLES_DIR, name)).convert("RGB"))


# What PP-OCRv5 reads on handwritten_printed_mixed_1.jpg (a 1929 receipt:
# printed form + pen entries), with boxes over the real image content so the
# structural classifier sees the actual pixels.
MIXED_PRINTED = [
    _line("No. 4309", 0.99, 420, 28, 105, 26),
    _line("COUNTY BOROUGH POLICE.", 0.99, 85, 62, 340, 32),
    _line("CHIEF CONSTABLE'S OFFICE", 0.98, 378, 112, 180, 18),
    _line("Received from Mrs", 0.97, 140, 182, 190, 22),
    _line("the Sum of", 0.97, 28, 222, 105, 20),
    _line("For Chief Constable.", 0.98, 388, 348, 125, 16),
]
MIXED_HAND = [
    _line("14th Oct 1929", 0.64, 325, 140, 185, 30),
    _line("use of motor ambulance", 0.58, 150, 250, 430, 32),
    _line("10/10/29", 0.55, 158, 282, 105, 26),
]

# What it reads on handwritten_printed_2.jpg: a fully machine-printed
# (typewritten) letter. Crisp uniform type reads at very high confidence.
PRINTED_ONLY = [
    _line("Bayerische Hammerwerke GmbH", 0.99, 28, 10, 200, 12),
    _line("Herrn Dr. Grunert", 0.98, 28, 22, 130, 12),
    _line("Geschwindigkeitstest mit vielen Laser- und", 0.99, 28, 88, 260, 12),
    _line("Sehr geehrter Herr Dr. Grunert,", 0.99, 28, 122, 200, 12),
    _line(
        "Sie konnen Laser-, Nadel- und Farb-Tintendrucker",
        0.99,
        28,
        140,
        280,
        12,
    ),
    _line("Mit freundlichem Gruss", 0.98, 28, 288, 160, 12),
]


class TestHandwritingOnlyRule(unittest.TestCase):
    """The credibility rule: printed characters never enter a report."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_server()
        from fastapi.testclient import TestClient

        cls.client = TestClient(cls.mod.app)
        # recognizer is a sys.modules singleton shared across test modules:
        # restore the real collect_lines when this class finishes.
        cls.addClassCleanup(
            setattr,
            cls.mod.recognizer,
            "collect_lines",
            cls.mod.recognizer.collect_lines,
        )

    def _stub_lines(self, lines):
        def fake_collect(_arr, _lang):
            # deep-ish copy: the pipeline mutates lines in place
            return [dict(l) for l in lines], "", "paddle", {}

        self.mod.recognizer.collect_lines = fake_collect

    def _post(self, url, png, expected_text=""):
        data = {"lang": "auto"}
        if expected_text:
            data["expected_text"] = expected_text
        return self.client.post(
            url,
            files={"image": ("page.png", png, "image/png")},
            data=data,
        )

    # ---- fixtures stay in the repository -------------------------------
    def test_sample_fixtures_present_and_decodable(self):
        for name in SAMPLE_FILES:
            path = os.path.join(SAMPLES_DIR, name)
            self.assertTrue(os.path.isfile(path), f"missing fixture {name}")
            arr = _load_sample(name)
            self.assertGreater(arr.shape[0], 50, name)
            self.assertGreater(arr.shape[1], 50, name)

    # ---- the strict filter itself ---------------------------------------
    def test_prefer_handwritten_has_no_fail_open(self):
        # 9 printed lines + 1 handwritten: the old fail-open returned all 10
        # ("handwriting scarce, keep everything"), which is exactly how
        # printed forms polluted reports. Now only the handwriting survives.
        lines = [
            {"printed_hint": True, "text": f"label {i}"} for i in range(9)
        ]
        lines.append({"printed_hint": False, "text": "ramu kumar"})
        import detector

        kept = detector.prefer_handwritten(lines)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["text"], "ramu kumar")

    # ---- mixed page: only the pen entries are analysed ------------------
    def test_mixed_page_report_excludes_all_printed_text(self):
        arr = _load_sample("handwritten_printed_mixed_1.jpg")
        self._stub_lines(MIXED_PRINTED + MIXED_HAND)
        r = self._post("/report-python", _png_bytes(arr))
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertTrue(j.get("ok"), j.get("error"))

        joined = " ".join(j.get("rec_texts", [])).lower()
        for printed in MIXED_PRINTED:
            self.assertNotIn(
                printed["text"].lower(),
                joined,
                f"printed text leaked into the report: {printed['text']!r}",
            )
        # the pen entries are what remains
        self.assertTrue(any("ambulance" in t.lower() for t in j["rec_texts"]))

        # printed lines are counted and disclosed, not scored
        rec = (j.get("analysis") or {}).get("recognition") or {}
        self.assertGreaterEqual(int(rec.get("printed_lines", 0)), 4)
        # and the full 20-factor analysis still ran on the handwriting
        self.assertEqual(len((j.get("analysis") or {}).get("results", [])), 20)
        self.assertEqual(len(j.get("factor_regions", {})), 20)

    def test_mixed_page_hand_lines_and_regions_are_handwriting_only(self):
        arr = _load_sample("handwritten_printed_mixed_1.jpg")
        self._stub_lines(MIXED_PRINTED + MIXED_HAND)
        j = self._post("/report-python", _png_bytes(arr)).json()
        printed_texts = {p["text"].lower() for p in MIXED_PRINTED}
        # hand_lines feeds the orange detection boxes in the app
        for l in j.get("hand_lines", []):
            self.assertNotIn(str(l.get("text", "")).lower(), printed_texts)
            self.assertFalse(bool(l.get("printed_hint")))
        # regions feed the report's evidence showcase
        for reg in j.get("regions", []):
            self.assertNotIn(str(reg.get("text", "")).lower(), printed_texts)

    # ---- fully printed page: refuse, do not fabricate a score -----------
    def test_fully_printed_page_is_refused_with_clear_reason(self):
        arr = _load_sample("handwritten_printed_2.jpg")
        self._stub_lines(PRINTED_ONLY)
        for url in ("/report-python", "/analyze-vl", "/ocr"):
            j = self._post(url, _png_bytes(arr)).json()
            self.assertEqual(
                j.get("error_code"),
                "no_handwriting",
                f"{url} did not refuse the printed page: {j.get('engine')}",
            )
            self.assertEqual(j.get("rec_texts"), [])
            self.assertIn("printed", j.get("error", "").lower())
            # adjacent typewritten rows merge, so the count is of MERGED
            # lines; the contract is refusal + disclosure, not the exact N
            self.assertGreaterEqual(int(j.get("printed_lines", 0)), 1)
            self.assertIsNone(j.get("analysis"))

    # ---- OCR down is NOT the same as printed-only -----------------------
    def test_ocr_failure_still_scores_geometry_via_cv_fallback(self):
        # A genuine handwritten letter with no OCR available must still be
        # scored from geometry (cv-fallback), never refused as "printed".
        arr = _load_sample("handwritten_letter_1.jpg")

        def fake_collect(_arr, _lang):
            return [], "engine init failed", "paddle", {}

        self.mod.recognizer.collect_lines = fake_collect
        j = self._post("/report-python", _png_bytes(arr)).json()
        self.assertTrue(j.get("ok"), j.get("error"))
        self.assertEqual(j.get("selected_backend"), "cv-fallback")
        self.assertEqual(len((j.get("analysis") or {}).get("results", [])), 20)
        rec = (j.get("analysis") or {}).get("recognition") or {}
        self.assertEqual(rec.get("level"), "unavailable")


if __name__ == "__main__":
    unittest.main()
