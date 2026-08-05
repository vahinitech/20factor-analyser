# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Kalman-smoothed baseline tracking across a text row (issue #31).

The word boxes of one visual row give an x-ordered sequence of noisy
baseline measurements: the bottom-centre of each box. Factor 7 and the
baseline-drift narrative previously reduced a whole row to the angle
between the FIRST TWO vertices of one OCR polygon, so a single noisy
vertex could flip "climbing" into "sinking" and every word between the
endpoints was ignored.

This module treats x as time and runs a constant-velocity Kalman filter
(state: baseline height and local slope, in pixels) followed by an RTS
smoother, so every word in the row informs the estimate. An EKF is
deliberately NOT used: the model is linear, and linearisation would add
error and opacity for nothing (the assessment lives in issue #31).

Two departures from the textbook, both forced by the data:

- Word-box bottoms are BIASED measurements. A word containing g/y/p/q
  extends below the true baseline, always downward (image y grows down).
  After a first smoothing pass the fit is re-run with descender-like
  outliers down-weighted: residuals beyond ``OUTLIER_MAD_K`` times the
  MAD, with the asymmetry that downward outliers are expected and
  clipped harder. Deterministic - same input, same output, no learned
  parts - per the repo's auditable-CV rule.
- Rows are short (often 3-8 words), so the smoother is deliberately
  stiff: the process noise lets the slope wander slowly, and the
  waviness OUTPUT is the residual scatter about the smoothed track, not
  the track's own wiggle.

Everything is plain numpy; scoring formulas are untouched in phase 1
(the robust slope feeds the drift DIRECTION narrative and evidence text
only - see issue #31 for the phased plan).

Provenance: written for this repo directly from the standard equations
(Kalman 1960, "A New Approach to Linear Filtering and Prediction
Problems"; Rauch, Tung & Striebel 1965 for the smoother), not copied or
adapted from any existing implementation. The repo's code-reuse rule
(CLAUDE.md) applies to textbook algorithms too: cite the source of the
equations, write the code independently.
"""

import math

import numpy as np

# Measurement noise prior: word-box bottoms scatter about the baseline
# by roughly a quarter of the row height even without descenders (OCR
# box quantisation, ink weight). Variance in px^2 is (R_REL * row_h)^2.
R_REL = 0.25

# Process noise: how fast the true baseline's slope may wander, as
# height change per row-height of horizontal travel. Small = stiff
# track that follows page-level drift but not per-word jitter.
Q_SLOPE_REL = 0.05

# Robust reweighting: residuals beyond this many MADs are outliers.
# Downward outliers (positive residual, likely descenders) are clipped
# at half this threshold because that failure mode is expected.
OUTLIER_MAD_K = 3.0

# Below this many words a "track" is just a line through noise; callers
# should fall back to whatever coarser estimate they already have.
MIN_POINTS = 3


def _kf_rts(xs, ys, r_var, q_var):
    """Constant-velocity KF forward pass + RTS backward pass.

    xs are strictly increasing pixel positions, ys the measurements,
    r_var the per-point measurement variance, q_var the slope process
    noise density (variance gained per px of travel). Returns the
    smoothed [y, slope] state per point.
    """
    n = len(xs)
    # forward KF
    x_f = np.zeros((n, 2))  # filtered state [y, dy/dx]
    p_f = np.zeros((n, 2, 2))  # filtered covariance
    x_p = np.zeros((n, 2))  # predicted state (saved for the RTS pass)
    p_p = np.zeros((n, 2, 2))
    x_f[0] = [ys[0], 0.0]
    p_f[0] = np.diag([r_var[0], 1.0])
    x_p[0] = x_f[0]
    p_p[0] = p_f[0]
    for k in range(1, n):
        dx = xs[k] - xs[k - 1]
        f = np.array([[1.0, dx], [0.0, 1.0]])
        q = np.array(
            [
                [q_var * dx**3 / 3.0, q_var * dx**2 / 2.0],
                [q_var * dx**2 / 2.0, q_var * dx],
            ]
        )
        x_p[k] = f @ x_f[k - 1]
        p_p[k] = f @ p_f[k - 1] @ f.T + q
        # scalar measurement update, H = [1, 0]
        s = p_p[k][0, 0] + r_var[k]
        gain = p_p[k][:, 0] / s
        innov = ys[k] - x_p[k][0]
        x_f[k] = x_p[k] + gain * innov
        p_f[k] = p_p[k] - np.outer(gain, p_p[k][0, :])
    # RTS smoother
    x_s = x_f.copy()
    p_s = p_f.copy()
    for k in range(n - 2, -1, -1):
        dx = xs[k + 1] - xs[k]
        f = np.array([[1.0, dx], [0.0, 1.0]])
        c = p_f[k] @ f.T @ np.linalg.inv(p_p[k + 1])
        x_s[k] = x_f[k] + c @ (x_s[k + 1] - x_p[k + 1])
        p_s[k] = p_f[k] + c @ (p_s[k + 1] - p_p[k + 1]) @ c.T
    return x_s


def _collapse_duplicate_x(pts):
    """Collapse points sharing an x position (within 1e-6 px) to one
    point at their mean y, so the filter sees a strictly increasing
    axis. Incremental mean per group: every tied point carries equal
    weight no matter how many share the x (repeated pairwise averaging
    would weight later points more). pts must be sorted by x."""
    xs, ys, counts = [], [], []
    for x, y in pts:
        if xs and x - xs[-1] < 1e-6:
            counts[-1] += 1
            ys[-1] += (y - ys[-1]) / counts[-1]
        else:
            xs.append(x)
            ys.append(y)
            counts.append(1)
    return xs, ys


def track_row_baseline(points, row_h):
    """Smooth one row's word-baseline measurements.

    points: iterable of (x_center, y_bottom) word-box measurements in
    pixels, any order (sorted internally; ties in x are averaged so the
    filter sees a strictly increasing axis). row_h: representative row
    height in pixels, > 0.

    Returns None when fewer than MIN_POINTS distinct x positions
    survive, else a dict:
      signed_slope_deg  net baseline angle over the row, degrees,
                        positive = sinking left-to-right (image y down)
      waviness          RMS inlier residual about the smoothed track,
                        normalised by row_h
      n_points          measurements used
      n_outliers        measurements down-weighted as descender-like
      y_smooth          smoothed baseline height per used x (pixels)
      xs                the used x positions (pixels)
    """
    row_h = float(max(1.0, row_h))
    pts = sorted((float(x), float(y)) for x, y in points)
    xs, ys = _collapse_duplicate_x(pts)
    if len(xs) < MIN_POINTS:
        return None
    xs = np.asarray(xs)
    ys = np.asarray(ys)

    r0 = (R_REL * row_h) ** 2
    # slope may random-walk by ~Q_SLOPE_REL (dimensionless dy/dx) over
    # one row-height of horizontal travel: variance per px of travel
    q_var = Q_SLOPE_REL**2 / row_h
    r_var = np.full(len(xs), r0)

    # pass 1: plain smooth; pass 2: descender-aware reweight
    state = _kf_rts(xs, ys, r_var, q_var)
    resid = ys - state[:, 0]
    mad = float(np.median(np.abs(resid - np.median(resid))))
    n_out = 0
    if mad > 1e-9:
        thr_up = OUTLIER_MAD_K * 1.4826 * mad
        # positive residual = box bottom below the track = descender
        thr_down = 0.5 * thr_up
        out = (resid > thr_down) | (resid < -thr_up)
        n_out = int(np.count_nonzero(out))
        if n_out and n_out < len(xs) - 1:
            r_var = np.where(out, r0 * 25.0, r0)
            state = _kf_rts(xs, ys, r_var, q_var)
            resid = ys - state[:, 0]
        else:
            out = np.zeros(len(xs), dtype=bool)
    else:
        out = np.zeros(len(xs), dtype=bool)

    span = float(xs[-1] - xs[0])
    if span < 1e-6:
        return None
    rise = float(state[-1, 0] - state[0, 0])
    inl = ~out
    wav = (
        float(np.sqrt(np.mean(resid[inl] ** 2))) / row_h
        if np.count_nonzero(inl)
        else 0.0
    )
    return {
        "signed_slope_deg": math.degrees(math.atan2(rise, span)),
        "waviness": wav,
        "n_points": int(len(xs)),
        "n_outliers": n_out,
        "y_smooth": state[:, 0].tolist(),
        "xs": xs.tolist(),
    }


def track_rows(rows):
    """Run track_row_baseline over _group_lines_by_rows() output.

    rows: list of {"items": [line dicts with "box" [x, y, w, h]]}.
    Rows with fewer than MIN_POINTS boxes are skipped. Returns a dict:
      slopes_deg  per-tracked-row signed baseline angle (degrees)
      waviness    per-tracked-row normalised residual RMS
      rows_used   how many rows produced a track
    """
    slopes, wavs = [], []
    for r in rows:
        items = r.get("items") or []
        if len(items) < MIN_POINTS:
            continue
        boxes = [it.get("box") or [0, 0, 0, 0] for it in items]
        row_h = float(np.median([max(1.0, float(b[3])) for b in boxes]))
        pts = [
            (float(b[0]) + float(b[2]) * 0.5, float(b[1]) + float(b[3]))
            for b in boxes
        ]
        t = track_row_baseline(pts, row_h)
        if t is None:
            continue
        slopes.append(t["signed_slope_deg"])
        wavs.append(t["waviness"])
    return {
        "slopes_deg": slopes,
        "waviness": wavs,
        "rows_used": len(slopes),
    }
