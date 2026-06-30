# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies. Pluggable OCR backends for the Vahini analyser.
# Third-party engines: PaddleOCR (Apache-2.0), TrOCR/transformers (MIT/Apache-2.0),
# Surya (datalab, GPL/commercial — see their licence), Chandra (OpenRAIL).
# See /THIRD-PARTY-NOTICES.md and server/README.md.
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
# 1. Heavy deps (paddlepaddle / torch / transformers / surya / chandra) are
#    imported LAZILY inside each adapter's methods. Importing this module costs
#    nothing and never fails just because an engine is not installed.
# 2. `available()` returns (ok, reason) so the server / /health can report which
#    engines are actually runnable on this machine without crashing.
# 3. Switch engine with the env var VAHINI_OCR_BACKEND = paddle|trocr|surya|
#    chandra|auto (default paddle). `auto` runs the installed candidates and
#    keeps the highest-quality result.

import io
import os
import re
import html
import urllib.request
import urllib.parse

import numpy as np
from PIL import Image

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

    def recognize(self, arr, lang, langs, detector=None):
        """Return list[line]. `arr` is an RGB uint8 numpy array.

        `detector` is an optional callable arr -> list[poly] that a recogniser-only
        engine (TrOCR) can use to localise text. Engines with their own detector
        ignore it.
        """
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# PaddleOCR (PP-OCRv5) — detection + recognition, classic CPU-friendly OCR
# --------------------------------------------------------------------------- #
class PaddleBackend(OCRBackend):
    """Thin wrapper around an injected paddle runner.

    The server owns the PaddleOCR engine cache + variant preprocessing (it is the
    proven path), and injects a `run(arr, lang) -> list[line]` callable plus a
    `detect(arr) -> list[poly]` callable. This keeps the legacy paddle code path
    byte-for-byte while still exposing paddle through the common registry.
    """

    name = "paddle"

    def __init__(self, run=None, detect=None, resolve_langs=None):
        self._run = run
        self._detect = detect
        self._resolve_langs = resolve_langs

    def available(self):
        try:
            import paddleocr  # noqa: F401
            return True, ""
        except Exception as e:
            return False, f"paddleocr not installed: {e}"

    def detect(self, arr):
        if self._detect is None:
            return []
        try:
            return self._detect(arr)
        except Exception:
            return []

    def recognize(self, arr, lang, langs, detector=None):
        if self._run is None:
            return []
        out = []
        use_langs = langs or (self._resolve_langs(lang) if self._resolve_langs else [lang or "en"])
        for lg in use_langs:
            try:
                out.extend(self._run(arr, lg))
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
        self._device = "cpu"
        self.model_name = _env("VAHINI_TROCR_MODEL", "microsoft/trocr-base-handwritten")
        # Cap the number of crops we feed per page so a busy page can't stall the
        # CPU for minutes. Detection order is preserved (top-to-bottom).
        self.max_crops = max(1, int(_env("VAHINI_TROCR_MAX_CROPS", "60") or "60"))
        self.min_side = max(4, int(_env("VAHINI_TROCR_MIN_SIDE", "8") or "8"))

    def available(self):
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401
            return True, ""
        except Exception as e:
            return False, f"trocr deps missing (pip install torch transformers): {e}"

    def _ensure_model(self):
        if self._model is not None:
            return
        import torch
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel

        self._processor = TrOCRProcessor.from_pretrained(self.model_name)
        self._model = VisionEncoderDecoderModel.from_pretrained(self.model_name)
        self._model.to(self._device)
        self._model.eval()
        torch.set_grad_enabled(False)

    def recognize(self, arr, lang, langs, detector=None):
        if detector is None:
            raise RuntimeError(
                "TrOCR is a recogniser-only engine and needs a detector. "
                "Run it with VAHINI_OCR_BACKEND=trocr while paddle is installed "
                "(paddle supplies the text-line boxes)."
            )
        polys = detector(arr) or []
        if not polys:
            return []
        self._ensure_model()
        import torch  # noqa: F401

        page = Image.fromarray(arr.astype(np.uint8), mode="RGB")
        H, W = arr.shape[:2]
        # Recognise top-to-bottom, then left-to-right (reading order).
        ordered = sorted(polys, key=lambda p: (poly_to_box(p)[1], poly_to_box(p)[0]))
        out = []
        for poly in ordered[: self.max_crops]:
            x, y, w, h = poly_to_box(poly)
            if w < self.min_side or h < self.min_side:
                continue
            x0 = max(0, int(round(x)))
            y0 = max(0, int(round(y)))
            x1 = min(W, int(round(x + w)))
            y1 = min(H, int(round(y + h)))
            if x1 <= x0 or y1 <= y0:
                continue
            crop = page.crop((x0, y0, x1, y1))
            try:
                text, score = self._read_crop(crop)
            except Exception:
                continue
            if text:
                out.append(make_line(text, poly, score, lang))
        return out

    def recognize_crop(self, crop_rgb):
        """Recognise a single pre-cropped line image → text. Used by the
        refinement path (paddle detects + classifies handwriting; TrOCR re-reads
        each handwriting crop for better text)."""
        self._ensure_model()
        text, _score = self._read_crop(Image.fromarray(crop_rgb.astype(np.uint8), mode="RGB"))
        return text

    def _read_crop(self, pil_img):
        import torch

        pixel_values = self._processor(images=pil_img.convert("RGB"), return_tensors="pt").pixel_values
        gen = self._model.generate(
            pixel_values.to(self._device),
            output_scores=True,
            return_dict_in_generate=True,
            max_new_tokens=64,
        )
        text = self._processor.batch_decode(gen.sequences, skip_special_tokens=True)[0].strip()
        # Approximate a confidence from the mean per-token softmax probability.
        score = 0.0
        try:
            if getattr(gen, "scores", None):
                probs = [torch.softmax(s[0], dim=-1).max().item() for s in gen.scores]
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

    def available(self):
        try:
            import surya  # noqa: F401
            return True, ""
        except Exception as e:
            return False, f"surya not installed (pip install surya-ocr): {e}"

    def _ensure(self):
        if self._rec is not None:
            return
        # Surya's module layout has shifted across releases; try the current
        # high-level API first, then a couple of known fallbacks.
        from surya.detection import DetectionPredictor
        from surya.recognition import RecognitionPredictor

        self._det = DetectionPredictor()
        try:
            from surya.inference import SuryaInferenceManager
            self._manager = SuryaInferenceManager()
            self._rec = RecognitionPredictor(self._manager)
        except Exception:
            # Older API: RecognitionPredictor() takes no manager.
            self._rec = RecognitionPredictor()

    def recognize_crop(self, crop_rgb):
        """Recognise a single pre-cropped line image → text (refinement path)."""
        self._ensure()
        img = Image.fromarray(crop_rgb.astype(np.uint8), mode="RGB")
        try:
            preds = self._rec([img], det_predictor=self._det)
        except TypeError:
            preds = self._rec([img], [["en"]], self._det)
        if not preds:
            return ""
        lines = getattr(preds[0], "text_lines", None) or []
        return " ".join((getattr(ln, "text", "") or "").strip() for ln in lines).strip()

    def recognize(self, arr, lang, langs, detector=None):
        self._ensure()
        page = Image.fromarray(arr.astype(np.uint8), mode="RGB")
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


