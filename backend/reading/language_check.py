# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Spelling and grammar for a page of English handwriting (#317).

The report's `language` section: the words a child may have spelt
another way and the sentences a grammar rule would change, each with
where it is on the page. It never changes a score, the recognised text or
anything the factors measure.

Only some rows are checked, so a scan does not slow down:

1. English handwriting rows only, in reading order. Printed lines were
   left out before this (classify.py).
2. Only rows the reader read at ROW_MIN or better and that hold a word
   the word list does not (a set lookup per word). Words the list holds
   and capitalised words need no ink check.
3. At most ROWS_MAX of those rows, the clearest first, and at most
   WORDS_PER_ROW of their words. Each is read again by the scan's own
   recogniser to get its letter scores (ocr_backends.read_line_scores)
   and judged in reading/spelling.py.

The limits are counts, not a clock: a wall-clock budget would give the
same photo different findings on a busy server, which the owner's rule
forbids (same photo, same score; CLAUDE.md). The counts were chosen so
the step's time stays small, measured in
docs/history/spelling-grammar-2026-10-24.md, and perf records it on
every scan as the "language" stage.

When the child copied a sentence or wrote one from dictation
(`expected_text`), the words read on the whole page, in reading order,
are lined up with the sentence's words. Where one word read stands
against one word of the sentence and they differ, the word the child
meant is known, so the reading is scored against that one word
(spelling.judge_meant), whether or not it is in the word list. The whole
page is lined up, not line by line, because the reader often reads a row
in pieces that match no sentence line on their own. The grammar rules
are not run: the sentence was given. Only lines holding such a word are
read again, under the same caps.

Nothing here is stored: the section goes back in the response only."""

import difflib
import re

import numpy as np

from reading import grammar, spelling
from vision import letter_boxes

ROW_MIN = 0.80
ROWS_MAX = 6
WORDS_PER_ROW = 4
# Capital-letter rules need this much of the letter's score in the case
# it was read in.
CASE_SURE = 0.9
# Rules about capitals are not applied on a row the reader was less sure
# of than this when its letter scores were not read again.
CASE_ROW_MIN = 0.90
_ENDS = re.compile(r"[.!?]")


def _english(line, langs):
    lang = str(line.get("lang") or "")
    return lang == "en" or (not lang and "en" in langs)


def _rows(hand_lines):
    """The handwriting lines in reading order: grouped into rows by where
    their middles sit, then left to right."""
    lines = [
        l
        for l in hand_lines
        if not l.get("printed_hint")
        and str(l.get("text_as_read", l.get("text", "")) or "").strip()
        and l.get("box")
    ]
    lines.sort(key=lambda l: (l["box"][1] + l["box"][3] / 2, l["box"][0]))
    rows = []
    for l in lines:
        mid = l["box"][1] + l["box"][3] / 2
        if rows:
            last = rows[-1]
            ref = last[0]["box"]
            if abs(mid - (ref[1] + ref[3] / 2)) <= 0.5 * ref[3]:
                last.append(l)
                continue
        rows.append([l])
    return [l for row in rows for l in sorted(row, key=lambda l: l["box"][0])]


def _listed(word):
    """Needs no ink check: in the list, a name, or capitalised (names the
    list cannot know, Ramesh, Lakshmi, are never judged)."""
    return (
        not word.islower()
        or spelling.is_word(word)
        or word in grammar.rules()["names"]
    )


def _odd(word):
    """A word the ink must settle: not listed, at least MIN_LETTERS long
    and not two listed words run together. Shorter unlisted words and
    joined words are left alone, and a sentence holding one is not given
    to the grammar rules."""
    return (
        not _listed(word)
        and len(word) >= spelling.MIN_LETTERS
        and not spelling.joined(word)
    )


def _text(line):
    return str(line.get("text_as_read", line.get("text", "")) or "")


def _has_odd(line):
    return any(_odd(w) for w, _s, _e in spelling.tokens(_text(line)))


def _choose(lines, needs):
    """Which lines are read again: (chosen ids, over the cap, unclear).
    needs(i, line) says whether the line holds a word to check."""
    wanted, unclear = [], 0
    for i, l in enumerate(lines):
        if not needs(i, l):
            continue
        score = float(l.get("score", 0.0) or 0.0)
        if score < ROW_MIN:
            unclear += 1
            continue
        wanted.append((-score, l["box"][1], l["box"][0], i))
    wanted.sort()
    chosen = {w[3] for w in wanted[:ROWS_MAX]}
    return chosen, max(0, len(wanted) - ROWS_MAX), unclear


def _letters(rec_text, poly):
    """[(char, column, bbox or None)] for each character the recogniser
    kept, with its place on the page."""
    chars, col_num = letter_boxes.recognise_columns(rec_text)
    placed = letter_boxes.letter_boxes(poly, chars, col_num)
    out, k = [], 0
    for ch, col in chars:
        box = None
        if ch.isalnum() and k < len(placed):
            box = placed[k]["bbox"]
            k += 1
        out.append((ch, col, box))
    return out


def _union(boxes):
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    return [int(x0), int(y0), int(x1 - x0), int(y1 - y0)]


def _estimated_box(line, text, start, end):
    """Where a span of a line's text sits, by its share of the characters
    along the line's outline: an estimate, for lines not read again."""
    poly = line.get("poly")
    n = max(1, len(text))
    if not poly or len(poly) < 4:
        return None
    # pylint: disable=protected-access
    a = letter_boxes._along(poly, start / n)
    b = letter_boxes._along(poly, end / n)
    top, bottom = min(a[1], b[1]), max(a[2], b[2])
    return [
        int(round(a[0])),
        int(round(top)),
        max(1, int(round(b[0] - a[0]))),
        max(1, int(round(bottom - top))),
    ]


