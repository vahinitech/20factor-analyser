# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies. Server-side handwriting/print recognition.
# Third-party: PaddleOCR (Apache-2.0). See /THIRD-PARTY-NOTICES.md and backend/README.md
#
# ppocr-server.py — PP-OCRv5 recognition microservice for the Vahini analyser.
#
# Filename is intentionally hyphenated; it is loaded by file path via
# importlib (see analyser-ocr-server.py and the tests), never
# `import ppocr_server`, so the hyphen is harmless. Only the module-name
# check is silenced here; re-enabled immediately for the rest of the file.
# pylint: disable=invalid-name
# pylint: enable=invalid-name
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

import os
import sys
import time
import threading

# This module is sometimes loaded by file path (analyser-ocr-server.py uses
# importlib), which does NOT put its own folder on sys.path. Add it so the
# sibling helper modules (ocr_backends, classify) always import cleanly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # server-wide settings, parsed once from the environment
import cache  # response cache (TTL + max-item eviction) for the endpoints
import ocr_backends  # pluggable engine adapters (paddle/trocr/surya)
import classify  # printed-vs-handwriting classifier
import computer_vision  # image decode/crop/preview + layout/doc-context
import scoring  # the 20-factor model (FactorScore/SectionScore/AnalysisResult)
import recognizer  # dispatches + post-processes recognition across backends
import layout_filter  # negative pre-filter using PaddleOCR's layout model
from gpu_detect import gpu_zero_caveat, nvidia_gpu_present

# Paddle 3.x on some CPUs can fail in oneDNN/PIR execution paths for OCR.
# Prefer the stable execution route unless explicitly overridden.
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
import numpy as np

# PaddleOCR 3.x (PP-OCRv5) is imported LAZILY inside get_engine() so this module
# loads even when paddle isn't installed (e.g. a non-paddle backend, or tests).
# pip install paddleocr paddlepaddle  (see requirements.txt)

app = FastAPI(title="Vahini PP-OCRv5 service", version="1.0")

# Every VAHINI_OCR_* env var is parsed once in config.py; these module-level
# names are thin aliases so the rest of this file (and the tests, which
# patch several of them directly) keep their existing short names.
SETTINGS = config.SETTINGS
USE_GPU = SETTINGS.use_gpu
OCR_LANGS = SETTINGS.ocr_langs
OCR_BACKEND = SETTINGS.ocr_backend
MAX_VARIANTS = SETTINGS.max_variants
ADV_PREPROC = SETTINGS.adv_preproc
USE_DOC_ORIENTATION = SETTINGS.use_doc_orientation
USE_DOC_UNWARP = SETTINGS.use_doc_unwarping
USE_TEXTLINE_ORIENTATION = SETTINGS.use_textline_orientation
MAX_OCR_SIDE = SETTINGS.max_ocr_side
OCR_VERSION = SETTINGS.ocr_version
DET_MODEL_NAME = SETTINGS.det_model_name
REC_MODEL_MAP_RAW = SETTINGS.rec_model_map_raw
REC_MODEL_MAP = SETTINGS.rec_model_map
TEXT_DET_LIMIT_SIDE_LEN = SETTINGS.text_det_limit_side_len
TEXT_REC_SCORE_THRESH = SETTINGS.text_rec_score_thresh
AUTO_MIN_LINES = SETTINGS.auto_min_lines
VARIANT_MIN_LINES = SETTINGS.variant_min_lines
RESP_CACHE_TTL_SEC = SETTINGS.resp_cache_ttl_sec
RESP_CACHE_MAX_ITEMS = SETTINGS.resp_cache_max_items
ALLOWED_ORIGINS = SETTINGS.allowed_origins

# Allow the Vahini site to call this from the browser. Lock this down in prod to
# your exact origin(s) instead of "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

cache.configure(ttl_sec=RESP_CACHE_TTL_SEC, max_items=RESP_CACHE_MAX_ITEMS)
_cache_key = cache.cache_key
_cache_get = cache.cache_get
_cache_set = cache.cache_set
_with_meta = cache.with_meta


