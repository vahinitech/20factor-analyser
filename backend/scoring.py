# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies. Server-side handwriting/print recognition.
# Third-party: PaddleOCR (Apache-2.0). See /THIRD-PARTY-NOTICES.md and backend/README.md
#
# scoring.py — the 20-factor handwriting-analysis model.
#
# Turns OCR lines + layout signals into the FactorScore/SectionScore/
# AnalysisResult dataclasses the /report-python endpoint serializes. Nothing
# here knows about OCR engines, HTTP, or image decoding; it only consumes
# the `lines`/`layout` shapes computer_vision.py and the recognizer produce.

import math
import re
from dataclasses import dataclass, field

import numpy as np

try:
    import cv2
except Exception:
    cv2 = None


@dataclass
class FactorScore:
    n: int
    sec: str
    name: str
    ex: str
    target: str
    tip: str
    score: float
    score100: int
    band: str
    value: str
    evidence: str
    based_on: str = None
    conf: str = "measured"
    imu_measured: bool = False
    unmeasured: bool = False
    unmeasured_reason: str = None
    unmeasured_kind: str = None

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "sec": self.sec,
            "name": self.name,
            "ex": self.ex,
            "target": self.target,
            "conf": self.conf,
            "tip": self.tip,
            "score": self.score,
            "score100": self.score100,
            "band": self.band,
            "value": self.value,
            "evidence": self.evidence,
            "imuMeasured": self.imu_measured,
            "unmeasured": self.unmeasured,
            "unmeasuredReason": self.unmeasured_reason,
            "unmeasuredKind": self.unmeasured_kind,
            "basedOn": self.based_on,
        }


@dataclass
class SectionScore:
    id: str
    name: str
    weight: float
    blurb: str
    factors: list = field(default_factory=list)
    avg: float = None
    avg100: int = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "weight": self.weight,
            "blurb": self.blurb,
            "avg": self.avg,
            "avg100": self.avg100,
            "factors": [f.to_dict() for f in self.factors],
            "scoredCount": len(self.factors),
        }


@dataclass
class AnalysisResult:
    results: list
    sections: list
    overall: int
    overall_measured: int
    measured_count: int
    top_weak: list
    top_strong: list
    source: str = "python"

    def to_dict(self) -> dict:
        return {
            "results": [r.to_dict() for r in self.results],
            "sections": [s.to_dict() for s in self.sections],
            "overall": self.overall,
            "overallMeasured": self.overall_measured,
            "measuredCount": self.measured_count,
            "topWeak": [r.to_dict() for r in self.top_weak],
            "topStrong": [r.to_dict() for r in self.top_strong],
            "source": self.source,
        }


_SECTIONS = [
    {
        "id": "structure",
        "name": "Structure",
        "weight": 0.30,
        "blurb": "Letter shapes, size & control",
    },
    {
        "id": "spatial",
        "name": "Spatial",
        "weight": 0.30,
        "blurb": "Spacing, baseline & layout",
    },
    {
        "id": "dynamics",
        "name": "Dynamics",
        "weight": 0.20,
        "blurb": "Speed, pressure & flow",
    },
    {
        "id": "style",
        "name": "Style & Readability",
        "weight": 0.20,
        "blurb": "Slant, legibility & neatness",
    },
]

