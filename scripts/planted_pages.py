# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Pages of real handwritten letters with one planted mistake each, to
measure whether the report's marked places land on the mistake.

Letters: UJI Pen Characters (Version 2), Prat, Castro, Llorens, Marzal
and Vilar, 2008, UCI Machine Learning Repository, doi:10.24432/C5FG8S,
CC BY 4.0. Only the 20 writers of its published test split are used.
The file is downloaded and checked against its SHA-256; it is never
committed, and neither are the pages.

Each page is written by one UJI writer: their own letters, scaled so the
writer's small letters share one height, set on a baseline with
letter and word gaps that vary a little, as handwriting does. One mistake
is then planted and its box recorded:

    tall_letter   one small letter 1.7 times taller        skill 5
    low_word      one word sunk 0.6 of a small letter      skill 7
    tilted_line   the last line sinking 4 degrees           skill 7
    wide_gap      one word gap three times wider            skill 8
    narrow_gap    one word gap a quarter as wide            skill 8
    clean         nothing planted (false marks)

The lines are handed to the evidence code the way the reader would: one
box and one four-corner outline per line, the outline being the smallest
rotated rectangle around the line's ink. That isolates the measuring
and marking from OCR; ``--ocr`` runs the real reader instead (analyser
image only).

    python scripts/planted_pages.py                 # download, run, print
    python scripts/planted_pages.py --json out.json --save-pages dir/

The results and what they mean are in docs/how-a-scan-works.md,
section 8.
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.request

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import cv2  # noqa: E402  pylint: disable=wrong-import-position

UJI_URL = (
    "https://archive.ics.uci.edu/ml/machine-learning-databases/"
    "uji-penchars/version2/ujipenchars2.txt"
)
UJI_SHA256 = "cc56f72f8477e763dd06a44746ba05a679e9232468aac93b3a7aad46a0300d61"
UNITS_PER_MM = {"UJI": 100.0, "UPV": 152.0}  # from the dataset's readme

SMALL = set("acemnorsuvwxz")
TALL = set("bdfhklt")
LOW = set("gjpqy")

# Text in our own cast's words. Letters only: UJI has no punctuation.
SENTENCES = [
    "vahini and bheema write letters every day",
    "pihu sings while tara reads a story",
    "chinnu keeps each word neat and clear",
    "the quick brown fox jumps over the lazy dog",
    "seetha and rama practise slowly with care",
    "vidhya draws big round letters on the line",
]
KINDS = [
    ("tall_letter", "5"),
    ("low_word", "7"),
    ("tilted_line", "7"),
    ("wide_gap", "8"),
    ("narrow_gap", "8"),
    ("clean", None),
]

X = 24  # small-letter height, processed-image pixels
PEN = 2  # stroke width, pixels
PAGE_W, PAGE_H = 1400, 900  # at least; see build_page
MARGIN = 80
LINE_STEP = 3.2 * X
WORD_GAP = 0.9 * X
LETTER_GAP = 0.18 * X
TILT_DEG = 4.0  # y grows downwards, so positive sinks to the right


