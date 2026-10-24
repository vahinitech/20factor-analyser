# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""English grammar for children's writing, as fixed rules (#317).

The rules are the common slips of a child writing English: a capital for
a name, "I" on its own, a or an, he/she/it with -s, the past of go, run
and eat, and "me and Bheema" as the subject.
Their words are data in backend/languages/skills/en.json (#221 keeps
language rules as data); this module only applies them.

A rule's mark is kept only when every word on the lines it looks at,
and on the line of the word before it, is trusted: the spelling check
(reading/language_check.py) read it as a listed word or a name on a
clear row, or checked it against the ink. The reader's misreads would
otherwise make false grammar marks: of 22 matches of the old browser
rules on 200 real pages, 14 came from misreads (#317). Lines, not whole
sentences, because children's pages often have no full stop the reader
sees, and one unchecked word would then silence the whole page. Rules
about capitals also need the case to be clear: letters such as c, o and
s look the same in both cases, and are never judged.

A rule that looks at two or more words needs them on one line as the
reader read it: across lines the reading order can be wrong. "I" is
judged only before a doing word (i ran, i am) and a or an only before a
lower-case word of three letters or more: on real pages the reader read
"in" as "i", and abbreviations (TV) follow "an" correctly.

No rule about full stops or a capital after one. The reader drops small
dots and reads stray marks as dots: on 183 real pages (GNHK) all nine
"capital after a full stop" marks the rule made were wrong by the
transcript (docs/history/spelling-grammar-2026-10-24.md)."""

import json
import os
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_FILE = os.path.join(
    os.path.dirname(HERE), "languages", "skills", "en.json"
)
RULES = (
    "capital_name",
    "capital_i",
    "a_an",
    "verb_s",
    "past_tense",
    "me_and",
)


@lru_cache(maxsize=1)
def rules():
    """The English rule data, loaded once."""
    with open(RULES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    third = data["third_person"]
    past = data["irregular_past"]
    verbs = (
        set(data["subject_verbs"])
        | set(third["verbs"])
        | set(third["verbs"].values())
        | set(past)
        | set(past.values())
    )
    return {
        "case_unclear": set(data["case_unclear_letters"]),
        "names": set(data["names"]) - set(data["names_also_words"]),
        "subjects": set(third["subjects"]),
        "not_after": set(third["not_after"]),
        "verb_s": dict(third["verbs"]),
        "past": dict(past),
        "consonant_starts": tuple(data["a_an"]["consonant_sound_starts"]),
        "vowel_words": set(data["a_an"]["vowel_sound_words"]),
        "subject_verbs": verbs,
    }


def _cap(word):
    return word[:1].upper() + word[1:]


def _sentences(tokens):
    """The page's sentences: runs of words between the ends (. ! ?) the
    reader read."""
    out, words = [], []
    for t in tokens:
        if t.get("end"):
            if words:
                out.append(words)
            words = []
            continue
        words.append(t)
    if words:
        out.append(words)
    return out


def _vowel_sound(word, r):
    w = word.lower()
    if w in r["vowel_words"]:
        return True
    return w[:1] in "aeiou" and not w.startswith(r["consonant_starts"])


def _case_ok(token, r):
    """A capital rule may judge this word: its first letter looks
    different in the two cases and was read clearly."""
    first = token["text"][:1]
    return (
        first.isalpha()
        and first.lower() not in r["case_unclear"]
        and token.get("case_sure", False)
    )


def _one_line(words):
    return len({t.get("line") for t in words}) == 1


def _finding(rule, words, suggestion):
    return {
        "rule": rule,
        "written": " ".join(t["raw"] for t in words),
        "suggestion": suggestion,
        "tokens": words,
    }


def _sentence_findings(words, r):
    out = []
    lows = [t["text"].lower() for t in words]
    for i, t in enumerate(words):
        text, low = t["text"], lows[i]
        if (
            text == "i"
            and t.get("case_sure", False)
            and i + 1 < len(words)
            and lows[i + 1] in r["subject_verbs"]
            and _one_line(words[i : i + 2])
        ):
            out.append(_finding("capital_i", [t], "I"))
        elif low in r["names"] and text[:1].islower() and _case_ok(t, r):
            out.append(_finding("capital_name", [t], _cap(text)))
        if low in ("a", "an") and i + 1 < len(words):
            nxt = words[i + 1]["text"]
            if nxt.islower() and len(nxt) > 2 and _one_line(words[i : i + 2]):
                want = "an" if _vowel_sound(nxt, r) else "a"
                if want != low:
                    word = _cap(want) if text[:1].isupper() else want
                    out.append(
                        _finding("a_an", words[i : i + 2], f"{word} {nxt}")
                    )
        if (
            low in r["subjects"]
            and i + 1 < len(words)
            and lows[i + 1] in r["verb_s"]
            and (i == 0 or lows[i - 1] not in r["not_after"])
            and _one_line(words[i : i + 2])
        ):
            verb = r["verb_s"][lows[i + 1]]
            out.append(_finding("verb_s", words[i : i + 2], f"{text} {verb}"))
        if low in r["past"]:
            want = r["past"][low]
            out.append(
                _finding(
                    "past_tense",
                    [t],
                    _cap(want) if text[:1].isupper() else want,
                )
            )
    if len(words) >= 4 and _one_line(words[:4]):
        a, b, c, d = lows[:4]
        if b == "and" and c == "me" and d in r["subject_verbs"]:
            out.append(
                _finding(
                    "me_and",
                    words[:3],
                    f"{words[0]['text']} and I",
                )
            )
        elif a == "me" and b == "and" and d in r["subject_verbs"]:
            out.append(
                _finding("me_and", words[:3], f"{words[2]['text']} and I")
            )
    return out


def find(tokens):
    """Grammar findings for a page: tokens are the page's words and
    sentence ends in reading order, each {"text": the word to judge,
    "raw": as written, "trusted", "case_sure", "end"} plus whatever the
    caller needs back. Each finding is {"rule", "written", "suggestion",
    "tokens"}; a finding is dropped when a line it looks at holds an
    untrusted word."""
    r = rules()
    trusted = {}
    for t in tokens:
        if not t.get("end"):
            key = t.get("line")
            trusted[key] = trusted.get(key, True) and bool(t.get("trusted"))
    out = []
    for words in _sentences(tokens):
        for f in _sentence_findings(words, r):
            first = words.index(f["tokens"][0])
            looked = f["tokens"] + words[max(0, first - 1) : first]
            if all(trusted.get(t.get("line"), False) for t in looked):
                out.append(f)
    return out
