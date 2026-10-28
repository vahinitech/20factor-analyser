# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Do the analyser's factor scores agree with occupational therapists?

The protocol is docs/23-therapist-agreement.md. Therapists mark consented
pages on the marking sheet, one mark per factor on the report's own 0-10
scale, and say whether they would want an occupational therapist to take
a closer look. The analyser scores the same pages. This joins the two and
writes aggregates only: no page id, mark or score of a single page
reaches the report.

    python scripts/therapist_agreement.py sheet [--check]
        write (or check) the marking sheet and the CSV template in
        docs/therapist-agreement/, from the factor list in
        backend/scoring.py
    python scripts/therapist_agreement.py score <pages> --out scores.csv
        analyser image only: read and score every page in the folder the
        way scripts/benchmark.py does (one container at a time); --out -
        writes to stdout
    python scripts/therapist_agreement.py report --scores scores.csv \\
        --marks marks.csv [--marks more.csv] [--flag-below 45]
        the agreement report, as markdown
    python scripts/therapist_agreement.py sample --out <folder>
        made-up scores and marks for the cast, to see the report's shape

scores.csv holds page, overall and f1 to f20 (blank where a factor was
not measured), or the error a page stopped on. The marks CSV is the
template's columns: page, therapist, f1 to f20 (0 to 10, blank when the
therapist could not judge), ot_look (yes or no).
"""

# Scripts here print their results; the analyser modules are imported
# from backend/ only when a command needs them.
# pylint: disable=import-outside-toplevel

import argparse
import contextlib
import csv
import html
import importlib.util
import io
import math
import os
import random
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(ROOT, "backend")
SHEET_DIR = os.path.join(ROOT, "docs", "therapist-agreement")
FACTORS = tuple(range(1, 21))
PEN = (13, 14, 15, 16)  # a photo cannot measure these (benchmark.SCORED)
COLUMNS = ["page", "therapist"] + [f"f{n}" for n in FACTORS] + ["ot_look"]

# Bands in the order the report ranks them, with the stage the report
# prints for each (scoring_parts.stats._band, practice_catalog.STAGES).
# Whole-number marks fall into them as 0-4, 5-6, 7-8 and 9-10.
BANDS = ("focus", "dev", "good", "strong")

# A number from fewer pages than this is not written: too few to mean
# anything, and too close to describing single children.
MIN_PAGES = 10

# What a therapist looks at for each factor, in plain words. Each says
# what the analyser's own measurement for that factor tries to capture
# (_FACTOR_META in backend/scoring.py, formulas in
# docs/03-scoring-criteria.md); the sheet prints both, so the two sides
# mark the same skill.
LOOK_FOR = {
    1: "Letters are formed the way they are taught and are easy to "
    "recognise on their own.",
    2: "Each letter is built the same way every time it appears. "
    "Best judged while watching the child write.",
    3: "Letters with a bowl or loop (a, d, g, o, p, q, e) are closed, "
    "with no gap at the top.",
    4: "Strokes are smooth and even, without wobble or tremor.",
    5: "Small letters (a, c, e, n, o) keep the same height across "
    "the page.",
    6: "Tall letters (b, d, h, k, l) reach up and tails (g, p, y) reach "
    "down by the right amount.",
    7: "Words sit on the line instead of floating above it or dropping "
    "below it.",
    8: "Spaces between words are clear and about the same each time.",
    9: "Letters inside a word are evenly spaced, neither crowded nor "
    "spread apart.",
    10: "Lines start at the same place on the left.",
    11: "Each line of writing runs level across the page.",
    12: "Upright strokes lean the same way from one line to the next.",
    13: "The child writes at a steady pace. Only if you watched.",
    14: "The pen presses evenly, not hard then light. Only if you "
    "watched or can feel the paper.",
    15: "Words are written in one flow, without breaks the child did "
    "not mean. Only if you watched.",
    16: "The pen leaves the paper only where it should. Only if you "
    "watched.",
    17: "Letters lean the same way across the page.",
    18: "Someone who does not know the child can read the page.",
    19: "Letters that look alike (a and o, n and h, u and v, 1 and l) "
    "can be told apart.",
    20: "The page as a whole looks tidy and organised.",
}


# ---------------------------------------------------------------------------
# The marking sheet
# ---------------------------------------------------------------------------


def factor_meta():
    """Number -> (section, name, what the analyser measures), read from
    backend/scoring.py so the sheet cannot name a factor it does not
    score."""
    if BACKEND not in sys.path:
        sys.path.insert(0, BACKEND)
    import scoring

    meta = scoring._FACTOR_META  # pylint: disable=protected-access
    if sorted(meta) != list(FACTORS) or sorted(LOOK_FOR) != list(FACTORS):
        raise SystemExit(
            "scoring._FACTOR_META and LOOK_FOR must both hold factors 1-20"
        )
    return meta


def stages():
    """(band, stage label, lowest whole mark, highest whole mark)."""
    if BACKEND not in sys.path:
        sys.path.insert(0, BACKEND)
    from report import practice_catalog

    out = []
    rows = list(practice_catalog.STAGES)
    for i, s in enumerate(rows):
        low = math.ceil(s["minimum"])
        high = (
            math.ceil(rows[i + 1]["minimum"]) - 1 if i + 1 < len(rows) else 10
        )
        out.append((s["band"], s["label"], low, high))
    if tuple(b for b, *_ in out) != BANDS:
        raise SystemExit("practice_catalog.STAGES no longer match BANDS")
    return out


def template_csv():
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(COLUMNS)
    writer.writerow(["P001", "T1"] + [""] * len(FACTORS) + [""])
    return buf.getvalue()


SHEET_STYLE = """
@page { size: A4; margin: 10mm; }
body { font: 9pt/1.2 Georgia, serif; margin: 0 auto; max-width: 190mm; }
h1 { font-size: 13pt; margin: 0 0 1.5mm; }
p { margin: 0 0 1.5mm; }
.ids { display: flex; gap: 8mm; margin: 2.5mm 0; font-size: 10pt; }
.ids span { flex: 1; border-bottom: 1px solid; padding-bottom: 1mm; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid; padding: 0.6mm 1.2mm; vertical-align: top; }
th { text-align: left; font-size: 8.5pt; }
td.n { width: 5mm; text-align: right; }
td.mark { width: 18mm; }
.how { font-size: 7.5pt; display: block; }
tr.section th { font-size: 8.5pt; padding-top: 1.2mm; }
.flag { margin-top: 2.5mm; border: 1px solid; padding: 1.5mm 2mm; }
.small { font-size: 8pt; }
""".strip()


def sheet_html():
    meta = factor_meta()
    bands = stages()
    scale = ", ".join(
        f"{low} to {high} {label}" for _b, label, low, high in bands
    )
    sections = {
        "structure": "Letter shapes and size",
        "spatial": "Spacing and lines",
        "dynamics": "Movement (only if you watched the child write)",
        "style": "Slant, legibility and neatness",
    }
    rows, last = [], None
    for n in FACTORS:
        section, name, measures = meta[n]
        if section != last:
            rows.append(
                f'<tr class="section"><th colspan="3">'
                f"{html.escape(sections[section])}</th></tr>"
            )
            last = section
        rows.append(
            "<tr>"
            f'<td class="n">{n}</td>'
            f"<td><b>{html.escape(name)}</b>: "
            f"{html.escape(LOOK_FOR[n])}"
            f'<span class="how">The analyser measures: '
            f"{html.escape(measures)}.</span></td>"
            '<td class="mark"></td>'
            "</tr>"
        )
    body = "\n".join(rows)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Handwriting marking sheet</title>
<style>
{SHEET_STYLE}
</style>
</head>
<body>
<!-- Generated by scripts/therapist_agreement.py sheet. Do not edit. -->
<h1>Handwriting marking sheet</h1>
<p class="small">One sheet per page. Mark before you see any analyser
score, and without talking to the other therapist about this page.
Write the page number only: never the child's name.</p>
<div class="ids"><span>Page number:</span>
<span>Your code (T1, T2 ...):</span></div>
<p class="small"><b>Marks:</b> a whole number from 0 to 10 for each
skill, the scale the report uses: {html.escape(scale)}. Leave a box empty
if you cannot judge that skill from what you have.</p>
<table>
<tr><th>#</th><th>Skill: what to look at</th><th>Mark 0-10</th></tr>
{body}
</table>
<div class="flag"><b>Would you want an occupational therapist to take a
closer look at this child's handwriting?</b> &nbsp; Yes &#9744; &nbsp; No
&#9744;
<p class="small">This is your professional judgement from the page. It
is not a diagnosis, and neither is any analyser score.</p></div>
</body>
</html>
"""


