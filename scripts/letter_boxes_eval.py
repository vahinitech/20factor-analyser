# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""How well the reader's own letter positions land on the real letters.

Builds the planted pages of scripts/planted_pages.py (20 UJI test
writers, photo style), records where every letter really is, runs the
real reader to find and keep the handwritten lines, then reads each line
again with word boxes on and places every character on the page with
backend/letter_boxes.py. A placed letter "lands" when its centre falls
inside a real letter's box on the same line; each real letter can be
claimed once, by the nearest placed letter.

    on kept lines     real letters on the lines the reader kept (a line
                      it drops has no letters to place)
    letters found     real letters with a placed letter on them
    landed            placed letters that sit on a real letter
    same letter       landed letters the reader also named correctly
    centre error      distance from the real letter's centre, in
                      letter widths

Letter size: each placed small letter's height, from the ink in the
middle of its slot, over the same letter elsewhere on the page
(or its line's typical small letter when the page has fewer than three)
(letter_geometry.placed_letter_heights). On the pages with one letter
planted 1.7 times taller it reports how often the tallest letter is the
planted one, and on every page how many other letters cross each
cut-off (a circle there would be a false mark). The ink-gap letters of
letter_geometry.size_marks, today's letter-level marks, are scored the
same way beside it.

It also keeps the reader's confidence for each character (the column's
own probability, which PaddleOCR averages away) to see whether a low
character confidence picks out the letters it named wrongly.

Analyser image only (needs the OCR models):

    python scripts/letter_boxes_eval.py --json out.json --save-pages dir/
"""

import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

import cv2  # noqa: E402  pylint: disable=wrong-import-position
import planted_pages  # noqa: E402  pylint: disable=wrong-import-position
import letter_boxes  # noqa: E402  pylint: disable=wrong-import-position
import letter_geometry  # noqa: E402  pylint: disable=wrong-import-position

CUTOFFS = (1.3, 1.4, 1.5, 1.6)
SURE = 0.9

_LAST_PROBS = []


def _keep_column_probs():
    """Keep each column's probability from PaddleOCR's CTC decode, which
    otherwise only reports their mean. Evaluation only."""
    # pylint: disable=import-outside-toplevel
    from paddlex.inference.models.text_recognition import processors

    decode = processors.BaseRecLabelDecode.decode

    def wrapped(self, text_index, *args, **kw):
        probs = kw.get("text_prob", args[0] if args else None)
        _LAST_PROBS[:] = (
            [np.asarray(p, dtype=float) for p in probs]
            if probs is not None
            else []
        )
        return decode(self, text_index, *args, **kw)

    processors.BaseRecLabelDecode.decode = wrapped


def _crop(img, poly):
    pts = np.asarray(poly, dtype=np.float32)
    w = int(
        max(np.linalg.norm(pts[0] - pts[1]), np.linalg.norm(pts[2] - pts[3]))
    )
    h = int(
        max(np.linalg.norm(pts[0] - pts[3]), np.linalg.norm(pts[1] - pts[2]))
    )
    m = cv2.getPerspectiveTransform(
        pts, np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    )
    return cv2.warpPerspective(
        img, m, (max(1, w), max(1, h)), borderMode=cv2.BORDER_REPLICATE
    )


def place_letters(img, hand_lines, rec):
    """Every character the reader places on the page, with its line,
    name, box and the column's probability."""
    out = []
    for li, line in enumerate(hand_lines):
        poly = line.get("poly")
        if not poly or len(poly) < 4:
            continue
        res = dict(
            list(rec.predict(_crop(img, poly), return_word_box=True))[0]
        )
        chars, col_num = letter_boxes.recognise_columns(res.get("rec_text"))
        probs = _LAST_PROBS[0] if _LAST_PROBS else None
        placed = letter_boxes.letter_boxes(poly, chars, col_num)
        kept = [(ch, col) for ch, col in chars if ch.isalnum()]
        for item, (_ch, col) in zip(placed, kept):
            item["line"] = li
            item["conf"] = (
                float(probs[col])
                if probs is not None and col < len(probs)
                else None
            )
            out.append(item)
    return out