_FACTOR_META = {
    1: ("structure", "Letter Formation Accuracy", "shape regularity proxy"),
    2: ("structure", "Stroke Order Consistency", "stroke order proxy"),
    3: ("structure", "Loop Closure", "loop-bearing character consistency"),
    4: ("structure", "Line Quality (Smoothness)", "stroke smoothness proxy"),
    5: ("structure", "Size Consistency", "letter-height consistency"),
    6: ("structure", "Ascender / Descender Control", "zone balance"),
    7: ("spatial", "Baseline Alignment", "baseline drift"),
    8: ("spatial", "Word Spacing", "inter-word spacing regularity"),
    9: ("spatial", "Letter Spacing", "intra-word spacing proxy"),
    10: ("spatial", "Margin Discipline", "left margin consistency"),
    11: ("spatial", "Line Straightness", "line slope stability"),
    12: ("spatial", "Vertical Alignment", "stroke tilt stability"),
    13: (
        "dynamics",
        "Speed Consistency",
        "speed proxy from stroke regularity",
    ),
    14: (
        "dynamics",
        "Pressure Consistency",
        "pressure proxy from ink variance",
    ),
    15: (
        "dynamics",
        "Stroke Continuity",
        "continuity proxy from word morphology",
    ),
    16: ("dynamics", "Pen Lift Frequency", "pen-lift proxy from segmentation"),
    17: ("style", "Slant Consistency", "slant variation"),
    18: ("style", "Legibility Score", "composite readability"),
    19: ("style", "Character Distinction", "character separability proxy"),
    20: ("style", "Overall Neatness", "layout neatness composite"),
}

# Per-factor rendering extras consumed by the report renderer (report-render.js):
#   ex     — drill group the Exercises page prescribes for this factor
#   target — the "good hand" band shown as the card's Target
#   tip     — the one-line practice suggestion
# These mirror the values that used to live in the browser scorer (factors.js);
# the scoring maths stays in _score_factor_map — this only labels the output so a
# report rendered purely from the server response reads the same as before.
_FACTOR_EXTRAS = {
    1: (
        "round",
        "shape dist ≤0.10",
        "Slow block-writing drills for the letters that deviate most (a, o, b rows).",
    ),
    2: (
        "round",
        "edit dist ≤2",
        "Guided stroke-tracing sheets for letters built in the wrong order.",
    ),
    3: (
        "round",
        "≥95% closed",
        "Loop drills — rows of oooo and aaaa keeping every counter closed.",
    ),
    4: (
        "slant",
        "jitter ≤0.5 px",
        "Straight-line and curve control drills — llll then cccc, slowly.",
    ),
    5: (
        "round",
        "height CV ≤0.12",
        "Write inside two guide-lines so every letter reaches the same height.",
    ),
    6: (
        "round",
        "ratio err ≤0.15",
        "Tall–short pattern drills (bl bl bl) to train ascenders and descenders.",
    ),
    7: (
        "frame",
        "RMS ≤0.08 x-h",
        "Underline / baseline tracing on ruled sheets.",
    ),
    8: (
        "rhythm",
        "≈1.0 x-h, CV ≤0.25",
        "“word␣␣word” spacing drill — one finger gap between words.",
    ),
    9: (
        "rhythm",
        "gap CV ≤0.30",
        "Spaced-letter slow writing — a matchstick gap between letters.",
    ),
    10: (
        "frame",
        "left CV ≤0.05",
        "Margin-box writing — keep an even left edge down the page.",
    ),
    11: (
        "frame",
        "drift ≤1°",
        "Ruled-sheet practice; pause at the right margin to reset to the line.",
    ),
    12: (
        "slant",
        "tilt CV ≤0.20",
        "Straight-stroke drills — l l l l kept upright.",
    ),
    13: (
        "wave",
        "velocity CV ≤0.20",
        "Slow-writing timing drill; write to a steady 1-2-3 count.",
    ),
    14: (
        "wave",
        "CV ≤0.20",
        "Same-pressure line drills; keep one steady, relaxed force.",
    ),
    15: (
        "rhythm",
        "0 unintended breaks",
        "Cursive joining practice — connect letters within a word.",
    ),
    16: (
        "rhythm",
        "≤0.3 lifts/char",
        "Continuous-word writing without lifting mid-word.",
    ),
    17: (
        "slant",
        "angle CV low",
        "Slant rails — rows of / at one steady angle, then \\.",
    ),
    18: (
        "round",
        "even & clear",
        "Lift your two lowest factors first — legibility rises with them.",
    ),
    19: (
        "round",
        "clear letter pairs",
        "Practise easily-confused pairs side by side until each is unmistakable.",
    ),
    20: (
        "frame",
        "weighted variance",
        "Keep the page tidy — even size, even spacing, straight lines.",
    ),
}


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
    if score >= 7.5:
        return "strong"
    if score >= 5.0:
        return "dev"
    return "focus"


