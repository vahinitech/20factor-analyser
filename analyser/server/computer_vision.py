# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Computer-vision algorithms for the recognition server.

Everything here operates on raw pixels: decoding an upload (image or PDF)
to a numpy array, cropping and JPEG-encoding evidence previews, and the
layout/document-context signals shown in the "context-aware" report
section. Nothing in this module knows about OCR engines or the 20-factor
scoring model; it only turns bytes into arrays and arrays into previews.
"""

import io
import re
import base64

import numpy as np
from PIL import Image

from geometry import clamp_box

try:
    import cv2
except Exception:  # pragma: no cover - cv2 optional
    cv2 = None


# --------------------------------------------------------------------------- #
# Decoding an upload (image or PDF) to a working array
# --------------------------------------------------------------------------- #
def _pdf_first_page(raw: bytes) -> Image.Image:
    """Render ONLY the first page of a PDF to an image. Multi-page PDFs are
    intentionally restricted to page 1 (the analyser scores a single
    handwriting page); the rest are ignored."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(raw)
    try:
        page = pdf[0]
        # ~150 DPI (scale = 150/72) is plenty for handwriting OCR.
        bitmap = page.render(scale=150.0 / 72.0)
        return bitmap.to_pil().convert("RGB")
    finally:
        pdf.close()


def decode_image(raw: bytes) -> Image.Image:
    """Decode an upload to an RGB PIL image. Accepts normal images and PDFs;
    for a PDF only the first page is used."""
    if raw[:4] == b"%PDF":
        return _pdf_first_page(raw)
    return Image.open(io.BytesIO(raw)).convert("RGB")


def to_numpy(raw: bytes, max_side: int = 2200) -> np.ndarray:
    """Decode an upload and downscale it so its longest side is at most
    `max_side` (the caller passes the server's configured limit)."""
    img = decode_image(raw)
    w, h = img.size
    m = max(w, h)
    if m > max_side:
        scale = max_side / float(m)
        img = img.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            Image.Resampling.LANCZOS,
        )
    return np.array(img)


# --------------------------------------------------------------------------- #
# Crops and JPEG previews (evidence images shown on the report)
# --------------------------------------------------------------------------- #
def _to_data_url(rgb_arr: np.ndarray, quality: int = 82) -> str:
    img = Image.fromarray(rgb_arr.astype(np.uint8), mode="RGB")
    buf = io.BytesIO()
    img.save(
        buf,
        format="JPEG",
        quality=int(max(35, min(95, quality))),
        optimize=True,
    )
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _crop_rgb(arr: np.ndarray, box):
    x, y, w, h = box
    box_px = clamp_box(x, y, w, h, arr.shape[1], arr.shape[0])
    if box_px is None:
        return None
    x0, y0, x1, y1 = box_px
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
        return float(max(0.0, b[2] if len(b) >= 3 else 0.0)) * float(
            max(0.0, b[3] if len(b) >= 4 else 0.0)
        )

    ranked = sorted(lines, key=_area, reverse=True)
    out = []
    for idx, l in enumerate(ranked[:max_regions]):
        box = l.get("box") or [0, 0, 0, 0]
        crop = _crop_rgb(arr, box)
        if crop is None or crop.size == 0:
            continue
        out.append(
            {
                "id": f"line_{idx+1}",
                "type": "line",
                "text": l.get("text", ""),
                "score": float(l.get("score", 0.0)),
                "bbox": [
                    float(box[0]),
                    float(box[1]),
                    float(box[2]),
                    float(box[3]),
                ],
                "preview": _to_data_url(crop, quality=90),
            }
        )
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
            small = np.array(
                Image.fromarray(arr).resize((nw, nh), Image.Resampling.BICUBIC)
            )
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
            str(n): {
                "url": fallback,
                "caption": labels.get(n, "factor evidence"),
            }
            for n in range(1, 21)
        }

    feats = []
    for i, r in enumerate(seq):
        b = r.get("bbox") or [0.0, 0.0, 0.0, 0.0]
        x, y, w, h = [float(v) for v in b]
        txt = str(r.get("text", "") or "")
        sc = float(r.get("score", 0.0) or 0.0)
        area = max(1.0, w * h)
        feats.append(
            {
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
                "digit_ratio": (
                    (len(re.findall(r"\d", txt)) / max(1, len(txt)))
                    if txt
                    else 0.0
                ),
                "preview": r.get("preview", ""),
            }
        )

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
    def compact(f):
        return f["area"] <= mean_area * 0.85 and f["h"] <= mean_h * 1.15

    def longline(f):
        return f["aspect"] >= 5.0 or f["text_len"] >= 16

    def spaced(f):
        return f["space_count"] >= 2

    def wordish(f):
        return f["space_count"] == 0 and f["text_len"] >= 4

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
        10: pick(
            None, key=lambda f: -f["x"], reverse=True
        ),  # left margin evidence
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


