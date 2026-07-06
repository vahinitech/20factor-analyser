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


def fallback_line_regions(arr: np.ndarray, max_lines: int = 40):
    """OCR-free text-line detection, used when NO OCR engine could run
    (model weights unavailable/offline, engine init failure, missing
    backend). The 20 factors are measured from the geometry of the writing
    — not from reading the words — so a scan must still yield line regions
    (with empty text) instead of failing outright. Returns lines in the
    same shape the OCR backends produce."""
    h, w = arr.shape[:2]
    if h < 8 or w < 8:
        return []

    boxes = []
    if cv2 is not None:
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        ink = cv2.adaptiveThreshold(
            blur,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            31,
            9,
        )
        # Merge letters/words into line blobs: strong horizontal dilation.
        kx = max(12, w // 40)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kx, 3))
        blob = cv2.dilate(ink, kernel, iterations=1)
        n_labels, _, stats, _ = cv2.connectedComponentsWithStats(
            blob, connectivity=8
        )
        for i in range(1, n_labels):
            x = float(stats[i, cv2.CC_STAT_LEFT])
            y = float(stats[i, cv2.CC_STAT_TOP])
            bw = float(stats[i, cv2.CC_STAT_WIDTH])
            bh = float(stats[i, cv2.CC_STAT_HEIGHT])
            area = float(stats[i, cv2.CC_STAT_AREA])
            # Keep line-shaped regions; drop specks and page-scale blobs.
            if bw < w * 0.03 or bh < 6 or area < 40:
                continue
            if bh > h * 0.5 or (bw > w * 0.98 and bh > h * 0.25):
                continue
            boxes.append([x, y, bw, bh])
    else:
        # No OpenCV: luminance threshold + row-projection line segmentation.
        gray = np.dot(arr[..., :3], [0.299, 0.587, 0.114]).astype(np.float32)
        ink = gray < float(np.mean(gray) - 15.0)
        row_frac = ink.mean(axis=1)
        thr = max(0.004, float(np.percentile(row_frac, 75)) * 0.5)
        y0 = None
        for y in range(h + 1):
            on = y < h and row_frac[y] > thr
            if on and y0 is None:
                y0 = y
            elif not on and y0 is not None:
                if y - y0 >= 6:
                    cols = np.where(ink[y0:y].any(axis=0))[0]
                    if cols.size >= 2:
                        boxes.append(
                            [
                                float(cols[0]),
                                float(y0),
                                float(cols[-1] - cols[0] + 1),
                                float(y - y0),
                            ]
                        )
                y0 = None

    boxes.sort(key=lambda b: (b[1], b[0]))
    out = []
    for x, y, bw, bh in boxes[:max_lines]:
        poly = [[x, y], [x + bw, y], [x + bw, y + bh], [x, y + bh]]
        out.append(
            {
                "text": "",
                "poly": poly,
                "box": [x, y, bw, bh],
                "score": 0.0,
                "lang": "en",
                "printed_hint": False,
                "cv_fallback": True,
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


def _factor_region_map(arr: np.ndarray, regions, lines=None):
    # `regions` is the shared, area-ranked preview pool built by
    # _build_region_previews (capped for response size), used for every
    # factor's evidence pick below. `lines` is the FULL, unranked
    # handwriting-only line set _extract_features scores from; factor 10
    # (margin) needs it directly, see the override near the end of this
    # function, because a page with more lines than the pool cap can have
    # its true left-most line excluded from `regions` by the area ranking.
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
        ),  # left margin evidence: fallback only, see the override below
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

    # Margin evidence (factor 10) must show the page's actual left-most
    # line. Picking within `seq` alone is wrong on any page with more lines
    # than _build_region_previews' pool cap: the true left-most line can be
    # short (small area) and never make it into that area-ranked pool, so
    # the "left-most in the pool" pick silently becomes an arbitrary large
    # line instead. Search the full, unranked, already handwriting-only
    # `lines` directly when available.
    margin_url = None
    if lines:
        leftmost = min(
            lines,
            key=lambda l: float((l.get("box") or [1e9, 0, 0, 0])[0]),
            default=None,
        )
        if leftmost is not None:
            crop = _crop_rgb(arr, leftmost.get("box") or [0, 0, 0, 0])
            if crop is not None and crop.size:
                margin_url = _to_data_url(crop, quality=90)

    out = {}
    for n in range(1, 21):
        if n == 10 and margin_url:
            out["10"] = {
                "url": margin_url,
                "caption": labels.get(10, "factor evidence"),
            }
            continue
        idx = picks.get(n)
        if idx is None:
            url = fallback
        else:
            region = seq[int(max(0, min(idx, len(seq) - 1)))]
            # Never emit an empty reference image: every factor must carry
            # a usable crop, falling back to the whole-page preview.
            url = region.get("preview") or fallback
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


# --------------------------------------------------------------------------- #
# Writing style: print / semi-cursive / cursive (descriptive, never scored)
# --------------------------------------------------------------------------- #
# Deliberately not a graded factor: no curriculum treats cursive as more
# "correct" than print (many schools teach print-first and rarely touch
# cursive), so this is shown as context only, the same way document_type is,
# never as a target a page can fall short of. See docs/ARCHITECTURE.md.
_STYLE_MIN_LETTERS = 12  # below this much Latin-letter evidence, say nothing
_STYLE_CURSIVE_MAX = 0.45
_STYLE_PRINT_MIN = 0.75


def _line_ink_components(arr, box):
    """Connected ink blobs inside one detected line's box, left to right,
    as (x, y, w, h) boxes in full-image coordinates. A word where every
    letter is joined by connecting strokes collapses toward one blob per
    word; a word in disconnected print stays close to one blob per letter
    (or a little over, from a dotted i or crossed t). No merging dilation
    is applied here, unlike fallback_line_regions: that function MERGES
    letters into line blobs on purpose, which would destroy the very
    connectivity signal this one depends on. Returns None when the crop
    is too small to say anything reliable (see the height guard below),
    rather than a wrong guess."""
    if cv2 is None:
        return None
    crop = _crop_rgb(arr, box)
    if crop is None or crop.size == 0:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape[:2]
    # Below this, individual letter strokes are only a few pixels wide, so
    # any fixed-size threshold window merges neighbouring print letters
    # into one blob and reads as falsely "joined".
    if h < 16 or w < 6:
        return None
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    # Threshold window scales with the line's own height instead of a
    # fixed pixel count, so this behaves the same whether the source photo
    # was scaled to 800px or 2200px wide, or the line is short or tall.
    block = max(9, int(round(h * 0.6)) | 1)
    ink = cv2.adaptiveThreshold(
        blur,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        block,
        9,
    )
    n_labels, _, stats, _ = cv2.connectedComponentsWithStats(
        ink, connectivity=8
    )
    min_area = max(2.0, (h * w) * 0.0006)
    ox, oy = float(box[0]), float(box[1])
    comps = []
    for i in range(1, n_labels):
        if float(stats[i, cv2.CC_STAT_AREA]) < min_area:
            continue
        comps.append(
            (
                ox + float(stats[i, cv2.CC_STAT_LEFT]),
                oy + float(stats[i, cv2.CC_STAT_TOP]),
                float(stats[i, cv2.CC_STAT_WIDTH]),
                float(stats[i, cv2.CC_STAT_HEIGHT]),
            )
        )
    comps.sort(key=lambda c: c[0])
    return comps


def _line_ink_component_count(arr, box):
    comps = _line_ink_components(arr, box)
    return None if comps is None else len(comps)


def infer_writing_style(arr, lines):
    """Print, semi-cursive or cursive, from how many separate ink blobs
    each line's letters actually form, not from asking an OCR/VLM to
    guess. Requires enough Latin-letter text to have real evidence (see
    docs/ROADMAP.md: letterform-based signals in this codebase assume
    Latin script); returns confidence=0.0/style=None rather than a guess
    when there isn't enough."""
    total_letters = 0
    total_components = 0
    for l in lines:
        text = str(l.get("text", "") or "")
        n_letters = len(re.findall(r"[A-Za-z]", text))
        if n_letters < 3:
            continue
        box = l.get("box") or [0, 0, 0, 0]
        n_comp = _line_ink_component_count(arr, box)
        if n_comp is None:
            continue
        total_letters += n_letters
        total_components += n_comp

    if total_letters < _STYLE_MIN_LETTERS:
        return {
            "style": None,
            "confidence": 0.0,
            "joined_ratio": None,
            "basis_letters": total_letters,
        }

    ratio = float(total_components) / float(total_letters)
    if ratio <= _STYLE_CURSIVE_MAX:
        style = "cursive"
    elif ratio >= _STYLE_PRINT_MIN:
        style = "print"
    else:
        style = "semi_cursive"

    # More letters sampled and a ratio further from either boundary both
    # raise confidence; this is a starting calibration, not a claim of
    # measured accuracy, see docs/ROADMAP.md.
    evidence_conf = min(1.0, total_letters / 60.0)
    boundary_dist = min(
        abs(ratio - _STYLE_CURSIVE_MAX), abs(ratio - _STYLE_PRINT_MIN)
    )
    clarity_conf = min(1.0, boundary_dist / 0.15)
    confidence = round(0.35 + 0.65 * min(evidence_conf, clarity_conf), 2)

    return {
        "style": style,
        "confidence": confidence,
        "joined_ratio": round(ratio, 3),
        "basis_letters": total_letters,
    }


# --------------------------------------------------------------------------- #
# Ambiguous word spacing: a fixable mistake, never a style judgement
# --------------------------------------------------------------------------- #
# Both failure modes a handwriting coach watches for reduce to the same
# measurable event once ink is reduced to connected ink blobs: a gap INSIDE
# one word that grew close to the size of a real word-to-word gap. In
# disconnected (print) writing that is a letter-to-letter gap stretched too
# wide; in joined (cursive) writing it is an unplanned pen lift splitting
# one word's single blob into two. Either way the word risks reading as two
# separate words. This is a concrete, fixable mistake, unlike writing style
# itself, so it is reported as a finding (like a grammar check), not folded
# into a factor score and not judging print vs cursive.
_AMBIGUOUS_GAP_FRACTION = 0.55


def find_ambiguous_word_gaps(arr, lines, max_findings=3):
    """Flags specific words whose internal spacing looks like it could be
    misread as two words. Needs at least 3 genuine word-to-word gaps
    somewhere on the page to know what a real word gap looks like here;
    returns no findings rather than guessing when there isn't enough."""
    per_line = []
    all_word_gap_sizes = []
    for l in lines:
        text = str(l.get("text", "") or "")
        words = [w for w in re.split(r"\s+", text.strip()) if w]
        box = l.get("box") or [0, 0, 0, 0]
        comps = _line_ink_components(arr, box)
        if not comps or len(comps) < 2:
            continue
        gaps = [
            comps[i + 1][0] - (comps[i][0] + comps[i][2])
            for i in range(len(comps) - 1)
        ]
        # A line with only ONE recognised word (or none) has no word-break
        # of its own to exclude: every gap in it is a same-word candidate,
        # exactly the "manage" case this whole check exists for. It just
        # can't ALSO contribute a reference word-gap size, since it has no
        # genuine word boundary to measure.
        n_word_breaks = min(max(0, len(words) - 1), len(gaps))
        if n_word_breaks > 0:
            order = sorted(
                range(len(gaps)), key=gaps.__getitem__, reverse=True
            )
            word_break_idx = set(order[:n_word_breaks])
            all_word_gap_sizes.extend(gaps[i] for i in word_break_idx)
        else:
            word_break_idx = set()
        intra_idx = [i for i in range(len(gaps)) if i not in word_break_idx]
        if intra_idx:
            per_line.append(
                {"comps": comps, "gaps": gaps, "intra_idx": intra_idx}
            )

    if len(all_word_gap_sizes) < 3:
        return []

    ref = float(np.median(all_word_gap_sizes))
    if ref <= 1.0:
        return []

    candidates = []
    for entry in per_line:
        comps, gaps = entry["comps"], entry["gaps"]
        for i in entry["intra_idx"]:
            g = gaps[i]
            if g < _AMBIGUOUS_GAP_FRACTION * ref:
                continue
            x0, x1 = comps[i][0], comps[i + 1][0] + comps[i + 1][2]
            y0 = min(comps[i][1], comps[i + 1][1])
            y1 = max(
                comps[i][1] + comps[i][3], comps[i + 1][1] + comps[i + 1][3]
            )
            pad = max(4.0, (y1 - y0) * 0.15)
            candidates.append(
                {
                    "gap_ratio": round(g / ref, 2),
                    "box": [
                        x0 - pad,
                        y0 - pad,
                        (x1 - x0) + 2 * pad,
                        (y1 - y0) + 2 * pad,
                    ],
                }
            )

    candidates.sort(key=lambda c: c["gap_ratio"], reverse=True)
    findings = []
    for c in candidates[:max_findings]:
        crop = _crop_rgb(arr, c["box"])
        if crop is None or crop.size == 0:
            continue
        findings.append(
            {
                "gap_ratio": c["gap_ratio"],
                "crop_url": _to_data_url(crop, quality=88),
            }
        )
    return findings


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
    context["writing_style"] = infer_writing_style(arr, lines)
    regions = _build_region_previews(arr, lines)
    factor_regions = _factor_region_map(arr, regions, lines)
    return {
        "document_context": context,
        "layout": layout,
        "regions": regions,
        "factor_regions": factor_regions,
        "ambiguous_word_gaps": find_ambiguous_word_gaps(arr, lines),
    }
