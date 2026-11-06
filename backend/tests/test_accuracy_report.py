# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Offline accuracy evidence: raw values, skips, provenance and HTML safety."""

import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / f"{name}.py"
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


report = module("accuracy_report")
bench = module("benchmark")


def sample_page(score=8, text="a simple sentence", found=1):
    return {
        "overall": 80,
        "scores": {str(n): score for n in bench.SCORED},
        "lines": [text],
        "sentences_found": found,
        "repeats": 0,
        "unmatched": 0,
    }


class TestObservedArtifacts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "s"
        (self.folder / "pages").mkdir(parents=True)
        (self.folder / "pages" / "a.jpg").touch()
        (self.folder / "pages" / "b.jpg").touch()
        self.meta = {
            "settings": {},
            "lines_per_page": 1,
            "floor_sentences_found": 2,
            "sentences": ["a simple sentence"],
        }
        self.base = {"pages": {"a": sample_page(), "b": sample_page()}}
        self.write("set.json", self.meta)
        self.write("expected.json", self.base)
        self.write(
            "reading.json", bench.reading(self.meta, self.base["pages"])
        )
        patcher = mock.patch.object(bench, "SETS", [self.tmp.name])
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, name, value):
        (self.folder / name).write_text(json.dumps(value), encoding="utf-8")

    def test_worse_raw_cer_is_kept_beside_unchanged_ratchet(self):
        pages = {"a": sample_page(text="a simple sentenc"), "b": sample_page()}
        with mock.patch.object(
            bench, "run_set", return_value=(self.meta, pages, [])
        ), mock.patch.dict(
            "os.environ", {"GITHUB_STEP_SUMMARY": ""}
        ), redirect_stdout(
            io.StringIO()
        ):
            code = bench.cmd_check(
                SimpleNamespace(set="s", results=self.tmp.name)
            )
        current = report.load(self.folder / "current.json")
        self.assertEqual(code, 1)
        self.assertGreater(current["observed"]["reading"]["cer"], 0)
        self.assertEqual(current["baseline"]["reading"]["cer"], 0)
        self.assertEqual(report.load(self.folder / "reading.json")["cer"], 0)
        self.assertTrue(current["valid"])
        self.assertEqual(current["status"], "regression")

    def test_missing_page_is_skipped_and_stays_in_denominator(self):
        current = bench.observation(
            "s",
            self.meta,
            {"a": sample_page()},
            self.base,
            ["b: missing reader crop"],
            "changed",
            [],
        )
        self.assertFalse(current["valid"])
        self.assertEqual(current["page_states"]["b"]["state"], "skipped")
        self.assertEqual(
            sum(p["written_lines"] for p in current["page_states"].values()), 2
        )
        markup = report.replay_section(current)
        self.assertIn("1 / 2", markup)
        self.assertIn("missing reader crop", markup)
        self.assertIn("Not measured", markup)

    def test_no_pages_is_invalid_not_a_zero_accuracy_pass(self):
        current = bench.observation("s", self.meta, {}, self.base, [], "", [])
        self.assertFalse(current["valid"])
        self.assertEqual(current["status"], "invalid")
        self.assertIsNone(current["observed"]["reading"]["cer"])

    def test_missing_eye_ranked_page_is_unavailable_not_re_ranked(self):
        meta = {**self.meta, "eye_ranking": ["a", "b", "c"]}
        current = bench.observation(
            "s", meta, {"a": sample_page()}, self.base, [], "changed", []
        )
        self.assertIsNone(current["observed"]["scores"]["eye_agreement"])
        self.assertFalse(current["valid"])

    def test_page_with_repeat_or_nondeterminism_is_invalid(self):
        current = bench.observation(
            "s",
            self.meta,
            self.base["pages"],
            self.base,
            ["a: two replays gave different results"],
            "",
            [],
        )
        self.assertEqual(current["page_states"]["a"]["state"], "invalid")
        self.assertEqual(current["page_states"]["b"]["state"], "valid")

    def test_ink_only_sets_do_not_gain_fake_reading_accuracy(self):
        meta = {
            **self.meta,
            "lang": "te",
            "settings": {"VAHINI_INK_GEOMETRY_LANGS": "te"},
        }
        current = bench.observation(
            "s", meta, self.base["pages"], self.base, [], "", []
        )
        self.assertIsNone(current["observed"]["reading"])
        self.assertIn("ink-only", current["reading_note"])

    def test_report_contains_no_recognised_words(self):
        pages = {
            "a": sample_page(text="private-recognised-words"),
            "b": sample_page(),
        }
        current = bench.observation(
            "s", self.meta, pages, self.base, [], "", []
        )
        self.assertNotIn("private-recognised-words", report.render([current]))


