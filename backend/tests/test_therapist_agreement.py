# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The therapist agreement test's maths and files
(scripts/therapist_agreement.py, docs/23-therapist-agreement.md), on
made-up pages named after the cast."""

import csv
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
ROOT = os.path.dirname(os.path.dirname(HERE))

spec = importlib.util.spec_from_file_location(
    "therapist_agreement",
    os.path.join(ROOT, "scripts", "therapist_agreement.py"),
)
ta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ta)

from report import practice_catalog  # noqa: E402
from scoring_parts.stats import _band  # noqa: E402

CAST = ["vahini", "bheema", "pihu", "tara", "chinnu", "vishnu"]


def write_csv(path, cols, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def mark_row(page, who, value, look="no", **marks):
    row = {"page": page, "therapist": who, "ot_look": look}
    for n in ta.FACTORS:
        row[f"f{n}"] = "" if n in ta.PEN else value
    row.update(marks)  # f5=12 and so on
    return row


class Statistics(unittest.TestCase):
    def test_ranks_share_ties(self):
        self.assertEqual(ta.ranks([3, 1, 3, 2]), [3.5, 1.0, 3.5, 2.0])

    def test_spearman_without_ties_matches_the_textbook_formula(self):
        a = [1, 2, 3, 4, 5]
        b = [2, 1, 4, 3, 5]
        d2 = sum((x - y) ** 2 for x, y in zip(a, b))
        self.assertAlmostEqual(ta.spearman(a, b), 1 - 6 * d2 / (5 * 24))

    def test_spearman_ends(self):
        self.assertAlmostEqual(ta.spearman([1, 2, 3, 4], [5, 6, 7, 9]), 1)
        self.assertAlmostEqual(ta.spearman([1, 2, 3, 4], [9, 7, 6, 5]), -1)
        # Nothing to rank: one side does not vary, or too few pairs.
        self.assertIsNone(ta.spearman([1, 2, 3], [5, 5, 5]))
        self.assertIsNone(ta.spearman([1, 2], [1, 2]))

    def test_spearman_with_ties(self):
        # Pearson on mid-ranks, worked by hand: ranks a = 1.5 1.5 3 4,
        # b = 1 2.5 2.5 4; deviations -1 -1 0.5 1.5 and -1.5 0 0 1.5.
        got = ta.spearman([7, 7, 8, 9], [4, 6, 6, 9])
        self.assertAlmostEqual(got, 3.75 / 4.5)

    def test_fisher_interval_holds_rho_and_narrows_with_pages(self):
        lo, hi = ta.fisher_ci(0.5, 30)
        self.assertLess(lo, 0.5)
        self.assertGreater(hi, 0.5)
        lo2, hi2 = ta.fisher_ci(0.5, 120)
        self.assertLess(hi2 - lo2, hi - lo)
        self.assertIsNone(ta.fisher_ci(None, 30))

    def test_weighted_kappa(self):
        same = [0, 1, 2, 3, 1, 2]
        self.assertAlmostEqual(ta.weighted_kappa(same, same), 1.0)
        # Worked by hand: two raters, two bands used, one miss of one
        # band in four pages. Quadratic weights over four bands: a
        # one-band miss weighs 1/9. Observed 1/9; expected from the
        # margins (2,2) x (1,3): (2*3 + 2*1) / 4 * 1/9 = 2/9.
        a, b = [0, 0, 1, 1], [0, 1, 1, 1]
        self.assertAlmostEqual(ta.weighted_kappa(a, b), 1 - (1 / 9) / (2 / 9))
        # Linear weights treat a one-band miss as a third.
        self.assertAlmostEqual(
            ta.weighted_kappa(a, b, weights="linear"), 1 - (1 / 3) / (2 / 3)
        )
        # Opposite ends every time is worse than chance.
        self.assertLess(ta.weighted_kappa([0, 3, 0, 3], [3, 0, 3, 0]), 0)

    def test_quadratic_kappa_forgives_a_near_miss_more_than_a_far_one(self):
        truth = [0, 1, 2, 3, 0, 1, 2, 3]
        near = [1, 1, 2, 3, 0, 1, 2, 2]
        far = [3, 1, 2, 3, 0, 1, 2, 0]
        self.assertGreater(
            ta.weighted_kappa(truth, near), ta.weighted_kappa(truth, far)
        )

    def test_cohen_kappa(self):
        a = [True, True, False, False]
        self.assertAlmostEqual(ta.cohen_kappa(a, a), 1.0)
        self.assertAlmostEqual(
            ta.cohen_kappa(a, [True, False, True, False]), 0
        )
        self.assertIsNone(ta.cohen_kappa([True, True], [True, True]))

    def test_band_shares(self):
        a, b = [0, 1, 2, 3], [0, 2, 0, 3]
        self.assertEqual(ta.same_band(a, b), 0.5)
        self.assertEqual(ta.within_one(a, b), 0.75)

    def test_wilson_interval(self):
        lo, hi = ta.wilson(8, 10)
        self.assertLess(lo, 0.8)
        self.assertGreater(hi, 0.8)
        self.assertEqual(ta.wilson(0, 10)[0], 0.0)
        self.assertIsNone(ta.wilson(0, 0))

    def test_auc_low_scores_are_the_flag(self):
        self.assertEqual(ta.auc([20, 30], [60, 70]), 1.0)
        self.assertEqual(ta.auc([60, 70], [20, 30]), 0.0)
        self.assertEqual(ta.auc([50], [50]), 0.5)
        self.assertIsNone(ta.auc([], [50]))


class Scale(unittest.TestCase):
    def test_bands_are_the_reports(self):
        names = {"focus": 0, "dev": 1, "good": 2, "strong": 3}
        for tenth in range(0, 101):
            score = tenth / 10
            self.assertEqual(ta.band(score), names[_band(score)], score)

    def test_whole_marks_fall_into_the_stages(self):
        got = ta.stages()
        self.assertEqual(
            got,
            [
                ("focus", "Learning", 0, 4),
                ("dev", "Improving", 5, 6),
                ("good", "Mastering", 7, 8),
                ("strong", "Strong", 9, 10),
            ],
        )
        for _b, _label, low, high in got:
            for mark in range(low, high + 1):
                self.assertEqual(
                    ta.BANDS[ta.band(mark)], _b, (mark, _label, low, high)
                )
        self.assertEqual(
            [s["label"] for s in practice_catalog.STAGES],
            [label for _b, label, _l, _h in got],
        )

    def test_pen_factors_are_the_benchmarks(self):
        spec_b = importlib.util.spec_from_file_location(
            "benchmark_for_ta", os.path.join(ROOT, "scripts", "benchmark.py")
        )
        bench = importlib.util.module_from_spec(spec_b)
        spec_b.loader.exec_module(bench)
        self.assertEqual(set(ta.FACTORS) - set(ta.PEN), set(bench.SCORED))


class Sheet(unittest.TestCase):
    def test_the_committed_sheet_is_current(self):
        self.assertEqual(ta.sheet(check=True), 0)

    def test_every_factor_is_on_the_sheet_by_its_scoring_name(self):
        page = ta.sheet_html()
        for n, (_section, name, measures) in ta.factor_meta().items():
            self.assertIn(f"<b>{name}</b>", page.replace("&amp;", "&"))
            self.assertIn(measures, page)
            self.assertIn(n, ta.LOOK_FOR)
        self.assertIn("take a\ncloser look", page)
        self.assertNotIn("\u2014", page)

    def test_the_sheet_makes_no_claim(self):
        # The one claim word allowed is the line saying neither side is a
        # diagnosis.
        found = practice_catalog.claim_pattern().finditer(ta.sheet_html())
        self.assertEqual([m.group(0) for m in found], ["diagnosis"])
        for text in ta.LOOK_FOR.values():
            self.assertIsNone(practice_catalog.claim_pattern().search(text))

    def test_template_has_the_columns_the_report_reads(self):
        first = ta.template_csv().splitlines()[0].split(",")
        self.assertEqual(first, ta.COLUMNS)


class Joining(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=R1732
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, name):
        return os.path.join(self.dir, name)

    def test_marks_refuse_a_second_sheet_and_out_of_range_marks(self):
        rows = [
            mark_row("vahini-01", "Vidhya", 7),
            mark_row("vahini-01", "Vidhya", 3),
            mark_row("bheema-01", "Arun", 7, f5=12),
            mark_row("", "Arun", 7),
        ]
        write_csv(self.path("m.csv"), ta.COLUMNS, rows)
        marks, problems = ta.read_marks([self.path("m.csv")])
        self.assertEqual(len(problems), 3)
        self.assertEqual(marks["vahini-01"]["Vidhya"]["marks"][1], 7)
        self.assertNotIn(5, marks["bheema-01"]["Arun"]["marks"])
        self.assertNotIn(13, marks["vahini-01"]["Vidhya"]["marks"])

    def test_pages_two_therapists_marked_use_the_mean(self):
        marks = {
            "pihu-01": {
                "Vidhya": {"marks": {1: 6}, "look": True},
                "Arun": {"marks": {1: 8}, "look": True},
            },
            "tara-01": {"Vidhya": {"marks": {1: 3}, "look": None}},
        }
        scores = {
            "pihu-01": {"page": "pihu-01", "f1": "6.5", "error": ""},
            "tara-01": {"page": "tara-01", "f1": "", "error": ""},
        }
        self.assertEqual(ta.factor_pairs(scores, marks, 1), [(6.5, 7.0)])
        self.assertEqual(ta.therapist_pairs(marks, 1), [(8, 6)])

    def test_a_page_that_stopped_is_counted_not_compared(self):
        marks = {"chinnu-01": {"Arun": {"marks": {1: 6}, "look": False}}}
        scores = {"chinnu-01": {"f1": "", "overall": "", "error": "Boom"}}
        self.assertEqual(ta.factor_pairs(scores, marks, 1), [])
        out = ta.report(scores, marks, [])
        self.assertIn("1 stopped with an error", out)

    def test_reference_flag_is_the_majority(self):
        def by(*looks):
            return {str(i): {"look": v} for i, v in enumerate(looks)}

        self.assertTrue(ta.reference_flag(by(True)))
        self.assertFalse(ta.reference_flag(by(False, False, True)))
        self.assertIsNone(ta.reference_flag(by(True, False)))
        self.assertIsNone(ta.reference_flag(by(None)))

    def test_flag_counts(self):
        marks, scores = {}, {}
        for i, (overall, look) in enumerate(
            [(30, True), (40, True), (60, True), (50, False), (80, False)]
        ):
            page = f"{CAST[i]}-01"
            marks[page] = {"Vidhya": {"marks": {}, "look": look}}
            scores[page] = {"overall": str(overall), "error": ""}
        got = ta.flag_table(scores, marks, [45])
        row = got["rows"][0]
        self.assertEqual((row["tp"], row["fn"]), (2, 1))
        self.assertEqual((row["tn"], row["fp"]), (2, 0))
        self.assertAlmostEqual(row["sens"], 2 / 3)
        self.assertEqual(row["spec"], 1.0)
        # Flagged 30, 40, 60 against not flagged 50, 80: 5 of 6 pairs
        # have the flagged page lower.
        self.assertAlmostEqual(got["auc"], 5 / 6)


class Report(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=R1732
        ta.sample(self.tmp.name)
        self.scores = ta.read_scores(os.path.join(self.tmp.name, "scores.csv"))
        self.marks, problems = ta.read_marks(
            [os.path.join(self.tmp.name, "marks.csv")]
        )
        self.assertEqual(problems, [])
        self.out = ta.report(self.scores, self.marks, [], 45, ta.factor_meta())

    def tearDown(self):
        self.tmp.cleanup()

    def test_sample_pages_are_the_casts(self):
        for page in self.scores:
            self.assertIn(page.split("-")[0], ta.CAST)
        therapists = {t for by in self.marks.values() for t in by}
        self.assertEqual(therapists, set(ta.THERAPISTS))

    def test_the_report_names_no_page(self):
        for page in self.scores:
            self.assertNotIn(page, self.out)
        for name in ta.CAST:
            self.assertNotIn(name, self.out.lower())

    def test_the_report_has_every_part(self):
        for part in (
            "## The analyser against the therapists",
            "## Therapist against therapist",
            "## The overall score as a flag",
            "| 1 Letter Formation Accuracy | 59 |",
            "| 45 (chosen) |",
            "Factors 13 to 16 need the pen",
        ):
            self.assertIn(part, self.out)
        self.assertNotIn("\u2014", self.out)

    def test_made_up_agreement_is_found(self):
        # The sample's analyser sees each page's level with little noise
        # on Letter Formation and much on Loop Closure; the report has to
        # tell them apart.
        f1 = ta.agreement_row(ta.factor_pairs(self.scores, self.marks, 1))
        f3 = ta.agreement_row(ta.factor_pairs(self.scores, self.marks, 3))
        self.assertGreater(f1["rho"], 0.8)
        self.assertGreater(f1["rho"], f3["rho"])
        self.assertGreater(f1["kappa"], f3["kappa"])

    def test_too_few_pages_gives_no_number(self):
        few = dict(list(self.marks.items())[:6])
        out = ta.report(self.scores, few, [])
        self.assertIn("fewer than 10 pages", out)
        self.assertIn("no sensitivity or specificity is given", out)
        self.assertNotIn("Area under the curve", out)

    def test_skipped_rows_are_counted_without_naming_pages(self):
        out = ta.report(
            self.scores, self.marks, ["m.csv:3: page vahini-01 marked twice"]
        )
        self.assertIn("1 rows in the marks were skipped", out)
        self.assertNotIn("vahini-01", out)


class Scoring(unittest.TestCase):
    def test_score_folder_keeps_scores_only_and_counts_errors(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("vahini-01.jpg", "bheema-01.png", "notes.txt"):
                with open(os.path.join(d, name), "wb") as f:
                    f.write(b"x")

            def scorer(_path, page):
                if page == "bheema-01":
                    raise ValueError("read: the words on the page")
                return {
                    "overall": 61,
                    "scores": {str(n): 6.0 for n in range(1, 13)},
                    "lines": ["the words on the page"],
                }

            rows = ta.score_folder(d, scorer)
            out = os.path.join(d, "scores.csv")
            ta.write_scores(rows, out)
            with open(out, encoding="utf-8") as f:
                text = f.read()
        self.assertEqual([r["page"] for r in rows], ["bheema-01", "vahini-01"])
        self.assertEqual(rows[0]["error"], "ValueError")
        self.assertEqual(rows[1]["f13"], "")
        self.assertEqual(rows[1]["overall"], 61)
        self.assertNotIn("words on the page", text)

    def test_stdout_holds_only_the_rows(self):
        # What the reader prints while scoring, from Python or from C,
        # goes to stderr, so `score --out -` gives a clean CSV.
        code = (
            "import importlib.util, os, sys\n"
            f"spec = importlib.util.spec_from_file_location('t', {spec.origin!r})\n"
            "ta = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(ta)\n"
            "with ta.console_to_stderr():\n"
            "    print('reader says hello')\n"
            "    os.write(1, b'paddle says hello\\n')\n"
            "ta.write_scores([{'page': 'pihu-01', 'overall': 70}], '-')\n"
        )
        got = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(
            got.stdout.splitlines()[1].split(",")[:2], ["pihu-01", "70"]
        )
        self.assertEqual(len(got.stdout.splitlines()), 2)
        self.assertIn("reader says hello", got.stderr)
        self.assertIn("paddle says hello", got.stderr)


if __name__ == "__main__":
    unittest.main()