def _windows(spans, letters, logp):
    """Each word's columns: its own letters' columns, widened over the
    columns the recogniser left blank on either side, and stopping at any
    column that holds another character, a space or a mark. A neighbour's
    letter or the space between words is not the word's ink."""
    blank = np.argmax(logp, axis=1) == 0
    steps = logp.shape[0]
    out = []
    for start, end in spans:
        own = [c for i, (_ch, c, _b) in letters if start <= i < end]
        if not own:
            out.append(None)
            continue
        lo, hi = own[0], own[-1]
        while lo > 0 and blank[lo - 1]:
            lo -= 1
        while hi + 1 < steps and blank[hi + 1]:
            hi += 1
        out.append((lo, hi))
    return out


def _read_again(arr, line, read_scores):
    """(text, letters by text index, log scores) for a line read again,
    or None."""
    crop = letter_boxes.crop_line(arr, line.get("poly"))
    if crop is None:
        return None
    got = read_scores(crop, line.get("lang") or "en")
    if not got:
        return None
    rec_text, matrix, characters = got
    text = rec_text[0] if isinstance(rec_text, (tuple, list)) else ""
    letters = _letters(rec_text, line.get("poly"))
    # Match the kept characters to the text: the recogniser drops spaces
    # and punctuation between words, never letters.
    by_index, k = {}, 0
    for i, ch in enumerate(text):
        if k < len(letters) and letters[k][0] == ch:
            by_index[i] = letters[k]
            k += 1
    if k != len(letters):
        return None
    logp = spelling.reduce_scores(matrix, characters)
    return text, by_index, logp, matrix, characters


def _case_sure(letter, matrix, characters):
    """The recogniser's share for the letter in the case it was read."""
    ch, col, _box = letter
    if col >= len(matrix):
        return False
    row = matrix[col]
    own = [i for i, c in enumerate(characters) if c == ch]
    other = [i for i, c in enumerate(characters) if c == ch.swapcase()]
    if not own or not other:
        return False
    a = float(sum(row[i] for i in own))
    b = float(sum(row[i] for i in other))
    return a + b > 0 and a / (a + b) >= CASE_SURE


def _checked_line(line, again):
    """Tokens of a line read again, each judged by the ink when odd."""
    text, by_index, logp, matrix, characters = again
    found = spelling.tokens(text)
    spans = [(s, e) for _w, s, e in found]
    letters = sorted(by_index.items())
    windows = _windows(spans, letters, logp)
    out, judged = [], 0
    for (word, start, end), window in zip(found, windows):
        own = [by_index[i] for i in range(start, end) if i in by_index]
        token = {
            "raw": word,
            "text": word,
            "line": line.get("evidence_id"),
            "span": [start, end],
            "bbox": _union([b for _c, _col, b in own]),
            "placed": "letters",
            "case_sure": bool(own) and _case_sure(own[0], matrix, characters),
        }
        if _listed(word):
            token["trusted"] = True
            token["status"] = "word"
        elif not _odd(word):
            token["trusted"] = False
            token["status"] = "unchecked"
        elif window is None or judged >= WORDS_PER_ROW:
            token["trusted"] = False
            token["status"] = "unchecked"
        else:
            judged += 1
            lo, hi = window
            cols = [c - lo for _ch, c, _b in own]
            verdict = spelling.judge(logp[lo : hi + 1], word, cols)
            token["status"] = verdict["status"]
            token["text"] = verdict["word"]
            token["trusted"] = verdict["status"] in ("misread", "written")
            token["suggestion"] = verdict.get("suggestion")
            token["margin"] = verdict.get("margin")
            token["letter_min"] = verdict.get("letter_min")
        out.append(token)
    return text, out


