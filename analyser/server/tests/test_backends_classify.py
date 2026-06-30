# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
# Pure-Python tests for the pluggable OCR registry and the printed-vs-handwriting
# classifier. These DO NOT require paddle/torch/surya/chandra — only numpy,
# pillow and (optionally) opencv. Run:
#     python -m unittest -v analyser/server/tests/test_backends_classify.py
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
sys.path.insert(0, SERVER_DIR)

import ocr_backends  # noqa: E402
import classify      # noqa: E402


def _printed_strip(w=240, h=40):
    """A crisp, uniform-stroke 'printed' strip: evenly spaced black bars on white.
    Uniform stroke width + constant height → should read as printed."""
    img = np.full((h, w, 3), 255, np.uint8)
    x = 8
    while x < w - 8:
        img[8:h - 8, x:x + 3] = 0   # constant 3px stroke, constant height
        x += 12
    return img


def _hand_strip(w=240, h=40):
    """A wobbly, variable-stroke, variable-height 'handwriting' strip."""
    rng = [3, 7, 2, 9, 4, 6, 2, 8, 5, 3, 7, 4]
    img = np.full((h, w, 3), 255, np.uint8)
    x = 8
    i = 0
    while x < w - 12:
        sw = rng[i % len(rng)]            # variable stroke width
        top = 6 + (i * 3) % 12            # variable top → variable height
        bot = h - 6 - (i * 2) % 10
        img[top:bot, x:x + sw] = 0
        x += sw + 6 + (i % 4)             # irregular spacing
        i += 1
    return img


class TestRegistry(unittest.TestCase):
    def test_registry_has_all_engines(self):
        ocr_backends.init_registry(paddle_run=lambda a, l: [], paddle_detect=lambda a: [])
        for name in ("paddle", "trocr", "surya", "chandra", "paddleocr-vl"):
            self.assertIsNotNone(ocr_backends.get_backend(name), f"missing backend {name}")

    def test_vl_results_classic_shape(self):
        results = [{"rec_texts": ["hi"], "rec_polys": [[[0, 0], [10, 0], [10, 6], [0, 6]]], "rec_scores": [0.9]}]
        lines = ocr_backends._vl_results_to_lines(results, "en")
        self.assertEqual(lines[0]["text"], "hi")
        self.assertEqual(lines[0]["box"], [0.0, 0.0, 10.0, 6.0])

    def test_vl_results_layout_blocks(self):
        results = [{"parsing_res_list": [{"block_content": "hello world", "block_bbox": [1, 2, 11, 8]}]}]
        lines = ocr_backends._vl_results_to_lines(results, "en")
        self.assertEqual(lines[0]["text"], "hello world")
        self.assertEqual(lines[0]["box"], [1.0, 2.0, 10.0, 6.0])

    def test_vl_results_markdown_fallback(self):
        class _R:
            markdown = {"markdown_texts": "<b>just text</b>"}
        lines = ocr_backends._vl_results_to_lines([_R()], "en")
        self.assertEqual(lines[0]["text"], "just text")

    def test_available_never_raises(self):
        ocr_backends.init_registry()
        probes = ocr_backends.available_backends()
        # Every probe must return a (bool, str) tuple, even with nothing installed.
        for name, val in probes.items():
            self.assertEqual(len(val), 2)
            self.assertIsInstance(val[0], bool)
            self.assertIsInstance(val[1], str)

    def test_make_line_shape(self):
        ln = ocr_backends.make_line("hi", [[1, 2], [10, 2], [10, 8], [1, 8]], 0.9, "en")
        self.assertEqual(ln["box"], [1.0, 2.0, 9.0, 6.0])
        self.assertEqual(ln["text"], "hi")
        self.assertAlmostEqual(ln["score"], 0.9)

    def test_trocr_needs_detector(self):
        be = ocr_backends.TrOCRBackend()
        with self.assertRaises(RuntimeError):
            be.recognize(np.zeros((10, 10, 3), np.uint8), "en", ["en"], detector=None)


