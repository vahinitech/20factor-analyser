# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""English spelling, checked against the ink (#317).

A dictionary alone cannot check handwriting: on 200 real pages 95% of the
words it flagged were the reader's misreads, not the writer's spelling
(#317). The reader's own letter scores settle it. For a word the reader
read that is not in the word list, every listed word one or two letters
away is scored on the reader's scores for that part of the row (the CTC
probability of the word, the same quantity the recogniser was trained
on). Three outcomes:

- a listed word fits the ink almost as well as the reading: the reader
  misread it, so the text is corrected quietly and nothing is said;
- no listed word comes close and every letter was read clearly: the
  writer wrote this spelling, and the most likely intended word is
  suggested;
- anything else: unclear, and nothing is said about the word.

The word list is SCOWL (backend/languages/words, built by
scripts/build_wordlist.py, its licence beside it). Nothing here runs a
model or keeps a word: the caller passes the scores of one row and gets
an answer back."""

import gzip
import hashlib
import math
import os
import re
from functools import lru_cache

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WORDS_FILE = os.path.join(
    os.path.dirname(HERE), "languages", "words", "en.txt.gz"
)
NEVER_FILE = os.path.join(os.path.dirname(WORDS_FILE), "never-suggest.txt.gz")
# What scripts/build_wordlist.py makes from SCOWL 2020.12.07; a test holds
# the files to these, so the lists change only by rebuilding them.
WORDS_SHA256 = (
    "2a9f7161feb8ebaec87aa59cd5e44a8f076ffd5ee8b033218ef32541febcbe83"
)
NEVER_SHA256 = (
    "00401af0c358bbb620dbb747c88fdde166fcbdf8f291d5a38f22c36c86a5fe6d"
)

# Suggestions two letters away come only from words at this SCOWL size
# or below (about 52,000 common words, the ones a child means): a delete
# index of the whole list costs 77 MB, of these about half.
COMMON_SIZE = 35
# At most this many listed words are scored for one word read, nearest
# and most common first. A fixed number, so the work per word is bounded
# whatever the load (same photo, same answer).
MAX_CANDIDATES = 40

# The decision, in natural-log units of the CTC probability. A listed
# word within MISREAD_LN of the reading fits the ink (1 in 20 as likely
# or better): the reader misread it. The reading must beat every listed
# word by WRITTEN_LN (10,000 times as likely) and each of its letters
# must score at least LETTER_MIN before we say the writer spelt it that
# way. Measured on real, benchmark and planted pages
# (docs/history/spelling-grammar-2026-10-24.md): 100 times and 0.5 let
# through 40 of the writers' own words and 88 others; these let through
# 4 and none.
MISREAD_LN = math.log(20.0)
WRITTEN_LN = math.log(10000.0)
LETTER_MIN = 0.9
# Words shorter than this are not judged: on real pages they were
# abbreviations and pieces of words (etc, sth, swa).
MIN_LETTERS = 4

_LETTERS = "abcdefghijklmnopqrstuvwxyz"
# Reduced alphabet for scoring: 0 blank, 1-26 letters (either case),
# 27 apostrophe, 28 any other character.
_APOS = 27
_OTHER = 28
_FLOOR = 1e-9
_TOKEN = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)*")


def _read(path, digest):
    """A word list's lines, after checking the file is the one
    scripts/build_wordlist.py made."""
    with open(path, "rb") as f:
        raw = f.read()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise RuntimeError(f"{os.path.basename(path)} is not the built list")
    return gzip.decompress(raw).decode("ascii").splitlines()


@lru_cache(maxsize=1)
def words():
    """{word: SCOWL size} for the English list, loaded once per process."""
    out = {}
    for line in _read(WORDS_FILE, WORDS_SHA256):
        word, size = line.split()
        out[word] = int(size)
    return out


@lru_cache(maxsize=1)
def never_suggest():
    """Words a child's report never offers as a spelling (SCOWL's taboo
    lists)."""
    return frozenset(
        line.strip() for line in _read(NEVER_FILE, NEVER_SHA256) if line
    )


def is_word(word):
    """True when the word, in lower case, is in the list. A possessive
    's on a listed word counts."""
    w = str(word or "").lower().replace("’", "'")
    table = words()
    if w in table:
        return True
    return w.endswith("'s") and w[:-2] in table


def tokens(text):
    """[(word, start, end)] of the letter words in a line of text, in
    order. An apostrophe inside a word belongs to it (don't)."""
    return [(m.group(0), m.start(), m.end()) for m in _TOKEN.finditer(text)]


def _deletes(word):
    return {word[:i] + word[i + 1 :] for i in range(len(word))}


@lru_cache(maxsize=1)
def _common_index():
    """{word with one letter deleted: (listed words)} over the common
    words, for suggestions two letters away."""
    index = {}
    for word, size in words().items():
        if size > COMMON_SIZE:
            continue
        for d in _deletes(word) | {word}:
            index.setdefault(d, []).append(word)
    return {k: tuple(sorted(v)) for k, v in index.items()}