# --------------------------------------------------------------------------- #
# Layout signals + the "context-aware" document-type inference
# --------------------------------------------------------------------------- #
def _layout_features(arr: np.ndarray):
    h, w = arr.shape[:2]
    if h <= 1 or w <= 1:
        return {
            "line_density": 0.0,
            "block_density": 0.0,
            "layout_complexity": 0.0,
            "cc_count": 0,
        }

    if cv2 is None:
        # Fallback without OpenCV: use simple luminance threshold.
        gray = np.dot(arr[..., :3], [0.299, 0.587, 0.114]).astype(np.float32)
        thr = float(np.mean(gray) - 15.0)
        ink = (gray < thr).astype(np.uint8)
        row_frac = ink.mean(axis=1)
        line_density = float(
            np.mean(row_frac > max(0.01, np.percentile(row_frac, 70)))
        )
        block_density = float(np.mean(ink))
        return {
            "line_density": line_density,
            "block_density": block_density,
            "layout_complexity": float(
                min(1.0, (line_density * 0.65 + block_density * 1.4))
            ),
            "cc_count": int(max(1, line_density * h * 0.6)),
        }

    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    thr = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 9
    )

    row_frac = (thr > 0).mean(axis=1)
    line_density = float(
        np.mean(row_frac > max(0.01, np.percentile(row_frac, 70)))
    )
    block_density = float(np.mean(thr > 0))

    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(
        thr, connectivity=8
    )
    areas = (
        stats[1:, cv2.CC_STAT_AREA]
        if num_labels > 1
        else np.array([], dtype=np.int32)
    )
    valid = areas[(areas >= 12) & (areas <= max(18, int(h * w * 0.04)))]
    cc_count = int(valid.size)

    complexity = float(
        min(
            1.0,
            (0.45 * line_density)
            + (1.15 * block_density)
            + (0.00045 * cc_count),
        )
    )

    return {
        "line_density": line_density,
        "block_density": block_density,
        "layout_complexity": complexity,
        "cc_count": cc_count,
    }


def _infer_doc_context(lines, layout):
    n_lines = len(lines)
    texts = [
        str(l.get("text", "")).strip()
        for l in lines
        if str(l.get("text", "")).strip()
    ]
    full = " ".join(texts)
    avg_len = (sum(len(t) for t in texts) / len(texts)) if texts else 0.0
    digits_ratio = 0.0
    if full:
        digits_ratio = len(re.findall(r"\d", full)) / max(1, len(full))

    has_salutation = bool(
        re.search(r"\b(dear|respected|sir|madam)\b", full, re.IGNORECASE)
    )
    has_signoff = bool(
        re.search(r"\b(thanks|regards|sincerely|yours)\b", full, re.IGNORECASE)
    )
    has_form_fields = bool(
        re.search(
            r"\b(name|date|address|phone|dob|id)\b\s*[:\-]",
            full,
            re.IGNORECASE,
        )
    )

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
    elif (
        n_lines >= 10
        and avg_len > 16
        and layout.get("layout_complexity", 0.0) > 0.42
    ):
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


def vl_analyze(arr: np.ndarray, lines):
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
