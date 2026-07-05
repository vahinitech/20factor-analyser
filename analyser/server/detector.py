# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies. Server-side handwriting/print recognition.
# Third-party: PaddleOCR (Apache-2.0). See /THIRD-PARTY-NOTICES.md and server/README.md
#
# detector.py — finding and cleaning up candidate text regions.
#
# Everything here operates on OCR "line" dicts (text/box/poly/score/
# printed_hint) or on raw pixels for preprocessing variants. Nothing here
# knows which OCR engine produced a line or how the 20-factor score is
# computed; it only decides which regions are worth keeping and whether a
# region looks like printed text versus handwriting.

import hashlib
import re

import numpy as np
from PIL import Image, ImageOps, ImageFilter

try:
    import cv2
except Exception:
    cv2 = None


def variants(arr: np.ndarray, max_variants: int, adv_preproc: bool):
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
    if emitted >= max_variants:
        return

    # Variant 1: local-contrast enhancement (+ denoise/CLAHE) for faint strokes.
    g = ImageOps.autocontrast(base.convert("L"), cutoff=1).filter(
        ImageFilter.SHARPEN
    )
    if cv2 is not None and adv_preproc:
        gv = np.array(g)
        gv = cv2.fastNlMeansDenoising(
            gv, None, h=10, templateWindowSize=7, searchWindowSize=21
        )
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gv = clahe.apply(gv)
        g = Image.fromarray(gv)
    v = _fresh(np.array(g.convert("RGB")))
    if v is not None:
        yield v
        emitted += 1
    if emitted >= max_variants:
        return

    # Variant 2: adaptive threshold path helps on uneven lighting/shadows.
    if cv2 is not None and adv_preproc:
        gray = cv2.cvtColor(np.array(base), cv2.COLOR_RGB2GRAY)
        thr = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )
        v = _fresh(np.dstack([thr, thr, thr]))
        if v is not None:
            yield v
            emitted += 1
        if emitted >= max_variants:
            return

    # Variant 3: upscale small captures so the recogniser sees more detail.
    if min(base.size) < 1200:
        up = base.resize(
            (int(base.width * 1.8), int(base.height * 1.8)),
            Image.Resampling.BICUBIC,
        )
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


def looks_printed(text: str, score: float, box=None) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    clean = len(re.sub(r"[^\wఀ-౿]", "", t)) / max(1, len(t))
    alpha = len(re.findall(r"[A-Za-z]", t))
    upper_ratio = (
        (len(re.findall(r"[A-Z]", t)) / max(1, alpha)) if alpha else 0.0
    )
    digit_ratio = len(re.findall(r"\d", t)) / max(1, len(t))
    form_kw = bool(
        re.search(
            r"\b(name|address|date|age|sex|case|doctor|diagnosis|admission|"
            r"procedure|phone|id|form|hospital)\b",
            low,
        )
    )
    # Printed headers/forms are often high confidence, all-caps, dense and horizontally long.
    aspect = 0.0
    if box and len(box) >= 4:
        bw = float(max(1.0, box[2]))
        bh = float(max(1.0, box[3]))
        aspect = bw / bh
    return bool(
        (
            score >= 0.985
            and len(t) >= 8
            and clean >= 0.88
            and (upper_ratio >= 0.62 or form_kw)
        )
        or (
            score >= 0.975
            and form_kw
            and (digit_ratio >= 0.10 or aspect >= 9.0)
        )
        or (score >= 0.992 and aspect >= 11.0 and len(t) >= 12)
    )


def merge_lines(lines):
    kept = []
    for line in sorted(
        lines, key=lambda l: float(l.get("score", 0.0)), reverse=True
    ):
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


def region_filter_lines(lines, arr_shape):
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
        if (
            (y_ratio < 0.14 or y_ratio > 0.90)
            and aspect > 8.0
            and (bool(l.get("printed_hint")) or sc > 0.75)
        ):
            continue

        # Remove long numeric/id strips; these are not handwriting quality evidence.
        digit_ratio = len(re.findall(r"\d", t)) / max(1, len(t))
        if (
            digit_ratio > 0.50
            and len(t) >= 6
            and (
                aspect > 4.0
                or bool(re.search(r"\b(ip|op|id|no\.?|ph|phone)\b", low))
            )
        ):
            continue

        out.append(l)

    return out if out else lines


def prefer_handwritten(lines):
    """Keep handwriting, drop printed text. Strictly.

    The printed/handwriting decision comes from classify.classify_lines
    (real stroke-width / glyph-height / edge / confidence CV features), set on
    each line as `printed_hint`. The analyser's rule of thumb is that printed
    text is NEVER analysed: it must not reach the factor measurements, the
    reference crops, or the recognition showcase. A page that is entirely
    printed therefore returns an empty list, and the server reports that no
    handwriting was found instead of quietly scoring machine type. (The old
    fail-open that kept every line when handwriting was scarce is exactly how
    printed forms polluted real reports.)
    """
    if not lines:
        return []
    return [l for l in lines if not bool(l.get("printed_hint"))]


def lines_quality(lines):
    if not lines:
        return -1e9
    texts = [str(l.get("text", "") or "").strip() for l in lines]
    texts = [t for t in texts if t]
    if not texts:
        return -1e9
    words = sum(len(t.split()) for t in texts)
    chars = sum(len(t) for t in texts)
    short_noise = sum(1 for t in texts if len(t) <= 2)
    digit_heavy = sum(
        1 for t in texts if (len(re.findall(r"\d", t)) / max(1, len(t))) > 0.55
    )
    avg_conf = sum(float(l.get("score", 0.0) or 0.0) for l in lines) / max(
        1, len(lines)
    )
    return float(
        chars
        + 2.5 * words
        + 12.0 * avg_conf
        - 5.0 * short_noise
        - 3.0 * digit_heavy
    )


def is_noise_line(l):
    """Single-char / punctuation-only fragments are OCR noise, not handwriting
    evidence (e.g. a stray 'e' or '2.')."""
    t = str(l.get("text", "") or "").strip()
    if len(t) < 2:
        return True
    if not re.search(r"[A-Za-z0-9ఀ-౿]", t):
        return True
    return False
