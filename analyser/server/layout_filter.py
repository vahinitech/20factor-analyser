# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies. Document-layout pre-filter for the recognition
# pipeline. Third-party: PaddleOCR / PaddleX (Apache-2.0). See
# /THIRD-PARTY-NOTICES.md and server/README.md.
#
# layout_filter.py — a NEGATIVE pre-filter using PaddleOCR's own document
# layout model (PP-DocLayout), run before text-line detection results reach
# classify.py.
#
# Why negative, not positive: PP-DocLayout's categories are document
# STRUCTURE (doc_title, paragraph_title, text, table, formula, image, seal,
# chart, header, footer, page_number...), not a printed-vs-handwriting
# signal — it cannot replace classify.py. Restricting analysis to only the
# "text" category would silently drop real handwritten content that the
# model correctly, but unhelpfully for us, tags "formula" or "table" (a
# student's worked-out equation, a filled-in form cell). So this module only
# EXCLUDES categories that are never ink/text content at all: image, figure,
# chart, seal. Everything else (including formula and table) still goes
# through the normal detection + classify.py pipeline unchanged.
#
# Speed-adaptive, same shape as ocr_backends' hybrid-engine speed memo: try
# the more accurate PP-DocLayout-M first; if a real measured call is too
# slow on this machine, fall back to the cheaper PP-DocLayout-S; if even
# that is too slow, skip layout filtering entirely for the retry window.
# Filtering is a pure accuracy nice-to-have, never a hard requirement, so a
# slow or unavailable model must never block a scan.

import os
import threading
import time
import importlib.util

import numpy as np

import ocr_backends

# Categories that are never ink/text content (see module docstring for why
# "formula" and "table" are deliberately NOT here). "header_image" and
# "footer_image" (e.g. a printed letterhead crest, a decorative footer
# graphic) are two of the 23 categories PP-DocLayout-L/M/S — the exact
# tiers this module runs — are documented to emit; they were missing here
# before, so a letterhead crest could previously slip through as an
# unfiltered "image" region. Deliberately NOT added: "figure_caption",
# "table_caption", "figure_title" (a student's own handwritten caption or
# title is real text, not decoration) or "header"/"footer" without
# "_image" (a page header/footer can be a student's own handwritten name
# or page number).
_EXCLUDE_LABELS = {
    "image",
    "figure",
    "chart",
    "seal",
    "header_image",
    "footer_image",
}

_MAX_MS = max(
    50.0, float(os.environ.get("VAHINI_LAYOUT_MAX_MS", "800") or "800")
)
_ENABLED = (os.environ.get("VAHINI_LAYOUT_FILTER", "1") or "1").strip() == "1"

_MODELS = {}  # tier name ("layout_m"/"layout_s") -> built LayoutDetection
_ATTEMPTED = set()  # tier names a background build has been started for


def _build(tier_key, model_name):
    """Return the already-built model for `tier_key`, or None if it isn't
    ready yet. NEVER blocks the caller (a request must never be slowed
    down by a model download): a not-yet-built model kicks off a
    background thread the FIRST time it's asked for — once, ever, per
    tier per process — and returns None immediately. A failed download
    doesn't fail fast (paddlex walks several mirror hosts, each with its
    own retry/backoff, before giving up — real seconds), which is exactly
    why this must run in the background rather than block a scan waiting
    for it. Warm this ahead of time with warmup_models.py so it's normally
    already built by the time real traffic arrives; the live path degrades
    to "not available yet" for free otherwise."""
    model = _MODELS.get(tier_key)
    if model is not None:
        return model
    if tier_key not in _ATTEMPTED:
        _ATTEMPTED.add(tier_key)

        def _worker():
            try:
                from paddleocr import LayoutDetection

                _MODELS[tier_key] = LayoutDetection(model_name=model_name)
            except Exception:
                pass  # leave unset; every caller treats this as unavailable

        threading.Thread(target=_worker, daemon=True).start()
    return None


