# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The recognition ladders (backend/languages/ladders.json, #219).

ladders.json is built by scripts/rank_stages.py from stages.json. The
first version must give every line exactly the engines it got before the
ladders: in paddle mode the reader alone, in trocr mode TrOCR for every
line, in hybrid mode TrOCR for Latin and Surya for the five Indic
scripts. Every quality and cost in stages.json is still unmeasured, so
the hybrid ladders are the committed route; the ranking rules of
docs/20-languages.md, section 17.2, are tested here on made-up facts,
which are test data and never go into stages.json.
"""

import contextlib
import copy
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(SERVER_DIR)
sys.path.insert(0, SERVER_DIR)

from reading import recognizer  # noqa: E402
from languages import ladders, stages  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "rank_stages", os.path.join(REPO, "scripts", "rank_stages.py")
)
rank = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rank)

# White-box tests deliberately reach into module-private helpers below.
# pylint: disable=protected-access

LANGS = ("en", "te", "hi", "ta", "kn", "ml")
OLD_INDIC_LANGS = {"te", "hi", "ta", "kn", "ml"}


def _old_route(line_lang, backend_name):
    """recognizer._refine_engine_for_line before #208."""
    if backend_name != "hybrid":
        return backend_name
    return "surya" if (line_lang or "en") in OLD_INDIC_LANGS else "trocr"


