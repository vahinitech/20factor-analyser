# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Train the handwritten Telugu reader (backend/reading/telugu_reader.py).

Data: IIIT-INDIC-HW-WORDS-Telugu (CVIT, IIIT Hyderabad; Gongidi and
Jawahar, ICDAR 2021; CC BY 4.0, https://ilocr.iiit.ac.in/dataset/23).
Each split is its zip as downloaded, or the folder it unpacks to; images
are read straight from the zip, never unpacked to disk. The training
split trains; the validation split picks the epoch; the test split is
read once at the end, by the exported weights through
backend/reading/telugu_reader.py, the code the analyser runs.

Half the training samples are words, half are lines of two to four words
joined with a space, so the reader reads a whole row. Each sample is
made to look more like a phone photo of a page: a small turn and slant,
thinner or thicker strokes, blur, uneven light and noise.

Where it runs (scripts/train_guard.py): a CUDA GPU, Apple's GPU (MPS),
else the CPU, restricted to half the cores, niced, and stopped before
the machine runs short of memory. A stopped run continues with --resume.

    python scripts/train_telugu_reader.py \\
        --train train.zip --val val.zip --test test.zip \\
        --work runs/te1 --out runs/te1/results.json

Needs torch, numpy, Pillow (psutil if present, for the memory guard).
"""

import argparse
import base64
import importlib.util
import io
import json
import os
import sys
import time
import zipfile

import numpy as np
import torch
from PIL import Image, ImageFilter
from torch import nn

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from reading import (
    telugu_reader as tr,
)  # noqa: E402  pylint: disable=wrong-import-position
import train_guard  # noqa: E402  pylint: disable=wrong-import-position


def _load_graphemes():
    """backend/languages/graphemes.py on its own, by path: the package
    also loads the pack schemas (jsonschema, not installed where training
    runs), and putting its folder on sys.path would hide the standard
    library's profile module behind languages/profile.py."""
    path = os.path.join(ROOT, "backend", "languages", "graphemes.py")
    spec = importlib.util.spec_from_file_location("vahini_graphemes", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


graphemes = _load_graphemes()

CONVS = [  # (in, out, pool)
    (1, 32, (2, 2)),
    (32, 64, (2, 2)),
    (64, 128, None),
    (128, 128, (2, 1)),
    (128, 192, None),
    (192, 192, (2, 1)),
]
FOLD = 256  # channels after the last convolution folds the height
HIDDEN = 128
LINE_SHARE = 0.5
SOURCE = (
    "Trained by scripts/train_telugu_reader.py on IIIT-INDIC-HW-WORDS-"
    "Telugu (Gongidi and Jawahar, ICDAR 2021; CVIT, IIIT Hyderabad), "
    "CC BY 4.0, https://ilocr.iiit.ac.in/dataset/23."
)


# ---------- data ----------


class Split:
    """One split's (image, text) pairs, from its zip or its folder."""

    def __init__(self, path):
        self.path = path
        self.zip = zipfile.ZipFile(path) if path.endswith(".zip") else None
        names = (
            self.zip.namelist()
            if self.zip
            else [
                os.path.relpath(os.path.join(d, f), path)
                for d, _s, fs in os.walk(path)
                for f in fs
            ]
        )
        gt = sorted(n for n in names if n.endswith("_gt.txt"))
        if not gt:
            raise SystemExit(f"{path}: no *_gt.txt label file")
        base = os.path.dirname(gt[0])
        self.items = []
        for line in self._read(gt[0]).decode("utf-8").splitlines():
            if "\t" not in line:
                continue
            rel, text = line.split("\t", 1)
            text = text.strip()
            if text:
                self.items.append((os.path.join(base, rel), text))

    def _read(self, name):
        if self.zip:
            return self.zip.read(name)
        with open(os.path.join(self.path, name), "rb") as f:
            return f.read()

    def image(self, i):
        """Grey uint8 array of item i."""
        with Image.open(io.BytesIO(self._read(self.items[i][0]))) as im:
            return np.asarray(im.convert("L"))


def charset_of(splits):
    chars = sorted({ch for s in splits for _p, t in s.items for ch in t})
    if " " not in chars:
        chars.insert(0, " ")
    return "".join(chars)


def augment(gray, rng):
    """A scan made to look more like a phone photo of a page."""
    im = Image.fromarray(gray)
    h = 2 * tr.H
    im = im.resize(
        (max(8, int(im.width * h / max(1, im.height))), h),
        Image.Resampling.BILINEAR,
    )
    if rng.random() < 0.3:
        im = im.filter(ImageFilter.MinFilter(3))  # thicker ink
    elif rng.random() < 0.2:
        im = im.filter(ImageFilter.MaxFilter(3))  # thinner ink
    shear = rng.uniform(-0.25, 0.25)
    im = im.transform(
        im.size,
        Image.Transform.AFFINE,
        (1, shear, -shear * h / 2, 0, 1, 0),
        Image.Resampling.BILINEAR,
        fillcolor=255,
    )
    im = im.rotate(
        rng.uniform(-2.5, 2.5),
        Image.Resampling.BILINEAR,
        expand=True,
        fillcolor=255,
    )
    if rng.random() < 0.5:
        im = im.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.2)))
    a = np.asarray(im, np.float32)
    paper = rng.uniform(170, 255)
    ink = rng.uniform(0, 90)
    a = ink + (paper - ink) * (a / 255.0)
    yy = np.linspace(0, 1, a.shape[0])[:, None]
    xx = np.linspace(0, 1, a.shape[1])[None, :]
    a = a * (1 - 0.15 * rng.random() * (yy + xx) / 2)
    a = a + rng.normal(0, rng.uniform(0, 8), a.shape)
    return np.clip(a, 0, 255).astype(np.uint8)


