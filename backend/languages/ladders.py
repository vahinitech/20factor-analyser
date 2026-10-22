# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Recognition ladders: which stages read a line, in what order.

``ladders.json`` lists, for each OCR mode and script, the stages that may
read a handwriting line, cheapest first. The first rung is always the
Paddle stage that found the line; the rungs above it are the engines a
line is sent up to. Design: docs/20-languages.md, sections 17.2 to 17.6
(#219).

The file is built by ``scripts/rank_stages.py`` from ``stages.json`` and
committed; the server reads it as is and never reorders it. It records
the sha256 of the stage table it was built from, and a ladder file built
from another table is refused, so the two cannot drift apart. Nothing
here looks at load, timing or which model is warm: the same photo always
meets the same ladder (#112).

Only the modes that read with Paddle first have ladders: ``paddle``,
``trocr`` and ``hybrid``. ``surya``, ``paddleocr-vl`` and ``auto`` read
whole pages and have none.
"""

import copy
import hashlib
import json
from pathlib import Path

from report import json_schema

from languages import stages

ROOT = Path(__file__).resolve().parent
LADDERS_PATH = ROOT / "ladders.json"
SCHEMA_PATH = ROOT / "ladders.schema.json"
MODES = ("paddle", "trocr", "hybrid")
READER = "paddle"
REBUILD = "run python scripts/rank_stages.py and commit ladders.json"


class LaddersError(ValueError):
    """A ladder file that cannot be loaded or does not fit the stages."""


def _validate(data, what):
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    error = json_schema.first_error(json_schema.validator(schema), data)
    if error is not None:
        where = "/".join(str(p) for p in error.path) or "(top)"
        raise LaddersError(f"{what}: {where}: {error.message}")


def _check_rungs(name, ladder, script, device, stage_table):
    """Every rung is a read stage on the file's device, the first is the
    Paddle stage for the script, and each reads the script (a pinned
    ladder may name a stage for another script: trocr mode)."""
    for i, stage_id in enumerate(ladder["rungs"]):
        try:
            stage = stage_table.stage(stage_id)
        except KeyError:
            raise LaddersError(
                f"{name}: {stage_id!r} is not in stages.json"
            ) from None
        if stage["task"] != "read" or stage["device"] != device:
            raise LaddersError(
                f"{name}: {stage_id} is not a read stage on {device}"
            )
        if i == 0 and stage["engine"] != READER:
            raise LaddersError(
                f"{name}: the first rung must be the {READER} stage "
                f"that found the line, not {stage_id}"
            )
        reads = script in stage["scripts"]
        if not reads and (i == 0 or ladder["basis"] != "pinned"):
            raise LaddersError(f"{name}: {stage_id} does not read {script}")
    named = list(ladder.get("left_off", {})) + ladder.get("unmeasured", [])
    for stage_id in named:
        try:
            stage_table.stage(stage_id)
        except KeyError:
            raise LaddersError(
                f"{name}: {stage_id!r} is not in stages.json"
            ) from None


def _cross_check(data, stage_table, what):
    """What the schema cannot say: the file was built from this stage
    table, and every script of the table has a ladder in every mode."""
    built, loaded = data["stages_sha256"], stage_table.hash
    if built != loaded:
        raise LaddersError(
            f"{what}: built from another stages.json ({built[:12]}, "
            f"loaded {loaded[:12]}); {REBUILD}"
        )
    scripts = sorted(stage_table.scripts())
    for mode in MODES:
        ladders = data["modes"][mode]["read"]
        if sorted(ladders) != scripts:
            raise LaddersError(
                f"{what}: {mode} has ladders for {sorted(ladders)}, "
                f"stages.json names {scripts}; {REBUILD}"
            )
        for script, ladder in ladders.items():
            _check_rungs(
                f"{what}: {mode}/read/{script}",
                ladder,
                script,
                data["device"],
                stage_table,
            )


class Ladders:
    """One loaded ladder file. Read-only."""

    def __init__(self, data, digest, stage_table):
        self._data = data
        self._table = stage_table
        self.hash = digest

    def __repr__(self):
        return f"Ladders(hash={self.hash[:12]})"

    @property
    def device(self):
        return self._data["device"]

    @property
    def stages_sha256(self):
        return self._data["stages_sha256"]

    def ladder(self, mode, script, task="read"):
        """A copy of one ladder entry, or None for a mode with none."""
        if mode not in MODES:
            return None
        return copy.deepcopy(self._data["modes"][mode][task][script])

    def rungs(self, mode, script, task="read"):
        """Stage ids, cheapest first, or None for a mode with no ladder."""
        ladder = self.ladder(mode, script, task)
        return None if ladder is None else ladder["rungs"]

    def rungs_for_lang(self, mode, lang):
        """The read ladder for a line tagged with a language code, through
        the stage table's script lookup (an unnamed code is Latin)."""
        return self.rungs(mode, self._table.script_for(lang or "en"))


def load(path=None, stage_table=None):
    """Read, validate and cross-check a ladder file against a stage
    table (the repository's, by default)."""
    path = Path(path) if path else LADDERS_PATH
    stage_table = stage_table or stages.table()
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError as e:
        raise LaddersError(f"{path}: {e}") from e
    _validate(data, str(path))
    _cross_check(data, stage_table, str(path))
    return Ladders(data, hashlib.sha256(raw).hexdigest(), stage_table)


_LADDERS = []


def table():
    """The repository's ladders, loaded once per process."""
    if not _LADDERS:
        _LADDERS.append(load())
    return _LADDERS[0]
