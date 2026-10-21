# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The safe engine is built only when the normal engine cannot read
(#173). It is a second copy of the reader's models; building it for
every language whatever happened kept that copy in memory for nothing.
What is read, and the error reported, stay as before."""

import os
import sys
import unittest
from unittest import mock

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(HERE)
sys.path.insert(0, SERVER_DIR)

from reading import detector  # noqa: E402
from reading import ocr_backends  # noqa: E402
from reading import recognizer  # noqa: E402

# White-box tests deliberately reach into module-private helpers below.
# pylint: disable=protected-access

ARR = np.full((40, 80, 3), 255, np.uint8)
NORMAL, SAFE = object(), object()


class Engines:
    """Stand-ins for get_engine, get_engine_safe and run."""

    def __init__(self, normal_builds=True, normal_reads=True):
        self.normal_builds = normal_builds
        self.normal_reads = normal_reads
        self.safe_builds = 0

    def get_engine(self, _lang):
        if not self.normal_builds:
            raise RuntimeError("normal engine init failed")
        return NORMAL

    def get_engine_safe(self, _lang):
        self.safe_builds += 1
        return SAFE

    def run(self, engine, _variant, _lang):
        if engine is NORMAL and not self.normal_reads:
            raise RuntimeError("normal engine run failed")
        return [{"text": "normal" if engine is NORMAL else "safe"}]

    def patched(self):
        return mock.patch.multiple(
            ocr_backends,
            get_engine=self.get_engine,
            get_engine_safe=self.get_engine_safe,
            run=self.run,
        )


def _two_variants(arr, *_args):
    return [arr, arr]


class TestSafeEngineLazy(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(detector, "variants", _two_variants)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _collect(self, engines):
        with engines.patched():
            return recognizer.collect_lines_paddle(ARR, "en")

    def _run_lang(self, engines):
        with engines.patched():
            return ocr_backends._paddle_run_lang(ARR, "en")

    def test_normal_engine_reads_without_the_safe_engine(self):
        engines = Engines()
        lines, err = self._collect(engines)
        self.assertEqual([l["text"] for l in lines], ["normal", "normal"])
        self.assertEqual(err, "")
        self.assertEqual(engines.safe_builds, 0)
        engines = Engines()
        self.assertEqual(len(self._run_lang(engines)), 2)
        self.assertEqual(engines.safe_builds, 0)

    def test_failed_read_falls_back_to_the_safe_engine(self):
        engines = Engines(normal_reads=False)
        lines, err = self._collect(engines)
        self.assertEqual([l["text"] for l in lines], ["safe", "safe"])
        self.assertEqual(err, "normal engine run failed")
        self.assertEqual(engines.safe_builds, 1)
        engines = Engines(normal_reads=False)
        out = self._run_lang(engines)
        self.assertEqual([l["text"] for l in out], ["safe", "safe"])
        self.assertEqual(engines.safe_builds, 1)

    def test_failed_build_falls_back_to_the_safe_engine(self):
        engines = Engines(normal_builds=False)
        lines, err = self._collect(engines)
        self.assertEqual([l["text"] for l in lines], ["safe", "safe"])
        self.assertIn("normal engine init failed", err)
        self.assertEqual(engines.safe_builds, 1)
        engines = Engines(normal_builds=False)
        out = self._run_lang(engines)
        self.assertEqual([l["text"] for l in out], ["safe", "safe"])
        self.assertEqual(engines.safe_builds, 1)


if __name__ == "__main__":
    unittest.main()
