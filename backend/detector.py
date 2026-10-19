# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies. Server-side handwriting/print recognition.
# Third-party: PaddleOCR (Apache-2.0). See /THIRD-PARTY-NOTICES.md and backend/README.md
#
# detector.py — finding and cleaning up candidate text regions.
#
# Everything here operates on OCR "line" dicts (text/box/poly/score/
# printed_hint) or on raw pixels for preprocessing variants. Nothing here
# knows which OCR engine produced a line or how the 20-factor score is
# computed; it only decides which regions are worth keeping and whether a
# region looks like printed text versus handwriting.

import difflib
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


def _text_similarity(a: str, b: str) -> float:
    a = re.sub(r"[^a-z0-9]", "", (a or "").lower())
    b = re.sub(r"[^a-z0-9]", "", (b or "").lower())
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _text_within(a: str, b: str) -> bool:
    """One reading is a word or words of the other ("day" inside "every
    day"): a piece read again inside its whole line."""
    a = re.sub(r"[^a-z0-9]", "", (a or "").lower())
    b = re.sub(r"[^a-z0-9]", "", (b or "").lower())
    return bool(a and b) and (a in b or b in a)


def _containment(box1, box2):
    """Share of the smaller box that lies inside the other."""
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2
    ix = max(0.0, min(x1 + w1, x2 + w2) - max(x1, x2))
    iy = max(0.0, min(y1 + h1, y2 + h2) - max(y1, y2))
    small = min(w1 * h1, w2 * h2)
    return (ix * iy) / small if small > 0 else 0.0


def overlap_share(box, other):
    """Share of box's area that lies inside other."""
    x1, y1, w1, h1 = box
    x2, y2, w2, h2 = other
    ix = max(0.0, min(x1 + w1, x2 + w2) - max(x1, x2))
    iy = max(0.0, min(y1 + h1, y2 + h2) - max(y1, y2))
    return (ix * iy) / (w1 * h1) if w1 * h1 > 0 else 0.0


# Two readings of one place on the page. The image variants each read the
# page, and a line read twice used to survive whenever the two readings
# differed by a letter ("seeta" and "seetha"), so it was scored twice.
# Boxes overlapping by more than half are one line whatever they say;
# a box mostly inside another is the same line when the texts agree or
# one text is part of the other.
DUP_IOU = 0.50
DUP_CONTAINED = 0.80
DUP_TEXT = 0.60


def merge_lines(lines):
    """Drop repeated readings of the same line, keeping the most confident
    one (see DUP_IOU). A whole line replaces a piece of it read on its own
    (the piece's box inside the line's, its text part of the line's)."""
    kept = []
    for line in sorted(
        lines, key=lambda l: float(l.get("score", 0.0)), reverse=True
    ):
        text = _normalize_text(line.get("text", ""))
        if not text:
            continue
        is_dup = False
        for i, k in enumerate(kept):
            k_text = k.get("text", "")
            same = _iou(line["box"], k["box"]) > DUP_IOU
            inside = _containment(line["box"], k["box"]) >= DUP_CONTAINED
            within = _text_within(text, k_text)
            if not (
                same
                or inside
                and (within or _text_similarity(text, k_text) >= DUP_TEXT)
            ):
                continue
            if within and _area(line["box"]) > _area(k["box"]):
                kept[i] = line
            is_dup = True
            break
        if not is_dup:
            kept.append(line)
    # A line that replaced a piece can hold other pieces kept before it.
    out = []
    for line in kept:
        if any(
            other is not line
            and _area(other["box"]) > _area(line["box"])
            and _containment(line["box"], other["box"]) >= DUP_CONTAINED
            and _text_within(line.get("text", ""), other.get("text", ""))
            for other in kept
        ):
            continue
        out.append(line)
    out.sort(key=lambda l: (l["box"][1], l["box"][0]))
    return out


def _area(box):
    return float(box[2]) * float(box[3])


# Pieces of one written line. The detector splits a line where letters
# or words stand far apart, and a line read in three pieces was scored as
# three short lines: three slopes, three left edges, and the gaps between
# the pieces counted beside word gaps. Rows are anchored on the widest
# pieces: a piece joins a row when it overlaps the row's anchor in height
# by ROW_OVERLAP of the shorter one, their middles are within ROW_MIDDLE
# of the taller one's height, and it overlaps no piece of the row left to
# right by more than ROW_SIDE_OVERLAP of the narrower one. A row is then
# cut where two neighbours are more than ROW_MAX_GAP of the page's typical
# line height apart (two columns stay apart).
ROW_OVERLAP = 0.60
ROW_MIDDLE = 0.35
ROW_SIDE_OVERLAP = 0.50
ROW_MAX_GAP = 4.0


def _fits_row(piece, anchor):
    """How far apart the middles of a piece and a row's anchor are, or
    None when the piece is not on that row (see ROW_OVERLAP)."""
    _ax, ay, aw, ah = [float(v) for v in anchor["box"][:4]]
    _bx, by, bw, bh = [float(v) for v in piece["box"][:4]]
    if min(ah, bh) <= 0 or min(aw, bw) <= 0:
        return None
    over_y = min(ay + ah, by + bh) - max(ay, by)
    if over_y < ROW_OVERLAP * min(ah, bh):
        return None
    off = abs((ay + ah / 2) - (by + bh / 2))
    if off > ROW_MIDDLE * max(ah, bh):
        return None
    return off


def on_same_row(a, b):
    """Whether two lines sit on one written row (see ROW_OVERLAP)."""
    return _fits_row(a, b) is not None


