# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Recognition stages: which engine reads each script, as data.

``stages.json`` replaces two things the code used to write out: the set
of Indic languages hybrid mode sent to Surya (``_INDIC_LANGS`` in
recognizer.py) and the TrOCR model id (ocr_backends.py). It also holds
the default Paddle recognition model for each language, which config.py
and warmup_models.py used to repeat as one string. Design:
docs/20-languages.md, sections 6, 17.1 and 17.8 (#208).

The table has two parts:

- ``scripts``: for each script, the languages written in it and the
  engine that re-reads its handwriting lines in hybrid mode. A language
  the table does not name reads as ``default_script``, as every language
  outside the old Indic set did.
- ``stages``: one entry per engine, script set and device, with the facts
  the ladders (#219) will be built from. Facts nobody has measured are
  the string ``unmeasured``.

Nothing here looks at server load, timing or which model is loaded: the
table is read from the repository once per process, so the same photo
always takes the same route (#112). ``VAHINI_TROCR_MODEL`` and
``VAHINI_OCR_REC_MODEL_MAP`` still override the model ids, read where
they always were.
"""

import copy
import hashlib
import json
from pathlib import Path

from report import json_schema

ROOT = Path(__file__).resolve().parent
TABLE_PATH = ROOT / "stages.json"
SCHEMA_PATH = ROOT / "stages.schema.json"
UNMEASURED = "unmeasured"


class StagesError(ValueError):
    """A stage table that cannot be loaded or does not hold together."""


def _validate(data, what):
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    error = json_schema.first_error(json_schema.validator(schema), data)
    if error is not None:
        where = "/".join(str(p) for p in error.path) or "(top)"
        raise StagesError(f"{what}: {where}: {error.message}")


def _check_languages(data, what):
    """default_script is a listed script and a language has one script."""
    scripts = data["scripts"]
    if data["default_script"] not in scripts:
        raise StagesError(
            f"{what}: default_script {data['default_script']!r} "
            "is not in scripts"
        )
    owner = {}
    for script, route in scripts.items():
        for lang in route["languages"]:
            if lang in owner:
                raise StagesError(
                    f"{what}: {lang!r} is under both {owner[lang]} "
                    f"and {script}"
                )
            owner[lang] = script


def _check_stages(data, what):
    """Ids are unique, quality and level name the stage's scripts, and
    the CPU and GPU stages of one engine and script name one model.
    Returns {(engine, task, script): model}."""
    seen = set()
    models = {}
    for stage in data["stages"]:
        if stage["id"] in seen:
            raise StagesError(f"{what}: stage {stage['id']!r} twice")
        seen.add(stage["id"])
        for field in ("quality", "level"):
            if set(stage[field]) != set(stage["scripts"]):
                raise StagesError(
                    f"{what}: {stage['id']}: {field} must name exactly "
                    "the stage's scripts"
                )
        model = stage["version"]["model"]
        for script in stage["scripts"]:
            key = (stage["engine"], stage["task"], script)
            if models.setdefault(key, model) != model:
                raise StagesError(
                    f"{what}: {stage['id']}: {stage['engine']} on "
                    f"{script} names {model!r}, another stage "
                    f"{models[key]!r}"
                )
    return models


def _cross_check(data, what):
    """What the schema cannot say; see the two checks above, and every
    routed engine has a read stage for the script it is routed to."""
    _check_languages(data, what)
    models = _check_stages(data, what)
    for script, route in data["scripts"].items():
        for engine in route["refine"]:
            if (engine, "read", script) not in models:
                raise StagesError(
                    f"{what}: {script} is re-read by {engine}, which has "
                    "no read stage for it"
                )


class Table:
    """One loaded stage table. Read-only."""

    def __init__(self, data, digest):
        self._data = data
        self.hash = digest
        self._script_of = {
            lang: script
            for script, route in data["scripts"].items()
            for lang in route["languages"]
        }

    def __repr__(self):
        return f"Table(hash={self.hash[:12]})"

    @property
    def default_script(self):
        return self._data["default_script"]

    def scripts(self):
        """Script codes in table order."""
        return list(self._data["scripts"])

    def languages(self, script):
        return list(self._data["scripts"][script]["languages"])

    def script_for(self, lang):
        """The script a language code is written in. The match is exact,
        as the old set lookup was: a code the table does not name (``fr``,
        ``te-IN``, ``TE``, None) reads as the default script."""
        return self._script_of.get(lang, self.default_script)

    def refine_engine(self, lang):
        """The engine that re-reads a handwriting line in hybrid mode."""
        return self._data["scripts"][self.script_for(lang)]["refine"][0]

    def route(self, script):
        """The engines hybrid mode re-reads a script's lines with, in
        order: the route scripts/rank_stages.py keeps while a stage's
        quality or cost is unmeasured."""
        return list(self._data["scripts"][script]["refine"])

    def stage(self, stage_id):
        """A copy of one stage entry; KeyError when there is none."""
        for stage in self._data["stages"]:
            if stage["id"] == stage_id:
                return copy.deepcopy(stage)
        raise KeyError(stage_id)

    def stages(self, engine=None):
        """Copies of the stage entries, optionally for one engine."""
        return [
            copy.deepcopy(stage)
            for stage in self._data["stages"]
            if engine is None or stage["engine"] == engine
        ]

    def model(self, engine, script=None):
        """The model id an engine reads with: for one script, or, with no
        script, the one model all its read stages share. None when the
        table does not record it (Surya picks its own)."""
        found = {
            stage["version"]["model"]
            for stage in self._data["stages"]
            if stage["engine"] == engine
            and stage["task"] == "read"
            and (script is None or script in stage["scripts"])
        }
        if len(found) > 1:
            raise StagesError(
                f"{engine} reads with {sorted(found)}; name a script"
            )
        model = found.pop() if found else None
        return None if model == UNMEASURED else model

    def default_rec_model_map(self):
        """``VAHINI_OCR_REC_MODEL_MAP``'s default, ``lang:model`` pairs
        joined by commas: each language of a script Paddle has a read
        stage for, in table order."""
        pairs = []
        for script in self.scripts():
            model = self.model("paddle", script)
            if model:
                pairs.extend(
                    f"{lang}:{model}" for lang in self.languages(script)
                )
        return ",".join(pairs)

    def stage_id(self, engine, script, device):
        """The stage an engine on a device reads a script with, or None."""
        for stage in self._data["stages"]:
            if (
                stage["engine"] == engine
                and stage["task"] == "read"
                and stage["device"] == device
                and script in stage["scripts"]
            ):
                return stage["id"]
        return None


def load(path=None):
    """Read, validate and cross-check a stage table file."""
    path = Path(path) if path else TABLE_PATH
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError as e:
        raise StagesError(f"{path}: {e}") from e
    _validate(data, str(path))
    _cross_check(data, str(path))
    return Table(data, hashlib.sha256(raw).hexdigest())


_TABLE = []


def table():
    """The repository's stage table, loaded once per process."""
    if not _TABLE:
        _TABLE.append(load())
    return _TABLE[0]
