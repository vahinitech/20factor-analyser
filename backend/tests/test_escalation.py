# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Each line up its ladder (backend/reading/escalation.py, #219).

The first version of the loop must read every page as the old refine
step did: the same engines, the same guard, the same text. What is new is
what happens when an engine cannot answer. A rung that is down matters
only if a line needs it: then the page is refused, never scored with the
lower reading, so one photo gets one score or a "try again"
(docs/20-languages.md, section 17.4). The engines here are fakes; CI has
no TrOCR or Surya.
"""

import contextlib
import copy
import difflib
import io
import os
import re
import sys
import unittest
from unittest import mock

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
sys.path.insert(0, SERVER_DIR)
sys.path.insert(0, HERE)

from vision import computer_vision  # noqa: E402
from reading import escalation  # noqa: E402
from reading import recognizer  # noqa: E402
from languages import ladders, stages  # noqa: E402
from test_server_pipeline import _hand_strip, _load_server  # noqa: E402

# White-box tests deliberately reach into module-private helpers below.
# pylint: disable=protected-access


def _png(arr):
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def _noise_page(height=640, width=300):
    """A page whose every crop differs, so no two lines share a cached
    answer by accident."""
    rng = np.random.default_rng(7)
    arr = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
    return _png(arr), arr


def _line(text, row, lang="en", score=0.6):
    return {
        "text": text,
        "score": score,
        "box": [10, 10 + 14 * row, 200, 10],
        "lang": lang,
    }


class _Fake:
    """An engine that answers from a list, in call order."""

    def __init__(self, answers, ok=True):
        self.answers = list(answers)
        self.calls = 0
        self.ok = ok

    def available(self):
        return self.ok, "" if self.ok else "not built"

    def recognize_crop(self, _crop):
        self.calls += 1
        return self.answers.pop(0)


class _Broken(_Fake):
    def recognize_crop(self, _crop):
        self.calls += 1
        raise RuntimeError("model crashed")


def _old_refine(raw_bytes, proc_arr, hand_lines, backend_name, get_backend):
    """recognizer.refine_handwriting_text as it was before #219, with the
    engine lookup passed in (and the /health timing left out)."""
    full = np.array(computer_vision.decode_image(raw_bytes))
    ph = float(max(1, proc_arr.shape[0]))
    pw = float(max(1, proc_arr.shape[1]))
    oh, ow = full.shape[0], full.shape[1]
    sx, sy = ow / pw, oh / ph
    for l in hand_lines[:40]:
        name = recognizer._refine_engine_for_line(l.get("lang"), backend_name)
        be = get_backend(name)
        if be is None or not be.available()[0]:
            continue
        box = l.get("box") or [0, 0, 0, 0]
        if len(box) < 4:
            continue
        x, y, w, h = [float(v) for v in box[:4]]
        padx = int(w * sx * 0.06) + 6
        pady = int(h * sy * 0.25) + 6
        x0 = max(0, int(x * sx) - padx)
        y0 = max(0, int(y * sy) - pady)
        x1 = min(ow, int((x + w) * sx) + padx)
        y1 = min(oh, int((y + h) * sy) + pady)
        if x1 <= x0 or y1 <= y0:
            continue
        try:
            cand, conf = be.recognize_crop(full[y0:y1, x0:x1])
        except Exception:
            continue
        cand = re.sub(r"\s*[.·,]+\s*$", "", (cand or "").strip()).strip()
        if not cand:
            continue
        a = re.sub(r"[^a-z0-9]", "", str(l.get("text", "")).strip().lower())
        b = re.sub(r"[^a-z0-9]", "", cand.lower())
        sim = difflib.SequenceMatcher(None, a, b).ratio() if (a and b) else 0
        if sim >= 0.70 or float(conf or 0.0) >= 0.75:
            l["text"] = cand
            l["refined_by"] = name


def _both(lines, mode, answers):
    """(old lines, new lines) for the same page and engine answers."""
    raw, arr = _noise_page()
    old, new = copy.deepcopy(lines), copy.deepcopy(lines)
    engines = {k: _Fake(v) for k, v in answers.items()}
    _old_refine(raw, arr, old, mode, engines.get)
    engines = {k: _Fake(v) for k, v in answers.items()}
    with mock.patch.object(
        recognizer.ocr_backends, "get_backend", engines.get
    ):
        recognizer.refine_handwriting_text(raw, arr, new, mode)
    return old, new


def _without_trail(lines):
    return [{k: v for k, v in l.items() if k != "trail"} for l in lines]


class TestSameAsBefore(unittest.TestCase):
    """The ladders reproduce the old refine step line for line."""

    def test_trocr_mode(self):
        lines = [
            _line("manay ment", 0),
            _line("Hypothyoidum", 1),
            _line("anhulane", 2),
            _line("word", 3),
            _line("kept", 4),
            _line("తెలుగు", 5, lang="te"),
        ]
        answers = {
            "trocr": [
                ("management", 0.2),  # similar: kept
                ("Transportation legislation", 0.2),  # invented: not kept
                ("ambulance", 0.92),  # sure: kept
                ("word .", 0.5),  # the stray " ." is dropped
                ("", 0.95),  # nothing read: the reader's text stays
                ("telugu", 0.9),  # trocr mode reads every script
            ]
        }
        old, new = _both(lines, "trocr", answers)
        self.assertEqual(_without_trail(new), old)
        self.assertEqual(
            [l["text"] for l in new],
            ["management", "Hypothyoidum", "ambulance", "word", "kept"]
            + ["telugu"],
        )

    def test_hybrid_mode(self):
        lines = [
            _line("garbled en", 0),
            _line("గవం", 1, lang="te"),
            _line("नमस", 2, lang="hi"),
            _line("garbled again", 3),
            _line("తెలుగు", 4, lang="te"),
        ]
        answers = {
            "trocr": [("english word", 0.9), ("garbled agian", 0.1)],
            "surya": [
                ("గమనించారు", 0.9),
                ("नमस्ते", 0.8),
                ("తెలుగు పదం", 0.3),  # unsure and not Latin: not kept
            ],
        }
        old, new = _both(lines, "hybrid", answers)
        self.assertEqual(_without_trail(new), old)
        self.assertEqual(
            [l.get("refined_by") for l in new],
            ["trocr", "surya", "surya", "trocr", None],
        )

    def test_a_line_without_a_box_keeps_its_reading(self):
        # A box off the photo gives no crop.
        lines = [_line("one", 0), dict(_line("two", 1), box=[900, 5, 9, 9])]
        old, new = _both(lines, "trocr", {"trocr": [("ONE", 0.9)]})
        self.assertEqual(_without_trail(new), old)
        self.assertEqual(new[1]["trail"]["held"], "no_crop")

    def test_lines_past_forty_keep_the_reader(self):
        lines = [_line(f"line {i}", i) for i in range(44)]
        answers = {"trocr": [(f"LINE {i}", 0.9) for i in range(40)]}
        old, new = _both(lines, "trocr", answers)
        self.assertEqual(_without_trail(new), old)
        self.assertEqual(new[39]["text"], "LINE 39")
        self.assertEqual(new[40]["text"], "line 40")
        self.assertEqual(new[40]["trail"]["held"], "line_limit")

    def test_paddle_mode_calls_no_engine(self):
        def no_engine(name):
            raise AssertionError(f"paddle mode asked for {name}")

        raw, arr = _noise_page()
        lines = [_line("one", 0), _line("రెండు", 1, lang="te")]
        before = copy.deepcopy(lines)
        with mock.patch.object(
            recognizer.ocr_backends, "get_backend", no_engine
        ):
            recognizer.refine_handwriting_text(raw, arr, lines, "paddle")
        self.assertEqual(_without_trail(lines), before)
        self.assertEqual(
            lines[1]["trail"],
            {
                "ladder": "paddle/read/Telu",
                "tried": ["paddle-telu-cpu"],
                "answered": "paddle-telu-cpu",
                "accepted": True,
            },
        )


class TestTrail(unittest.TestCase):
    def test_each_line_records_its_way_up(self):
        lines = [_line("garbled", 0), _line("garbled", 1)]
        answers = {"trocr": [("good", 0.9), ("bad", 0.1)]}
        _old, new = _both(lines, "hybrid", answers)
        self.assertEqual(
            [l["trail"] for l in new],
            [
                {
                    "ladder": "hybrid/read/Latn",
                    "tried": ["paddle-latn-cpu", "trocr-latn-cpu"],
                    "answered": "trocr-latn-cpu",
                    "accepted": True,
                },
                {
                    "ladder": "hybrid/read/Latn",
                    "tried": ["paddle-latn-cpu", "trocr-latn-cpu"],
                    "answered": "paddle-latn-cpu",
                    "accepted": False,
                },
            ],
        )
        got = escalation.summary("hybrid", new)
        self.assertEqual(got["ladders_sha256"], ladders.table().hash)
        self.assertEqual(got["stages_sha256"], stages.table().hash)
        self.assertEqual(
            got["answered"], {"paddle-latn-cpu": 1, "trocr-latn-cpu": 1}
        )
        self.assertEqual(
            got["stages"]["trocr-latn-cpu"],
            stages.table().stage("trocr-latn-cpu")["version"],
        )

    def test_whole_page_modes_record_no_ladder(self):
        for mode in ("surya", "paddleocr-vl", "cv-fallback", None):
            with self.subTest(mode=mode):
                self.assertIsNone(escalation.summary(mode, []))


class TestFallback(unittest.TestCase):
    """A rung that is down: no change when no line needs it, refused when
    one does, never a different reading."""

    def _read(self, lines, mode, engines):
        raw, arr = _noise_page()
        lines = copy.deepcopy(lines)
        with mock.patch.object(
            recognizer.ocr_backends, "get_backend", engines.get
        ):
            recognizer.refine_handwriting_text(raw, arr, lines, mode)
        return lines

    def test_a_down_rung_no_line_needs_changes_nothing(self):
        # A Telugu page in hybrid mode never needs TrOCR.
        lines = [_line("గవం", 0, lang="te"), _line("పదం", 1, lang="te")]
        surya = [("గమనించారు", 0.9), ("పదం", 0.2)]
        up = self._read(
            lines, "hybrid", {"trocr": _Fake([]), "surya": _Fake(surya)}
        )
        down = self._read(
            lines, "hybrid", {"trocr": None, "surya": _Fake(surya)}
        )
        self.assertEqual(down, up)

    def test_a_down_rung_a_line_needs_refuses_the_page(self):
        lines = [_line("గవం", 0, lang="te"), _line("garbled", 1)]
        for trocr in (None, _Fake([], ok=False), _Broken([])):
            with self.subTest(trocr=trocr):
                raw, arr = _noise_page()
                page = copy.deepcopy(lines)
                surya = _Fake([("గమనించారు", 0.9)])
                engines = {"trocr": trocr, "surya": surya}
                with mock.patch.object(
                    recognizer.ocr_backends, "get_backend", engines.get
                ):
                    with self.assertRaises(escalation.RungDown) as caught:
                        recognizer.refine_handwriting_text(
                            raw, arr, page, "hybrid"
                        )
                self.assertEqual(caught.exception.stage_id, "trocr-latn-cpu")
                # Refused, not half read: no line was changed.
                self.assertEqual(page, lines)

    def test_with_an_acceptance_limit_only_unsure_lines_need_the_rung(self):
        # Once a pack sets reading.accept_confidence, a sure reading stops
        # on the first rung, and a down rung above it changes nothing.
        class _Pack:
            def get(self, path, default=None):
                return {
                    "reading.accept_confidence": 0.8,
                    "min_script_share": 0.9,
                }.get(path, default)

            def share(self, _text):
                return 1.0

        sure = [_line("clear", 0, score=0.95), _line("plain", 1, score=0.9)]
        with mock.patch.object(escalation, "_pack_for", lambda _l: _Pack()):
            up = self._read(sure, "hybrid", {"trocr": _Fake([])})
            down = self._read(sure, "hybrid", {"trocr": None})
            self.assertEqual(down, up)
            self.assertEqual(_without_trail(down), sure)
            unsure = sure + [_line("smudge", 2, score=0.4)]
            with self.assertRaises(escalation.RungDown):
                self._read(unsure, "hybrid", {"trocr": None})


class _SurePack:
    """A pack that accepts a reading at confidence 0.7 (test data)."""

    def get(self, path, default=None):
        return {"reading.accept_confidence": 0.7}.get(path, default)

    def share(self, _text):
        return 1.0


class TestServerRefusal(unittest.TestCase):
    """The same photo through the server, in hybrid mode with TrOCR down:
    scored exactly as with TrOCR up when no line needs it, refused with a
    503 and Retry-After when a line does, and the refusal is not cached.
    Never a score from the lower reading."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_server()
        from fastapi.testclient import TestClient

        cls.client = TestClient(cls.mod.app)
        arr = np.full((240, 380, 3), 255, np.uint8)
        arr[150:190, 10:370] = _hand_strip(360, 40)
        arr[3, 3] = [253, 251, 250]  # a photo no other test file sends
        cls.arr = arr
        cls.png = _png(arr)

    @staticmethod
    def _collect(arr_in, _lang):
        del arr_in
        line = {
            "text": "ramu kumar",
            "score": 0.72,
            "box": [10, 150, 360, 40],
            "poly": [[10, 150], [370, 150], [370, 190], [10, 190]],
            "lang": "en",
        }
        return [line], "", "hybrid", {"strategy": "hybrid"}

    def _patched(self, collect, engines, pack=None):
        mod = self.mod
        stack = contextlib.ExitStack()
        stack.enter_context(
            mock.patch.object(mod.recognizer, "collect_lines", collect)
        )
        stack.enter_context(
            mock.patch.object(mod.ocr_backends, "get_backend", engines.get)
        )
        stack.enter_context(
            mock.patch.object(escalation, "_pack_for", lambda _l: pack)
        )
        return stack

    def _scan(self, engines, pack=None):
        with self._patched(self._collect, engines, pack):
            return self.mod._report_python_process(
                self.arr, self.png, "auto", ""
            )

    def test_no_line_needs_the_down_rung_so_the_score_is_the_same(self):
        up = self._scan({"trocr": _Fake([])}, _SurePack())
        down = self._scan({}, _SurePack())
        self.assertTrue(up["ok"], up)
        self.assertEqual(down["analysis"], up["analysis"])
        self.assertEqual(down["hand_lines"], up["hand_lines"])
        self.assertEqual(up["ladder"]["answered"], {"paddle-latn-cpu": 1})

    def test_a_line_needs_the_down_rung_so_the_page_is_refused(self):
        up = self._scan({"trocr": _Fake([("ramu kumar", 0.9)])})
        self.assertTrue(up["ok"], up)
        self.assertEqual(up["ladder"]["answered"], {"trocr-latn-cpu": 1})
        down = self._scan({})
        self.assertEqual(down["error_code"], "ocr_unavailable")
        self.assertNotIn("analysis", down)

    def test_the_refusal_is_a_503_and_is_not_cached(self):
        mod = self.mod
        calls = []

        def counted(arr_in, lang):
            calls.append(1)
            return self._collect(arr_in, lang)

        with self._patched(counted, {}):
            for url in ("/report-python", "/report-python", "/ocr"):
                r = self.client.post(
                    url,
                    files={"image": ("page.png", self.png, "image/png")},
                    data={"lang": "auto"},
                )
                self.assertEqual(r.status_code, 503, r.text)
                self.assertEqual(
                    r.headers.get("retry-after"),
                    str(mod.OCR_UNAVAILABLE_RETRY_SEC),
                )
                self.assertEqual(
                    r.json()["detail"]["error_code"], "ocr_unavailable"
                )
        self.assertEqual(len(calls), 3)  # read again each time, not cached


