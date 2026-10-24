# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The spelling and grammar check (#317): reading/spelling.py,
reading/grammar.py and reading/language_check.py.

The recogniser is replaced by a fake that turns a line of text into the
column scores PaddleOCR would give: each character fires one column, a
blank follows. A character can be made unsure (its score shared with
another letter), which is how a misread looks. Nothing here loads a
model."""

import copy
import hashlib
import itertools
import json
import math
import os
import sys
import unittest
from datetime import date

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from reading import grammar, language_check, spelling  # noqa: E402
from report import compact_reports, contract_schemas  # noqa: E402
from report.report_contract import public_report  # noqa: E402
from server import entitlements, report_store  # noqa: E402
from backend.tests.test_schemas import realistic_payload  # noqa: E402

CHARACTERS = (
    ["blank"]
    + list("abcdefghijklmnopqrstuvwxyz")
    + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    + list("0123456789")
    + list(" .,'!?")
)


def fake_scores(text, unsure=None, sure=0.999):
    """(rec_text, matrix, characters) as ocr_backends.read_line_scores
    gives them. unsure: {text index: (other char, share)}, the column
    split between the written character and another one."""
    unsure = unsure or {}
    cols, kept, words, word_cols, current, cur_cols = [], [], [], [], [], []
    for i, ch in enumerate(text):
        row = np.full(len(CHARACTERS), (1 - sure) / (len(CHARACTERS) - 1))
        idx = CHARACTERS.index(ch)
        if i in unsure:
            other, share = unsure[i]
            row[:] = 0.001
            row[idx] = 1 - share
            row[CHARACTERS.index(other)] = share
        else:
            row[idx] = sure
        row /= row.sum()
        col = len(cols)
        cols.append(row)
        blank = np.full(len(CHARACTERS), 0.00001)
        blank[0] = 1.0
        cols.append(blank / blank.sum())
        if ch.isalnum():
            current.append(ch)
            cur_cols.append(col)
            kept.append(ch)
        elif current:
            words.append(current)
            word_cols.append(cur_cols)
            current, cur_cols = [], []
    if current:
        words.append(current)
        word_cols.append(cur_cols)
    matrix = np.asarray(cols, dtype=np.float32)
    rec_text = (text, [len(cols), words, word_cols, ["en&num"] * len(words)])
    return rec_text, matrix, list(CHARACTERS)


def line(text, y=100, score=0.95, ident=None, x=40):
    w = 22 * len(text)
    return {
        "text": text,
        "text_as_read": text,
        "score": score,
        "lang": "en",
        "printed_hint": False,
        "box": [x, y, w, 50],
        "poly": [[x, y], [x + w, y], [x + w, y + 50], [x, y + 50]],
        "evidence_id": ident or f"line_{y}",
    }


class FakeReader:
    """read_scores for check(): reads each crop as its line's text."""

    def __init__(self, texts, unsure=None):
        self.texts = list(texts)
        self.unsure = unsure or {}
        self.calls = 0

    def __call__(self, _crop, _lang):
        text = self.texts[self.calls]
        self.calls += 1
        return fake_scores(text, self.unsure.get(text))


PAGE = np.full((900, 1400, 3), 255, dtype=np.uint8)


def run(lines, reader, expected=""):
    return language_check.check(PAGE, lines, ["en"], reader, expected)


class TestCtc(unittest.TestCase):
    def test_matches_every_path_summed(self):
        rng = np.random.default_rng(3)
        p = rng.random((5, 4))
        p /= p.sum(axis=1, keepdims=True)

        def collapse(path):
            out, prev = [], None
            for s in path:
                if s != prev and s != 0:
                    out.append(s)
                prev = s
            return out

        for seq in ([1], [1, 2], [1, 1], [2, 3, 1]):
            total = sum(
                math.prod(p[t, s] for t, s in enumerate(path))
                for path in itertools.product(range(4), repeat=5)
                if collapse(path) == seq
            )
            self.assertAlmostEqual(
                spelling.ctc_log_likelihood(np.log(p), seq),
                math.log(total),
                places=9,
            )

    def test_too_few_columns_is_impossible(self):
        logp = np.log(np.full((2, 4), 0.25))
        self.assertEqual(
            spelling.ctc_log_likelihood(logp, [1, 1, 1]), -math.inf
        )


