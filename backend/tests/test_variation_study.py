# SPDX-License-Identifier: AGPL-3.0-only
"""The normal-variation tool (scripts/variation_study.py): its maths, its
refusal to propose a band from too little data, and its comparability
check. Synthetic scores and drawn letters only."""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


study = _load("variation_study")
planted = _load("planted_pages")


def compact(scores, words=20, script="latin", page="handwriting"):
    return {
        "factors": [{"n": n, "s": s, "st": "e"} for n, s in scores.items()],
        "comparability": {"words": words, "script": script, "page": page},
    }


class SummaryTests(unittest.TestCase):
    def test_percentiles_of_the_absolute_difference(self):
        pairs = [
            (f"w{i:02d}", {5: 6.0}, {5: 6.0 + (-1) ** i * i / 10})
            for i in range(10)
        ]
        row = study.summarise(pairs)["factors"]["5"]
        deltas = np.array([i / 10 for i in range(10)])
        self.assertEqual(row["pairs"], 10)
        self.assertEqual(row["writers"], 10)
        self.assertEqual(row["median"], round(float(np.median(deltas)), 2))
        self.assertEqual(
            row["p90"], round(float(np.percentile(deltas, 90)), 2)
        )
        self.assertEqual(row["max"], 0.9)

    def test_no_band_from_too_little_data(self):
        few = [("w01", {7: 5.0}, {7: 6.0})] * 40
        row = study.summarise(few)["factors"]["7"]
        self.assertIsNone(row["band"])
        self.assertIn("1 writers", row["reason"])
        many = [(f"w{i:02d}", {7: 5.0}, {7: 5.5}) for i in range(30)]
        self.assertEqual(study.summarise(many)["factors"]["7"]["band"], 0.5)

    def test_unscored_factors_are_left_out_not_counted_as_zero(self):
        pairs = [("w01", {13: None, 5: 6.0}, {13: None, 5: 6.5})]
        factors = study.summarise(pairs)["factors"]
        self.assertNotIn("13", factors)
        self.assertEqual(factors["5"]["pairs"], 1)

    def test_synthetic_mode_never_proposes_a_band(self):
        rows = study.summarise([("w01", {5: 6.0}, {5: 6.4})] * 50, band=False)
        self.assertNotIn("band", rows["factors"]["5"])


class ReportPairTests(unittest.TestCase):
    def test_reads_both_formats(self):
        expanded = {
            "factors": [{"number": 5, "score": {"value": 7.1}}],
        }
        self.assertEqual(study.factor_scores(expanded), {5: 7.1})
        self.assertEqual(study.factor_scores(compact({5: 6.2})), {5: 6.2})

    def test_pages_that_are_not_alike_are_skipped(self):
        same = compact({5: 6.0})
        self.assertIsNone(study.not_comparable(same, compact({5: 7.0})))
        self.assertEqual(
            study.not_comparable(same, compact({5: 7.0}, script="telugu")),
            "script",
        )
        self.assertEqual(
            study.not_comparable(same, compact({5: 7.0}, words=40)),
            "length",
        )
        self.assertEqual(
            study.not_comparable(
                same, compact({5: 7.0}, page="handwriting_with_print")
            ),
            "print",
        )

    def test_manifest_of_saved_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            files = {
                "a.json": compact({5: 6.0, 7: 8.0}),
                "b.json": compact({5: 6.6, 7: 7.5}),
                "c.json": compact({5: 9.0}, words=60),
            }
            for name, body in files.items():
                (base / name).write_text(json.dumps(body))
            (base / "pairs.json").write_text(
                json.dumps(
                    [
                        {
                            "writer": "w01",
                            "first": "a.json",
                            "second": "b.json",
                        },
                        {
                            "writer": "w02",
                            "first": "a.json",
                            "second": "c.json",
                        },
                    ]
                )
            )
            out = study.from_reports(str(base / "pairs.json"))
        self.assertEqual(out["skipped"], {"length": 1})
        self.assertEqual(out["factors"]["5"]["max"], 0.6)
        self.assertEqual(out["factors"]["7"]["max"], 0.5)


def zigzag(ch, lean):
    h = 2.0 if ch in planted.TALL or ch in planted.LOW else 1.0
    xs = np.linspace(0, 0.5 + lean, 6)
    return [
        np.array(list(zip(xs, [0.0 if i % 2 == 0 else h for i in range(6)])))
    ]


class SyntheticPairTests(unittest.TestCase):
    def test_same_pages_give_the_same_pairs(self):
        letters = {
            ch: [zigzag(ch, 0.0), zigzag(ch, 0.1)]
            for ch in set("".join(planted.SENTENCES).replace(" ", ""))
        }
        writers = {"w01": letters}
        first = study.synthetic_pairs(writers, 1, planted)
        again = study.synthetic_pairs(writers, 1, planted)
        self.assertEqual(first, again)
        self.assertEqual(len(first), 1)
        self.assertEqual(
            planted.SENTENCES[4], "seetha and rama practise slowly with care"
        )


if __name__ == "__main__":
    unittest.main()
