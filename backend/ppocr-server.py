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
import lang_tags  # BCP 47 tags in the request to the engine's codes
import ocr_backends  # pluggable engine adapters (paddle/trocr/surya)
import classify  # printed-vs-handwriting classifier
from PIL import UnidentifiedImageError
from pypdfium2 import PdfiumError

import computer_vision  # image decode/crop/preview + layout/doc-context
import ink_geometry  # lines and geometry from the ink, for unread scripts
import scoring  # the 20-factor model (FactorScore/SectionScore/AnalysisResult)
import factor_needs  # what each factor needs; a profile's emptied classes
import recognizer  # dispatches + post-processes recognition across backends
import layout_filter  # negative pre-filter using PaddleOCR's layout model
import entitlements
import access_api  # internal ledger API, off unless provisioned
import report_contract
import compact_reports
import practice_catalog
import scan_slots  # caps simultaneous scans so memory cannot run out
import debug_store  # stage-only photo keeping, off unless provisioned
from typing import Literal
from gpu_detect import gpu_zero_caveat, nvidia_gpu_present
from languages import stages  # which engine reads each script (#208)
from languages import profile as profiles  # school/class/child rules (#220)

# Paddle 3.x on some CPUs can fail in oneDNN/PIR execution paths for OCR.
# Prefer the stable execution route unless explicitly overridden.
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

from fastapi import (
    FastAPI,
    Request,
    UploadFile,
    File,
    Form,
    Header,
    HTTPException,
    Query,
)
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from upload_limits import MAX_UPLOAD_BYTES, UploadBodyLimit
from daily_limit import LIMIT as DAILY
import numpy as np

# PaddleOCR 3.x (PP-OCRv5) is imported LAZILY inside get_engine() so this module
# loads even when paddle isn't installed (e.g. a non-paddle backend, or tests).
# pip install paddleocr paddlepaddle  (see requirements.txt)

app = FastAPI(title="Vahini PP-OCRv5 service", version="1.0")
app.add_middleware(UploadBodyLimit)


@app.middleware("http")
async def private_api_responses(request, call_next):
    """Personal reports and subscription responses must not enter HTTP caches."""
    response = await call_next(request)
    path = request.url.path
    if (
        (
            path.startswith("/api/v2/")
            and not path.startswith("/api/v2/catalog/")
        )
        or path.startswith("/internal/")
        or path
        in (
            "/report-python",
            "/analyze-vl",
        )
    ):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Vary"] = "Authorization"
    return response


access_api.install(app)

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
        layout_filter.warm()

    threading.Thread(
        target=_warm, name="vahini-engine-warmup", daemon=True
    ).start()


# decode_image/_pdf_first_page/to_numpy now live in computer_vision.py.
# Thin aliases here keep the rest of this file (and callers that still refer
# to these by their historical short names) unchanged.
_decode_image = computer_vision.decode_image


async def _read_upload(image):
    raw = await image.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Upload exceeds 5 MiB")
    debug_store.received(raw)
    return raw


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
        # One engine copy per scan slot, each on its share of the cores
        # (or spread over the GPUs). A single slot keeps Paddle's defaults.
        "cpu_threads": (
            scan_slots.PLAN["threads_per_engine"] or 0
            if scan_slots.PLAN["active"] > 1
            else 0
        ),
        "gpu_count": scan_slots.PLAN["gpus"],
    },
)
print(f"[capacity] {scan_slots.PLAN}", flush=True)


# _to_data_url/_crop_rgb/_build_region_previews/_full_page_preview/
# _factor_region_map/_layout_features/_infer_doc_context/vl_analyze now
# live in computer_vision.py. This module only needs vl_analyze.
# The hardest letters on the hardest line are read again by the scan's
# own PaddleOCR recogniser, so only where PaddleOCR reads the page.
_READ_LETTERS = (
    ocr_backends.read_line_letters
    if OCR_BACKEND in ("paddle", "hybrid", "auto")
    else None
)
# Writing the detector missed is read by the same recogniser
# (line_recovery.py), wherever PaddleOCR found the lines.
_READ_REGION = (
    ocr_backends.read_region
    if OCR_BACKEND in ("paddle", "trocr", "hybrid", "auto")
    else None
)