def fetch(path):
    """The UJI file at ``path``, downloaded first if missing."""
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with urllib.request.urlopen(UJI_URL, timeout=60) as resp:
            data = resp.read()
        with open(path, "wb") as f:
            f.write(data)
    with open(path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    if digest != UJI_SHA256:
        raise SystemExit(f"{path}: SHA-256 {digest}, expected {UJI_SHA256}")
    return path


def parse(path):
    """{writer: {letter: [strokes, ...]}} for the test writers' lower-case
    letters. Strokes are (n, 2) arrays in millimetres, y down."""
    out, cur = {}, None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            parts = raw.split()
            if not parts or parts[0].startswith("//"):
                continue
            if parts[0] == "WORD":
                split, site, rest = parts[2].split("_", 2)
                letter = parts[1]
                cur = None
                if split == "tst" and letter.islower() and letter.isalpha():
                    writer = f"{site}_{rest.split('-')[0]}"
                    cur = {"mm": UNITS_PER_MM[site], "strokes": []}
                    out.setdefault(writer, {}).setdefault(letter, []).append(
                        cur["strokes"]
                    )
            elif parts[0] == "POINTS" and cur is not None:
                xy = np.array(parts[3:], dtype=np.float64).reshape(-1, 2)
                cur["strokes"].append(xy / cur["mm"])
    return out


def _bounds(strokes):
    pts = np.concatenate(strokes)
    return pts.min(0), pts.max(0)


def writer_scale(letters):
    """Pixels per millimetre that make this writer's small letters X tall."""
    heights = [
        _bounds(s)[1][1] - _bounds(s)[0][1]
        for ch, samples in letters.items()
        if ch in SMALL
        for s in samples
    ]
    return X / max(1e-6, float(np.median(heights)))


def build_page(letters, rng, kind):
    """Lines of words in one writer's letters, with one planted mistake.
    Returns (image, lines, truth) where lines carry box, poly and text."""
    scale = writer_scale(letters)
    sentences = list(SENTENCES)
    rng.shuffle(sentences)
    lines = []
    for li, sentence in enumerate(sentences[:4]):
        baseline = MARGIN + X * 1.8 + li * LINE_STEP
        x = MARGIN + rng.uniform(0, 12)
        words = []
        for word in sentence.split():
            glyphs = []
            for ch in word:
                sample = letters[ch][rng.integers(len(letters[ch]))]
                glyphs.append({"ch": ch, "strokes": sample})
            words.append(glyphs)
        lines.append({"baseline": baseline, "x0": x, "words": words})

    # Which line, word or gap gets the mistake.
    # A turned line is the last one, so it sinks into empty paper instead
    # of running into the line below, as a drifting line usually does.
    li = (
        len(lines) - 1
        if kind == "tilted_line"
        else int(rng.integers(len(lines)))
    )
    line = lines[li]
    nw = len(line["words"])
    wi = int(rng.integers(1, nw - 1))
    small_at = [
        (wj, gj)
        for wj, w in enumerate(line["words"])
        for gj, g in enumerate(w)
        if g["ch"] in SMALL
    ]
    target_glyph = small_at[int(rng.integers(len(small_at)))]

    ink = []
    page_lines = []
    truth = None
    for lj, line_ in enumerate(lines):
        x = line_["x0"]
        pts_line = []
        word_boxes = []
        for wj, word in enumerate(line_["words"]):
            drop = (
                0.6 * X
                if kind == "low_word" and lj == li and wj == wi
                else 0.0
            )
            word_pts = []
            for gj, g in enumerate(word):
                grow = (
                    1.7
                    if kind == "tall_letter"
                    and lj == li
                    and (wj, gj) == target_glyph
                    else 1.0
                )
                placed, width = _place(
                    g, scale, x, line_["baseline"] + drop, grow
                )
                if grow != 1.0:
                    truth = _box(placed)
                word_pts.extend(placed)
                x += width + LETTER_GAP * rng.uniform(0.7, 1.3)
            if drop:
                truth = _box(word_pts)
            word_boxes.append(_box(word_pts))
            pts_line.append(word_pts)
            gap = WORD_GAP * rng.uniform(0.85, 1.15)
            if (
                lj == li
                and wj == wi - 1
                and kind in ("wide_gap", "narrow_gap")
            ):
                gap = WORD_GAP * (3.0 if kind == "wide_gap" else 0.25)
            x += gap - LETTER_GAP
        if kind in ("wide_gap", "narrow_gap") and lj == li:
            left = word_boxes[wi - 1]
            right = word_boxes[wi]
            x0 = left[0] + left[2]
            truth = [
                x0,
                min(left[1], right[1]),
                max(1, right[0] - x0),
                max(left[1] + left[3], right[1] + right[3])
                - min(left[1], right[1]),
            ]
        strokes = [s for w in pts_line for s in w]
        if kind == "tilted_line" and lj == li:
            box = _box(strokes)
            cx, cy = box[0], line_["baseline"]
            strokes = [_rotate(s, cx, cy, TILT_DEG) for s in strokes]
            truth = _box(strokes)
        ink.extend(strokes)
        text = " ".join("".join(g["ch"] for g in w) for w in line_["words"])
        page_lines.append({"strokes": strokes, "text": text})

    # The page fits the writing: some writers' letters run wider.
    far = np.concatenate(ink).max(0)
    width = max(PAGE_W, int(far[0]) + MARGIN)
    height = max(PAGE_H, int(far[1]) + MARGIN)
    img = np.full((height, width, 3), 250, np.uint8)
    for s in ink:
        pts = np.round(s).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(img, [pts], False, (40, 40, 60), PEN, cv2.LINE_AA)
    noise = rng.normal(0, 3, img.shape)
    img = np.clip(img.astype(np.float64) + noise, 0, 255).astype(np.uint8)

    hand_lines = []
    for pl in page_lines:
        allp = np.concatenate(pl["strokes"]).astype(np.float32)
        box = _box(pl["strokes"], pad=PEN)
        rect = cv2.minAreaRect(allp)
        corners = cv2.boxPoints(rect)
        hand_lines.append(
            {
                "text": pl["text"],
                "score": 0.9,
                "box": box,
                "poly": _quad(corners),
            }
        )
    if truth is not None:
        truth = [int(round(v)) for v in truth]
    return img, hand_lines, truth


def _place(glyph, scale, x, baseline, grow):
    strokes = glyph["strokes"]
    lo, hi = _bounds(strokes)
    s = scale * grow
    h = (hi[1] - lo[1]) * s
    if glyph["ch"] in LOW:
        top = baseline - X * grow
    else:
        top = baseline - h
    placed = [(p - lo) * s + np.array([x, top]) for p in strokes]
    return placed, (hi[0] - lo[0]) * s


def _box(strokes, pad=0):
    pts = np.concatenate(strokes)
    lo, hi = pts.min(0) - pad, pts.max(0) + pad
    return [
        int(np.floor(lo[0])),
        int(np.floor(lo[1])),
        int(np.ceil(hi[0] - lo[0])),
        int(np.ceil(hi[1] - lo[1])),
    ]


def _rotate(pts, cx, cy, deg):
    a = np.radians(deg)
    r = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    return (pts - [cx, cy]) @ r.T + [cx, cy]


def _quad(corners):
    """Top-left, top-right, bottom-right, bottom-left, like the reader's
    line outlines."""
    c = sorted(corners.tolist(), key=lambda p: p[0])
    left = sorted(c[:2], key=lambda p: p[1])
    right = sorted(c[2:], key=lambda p: p[1])
    return [left[0], right[0], right[1], left[1]]


def _covers(place, truth):
    """Share of the planted box inside the marked box."""
    px, py, pw, ph = place
    tx, ty, tw, th = truth
    ix = max(0, min(px + pw, tx + tw) - max(px, tx))
    iy = max(0, min(py + ph, ty + th) - max(py, ty))
    return ix * iy / max(1, tw * th)


def evaluate(pages):
    """Per kind: how often a mark of the right skill covers the mistake,
    how often the first mark does, how tight the mark is, and the score."""
    rows = {}
    for page in pages:
        row = rows.setdefault(
            page["kind"],
            {
                "pages": 0,
                "hit": 0,
                "first": 0,
                "tight": [],
                "marks": {},
                "scores": {},
            },
        )
        row["pages"] += 1
        for n in ("5", "7", "8"):
            look = [
                p for p in page["places"].get(n, []) if p["role"] == "look"
            ]
            row["marks"].setdefault(n, []).append(len(look))
            row["scores"].setdefault(n, []).append(page["scores"].get(n))
        n = page["skill"]
        if n is None:
            continue
        look = [p for p in page["places"].get(n, []) if p["role"] == "look"]
        hits = [p for p in look if _covers(p["bbox"], page["truth"]) >= 0.5]
        if hits:
            row["hit"] += 1
            t = page["truth"]
            row["tight"].append(
                t[2] * t[3] / max(1, hits[0]["bbox"][2] * hits[0]["bbox"][3])
            )
        if look and _covers(look[0]["bbox"], page["truth"]) >= 0.5:
            row["first"] += 1
    out = {}
    for kind, row in rows.items():
        out[kind] = {
            "pages": row["pages"],
            "marked": round(row["hit"] / row["pages"], 3),
            "marked_first": round(row["first"] / row["pages"], 3),
            "mark_tightness_median": (
                round(float(np.median(row["tight"])), 3)
                if row["tight"]
                else None
            ),
            "marks_per_page": {
                n: round(float(np.mean(v)), 2) for n, v in row["marks"].items()
            },
            "score_mean": {
                n: round(float(np.mean([s for s in v if s is not None])), 2)
                for n, v in row["scores"].items()
            },
        }
    return out


def run_page(img, hand_lines, ocr):
    import computer_vision  # pylint: disable=import-outside-toplevel
    import scoring  # pylint: disable=import-outside-toplevel

    if ocr:
        import recognizer  # pylint: disable=import-outside-toplevel

        raw, _err, backend, _meta = recognizer.collect_lines(img, "en")
        found, hand_lines = recognizer.extract_hand_lines(
            img, raw, refine_backend=backend
        )
        if not hand_lines:
            printed = sum(1 for l in found if l.get("printed_hint"))
            return None, {"refused": f"{len(found)} lines, {printed} printed"}
    regions = computer_vision._factor_region_map(  # pylint: disable=W0212
        img, [], hand_lines
    )
    analysis = scoring.build_analysis(img, hand_lines, {}).to_dict()
    scores = {
        str(r["n"]): (None if r["unmeasured"] else r["score"])
        for r in analysis["results"]
    }
    places = {n: regions[n].get("places", []) for n in ("1", "5", "7", "8")}
    return places, scores


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n", maxsplit=1)[0]
    )
    ap.add_argument(
        "--uji",
        default=os.path.join(
            os.path.expanduser("~"), ".cache", "vahini", "ujipenchars2.txt"
        ),
    )
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json")
    ap.add_argument("--save-pages")
    ap.add_argument("--ocr", action="store_true")
    args = ap.parse_args(argv)

    writers = parse(fetch(args.uji))
    rng = np.random.default_rng(args.seed)
    pages, refused = [], []
    for writer in sorted(writers):
        letters = writers[writer]
        if not all(
            ch in letters for s in SENTENCES for ch in s.replace(" ", "")
        ):
            continue
        for kind, skill in KINDS:
            img, hand_lines, truth = build_page(letters, rng, kind)
            places, scores = run_page(img, hand_lines, args.ocr)
            if places is None:
                refused.append({"writer": writer, "kind": kind, **scores})
                continue
            pages.append(
                {
                    "writer": writer,
                    "kind": kind,
                    "skill": skill,
                    "truth": truth,
                    "places": places,
                    "scores": scores,
                }
            )
            if args.save_pages:
                os.makedirs(args.save_pages, exist_ok=True)
                mark = img.copy()
                if truth:
                    x, y, w, h = truth
                    cv2.rectangle(mark, (x, y), (x + w, y + h), (0, 160, 0), 2)
                for p in places.get(skill or "5", []):
                    if p["role"] == "look":
                        x, y, w, h = p["bbox"]
                        cv2.rectangle(
                            mark, (x, y), (x + w, y + h), (200, 60, 30), 2
                        )
                cv2.imwrite(
                    os.path.join(args.save_pages, f"{writer}-{kind}.png"),
                    cv2.cvtColor(mark, cv2.COLOR_RGB2BGR),
                )
    result = {
        "data": "UJI Pen Characters v2, published test split",
        "writers": len({p["writer"] for p in pages}),
        "seed": args.seed,
        "reader": "real OCR" if args.ocr else "line outlines from the ink",
        "by_kind": evaluate(pages),
        "refused": refused,
    }
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
