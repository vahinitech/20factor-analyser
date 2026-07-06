# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies. Server-side handwriting/print recognition.
# Third-party: PaddleOCR (Apache-2.0). See /THIRD-PARTY-NOTICES.md and backend/README.md
#
# recognizer.py — orchestrates recognition across OCR backends.
#
# Resolves the language list, dispatches to the configured backend
# (paddle/trocr/surya/hybrid/auto, falling back to paddle when an
# alternative engine is unavailable or empty), and post-processes the
# result: merge/filter candidate regions, classify printed vs handwriting,
# optionally refine handwriting text with a stronger engine, and align
# recognised lines to a known reference passage. Nothing here decodes
# images or computes the 20-factor score; it only turns OCR backends into
# a clean list of handwriting lines.
#
# Why "hybrid": paddle (PP-OCRv5) reads printed text very well but is not a
# handwriting specialist, while trocr (English) and surya (Indic scripts)
# are. Rather than pick ONE engine for a whole page (which forfeits paddle's
# strength on the printed parts of a mixed page), hybrid mode always uses
# paddle to detect lines and classify printed vs handwriting, then re-reads
# ONLY the handwriting lines with the script-appropriate specialist — so a
# typical mixed form pays the specialist's per-line cost only on the
# smaller handwriting subset, not the whole page.

import difflib
import re
import time

import numpy as np

import ocr_backends
import classify
import detector
import computer_vision
import layout_filter

_CFG = {
    "ocr_langs": ["en"],
    "ocr_backend": "paddle",
    "max_variants": 2,
    "adv_preproc": True,
    "auto_min_lines": 3,
    "variant_min_lines": 3,
    "refine_min_sim": 0.70,
    "refine_min_conf": 0.75,
}

# Languages Surya is documented to handle well (Indic + English); anything
# else routes to TrOCR, which is an English-only handwriting checkpoint
# (microsoft/trocr-base-handwritten).
_INDIC_LANGS = {"te", "hi", "ta", "kn", "ml"}


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


def _build_engine(builder, lg: str):
    """Build one paddle engine, returning (engine|None, error). Engine
    construction can fail at REQUEST time — the first use of a language
    triggers a model download, which dies on an offline/blocked network,
    and an incompatible paddleocr build can refuse our kwargs. A scan must
    survive that, so construction never raises out of here."""
    try:
        return builder(lg), ""
    except Exception as e:
        return None, f"paddle engine init failed for '{lg}': {e}"