def _edits1(word):
    """Every string one edit away: a letter left out, one added, one
    changed, or two neighbours swapped (an apostrophe may be added)."""
    splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
    out = {a + b[1:] for a, b in splits if b}
    out |= {a + b[1] + b[0] + b[2:] for a, b in splits if len(b) > 1}
    out |= {a + c + b[1:] for a, b in splits if b for c in _LETTERS}
    out |= {a + c + b for a, b in splits for c in _LETTERS + "'"}
    out.discard(word)
    return out


def distance(a, b):
    """Edit distance with neighbour swaps counted as one edit (optimal
    string alignment)."""
    rows = [list(range(len(b) + 1))]
    for i, ca in enumerate(a, 1):
        row = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            row[j] = min(
                rows[-1][j] + 1,
                row[j - 1] + 1,
                rows[-1][j - 1] + (ca != cb),
            )
            if (
                i > 1
                and j > 1
                and ca == b[j - 2]
                and a[i - 2] == cb
                and len(rows) > 1
            ):
                row[j] = min(row[j], rows[-2][j - 2] + 1)
        rows.append(row)
    return rows[-1][-1]


_VOWELS = set("aeiouy")
# Pairs a child swaps by sound: one of them costs half an edit.
_SOUND_PAIRS = {
    frozenset(p) for p in ("sz", "ck", "cs", "kq", "fv", "ij", "wv")
}


def _sub_cost(a, b):
    if a == b:
        return 0.0
    if (a in _VOWELS and b in _VOWELS) or frozenset((a, b)) in _SOUND_PAIRS:
        return 0.5
    return 1.0


def _gap_cost(word, i):
    """Leaving out, or adding, word[i]: half an edit when it doubles a
    neighbour (storry, untill) or is a vowel (slowley, evry)."""
    ch = word[i]
    near = word[i - 1 : i] + word[i + 1 : i + 2]
    return 0.5 if ch in near or ch in _VOWELS else 1.0