def line_starts(lines):
    """The lines that start a row: a line with another line wholly to its
    left on the same row (a piece the join left apart) is not a start."""
    out = []
    for line in lines:
        x = float(line["box"][0])
        if not any(
            o is not line
            and float(o["box"][0]) + float(o["box"][2]) <= x
            and on_same_row(line, o)
            for o in lines
        ):
            out.append(line)
    return out or list(lines)


def _side_overlap(a, b):
    ax, _ay, aw, _ah = [float(v) for v in a["box"][:4]]
    bx, _by, bw, _bh = [float(v) for v in b["box"][:4]]
    over_x = min(ax + aw, bx + bw) - max(ax, bx)
    return over_x > ROW_SIDE_OVERLAP * min(aw, bw)


def outline(points):
    """Four corners, top-left, top-right, bottom-right, bottom-left, of
    the smallest rotated rectangle around the points (the shape the
    reader gives a line)."""
    pts = np.ascontiguousarray(points, dtype=np.float32).reshape(-1, 2)
    if cv2 is not None and len(pts) >= 3:
        corners = cv2.boxPoints(cv2.minAreaRect(pts))
    else:
        x0, y0 = pts.min(axis=0)
        x1, y1 = pts.max(axis=0)
        corners = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
    by_x = sorted(corners.tolist(), key=lambda p: (p[0], p[1]))
    left = sorted(by_x[:2], key=lambda p: p[1])
    right = sorted(by_x[2:], key=lambda p: p[1])
    return [
        [float(v) for v in left[0]],
        [float(v) for v in right[0]],
        [float(v) for v in right[1]],
        [float(v) for v in left[1]],
    ]


# A joined line keeps to its widest piece's height, give or take this
# share of it: one piece whose box reaches into the next line (a long
# tail, a second line caught in a crop) must not make the line two lines
# tall.
JOIN_REACH = 0.25


def _join(pieces):
    pieces = sorted(pieces, key=lambda l: float(l["box"][0]))
    anchor = max(pieces, key=lambda l: float(l["box"][2]))
    ay, ah = float(anchor["box"][1]), float(anchor["box"][3])
    top = min(float(p["box"][1]) for p in pieces)
    bottom = max(float(p["box"][1]) + float(p["box"][3]) for p in pieces)
    y0 = max(top, ay - JOIN_REACH * ah)
    y1 = min(bottom, ay + ah + JOIN_REACH * ah)
    texts = [str(p.get("text", "") or "").strip() for p in pieces]
    weights = [max(1, len(t)) for t in texts]
    points = []
    for p in pieces:
        poly = p.get("poly") or []
        if len(poly) < 3:
            x, y, w, h = [float(v) for v in p["box"][:4]]
            poly = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
        points.extend(
            [[float(px), min(y1, max(y0, float(py)))] for px, py in poly]
        )
    x0 = min(float(p["box"][0]) for p in pieces)
    x1 = max(float(p["box"][0]) + float(p["box"][2]) for p in pieces)
    line = dict(anchor)
    line.update(
        {
            "text": " ".join(t for t in texts if t),
            "box": [x0, y0, x1 - x0, y1 - y0],
            "poly": outline(points),
            "score": float(
                sum(
                    float(p.get("score", 0.0) or 0.0) * w
                    for p, w in zip(pieces, weights)
                )
                / sum(weights)
            ),
            "joined_pieces": len(pieces),
        }
    )
    if any("text_as_read" in p for p in pieces):
        line["text_as_read"] = " ".join(
            str(p.get("text_as_read", p.get("text", "")) or "").strip()
            for p in pieces
        )
    return line


def join_row_pieces(lines):
    """Join the pieces of each written line into one line (see
    ROW_OVERLAP), left to right; lines that need no join are returned
    unchanged, in reading order."""
    rows = []  # [anchor, members]
    for piece in sorted(
        lines, key=lambda l: (-float(l["box"][2]), float(l["box"][1]))
    ):
        best_off, best_row = 0.0, None
        reread = False
        for row in rows:
            off = _fits_row(piece, row[0])
            if off is None:
                continue
            if any(_side_overlap(piece, m) for m in row[1]):
                # Over ink the row already holds: a second reading of it
                # (another image variant, or line_recovery.py), not a
                # piece of the line. Pieces come widest first, so the
                # fuller reading stays.
                reread = True
                continue
            if best_row is None or off < best_off:
                best_off, best_row = off, row
        if best_row is not None:
            best_row[1].append(piece)
        elif not reread:
            rows.append([piece, [piece]])
    line_h = float(np.median([float(r[0]["box"][3]) for r in rows] or [0]))
    out = []
    for _anchor, members in rows:
        members.sort(key=lambda l: float(l["box"][0]))
        run = [members[0]]
        for m in members[1:]:
            prev_end = max(
                float(p["box"][0]) + float(p["box"][2]) for p in run
            )
            if float(m["box"][0]) - prev_end > ROW_MAX_GAP * line_h:
                out.append(run)
                run = []
            run.append(m)
        out.append(run)
    out = [r[0] if len(r) == 1 else _join(r) for r in out]
    out.sort(key=lambda l: (float(l["box"][1]), float(l["box"][0])))
    return out


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

        # Drop extreme-width header/footer lines that look printed. A
        # confident reading alone is not enough: the first handwritten
        # line of a page photographed close sits in the top 14% too, and
        # was dropped on most pages of the UJI test set. classify.py
        # still removes printed lines the text check misses.
        if (
            (y_ratio < 0.14 or y_ratio > 0.90)
            and aspect > 8.0
            and bool(l.get("printed_hint"))
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