def _group_lines_by_rows(lines):
    if not lines:
        return []
    hs = [max(1.0, float((l.get("box") or [0, 0, 0, 0])[3])) for l in lines]
    row_thr = max(14.0, mean(hs) * 0.75)
    ordered = sorted(
        lines, key=lambda l: float((l.get("box") or [0, 0, 0, 0])[1])
    )
    rows = []
    for l in ordered:
        b = l.get("box") or [0, 0, 0, 0]
        y = float(b[1])
        h = float(max(1.0, b[3]))
        cy = y + (h * 0.5)
        if not rows:
            rows.append({"cy": cy, "items": [l]})
            continue
        if abs(cy - rows[-1]["cy"]) <= row_thr:
            rows[-1]["items"].append(l)
            rows[-1]["cy"] = mean(
                [
                    float((x.get("box") or [0, 0, 0, 0])[1])
                    + float(max(1.0, (x.get("box") or [0, 0, 0, 0])[3])) * 0.5
                    for x in rows[-1]["items"]
                ]
            )
        else:
            rows.append({"cy": cy, "items": [l]})
    for r in rows:
        r["items"].sort(key=lambda x: float((x.get("box") or [0, 0, 0, 0])[0]))
    return rows


def _extract_features(arr: np.ndarray, lines, layout):
    h, w = arr.shape[:2]
    boxes = [l.get("box") or [0, 0, 0, 0] for l in lines]
    widths = [float(max(1.0, b[2])) for b in boxes]
    heights = [float(max(1.0, b[3])) for b in boxes]
    lefts = [float(b[0]) / max(1.0, float(w)) for b in boxes]
    scores = [float(l.get("score", 0.0)) for l in lines]
    texts = [str(l.get("text", "") or "") for l in lines]
    n_lines = len(lines)

    n_words = sum(len(re.findall(r"\S+", t)) for t in texts)
    n_chars = sum(len(re.sub(r"\s+", "", t)) for t in texts)
    char_w = (
        [
            widths[i] / max(1, len(re.sub(r"\s+", "", texts[i])))
            for i in range(n_lines)
        ]
        if n_lines
        else []
    )

    y_centers = [float(b[1] + b[3] * 0.5) / max(1.0, float(h)) for b in boxes]
    line_spacing = []
    if len(y_centers) >= 2:
        ys = sorted(y_centers)
        line_spacing = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)]

    slopes = []
    for l in lines:
        poly = l.get("poly") or []
        if len(poly) >= 2:
            x0, y0 = float(poly[0][0]), float(poly[0][1])
            x1, y1 = float(poly[1][0]), float(poly[1][1])
            dx = max(1e-6, x1 - x0)
            slopes.append(abs(math.degrees(math.atan2(y1 - y0, dx))))
        else:
            slopes.append(0.0)

    rows = _group_lines_by_rows(lines)
    word_gaps = []
    for r in rows:
        items = r.get("items", [])
        if len(items) < 2:
            continue
        row_h = mean(
            [
                float(max(1.0, (it.get("box") or [0, 0, 0, 0])[3]))
                for it in items
            ]
        )
        for i in range(len(items) - 1):
            b1 = items[i].get("box") or [0, 0, 0, 0]
            b2 = items[i + 1].get("box") or [0, 0, 0, 0]
            gap = float(b2[0] - (b1[0] + b1[2]))
            word_gaps.append(max(0.0, gap) / max(1.0, row_h))

    full = " ".join(texts)
    digits_ratio = (
        len(re.findall(r"\d", full)) / max(1, len(full)) if full else 0.0
    )
    loop_chars = len(re.findall(r"[aodpegqAODPEGQ]", full))
    alpha_chars = len(re.findall(r"[A-Za-z]", full))
    loop_ratio = (loop_chars / max(1, alpha_chars)) if alpha_chars else 0.0
    tall_chars = len(re.findall(r"[bdfhkltgjpqy]", full))
    tall_ratio = (tall_chars / max(1, alpha_chars)) if alpha_chars else 0.0

    ink_cv = 0.0
    if cv2 is not None:
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        vals = []
        for b in boxes[:80]:
            x, y, bw, bh = [int(round(v)) for v in b]
            x0 = max(0, x)
            y0 = max(0, y)
            x1 = min(w, x + max(1, bw))
            y1 = min(h, y + max(1, bh))
            if x1 <= x0 or y1 <= y0:
                continue
            patch = gray[y0:y1, x0:x1]
            if patch.size:
                vals.append(float(np.std(patch.astype(np.float32))))
        ink_cv = _cv(vals) if vals else 0.0

    return {
        "n_lines": n_lines,
        "n_words": n_words,
        "n_chars": n_chars,
        "avg_score": mean(scores),
        "height_cv": _cv(heights),
        "width_cv": _cv(widths),
        "char_w_cv": _cv(char_w),
        "left_cv": _cv(lefts),
        "line_slope_abs": mean(slopes),
        "line_slope_std": _std(slopes),
        "line_spacing_cv": _cv(line_spacing),
        "word_gap_cv": _cv(word_gaps),
        "digits_ratio": digits_ratio,
        "loop_ratio": loop_ratio,
        "tall_ratio": tall_ratio,
        "ink_cv": ink_cv,
        "layout_complexity": float(
            layout.get("layout_complexity", 0.0) or 0.0
        ),
    }