def sample(split, idx, rng, train):
    """One input (H x W float32) and its text: a word, or for training,
    sometimes a line of words."""
    n = 1
    if train and rng.random() < LINE_SHARE:
        n = int(rng.integers(2, 5))
    parts, texts, width = [], [], 0
    for k in range(n):
        i = idx if k == 0 else int(rng.integers(len(split.items)))
        gray = split.image(i)
        x = tr.prepare(augment(gray, rng) if train else gray)
        if x is None:
            continue
        gap = int(rng.uniform(0.4, 1.0) * tr.H) if parts else 0
        if width + gap + x.shape[1] > tr.MAX_W:
            break
        if gap:
            parts.append(np.zeros((tr.H, gap), np.float32))
        parts.append(x)
        texts.append(split.items[i][1])
        width += gap + x.shape[1]
    if not parts:
        return None, None
    return np.concatenate(parts, axis=1), " ".join(texts)


def batch(samples, charset):
    index = {ch: k + 1 for k, ch in enumerate(charset)}
    width = max(x.shape[1] for x, _t in samples)
    xb = np.zeros((len(samples), 1, tr.H, width), np.float32)
    targets, t_lens, in_lens = [], [], []
    for j, (x, t) in enumerate(samples):
        xb[j, 0, :, : x.shape[1]] = x
        codes = [index[ch] for ch in t if ch in index]
        targets.extend(codes)
        t_lens.append(len(codes))
        in_lens.append(x.shape[1] // tr.STRIDE)
    return (
        torch.from_numpy(xb),
        torch.tensor(targets, dtype=torch.long),
        torch.tensor(in_lens, dtype=torch.long),
        torch.tensor(t_lens, dtype=torch.long),
    )


# ---------- model ----------


class Reader(nn.Module):
    def __init__(self, n_chars):
        super().__init__()
        layers = []
        for c_in, c_out, pool in CONVS:
            layers += [
                nn.Conv2d(c_in, c_out, 3, padding=1, bias=False),
                nn.BatchNorm2d(c_out),
                nn.ReLU(),
            ]
            if pool:
                layers.append(nn.MaxPool2d(pool, pool))
        layers += [nn.Conv2d(CONVS[-1][1], FOLD, (3, 1)), nn.ReLU()]
        self.cnn = nn.Sequential(*layers)
        self.rnn = nn.LSTM(
            FOLD, HIDDEN, num_layers=2, bidirectional=True, dropout=0.2
        )
        self.fc = nn.Linear(2 * HIDDEN, n_chars + 1)

    def forward(self, x):
        f = self.cnn(x).squeeze(2).permute(2, 0, 1)  # (T, B, C)
        out, _ = self.rnn(f)
        return self.fc(out).log_softmax(2)


def _q(a):
    a = np.asarray(a, np.float32)
    scale = float(np.abs(a).max() / 127.0) or 1.0
    q = np.clip(np.round(a / scale), -127, 127).astype(np.int8)
    return {
        "shape": list(a.shape),
        "scale": scale,
        "data": base64.b64encode(q.tobytes()).decode("ascii"),
    }


def export(net, charset):
    """The spec backend/reading/telugu_reader.py loads: batch normalisation
    folded into each convolution, every tensor 8-bit."""
    mods = list(net.cnn)
    layers = []
    i = 0
    while i < len(mods):
        m = mods[i]
        if isinstance(m, nn.Conv2d) and i + 1 < len(mods):
            if isinstance(mods[i + 1], nn.BatchNorm2d):
                bn = mods[i + 1]
                s = (bn.weight / torch.sqrt(bn.running_var + bn.eps)).detach()
                w = m.weight.detach() * s[:, None, None, None]
                b = bn.bias.detach() - bn.running_mean * s
                pool = mods[i + 3] if i + 3 < len(mods) else None
                pool = (
                    list(pool.kernel_size)
                    if isinstance(pool, nn.MaxPool2d)
                    else None
                )
                layers.append(
                    {
                        "type": "conv",
                        "w": _q(w.numpy()),
                        "b": _q(b.detach().numpy()),
                        "pad": [1, 1],
                        "pool": pool,
                    }
                )
            else:
                layers.append(
                    {
                        "type": "conv",
                        "w": _q(m.weight.detach().numpy()),
                        "b": _q(m.bias.detach().numpy()),
                        "pad": [0, 0],
                        "pool": None,
                    }
                )
        i += 1
    sd = {k: v.detach().cpu().numpy() for k, v in net.rnn.state_dict().items()}
    for k in range(net.rnn.num_layers):
        dirs = []
        for suffix in ("", "_reverse"):
            dirs.append(
                {
                    "w_ih": _q(sd[f"weight_ih_l{k}{suffix}"]),
                    "w_hh": _q(sd[f"weight_hh_l{k}{suffix}"]),
                    "b": _q(
                        sd[f"bias_ih_l{k}{suffix}"]
                        + sd[f"bias_hh_l{k}{suffix}"]
                    ),
                }
            )
        layers.append({"type": "bilstm", "fw": dirs[0], "bw": dirs[1]})
    layers.append(
        {
            "type": "dense",
            "w": _q(net.fc.weight.detach().cpu().numpy()),
            "b": _q(net.fc.bias.detach().cpu().numpy()),
        }
    )
    return {
        "source": SOURCE,
        "input": {"height": tr.H, "max_width": tr.MAX_W},
        "charset": charset,
        "layers": layers,
    }


# ---------- scoring ----------


def _edits(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(
                min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y))
            )
        prev = cur
    return prev[-1]