def _vl_analyze(arr, lines, include_evidence=True):
    # Rows found from the ink were not read, and are not read again for
    # their least-sure letters either.
    unread = bool(lines) and all(l.get("ink_row") for l in lines)
    return computer_vision.vl_analyze(
        arr,
        lines,
        include_evidence,
        read_letters=None if unread else _READ_LETTERS,
    )


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
        "scan_capacity": {**scan_slots.PLAN, **scan_slots.SLOTS.stats()},
        # True only on stage with debug storage provisioned (debug_store.py).
        "debug_store": debug_store.STORE.enabled,
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
        # recognizer.refine_handwriting_text) record here. Empty until the
        # first relevant call has actually run. The layout filter's model is
        # fixed by configuration, so it records nothing here (#112).
        "adaptive_engine_speed": ocr_backends.engine_speed_snapshot(),
        # The committed stage table every route comes from, and the device
        # each engine resolved to (None until it is built). Recorded so the
        # ladders, where the device is part of the stage (#219), have data.
        "recognition": {
            "stages_sha256": stages.table().hash,
            "devices": ocr_backends.engine_devices(),
        },
        # Which layout model is loaded (see layout_filter.py). A scan waits
        # for the load, never skips it, so this is the model every scan uses.
        "layout_filter": {
            "enabled": layout_filter.is_enabled(),
            "built_tiers": layout_filter.built_tiers(),
        },
    }


# When no OCR engine could read the page (an engine that will not load, or
# a run that failed, e.g. under memory pressure), the scan is refused with a
# 503 and the visitor tries again. It used to be scored from OCR-free CV line
# regions, which differ from OCR's, so the same photo got different scores
# depending on whether the engine was up (owner decision 2026-10-10, #112).
# A 503 is never cached and never counts against the daily free checks.
OCR_UNAVAILABLE_RETRY_SEC = 60
OCR_UNAVAILABLE_DETAIL = (
    "The analyser could not read this photo just now. "
    "Please try again in a minute."
)


def _ocr_unavailable_payload(engine):
    return {
        "ok": False,
        "engine": engine,
        "error_code": "ocr_unavailable",
        "error": OCR_UNAVAILABLE_DETAIL,
    }


def _raise_if_ocr_unavailable(payload):
    if payload.get("error_code") == "ocr_unavailable":
        raise HTTPException(
            503,
            {
                "error_code": "ocr_unavailable",
                "error": OCR_UNAVAILABLE_DETAIL,
            },
            headers={"Retry-After": str(OCR_UNAVAILABLE_RETRY_SEC)},
        )


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
        "text_classification": classify.classification_summary(lines),
        "rec_texts": [],
        "rec_polys": [],
        "rec_scores": [],
        "full_text": "",
        "lang": lang,
    }
    if extra:
        payload.update(extra)
    return payload


# A page asked for in Telugu that the reader did not manage: mostly Latin
# letters, or an unsure reading (recognizer.telugu_not_read). The geometry
# could still be measured, but a report built on lines the reader invented
# is not a report on this child's writing, so the scan is refused. Like
# no_handwriting it is never cached and never counts as a free check.
HANDWRITING_NOT_READ_DETAIL = (
    "The analyser could not read the writing on this page. It reads "
    "English handwriting; it cannot yet read handwritten Telugu, so this "
    "page was not scored."
)


def _handwriting_not_read_payload(engine, lang, counts, extra=None):
    payload = {
        "ok": False,
        "engine": engine,
        "error_code": "handwriting_not_read",
        "error": HANDWRITING_NOT_READ_DETAIL,
        **counts,
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
            arr,
            raw_lines,
            raw_bytes=raw,
            refine_backend=selected_backend,
            read_region=_READ_REGION,
        )
        if lines and not hand_lines:
            # Text was detected but every line is printed: refuse rather
            # than return machine type as "recognised handwriting".
            return _no_handwriting_payload("pp-ocrv5", lang, lines)
        not_read = recognizer.telugu_not_read(lang, hand_lines)
        if not_read:
            return _handwriting_not_read_payload("pp-ocrv5", lang, not_read)
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
        "text_classification": classify.classification_summary(
            lines, hand_lines
        ),
        "full_text": "\n".join(texts),
        "proc_w": int(arr.shape[1]),
        "proc_h": int(arr.shape[0]),
        "engine": f"pp-ocrv5+{selected_backend}",
        "selected_backend": selected_backend,
        "backend_compare": compare_meta,
        "lang": lang,
        "langs": recognizer.resolve_langs(lang),
    }