# A word read is paired with a different sentence word only when their
# letters are this alike (difflib ratio) and it has at least
# PAIR_LETTERS letters: neet and neat are 0.75, rite and write 0.89, and
# and the 0.33. Lower let through the reader's run-together pieces
# (tersevry for letters) and cut words (da for day).
PAIR_MIN = 0.7
PAIR_LETTERS = 3


def _similar(a, b):
    """How alike two words are, 0 when their lengths differ by more than
    one letter (a word the reader split, wri te, or joined is not a
    spelling) or the word read is shorter than PAIR_LETTERS."""
    if abs(len(a) - len(b)) > 1 or len(a) < PAIR_LETTERS:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _pair_block(read, meant):
    """[(k, j)] pairing read[k] with meant[j], in order, most alike in
    total, only pairs at least PAIR_MIN alike (_similar): a dropped,
    added or split word around them does not stop the others pairing."""
    n, m = len(read), len(meant)
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    for k in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            r = _similar(read[k], meant[j])
            take = r + best[k + 1][j + 1] if r >= PAIR_MIN else -1.0
            best[k][j] = max(take, best[k + 1][j], best[k][j + 1])
    out, k, j = [], 0, 0
    while k < n and j < m:
        r = _similar(read[k], meant[j])
        if r >= PAIR_MIN and best[k][j] == r + best[k + 1][j + 1]:
            out.append((k, j))
            k, j = k + 1, j + 1
        elif best[k][j] == best[k + 1][j]:
            k += 1
        else:
            j += 1
    return out


def _page_pairs(line_tokens, meant):
    """{(line index, start, end): the sentence's word} for each word read
    that lines up with a different word of the sentence, the whole page
    in reading order against the whole sentence. Where the two do not
    line up word for word (the reader drops, adds and splits words), only
    alike words are paired (_pair_block)."""
    read = [
        (i, w, s, e)
        for i, tokens in enumerate(line_tokens)
        for w, s, e in tokens
    ]
    a = [r[1].lower() for r in read]
    b = [w.lower() for w in meant]
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    out = {}
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op != "replace":
            continue
        if i2 - i1 == j2 - j1:
            pairs = [
                (k, k)
                for k in range(i2 - i1)
                if _similar(a[i1 + k], b[j1 + k]) >= PAIR_MIN
            ]
        else:
            pairs = _pair_block(a[i1:i2], b[j1:j2])
        for k, j in pairs:
            i, _w, s, e = read[i1 + k]
            out[(i, s, e)] = meant[j1 + j]
    return out


def _sentence_line(line, again, meant_for):
    """Tokens of a line read again on a sentence page: each word lined up
    with a different word of the sentence (meant_for, by its span) is
    judged against that word. The tokens are never given to the grammar
    rules (trusted is False)."""
    text, by_index, logp, _matrix, _chars = again
    found = spelling.tokens(text)
    spans = [(s, e) for _w, s, e in found]
    windows = dict(zip(spans, _windows(spans, sorted(by_index.items()), logp)))
    out, judged = [], 0
    for word, start, end in found:
        own = [by_index[i] for i in range(start, end) if i in by_index]
        token = {
            "raw": word,
            "text": word,
            "line": line.get("evidence_id"),
            "span": [start, end],
            "bbox": _union([b for _c, _col, b in own]),
            "placed": "letters",
            "trusted": False,
            "status": "as_meant",
        }
        meant = meant_for.get((start, end))
        window = windows.get((start, end))
        if meant and window and judged < WORDS_PER_ROW:
            judged += 1
            lo, hi = window
            cols = [c - lo for _ch, c, _b in own]
            verdict = spelling.judge_meant(
                logp[lo : hi + 1], word, meant, cols
            )
            token["status"] = verdict["status"]
            token["suggestion"] = meant
            token["against"] = "sentence"
            token["margin"] = verdict.get("margin")
            token["letter_min"] = verdict.get("letter_min")
            token["row_score"] = line.get("score")
        out.append(token)
    return text, out


def _plain_line(line, sentence=False):
    """Tokens of a line not read again: trusted when listed (or a name)
    on a clear row and not on a sentence page, with estimated places."""
    text = _text(line)
    score = float(line.get("score", 0.0) or 0.0)
    out = []
    for word, start, end in spelling.tokens(text):
        listed = _listed(word)
        out.append(
            {
                "raw": word,
                "text": word,
                "line": line.get("evidence_id"),
                "span": [start, end],
                "bbox": _estimated_box(line, text, start, end),
                "placed": "estimated",
                "case_sure": score >= CASE_ROW_MIN,
                "trusted": listed and score >= ROW_MIN and not sentence,
                "status": "word" if listed else "unchecked",
            }
        )
    return text, out


# A full stop after one of these, a single letter or a number is not
# the end of a sentence (e.g., i.e., Mr., 1.).
_ABBREVIATIONS = {"etc", "eg", "ie", "mr", "mrs", "ms", "dr", "st", "vs"}
_BEFORE = re.compile(r"([A-Za-z0-9]+)\W*$")


