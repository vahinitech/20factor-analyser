# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""A reader for handwritten Telugu: one row or word of ink in, text out.

PP-OCRv5's Telugu model was trained on print. On real handwritten Telugu
it returned Latin fragments ("es aons") and found 7 of 80 lines
(docs/18-benchmark.md, "Telugu"). This reader is trained on handwriting:
IIIT-INDIC-HW-WORDS-Telugu (Gongidi and Jawahar, ICDAR 2021, CC BY 4.0),
by scripts/train_telugu_reader.py.

How it reads a crop:

1. Grey, ink 1 and paper 0, contrast stretched between the crop's
   0.5th and 90th percentiles, cropped to the ink, scaled to H pixels tall
   (vowel signs above and consonants written below the row both fit),
   at most MAX_W wide (prepare).
2. Six 3x3 convolutions with ReLU; max pooling halves both sides twice
   and then the height twice, so each output column covers 4 pixels of
   width. A last convolution folds the remaining 3 rows into one.
3. Two bidirectional LSTM layers read the columns left to right and
   right to left.
4. One dense layer gives, per column, a score for every character and
   for "no character" (CTC blank). The best path, with repeats and
   blanks removed, is the text (decode).

Weights: backend/models/telugu_reader.json, 8-bit integers with one scale
per tensor, batch normalisation folded into the convolutions at export.
Pure numpy and Pillow: the same crop gives the same text every time, and
the analyser image needs no torch.
"""

import base64
import json
import os

import numpy as np
from PIL import Image

H = 48
MAX_W = 1024
MIN_W = 16
STRIDE = 4  # input pixels per output column
WEIGHTS = os.path.join(
    os.path.dirname(__file__), "models", "telugu_reader.json"
)

_NET = None


def _decode_tensor(t):
    raw = np.frombuffer(base64.b64decode(t["data"]), dtype=np.int8)
    return raw.astype(np.float32).reshape(t["shape"]) * np.float32(t["scale"])


def load_spec(spec):
    """The network from its stored spec (a dict, as in the JSON file)."""
    layers = []
    for layer in spec["layers"]:
        kind = layer["type"]
        if kind == "conv":
            layers.append(
                {
                    "type": "conv",
                    "w": _decode_tensor(layer["w"]),
                    "b": _decode_tensor(layer["b"]),
                    "pad": tuple(layer.get("pad", (1, 1))),
                    "pool": (
                        tuple(layer["pool"]) if layer.get("pool") else None
                    ),
                }
            )
        elif kind == "bilstm":
            layers.append(
                {
                    "type": "bilstm",
                    "dirs": [
                        {
                            k: _decode_tensor(d[k])
                            for k in ("w_ih", "w_hh", "b")
                        }
                        for d in (layer["fw"], layer["bw"])
                    ],
                }
            )
        elif kind == "dense":
            layers.append(
                {
                    "type": "dense",
                    "w": _decode_tensor(layer["w"]),
                    "b": _decode_tensor(layer["b"]),
                }
            )
        else:
            raise ValueError(f"unknown layer type {kind!r}")
    return {"charset": spec["charset"], "layers": layers}


def load(path=WEIGHTS):
    with open(path, encoding="utf-8") as f:
        return load_spec(json.load(f))


def net():
    """The committed reader, loaded once; None when no weights exist."""
    global _NET  # pylint: disable=global-statement
    if _NET is None and os.path.exists(WEIGHTS):
        _NET = load(WEIGHTS)
    return _NET


def prepare(img):
    """A crop (H x W grey, or H x W x 3) as the reader's input: H tall,
    float32, ink 1 and paper 0. None when the crop holds no ink."""
    a = np.asarray(img)
    if a.ndim == 3:
        a = a[..., :3].astype(np.float32) @ np.array(
            [0.299, 0.587, 0.114], np.float32
        )
    a = a.astype(np.float32)
    if a.size == 0:
        return None
    # Paper at the 90th percentile and ink at the 0.5th: a long row is
    # mostly paper, and its ink can be under 2% of the crop.
    lo, hi = np.percentile(a, 0.5), np.percentile(a, 90)
    if hi - lo < 1.0:
        return None
    ink = np.clip((hi - a) / (hi - lo), 0.0, 1.0)
    rows = np.where(ink.max(axis=1) > 0.5)[0]
    cols = np.where(ink.max(axis=0) > 0.5)[0]
    if len(rows) == 0 or len(cols) == 0:
        return None
    pad = max(2, int(0.08 * (rows[-1] - rows[0] + 1)))
    y0, y1 = max(0, rows[0] - pad), min(ink.shape[0], rows[-1] + pad + 1)
    x0, x1 = max(0, cols[0] - pad), min(ink.shape[1], cols[-1] + pad + 1)
    ink = ink[y0:y1, x0:x1]
    h, w = ink.shape
    new_w = int(round(w * H / float(h)))
    new_w = int(min(MAX_W, max(MIN_W, new_w)))
    im = Image.fromarray(np.round(ink * 255.0).astype(np.uint8))
    im = im.resize((new_w, H), Image.Resampling.BILINEAR)
    return np.asarray(im, dtype=np.float32) / np.float32(255.0)


def _conv(x, w, b, pad):
    """x (C, H, W), w (O, C, kh, kw): same-type 2-D convolution."""
    ph, pw = pad
    o, c, kh, kw = w.shape
    xp = np.pad(x, ((0, 0), (ph, ph), (pw, pw)))
    win = np.lib.stride_tricks.sliding_window_view(xp, (kh, kw), axis=(1, 2))
    oh, ow = win.shape[1], win.shape[2]
    cols = win.transpose(0, 3, 4, 1, 2).reshape(c * kh * kw, oh * ow)
    out = w.reshape(o, -1) @ cols + b[:, None]
    return out.reshape(o, oh, ow)


def _pool(x, ph, pw):
    c, h, w = x.shape
    h2, w2 = h // ph, w // pw
    x = x[:, : h2 * ph, : w2 * pw]
    return x.reshape(c, h2, ph, w2, pw).max(axis=(2, 4))


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def _lstm(x, w_ih, w_hh, b, reverse):
    """One LSTM direction over x (T, D). Gate order: input, forget,
    cell, output (torch's)."""
    t_len = x.shape[0]
    hid = w_hh.shape[1]
    pre = x @ w_ih.T + b
    h = np.zeros(hid, np.float32)
    c = np.zeros(hid, np.float32)
    out = np.zeros((t_len, hid), np.float32)
    steps = range(t_len - 1, -1, -1) if reverse else range(t_len)
    for t in steps:
        g = pre[t] + w_hh @ h
        i = _sigmoid(g[:hid])
        f = _sigmoid(g[hid : 2 * hid])
        cell = np.tanh(g[2 * hid : 3 * hid])
        o = _sigmoid(g[3 * hid :])
        c = f * c + i * cell
        h = o * np.tanh(c)
        out[t] = h
    return out


def forward(model, x):
    """Per-column scores (T, len(charset) + 1) for a prepared crop;
    index 0 is the blank."""
    a = x[None].astype(np.float32)
    seq = None
    for layer in model["layers"]:
        kind = layer["type"]
        if kind == "conv":
            a = np.maximum(_conv(a, layer["w"], layer["b"], layer["pad"]), 0)
            if layer["pool"]:
                a = _pool(a, *layer["pool"])
        elif kind == "bilstm":
            if seq is None:
                seq = a.mean(axis=1).T  # (T, C); height is 1 here
            fw, bw = layer["dirs"]
            seq = np.concatenate(
                [
                    _lstm(seq, fw["w_ih"], fw["w_hh"], fw["b"], False),
                    _lstm(seq, bw["w_ih"], bw["w_hh"], bw["b"], True),
                ],
                axis=1,
            )
        else:
            seq = seq @ layer["w"].T + layer["b"]
    return seq


def decode(model, scores):
    """Best-path text and its confidence: the mean, over the characters
    kept, of each one's probability in its column."""
    z = scores - scores.max(axis=1, keepdims=True)
    p = np.exp(z)
    p /= p.sum(axis=1, keepdims=True)
    best = p.argmax(axis=1)
    chars, probs, prev = [], [], 0
    for t, k in enumerate(best):
        if k not in (0, prev):
            chars.append(model["charset"][k - 1])
            probs.append(float(p[t, k]))
        prev = k
    text = "".join(chars)
    return text, (float(np.mean(probs)) if probs else 0.0)


def read(model, crop):
    """{"text", "score"} for one crop of ink, or None when it holds none."""
    x = prepare(crop)
    if x is None:
        return None
    text, score = decode(model, forward(model, x))
    return {"text": text, "score": round(score, 4)}
