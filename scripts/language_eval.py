# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Measure the spelling and grammar check (#317) on pages whose words are
known, with the real recogniser. Runs inside the analyser image with the
models volume mounted; one container at a time on the shared host.

    uji   the 20 benchmark pages (benchmarks/uji-clean): every word is
          spelt right, so every spelling finding is a false one.
    gnhk  GNHK pages scored by the analyser, with GNHK's per-word
          transcripts: a finding is the writer's own when the transcript
          has the same word at that place and the word is not listed.
    planted  pages in the UJI test writers' own letters
          (scripts/planted_pages.py) of the benchmark sentences with
          misspellings planted (MISSPELT), read by the real reader: how
          many planted words are found, and what else is.
    copied  the same writers copying the benchmark sentences, once with
          the planted misspellings and once correctly, each checked
          against the sentences as expected_text (the copy mode).

For each page it re-reads every row the check would consider (no row
cap, so the decision can be studied offline), times each re-read, and
writes one JSON line per page with every judged word: the reading, its
margin over the best listed word, its weakest letter, the transcript
word at that place. scripts/language_eval.py summary <file> applies the
thresholds and the row cap to those lines.

    python scripts/language_eval.py uji > uji.jsonl
    python scripts/language_eval.py gnhk <results/raw> <pages> <truth> > gnhk.jsonl
    python scripts/language_eval.py planted <ujipenchars2.txt> > planted.jsonl
    python scripts/language_eval.py copied <ujipenchars2.txt> [seed] > copied.jsonl
    python scripts/language_eval.py summary uji.jsonl gnhk.jsonl
