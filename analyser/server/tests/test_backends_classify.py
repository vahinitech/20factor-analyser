# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
# Pure-Python tests for the pluggable OCR registry and the printed-vs-handwriting
# classifier. These DO NOT require paddle/torch/surya — only numpy,
# pillow and (optionally) opencv. Run:
#     python -m unittest -v analyser/server/tests/test_backends_classify.py
import os
import sys
import unittest
from unittest import mock

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
sys.path.insert(0, SERVER_DIR)

import ocr_backends  # noqa: E402
import classify  # noqa: E402
import gpu_detect  # noqa: E402
import scoring  # noqa: E402
import detector  # noqa: E402

# White-box tests deliberately reach into module-private helpers below.
# pylint: disable=protected-access


def _printed_strip(w=240, h=40):
    """A crisp, uniform-stroke 'printed' strip: evenly spaced black bars on white.
    Uniform stroke width + constant height → should read as printed."""
    img = np.full((h, w, 3), 255, np.uint8)
    x = 8
    while x < w - 8:
        img[8 : h - 8, x : x + 3] = 0  # constant 3px stroke, constant height
        x += 12
    return img


def _hand_strip(w=240, h=40):
    """A wobbly, variable-stroke, variable-height 'handwriting' strip."""
    rng = [3, 7, 2, 9, 4, 6, 2, 8, 5, 3, 7, 4]
    img = np.full((h, w, 3), 255, np.uint8)
    x = 8
    i = 0
    while x < w - 12:
        sw = rng[i % len(rng)]  # variable stroke width
        top = 6 + (i * 3) % 12  # variable top → variable height
        bot = h - 6 - (i * 2) % 10
        img[top:bot, x : x + sw] = 0
        x += sw + 6 + (i % 4)  # irregular spacing
        i += 1
    return img


class TestRegistry(unittest.TestCase):
    def test_registry_has_all_engines(self):
        ocr_backends.init_registry()
        for name in ("paddle", "trocr", "surya", "paddleocr-vl"):
            self.assertIsNotNone(
                ocr_backends.get_backend(name), f"missing backend {name}"
            )

    def test_engine_speed_memo_marks_slow_and_fast_from_real_measurements(
        self,
    ):
        # No measurement yet -> caller should measure and record.
        ocr_backends._SPEED_MEMO.clear()
        self.assertIsNone(ocr_backends.engine_speed_verdict("trocr"))

        # A fast measurement is remembered as fast.
        fast = ocr_backends.record_engine_speed("trocr", 400.0)
        self.assertTrue(fast)
        measured_ms, is_fast = ocr_backends.engine_speed_verdict("trocr")
        self.assertAlmostEqual(measured_ms, 400.0)
        self.assertTrue(is_fast)

        # A slow measurement on a different engine is remembered as slow.
        slow = ocr_backends.record_engine_speed("surya", 9000.0)
        self.assertFalse(slow)
        _measured_ms, is_fast = ocr_backends.engine_speed_verdict("surya")
        self.assertFalse(is_fast)

        snap = ocr_backends.engine_speed_snapshot()
        self.assertTrue(snap["trocr"]["fast_enough"])
        self.assertFalse(snap["surya"]["fast_enough"])
        ocr_backends._SPEED_MEMO.clear()

    def test_vl_results_classic_shape(self):
        results = [
            {
                "rec_texts": ["hi"],
                "rec_polys": [[[0, 0], [10, 0], [10, 6], [0, 6]]],
                "rec_scores": [0.9],
            }
        ]
        lines = ocr_backends._vl_results_to_lines(results, "en")
        self.assertEqual(lines[0]["text"], "hi")
        self.assertEqual(lines[0]["box"], [0.0, 0.0, 10.0, 6.0])

    def test_vl_results_layout_blocks(self):
        results = [
            {
                "parsing_res_list": [
                    {
                        "block_content": "hello world",
                        "block_bbox": [1, 2, 11, 8],
                    }
                ]
            }
        ]
        lines = ocr_backends._vl_results_to_lines(results, "en")
        self.assertEqual(lines[0]["text"], "hello world")
        self.assertEqual(lines[0]["box"], [1.0, 2.0, 10.0, 6.0])

    def test_vl_results_markdown_fallback(self):
        class _R:  # pylint: disable=too-few-public-methods
            markdown = {"markdown_texts": "<b>just text</b>"}

        lines = ocr_backends._vl_results_to_lines([_R()], "en")
        self.assertEqual(lines[0]["text"], "just text")

    def test_available_never_raises(self):
        ocr_backends.init_registry()
        probes = ocr_backends.available_backends()
        # Every probe must return a (bool, str) tuple, even with nothing installed.
        for _name, val in probes.items():
            self.assertEqual(len(val), 2)
            self.assertIsInstance(val[0], bool)
            self.assertIsInstance(val[1], str)

    def test_make_line_shape(self):
        ln = ocr_backends.make_line(
            "hi", [[1, 2], [10, 2], [10, 8], [1, 8]], 0.9, "en"
        )
        self.assertEqual(ln["box"], [1.0, 2.0, 9.0, 6.0])
        self.assertEqual(ln["text"], "hi")
        self.assertAlmostEqual(ln["score"], 0.9)

    def test_trocr_needs_detector(self):
        be = ocr_backends.TrOCRBackend()
        with self.assertRaises(RuntimeError):
            be.recognize(
                np.zeros((10, 10, 3), np.uint8), "en", ["en"], detect_fn=None
            )


