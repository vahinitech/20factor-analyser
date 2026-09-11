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
from PIL import Image, ImageOps, ImageDraw

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
    with Image.open(io.BytesIO(raw)) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


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
    """Locate score inputs in the full handwriting set, never the preview cap.

    Boxes use processed-image pixels, the same space as hand_lines/proc_w/h.
    A context crop is not proof of a local defect. In particular, OCR proxies
    and composite scores cannot identify an exact faulty character.
    """
    # Reuse the scorer's row grouping and camera-tilt correction so evidence
    # selection follows the measurements that produced the report.
    from scoring import (
        _group_lines_by_rows,
        _page_tilt_degrees,
        _detilted_left_x,
    )

    height, width = arr.shape[:2]
    source = (
        lines
        if lines is not None
        else [{**r, "box": r.get("bbox")} for r in regions]
    )
    accepted = []
    for item in source:
        box = item.get("box")
        if item.get("printed_hint") or not box or len(box) != 4:
            continue
        if not all(np.isfinite(float(v)) for v in box):
            continue
        bounds = clamp_box(*box, width, height)
        if bounds is None:
            continue
        x0, y0, x1, y1 = bounds
        accepted.append(
            {
                **item,
                "box": [x0, y0, x1 - x0, y1 - y0],
            }
        )
    accepted.sort(key=lambda l: (l["box"][1], l["box"][0]))
    for i, item in enumerate(accepted):
        item["evidence_id"] = f"line_{i+1}"

    # Only accepted handwriting rectangles reach page-wide context or
    # multi-region crops. Printed headers between regions remain white.
    masked = np.full_like(arr, 255)
    for item in accepted:
        x, y, w, h = item["box"]
        masked[y : y + h, x : x + w] = arr[y : y + h, x : x + w]

    def unavailable(reason):
        return {
            "url": "",
            "caption": reason,
            "status": "unavailable",
            "bbox": None,
            "region_ids": [],
            "location_url": "",
            "coordinate_space": "processed-image",
            "source_size": [width, height],
            "selection_method": "unavailable",
        }

    if not accepted:
        return {
            str(n): unavailable("No handwriting region available.")
            for n in range(1, 21)
        }

    encoded = {}
    locators = {}

    def evidence(items, method, caption, status="context", page=False):
        boxes = [item["box"] for item in items]
        x = min(b[0] for b in boxes)
        y = min(b[1] for b in boxes)
        right = max(b[0] + b[2] for b in boxes)
        bottom = max(b[1] + b[3] for b in boxes)
        bbox = [x, y, right - x, bottom - y]
        crop_box = [0, 0, width, height] if page else bbox
        key = tuple(crop_box)
        if key not in encoded:
            encoded[key] = _to_data_url(
                _crop_rgb(masked, crop_box), quality=90
            )
        ids = [item["evidence_id"] for item in items]
        locator_key = tuple(ids)
        if locator_key not in locators:
            # A small page map preserves each region's position without
            # exposing the rejected printed content surrounding the writing.
            preview = Image.fromarray(masked)
            preview.thumbnail((180, 180), Image.Resampling.LANCZOS)
            draw = ImageDraw.Draw(preview)
            sx, sy = preview.width / width, preview.height / height
            for bx, by, bw, bh in boxes:
                draw.rectangle(
                    [bx * sx, by * sy, (bx + bw - 1) * sx, (by + bh - 1) * sy],
                    outline=(210, 85, 25),
                    width=2,
                )
            locators[locator_key] = _to_data_url(np.array(preview), quality=90)
        location = (
            ", ".join(
                f"region {item['evidence_id'].split('_')[1]}" for item in items
            )
            if len(items) <= 2
            else f"{len(items)} handwriting regions"
        )
        return {
            "url": encoded[key],
            "caption": f"{location}: {caption}",
            "status": status,
            "bbox": crop_box,
            "region_ids": ids,
            "location_url": locators[locator_key],
            "coordinate_space": "processed-image",
            "source_size": [width, height],
            "selection_method": method,
        }

    def outlier(values):
        center = float(np.median(values))
        return accepted[
            max(range(len(values)), key=lambda i: abs(values[i] - center))
        ]

    widths = [item["box"][2] for item in accepted]
    heights = [item["box"][3] for item in accepted]
    low_confidence = min(accepted, key=lambda l: float(l.get("score", 0) or 0))
    char_widths = [
        item["box"][2]
        / max(1, len(re.sub(r"\s+", "", str(item.get("text") or ""))))
        for item in accepted
    ]
    char_outlier = outlier(char_widths)
    height_outlier = outlier(heights)
    width_outlier = outlier(widths)
    loop_context = max(
        accepted,
        key=lambda l: len(
            re.findall(r"[abdegopqABDGOPQR0689]", str(l.get("text") or ""))
        ),
    )
    out = {
        "1": evidence(
            [low_confidence],
            "ocr-confidence-context",
            "OCR-confidence context; letter-shape fault not localized.",
        ),
        "2": evidence(
            [char_outlier],
            "character-width-proxy-context",
            "Character-width proxy context; stroke order not visible in a photo.",
        ),
        "3": evidence(
            [loop_context],
            "loop-text-context",
            "Loop-letter text context; open loop not localized.",
        ),
        "4": evidence(
            [width_outlier],
            "region-width-proxy-context",
            "Region width differs most from the median; stroke roughness not localized.",
        ),
        "5": evidence(
            [height_outlier],
            "height-deviation",
            "Region height differs most from the page median.",
            "measurement",
        ),
        "6": evidence(
            [max(accepted, key=lambda l: l["box"][3])],
            "zone-context",
            "Tall-region zone context; individual zone fault not localized.",
        ),
        "9": evidence(
            [char_outlier],
            "character-width-proxy-context",
            "Character-width proxy context; individual letter gap not localized.",
        ),
        "18": evidence(
            accepted,
            "aggregate-context",
            "Handwriting-only context for a composite score.",
            page=True,
        ),
        "19": evidence(
            [low_confidence],
            "ocr-confidence-context",
            "OCR-confidence context; confused character not localized.",
        ),
        "20": evidence(
            accepted,
            "aggregate-context",
            "Handwriting-only context for a composite score.",
            page=True,
        ),
    }
    # Factors 7/11 score absolute polygon angles. A long level line must
    # never displace a shorter tilted line merely because its crop is wider.
    angled = []
    for item in accepted:
        poly = item.get("poly") or []
        if len(poly) >= 2:
            dx = max(1e-6, float(poly[1][0]) - float(poly[0][0]))
            angle = float(
                np.degrees(
                    np.arctan2(float(poly[1][1]) - float(poly[0][1]), dx)
                )
            )
            if np.isfinite(angle):
                angled.append((item, abs(angle)))
    for n in ("7", "11"):
        out[n] = (
            evidence(
                [max(angled, key=lambda p: p[1])[0]],
                "absolute-line-angle",
                "Largest absolute detected line angle.",
                "measurement",
            )
            if angled
            else evidence(
                accepted,
                "line-context",
                "No line angle available; fault not localized.",
                page=True,
            )
        )
    for n in ("12", "17"):
        if angled:
            median = float(np.median([angle for _, angle in angled]))
            item = max(angled, key=lambda p: abs(p[1] - median))[0]
            out[n] = evidence(
                [item],
                "line-angle-spread-context",
                "Line-angle spread proxy; individual stroke slant not localized.",
            )
        else:
            out[n] = evidence(
                accepted,
                "line-context",
                "No line angle available; fault not localized.",
                page=True,
            )

    tilt = _page_tilt_degrees(accepted)
    lefts = [_detilted_left_x(l["box"], tilt, width, height) for l in accepted]
    out["10"] = evidence(
        [outlier(lefts)],
        "detilted-left-deviation",
        "Left edge differs most from the corrected page median.",
        "measurement",
    )

    gaps = []
    for row in _group_lines_by_rows(accepted):
        items = row["items"]
        row_height = float(np.mean([l["box"][3] for l in items]))
        for left, right in zip(items, items[1:]):
            gap = max(0, right["box"][0] - left["box"][0] - left["box"][2])
            gaps.append((left, right, gap / max(1, row_height)))
    if gaps:
        median = float(np.median([gap for _, _, gap in gaps]))
        left, right, _ = max(gaps, key=lambda g: abs(g[2] - median))
        out["8"] = evidence(
            [left, right],
            "normalized-word-gap-deviation",
            "Observed gap differs most from the page median.",
            "measurement",
        )
    else:
        out["8"] = evidence(
            accepted,
            "spacing-context",
            "No between-region word gap available; fault not localized.",
            page=True,
        )
    for n in range(13, 17):
        out[str(n)] = unavailable(
            "Requires sensor-pen data; no photo location can show this measurement."
        )
    return {str(n): out[str(n)] for n in range(1, 21)}


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
    bounds = clamp_box(*box, arr.shape[1], arr.shape[0])
    if bounds is None:
        return None
    x0, y0, x1, y1 = bounds
    crop = arr[y0:y1, x0:x1]
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
    ox, oy = float(x0), float(y0)
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