class TestFactorArtifacts(unittest.TestCase):
    def test_factor_json_reuses_exactly_one_run(self):
        fake = SimpleNamespace(
            TARGETS={"wide_gap": ("8",)},
            run=mock.Mock(
                return_value=[{"kind": "wide_gap", "writer": "synthetic"}]
            ),
            summarise=mock.Mock(
                return_value={
                    "wide_gap": {
                        "writers": 1,
                        "targets": {"8": {"measured": 1, "caught": 0.5}},
                    }
                }
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "factors"
            folder.mkdir()
            (folder / "expected.json").write_text('{"wide_gap": {"8": 1}}')
            out = Path(tmp) / "measured.json"
            spec = SimpleNamespace(
                loader=SimpleNamespace(exec_module=lambda _module: None)
            )
            with mock.patch.object(bench, "SETS", [tmp]), mock.patch.object(
                bench.importlib.util,
                "spec_from_file_location",
                return_value=spec,
            ), mock.patch.object(
                bench.importlib.util, "module_from_spec", return_value=fake
            ), mock.patch.dict(
                "os.environ", {"GITHUB_STEP_SUMMARY": ""}
            ), redirect_stdout(
                io.StringIO()
            ):
                result = bench.cmd_factors(
                    SimpleNamespace(
                        uji="unused", ruled=False, update=False, json=str(out)
                    )
                )
            self.assertEqual(result, 1)
            fake.run.assert_called_once()
            measured = report.load(out)
            self.assertEqual(
                measured["summary"]["wide_gap"]["targets"]["8"]["caught"], 0.5
            )
            self.assertEqual(measured["baseline"]["wide_gap"]["8"], 1)
            self.assertEqual(measured["rows"], fake.run.return_value)

    def test_partly_measured_pairs_remain_visible(self):
        markup = report.factor_section(
            {
                "rows": [{"kind": "gap"}, {"kind": "gap"}],
                "summary": {
                    "gap": {
                        "writers": 1,
                        "targets": {"8": {"measured": 1, "caught": 1}},
                    }
                },
            }
        )
        self.assertIn("partial", markup)
        self.assertIn("Attempted pairs", markup)
        self.assertIn("Skipped pairs", markup)

    def test_no_pairs_means_skipped_not_zero(self):
        markup = report.factor_section(
            {
                "summary": {
                    "wide_gap": {
                        "writers": 0,
                        "targets": {"8": {"measured": 0}},
                    }
                },
                "baseline": {"wide_gap": {"8": 1}},
            }
        )
        self.assertIn("skipped", markup)
        self.assertIn("Not measured", markup)
        self.assertIn("Not comparable", markup)


class TestReport(unittest.TestCase):
    def test_html_escapes_all_external_values(self):
        attack = '<img src=x onerror="alert(1)">'
        markup = report.render(notes=[attack], factors=[{"set": attack}])
        self.assertNotIn(attack, markup)
        self.assertIn("&lt;img", markup)
        self.assertNotIn("<script", markup)
        self.assertIn("Content-Security-Policy", markup)

    def test_missing_metrics_are_not_rendered_as_zero(self):
        self.assertEqual(report.fmt(None), "Not measured")
        self.assertEqual(report.fmt(float("nan")), "Not measured")
        self.assertEqual(report.fmt(True), "Not measured")
        self.assertEqual(report.delta(None, 2), "Not comparable")
        self.assertEqual(report.delta(2, 0), "+2.00")

    def test_charts_leave_gaps_and_have_accessible_labels(self):
        markup = report.spark([1, None, 2], "CER %")
        self.assertEqual(markup.count("<polyline"), 2)
        self.assertIn('role="img"', markup)
        self.assertIn("min 1, max 2", markup)

    def test_legacy_catch_is_labelled_not_charted(self):
        markup = report.history_section(
            [{"set": "s", "catch": {"wide_gap/8": 0.1234}}]
        )
        self.assertIn("legacy accepted floors; not measured", markup)
        self.assertIn("0.1234", markup)
        self.assertIn("No measured catch history", markup)
        self.assertNotIn("<circle", markup)
        self.assertIn("legacy / unverified", markup)

    def test_invalid_history_is_visible_but_does_not_draw_point(self):
        markup = report.history_section(
            [{"set": "s", "valid": False, "cer": 99.9}]
        )
        self.assertNotIn("<circle", markup)
        self.assertIn("99.9", markup)
        self.assertIn("invalid", markup)

    def test_cli_does_not_treat_old_artifacts_as_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "set").mkdir()
            (root / "set" / "expected.json").write_text('{"pages": {}}')
            (root / "set" / "reading.json").write_text('{"cer": 0}')
            out = root / "report.html"
            with redirect_stdout(io.StringIO()):
                code = report.main(
                    [
                        "--results",
                        tmp,
                        "--out",
                        str(out),
                        "--factor-results",
                        str(root / "missing.json"),
                    ]
                )
            self.assertEqual(code, 0)
            markup = out.read_text()
            self.assertIn("baseline candidates, not raw measurements", markup)
            self.assertIn("Factor output missing", markup)
            self.assertIn("Replay observations: unavailable", markup)

    def test_mixed_successful_and_missing_sets_are_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "successful").mkdir()
            (root / "successful" / "current.json").write_text(
                '{"set": "successful"}'
            )
            (root / "partial").mkdir()
            (root / "partial" / "reading.json").write_text('{"cer": 0}')
            out = root / "report.html"
            with redirect_stdout(io.StringIO()):
                report.main(
                    [
                        "--results",
                        tmp,
                        "--expected-set",
                        "crashed",
                        "--out",
                        str(out),
                    ]
                )
            markup = out.read_text()
            self.assertIn("Replay partial: unavailable", markup)
            self.assertIn("Replay crashed: unavailable", markup)
            self.assertIn("<h2>successful</h2>", markup)

    def test_factor_chart_excludes_invalid_or_unmeasured_pairs(self):
        pages = {"a": sample_page(6), "b": sample_page(1)}
        baseline = {"a": sample_page(8), "b": sample_page(9)}
        markup = report.factor_chart(
            pages,
            baseline,
            {"a": {"state": "valid"}, "b": {"state": "invalid"}},
        )
        self.assertIn("accepted 8.00, observed 6.00, 1 paired pages", markup)
        self.assertNotIn("2 paired pages", markup)

    def test_render_does_not_mutate_inputs(self):
        factors = {"summary": {}, "baseline": {}}
        before = copy.deepcopy(factors)
        report.render(factors=[factors])
        self.assertEqual(factors, before)


if __name__ == "__main__":
    unittest.main()
