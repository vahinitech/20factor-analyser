<!-- SPDX-License-Identifier: AGPL-3.0-only
     © 2026 Vahini Technologies. Contact: info@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
     Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json -->
# Vahini recognition (OCR) — server vs. client, in plain terms

You asked exactly the right question. Here is the straight answer.

---

## 🚀 Quick start (CPU-only, this machine)

The analyser now uses **pluggable OCR engines** behind one switch. The Python
server drives the 20-factor report; the browser front-end renders it.

```powershell
# Windows (PowerShell) — from the repo root. Creates .venv at the repo root,
# installs core + the engines you pick, and pre-downloads the models.
.\analyser\server\setup.ps1                        # core + PaddleOCR (default)
.\analyser\server\setup.ps1 -Engines paddle,trocr  # + English handwriting
.\analyser\server\setup.ps1 -Engines all           # paddle + trocr + surya
```

```bash
# Linux / macOS
./analyser/server/setup.sh                 # core + PaddleOCR (default)
./analyser/server/setup.sh paddle trocr    # + English handwriting
./analyser/server/setup.sh all             # paddle + trocr + surya
```

Then run the service and pick the engine with **one env var**:

```powershell
$env:VAHINI_OCR_BACKEND = "paddle"     # paddle | trocr | surya | chandra | auto
& .\.venv\Scripts\python.exe .\analyser\server\ppocr-server.py    # serves :8868
```

Check what's installed/ready:  `curl http://127.0.0.1:8868/health`  →  the
`backends` field lists every engine and whether it can run here.

### Server module layout

Each file has one job, so a change (a new OCR engine, a CV tweak, a 21st
factor) touches one obvious place:

| File | Responsibility |
|---|---|
| `ppocr-server.py` | Thin FastAPI layer: the `/ocr`, `/analyze-vl`, `/report-python` and `/health` routes, CORS, and wiring the modules below together at startup. |
| `config.py` | Every `VAHINI_OCR_*`/`VAHINI_CHANDRA_*` env var, parsed once into a `Settings` dataclass. |
| `cache.py` | The response cache (TTL + max-item eviction) shared by the three recognition endpoints. |
| `ocr_backends.py` | One adapter per engine (paddle/trocr/surya/chandra/paddleocr-vl) behind a common `OCRBackend` interface, plus the paddle engine cache/lock/inference call. |
| `detector.py` | Preprocessing variants and candidate text-region filtering (dedup, noise, printed-vs-handwriting heuristics). |
| `recognizer.py` | Orchestrates recognition across backends: language resolution, backend dispatch (`auto` mode scores every engine and keeps the best), refinement and reference-passage alignment. |
| `computer_vision.py` | Pure image algorithms: decoding an upload, crops/previews, layout and document-context signals. |
| `scoring.py` | The 20-factor model: `FactorScore`/`SectionScore`/`AnalysisResult` dataclasses and the feature-extraction/scoring maths. |
| `classify.py` | The printed-vs-handwriting classifier. |
| `geometry.py`, `model_map.py`, `gpu_detect.py` | Small shared helpers (bbox clamping, `lang:model` map parsing, GPU auto-detection). |

### The engines (and the honest CPU verdict on this laptop)

| `VAHINI_OCR_BACKEND` | Engine | Handwriting | Indic (Telugu) | CPU on this box | Install |
|---|---|---|---|---|---|
| `paddle` *(default)* | PaddleOCR PP-OCRv5 | modest | modest | ✅ fast (~1–3 s) | `requirements-paddle.txt` |
| `trocr` | TrOCR (Microsoft) | **strong (English)** | ❌ none | ✅ ok (~1–4 s/line) | `requirements-trocr.txt` (+paddle for detection) |
| `surya` | Surya 2 (datalab) | **strong** | ✅ good | ⚠️ slow (~10–60 s/page, needs llama.cpp) | `requirements-surya.txt` |
| `chandra` | Chandra 2 (datalab) | best | best | ❌ impractical (4B VLM → GPU/API) | API: none · local: `requirements-chandra.txt` |
| `paddleocr-vl` | PaddleOCR-VL (Baidu) | **strong** | ✅ good | ❌ impractical (~0.9B VLM → GPU) | ships in `paddleocr` (`pip install -U paddleocr`) |
| `auto` | best-of installed | — | — | runs candidates, keeps best | — |