@app.on_event("startup")
def _warm_startup_engines():
    # Warm EVERY configured language (both the normal and the safe engine) at
    # startup so the FIRST real request isn't slowed by model download/init —
    # which previously pushed the first /report-python past the reverse-proxy
    # read timeout. Only paddle is warmed here; other backends warm on demand.
    # Runs in a background thread: on an offline/blocked network the model
    # download can take minutes to fail, and the server must still answer
    # /health and scans (via the CV fallback) while it warms.
    if os.environ.get("VAHINI_OCR_PRELOAD_ON_START", "1") != "1":
        return

    def _warm():
        for lg in OCR_LANGS or ["en"]:
            try:
                ocr_backends.get_engine(lg)
                ocr_backends.get_engine_safe(lg)
            except Exception:
                pass

    threading.Thread(
        target=_warm, name="vahini-engine-warmup", daemon=True
    ).start()


# decode_image/_pdf_first_page/to_numpy now live in computer_vision.py.
# Thin aliases here keep the rest of this file (and callers that still refer
# to these by their historical short names) unchanged.
_decode_image = computer_vision.decode_image


def _to_numpy(raw: bytes) -> np.ndarray:
    return computer_vision.to_numpy(raw, max_side=MAX_OCR_SIDE)


# _resolve_langs/_collect_lines_paddle/_backend_recognize/_collect_lines/
# _refine_handwriting_text/_extract_hand_lines/_align_to_expected now live
# in recognizer.py as resolve_langs()/collect_lines_paddle()/
# backend_recognize()/collect_lines()/refine_handwriting_text()/
# extract_hand_lines()/align_to_expected(), configured once via
# recognizer.configure() below.
recognizer.configure(
    ocr_langs=OCR_LANGS,
    ocr_backend=OCR_BACKEND,
    max_variants=MAX_VARIANTS,
    adv_preproc=ADV_PREPROC,
    auto_min_lines=AUTO_MIN_LINES,
    variant_min_lines=VARIANT_MIN_LINES,
    refine_min_sim=SETTINGS.refine_min_sim,
    refine_min_conf=SETTINGS.refine_min_conf,
)
ocr_backends.init_registry(
    resolve_langs=recognizer.resolve_langs,
    paddle_config={
        "use_gpu": USE_GPU,
        "ocr_version": OCR_VERSION,
        "det_model_name": DET_MODEL_NAME,
        "rec_model_map": REC_MODEL_MAP,
        "text_det_limit_side_len": TEXT_DET_LIMIT_SIDE_LEN,
        "text_rec_score_thresh": TEXT_REC_SCORE_THRESH,
        "use_doc_orientation": USE_DOC_ORIENTATION,
        "use_doc_unwarping": USE_DOC_UNWARP,
        "use_textline_orientation": USE_TEXTLINE_ORIENTATION,
        "max_variants": MAX_VARIANTS,
        "adv_preproc": ADV_PREPROC,
    },
)


# _to_data_url/_crop_rgb/_build_region_previews/_full_page_preview/
# _factor_region_map/_layout_features/_infer_doc_context/vl_analyze now
# live in computer_vision.py. This module only needs vl_analyze.
_vl_analyze = computer_vision.vl_analyze


# _SECTIONS/_FACTOR_META/_FACTOR_EXTRAS/_mean/_std/_cv/_clamp10/_band/
# _group_lines_by_rows/_extract_features/_score_factor_map/
# _build_python_analysis now live in scoring.py as the FactorScore/
# SectionScore/AnalysisResult dataclasses + build_analysis().


