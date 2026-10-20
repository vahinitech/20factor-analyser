# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Build backend/languages/ladders.json from backend/languages/stages.json.

    python scripts/rank_stages.py            write ladders.json
    python scripts/rank_stages.py --check    fail when ladders.json is not
                                             what stages.json gives

A ladder is the list of stages that may read a handwriting line of one
script, cheapest first (docs/20-languages.md, section 17.2). The first
rung is always the Paddle stage that found the line: Paddle detects every
line in the paddle, trocr and hybrid modes, and its reading comes with
the detection. The rungs above it depend on the mode:

- ``paddle``: none. The reader's own reading is the answer.
- ``trocr``: TrOCR re-reads every handwriting line, whatever its script,
  as trocr mode did before the ladders (#219).
- ``hybrid``: ranked from the stage facts by the three rules of 17.2.
  1. Filter: drop a stage that sends the photo off the server (unless
     ``--allow-leaves``), one that is measured as not fixed (the same
     input can read differently), and one measured below maturity level
     2 for the script (section 11: level 2 is where reading starts).
  2. Sort by cost: on the server first, then p95 time per line, then
     money per call, ties by stage id, so file order never matters.
  3. Keep a stage only if its quality band is strictly better than every
     cheaper stage kept, the reader included. A slower stage that is no
     better can never help, so it is not on the ladder.
  When the reader or a stage that passed the filter has its quality or
  cost for the script still ``unmeasured``, nothing can be ranked: the
  ladder is the route stages.json names for the script (``refine``),
  marked ``basis: route`` with the stages that were not measured. That
  keeps hybrid mode reading exactly as it did until the figures exist.

A hard rule that fails on a measured fact is applied to the route too:
a route through a stage measured as not fixed is refused, not followed.

Measuring is not done here yet. Quality bands per script from the
benchmark sets, the confidence calibration and sure-and-wrong counts
(section 19, gap 5) and p95 time on the deploy box are follow-ups of
#219; until they land, every such figure in stages.json is
``unmeasured`` and this script says so in the ladders.

Standard library plus jsonschema (backend/requirements-core.txt).
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from languages import ladders, stages  # noqa: E402

BANDS = ("A", "B", "C", "D")  # best first
READER = ladders.READER
PINNED = "trocr"
# The engines hybrid mode may send a line up to. paddleocr-vl reads whole
# pages and has no way to read one line, so it is not a rung.
CLIMBERS = ("surya", "trocr")
MIN_READ_LEVEL = 2
COMMENT = (
    "Built by scripts/rank_stages.py from stages.json (docs/20-languages.md, "
    "section 17.2); do not edit by hand. Each ladder lists the stages that "
    "may read a handwriting line of one script, cheapest first: the Paddle "
    "stage that found the line, then the stages a line is sent up to. "
    "basis: reader (paddle mode, the reader alone), pinned (trocr mode, "
    "TrOCR re-reads every line), route (hybrid mode while a quality or cost "
    "is unmeasured: the refine route in stages.json), ranked (hybrid mode "
    "from measured facts). left_off says why a stage is not on a ladder; "
    "unmeasured names the stages that kept a ladder from being ranked."
)


class RankError(ValueError):
    """Stage facts that cannot give a ladder."""


def _measured(value):
    return value != stages.UNMEASURED


def hard_rule(stage, script, allow_leaves=False):
    """Why a stage may not read this script, or None. An unmeasured fact
    breaks no rule; it only keeps the ladder from being ranked."""
    if stage["where"] == "leaves" and not allow_leaves:
        return "sends the photo off the server"
    if stage["fixed"] is False:
        return "not fixed: the same line can read differently"
    level = stage["level"].get(script, stages.UNMEASURED)
    if _measured(level) and level < MIN_READ_LEVEL:
        return f"maturity level {level}, reading needs {MIN_READ_LEVEL}"
    return None


def _unmeasured(stage, script):
    cost = stage["cost"]
    facts = (
        stage["quality"][script],
        cost["p95_ms_per_line"],
        cost["money_per_call"],
    )
    return not all(_measured(v) for v in facts)


def cost_key(stage):
    """17.2 rule 2: on the server first, then time, then money, then id."""
    cost = stage["cost"]
    return (
        stage["where"] != "server",
        cost["p95_ms_per_line"],
        cost["money_per_call"],
        stage["id"],
    )


def _stage(table, engine, script, device):
    stage_id = table.stage_id(engine, script, device)
    return None if stage_id is None else table.stage(stage_id)


def _reader(table, script, device):
    stage = _stage(table, READER, script, device)
    if stage is None:
        raise RankError(
            f"{script}: no {READER} read stage on {device}; every script "
            "needs one, since it reads the lines it finds"
        )
    why = hard_rule(stage, script)
    if why:
        raise RankError(
            f"{stage['id']} is every {script} ladder's first rung but "
            f"is {why}"
        )
    return stage


def rank(reader, candidates, script, allow_leaves=False):
    """Section 17.2 on measured facts. The reader is always the first
    rung. Returns (entry, unmeasured): entry is None and unmeasured names
    the stages that kept the ladder from being ranked."""
    left_off = {}
    usable = []
    for stage in candidates:
        why = hard_rule(stage, script, allow_leaves)
        if why:
            left_off[stage["id"]] = why
        else:
            usable.append(stage)
    missing = sorted(
        s["id"] for s in [reader] + usable if _unmeasured(s, script)
    )
    if missing:
        return None, missing
    rungs = [reader["id"]]
    best = reader["quality"][script]
    for stage in sorted(usable, key=cost_key):
        band = stage["quality"][script]
        if BANDS.index(band) < BANDS.index(best):
            rungs.append(stage["id"])
            best = band
        else:
            left_off[stage["id"]] = (
                f"band {band}, no better than {best} on a cheaper rung"
            )
    entry = {"basis": "ranked", "rungs": rungs}
    if left_off:
        entry["left_off"] = dict(sorted(left_off.items()))
    return entry, []


def reader_ladder(table, script, device, _allow_leaves=False):
    return {"basis": "reader", "rungs": [_reader(table, script, device)["id"]]}


def pinned_ladder(table, script, device, _allow_leaves=False):
    """trocr mode: TrOCR re-reads every line. TrOCR reads Latin only, so a
    line of another script is read by its Latin stage, as before."""
    reader = _reader(table, script, device)
    read_as = script
    stage = _stage(table, PINNED, script, device)
    if stage is None:
        read_as = table.default_script
        stage = _stage(table, PINNED, read_as, device)
    if stage is None:
        raise RankError(f"no {PINNED} read stage on {device}")
    why = hard_rule(stage, read_as)
    if why:
        raise RankError(f"trocr mode re-reads with {stage['id']}, {why}")
    return {"basis": "pinned", "rungs": [reader["id"], stage["id"]]}


def hybrid_ladder(table, script, device, allow_leaves=False):
    reader = _reader(table, script, device)
    candidates = [
        stage
        for stage in (_stage(table, e, script, device) for e in CLIMBERS)
        if stage is not None
    ]
    entry, missing = rank(reader, candidates, script, allow_leaves)
    if entry is not None:
        return entry
    rungs = [reader["id"]]
    for engine in table.route(script):
        stage = _stage(table, engine, script, device)
        if stage is None:
            raise RankError(
                f"{script}: the route names {engine}, which has no read "
                f"stage on {device}"
            )
        why = hard_rule(stage, script, allow_leaves)
        if why:
            raise RankError(
                f"{script}: the route names {stage['id']}, which is {why}"
            )
        rungs.append(stage["id"])
    return {"basis": "route", "rungs": rungs, "unmeasured": missing}


MODES = {
    "paddle": reader_ladder,
    "trocr": pinned_ladder,
    "hybrid": hybrid_ladder,
}


def build(table, device="cpu", allow_leaves=False):
    """The ladder file stages.json gives, as a dict."""
    modes = {
        mode: {
            "read": {
                script: make(table, script, device, allow_leaves)
                for script in table.scripts()
            }
        }
        for mode, make in MODES.items()
    }
    return {
        "$comment": COMMENT,
        "version": 1,
        "stages_sha256": table.hash,
        "device": device,
        "modes": modes,
    }


def _differences(current, built):
    """The ladders that differ, one line each, for --check."""
    out = []
    for key in ("stages_sha256", "device"):
        if current.get(key) != built[key]:
            out.append(f"{key}: {current.get(key)} -> {built[key]}")
    old_modes = current.get("modes") or {}
    for mode, tasks in built["modes"].items():
        for script, ladder in tasks["read"].items():
            old = (old_modes.get(mode) or {}).get("read", {}).get(script)
            if old != ladder:
                out.append(f"{mode}/read/{script}: {old} -> {ladder}")
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--device",
        choices=("cpu", "gpu"),
        help="device every rung runs on (default: the committed file's)",
    )
    parser.add_argument(
        "--allow-leaves",
        action="store_true",
        help="allow stages that send the photo off the server; only with "
        "the owner's written policy (section 17.2)",
    )
    args = parser.parse_args(argv)
    path = ladders.LADDERS_PATH
    current = None
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
    device = args.device or (current or {}).get("device") or "cpu"
    table = stages.load()
    built = build(table, device, args.allow_leaves)
    if args.check:
        if current != built:
            print(
                f"{path} is not what stages.json gives; run python "
                "scripts/rank_stages.py and commit it:",
                file=sys.stderr,
            )
            for line in _differences(current or {}, built) or ["$comment"]:
                print(f"  {line}", file=sys.stderr)
            return 1
        ladders.load(path, table)
        print(f"{path.name} is up to date with stages.json")
        return 0
    path.write_text(
        json.dumps(built, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    ladders.load(path, stages.load())
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