class TestCache(unittest.TestCase):
    def _rung(self, engine, model=None):
        stage = stages.table().stage("trocr-latn-cpu")
        if model:
            engine.model_name = model
        return escalation.Rung(stage, engine)

    def test_the_same_crop_on_the_same_engine_is_read_once(self):
        _raw, arr = _noise_page()
        crop = arr[10:30, 10:200]
        engine = _Fake([("first", 0.9), ("second", 0.9)])
        rung = self._rung(engine)
        self.assertEqual(rung.read_batch([crop]), [("first", 0.9)])
        self.assertEqual(rung.read_batch([crop.copy()]), [("first", 0.9)])
        self.assertEqual(engine.calls, 1)
        # Another crop, another engine or another model is read again.
        self.assertEqual(rung.read_batch([arr[40:60, 10:200]])[0][0], "second")
        other = self._rung(_Fake([("other", 0.5)]))
        self.assertEqual(other.read_batch([crop]), [("other", 0.5)])
        engine.answers.append(("new model", 0.9))
        renamed = self._rung(engine, model="microsoft/trocr-large")
        self.assertEqual(renamed.read_batch([crop]), [("new model", 0.9)])

    def test_the_key_names_the_stage_and_prompt_versions(self):
        rung = self._rung(_Fake([]))
        self.assertIn("trocr-base-handwritten", rung.version)
        self.assertEqual(escalation.PROMPT_VERSION, 1)