def _stage_data():
    with open(stages.TABLE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _ladder_data():
    with open(ladders.LADDERS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _engines(rungs):
    table = stages.table()
    return [table.stage(stage_id)["engine"] for stage_id in rungs]


def _measure(data, stage_id, script, band, p95, **facts):
    """Give one stage measured facts for one script (test data only)."""
    for stage in data["stages"]:
        if stage["id"] == stage_id:
            stage["quality"][script] = band
            stage["cost"]["p95_ms_per_line"] = p95
            stage["fixed"] = facts.get("fixed", True)
            stage["level"][script] = facts.get("level", 2)
            if "where" in facts:
                stage["where"] = facts["where"]
                stage["cost"]["money_per_call"] = facts.get("money", 0)
            return
    raise KeyError(stage_id)


def _load_stages(tmp, data):
    path = os.path.join(tmp, "stages.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return stages.load(path)


def _hybrid(data, script, allow_leaves=False):
    with tempfile.TemporaryDirectory() as tmp:
        table = _load_stages(tmp, data)
        return rank.hybrid_ladder(table, script, "cpu", allow_leaves)


class TestCommittedLadders(unittest.TestCase):
    def test_loads_and_matches_the_stage_table(self):
        table = ladders.load()
        self.assertRegex(table.hash, r"^[0-9a-f]{64}$")
        self.assertEqual(table.hash, ladders.table().hash)
        self.assertEqual(table.stages_sha256, stages.table().hash)
        self.assertEqual(table.device, "cpu")

    def test_up_to_date_with_stages_json(self):
        # What `python scripts/rank_stages.py --check` checks in CI.
        built = rank.build(stages.table(), "cpu")
        self.assertEqual(built, _ladder_data())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rank.main(["--check"]), 0)

    def test_check_fails_on_a_stale_file(self):
        data = _ladder_data()
        data["modes"]["hybrid"]["read"]["Latn"]["rungs"].reverse()
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ladders.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with mock.patch.object(rank.ladders, "LADDERS_PATH", path):
                with contextlib.redirect_stderr(err):
                    self.assertEqual(rank.main(["--check"]), 1)
        self.assertIn("hybrid/read/Latn", err.getvalue())

    def test_every_hybrid_ladder_is_the_route_until_measured(self):
        # Nothing in stages.json is measured yet, so nothing is ranked;
        # each ladder names the stages that kept it from being ranked.
        for script in stages.table().scripts():
            ladder = ladders.table().ladder("hybrid", script)
            with self.subTest(script=script):
                self.assertEqual(ladder["basis"], "route")
                self.assertIn(ladder["rungs"][0], ladder["unmeasured"])


class TestTodaysRouting(unittest.TestCase):
    """Per language and mode, the engines a line meets are the ones
    recognizer gave it before the ladders."""

    def _check(self, lang, mode, want):
        rungs = ladders.table().rungs_for_lang(mode, lang)
        self.assertEqual(_engines(rungs), want)
        # The first rung is the Paddle stage for the line's own script.
        reader = stages.table().stage(rungs[0])
        self.assertIn(stages.table().script_for(lang), reader["scripts"])

    def test_paddle_mode_reads_with_paddle_alone(self):
        for lang in LANGS:
            with self.subTest(lang=lang):
                self._check(lang, "paddle", ["paddle"])

    def test_trocr_mode_rereads_every_line_with_trocr(self):
        for lang in LANGS:
            with self.subTest(lang=lang):
                self._check(lang, "trocr", ["paddle", "trocr"])
                self.assertEqual(
                    recognizer._refine_engine_for_line(lang, "trocr"),
                    "trocr",
                )

    def test_hybrid_mode_routes_by_script_as_before(self):
        for lang in LANGS:
            want = _old_route(lang, "hybrid")
            with self.subTest(lang=lang):
                self._check(lang, "hybrid", ["paddle", want])
                self.assertEqual(
                    recognizer._refine_engine_for_line(lang, "hybrid"), want
                )

    def test_unnamed_codes_read_as_latin(self):
        latin = ladders.table().rungs("hybrid", "Latn")
        for lang in (None, "", "fr", "te-IN", "TE"):
            with self.subTest(lang=lang):
                self.assertEqual(
                    ladders.table().rungs_for_lang("hybrid", lang), latin
                )

    def test_whole_page_modes_have_no_ladder(self):
        for mode in ("surya", "paddleocr-vl", "auto", "cv-fallback", None):
            with self.subTest(mode=mode):
                self.assertIsNone(ladders.table().rungs(mode, "Latn"))


class TestRanking(unittest.TestCase):
    """Section 17.2 on made-up measured facts."""

    def test_a_slower_stage_no_better_is_left_off(self):
        # Surya reads Latin no better than Paddle and costs more, so it can
        # never help: left off, whether it is faster than TrOCR or slower.
        for surya_ms in (300, 900):
            data = _stage_data()
            _measure(data, "paddle-latn-cpu", "Latn", "B", 50)
            _measure(data, "trocr-latn-cpu", "Latn", "A", 400)
            _measure(data, "surya-cpu", "Latn", "B", surya_ms)
            ladder = _hybrid(data, "Latn")
            with self.subTest(surya_ms=surya_ms):
                self.assertEqual(ladder["basis"], "ranked")
                self.assertEqual(
                    ladder["rungs"], ["paddle-latn-cpu", "trocr-latn-cpu"]
                )
                self.assertIn(
                    "no better than", ladder["left_off"]["surya-cpu"]
                )

    def test_the_judgement_in_section_17_gives_its_ladders(self):
        # The bands of the 17.1 table, with times in the order it gives
        # (Paddle cheapest): the ladders of the 17.2 table.
        data = _stage_data()
        _measure(data, "paddle-latn-cpu", "Latn", "B", 100)
        _measure(data, "trocr-latn-cpu", "Latn", "A", 300)
        _measure(data, "surya-cpu", "Latn", "B", 300)
        _measure(data, "paddle-telu-cpu", "Telu", "C", 100)
        _measure(data, "surya-cpu", "Telu", "B", 300)
        self.assertEqual(
            _engines(_hybrid(data, "Latn")["rungs"]), ["paddle", "trocr"]
        )
        self.assertEqual(
            _engines(_hybrid(data, "Telu")["rungs"]), ["paddle", "surya"]
        )

    def test_each_step_up_is_better(self):
        data = _stage_data()
        _measure(data, "paddle-latn-cpu", "Latn", "C", 50)
        _measure(data, "surya-cpu", "Latn", "B", 200)
        _measure(data, "trocr-latn-cpu", "Latn", "A", 400)
        ladder = _hybrid(data, "Latn")
        self.assertEqual(
            _engines(ladder["rungs"]), ["paddle", "surya", "trocr"]
        )
        self.assertNotIn("left_off", ladder)

    def test_ties_break_on_the_stage_id(self):
        data = _stage_data()
        _measure(data, "paddle-latn-cpu", "Latn", "B", 50)
        _measure(data, "trocr-latn-cpu", "Latn", "A", 300)
        _measure(data, "surya-cpu", "Latn", "A", 300)
        ladder = _hybrid(data, "Latn")
        self.assertEqual(ladder["rungs"], ["paddle-latn-cpu", "surya-cpu"])
        self.assertIn("trocr-latn-cpu", ladder["left_off"])

    def test_a_stage_that_is_not_fixed_is_left_off(self):
        data = _stage_data()
        _measure(data, "paddle-telu-cpu", "Telu", "C", 50)
        _measure(data, "surya-cpu", "Telu", "A", 300, fixed=False)
        ladder = _hybrid(data, "Telu")
        self.assertEqual(ladder["rungs"], ["paddle-telu-cpu"])
        self.assertIn("not fixed", ladder["left_off"]["surya-cpu"])

    def test_a_route_through_a_stage_that_is_not_fixed_is_refused(self):
        # Facts still unmeasured keep the route, but a measured hard rule
        # is never followed.
        data = _stage_data()
        for stage in data["stages"]:
            if stage["id"] == "surya-cpu":
                stage["fixed"] = False
        with self.assertRaisesRegex(rank.RankError, "surya-cpu.*not fixed"):
            _hybrid(data, "Telu")

    def test_a_stage_below_reading_maturity_is_left_off(self):
        data = _stage_data()
        _measure(data, "paddle-telu-cpu", "Telu", "C", 50)
        _measure(data, "surya-cpu", "Telu", "B", 300, level=1)
        ladder = _hybrid(data, "Telu")
        self.assertEqual(ladder["rungs"], ["paddle-telu-cpu"])
        self.assertIn("maturity level 1", ladder["left_off"]["surya-cpu"])

    def test_a_stage_that_leaves_the_server_needs_the_policy(self):
        data = _stage_data()
        _measure(data, "paddle-telu-cpu", "Telu", "C", 50)
        _measure(data, "surya-cpu", "Telu", "A", 300, where="leaves", money=2)
        self.assertEqual(_hybrid(data, "Telu")["rungs"], ["paddle-telu-cpu"])
        allowed = _hybrid(data, "Telu", allow_leaves=True)
        self.assertEqual(allowed["rungs"], ["paddle-telu-cpu", "surya-cpu"])

    def test_one_unmeasured_fact_keeps_the_route(self):
        data = _stage_data()
        _measure(data, "paddle-latn-cpu", "Latn", "B", 50)
        _measure(data, "trocr-latn-cpu", "Latn", "A", 400)
        ladder = _hybrid(data, "Latn")
        self.assertEqual(ladder["basis"], "route")
        self.assertEqual(ladder["unmeasured"], ["surya-cpu"])
        self.assertEqual(_engines(ladder["rungs"]), ["paddle", "trocr"])

    def test_cost_order_ignores_file_order(self):
        data = _stage_data()
        _measure(data, "paddle-latn-cpu", "Latn", "C", 50)
        _measure(data, "surya-cpu", "Latn", "B", 200)
        _measure(data, "trocr-latn-cpu", "Latn", "A", 400)
        first = _hybrid(data, "Latn")
        data["stages"].reverse()
        self.assertEqual(_hybrid(data, "Latn"), first)


class TestBrokenLadders(unittest.TestCase):
    """A ladder file that does not fit the stage table stops the server
    at start-up, naming what is wrong."""

    def _refused(self, change, message, stage_data=None):
        data = copy.deepcopy(_ladder_data())
        change(data)
        with tempfile.TemporaryDirectory() as tmp:
            table = stages.table()
            if stage_data is not None:
                table = _load_stages(tmp, stage_data)
            path = os.path.join(tmp, "ladders.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            with self.assertRaises(ladders.LaddersError) as caught:
                ladders.load(path, table)
        self.assertRegex(str(caught.exception), message)

    def test_built_from_another_stage_table(self):
        stage_data = _stage_data()
        stage_data["$comment"] = "changed"
        self._refused(lambda _data: None, "built from another", stage_data)

    def test_a_rung_that_is_not_a_stage(self):
        def change(data):
            ladder = data["modes"]["hybrid"]["read"]["Latn"]
            ladder["rungs"][1] = "tesseract"

        self._refused(change, "'tesseract' is not in stages.json")

    def test_a_first_rung_that_is_not_the_reader(self):
        def change(data):
            data["modes"]["hybrid"]["read"]["Latn"]["rungs"].reverse()

        self._refused(change, "first rung")

    def test_a_route_rung_for_another_script(self):
        def change(data):
            ladder = data["modes"]["hybrid"]["read"]["Telu"]
            ladder["rungs"][1] = "trocr-latn-cpu"

        self._refused(change, "trocr-latn-cpu does not read Telu")

    def test_a_gpu_rung_in_a_cpu_file(self):
        def change(data):
            ladder = data["modes"]["hybrid"]["read"]["Telu"]
            ladder["rungs"][1] = "surya-gpu"

        self._refused(change, "not a read stage on cpu")

    def test_a_script_without_a_ladder(self):
        def change(data):
            del data["modes"]["trocr"]["read"]["Mlym"]

        self._refused(change, "trocr has ladders for")

    def test_an_unknown_basis(self):
        def change(data):
            data["modes"]["paddle"]["read"]["Latn"]["basis"] = "fastest"

        self._refused(change, "basis")


if __name__ == "__main__":
    unittest.main()
