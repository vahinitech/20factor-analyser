# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Language packs: the letter facts the scorer uses, as data.

A pack is a JSON file. Packs inherit, most general first: a script pack
(``scripts/Latn.json``), then a language (``langs/en.json``), then a
locale (``locales/en-IN.json``). Design: docs/20-languages.md, section 4.

Every pack holds its facts under ``set``, ``add`` and ``remove``, so each
field says how it combines with the parent:

- ``set`` replaces the value (a dotted key such as ``classes.loop``
  reaches inside an object);
- ``add`` appends to a list, or appends letters to a string of letters;
- ``remove`` takes items out of a list, or letters out of a string.

A field may appear under one operation only. Adding an item that is
already there, or removing one that is not, is an error: a pack says
exactly what it changes. A script pack has no parent, so it only sets.

The resolved pack is checked against ``pack.schema.json`` and hashed
(sha256 of its canonical JSON), and resolved packs are cached for the
process. Packs are read from the repository, never from the request or
from server state, so the same photo always meets the same facts.

``python backend/languages/registry.py --check`` resolves every pack in
the repository; ``--benchmark-sets`` prints the benchmark set each pack
names, one per line, for CI to replay.
"""

import copy
import hashlib
import json
import re
import sys
from pathlib import Path

# Run as a script (python backend/languages/registry.py): backend/ goes on
# the path so the shared schema module imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# pylint: disable-next=wrong-import-position
from report import json_schema  # noqa: E402

ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "pack.schema.json"
# Which folder holds each kind of pack.
FOLDERS = {"script": "scripts", "language": "langs", "locale": "locales"}
# The language a page is read in when nothing else says.
DEFAULT_LANG = "en"
OPERATIONS = ("set", "add", "remove")
# Pack ids: ISO 15924 script, ISO 639 language, language-REGION locale.
ID_PATTERNS = {
    "script": r"[A-Z][a-z]{3}",
    "language": r"[a-z]{2,3}",
    "locale": r"[a-z]{2,3}-[A-Z]{2}",
}
# A regex that matches nothing, for an emptied letter class or pair list.
NEVER = r"[^\s\S]"


class PackError(ValueError):
    """A pack that cannot be loaded, merged or validated."""


def _validator(definition):
    """The validator for a pack file (None) or for one of its
    definitions."""
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    return json_schema.validator(schema, definition or None)


def _check(definition, data, what):
    error = json_schema.first_error(_validator(definition), data)
    if error is not None:
        where = "/".join(str(p) for p in error.path) or "(top)"
        raise PackError(f"{what}: {where}: {error.message}")


def _read(root, kind, pack_id):
    path = Path(root) / FOLDERS[kind] / f"{pack_id}.json"
    if not path.is_file():
        raise PackError(f"no {kind} pack {pack_id!r} ({path})")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    _check(None, data, str(path))
    if data["id"] != pack_id or data["kind"] != kind:
        raise PackError(
            f"{path}: holds {data['kind']} {data['id']!r}, "
            f"expected {kind} {pack_id!r}"
        )
    return data


def _kind(pack_id):
    """script (Latn), language (en) or locale (en-IN), from the id."""
    for kind, pattern in ID_PATTERNS.items():
        if re.fullmatch(pattern, str(pack_id)):
            return kind
    raise PackError(f"{pack_id!r} is not a script, language or locale id")


def _overlap(paths):
    """Fields named by more than one operation, or one inside another."""
    ordered = sorted(paths)
    for a, b in zip(ordered, ordered[1:]):
        if a == b or b.startswith(a + "."):
            return a, b
    return None


def _walk(facts, path, create):
    keys = path.split(".")
    node = facts
    for key in keys[:-1]:
        if key not in node:
            if not create:
                raise PackError(f"{path}: the parent has no {key!r}")
            node[key] = {}
        node = node[key]
        if not isinstance(node, dict):
            raise PackError(f"{path}: {key!r} is not an object")
    return node, keys[-1]


def _change(current, items, op, path):
    if isinstance(current, str) and isinstance(items, str):
        have, change, joined = list(current), list(items), True
    elif isinstance(current, list) and isinstance(items, list):
        have, change, joined = list(current), list(items), False
    else:
        raise PackError(
            f"{op} {path}: needs a list or a string of letters on both sides"
        )
    if len(set(map(json.dumps, change))) != len(change):
        raise PackError(f"{op} {path}: names an item twice")
    for item in change:
        if op == "add":
            if item in have:
                raise PackError(f"add {path}: {item!r} is already there")
            have.append(item)
        else:
            if item not in have:
                raise PackError(f"remove {path}: {item!r} is not there")
            have = [h for h in have if h != item]
    return "".join(have) if joined else have


def merge(parent, pack):
    """The parent's facts with one pack's set, add and remove applied."""
    named = [p for op in OPERATIONS for p in pack.get(op, {})]
    clash = _overlap(named)
    if clash:
        raise PackError(
            f"{pack.get('id')}: {clash[0]!r} and {clash[1]!r} are changed "
            "by more than one operation"
        )
    facts = copy.deepcopy(parent)
    for path, value in pack.get("set", {}).items():
        node, key = _walk(facts, path, create=True)
        node[key] = copy.deepcopy(value)
    for op in ("add", "remove"):
        for path, items in pack.get(op, {}).items():
            node, key = _walk(facts, path, create=False)
            if key not in node:
                raise PackError(f"{op} {path}: the parent has no {key!r}")
            node[key] = _change(node[key], items, op, path)
    return facts


def pack_hash(facts):
    """sha256 of the resolved facts as canonical JSON."""
    text = json.dumps(
        facts, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _resolve(root, pack_id, seen):
    kind = _kind(pack_id)
    if pack_id in seen:
        raise PackError(f"{pack_id}: inherits from itself ({seen})")
    data = _read(root, kind, pack_id)
    if kind == "script":
        facts = merge({}, data)
        facts["script"] = pack_id
        return facts, [pack_id]
    parent, chain = _resolve(root, data["extends"], seen + [pack_id])
    want = "script" if kind == "language" else "language"
    if _kind(data["extends"]) != want:
        raise PackError(f"{pack_id}: a {kind} extends a {want} pack")
    facts = merge(parent, data)
    if kind == "language":
        facts["language"] = pack_id
    return facts, chain + [pack_id]


class Pack:
    """One resolved pack. Its facts are read-only."""

    def __init__(self, pack_id, kind, chain, facts):
        self.id = pack_id
        self.kind = kind
        self.chain = tuple(chain)
        self._facts = facts
        self.hash = pack_hash(facts)

    def __repr__(self):
        return f"Pack({self.id!r}, hash={self.hash[:12]})"

    def facts(self):
        """A copy of every resolved fact."""
        return copy.deepcopy(self._facts)

    def get(self, path, default=None):
        """One fact by dotted path; lists come back as tuples."""
        node = self._facts
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        if isinstance(node, (dict, list)):
            node = copy.deepcopy(node)
        return tuple(node) if isinstance(node, list) else node

    def letters(self, name):
        """The letters of one class, as a string (may be empty)."""
        classes = self._facts.get("classes", {})
        if name not in classes:
            raise KeyError(f"{self.id} has no letter class {name!r}")
        return classes[name]

    def letter_set(self, name):
        return frozenset(self.letters(name))

    def char_class(self, name):
        """A regex matching one letter of the class; nothing when empty."""
        letters = self.letters(name)
        if not letters:
            return NEVER
        return "[" + "".join(re.escape(c) for c in letters) + "]"

    def any_of(self, path):
        """A regex matching any literal in a list fact; nothing if empty."""
        items = self.get(path)
        if items is None:
            raise KeyError(f"{self.id} has no list {path!r}")
        if not items:
            return NEVER
        return "|".join(re.escape(item) for item in items)

    def share(self, text, name="letter"):
        """Share of the alphabetic characters in `text` that belong to the
        class (0.0 when there are none)."""
        members = self.letter_set(name)
        letters = [c for c in str(text or "") if c.isalpha()]
        if not letters:
            return 0.0
        return sum(1 for c in letters if c in members) / float(len(letters))


_CACHE = {}


def resolve(pack_id, root=None):
    """The resolved pack, validated and cached for the process."""
    root = Path(root) if root else ROOT
    key = (str(root), pack_id)
    if key not in _CACHE:
        facts, chain = _resolve(root, pack_id, [])
        kind = _kind(pack_id)
        resolved = dict(facts, id=pack_id, kind=kind, chain=chain)
        _check("resolved", resolved, f"resolved {pack_id}")
        _CACHE[key] = Pack(pack_id, kind, chain, facts)
    return _CACHE[key]


def language(code=DEFAULT_LANG, root=None):
    """The pack for a language or locale code (``en``, ``en-IN``)."""
    if _kind(code) == "script":
        raise PackError(f"{code!r} is a script, not a language")
    return resolve(code, root)


def clear_cache():
    _CACHE.clear()


def all_ids(root=None):
    """Every pack id in the repository, scripts first."""
    root = Path(root) if root else ROOT
    ids = []
    for kind in ("script", "language", "locale"):
        folder = root / FOLDERS[kind]
        if folder.is_dir():
            ids.extend(sorted(p.stem for p in folder.glob("*.json")))
    return ids


def resolve_all(root=None):
    return [resolve(pack_id, root) for pack_id in all_ids(root)]


def benchmark_sets(root=None):
    """The benchmark sets the packs name, each once, in pack order."""
    out = []
    for pack in resolve_all(root):
        name = pack.get("benchmark")
        if name and name not in out:
            out.append(name)
    return out


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args == ["--check"]:
        for pack in resolve_all():
            print(f"{pack.id}: {' -> '.join(pack.chain)} {pack.hash}")
        return 0
    if args == ["--benchmark-sets"]:
        sets = benchmark_sets()
        if not sets:
            print("no pack names a benchmark set", file=sys.stderr)
            return 1
        print("\n".join(sets))
        return 0
    print("usage: registry.py --check | --benchmark-sets", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
