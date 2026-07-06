#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies. Server-side handwriting/print recognition.
# Third-party: PaddleOCR (Apache-2.0). See /THIRD-PARTY-NOTICES.md and backend/README.md
#
# benchmark_ocr.py — measure REAL engine speed and yield on THIS machine
# against the repo's own sample fixtures, and print a Markdown table you
# can paste into a README. No numbers here are invented: every row is a
# real timed run of the SAME production code paths the server calls
# (recognizer.collect_lines_paddle / recognizer.backend_recognize), never a
# reimplementation that could drift from what actually ships.
#
# Whichever engines aren't installed on this machine are skipped with a
# note, not an error — same convention as warmup_models.py.
#
# Usage:
#   python backend/benchmark_ocr.py
#   python backend/benchmark_ocr.py --samples path/to/dir --format md
#
# What "detection" vs "recognition" means below: PaddleOCR's high-level API
# does detection + recognition in one call — there is no separate
# detect-only fast path to time in isolation. So "detection (s)" is the
# real cost of ONE standalone paddle.detect() call (the shared detector
# every recogniser-only engine, trocr/surya, also depends on), and
# "recognition (s)" for trocr/surya is the remainder after subtracting
# that shared detection cost from their own end-to-end time — an estimate,
# clearly labelled as such, not a true isolated measurement. "Total (s)"
# is always the real, directly measured, end-to-end wall time.
import argparse
import os
import platform
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import gpu_detect  # noqa: E402
import ocr_backends  # noqa: E402
import recognizer  # noqa: E402

_IMAGE_EXTS = (".png", ".jpg", ".jpeg")


def _default_samples_dir():
    d = os.path.join(REPO_ROOT, "tests", "fixtures", "samples")
    return (
        d if os.path.isdir(d) else os.path.join(REPO_ROOT, "tests", "fixtures")
    )


def _find_image_paths(samples_dir):
    """Every image file under samples_dir, walked recursively -- the same
    files a `find DIR -type f \\( -iname "*.png" -o -iname "*.jpg" -o
    -iname "*.jpeg" \\)` would list. A single source of truth for both the
    raw "found" count and the images actually loaded below, so the two
    numbers in the report can never drift apart."""
    paths = []
    for root, _dirs, files in os.walk(samples_dir):
        for fn in files:
            if os.path.splitext(fn)[1].lower() in _IMAGE_EXTS:
                paths.append(os.path.join(root, fn))
    return sorted(paths)


def _system_info():
    """Real, measured host facts (never guessed) for the report header:
    OS/CPU architecture, logical CPU count, and NVIDIA GPU count (0 if
    there is none or nvidia-smi isn't installed -- CPU-only is the normal
    case for this project)."""
    return {
        "os": platform.system(),
        "arch": platform.machine(),
        "cpu_count": os.cpu_count() or 0,
        "gpu_count": gpu_detect.gpu_count(),
    }


def _load_images(samples_dir, limit):
    paths = _find_image_paths(samples_dir)
    paths = paths[:limit] if limit else paths
    out = []
    for p in paths:
        try:
            out.append(
                (os.path.basename(p), np.array(Image.open(p).convert("RGB")))
            )
        except Exception as e:
            print(f"[benchmark] skipping {p}: {e}")
    return out


def _init(lang):
    recognizer.configure(
        ocr_langs=[lang] if lang != "auto" else ["en", "te"],
        ocr_backend="paddle",
        max_variants=1,  # keep the benchmark to the base pass, no retries
        adv_preproc=False,
        auto_min_lines=3,
        variant_min_lines=3,
        refine_min_sim=0.70,
        refine_min_conf=0.75,
    )
    ocr_backends.init_registry(resolve_langs=recognizer.resolve_langs)


def _mean_conf(lines):
    scores = [float(l.get("score", 0.0) or 0.0) for l in lines]
    return sum(scores) / len(scores) if scores else 0.0


def bench_paddle_detect_only(images):
    """One standalone paddle.detect() call per image — the shared
    detection cost every recogniser-only engine (trocr/surya) also pays,
    used below to estimate their incremental recognition-only cost."""
    paddle = ocr_backends.get_backend("paddle")
    rows = []
    for name, arr in images:
        t0 = time.perf_counter()
        polys = paddle.detect(arr)
        ms = (time.perf_counter() - t0) * 1000.0
        rows.append(
            {
                "engine": "paddle (detection only)",
                "sample": name,
                "lines": len(polys),
                "detect_ms": round(ms, 1),
                "recognize_ms": None,
                "total_ms": round(ms, 1),
                "mean_conf": None,
            }
        )
    return rows


def bench_paddle(images, lang="en"):
    rows = []
    for name, arr in images:
        t0 = time.perf_counter()
        lines, err = recognizer.collect_lines_paddle(arr, lang)
        ms = (time.perf_counter() - t0) * 1000.0
        rows.append(
            {
                "engine": "paddle (PP-OCRv5, detect+recognize)",
                "sample": name,
                "lines": len(lines),
                "detect_ms": None,
                "recognize_ms": None,
                "total_ms": round(ms, 1),
                "mean_conf": round(_mean_conf(lines), 3),
                "error": err or None,
            }
        )
    return rows


