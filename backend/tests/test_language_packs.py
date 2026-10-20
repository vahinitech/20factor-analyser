# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The language pack registry (backend/languages, #206).

The Latin and English packs must hold the scorer's old constants exactly,
so the first version moves no score: each pack regex is checked against
the literal it replaced on every character up to U+024F and a few Telugu
ones. The rest covers the merge rules (set, add, remove), the schema, the
resolved-pack hash and a class emptied by a child pack.
"""

import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from languages import registry  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PACKS = os.path.join(REPO, "backend", "languages")
# Every Latin code point the old regexes could meet, a space, and some
# Telugu letters and marks.
SAMPLE = "".join(chr(c) for c in range(0x20, 0x250)) + " నా పిల్లి"

# The literals the packs replaced, as they were on main before #206.
OLD_FORM_KW = re.compile(
    r"\b(name|address|adress|date|age|sex|gender|case|doctor|dr|diagnosis|"
    r"admission|discharge|procedure|phone|mobile|id|form|hospital|patient|"
    r"summary|findings|consultant|fir|ip|op|investigation|investgation|"
    r"results|dob|dod|d\.o\.b|d\.o\.d|reg|no|ref|signature|sign|amount|"
    r"total|qty|rate|received|receipt|paid|issued|office|department)\b",
    re.IGNORECASE,
)


def _old_share(text):
    """coach_tips._latin_share and style_analysis._latin_share before."""
    letters = [c for c in str(text or "") if c.isalpha()]
    if not letters:
        return 0.0
    latin = sum(1 for c in letters if c.isascii())
    return latin / float(len(letters))


class PackTree:
    """A temporary packs folder: the real Latn pack plus test packs."""

    def __init__(self, *packs):
        self.dir = tempfile.mkdtemp(prefix="packs-")
        for folder in registry.FOLDERS.values():
            os.makedirs(os.path.join(self.dir, folder))
        shutil.copy(
            os.path.join(PACKS, "scripts", "Latn.json"),
            os.path.join(self.dir, "scripts", "Latn.json"),
        )
        for pack in packs:
            self.write(pack)

    def write(self, pack):
        folder = registry.FOLDERS[pack["kind"]]
        path = os.path.join(self.dir, folder, pack["id"] + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(pack, f)

    def resolve(self, pack_id):
        return registry.resolve(pack_id, root=self.dir)

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def _lang(**ops):
    pack = {
        "id": "xx",
        "kind": "language",
        "extends": "Latn",
        "set": {"name": "Test", "level": 0},
    }
    for op, fields in ops.items():
        pack.setdefault(op, {}).update(fields)
    return pack


class RegistryCase(unittest.TestCase):
    def setUp(self):
        registry.clear_cache()
        self.trees = []

    def tearDown(self):
        for tree in self.trees:
            tree.close()
        registry.clear_cache()

    def tree(self, *packs):
        tree = PackTree(*packs)
        self.trees.append(tree)
        return tree


class TodaysConstants(RegistryCase):
    """The English pack is exactly what the modules used to write out."""

    def setUp(self):
        super().setUp()
        self.en = registry.language("en")

    def test_chain_and_script(self):
        self.assertEqual(self.en.chain, ("Latn", "en"))
        self.assertEqual(self.en.kind, "language")
        self.assertEqual(self.en.get("script"), "Latn")
        self.assertEqual(self.en.get("language"), "en")
        self.assertEqual(self.en.get("direction"), "ltr")
        self.assertEqual(self.en.get("unit"), "letter")
        self.assertEqual(self.en.get("level"), 3)
        self.assertEqual(registry.DEFAULT_LANG, "en")

    def test_letter_lists(self):
        en = self.en
        self.assertEqual(en.letter_set("bowl"), set("abdegopq"))
        self.assertEqual(en.letter_set("body_only"), set("acemnorsuvwxz"))
        self.assertEqual(frozenset(en.get("finishing")), set("adhilmnrtu"))
        self.assertEqual(en.letters("c_family"), "adgqo")
        self.assertEqual(en.get("letters_per_word"), 5.0)
        self.assertEqual(en.get("min_script_share"), 0.9)

    def test_regexes_match_the_old_literals(self):
        en = self.en
        pairs = [
            (r"[A-Za-z]", en.char_class("letter")),
            (r"[A-Z]", en.char_class("upper")),
            (r"[aodpegqAODPEGQ]", en.char_class("loop")),
            (r"[abdegopqABDGOPQR0689]", en.char_class("loop_shapes")),
            (r"[bdfhklt]", en.char_class("ascender")),
            (r"[gjpqy]", en.char_class("descender")),
            (
                r"[bdfhkltgjpqy]",
                en.char_class("ascender") + "|" + en.char_class("descender"),
            ),
            (r"[A-Za-z]+", en.char_class("letter") + "+"),
            (r"[A-Z]{5,}", en.char_class("upper") + "{5,}"),
            (r"tt", en.any_of("tbar_pairs.double")),
            (r"t[lhkb]|[lhkb]t", en.any_of("tbar_pairs.beside_stem")),
        ]
        words = SAMPLE + " little bottle THATS ABCDE Hand tthh kt bt"
        for old, new in pairs:
            with self.subTest(old=old):
                self.assertEqual(
                    re.findall(old, words), re.findall(new, words)
                )
                for c in SAMPLE:
                    self.assertEqual(
                        bool(re.fullmatch(old, c)), bool(re.fullmatch(new, c))
                    )

    def test_form_words_match_the_old_pattern(self):
        new = re.compile(
            r"\b(" + self.en.any_of("form_words") + r")\b", re.IGNORECASE
        )
        texts = [
            "Name:",
            "patient d.o.b 12",
            "D.O.D",
            "dobby",
            "nothing here",
            "Received with thanks",
            "dr. rao",
            "investgation",
            "ip/op",
            "a no b",
            "node",
        ]
        for text in texts:
            with self.subTest(text=text):
                self.assertEqual(
                    bool(OLD_FORM_KW.search(text.lower())),
                    bool(new.search(text.lower())),
                )

    def test_share_matches_the_old_share(self):
        for text in ["", "123", "Hello", "నా school bag", "Ünïcode ok", None]:
            with self.subTest(text=text):
                self.assertEqual(self.en.share(text), _old_share(text))
        self.assertEqual(self.en.share(SAMPLE), _old_share(SAMPLE))


class MergeRules(RegistryCase):
    """set replaces, add and remove change a list or a string of letters."""

    def test_set_replaces_and_reaches_inside(self):
        changes = {"classes.bowl": "ao", "direction": "rtl"}
        pack = self.tree(_lang(set=changes)).resolve("xx")
        self.assertEqual(pack.letters("bowl"), "ao")
        self.assertEqual(pack.letters("loop"), "aodpegqAODPEGQ")
        self.assertEqual(pack.get("direction"), "rtl")

    def test_add_and_remove_letters(self):
        pack = _lang(add={"classes.bowl": "ä"}, remove={"classes.loop": "AO"})
        pack = self.tree(pack).resolve("xx")
        self.assertEqual(pack.letters("bowl"), "abdegopqä")
        self.assertEqual(pack.letters("loop"), "aodpegqDPEGQ")

    def test_add_and_remove_list_items(self):
        added = {"tbar_pairs.double": ["ťť"]}
        removed = {"tbar_pairs.beside_stem": ["bt", "tb"]}
        pack = self.tree(_lang(add=added, remove=removed)).resolve("xx")
        self.assertEqual(pack.get("tbar_pairs.double"), ("tt", "ťť"))
        self.assertEqual(
            pack.get("tbar_pairs.beside_stem"),
            ("tl", "th", "tk", "lt", "ht", "kt"),
        )

    def test_a_pack_says_exactly_what_it_changes(self):
        bad = {
            "adds what is there": _lang(add={"classes.bowl": "a"}),
            "removes what is not": _lang(remove={"classes.bowl": "z"}),
            "names an item twice": _lang(add={"classes.bowl": "ää"}),
            "adds to a missing field": _lang(add={"classes.nope": "a"}),
            "adds a list to letters": _lang(add={"classes.bowl": ["z"]}),
            "two operations on a field": _lang(
                add={"classes.bowl": "z"}, remove={"classes.bowl": "a"}
            ),
            "set over an add": _lang(
                set={"classes": {}}, add={"classes.bowl": "z"}
            ),
        }
        for why, pack in bad.items():
            with self.subTest(why=why):
                registry.clear_cache()
                tree = self.tree(pack)
                with self.assertRaises(registry.PackError):
                    tree.resolve("xx")

    def test_merge_leaves_the_parent_alone(self):
        parent = {"classes": {"bowl": "ab"}, "words": ["x"]}
        child = {
            "id": "xx",
            "add": {"classes.bowl": "c", "words": ["y"]},
        }
        merged = registry.merge(parent, child)
        self.assertEqual(
            merged, {"classes": {"bowl": "abc"}, "words": ["x", "y"]}
        )
        self.assertEqual(parent, {"classes": {"bowl": "ab"}, "words": ["x"]})


class EmptiedClass(RegistryCase):
    """A child can empty a class; its regex then matches nothing."""

    def test_emptied_class(self):
        removed = {"classes.bowl": "abdegopq", "tbar_pairs.double": ["tt"]}
        pack = self.tree(_lang(remove=removed)).resolve("xx")
        self.assertEqual(pack.letters("bowl"), "")
        self.assertEqual(pack.letter_set("bowl"), frozenset())
        self.assertEqual(pack.get("tbar_pairs.double"), ())
        for regex in (
            pack.char_class("bowl"),
            pack.char_class("bowl") + "+",
            pack.char_class("bowl") + "{5,}",
            pack.any_of("tbar_pairs.double"),
        ):
            with self.subTest(regex=regex):
                self.assertEqual(re.findall(regex, SAMPLE + "tt"), [])
        self.assertEqual(pack.share("bob", "bowl"), 0.0)


class Schema(RegistryCase):
    """Pack files and resolved packs are checked against pack.schema.json."""

    def test_every_pack_in_the_repository_resolves(self):
        packs = registry.resolve_all()
        self.assertIn("Latn", [p.id for p in packs])
        self.assertIn("en", [p.id for p in packs])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(registry.main(["--check"]), 0)
        self.assertIn("en: Latn -> en", out.getvalue())

    def test_bad_packs_are_refused(self):
        bad = {
            "unknown top-level key": dict(_lang(), colour="red"),
            "language without a parent": {
                "id": "xx",
                "kind": "language",
                "set": {"name": "X", "level": 0},
            },
            "direction that is not ltr or rtl": _lang(set={"direction": "up"}),
            "level 1 without a benchmark set": _lang(set={"level": 1}),
            "language without a level": {
                "id": "xx",
                "kind": "language",
                "extends": "Latn",
                "set": {"name": "X"},
            },
            "letter class that is not a string": _lang(
                set={"classes.bowl": ["a"]}
            ),
            "unknown resolved field": _lang(set={"colour": "red"}),
            "language extending a language": dict(_lang(), extends="en"),
        }
        for why, pack in bad.items():
            with self.subTest(why=why):
                registry.clear_cache()
                tree = self.tree(pack)
                if why == "language extending a language":
                    shutil.copy(
                        os.path.join(PACKS, "langs", "en.json"),
                        os.path.join(tree.dir, "langs", "en.json"),
                    )
                with self.assertRaises(registry.PackError):
                    tree.resolve("xx")

    def test_a_script_pack_only_sets(self):
        tree = self.tree()
        path = os.path.join(tree.dir, "scripts", "Latn.json")
        with open(path, encoding="utf-8") as f:
            latn = json.load(f)
        latn["add"] = {"classes.bowl": "z"}
        tree.write(latn)
        with self.assertRaises(registry.PackError):
            tree.resolve("Latn")

    def test_ids_must_look_like_ids(self):
        for bad in ("../en", "english", "EN", "en_IN", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(registry.PackError):
                    registry.resolve(bad)
        with self.assertRaises(registry.PackError):
            registry.language("Latn")

    def test_file_must_hold_the_pack_it_is_named_for(self):
        tree = self.tree(_lang())
        os.rename(
            os.path.join(tree.dir, "langs", "xx.json"),
            os.path.join(tree.dir, "langs", "yy.json"),
        )
        with self.assertRaises(registry.PackError):
            tree.resolve("yy")


class Hash(RegistryCase):
    """The resolved pack's hash depends on its facts and nothing else."""

    def test_same_facts_same_hash(self):
        first = registry.language("en").hash
        registry.clear_cache()
        self.assertEqual(registry.language("en").hash, first)
        self.assertRegex(first, r"^[0-9a-f]{64}$")

    def test_layout_of_the_file_does_not_change_the_hash(self):
        tree = self.tree()
        path = os.path.join(PACKS, "langs", "en.json")
        with open(path, encoding="utf-8") as f:
            en = json.load(f)
        reordered = {key: en[key] for key in reversed(list(en))}
        reordered["set"] = {
            key: en["set"][key] for key in reversed(list(en["set"]))
        }
        path = os.path.join(tree.dir, "langs", "en.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(reordered, f, indent=7)
        self.assertEqual(tree.resolve("en").hash, registry.language("en").hash)

    def test_one_letter_changes_the_hash(self):
        level = {"level": 3, "benchmark": "uji-clean"}
        tree = self.tree(_lang(set=level))
        base = tree.resolve("xx").hash
        registry.clear_cache()
        tree.write(_lang(set=level, remove={"classes.bowl": "q"}))
        self.assertNotEqual(tree.resolve("xx").hash, base)


class BenchmarkSets(RegistryCase):
    """Each pack past level 0 names a benchmark set that CI replays."""

    def test_every_named_set_exists(self):
        for pack in registry.resolve_all():
            name = pack.get("benchmark")
            if (pack.get("level") or 0) >= 1:
                self.assertTrue(name, f"{pack.id} names no benchmark set")
            if name:
                path = os.path.join(REPO, "benchmarks", name, "set.json")
                with self.subTest(pack=pack.id):
                    self.assertTrue(os.path.isfile(path), path)

    def test_the_command_prints_the_sets(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(registry.main(["--benchmark-sets"]), 0)
        self.assertEqual(out.getvalue().split(), ["uji-clean"])


if __name__ == "__main__":
    unittest.main()
