# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The analyser's own sample page, replayed from the reader's kept output
(benchmarks/sample-page), and the sloping lines that broke it.

On 22 October 2026 the stage analyser scored this photo Size Consistency
0.0 and Baseline Alignment 3.2. Its lower lines slope by three to six
degrees, so their boxes are up to 126 px tall on rows about 45 px apart.
The letter measurements took the ink of each line's box, rows above and
below included: words came out three small letters tall (size spread
0.55, a quarter of the words off size) and a fifth of the words off the
line. The sloping box of "can I write better?" also took in the short
line above it, and "with care." was dropped as a second reading of it.
"""

import importlib.util
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from test_line_pieces import line  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
spec = importlib.util.spec_from_file_location(
    "benchmark", os.path.join(ROOT, "scripts", "benchmark.py")
)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

PAGE = "handwriting-sample"
# The factors the free report shows. An even adult hand, scored 6 to 7.5
# on each of them when the sample report was made (14 October 2026); a
# measured 0, or anything near it, is a broken measurement.
FREE = (1, 5, 7, 8, 18)
FLOOR = 4.0


def replay():
    """(hand lines, analysis dict) for the sample page, as the server
    scores it after the reader (benchmark.py's _score)."""
    folder, meta = bench._load_set("sample-page")  # pylint: disable=W0212
    bench._apply_settings(meta)  # pylint: disable=W0212
    from vision import computer_vision  # pylint: disable=C0415
    from vision import ink_geometry  # pylint: disable=C0415
    import scoring  # pylint: disable=C0415

    raw, arr = bench._image(folder, PAGE, meta)  # pylint: disable=W0212
    with open(
        os.path.join(folder, "reader", PAGE + ".json"), encoding="utf-8"
    ) as f:
        reader = json.load(f)
    found, hand = bench._reader_lines(  # pylint: disable=W0212
        arr, raw, reader, meta
    )
    printed = [l for l in found if l.get("printed_hint")]
    rows, _cover = ink_geometry.fragment_rows(arr, hand, printed)
    measured = rows or hand
    layout = computer_vision.vl_analyze(arr, measured, False)["layout"]
    return hand, scoring.build_analysis(arr, measured, layout).to_dict()


class TestSamplePage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hand, cls.analysis = replay()
        cls.results = {r["n"]: r for r in cls.analysis["results"]}

    def features(self, n):
        return self.results[n]["scoringInputs"]["features"]

    def test_the_line_above_a_sloping_line_is_kept(self):
        texts = [l["text"] for l in self.hand]
        self.assertIn("wik cave:", texts)
        self.assertEqual(len(texts), 16)

    def test_letter_sizes_are_the_lines_own(self):
        fx = self.features(5)
        self.assertLess(fx["size_cv"], 0.30)
        self.assertLess(fx["words_off_size"], 0.15)

    def test_words_sit_on_their_own_line(self):
        self.assertLess(self.features(7)["words_off_line"], 0.15)

    def test_free_factors_are_measured_and_sensible(self):
        for n in FREE:
            r = self.results[n]
            with self.subTest(factor=n):
                self.assertFalse(r["unmeasured"])
                self.assertGreaterEqual(r["score"], FLOOR)


class TestLineBand(unittest.TestCase):
    def setUp(self):
        from vision import geometry  # pylint: disable=C0415

        self.band = geometry.line_band

    def test_a_level_line_is_its_box(self):
        self.assertEqual(
            self.band(line("a b", [100, 50, 600, 40]), 400), (50, 90)
        )

    def test_a_sloping_line_follows_its_outline(self):
        # "4e! parctic daily, ..." on the sample page: 4.5 degrees.
        sloping = line("yes", [145, 916, 654, 126])
        sloping["poly"] = [[145, 967], [793, 916], [799, 992], [151, 1042]]
        top, bottom = self.band(sloping, 160)
        self.assertAlmostEqual(top, 965.8, places=1)
        self.assertLess(bottom - top, 80)
        # Past the outline's end: the band at that end.
        self.assertEqual(self.band(sloping, 900), self.band(sloping, 799))

    def test_a_short_word_is_its_box(self):
        # "ps" on UPV_W60: its rotated rectangle leans by 22 degrees.
        word = line("ps", [788, 231, 117, 80])
        word["poly"] = [[788, 272], [889, 231], [905, 271], [804, 312]]
        self.assertEqual(self.band(word, 800), (231, 311))

    def test_no_outline_is_the_box(self):
        bare = line("a", [0, 10, 300, 20])
        del bare["poly"]
        self.assertEqual(self.band(bare, 5), (10, 30))


class TestRereadOnASlope(unittest.TestCase):
    def test_a_short_line_above_a_sloping_line_stays(self):
        from reading import detector  # pylint: disable=C0415

        above = line("wik cave:", [151, 873, 214, 52])
        above["poly"] = [[151, 886], [363, 873], [365, 912], [154, 925]]
        below = line("can ! wrik berter He osls", [144, 884, 525, 93])
        below["poly"] = [[144, 912], [666, 884], [669, 950], [147, 977]]
        out = detector.join_row_pieces([below, above])
        self.assertEqual(
            [l["text"] for l in out], ["wik cave:", below["text"]]
        )


if __name__ == "__main__":
    unittest.main()
