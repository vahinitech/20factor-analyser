# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies. Document-layout pre-filter for the recognition
# pipeline. Third-party: PaddleOCR / PaddleX (Apache-2.0). See
# /THIRD-PARTY-NOTICES.md and backend/README.md.
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
# One model, chosen by configuration (VAHINI_LAYOUT_MODEL, default
# PP-DocLayout-M), never by how fast the last call was. It used to switch
# to PP-DocLayout-S, or skip filtering, after one slow call, and to skip it
# while the model loaded in the background. The two models and "no filter"
# keep different lines, so the same photo scored differently depending on
# server load (20factor-analyser#112). The model is preloaded in the image
# and warmed at start-up; a scan that arrives first waits for it.

import os
import threading
import importlib.util

import numpy as np

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

# A photographed notebook is often labelled one "image" covering the
# whole frame (PP-DocLayout-M gave 0.66 on tests' handwriting-sample.jpg,
# box over ~87% of the page), which dropped every handwritten line and
# left the report scoring CV fallback regions. A region this large is the
# page itself, not a figure on it.
_MAX_REGION_PAGE_FRACTION = 0.5

_ENABLED = (os.environ.get("VAHINI_LAYOUT_FILTER", "1") or "1").strip() == "1"

_TIERS = {"PP-DocLayout-M": "layout_m", "PP-DocLayout-S": "layout_s"}
_MODEL_NAME = (
    os.environ.get("VAHINI_LAYOUT_MODEL", "PP-DocLayout-M") or ""
).strip()
if _MODEL_NAME not in _TIERS:
    _MODEL_NAME = "PP-DocLayout-M"

_MODELS = {}  # tier name ("layout_m"/"layout_s") -> built LayoutDetection
_FAILED = {}  # tier name -> load error, kept for the life of the process
_LOCK = threading.Lock()


def _build(tier_key, model_name):
    """Return the model for `tier_key`, loading it on first use. Callers
    wait for the load: skipping the filter until a background load finished
    made the first scans after a start score differently from later ones.
    A failed load is remembered for the life of the process, so every scan
    on this server takes the same path instead of flipping on a retry."""
    model = _MODELS.get(tier_key)
    if model is not None or tier_key in _FAILED:
        return model
    with _LOCK:
        if tier_key in _MODELS or tier_key in _FAILED:
            return _MODELS.get(tier_key)
        try:
            from paddleocr import LayoutDetection

            _MODELS[tier_key] = LayoutDetection(model_name=model_name)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _FAILED[tier_key] = str(exc)
    return _MODELS.get(tier_key)


def warm():
    """Load the configured model ahead of the first scan (server start-up).
    Never raises."""
    if not _ENABLED or not available()[0]:
        return
    try:
        _build(_TIERS[_MODEL_NAME], _MODEL_NAME)
    except Exception:  # pylint: disable=broad-exception-caught
        pass


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
    """Which model tiers ("layout_m"/"layout_s") are loaded right now, for
    /health."""
    return sorted(_MODELS.keys())


def status():
    """The configured model and whether it loaded, for /health."""
    tier = _TIERS[_MODEL_NAME]
    return {
        "model": _MODEL_NAME,
        "loaded": tier in _MODELS,
        "error": _FAILED.get(tier, ""),
    }


def _select_tier():
    """The configured (tier_key, model_name). Always the same for a given
    deployment: measured speed must not change which lines get scored."""
    return _TIERS[_MODEL_NAME], _MODEL_NAME


def excluded_regions(arr: np.ndarray):
    """[[x0,y0,x1,y1], ...] boxes of non-text-ink content on this page
    (image/figure/chart/seal), or [] if layout filtering is disabled or
    the model is unavailable. Never raises."""
    if not _ENABLED:
        return []
    tier_key, model_name = _select_tier()
    ok, _reason = available()
    if not ok:
        return []
    try:
        model = _build(tier_key, model_name)
    except Exception:
        return []
    if model is None:
        return []  # failed to load; the same for every scan on this server

    page_area = float(max(1, arr.shape[0]) * max(1, arr.shape[1]))
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
                if label not in _EXCLUDE_LABELS:
                    continue
                x0, y0, x1, y1 = [float(v) for v in box["coordinate"][:4]]
                if (max(0.0, x1 - x0) * max(0.0, y1 - y0)) >= (
                    _MAX_REGION_PAGE_FRACTION * page_area
                ):
                    continue
                boxes.append([x0, y0, x1, y1])
    except Exception:
        return []
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
    # Fail-open, like the noise filter: a layout guess must not remove
    # every line on the page.
    return kept or lines