def _one_per_line(hand_lines):
    """The reader can keep the same line twice, once per image variant,
    when the two readings differ by a letter (detector.merge_lines only
    drops exact repeats). Place letters once per line: the
    higher-scoring reading of any two whose boxes mostly overlap."""
    import detector  # pylint: disable=import-outside-toplevel

    kept = []
    for line in sorted(
        hand_lines, key=lambda l: -float(l.get("score", 0.0) or 0.0)
    ):
        # pylint: disable=protected-access
        if all(detector._iou(line["box"], k["box"]) <= 0.5 for k in kept):
            kept.append(line)
    return kept


def match(truth, placed):
    """Claim each real letter at most once, by the nearest placed letter
    whose centre lies inside it."""
    pairs = []
    for pi, p in enumerate(placed):
        x, y = p["x"], p["bbox"][1] + p["bbox"][3] / 2
        for ti, t in enumerate(truth):
            tx, ty, tw, th = t["bbox"]
            if tx <= x <= tx + tw and ty - th <= y <= ty + 2 * th:
                pairs.append((abs(x - (tx + tw / 2)), pi, ti))
    pairs.sort()
    used_p, used_t, out = set(), set(), []
    for d, pi, ti in pairs:
        if pi in used_p or ti in used_t:
            continue
        used_p.add(pi)
        used_t.add(ti)
        out.append((pi, ti, d / max(1.0, truth[ti]["bbox"][2])))
    return out


def _inside(box, truth):
    x, y, w, h = box
    tx, ty, tw, th = truth
    return tx <= x + w / 2 <= tx + tw and ty <= y + h / 2 <= ty + th


def _real_letter(box, truth):
    """The real letter under a measured slot's centre, or None."""
    x = box[0] + box[2] / 2
    y = box[1] + box[3] / 2
    for t in truth:
        tx, ty, tw, th = t["bbox"]
        if tx <= x <= tx + tw and ty - th <= y <= ty + 2 * th:
            return t["ch"]
    return None


def letter_sizes(img, once, placed, truth_box, truth=()):
    """Every placed small letter's height ratio, and whether it is the
    planted tall letter; the same for today's ink-gap letter marks."""
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    geo = letter_geometry.measure_page(img, once)
    sizes = []
    for li, (line, g) in enumerate(zip(once, geo)):
        if not g:
            continue
        mine = [p for p in placed if p["line"] == li]
        conf = {p["bbox"][0]: p["conf"] for p in mine}
        for h in letter_geometry.placed_letter_heights(gray, line, mine):
            h["planted"] = bool(truth_box) and _inside(h["bbox"], truth_box)
            h["conf"] = conf.get(h["bbox"][0])
            h["real"] = _real_letter(h["bbox"], truth)
            sizes.append(h)
    letter_geometry.same_letter_ratios(sizes)
    marks = letter_geometry.size_marks(once, geo)
    sizes = [
        {
            "char": h["char"],
            "ratio": round(h["ratio"], 3),
            "reference": h["reference"],
            "conf": None if h["conf"] is None else round(h["conf"], 3),
            "planted": h["planted"],
            "real": h["real"],
        }
        for h in sizes
    ]
    return sizes, [
        {
            "ratio": m["value"],
            "planted": bool(truth_box) and _inside(m["bbox"], truth_box),
        }
        for m in marks
        if m["direction"] == "taller"
    ]