async def _decode_upload(raw):
    """Decode outside the event loop. Oversized pages are 413; malformed
    uploads are 422 client errors, never server errors."""
    try:
        return await scan_slots.run(_to_numpy, raw)
    except computer_vision.UploadLimitError as exc:
        raise HTTPException(413, str(exc)) from exc
    except (UnidentifiedImageError, OSError, ValueError, PdfiumError) as exc:
        raise HTTPException(
            status_code=422, detail="Upload a valid image or PDF."
        ) from exc


@app.post("/ocr")
@debug_store.keeps("/ocr")
async def ocr(
    request: Request,
    image: UploadFile = File(...),
    lang: str = Form("auto"),
    det: str = Form("true"),
    rec: str = Form("true"),
    authorization: str = Header(default=None),
):
    charge = DAILY.check(request, exempt=await _is_pro(authorization))
    t0 = time.perf_counter()
    # te-Telu-IN reads, caches and answers as te (lang_tags.py).
    lang = lang_tags.engine_langs(lang)
    raw = await _read_upload(image)
    ckey = _cache_key(
        "ocr",
        raw,
        lang,
        f"det={det}|rec={rec}|backend={OCR_BACKEND}",
    )
    cached = _cache_get(ckey)
    if cached is not None:
        DAILY.spend(charge)
        return _with_meta(cached, "hit", t0)

    async with scan_slots.SLOTS.slot():
        arr = await _decode_upload(raw)
        payload = await scan_slots.run(_ocr_process, arr, raw, lang)
    if "error" in payload:
        return JSONResponse(status_code=200, content=payload)

    _cache_set(ckey, payload)
    DAILY.spend(charge)
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
            arr,
            raw_lines,
            raw_bytes=raw,
            refine_backend=selected_backend,
            read_region=_READ_REGION,
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
                    "ambiguous_word_gaps": [],
                },
            )
        if not raw_lines and last_err:
            # No OCR engine could read the page: refuse, never score CV
            # regions in its place (see OCR_UNAVAILABLE_DETAIL).
            return _ocr_unavailable_payload("pp-ocrv5+vl")
        not_read = recognizer.telugu_not_read(lang, hand_lines)
        if not_read:
            return _handwriting_not_read_payload(
                "pp-ocrv5+vl",
                lang,
                not_read,
                extra={
                    "document_context": {},
                    "layout": {},
                    "regions": [],
                    "factor_regions": {},
                    "ambiguous_word_gaps": [],
                },
            )
        if not hand_lines:
            # OCR ran and found no lines. The layout/context/factor-region
            # analysis is pure CV, so use OCR-free line detection; the same
            # photo always takes this path.
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
            "ambiguous_word_gaps": [],
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
            "ambiguous_word_gaps": [],
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
        "text_classification": classify.classification_summary(
            lines, hand_lines
        ),
        "full_text": "\n".join(texts),
        "proc_w": int(arr.shape[1]),
        "proc_h": int(arr.shape[0]),
        "document_context": vl.get("document_context", {}),
        "layout": vl.get("layout", {}),
        "regions": vl.get("regions", []),
        "factor_regions": vl.get("factor_regions", {}),
        "measurements": vl.get("measurements", {}),
        "ambiguous_word_gaps": vl.get("ambiguous_word_gaps", []),
    }