@app.get("/health")
def health():
    # Probe every registered engine without crashing if its deps are missing.
    backends = {}
    for name, (ok, reason) in ocr_backends.available_backends().items():
        backends[name] = {"ready": bool(ok), "reason": reason}
    gpu_present = nvidia_gpu_present()
    return {
        "ok": True,
        "engine": "pp-ocrv5",
        "ocr_backend": OCR_BACKEND,
        "active_backend": OCR_BACKEND,
        "backends": backends,
        "gpu": USE_GPU,
        "gpu_detected": gpu_present,
        "gpu_note": None if gpu_present else gpu_zero_caveat(),
        "langs": OCR_LANGS,
        "variants": MAX_VARIANTS,
        "ocr_version": OCR_VERSION,
        "det_model": DET_MODEL_NAME,
        "rec_model_map": REC_MODEL_MAP,
        "det_limit_side_len": TEXT_DET_LIMIT_SIDE_LEN,
        "printed_threshold": classify.PRINTED_THRESHOLD,
        # Real, measured per-engine speed on THIS machine, not a synthetic
        # benchmark: hybrid mode's trocr/surya refine calls (see
        # recognizer.refine_handwriting_text) and the layout pre-filter's
        # PP-DocLayout-M/S tier choice (see layout_filter.py) both record
        # here. Empty until the first relevant call has actually run.
        "adaptive_engine_speed": ocr_backends.engine_speed_snapshot(),
        # Whether a layout model is built and ready yet (see layout_filter.py
        # — the build never blocks a request, so this can be empty for a
        # while after startup even with VAHINI_LAYOUT_FILTER=1).
        "layout_filter": {
            "enabled": layout_filter.is_enabled(),
            "built_tiers": layout_filter.built_tiers(),
        },
    }


def _no_handwriting_payload(engine, lang, lines, extra=None):
    """Refusal payload for a page where text was detected but ALL of it is
    printed. The analyser's rule of thumb: printed text is never analysed,
    never scored, never shown as evidence. Scoring a printed page would be
    fabrication, so the honest answer is a clear refusal the app can show."""
    printed = int(sum(1 for l in lines if l.get("printed_hint")))
    payload = {
        "ok": False,
        "engine": engine,
        "error_code": "no_handwriting",
        "error": (
            "No handwriting found on this page. It looks fully printed "
            f"({printed} printed line{'s' if printed != 1 else ''} "
            "detected). This analyser measures pen handwriting only; "
            "printed text is always excluded from the analysis."
        ),
        "printed_lines": printed,
        "rec_texts": [],
        "rec_polys": [],
        "rec_scores": [],
        "full_text": "",
        "lang": lang,
    }
    if extra:
        payload.update(extra)
    return payload


