# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Reading accuracy in the benchmark (scripts/benchmark.py, #253): the
character error rate in graphemes against the written sentences, its
baseline in reading.json, and the check that fails when the reader's
text gets worse, as it did when vowel signs were dropped (#209)."""

import importlib.util
import io
import json
import os
import tempfile
import unicodedata
import unittest
from contextlib import redirect_stdout
from unittest import mock

# The benchmark's own helpers are what is tested here.
# pylint: disable=protected-access

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
spec = importlib.util.spec_from_file_location(
    "benchmark", os.path.join(ROOT, "scripts", "benchmark.py")
)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

ENGLISH = {
    "settings": {},
    "sentences": [
        "pihu sings while tara reads a story",
        "the quick brown fox jumps over the lazy dog",
    ]
}
TELUGU = {"sentences": ["పిల్లి పాలు తాగింది", "అమ్మ కథ చెప్పింది"]}


def page(*lines):
    return {"lines": list(lines)}


def without_marks(text):
    """The #209 bug: every vowel sign and virama dropped."""
    return "".join(
        ch for ch in text if not unicodedata.category(ch).startswith("M")
    )


class TestUnits(unittest.TestCase):
    def test_a_vowel_sign_stays_on_its_letter(self):
        self.assertEqual(bench._units("పిల్లి"), ["పి", "ల్లి"])

    def test_case_and_spacing_do_not_count(self):
        self.assertEqual(
            bench._units("  Tara   reads "), bench._units("tara reads")
        )

    def test_edits_count_graphemes(self):
        self.assertEqual(bench._edits(list("story"), list("stoy")), 1)
        self.assertEqual(bench._edits([], list("ab")), 2)
        self.assertEqual(bench._edits(list("ab"), list("ab")), 0)
        dropped = bench._units(without_marks("పిల్లి"))
        self.assertEqual(bench._edits(dropped, bench._units("పిల్లి")), 3)

    def test_script_by_letters(self):
        self.assertEqual(bench._script("tara reads"), "Latin")
        self.assertEqual(bench._script("పిల్లి 2"), "Telugu")
        self.assertEqual(bench._script("12 ."), "Unknown")


class TestReading(unittest.TestCase):
    def test_rate_per_page_and_set(self):
        results = {
            "a": page("pihu sings while tara reads a stoy"),
            "b": page("the quick brown fox jumps over the lazy dog"),
        }
        got = bench.reading(ENGLISH, results)
        self.assertEqual(got["pages"]["a"]["edits"], 1)
        self.assertEqual(got["pages"]["a"]["graphemes"], 35)
        self.assertEqual(got["pages"]["a"]["cer"], round(100 / 35, 2))
        self.assertEqual(got["pages"]["b"]["cer"], 0.0)
        self.assertEqual(got["graphemes"], 35 + 43)
        self.assertEqual(list(got["scripts"]), ["Latin"])

    def test_unmatched_and_repeated_lines_are_left_out(self):
        results = {
            "a": page(
                "pihu sings while tara reads a story",
                "pihu sings while tara reads a stor",
                "xq",
            )
        }
        got = bench.reading(ENGLISH, results)
        self.assertEqual(got["pages"]["a"]["edits"], 0)
        self.assertEqual(got["pages"]["a"]["graphemes"], 35)

    def test_a_page_with_nothing_read_has_no_rate(self):
        got = bench.reading(ENGLISH, {"a": page()})
        self.assertIsNone(got["pages"]["a"]["cer"])
        self.assertIsNone(got["cer"])

    def test_a_page_may_have_its_own_text(self):
        meta = {"sentences": ["x"], "page_text": {"a": ["tara reads"]}}
        got = bench.reading(meta, {"a": page("tara reads")})
        self.assertEqual(got["pages"]["a"]["graphemes"], 10)


class TestReadingGate(unittest.TestCase):
    def test_dropped_vowel_signs_fail_the_check(self):
        good = {"a": page(*TELUGU["sentences"])}
        bad = {"a": page(*(without_marks(s) for s in TELUGU["sentences"]))}
        base = bench.reading(TELUGU, good)
        now = bench.reading(TELUGU, bad)
        self.assertEqual(list(now["scripts"]), ["Telugu"])
        problems = bench.reading_problems(now, base)
        self.assertEqual(len(problems), 2)
        self.assertIn("a: character error rate rose", problems[0])
        self.assertIn("of the set rose", problems[1])

    def test_a_small_rise_inside_the_limits_passes(self):
        base = {"cer": 5.0, "pages": {"a": {"cer": 5.0}}}
        now = {"cer": 5.1, "pages": {"a": {"cer": 5.4}}}
        self.assertEqual(bench.reading_problems(now, base), [])
        now = {"cer": 5.3, "pages": {"a": {"cer": 5.6}}}
        self.assertEqual(len(bench.reading_problems(now, base)), 2)

    def test_a_new_page_has_nothing_to_compare(self):
        now = {"cer": 1.0, "pages": {"new": {"cer": 50.0}}}
        self.assertEqual(bench.reading_problems(now, {}), [])

    def test_the_baseline_only_falls(self):
        base = {
            "cer": 5.0,
            "edits": 5,
            "graphemes": 100,
            "scripts": {"Latin": {"cer": 5.0}},
            "pages": {"a": {"cer": 5.0}, "b": {"cer": 5.0}},
        }
        now = {
            "cer": 6.0,
            "edits": 6,
            "graphemes": 100,
            "scripts": {"Latin": {"cer": 6.0}},
            "pages": {"a": {"cer": 4.0}, "b": {"cer": 6.0}, "c": {"cer": 1}},
        }
        kept = bench.ratchet(now, base)
        self.assertEqual(kept["pages"]["a"]["cer"], 4.0)
        self.assertEqual(kept["pages"]["b"]["cer"], 5.0)
        self.assertEqual(kept["pages"]["c"]["cer"], 1)
        self.assertEqual(kept["cer"], 5.0)
        self.assertEqual(kept["edits"], 5)
        now["cer"] = 4.5
        self.assertEqual(bench.ratchet(now, base)["cer"], 4.5)

    def test_the_table_lists_scripts_and_pages(self):
        now = bench.reading(ENGLISH, {"a": page("tara reads a story")})
        text = bench.reading_table(now, {"pages": {"a": {"cer": 1.0}}})
        self.assertIn("| Latin |", text)
        self.assertIn("| a |", text)
        self.assertIn("| 1.0 |", text)
        self.assertIn("| none |", bench.reading_table(now, {}))


class TestReport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=R1732
        self.addCleanup(self.tmp.cleanup)
        os.makedirs(os.path.join(self.tmp.name, "s"))
        patcher = mock.patch.object(bench, "SETS", [self.tmp.name])
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("GITHUB_STEP_SUMMARY", None)

    def report(self, results, meta=None):
        out = io.StringIO()
        with redirect_stdout(out):
            problems = bench.report_reading(
                "s", meta or ENGLISH, results, "Reading"
            )
        return problems, out.getvalue()

    def test_without_a_baseline_it_says_how_to_make_one(self):
        problems, text = self.report({"a": page("tara reads a story")})
        self.assertEqual(problems, [])
        self.assertIn("No reading.json", text)

    def test_with_a_baseline_a_worse_reading_fails(self):
        good = bench.reading(ENGLISH, {"a": page(ENGLISH["sentences"][0])})
        bench._write_reading("s", good)
        with open(
            os.path.join(self.tmp.name, "s", "reading.json"), encoding="utf-8"
        ) as f:
            self.assertEqual(json.load(f)["cer"], 0.0)
        problems, text = self.report({"a": page("pihu sing whle tara red")})
        self.assertTrue(problems)
        self.assertIn("baseline 0.0%", text)
        self.assertIn("edit reading.json by hand", text)

    def test_pages_measured_from_the_ink_have_no_text_to_rate(self):
        meta = dict(ENGLISH, lang="te")
        meta["settings"] = {"VAHINI_INK_GEOMETRY_LANGS": "te"}
        problems, text = self.report({"a": page("")}, meta)
        self.assertEqual((problems, text), ([], ""))


if __name__ == "__main__":
    unittest.main()