"""

import glob
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

# pylint: disable=wrong-import-position
from reading import language_check, spelling  # noqa: E402


def _reader(timings):
    # Importing the server configures the reader exactly as a scan does
    # (VAHINI_OCR_* settings, ocr_backends.init_registry).
    # pylint: disable=import-outside-toplevel,unused-import
    from server import app  # noqa: F401
    from reading import ocr_backends

    def read(crop, lang):
        t0 = time.perf_counter()
        got = ocr_backends.read_line_scores(crop, lang)
        timings.append(round((time.perf_counter() - t0) * 1000, 1))
        return got

    return read


LIMITS = {
    (spelling, "MISREAD_LN"): spelling.MISREAD_LN,
    (spelling, "WRITTEN_LN"): spelling.WRITTEN_LN,
    (spelling, "LETTER_MIN"): spelling.LETTER_MIN,
    (spelling, "SENTENCE_WRITTEN_LN"): spelling.SENTENCE_WRITTEN_LN,
    (spelling, "SENTENCE_LETTER_MIN"): spelling.SENTENCE_LETTER_MIN,
    (language_check, "ROW_MIN"): language_check.ROW_MIN,
    (language_check, "ROWS_MAX"): language_check.ROWS_MAX,
    (language_check, "WORDS_PER_ROW"): language_check.WORDS_PER_ROW,
}
OPEN = {
    (spelling, "MISREAD_LN"): -1e9,
    (spelling, "WRITTEN_LN"): -1e9,
    (spelling, "LETTER_MIN"): 0.0,
    (spelling, "SENTENCE_WRITTEN_LN"): -1e9,
    (spelling, "SENTENCE_LETTER_MIN"): 0.0,
    (language_check, "ROW_MIN"): 0.0,
    (language_check, "ROWS_MAX"): 10**6,
    (language_check, "WORDS_PER_ROW"): 10**6,
}


def _set(limits):
    for (module, name), value in limits.items():
        setattr(module, name, value)


def _boxes_text(truth_at, places):
    return " ".join(
        str(truth_at(p.get("bbox")) or "") for p in places or []
    ).strip()


def _page(arr, lines, truth_at=None, expected=""):
    """Two passes over the page. "open": every row with an odd word read
    again and every judged word kept as a finding with its margin and
    weakest letter, for studying the thresholds. "report": the section
    exactly as a scan gives it, with its time."""
    timings = []
    _set(OPEN)
    opened = language_check.check(
        arr, lines, ["en"], _reader(timings), expected, detail=True
    )
    _set(LIMITS)
    timings = []
    t0 = time.perf_counter()
    report = language_check.check(
        arr, lines, ["en"], _reader(timings), expected
    )
    total = round((time.perf_counter() - t0) * 1000, 1)
    out = {
        "ms": total,
        "reads_ms": timings,
        "rows": report.get("rows"),
        "spelling": report.get("spelling"),
        "grammar": report.get("grammar"),
        "open_rows": opened.get("rows"),
        "open_spelling": opened.get("spelling"),
    }
    if truth_at:
        for f in out["open_spelling"] or []:
            box = (f["places"] or [{}])[0].get("bbox")
            f["truth"] = truth_at(box)
        for f in (out["spelling"] or []) + (out["grammar"] or []):
            f["truth"] = _boxes_text(truth_at, f["places"])
    return out


def uji():
    import numpy as np  # pylint: disable=import-outside-toplevel
    from PIL import Image  # pylint: disable=import-outside-toplevel

    folder = os.path.join(ROOT, "benchmarks", "uji-clean")
    for path in sorted(glob.glob(os.path.join(folder, "reader", "*.json"))):
        name = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as f:
            reader = json.load(f)
        lines = [
            dict(l, lang="en", evidence_id=f"line_{i}")
            for i, l in enumerate(reader["raw_lines"])
            if str(l.get("text") or "").strip() and l.get("score", 0) > 0
        ]
        img = Image.open(os.path.join(folder, "pages", name + ".jpg"))
        arr = np.asarray(img.convert("RGB"))
        print(json.dumps(dict(_page(arr, lines), page=name)), flush=True)


def _truth_lookup(truth, scale):
    def at(box):
        if not box:
            return None
        x, y, w, h = box
        best, area = None, 0.0
        for t in truth:
            p = t["polygon"]
            xs = [p[f"x{i}"] * scale for i in range(4)]
            ys = [p[f"y{i}"] * scale for i in range(4)]
            ox = min(x + w, max(xs)) - max(x, min(xs))
            oy = min(y + h, max(ys)) - max(y, min(ys))
            if ox > 0 and oy > 0 and ox * oy > area:
                best, area = t["text"], ox * oy
        return best

    return at


def gnhk(raw_dir, pages_dir, truth_dir):
    import cv2  # pylint: disable=import-outside-toplevel
    import numpy as np  # pylint: disable=import-outside-toplevel
    from vision import (  # pylint: disable=import-outside-toplevel
        computer_vision,
    )

    for path in sorted(glob.glob(os.path.join(raw_dir, "*.json"))):
        name = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as f:
            result = json.load(f)
        if not result.get("ok"):
            continue
        with open(os.path.join(pages_dir, name + ".jpg"), "rb") as f:
            raw = f.read()
        image = computer_vision.decode_image(raw, result.get("turned", 0))
        full_w = image.size[0]
        arr = np.asarray(image)
        size = (result["proc_w"], result["proc_h"])
        if (arr.shape[1], arr.shape[0]) != size:
            arr = cv2.resize(arr, size, interpolation=cv2.INTER_AREA)
        with open(
            os.path.join(truth_dir, name + ".json"), encoding="utf-8"
        ) as f:
            truth = json.load(f)
        lines = [
            l
            for l in result.get("hand_lines", [])
            if not l.get("printed_hint")
        ]
        at = _truth_lookup(truth, result["proc_w"] / float(full_w))
        out = _page(arr, lines, at)
        print(json.dumps(dict(out, page=name)), flush=True)


def _own(f):
    word = (f.get("truth") or "").strip(".,;:!?\"'()").lower()
    return word == f["written"].lower() and not spelling.is_word(word)


# The benchmark sentences with a child's misspellings planted: each line
# keeps the same letters available in the UJI test writers' sets.
MISSPELT = [
    "vahini and bheema rite leters evry day",
    "pihu sings wile tara reads a storry",
    "chinnu keps each wurd neet and cleer",
    "the quik brown fox jumps ovr the lazy dog",
    "seetha and rama practis slowley with caer",
    "vidhya drawz big rownd leters on the line",
]


def planted(uji_path):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    # pylint: disable=import-outside-toplevel
    import numpy as np
    import planted_pages as pp

    reader = pp.real_reader()
    writers = pp.parse(pp.fetch(uji_path))
    rng = np.random.default_rng(0)
    wrong = {
        w
        for s in MISSPELT
        for w in s.split()
        if len(w) >= spelling.MIN_LETTERS
        and not spelling.is_word(w)
        and w not in language_check.grammar.rules()["names"]
    }
    for writer in sorted(writers):
        letters = writers[writer]
        if not all(ch in letters for s in MISSPELT for ch in s if ch != " "):
            continue
        pp.SENTENCES = MISSPELT
        img, lines, _truth = pp.build_page(letters, rng, "clean", "photo")
        raw, _err, backend, _meta = reader.collect_lines(img, "auto")
        _found, hand = reader.extract_hand_lines(
            img, raw, refine_backend=backend
        )
        for i, l in enumerate(hand):
            l.setdefault("evidence_id", f"line_{i}")
            l.setdefault("text_as_read", l.get("text", ""))
        written = [w for l in lines for w in l["text"].split()]
        out = _page(img, hand)
        out["planted"] = sorted(w for w in written if w in wrong)
        out["written"] = " / ".join(l["text"] for l in lines)
        print(json.dumps(dict(out, page=writer)), flush=True)


def copied(uji_path, seed=1):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    # pylint: disable=import-outside-toplevel
    import numpy as np
    import planted_pages as pp
    from reading import recognizer as rec

    reader = pp.real_reader()
    writers = pp.parse(pp.fetch(uji_path))
    right = list(pp.SENTENCES)
    meant = dict(zip(MISSPELT, right))
    meant.update(zip(right, right))
    rng = np.random.default_rng(seed)
    for writer in sorted(writers):
        letters = writers[writer]
        if not all(ch in letters for s in MISSPELT for ch in s if ch != " "):
            continue
        for kind, sentences in (("misspelt", MISSPELT), ("clean", right)):
            pp.SENTENCES = sentences
            img, lines, _truth = pp.build_page(letters, rng, "clean", "photo")
            raw, _err, backend, _meta = reader.collect_lines(img, "auto")
            _found, hand = reader.extract_hand_lines(
                img, raw, refine_backend=backend
            )
            for i, l in enumerate(hand):
                l.setdefault("evidence_id", f"line_{i}")
                l.setdefault("text_as_read", l.get("text", ""))
            expected = "\n".join(meant[l["text"]] for l in lines)
            aligned = rec.align_to_expected(hand, expected)
            pairs = [
                (w, m)
                for l in lines
                for w, m in zip(l["text"].split(), meant[l["text"]].split())
                if w != m
            ]
            out = _page(img, hand, expected=expected)
            out.update(
                kind=kind,
                planted=pairs,
                aligned=(aligned or {}).get("aligned"),
                written=" / ".join(l["text"] for l in lines),
            )
            print(json.dumps(dict(out, page=writer)), flush=True)
    pp.SENTENCES = right


def summary(paths):
    """The report pass of saved runs: findings, pages with one, the
    writer's own among spelling findings (GNHK), times."""
    for path in paths:
        with open(path, encoding="utf-8") as f:
            pages = [json.loads(l) for l in f if l.strip()]
        found = [s for p in pages for s in (p.get("spelling") or [])]
        reads = sorted(ms for p in pages for ms in p["reads_ms"])
        times = sorted(p["ms"] for p in pages)
        rules = {}
        for p in pages:
            for g in p.get("grammar") or []:
                rules[g["rule"]] = rules.get(g["rule"], 0) + 1
        print(
            json.dumps(
                {
                    "file": os.path.basename(path),
                    "pages": len(pages),
                    "spelling_findings": len(found),
                    "writers_own": sum(1 for s in found if _own(s)),
                    "pages_with_spelling": sum(
                        1 for p in pages if p.get("spelling")
                    ),
                    "grammar_by_rule": rules,
                    "rows_read_again": len(reads),
                    "read_ms_median": reads[len(reads) // 2] if reads else 0,
                    "read_ms_p90": (
                        reads[int(0.9 * len(reads))] if reads else 0
                    ),
                    "page_ms_median": times[len(times) // 2],
                    "page_ms_p90": times[int(0.9 * len(times))],
                    "page_ms_max": times[-1],
                }
            )
        )


def main(argv):
    if len(argv) >= 2 and argv[1] == "uji":
        uji()
    elif len(argv) == 5 and argv[1] == "gnhk":
        gnhk(argv[2], argv[3], argv[4])
    elif len(argv) == 3 and argv[1] == "planted":
        planted(argv[2])
    elif len(argv) in (3, 4) and argv[1] == "copied":
        copied(argv[2], int(argv[3]) if len(argv) == 4 else 1)
    elif len(argv) >= 3 and argv[1] == "summary":
        summary(argv[2:])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