def collect_lines_paddle(arr: np.ndarray, lang: str):
    last_err = ""
    langs = resolve_langs(lang)
    lines = []
    for lg in langs:
        engine, err = _build_engine(ocr_backends.get_engine, lg)
        if err:
            last_err = err
        engine_safe, err_safe = _build_engine(ocr_backends.get_engine_safe, lg)
        if err_safe:
            last_err = err_safe
        if engine is None and engine_safe is None:
            continue  # try the next configured language
        for variant in detector.variants(
            arr, _CFG["max_variants"], _CFG["adv_preproc"]
        ):
            got = False
            if engine is not None:
                try:
                    lines.extend(ocr_backends.run(engine, variant, lg))
                    got = True
                except Exception as e:
                    last_err = str(e)
            if not got and engine_safe is not None:
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

    VAHINI_OCR_BACKEND = paddle | trocr | surya | hybrid | paddleocr-vl | auto
    Any non-paddle engine that is unavailable or returns nothing falls back to
    paddle, so the caller ALWAYS gets a usable result on this CPU-only box.
    """
    ocr_backend = _CFG["ocr_backend"]
    mode = (
        ocr_backend
        if ocr_backend
        in ("paddle", "trocr", "surya", "hybrid", "paddleocr-vl", "auto")
        else "paddle"
    )
    compare = {}

    paddle_lines, paddle_err = collect_lines_paddle(arr, lang)
    if mode == "paddle":
        return paddle_lines, paddle_err, "paddle", compare

    if mode in ("trocr", "hybrid"):
        # TrOCR/Surya are recognisers, not detectors/classifiers. Keep
        # paddle's detection + printed/handwriting classification (which we
        # trust), and let the specialist engine(s) REFINE the handwriting
        # text downstream (see refine_handwriting_text). This avoids feeding
        # the classifier an uncalibrated engine's scores and confines each
        # specialist to what it's good at. "trocr" mode always refines with
        # TrOCR; "hybrid" mode also routes Indic-script lines to Surya.
        strategy = (
            "paddle-detect+classify, trocr-refine"
            if mode == "trocr"
            else "paddle-detect+classify, trocr/surya-refine-by-script"
        )
        return paddle_lines, paddle_err, mode, {"strategy": strategy}

    if mode in ("surya", "paddleocr-vl"):
        alt_lines, alt_err = backend_recognize(mode, arr, lang)
        if alt_lines:
            return alt_lines, alt_err, mode, compare
        compare = {"requested": mode, "fallback": "paddle", "reason": alt_err}
        return paddle_lines, (paddle_err or alt_err), "paddle", compare

    # auto: score paddle against every available alternative, keep the best.
    candidates = [("paddle", paddle_lines, paddle_err)]
    for name in ("trocr", "surya", "paddleocr-vl"):
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


def _refine_engine_for_line(line_lang: str, backend_name: str) -> str:
    """Which registered engine should re-read a handwriting line.

    In "hybrid" mode, route by script: Surya is documented to handle Indic
    scripts well; TrOCR's checkpoint (microsoft/trocr-base-handwritten) is
    English-only, so anything else goes to TrOCR. Only Telugu is currently
    auto-detected per line (see ocr_backends._TELUGU); other Indic scripts
    route to Surya when the request itself was made with that `lang=`. Any
    other mode (e.g. "trocr") uses that single named engine for every line,
    unchanged from before.
    """
    if backend_name != "hybrid":
        return backend_name
    return "surya" if (line_lang or "en") in _INDIC_LANGS else "trocr"


def refine_handwriting_text(
    raw_bytes: bytes, proc_arr: np.ndarray, hand_lines, backend_name: str
):
    """Re-recognise each handwriting crop with a stronger, script-appropriate
    engine and accept its text when EITHER holds:
      - it roughly agrees with paddle's reading, or
      - the specialist engine's OWN confidence is high.

    Why two acceptance paths, not just agreement: TrOCR/Surya are
    language-model recognisers that produce excellent text on clear input
    ("manay ment" -> "management") but HALLUCINATE on out-of-distribution
    content ("Hypothyoidum" -> "Transportation legislation") — the agreement
    gate catches that. But paddle is not a handwriting specialist (that's
    the whole reason we're re-reading), so on genuinely hard handwriting its
    own reading can be badly wrong too; requiring the specialist to also
    agree with a wrong baseline would throw away real corrections. A
    confident specialist reading is trusted even when it disagrees with
    paddle. (The agreement check is Latin-only — non-Latin scripts strip to
    an empty string and always score 0 — so Indic refinements rely on the
    confidence path.) Crops are taken from the FULL-RESOLUTION original
    (paddle's working image is downscaled), which materially improves
    recognition.

    Adaptive to CPU speed: every call is timed and recorded via
    ocr_backends.record_engine_speed(). Once an engine measures slower than
    VAHINI_HYBRID_MAX_MS_PER_LINE, it is skipped for the rest of THIS page
    (keeping paddle's reading) and for VAHINI_HYBRID_RETRY_SEC afterwards —
    a real measured latency on this exact machine, not a synthetic
    benchmark or a manual "is this box fast?" setting. This is what makes
    hybrid mode safe to enable everywhere: a fast machine gets every
    handwriting line re-read, a slow one quietly behaves like plain paddle
    after the first slow measurement instead of stalling every scan.
    """
    try:
        full = np.array(computer_vision.decode_image(raw_bytes))
    except Exception:
        return

    ph = float(max(1, proc_arr.shape[0]))
    pw = float(max(1, proc_arr.shape[1]))
    oh, ow = full.shape[0], full.shape[1]
    sx, sy = ow / pw, oh / ph

    ready = {}  # engine name -> backend, or None if unavailable (cached)

    def _get_ready(name):
        if name not in ready:
            be = ocr_backends.get_backend(name)
            ok = False
            if be is not None and hasattr(be, "recognize_crop"):
                try:
                    ok, _reason = be.available()
                except Exception:
                    ok = False
            ready[name] = be if ok else None
        return ready[name]

    for l in hand_lines[:40]:
        engine_name = _refine_engine_for_line(l.get("lang"), backend_name)
        verdict = ocr_backends.engine_speed_verdict(engine_name)
        if verdict is not None and not verdict[1]:
            continue  # measured too slow on this machine recently; skip
        be = _get_ready(engine_name)
        if be is None:
            continue
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
        t0 = time.perf_counter()
        try:
            cand, conf = be.recognize_crop(crop)
        except Exception:
            continue
        # Only a successful call counts as a speed measurement — an
        # exception is a reliability problem, not a latency one, and
        # recording it here would let an instant crash look "fast".
        ocr_backends.record_engine_speed(
            engine_name, (time.perf_counter() - t0) * 1000.0
        )
        cand = (cand or "").strip()
        # TrOCR often appends a stray " ." — drop trailing isolated punctuation.
        cand = re.sub(r"\s*[.·,]+\s*$", "", cand).strip()
        if not cand:
            continue
        base = str(l.get("text", "") or "").strip()
        a = re.sub(r"[^a-z0-9]", "", base.lower())
        b = re.sub(r"[^a-z0-9]", "", cand.lower())
        sim = difflib.SequenceMatcher(None, a, b).ratio() if (a and b) else 0.0
        conf = float(conf or 0.0)
        if sim >= _CFG["refine_min_sim"] or conf >= _CFG["refine_min_conf"]:
            l["text"] = cand
            l["refined_by"] = engine_name


def extract_hand_lines(
    arr: np.ndarray,
    raw_lines,
    raw_bytes: bytes = None,
    refine_backend: str = None,
):
    """Shared post-processing: merge → region-filter → drop non-text-ink
    layout regions (image/figure/chart/seal) → classify printed vs
    handwriting → keep handwriting, minus OCR noise fragments → optionally
    refine handwriting text with a stronger engine. Returns (all_lines,
    hand_lines).
    """
    lines = detector.region_filter_lines(
        detector.merge_lines(raw_lines), arr.shape
    )
    lines = layout_filter.filter_excluded_regions(
        lines, layout_filter.excluded_regions(arr)
    )
    classify.classify_lines(arr, lines)
    hand_lines = detector.prefer_handwritten(lines)
    cleaned = [l for l in hand_lines if not detector.is_noise_line(l)]
    # Fail-open: never empty the set just because noise filtering was strict.
    if cleaned:
        hand_lines = cleaned
    if refine_backend in ("trocr", "hybrid") and raw_bytes:
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
