# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies. Server-side handwriting/print recognition.
# Third-party: PaddleOCR (Apache-2.0). See /THIRD-PARTY-NOTICES.md and server/README.md
#
# recognizer.py — orchestrates recognition across OCR backends.
#
# Resolves the language list, dispatches to the configured backend
# (paddle/trocr/surya/chandra/auto, falling back to paddle when an
# alternative engine is unavailable or empty), and post-processes the
# result: merge/filter candidate regions, classify printed vs handwriting,
# optionally refine handwriting text with a stronger engine, and align
# recognised lines to a known reference passage. Nothing here decodes
# images or computes the 20-factor score; it only turns OCR backends into
# a clean list of handwriting lines.

import difflib
import re

import numpy as np

import ocr_backends
import classify
import detector
import computer_vision

_CFG = {
    "ocr_langs": ["en"],
    "ocr_backend": "paddle",
    "max_variants": 2,
    "adv_preproc": True,
    "auto_min_lines": 3,
    "variant_min_lines": 3,
    "refine_min_sim": 0.70,
}


def configure(**kwargs):
    """Set the recognizer's dispatch config once at startup. Unknown keys
    are ignored so callers can pass a superset of _CFG."""
    for k, v in kwargs.items():
        if k in _CFG:
            _CFG[k] = v


def resolve_langs(lang: str):
    req = (lang or "").strip().lower()
    ocr_langs = _CFG["ocr_langs"]
    if not req or req == "auto":
        return ocr_langs or ["en"]
    if "," in req:
        langs = [x.strip() for x in req.split(",") if x.strip()]
        return [x for x in langs if x in ocr_langs] or ocr_langs or ["en"]
    return [req] if req in ocr_langs else ocr_langs or ["en"]


def collect_lines_paddle(arr: np.ndarray, lang: str):
    last_err = ""
    langs = resolve_langs(lang)
    lines = []
    for lg in langs:
        engine = ocr_backends.get_engine(lg)
        engine_safe = ocr_backends.get_engine_safe(lg)
        for variant in detector.variants(
            arr, _CFG["max_variants"], _CFG["adv_preproc"]
        ):
            try:
                lines.extend(ocr_backends.run(engine, variant, lg))
            except Exception as e:
                last_err = str(e)
                try:
                    lines.extend(ocr_backends.run(engine_safe, variant, lg))
                except Exception as e2:
                    last_err = str(e2)
            if (lang or "").strip().lower() == "auto" and len(lines) >= _CFG[
                "variant_min_lines"
            ]:
                break
        if (lang or "").strip().lower() == "auto" and len(lines) >= _CFG[
            "auto_min_lines"
        ]:
            break
    return lines, last_err


def backend_recognize(name: str, arr: np.ndarray, lang: str):
    """Run a non-paddle backend through the registry. Returns (lines, error)."""
    be = ocr_backends.get_backend(name)
    if be is None:
        return [], f"unknown backend '{name}'"
    ok, reason = be.available()
    if not ok:
        return [], reason
    try:
        paddle = ocr_backends.get_backend("paddle")
        lines = be.recognize(
            arr, (lang or "en"), resolve_langs(lang), detect_fn=paddle.detect
        )
        return lines, ""
    except Exception as e:
        return [], str(e)


