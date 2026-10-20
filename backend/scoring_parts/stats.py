# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# stats.py - the small statistics every part of the scorer shares, and
# the score bands.

import math

import numpy as np


def mean(xs):
    vals = [float(x) for x in xs if x is not None and np.isfinite(float(x))]
    if not vals:
        return 0.0
    return float(sum(vals) / len(vals))


def _std(xs):
    vals = [float(x) for x in xs if x is not None and np.isfinite(float(x))]
    if len(vals) < 2:
        return 0.0
    m = mean(vals)
    v = sum((x - m) ** 2 for x in vals) / max(1, len(vals) - 1)
    return float(math.sqrt(max(0.0, v)))


def _cv(xs):
    m = mean(xs)
    if m <= 1e-9:
        return 0.0
    return float(_std(xs) / m)


def _clamp10(v):
    return float(max(0.0, min(10.0, v)))


def _band(score):
    if score >= 8.5:
        return "strong"
    if score >= 7.0:
        return "good"
    if score >= 4.5:
        return "dev"
    return "focus"