class TestBatch(unittest.TestCase):
    class _Batch(_Fake):
        def __init__(self, answers):
            super().__init__(answers)
            self.batches = []

        def recognize_crops(self, crops):
            self.batches.append(len(crops))
            return [self.answers.pop(0) for _ in crops]

    def test_lines_at_one_rung_go_in_one_call(self):
        engine = self._Batch([("a", 0.9), ("b", 0.9), ("c", 0.9)])
        raw, arr = _noise_page()
        lines = [_line("x", 0), _line("y", 1), _line("z", 2)]
        with mock.patch.object(
            recognizer.ocr_backends, "get_backend", {"trocr": engine}.get
        ):
            recognizer.refine_handwriting_text(raw, arr, lines, "trocr")
        self.assertEqual(engine.batches, [3])
        self.assertEqual([l["text"] for l in lines], ["a", "b", "c"])

    def test_a_short_batch_answer_refuses_the_page(self):
        class _Short(self._Batch):
            def recognize_crops(self, crops):
                return [("a", 0.9)]

        rung = escalation.Rung(
            stages.table().stage("trocr-latn-cpu"), _Short([])
        )
        _raw, arr = _noise_page()
        with self.assertRaisesRegex(escalation.RungDown, "1 of 2"):
            rung.read_batch([arr[0:10, 0:10], arr[20:30, 0:10]])