@app.post("/analyze-vl")
@debug_store.keeps("/analyze-vl")
async def analyze_vl(
    request: Request,
    image: UploadFile = File(...),
    lang: str = Form("auto"),
    authorization: str = Header(default=None),
):
    if os.environ.get("VAHINI_ENFORCE_TIERS") == "1":
        if (await run_in_threadpool(entitlements.access_for, authorization))[
            "tier"
        ] != "pro":
            raise HTTPException(403, "Detailed factor evidence requires Pro")
    charge = DAILY.check(request, exempt=await _is_pro(authorization))
    t0 = time.perf_counter()
    # te-Telu-IN reads, caches and answers as te (lang_tags.py).
    lang = lang_tags.engine_langs(lang)
    raw = await _read_upload(image)
    ckey = _cache_key(
        "analyze-vl",
        raw,
        lang,
        f"backend={OCR_BACKEND}",
    )
    cached = _cache_get(ckey)
    if cached is not None:
        payload = cached
    else:
        async with scan_slots.SLOTS.slot():
            arr = await _decode_upload(raw)
            payload = await scan_slots.run(_analyze_vl_process, arr, raw, lang)
        _raise_if_ocr_unavailable(payload)
    if os.environ.get("VAHINI_ENFORCE_TIERS") == "1":
        if (await run_in_threadpool(entitlements.access_for, authorization))[
            "tier"
        ] != "pro":
            raise HTTPException(403, "Detailed factor evidence requires Pro")
    if not payload.get("ok"):
        return JSONResponse(status_code=200, content=payload)

    _cache_set(ckey, payload)
    DAILY.spend(charge)
    return _with_meta(payload, "hit" if cached is not None else "miss", t0)


INK_LANGS = set(SETTINGS.ink_geometry_langs)


def _ink_mode(lang):
    """Whether a check in this language is measured from the ink
    (VAHINI_INK_GEOMETRY_LANGS): only when the request names languages
    and every one of them is set; "auto" cannot know the script before
    reading, so it never is."""
    req = [x for x in lang_tags.engine_langs(lang).split(",") if x]
    if not INK_LANGS or not req or "auto" in req:
        return False
    return all(x in INK_LANGS for x in req)


def _ink_lines(arr, expected_text):
    """(all rows, handwriting rows) from the ink. The printed check still
    runs on each row's shape, so a printed page is still refused. A
    passage with one line per row gives each row its number of words."""
    rows = ink_geometry.find_rows(arr)
    classify.classify_lines(arr, rows)
    hand = [r for r in rows if not r.get("printed_hint")]
    ink_geometry.expect_words(hand, expected_text)
    return rows, hand


