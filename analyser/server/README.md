<!-- SPDX-License-Identifier: AGPL-3.0-only
     © 2026 Vahini Technologies. Contact: info@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
     Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json -->
# Recognition server

This folder is the Python service that does all the work: text detection and
recognition (pluggable OCR engines), the printed-vs-handwriting classifier,
and the 20-factor scoring. The browser only uploads the image and renders the
returned report.

## Run it

```bash
# from the repo root
./analyser/server/setup.sh            # venv + core deps + PaddleOCR (default)
python analyser/server/analyser-ocr-server.py
# open http://localhost:8080
```

Or with Docker from the repo root:

```bash
docker compose up -d --build
# open http://localhost:8080
```

Check it: `curl http://localhost:8080/health` lists every engine and whether
it can run on this machine.

Model weights download automatically on the first request for each language
and are cached under `~/.paddlex`. If the machine is offline the scan still
completes: the 20 factors are measured from geometry and the report says that
words were not read.

## Module layout

| File | Job |
|---|---|
| `analyser-ocr-server.py` | Serves the app under `/analyser` plus the APIs below, on one origin |
| `ppocr-server.py` | The API routes: `/ocr`, `/analyze-vl`, `/report-python`, `/health` |
| `config.py` | Every `VAHINI_*` env var, parsed once |
| `ocr_backends.py` | One adapter per OCR engine behind a common interface |
| `detector.py` | Preprocessing variants and candidate region filtering |
| `recognizer.py` | Dispatches recognition across engines, refinement, passage alignment |
| `classify.py` | Printed vs handwriting classifier |
| `computer_vision.py` | Image decode, evidence crops, layout signals, OCR-free fallback |
| `scoring.py` | The 20-factor model and reference values |
| `cache.py`, `geometry.py`, `model_map.py`, `gpu_detect.py` | Small shared helpers |

## OCR engines

Pick the engine with one env var: `VAHINI_OCR_BACKEND`.

| Value | Engine | Best at | CPU speed | Install |
|---|---|---|---|---|
| `paddle` (default) | PaddleOCR PP-OCRv5 | printed text, fast private default | 1 to 3 s | `requirements-paddle.txt` |
| `trocr` | TrOCR (Microsoft) | English handwriting | 1 to 4 s/line | `requirements-trocr.txt` |
| `surya` | Surya 2 (Datalab) | multilingual and Indic handwriting | slow | `requirements-surya.txt` |
| `hybrid` | paddle + trocr + surya | mixed pages: printed AND handwriting, any of the languages above | 1 to 4 s/handwriting line | `requirements-trocr.txt` + `requirements-surya.txt` |
| `paddleocr-vl` | PaddleOCR-VL | strong handwriting, needs GPU | impractical | ships in `paddleocr` |
| `auto` | best of the installed engines | | | |

Every engine maps to the same response shape, so the app never changes when
you switch. In `trocr` and `hybrid` mode, paddle still detects and classifies
every line (that decision stays centralised in `classify.py`); only the
*handwriting* lines get re-read by a specialist, and paddle keeps doing what
it's already good at on the printed ones. `trocr` mode always re-reads with
TrOCR; `hybrid` mode picks the specialist per line by script — English to
TrOCR, Telugu/Hindi/Tamil/Kannada/Malayalam to Surya — so a mixed-language
page gets the right engine for each line instead of one engine for the whole
page.

The re-read text is accepted when EITHER it agrees with paddle's own reading
at least 70% (`VAHINI_REFINE_MIN_SIM`), or the specialist's own confidence is
at least 75% (`VAHINI_REFINE_MIN_CONF`) even if it disagrees with paddle.
Paddle is not a handwriting specialist — that's the whole reason to re-read
— so on genuinely hard handwriting requiring agreement with paddle's own
(possibly wrong) reading would throw away real corrections; a confident
specialist reading is trusted on its own. The agreement path still guards
against hallucination on low-confidence, made-up text.

To bake TrOCR into the Docker image, build with `VAHINI_WITH_TROCR=1` in
`docker-compose.yml`. Surya is `VAHINI_WITH_SURYA=1` (heavy, compiles
llama.cpp). `hybrid` mode needs both.