def slip_cost(written, meant):
    """How likely a child is to write `written` for `meant`, as an edit
    cost: the slips children make most (a vowel for a vowel, a doubled
    letter, s for z, two letters swapped) cost half an edit."""
    a, b = written, meant
    rows = [[0.0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        rows[i][0] = rows[i - 1][0] + _gap_cost(a, i - 1)
    for j in range(1, len(b) + 1):
        rows[0][j] = rows[0][j - 1] + _gap_cost(b, j - 1)
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            best = min(
                rows[i - 1][j] + _gap_cost(a, i - 1),
                rows[i][j - 1] + _gap_cost(b, j - 1),
                rows[i - 1][j - 1] + _sub_cost(a[i - 1], b[j - 1]),
            )
            if (
                i > 1
                and j > 1
                and a[i - 1] == b[j - 2]
                and a[i - 2] == b[j - 1]
            ):
                best = min(best, rows[i - 2][j - 2] + 0.5)
            rows[i][j] = best
    return rows[-1][-1]


def candidates(word):
    """Listed words a writer may have meant: [(edits, size, word)], one
    edit away from the whole list, two away from the common words, most
    likely first (the child's usual slips, the same first letter, the
    more common word), at most MAX_CANDIDATES. Never a taboo word."""
    w = str(word or "").lower().replace("\u2019", "'")
    table = words()
    found = {c for c in _edits1(w) if c in table}
    index = _common_index()
    for d in _deletes(w) | {w}:
        found.update(index.get(d, ()))
    found.discard(w)
    found -= never_suggest()
    ranked = sorted(
        (slip_cost(w, c), c[:1] != w[:1], table[c], c)
        for c in found
        if abs(len(c) - len(w)) <= 2 and distance(w, c) <= 2
    )
    return [(distance(w, c), size, c) for _cost, _f, size, c in ranked][
        :MAX_CANDIDATES
    ]


def reduce_scores(matrix, characters):
    """The recogniser's column scores (columns x its characters, 0 the
    blank) as log probabilities over the reduced alphabet: a letter's
    two cases are added together, everything that is not a letter, the
    apostrophe or the blank is one "other" symbol."""
    m = np.asarray(matrix, dtype=np.float64)
    out = np.zeros((m.shape[0], _OTHER + 1), dtype=np.float64)
    out[:, 0] = m[:, 0]
    used = np.zeros(m.shape[1], dtype=bool)
    used[0] = True
    for i, ch in enumerate(characters):
        if i == 0 or i >= m.shape[1]:
            continue
        low = ch.lower()
        if len(low) == 1 and low in _LETTERS:
            out[:, 1 + _LETTERS.index(low)] += m[:, i]
            used[i] = True
        elif ch in ("'", "’"):
            out[:, _APOS] += m[:, i]
            used[i] = True
    out[:, _OTHER] = m[:, ~used].sum(axis=1)
    return np.log(np.maximum(out, _FLOOR))


def labels(word):
    """The reduced-alphabet labels of a word, or None if it holds a
    character the alphabet has no place for."""
    out = []
    for ch in str(word or "").lower():
        if ch in _LETTERS:
            out.append(1 + _LETTERS.index(ch))
        elif ch in ("'", "’"):
            out.append(_APOS)
        else:
            return None
    return out


def ctc_log_likelihood(logp, seq):
    """log P(seq | columns) under CTC: the sum over every way the columns
    can spell seq with blanks between and repeats merged (the forward
    algorithm, in log space). -inf when there are too few columns."""
    logp = np.asarray(logp, dtype=np.float64)
    steps = logp.shape[0]
    if not seq:
        return float(logp[:, 0].sum()) if steps else 0.0
    ext = [0]
    for s in seq:
        ext += [s, 0]
    n = len(ext)
    ext = np.asarray(ext)
    # A label may skip the blank before it unless it repeats the label
    # two places back (then the blank between them is required).
    skip = np.zeros(n, dtype=bool)
    skip[2:] = (ext[2:] != 0) & (ext[2:] != ext[:-2])
    neg = -np.inf
    alpha = np.full(n, neg)
    if steps == 0:
        return neg
    alpha[0] = logp[0, ext[0]]
    if n > 1:
        alpha[1] = logp[0, ext[1]]
    for t in range(1, steps):
        stay = alpha
        one = np.concatenate(([neg], alpha[:-1]))
        two = np.where(skip, np.concatenate(([neg, neg], alpha[:-2])), neg)
        alpha = np.logaddexp(np.logaddexp(stay, one), two) + logp[t, ext]
    total = np.logaddexp(alpha[-1], alpha[-2]) if n > 1 else alpha[-1]
    return float(total)


def judge(logp, word, letter_cols):
    """What the ink says about one word the reader read and the list
    does not hold. logp: the reduced log scores of the word's columns
    (its window); letter_cols: each read letter's column inside that
    window. Returns {"status": "misread" | "written" | "unclear",
    "word": the word to use, "suggestion": the intended word or None,
    "margin": how many log units the reading beats the best listed
    word by}."""
    read = labels(word)
    if read is None:
        return {"status": "unclear", "word": word, "suggestion": None}
    read_ll = ctc_log_likelihood(logp, read)
    scored = []
    for rank, (_edits, _size, cand) in enumerate(candidates(word)):
        seq = labels(cand)
        if seq is None:
            continue
        scored.append((ctc_log_likelihood(logp, seq), -rank, cand))
    if not scored or not math.isfinite(read_ll):
        return {"status": "unclear", "word": word, "suggestion": None}
    best = max(scored)
    margin = read_ll - best[0]
    if margin <= MISREAD_LN:
        return {
            "status": "misread",
            "word": _same_case(best[2], word),
            "suggestion": None,
            "margin": round(margin, 2),
        }
    letter_min = min(
        (
            math.exp(logp[c, lab])
            for c, lab in zip(letter_cols, [x for x in read if x != _APOS])
            if 0 <= c < logp.shape[0]
        ),
        default=0.0,
    )
    if margin >= WRITTEN_LN and letter_min >= LETTER_MIN:
        # The writer meant the most likely slip (candidates' order).
        meant = max(scored, key=lambda s: s[1])
        return {
            "status": "written",
            "word": word,
            "suggestion": _same_case(meant[2], word),
            "margin": round(margin, 2),
            "letter_min": round(letter_min, 3),
        }
    return {
        "status": "unclear",
        "word": word,
        "suggestion": None,
        "margin": round(margin, 2),
        "letter_min": round(letter_min, 3),
    }


def _same_case(word, like):
    if like[:1].isupper() and like[1:].islower():
        return word[:1].upper() + word[1:]
    return word


def joined(word):
    """True when the word is two listed words run together (onthe,
    drawsbig): a space the writer or the reader left out, which is the
    word-spacing skill's business, never a spelling."""
    w = str(word or "").lower()
    for i in range(1, len(w)):
        a, b = w[:i], w[i:]
        if (
            (len(a) > 1 or a in ("a", "i"))
            and (len(b) > 1 or b in ("a", "i"))
            and is_word(a)
            and is_word(b)
        ):
            return True
    return False


def kind(written, meant):
    """Which kind of slip turns meant into written, for the tip:
    letter_order, missing_letter, extra_letter, other_letter or letters
    (more than one)."""
    a, b = written.lower(), meant.lower()
    if distance(a, b) != 1:
        return "letters"
    if len(a) == len(b):
        diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        return "letter_order" if len(diff) == 2 else "other_letter"
    return "missing_letter" if len(a) < len(b) else "extra_letter"
