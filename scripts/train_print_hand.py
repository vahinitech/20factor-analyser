# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Train the print-or-handwriting line reader (backend/reading/print_hand.py).

Reads the lines scripts/print_hand_data.py wrote, trains on 64-pixel
windows of the training lines, keeps the epoch that does best on a
validation slice of those lines, and exports 8-bit weights to
backend/models/print_hand.json. The exported weights are then scored
with print_hand.py itself, the code the analyser runs, on:

- synthetic test lines: the 20 UJI test writers and four fonts that
  never trained;
- real lines: every labelled line the OCR found on the committed sample
  pages, none of which trained.

Needs torch (CPU is enough: about 19,000 weights).

    python scripts/train_print_hand.py lines.npz --out results.json
"""

import argparse
import base64
import json
import os
import sys

import numpy as np
import torch
from torch import nn

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from reading import (
    print_hand,
)  # noqa: E402  pylint: disable=wrong-import-position


def model():
    return nn.Sequential(
        nn.Conv2d(1, 16, 3, padding=1),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Conv2d(16, 32, 3, padding=1),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Conv2d(32, 48, 3, padding=1),
        nn.ReLU(),
        nn.MaxPool2d(2),
        nn.AdaptiveAvgPool2d(1),
        nn.Flatten(),
        nn.Linear(48, 1),
    )


def sample_windows(x, widths, y, rng, per_line):
    """Random 64-pixel windows with ink from each line."""
    xs, ys = [], []
    for i in range(len(x)):
        w = int(widths[i])
        line = x[i, :, :w].astype(np.float32) / 255.0
        if w < print_hand.WIN:
            line = np.pad(line, ((0, 0), (0, print_hand.WIN - w)))
            w = print_hand.WIN
        for _ in range(per_line):
            s = int(rng.integers(0, w - print_hand.WIN + 1))
            win = line[:, s : s + print_hand.WIN]
            if win.mean() >= print_hand.MIN_INK:
                xs.append(win)
                ys.append(y[i])
    return np.stack(xs)[:, None], np.array(ys, np.float32)


def line_probs(net_np, x, widths):
    """print_hand.py's own line probability for each stored line."""
    out = []
    for i in range(len(x)):
        line = x[i, :, : int(widths[i])].astype(np.float32) / 255.0
        wins = print_hand.windows(line)
        if wins is None:
            out.append(None)
            continue
        score = float(np.mean(print_hand.window_scores(net_np, wins)))
        out.append(1.0 / (1.0 + np.exp(-score)))
    return out


def quantize(net):
    layers = []
    mods = [m for m in net if isinstance(m, (nn.Conv2d, nn.Linear))]
    for m in mods:
        entry = {"type": "conv" if isinstance(m, nn.Conv2d) else "dense"}
        for key, t in (("w", m.weight), ("b", m.bias)):
            a = t.detach().numpy().astype(np.float32)
            scale = float(np.abs(a).max() / 127.0) or 1.0
            q = np.clip(np.round(a / scale), -127, 127).astype(np.int8)
            entry[key] = {
                "shape": list(a.shape),
                "scale": scale,
                "data": base64.b64encode(q.tobytes()).decode("ascii"),
            }
        layers.append(entry)
    return layers


def accuracy(probs, y):
    pairs = [(p, t) for p, t in zip(probs, y) if p is not None]
    if not pairs:
        return None, 0
    right = sum((p >= 0.5) == bool(t) for p, t in pairs)
    return round(100.0 * right / len(pairs), 2), len(pairs)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("data")
    ap.add_argument("--out", required=True, help="results JSON")
    ap.add_argument("--weights", default=print_hand.WEIGHTS)
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    torch.manual_seed(args.seed)
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    rng = np.random.default_rng(args.seed)
    d = np.load(args.data)
    x, w, y = d["train_x"], d["train_w"], d["train_y"]
    order = rng.permutation(len(x))
    n_val = len(x) // 8
    val, train = order[:n_val], order[n_val:]

    net = model()
    opt = torch.optim.Adam(net.parameters(), lr=2e-3)
    loss_fn = nn.BCEWithLogitsLoss()
    best, best_state, history = -1.0, None, []
    for epoch in range(args.epochs):
        net.train()
        wx, wy = sample_windows(x[train], w[train], y[train], rng, 4)
        perm = rng.permutation(len(wx))
        total = 0.0
        for i in range(0, len(perm), 128):
            idx = perm[i : i + 128]
            xb = torch.from_numpy(wx[idx])
            # Brightness and contrast vary between photos.
            xb = xb * (0.7 + 0.6 * torch.rand(len(idx), 1, 1, 1))
            xb = xb.clamp(0, 1)
            opt.zero_grad()
            loss = loss_fn(net(xb)[:, 0], torch.from_numpy(wy[idx]))
            loss.backward()
            opt.step()
            total += float(loss) * len(idx)
        net_np = print_hand.load_layers(quantize(net))
        val_acc, _ = accuracy(line_probs(net_np, x[val], w[val]), y[val])
        history.append(
            {
                "epoch": epoch + 1,
                "loss": round(total / len(perm), 4),
                "val_line_accuracy": val_acc,
            }
        )
        print(history[-1], flush=True)
        if val_acc > best:
            best, best_state = val_acc, quantize(net)

    spec = {
        "source": (
            "Trained by scripts/train_print_hand.py on handwriting from UJI "
            "Pen Characters v2 (Prat, Castro, Llorens, Marzal and Vilar, "
            "2008), CC BY 4.0, doi:10.24432/C5FG8S, and print from "
            "open-licence fonts in google/fonts at "
            "66928797f271fed5ee428544e7229685e2d90127."
        ),
        "input": {
            "height": print_hand.H,
            "window": print_hand.WIN,
            "step": print_hand.STEP,
        },
        "layers": best_state,
    }
    with open(args.weights, "w", encoding="utf-8") as f:
        json.dump(spec, f, separators=(",", ":"))
        f.write("\n")

    net_np = print_hand.load(args.weights)
    results = {
        "seed": args.seed,
        "history": history,
        "best_val_line_accuracy": best,
    }
    probs = line_probs(net_np, d["test_x"], d["test_w"])
    results["synthetic_test"] = accuracy(probs, d["test_y"])
    if "real_x" in d:
        probs = line_probs(net_np, d["real_x"], d["real_w"])
        results["real"] = accuracy(probs, d["real_y"])
        pages = {}
        rows = []
        for p, t, page, text in zip(
            probs, d["real_y"], d["real_page"], d["real_text"]
        ):
            pages.setdefault(str(page), []).append((p, t))
            rows.append(
                {
                    "page": str(page),
                    "text": str(text),
                    "label": "print" if t else "hand",
                    "p_print": None if p is None else round(p, 3),
                }
            )
        results["real_by_page"] = {
            k: accuracy([a for a, _ in v], [b for _, b in v])
            for k, v in pages.items()
        }
        results["real_lines"] = rows
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1)
    print(
        json.dumps(
            {
                k: v
                for k, v in results.items()
                if k not in ("history", "real_lines")
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