def _report_python_process(
    arr, raw, lang, expected_text, include_evidence=True, ruleset=None
):
    """Synchronous body of /report-python: OCR plus the full 20-factor
    analysis, the heaviest of the three endpoints (see _ocr_process for why
    this runs off the event loop). ruleset: the packs plus the request's
    profile (languages/profile.py); None is the packs alone."""
    last_err = ""
    selected_backend = "paddle"
    compare_meta = {}
    try:
        if _ink_mode(lang):
            # A language the reader cannot find the lines of: measured
            # from the ink (ink_geometry.py), nothing read.
            raw_lines, last_err, selected_backend = [], "", "ink-geometry"
            lines, hand_lines = _ink_lines(arr, expected_text)
        else:
            raw_lines, last_err, selected_backend, compare_meta = (
                recognizer.collect_lines(arr, lang)
            )
            lines, hand_lines = recognizer.extract_hand_lines(
                arr,
                raw_lines,
                raw_bytes=raw,
                refine_backend=selected_backend,
                read_region=_READ_REGION,
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
                    "ambiguous_word_gaps": [],
                },
            )
        if not raw_lines and last_err:
            # No OCR engine could read the page: refuse, never score CV
            # regions in its place (see OCR_UNAVAILABLE_DETAIL).
            return _ocr_unavailable_payload("pp-ocrv5+python-report")
        not_read = recognizer.telugu_not_read(lang, hand_lines)
        if not_read:
            return _handwriting_not_read_payload(
                "pp-ocrv5+python-report",
                lang,
                not_read,
                extra={
                    "analysis": None,
                    "document_context": {},
                    "layout": {},
                    "regions": [],
                    "factor_regions": {},
                    "ambiguous_word_gaps": [],
                },
            )
        if not hand_lines:
            # OCR ran and found no lines. The 20 factors are measured from
            # GEOMETRY, so score OCR-free CV line regions; recognition is
            # reported as unavailable below. The same photo always takes
            # this path.
            hand_lines = computer_vision.fallback_line_regions(arr)
            lines = lines or hand_lines
            if hand_lines:
                selected_backend = "cv-fallback"
        if not hand_lines:
            return _no_handwriting_payload(
                "pp-ocrv5+python-report",
                lang,
                lines,
                extra={
                    "error": "No handwriting found. Upload a clear photo of handwriting.",
                    "analysis": None,
                    "document_context": {},
                    "layout": {},
                    "regions": [],
                    "factor_regions": {},
                    "ambiguous_word_gaps": [],
                },
            )
        # Classification and spelling must see the text as the OCR read it.
        # align_to_expected() rewrites each accepted line's text to the
        # supplied passage, so keep the original reading on the line.
        for line in list(lines) + list(hand_lines):
            line.setdefault("text_as_read", str(line.get("text") or ""))
        # Reference-passage alignment: if the writer copied a known passage,
        # correct the recognised text against it (consistent, dependable reading).
        align_info = recognizer.align_to_expected(hand_lines, expected_text)
        texts = [l["text"] for l in hand_lines]
        polys = [l["poly"] for l in hand_lines]
        scores = [float(l["score"]) for l in hand_lines]
        rec_langs = [l["lang"] for l in hand_lines]
        printed_hints = [bool(l["printed_hint"]) for l in hand_lines]

        vl = (
            _vl_analyze(arr, hand_lines)
            if include_evidence
            else _vl_analyze(arr, hand_lines, include_evidence=False)
        )
        # The profile reaches the scorer through factor_needs, for this
        # call only: a class it emptied leaves its factors Not measured.
        with profiles.applied(ruleset):
            analysis = scoring.build_analysis(
                arr, hand_lines, vl.get("layout", {})
            ).to_dict()
        factor_needs.explain(analysis, ruleset)
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
            "ambiguous_word_gaps": [],
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
            "ambiguous_word_gaps": [],
        }

    # Recognition transparency: which engine read the page, how many handwriting
    # vs printed lines were found, and the mean recognition confidence. Lets the
    # report show an honest accuracy/confidence indicator instead of implying a
    # certainty the engine doesn't have.
    if isinstance(analysis, dict):
        analysis["textClassification"] = classify.classification_summary(
            lines, hand_lines
        )
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

    photo = computer_vision.photo_size(raw)
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
        "text_classification": classify.classification_summary(
            lines, hand_lines
        ),
        "full_text": "\n".join(texts),
        "proc_w": int(arr.shape[1]),
        "proc_h": int(arr.shape[0]),
        # The uploaded photo's own size, so version-2 reports can give
        # factor marks in its pixels (comparison_data.factor_marks).
        **dict(zip(("photo_w", "photo_h"), photo or ())),
        "document_context": vl.get("document_context", {}),
        "layout": vl.get("layout", {}),
        "regions": vl.get("regions", []),
        "factor_regions": vl.get("factor_regions", {}),
        "measurements": vl.get("measurements", {}),
        "ambiguous_word_gaps": vl.get("ambiguous_word_gaps", []),
    }


def _ruleset(profile):
    """The packs plus the request's profile field, or HTTP 413/422 with
    the profile's error code. Called before the upload is read or a free
    check is counted. The profile is never logged or stored; only its
    hash leaves this request."""
    try:
        return profiles.from_request(profile)
    except profiles.ProfileError as exc:
        raise HTTPException(exc.status, exc.detail()) from None


async def _report_payload(
    image, lang, expected_text, include_evidence=True, ruleset=None
):
    t0 = time.perf_counter()
    ruleset = ruleset or profiles.resolve()
    # te-Telu-IN reads, caches and answers as te (lang_tags.py).
    lang = lang_tags.engine_langs(lang)
    raw = await _read_upload(image)
    # The ruleset hash keys the cache: a changed profile is a new scan.
    ckey = _cache_key(
        "report-python",
        raw,
        lang,
        f"{expected_text or ''}|backend={OCR_BACKEND}|evidence={include_evidence}",
        ruleset=ruleset.hash,
    )
    cached = _cache_get(ckey)
    if cached is not None:
        return _with_meta(cached, "hit", t0)

    async with scan_slots.SLOTS.slot():
        arr = await _decode_upload(raw)
        payload = await scan_slots.run(
            _report_python_process,
            arr,
            raw,
            lang,
            expected_text,
            include_evidence,
            ruleset,
        )
    payload["ruleset"] = ruleset.hash
    _raise_if_ocr_unavailable(payload)
    if not payload.get("ok"):
        return payload

    _cache_set(ckey, payload)
    return _with_meta(payload, "miss", t0)