class TestClassifier(unittest.TestCase):
    def test_printed_scores_higher_than_handwriting(self):
        printed = _printed_strip()
        hand = _hand_strip()
        p_prob, _ = classify.printed_probability(
            printed, "Patient Name:", 0.99, [0, 0, 240, 40]
        )
        h_prob, _ = classify.printed_probability(
            hand, "ramu kumar", 0.78, [0, 0, 240, 40]
        )
        self.assertGreater(
            p_prob,
            h_prob,
            f"printed {p_prob:.2f} should exceed handwriting {h_prob:.2f}",
        )

    def test_classify_lines_splits_mixed_page(self):
        arr = np.full((200, 260, 3), 255, np.uint8)
        arr[10:50, 10:250] = _printed_strip()
        arr[120:160, 10:250] = _hand_strip()
        lines = [
            {
                "text": "Patient Name:",
                "score": 0.99,
                "box": [10, 10, 240, 40],
                "poly": [],
            },
            {
                "text": "ramu kumar",
                "score": 0.74,
                "box": [10, 120, 240, 40],
                "poly": [],
            },
        ]
        hand, _printed = classify.split_lines(arr, lines)
        hand_texts = [l["text"] for l in hand]
        self.assertIn("ramu kumar", hand_texts)

    def test_high_confidence_printed_letterhead_excluded(self):
        # Regression for the Ahalya Hospital discharge summary: the printed
        # letterhead address read at very high OCR confidence and was leaking
        # into the handwriting set (poisoning every factor crop). A clean,
        # high-confidence, multi-char line must classify as printed even when a
        # phone photo blurs the structural stroke-width signal.
        blurry = np.full(
            (30, 360, 3), 235, np.uint8
        )  # near-uniform: weak structure
        lines = [
            {
                "text": "Kothapet, Behind Sivalayam, GUNTUR - 522 001.",
                "score": 0.991,
                "box": [10, 10, 340, 24],
                "poly": [],
            },
            {
                "text": "Procedure Done (if any) :",
                "score": 0.97,
                "box": [10, 50, 240, 24],
                "poly": [],
            },
            {
                "text": "Midiral manay ment",
                "score": 0.66,
                "box": [10, 90, 200, 28],
                "poly": [],
            },
        ]
        arr = np.full((140, 380, 3), 235, np.uint8)
        for ln in lines:
            x, y, w, h = ln["box"]
            arr[y : y + h, x : x + w] = blurry[:h, :w]
        hand, _printed = classify.split_lines(arr, lines)
        hand_texts = [l["text"] for l in hand]
        self.assertNotIn(
            "Kothapet, Behind Sivalayam, GUNTUR - 522 001.", hand_texts
        )
        self.assertNotIn("Procedure Done (if any) :", hand_texts)

    def test_letterhead_tagline_band_suppressed(self):
        # A stylised cursive tagline ("Life Begins in safe hands") sits in the
        # letterhead band and reads like handwriting (moderate confidence,
        # variable strokes). It must be suppressed via the content-relative top
        # band, while real handwriting lower on the page is kept.
        arr = np.full((600, 400, 3), 245, np.uint8)

        def mk_line(text, sc, y):
            return {
                "text": text,
                "score": sc,
                "box": [20, y, 300, 24],
                "poly": [],
            }

        lines = [
            mk_line("AHALYA HOSPITAL", 0.98, 10),
            mk_line('"Life Begins in safe hands"', 0.85, 36),
            mk_line("DISCHARGE SUMMARY", 0.98, 64),
            mk_line("Patient Name :", 0.95, 120),
            mk_line("medical management", 0.66, 480),
        ]
        hand, _printed = classify.split_lines(arr, lines)
        ht = [l["text"] for l in hand]
        self.assertNotIn('"Life Begins in safe hands"', ht)
        self.assertIn("medical management", ht)

    def test_reference_passage_alignment(self):
        # When a known passage is supplied, garbled OCR is corrected to the
        # target and a per-line match score is produced (consistent reading).
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "ppsrv_align", os.path.join(SERVER_DIR, "ppocr-server.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        hand = [
            {"text": "The Quiclc brown tox sumfs over"},  # garbled OCR
            {"text": "the 1a3y dog"},
        ]
        expected = "The quick brown fox jumps over\nthe lazy dog"
        info = mod.recognizer.align_to_expected(hand, expected)
        self.assertIsNotNone(info)
        self.assertEqual(info["aligned"], 2)
        self.assertEqual(
            hand[0]["text"], "The quick brown fox jumps over"
        )  # corrected
        self.assertGreater(hand[0]["match"], 0.45)

    def test_alignment_no_passage_is_noop(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "ppsrv_align2", os.path.join(SERVER_DIR, "ppocr-server.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        hand = [{"text": "anything"}]
        self.assertIsNone(mod.recognizer.align_to_expected(hand, ""))
        self.assertEqual(hand[0]["text"], "anything")

    def test_fail_open_keeps_all_when_everything_printed(self):
        # detector.prefer_handwritten has this fail-open contract; emulate it here.
        lines = [{"text": "X", "printed_hint": True} for _ in range(5)]
        hand = [l for l in lines if not l.get("printed_hint")]
        if len(hand) < max(1, int(0.15 * len(lines))):
            hand = lines
        self.assertEqual(len(hand), 5)


class TestGpuDetect(unittest.TestCase):
    def test_explicit_env_var_always_wins(self):
        with mock.patch.dict(os.environ, {"VAHINI_TEST_GPU": "1"}):
            self.assertTrue(gpu_detect.resolve_use_gpu("VAHINI_TEST_GPU"))
        with mock.patch.dict(os.environ, {"VAHINI_TEST_GPU": "0"}):
            self.assertFalse(gpu_detect.resolve_use_gpu("VAHINI_TEST_GPU"))

    def test_unset_falls_back_to_autodetect(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VAHINI_TEST_GPU_UNSET", None)
            with mock.patch.object(
                gpu_detect, "gpu_capable", return_value=True
            ):
                self.assertTrue(
                    gpu_detect.resolve_use_gpu("VAHINI_TEST_GPU_UNSET")
                )
            with mock.patch.object(
                gpu_detect, "gpu_capable", return_value=False
            ):
                self.assertFalse(
                    gpu_detect.resolve_use_gpu("VAHINI_TEST_GPU_UNSET")
                )

    def test_torch_cuda_available_true(self):
        fake_torch = mock.Mock()
        fake_torch.cuda.is_available.return_value = True
        with mock.patch.dict(sys.modules, {"torch": fake_torch}):
            self.assertTrue(gpu_detect._torch_cuda_available())

    def test_torch_cuda_available_false_when_torch_missing(self):
        with mock.patch.dict(sys.modules, {"torch": None}):
            self.assertFalse(gpu_detect._torch_cuda_available())

    def test_paddle_cuda_requires_compiled_and_a_device(self):
        fake_paddle = mock.Mock()
        fake_paddle.is_compiled_with_cuda.return_value = True
        fake_paddle.device.cuda.device_count.return_value = 1
        with mock.patch.dict(sys.modules, {"paddle": fake_paddle}):
            self.assertTrue(gpu_detect._paddle_cuda_available())

        fake_paddle_cpu_only = mock.Mock()
        fake_paddle_cpu_only.is_compiled_with_cuda.return_value = False
        with mock.patch.dict(sys.modules, {"paddle": fake_paddle_cpu_only}):
            self.assertFalse(gpu_detect._paddle_cuda_available())

    def test_gpu_capable_dispatches_by_engine(self):
        with mock.patch.object(
            gpu_detect, "_torch_cuda_available", return_value=True
        ), mock.patch.object(
            gpu_detect, "_paddle_cuda_available", return_value=False
        ):
            self.assertTrue(gpu_detect.gpu_capable("torch"))
            self.assertFalse(gpu_detect.gpu_capable("paddle"))
            self.assertTrue(gpu_detect.gpu_capable("any"))

    def test_nvidia_gpu_present_never_raises(self):
        # No nvidia-smi on this box (or any CI box) — must resolve to False,
        # not throw.
        self.assertFalse(gpu_detect.nvidia_gpu_present())


class TestScoringDataclasses(unittest.TestCase):
    """to_dict() is the one place a camelCase-mapping bug could hide, since
    the browser's report renderer expects these exact JSON keys."""

    def _factor(self, **overrides):
        kwargs = {
            "n": 1,
            "sec": "structure",
            "name": "Letter Formation Accuracy",
            "ex": "round",
            "target": "shape dist ≤10.10",
            "tip": "Practice.",
            "score": 7.5,
            "score100": 75,
            "band": "strong",
            "value": "75%",
            "evidence": "Server-side heuristic.",
        }
        kwargs.update(overrides)
        return scoring.FactorScore(**kwargs)

    def test_factor_score_to_dict_keys_and_casing(self):
        d = self._factor(based_on="12 letters").to_dict()
        self.assertEqual(
            set(d.keys()),
            {
                "n",
                "sec",
                "name",
                "ex",
                "target",
                "conf",
                "tip",
                "score",
                "score100",
                "band",
                "value",
                "evidence",
                "imuMeasured",
                "unmeasured",
                "unmeasuredReason",
                "unmeasuredKind",
                "basedOn",
            },
        )
        self.assertEqual(d["basedOn"], "12 letters")
        self.assertEqual(d["conf"], "measured")
        self.assertFalse(d["imuMeasured"])

    def test_section_score_to_dict_includes_scored_count(self):
        factors = [self._factor(n=1), self._factor(n=2, sec="structure")]
        section = scoring.SectionScore(
            id="structure",
            name="Structure",
            weight=0.3,
            blurb="Letter shapes, size & control",
            factors=factors,
            avg=7.0,
            avg100=70,
        )
        d = section.to_dict()
        self.assertEqual(
            set(d.keys()),
            {
                "id",
                "name",
                "weight",
                "blurb",
                "avg",
                "avg100",
                "factors",
                "scoredCount",
            },
        )
        self.assertEqual(d["scoredCount"], 2)
        self.assertEqual(len(d["factors"]), 2)
        self.assertEqual(d["factors"][0]["n"], 1)

    def test_analysis_result_to_dict_keys_and_casing(self):
        factor = self._factor()
        section = scoring.SectionScore(
            id="structure",
            name="Structure",
            weight=0.3,
            blurb="Letter shapes, size & control",
            factors=[factor],
            avg=7.5,
            avg100=75,
        )
        analysis = scoring.AnalysisResult(
            results=[factor],
            sections=[section],
            overall=75,
            overall_measured=75,
            measured_count=1,
            top_weak=[factor],
            top_strong=[factor],
        )
        d = analysis.to_dict()
        self.assertEqual(
            set(d.keys()),
            {
                "results",
                "sections",
                "overall",
                "overallMeasured",
                "measuredCount",
                "topWeak",
                "topStrong",
                "source",
            },
        )
        self.assertEqual(d["source"], "python")
        self.assertEqual(d["measuredCount"], 1)
        self.assertEqual(d["topWeak"][0]["n"], 1)

    def test_build_analysis_produces_twenty_factors(self):
        lines = [
            {
                "text": "hello world",
                "box": [10, 10 + (i * 20), 100, 18],
                "poly": [[10, 10 + (i * 20)], [110, 10 + (i * 20)]],
                "score": 0.9,
            }
            for i in range(4)
        ]
        arr = np.full((200, 300, 3), 255, np.uint8)
        analysis = scoring.build_analysis(arr, lines, {})
        self.assertIsInstance(analysis, scoring.AnalysisResult)
        self.assertEqual(len(analysis.results), 20)
        d = analysis.to_dict()
        self.assertEqual(len(d["results"]), 20)
        self.assertEqual(d["source"], "python")


class TestDetector(unittest.TestCase):
    def test_merge_lines_drops_overlapping_duplicate_text(self):
        lines = [
            {"text": "hello", "box": [10, 10, 50, 20], "score": 0.9},
            {"text": "hello", "box": [12, 11, 50, 20], "score": 0.95},
            {"text": "world", "box": [100, 10, 50, 20], "score": 0.8},
        ]
        out = detector.merge_lines(lines)
        self.assertEqual(len(out), 2)
        hello = next(l for l in out if l["text"] == "hello")
        self.assertEqual(hello["score"], 0.95)

    def test_region_filter_lines_drops_tiny_low_confidence_specks(self):
        lines = [
            {"text": "a", "box": [0, 0, 2, 2], "score": 0.1},
            {"text": "hello world", "box": [10, 10, 100, 20], "score": 0.9},
        ]
        out = detector.region_filter_lines(lines, (500, 500, 3))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["text"], "hello world")

    def test_prefer_handwritten_keeps_only_non_printed(self):
        lines = [
            {"text": "printed", "printed_hint": True},
            {"text": "written", "printed_hint": False},
        ]
        out = detector.prefer_handwritten(lines)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["text"], "written")

    def test_prefer_handwritten_fails_open_when_all_printed(self):
        lines = [{"text": "x", "printed_hint": True} for _ in range(5)]
        out = detector.prefer_handwritten(lines)
        self.assertEqual(len(out), 5)

    def test_is_noise_line_flags_single_char_and_punctuation(self):
        self.assertTrue(detector.is_noise_line({"text": "e"}))
        self.assertTrue(detector.is_noise_line({"text": "..."}))
        self.assertFalse(detector.is_noise_line({"text": "hi"}))

    def test_lines_quality_prefers_more_words_and_confidence(self):
        rich = [{"text": "a fine sentence here", "score": 0.95}]
        poor = [{"text": "12", "score": 0.3}]
        self.assertGreater(
            detector.lines_quality(rich), detector.lines_quality(poor)
        )

    def test_looks_printed_detects_dense_uppercase_header(self):
        self.assertTrue(
            detector.looks_printed(
                "PATIENT NAME ADDRESS DATE", 0.99, box=[0, 0, 300, 20]
            )
        )
        self.assertFalse(detector.looks_printed("hello there", 0.6))

    def test_variants_yields_base_first_and_respects_max(self):
        arr = np.full((60, 200, 3), 255, np.uint8)
        out = list(detector.variants(arr, max_variants=1, adv_preproc=False))
        self.assertEqual(len(out), 1)
        self.assertTrue(np.array_equal(out[0], arr))


if __name__ == "__main__":
    unittest.main()