def available():
    try:
        found = importlib.util.find_spec("paddleocr") is not None
    except (ImportError, ValueError):
        # ValueError: another module has stubbed sys.modules["paddleocr"]
        # with a bare module object that has no __spec__ (some tests do
        # this to fake PaddleOCR without installing it) — treat that the
        # same as "not really available" for layout detection specifically.
        found = False
    if not found:
        return False, "layout filter deps missing: no paddleocr"
    return True, ""


def is_enabled():
    """Whether the layout pre-filter is turned on (VAHINI_LAYOUT_FILTER)."""
    return _ENABLED


def built_tiers():
    """Which model tiers ("layout_m"/"layout_s") are actually built and
    ready right now — used by /health. A build never blocks a request (see
    _build()), so this can be empty for a while after startup even with
    the filter enabled."""
    return sorted(_MODELS.keys())


def _select_tier():
    """Which model tier to use right now, from real measured speed on this
    machine (see module docstring). Returns (tier_key, model_name) or
    (None, None) if layout filtering should be skipped this round."""
    m_verdict = ocr_backends.engine_speed_verdict("layout_m")
    if m_verdict is None or m_verdict[1]:
        return "layout_m", "PP-DocLayout-M"
    s_verdict = ocr_backends.engine_speed_verdict("layout_s")
    if s_verdict is None or s_verdict[1]:
        return "layout_s", "PP-DocLayout-S"
    return None, None


def excluded_regions(arr: np.ndarray):
    """[[x0,y0,x1,y1], ...] boxes of non-text-ink content on this page
    (image/figure/chart/seal), or [] if layout filtering is disabled,
    unavailable, or currently too slow on this machine. Never raises."""
    if not _ENABLED:
        return []
    tier_key, model_name = _select_tier()
    if tier_key is None:
        return []
    ok, _reason = available()
    if not ok:
        return []
    try:
        model = _build(tier_key, model_name)
    except Exception:
        return []
    if model is None:
        return []  # not built yet (still downloading in the background)

    t0 = time.perf_counter()
    try:
        results = model.predict(arr, batch_size=1)
        boxes = []
        for res in results:
            for box in (res.get("boxes") if hasattr(res, "get") else []) or []:
                label = str(box.get("label", "")).strip().lower()
                # Docs describe multi-word categories in prose ("header
                # image") while the real API returns snake_case label
                # strings (e.g. "figure_title", confirmed from PaddleOCR's
                # own example output) — normalize both space and hyphen
                # variants to underscore so the match doesn't depend on an
                # exact, unverifiable-in-this-sandbox string format.
                label = label.replace("-", "_").replace(" ", "_")
                if label in _EXCLUDE_LABELS:
                    boxes.append([float(v) for v in box["coordinate"][:4]])
    except Exception:
        return []
    ocr_backends.record_engine_speed(
        tier_key, (time.perf_counter() - t0) * 1000.0
    )
    return boxes


def _overlap_fraction(box, region):
    bx0, by0, bx1, by1 = box[0], box[1], box[0] + box[2], box[1] + box[3]
    rx0, ry0, rx1, ry1 = region
    ix0, iy0 = max(bx0, rx0), max(by0, ry0)
    ix1, iy1 = min(bx1, rx1), min(by1, ry1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area = max(1.0, (bx1 - bx0) * (by1 - by0))
    return inter / area


def filter_excluded_regions(lines, regions):
    """Drop any detected line whose box mostly overlaps a non-text-ink
    region (image/figure/chart/seal). A line only partly touching the edge
    of an excluded region (e.g. a caption just below a figure) is kept."""
    if not regions:
        return lines
    kept = []
    for l in lines:
        box = l.get("box") or [0, 0, 0, 0]
        if any(_overlap_fraction(box, r) >= 0.6 for r in regions):
            continue
        kept.append(l)
    return kept