class TestCircuitBreaker(unittest.TestCase):
    def test_opens_after_failures_and_lets_one_page_try_later(self):
        now = [0.0]
        breaker = escalation.CircuitBreaker(3, 60.0, clock=lambda: now[0])
        for _ in range(3):
            self.assertTrue(breaker.allow())
            breaker.failure()
        self.assertFalse(breaker.allow())
        now[0] = 59.0
        self.assertFalse(breaker.allow())
        now[0] = 61.0
        self.assertTrue(breaker.allow())
        breaker.failure()  # the try failed: open again at once
        self.assertFalse(breaker.allow())
        now[0] = 200.0
        self.assertTrue(breaker.allow())
        breaker.success()
        breaker.failure()
        self.assertTrue(breaker.allow())

    def test_a_remote_rung_is_refused_at_once_when_open(self):
        stage = dict(stages.table().stage("surya-gpu"), device="remote")
        stage["id"] = "surya-remote-test"
        engine = _Broken([])
        _raw, arr = _noise_page()
        try:
            for i in range(escalation.BREAKER_FAILURES):
                rung = escalation.Rung(stage, engine)
                self.assertEqual(rung.available(), (True, ""))
                with self.assertRaises(escalation.RungDown):
                    rung.read_batch([arr[:5, :5] + i])
            ok, reason = escalation.Rung(stage, engine).available()
            self.assertFalse(ok)
            self.assertIn("circuit open", reason)
            self.assertEqual(engine.calls, escalation.BREAKER_FAILURES)
        finally:
            escalation._BREAKERS.pop("surya-remote-test", None)

    def test_a_server_rung_has_no_breaker(self):
        rung = escalation.Rung(
            stages.table().stage("trocr-latn-cpu"), _Broken([])
        )
        _raw, arr = _noise_page()
        for i in range(5):
            with self.assertRaises(escalation.RungDown):
                rung.read_batch([arr[:5, :5] + i])
        self.assertEqual(rung.available(), (True, ""))