def size_summary(rows, key):
    """On the tall-letter pages: the tallest letter is the planted one
    and crosses the cut-off. On every page: other letters over it."""
    tall = [r[key] for r in rows if r["kind"] == "tall_letter"]
    pages = [r[key] for r in rows]
    out = {
        "tall_pages": len(tall),
        "planted_letter_placed_pct": (
            round(
                100.0
                * sum(any(l["planted"] for l in t) for t in tall)
                / len(tall),
                1,
            )
            if tall
            else None
        ),
        "planted_ratio_median": (
            round(
                float(
                    np.median(
                        [l["ratio"] for t in tall for l in t if l["planted"]]
                    )
                ),
                3,
            )
            if any(l["planted"] for t in tall for l in t)
            else None
        ),
        "other_ratio_p95": (
            round(
                float(
                    np.percentile(
                        [
                            l["ratio"]
                            for t in pages
                            for l in t
                            if not l["planted"]
                        ],
                        95,
                    )
                ),
                3,
            )
            if any(not l["planted"] for t in pages for l in t)
            else None
        ),
    }
    for c in CUTOFFS:
        first = 0
        for t in tall:
            top = max(t, key=lambda l: l["ratio"], default=None)
            first += bool(top and top["planted"] and top["ratio"] >= c)
        false = [
            sum(not l["planted"] and l["ratio"] >= c for l in t) for t in pages
        ]
        out[str(c)] = {
            "tallest_is_planted_pct": (
                round(100.0 * first / len(tall), 1) if tall else None
            ),
            "pages_with_false_mark_pct": round(
                100.0 * sum(f > 0 for f in false) / max(1, len(false)), 1
            ),
            "false_marks_per_page": round(
                float(np.mean(false)) if false else 0.0, 2
            ),
        }
    return out