def _score_factor_map(fx):
    s = {}
    s[1] = _clamp10(
        (fx["avg_score"] * 7.2) + ((1.0 - min(1.0, fx["height_cv"])) * 2.8)
    )
    s[2] = _clamp10(
        5.4 + (1.0 - min(1.0, fx["char_w_cv"])) * 2.6 + (fx["avg_score"] * 2.0)
    )
    s[3] = _clamp10((min(1.0, fx["loop_ratio"] / 0.28)) * 10.0)
    s[4] = _clamp10((1.0 - min(1.0, fx["width_cv"] / 0.8)) * 10.0)
    s[5] = _clamp10((1.0 - min(1.0, fx["height_cv"] / 0.65)) * 10.0)
    s[6] = _clamp10(
        (1.0 - min(1.0, abs(fx["tall_ratio"] - 0.34) / 0.34)) * 10.0
    )
    s[7] = _clamp10((1.0 - min(1.0, fx["line_slope_abs"] / 8.0)) * 10.0)
    s[8] = _clamp10((1.0 - min(1.0, fx["word_gap_cv"] / 1.4)) * 10.0)
    s[9] = _clamp10((1.0 - min(1.0, fx["char_w_cv"] / 1.2)) * 10.0)
    s[10] = _clamp10((1.0 - min(1.0, fx["left_cv"] / 0.55)) * 10.0)
    s[11] = _clamp10((1.0 - min(1.0, fx["line_slope_abs"] / 10.0)) * 10.0)
    s[12] = _clamp10((1.0 - min(1.0, fx["line_slope_std"] / 10.0)) * 10.0)
    s[13] = _clamp10((1.0 - min(1.0, fx["width_cv"] / 0.85)) * 10.0)
    s[14] = _clamp10((1.0 - min(1.0, fx["ink_cv"] / 0.95)) * 10.0)
    s[15] = _clamp10(
        (
            1.0
            - min(
                1.0, abs((fx["n_chars"] / max(1, fx["n_words"])) - 5.0) / 5.0
            )
        )
        * 10.0
    )
    s[16] = _clamp10((1.0 - min(1.0, fx["char_w_cv"] / 1.4)) * 10.0)
    s[17] = _clamp10((1.0 - min(1.0, fx["line_slope_std"] / 12.0)) * 10.0)
    s[18] = _clamp10(
        (0.35 * s[1]) + (0.25 * s[5]) + (0.20 * s[8]) + (0.20 * s[7])
    )
    s[19] = _clamp10(
        (fx["avg_score"] * 7.5)
        + ((1.0 - min(1.0, fx["digits_ratio"] / 0.5)) * 2.5)
    )
    s[20] = _clamp10(
        (0.30 * s[5])
        + (0.20 * s[8])
        + (0.20 * s[10])
        + (0.15 * s[11])
        + (0.15 * s[17])
    )
    return s