### Hybrid mode adapts to this machine's real speed

There's no manual "is this box fast enough?" setting. Every re-read is
timed, and the elapsed time is what decides: once an engine measures
slower than `VAHINI_HYBRID_MAX_MS_PER_LINE` (default 2.5s), it's skipped
for the rest of that page and for `VAHINI_HYBRID_RETRY_SEC` (default 10
minutes) afterwards — paddle's own reading is kept instead, and the next
scan tries the specialist again once the cooldown passes. A fast machine
gets every handwriting line re-read; a slow one quietly behaves like plain
`paddle` after the first slow measurement instead of stalling every scan.
So `VAHINI_OCR_BACKEND=hybrid` is safe to set on any machine — check
`GET /health`'s `hybrid_engine_speed` field to see the actual measured
milliseconds per line and whether each engine is currently considered fast
enough on this box.

## Common settings

| Env var | Default | What it does |
|---|---|---|
| `PORT` | `8080` | HTTP port |
| `VAHINI_OCR_BACKEND` | `paddle` | engine, see the table above |
| `VAHINI_OCR_LANGS` | `en,te` | languages to load; request one with `lang=` |
| `VAHINI_OCR_GPU` | auto | force GPU (`1`) or CPU (`0`); unset auto-detects |
| `VAHINI_OCR_VARIANTS` | `2` | max preprocessing variants for faint pages |
| `VAHINI_PRINTED_THRESHOLD` | `0.58` | printed vs handwriting split; higher keeps more as handwriting |
| `VAHINI_OCR_ENGINE_RETRY_SEC` | `300` | how long a failed engine build is remembered before retrying |
| `VAHINI_OCR_ORIGINS` | `*` | CORS allowlist for cross-origin deployments |
| `VAHINI_REFINE_MIN_SIM` | `0.70` | in `trocr`/`hybrid` mode, accept a re-read line if it's at least this similar to paddle's reading |
| `VAHINI_REFINE_MIN_CONF` | `0.75` | in `trocr`/`hybrid` mode, accept a re-read line if the specialist's own confidence is at least this high, even if it disagrees with paddle |
| `VAHINI_HYBRID_MAX_MS_PER_LINE` | `2500` | above this measured latency, hybrid mode stops using that specialist engine until the retry cooldown passes |
| `VAHINI_HYBRID_RETRY_SEC` | `600` | how long a "too slow" verdict is remembered before trying that engine again |

GPU is auto-detected per engine; force it per engine with `VAHINI_OCR_GPU`,
`VAHINI_TROCR_GPU`, `VAHINI_SURYA_GPU`.

## Pointing a website at it

The client tries `window.VAHINI_OCR_ENDPOINT`, then same-origin `/ocr`, then
`http://127.0.0.1:8080/ocr`. In production set one line before the bundle
loads and reverse-proxy `/ocr` to this service:

```html
<script>window.VAHINI_OCR_ENDPOINT = "https://example.com/ocr";</script>
```

Requests are `multipart/form-data` with `image` and optional `lang`
(`en`, `te`, `hi`, `ta`, `kn`, `ml`, or `auto`).

## Keep models on disk between deployments

Mount a host folder over the model cache so containers never re-download:

```bash
docker run --rm -p 8080:8080 \
  -e PADDLE_PDX_CACHE_HOME=/opt/paddle-models \
  -v /srv/paddle-models:/opt/paddle-models \
  vahini/20factor-analyser:local
```

`docker-compose.yml` already does this with a named volume.

## Tests

```bash
pip install -r analyser/server/requirements-core.txt
python -m unittest -v \
  analyser.server.tests.test_backends_classify \
  analyser.server.tests.test_server_pipeline \
  analyser.server.tests.test_regression_functional
```

The suite covers the response contracts, the printed/handwriting split, the
20-factor pipeline, engine failure recovery and the reference-image
guarantees. It does not need paddle or torch installed.

## One honest note

OCR here is assistive. It labels what was written so the report can show it.
It is never the basis of a factor score; the 20 factors are measured from the
pixels whether or not any engine could read the words.

*PaddleOCR is Apache-2.0, see /THIRD-PARTY-NOTICES.md.*
