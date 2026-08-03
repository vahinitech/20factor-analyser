# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# generate_examples.py — produces the JSON behind docs/example-report.md
# and docs/case-studies.md by running the REAL scorer
# (backend/scoring.py build_analysis) on synthetic page geometry.
#
# Why synthetic: the repo policy (CONTRIBUTING.md) forbids committing real
# handwriting with personal data, and the repo policy (CLAUDE.md) forbids
# inventing scores in docs. This script squares both: no real child's page,
# yet every number in the example docs is actual scorer output anyone can
# regenerate:
#
#     pip install -r backend/requirements-core.txt
#     python docs/examples/generate_examples.py
#
# Each scenario builds the `lines`/`layout` shapes the recognizer hands to
# build_analysis — one detected line per written row (the shape the factor
# targets assume: Margin Discipline's basis is "N lines"), splitting a row
# into segments only where a gap is wide enough that a detector would
# split it — plus a synthetic ink image with real three-zone structure
# (dense x-height band, sparser ascender/descender strokes) so
# zone_analysis measures reach instead of falling back to the proxy.
# Deterministic: fixed per-scenario seed, same JSON every run.

import json
import math
import os
import sys
import zlib

import numpy as np

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"
    ),
)

from scoring import build_analysis  # noqa: E402  (path set up above)

# Tall enough that rows sit ~2.5 box-heights apart: zone_analysis pads
# each line crop by half its box height, so tighter packing would let a
# crop catch the neighbouring row's ink and misread the zone reach.
W, H = 1100, 2800
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Practice sentences, one per written row. Ordinary classroom copy work:
# a mix of loop letters (a o d e g), ascenders/descenders and short words.
ROWS_TEXT = [
    "the quick brown fox jumps over the lazy dog",
    "a good pen and a steady hand make tidy pages",
    "every big letter stands tall and tails hang low",
    "keep one finger of space between all your words",
    "round letters close their loops before moving on",
    "practice a little every day and progress follows",
    "the lines of a good page stay level to the edge",
    "write slowly first and let the speed come later",
    "equal gaps and equal heights make reading easy",
    "a page begins with a straight and even margin",
]


def _draw_zoned_ink(arr, x, y_top, w, upper, x_h, lower, amp):
    """Ink with the three-zone structure zone_analysis.py measures: a
    dense x-height band (~60% column coverage, the projection-profile
    peak), sparser full-height strokes for ascenders (~15%) and
    descenders (~12%) — between INK_FRAC and DENSE_FRAC of the peak, so
    the dense-band search finds the middle zone and the ink extents land
    exactly at the configured reaches."""
    x0, x1 = int(x), min(W, int(x + w))
    if x1 <= x0:
        return
    cols = np.arange(x0, x1)
    mid_cols = (cols % 5) < 3
    asc_cols = (cols % 13) < 2
    desc_cols = (cols % 17) < 2

    def paint(y_a, y_b, col_mask):
        ya, yb = int(max(0, y_a)), int(min(H, y_b))
        if yb <= ya or not col_mask.any():
            return
        yy = np.arange(ya, yb)
        ink = 245.0 - amp * (
            1.0 + 0.12 * np.sin(yy[:, None] * 0.6 + cols[None, :] * 0.13)
        )
        region = arr[ya:yb, x0:x1, :]
        sel = np.broadcast_to(col_mask[None, :], (yb - ya, x1 - x0))
        region[sel] = np.clip(ink, 0, 255)[sel][:, None]

    midline = y_top + upper
    baseline = midline + x_h
    paint(midline, baseline, mid_cols)
    paint(y_top, midline, asc_cols)
    paint(baseline, y_top + upper + x_h + lower, desc_cols)


def make_page(
    rng,
    conf_mean=0.88,
    conf_jitter=0.02,
    xh_base=34.0,
    xh_jitter=0.06,
    asc_reach=2.0,
    desc_reach=2.0,
    reach_jitter=0.06,
    slope_base_deg=0.0,
    slope_jitter_deg=0.4,
    left_base=90.0,
    left_jitter=4.0,
    char_w_base=15.0,
    char_w_jitter=0.06,
    segments_per_row=1,
    seg_gap_base=45.0,
    seg_gap_jitter=0.15,
    ink_amp_base=62.0,
    ink_amp_jitter=0.10,
):
    """Build (image, lines, layout) for one synthetic page.

    Every *_jitter parameter is the knob a scenario turns to portray a
    fault: slope_base_deg portrays a sinking baseline, left_jitter a
    ragged margin, asc/desc_reach the three-zone letter-size habit,
    segments_per_row + seg_gap_jitter erratic word gaps wide enough to
    split detection. The scorer sees only the resulting geometry,
    exactly as it would from a real OCR pass.
    """
    arr = np.full((H, W, 3), 245, dtype=np.uint8)
    lines = []
    y = 140.0
    for text in ROWS_TEXT:
        slope = math.radians(
            slope_base_deg + rng.normal(0.0, slope_jitter_deg)
        )
        x_h = xh_base * (1.0 + rng.normal(0.0, xh_jitter))
        upper = max(
            0.0, (asc_reach + rng.normal(0.0, reach_jitter) - 1.0) * x_h
        )
        lower = max(
            0.0, (desc_reach + rng.normal(0.0, reach_jitter) - 1.0) * x_h
        )
        bh = upper + x_h + lower
        char_w = char_w_base * (1.0 + rng.normal(0.0, char_w_jitter))
        x = left_base + rng.normal(0.0, left_jitter)
        row_x0 = x

        words = text.split()
        n_seg = max(1, min(int(segments_per_row), len(words)))
        bounds = [round(i * len(words) / n_seg) for i in range(n_seg + 1)]
        segments = [
            " ".join(words[bounds[i] : bounds[i + 1]])
            for i in range(n_seg)
            if bounds[i + 1] > bounds[i]
        ]
        for seg in segments:
            w = max(10.0, char_w * len(seg))
            sy = y + (x - row_x0) * math.tan(slope)
            poly = [
                [x, sy],
                [x + w, sy + w * math.tan(slope)],
                [x + w, sy + bh + w * math.tan(slope)],
                [x, sy + bh],
            ]
            lines.append(
                {
                    "box": [x, sy, w, bh],
                    "poly": poly,
                    "score": float(
                        np.clip(rng.normal(conf_mean, conf_jitter), 0.5, 0.99)
                    ),
                    "text": seg,
                }
            )
            amp = ink_amp_base * (1.0 + rng.normal(0.0, ink_amp_jitter))
            _draw_zoned_ink(arr, x, sy, w, upper, x_h, lower, amp)
            x += w + max(
                4.0,
                seg_gap_base * (1.0 + rng.normal(0.0, seg_gap_jitter)),
            )
        y += 250.0
    return arr, lines, {"layout_complexity": 0.0}