def build_analysis(arr: np.ndarray, lines, layout) -> AnalysisResult:
    fx = _extract_features(arr, lines, layout)
    scores = _score_factor_map(fx)
    basis = {
        1: f"{fx['n_chars']} letters",
        2: f"{fx['n_words']} words",
        3: f"{fx['n_chars']} letters",
        4: f"{fx['n_lines']} lines",
        5: f"{fx['n_chars']} letters",
        6: f"{fx['n_chars']} letters",
        7: f"{fx['n_lines']} lines",
        8: f"{fx['n_words']} words",
        9: f"{fx['n_chars']} letters",
        10: f"{fx['n_lines']} lines",
        11: f"{fx['n_lines']} lines",
        12: f"{fx['n_lines']} lines",
        13: f"{fx['n_lines']} lines",
        14: f"{fx['n_lines']} lines",
        15: f"{fx['n_words']} words",
        16: f"{fx['n_words']} words",
        17: f"{fx['n_lines']} lines",
        18: f"{fx['n_lines']} lines",
        19: f"{fx['n_chars']} letters",
        20: f"{fx['n_lines']} lines",
    }

    results = []
    for n in range(1, 21):
        sec, name, detail = _FACTOR_META[n]
        ex, target, tip = _FACTOR_EXTRAS.get(
            n,
            (
                "round",
                "python-server estimate",
                "Practice this factor with short daily drills and rescan after 3-5 days.",
            ),
        )
        score = round(float(scores.get(n, 0.0)), 1)
        value = f"{round(score * 10):.0f}%"
        results.append(
            FactorScore(
                n=n,
                sec=sec,
                name=name,
                ex=ex,
                target=target,
                tip=tip,
                score=score,
                score100=int(round(score * 10)),
                band=_band(score),
                value=value,
                evidence=f"Server-side OCR/layout heuristic based on {detail}.",
                based_on=basis.get(n),
            )
        )

    sections = []
    for sec_meta in _SECTIONS:
        fs = [r for r in results if r.sec == sec_meta["id"]]
        avg = mean([r.score for r in fs]) if fs else 0.0
        sections.append(
            SectionScore(
                id=sec_meta["id"],
                name=sec_meta["name"],
                weight=sec_meta["weight"],
                blurb=sec_meta["blurb"],
                factors=fs,
                avg=round(avg, 1) if fs else None,
                avg100=int(round(avg * 10)) if fs else None,
            )
        )

    wsum = sum(float(s.weight) for s in sections) or 1.0
    overall = int(
        round(
            sum(
                float(s.avg100 or 0) * (float(s.weight) / wsum)
                for s in sections
            )
        )
    )
    ranked = sorted(results, key=lambda r: float(r.score))
    top_weak = ranked[:3]
    top_strong = sorted(results, key=lambda r: float(r.score), reverse=True)[
        :4
    ]

    return AnalysisResult(
        results=results,
        sections=sections,
        overall=overall,
        overall_measured=overall,
        measured_count=len(results),
        top_weak=top_weak,
        top_strong=top_strong,
    )