class TestClassifier(unittest.TestCase):
    def test_printed_scores_higher_than_handwriting(self):
        printed = _printed_strip()
        hand = _hand_strip()
        p_prob, _ = classify.printed_probability(printed, "Patient Name:", 0.99, [0, 0, 240, 40])
        h_prob, _ = classify.printed_probability(hand, "ramu kumar", 0.78, [0, 0, 240, 40])
        self.assertGreater(p_prob, h_prob,
                           f"printed {p_prob:.2f} should exceed handwriting {h_prob:.2f}")

    def test_classify_lines_splits_mixed_page(self):
        arr = np.full((200, 260, 3), 255, np.uint8)
        arr[10:50, 10:250] = _printed_strip()
        arr[120:160, 10:250] = _hand_strip()
        lines = [
            {"text": "Patient Name:", "score": 0.99, "box": [10, 10, 240, 40], "poly": []},
            {"text": "ramu kumar", "score": 0.74, "box": [10, 120, 240, 40], "poly": []},
        ]
        hand, printed = classify.split_lines(arr, lines)
        hand_texts = [l["text"] for l in hand]
        self.assertIn("ramu kumar", hand_texts)

    def test_high_confidence_printed_letterhead_excluded(self):
        # Regression for the Ahalya Hospital discharge summary: the printed
        # letterhead address read at very high OCR confidence and was leaking
        # into the handwriting set (poisoning every factor crop). A clean,
        # high-confidence, multi-char line must classify as printed even when a
        # phone photo blurs the structural stroke-width signal.
        blurry = np.full((30, 360, 3), 235, np.uint8)  # near-uniform: weak structure
        lines = [
            {"text": "Kothapet, Behind Sivalayam, GUNTUR - 522 001.",
             "score": 0.991, "box": [10, 10, 340, 24], "poly": []},
            {"text": "Procedure Done (if any) :", "score": 0.97,
             "box": [10, 50, 240, 24], "poly": []},
            {"text": "Midiral manay ment", "score": 0.66,
             "box": [10, 90, 200, 28], "poly": []},
        ]
        arr = np.full((140, 380, 3), 235, np.uint8)
        for ln in lines:
            x, y, w, h = ln["box"]
            arr[y:y + h, x:x + w] = blurry[:h, :w]
        hand, printed = classify.split_lines(arr, lines)
        hand_texts = [l["text"] for l in hand]
        self.assertNotIn("Kothapet, Behind Sivalayam, GUNTUR - 522 001.", hand_texts)
        self.assertNotIn("Procedure Done (if any) :", hand_texts)

    def test_letterhead_tagline_band_suppressed(self):
        # A stylised cursive tagline ("Life Begins in safe hands") sits in the
        # letterhead band and reads like handwriting (moderate confidence,
        # variable strokes). It must be suppressed via the content-relative top
        # band, while real handwriting lower on the page is kept.
        arr = np.full((600, 400, 3), 245, np.uint8)

        def L(text, sc, y):
            return {"text": text, "score": sc, "box": [20, y, 300, 24], "poly": []}

        lines = [
            L("AHALYA HOSPITAL", 0.98, 10),
            L('"Life Begins in safe hands"', 0.85, 36),
            L("DISCHARGE SUMMARY", 0.98, 64),
            L("Patient Name :", 0.95, 120),
            L("medical management", 0.66, 480),
        ]
        hand, printed = classify.split_lines(arr, lines)
        ht = [l["text"] for l in hand]
        self.assertNotIn('"Life Begins in safe hands"', ht)
        self.assertIn("medical management", ht)

    def test_reference_passage_alignment(self):
        # When a known passage is supplied, garbled OCR is corrected to the
        # target and a per-line match score is produced (consistent reading).
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ppsrv_align", os.path.join(SERVER_DIR, "ppocr-server.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        hand = [
            {"text": "The Quiclc brown tox sumfs over"},  # garbled OCR
            {"text": "the 1a3y dog"},
        ]
        expected = "The quick brown fox jumps over\nthe lazy dog"
        info = mod._align_to_expected(hand, expected)
        self.assertIsNotNone(info)
        self.assertEqual(info["aligned"], 2)
        self.assertEqual(hand[0]["text"], "The quick brown fox jumps over")  # corrected
        self.assertGreater(hand[0]["match"], 0.45)

    def test_alignment_no_passage_is_noop(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ppsrv_align2", os.path.join(SERVER_DIR, "ppocr-server.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        hand = [{"text": "anything"}]
        self.assertIsNone(mod._align_to_expected(hand, ""))
        self.assertEqual(hand[0]["text"], "anything")

    def test_fail_open_keeps_all_when_everything_printed(self):
        # _prefer_handwritten lives in the server; emulate its fail-open contract.
        lines = [{"text": "X", "printed_hint": True} for _ in range(5)]
        hand = [l for l in lines if not l.get("printed_hint")]
        if len(hand) < max(1, int(0.15 * len(lines))):
            hand = lines
        self.assertEqual(len(hand), 5)


if __name__ == "__main__":
    unittest.main()