def _ocr_process(arr, raw, lang):
    """Synchronous body of /ocr. Run off the event loop via
    run_in_threadpool so one slow analysis (10-30s of CPU work) doesn't
    block other requests (other users, cache hits, /health) while it
    runs; see the endpoint below."""
    last_err = ""
    selected_backend = "paddle"
    compare_meta = {}
    try:
        raw_lines, last_err, selected_backend, compare_meta = (
            recognizer.collect_lines(arr, lang)
        )
        lines, hand_lines = recognizer.extract_hand_lines(
            arr, raw_lines, raw_bytes=raw, refine_backend=selected_backend
        )
        if lines and not hand_lines:
            # Text was detected but every line is printed: refuse rather
            # than return machine type as "recognised handwriting".
            return _no_handwriting_payload("pp-ocrv5", lang, lines)
        texts = [l["text"] for l in hand_lines]
        polys = [l["poly"] for l in hand_lines]
        scores = [float(l["score"]) for l in hand_lines]
        rec_langs = [l["lang"] for l in hand_lines]
        printed_hints = [bool(l["printed_hint"]) for l in hand_lines]
    except (
        Exception
    ) as e:  # never 500 the client — let it fall back to on-device
        return {
            "rec_texts": [],
            "rec_polys": [],
            "rec_scores": [],
            "full_text": "",
            "engine": "pp-ocrv5",
            "lang": lang,
            "error": str(e),
        }

    if not texts and last_err:
        return {
            "rec_texts": [],
            "rec_polys": [],
            "rec_scores": [],
            "full_text": "",
            "engine": "pp-ocrv5",
            "lang": lang,
            "error": last_err,
        }

    return {
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
        "langs": recognizer.resolve_langs(lang),
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
    ckey = _cache_key(
        "ocr",
        raw,
        lang,
        f"det={det}|rec={rec}|backend={OCR_BACKEND}",
    )
    cached = _cache_get(ckey)
    if cached is not None:
        return _with_meta(cached, "hit", t0)

    arr = _to_numpy(raw)
    payload = await run_in_threadpool(_ocr_process, arr, raw, lang)
    if "error" in payload:
        return JSONResponse(status_code=200, content=payload)

    _cache_set(ckey, payload)
    return _with_meta(payload, "miss", t0)


def _analyze_vl_process(arr, raw, lang):
    """Synchronous body of /analyze-vl (see _ocr_process for why this runs
    off the event loop)."""
    last_err = ""
    selected_backend = "paddle"
    compare_meta = {}
    try:
        raw_lines, last_err, selected_backend, compare_meta = (
            recognizer.collect_lines(arr, lang)
        )
        lines, hand_lines = recognizer.extract_hand_lines(
            arr, raw_lines, raw_bytes=raw, refine_backend=selected_backend
        )
        if lines and not hand_lines:
            # Every detected line is printed: refuse to analyse the page
            # (printed text is never scored or shown as evidence).
            return _no_handwriting_payload(
                "pp-ocrv5+vl",
                lang,
                lines,
                extra={
                    "document_context": {},
                    "layout": {},
                    "regions": [],
                    "factor_regions": {},
                },
            )
        if not hand_lines:
            # No OCR engine could run (models unavailable, engine init
            # failure). The layout/context/factor-region analysis is pure
            # CV, so fall back to OCR-free line detection instead of
            # failing the request.
            hand_lines = computer_vision.fallback_line_regions(arr)
            lines = lines or hand_lines
            if hand_lines:
                selected_backend = "cv-fallback"
        texts = [l["text"] for l in hand_lines]
        polys = [l["poly"] for l in hand_lines]
        scores = [float(l["score"]) for l in hand_lines]
        rec_langs = [l["lang"] for l in hand_lines]
        printed_hints = [bool(l["printed_hint"]) for l in hand_lines]

        vl = _vl_analyze(arr, hand_lines)
    except Exception as e:
        return {
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
        }

    if not texts and last_err:
        return {
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
        }

    return {
        "ok": True,
        "engine": f"pp-ocrv5+opencv-context+{selected_backend}",
        "selected_backend": selected_backend,
        "backend_compare": compare_meta,
        "lang": lang,
        "langs": recognizer.resolve_langs(lang),
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


@app.post("/analyze-vl")
async def analyze_vl(
    image: UploadFile = File(...),
    lang: str = Form("auto"),
):
    t0 = time.perf_counter()
    raw = await image.read()
    ckey = _cache_key(
        "analyze-vl",
        raw,
        lang,
        f"backend={OCR_BACKEND}",
    )
    cached = _cache_get(ckey)
    if cached is not None:
        return _with_meta(cached, "hit", t0)

    arr = _to_numpy(raw)
    payload = await run_in_threadpool(_analyze_vl_process, arr, raw, lang)
    if not payload.get("ok"):
        return JSONResponse(status_code=200, content=payload)

    _cache_set(ckey, payload)
    return _with_meta(payload, "miss", t0)


def _report_python_process(arr, raw, lang, expected_text):
    """Synchronous body of /report-python: OCR plus the full 20-factor
    analysis, the heaviest of the three endpoints (see _ocr_process for why
    this runs off the event loop)."""
    last_err = ""
    selected_backend = "paddle"
    compare_meta = {}
    try:
        raw_lines, last_err, selected_backend, compare_meta = (
            recognizer.collect_lines(arr, lang)
        )
        lines, hand_lines = recognizer.extract_hand_lines(
            arr, raw_lines, raw_bytes=raw, refine_backend=selected_backend
        )
        if lines and not hand_lines:
            # Every detected line is printed. Scoring machine type as
            # handwriting would fabricate a report, so refuse clearly.
            return _no_handwriting_payload(
                "pp-ocrv5+python-report",
                lang,
                lines,
                extra={
                    "analysis": None,
                    "document_context": {},
                    "layout": {},
                    "regions": [],
                    "factor_regions": {},
                },
            )
        if not hand_lines:
            # No OCR engine could run (models unavailable, engine init
            # failure). The 20 factors are measured from GEOMETRY, not from
            # reading the words, so score the scan from OCR-free CV line
            # detection instead of failing it; recognition is reported as
            # unavailable below.
            hand_lines = computer_vision.fallback_line_regions(arr)
            lines = lines or hand_lines
            if hand_lines:
                selected_backend = "cv-fallback"
        # Reference-passage alignment: if the writer copied a known passage,
        # correct the recognised text against it (consistent, dependable reading).
        align_info = recognizer.align_to_expected(hand_lines, expected_text)
        texts = [l["text"] for l in hand_lines]
        polys = [l["poly"] for l in hand_lines]
        scores = [float(l["score"]) for l in hand_lines]
        rec_langs = [l["lang"] for l in hand_lines]
        printed_hints = [bool(l["printed_hint"]) for l in hand_lines]

        vl = _vl_analyze(arr, hand_lines)
        analysis = scoring.build_analysis(
            arr, hand_lines, vl.get("layout", {})
        ).to_dict()
    except Exception as e:
        return {
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
        }

    if not texts and last_err:
        return {
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
        }

    # Recognition transparency: which engine read the page, how many handwriting
    # vs printed lines were found, and the mean recognition confidence. Lets the
    # report show an honest accuracy/confidence indicator instead of implying a
    # certainty the engine doesn't have.
    if isinstance(analysis, dict):
        hand_conf = scoring.mean(
            [float(l.get("score", 0.0)) for l in hand_lines]
        )
        reliable_lines = int(
            sum(
                1
                for l in hand_lines
                if float(l.get("score", 0.0) or 0.0) >= 0.85
            )
        )
        # Which specialist engine (if any) actually re-read each handwriting
        # line in trocr/hybrid mode -- proof, not a claim, that e.g. TrOCR
        # ran on this scan. hand_lines only carries "refined_by" on lines a
        # specialist's re-read was accepted for (see
        # recognizer.refine_handwriting_text); paddle-only lines have none.
        refined_by = {}
        for l in hand_lines:
            engine = l.get("refined_by")
            if engine:
                refined_by[engine] = refined_by.get(engine, 0) + 1
        passage_aligned = bool(align_info and align_info.get("aligned"))
        has_read_text = any(
            str(l.get("text") or "").strip() for l in hand_lines
        )
        # Trust level the report should display. With a matched reference passage
        # recognition is dependable; otherwise it is honestly "assistive" and the
        # report must make clear the 20 factors do NOT depend on it. When no OCR
        # engine could run at all (cv-fallback path) say so outright.
        if passage_aligned:
            level = "passage-verified"
        elif not has_read_text:
            level = "unavailable"
        elif hand_conf >= 0.85:
            level = "high"
        elif hand_conf >= 0.70:
            level = "moderate"
        else:
            level = "low"
        analysis["recognition"] = {
            "backend": selected_backend,
            "ocr_error": (last_err or None) if not has_read_text else None,
            "hand_lines": len(hand_lines),
            "printed_lines": int(
                sum(1 for l in lines if l.get("printed_hint"))
            ),
            "reliable_lines": reliable_lines,
            "mean_confidence": round(hand_conf, 3),
            "confidence_pct": int(round(hand_conf * 100)),
            "refined_by": refined_by,
            "refined_lines": sum(refined_by.values()),
            "level": level,
            "assistive_only": not passage_aligned,
            "passage_aligned": passage_aligned,
            "passage_match": (align_info or {}).get("passage_match"),
            "note": (
                "The 20 factors are measured from the geometry of the "
                "writing and do not depend on reading the words."
            ),
        }

    return {
        "ok": True,
        "engine": f"pp-ocrv5+python-report+{selected_backend}",
        "selected_backend": selected_backend,
        "backend_compare": compare_meta,
        "lang": lang,
        "langs": recognizer.resolve_langs(lang),
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


@app.post("/report-python")
async def report_python(
    image: UploadFile = File(...),
    lang: str = Form("auto"),
    expected_text: str = Form(""),
):
    t0 = time.perf_counter()
    raw = await image.read()
    ckey = _cache_key(
        "report-python",
        raw,
        lang,
        f"{expected_text or ''}|backend={OCR_BACKEND}",
    )
    cached = _cache_get(ckey)
    if cached is not None:
        return _with_meta(cached, "hit", t0)

    arr = _to_numpy(raw)
    payload = await run_in_threadpool(
        _report_python_process, arr, raw, lang, expected_text
    )
    if not payload.get("ok"):
        return JSONResponse(status_code=200, content=payload)

    _cache_set(ckey, payload)
    return _with_meta(payload, "miss", t0)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
