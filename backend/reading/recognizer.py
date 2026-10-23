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
import unicodedata

import numpy as np

import config
from languages import tags as lang_tags
from reading import ocr_backends
from reading import classify
from reading import detector
from vision import computer_vision
from reading import layout_filter
from reading import line_recovery
from reading import escalation
from server import perf
from languages import graphemes, ladders, stages

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


def configure(**kwargs):
    """Set the recognizer's dispatch config once at startup. Unknown keys
    are ignored so callers can pass a superset of _CFG."""
    for k, v in kwargs.items():
        if k in _CFG:
            _CFG[k] = v


def resolve_langs(lang: str):
    req = lang_tags.engine_langs(lang)
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
        # The safe engine is a second copy of the reader's models, used only
        # when the normal engine cannot read, so it is built only then: when
        # the normal engine failed to build, or failed on a variant (#173).
        engine_safe, safe_tried = None, False
        if engine is None:
            engine_safe, err_safe = _build_engine(
                ocr_backends.get_engine_safe, lg
            )
            safe_tried = True
            if err_safe:
                last_err = err_safe
            if engine_safe is None:
                continue  # try the next configured language
        for variant in detector.variants(
            arr, _CFG["max_variants"], _CFG["adv_preproc"]
        ):
            got = False
            if engine is not None:
                try:
                    perf.count("reader_calls")
                    lines.extend(ocr_backends.run(engine, variant, lg))
                    got = True
                except Exception as e:
                    last_err = str(e)
            if not got and not safe_tried:
                # The variant's error stays the one reported, as when the
                # safe engine was built before the variants were read.
                engine_safe, _err = _build_engine(
                    ocr_backends.get_engine_safe, lg
                )
                safe_tried = True
            if not got and engine_safe is not None:
                try:
                    perf.count("reader_calls")
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
        with perf.stage("detect." + name):
            lines = be.recognize(
                arr,
                (lang or "en"),
                resolve_langs(lang),
                detect_fn=paddle.detect,
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
    # config.load() refuses any other value at start-up; this guard only
    # covers a caller that set _CFG directly.
    mode = ocr_backend if ocr_backend in config.OCR_BACKENDS else "paddle"
    compare = {}

    with perf.stage("detect", pixels=int(arr.shape[0] * arr.shape[1])):
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

    In "hybrid" mode, route by script, as backend/languages/stages.json
    says: Telugu, Hindi, Tamil, Kannada and Malayalam go to Surya, and
    Latin, the script of any language the table does not name, goes to
    TrOCR. Only Telugu is currently auto-detected per line (see
    ocr_backends._TELUGU); other Indic scripts route to Surya when the
    request itself was made with that `lang=`. The route depends on the
    line's language and the committed table only, never on how fast an
    engine has been (#112). Any other mode (e.g. "trocr") uses that single
    named engine for every line, unchanged from before.
    """
    if backend_name != "hybrid":
        return backend_name
    return stages.table().refine_engine(line_lang or "en")


def _crop_reader(raw_bytes, proc_arr, turn=0):
    """crop_for(line) for the escalation loop: the line's box cut from the
    FULL-RESOLUTION original (paddle's working image is downscaled, and
    the full image reads materially better), padded 6% across and 25% up
    and down plus 6 px. The photo is decoded on the first crop asked for.
    None for a line with no usable box, or when the photo cannot be
    decoded: such a line keeps the reader's reading, as it always has.
    turn: the page's turn to upright (page_turn.py), as the working copy
    had it."""
    ph = float(max(1, proc_arr.shape[0]))
    pw = float(max(1, proc_arr.shape[1]))
    full = []

    def crop_for(line):
        if not full:
            try:
                with perf.stage("decode.full") as step:
                    full.append(
                        np.array(computer_vision.decode_image(raw_bytes, turn))
                    )
                    step.size(pixels=full[0].shape[0] * full[0].shape[1])
            except Exception:
                full.append(None)
        img = full[0]
        box = line.get("box") or [0, 0, 0, 0]
        if img is None or len(box) < 4:
            return None
        oh, ow = img.shape[0], img.shape[1]
        sx, sy = ow / pw, oh / ph
        x, y, w, h = [float(v) for v in box[:4]]
        padx = int(w * sx * 0.06) + 6
        pady = int(h * sy * 0.25) + 6
        x0 = max(0, int(x * sx) - padx)
        y0 = max(0, int(y * sy) - pady)
        x1 = min(ow, int((x + w) * sx) + padx)
        y1 = min(oh, int((y + h) * sy) + pady)
        if x1 <= x0 or y1 <= y0:
            return None
        return img[y0:y1, x0:x1]

    return crop_for


def _guard(lower, text, conf):
    return escalation.trusted(
        lower, text, conf, _CFG["refine_min_sim"], _CFG["refine_min_conf"]
    )


def refine_handwriting_text(
    raw_bytes: bytes,
    proc_arr: np.ndarray,
    hand_lines,
    backend_name: str,
    turn: int = 0,
):
    """Send each handwriting line up its ladder (backend/languages/
    ladders.json, escalation.py) and keep a higher rung's text when
    EITHER holds:
      - it roughly agrees with the lower rung's reading, or
      - the higher engine's OWN confidence is high.

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
    confidence path.)

    The ladders for paddle, trocr and hybrid mode give every line the
    engines it got before them: paddle alone, TrOCR, or TrOCR for Latin
    and Surya for the Indic scripts. Every handwriting line (up to 40) is
    re-read, every time: the engines used to be skipped after one slow
    line, so the text read from one photo depended on server load (#112).
    A line that needs an engine that cannot answer refuses the page
    (escalation.RungDown); it is never left with the lower reading
    instead. Calls are still timed for /health's adaptive_engine_speed,
    which is information only.
    """
    escalation.climb(
        hand_lines,
        backend_name,
        (
            _crop_reader(raw_bytes, proc_arr, turn)
            if raw_bytes
            else lambda _l: None
        ),
        _guard,
    )


def extract_hand_lines(
    arr: np.ndarray,
    raw_lines,
    raw_bytes: bytes = None,
    refine_backend: str = None,
    read_region=None,
    turn: int = 0,
):
    """Shared post-processing: merge repeated readings → region-filter →
    drop non-text-ink layout regions (image/figure/chart/seal) → read the
    writing the detector missed (when read_region is given) → classify
    printed vs handwriting → keep handwriting, minus OCR noise fragments →
    join the pieces of each line → optionally refine handwriting text
    with a stronger engine. Returns (all_lines, hand_lines).

    read_region(crop, lang) -> lines | None is the scan's own reader
    (ocr_backends.read_region); see line_recovery.py. turn: how far the
    working copy was turned to stand upright (page_turn.py), applied to
    the full-size photo the same way.
    """
    with perf.stage("merge", lines=len(raw_lines)):
        lines = detector.region_filter_lines(
            detector.merge_lines(raw_lines), arr.shape
        )
    with perf.stage("layout", lines=len(lines)):
        lines = layout_filter.filter_excluded_regions(
            lines, layout_filter.excluded_regions(arr)
        )
    if read_region is not None and lines:
        lang = str(lines[0].get("lang") or "en")
        with perf.stage("recovery", lines=len(lines)):
            lines = line_recovery.add_missed(arr, lines, read_region, lang)
    with perf.stage("printed", lines=len(lines)):
        classify.classify_lines(arr, lines)
        hand_lines = detector.prefer_handwritten(lines)
        cleaned = [l for l in hand_lines if not detector.is_noise_line(l)]
        # Fail-open: never empty the set because noise filtering was strict.
        if cleaned:
            hand_lines = cleaned
    with perf.stage("join", lines=len(hand_lines)):
        hand_lines = detector.join_row_pieces(hand_lines)
    if refine_backend in ladders.MODES:
        refine_handwriting_text(
            raw_bytes, arr, hand_lines, refine_backend, turn
        )
    return lines, hand_lines


# Telugu handwriting is not read yet. On 60 handwritten Telugu pages
# (IIIT-INDIC-HW-WORDS, 2026-10-19) the Telugu reader returned 395 Latin
# letters against 123 Telugu ones ("es aons", "aase"), and the server still
# built a full report from them. A page asked for as Telugu (lang "te", not
# with "en") is refused unless at least three in four of the letters read
# are Telugu and the reader's mean confidence is 0.80 or more. The pages
# that were mostly Telugu letters still read at 0.61 to 0.70 and lost half
# their lines ("గవం నింబారు" for "గమనించారు సబ్జెక్టులో"); printed Telugu
# reads at 0.96 to 1.0. The line tag cannot decide this: ocr_backends tags
# every line the Telugu reader read as "te", Latin or not, and under "auto"
# that reader also runs on short English pages. So only the request turns
# the check on, and English and "auto" scans are unchanged.
TELUGU_MIN_SHARE = 0.75
TELUGU_MIN_CONFIDENCE = 0.80
_TELUGU_CHAR = re.compile(r"[\u0C00-\u0C7F]")
_LATIN_CHAR = re.compile(r"[A-Za-z]")


def telugu_not_read(lang, hand_lines):
    """Return the letter counts when a page asked for as Telugu was not
    really read, or None when it passes or was not asked for as Telugu.
    Lines with no text were not read at all (cv-fallback, or rows found
    from the ink); a page of only those keeps its own path."""
    asked = set(lang_tags.engine_langs(str(lang or "")).split(","))
    if "te" not in asked or "en" in asked:
        return None
    read = [l for l in hand_lines if str(l.get("text") or "").strip()]
    if not read:
        return None
    text = " ".join(str(l["text"]) for l in read)
    telugu = len(_TELUGU_CHAR.findall(text))
    latin = len(_LATIN_CHAR.findall(text))
    confidence = sum(float(l.get("score") or 0.0) for l in read) / len(read)
    if (
        telugu
        and telugu >= TELUGU_MIN_SHARE * (telugu + latin)
        and confidence >= TELUGU_MIN_CONFIDENCE
    ):
        return None
    return {
        "telugu_letters": telugu,
        "latin_letters": latin,
        "reading_confidence": round(confidence, 3),
    }


# A maths, accounts or number page is not a writing page. Children scan
# their maths and science notebooks, and the check used to score sums and
# formulas as if they were sentences: the factors count letters, words and
# word gaps, so a page of "3x4=12" gave a report about nothing it could
# measure. A page is refused when digits and maths signs make up at least
# 35% of what was read. On the 200 GNHK pages (2026-10-19 readings, lang
# auto and en) the four pages at or above that were a shopping list with
# prices, an accounting journal, an address and an unreadable scrap; no
# page written in sentences reached it (below them: a three-letter scrap
# at 0.33, then mixed notes and a measurement list at 0.25 and less,
# all still scored). A page with
# fewer than 12 such characters read is too short to judge and keeps its
# own path. Letters include combining marks, so Telugu vowel signs count
# as letters, not as symbols.
NUMBERS_MAX_SHARE = 0.35
NUMBERS_MIN_CHARS = 12
_MATHS_SIGNS = frozenset("+=×÷*/^<>√π∑∫%")


def not_writing_page(hand_lines):
    """Return the counts when the page read is mostly numbers and sums,
    or None when it is a writing page or too short to judge. Lines with
    no text (cv-fallback, rows found from the ink) carry no reading and
    are not judged."""
    letters = numbers = 0
    for line in hand_lines:
        for ch in str(line.get("text") or ""):
            if unicodedata.category(ch)[0] in "LM":
                letters += 1
            elif ch.isdigit() or ch in _MATHS_SIGNS:
                numbers += 1
    counted = letters + numbers
    if counted < NUMBERS_MIN_CHARS:
        return None
    if numbers < NUMBERS_MAX_SHARE * counted:
        return None
    return {
        "page_kind": "maths",
        "letters_read": letters,
        "numbers_read": numbers,
    }


_WORD = re.compile(r"\w")


def _match_units(text):
    """The graphemes a passage line is compared by: NFC, lower case,
    letters, digits and their marks, one space between words. Python's
    \\w does not match combining marks, so the old \\w-only filter
    dropped every vowel sign and virama: పిల్లి compared as పలల and
    a missing vowel sign was invisible (#209). Latin text gives one unit
    per letter, so English matches are what they were."""
    text = unicodedata.normalize("NFC", str(text or "")).lower()
    kept = "".join(
        ch
        for ch in text
        if ch == " "
        or _WORD.match(ch)
        or unicodedata.category(ch).startswith("M")
    )
    return graphemes.split(re.sub(" +", " ", kept).strip())


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

    matches = []
    for hl in hand_lines:
        rec = _match_units(hl.get("text", ""))
        if not rec:
            continue
        best_i, best_r = -1, 0.0
        for i, el in enumerate(exp_lines):
            r = difflib.SequenceMatcher(None, rec, _match_units(el)).ratio()
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
