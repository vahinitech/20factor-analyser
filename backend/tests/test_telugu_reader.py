# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
# The handwritten Telugu reader (backend/reading/telugu_reader.py) and the guard
# that keeps its training off production's memory (scripts/train_guard.py).
# The runtime is checked with a small network of the same shape; where
# torch is installed, the trainer's network and its export are checked to
# read the same as the numpy runtime.
import base64
import os
import sys
import unittest
import importlib.util

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from reading import (
    telugu_reader as tr,
)  # noqa: E402  pylint: disable=wrong-import-position
import train_guard as guard  # noqa: E402  pylint: disable=wrong-import-position

HAVE_TORCH = importlib.util.find_spec("torch") is not None


def _t(a):
    a = np.asarray(a, np.float32)
    scale = float(np.abs(a).max() / 127.0) or 1.0
    q = np.clip(np.round(a / scale), -127, 127).astype(np.int8)
    return {
        "shape": list(a.shape),
        "scale": scale,
        "data": base64.b64encode(q.tobytes()).decode("ascii"),
    }


def tiny_spec(seed=0, charset="అఆ "):
    rng = np.random.default_rng(seed)

    def w(*shape):
        return rng.normal(0, 0.5, shape)

    layers = []
    c_in = 1
    for c_out, pool in ((2, [2, 2]), (3, [2, 2]), (3, [2, 1]), (3, [2, 1])):
        layers.append(
            {
                "type": "conv",
                "w": _t(w(c_out, c_in, 3, 3)),
                "b": _t(w(c_out)),
                "pad": [1, 1],
                "pool": pool,
            }
        )
        c_in = c_out
    layers.append(
        {
            "type": "conv",
            "w": _t(w(4, c_in, 3, 1)),
            "b": _t(w(4)),
            "pad": [0, 0],
            "pool": None,
        }
    )
    hid = 3
    for d_in in (4, 2 * hid):
        layers.append(
            {
                "type": "bilstm",
                **{
                    k: {
                        "w_ih": _t(w(4 * hid, d_in)),
                        "w_hh": _t(w(4 * hid, hid)),
                        "b": _t(w(4 * hid)),
                    }
                    for k in ("fw", "bw")
                },
            }
        )
    layers.append(
        {
            "type": "dense",
            "w": _t(w(len(charset) + 1, 2 * hid)),
            "b": _t(w(len(charset) + 1)),
        }
    )
    return {"charset": charset, "layers": layers}


def page_crop(width=300, height=90):
    """Dark strokes on light paper, like a photographed word."""
    a = np.full((height, width), 235, np.uint8)
    a[30:60, 20:60] = 40
    a[25:65, 90:110] = 50
    a[35:55, 150:260] = 45
    return a


class TestPrepare(unittest.TestCase):
    def test_blank_paper_has_no_ink(self):
        self.assertIsNone(tr.prepare(np.full((60, 200), 240, np.uint8)))

    def test_ink_is_one_and_height_is_fixed(self):
        x = tr.prepare(page_crop())
        self.assertEqual(x.shape[0], tr.H)
        self.assertEqual(x.dtype, np.float32)
        self.assertGreater(x.max(), 0.9)  # ink
        self.assertLess(np.median(x), 0.5)  # paper

    def test_colour_crop_reads_like_grey(self):
        grey = page_crop()
        colour = np.stack([grey] * 3, axis=2)
        np.testing.assert_allclose(
            tr.prepare(colour), tr.prepare(grey), atol=1e-2
        )

    def test_width_is_capped(self):
        x = tr.prepare(page_crop(width=6000, height=60))
        self.assertLessEqual(x.shape[1], tr.MAX_W)