class TestAcceptance(unittest.TestCase):
    """17.3 on a three-rung ladder, which no mode has yet."""

    class _Ladders:
        hash = "0" * 64
        stages_sha256 = "0" * 64

        @staticmethod
        def rungs(_mode, _script):
            return ["paddle-latn-cpu", "surya-cpu", "trocr-latn-cpu"]

    class _Pack:
        def get(self, path, default=None):
            return {"reading.accept_confidence": 0.8}.get(path, default)

    def _climb(self, lines, engines):
        raw, arr = _noise_page()
        with mock.patch.object(
            escalation, "_pack_for", lambda _l: self._Pack()
        ):
            escalation.climb(
                lines,
                "hybrid",
                recognizer._crop_reader(raw, arr),
                recognizer._guard,
                get_backend=engines.get,
                ladder_table=self._Ladders(),
            )

    def test_no_limit_means_the_top_rung_decides(self):
        self.assertFalse(escalation.passes("word", 0.99, "en", top=False))
        self.assertTrue(escalation.passes("word", 0.10, "en", top=True))
        self.assertTrue(escalation.passes("గవం", 0.10, "te", top=True))

    def test_a_trusted_but_unsure_reading_climbs_on(self):
        lines = [_line("word", 0, score=0.5)]
        surya, trocr = _Fake([("words", 0.6)]), _Fake([("word", 0.95)])
        self._climb(lines, {"surya": surya, "trocr": trocr})
        self.assertEqual(lines[0]["text"], "word")
        self.assertEqual(lines[0]["refined_by"], "trocr")
        self.assertEqual(
            lines[0]["trail"]["tried"],
            ["paddle-latn-cpu", "surya-cpu", "trocr-latn-cpu"],
        )
        self.assertTrue(lines[0]["trail"]["accepted"])

    def test_a_sure_middle_rung_stops_the_climb(self):
        lines = [_line("word", 0, score=0.5)]
        surya, trocr = _Fake([("word", 0.9)]), _Fake([])
        self._climb(lines, {"surya": surya, "trocr": None})
        self.assertEqual(lines[0]["trail"]["answered"], "surya-cpu")
        self.assertEqual(trocr.calls, 0)

    def test_an_untrusted_reading_is_not_carried_up(self):
        # Surya invents text it is unsure of: the guard keeps the reader's
        # text, and TrOCR is compared with that, not with Surya's.
        lines = [_line("word", 0, score=0.5)]
        surya = _Fake([("Transportation legislation", 0.3)])
        trocr = _Fake([("ward", 0.5)])
        self._climb(lines, {"surya": surya, "trocr": trocr})
        self.assertEqual(lines[0]["text"], "ward")
        self.assertFalse(lines[0]["trail"]["accepted"])


if __name__ == "__main__":
    unittest.main()
