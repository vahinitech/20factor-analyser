# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies. Server-side handwriting/print recognition.
# Third-party: PaddleOCR (Apache-2.0). See /THIRD-PARTY-NOTICES.md and server/README.md
#
# ppocr-server.py — PP-OCRv5 recognition microservice for the Vahini analyser.
#
#   POST /ocr   multipart/form-data
#       image : the page image (required)
#       lang  : language code  (optional, default "en"; e.g. "te" Telugu,
#                                "hi" Hindi, "ta" Tamil, "kn" Kannada, "ml" Malayalam)
#       det   : "true"/"false" run text detection      (default true)
#       rec   : "true"/"false" run text recognition    (default true)
#   ->  JSON  { "rec_texts":[...], "rec_polys":[[[x,y]...]...], "rec_scores":[...],
#               "full_text":"...", "engine":"pp-ocrv5", "lang":"en" }
#
#   GET  /health -> { "ok": true, ... }
#
# This response shape is consumed directly by src/engine/ocr.js -> normalize().
#
# IMPORTANT — what "download" means here:
#   You do NOT download model files by hand. The `paddleocr` package fetches the
#   PP-OCRv5 detection + recognition weights AUTOMATICALLY the first time a given
#   language is requested, and caches them under ~/.paddlex (or PADDLE_PDX_CACHE_HOME).
#   The first request for a new language is therefore slow (it downloads); every
#   request after that is fast. To pre-warm at deploy time, see README "warm-up".

import io
import os
import re
import base64
import math
import time
import copy
import hashlib
import threading
import sys
import urllib.request
import urllib.parse
from functools import lru_cache

# This module is sometimes loaded by file path (analyser-ocr-server.py uses
# importlib), which does NOT put its own folder on sys.path. Add it so the
# sibling helper modules (ocr_backends, classify) always import cleanly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ocr_backends  # pluggable engine adapters (paddle/trocr/surya/chandra)
import classify      # printed-vs-handwriting classifier

# Paddle 3.x on some CPUs can fail in oneDNN/PIR execution paths for OCR.
# Prefer the stable execution route unless explicitly overridden.
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
from PIL import Image, ImageOps, ImageFilter

try:
    import cv2
except Exception:
    cv2 = None

# PaddleOCR 3.x (PP-OCRv5) is imported LAZILY inside get_engine() so this module
# loads even when paddle isn't installed (e.g. a non-paddle backend, or tests).
# pip install paddleocr paddlepaddle  (see requirements.txt)

app = FastAPI(title="Vahini PP-OCRv5 service", version="1.0")

