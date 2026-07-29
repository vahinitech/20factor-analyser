# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# Tests for baseline_track.py (issue #31): the Kalman-RTS baseline
# tracker that replaces the two-vertex polygon slope for drift and
# factor-7 evidence. Synthetic rows with known geometry, so every
# assertion checks the estimator against ground truth: level rows read
# level, drifting rows read their true angle with the right sign,
# descender outliers get down-weighted instead of bending the track,
# and degenerate rows refuse to answer rather than guessing.

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from baseline_track import (  # noqa: E402
    MIN_POINTS,
    track_row_baseline,
    track_rows,
)

ROW_H = 40.0


def _row(slope_deg, n=8, x0=100.0, y0=500.0, step=90.0, noise=None, seed=7):
    """Word baseline points along a straight row of known angle."""
    rng = np.random.default_rng(seed)
    m = math.tan(math.radians(slope_deg))
    pts = []
    for i in range(n):
        x = x0 + i * step
        y = y0 + m * (x - x0)
        if noise:
            y += float(rng.normal(0.0, noise))
        pts.append((x, y))
    return pts


def test_level_row_reads_level():
    t = track_row_baseline(_row(0.0, noise=1.5), ROW_H)
    assert t is not None
    assert abs(t["signed_slope_deg"]) < 0.6
    assert t["waviness"] < 0.12


def test_sinking_row_reads_positive_true_angle():
    # image y grows downward, so sinking = positive angle, same
    # convention as scoring.py's line_slope_signed_med
    t = track_row_baseline(_row(3.0, noise=1.0), ROW_H)
    assert t is not None
    assert 2.0 < t["signed_slope_deg"] < 4.0


def test_climbing_row_reads_negative():
    t = track_row_baseline(_row(-2.5, noise=1.0), ROW_H)
    assert t is not None
    assert -3.5 < t["signed_slope_deg"] < -1.5


def test_descender_outlier_does_not_bend_the_track():
    # one word with a deep descender: its box bottom sits half a row
    # height BELOW the true baseline. The naive 2-point slope through
    # that word would tilt several degrees; the tracker must not.
    pts = _row(0.0, n=8, noise=0.8)
    x, y = pts[4]
    pts[4] = (x, y + ROW_H * 0.5)
    t = track_row_baseline(pts, ROW_H)
    assert t is not None
    assert t["n_outliers"] >= 1
    assert abs(t["signed_slope_deg"]) < 0.8


def test_wavy_row_scores_wavier_than_straight():
    straight = track_row_baseline(_row(0.0, noise=0.5), ROW_H)
    wavy_pts = [
        (x, y + ROW_H * 0.22 * math.sin(i * 1.9))
        for i, (x, y) in enumerate(_row(0.0, n=10, noise=0.5))
    ]
    wavy = track_row_baseline(wavy_pts, ROW_H)
    assert straight is not None and wavy is not None
    assert wavy["waviness"] > straight["waviness"] * 2.0


def test_short_rows_refuse_rather_than_guess():
    assert track_row_baseline(_row(0.0, n=MIN_POINTS - 1), ROW_H) is None
    # duplicate x positions collapse; still under the minimum
    assert (
        track_row_baseline([(100, 500), (100, 502), (100, 498)], ROW_H) is None
    )


def test_track_rows_maps_group_rows_shape():
    def box_row(slope_deg, y0):
        m = math.tan(math.radians(slope_deg))
        items = []
        for i in range(6):
            x = 80.0 + i * 100.0
            y_base = y0 + m * (x + 40.0 - 80.0)
            items.append({"box": [x, y_base - ROW_H, 80.0, ROW_H]})
        return {"items": items}

    out = track_rows(
        [
            box_row(2.0, 300.0),
            box_row(2.4, 380.0),
            {"items": [{"box": [0, 0, 50, 20]}]},  # too short: skipped
        ]
    )
    assert out["rows_used"] == 2
    med = float(np.median(out["slopes_deg"]))
    assert 1.5 < med < 3.0
    assert all(w < 0.1 for w in out["waviness"])