async def _is_pro(authorization):
    """A Pro access key is not counted against the daily free checks."""
    if not authorization:
        return False
    try:
        access = await run_in_threadpool(
            entitlements.access_for, authorization
        )
    except HTTPException:
        return False
    return access.get("tier") == "pro"


def _spend_if_report(charge, payload):
    """Only a check that produced a report counts (daily_limit.py)."""
    if payload.get("ok") is not False and not payload.get("error_code"):
        DAILY.spend(charge)


@app.post("/report-python")
@debug_store.keeps("/report-python")
async def report_python(
    request: Request,
    image: UploadFile = File(...),
    lang: str = Form("auto"),
    expected_text: str = Form(""),
    profile: str = Form(""),
    authorization: str = Header(default=None),
):
    enforce = os.environ.get("VAHINI_ENFORCE_TIERS") == "1"
    if enforce:
        await run_in_threadpool(entitlements.access_for, authorization)
    ruleset = _ruleset(profile)
    charge = DAILY.check(request, exempt=await _is_pro(authorization))
    payload = await _report_payload(image, lang, expected_text, True, ruleset)
    _spend_if_report(charge, payload)
    if enforce:
        # Recheck after inference: expiry/revocation must also affect cache hits.
        return report_contract.legacy_report(
            payload,
            await run_in_threadpool(entitlements.access_for, authorization),
        )
    return payload


@app.get("/api/v2/me")
async def api_identity(authorization: str = Header(default=None)):
    access = await run_in_threadpool(entitlements.access_for, authorization)
    return {
        "schema_version": "2.0",
        "access": {
            **access,
            "capabilities": entitlements.capabilities(access),
        },
        # How many skills, exercises and tips this visitor's report shows
        # (practice_catalog.TIERS, the one place those numbers live).
        "practice": practice_catalog.limits(access["tier"]),
    }


@app.post("/api/v2/reports")
@debug_store.keeps("/api/v2/reports")
async def api_report(
    request: Request,
    image: UploadFile = File(...),
    lang: str = Form("auto"),
    expected_text: str = Form(""),
    profile: str = Form(""),
    authorization: str = Header(default=None),
    format: Literal["expanded", "compact"] = Query(default="expanded"),
    include: str = Query(default=""),
):
    access = await run_in_threadpool(entitlements.access_for, authorization)
    fields = set(filter(None, include.split(",")))
    if fields - compact_reports.OPTIONAL_FIELDS:
        raise HTTPException(422, "Unsupported include field")
    # Free may request text and the evidence crops for its own five
    # factors; scoring inputs and coaching stay Pro.
    if fields - {"text", "evidence"} and access["tier"] != "pro":
        raise HTTPException(403, "Requested report details require Pro")
    ruleset = _ruleset(profile)
    charge = DAILY.check(request, exempt=access["tier"] == "pro")
    if format == "compact":
        payload = await _report_payload(
            image,
            lang,
            expected_text,
            include_evidence="evidence" in fields,
            ruleset=ruleset,
        )
        _spend_if_report(charge, payload)
        access = await run_in_threadpool(
            entitlements.access_for, authorization
        )
        return compact_reports.build_compact(payload, access, fields)
    payload = await _report_payload(image, lang, expected_text, True, ruleset)
    _spend_if_report(charge, payload)
    return report_contract.public_report(
        payload,
        await run_in_threadpool(entitlements.access_for, authorization),
    )


@app.get("/api/v2/catalog/{version}")
def api_catalog(version: str, if_none_match: str = Header(default=None)):
    content = compact_reports.catalog_bytes(version)
    if content is None:
        raise HTTPException(404, "Unknown catalogue version")
    headers = {
        "Cache-Control": "public, max-age=31536000, immutable",
        "ETag": '"' + version + '"',
    }
    validators = {
        tag.strip().removeprefix("W/")
        for tag in (if_none_match or "").split(",")
    }
    if headers["ETag"] in validators or "*" in validators:
        return Response(status_code=304, headers=headers)
    return Response(
        content=content, media_type="application/json", headers=headers
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
