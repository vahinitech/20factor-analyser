# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies. Pluggable OCR backends for the Vahini analyser.
# Third-party engines: PaddleOCR (Apache-2.0), TrOCR/transformers (MIT/Apache-2.0),
# Surya (datalab, GPL/commercial — see their licence).
# See /THIRD-PARTY-NOTICES.md and backend/README.md.
#
# ocr_backends.py — one adapter per recognition engine behind a common interface.
#
# Why this file exists
# --------------------
# The analyser must "shift easily" between recognition engines. Every engine here
# produces the SAME line shape so the rest of the server (merge / classify /
# factor-region / scoring) never changes when you switch engines:
#
#     line = {
#       "text":  str,                 # recognised text for the region
#       "poly":  [[x,y], ...],        # detection polygon in image pixels
#       "box":   [x, y, w, h],        # axis-aligned bbox derived from poly
#       "score": float,               # 0..1 recognition confidence
#       "lang":  str,                 # language tag for the line
#     }
#
# `printed_hint` is intentionally NOT set here — printed-vs-handwriting
# classification is centralised in the server (see classify.py) so it is
# consistent across every engine.
#
# Design rules
# ------------
# 1. Heavy deps (paddlepaddle / torch / transformers / surya) are imported
#    LAZILY inside each adapter's methods. Importing this module costs
#    nothing and never fails just because an engine is not installed.
# 2. `available()` returns (ok, reason) so the server / /health can report which
#    engines are actually runnable on this machine without crashing.
# 3. Switch engine with the env var VAHINI_OCR_BACKEND = paddle|trocr|surya|
#    hybrid|auto (default paddle). `auto` runs the installed candidates and
#    keeps the highest-quality result; `hybrid` always detects+classifies with
#    paddle and re-reads handwriting with trocr (English) or surya (Indic
#    scripts) — see recognizer.refine_handwriting_text.

import os
import re
import html
import time
import threading
import importlib.util
from functools import lru_cache

import numpy as np
from PIL import Image

import detector
from geometry import clamp_box
from gpu_detect import resolve_use_gpu, gpu_capable

_TELUGU = re.compile(r"[ఀ-౿]")


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def poly_to_box(pts):
    """[[x,y]...] -> [x, y, w, h] axis-aligned bbox."""
    if not pts:
        return [0.0, 0.0, 0.0, 0.0]
    xs = [float(p[0]) for p in pts]
    ys = [float(p[1]) for p in pts]
    return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]


def make_line(text, pts, score, lang):
    """Build the canonical line dict every backend returns."""
    pts = [[float(x), float(y)] for x, y in (pts or [])]
    box = poly_to_box(pts)
    t = text or ""
    return {
        "text": t,
        "poly": pts,
        "box": box,
        "score": float(score or 0.0),
        "lang": "te" if _TELUGU.search(t) else (lang or "en"),
    }


def _env(name, default=""):
    return (os.environ.get(name, default) or "").strip()


# --------------------------------------------------------------------------- #
# Base interface
# --------------------------------------------------------------------------- #
class OCRBackend:
    name = "base"

    def available(self):
        """Return (ok: bool, reason: str). Cheap; never raises."""
        return False, "not implemented"

    def recognize(self, arr, lang, langs, detect_fn=None):
        """Return list[line]. `arr` is an RGB uint8 numpy array.

        `detect_fn` is an optional callable arr -> list[poly] that a
        recogniser-only engine (TrOCR) can use to localise text. Engines
        with their own detector ignore it.
        """
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# PaddleOCR (PP-OCRv5) — detection + recognition, classic CPU-friendly OCR.
#
# Paddle owns its own engine cache, per-engine lock and inference call here
# (configure_paddle() sets the engine build options once at startup; only
# the language-availability list is injected into PaddleBackend, since the
# server owns VAHINI_OCR_LANGS).
# --------------------------------------------------------------------------- #
_PADDLE_CFG = {
    "use_gpu": False,
    "ocr_version": None,
    "det_model_name": None,
    "rec_model_map": {},
    "text_det_limit_side_len": 0,
    "text_rec_score_thresh": 0.0,
    "use_doc_orientation": False,
    "use_doc_unwarping": False,
    "use_textline_orientation": False,
    "max_variants": 2,
    "adv_preproc": True,
}

