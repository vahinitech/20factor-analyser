# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Is a line printed or handwritten? A small trained reader of the ink.

classify.py decides print from stroke width, letter heights, edges and
how confidently the OCR read a line. Neat handwriting reads as
confidently as type, and on those measures it overlaps a clean font, so
pages of neat handwriting were refused as print
(docs/02-how-a-scan-works.md, sections 8 and 10). This reader looks at the
ink itself.

How it reads a line:

1. Grey, scaled to 32 pixels tall, ink 1 and paper 0 (contrast
   stretched between the crop's 2nd and 98th percentiles).
2. Windows 64 pixels wide, every 32 pixels; windows with almost no ink
   are skipped.
3. Each window goes through three 3x3 convolutions (16, 32 and 48
   filters, each followed by ReLU and 2x2 max pooling), an average over
   the remaining positions, and one output: the window's print score.
4. The line's probability of print is the logistic of the mean score.

Weights: backend/models/print_hand.json, trained by
scripts/train_print_hand.py on handwriting from UJI Pen Characters v2
(CC BY 4.0) and print from open-licence fonts (scripts/print_hand_data.py).
Stored as 8-bit integers with one scale per tensor. Pure numpy, the same
answer for the same crop every time.
"""

import base64
import json
import os

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - cv2 ships in core
    cv2 = None

H = 32
WIN = 64
STEP = 32
MAX_W = 384
MIN_INK = 0.02
WEIGHTS = os.path.join(os.path.dirname(__file__), "models", "print_hand.json")

_NET = None


def _decode(t):
    raw = np.frombuffer(base64.b64decode(t["data"]), dtype=np.int8)
    return raw.astype(np.float32).reshape(t["shape"]) * np.float32(t["scale"])


def load_layers(layers):
    """The network from its stored layers."""
    return [
        {"type": l["type"], "w": _decode(l["w"]), "b": _decode(l["b"])}
        for l in layers
    ]


def load(path=WEIGHTS):
    """The network from its JSON file (cached), or None if it is missing."""
    global _NET  # pylint: disable=global-statement
    if _NET is not None and path == WEIGHTS:
        return _NET
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    net = load_layers(spec["layers"])
    if path == WEIGHTS:
        _NET = net
    return net


def to_input(gray):
    """A grey line crop as the network sees it (H tall, ink 1, paper 0,
    at most MAX_W wide), or None when it is too small."""
    if cv2 is None:
        return None
    h, w = gray.shape[:2]
    if h < 4 or w < 4:
        return None
    nw = max(1, int(round(w * H / float(h))))
    # Shrink by area; enlarge smoothly (area enlarging repeats pixels).
    interp = cv2.INTER_AREA if h >= H else cv2.INTER_LINEAR
    g = cv2.resize(gray, (nw, H), interpolation=interp).astype(np.float32)
    lo, hi = np.percentile(g, 2), np.percentile(g, 98)
    x = np.clip((hi - g) / max(8.0, hi - lo), 0, 1)
    # The training lines are stored as 8-bit; match their rounding.
    return np.floor(x[:, :MAX_W] * 255) / 255.0


def windows(x):
    """(n, 1, H, WIN) windows with ink, left to right."""
    w = x.shape[1]
    if w < WIN:
        x = np.pad(x, ((0, 0), (0, WIN - w)))
        w = WIN
    starts = list(range(0, w - WIN + 1, STEP))
    if starts[-1] != w - WIN:
        starts.append(w - WIN)
    wins = [x[:, s : s + WIN] for s in starts]
    wins = [v for v in wins if v.mean() >= MIN_INK]
    if not wins:
        return None
    return np.stack(wins)[:, None].astype(np.float32)


def _conv3(x, w, b):
    """3x3 convolution, padding 1. x (n, c, h, w), w (o, c, 3, 3)."""
    n, c, h, wd = x.shape
    p = np.pad(x, ((0, 0), (0, 0), (1, 1), (1, 1)))
    cols = np.lib.stride_tricks.sliding_window_view(p, (3, 3), axis=(2, 3))
    # cols: (n, c, h, w, 3, 3) -> (n, h, w, c*9)
    cols = cols.transpose(0, 2, 3, 1, 4, 5).reshape(n, h, wd, c * 9)
    out = cols @ w.reshape(w.shape[0], -1).T + b
    return out.transpose(0, 3, 1, 2)


def _pool2(x):
    n, c, h, w = x.shape
    x = x[:, :, : h // 2 * 2, : w // 2 * 2]
    return x.reshape(n, c, h // 2, 2, w // 2, 2).max(axis=(3, 5))


def window_scores(net, wins):
    x = wins
    for layer in net:
        if layer["type"] == "conv":
            x = _pool2(np.maximum(_conv3(x, layer["w"], layer["b"]), 0))
        else:  # dense, after the average over positions
            x = x.mean(axis=(2, 3)) @ layer["w"].T + layer["b"]
    return x[:, 0]


def print_probability(gray, net=None):
    """Probability that a grey line crop is print, or None when the
    network is missing or the crop has too little ink to judge."""
    net = net or load()
    if net is None:
        return None
    x = to_input(gray)
    if x is None:
        return None
    wins = windows(x)
    if wins is None:
        return None
    score = float(np.mean(window_scores(net, wins)))
    return float(1.0 / (1.0 + np.exp(-score)))
