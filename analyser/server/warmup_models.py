# SPDX-License-Identifier: AGPL-3.0-only
# © 2026 Vahini Technologies. Contact: infor@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
# Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json
#
# warmup_models.py — pre-download / warm the recognition models so the FIRST
# real request isn't slow (model weights are fetched + cached on first use).
#
# It warms whichever engines are installed; missing engines are skipped with a
# note (never an error). Control what to warm:
#   VAHINI_OCR_PRELOAD_LANGS   paddle languages (default "en,te")
#   VAHINI_WARMUP_ENGINES      comma list of paddle,trocr,surya (default: all installed)
#   VAHINI_TROCR_MODEL         TrOCR model id (default microsoft/trocr-base-handwritten)
#
# Usage:
#   python warmup_models.py
import os


def parse_langs(raw):
    langs = [x.strip() for x in (raw or "").split(",") if x.strip()]
    return langs or ["en"]


def parse_model_map(raw):
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


def rec_for_lang(model_map, lang):
    lg = (lang or "").strip().lower()
    return model_map.get(lg) or model_map.get("*")


def _wanted(name):
    raw = (os.environ.get("VAHINI_WARMUP_ENGINES", "") or "").strip().lower()
    if not raw:
        return True  # default: warm everything that is installed
    return name in [x.strip() for x in raw.split(",") if x.strip()]


def warm_paddle():
    if not _wanted("paddle"):
        return
    try:
        from paddleocr import PaddleOCR
    except Exception as e:
        print(f"[warmup] paddle: skipped (not installed: {e})")
        return
    langs = parse_langs(os.environ.get("VAHINI_OCR_PRELOAD_LANGS", "en,te"))
    ocr_version = (os.environ.get("VAHINI_OCR_VERSION", "PP-OCRv5") or "").strip() or None
    det_model_name = (os.environ.get("VAHINI_OCR_DET_MODEL_NAME", "PP-OCRv5_mobile_det") or "").strip() or None
    rec_model_map = parse_model_map(os.environ.get(
        "VAHINI_OCR_REC_MODEL_MAP", "en:PP-OCRv5_server_rec,te:te_PP-OCRv5_mobile_rec"))
    det_limit_side_len = max(0, int(os.environ.get("VAHINI_OCR_DET_LIMIT_SIDE_LEN", "2048")))
    for lang in langs:
        print(f"[warmup] paddle: loading PP-OCRv5 for lang={lang}")
        kwargs = {
            "lang": lang,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
            "device": "cpu",
        }
        if ocr_version:
            kwargs["ocr_version"] = ocr_version
        if det_model_name:
            kwargs["text_detection_model_name"] = det_model_name
        rec_name = rec_for_lang(rec_model_map, lang)
        if rec_name:
            kwargs["text_recognition_model_name"] = rec_name
        if det_limit_side_len > 0:
            kwargs["text_det_limit_side_len"] = det_limit_side_len
        try:
            PaddleOCR(**kwargs)
        except TypeError:
            PaddleOCR(lang=lang, use_angle_cls=True, use_gpu=False, show_log=False)
    print("[warmup] paddle: done")


def warm_trocr():
    if not _wanted("trocr"):
        return
    try:
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    except Exception as e:
        print(f"[warmup] trocr: skipped (not installed: {e})")
        return
    model = os.environ.get("VAHINI_TROCR_MODEL", "microsoft/trocr-base-handwritten")
    print(f"[warmup] trocr: downloading {model}")
    TrOCRProcessor.from_pretrained(model)
    VisionEncoderDecoderModel.from_pretrained(model)
    print("[warmup] trocr: done")


def warm_surya():
    if not _wanted("surya"):
        return
    try:
        import surya  # noqa: F401
        from surya.detection import DetectionPredictor
    except Exception as e:
        print(f"[warmup] surya: skipped (not installed: {e})")
        return
    print("[warmup] surya: loading detection weights")
    try:
        DetectionPredictor()
        print("[warmup] surya: detection ready (recognition needs the inference "
              "backend running — see server/README.md)")
    except Exception as e:
        print(f"[warmup] surya: detection load failed: {e}")


def main():
    warm_paddle()
    warm_trocr()
    warm_surya()
    print("[warmup] completed")


if __name__ == "__main__":
    main()