def bench_backend(name, images, lang, detect_ms_by_sample):
    be = ocr_backends.get_backend(name)
    if be is None:
        print(f"[benchmark] {name}: not registered, skipping")
        return []
    ok, reason = be.available()
    if not ok:
        print(f"[benchmark] {name}: skipped ({reason})")
        return []
    rows = []
    for sample_name, arr in images:
        t0 = time.perf_counter()
        lines, err = recognizer.backend_recognize(name, arr, lang)
        ms = (time.perf_counter() - t0) * 1000.0
        det_ms = detect_ms_by_sample.get(sample_name)
        # Estimate only: total end-to-end minus the shared detection cost
        # measured separately above. Never negative; None if we have no
        # detection baseline for this sample.
        rec_ms = max(0.0, ms - det_ms) if det_ms is not None else None
        rows.append(
            {
                "engine": name,
                "sample": sample_name,
                "lines": len(lines),
                "detect_ms": det_ms,
                "recognize_ms": (
                    round(rec_ms, 1) if rec_ms is not None else None
                ),
                "total_ms": round(ms, 1),
                "mean_conf": round(_mean_conf(lines), 3),
                "error": err or None,
            }
        )
    return rows


def _fmt_seconds(ms):
    """Human-readable duration for the report: seconds to 2dp, or
    "<minutes>m <seconds>s" once a single call runs a minute or longer
    (paddle detection on a dense page can take well over 60s on a slow
    CPU -- see the benchmark output this replaces)."""
    if ms is None:
        return "—"
    secs = ms / 1000.0
    if secs < 60:
        return f"{secs:.2f}s"
    minutes, rem = divmod(secs, 60)
    return f"{int(minutes)}m {rem:.2f}s"


def to_markdown(rows, info=None, image_count=None):
    parts = []
    if info is not None or image_count is not None:
        meta = []
        if info is not None:
            meta.append(
                f"- System: {info['os']} {info['arch']}, "
                f"{info['cpu_count']} CPU(s), {info['gpu_count']} GPU(s)"
            )
            if info["gpu_count"] == 0:
                meta.append(f"- Note: {gpu_detect.gpu_zero_caveat()}")
        if image_count is not None:
            meta.append(f"- Sample images found: {image_count}")
        parts.append("\n".join(meta))
        parts.append("")

    headers = [
        "Engine",
        "Sample",
        "Lines analysed",
        "Detection (s)",
        "Recognition (s)",
        "Total (s)",
        "Mean confidence",
    ]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        det = _fmt_seconds(r["detect_ms"])
        rec = _fmt_seconds(r["recognize_ms"])
        total = _fmt_seconds(r["total_ms"])
        conf = r["mean_conf"] if r["mean_conf"] is not None else "—"
        lines.append(
            f"| {r['engine']} | {r['sample']} | {r['lines']} | {det} | "
            f"{rec} | {total} | {conf} |"
        )
    parts.append("\n".join(lines))
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--samples", default=_default_samples_dir())
    ap.add_argument("--lang", default="en")
    ap.add_argument("--limit", type=int, default=0, help="0 = all images")
    args = ap.parse_args()

    info = _system_info()
    print(
        f"[benchmark] System: {info['os']} {info['arch']}, "
        f"{info['cpu_count']} CPU(s), {info['gpu_count']} GPU(s)"
    )
    if info["gpu_count"] == 0:
        print(f"[benchmark] Note: {gpu_detect.gpu_zero_caveat()}")

    found = len(_find_image_paths(args.samples))
    print(
        f"[benchmark] {found} image file(s) found under {args.samples} "
        '(same as: find DIR -type f \\( -iname "*.png" -o -iname "*.jpg" '
        '-o -iname "*.jpeg" \\) | wc -l)'
    )

    images = _load_images(args.samples, args.limit)
    if not images:
        print(f"[benchmark] no images found under {args.samples}")
        return
    print(f"[benchmark] {len(images)} sample(s) loaded for benchmarking")

    _init(args.lang)

    all_rows = []
    detect_rows = bench_paddle_detect_only(images)
    all_rows.extend(detect_rows)
    detect_ms_by_sample = {r["sample"]: r["detect_ms"] for r in detect_rows}

    all_rows.extend(bench_paddle(images, args.lang))
    for name in ("trocr", "surya", "paddleocr-vl"):
        all_rows.extend(
            bench_backend(name, images, args.lang, detect_ms_by_sample)
        )

    print()
    print(to_markdown(all_rows, info=info, image_count=found))
    print()
    print(
        "[benchmark] Recognition (s) for trocr/surya is an ESTIMATE: total "
        "measured time minus the shared paddle detection cost measured "
        "separately above, not a true isolated measurement (PaddleOCR's API "
        "doesn't expose detection and recognition as separately callable "
        "steps)."
    )


if __name__ == "__main__":
    main()