_ENGINE_LOCKS_GUARD = threading.Lock()
_ENGINE_LOCKS = {}


def configure_paddle(**kwargs):
    """Set the paddle engine build options once at startup. Unknown keys are
    ignored so callers can pass a superset of _PADDLE_CFG."""
    for k, v in kwargs.items():
        if k in _PADDLE_CFG:
            _PADDLE_CFG[k] = v


def _lock_for_engine(engine):
    # Multiple analyses can land at the same time (several browser tabs,
    # several users). Engine objects are cached and reused across requests,
    # but a single PaddleOCR instance is not guaranteed safe to run
    # concurrently from more than one thread. Rather than serialize the
    # whole server, only calls that share the SAME engine object take
    # turns; a different language (a different engine instance) still runs
    # at the same time.
    key = id(engine)
    with _ENGINE_LOCKS_GUARD:
        lock = _ENGINE_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _ENGINE_LOCKS[key] = lock
        return lock


def _rec_model_for_paddle_lang(lang):
    lg = (lang or "").strip().lower()
    rec_map = _PADDLE_CFG["rec_model_map"]
    if lg in rec_map:
        return rec_map[lg]
    return rec_map.get("*", None)


def _paddle_engine_kwargs(lang, safe=False):
    kwargs = {
        "lang": lang,
        "use_doc_orientation_classify": (
            False if safe else _PADDLE_CFG["use_doc_orientation"]
        ),
        "use_doc_unwarping": (
            False if safe else _PADDLE_CFG["use_doc_unwarping"]
        ),
        "use_textline_orientation": (
            False if safe else _PADDLE_CFG["use_textline_orientation"]
        ),
        "device": (
            "cpu" if safe else ("gpu" if _PADDLE_CFG["use_gpu"] else "cpu")
        ),
    }
    if _PADDLE_CFG["ocr_version"]:
        kwargs["ocr_version"] = _PADDLE_CFG["ocr_version"]
    if _PADDLE_CFG["det_model_name"]:
        kwargs["text_detection_model_name"] = _PADDLE_CFG["det_model_name"]
    rec_name = _rec_model_for_paddle_lang(lang)
    if rec_name:
        kwargs["text_recognition_model_name"] = rec_name
    if _PADDLE_CFG["text_det_limit_side_len"] > 0:
        kwargs["text_det_limit_side_len"] = _PADDLE_CFG[
            "text_det_limit_side_len"
        ]
    kwargs["text_rec_score_thresh"] = _PADDLE_CFG["text_rec_score_thresh"]
    return kwargs


# Engine construction can be very slow to FAIL (first use triggers a model
# download that walks several hosters with long timeouts before giving up on
# an offline/blocked network). Remember recent failures so every scan after
# the first fails over to the CV fallback in milliseconds, and retry after a
# cooldown in case the network recovered.
_ENGINE_FAIL_TTL = max(
    30.0, float(os.environ.get("VAHINI_OCR_ENGINE_RETRY_SEC", "300") or "300")
)
_ENGINE_FAIL_CACHE = {}  # (kind, lang) -> (monotonic_ts, error_str)


def _engine_fail_cached(key):
    hit = _ENGINE_FAIL_CACHE.get(key)
    if not hit:
        return None
    ts, err = hit
    if (time.monotonic() - ts) < _ENGINE_FAIL_TTL:
        return err
    _ENGINE_FAIL_CACHE.pop(key, None)
    return None


