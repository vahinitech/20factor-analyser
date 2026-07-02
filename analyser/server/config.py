# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies. Server-side handwriting/print recognition.
# Third-party: PaddleOCR (Apache-2.0). See /THIRD-PARTY-NOTICES.md and server/README.md
#
# config.py — server-wide settings, parsed from environment variables once
# at import time. Single source of truth for every VAHINI_OCR_*/
# VAHINI_CHANDRA_* env var; ppocr-server.py exposes these as module-level
# constants (under their existing names) for the rest of the file to use.

import os
from dataclasses import dataclass

from model_map import parse_model_map
from gpu_detect import resolve_use_gpu


@dataclass
class Settings:
    use_gpu: bool
    ocr_langs: list
    ocr_backend: str
    chandra_method: str
    chandra_max_tokens: int
    max_variants: int
    adv_preproc: bool
    use_doc_orientation: bool
    use_doc_unwarping: bool
    use_textline_orientation: bool
    max_ocr_side: int
    ocr_version: str
    det_model_name: str
    rec_model_map_raw: str
    rec_model_map: dict
    text_det_limit_side_len: int
    text_rec_score_thresh: float
    auto_min_lines: int
    variant_min_lines: int
    resp_cache_ttl_sec: int
    resp_cache_max_items: int
    allowed_origins: list
    refine_min_sim: float


def load() -> Settings:
    """Read every setting from the environment. Called once at import time
    below; call again (e.g. in a test) to pick up changed env vars."""
    ocr_langs = [
        s.strip()
        for s in os.environ.get("VAHINI_OCR_LANGS", "en,te").split(",")
        if s.strip()
    ]
    auto_min_lines = max(
        2, int(os.environ.get("VAHINI_OCR_AUTO_MIN_LINES", "3"))
    )
    rec_model_map_raw = os.environ.get(
        "VAHINI_OCR_REC_MODEL_MAP",
        "en:PP-OCRv5_server_rec,te:te_PP-OCRv5_mobile_rec",
    )
    return Settings(
        use_gpu=resolve_use_gpu("VAHINI_OCR_GPU", engine="paddle"),
        ocr_langs=ocr_langs,
        ocr_backend=(
            (os.environ.get("VAHINI_OCR_BACKEND", "paddle") or "paddle")
            .strip()
            .lower()
        ),
        chandra_method=(
            (os.environ.get("VAHINI_CHANDRA_METHOD", "api") or "api")
            .strip()
            .lower()
        ),
        chandra_max_tokens=max(
            512,
            int(os.environ.get("VAHINI_CHANDRA_MAX_OUTPUT_TOKENS", "6144")),
        ),
        # A mobile detector is several times faster than the server detector
        # on CPU, with negligible real-world accuracy loss on handwriting
        # pages; VAHINI_OCR_DET_MODEL_NAME overrides it (recommended only
        # when a GPU is available). Recognition defaults English to the
        # server rec model (materially more accurate on handwriting than
        # the mobile rec) while Telugu keeps its language-specific mobile
        # rec; VAHINI_OCR_REC_MODEL_MAP overrides both.
        max_variants=max(
            1, min(3, int(os.environ.get("VAHINI_OCR_VARIANTS", "2")))
        ),
        adv_preproc=os.environ.get("VAHINI_OCR_ADV_PREPROC", "1") == "1",
        use_doc_orientation=(
            os.environ.get("VAHINI_OCR_DOC_ORIENT", "0") == "1"
        ),
        use_doc_unwarping=os.environ.get("VAHINI_OCR_DOC_UNWARP", "0") == "1",
        use_textline_orientation=(
            os.environ.get("VAHINI_OCR_TEXTLINE_ORIENT", "0") == "1"
        ),
        max_ocr_side=max(
            960, int(os.environ.get("VAHINI_OCR_MAX_SIDE", "2200"))
        ),
        ocr_version=(
            os.environ.get("VAHINI_OCR_VERSION", "PP-OCRv5") or ""
        ).strip()
        or None,
        det_model_name=(
            os.environ.get("VAHINI_OCR_DET_MODEL_NAME", "PP-OCRv5_mobile_det")
            or ""
        ).strip()
        or None,
        rec_model_map_raw=rec_model_map_raw,
        rec_model_map=parse_model_map(rec_model_map_raw),
        text_det_limit_side_len=max(
            0, int(os.environ.get("VAHINI_OCR_DET_LIMIT_SIDE_LEN", "2048"))
        ),
        text_rec_score_thresh=float(
            os.environ.get("VAHINI_OCR_TEXT_REC_SCORE_THRESH", "0.0")
        ),
        auto_min_lines=auto_min_lines,
        variant_min_lines=max(
            1,
            int(
                os.environ.get(
                    "VAHINI_OCR_VARIANT_MIN_LINES", str(auto_min_lines)
                )
            ),
        ),
        resp_cache_ttl_sec=max(
            0, int(os.environ.get("VAHINI_OCR_CACHE_TTL_SEC", "180"))
        ),
        resp_cache_max_items=max(
            16, int(os.environ.get("VAHINI_OCR_CACHE_MAX_ITEMS", "128"))
        ),
        allowed_origins=os.environ.get("VAHINI_OCR_ORIGINS", "*").split(","),
        # Accept a stronger engine's refinement of paddle's reading only
        # when it is at least this similar (0.70 cleanly separates real
        # refinements from VLM hallucinations; see recognizer.py).
        refine_min_sim=float(os.environ.get("VAHINI_REFINE_MIN_SIM", "0.70")),
    )


SETTINGS = load()