def collect_lines(arr: np.ndarray, lang: str):
    """Dispatch recognition to the configured backend.

    VAHINI_OCR_BACKEND = paddle | trocr | surya | chandra | auto
    Any non-paddle engine that is unavailable or returns nothing falls back to
    paddle, so the caller ALWAYS gets a usable result on this CPU-only box.
    """
    ocr_backend = _CFG["ocr_backend"]
    mode = (
        ocr_backend
        if ocr_backend
        in ("paddle", "trocr", "surya", "chandra", "paddleocr-vl", "auto")
        else "paddle"
    )
    compare = {}

    paddle_lines, paddle_err = collect_lines_paddle(arr, lang)
    if mode == "paddle":
        return paddle_lines, paddle_err, "paddle", compare

    if mode == "trocr":
        # TrOCR is a recogniser, not a detector/classifier. Keep paddle's
        # detection + printed/handwriting classification (which we trust), and
        # let TrOCR REFINE the handwriting text downstream (see
        # refine_handwriting_text). This avoids feeding the classifier TrOCR's
        # uncalibrated scores and confines TrOCR to what it's good at.
        return (
            paddle_lines,
            paddle_err,
            "trocr",
            {"strategy": "paddle-detect+classify, trocr-refine"},
        )

    if mode in ("surya", "chandra", "paddleocr-vl"):
        alt_lines, alt_err = backend_recognize(mode, arr, lang)
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
        alt_lines, alt_err = backend_recognize(name, arr, lang)
        if alt_lines:
            candidates.append((name, alt_lines, alt_err))

    scored = {}
    best = None  # (name, raw_lines, err, quality)
    for name, lns, err in candidates:
        proc = detector.region_filter_lines(
            detector.merge_lines(lns), arr.shape
        )
        q = detector.lines_quality(proc)
        scored[name] = {"quality": round(q, 2), "count": len(proc)}
        # pylint can't narrow best's type across the loop; the "best is None
        # or" short-circuit already guarantees best is a tuple here.
        # pylint: disable-next=unsubscriptable-object
        if best is None or q > best[3]:
            best = (name, lns, err, q)
    compare = {
        "mode": "auto",
        "scored": scored,
        "selected": best[0] if best else "paddle",
    }
    if best:
        return best[1], best[2], best[0], compare
    return paddle_lines, paddle_err, "paddle", compare


def refine_handwriting_text(
    raw_bytes: bytes, proc_arr: np.ndarray, hand_lines, backend_name: str
):
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
        full = np.array(computer_vision.decode_image(raw_bytes))
    except Exception:
        return

    ph = float(max(1, proc_arr.shape[0]))
    pw = float(max(1, proc_arr.shape[1]))
    oh, ow = full.shape[0], full.shape[1]
    sx, sy = ow / pw, oh / ph

    for l in hand_lines[:40]:
        box = l.get("box") or [0, 0, 0, 0]
        if len(box) < 4:
            continue
        x, y, w, h = [float(v) for v in box[:4]]
        padx = int(w * sx * 0.06) + 6
        pady = int(h * sy * 0.25) + 6
        x0 = max(0, int(x * sx) - padx)
        y0 = max(0, int(y * sy) - pady)
        x1 = min(ow, int((x + w) * sx) + padx)
        y1 = min(oh, int((y + h) * sy) + pady)
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
        if sim >= _CFG["refine_min_sim"]:
            l["text"] = cand
            l["refined_by"] = backend_name


def extract_hand_lines(
    arr: np.ndarray,
    raw_lines,
    raw_bytes: bytes = None,
    refine_backend: str = None,
):
    """Shared post-processing: merge → region-filter → classify printed vs
    handwriting → keep handwriting, minus OCR noise fragments → optionally refine
    handwriting text with a stronger engine. Returns (all_lines, hand_lines).
    """
    lines = detector.region_filter_lines(
        detector.merge_lines(raw_lines), arr.shape
    )
    classify.classify_lines(arr, lines)
    hand_lines = detector.prefer_handwritten(lines)
    cleaned = [l for l in hand_lines if not detector.is_noise_line(l)]
    # Fail-open: never empty the set just because noise filtering was strict.
    if cleaned:
        hand_lines = cleaned
    if refine_backend == "trocr" and raw_bytes:
        refine_handwriting_text(raw_bytes, arr, hand_lines, refine_backend)
    return lines, hand_lines


def align_to_expected(hand_lines, expected_text):
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
    exp_lines = [
        s.strip()
        for s in re.split(r"[\r\n]+", expected_text or "")
        if s.strip()
    ]
    if not exp_lines or not hand_lines:
        return None

    def _norm(s):
        return re.sub(
            r"\s+", " ", re.sub(r"[^\w ]", "", str(s or "").lower())
        ).strip()

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
            hl["text"] = exp_lines[
                best_i
            ]  # show the known target, not garbled OCR
            matches.append(best_r)

    if not matches:
        return {
            "passage_lines": len(exp_lines),
            "aligned": 0,
            "passage_match": 0.0,
        }
    return {
        "passage_lines": len(exp_lines),
        "aligned": len(matches),
        "passage_match": round(sum(matches) / len(matches), 3),
    }