> **PaddleOCR-VL** is a vision-language model that parses the whole page (layout +
> text) at once, more accurate on messy handwriting and structure than classic
> PP-OCRv5. It needs a GPU to be usable; on a CPU it runs at minutes per page.
> It is already wired and reported by `/health`, so on a GPU box you just set
> `VAHINI_OCR_BACKEND=paddleocr-vl`. The model weights download on first use.

**Reaching ~90% handwriting accuracy:** realistic on **neat English** with
`trocr`. For **messy or Telugu/Indic** handwriting no CPU engine reliably hits
90% — `surya` is the best CPU-viable option; `chandra` (the only "best
available") needs a GPU or the hosted API. See the model comparison in
[`../../docs/VISION-MODELS.md`](../../docs/VISION-MODELS.md).

### Speed vs accuracy knobs (paddle path)

The default balances both on CPU: a **fast mobile detector** plus an **accurate
server recogniser**.

| Env var | Default | Effect |
|---|---|---|
| `VAHINI_OCR_DET_MODEL_NAME` | `PP-OCRv5_mobile_det` | detection. `PP-OCRv5_server_det` is more accurate but ~10x slower on CPU (only worth it on a GPU). |
| `VAHINI_OCR_REC_MODEL_MAP` | `en:PP-OCRv5_server_rec,te:te_PP-OCRv5_mobile_rec` | recognition. The server rec reads handwriting better than mobile at ~2x cost. |
| `VAHINI_OCR_VARIANTS` | `2` | max preprocessing variants (built lazily; faint pages may use more). |

On a sharp single page this lands around 10-15 s on a modest CPU. Genuinely
messy cursive has a hard ceiling regardless of model; the two paths past it are
(1) the **reference-passage** feature (when the writer copies a known passage,
the recognised text can be aligned to it for near-perfect letter checks) and
(2) a **GPU VLM** (`paddleocr-vl` / `chandra`).

### GPU vs CPU (auto-detected)

Every engine (paddle, trocr, surya, chandra) picks its device automatically:
if this machine has a GPU that the installed build can actually reach, it's
used; otherwise the engine runs on CPU. No configuration needed on either
kind of machine.

| Env var | Effect when set to `1` / `0` |
|---|---|
| `VAHINI_OCR_GPU` | force paddle (and `paddleocr-vl`) onto GPU / CPU |
| `VAHINI_TROCR_GPU` | force trocr onto GPU / CPU |
| `VAHINI_SURYA_GPU` | force surya onto GPU / CPU |
| `VAHINI_CHANDRA_GPU` | force chandra's `hf` method onto GPU / CPU |

Leave the variable unset to auto-detect (the default and the recommended
setting). `docker compose` sets `VAHINI_OCR_GPU=0` explicitly, because the
shipped image installs the CPU-only `paddlepaddle` wheel; see
`requirements-paddle.txt` to switch to `paddlepaddle-gpu` for a GPU build.
`/health` reports both the resolved choice (`gpu`) and whether an NVIDIA GPU
was found on the machine at all (`gpu_detected`), so you can tell "no GPU
here" apart from "a GPU is here, but this engine's build can't use it."

### Multiple analyses at once

Several users (or browser tabs) analysing at the same time run concurrently,
not one after another: `/ocr`, `/analyze-vl` and `/report-python` offload
their CPU-heavy work to a thread pool, so the server keeps answering
`/health` and other requests while an analysis is in flight. Calls that share
the same cached engine instance (the common case: repeated requests in the
same language) are serialized internally to avoid running one engine
concurrently on itself; different languages or different engines still run
in parallel.

### How `trocr` mode works — guarded refinement (no hallucinations)

Setting `VAHINI_OCR_BACKEND=trocr` does **not** hand the whole page to TrOCR.
PaddleOCR still does detection **and** the printed/handwriting classification
(which we trust). TrOCR then re-reads each *handwriting* crop at **full
resolution**, and its text is accepted **only when it's at least ~70% similar to
paddle's reading** (`VAHINI_REFINE_MIN_SIM`, default `0.70`). This keeps the real
corrections — `manay ment → "management"`, `Midical → "medical"` — and rejects
TrOCR's out-of-distribution hallucinations — `Hypothyoidum → "Transportation
legislation"`, which falls back to paddle. Net: strictly better reading, no
regressions.

### Baking engines into the Docker image

The analyser image ships **PaddleOCR + TrOCR** by default; Surya is opt-in
(it adds a source-built `llama-server` and is slow on CPU):

```bash
# default — paddle + trocr
docker compose build analyser
# also bake Surya (heavy: compiles llama.cpp; minutes/page on CPU)
docker compose build analyser --build-arg VAHINI_WITH_SURYA=1
# then enable it at runtime
#   environment: VAHINI_OCR_BACKEND=surya
```

Build args: `VAHINI_WITH_TROCR` (default 1 in compose), `VAHINI_WITH_SURYA`
(default 0). The TrOCR model is pre-downloaded into the image so the first
request is fast.

### Running Chandra on a CPU-only box

Chandra is a 4-billion-parameter vision-language model. It cannot run usably on
this laptop. Pick how it executes with `VAHINI_CHANDRA_METHOD`:

```powershell
# Recommended on CPU: the hosted Datalab API (no model download, fast, accurate).
$env:VAHINI_OCR_BACKEND   = "chandra"
$env:VAHINI_CHANDRA_METHOD = "api"          # api | vllm | hf
$env:DATALAB_API_KEY      = "<your key>"     # images leave the machine — consent!
```

`vllm` needs a GPU; `hf` runs locally via `transformers` but is impractical on
CPU (minutes/page, RAM-tight). The toggle is wired so you can switch Chandra on
later when a GPU or API key is available, without touching code.

### Tuning the printed-vs-handwriting split

On mixed pages (forms, prescriptions) the server now classifies each detected
region as **printed** or **handwriting** (stroke-width / glyph-height / edge /
confidence features in `classify.py`) so the recognition text, the orange word
boxes, and the per-factor reference crops use **handwriting only**. Nudge the
decision with `VAHINI_PRINTED_THRESHOLD` (default `0.58`; higher = keep more as
handwriting).

> After editing anything under `analyser/src/`, rebuild the browser bundle:
> `python analyser/build_bundle.py` (see `../../docs/BUILD.md`).

---

## The two options, and which one works

| | **Server-side** (recommended) | **Client-side** (in the browser) |
|---|---|---|
| Where the model runs | On a machine **you** control — e.g. a box behind `vahinitech.com` | Inside each visitor's browser tab |
| What ships to the user | Nothing extra — just a normal web request | The model weights (tens of MB) download to every visitor |
| PP-OCRv5 support | ✅ Full PaddleOCR / PP-OCRv5, all languages incl. Telugu | ⚠️ Needs an ONNX/Paddle.js port + WASM runtime; heavy, slower, limited |
| Accuracy / speed | Best (real PP-OCRv5, optional GPU) | Lower; constrained by the browser |
| Effort | Run the service in this folder | A separate, much larger build |

**Recommendation: server-side.** "Server" here means a small Python service running on
your infrastructure (the same place that serves `vahinitech.com`, or a sibling box).
The browser just sends the photo to it and gets text back. This is what the Vahini
front-end is **already wired for** — it was only missing the server, which is now in
this folder.

> **Why not client-side?** PP-OCRv5 is a PaddlePaddle deep-learning model. To run it
> *in the browser* you must convert it to ONNX and ship it with a WASM inference
> runtime (`onnxruntime-web`) — every visitor downloads ~tens of MB and recognition
> is slower and less capable. It's a real project on its own. Start with server-side;
> add a browser fallback later only if you need fully-offline recognition.

---

## What "download the model" actually means

You do **not** hand-download model files. The `paddleocr` Python package fetches the
PP-OCRv5 detection + recognition weights **automatically** the first time each
language is used, and caches them. So:

- First `/ocr` request for a language → slow (it downloads the weights once).
- Every request after that → fast.

To pre-download at deploy time (so the first user isn't slow), see **Warm-up** below.

---

## Run it (server-side)

```bash
cd server
pip install -r requirements.txt
python ppocr-server.py          # serves http://0.0.0.0:8868/ocr
```

or with Docker:

```bash
docker build -t vahini-ocr ./server
docker run -p 8868:8868 vahini-ocr
```

To preload PP-OCRv5 models into the image at build time:

```bash
docker build --build-arg VAHINI_OCR_PRELOAD_LANGS=en,te -t vahini-ocr ./server
```

This bakes model caches into the image (`/opt/paddle-models`) so first-request
latency is removed on new deployments.

## Keep models on server disk (recommended)

Instead of re-downloading models in every container/image, keep Paddle cache on
the server and mount it into OCR containers.

1. Seed cache once from a running OCR container:

```bash
mkdir -p /home/vishnu/paddle-models
docker cp vahini-vd-ocr:/root/.paddlex /home/vishnu/paddle-models/.paddlex
```

2. Run OCR with mounted cache:

```bash
docker run --rm -p 8868:8868 \
    -e PADDLE_PDX_CACHE_HOME=/opt/paddle-models \
    -v /home/vishnu/paddle-models/.paddlex:/opt/paddle-models \
    vahini-ocr
```

This avoids repeated model downloads and keeps startup stable across rebuilds.

One-command prewarm helper from the repository root:

```bash
./deploy/prewarm-models.sh stag en,te,hi,ta,kn,ml
./deploy/prewarm-models.sh prod en,te
```

This script ensures the analyser container is running, then executes
`warmup_models.py` inside it while writing model cache to
`/home/vishnu/paddle-models/.paddlex`.

Check it:  `curl http://127.0.0.1:8868/health`

## Functional regression tests

Run the Python functional regression suite for OCR, context-vision/OpenCV,
and frontend compatibility contract checks:

```bash
cd server
python3 -m pip install -r requirements.txt
python3 -m unittest -v tests/test_regression_functional.py
```

The suite validates:

- `/health` availability
- `/ocr` response contract (`rec_texts`, `rec_polys`, `rec_scores`, `full_text`)
- `/analyze-vl` context/layout/region-preview payload
- OpenCV path resilience (including fallback behavior)
- Contract compatibility expected by the existing 20-factor frontend pipeline

**Warm-up (optional, recommended for prod):**
```bash
python -c "from paddleocr import PaddleOCR; [PaddleOCR(lang=l) for l in ['en','te']]"
```

---

## Point the website at it

The front-end (`src/engine/ocr.js`) already tries, in order:
1. `window.VAHINI_OCR_ENDPOINT` (if you set it), then
2. `/ocr` (same-origin reverse proxy), then
3. `http://127.0.0.1:8868/ocr` (local dev).

It sends `multipart/form-data` with `image`, `lang`, `det`, `rec`, and understands the
PP-OCRv5 response this server returns. So you only need to set the endpoint in
production. On `vahinitech.com`, add **one line** before the engine bundle loads:

```html
<script>window.VAHINI_OCR_ENDPOINT = "https://vahinitech.com/ocr";</script>
```

…and reverse-proxy `/ocr` to the Python service (keeps it same-origin, so no CORS):

```nginx
# add inside the vahinitech.com server { } block
location /ocr {
    proxy_pass         http://127.0.0.1:8868/ocr;
    proxy_read_timeout 30s;
    client_max_body_size 15m;
}
```

If you serve OCR from a different origin instead, set `VAHINI_OCR_ORIGINS` on the
Python service to your site origin so the browser is allowed to call it.

### Telugu and other Indic scripts
Pass `lang` on the request (the front-end currently sends `en`). To recognise the
printed Telugu on a prescription, call with `lang=te`. You can also run language
auto-detection in front of this, or send `lang` from the UI per upload. Supported
examples: `te` Telugu · `hi` Hindi · `ta` Tamil · `kn` Kannada · `ml` Malayalam · `en`.

> To change the language the site requests, edit the `fd.append('lang', 'en')` line
> in `src/engine/ocr.js` (then rebuild the bundle), or expose a language picker.

---

## Important: recognition is assistive, not the score

OCR tells the engine **which characters** were written. It is layered in to label
evidence and (later) drive shape-matching — it is **never** the basis of a
handwriting factor score. The 20 geometric factors are measured from pixels
regardless of OCR. So adding this server improves *labels and print/handwriting
separation*, not the core measurements.

---

## Alternative engines: Chandra 2, Surya 2, TrOCR (now built in)

These are no longer a "wire it yourself" task — each is a first-class adapter in
`ocr_backends.py` and maps its output to the same `{rec_texts, rec_polys,
rec_scores}` shape, so the front-end never changes. Switch with
`VAHINI_OCR_BACKEND` (see **Quick start** above):

- **Chandra 2** (Datalab) — strongest handwriting + Indic, 90+ languages, layout
  output. Hosted API (`VAHINI_CHANDRA_METHOD=api` + `DATALAB_API_KEY`) or local
  GPU (`vllm`). Trade-off: API cost + data leaves your servers.
- **Surya 2** (Datalab) — lighter multilingual/Indic handwriting model that runs
  on CPU via llama.cpp; the best CPU-viable Indic option.
- **TrOCR** (Microsoft) — pure-`transformers` English-handwriting recogniser;
  reuses paddle's detector. The best bang-for-buck handwriting upgrade on CPU.

Self-hosted **PP-OCRv5** stays the free, private default. Pick per cost/privacy/
accuracy — all four fit the same socket.

---

*PaddleOCR is Apache-2.0 (see `/THIRD-PARTY-NOTICES.md`). This service code is
proprietary to Vahini Technologies.*
