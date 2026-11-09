# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Letter styles: the cursive and print models schools teach, as data.

``letter_styles.json`` holds one entry per style (#350): its family, whether
it stands upright or leans right, the letters it leaves unjoined after
them, whether capitals join, whether tall letters loop, the Playwrite face
it is drawn in, the countries that teach it and the free shop sheets drawn
in it. The check page's picker, the report's join marks (#344) and Bheema's
plan read it; vahini-web generates its search text from it and keeps no
copy (docs/12-report-rules.md, "Checks are modules on the analyser page").

A style never moves a factor score. It decides which joins the report
expects and which sheets and tips it offers.

``guess()`` is the "Not sure" answer: joined or print from the style check
(vision/style_analysis.py), upright or right from the words' mean lean.
Joined styles that share a family and a lean cannot be told apart by these
two facts, so it returns every style that fits, best first, and always says
it guessed. Consistent break letters (#343) will narrow it further.

The table is read from the repository once per process, so the same photo
always gets the same guess. ``python backend/styles/letter_styles.py
--check`` validates it.
"""

import copy
import hashlib
import json
import sys
from pathlib import Path

# Run as a script: backend/ goes on the path so the schema module imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# pylint: disable-next=wrong-import-position
from report import json_schema  # noqa: E402

ROOT = Path(__file__).resolve().parent
TABLE_PATH = ROOT / "letter_styles.json"
SCHEMA_PATH = ROOT / "letter_styles.schema.json"

# Words leaning less than this, on average, count as upright for the guess.
# A boundary for telling styles apart, not a target: no factor reads it, and
# its accuracy per family is measured on the reference pages (#342).
UPRIGHT_MAX_DEG = 6.0
# Fewest words with a measured lean before the lean takes part in the guess.
MIN_LEAN_WORDS = 3

_TABLE = None


class LetterStyleError(ValueError):
    """A style table that cannot be loaded or does not hold together."""


def _validate(data, what):
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    error = json_schema.first_error(json_schema.validator(schema), data)
    if error is not None:
        where = "/".join(str(p) for p in error.path) or "(top)"
        raise LetterStyleError(f"{what}: {where}: {error.message}")


def _check_rules(data, what):
    """What the schema cannot say: ids are unique, the default exists, a
    print style has no font, joins and breaks agree with the family."""
    ids = [s["id"] for s in data["styles"]]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise LetterStyleError(f"{what}: duplicate style ids {dupes}")
    if data["default_style"] not in ids:
        raise LetterStyleError(
            f"{what}: default_style {data['default_style']!r} is not a style"
        )
    for s in data["styles"]:
        name = f"{what}: {s['id']}"
        if s["family"] == "print":
            if s["font"] is not None:
                raise LetterStyleError(
                    f"{name}: print is drawn in print, not {s['font']}"
                )
            if s["breaks_after"] or s["loops"]:
                raise LetterStyleError(f"{name}: print has no joins or loops")
        elif s["font"] is None:
            raise LetterStyleError(f"{name}: a joined style names its font")
        if s["family"] == "joined-with-breaks" and not s["breaks_after"]:
            raise LetterStyleError(
                f"{name}: joined with breaks lists its breaks"
            )
        if s["family"] == "looped" and s["breaks_after"]:
            raise LetterStyleError(
                f"{name}: looped cursive joins every letter"
            )


def load(path=TABLE_PATH):
    """The validated table. Raises LetterStyleError when it is broken."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    what = Path(path).name
    _validate(data, what)
    _check_rules(data, what)
    return data


def table():
    """The repository's table, read once per process (a copy)."""
    global _TABLE  # pylint: disable=global-statement
    if _TABLE is None:
        _TABLE = load()
    return copy.deepcopy(_TABLE)


def version_hash():
    """sha256 of the table's canonical JSON, for a report to name."""
    canon = json.dumps(table(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def styles():
    """Every style, in table order."""
    return table()["styles"]


def style(style_id):
    """One style by id, or None."""
    for s in styles():
        if s["id"] == style_id:
            return s
    return None


def mean_lean(slants):
    """The words' mean lean in degrees (positive leans right), or None with
    fewer than MIN_LEAN_WORDS measured words."""
    vals = [float(v) for v in slants or () if v is not None]
    if len(vals) < MIN_LEAN_WORDS:
        return None
    return sum(vals) / len(vals)


def lean_label(lean):
    """'upright', 'right' or None for a mean lean in degrees. A backhand
    lean counts as upright: no style leans left."""
    if lean is None:
        return None
    return "right" if lean >= UPRIGHT_MAX_DEG else "upright"


def guess(style_check, lean=None, country=None):
    """The "Not sure" answer for one page.

    style_check: vision/style_analysis.analyze_style's result. lean: the
    words' mean lean in degrees, or None. country: ISO 3166 alpha-2 of the
    visitor's place, or None; it only reorders the styles that fit.

    Returns {"available": False, "reason": ...} when the style check could
    not read the page, else {"available": True, "guessed": True, "style":
    <best id>, "candidates": [ids], "basis": {...}}."""
    if not style_check or not style_check.get("available"):
        return {
            "available": False,
            "reason": "the style check could not read this page",
        }
    data = table()
    verdict = style_check.get("verdict")
    slant = lean_label(lean)
    if verdict == "print":
        fits = [s for s in data["styles"] if s["family"] == "print"]
    else:
        fits = [
            s
            for s in data["styles"]
            if s["family"] != "print"
            and (slant is None or s["slant"] == slant)
        ]
    if country:
        fits.sort(key=lambda s: country not in s["countries"])
    ids = [s["id"] for s in fits]
    if not ids:
        ids = [data["default_style"]]
    elif slant is None and data["default_style"] in ids:
        ids.remove(data["default_style"])
        ids.insert(0, data["default_style"])
    return {
        "available": True,
        "guessed": True,
        "style": ids[0],
        "candidates": ids,
        "basis": {
            "writing": verdict,
            "lean": slant,
            "leanDeg": None if lean is None else round(float(lean), 1),
        },
    }


def ids():
    """Every style id, in table order."""
    return [s["id"] for s in styles()]


def picked(style_id, page_guess=None):
    """The style the visitor picked, as the report carries it, beside what
    the page itself looked like (the guess), or None for an id the table
    does not hold: an unknown style reads as "Not sure"."""
    if style_id not in ids():
        return None
    guess = page_guess if page_guess and page_guess.get("available") else {}
    return {
        "available": True,
        "guessed": False,
        "style": style_id,
        "candidates": [style_id],
        "pageGuess": guess.get("style"),
        "basis": guess.get("basis")
        or {"writing": None, "lean": None, "leanDeg": None},
    }


if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        load()
        print(
            f"letter styles ok: {len(styles())} styles, {version_hash()[:12]}"
        )
    else:
        sys.exit("usage: letter_styles.py --check")