class TestWords(unittest.TestCase):
    def test_list_holds_british_and_american(self):
        for w in ("colour", "color", "centre", "realise", "don't", "every"):
            self.assertTrue(spelling.is_word(w), w)
        self.assertTrue(spelling.is_word("Bheema's") is False)
        self.assertTrue(spelling.is_word("dog's"))
        self.assertFalse(spelling.is_word("freind"))

    def test_candidates_put_the_meant_word_first(self):
        for written, meant in (
            ("freind", "friend"),
            ("smal", "small"),
            ("evry", "every"),
            ("becaus", "because"),
            ("untill", "until"),
            ("recieve", "receive"),
        ):
            self.assertEqual(spelling.candidates(written)[0][2], meant)

    def test_candidates_are_bounded(self):
        self.assertLessEqual(
            len(spelling.candidates("tat")), spelling.MAX_CANDIDATES
        )

    def test_kind_names_the_slip(self):
        self.assertEqual(spelling.kind("freind", "friend"), "letter_order")
        self.assertEqual(spelling.kind("smal", "small"), "missing_letter")
        self.assertEqual(spelling.kind("untill", "until"), "extra_letter")
        self.assertEqual(spelling.kind("tox", "fox"), "other_letter")
        self.assertEqual(spelling.kind("becos", "because"), "letters")

    def test_word_list_matches_its_build(self):
        """The lists are SCOWL's, built by scripts/build_wordlist.py; its
        licence travels with them, and they change only by a rebuild."""
        folder = os.path.dirname(spelling.WORDS_FILE)
        self.assertTrue(
            os.path.isfile(os.path.join(folder, "SCOWL-Copyright.txt"))
        )
        for path, digest in (
            (spelling.WORDS_FILE, spelling.WORDS_SHA256),
            (spelling.NEVER_FILE, spelling.NEVER_SHA256),
        ):
            with open(path, "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), digest)
        self.assertGreater(len(spelling.words()), 100000)

    def test_taboo_words_are_never_suggested(self):
        never = spelling.never_suggest()
        self.assertTrue(never)
        for word in ("freind", "smal", "wurd", "tox", "becaus", "shat"):
            for _e, _s, cand in spelling.candidates(word):
                self.assertNotIn(cand, never)


class TestSpellingOnInk(unittest.TestCase):
    def test_clear_misspelling_is_found_with_its_place(self):
        out = run(
            [line("My freind is here.")], FakeReader(["My freind is here."])
        )
        self.assertTrue(out["checked"])
        self.assertEqual(len(out["spelling"]), 1)
        f = out["spelling"][0]
        self.assertEqual((f["written"], f["suggestion"]), ("freind", "friend"))
        self.assertEqual(f["kind"], "letter_order")
        place = f["places"][0]
        self.assertEqual(place["placed"], "letters")
        self.assertEqual(place["line"], "line_100")
        x, _y, w, _h = place["bbox"]
        # freind is characters 3 to 9 of 18 along a 396 px line from x=40;
        # its left edge is half way to the y before it.
        self.assertTrue(40 + 396 * 1.5 / 18 <= x <= 40 + 396 * 4 / 18, x)
        self.assertTrue(396 * 4 / 18 <= w <= 396 * 8 / 18, w)

    def test_an_unsure_letter_is_a_misread_not_a_finding(self):
        # "tox": the t column is nearly as much f, so the ink fits fox.
        text = "the tox ran"
        out = run(
            [line(text)],
            FakeReader([text], {text: {4: ("f", 0.45)}}),
        )
        self.assertEqual(out["spelling"], [])

    def test_capitalised_and_listed_words_are_never_read_again(self):
        reader = FakeReader([])
        out = run([line("Ramesh and Lakshmi went home.")], reader)
        self.assertEqual(reader.calls, 0)
        self.assertEqual(out["spelling"], [])
        self.assertEqual(out["rows"]["checked"], 0)

    def test_cast_names_are_not_misspellings(self):
        text = "pihu can fly"
        out = run([line(text)], FakeReader([text]))
        self.assertEqual(out["spelling"], [])

    def test_wrong_past_goes_to_grammar_not_spelling(self):
        text = "Then we goed to school."
        out = run([line(text)], FakeReader([text]))
        self.assertEqual(out["spelling"], [])
        self.assertIn(
            ("past_tense", "goed", "went"),
            [
                (g["rule"], g["written"], g["suggestion"])
                for g in out["grammar"]
            ],
        )

    def test_joined_and_short_words_are_left_alone(self):
        # onthe and drawsbig were read on clean benchmark pages: two words
        # run together, a spacing matter. Short unlisted words were
        # abbreviations and word pieces on real pages.
        reader = FakeReader([])
        out = run([line("we sat onthe mat and drawsbig sth")], reader)
        self.assertEqual(reader.calls, 0)
        self.assertEqual(out["spelling"], [])

    def test_abbreviation_dots_do_not_end_a_sentence(self):
        ends = language_check._ends  # pylint: disable=protected-access
        self.assertEqual(ends("We ate eg. apples, mangoes"), [])
        self.assertEqual(ends("Step 1. Mr. Rao came"), [])
        self.assertEqual(len(ends("We ate. Then we ran! Why?")), 3)

    def test_not_english_is_not_checked(self):
        l = dict(line("abc"), lang="te")
        out = run([l], FakeReader([]))
        self.assertEqual(
            (out["checked"], out["reason"]), (False, "not_english")
        )

    def test_without_letter_scores_nothing_is_claimed(self):
        out = language_check.check(PAGE, [line("my freind")], ["en"], None)
        self.assertFalse(out["checked"])
        self.assertNotIn("spelling", out)


def copied(read, meant, reader=None, **kw):
    """A page where the child copied `meant` and the reader read `read`."""
    return run([line(read, **kw)], reader or FakeReader([read]), meant)


class TestSentence(unittest.TestCase):
    """A copied or dictated sentence: the meant word is known."""

    def test_a_clear_difference_is_the_childs_with_the_sentence_word(self):
        read = "Vahini and Bheema write leters evry day"
        meant = "Vahini and Bheema write letters every day"
        out = copied(read, meant)
        found = [
            (f["written"], f["suggestion"], f["against"])
            for f in out["spelling"]
        ]
        self.assertEqual(
            found,
            [
                ("leters", "letters", "sentence"),
                ("evry", "every", "sentence"),
            ],
        )

    def test_a_listed_word_copied_wrong_is_found_too(self):
        # rite is a word; the sentence says write.
        read = "they rite letters"
        out = copied(read, "they write letters")
        self.assertEqual(
            [(f["written"], f["suggestion"]) for f in out["spelling"]],
            [("rite", "write")],
        )

    def test_a_misread_is_not_the_childs(self):
        # The reader read tetters, but its l column is nearly as much t.
        read = "they write tetters"
        out = copied(
            read,
            "they write letters",
            FakeReader([read], {read: {11: ("l", 0.45)}}),
        )
        self.assertEqual(out["spelling"], [])

    def test_a_line_read_as_its_sentence_is_not_read_again(self):
        reader = FakeReader([])
        text = "they write letters"
        out = copied(text, text, reader)
        self.assertEqual(reader.calls, 0)
        self.assertEqual(out["spelling"], [])

    def test_split_and_unlike_words_make_no_claim(self):
        # wri te is write split in two; and is nothing like the.
        out = copied("they wri te and", "they write the")
        self.assertEqual(out["spelling"], [])

    def test_a_dropped_word_does_not_stop_the_others(self):
        # "big" was not read; leters and rownd still pair with their words.
        read = "vidhya drawz rownd leters on the line"
        out = copied(read, "vidhya draws big round letters on the line")
        self.assertEqual(
            [(f["written"], f["suggestion"]) for f in out["spelling"]],
            [("drawz", "draws"), ("rownd", "round"), ("leters", "letters")],
        )

    def test_no_grammar_on_a_given_sentence(self):
        read = "she sing every day"
        out = copied(read, read, FakeReader([]))
        self.assertEqual(out["grammar"], [])

    def test_a_row_read_in_pieces_still_lines_up(self):
        # The reader read one row as two pieces; neither matches a
        # sentence line on its own, the page as a whole does.
        pieces = [
            line("vahini and", y=100, x=40, ident="a"),
            line("bheema rite leters", y=100, x=300, ident="b"),
        ]
        out = run(
            pieces,
            FakeReader(["bheema rite leters"]),
            "vahini and bheema write letters",
        )
        self.assertEqual(
            [(f["written"], f["suggestion"]) for f in out["spelling"]],
            [("rite", "write"), ("leters", "letters")],
        )
        self.assertEqual(out["spelling"][0]["places"][0]["line"], "b")


class TestRegion(unittest.TestCase):
    def test_at_most_six_rows_are_read_again_clearest_first(self):
        lines = [
            line(f"row freind {i}", y=60 * i + 20, score=0.81 + i * 0.01)
            for i in range(10)
        ]
        reader = FakeReader([l["text"] for l in lines[::-1]])
        out = run(lines, reader)
        self.assertEqual(reader.calls, language_check.ROWS_MAX)
        self.assertEqual(out["rows"]["checked"], 6)
        self.assertEqual(out["rows"]["over_cap"], 4)
        # The six clearest are the last six rows.
        lines_found = {f["places"][0]["line"] for f in out["spelling"]}
        self.assertEqual(lines_found, {l["evidence_id"] for l in lines[4:]})

    def test_unclear_rows_are_not_read_again(self):
        reader = FakeReader([])
        out = run([line("my freind", score=0.6)], reader)
        self.assertEqual(reader.calls, 0)
        self.assertEqual(out["rows"]["unclear"], 1)
        self.assertEqual(out["spelling"], [])

    def test_words_per_row_are_capped(self):
        text = "freind smal evry becaus untill recieve"
        out = run([line(text)], FakeReader([text]))
        self.assertEqual(len(out["spelling"]), language_check.WORDS_PER_ROW)

    def test_same_page_same_answer(self):
        lines = [
            line("My freind sing evry day.", y=40),
            line("she sing", y=120),
        ]
        texts = [l["text"] for l in lines]
        first = run(copy.deepcopy(lines), FakeReader(texts))
        again = run(copy.deepcopy(lines), FakeReader(texts))
        self.assertEqual(first, again)

    def test_the_text_and_lines_are_not_changed(self):
        lines = [line("My freind is here.")]
        before = copy.deepcopy(lines)
        run(lines, FakeReader(["My freind is here."]))
        self.assertEqual(lines, before)


class TestReaderHook(unittest.TestCase):
    """ocr_backends.read_line_scores keeps the decoder's whole matrix and
    puts the decoder back, even when the model fails."""

    def _engine(self, fail=False):
        class Decoder:
            character = ["blank", "a", "b"]

            def __call__(self, pred, return_word_box=False, **_kw):
                return [("ab", [2, [["a", "b"]], [[0, 1]], ["en&num"]])], [0.9]

        class Model:
            def __init__(self):
                self.post_op = Decoder()

            def __call__(self, crops, return_word_box=False):
                if fail:
                    raise RuntimeError("model failed")
                texts, _scores = self.post_op(
                    [np.full((1, 2, 3), 1 / 3)], return_word_box=True
                )
                return [{"rec_text": texts[0]}]

        model = Model()

        class Engine:
            paddlex_pipeline = type("P", (), {"text_rec_model": model})()

        return Engine(), model

    def test_matrix_kept_and_decoder_restored(self):
        from reading import ocr_backends  # pylint: disable=C0415

        engine, model = self._engine()
        original = model.post_op
        real = ocr_backends.get_engine
        ocr_backends.get_engine = lambda _lang: engine
        try:
            rec_text, matrix, chars = ocr_backends.read_line_scores(
                np.zeros((10, 40, 3), np.uint8), "en"
            )
        finally:
            ocr_backends.get_engine = real
        self.assertEqual(rec_text[0], "ab")
        self.assertEqual(matrix.shape, (2, 3))
        self.assertEqual(chars, ["blank", "a", "b"])
        self.assertIs(model.post_op, original)

    def test_a_failing_model_gives_none_and_restores(self):
        from reading import ocr_backends  # pylint: disable=C0415

        engine, model = self._engine(fail=True)
        original = model.post_op
        real = ocr_backends.get_engine
        ocr_backends.get_engine = lambda _lang: engine
        try:
            got = ocr_backends.read_line_scores(
                np.zeros((10, 40, 3), np.uint8), "en"
            )
        finally:
            ocr_backends.get_engine = real
        self.assertIsNone(got)
        self.assertIs(model.post_op, original)


class TestReport(unittest.TestCase):
    """The section in the version-2 responses, and never in the store."""

    def setUp(self):
        text = "My freind is here. She sing. Then i ran"
        self.section = run([line(text)], FakeReader([text]))
        self.payload = dict(realistic_payload(), language=self.section)
        self.free = entitlements.access_for(None)

    def test_the_page_section_has_findings(self):
        self.assertEqual(len(self.section["spelling"]), 1)
        rules = {g["rule"] for g in self.section["grammar"]}
        self.assertEqual(rules, {"verb_s", "capital_i"})

    def test_compact_free_gets_it_with_the_text_only(self):
        body = compact_reports.build_compact(
            self.payload, self.free, ("text",)
        )
        self.assertEqual(body["language"], self.section)
        self.assertEqual(contract_schemas.errors("report-compact", body), [])
        bare = compact_reports.build_compact(self.payload, self.free)
        self.assertNotIn("language", bare)

    def test_expanded_has_it_for_every_tier(self):
        body = public_report(self.payload, self.free)
        self.assertEqual(body["language"], self.section)
        self.assertEqual(contract_schemas.errors("report-expanded", body), [])
        pro = public_report(self.payload, {"tier": "pro"})
        self.assertEqual(pro["language"], self.section)

    def test_not_checked_validates_too(self):
        payload = dict(
            realistic_payload(),
            language={"version": 1, "checked": False, "reason": "error"},
        )
        body = compact_reports.build_compact(payload, self.free, ("text",))
        self.assertEqual(contract_schemas.errors("report-compact", body), [])

    def test_the_kept_record_holds_no_word(self):
        body = compact_reports.build_compact(
            self.payload, {"tier": "pro"}, compact_reports.OPTIONAL_FIELDS
        )
        self.assertIn("freind", json.dumps(body))
        record = json.dumps(report_store.record_from(body, date(2026, 10, 24)))
        for word in ('"freind"', '"friend"', "She sing", '"language"'):
            self.assertNotIn(word, record)


def tok(text, trusted=True, case_sure=True):
    return {
        "text": text,
        "raw": text,
        "trusted": trusted,
        "case_sure": case_sure,
    }


def sentence(words, end=True, **kw):
    out = [tok(w, **kw) for w in words.split()]
    return out + ([{"end": True}] if end else [])


def rules_found(tokens):
    return [
        (f["rule"], f["written"], f["suggestion"])
        for f in grammar.find(tokens)
    ]


class TestGrammar(unittest.TestCase):
    def test_the_mock_up_page(self):
        tokens = (
            sentence("My friend Pihu is a small bird")
            + sentence("She sing every morning")
            + sentence("Yesterday Bheema and me goed to the park with tara")
        )
        found = rules_found(tokens)
        self.assertIn(("verb_s", "She sing", "She sings"), found)
        self.assertIn(("past_tense", "goed", "went"), found)
        self.assertIn(("capital_name", "tara", "Tara"), found)

    def test_me_and_at_the_start(self):
        found = rules_found(sentence("Bheema and me went to school"))
        self.assertIn(("me_and", "Bheema and me", "Bheema and I"), found)
        self.assertEqual(
            rules_found(sentence("He saw Bheema and me today")), []
        )

    def test_a_and_an(self):
        self.assertIn(
            ("a_an", "a apple", "an apple"),
            rules_found(sentence("I ate a apple")),
        )
        self.assertIn(
            ("a_an", "an dog", "a dog"), rules_found(sentence("I saw an dog"))
        )
        for ok in (
            "I saw a university",
            "I waited an hour",
            "It is a one way road",
            "I ate an egg",
        ):
            self.assertEqual(
                [f for f in rules_found(sentence(ok)) if f[0] == "a_an"],
                [],
                ok,
            )

    def test_verb_s_not_after_let_or_a_modal(self):
        for ok in (
            "Let it go",
            "We can make it run",
            "Does she sing",
            "She sings",
            "Raji and she play",
        ):
            self.assertEqual(
                [f for f in rules_found(sentence(ok)) if f[0] == "verb_s"],
                [],
                ok,
            )

    def test_she_read_is_not_flagged(self):
        self.assertEqual(rules_found(sentence("She read a story")), [])

    def test_capitals(self):
        self.assertIn(
            ("capital_i", "i", "I"), rules_found(sentence("Then i ran"))
        )
        # No rule about a capital after a full stop: the reader's dots
        # are not reliable (all nine such marks on GNHK were wrong).
        self.assertEqual(
            rules_found(sentence("We play") + sentence("then we eat")), []
        )

    def test_two_word_rules_stay_on_one_line(self):
        tokens = sentence("She sing every morning")
        tokens[0]["line"], tokens[1]["line"] = "line_1", "line_2"
        self.assertEqual(rules_found(tokens), [])

    def test_case_unclear_letters_are_never_judged(self):
        # s, c and o look the same in both cases.
        self.assertEqual(rules_found(sentence("We met chinnu")), [])
        self.assertEqual(rules_found(sentence("It was sunday")), [])

    def test_unsure_case_is_not_judged(self):
        self.assertEqual(
            rules_found(sentence("I met tara", case_sure=False)), []
        )
        self.assertIn(
            ("capital_name", "tara", "Tara"),
            rules_found(sentence("I met tara")),
        )

    def test_a_sentence_with_an_untrusted_word_is_skipped(self):
        tokens = sentence("She sing every morning")
        tokens[2]["trusted"] = False
        self.assertEqual(rules_found(tokens), [])

    def test_may_and_march_are_words_too(self):
        self.assertEqual(rules_found(sentence("We may march home")), [])

    def test_rule_data_is_consistent(self):
        r = grammar.rules()
        for base, third in r["verb_s"].items():
            self.assertTrue(spelling.is_word(base), base)
            self.assertTrue(spelling.is_word(third), third)
        for right in r["past"].values():
            self.assertTrue(spelling.is_word(right), right)
        self.assertNotIn("read", r["verb_s"])


if __name__ == "__main__":
    unittest.main()