class TestRuntime(unittest.TestCase):
    def setUp(self):
        self.model = tr.load_spec(tiny_spec())

    def test_one_column_per_four_pixels(self):
        x = tr.prepare(page_crop())
        scores = tr.forward(self.model, x)
        self.assertEqual(scores.shape, (x.shape[1] // tr.STRIDE, 4))

    def test_same_crop_same_text(self):
        a = tr.read(self.model, page_crop())
        b = tr.read(self.model, page_crop())
        self.assertEqual(a, b)

    def test_decode_drops_blanks_and_repeats(self):
        # columns: blank, అ, అ, blank, అ, ఆ, ఆ, space
        best = [0, 1, 1, 0, 1, 2, 2, 3]
        scores = np.full((len(best), 4), -5.0, np.float32)
        for t, k in enumerate(best):
            scores[t, k] = 5.0
        text, conf = tr.decode(self.model, scores)
        self.assertEqual(text, "అఅఆ ")
        self.assertGreater(conf, 0.9)

    def test_no_ink_no_reading(self):
        self.assertIsNone(
            tr.read(self.model, np.full((40, 90), 250, np.uint8))
        )


class FakeTorch:
    def __init__(self, cuda, mps):
        class _Cuda:
            @staticmethod
            def is_available():
                return cuda

        class _Mps:
            @staticmethod
            def is_available():
                return mps

        class _Backends:
            pass

        self.cuda = _Cuda()
        self.backends = _Backends()
        self.backends.mps = _Mps()


class TestGuard(unittest.TestCase):
    LIMITS = {"floor_mb": 1500, "max_rss_mb": 2000, "max_load": 1.0}

    def test_device_falls_back(self):
        self.assertEqual(
            guard.pick_device("auto", FakeTorch(False, True))[0], "mps"
        )
        self.assertEqual(
            guard.pick_device("auto", FakeTorch(True, True))[0], "cuda"
        )
        dev, note = guard.pick_device("cuda", FakeTorch(False, False))
        self.assertEqual(dev, "cpu")
        self.assertIn("not available", note)
        self.assertEqual(
            guard.pick_device("cpu", FakeTorch(True, True))[0], "cpu"
        )

    def test_cpu_threads_leave_a_core_free(self):
        self.assertEqual(guard.cpu_threads(0, 4), 2)
        self.assertEqual(guard.cpu_threads(8, 4), 3)
        self.assertEqual(guard.cpu_threads(0, 1), 1)

    def test_decisions(self):
        d = guard.decide
        self.assertEqual(d(4000, 800, 1.0, 4, self.LIMITS), guard.OK)
        self.assertEqual(d(1000, 800, 1.0, 4, self.LIMITS), guard.PAUSE)
        self.assertEqual(d(4000, 2500, 1.0, 4, self.LIMITS), guard.STOP)
        self.assertEqual(d(4000, 800, 6.0, 4, self.LIMITS), guard.PAUSE)
        no_load = dict(self.LIMITS, max_load=None)
        self.assertEqual(d(4000, 800, 9.0, 4, no_load), guard.OK)

    def _guard(self, probes):
        saved, slept = [], []
        g = guard.Guard(
            dict(self.LIMITS, pause_s=1, max_pauses=2),
            save=lambda: saved.append(1),
            log=lambda _m: None,
            sleep=slept.append,
        )
        it = iter(probes)
        return g, (lambda: next(it)), saved, slept

    def test_waits_for_memory_then_goes_on(self):
        g, probe, saved, slept = self._guard(
            [(900, 500, 0.5), (3000, 500, 0.5)]
        )
        g.check(probe)
        self.assertEqual((len(saved), len(slept)), (1, 1))

    def test_stops_with_resume_code_when_memory_stays_short(self):
        g, probe, saved, _slept = self._guard([(900, 500, 0.5)] * 5)
        with self.assertRaises(SystemExit) as cm:
            g.check(probe)
        self.assertEqual(cm.exception.code, guard.EXIT_RESUME)
        self.assertGreaterEqual(len(saved), 1)

    def test_stops_at_once_over_its_own_ceiling(self):
        g, probe, saved, slept = self._guard([(5000, 2600, 0.5)])
        with self.assertRaises(SystemExit):
            g.check(probe)
        self.assertEqual((len(saved), len(slept)), (1, 0))


@unittest.skipUnless(HAVE_TORCH, "torch is not installed (training only)")
class TestExportMatchesTorch(unittest.TestCase):
    def test_numpy_reads_what_torch_reads(self):
        import torch  # pylint: disable=import-outside-toplevel
        import train_telugu_reader as trainer  # pylint: disable=import-outside-toplevel

        torch.manual_seed(0)
        charset = " అఆఇ"
        net = trainer.Reader(len(charset))
        # Batch-norm statistics that are not the identity, so folding
        # them into the convolutions is tested.
        for m in net.cnn:
            if isinstance(m, torch.nn.BatchNorm2d):
                m.running_mean.uniform_(-0.2, 0.2)
                m.running_var.uniform_(0.5, 1.5)
        net.eval()
        x = tr.prepare(page_crop())
        with torch.no_grad():
            want = net(torch.from_numpy(x)[None, None])[:, 0].numpy()
        got = tr.forward(tr.load_spec(trainer.export(net, charset)), x)
        z = got - got.max(1, keepdims=True)
        got = z - np.log(np.exp(z).sum(1, keepdims=True))  # log-softmax
        self.assertEqual(got.shape, want.shape)
        # 8-bit weights: close, not equal.
        self.assertLess(float(np.abs(got - want).mean()), 0.05)
        self.assertTrue((got.argmax(1) == want.argmax(1)).mean() > 0.9)


if __name__ == "__main__":
    unittest.main()
