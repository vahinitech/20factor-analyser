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

After pulling changes or editing a Dockerfile/requirements file, rebuild
clean instead of relying on cached layers:

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

Check it: `curl http://localhost:8080/health` lists every engine and whether
it can run on this machine.

The server speaks plain HTTP. `https://localhost:8080` cannot work (the TLS
handshake fails before any redirect could run), so make sure the address bar
says `http://`. Terminate TLS in a reverse proxy if you need HTTPS.

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
| `layout_filter.py` | Negative pre-filter dropping photos/seals/charts before classification |
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
`GET /health`'s `adaptive_engine_speed` field to see the actual measured
milliseconds per line and whether each engine is currently considered fast
enough on this box.

**Proof a specialist engine actually ran, not just that hybrid mode was
requested:** `POST /report-python`'s response has
`analysis.recognition.refined_by` — a count per engine of how many
handwriting lines it actually refined this scan (e.g.
`{"trocr": 4, "surya": 1}`), and `refined_lines` for the total. An empty
`{}` means no specialist touched any line this scan — check three things
in order: (1) `VAHINI_OCR_BACKEND` is actually `hybrid` or `trocr` (the
default is `paddle`, which never refines anything); (2) `GET /health`
lists `trocr`/`surya` as available, not skipped (they must be baked into
the image via `VAHINI_WITH_TROCR=1`/`VAHINI_WITH_SURYA=1`); (3)
`adaptive_engine_speed` hasn't marked the engine too slow on this machine
(see above).

### Layout pre-filter (excludes photos, seals, charts — never handwriting)

Before a page's detected lines reach the printed/handwriting classifier,
an optional pass using PaddleOCR's own document-layout model (PP-DocLayout)
drops anything that clearly isn't ink-on-paper content at all: photos,
figures, charts, seals/stamps, and decorative header/footer images (e.g. a
printed letterhead crest). It is a NEGATIVE filter only — it never
restricts analysis to "text-labelled" regions, because that would also
throw away genuine handwritten formulas and filled-in table cells, which
PP-DocLayout tags `formula`/`table` regardless of whether a pen or a
printer produced them. Those categories, along with captions and titles
(a student's own handwritten caption is real text, not decoration), are
always kept.

This does not replace `classify.py`: PP-DocLayout's categories are
document structure (title, text, table, formula, image, seal...), not a
printed-vs-handwriting signal.

Same speed-adaptive shape as hybrid mode, applied to picking a model
size instead of an engine: tries the more accurate `PP-DocLayout-M` first,
falls back to the cheaper `PP-DocLayout-S` if a real measured call is too
slow, and disables filtering entirely (falls back to today's unfiltered
behaviour) if even that is too slow — never a hard requirement. Building
the model itself never blocks a request either: the first time it's
needed, a background download starts and that request (and every one
after it, until the download finishes) simply skips filtering for free.
Run `python warmup_models.py` (or let the Docker image's startup warmup
do it) so it's normally already built by the time real traffic arrives.
Both model tiers are a few MB and download to the same model cache as
PaddleOCR, so they persist across restarts the same way (see "Keep models
on disk between deployments" below).

| Env var | Default | What it does |
|---|---|---|
| `VAHINI_LAYOUT_FILTER` | `1` | turn the layout pre-filter off with `0` |
| `VAHINI_LAYOUT_MAX_MS` | `800` | above this measured latency, drop from `PP-DocLayout-M` to `-S`, then to no filtering |

Check `GET /health`'s `layout_filter` field for whether it's enabled and
which model tier is actually built and ready on this machine.

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

## Benchmarks

Real, measured numbers only — this project's whole premise is auditable
geometry over guesswork, so a made-up speed table would contradict that.
Run it yourself and paste the output here (or open a PR):

```bash
pip install -r analyser/server/requirements-core.txt   # + whichever engine tiers you want measured
python analyser/server/benchmark_ocr.py
```

It runs the SAME production code path (`recognizer.collect_lines_paddle` /
`recognizer.backend_recognize`) against the pages already committed under
`tests/fixtures/samples/`, times every call, and prints a Markdown table:
engine, sample, lines found, detection/recognition/total time, mean
confidence. Engines you haven't installed are skipped with a note, not an
error. See the script's own header comment for exactly what "detection"
vs "recognition" means for a recogniser-only engine like TrOCR or Surya
(PaddleOCR's API doesn't expose them as separately timeable steps, so one
of the two is an estimate — clearly labelled as such in the output).

`--samples <dir>` points it at a different folder of images, `--limit N`
caps how many it runs, `--lang en|te|hi|...` picks the language.

_No results are published here yet — be the first to run it on real
hardware and send a PR with your table and CPU/GPU details._

## Tests

```bash
pip install -r analyser/server/requirements-core.txt
python -m unittest -v \
  analyser.server.tests.test_backends_classify \
  analyser.server.tests.test_server_pipeline \
  analyser.server.tests.test_regression_functional \
  analyser.server.tests.test_handwriting_only
```

The suite covers the response contracts, the printed/handwriting split, the
20-factor pipeline, engine failure recovery, the reference-image guarantees
and the handwriting-only rule (printed text is never analysed; fully printed
pages are refused with `no_handwriting`). It does not need paddle or torch
installed.

## One honest note

OCR here is assistive. It labels what was written so the report can show it.
It is never the basis of a factor score; the 20 factors are measured from the
pixels whether or not any engine could read the words.

*PaddleOCR is Apache-2.0, see /THIRD-PARTY-NOTICES.md.*