# Allow the Vahini site to call this from the browser. Lock this down in prod to
# your exact origin(s) instead of "*".
ALLOWED_ORIGINS = os.environ.get("VAHINI_OCR_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

USE_GPU = os.environ.get("VAHINI_OCR_GPU", "0") == "1"
OCR_LANGS = [s.strip() for s in os.environ.get("VAHINI_OCR_LANGS", "en,te").split(",") if s.strip()]
OCR_BACKEND = (os.environ.get("VAHINI_OCR_BACKEND", "paddle") or "paddle").strip().lower()
CHANDRA_METHOD = (os.environ.get("VAHINI_CHANDRA_METHOD", "api") or "api").strip().lower()
CHANDRA_MAX_TOKENS = max(512, int(os.environ.get("VAHINI_CHANDRA_MAX_OUTPUT_TOKENS", "6144")))
MAX_VARIANTS = max(1, min(3, int(os.environ.get("VAHINI_OCR_VARIANTS", "2"))))
ADV_PREPROC = os.environ.get("VAHINI_OCR_ADV_PREPROC", "1") == "1"
USE_DOC_ORIENTATION = os.environ.get("VAHINI_OCR_DOC_ORIENT", "0") == "1"
USE_DOC_UNWARP = os.environ.get("VAHINI_OCR_DOC_UNWARP", "0") == "1"
USE_TEXTLINE_ORIENTATION = os.environ.get("VAHINI_OCR_TEXTLINE_ORIENT", "0") == "1"
MAX_OCR_SIDE = max(960, int(os.environ.get("VAHINI_OCR_MAX_SIDE", "2200")))
OCR_VERSION = (os.environ.get("VAHINI_OCR_VERSION", "PP-OCRv5") or "").strip() or None
# Default to the MOBILE detection model: on CPU it is several times faster than
# PP-OCRv5_server_det with negligible real-world accuracy loss on handwriting
# pages. Set VAHINI_OCR_DET_MODEL_NAME=PP-OCRv5_server_det to restore the heavy
# model (recommended only on a GPU).
DET_MODEL_NAME = (os.environ.get("VAHINI_OCR_DET_MODEL_NAME", "PP-OCRv5_mobile_det") or "").strip() or None
# Recognition: default English to the SERVER rec model (more accurate on
# handwriting than the mobile rec, e.g. reads "fox"/"small" where mobile reads
# "tox"/"sud"), while detection stays on the fast mobile model. Telugu keeps its
# language-specific mobile rec. Override with VAHINI_OCR_REC_MODEL_MAP.
REC_MODEL_MAP_RAW = os.environ.get("VAHINI_OCR_REC_MODEL_MAP", "en:PP-OCRv5_server_rec,te:te_PP-OCRv5_mobile_rec")
TEXT_DET_LIMIT_SIDE_LEN = max(0, int(os.environ.get("VAHINI_OCR_DET_LIMIT_SIDE_LEN", "2048")))
TEXT_REC_SCORE_THRESH = float(os.environ.get("VAHINI_OCR_TEXT_REC_SCORE_THRESH", "0.0"))
AUTO_MIN_LINES = max(2, int(os.environ.get("VAHINI_OCR_AUTO_MIN_LINES", "3")))
VARIANT_MIN_LINES = max(1, int(os.environ.get("VAHINI_OCR_VARIANT_MIN_LINES", str(AUTO_MIN_LINES))))
RESP_CACHE_TTL_SEC = max(0, int(os.environ.get("VAHINI_OCR_CACHE_TTL_SEC", "180")))
RESP_CACHE_MAX_ITEMS = max(16, int(os.environ.get("VAHINI_OCR_CACHE_MAX_ITEMS", "128")))
_TELUGU = re.compile(r"[\u0C00-\u0C7F]")

_RESP_CACHE = {}
_RESP_CACHE_LOCK = threading.Lock()


def _parse_rec_model_map(raw: str):
    out = {}
    for item in (raw or "").split(","):
        token = item.strip()
        if not token or ":" not in token:
            continue
        k, v = token.split(":", 1)
        k = k.strip().lower()
        v = v.strip()
        if k and v:
            out[k] = v
    return out


REC_MODEL_MAP = _parse_rec_model_map(REC_MODEL_MAP_RAW)


def _rec_model_for_lang(lang: str):
    lg = (lang or "").strip().lower()
    if lg in REC_MODEL_MAP:
        return REC_MODEL_MAP[lg]
    return REC_MODEL_MAP.get("*", None)


def _engine_kwargs(lang: str, safe: bool = False):
    kwargs = {
        "lang": lang,
        "use_doc_orientation_classify": False if safe else USE_DOC_ORIENTATION,
        "use_doc_unwarping": False if safe else USE_DOC_UNWARP,
        "use_textline_orientation": False if safe else USE_TEXTLINE_ORIENTATION,
        "device": "cpu" if safe else ("gpu" if USE_GPU else "cpu"),
    }
    if OCR_VERSION:
        kwargs["ocr_version"] = OCR_VERSION
    if DET_MODEL_NAME:
        kwargs["text_detection_model_name"] = DET_MODEL_NAME
    rec_name = _rec_model_for_lang(lang)
    if rec_name:
        kwargs["text_recognition_model_name"] = rec_name
    if TEXT_DET_LIMIT_SIDE_LEN > 0:
        kwargs["text_det_limit_side_len"] = TEXT_DET_LIMIT_SIDE_LEN
    kwargs["text_rec_score_thresh"] = TEXT_REC_SCORE_THRESH
    return kwargs


def _cache_key(endpoint: str, raw: bytes, lang: str, extra: str = "") -> str:
    h = hashlib.sha1(raw).hexdigest()
    return f"{endpoint}|{(lang or '').strip().lower()}|{extra}|{h}"


def _cache_get(key: str):
    if RESP_CACHE_TTL_SEC <= 0:
        return None
    now = time.time()
    with _RESP_CACHE_LOCK:
        row = _RESP_CACHE.get(key)
        if not row:
            return None
        exp, payload = row
        if exp < now:
            _RESP_CACHE.pop(key, None)
            return None
        return copy.deepcopy(payload)


def _cache_set(key: str, payload):
    if RESP_CACHE_TTL_SEC <= 0:
        return
    now = time.time()
    with _RESP_CACHE_LOCK:
        if len(_RESP_CACHE) >= RESP_CACHE_MAX_ITEMS:
            # Drop oldest by expiry timestamp.
            oldest = sorted(_RESP_CACHE.items(), key=lambda kv: kv[1][0])[: max(1, RESP_CACHE_MAX_ITEMS // 8)]
            for k, _ in oldest:
                _RESP_CACHE.pop(k, None)
        _RESP_CACHE[key] = (now + RESP_CACHE_TTL_SEC, copy.deepcopy(payload))


def _with_meta(payload: dict, cache_status: str, t0: float):
    out = dict(payload)
    out["_meta"] = {
        "cache": cache_status,
        "elapsed_ms": int(round((time.perf_counter() - t0) * 1000.0)),
    }
    return out


@app.on_event("startup")
def _warm_startup_engines():
    # Warm EVERY configured language (both the normal and the safe engine) at
    # startup so the FIRST real request isn't slowed by model download/init —
    # which previously pushed the first /report-python past the reverse-proxy
    # read timeout. Only paddle is warmed here; other backends warm on demand.
    if os.environ.get("VAHINI_OCR_PRELOAD_ON_START", "1") != "1":
        return
    for lg in (OCR_LANGS or ["en"]):
        try:
            get_engine(lg)
            get_engine_safe(lg)
        except Exception:
            pass


@lru_cache(maxsize=8)
def get_engine(lang: str):
    """One PaddleOCR instance per language, built lazily and cached.
    PP-OCRv5 is the default model family in PaddleOCR 3.x."""
    from paddleocr import PaddleOCR
    try:
        return PaddleOCR(**_engine_kwargs(lang, safe=False))
    except TypeError:
        # PaddleOCR 2.x compatibility path.
        return PaddleOCR(
            lang=lang,
            use_angle_cls=True,
            use_gpu=USE_GPU,
            show_log=False,
        )


@lru_cache(maxsize=8)
def get_engine_safe(lang: str):
    """Fallback engine with minimal pre/post modules for max compatibility."""
    from paddleocr import PaddleOCR
    try:
        return PaddleOCR(**_engine_kwargs(lang, safe=True))
    except TypeError:
        return PaddleOCR(
            lang=lang,
            use_angle_cls=True,
            use_gpu=False,
            show_log=False,
        )


def _pdf_first_page(raw: bytes) -> Image.Image:
    """Render ONLY the first page of a PDF to an image. Multi-page PDFs are
    intentionally restricted to page 1 (the analyser scores a single handwriting
    page); the rest are ignored."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(raw)
    try:
        page = pdf[0]
        # ~150 DPI (scale = 150/72) is plenty for handwriting OCR.
        bitmap = page.render(scale=150.0 / 72.0)
        return bitmap.to_pil().convert("RGB")
    finally:
        pdf.close()


def _decode_image(raw: bytes) -> Image.Image:
    """Decode an upload to an RGB PIL image. Accepts normal images and PDFs;
    for a PDF only the first page is used."""
    if raw[:4] == b"%PDF":
        return _pdf_first_page(raw)
    return Image.open(io.BytesIO(raw)).convert("RGB")


def _to_numpy(raw: bytes) -> np.ndarray:
    img = _decode_image(raw)
    w, h = img.size
    m = max(w, h)
    if m > MAX_OCR_SIDE:
        scale = MAX_OCR_SIDE / float(m)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    return np.array(img)


def _variants(arr: np.ndarray):
    """Yield preprocessing variants LAZILY, base first.

    This is a generator on purpose: the caller stops pulling variants as soon as
    a pass yields enough text (the common clear-page case), so the expensive
    enhancement variants (notably cv2.fastNlMeansDenoising, which can cost tens of
    seconds) are NEVER computed for a normal page. Only faint/low-yield images
    pay for the extra variants. Output is unchanged for the variants that do run.
    """
    base = Image.fromarray(arr).convert("RGB")
    seen = set()
    emitted = 0

    def _fresh(v):
        key = hashlib.sha1(v.tobytes()).hexdigest()
        if key in seen:
            return None
        seen.add(key)
        return v

    # Variant 0: the raw page (no processing) — fast, and enough for clear pages.
    v = _fresh(np.array(base))
    if v is not None:
        yield v
        emitted += 1
    if emitted >= MAX_VARIANTS:
        return

    # Variant 1: local-contrast enhancement (+ denoise/CLAHE) for faint strokes.
    g = ImageOps.autocontrast(base.convert("L"), cutoff=1).filter(ImageFilter.SHARPEN)
    if cv2 is not None and ADV_PREPROC:
        gv = np.array(g)
        gv = cv2.fastNlMeansDenoising(gv, None, h=10, templateWindowSize=7, searchWindowSize=21)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gv = clahe.apply(gv)
        g = Image.fromarray(gv)
    v = _fresh(np.array(g.convert("RGB")))
    if v is not None:
        yield v
        emitted += 1
    if emitted >= MAX_VARIANTS:
        return

    # Variant 2: adaptive threshold path helps on uneven lighting/shadows.
    if cv2 is not None and ADV_PREPROC:
        gray = cv2.cvtColor(np.array(base), cv2.COLOR_RGB2GRAY)
        thr = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)
        v = _fresh(np.dstack([thr, thr, thr]))
        if v is not None:
            yield v
            emitted += 1
        if emitted >= MAX_VARIANTS:
            return

    # Variant 3: upscale small captures so the recogniser sees more detail.
    if min(base.size) < 1200:
        up = base.resize((int(base.width * 1.8), int(base.height * 1.8)), Image.Resampling.BICUBIC)
        up = ImageOps.autocontrast(up, cutoff=1).filter(ImageFilter.SHARPEN)
        v = _fresh(np.array(up.convert("RGB")))
        if v is not None:
            yield v
            emitted += 1


def _iou(box1, box2):
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2
    ix = max(0.0, min(x1 + w1, x2 + w2) - max(x1, x2))
    iy = max(0.0, min(y1 + h1, y2 + h2) - max(y1, y2))
    inter = ix * iy
    union = (w1 * h1) + (w2 * h2) - inter
    return inter / union if union > 0 else 0.0


def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _looks_printed(text: str, score: float, box=None) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    clean = len(re.sub(r"[^\w\u0C00-\u0C7F]", "", t)) / max(1, len(t))
    alpha = len(re.findall(r"[A-Za-z]", t))
    upper_ratio = (len(re.findall(r"[A-Z]", t)) / max(1, alpha)) if alpha else 0.0
    digit_ratio = len(re.findall(r"\d", t)) / max(1, len(t))
    form_kw = bool(re.search(r"\b(name|address|date|age|sex|case|doctor|diagnosis|admission|procedure|phone|id|form|hospital)\b", low))
    # Printed headers/forms are often high confidence, all-caps, dense and horizontally long.
    aspect = 0.0
    if box and len(box) >= 4:
        bw = float(max(1.0, box[2]))
        bh = float(max(1.0, box[3]))
        aspect = bw / bh
    return bool(
        (score >= 0.985 and len(t) >= 8 and clean >= 0.88 and (upper_ratio >= 0.62 or form_kw))
        or (score >= 0.975 and form_kw and (digit_ratio >= 0.10 or aspect >= 9.0))
        or (score >= 0.992 and aspect >= 11.0 and len(t) >= 12)
    )


def _resolve_langs(lang: str):
    req = (lang or "").strip().lower()
    if not req or req == "auto":
        return OCR_LANGS or ["en"]
    if "," in req:
        langs = [x.strip() for x in req.split(",") if x.strip()]
        return [x for x in langs if x in OCR_LANGS] or OCR_LANGS or ["en"]
    return [req] if req in OCR_LANGS else OCR_LANGS or ["en"]


def _merge_lines(lines):
    kept = []
    for line in sorted(lines, key=lambda l: float(l.get("score", 0.0)), reverse=True):
        text = _normalize_text(line.get("text", ""))
        if not text:
            continue
        is_dup = False
        for k in kept:
            if _iou(line["box"], k["box"]) > 0.50:
                if text == _normalize_text(k.get("text", "")):
                    is_dup = True
                    break
        if not is_dup:
            kept.append(line)
    kept.sort(key=lambda l: (l["box"][1], l["box"][0]))
    return kept


def _region_filter_lines(lines, arr_shape):
    if not lines:
        return []
    h = float(max(1, arr_shape[0] if len(arr_shape) >= 1 else 1))
    w = float(max(1, arr_shape[1] if len(arr_shape) >= 2 else 1))

    out = []
    for l in lines:
        t = str(l.get("text", "") or "").strip()
        if not t:
            continue
        box = l.get("box") or [0.0, 0.0, 0.0, 0.0]
        bw = float(box[2]) if len(box) >= 3 else 0.0
        bh = float(box[3]) if len(box) >= 4 else 0.0
        by = float(box[1]) if len(box) >= 2 else 0.0
        aspect = bw / max(1.0, bh)
        area_ratio = (bw * bh) / max(1.0, w * h)
        y_ratio = by / max(1.0, h)
        low = t.lower()
        sc = float(l.get("score", 0.0) or 0.0)

        # Drop tiny low-confidence specks and OCR garbage fragments.
        if len(t) <= 1 and sc < 0.92 and area_ratio < 0.0008:
            continue
        if len(t) <= 3 and sc < 0.65 and area_ratio < 0.0015:
            continue

        # Drop extreme-width header/footer lines that are likely printed metadata.
        if (y_ratio < 0.14 or y_ratio > 0.90) and aspect > 8.0 and (bool(l.get("printed_hint")) or sc > 0.75):
            continue

        # Remove long numeric/id strips; these are not handwriting quality evidence.
        digit_ratio = len(re.findall(r"\d", t)) / max(1, len(t))
        if digit_ratio > 0.50 and len(t) >= 6 and (aspect > 4.0 or bool(re.search(r"\b(ip|op|id|no\.?|ph|phone)\b", low))):
            continue

        out.append(l)

    return out if out else lines


def _prefer_handwritten(lines):
    """Keep handwriting, drop printed text.

    The printed/handwriting decision now comes from classify.classify_lines
    (real stroke-width / glyph-height / edge / confidence CV features), set on
    each line as `printed_hint`. This replaces the old brittle keyword rules.
    Fail-open: if classification would remove almost everything (a fully printed
    scan, or a misfire on faint pen), keep all lines rather than emit nothing.
    """
    if not lines:
        return []
    hand = [l for l in lines if not bool(l.get("printed_hint"))]
    if len(hand) < max(1, int(0.15 * len(lines))):
        return lines
    return hand


def _run(engine, arr: np.ndarray, lang: str):
    """Return (texts, polys, scores) across PaddleOCR API variants."""
    # Prefer the classic ocr() entrypoint on CPU builds to avoid PIR/oneDNN
    # runtime incompatibilities seen on some Paddle 3.x combinations.
    try:
        results = engine.ocr(arr)
    except Exception:
        # Fallback to predict() for builds that only expose it.
        results = engine.predict(arr)

    lines = []
    for res in (results or []):
        # 3.x result objects behave like dicts with these keys
        d = res if isinstance(res, dict) else getattr(res, "json", None) or {}
        if isinstance(res, dict) or "rec_texts" in d:
            rt = (res.get("rec_texts") if isinstance(res, dict) else d.get("rec_texts"))
            rp = (res.get("rec_polys") if isinstance(res, dict) else d.get("rec_polys"))
            if rp is None:
                rp = (res.get("rec_boxes") if isinstance(res, dict) else d.get("rec_boxes"))
            rs = (res.get("rec_scores") if isinstance(res, dict) else d.get("rec_scores"))
            rt = list(rt) if rt is not None else []
            rp = list(rp) if rp is not None else []
            rs = list(rs) if rs is not None else []
            for i, t in enumerate(rt):
                poly = rp[i] if i < len(rp) else []
                pts = [[float(x), float(y)] for x, y in (poly if poly is not None else [])]
                if pts:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    box = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
                else:
                    box = [0.0, 0.0, 0.0, 0.0]
                score = float(rs[i]) if i < len(rs) else 0.0
                lines.append({
                    "text": t,
                    "poly": pts,
                    "box": box,
                    "score": score,
                    "lang": "te" if _TELUGU.search(t or "") else lang,
                    "printed_hint": _looks_printed(t, score, box),
                })
        else:
            # --- classic API: [[poly, (text, score)], ...] ---
            if not isinstance(res, (list, tuple)):
                continue
            for item in res:
                poly, (txt, sc) = item[0], item[1]
                pts = [[float(x), float(y)] for x, y in poly]
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                box = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)] if pts else [0.0, 0.0, 0.0, 0.0]
                score = float(sc)
                lines.append({
                    "text": txt,
                    "poly": pts,
                    "box": box,
                    "score": score,
                    "lang": "te" if _TELUGU.search(txt or "") else lang,
                    "printed_hint": _looks_printed(txt, score, box),
                })
    return lines


# NOTE: Chandra recognition now lives in ocr_backends.ChandraBackend (api/vllm/hf
# methods). The previous inline _run_chandra / get_chandra_manager helpers were
# removed when the engine adapters were centralised.


def _lines_quality(lines):
    if not lines:
        return -1e9
    texts = [str(l.get("text", "") or "").strip() for l in lines]
    texts = [t for t in texts if t]
    if not texts:
        return -1e9
    words = sum(len(t.split()) for t in texts)
    chars = sum(len(t) for t in texts)
    short_noise = sum(1 for t in texts if len(t) <= 2)
    digit_heavy = sum(1 for t in texts if (len(re.findall(r"\d", t)) / max(1, len(t))) > 0.55)
    avg_conf = sum(float(l.get("score", 0.0) or 0.0) for l in lines) / max(1, len(lines))
    return float(chars + 2.5 * words + 12.0 * avg_conf - 5.0 * short_noise - 3.0 * digit_heavy)


def _collect_lines_paddle(arr: np.ndarray, lang: str):
    last_err = ""
    langs = _resolve_langs(lang)
    lines = []
    for lg in langs:
        engine = get_engine(lg)
        engine_safe = get_engine_safe(lg)
        for variant in _variants(arr):
            try:
                lines.extend(_run(engine, variant, lg))
            except Exception as e:
                last_err = str(e)
                try:
                    lines.extend(_run(engine_safe, variant, lg))
                except Exception as e2:
                    last_err = str(e2)
            if (lang or "").strip().lower() == "auto" and len(lines) >= VARIANT_MIN_LINES:
                break
        if (lang or "").strip().lower() == "auto" and len(lines) >= AUTO_MIN_LINES:
            break
    return lines, last_err


# --- registry wiring: expose paddle through the common backend interface ----- #
def _paddle_run_lang(arr: np.ndarray, lg: str):
    """Single-language paddle recogniser over all preprocessing variants.
    Injected into ocr_backends.PaddleBackend so paddle is reachable via the
    registry without changing the proven code path."""
    engine = get_engine(lg)
    engine_safe = get_engine_safe(lg)
    out = []
    for variant in _variants(arr):
        try:
            out.extend(_run(engine, variant, lg))
        except Exception:
            try:
                out.extend(_run(engine_safe, variant, lg))
            except Exception:
                pass
    return out


def _paddle_detect(arr: np.ndarray):
    """Detection boxes (polys) from paddle, used by recogniser-only engines
    such as TrOCR. Paddle detects + recognises in one pass; we keep the polys."""
    primary = (_resolve_langs("auto")[:1] or ["en"])[0]
    try:
        lines = _paddle_run_lang(arr, primary)
    except Exception:
        return []
    return [l.get("poly") for l in lines if l.get("poly")]


ocr_backends.init_registry(
    paddle_run=_paddle_run_lang,
    paddle_detect=_paddle_detect,
    resolve_langs=_resolve_langs,
)


def _backend_recognize(name: str, arr: np.ndarray, lang: str):
    """Run a non-paddle backend through the registry. Returns (lines, error)."""
    be = ocr_backends.get_backend(name)
    if be is None:
        return [], f"unknown backend '{name}'"
    ok, reason = be.available()
    if not ok:
        return [], reason
    try:
        lines = be.recognize(arr, (lang or "en"), _resolve_langs(lang), detector=_paddle_detect)
        return lines, ""
    except Exception as e:
        return [], str(e)


def _collect_lines(arr: np.ndarray, lang: str):
    """Dispatch recognition to the configured backend.

    VAHINI_OCR_BACKEND = paddle | trocr | surya | chandra | auto
    Any non-paddle engine that is unavailable or returns nothing falls back to
    paddle, so the caller ALWAYS gets a usable result on this CPU-only box.
    """
    mode = OCR_BACKEND if OCR_BACKEND in ("paddle", "trocr", "surya", "chandra", "paddleocr-vl", "auto") else "paddle"
    compare = {}

    paddle_lines, paddle_err = _collect_lines_paddle(arr, lang)
    if mode == "paddle":
        return paddle_lines, paddle_err, "paddle", compare

    if mode == "trocr":
        # TrOCR is a recogniser, not a detector/classifier. Keep paddle's
        # detection + printed/handwriting classification (which we trust), and
        # let TrOCR REFINE the handwriting text downstream (see
        # _refine_handwriting_text). This avoids feeding the classifier TrOCR's
        # uncalibrated scores and confines TrOCR to what it's good at.
        return paddle_lines, paddle_err, "trocr", {"strategy": "paddle-detect+classify, trocr-refine"}

    if mode in ("surya", "chandra", "paddleocr-vl"):
        alt_lines, alt_err = _backend_recognize(mode, arr, lang)
        if alt_lines:
            return alt_lines, alt_err, mode, compare
        compare = {"requested": mode, "fallback": "paddle", "reason": alt_err}
        return paddle_lines, (paddle_err or alt_err), "paddle", compare

    # auto: score paddle against every available alternative, keep the best.
    candidates = [("paddle", paddle_lines, paddle_err)]
    for name in ("trocr", "surya", "chandra", "paddleocr-vl"):
        be = ocr_backends.get_backend(name)
        if be is None:
            continue
        ok, _reason = be.available()
        if not ok:
            continue
        alt_lines, alt_err = _backend_recognize(name, arr, lang)
        if alt_lines:
            candidates.append((name, alt_lines, alt_err))

    scored = {}
    best = None  # (name, raw_lines, err, quality)
    for name, lns, err in candidates:
        proc = _region_filter_lines(_merge_lines(lns), arr.shape)
        q = _lines_quality(proc)
        scored[name] = {"quality": round(q, 2), "count": len(proc)}
        if best is None or q > best[3]:
            best = (name, lns, err, q)
    compare = {"mode": "auto", "scored": scored, "selected": best[0] if best else "paddle"}
    if best:
        return best[1], best[2], best[0], compare
    return paddle_lines, paddle_err, "paddle", compare


def _is_noise_line(l):
    """Single-char / punctuation-only fragments are OCR noise, not handwriting
    evidence (e.g. a stray 'e' or '2.')."""
    t = str(l.get("text", "") or "").strip()
    if len(t) < 2:
        return True
    if not re.search(r"[A-Za-z0-9ఀ-౿]", t):
        return True
    return False


# Accept the engine's text only when it's at least this similar to paddle's
# reading. 0.70 cleanly separates real refinements (e.g. "manay ment"->
# "management" ~0.84) from VLM hallucinations ("Navasaropet"->"niguassanette"
# ~0.50, "Hypothyoidum"->"Transportation legislation" ~0.27).
REFINE_MIN_SIM = float(os.environ.get("VAHINI_REFINE_MIN_SIM", "0.70"))


def _refine_handwriting_text(raw_bytes: bytes, proc_arr: np.ndarray, hand_lines, backend_name: str):
    """Re-recognise each handwriting crop with a stronger engine (TrOCR) and
    accept its text ONLY when it roughly agrees with paddle's reading.

    Why the agreement guard: TrOCR is a language-model recogniser that produces
    excellent text on clear English words ("manay ment" -> "management") but
    HALLUCINATES on out-of-distribution medical/Indic content ("Hypothyoidum" ->
    "Transportation legislation"). Requiring a minimum string similarity to
    paddle's reading keeps the wins and rejects the hallucinations. Crops are
    taken from the FULL-RESOLUTION original (paddle's working image is
    downscaled), which materially improves recognition.
    """
    import difflib

    be = ocr_backends.get_backend(backend_name)
    if be is None or not hasattr(be, "recognize_crop"):
        return
    try:
        ok, _reason = be.available()
    except Exception:
        ok = False
    if not ok:
        return
    try:
        full = np.array(_decode_image(raw_bytes))
    except Exception:
        return

    ph = float(max(1, proc_arr.shape[0]))
    pw = float(max(1, proc_arr.shape[1]))
    OH, OW = full.shape[0], full.shape[1]
    sx, sy = OW / pw, OH / ph

    for l in hand_lines[:40]:
        box = l.get("box") or [0, 0, 0, 0]
        if len(box) < 4:
            continue
        x, y, w, h = [float(v) for v in box[:4]]
        padx = int(w * sx * 0.06) + 6
        pady = int(h * sy * 0.25) + 6
        x0 = max(0, int(x * sx) - padx)
        y0 = max(0, int(y * sy) - pady)
        x1 = min(OW, int((x + w) * sx) + padx)
        y1 = min(OH, int((y + h) * sy) + pady)
        if x1 <= x0 or y1 <= y0:
            continue
        crop = full[y0:y1, x0:x1]
        try:
            cand = (be.recognize_crop(crop) or "").strip()
        except Exception:
            continue
        # TrOCR often appends a stray " ." — drop trailing isolated punctuation.
        cand = re.sub(r"\s*[.·,]+\s*$", "", cand).strip()
        if not cand:
            continue
        base = str(l.get("text", "") or "").strip()
        a = re.sub(r"[^a-z0-9]", "", base.lower())
        b = re.sub(r"[^a-z0-9]", "", cand.lower())
        sim = difflib.SequenceMatcher(None, a, b).ratio() if (a and b) else 0.0
        if sim >= REFINE_MIN_SIM:
            l["text"] = cand
            l["refined_by"] = backend_name


def _extract_hand_lines(arr: np.ndarray, raw_lines, raw_bytes: bytes = None, refine_backend: str = None):
    """Shared post-processing: merge → region-filter → classify printed vs
    handwriting → keep handwriting, minus OCR noise fragments → optionally refine
    handwriting text with a stronger engine. Returns (all_lines, hand_lines)."""
    lines = _region_filter_lines(_merge_lines(raw_lines), arr.shape)
    classify.classify_lines(arr, lines)
    hand_lines = _prefer_handwritten(lines)
    cleaned = [l for l in hand_lines if not _is_noise_line(l)]
    # Fail-open: never empty the set just because noise filtering was strict.
    if cleaned:
        hand_lines = cleaned
    if refine_backend == "trocr" and raw_bytes:
        _refine_handwriting_text(raw_bytes, arr, hand_lines, refine_backend)
    return lines, hand_lines


def _align_to_expected(hand_lines, expected_text):
    """Reference-passage alignment (the consistent-accuracy path).

    When the writer copies a KNOWN passage, free-form recognition becomes a
    verification problem: we already know the target text. We match each
    recognised handwriting line to its best expected line and, when they agree
    well enough, present the KNOWN text instead of the garbled OCR. This makes
    the recognised text dependable on every upload that supplies a passage, and
    yields a real per-line "how closely you matched it" score.

    Returns a summary dict, or None when there is no passage to align to. Mutates
    each aligned line: sets l['expected'], l['match'] (0..1), and replaces
    l['text'] with the known line when the match is reasonable.
    """
    import difflib

    exp_lines = [s.strip() for s in re.split(r"[\r\n]+", expected_text or "") if s.strip()]
    if not exp_lines or not hand_lines:
        return None

    def _norm(s):
        return re.sub(r"\s+", " ", re.sub(r"[^\w ]", "", str(s or "").lower())).strip()

    matches = []
    for hl in hand_lines:
        rec = _norm(hl.get("text", ""))
        if not rec:
            continue
        best_i, best_r = -1, 0.0
        for i, el in enumerate(exp_lines):
            r = difflib.SequenceMatcher(None, rec, _norm(el)).ratio()
            if r > best_r:
                best_r, best_i = r, i
        if best_i >= 0 and best_r >= 0.45:
            hl["expected"] = exp_lines[best_i]
            hl["match"] = round(best_r, 3)
            hl["text"] = exp_lines[best_i]  # show the known target, not garbled OCR
            matches.append(best_r)

    if not matches:
        return {"passage_lines": len(exp_lines), "aligned": 0, "passage_match": 0.0}
    return {
        "passage_lines": len(exp_lines),
        "aligned": len(matches),
        "passage_match": round(sum(matches) / len(matches), 3),
    }


def _to_data_url(rgb_arr: np.ndarray, quality: int = 82) -> str:
    img = Image.fromarray(rgb_arr.astype(np.uint8), mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=int(max(35, min(95, quality))), optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _crop_rgb(arr: np.ndarray, box):
    x, y, w, h = box
    x0 = max(0, int(round(x)))
    y0 = max(0, int(round(y)))
    x1 = min(arr.shape[1], int(round(x + w)))
    y1 = min(arr.shape[0], int(round(y + h)))
    if x1 <= x0 or y1 <= y0:
        return None
    return arr[y0:y1, x0:x1]


def _build_region_previews(arr: np.ndarray, lines, max_regions: int = 8):
    if not lines:
        return []
    # Rank by region AREA, not OCR score. Ranking by score surfaced the most
    # confident (i.e. most printed-like) lines first, so any residual printed
    # leak became the evidence crop for every factor. Larger handwriting regions
    # are the more representative evidence; printed lines are already excluded.
    def _area(l):
        b = l.get("box") or [0, 0, 0, 0]
        return float(max(0.0, b[2] if len(b) >= 3 else 0.0)) * float(max(0.0, b[3] if len(b) >= 4 else 0.0))
    ranked = sorted(lines, key=_area, reverse=True)
    out = []
    for idx, l in enumerate(ranked[:max_regions]):
        box = l.get("box") or [0, 0, 0, 0]
        crop = _crop_rgb(arr, box)
        if crop is None or crop.size == 0:
            continue
        out.append({
            "id": f"line_{idx+1}",
            "type": "line",
            "text": l.get("text", ""),
            "score": float(l.get("score", 0.0)),
            "bbox": [float(box[0]), float(box[1]), float(box[2]), float(box[3])],
            "preview": _to_data_url(crop, quality=90),
        })
    return out


def _full_page_preview(arr: np.ndarray):
    h, w = arr.shape[:2]
    target_w = 900
    if w <= target_w:
        small = arr
    else:
        scale = target_w / float(max(1, w))
        nh = max(1, int(round(h * scale)))
        nw = max(1, int(round(w * scale)))
        if cv2 is not None:
            small = cv2.resize(arr, (nw, nh), interpolation=cv2.INTER_AREA)
        else:
            small = np.array(Image.fromarray(arr).resize((nw, nh), Image.Resampling.BICUBIC))
    return _to_data_url(small, quality=78)


def _factor_region_map(arr: np.ndarray, regions):
    # Keep captions aligned to the current 20-factor language while letting
    # backend vision provide the concrete evidence crop.
    labels = {
        1: "letter formation evidence from detected writing",
        2: "stroke sequence proxy from detected word region",
        3: "loop/closure evidence from rounded letter region",
        4: "stroke smoothness evidence from local letter region",
        5: "size consistency evidence from representative line",
        6: "ascender/descender zone evidence",
        7: "baseline alignment evidence from line crop",
        8: "word spacing evidence",
        9: "letter spacing evidence",
        10: "margin consistency evidence",
        11: "line straightness evidence",
        12: "vertical alignment evidence",
        13: "speed factor context from writing region",
        14: "pressure factor context from writing region",
        15: "stroke continuity context",
        16: "pen-lift context",
        17: "slant consistency evidence",
        18: "overall legibility evidence",
        19: "character distinction evidence",
        20: "overall neatness evidence",
    }
    fallback = _full_page_preview(arr)
    seq = regions if regions else []

    if not seq:
        return {
            str(n): {"url": fallback, "caption": labels.get(n, "factor evidence")}
            for n in range(1, 21)
        }

    feats = []
    for i, r in enumerate(seq):
        b = r.get("bbox") or [0.0, 0.0, 0.0, 0.0]
        x, y, w, h = [float(v) for v in b]
        txt = str(r.get("text", "") or "")
        sc = float(r.get("score", 0.0) or 0.0)
        area = max(1.0, w * h)
        feats.append({
            "i": i,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "area": area,
            "aspect": (w / max(1.0, h)),
            "score": sc,
            "text": txt,
            "text_len": len(txt),
            "space_count": txt.count(" "),
            "digit_ratio": (len(re.findall(r"\d", txt)) / max(1, len(txt))) if txt else 0.0,
            "preview": r.get("preview", ""),
        })

    mean_area = float(np.mean([f["area"] for f in feats])) if feats else 1.0
    mean_h = float(np.mean([f["h"] for f in feats])) if feats else 1.0

    def pick(pred=None, key=None, reverse=True, default_idx=0):
        pool = feats
        if pred is not None:
            pool = [f for f in feats if pred(f)]
        if not pool:
            pool = feats
        if not pool:
            return default_idx
        if key is None:
            return pool[0]["i"]
        pool.sort(key=key, reverse=reverse)
        return pool[0]["i"]

    # Factor-specific picks (heuristic, deterministic):
    # Compact regions tend to represent single letters/short glyph clusters.
    compact = lambda f: f["area"] <= mean_area * 0.85 and f["h"] <= mean_h * 1.15
    longline = lambda f: f["aspect"] >= 5.0 or f["text_len"] >= 16
    spaced = lambda f: f["space_count"] >= 2
    wordish = lambda f: f["space_count"] == 0 and f["text_len"] >= 4

    picks = {
        1: pick(compact, key=lambda f: (f["score"], -f["digit_ratio"])),
        2: pick(longline, key=lambda f: (f["text_len"], f["score"])),
        3: pick(compact, key=lambda f: (f["h"], f["score"])),
        4: pick(compact, key=lambda f: (f["score"], -f["aspect"])),
        5: pick(None, key=lambda f: (f["h"], f["score"])),
        6: pick(None, key=lambda f: (f["h"], f["text_len"])),
        7: pick(None, key=lambda f: (f["w"], f["score"])),
        8: pick(spaced, key=lambda f: (f["space_count"], f["w"])),
        9: pick(wordish, key=lambda f: (-abs(f["text_len"] - 7), f["score"])),
        10: pick(None, key=lambda f: -f["x"], reverse=True),  # left margin evidence
        11: pick(None, key=lambda f: (f["w"], f["score"])),
        12: pick(None, key=lambda f: (f["h"], -f["w"], f["score"])),
        13: pick(None, key=lambda f: (f["score"], f["text_len"])),
        14: pick(None, key=lambda f: (f["h"], f["score"])),
        15: pick(longline, key=lambda f: (f["text_len"], f["score"])),
        16: pick(longline, key=lambda f: (f["text_len"], f["score"])),
        17: pick(None, key=lambda f: (f["aspect"], f["text_len"])),
        18: None,  # whole-page readability
        19: pick(compact, key=lambda f: (f["score"], -f["digit_ratio"])),
        20: None,  # whole-page neatness
    }

    out = {}
    for n in range(1, 21):
        idx = picks.get(n)
        if idx is None:
            url = fallback
        else:
            region = seq[int(max(0, min(idx, len(seq) - 1)))]
            url = region.get("preview", fallback)
        out[str(n)] = {
            "url": url,
            "caption": labels.get(n, "factor evidence"),
        }
    return out


def _layout_features(arr: np.ndarray):
    h, w = arr.shape[:2]
    if h <= 1 or w <= 1:
        return {"line_density": 0.0, "block_density": 0.0, "layout_complexity": 0.0, "cc_count": 0}

    if cv2 is None:
        # Fallback without OpenCV: use simple luminance threshold.
        gray = np.dot(arr[..., :3], [0.299, 0.587, 0.114]).astype(np.float32)
        thr = float(np.mean(gray) - 15.0)
        ink = (gray < thr).astype(np.uint8)
        row_frac = ink.mean(axis=1)
        line_density = float(np.mean(row_frac > max(0.01, np.percentile(row_frac, 70))))
        block_density = float(np.mean(ink))
        return {
            "line_density": line_density,
            "block_density": block_density,
            "layout_complexity": float(min(1.0, (line_density * 0.65 + block_density * 1.4))),
            "cc_count": int(max(1, line_density * h * 0.6)),
        }

    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    thr = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 9
    )

    row_frac = (thr > 0).mean(axis=1)
    line_density = float(np.mean(row_frac > max(0.01, np.percentile(row_frac, 70))))
    block_density = float(np.mean(thr > 0))

    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(thr, connectivity=8)
    areas = stats[1:, cv2.CC_STAT_AREA] if num_labels > 1 else np.array([], dtype=np.int32)
    valid = areas[(areas >= 12) & (areas <= max(18, int(h * w * 0.04)))]
    cc_count = int(valid.size)

    complexity = float(
        min(1.0, (0.45 * line_density) + (1.15 * block_density) + (0.00045 * cc_count))
    )

    return {
        "line_density": line_density,
        "block_density": block_density,
        "layout_complexity": complexity,
        "cc_count": cc_count,
    }


def _infer_doc_context(lines, layout):
    n_lines = len(lines)
    texts = [str(l.get("text", "")).strip() for l in lines if str(l.get("text", "")).strip()]
    full = " ".join(texts)
    avg_len = (sum(len(t) for t in texts) / len(texts)) if texts else 0.0
    digits_ratio = 0.0
    if full:
        digits_ratio = len(re.findall(r"\d", full)) / max(1, len(full))

    has_salutation = bool(re.search(r"\b(dear|respected|sir|madam)\b", full, re.IGNORECASE))
    has_signoff = bool(re.search(r"\b(thanks|regards|sincerely|yours)\b", full, re.IGNORECASE))
    has_form_fields = bool(re.search(r"\b(name|date|address|phone|dob|id)\b\s*[:\-]", full, re.IGNORECASE))

    doc_type = "personal_note"
    conf = 0.62
    purpose = "free writing"
    audience = "general"

    if has_form_fields or digits_ratio > 0.24:
        doc_type = "application_form"
        conf = 0.78
        purpose = "structured data entry"
        audience = "institution"
    elif has_salutation or has_signoff:
        doc_type = "formal_letter"
        conf = 0.76
        purpose = "written communication"
        audience = "specific recipient"
    elif n_lines >= 10 and avg_len > 16 and layout.get("layout_complexity", 0.0) > 0.42:
        doc_type = "academic_paper"
        conf = 0.68
        purpose = "long-form explanation"
        audience = "reviewer/reader"
    elif n_lines <= 2 and avg_len < 14:
        doc_type = "signature"
        conf = 0.64
        purpose = "identity mark"
        audience = "verification"

    urgency = []
    if "!" in full:
        urgency.append("exclamation marks")
    if re.search(r"\b(urgent|asap|immediately)\b", full, re.IGNORECASE):
        urgency.append("urgent vocabulary")

    formality = 0.55
    if has_salutation or has_signoff:
        formality += 0.2
    if re.search(r"\bpls\b|\bthx\b|\bu\b", full, re.IGNORECASE):
        formality -= 0.18
    formality = float(max(0.0, min(1.0, formality)))

    coherence = 0.35
    if n_lines >= 3:
        coherence += 0.25
    if avg_len >= 18:
        coherence += 0.20
    coherence = float(max(0.0, min(1.0, coherence)))

    return {
        "document_type": {"type": doc_type, "confidence": conf},
        "purpose": purpose,
        "intended_audience": audience,
        "emotional_tone": "neutral",
        "formality_level": formality,
        "urgency_indicators": urgency,
        "content_coherence": coherence,
        "sections": [
            {"name": "header", "present": bool(n_lines >= 1)},
            {"name": "body", "present": bool(n_lines >= 2)},
            {"name": "closing", "present": has_signoff},
        ],
    }


def _vl_analyze(arr: np.ndarray, lines):
    layout = _layout_features(arr)
    context = _infer_doc_context(lines, layout)
    regions = _build_region_previews(arr, lines)
    factor_regions = _factor_region_map(arr, regions)
    return {
        "document_context": context,
        "layout": layout,
        "regions": regions,
        "factor_regions": factor_regions,
    }


_SECTIONS = [
    {"id": "structure", "name": "Structure", "weight": 0.30, "blurb": "Letter shapes, size & control"},
    {"id": "spatial", "name": "Spatial", "weight": 0.30, "blurb": "Spacing, baseline & layout"},
    {"id": "dynamics", "name": "Dynamics", "weight": 0.20, "blurb": "Speed, pressure & flow"},
    {"id": "style", "name": "Style & Readability", "weight": 0.20, "blurb": "Slant, legibility & neatness"},
]

_FACTOR_META = {
    1: ("structure", "Letter Formation Accuracy", "shape regularity proxy"),
    2: ("structure", "Stroke Order Consistency", "stroke order proxy"),
    3: ("structure", "Loop Closure", "loop-bearing character consistency"),
    4: ("structure", "Line Quality (Smoothness)", "stroke smoothness proxy"),
    5: ("structure", "Size Consistency", "letter-height consistency"),
    6: ("structure", "Ascender / Descender Control", "zone balance"),
    7: ("spatial", "Baseline Alignment", "baseline drift"),
    8: ("spatial", "Word Spacing", "inter-word spacing regularity"),
    9: ("spatial", "Letter Spacing", "intra-word spacing proxy"),
    10: ("spatial", "Margin Discipline", "left margin consistency"),
    11: ("spatial", "Line Straightness", "line slope stability"),
    12: ("spatial", "Vertical Alignment", "stroke tilt stability"),
    13: ("dynamics", "Speed Consistency", "speed proxy from stroke regularity"),
    14: ("dynamics", "Pressure Consistency", "pressure proxy from ink variance"),
    15: ("dynamics", "Stroke Continuity", "continuity proxy from word morphology"),
    16: ("dynamics", "Pen Lift Frequency", "pen-lift proxy from segmentation"),
    17: ("style", "Slant Consistency", "slant variation"),
    18: ("style", "Legibility Score", "composite readability"),
    19: ("style", "Character Distinction", "character separability proxy"),
    20: ("style", "Overall Neatness", "layout neatness composite"),
}


def _mean(xs):
    vals = [float(x) for x in xs if x is not None and np.isfinite(float(x))]
    if not vals:
        return 0.0
    return float(sum(vals) / len(vals))


def _std(xs):
    vals = [float(x) for x in xs if x is not None and np.isfinite(float(x))]
    if len(vals) < 2:
        return 0.0
    m = _mean(vals)
    v = sum((x - m) ** 2 for x in vals) / max(1, len(vals) - 1)
    return float(math.sqrt(max(0.0, v)))


def _cv(xs):
    m = _mean(xs)
    if m <= 1e-9:
        return 0.0
    return float(_std(xs) / m)


def _clamp10(v):
    return float(max(0.0, min(10.0, v)))


def _band(score):
    if score >= 7.5:
        return "strong"
    if score >= 5.0:
        return "dev"
    return "focus"


def _group_lines_by_rows(lines):
    if not lines:
        return []
    hs = [max(1.0, float((l.get("box") or [0, 0, 0, 0])[3])) for l in lines]
    row_thr = max(14.0, _mean(hs) * 0.75)
    ordered = sorted(lines, key=lambda l: float((l.get("box") or [0, 0, 0, 0])[1]))
    rows = []
    for l in ordered:
        b = l.get("box") or [0, 0, 0, 0]
        y = float(b[1])
        h = float(max(1.0, b[3]))
        cy = y + (h * 0.5)
        if not rows:
            rows.append({"cy": cy, "items": [l]})
            continue
        if abs(cy - rows[-1]["cy"]) <= row_thr:
            rows[-1]["items"].append(l)
            rows[-1]["cy"] = _mean([float((x.get("box") or [0, 0, 0, 0])[1]) + float(max(1.0, (x.get("box") or [0, 0, 0, 0])[3])) * 0.5 for x in rows[-1]["items"]])
        else:
            rows.append({"cy": cy, "items": [l]})
    for r in rows:
        r["items"].sort(key=lambda x: float((x.get("box") or [0, 0, 0, 0])[0]))
    return rows


def _extract_features(arr: np.ndarray, lines, layout):
    h, w = arr.shape[:2]
    boxes = [l.get("box") or [0, 0, 0, 0] for l in lines]
    widths = [float(max(1.0, b[2])) for b in boxes]
    heights = [float(max(1.0, b[3])) for b in boxes]
    lefts = [float(b[0]) / max(1.0, float(w)) for b in boxes]
    scores = [float(l.get("score", 0.0)) for l in lines]
    texts = [str(l.get("text", "") or "") for l in lines]
    n_lines = len(lines)

    n_words = sum(len(re.findall(r"\S+", t)) for t in texts)
    n_chars = sum(len(re.sub(r"\s+", "", t)) for t in texts)
    char_w = [widths[i] / max(1, len(re.sub(r"\s+", "", texts[i]))) for i in range(n_lines)] if n_lines else []

    y_centers = [float(b[1] + b[3] * 0.5) / max(1.0, float(h)) for b in boxes]
    line_spacing = []
    if len(y_centers) >= 2:
        ys = sorted(y_centers)
        line_spacing = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)]

    slopes = []
    for l in lines:
        poly = l.get("poly") or []
        if len(poly) >= 2:
            x0, y0 = float(poly[0][0]), float(poly[0][1])
            x1, y1 = float(poly[1][0]), float(poly[1][1])
            dx = max(1e-6, x1 - x0)
            slopes.append(abs(math.degrees(math.atan2(y1 - y0, dx))))
        else:
            slopes.append(0.0)

    rows = _group_lines_by_rows(lines)
    word_gaps = []
    for r in rows:
        items = r.get("items", [])
        if len(items) < 2:
            continue
        row_h = _mean([float(max(1.0, (it.get("box") or [0, 0, 0, 0])[3])) for it in items])
        for i in range(len(items) - 1):
            b1 = items[i].get("box") or [0, 0, 0, 0]
            b2 = items[i + 1].get("box") or [0, 0, 0, 0]
            gap = float(b2[0] - (b1[0] + b1[2]))
            word_gaps.append(max(0.0, gap) / max(1.0, row_h))

    full = " ".join(texts)
    digits_ratio = len(re.findall(r"\d", full)) / max(1, len(full)) if full else 0.0
    loop_chars = len(re.findall(r"[aodpegqAODPEGQ]", full))
    alpha_chars = len(re.findall(r"[A-Za-z]", full))
    loop_ratio = (loop_chars / max(1, alpha_chars)) if alpha_chars else 0.0
    tall_chars = len(re.findall(r"[bdfhkltgjpqy]", full))
    tall_ratio = (tall_chars / max(1, alpha_chars)) if alpha_chars else 0.0

    ink_cv = 0.0
    if cv2 is not None:
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        vals = []
        for b in boxes[:80]:
            x, y, bw, bh = [int(round(v)) for v in b]
            x0 = max(0, x)
            y0 = max(0, y)
            x1 = min(w, x + max(1, bw))
            y1 = min(h, y + max(1, bh))
            if x1 <= x0 or y1 <= y0:
                continue
            patch = gray[y0:y1, x0:x1]
            if patch.size:
                vals.append(float(np.std(patch.astype(np.float32))))
        ink_cv = _cv(vals) if vals else 0.0

    return {
        "n_lines": n_lines,
        "n_words": n_words,
        "n_chars": n_chars,
        "avg_score": _mean(scores),
        "height_cv": _cv(heights),
        "width_cv": _cv(widths),
        "char_w_cv": _cv(char_w),
        "left_cv": _cv(lefts),
        "line_slope_abs": _mean(slopes),
        "line_slope_std": _std(slopes),
        "line_spacing_cv": _cv(line_spacing),
        "word_gap_cv": _cv(word_gaps),
        "digits_ratio": digits_ratio,
        "loop_ratio": loop_ratio,
        "tall_ratio": tall_ratio,
        "ink_cv": ink_cv,
        "layout_complexity": float(layout.get("layout_complexity", 0.0) or 0.0),
    }


def _score_factor_map(fx):
    s = {}
    s[1] = _clamp10((fx["avg_score"] * 7.2) + ((1.0 - min(1.0, fx["height_cv"])) * 2.8))
    s[2] = _clamp10(5.4 + (1.0 - min(1.0, fx["char_w_cv"])) * 2.6 + (fx["avg_score"] * 2.0))
    s[3] = _clamp10((min(1.0, fx["loop_ratio"] / 0.28)) * 10.0)
    s[4] = _clamp10((1.0 - min(1.0, fx["width_cv"] / 0.8)) * 10.0)
    s[5] = _clamp10((1.0 - min(1.0, fx["height_cv"] / 0.65)) * 10.0)
    s[6] = _clamp10((1.0 - min(1.0, abs(fx["tall_ratio"] - 0.34) / 0.34)) * 10.0)
    s[7] = _clamp10((1.0 - min(1.0, fx["line_slope_abs"] / 8.0)) * 10.0)
    s[8] = _clamp10((1.0 - min(1.0, fx["word_gap_cv"] / 1.4)) * 10.0)
    s[9] = _clamp10((1.0 - min(1.0, fx["char_w_cv"] / 1.2)) * 10.0)
    s[10] = _clamp10((1.0 - min(1.0, fx["left_cv"] / 0.55)) * 10.0)
    s[11] = _clamp10((1.0 - min(1.0, fx["line_slope_abs"] / 10.0)) * 10.0)
    s[12] = _clamp10((1.0 - min(1.0, fx["line_slope_std"] / 10.0)) * 10.0)
    s[13] = _clamp10((1.0 - min(1.0, fx["width_cv"] / 0.85)) * 10.0)
    s[14] = _clamp10((1.0 - min(1.0, fx["ink_cv"] / 0.95)) * 10.0)
    s[15] = _clamp10((1.0 - min(1.0, abs((fx["n_chars"] / max(1, fx["n_words"])) - 5.0) / 5.0)) * 10.0)
    s[16] = _clamp10((1.0 - min(1.0, fx["char_w_cv"] / 1.4)) * 10.0)
    s[17] = _clamp10((1.0 - min(1.0, fx["line_slope_std"] / 12.0)) * 10.0)
    s[18] = _clamp10((0.35 * s[1]) + (0.25 * s[5]) + (0.20 * s[8]) + (0.20 * s[7]))
    s[19] = _clamp10((fx["avg_score"] * 7.5) + ((1.0 - min(1.0, fx["digits_ratio"] / 0.5)) * 2.5))
    s[20] = _clamp10((0.30 * s[5]) + (0.20 * s[8]) + (0.20 * s[10]) + (0.15 * s[11]) + (0.15 * s[17]))
    return s


def _build_python_analysis(arr: np.ndarray, lines, layout):
    fx = _extract_features(arr, lines, layout)
    scores = _score_factor_map(fx)
    basis = {
        1: f"{fx['n_chars']} letters",
        2: f"{fx['n_words']} words",
        3: f"{fx['n_chars']} letters",
        4: f"{fx['n_lines']} lines",
        5: f"{fx['n_chars']} letters",
        6: f"{fx['n_chars']} letters",
        7: f"{fx['n_lines']} lines",
        8: f"{fx['n_words']} words",
        9: f"{fx['n_chars']} letters",
        10: f"{fx['n_lines']} lines",
        11: f"{fx['n_lines']} lines",
        12: f"{fx['n_lines']} lines",
        13: f"{fx['n_lines']} lines",
        14: f"{fx['n_lines']} lines",
        15: f"{fx['n_words']} words",
        16: f"{fx['n_words']} words",
        17: f"{fx['n_lines']} lines",
        18: f"{fx['n_lines']} lines",
        19: f"{fx['n_chars']} letters",
        20: f"{fx['n_lines']} lines",
    }

    results = []
    for n in range(1, 21):
        sec, name, detail = _FACTOR_META[n]
        score = round(float(scores.get(n, 0.0)), 1)
        value = f"{round(score * 10):.0f}%"
        results.append({
            "n": n,
            "sec": sec,
            "name": name,
            "target": "python-server estimate",
            "conf": "measured",
            "tip": "Practice this factor with short daily drills and rescan after 3-5 days.",
            "score": score,
            "score100": int(round(score * 10)),
            "band": _band(score),
            "value": value,
            "evidence": f"Server-side OCR/layout heuristic based on {detail}.",
            "imuMeasured": False,
            "unmeasured": False,
            "unmeasuredReason": None,
            "unmeasuredKind": None,
            "basedOn": basis.get(n),
        })

    sections = []
    for s in _SECTIONS:
        fs = [r for r in results if r["sec"] == s["id"]]
        avg = _mean([r["score"] for r in fs]) if fs else 0.0
        sections.append({
            **s,
            "avg": round(avg, 1) if fs else None,
            "avg100": int(round(avg * 10)) if fs else None,
            "factors": fs,
            "scoredCount": len(fs),
        })

    wsum = sum(float(s["weight"]) for s in sections) or 1.0
    overall = int(round(sum(float(s["avg100"] or 0) * (float(s["weight"]) / wsum) for s in sections)))
    ranked = sorted(results, key=lambda r: float(r.get("score", 0.0)))
    top_weak = ranked[:3]
    top_strong = sorted(results, key=lambda r: float(r.get("score", 0.0)), reverse=True)[:4]

    return {
        "results": results,
        "sections": sections,
        "overall": overall,
        "overallMeasured": overall,
        "measuredCount": len(results),
        "topWeak": top_weak,
        "topStrong": top_strong,
        "source": "python",
    }


@app.get("/health")
def health():
    # Probe every registered engine without crashing if its deps are missing.
    backends = {}
    for name, (ok, reason) in ocr_backends.available_backends().items():
        backends[name] = {"ready": bool(ok), "reason": reason}
    return {
        "ok": True,
        "engine": "pp-ocrv5",
        "ocr_backend": OCR_BACKEND,
        "active_backend": OCR_BACKEND,
        "backends": backends,
        "gpu": USE_GPU,
        "langs": OCR_LANGS,
        "variants": MAX_VARIANTS,
        "ocr_version": OCR_VERSION,
        "det_model": DET_MODEL_NAME,
        "rec_model_map": REC_MODEL_MAP,
        "det_limit_side_len": TEXT_DET_LIMIT_SIDE_LEN,
        "printed_threshold": classify.PRINTED_THRESHOLD,
    }


@app.post("/ocr")
async def ocr(
    image: UploadFile = File(...),
    lang: str = Form("auto"),
    det: str = Form("true"),
    rec: str = Form("true"),
):
    t0 = time.perf_counter()
    raw = await image.read()
    ckey = _cache_key("ocr", raw, lang, f"det={det}|rec={rec}|backend={OCR_BACKEND}|chandra={CHANDRA_METHOD}")
    cached = _cache_get(ckey)
    if cached is not None:
        return _with_meta(cached, "hit", t0)

    arr = _to_numpy(raw)
    last_err = ""
    selected_backend = "paddle"
    compare_meta = {}
    try:
        raw_lines, last_err, selected_backend, compare_meta = _collect_lines(arr, lang)
        lines, hand_lines = _extract_hand_lines(arr, raw_lines, raw_bytes=raw, refine_backend=selected_backend)
        texts = [l["text"] for l in hand_lines]
        polys = [l["poly"] for l in hand_lines]
        scores = [float(l["score"]) for l in hand_lines]
        rec_langs = [l["lang"] for l in hand_lines]
        printed_hints = [bool(l["printed_hint"]) for l in hand_lines]
    except Exception as e:  # never 500 the client — let it fall back to on-device
        return JSONResponse(
            status_code=200,
            content={"rec_texts": [], "rec_polys": [], "rec_scores": [],
                     "full_text": "", "engine": "pp-ocrv5", "lang": lang, "error": str(e)},
        )

    if not texts and last_err:
        return JSONResponse(
            status_code=200,
            content={"rec_texts": [], "rec_polys": [], "rec_scores": [],
                     "full_text": "", "engine": "pp-ocrv5", "lang": lang, "error": last_err},
        )

    payload = {
        "rec_texts": texts,
        "rec_polys": polys,
        "rec_scores": scores,
        "rec_langs": rec_langs,
        "printed_hints": printed_hints,
        "hand_lines": hand_lines,
        "all_lines": lines,
        "full_text": "\n".join(texts),
        "proc_w": int(arr.shape[1]),
        "proc_h": int(arr.shape[0]),
        "engine": f"pp-ocrv5+{selected_backend}",
        "selected_backend": selected_backend,
        "backend_compare": compare_meta,
        "lang": lang,
        "langs": _resolve_langs(lang),
    }
    _cache_set(ckey, payload)
    return _with_meta(payload, "miss", t0)


@app.post("/analyze-vl")
async def analyze_vl(
    image: UploadFile = File(...),
    lang: str = Form("auto"),
):
    t0 = time.perf_counter()
    raw = await image.read()
    ckey = _cache_key("analyze-vl", raw, lang, f"backend={OCR_BACKEND}|chandra={CHANDRA_METHOD}")
    cached = _cache_get(ckey)
    if cached is not None:
        return _with_meta(cached, "hit", t0)

    arr = _to_numpy(raw)
    last_err = ""
    selected_backend = "paddle"
    compare_meta = {}
    try:
        raw_lines, last_err, selected_backend, compare_meta = _collect_lines(arr, lang)
        lines, hand_lines = _extract_hand_lines(arr, raw_lines, raw_bytes=raw, refine_backend=selected_backend)
        texts = [l["text"] for l in hand_lines]
        polys = [l["poly"] for l in hand_lines]
        scores = [float(l["score"]) for l in hand_lines]
        rec_langs = [l["lang"] for l in hand_lines]
        printed_hints = [bool(l["printed_hint"]) for l in hand_lines]

        vl = _vl_analyze(arr, hand_lines)
    except Exception as e:
        return JSONResponse(
            status_code=200,
            content={
                "ok": False,
                "engine": "pp-ocrv5+vl",
                "error": str(e),
                "rec_texts": [],
                "rec_polys": [],
                "rec_scores": [],
                "full_text": "",
                "document_context": {},
                "layout": {},
                "regions": [],
                "factor_regions": {},
            },
        )

    if not texts and last_err:
        return JSONResponse(
            status_code=200,
            content={
                "ok": False,
                "engine": "pp-ocrv5+vl",
                "error": last_err,
                "rec_texts": [],
                "rec_polys": [],
                "rec_scores": [],
                "full_text": "",
                "document_context": {},
                "layout": {},
                "regions": [],
                "factor_regions": {},
            },
        )

    payload = {
        "ok": True,
        "engine": f"pp-ocrv5+opencv-context+{selected_backend}",
        "selected_backend": selected_backend,
        "backend_compare": compare_meta,
        "lang": lang,
        "langs": _resolve_langs(lang),
        "rec_texts": texts,
        "rec_polys": polys,
        "rec_scores": scores,
        "rec_langs": rec_langs,
        "printed_hints": printed_hints,
        "hand_lines": hand_lines,
        "all_lines": lines,
        "full_text": "\n".join(texts),
        "proc_w": int(arr.shape[1]),
        "proc_h": int(arr.shape[0]),
        "document_context": vl.get("document_context", {}),
        "layout": vl.get("layout", {}),
        "regions": vl.get("regions", []),
        "factor_regions": vl.get("factor_regions", {}),
    }
    _cache_set(ckey, payload)
    return _with_meta(payload, "miss", t0)


@app.post("/report-python")
async def report_python(
    image: UploadFile = File(...),
    lang: str = Form("auto"),
    expected_text: str = Form(""),
):
    t0 = time.perf_counter()
    raw = await image.read()
    ckey = _cache_key("report-python", raw, lang, f"{expected_text or ''}|backend={OCR_BACKEND}|chandra={CHANDRA_METHOD}")
    cached = _cache_get(ckey)
    if cached is not None:
        return _with_meta(cached, "hit", t0)

    arr = _to_numpy(raw)
    last_err = ""
    selected_backend = "paddle"
    compare_meta = {}
    try:
        raw_lines, last_err, selected_backend, compare_meta = _collect_lines(arr, lang)
        lines, hand_lines = _extract_hand_lines(arr, raw_lines, raw_bytes=raw, refine_backend=selected_backend)
        # Reference-passage alignment: if the writer copied a known passage,
        # correct the recognised text against it (consistent, dependable reading).
        align_info = _align_to_expected(hand_lines, expected_text)
        texts = [l["text"] for l in hand_lines]
        polys = [l["poly"] for l in hand_lines]
        scores = [float(l["score"]) for l in hand_lines]
        rec_langs = [l["lang"] for l in hand_lines]
        printed_hints = [bool(l["printed_hint"]) for l in hand_lines]

        vl = _vl_analyze(arr, hand_lines)
        analysis = _build_python_analysis(arr, hand_lines, vl.get("layout", {}))
    except Exception as e:
        return JSONResponse(
            status_code=200,
            content={
                "ok": False,
                "engine": "pp-ocrv5+python-report",
                "error": str(e),
                "analysis": None,
                "rec_texts": [],
                "rec_polys": [],
                "rec_scores": [],
                "full_text": "",
                "document_context": {},
                "layout": {},
                "regions": [],
                "factor_regions": {},
            },
        )

    if not texts and last_err:
        return JSONResponse(
            status_code=200,
            content={
                "ok": False,
                "engine": "pp-ocrv5+python-report",
                "error": last_err,
                "analysis": None,
                "rec_texts": [],
                "rec_polys": [],
                "rec_scores": [],
                "full_text": "",
                "document_context": {},
                "layout": {},
                "regions": [],
                "factor_regions": {},
            },
        )

    # Recognition transparency: which engine read the page, how many handwriting
    # vs printed lines were found, and the mean recognition confidence. Lets the
    # report show an honest accuracy/confidence indicator instead of implying a
    # certainty the engine doesn't have.
    if isinstance(analysis, dict):
        hand_conf = _mean([float(l.get("score", 0.0)) for l in hand_lines])
        reliable_lines = int(sum(1 for l in hand_lines if float(l.get("score", 0.0) or 0.0) >= 0.85))
        passage_aligned = bool(align_info and align_info.get("aligned"))
        # Trust level the report should display. With a matched reference passage
        # recognition is dependable; otherwise it is honestly "assistive" and the
        # report must make clear the 20 factors do NOT depend on it.
        if passage_aligned:
            level = "passage-verified"
        elif hand_conf >= 0.85:
            level = "high"
        elif hand_conf >= 0.70:
            level = "moderate"
        else:
            level = "low"
        analysis["recognition"] = {
            "backend": selected_backend,
            "hand_lines": len(hand_lines),
            "printed_lines": int(sum(1 for l in lines if l.get("printed_hint"))),
            "reliable_lines": reliable_lines,
            "mean_confidence": round(hand_conf, 3),
            "confidence_pct": int(round(hand_conf * 100)),
            "level": level,
            "assistive_only": not passage_aligned,
            "passage_aligned": passage_aligned,
            "passage_match": (align_info or {}).get("passage_match"),
            "note": "The 20 factors are measured from the geometry of the writing and do not depend on reading the words.",
        }

    payload = {
        "ok": True,
        "engine": f"pp-ocrv5+python-report+{selected_backend}",
        "selected_backend": selected_backend,
        "backend_compare": compare_meta,
        "lang": lang,
        "langs": _resolve_langs(lang),
        "expected_text": expected_text or "",
        "passage": align_info,
        "analysis": analysis,
        "rec_texts": texts,
        "rec_polys": polys,
        "rec_scores": scores,
        "rec_langs": rec_langs,
        "printed_hints": printed_hints,
        "hand_lines": hand_lines,
        "all_lines": lines,
        "full_text": "\n".join(texts),
        "proc_w": int(arr.shape[1]),
        "proc_h": int(arr.shape[0]),
        "document_context": vl.get("document_context", {}),
        "layout": vl.get("layout", {}),
        "regions": vl.get("regions", []),
        "factor_regions": vl.get("factor_regions", {}),
    }
    _cache_set(ckey, payload)
    return _with_meta(payload, "miss", t0)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8868")))
