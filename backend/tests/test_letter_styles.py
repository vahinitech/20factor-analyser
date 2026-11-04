# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The letter-style registry (styles/letter_styles.py, #350): the table
holds together, a broken table is refused, the "Not sure" guess picks the
styles that fit the page, and no style or guess moves a factor score."""

# pylint: disable=protected-access

import copy
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import scoring  # noqa: E402
from styles import letter_styles as ls  # noqa: E402
from backend.tests.test_factor_scores import BASE  # noqa: E402

CURSIVE = {"available": True, "verdict": "cursive", "wordsUsed": 12}
MIXED = {"available": True, "verdict": "mixed", "wordsUsed": 12}
PRINT = {"available": True, "verdict": "print", "wordsUsed": 12}


class TableTests(unittest.TestCase):
    def test_the_table_loads(self):
        data = ls.load()
        self.assertEqual(data["version"], 1)
        self.assertIsNotNone(ls.style(data["default_style"]))

    def test_every_family_the_plan_names_is_there(self):
        families = {s["family"] for s in ls.styles()}
        self.assertEqual(
            families,
            {"looped", "joined-with-breaks", "french", "german", "print"},
        )
        for sid in ("looped", "vertical", "straight-india", "print"):
            self.assertIsNotNone(ls.style(sid), sid)

    def test_joined_styles_name_a_cursive_font_and_print_none(self):
        for s in ls.styles():
            if s["family"] == "print":
                self.assertIsNone(s["font"])
            else:
                self.assertTrue(s["font"].startswith("Playwrite "), s["id"])

    def test_the_current_sheets_belong_to_their_model(self):
        # The free cursive sheets are looped cursive leaning right, drawn
        # in Playwrite IN (vahinitech/EdTechBooks#19).
        for s in ls.styles():
            if s["shop_products"]:
                self.assertEqual(
                    (s["family"], s["slant"]), ("looped", "right"), s["id"]
                )

    def test_the_hash_is_stable(self):
        self.assertEqual(ls.version_hash(), ls.version_hash())
        self.assertEqual(len(ls.version_hash()), 64)

    def test_callers_get_a_copy(self):
        ls.styles()[0]["label"] = "changed"
        self.assertNotEqual(ls.styles()[0]["label"], "changed")


class BrokenTableTests(unittest.TestCase):
    def _load(self, change):
        data = copy.deepcopy(ls.table())
        change(data)
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
        self.addCleanup(os.unlink, f.name)
        return ls.load(f.name)

    def _style(self, data, sid):
        return next(s for s in data["styles"] if s["id"] == sid)

    def test_refused(self):
        cases = {
            "duplicate id": lambda d: d["styles"].append(
                copy.deepcopy(d["styles"][0])
            ),
            "missing default": lambda d: d.update(default_style="nope"),
            "print with a font": lambda d: self._style(d, "print").update(
                font="Playwrite IN"
            ),
            "joined without a font": lambda d: self._style(d, "looped").update(
                font=None
            ),
            "breaks with no letters": lambda d: self._style(
                d, "joined-breaks"
            ).update(breaks_after=[]),
            "looped with a break": lambda d: self._style(d, "looped").update(
                breaks_after=["b"]
            ),
            "a slant degree": lambda d: self._style(d, "looped").update(
                slant=12
            ),
            "an unknown field": lambda d: self._style(d, "looped").update(
                colour="red"
            ),
            "a font from elsewhere": lambda d: self._style(d, "looped").update(
                font="Caveat"
            ),
        }
        for name, change in cases.items():
            with self.subTest(name):
                with self.assertRaises(ls.LetterStyleError):
                    self._load(change)


class GuessTests(unittest.TestCase):
    def test_no_guess_without_the_style_check(self):
        self.assertFalse(ls.guess(None)["available"])
        self.assertFalse(ls.guess({"available": False})["available"])

    def test_print_is_print(self):
        g = ls.guess(PRINT, lean=10.0)
        self.assertEqual((g["style"], g["candidates"]), ("print", ["print"]))
        self.assertTrue(g["guessed"])

    def test_upright_joined_writing(self):
        g = ls.guess(CURSIVE, lean=1.5)
        self.assertEqual(g["style"], "vertical")
        self.assertEqual(
            set(g["candidates"]),
            {"vertical", "straight-india", "joined-breaks", "french"},
        )
        self.assertEqual(g["basis"]["lean"], "upright")

    def test_a_backhand_counts_as_upright(self):
        self.assertEqual(
            ls.guess(CURSIVE, lean=-9.0)["basis"]["lean"], "upright"
        )

    def test_right_leaning_joined_writing(self):
        g = ls.guess(MIXED, lean=12.0)
        self.assertEqual(g["style"], "looped")
        self.assertNotIn("vertical", g["candidates"])
        self.assertNotIn("print", g["candidates"])
        self.assertIn("joined-breaks-au", g["candidates"])

    def test_the_country_reorders_only(self):
        g = ls.guess(CURSIVE, lean=1.5, country="IN")
        self.assertEqual(g["style"], "straight-india")
        g = ls.guess(CURSIVE, lean=12.0, country="AU")
        self.assertEqual(g["style"], "joined-breaks-au")
        self.assertEqual(
            ls.guess(CURSIVE, lean=1.5, country="GB")["style"],
            "joined-breaks",
        )
        everywhere = set(ls.guess(CURSIVE, lean=12.0)["candidates"])
        self.assertEqual(set(g["candidates"]), everywhere)

    def test_no_lean_falls_back_to_the_default(self):
        g = ls.guess(CURSIVE, lean=None)
        self.assertEqual(g["style"], ls.table()["default_style"])
        self.assertIn("vertical", g["candidates"])
        self.assertIsNone(g["basis"]["leanDeg"])

    def test_the_boundary(self):
        edge = ls.UPRIGHT_MAX_DEG
        self.assertEqual(ls.lean_label(edge), "right")
        self.assertEqual(ls.lean_label(edge - 0.1), "upright")

    def test_mean_lean_needs_enough_words(self):
        self.assertIsNone(ls.mean_lean([9.0, 12.0]))
        self.assertIsNone(ls.mean_lean([9.0, None, 12.0]))
        self.assertEqual(ls.mean_lean([3.0, 6.0, 9.0]), 6.0)

    def test_same_page_same_guess(self):
        self.assertEqual(
            ls.guess(MIXED, lean=7.5, country="US"),
            ls.guess(MIXED, lean=7.5, country="US"),
        )


class SameScoreTests(unittest.TestCase):
    def test_the_lean_moves_no_factor(self):
        base = scoring._score_factor_map({**BASE, "slant_mean": 0.0})
        for lean in (None, -12.0, 3.0, 20.0):
            fx = {**BASE, "slant_mean": lean}
            self.assertEqual(
                scoring._score_factor_map(fx),
                base,
                lean,
            )

    def test_the_profile_keeps_the_style_check(self):
        out = scoring._style_profile(CURSIVE, {"slant_mean": 2.0})
        self.assertEqual(out["verdict"], "cursive")
        self.assertEqual(out["letterStyle"]["style"], "vertical")
        none = scoring._style_profile({"available": False, "reason": "x"}, {})
        self.assertNotIn("letterStyle", none)


if __name__ == "__main__":
    unittest.main()