def _ends(text):
    """Where the line's sentences end: ! and ?, and a full stop after a
    word of two letters or more that is not an abbreviation, followed by
    a space or the end of the line."""
    out = []
    for m in _ENDS.finditer(text):
        at = m.start()
        if m.group(0) == ".":
            after = text[at + 1 : at + 2]
            before = _BEFORE.search(text[:at])
            word = before.group(1) if before else ""
            if (
                (after and not after.isspace())
                or len(word) < 2
                or word.isdigit()
                or word.lower() in _ABBREVIATIONS
            ):
                continue
        out.append({"end": True, "at": at})
    return out


def _with_ends(text, words):
    """The line's words with its sentence ends between them."""
    ends = _ends(text)
    merged = sorted(
        [(w["span"][0], 1, w) for w in words]
        + [(e["at"], 0, e) for e in ends],
        key=lambda x: (x[0], x[1]),
    )
    return [m[2] for m in merged]


def _place(tokens):
    """Where a finding is: one box per line it touches."""
    by_line = {}
    for t in tokens:
        key = t.get("line")
        by_line.setdefault(key, []).append(t)
    out = []
    for line, ts in by_line.items():
        out.append(
            {
                "line": line,
                "bbox": _union([t.get("bbox") for t in ts]),
                "placed": (
                    "letters"
                    if all(t["placed"] == "letters" for t in ts)
                    else "estimated"
                ),
            }
        )
    return out


def check(arr, hand_lines, langs, read_scores, expected_text="", detail=False):
    """The `language` section of a report. langs: the scan's resolved
    reading languages; read_scores(crop, lang) is
    ocr_backends.read_line_scores, or None where PaddleOCR does not read
    the page; expected_text: the sentence the child copied or wrote from
    dictation, if any. detail adds each spelling finding's margin and
    weakest letter, for scripts/language_eval.py only."""
    english = [l for l in hand_lines if _english(l, langs)]
    if not english:
        return {"version": 1, "checked": False, "reason": "not_english"}
    if read_scores is None:
        return {"version": 1, "checked": False, "reason": "no_letter_scores"}
    lines = _rows(english)
    if not lines:
        return {"version": 1, "checked": False, "reason": "no_text"}
    meant = [w for w, _s, _e in spelling.tokens(expected_text or "")]
    if meant:
        first = _page_pairs([spelling.tokens(_text(l)) for l in lines], meant)
        marked = {i for i, _s, _e in first}
        chosen, over_cap, unclear = _choose(lines, lambda i, _l: i in marked)
    else:
        chosen, over_cap, unclear = _choose(lines, lambda _i, l: _has_odd(l))
    again = {
        i: _read_again(arr, lines[i], read_scores) for i in sorted(chosen)
    }
    again = {i: a for i, a in again.items() if a is not None}
    if meant:
        # Line the page up again with what the chosen lines read now.
        tokens = [
            spelling.tokens(again[i][0] if i in again else _text(l))
            for i, l in enumerate(lines)
        ]
        pairs = _page_pairs(tokens, meant)
    stream = []
    for i, line in enumerate(lines):
        if i in again and meant:
            for_line = {(s, e): w for (j, s, e), w in pairs.items() if j == i}
            text, words = _sentence_line(line, again[i], for_line)
        elif i in again:
            text, words = _checked_line(line, again[i])
        else:
            text, words = _plain_line(line, sentence=bool(meant))
        stream.extend(_with_ends(text, words))
    read_again = len(again)
    past = grammar.rules()["past"]
    spelling_out = [
        {
            "written": t["raw"],
            "suggestion": t["suggestion"],
            "kind": spelling.kind(t["raw"], t["suggestion"]),
            "against": t.get("against", "list"),
            "places": _place([t]),
            **(
                {
                    "margin": t.get("margin"),
                    "letter_min": t.get("letter_min"),
                    "row_score": t.get("row_score"),
                }
                if detail
                else {}
            ),
        }
        for t in stream
        if not t.get("end")
        and t.get("status") == "written"
        and t.get("suggestion")
        and (t.get("against") or t["raw"].lower() not in past)
    ]
    grammar_out = [
        {
            "rule": f["rule"],
            "written": f["written"],
            "suggestion": f["suggestion"],
            "places": _place(f["tokens"]),
        }
        for f in grammar.find(stream)
    ]
    return {
        "version": 1,
        "checked": True,
        "reason": None,
        "rows": {
            "read": len(lines),
            "checked": read_again,
            "not_read": len(chosen) - read_again,
            "over_cap": over_cap,
            "unclear": unclear,
        },
        "spelling": spelling_out,
        "grammar": grammar_out,
    }