# --------------------------------------------------------------------------- #
# Adaptive engine speed (hybrid mode) — decide whether THIS machine's CPU can
# afford a specialist's per-line cost from a REAL measured latency, not a
# synthetic benchmark or a manual "is this machine fast?" env var. Every
# refine call times itself and records the result here; once an engine is
# measured too slow, recognizer.refine_handwriting_text skips calling it for
# the rest of the page (and for VAHINI_HYBRID_RETRY_SEC afterwards) and keeps
# paddle's own reading instead — the same fail-fast-then-retry-later shape as
# _ENGINE_FAIL_CACHE above, so hybrid mode is safe to enable on any machine:
# fast hardware gets the accuracy win, slow hardware quietly behaves like
# plain paddle after one measurement instead of stalling every scan.
# --------------------------------------------------------------------------- #
_SPEED_TTL = max(30.0, float(_env("VAHINI_HYBRID_RETRY_SEC", "600") or "600"))
_MAX_MS_PER_LINE = max(
    200.0, float(_env("VAHINI_HYBRID_MAX_MS_PER_LINE", "2500") or "2500")
)
_SPEED_MEMO = {}  # engine name -> (monotonic_ts, measured_ms, fast_enough)


def engine_speed_verdict(name):
    """(measured_ms, fast_enough) for `name` from the last measurement within
    VAHINI_HYBRID_RETRY_SEC, or None if never measured (or expired) — the
    caller should measure this call and record it."""
    hit = _SPEED_MEMO.get(name)
    if not hit:
        return None
    ts, measured_ms, fast = hit
    if (time.monotonic() - ts) < _SPEED_TTL:
        return measured_ms, fast
    _SPEED_MEMO.pop(name, None)
    return None


def record_engine_speed(name, elapsed_ms):
    """Record one real recognize_crop() latency for `name` and return
    whether it was fast enough (elapsed_ms <= VAHINI_HYBRID_MAX_MS_PER_LINE).
    """
    fast = elapsed_ms <= _MAX_MS_PER_LINE
    _SPEED_MEMO[name] = (time.monotonic(), elapsed_ms, fast)
    return fast


def engine_speed_snapshot():
    """{name: {measured_ms, fast_enough, age_sec}} — used by /health so a
    slow-CPU fallback is visible and debuggable, not a silent guess."""
    now = time.monotonic()
    return {
        name: {
            "measured_ms": round(ms, 1),
            "fast_enough": fast,
            "age_sec": round(now - ts, 1),
        }
        for name, (ts, ms, fast) in _SPEED_MEMO.items()
    }


@lru_cache(maxsize=8)
def _build_engine_cached(lang: str):
    """One PaddleOCR instance per language, built lazily and cached.
    PP-OCRv5 is the default model family in PaddleOCR 3.x."""
    from paddleocr import PaddleOCR

    try:
        return PaddleOCR(**_paddle_engine_kwargs(lang, safe=False))
    except TypeError:
        # PaddleOCR 2.x compatibility path.
        return PaddleOCR(
            lang=lang,
            use_angle_cls=True,
            use_gpu=_PADDLE_CFG["use_gpu"],
            show_log=False,
        )


@lru_cache(maxsize=8)
def _build_engine_safe_cached(lang: str):
    """Fallback engine with minimal pre/post modules for max compatibility."""
    from paddleocr import PaddleOCR

    try:
        return PaddleOCR(**_paddle_engine_kwargs(lang, safe=True))
    except TypeError:
        return PaddleOCR(
            lang=lang,
            use_angle_cls=True,
            use_gpu=False,
            show_log=False,
        )


def get_engine(lang: str):
    """Cached engine builder with a failure memo (see _ENGINE_FAIL_TTL)."""
    cached_err = _engine_fail_cached(("normal", lang))
    if cached_err:
        raise RuntimeError(cached_err)
    try:
        return _build_engine_cached(lang)
    except Exception as e:
        _ENGINE_FAIL_CACHE[("normal", lang)] = (time.monotonic(), str(e))
        raise


def get_engine_safe(lang: str):
    """Cached safe-engine builder with the same failure memo."""
    cached_err = _engine_fail_cached(("safe", lang))
    if cached_err:
        raise RuntimeError(cached_err)
    try:
        return _build_engine_safe_cached(lang)
    except Exception as e:
        _ENGINE_FAIL_CACHE[("safe", lang)] = (time.monotonic(), str(e))
        raise


