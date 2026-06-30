# SPDX-License-Identifier: AGPL-3.0-only
# © 2026 Vahini Technologies. Contact: infor@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
# Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json
#!/usr/bin/env python3
"""
Vahini local recognition server — PaddleOCR **PP-OCRv5**, fully on-device.

WHAT THIS IS (server-side OCR)
------------------------------
This runs on a machine YOU control — your laptop for testing, or the
vahinitech.com server in production. The browser app (client side) sends the
photo here over HTTP; this process runs the PP-OCRv5 deep-learning models and
sends back the recognised text + boxes. The model weights live here, never in
the browser. "Server side" = this file. "Client side" = engine.bundle.js in the
visitor's browser, which only does the deterministic geometry and calls this.

WHY USE IT
----------
Pure in-browser computer vision measures *geometry* well but cannot reliably
tell a printed letterhead from handwriting, or read Telugu. PP-OCRv5 here:
  • recognises English AND Telugu (and 80+ scripts),
  • unwarps / deorients the page first (helps hand-held phone tilt),
  • returns a per-line print-vs-handwriting HINT (see note below) so the
    geometry engine can drop printed letterhead / footer lines before scoring.

SETUP (one time, needs internet to download the models, ~20-80 MB)
    pip install paddlepaddle paddleocr flask flask-cors pillow numpy
RUN
    python ppocr-server.py                 # English + Telugu, port 8868
    VAHINI_OCR_LANGS=en,te,fr python ppocr-server.py   # add more scripts
The first run downloads the PP-OCRv5 detection + recognition models; after that
it works fully offline.

RESPONSE SHAPE (what engine.bundle.js expects)
    { "lines": [ {"text": str, "box": [x,y,w,h], "score": float,
                  "lang": "en"|"te", "printed_hint": bool}, ... ],
      "full_text": str, "engine": "pp-ocrv5" }

NOTE ON THE PRINTED HINT — honesty matters for this product:
    printed_hint is a HEURISTIC (high recognition confidence + dictionary-clean
    text recognises far more cleanly than handwriting). It is advisory only. The
    geometry engine still makes the final printed/handwritten call by combining
    this hint with letter-size and baseline evidence, and never reports a score
    it cannot stand behind.
"""
import io
import os
import re

from flask import Flask, request, jsonify
from flask_cors import CORS
from PIL import Image
import numpy as np

from paddleocr import PaddleOCR

app = Flask(__name__)
CORS(app)  # allow the browser app (file:// or localhost) to call us

# Languages to load. PP-OCRv5 ships a multilingual recognition model; we hold one
# PaddleOCR instance per script so mixed English + Telugu pages read correctly.
# Override with  VAHINI_OCR_LANGS=en,te,hi  etc.
LANGS = [s.strip() for s in os.environ.get("VAHINI_OCR_LANGS", "en,te").split(",") if s.strip()]

# Turn doc orientation + unwarping ON: handwriting photos are shot by hand and
# are rarely square to the page. PP-OCRv5 deskews/unwarps before recognition,
# which directly improves a tilted phone shot (your Line-Straightness concern,
# handled here at the pixel level in addition to the engine's median-tilt deskew).
_OCR_KW = dict(
    use_doc_orientation_classify=True,
    use_doc_unwarping=True,
    use_textline_orientation=True,
)

_engines = {}

def get_engine(lang):
    """Lazy-load one PaddleOCR per language so startup is fast."""
    if lang not in _engines:
        try:
            _engines[lang] = PaddleOCR(lang=lang, **_OCR_KW)
        except Exception as e:
            print(f"[Vahini] could not load lang={lang}: {e}")
            _engines[lang] = None
    return _engines[lang]

# Telugu code points — used only to label a line's script for the report.
_TELUGU = re.compile(r"[\u0C00-\u0C7F]")

def poly_to_box(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return [float(min(xs)), float(min(ys)),
            float(max(xs) - min(xs)), float(max(ys) - min(ys))]

def looks_printed(text, score):
    """ADVISORY hint only (see module docstring). Printed text recognises with
    high confidence and clean, well-formed tokens; handwriting does not."""
    if score is None:
        return False
    t = (text or "").strip()
    if not t:
        return False
    # high confidence + no isolated single-char noise + mostly letters/digits
    clean = len(re.sub(r"[^\w\u0C00-\u0C7F]", "", t)) / max(1, len(t))
    return score >= 0.92 and len(t) >= 3 and clean >= 0.7

def run_lang(arr, lang):
    eng = get_engine(lang)
    if eng is None:
        return []
    out = []
    for page in eng.predict(arr):
        texts  = page.get("rec_texts", [])
        polys  = page.get("rec_polys", page.get("dt_polys", []))
        scores = page.get("rec_scores", [])
        for i, text in enumerate(texts):
            if not (text or "").strip():
                continue
            box = poly_to_box(polys[i]) if i < len(polys) else [0, 0, 0, 0]
            score = float(scores[i]) if i < len(scores) else 0.0
            out.append({
                "text": text,
                "box": box,
                "score": score,
                "lang": "te" if _TELUGU.search(text) else lang,
                "printed_hint": looks_printed(text, score),
            })
    return out

def dedupe(lines):
    """When several language passes return the same region, keep the
    highest-confidence reading per box (IoU-overlap merge, simple + robust)."""
    kept = []
    for ln in sorted(lines, key=lambda l: -l["score"]):
        x, y, w, h = ln["box"]
        dup = False
        for k in kept:
            kx, ky, kw, kh = k["box"]
            ox = max(0, min(x + w, kx + kw) - max(x, kx))
            oy = max(0, min(y + h, ky + kh) - max(y, ky))
            inter = ox * oy
            union = w * h + kw * kh - inter
            if union > 0 and inter / union > 0.5:
                dup = True
                break
        if not dup:
            kept.append(ln)
    return kept

@app.route("/ocr", methods=["POST"])
def do_ocr():
    f = request.files.get("image")
    if f is None:
        return jsonify({"error": "POST an 'image' file"}), 400
    img = Image.open(io.BytesIO(f.read())).convert("RGB")
    arr = np.array(img)

    # Honour an explicit lang from the client, else run every configured script
    # and merge — this is what makes a mixed English + Telugu page read fully.
    req_lang = (request.form.get("lang") or "").strip()
    langs = [req_lang] if req_lang in LANGS else LANGS

    lines = []
    for lg in langs:
        lines.extend(run_lang(arr, lg))
    lines = dedupe(lines)
    lines.sort(key=lambda l: l["box"][1])  # top-to-bottom reading order

    return jsonify({
        "lines": lines,
        "full_text": "\n".join(l["text"] for l in lines),
        "engine": "pp-ocrv5",
        "langs": langs,
    })

@app.route("/health")
def health():
    return jsonify({"ok": True, "engine": "pp-ocrv5", "langs": LANGS})

if __name__ == "__main__":
    print(f"Vahini PP-OCRv5 server → http://127.0.0.1:8868/ocr  (langs: {', '.join(LANGS)})")
    app.run(host="127.0.0.1", port=8868)