def score(model_np, split, limit, seed):
    """Character error rate in graphemes, and words read exactly, of the
    exported weights through backend/reading/telugu_reader.py."""
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(split.items))[: limit or None]
    edits = units = exact = n = 0
    for i in idx:
        got = tr.read(model_np, split.image(int(i)))
        want = split.items[int(i)][1]
        text = got["text"] if got else ""
        g_want = graphemes.split(want)
        edits += _edits(graphemes.split(text), g_want)
        units += len(g_want)
        exact += text == want
        n += 1
    return {
        "words": n,
        "cer": round(100.0 * edits / max(1, units), 2),
        "word_accuracy": round(100.0 * exact / max(1, n), 2),
    }


# ---------- training ----------


def _save(path, state):
    tmp = path + ".tmp"
    torch.save(state, tmp)
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--train", required=True)
    ap.add_argument("--val", required=True)
    ap.add_argument("--test")
    ap.add_argument("--work", required=True, help="checkpoint folder")
    ap.add_argument("--out", required=True, help="results JSON")
    ap.add_argument(
        "--weights", default=None, help="default: <work>/telugu_reader.json"
    )
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="training samples per epoch (0: all)",
    )
    ap.add_argument("--val-limit", type=int, default=2000)
    ap.add_argument(
        "--device", default="auto", choices=["auto", "cuda", "mps", "cpu"]
    )
    ap.add_argument(
        "--threads",
        type=int,
        default=0,
        help="CPU threads (default half the cores)",
    )
    ap.add_argument(
        "--floor-mb",
        type=int,
        default=1500,
        help="memory the machine must keep free",
    )
    ap.add_argument(
        "--max-rss-mb",
        type=int,
        default=2000,
        help="this run's memory ceiling",
    )
    ap.add_argument(
        "--max-load",
        type=float,
        default=1.0,
        help="load average per core before waiting",
    )
    ap.add_argument("--pause-s", type=int, default=60)
    ap.add_argument("--max-pauses", type=int, default=30)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args(argv)

    os.makedirs(args.work, exist_ok=True)
    ckpt = os.path.join(args.work, "checkpoint.pt")
    weights = args.weights or os.path.join(args.work, "telugu_reader.json")
    device, note = train_guard.pick_device(args.device, torch)
    if note:
        print(note, flush=True)
    if device == "cpu":
        threads = train_guard.cpu_threads(args.threads, os.cpu_count())
        train_guard.restrict_cpu(torch, threads)
        print(f"cpu: {threads} threads, niced", flush=True)
    torch.manual_seed(args.seed)

    train, val = Split(args.train), Split(args.val)
    charset = charset_of([train, val])
    net = Reader(len(charset)).to(device)
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    ctc = nn.CTCLoss(blank=0, zero_infinity=True)
    state = {"epoch": 0, "step": 0, "best": None, "history": [], "lr": args.lr}
    if args.resume and os.path.exists(ckpt):
        saved = torch.load(ckpt, map_location=device, weights_only=False)
        if saved["charset"] != charset:
            raise SystemExit("checkpoint charset differs from this data")
        net.load_state_dict(saved["model"])
        opt.load_state_dict(saved["opt"])
        state = saved["state"]
        print(
            f"resumed at epoch {state['epoch'] + 1}, step {state['step']}",
            flush=True,
        )

    def save():
        _save(
            ckpt,
            {
                "model": net.state_dict(),
                "opt": opt.state_dict(),
                "state": state,
                "charset": charset,
            },
        )

    guard = train_guard.Guard(
        {
            "floor_mb": args.floor_mb,
            "max_rss_mb": args.max_rss_mb,
            "max_load": args.max_load if device == "cpu" else None,
            "pause_s": args.pause_s,
            "max_pauses": args.max_pauses,
        },
        save,
        log=lambda m: print(m, flush=True),
    )

    while state["epoch"] < args.epochs:
        epoch = state["epoch"]
        rng = np.random.default_rng(args.seed * 1000 + epoch)
        order = rng.permutation(len(train.items))
        if args.limit:
            order = order[: args.limit]
        steps = range(0, len(order), args.batch)
        net.train()
        t0, total, seen = time.time(), 0.0, 0
        for s, start in enumerate(steps):
            if s < state["step"]:
                continue  # done before a resume
            guard.check()
            brng = np.random.default_rng([args.seed, epoch, s])
            samples = [
                sample(train, int(i), brng, True)
                for i in order[start : start + args.batch]
            ]
            samples = [x for x in samples if x[0] is not None]
            if not samples:
                continue
            xb, tg, il, tl = batch(samples, charset)
            out = net(xb.to(device))
            if device == "mps":
                out = out.cpu()  # CTC loss runs on the CPU there
            loss = ctc(out, tg, il, tl)
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 5.0)
            opt.step()
            total += float(loss.detach()) * len(samples)
            seen += len(samples)
            state["step"] = s + 1
            if (s + 1) % 200 == 0:
                print(
                    f"epoch {epoch + 1} step {s + 1}/{len(steps)} "
                    f"loss {total / seen:.3f} {time.time() - t0:.0f}s",
                    flush=True,
                )
                save()
        net.eval()
        spec = export(net.cpu(), charset)
        net.to(device)
        val_score = score(tr.load_spec(spec), val, args.val_limit, args.seed)
        row = {
            "epoch": epoch + 1,
            "loss": round(total / max(1, seen), 4),
            "seconds": round(time.time() - t0),
            "val": val_score,
            "lr": state["lr"],
        }
        state["history"].append(row)
        print(row, flush=True)
        if state["best"] is None or val_score["cer"] < state["best"]["cer"]:
            state["best"] = {**val_score, "epoch": epoch + 1}
            with open(weights, "w", encoding="utf-8") as f:
                json.dump(spec, f, separators=(",", ":"), ensure_ascii=False)
                f.write("\n")
        elif epoch + 1 - state["best"]["epoch"] >= 2:
            state["lr"] = state["lr"] / 2
            for g in opt.param_groups:
                g["lr"] = state["lr"]
        state["epoch"] += 1
        state["step"] = 0
        save()

    results = {
        "seed": args.seed,
        "device": device,
        "charset_size": len(charset),
        "train_words": len(train.items),
        "history": state["history"],
        "best": state["best"],
        "weights": weights,
    }
    if args.test:
        results["test"] = score(
            tr.load(weights), Split(args.test), 0, args.seed
        )
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, ensure_ascii=False)
    print(json.dumps(results.get("test") or results["best"]), flush=True)


if __name__ == "__main__":
    main()