# --------------------------------------------------------------------------- #
# Chandra 2 (datalab) — 4B VLM, best handwriting/Indic accuracy.
# Three ways to run, picked by VAHINI_CHANDRA_METHOD:
#   - "api"  : Datalab hosted API  (set DATALAB_API_KEY)  — works on any machine
#   - "vllm" : local vLLM server   (needs GPU)            — VLLM_API_BASE
#   - "hf"   : local transformers  (GPU strongly advised; CPU is impractical)
# On this CPU-only laptop, "api" is the only usable option.
# --------------------------------------------------------------------------- #
class ChandraBackend(OCRBackend):
    name = "chandra"

    def __init__(self):
        self.method = (_env("VAHINI_CHANDRA_METHOD", "api") or "api").lower()
        self.max_tokens = max(512, int(_env("VAHINI_CHANDRA_MAX_OUTPUT_TOKENS", "6144") or "6144"))
        self._manager = None

    def available(self):
        if self.method == "api":
            if _env("DATALAB_API_KEY"):
                return True, ""
            return False, "chandra api: set DATALAB_API_KEY"
        if self.method == "hf":
            try:
                import torch  # noqa: F401
                import transformers  # noqa: F401
                return True, "chandra hf ready (CPU run is very slow)"
            except Exception as e:
                return False, f"chandra hf deps missing: {e}"
        # vllm: probe the server quickly.
        base = _env("VLLM_API_BASE", "http://localhost:8000/v1")
        try:
            u = urllib.parse.urlparse(base)
            url = f"{u.scheme}://{u.netloc}/v1/models"
            with urllib.request.urlopen(url, timeout=0.6) as r:
                if 200 <= r.status < 300:
                    return True, ""
            return False, f"vllm non-2xx at {url}"
        except Exception as e:
            return False, f"vllm unreachable: {e}"

    # --- hosted Datalab API ------------------------------------------------- #
    def _recognize_api(self, arr, lang):
        import json
        import base64

        api_key = _env("DATALAB_API_KEY")
        base = _env("DATALAB_API_BASE", "https://api.datalab.to/v1")
        buf = io.BytesIO()
        Image.fromarray(arr.astype(np.uint8), mode="RGB").save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        body = json.dumps({"image": b64, "model": _env("DATALAB_OCR_MODEL", "chandra")}).encode()
        req = urllib.request.Request(
            f"{base}/ocr",
            data=body,
            headers={"Content-Type": "application/json", "X-Api-Key": api_key},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = json.loads(r.read().decode("utf-8"))
        return self._chunks_to_lines(payload.get("chunks") or payload.get("results") or [], lang)

    # --- local model (vllm / hf) via the chandra package -------------------- #
    def _get_manager(self):
        if self._manager is None:
            from chandra.model import InferenceManager
            method = self.method if self.method in ("vllm", "hf") else "vllm"
            self._manager = InferenceManager(method=method)
        return self._manager

    def _recognize_local(self, arr, lang):
        from chandra.model.schema import BatchInputItem

        manager = self._get_manager()
        img = Image.fromarray(arr.astype(np.uint8), mode="RGB")
        batch = [BatchInputItem(image=img, prompt_type="ocr_layout")]
        out = manager.generate(
            batch,
            max_output_tokens=self.max_tokens,
            max_retries=0,
            max_failure_retries=0,
            include_images=False,
            include_headers_footers=False,
        )
        if not out:
            return []
        return self._chunks_to_lines(out[0].chunks or [], lang)

    def _chunks_to_lines(self, chunks, lang):
        out = []
        for ch in chunks:
            label = str((ch.get("label", "") if isinstance(ch, dict) else "") or "").strip().lower()
            if label in ("image", "figure", "page-header", "page-footer", "blank-page"):
                continue
            content = ch.get("content", "") if isinstance(ch, dict) else ""
            txt = _html_to_text(content)
            if not txt:
                continue
            bbox = (ch.get("bbox") if isinstance(ch, dict) else None) or [0, 0, 1, 1]
            x0, y0, x1, y1 = [float(v) for v in bbox[:4]]
            poly = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
            out.append(make_line(txt, poly, 0.82, lang))
        return out

    def recognize(self, arr, lang, langs, detector=None):
        if self.method == "api":
            return self._recognize_api(arr, lang)
        return self._recognize_local(arr, lang)


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

    def available(self):
        try:
            import paddleocr
        except Exception as e:
            return False, f"paddleocr not installed: {e}"
        if hasattr(paddleocr, "PaddleOCRVL"):
            return True, "paddleocr-vl available (VLM; CPU run is slow, GPU advised)"
        return False, "this paddleocr build has no PaddleOCRVL (pip install -U paddleocr)"

    def _ensure(self):
        if self._pipe is None:
            from paddleocr import PaddleOCRVL
            kwargs = {}
            device = "gpu" if _env("VAHINI_OCR_GPU", "0") == "1" else "cpu"
            try:
                self._pipe = PaddleOCRVL(device=device)
            except TypeError:
                # Older signature without a device kwarg.
                self._pipe = PaddleOCRVL()

    def recognize(self, arr, lang, langs, detector=None):
        self._ensure()
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
    for res in (results or []):
        d = res if isinstance(res, dict) else (getattr(res, "json", None) or {})
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
            for k in ("parsing_res_list", "layout_parsing_result", "blocks", "boxes"):
                v = d.get(k)
                if isinstance(v, list) and v:
                    blocks = v
                    break
        for blk in blocks:
            if not isinstance(blk, dict):
                continue
            txt = _html_to_text(blk.get("block_content") or blk.get("content") or blk.get("text") or "")
            if not txt:
                continue
            bbox = blk.get("block_bbox") or blk.get("bbox") or blk.get("coordinate")
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


def init_registry(paddle_run=None, paddle_detect=None, resolve_langs=None):
    """Build the registry once. The server injects its proven paddle runner."""
    _REGISTRY.clear()
    register(PaddleBackend(run=paddle_run, detect=paddle_detect, resolve_langs=resolve_langs))
    register(TrOCRBackend())
    register(SuryaBackend())
    register(ChandraBackend())
    register(PaddleVLBackend())
    return _REGISTRY