# One entry per generated JSON file. `params` portrays the writer;
# docs/case-studies.md tells the story around the resulting numbers.
SCENARIOS = {
    # The worked example for docs/example-report.md: a competent but
    # uneven hand — the baseline sinks, letter heights wander, and
    # ascenders stop short of the 1:2 reach.
    "example-report": dict(
        conf_mean=0.84,
        xh_jitter=0.15,
        asc_reach=1.32,
        desc_reach=2.50,
        reach_jitter=0.10,
        slope_base_deg=2.2,
        slope_jitter_deg=1.2,
        left_jitter=8.0,
        char_w_jitter=0.12,
        ink_amp_jitter=0.16,
    ),
    # Case study 1, before: lines sink hard and wander; slant unstable.
    "case1-baseline-before": dict(
        conf_mean=0.82,
        xh_jitter=0.13,
        slope_base_deg=3.6,
        slope_jitter_deg=2.6,
        left_jitter=9.0,
        char_w_jitter=0.12,
        ink_amp_jitter=0.16,
    ),
    # Case study 1, after ruled-sheet practice: slope and its spread cut
    # to roughly a quarter; everything else deliberately left similar.
    "case1-baseline-after": dict(
        conf_mean=0.85,
        xh_jitter=0.11,
        slope_base_deg=0.9,
        slope_jitter_deg=0.6,
        left_jitter=6.0,
        char_w_jitter=0.11,
        ink_amp_jitter=0.15,
    ),
    # Case study 2, before: word gaps so erratic that detection splits
    # every row into three ragged segments.
    "case2-spacing-before": dict(
        conf_mean=0.83,
        xh_jitter=0.12,
        slope_base_deg=0.8,
        slope_jitter_deg=0.6,
        segments_per_row=3,
        seg_gap_base=52.0,
        seg_gap_jitter=0.75,
        char_w_jitter=0.32,
        ink_amp_jitter=0.15,
    ),
    # Case study 2, after finger-gap drills: gaps regular enough that
    # rows are detected whole again.
    "case2-spacing-after": dict(
        conf_mean=0.86,
        xh_jitter=0.11,
        slope_base_deg=0.8,
        slope_jitter_deg=0.6,
        char_w_jitter=0.12,
        ink_amp_jitter=0.14,
    ),
    # Case study 3, before: everything written in one size — ascenders
    # and descenders barely leave the middle zone (the coaches'
    # "single-zone" mistake) — with a wandering left margin and heavy,
    # uneven pressure.
    "case3-size-margin-before": dict(
        conf_mean=0.84,
        xh_jitter=0.24,
        asc_reach=1.30,
        desc_reach=1.25,
        reach_jitter=0.16,
        slope_base_deg=0.9,
        slope_jitter_deg=0.8,
        left_base=75.0,
        left_jitter=28.0,
        char_w_jitter=0.15,
        ink_amp_base=80.0,
        ink_amp_jitter=0.40,
    ),
    # Case study 3, after tall–short pattern and margin-box drills.
    "case3-size-margin-after": dict(
        conf_mean=0.87,
        xh_jitter=0.11,
        asc_reach=1.85,
        desc_reach=2.10,
        reach_jitter=0.08,
        slope_base_deg=0.8,
        slope_jitter_deg=0.6,
        left_base=88.0,
        left_jitter=6.0,
        char_w_jitter=0.11,
        ink_amp_base=66.0,
        ink_amp_jitter=0.14,
    ),
}


def main():
    for name, params in SCENARIOS.items():
        # Per-scenario fixed seed (crc32, not hash(): str hash is
        # randomized per process): regenerating one file never shifts
        # the numbers in another.
        rng = np.random.default_rng(zlib.crc32(name.encode("utf-8")))
        arr, lines, layout = make_page(rng, **params)
        result = build_analysis(arr, lines, layout).to_dict()
        path = os.path.join(OUT_DIR, f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            f.write("\n")
        weak = ", ".join(
            f"#{r['n']} {r['name']} {r['score']}" for r in result["topWeak"]
        )
        print(f"{name}: overall {result['overall']}  weakest: {weak}")


if __name__ == "__main__":
    main()
