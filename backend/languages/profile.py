# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""School, class and child profiles on top of the language packs.

A profile holds teaching choices as data: the letter model, accepted
letter forms, the ruling, class word lists, exception words, what to skip
and which language-skill checks run (docs/20-languages.md, section 18.1,
#220). Layers apply in a fixed order: the packs, then school, then class,
then child. Each field says how it changes what came before:

- ``set`` replaces the value (for a map, the value of each key named);
- ``add`` appends items to a list;
- ``remove`` takes items out of a list.

As in the packs, a key may be named by one operation only, adding an item
that is already there or removing one that is not is an error, and
nothing merges by guesswork. Fixed fields and literal lists only: no code
and no regular expressions, and every list and the whole profile have a
size limit (profile.schema.json, MAX_BYTES).

The result, the ruleset, is hashed with the pack: the hash goes into the
response, the cache key and ``comparability``. With no profile, or one
that changes nothing, the hash is the pack's own hash.

What a profile changes today: a letter whose accepted forms are set to an
empty list is not taught yet. When every letter of a class is untaught,
a factor that counts that class is "Not measured" (factor_needs.py),
never a higher score; a class that keeps one taught letter is counted as
before. Every letter, or every small letter (MUST_KEEP), cannot be
untaught. Everything else is resolved, checked and hashed only, until
its consumers exist: exception words and skip rules for the script
decision (#211) and the language skills (#221), letter forms for
measured letter shapes (level 2). Exception words never change geometry.

Privacy: exception lists can hold children's names. Nothing here logs or
prints a profile's contents; errors name the field, never the value, and
a Ruleset's repr shows only its hash. Profiles are not stored.
"""

import contextlib
import contextvars
import copy
import hashlib
import json
import re
from pathlib import Path

from report import json_schema

from .registry import language

SCHEMA_PATH = Path(__file__).resolve().parent / "profile.schema.json"
# The order layers apply in, most general first.
LEVELS = ("school", "class", "child")
FIELDS = (
    "letter_model",
    "ruling",
    "variants",
    "word_lists",
    "exceptions",
    "checks",
)
OPERATIONS = ("set", "add", "remove")
# The request's profile field, as UTF-8 bytes: every layer together.
MAX_BYTES = 16384
# The letter classes a profile may not empty: every letter, and the small
# letters whose heights factor 5 measures and factors 18 and 20 blend in.
# No factor could honestly be left unmeasured for them. An emptied class
# that factor_needs.CLASSES lists leaves its factor "Not measured"; the
# others (capitals, the c family) steer reading and tips, not a score.
MUST_KEEP = ("body_only", "letter")
# The profile part of a ruleset before any layer: the packs alone.
NOTHING = {
    "letter_model": None,
    "ruling": None,
    "variants": {},
    "word_lists": {},
    "exceptions": {"words": [], "skip": []},
    "checks": {},
}
# 413 for a profile over MAX_BYTES, 422 for every other refusal.
CODES = {
    "profile_too_large": 413,
    "profile_not_json": 422,
    "profile_field_not_allowed": 422,
    "profile_list_too_long": 422,
    "profile_not_in_pack": 422,
    "profile_empties_class": 422,
    "profile_invalid": 422,
}


class ProfileError(ValueError):
    """A profile the server refuses. The message names the field, never
    what the caller wrote in it."""

    def __init__(self, code, message, field=""):
        super().__init__(message)
        self.code = code
        self.field = field

    @property
    def status(self):
        return CODES[self.code]

    def detail(self):
        return {
            "error_code": self.code,
            "error": str(self),
            "field": self.field,
        }


def _schema():
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _validator(definition):
    return json_schema.validator(_schema(), definition)


_VALIDATORS = {}


def _check(definition, data, where):
    if definition not in _VALIDATORS:
        _VALIDATORS[definition] = _validator(definition)
    error = json_schema.first_error(_VALIDATORS[definition], data)
    if error is None:
        return
    path = ".".join([where] + [str(p) for p in error.absolute_path])
    path = path.strip(".")
    kind = error.validator
    extra = []
    # A child's profile lists the fields it may hold as propertyNames.
    if kind == "enum" and "propertyNames" in error.schema_path:
        kind, extra = "additionalProperties", [error.instance]
    elif kind == "additionalProperties":
        known = set(error.schema.get("properties", {}))
        extra = [k for k in error.instance if k not in known]
    if kind == "additionalProperties":
        # Field names only, and only names that look like one.
        extra = sorted(
            k for k in extra if re.fullmatch(r"[a-z_]{1,40}", str(k))
        )
        named = f" ({', '.join(extra)})" if extra else ""
        raise ProfileError(
            "profile_field_not_allowed",
            f"{path or 'profile'}: holds a field a profile may not set"
            + named,
            path,
        )
    if kind in ("maxItems", "maxProperties"):
        limit = error.validator_value
        raise ProfileError(
            "profile_list_too_long",
            f"{path}: holds more than {limit} items",
            path,
        )
    if kind == "maxLength":
        raise ProfileError(
            "profile_invalid",
            f"{path}: longer than {error.validator_value} characters",
            path,
        )
    raise ProfileError(
        "profile_invalid", f"{path or 'profile'}: not valid here", path
    )


def _reject_constant(name):
    raise ValueError(f"{name} is not JSON")


def parse(text):
    """The JSON in the request's profile field, or None when empty.
    Refused when over MAX_BYTES or not JSON; resolve() checks the rest."""
    if text is None or not str(text).strip():
        return None
    if len(str(text).encode("utf-8")) > MAX_BYTES:
        raise ProfileError(
            "profile_too_large",
            f"profile: larger than {MAX_BYTES} bytes",
        )
    try:
        layers = json.loads(text, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        raise ProfileError(
            "profile_not_json", "profile: not valid JSON"
        ) from None
    return layers


def _letters(pack):
    return set(pack.letters("letter"))


def _change_list(have, items, op, where):
    have = list(have)
    for item in items:
        if op == "add":
            if item in have:
                raise ProfileError(
                    "profile_invalid",
                    f"{where}: an item is already there",
                    where,
                )
            have.append(item)
        else:
            if item not in have:
                raise ProfileError(
                    "profile_invalid",
                    f"{where}: an item is not there",
                    where,
                )
            have.remove(item)
    return have


def _apply_map(current, change, where):
    """set, add and remove on a map of lists or values, key by key."""
    named = [key for op in OPERATIONS for key in change.get(op, {})]
    if len(named) != len(set(named)):
        raise ProfileError(
            "profile_invalid",
            f"{where}: a key is changed by more than one operation",
            where,
        )
    out = copy.deepcopy(current)
    for key, value in change.get("set", {}).items():
        out[key] = copy.deepcopy(value)
    for op in ("add", "remove"):
        for key, items in change.get(op, {}).items():
            if key not in out and op == "remove":
                raise ProfileError(
                    "profile_invalid",
                    f"{where}.{op}.{key}: nothing to remove from",
                    f"{where}.{op}.{key}",
                )
            out[key] = _change_list(
                out.get(key, []), items, op, f"{where}.{op}.{key}"
            )
    return out


def _within_pack(rules, pack, where):
    """Letter models and forms come from the pack's reviewed lists."""
    model = rules["letter_model"]
    if model is not None and model not in (pack.get("letter_models") or ()):
        raise ProfileError(
            "profile_not_in_pack",
            f"{where}.letter_model: not a letter model the {pack.id} pack "
            "lists",
            f"{where}.letter_model",
        )
    letters = _letters(pack)
    reviewed = pack.get("variants") or {}
    for letter, forms in rules["variants"].items():
        if letter not in letters:
            raise ProfileError(
                "profile_not_in_pack",
                f"{where}.variants: names a letter the {pack.id} pack does "
                "not have",
                f"{where}.variants",
            )
        if set(forms) - set(reviewed.get(letter, ())):
            raise ProfileError(
                "profile_not_in_pack",
                f"{where}.variants: names a form the {pack.id} pack does "
                "not list for that letter",
                f"{where}.variants",
            )


def apply(rules, layer, level, pack):
    """The rules with one layer's set, add and remove applied."""
    out = copy.deepcopy(rules)
    for name in FIELDS:
        change = layer.get(name)
        if change is None:
            continue
        where = f"{level}.{name}"
        if name in ("letter_model", "ruling"):
            out[name] = change["set"]
        elif name == "checks":
            out[name] = dict(out[name], **change["set"])
        else:
            out[name] = _apply_map(out[name], change, where)
    _within_pack(out, pack, level)
    return out


def _canonical(rules):
    """Lists sorted, so the same rules always hash the same."""
    out = copy.deepcopy(rules)
    out["variants"] = {k: sorted(v) for k, v in out["variants"].items()}
    out["word_lists"] = {k: sorted(v) for k, v in out["word_lists"].items()}
    out["exceptions"] = {
        k: sorted(v) for k, v in sorted(out["exceptions"].items())
    }
    return out


def _digest(value):
    text = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def emptied(rules, pack):
    """The letter classes with no letter left: every letter in them has
    an empty list of accepted forms."""
    untaught = {k for k, forms in rules["variants"].items() if not forms}
    classes = pack.get("classes") or {}
    return frozenset(
        name
        for name, letters in classes.items()
        if letters and set(letters) <= untaught
    )


class Ruleset:
    """The packs plus a resolved profile, and the hash of both. Its rules
    are read-only; its repr never shows them."""

    def __init__(self, pack, rules):
        self.pack = pack
        self._rules = rules
        self.emptied_classes = emptied(rules, pack)
        if rules == NOTHING:
            self.hash = pack.hash
        else:
            self.hash = _digest({"pack": pack.hash, "profile": rules})

    def __repr__(self):
        return f"Ruleset({self.pack.id!r}, hash={self.hash[:12]})"

    def rules(self):
        return copy.deepcopy(self._rules)


def resolve(layers=None, pack=None):
    """The ruleset for these layers (definitions/layers of profile.schema.json,
    or None) on the pack the scorer reads (the English pack by default).
    Refused with ProfileError."""
    pack = pack or language()
    rules = copy.deepcopy(NOTHING)
    if layers is not None:
        _check("layers", layers, "")
    for level in LEVELS:
        layer = (layers or {}).get(level)
        if layer:
            rules = apply(rules, layer, level, pack)
    rules = _canonical(rules)
    _check("resolved", rules, "ruleset")
    gone = emptied(rules, pack) & set(MUST_KEEP)
    if gone:
        raise ProfileError(
            "profile_empties_class",
            "variants: takes every letter out of the "
            + ", ".join(sorted(gone))
            + " class; keep at least one taught",
            "variants",
        )
    return Ruleset(pack, rules)


def from_request(text, pack=None):
    """The ruleset for the request's profile field (empty: the packs)."""
    return resolve(parse(text), pack)


# The ruleset of the scan this thread is scoring, read by factor_needs.
# Set only by applied(), around one call to the scorer.
_ACTIVE = contextvars.ContextVar("vahini_ruleset", default=None)


@contextlib.contextmanager
def applied(ruleset):
    """Score inside this block with the ruleset's emptied classes."""
    token = _ACTIVE.set(ruleset)
    try:
        yield ruleset
    finally:
        _ACTIVE.reset(token)


def active():
    """The ruleset applied() set for this scan, or None (the packs)."""
    return _ACTIVE.get()
