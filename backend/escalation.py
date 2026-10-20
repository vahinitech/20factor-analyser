# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Each handwriting line, sent up its recognition ladder.

Design: docs/20-languages.md, sections 17.3, 17.4, 17.6 and 17.7 (#219).
The ladders are backend/languages/ladders.json, built offline by
scripts/rank_stages.py; nothing here reorders or shortens them.

A line starts on the first rung, the Paddle stage that found it, whose
reading came with the detection. When that reading does not pass the
acceptance test (17.3), the line goes to the next rung, and so on. Lines
that reach the same rung on one page are read together. A higher rung's
reading replaces the one below it only through the guard that hybrid
mode has always used: similar enough to the lower reading
(``VAHINI_REFINE_MIN_SIM``, 0.70), or the higher engine itself very sure
(``VAHINI_REFINE_MIN_CONF``, 0.75). Confidences from different engines are
never compared with each other: the rung decides, not the number.

Fallback (17.4): a rung that cannot answer (not installed, failing to
build or read, or a remote rung whose circuit is open) matters only when
a line needs it. Then the page is refused with ``RungDown``, which the
server answers as ``ocr_unavailable`` with ``Retry-After``. The loop never
skips to the next rung and never keeps the last answer instead, so one
photo is read the same way every time, or not at all (#112).

Answers are cached per loaded engine by the crop's hash, the stage's
version and the prompt version: the same crop on the same engine gets the
same answer without reading it again.

Each line records its trail: the ladder, the rungs tried, the rung whose
reading it kept, and whether that reading passed the acceptance test.
"""

import collections
import difflib
import functools
import hashlib
import json
import re
import threading
import time
import weakref

import ocr_backends
import perf
from languages import ladders, registry, stages

# What a rung is given: the line's crop from the full-resolution photo,
# padded as recognizer._crop_reader pads it, and nothing else. Changing
# that is a new prompt version, so cached answers are not reused.
PROMPT_VERSION = 1
# Lines past this many stay with the reader's reading, as they did before
# the ladders: a page cannot send more than 40 lines up.
MAX_LINES = 40
CACHE_ITEMS = 2048
BREAKER_FAILURES = 3
BREAKER_OPEN_SEC = 60.0
_TRAILING_MARKS = re.compile(r"\s*[.·,]+\s*$")


class RungDown(RuntimeError):
    """A rung a line needs cannot answer: the page is refused (17.4)."""

    def __init__(self, stage_id, reason):
        super().__init__(f"{stage_id} cannot read: {reason}")
        self.stage_id = stage_id
        self.reason = reason


class CircuitBreaker:
    """For a remote rung (a stage on device ``remote``). After ``failures``
    failures in a row it opens for ``open_sec`` seconds, so a page that
    needs the rung is refused at once instead of waiting for a timeout.
    Then one page may try again; a failure opens it again. It only ever
    refuses a page; it never changes which rung reads a line."""

    def __init__(
        self,
        failures=BREAKER_FAILURES,
        open_sec=BREAKER_OPEN_SEC,
        clock=time.monotonic,
    ):
        self.failures = failures
        self.open_sec = open_sec
        self._clock = clock
        self._lock = threading.Lock()
        self._count = 0
        self._opened_at = None

    def allow(self):
        with self._lock:
            if self._opened_at is None:
                return True
            if self._clock() - self._opened_at < self.open_sec:
                return False
            self._opened_at = None
            self._count = self.failures - 1
            return True

    def success(self):
        with self._lock:
            self._count = 0
            self._opened_at = None

    def failure(self):
        with self._lock:
            self._count += 1
            if self._count >= self.failures:
                self._opened_at = self._clock()


_BREAKERS = {}
_BREAKERS_LOCK = threading.Lock()


def breaker(stage_id):
    """The circuit breaker of one remote stage, made on first use."""
    with _BREAKERS_LOCK:
        if stage_id not in _BREAKERS:
            _BREAKERS[stage_id] = CircuitBreaker()
        return _BREAKERS[stage_id]


class AnswerCache:
    """Answers by (crop hash, stage id, stage version, prompt version),
    kept per loaded engine object and dropped with it, oldest first past
    ``items``. An engine object that cannot be weakly referenced is not
    cached at all."""

    def __init__(self, items=CACHE_ITEMS):
        self._items = items
        self._lock = threading.Lock()
        self._by_engine = weakref.WeakKeyDictionary()

    def _store(self, engine):
        try:
            return self._by_engine.setdefault(
                engine, collections.OrderedDict()
            )
        except TypeError:
            return None

    def get(self, engine, key):
        with self._lock:
            store = self._store(engine)
            if store is None or key not in store:
                return None
            store.move_to_end(key)
            return store[key]

    def put(self, engine, key, answer):
        with self._lock:
            store = self._store(engine)
            if store is None:
                return
            store[key] = answer
            store.move_to_end(key)
            while len(store) > self._items:
                store.popitem(last=False)


ANSWERS = AnswerCache()


def crop_hash(crop):
    digest = hashlib.sha256(f"{crop.shape}|{crop.dtype}|".encode())
    digest.update(crop.tobytes())
    return digest.hexdigest()


def stage_version(stage, engine):
    """The stage's version as one string. A model named in the
    environment (``VAHINI_TROCR_MODEL``) is the one that reads, so it
    replaces the table's."""
    version = dict(stage["version"])
    model = getattr(engine, "model_name", None)
    if isinstance(model, str) and model:
        version["model"] = model
    return json.dumps(version, sort_keys=True)


class Rung:
    """One stage on a ladder, with the engine that runs it."""

    def __init__(self, stage, engine):
        self.stage = stage
        self.id = stage["id"]
        self.name = stage["engine"]
        self.engine = engine
        self.remote = stage["device"] == "remote"
        self.version = stage_version(stage, engine)

    def available(self):
        """(ok, reason). Cheap; checked only when a line needs the rung."""
        if self.engine is None or not hasattr(self.engine, "recognize_crop"):
            return False, f"{self.name} is not installed"
        if self.remote and not breaker(self.id).allow():
            return False, "circuit open after repeated failures"
        try:
            ok, reason = self.engine.available()
        except Exception as exc:
            return False, str(exc) or type(exc).__name__
        return bool(ok), reason

    def read_batch(self, crops):
        """(text, confidence) per crop, in order, cached answers first.
        Raises RungDown when the engine fails."""
        keys = [
            (crop_hash(crop), self.id, self.version, PROMPT_VERSION)
            for crop in crops
        ]
        answers = [ANSWERS.get(self.engine, key) for key in keys]
        todo = [i for i, answer in enumerate(answers) if answer is None]
        if todo:
            fresh = self._read([crops[i] for i in todo])
            for i, answer in zip(todo, fresh):
                answers[i] = answer
                ANSWERS.put(self.engine, keys[i], answer)
        return answers

    def _read(self, crops):
        """One call for the page's lines when the engine reads a batch
        (``recognize_crops``), else one call per line. Each line's time
        goes to /health's adaptive_engine_speed, which is information only:
        it never decides a route (#112)."""
        batch = getattr(self.engine, "recognize_crops", None)
        try:
            if callable(batch):
                perf.count("reader_calls")
                perf.count("model_calls")
                t0 = time.perf_counter()
                got = list(batch(crops))
                if len(got) != len(crops):
                    raise RuntimeError(
                        f"answered {len(got)} of {len(crops)} lines"
                    )
                each_ms = (time.perf_counter() - t0) * 1000.0 / len(crops)
                for _ in crops:
                    ocr_backends.record_engine_speed(self.name, each_ms)
            else:
                got = []
                for crop in crops:
                    perf.count("reader_calls")
                    t0 = time.perf_counter()
                    got.append(self.engine.recognize_crop(crop))
                    ocr_backends.record_engine_speed(
                        self.name, (time.perf_counter() - t0) * 1000.0
                    )
        except Exception as exc:
            if self.remote:
                breaker(self.id).failure()
            raise RungDown(self.id, str(exc) or type(exc).__name__) from exc
        if self.remote:
            breaker(self.id).success()
        return [(str(text or ""), float(conf or 0.0)) for text, conf in got]


def clean(text):
    """A rung's reading without the stray trailing " ." TrOCR adds."""
    return _TRAILING_MARKS.sub("", str(text or "").strip()).strip()


def _letters(text):
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def trusted(lower, text, conf, min_sim, min_conf):
    """The guard (config.refine_min_sim and refine_min_conf): a higher
    rung's reading replaces the lower one when it is at least min_sim
    similar to it, or its own engine is at least min_conf sure. The
    similarity compares Latin letters and digits only, so a reading in
    another script is trusted through its confidence alone."""
    a, b = _letters(lower), _letters(text)
    sim = difflib.SequenceMatcher(None, a, b).ratio() if (a and b) else 0.0
    return sim >= min_sim or conf >= min_conf


@functools.lru_cache(maxsize=None)
def _pack_for(lang):
    """The language pack of a line's language, else its script's, else
    None. Packs are repository files, read once per process."""
    ids = set(registry.all_ids())
    for pack_id in (lang, stages.table().script_for(lang)):
        if pack_id in ids:
            return registry.resolve(pack_id)
    return None


def passes(text, conf, lang, top):
    """The acceptance test for a reading (17.3). A line's pack may set
    ``reading.accept_confidence``: a reading is then accepted when the
    confidence of the rung that gave it reaches the limit and its letters
    are in the script (``min_script_share``). No pack sets a limit yet; it
    waits for rank_stages.py to calibrate each stage's confidence per
    script (section 19, gap 5). Until then a reading is accepted at the
    top rung only, so every line climbs its whole ladder, as every line
    was re-read before the ladders."""
    pack = _pack_for(lang)
    limit = pack.get("reading.accept_confidence") if pack else None
    if limit is None:
        return top
    if not text or conf < limit:
        return False
    share = pack.get("min_script_share")
    return share is None or pack.share(text) >= share


class _Line:
    """One line on its way up: the ladder, where it is, the reading it
    holds and the rung that gave it."""

    def __init__(self, line, ladder_name, rungs):
        self.line = line
        self.lang = line.get("lang") or "en"
        self.ladder = ladder_name
        self.rungs = rungs
        self.text = str(line.get("text", "") or "").strip()
        self.by = rungs[0]
        self.tried = [rungs[0]]
        self.crop = None
        self.held = None
        self.accepted = False
        self.done = False

    def trail(self):
        trail = {
            "ladder": self.ladder,
            "tried": list(self.tried),
            "answered": self.by,
            "accepted": self.accepted,
        }
        if self.held:
            trail["held"] = self.held
        return trail


def _start(lines, mode, crop_for, ladder_table):
    """Each line on the first rung, with its crop when it must climb."""
    stage_table = stages.table()
    out = []
    for i, line in enumerate(lines):
        script = stage_table.script_for(line.get("lang") or "en")
        rungs = ladder_table.rungs(mode, script)
        state = _Line(line, f"{mode}/read/{script}", rungs)
        score = float(line.get("score", 0.0) or 0.0)
        top = len(rungs) == 1
        if passes(state.text, score, state.lang, top):
            state.accepted = state.done = True
        elif top:
            state.done = True
        elif i >= MAX_LINES:
            state.held, state.done = "line_limit", True
        else:
            state.crop = crop_for(line)
            if state.crop is None:
                state.held, state.done = "no_crop", True
        out.append(state)
    return out


def _answer(state, stage_id, answer, guard):
    """One rung's reading of one line, through the guard and the test."""
    text, conf = answer
    text = clean(text)
    top = stage_id == state.rungs[-1]
    state.tried.append(stage_id)
    if text and guard(state.text, text, conf):
        state.text, state.by = text, stage_id
        if passes(text, conf, state.lang, top):
            state.accepted = state.done = True
    if top:
        state.done = True


def climb(lines, mode, crop_for, guard, get_backend=None, ladder_table=None):
    """Send each line up its ladder for this OCR mode (17.6).

    crop_for(line) gives the line's crop, or None when it has none.
    guard(lower_text, text, conf) says whether a higher rung's reading
    replaces the lower one. Lines are changed in place, only once every
    rung a line needed has answered: ``text`` and ``refined_by`` (the
    engine) when a higher rung's reading was kept, as before, and
    ``trail`` always. The reader's confidence stays in ``score``.

    Raises RungDown when a line needs a rung that cannot answer; no line
    is changed then.

    perf.py times the ladder and each rung's reading, and counts the
    reader's calls against the page's budget (lines times rungs, one
    batched call per rung); it never changes a route."""
    ladder_table = ladder_table or ladders.table()
    get_backend = get_backend or ocr_backends.get_backend
    with perf.stage("ladder", lines=len(lines)) as step:
        states = _start(lines, mode, crop_for, ladder_table)
        step.size(rungs=max((len(s.rungs) for s in states), default=0))
        page_rungs = _read_up(states, guard, get_backend)
    for state in states:
        if state.by != state.rungs[0]:
            state.line["text"] = state.text
            state.line["refined_by"] = page_rungs[state.by].name
        state.line["trail"] = state.trail()


def _read_up(states, guard, get_backend):
    """Each level of the ladders in turn, every line still climbing read
    together with the others on its rung. Returns the page's rungs."""
    stage_table = stages.table()
    page_rungs = {}
    level = 1
    while True:
        todo = [s for s in states if not s.done]
        if not todo:
            break
        at = collections.OrderedDict()
        for state in todo:
            at.setdefault(state.rungs[level], []).append(state)
        for stage_id, group in at.items():
            if stage_id not in page_rungs:
                stage = stage_table.stage(stage_id)
                engine = get_backend(stage["engine"])
                page_rungs[stage_id] = Rung(stage, engine)
            rung = page_rungs[stage_id]
            ok, reason = rung.available()
            if not ok:
                raise RungDown(stage_id, reason)
            with perf.stage("read." + stage_id, lines=len(group)):
                answers = rung.read_batch([s.crop for s in group])
            for state, answer in zip(group, answers):
                _answer(state, stage_id, answer, guard)
        level += 1
    return page_rungs


def summary(mode, hand_lines, ladder_table=None):
    """What a response records about the ladders a page was read with
    (17.7): the ladder file and stage table versions, the version of each
    stage that was tried, and how many lines each rung answered. None for
    a mode with no ladders."""
    if mode not in ladders.MODES:
        return None
    ladder_table = ladder_table or ladders.table()
    trails = [
        line["trail"]
        for line in hand_lines
        if isinstance(line.get("trail"), dict)
    ]
    tried = sorted({stage_id for t in trails for stage_id in t["tried"]})
    answered = collections.Counter(t["answered"] for t in trails)
    stage_table = stages.table()
    return {
        "mode": mode,
        "ladders_sha256": ladder_table.hash,
        "stages_sha256": ladder_table.stages_sha256,
        "stages": {
            stage_id: stage_table.stage(stage_id)["version"]
            for stage_id in tried
        },
        "answered": dict(sorted(answered.items())),
    }