def summarise(rows):
    truth = sum(r["truth"] for r in rows)
    on_kept = sum(r["truth_on_kept"] for r in rows)
    placed = sum(r["placed"] for r in rows)
    pairs = [p for r in rows for p in r["pairs"]]
    same = [p for p in pairs if p["same"]]
    errs = [p["err"] for p in pairs]
    good = [p["conf"] for p in pairs if p["same"] and p["conf"] is not None]
    off = [p["conf"] for p in pairs if not p["same"] and p["conf"] is not None]

    def pct(a, b):
        return round(100.0 * a / b, 1) if b else None

    out = {
        "pages": len(rows),
        "real_letters": truth,
        "placed_letters": placed,
        "letters_on_kept_lines_pct": pct(on_kept, truth),
        "letters_found_pct": pct(len(pairs), truth),
        "letters_found_on_kept_lines_pct": pct(len(pairs), on_kept),
        "repeated_lines": sum(r["repeated_lines"] for r in rows),
        "landed_pct": pct(len(pairs), placed),
        "same_letter_pct": pct(len(same), len(pairs)),
        "centre_error_letter_widths": {
            "median": round(float(np.median(errs)), 3) if errs else None,
            "p90": round(float(np.percentile(errs, 90)), 3) if errs else None,
        },
        "char_confidence": {
            "named_right_median": (
                round(float(np.median(good)), 3) if good else None
            ),
            "named_wrong_median": (
                round(float(np.median(off)), 3) if off else None
            ),
        },
    }
    # Would a cut-off on the character's confidence pick out the letters
    # it named wrongly?
    if good and off:
        out["char_confidence"]["below"] = {
            str(c): {
                "wrong_caught_pct": pct(sum(v < c for v in off), len(off)),
                "right_flagged_pct": pct(sum(v < c for v in good), len(good)),
            }
            for c in (0.5, 0.7, 0.9)
        }
    return out


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
    ap.add_argument("--style", choices=("photo", "plain"), default="photo")
    ap.add_argument(
        "--rec-model",
        help="default: the server's English model (VAHINI_OCR_REC_MODEL_MAP)",
    )
    ap.add_argument(
        "--kinds",
        help="comma list of planted kinds to read (all pages are still "
        "built, so each page is the same as in a full run)",
    )
    ap.add_argument("--json")
    ap.add_argument("--save-pages")
    args = ap.parse_args(argv)

    # pylint: disable=import-outside-toplevel
    from paddleocr import TextRecognition

    recognizer = planted_pages.real_reader()

    _keep_column_probs()
    import config

    args.rec_model = args.rec_model or config.SETTINGS.rec_model_map.get(
        "en", "PP-OCRv5_server_rec"
    )
    rec = TextRecognition(model_name=args.rec_model, device="cpu")
    writers = planted_pages.parse(planted_pages.fetch(args.uji))
    rng = np.random.default_rng(args.seed)
    rows, by_kind, refused = [], {}, []
    for writer in sorted(writers):
        letters = writers[writer]
        if not all(
            ch in letters
            for s in planted_pages.SENTENCES
            for ch in s.replace(" ", "")
        ):
            continue
        for kind, _skill in planted_pages.KINDS:
            truth = []
            img, _lines, planted = planted_pages.build_page(
                letters, rng, kind, args.style, letters_out=truth
            )
            if args.kinds and kind not in args.kinds.split(","):
                continue
            # "auto", as the website and the app send.
            raw, _err, backend, _meta = recognizer.collect_lines(img, "auto")
            _found, hand = recognizer.extract_hand_lines(
                img, raw, refine_backend=backend
            )
            if not hand:
                refused.append({"writer": writer, "kind": kind})
                continue
            once = _one_per_line(hand)
            placed = place_letters(img, once, rec)
            pairs = match(truth, placed)
            sizes, gap_marks = letter_sizes(
                img,
                once,
                placed,
                planted if kind == "tall_letter" else None,
                truth,
            )
            kept_lines = {
                t["line"]
                for t in truth
                for h in once
                if h["box"][1]
                <= t["bbox"][1] + t["bbox"][3] / 2
                <= h["box"][1] + h["box"][3]
            }
            row = {
                "writer": writer,
                "kind": kind,
                "truth": len(truth),
                "truth_on_kept": sum(t["line"] in kept_lines for t in truth),
                "repeated_lines": len(hand) - len(once),
                "placed": len(placed),
                "sizes": sizes,
                # Letters the reader named with confidence of at least
                # SURE: a letter it was unsure of may be two letters, or
                # a neighbour's stroke.
                "sizes_sure": [l for l in sizes if (l["conf"] or 0) >= SURE],
                "gap_marks": gap_marks,
                "pairs": [
                    {
                        "same": placed[pi]["char"].lower()
                        == truth[ti]["ch"].lower(),
                        "err": err,
                        "conf": placed[pi]["conf"],
                    }
                    for pi, ti, err in pairs
                ],
            }
            rows.append(row)
            by_kind.setdefault(kind, []).append(row)
            if args.save_pages:
                os.makedirs(args.save_pages, exist_ok=True)
                mark = img.copy()
                for t in truth:
                    x, y, w, h = t["bbox"]
                    cv2.rectangle(mark, (x, y), (x + w, y + h), (0, 160, 0), 1)
                for p in placed:
                    x, y, w, h = p["bbox"]
                    cv2.rectangle(
                        mark, (x, y), (x + w, y + h), (200, 60, 30), 1
                    )
                    cv2.putText(
                        mark,
                        p["char"],
                        (x, y - 3),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (200, 60, 30),
                        1,
                    )
                cv2.imwrite(
                    os.path.join(args.save_pages, f"{writer}-{kind}.png"),
                    cv2.cvtColor(mark, cv2.COLOR_RGB2BGR),
                )
    result = {
        "data": "UJI Pen Characters v2, published test split",
        "seed": args.seed,
        "style": args.style,
        "rec_model": args.rec_model,
        "all": summarise(rows),
        "letter_size": size_summary(rows, "sizes"),
        "letter_size_reader_sure": size_summary(rows, "sizes_sure"),
        "letter_size_ink_gaps_today": size_summary(rows, "gap_marks"),
        "letter_sizes_by_page": [
            {"writer": r["writer"], "kind": r["kind"], "sizes": r["sizes"]}
            for r in rows
        ],
        "by_kind": {k: summarise(v) for k, v in by_kind.items()},
        "refused": refused,
    }
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