def run(engine, arr: np.ndarray, lang: str):
    """Return list[line] across PaddleOCR API variants."""
    # Prefer the classic ocr() entrypoint on CPU builds to avoid PIR/oneDNN
    # runtime incompatibilities seen on some Paddle 3.x combinations.
    # Concurrent requests can share this exact engine object (see
    # _lock_for_engine); only the model call itself needs to be serialized.
    with _lock_for_engine(engine):
        try:
            results = engine.ocr(arr)
        except Exception:
            # Fallback to predict() for builds that only expose it.
            results = engine.predict(arr)

    lines = []
    for res in results or []:
        # 3.x result objects behave like dicts with these keys
        d = res if isinstance(res, dict) else getattr(res, "json", None) or {}
        if isinstance(res, dict) or "rec_texts" in d:
            rt = (
                res.get("rec_texts")
                if isinstance(res, dict)
                else d.get("rec_texts")
            )
            rp = (
                res.get("rec_polys")
                if isinstance(res, dict)
                else d.get("rec_polys")
            )
            if rp is None:
                rp = (
                    res.get("rec_boxes")
                    if isinstance(res, dict)
                    else d.get("rec_boxes")
                )
            rs = (
                res.get("rec_scores")
                if isinstance(res, dict)
                else d.get("rec_scores")
            )
            rt = list(rt) if rt is not None else []
            rp = list(rp) if rp is not None else []
            rs = list(rs) if rs is not None else []
            for i, t in enumerate(rt):
                poly = rp[i] if i < len(rp) else []
                pts = [
                    [float(x), float(y)]
                    for x, y in (poly if poly is not None else [])
                ]
                if pts:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    box = [
                        min(xs),
                        min(ys),
                        max(xs) - min(xs),
                        max(ys) - min(ys),
                    ]
                else:
                    box = [0.0, 0.0, 0.0, 0.0]
                score = float(rs[i]) if i < len(rs) else 0.0
                lines.append(
                    {
                        "text": t,
                        "poly": pts,
                        "box": box,
                        "score": score,
                        "lang": "te" if _TELUGU.search(t or "") else lang,
                        "printed_hint": detector.looks_printed(t, score, box),
                    }
                )
        else:
            # --- classic API: [[poly, (text, score)], ...] ---
            if not isinstance(res, (list, tuple)):
                continue
            for item in res:
                poly, (txt, sc) = item[0], item[1]
                pts = [[float(x), float(y)] for x, y in poly]
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                box = (
                    [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
                    if pts
                    else [0.0, 0.0, 0.0, 0.0]
                )
                score = float(sc)
                lines.append(
                    {
                        "text": txt,
                        "poly": pts,
                        "box": box,
                        "score": score,
                        "lang": "te" if _TELUGU.search(txt or "") else lang,
                        "printed_hint": detector.looks_printed(
                            txt, score, box
                        ),
                    }
                )
    return lines


def _paddle_run_lang(arr: np.ndarray, lg: str):
    """Single-language paddle recogniser over all preprocessing variants.
    Engine construction happens lazily on first use (it can trigger a model
    download) and must not raise out of here — a failed build of the normal
    engine still leaves the safe engine usable, and vice versa."""
    try:
        engine = get_engine(lg)
    except Exception:
        engine = None
    try:
        engine_safe = get_engine_safe(lg)
    except Exception:
        engine_safe = None
    out = []
    if engine is None and engine_safe is None:
        return out
    for variant in detector.variants(
        arr, _PADDLE_CFG["max_variants"], _PADDLE_CFG["adv_preproc"]
    ):
        got = False
        if engine is not None:
            try:
                out.extend(run(engine, variant, lg))
                got = True
            except Exception:
                pass
        if not got and engine_safe is not None:
            try:
                out.extend(run(engine_safe, variant, lg))
            except Exception:
                pass
    return out


class PaddleBackend(OCRBackend):
    """PaddleOCR (PP-OCRv5): engine cache, per-engine lock, preprocessing
    variants and the actual inference call all live at module level above
    (get_engine/get_engine_safe/run/_paddle_run_lang), configured once via
    configure_paddle(). Only `resolve_langs` is injected, since the server
    owns the language-availability list (VAHINI_OCR_LANGS).
    """

    name = "paddle"

    def __init__(self, resolve_langs=None):
        self._resolve_langs = resolve_langs

    def available(self):
        if importlib.util.find_spec("paddleocr") is None:
            return False, "paddleocr not installed"
        return True, ""

    def detect(self, arr):
        """Detection boxes (polys) from paddle, used by recogniser-only
        engines such as TrOCR. Paddle detects + recognises in one pass; we
        keep the polys."""
        langs = self._resolve_langs("auto") if self._resolve_langs else ["en"]
        primary = (langs[:1] or ["en"])[0]
        try:
            lines = _paddle_run_lang(arr, primary)
        except Exception:
            return []
        return [l.get("poly") for l in lines if l.get("poly")]

    def recognize(self, arr, lang, langs, detect_fn=None):
        use_langs = langs or (
            self._resolve_langs(lang)
            if self._resolve_langs
            else [lang or "en"]
        )
        out = []
        for lg in use_langs:
            try:
                out.extend(_paddle_run_lang(arr, lg))
            except Exception:
                continue
        return out


# --------------------------------------------------------------------------- #
# TrOCR (Microsoft) — transformer recogniser, strong on English handwriting.
# Recogniser only: needs a detector to localise lines (we reuse paddle's).
# Pure `transformers` + `torch` on CPU; no extra binary required.
# --------------------------------------------------------------------------- #
class TrOCRBackend(OCRBackend):
    name = "trocr"

    def __init__(self):
        self._model = None
        self._processor = None
        # Guards the actual model call: this backend is a registry singleton,
        # so concurrent analyses would otherwise call the same cached model
        # from multiple threads at once.
        self._lock = threading.Lock()
        # VAHINI_TROCR_GPU=1/0 overrides; left unset, use the GPU if this
        # machine's installed torch build can actually reach one.
        self._device = "cuda" if resolve_use_gpu("VAHINI_TROCR_GPU") else "cpu"
        self.model_name = _env(
            "VAHINI_TROCR_MODEL", "microsoft/trocr-base-handwritten"
        )
        # Cap the number of crops we feed per page so a busy page can't stall the
        # CPU for minutes. Detection order is preserved (top-to-bottom).
        self.max_crops = max(
            1, int(_env("VAHINI_TROCR_MAX_CROPS", "60") or "60")
        )
        self.min_side = max(4, int(_env("VAHINI_TROCR_MIN_SIDE", "8") or "8"))

    def available(self):
        missing = [
            name
            for name in ("torch", "transformers")
            if importlib.util.find_spec(name) is None
        ]
        if missing:
            return (
                False,
                "trocr deps missing (pip install torch transformers): "
                f"no {', '.join(missing)}",
            )
        return True, f"trocr ready (device: {self._device})"

    def _ensure_model(self):
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:  # a concurrent call may have loaded it
                return
            import torch
            from transformers import (
                TrOCRProcessor,
                VisionEncoderDecoderModel,
            )

            processor = TrOCRProcessor.from_pretrained(self.model_name)
            model = VisionEncoderDecoderModel.from_pretrained(self.model_name)
            model.to(self._device)
            model.eval()
            torch.set_grad_enabled(False)
            # Assign last, and only once fully prepared: another thread's
            # fast-path check (self._model is not None) must never see a
            # model that hasn't had .to()/.eval() applied yet.
            self._processor = processor
            self._model = model

    def recognize(self, arr, lang, langs, detect_fn=None):
        if detect_fn is None:
            raise RuntimeError(
                "TrOCR is a recogniser-only engine and needs a detector. "
                "Run it with VAHINI_OCR_BACKEND=trocr while paddle is installed "
                "(paddle supplies the text-line boxes)."
            )
        polys = detect_fn(arr) or []
        if not polys:
            return []
        self._ensure_model()

        page = Image.fromarray(arr.astype(np.uint8), mode="RGB")
        height, width = arr.shape[:2]
        # Recognise top-to-bottom, then left-to-right (reading order).
        ordered = sorted(
            polys, key=lambda p: (poly_to_box(p)[1], poly_to_box(p)[0])
        )
        out = []
        for poly in ordered[: self.max_crops]:
            x, y, w, h = poly_to_box(poly)
            if w < self.min_side or h < self.min_side:
                continue
            box_px = clamp_box(x, y, w, h, width, height)
            if box_px is None:
                continue
            crop = page.crop(box_px)
            try:
                text, score = self._read_crop(crop)
            except Exception:
                continue
            if text:
                out.append(make_line(text, poly, score, lang))
        return out

    def recognize_crop(self, crop_rgb):
        """Recognise a single pre-cropped line image → (text, confidence).
        Used by the refinement path (paddle detects + classifies
        handwriting; TrOCR re-reads each handwriting crop for better text).
        The confidence is TrOCR's own mean per-token softmax probability, so
        the caller can trust a confident reading even when it disagrees with
        paddle's (paddle is not a handwriting specialist)."""
        self._ensure_model()
        return self._read_crop(
            Image.fromarray(crop_rgb.astype(np.uint8), mode="RGB")
        )

    def _read_crop(self, pil_img):
        import torch

        with self._lock:
            pixel_values = self._processor(
                images=pil_img.convert("RGB"), return_tensors="pt"
            ).pixel_values
            gen = self._model.generate(
                pixel_values.to(self._device),
                output_scores=True,
                return_dict_in_generate=True,
                max_new_tokens=64,
            )
            text = self._processor.batch_decode(
                gen.sequences, skip_special_tokens=True
            )[0].strip()
        # Approximate a confidence from the mean per-token softmax probability.
        score = 0.0
        try:
            if getattr(gen, "scores", None):
                probs = [
                    torch.softmax(s[0], dim=-1).max().item()
                    for s in gen.scores
                ]
                score = float(sum(probs) / max(1, len(probs)))
        except Exception:
            score = 0.0
        return text, (score if score > 0 else 0.80)


# --------------------------------------------------------------------------- #
# Surya 2 (datalab) — multilingual VLM OCR incl. Indic + handwriting.
# Detection runs in pytorch; recognition needs an inference backend
# (llama.cpp `llama-server` on CPU, or vllm on GPU). We call the documented
# high-level API and fail gracefully with a clear reason if the backend is down.
# --------------------------------------------------------------------------- #
class SuryaBackend(OCRBackend):
    name = "surya"

    def __init__(self):
        self._det = None
        self._rec = None
        self._manager = None
        # Guards both building the models (below) and the actual predict
        # calls: this backend is a registry singleton shared by every
        # concurrent analysis.
        self._lock = threading.Lock()

    def available(self):
        if importlib.util.find_spec("surya") is None:
            return False, "surya not installed (pip install surya-ocr)"
        device = "gpu" if gpu_capable("torch") else "CPU (slow)"
        return True, f"surya ready (device: {device})"

    def _ensure(self):
        if self._rec is not None:
            return
        with self._lock:
            if self._rec is not None:  # a concurrent call may have built it
                return
            # Surya (built on pydantic-settings) reads its device from the
            # TORCH_DEVICE env var. Set a default only if the operator hasn't
            # already chosen one, so VAHINI_SURYA_GPU=1/0 always wins and
            # unset auto-detects this machine's installed torch build.
            if "TORCH_DEVICE" not in os.environ:
                use_gpu = resolve_use_gpu("VAHINI_SURYA_GPU")
                os.environ["TORCH_DEVICE"] = "cuda" if use_gpu else "cpu"
            # Surya's module layout has shifted across releases; try the
            # current high-level API first, then a couple of known fallbacks.
            from surya.detection import DetectionPredictor
            from surya.recognition import RecognitionPredictor

            det = DetectionPredictor()
            try:
                from surya.inference import SuryaInferenceManager

                manager = SuryaInferenceManager()
                rec = RecognitionPredictor(manager)
            except Exception:
                # Older API: RecognitionPredictor() takes no manager.
                manager = None
                rec = RecognitionPredictor()
            # Assign last: another thread's fast-path check must never see
            # a partially-built predictor pair.
            self._det = det
            self._manager = manager
            self._rec = rec

    def recognize_crop(self, crop_rgb):
        """Recognise a single pre-cropped line image → (text, confidence)
        (refinement path). The confidence is Surya's own per-line score, so
        the caller can trust a confident Indic-script reading even when it
        disagrees with paddle (paddle is not a handwriting specialist)."""
        self._ensure()
        img = Image.fromarray(crop_rgb.astype(np.uint8), mode="RGB")
        with self._lock:
            try:
                preds = self._rec([img], det_predictor=self._det)
            except TypeError:
                preds = self._rec([img], [["en"]], self._det)
        if not preds:
            return "", 0.0
        lines = getattr(preds[0], "text_lines", None) or []
        text = " ".join(
            (getattr(ln, "text", "") or "").strip() for ln in lines
        ).strip()
        if not lines:
            return text, 0.0
        conf = sum(
            float(getattr(ln, "confidence", 0.0) or 0.0) for ln in lines
        ) / len(lines)
        return text, conf

    def recognize(self, arr, lang, langs, detect_fn=None):
        self._ensure()
        page = Image.fromarray(arr.astype(np.uint8), mode="RGB")
        with self._lock:
            try:
                preds = self._rec([page], det_predictor=self._det)
            except TypeError:
                # Older API variants expect (images, langs, det_predictor).
                preds = self._rec([page], [langs or [lang or "en"]], self._det)
        if not preds:
            return []
        result = preds[0]
        out = []
        # Result exposes text lines with bbox/polygon + confidence across versions
        # under `text_lines`; each line has `text`, `bbox` and/or `polygon`,
        # `confidence`.
        lines = getattr(result, "text_lines", None) or []
        for ln in lines:
            text = (getattr(ln, "text", "") or "").strip()
            if not text:
                continue
            poly = getattr(ln, "polygon", None)
            if not poly:
                bbox = getattr(ln, "bbox", None) or [0, 0, 1, 1]
                x0, y0, x1, y1 = [float(v) for v in bbox[:4]]
                poly = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
            score = float(getattr(ln, "confidence", 0.0) or 0.0) or 0.85
            out.append(make_line(text, poly, score, lang))
        return out


def _html_to_text(s):
    plain = re.sub(r"<[^>]+>", " ", str(s or ""))
    plain = html.unescape(plain)
    return re.sub(r"\s+", " ", plain).strip()


# --------------------------------------------------------------------------- #
# PaddleOCR-VL (Baidu) — a ~0.9B vision-language model (NaViT vision encoder +
# ERNIE-4.5) that parses a whole page (layout + text) at once. More accurate on
# messy handwriting and layout than classic PP-OCRv5, but it is a VLM: it wants a
# GPU. On a CPU-only box it runs at minutes per page, so this is an opt-in engine
# for when a GPU (or a hosted endpoint) is available. Shipped inside the
# `paddleocr` package as `PaddleOCRVL` in recent versions.
# --------------------------------------------------------------------------- #
class PaddleVLBackend(OCRBackend):
    name = "paddleocr-vl"

    def __init__(self):
        self._pipe = None
        # Guards building the pipeline and its predict() call: this backend
        # is a registry singleton shared by every concurrent analysis.
        self._lock = threading.Lock()

    def available(self):
        try:
            import paddleocr
        except Exception as e:
            return False, f"paddleocr not installed: {e}"
        if hasattr(paddleocr, "PaddleOCRVL"):
            device = "GPU" if gpu_capable("paddle") else "CPU (slow)"
            return True, f"paddleocr-vl available (device: {device})"
        return (
            False,
            "this paddleocr build has no PaddleOCRVL (pip install -U paddleocr)",
        )

    def _ensure(self):
        if self._pipe is not None:
            return
        with self._lock:
            if self._pipe is not None:  # a concurrent call may have built it
                return
            from paddleocr import PaddleOCRVL

            use_gpu = resolve_use_gpu("VAHINI_OCR_GPU", engine="paddle")
            device = "gpu" if use_gpu else "cpu"
            try:
                self._pipe = PaddleOCRVL(device=device)
            except TypeError:
                # Older signature without a device kwarg.
                self._pipe = PaddleOCRVL()

    def recognize(self, arr, lang, langs, detect_fn=None):
        self._ensure()
        with self._lock:
            try:
                results = self._pipe.predict(arr)
            except TypeError:
                results = self._pipe.predict(input=arr)
        return _vl_results_to_lines(results, lang)


def _vl_results_to_lines(results, lang):
    """Map PaddleOCR-VL output to the common line shape. The result schema has
    shifted across versions, so we try, in order: classic rec_texts/rec_polys,
    layout-parsing block lists, then a markdown text-only fallback."""
    lines = []
    for res in results or []:
        d = (
            res
            if isinstance(res, dict)
            else (getattr(res, "json", None) or {})
        )
        if isinstance(d, dict) and isinstance(d.get("res"), dict):
            d = d["res"]

        # 1) classic detection+recognition arrays
        rt = d.get("rec_texts") if isinstance(d, dict) else None
        if rt:
            rp = d.get("rec_polys") or d.get("rec_boxes") or []
            rs = d.get("rec_scores") or []
            for i, t in enumerate(rt):
                poly = rp[i] if i < len(rp) else []
                pts = [[float(x), float(y)] for x, y in (poly or [])]
                score = float(rs[i]) if i < len(rs) else 0.85
                if str(t).strip():
                    lines.append(make_line(t, pts, score, lang))
            if lines:
                continue

        # 2) layout-parsing block lists
        blocks = []
        if isinstance(d, dict):
            for k in (
                "parsing_res_list",
                "layout_parsing_result",
                "blocks",
                "boxes",
            ):
                v = d.get(k)
                if isinstance(v, list) and v:
                    blocks = v
                    break
        for blk in blocks:
            if not isinstance(blk, dict):
                continue
            txt = _html_to_text(
                blk.get("block_content")
                or blk.get("content")
                or blk.get("text")
                or ""
            )
            if not txt:
                continue
            bbox = (
                blk.get("block_bbox")
                or blk.get("bbox")
                or blk.get("coordinate")
            )
            if bbox and len(bbox) >= 4:
                x0, y0, x1, y1 = [float(v) for v in bbox[:4]]
                pts = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
            else:
                pts = []
            lines.append(make_line(txt, pts, 0.85, lang))
        if lines:
            continue

        # 3) markdown text-only fallback (no geometry)
        md = getattr(res, "markdown", None)
        if isinstance(md, dict):
            md = md.get("markdown_texts") or md.get("text") or ""
        txt = _html_to_text(md) if md else ""
        if txt:
            lines.append(make_line(txt, [], 0.8, lang))
    return lines


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
_REGISTRY = {}


def register(backend):
    _REGISTRY[backend.name] = backend
    return backend


def get_backend(name):
    return _REGISTRY.get((name or "").strip().lower())


def available_backends():
    """{name: (ok, reason)} for every registered engine — used by /health."""
    out = {}
    for name, be in _REGISTRY.items():
        try:
            out[name] = be.available()
        except Exception as e:  # never let a probe crash health
            out[name] = (False, str(e))
    return out


def init_registry(resolve_langs=None, paddle_config=None):
    """Build the registry once. `paddle_config` (see configure_paddle) sets
    the paddle engine build options; the server owns the language list."""
    _REGISTRY.clear()
    if paddle_config:
        configure_paddle(**paddle_config)
    register(PaddleBackend(resolve_langs=resolve_langs))
    register(TrOCRBackend())
    register(SuryaBackend())
    register(PaddleVLBackend())
    return _REGISTRY