def sheet(check=False):
    files = {
        "marking-sheet.html": sheet_html(),
        "marks-template.csv": template_csv(),
    }
    stale = []
    for name, text in files.items():
        path = os.path.join(SHEET_DIR, name)
        if check:
            try:
                with open(path, encoding="utf-8") as f:
                    if f.read() != text:
                        stale.append(name)
            except FileNotFoundError:
                stale.append(name)
            continue
        os.makedirs(SHEET_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    if stale:
        print(
            "Out of date: "
            + ", ".join(stale)
            + ". Run python scripts/therapist_agreement.py sheet"
        )
        return 1
    return 0


# ---------------------------------------------------------------------------
# Scoring the pages (analyser image, models mounted)
# ---------------------------------------------------------------------------

IMAGE_TYPES = (".jpg", ".jpeg", ".png", ".webp")


def _benchmark():
    spec = importlib.util.spec_from_file_location(
        "benchmark", os.path.join(ROOT, "scripts", "benchmark.py")
    )
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    return bench


def page_files(folder):
    return sorted(
        f
        for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() in IMAGE_TYPES
    )


def benchmark_scorer(lang):
    """Score one page file the way benchmark.py's live run does: the
    stage analyser's reader settings (benchmarks/uji-clean/set.json), the
    server's own reader, then the scorer. Returns overall and the factor
    scores; the words read are dropped here and never written."""
    bench = _benchmark()
    _folder, meta = bench._load_set("uji-clean")  # pylint: disable=W0212
    bench._apply_settings(meta)  # pylint: disable=W0212
    server = bench._server()  # pylint: disable=W0212

    def score(path, page):
        raw, arr = bench._image_file(path, meta)  # pylint: disable=W0212
        reader = bench.read_image(server, raw, arr, lang, page)
        got = bench._score(arr, raw, reader, meta)  # pylint: disable=W0212
        return {"overall": got["overall"], "scores": got["scores"]}

    return score


def score_folder(folder, scorer):
    """One row per page: its scores, or the kind of error it stopped
    on. A page that fails stays in the file so the report counts it."""
    rows = []
    for name in page_files(folder):
        page = os.path.splitext(name)[0]
        row = {"page": page, "overall": "", "error": ""}
        try:
            got = scorer(os.path.join(folder, name), page)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # The type only: a message can quote what the reader read.
            row["error"] = type(e).__name__
            got = {"overall": None, "scores": {}}
        if got["overall"] is not None:
            row["overall"] = got["overall"]
        for n in FACTORS:
            v = got["scores"].get(str(n))
            row[f"f{n}"] = "" if v is None else v
        rows.append(row)
    return rows


@contextlib.contextmanager
def console_to_stderr():
    """While the reader runs, anything it prints (Python or the OCR
    library's own C code) goes to stderr, so `--out -` stays clean."""
    sys.stdout.flush()
    saved = os.dup(1)
    os.dup2(2, 1)
    try:
        yield
    finally:
        sys.stdout.flush()
        os.dup2(saved, 1)
        os.close(saved)


def write_scores(rows, path):
    """To a file, or to stdout for "-": the container writes nowhere,
    and the shell on the server puts the rows in the run folder."""
    cols = ["page", "overall"] + [f"f{n}" for n in FACTORS] + ["error"]
    if path == "-":
        writer = csv.DictWriter(
            sys.stdout, fieldnames=cols, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
        return
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# The maths. Standard library only, so the tests need nothing installed.
# ---------------------------------------------------------------------------


def band(score):
    """Index into BANDS of a 0-10 score, with the report's cut-offs
    (scoring_parts.stats._band): 4.5, 7.0 and 8.5."""
    if score >= 8.5:
        return 3
    if score >= 7.0:
        return 2
    if score >= 4.5:
        return 1
    return 0


def ranks(xs):
    """Ranks from 1, ties sharing the mean of the ranks they span."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2.0 + 1
        i = j + 1
    return out


def pearson(a, b):
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    sab = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    saa = sum((x - ma) ** 2 for x in a)
    sbb = sum((y - mb) ** 2 for y in b)
    if saa == 0 or sbb == 0:
        return None
    return sab / math.sqrt(saa * sbb)


def spearman(a, b):
    """Rank correlation with ties (Pearson on mid-ranks); None when
    either side does not vary or there are fewer than three pairs.
    benchmark._spearman takes two orderings without ties; marks on a
    0-10 scale tie all the time, so this one is separate."""
    return pearson(ranks(a), ranks(b))


def fisher_ci(r, n, z=1.96):
    """Approximate 95% interval of a rank correlation (Fisher's z,
    standard error 1/sqrt(n-3))."""
    if r is None or n < 4:
        return None
    r = max(-0.999999, min(0.999999, r))
    half = z / math.sqrt(n - 3)
    at = math.atanh(r)
    return math.tanh(at - half), math.tanh(at + half)


def weighted_kappa(a, b, k=len(BANDS), weights="quadratic"):
    """Cohen's weighted kappa for two ratings in categories 0..k-1.
    Quadratic weights by default: a two-band miss costs four times a
    one-band miss. 1 is full agreement, 0 what chance gives."""
    n = len(a)
    if n == 0:
        return None
    obs = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[x][y] += 1
    row = [sum(obs[i]) for i in range(k)]
    col = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    power = 2 if weights == "quadratic" else 1
    seen = expected = 0.0
    for i in range(k):
        for j in range(k):
            w = (abs(i - j) / (k - 1)) ** power
            seen += w * obs[i][j]
            expected += w * row[i] * col[j] / n
    if expected == 0:
        return None
    return 1 - seen / expected


def cohen_kappa(a, b):
    """Unweighted kappa for two yes/no ratings (True/False)."""
    n = len(a)
    if n == 0:
        return None
    agree = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    chance = pa * pb + (1 - pa) * (1 - pb)
    if chance == 1:
        return None
    return (agree - chance) / (1 - chance)


def within_one(a, b):
    """Share of pairs whose bands differ by at most one."""
    if not a:
        return None
    return sum(abs(x - y) <= 1 for x, y in zip(a, b)) / len(a)


def same_band(a, b):
    if not a:
        return None
    return sum(x == y for x, y in zip(a, b)) / len(a)


def wilson(hits, n, z=1.96):
    """95% interval for a proportion (Wilson score)."""
    if n == 0:
        return None
    p = hits / n
    d = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, mid - half), min(1.0, mid + half)


def auc(flagged, not_flagged):
    """Chance that a page the therapists flagged scores lower overall
    than one they did not (ties count half): 0.5 is no better than a
    coin, 1 is perfect. Low scores are the analyser's flag, so the
    comparison is reversed from the usual one."""
    if not flagged or not not_flagged:
        return None
    wins = 0.0
    for f in flagged:
        for g in not_flagged:
            if f < g:
                wins += 1
            elif f == g:
                wins += 0.5
    return wins / (len(flagged) * len(not_flagged))


# ---------------------------------------------------------------------------
# Reading the files and joining them
# ---------------------------------------------------------------------------


def _num(v):
    v = (v or "").strip()
    return None if v == "" else float(v)


def _yes(v):
    v = (v or "").strip().lower()
    if v in ("yes", "y", "1", "true"):
        return True
    if v in ("no", "n", "0", "false"):
        return False
    return None


def read_scores(path):
    with open(path, encoding="utf-8", newline="") as f:
        return {r["page"]: r for r in csv.DictReader(f)}


def read_marks(paths):
    """{page: {therapist: {"marks": {n: mark}, "look": bool}}}. A second
    sheet for the same page and therapist is refused: it is a typing
    slip, and averaging it in would hide that."""
    marks, problems = {}, []
    for path in paths:
        with open(path, encoding="utf-8", newline="") as f:
            for line, r in enumerate(csv.DictReader(f), start=2):
                page = (r.get("page") or "").strip()
                who = (r.get("therapist") or "").strip()
                if not page or not who:
                    problems.append(f"{path}:{line}: no page or therapist")
                    continue
                if who in marks.get(page, {}):
                    problems.append(
                        f"{path}:{line}: page {page} marked twice by {who}"
                    )
                    continue
                got = {}
                for n in FACTORS:
                    v = _num(r.get(f"f{n}"))
                    if v is not None and not 0 <= v <= 10:
                        problems.append(
                            f"{path}:{line}: f{n} is {v}, outside 0-10"
                        )
                        v = None
                    if v is not None:
                        got[n] = v
                marks.setdefault(page, {})[who] = {
                    "marks": got,
                    "look": _yes(r.get("ot_look")),
                }
    return marks, problems


def _mean(xs):
    return sum(xs) / len(xs)


def factor_pairs(scores, marks, n):
    """(analyser score, therapists' mean mark) for every page where both
    exist for factor n."""
    out = []
    for page, by in sorted(marks.items()):
        row = scores.get(page)
        if not row or row.get("error"):
            continue
        s = _num(row.get(f"f{n}"))
        got = [m["marks"][n] for m in by.values() if n in m["marks"]]
        if s is None or not got:
            continue
        out.append((s, _mean(got)))
    return out


def therapist_pairs(marks, n):
    """(first therapist's mark, second's) on pages two or more marked;
    with three, every pair counts once."""
    out = []
    for _page, by in sorted(marks.items()):
        names = sorted(by)
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                ma, mb = by[a]["marks"], by[b]["marks"]
                if n in ma and n in mb:
                    out.append((ma[n], mb[n]))
    return out


def agreement_row(pairs):
    """Spearman, its interval, weighted kappa on bands, same band and
    within one band, for (x, y) pairs on the 0-10 scale."""
    a = [x for x, _ in pairs]
    b = [y for _, y in pairs]
    ba = [band(x) for x in a]
    bb = [band(y) for y in b]
    rho = spearman(a, b)
    return {
        "n": len(pairs),
        "rho": rho,
        "ci": fisher_ci(rho, len(pairs)),
        "kappa": weighted_kappa(ba, bb),
        "same": same_band(ba, bb),
        "within": within_one(ba, bb),
    }


def reference_flag(by):
    """The therapists' answer for a page: the majority, or None when
    they split evenly or nobody answered."""
    votes = [m["look"] for m in by.values() if m["look"] is not None]
    yes = sum(votes)
    if not votes or yes * 2 == len(votes):
        return None
    return yes * 2 > len(votes)


def flag_table(scores, marks, cut_offs):
    """For each overall cut-off, the analyser flags pages scoring below
    it; compare with the therapists' majority answer."""
    flagged, other, split = [], [], 0
    for page, by in sorted(marks.items()):
        row = scores.get(page)
        if not row or row.get("error") or _num(row.get("overall")) is None:
            continue
        ref = reference_flag(by)
        if ref is None:
            split += 1
            continue
        (flagged if ref else other).append(_num(row["overall"]))
    rows = []
    for cut in cut_offs:
        tp = sum(s < cut for s in flagged)
        tn = sum(s >= cut for s in other)
        rows.append(
            {
                "cut": cut,
                "tp": tp,
                "fn": len(flagged) - tp,
                "tn": tn,
                "fp": len(other) - tn,
                "sens": tp / len(flagged) if flagged else None,
                "sens_ci": wilson(tp, len(flagged)),
                "spec": tn / len(other) if other else None,
                "spec_ci": wilson(tn, len(other)),
            }
        )
    return {
        "flagged": len(flagged),
        "not_flagged": len(other),
        "split": split,
        "auc": auc(flagged, other),
        "rows": rows,
    }


def flag_kappa(marks):
    pairs = []
    for _page, by in sorted(marks.items()):
        names = sorted(by)
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                x, y = by[a]["look"], by[b]["look"]
                if x is not None and y is not None:
                    pairs.append((x, y))
    if not pairs:
        return 0, None, None
    a = [x for x, _ in pairs]
    b = [y for _, y in pairs]
    return len(pairs), same_band(a, b), cohen_kappa(a, b)


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------


def _f(v, digits=2):
    return "" if v is None else f"{v:.{digits}f}"


def _pct(v):
    return "" if v is None else f"{round(100 * v)}%"


def _ci(ci):
    return "" if ci is None else f"{ci[0]:.2f} to {ci[1]:.2f}"


def _pct_ci(ci):
    return "" if ci is None else f"{round(100 * ci[0])}-{round(100 * ci[1])}%"


def _table_rows(rows):
    out = []
    for name, r in rows:
        if r["n"] < MIN_PAGES:
            out.append(f"| {name} | {r['n']} | fewer than {MIN_PAGES} pages")
            continue
        out.append(
            f"| {name} | {r['n']} | {_f(r['rho'])} | {_ci(r['ci'])} | "
            f"{_f(r['kappa'])} | {_pct(r['same'])} | {_pct(r['within'])} |"
        )
    return out


def report(scores, marks, problems, flag_below=45, meta=None):
    meta = meta or {}
    names = {n: f"{n} {name}" for n, (_s, name, _m) in meta.items()}
    marked = set(marks)
    scored = {p for p in marked if p in scores and not scores[p].get("error")}
    errors = sum(1 for p in marked if p in scores and scores[p].get("error"))
    therapists = {t for by in marks.values() for t in by}
    double = sum(1 for by in marks.values() if len(by) >= 2)
    lines = [
        "# Therapist agreement",
        "",
        f"{len(marked)} pages marked by {len(therapists)} therapists; "
        f"{double} pages marked by two or more. The analyser scored "
        f"{len(scored)} of them; {errors} stopped with an error and "
        f"{len(marked - set(scores))} have no analyser row.",
        "",
        "Aggregates only: no page or child is named. A number from fewer "
        f"than {MIN_PAGES} pages is left out.",
    ]
    if problems:
        # Counted here; the rows themselves go to the console on the
        # server (main), since they name pages.
        lines += [
            "",
            f"{len(problems)} rows in the marks were skipped; the run "
            "listed them on the server.",
        ]

    head = (
        "| Factor | Pages | Spearman | 95% interval | Weighted kappa "
        "| Same band | Within one band |\n|---|---|---|---|---|---|---|"
    )
    lines += [
        "",
        "## The analyser against the therapists",
        "",
        "Each page's therapist mark is the mean of its therapists' marks. "
        "Spearman compares the order of the pages (1 the same order, 0 "
        "none); the interval is approximate (Fisher). Bands use the "
        "report's cut-offs (4.5, 7.0, 8.5), and kappa weighs a two-band "
        "miss four times a one-band miss (quadratic weights; 0 is what "
        "chance gives).",
        "",
        head,
    ]
    rows = []
    for n in FACTORS:
        pairs = factor_pairs(scores, marks, n)
        if n in PEN and not pairs:
            continue
        rows.append((names.get(n, str(n)), agreement_row(pairs)))
    lines += _table_rows(rows)
    if all(not factor_pairs(scores, marks, n) for n in PEN):
        lines += [
            "",
            "Factors 13 to 16 need the pen; a photo does not measure "
            "them, so they are not compared.",
        ]

    lines += [
        "",
        "## Therapist against therapist",
        "",
        "Pages two therapists marked, compared the same way. This is the "
        "ceiling: the analyser cannot be expected to agree with a "
        "therapist more than two therapists agree with each other.",
        "",
        head,
    ]
    rows = [
        (names.get(n, str(n)), agreement_row(therapist_pairs(marks, n)))
        for n in FACTORS
        if therapist_pairs(marks, n) or n not in PEN
    ]
    lines += _table_rows(rows)
    n_pairs, same, kappa = flag_kappa(marks)
    if n_pairs >= MIN_PAGES:
        lines += [
            "",
            f"Would they want an OT to take a closer look: the two answers "
            f"matched on {_pct(same)} of {n_pairs} pages (kappa "
            f"{_f(kappa)}).",
        ]

    cuts = sorted({35, 45, 55, 65, flag_below})
    flags = flag_table(scores, marks, cuts)
    lines += [
        "",
        "## The overall score as a flag",
        "",
        "The reference is the therapists' answer to \"would you want an "
        'occupational therapist to take a closer look" (the majority '
        "when two or more answered). The analyser flags a page when its "
        "overall score is below the cut-off. Sensitivity is the share of "
        "pages the therapists flagged that the analyser also flagged; "
        "specificity the share they did not flag that it also left alone. "
        "Neither side is a diagnosis.",
        "",
        f"{flags['flagged']} pages flagged by the therapists, "
        f"{flags['not_flagged']} not; {flags['split']} split evenly and "
        "are left out.",
    ]
    if min(flags["flagged"], flags["not_flagged"]) < MIN_PAGES:
        lines += [
            "",
            f"Fewer than {MIN_PAGES} pages on one side: no sensitivity "
            "or specificity is given.",
        ]
    else:
        lines += [
            "",
            "Area under the curve (the chance a flagged page scores lower "
            f"than one not flagged; 0.5 is a coin): {_f(flags['auc'])}.",
            "",
            "| Overall below | Sensitivity | 95% interval | Specificity "
            "| 95% interval |\n|---|---|---|---|---|",
        ]
        for r in flags["rows"]:
            mark = " (chosen)" if r["cut"] == flag_below else ""
            lines.append(
                f"| {r['cut']}{mark} | {_pct(r['sens'])} | "
                f"{_pct_ci(r['sens_ci'])} | {_pct(r['spec'])} | "
                f"{_pct_ci(r['spec_ci'])} |"
            )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Made-up data for the cast, to show the report's shape
# ---------------------------------------------------------------------------

CAST = (
    "vahini",
    "bheema",
    "pihu",
    "tara",
    "chinnu",
    "vishnu",
    "raji",
    "madhuri",
    "keshava",
    "shivani",
)
THERAPISTS = ("Vidhya", "Arun")


def sample(out, pages=60, seed=20261028):
    """Scores and marks for made-up pages named after the cast. Each page
    has a hidden 'true' level per factor; the analyser and each therapist
    see it with their own noise, the analyser noisier on some factors.
    Nothing here is a real child or a real result."""
    rng = random.Random(seed)
    noise = {n: 1.0 for n in FACTORS}
    noise.update({3: 3.0, 8: 2.5, 10: 3.0, 9: 2.0})
    score_rows, mark_rows = [], []
    for i in range(pages):
        page = f"{CAST[i % len(CAST)]}-{i // len(CAST) + 1:02d}"
        skill = rng.uniform(2.0, 9.5)
        true = {n: min(10, max(0, rng.gauss(skill, 1.2))) for n in FACTORS}
        row = {"page": page, "error": ""}
        for n in FACTORS:
            v = None
            if n not in PEN:
                v = round(min(10, max(0, rng.gauss(true[n], noise[n]))), 1)
            row[f"f{n}"] = "" if v is None else v
        five = {1: 40, 7: 20, 5: 20, 11: 10, 17: 10}
        row["overall"] = round(
            sum(p * row[f"f{n}"] / 10 for n, p in five.items())
        )
        if i == 7:
            row = {"page": page, "overall": "", "error": "ValueError"}
        score_rows.append(row)
        who = THERAPISTS if i % 2 == 0 else THERAPISTS[i // 2 % 2 :][:1]
        for t in who:
            r = {"page": page, "therapist": t}
            for n in FACTORS:
                m = round(min(10, max(0, rng.gauss(true[n], 0.8))))
                r[f"f{n}"] = "" if n in PEN else m
            look = _mean([true[n] for n in (1, 5, 7, 18)])
            r["ot_look"] = "yes" if look + rng.gauss(0, 0.7) < 5 else "no"
            mark_rows.append(r)
    os.makedirs(out, exist_ok=True)
    write_scores(score_rows, os.path.join(out, "scores.csv"))
    with open(
        os.path.join(out, "marks.csv"), "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(mark_rows)


# ---------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n", maxsplit=1)[0]
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sheet")
    p.add_argument("--check", action="store_true")
    p = sub.add_parser("score")
    p.add_argument("pages")
    p.add_argument("--out", required=True)
    p.add_argument("--lang", default="auto")
    p = sub.add_parser("report")
    p.add_argument("--scores", required=True)
    p.add_argument("--marks", action="append", required=True)
    p.add_argument("--flag-below", type=int, default=45)
    p = sub.add_parser("sample")
    p.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    if args.cmd == "sheet":
        return sheet(args.check)
    if args.cmd == "score":
        with console_to_stderr():
            rows = score_folder(args.pages, benchmark_scorer(args.lang))
        write_scores(rows, args.out)
        bad = sum(1 for r in rows if r["error"])
        print(
            f"scored {len(rows) - bad} of {len(rows)} pages", file=sys.stderr
        )
        return 0
    if args.cmd == "sample":
        sample(args.out)
        return 0
    marks, problems = read_marks(args.marks)
    for p in problems:
        print(p, file=sys.stderr)
    sys.stdout.write(
        report(
            read_scores(args.scores),
            marks,
            problems,
            args.flag_below,
            factor_meta(),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
