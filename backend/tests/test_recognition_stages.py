# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The recognition stage table (backend/languages/stages.json, #208).

The table replaced ``_INDIC_LANGS`` in recognizer.py and the TrOCR and
Paddle model ids written out in ocr_backends.py, config.py and
warmup_models.py, so the first version must route and load exactly as
before: hybrid mode sends each of en, te, hi, ta, kn and ml to the same
engine as the old set did, the default model ids are the old strings,
and the environment variables still override them. The rest covers the
schema and the cross-checks, the language packs agreeing with the table,
that speed never changes a route (#112), and the devices /health reports.
"""

import copy
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(SERVER_DIR)
sys.path.insert(0, SERVER_DIR)

import config  # noqa: E402
from reading import ocr_backends  # noqa: E402
from reading import recognizer  # noqa: E402
import warmup_models  # noqa: E402
from languages import registry, stages  # noqa: E402

# White-box tests deliberately reach into module-private helpers below.
# pylint: disable=protected-access

# What the code said before the table, as it was on main before #208.
OLD_INDIC_LANGS = {"te", "hi", "ta", "kn", "ml"}
OLD_REC_MODEL_MAP = "en:PP-OCRv5_server_rec,te:te_PP-OCRv5_mobile_rec"
OLD_TROCR_MODEL = "microsoft/trocr-base-handwritten"


def _old_route(line_lang, backend_name):
    """recognizer._refine_engine_for_line before #208."""
    if backend_name != "hybrid":
        return backend_name
    return "surya" if (line_lang or "en") in OLD_INDIC_LANGS else "trocr"


def _read_table():
    with open(stages.TABLE_PATH, encoding="utf-8") as f:
        return json.load(f)


class TestHybridRoutesAsBefore(unittest.TestCase):
    """One test per language hybrid mode handled before the table."""

    def _check(self, lang, engine):
        got = recognizer._refine_engine_for_line(lang, "hybrid")
        self.assertEqual(got, engine)
        self.assertEqual(got, _old_route(lang, "hybrid"))

    def test_english_goes_to_trocr(self):
        self._check("en", "trocr")

    def test_telugu_goes_to_surya(self):
        self._check("te", "surya")

    def test_hindi_goes_to_surya(self):
        self._check("hi", "surya")

    def test_tamil_goes_to_surya(self):
        self._check("ta", "surya")

    def test_kannada_goes_to_surya(self):
        self._check("kn", "surya")

    def test_malayalam_goes_to_surya(self):
        self._check("ml", "surya")

    def test_unnamed_codes_read_as_latin_like_before(self):
        # The old lookup was an exact set match: anything else, including
        # a locale or a capitalised code, went to TrOCR.
        for lang in (None, "", "fr", "de", "te-IN", "TE", "auto", "latin"):
            with self.subTest(lang=lang):
                self._check(lang, "trocr")

    def test_other_modes_use_their_one_engine(self):
        for mode in ("trocr", "surya", "paddle", "paddleocr-vl"):
            for lang in ("en", "te", "hi", None):
                with self.subTest(mode=mode, lang=lang):
                    got = recognizer._refine_engine_for_line(lang, mode)
                    self.assertEqual(got, mode)
                    self.assertEqual(got, _old_route(lang, mode))

    def test_speed_never_changes_the_route(self):
        # engine_speed_verdict is information for /health only (#112): an
        # engine measured slow is still the one a line is routed to.
        saved = dict(ocr_backends._SPEED_MEMO)
        try:
            ocr_backends._SPEED_MEMO.clear()
            before = {
                lang: recognizer._refine_engine_for_line(lang, "hybrid")
                for lang in ("en", "te", "hi", "ta", "kn", "ml")
            }
            ocr_backends.record_engine_speed("trocr", 1e9)
            ocr_backends.record_engine_speed("surya", 1e9)
            self.assertFalse(ocr_backends.engine_speed_verdict("trocr")[1])
            after = {
                lang: recognizer._refine_engine_for_line(lang, "hybrid")
                for lang in before
            }
            self.assertEqual(before, after)
        finally:
            ocr_backends._SPEED_MEMO.clear()
            ocr_backends._SPEED_MEMO.update(saved)

    def test_recognizer_holds_no_language_list(self):
        self.assertFalse(hasattr(recognizer, "_INDIC_LANGS"))


class TestModelsAsBefore(unittest.TestCase):
    def test_default_paddle_models_are_the_old_string(self):
        self.assertEqual(
            stages.table().default_rec_model_map(), OLD_REC_MODEL_MAP
        )

    def test_config_default_and_override(self):
        env = {"VAHINI_OCR_GPU": "0"}
        with mock.patch.dict(os.environ, env):
            os.environ.pop("VAHINI_OCR_REC_MODEL_MAP", None)
            settings = config.load()
        self.assertEqual(settings.rec_model_map_raw, OLD_REC_MODEL_MAP)
        self.assertEqual(
            settings.rec_model_map,
            {"en": "PP-OCRv5_server_rec", "te": "te_PP-OCRv5_mobile_rec"},
        )
        env["VAHINI_OCR_REC_MODEL_MAP"] = "en:MyRec,*:OtherRec"
        with mock.patch.dict(os.environ, env):
            settings = config.load()
        self.assertEqual(
            settings.rec_model_map, {"en": "MyRec", "*": "OtherRec"}
        )

    def test_trocr_default_and_override(self):
        with mock.patch.dict(os.environ, {"VAHINI_TROCR_GPU": "0"}):
            os.environ.pop("VAHINI_TROCR_MODEL", None)
            self.assertEqual(
                ocr_backends.TrOCRBackend().model_name, OLD_TROCR_MODEL
            )
            os.environ["VAHINI_TROCR_MODEL"] = "someone/other-trocr"
            self.assertEqual(
                ocr_backends.TrOCRBackend().model_name, "someone/other-trocr"
            )

    def test_table_model_lookups(self):
        table = stages.table()
        self.assertEqual(table.model("trocr"), OLD_TROCR_MODEL)
        self.assertEqual(table.model("paddle", "Latn"), "PP-OCRv5_server_rec")
        self.assertEqual(
            table.model("paddle", "Telu"), "te_PP-OCRv5_mobile_rec"
        )
        # PaddleOCR picks its own model for Hindi; the table records none.
        self.assertIsNone(table.model("paddle", "Deva"))
        # Surya's checkpoint is not recorded yet.
        self.assertIsNone(table.model("surya"))
        with self.assertRaises(stages.StagesError):
            table.model("paddle")

    def test_warmup_reads_the_same_table(self):
        # warmup_models.py warms what the server will load.
        self.assertIs(warmup_models.stages, stages)

    def test_dockerfile_downloads_the_table_trocr_model(self):
        # The image build pre-downloads TrOCR before backend/ is copied in,
        # so it names the model itself; it must name the table's.
        path = os.path.join(REPO, "deployment", "Dockerfile")
        with open(path, encoding="utf-8") as f:
            named = set(re.findall(r"m='([^']+)'", f.read()))
        self.assertEqual(named, {stages.table().model("trocr")})


class TestTable(unittest.TestCase):
    def test_table_loads_and_hashes(self):
        table = stages.load()
        self.assertRegex(table.hash, r"^[0-9a-f]{64}$")
        self.assertEqual(table.hash, stages.table().hash)
        self.assertEqual(table.default_script, "Latn")

    def test_nothing_measured_is_invented(self):
        # Every quality, cost, memory and maturity figure waits for
        # rank_stages.py and load_test.py on stage (#219). When they
        # record real numbers, this test changes with them.
        for stage in stages.table().stages():
            with self.subTest(stage=stage["id"]):
                for field in ("load_mb", "work_mb", "threads", "fixed"):
                    self.assertEqual(stage[field], stages.UNMEASURED)
                self.assertEqual(
                    stage["cost"]["p95_ms_per_line"], stages.UNMEASURED
                )
                values = list(stage["quality"].values())
                values += list(stage["level"].values())
                for value in values:
                    self.assertEqual(value, stages.UNMEASURED)
                self.assertEqual(
                    stage["version"]["weights_sha256"], stages.UNMEASURED
                )
                if stage["device"] == "gpu":
                    self.assertEqual(stage["vram_mb"], stages.UNMEASURED)

    def test_every_engine_has_a_cpu_and_a_gpu_stage(self):
        table = stages.table()
        for script in table.scripts():
            for engine in ("paddle", "trocr", "surya"):
                ids = {
                    table.stage_id(engine, script, device)
                    for device in ("cpu", "gpu")
                }
                with self.subTest(script=script, engine=engine):
                    self.assertEqual(None in ids, len(ids) == 1)

    def test_schema_engines_are_the_registered_backends(self):
        with open(stages.SCHEMA_PATH, encoding="utf-8") as f:
            schema = json.load(f)
        ocr_backends.init_registry()
        self.assertEqual(
            set(schema["definitions"]["engine"]["enum"]),
            set(ocr_backends._REGISTRY),
        )

    def test_language_packs_agree_with_the_table(self):
        table = stages.table()
        for pack_id in registry.all_ids():
            pack = registry.resolve(pack_id)
            if pack.kind != "language":
                continue
            with self.subTest(pack=pack_id):
                self.assertIn(pack_id, table.languages(pack.get("script")))
                self.assertEqual(table.script_for(pack_id), pack.get("script"))


class TestBrokenTables(unittest.TestCase):
    """A table that does not hold together stops the server at start-up,
    naming what is wrong, rather than routing a line somewhere odd."""

    def _refused(self, change, message):
        data = copy.deepcopy(_read_table())
        change(data)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "stages.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            with self.assertRaises(stages.StagesError) as caught:
                stages.load(path)
        self.assertRegex(str(caught.exception), message)

    def test_a_guessed_figure_is_refused(self):
        def change(data):
            data["stages"][0]["load_mb"] = "about 300"

        self._refused(change, "load_mb")

    def test_a_language_under_two_scripts(self):
        def change(data):
            data["scripts"]["Deva"]["languages"].append("te")

        self._refused(change, "'te' is under both")

    def test_a_route_without_a_stage(self):
        def change(data):
            data["scripts"]["Deva"]["refine"] = ["trocr"]

        self._refused(change, "Deva is re-read by trocr")

    def test_cpu_and_gpu_naming_different_models(self):
        def change(data):
            for stage in data["stages"]:
                if stage["id"] == "trocr-latn-gpu":
                    stage["version"]["model"] = "microsoft/trocr-large"

        self._refused(change, "trocr-latn-gpu")

    def test_a_default_script_that_is_not_listed(self):
        def change(data):
            data["default_script"] = "Grek"

        self._refused(change, "default_script")

    def test_quality_for_a_script_the_stage_does_not_read(self):
        def change(data):
            data["stages"][0]["quality"]["Telu"] = "unmeasured"

        self._refused(change, "quality")

    def test_a_cpu_stage_with_video_memory(self):
        def change(data):
            data["stages"][0]["vram_mb"] = 100

        self._refused(change, "vram_mb|0 was expected")

    def test_two_refine_engines_wait_for_the_ladders(self):
        def change(data):
            data["scripts"]["Telu"]["refine"] = ["surya", "trocr"]

        self._refused(change, "refine|too long")


class TestDevices(unittest.TestCase):
    def test_device_names(self):
        for raw, want in (
            ("cuda", "gpu"),
            ("cuda:1", "gpu"),
            ("gpu", "gpu"),
            ("gpu:0", "gpu"),
            ("CPU", "cpu"),
            ("mps", "mps"),
            ("", None),
            (None, None),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(ocr_backends._device_name(raw), want)

    def test_health_devices_before_any_scan(self):
        saved = ocr_backends._PADDLE_CFG["use_gpu"]
        try:
            with mock.patch.dict(os.environ, {"VAHINI_TROCR_GPU": "0"}):
                ocr_backends.init_registry(paddle_config={"use_gpu": False})
            self.assertEqual(
                ocr_backends.engine_devices(),
                {
                    "paddle": "cpu",
                    "trocr": "cpu",
                    "surya": None,
                    "paddleocr-vl": None,
                },
            )
            ocr_backends.configure_paddle(use_gpu=True)
            self.assertEqual(ocr_backends.engine_devices()["paddle"], "gpu")
        finally:
            ocr_backends.configure_paddle(use_gpu=saved)

    def test_a_failing_probe_reads_as_unknown(self):
        class _Broken(ocr_backends.OCRBackend):
            name = "broken-probe"

            def resolved_device(self):
                raise RuntimeError("no device")

        ocr_backends.init_registry()
        try:
            ocr_backends.register(_Broken())
            self.assertIsNone(ocr_backends.engine_devices()["broken-probe"])
        finally:
            ocr_backends._REGISTRY.pop("broken-probe", None)


if __name__ == "__main__":
    unittest.main()
