# Vision and OCR models: options and what shipped

Plain-language comparison of the recognition engines Vahini can use, what
each is good at, and how accurate they are on handwriting and on Telugu
and Hindi specifically. Last reviewed July 2026.

Read this first: OCR in Vahini is auxiliary. It powers the reading layer,
which words were written, spelling, the writing-craft checks. It does not
compute the 20 handwriting quality scores. Those come from geometry
(size, spacing, baseline, slant, loops) and need no OCR at all. A better
OCR engine improves the spelling and word-identification layer. It does
not change the neatness or spacing scores.

## The two jobs, kept separate

| Job | What it answers | Where it runs | Needs OCR |
|---|---|---|---|
| Quality measurement (the 20 factors) | How neat, even, straight and well-spaced is the writing | The server's computer-vision pipeline (`backend/scoring.py`, `geometry.py`, `computer_vision.py`) | No |
| Reading (words, spelling, craft) | Which letters and words are these, and are there spelling or grammar issues | The OCR backend registry (`backend/reading/ocr_backends.py`) | Yes |

Everything below is about the second job.

## What is deployed today

**PaddleOCR (PP-OCRv5, optionally PP-OCRv6) is the default engine and
always runs.** It detects every line on the page and reads it, and its own
classifier separates printed from handwritten lines. It is CPU-only, self-hosted,
and free (Apache-2.0). Public Telugu and Devanagari handwriting training
sets are small, a few thousand line images, so its Indic handwriting
accuracy is usable but modest, not the strongest available.

**Hybrid mode adds two recognisers for handwriting specifically.** Paddle's
detection and printed-vs-handwriting split are kept either way; only lines
paddle already classified as handwriting get a second read. TrOCR
(Microsoft, `microsoft/trocr-base-handwritten`) handles English. Surya
handles Telugu, Hindi, Tamil, Kannada and Malayalam. Both are CPU-capable,
free, and self-hosted, at the cost of extra CPU time per line. Every
handwriting line is re-read on every scan: a speed check used to turn an
engine off on a slow box, so the same photo read differently under load
(#112). It now only reports speed in `/health`; a machine too slow for
hybrid mode should run `paddle`.

Which engine reads which script, and the model ids, live in one committed
table, `backend/languages/stages.json` (design: `docs/20-languages.md`,
sections 6 and 17, in #205; #208). Its
quality, cost and memory figures are marked `unmeasured` until they are
measured on stage.

**Reference-passage alignment is the single biggest accuracy win, and it
costs nothing extra.** When a writer copies a known passage, the
recognised text is matched against the expected text directly. A close
match replaces the raw OCR output with the known-correct text and yields
a real per-line accuracy score. This works with any of the engines above.

## Why Chandra OCR is not in the deployed set

Chandra OCR 2 (Datalab) was evaluated: a vision-language model with
strong accuracy on Indic-script handwriting, including large reported
gains over its previous version on Telugu, Kannada, Tamil, Malayalam and
Bengali. It needs a GPU (roughly H100-class) to self-host, or Datalab's
paid hosted API. This deployment has neither: no GPU in the target
environment, and a hosted API means handwriting images, often children's
handwriting, leave the server. Given that constraint it was removed
entirely rather than kept as a dead, unusable option. If a GPU budget or
an acceptable hosted-API privacy review ever exists, it remains the
strongest known option for Indic handwriting specifically and worth
revisiting then.

## Side by side

| | PaddleOCR (PP-OCRv5/v6) | TrOCR | Surya | Chandra OCR 2 | Cloud APIs |
|---|---|---|---|---|---|
| English print | Very good | Good | Good | Excellent | Excellent |
| English handwriting | Good | Strong | Good | Excellent | Very good |
| Telugu/Hindi print | Good | Weak/none | Good | Excellent | Mixed |
| Telugu/Hindi handwriting | Modest | Weak/none | Good | Best available | Weak to mixed |
| Runs offline on CPU | Yes | Yes | Yes, but slower | No, needs a GPU | No, cloud only |
| Keeps data on your server | Yes | Yes | Yes | Self-host only | No |
| Cost | Free | Free | Free | Free weights or paid API | Per page |
| Deployed in this repo | Yes, default | Yes, opt-in build arg | Yes, opt-in build arg | No, removed | No |

## Recommendation, in order

1. PaddleOCR self-hosted is the baseline and always on. Free, CPU-friendly,
   handles English, Telugu and Hindi, and data never leaves the server.
2. Turn on hybrid mode (`VAHINI_OCR_BACKEND=hybrid`, built with
   `VAHINI_WITH_TROCR=1` and `VAHINI_WITH_SURYA=1`) once English or Indic
   handwriting reading quality matters more than the extra CPU cost of
   the specialist recognisers. See [Engine settings and modes](#engine-settings-and-modes).
3. Collect real Telugu and English handwriting samples and measure actual
   per-line accuracy. This is the basis for deciding whether the current
   engines are good enough, not a guess.
4. Revisit Chandra OCR only if a GPU budget exists and Indic handwriting
   accuracy is still the bottleneck after real measurement. Trial on
   non-personal samples first if using the hosted API.
5. Keep building the sensor-pen dataset regardless. Every capture is
   labelled Indic-handwriting motion data, the asset that eventually lets
   Vahini fine-tune any of these engines for its own users. See the "data
   moat" section in `16-roadmap.md`.

Privacy guardrail: Vahini's promise is that handwriting images are
processed and not retained. Every engine listed as deployed upholds that.
Any cloud API or hosted model means images leave the server; only adopt
one with explicit consent and a privacy review first.

## Glossary

- OCR: optical character recognition, software that turns an image of
  text into characters.
- Vision-language model (VLM): a neural model that looks at an image and
  produces text or structure directly. Chandra 2 is one. Heavier and more
  capable than classic OCR, usually needs a GPU.
- Detector vs recogniser: classic OCR finds where text is first, the
  detector, then reads each line, the recogniser. PaddleOCR, TrOCR and
  Surya all work this way in this deployment (paddle detects, whichever
  engine reads). A VLM like Chandra does both at once.
- Self-host: run the model on your own machine, so data never leaves it.

Companion to `04-algorithms-plain-guide.md` and `16-roadmap.md`.

## Engine settings and modes

Moved here from `backend/README.md` when the backend was sorted into folders.

### OCR engines

Pick the engine with one env var: `VAHINI_OCR_BACKEND`.

| Value | Engine | Best at | CPU speed | Install |
|---|---|---|---|---|
| `paddle` (default) | PaddleOCR PP-OCRv5 | printed text, fast private default | 1 to 3 s | `requirements/paddle.txt` |
| `trocr` | TrOCR (Microsoft) | English handwriting | 1 to 4 s/line | `requirements/trocr.txt` |
| `surya` | Surya 2 (Datalab) | multilingual and Indic handwriting | slow | `requirements/surya.txt` |
| `hybrid` | paddle + trocr + surya | mixed pages: printed AND handwriting, any of the languages above | 1 to 4 s/handwriting line | `requirements/trocr.txt` + `requirements/surya.txt` |
| `paddleocr-vl` | PaddleOCR-VL | strong handwriting, needs GPU | impractical | ships in `paddleocr` |
| `auto` | best of the installed engines | | | |

Every engine maps to the same response shape, so the app never changes when
you switch. In `trocr` and `hybrid` mode, paddle still detects and classifies
every line (that decision stays centralised in `classify.py`); only the
*handwriting* lines get re-read by a specialist, and paddle keeps doing what
it's already good at on the printed ones. `trocr` mode always re-reads with
TrOCR; `hybrid` mode picks the specialist per line by script: English to
TrOCR, Telugu/Hindi/Tamil/Kannada/Malayalam to Surya: so a mixed-language
page gets the right engine for each line instead of one engine for the whole
page.

That routing, and the model each engine reads with, is data:
`backend/languages/stages.json` (checked against `stages.schema.json` when
the server starts). Its `scripts` part lists the languages of each script
and the engine that re-reads that script; a language it does not name reads
as Latin, so it goes to TrOCR. Its `stages` part has one entry per engine,
script and device with the facts the ladders (#219) will be built from:
quality, cost, memory, threads and maturity, all `unmeasured` until
`backend/tools/load_test.py` and the benchmark measure them on stage. The default
Paddle recognition models (`VAHINI_OCR_REC_MODEL_MAP`) and the TrOCR model
(`VAHINI_TROCR_MODEL`) come from the same file, and both variables still
override it. `GET /health`'s `recognition` field gives the file's sha256
and the device each engine resolved to (`null` until the engine is built).

`backend/languages/ladders.json` is built from that table by
`python scripts/rank_stages.py` and committed (#219, design in
`docs/20-languages.md`, section 17.2). For each mode and script it lists
the stages that may read a handwriting line, cheapest first: the Paddle
stage that found the line, then the stages a line is sent up to. In
paddle mode that is Paddle alone, in trocr mode Paddle then TrOCR for
every script, and in hybrid mode the stages ranked by the rules of 17.2.
While a quality or a cost is `unmeasured`, a hybrid ladder cannot be
ranked, so it is the route the stage table names (`basis: route`) and
lists the stages that were not measured. The file records the sha256 of
the stage table it was built from; after any change to `stages.json`,
run the script again and commit both. CI runs it with `--check`.

The re-read text is accepted when EITHER it agrees with paddle's own reading
at least 70% (`VAHINI_REFINE_MIN_SIM`), or the specialist's own confidence is
at least 75% (`VAHINI_REFINE_MIN_CONF`) even if it disagrees with paddle.
Paddle is not a handwriting specialist, which is the whole reason to
re-read. On genuinely hard handwriting, requiring agreement with paddle's
own possibly wrong reading would throw away real corrections, so a
confident specialist reading is trusted on its own. The agreement path
still guards against hallucination on low-confidence, made-up text.

The re-reading is `backend/reading/escalation.py`, driven by `ladders.json`
(`docs/20-languages.md`, section 17.6). Each line climbs its ladder
until a rung's reading passes the acceptance test. No language pack sets
an acceptance limit yet (`reading.accept_confidence`), so a reading is
accepted at the top rung only and every line is re-read, as before. Lines
that reach the same rung on a page go in one call when the engine reads
batches, and answers are cached per loaded engine by the crop's hash,
the stage version and the prompt version. If a line needs an engine that
cannot answer (not installed, failing, or a remote stage whose circuit
breaker is open), the page is refused with `ocr_unavailable`, a 503 and
`Retry-After: 60`, on `/ocr`, `/analyze-vl`, `/report-python` and
`/api/v2/reports`. It is not cached and uses no free check. The line is
never left with the lower reading, so one photo always gets the same
score or a "try again". In the legacy payloads, each entry of
`hand_lines` carries `trail` (`ladder`, `tried`, `answered`, `accepted`,
and `held` when a line could not be sent up: `no_crop` or `line_limit`
past 40 lines), and the payload carries `ladder`: the sha256 of
`ladders.json` and `stages.json`, the version of each stage tried, and
how many lines each stage answered.

To bake TrOCR into the Docker image, build with `VAHINI_WITH_TROCR=1` in
`docker-compose.yml`. Surya is `VAHINI_WITH_SURYA=1` (heavy, compiles
llama.cpp). `hybrid` mode needs both.

#### Hybrid mode re-reads every line, every time

Hybrid and trocr modes re-read every handwriting line (up to 40) on every
scan. They used to skip an engine after one line slower than
`VAHINI_HYBRID_MAX_MS_PER_LINE`, for the rest of the page and for
`VAHINI_HYBRID_RETRY_SEC` afterwards, so the same photo could read
differently on a busy server (#112). Speed no longer changes the result.
`GET /health`'s `adaptive_engine_speed` still shows the measured
milliseconds per line, and whether that is under
`VAHINI_HYBRID_MAX_MS_PER_LINE`, so you can see whether this machine can
afford hybrid mode. If it cannot, run `paddle`.

**Proof a specialist engine actually ran, not just that hybrid mode was
requested:** `POST /report-python`'s response has
`analysis.recognition.refined_by`: a count per engine of how many
handwriting lines it actually refined this scan (e.g.
`{"trocr": 4, "surya": 1}`), and `refined_lines` for the total. An empty
`{}` means no specialist touched any line this scan: check three things
in order: (1) `VAHINI_OCR_BACKEND` is actually `hybrid` or `trocr` (the
default is `paddle`, which never refines anything); (2) `GET /health`
lists `trocr`/`surya` as available, not skipped (they must be baked into
the image via `VAHINI_WITH_TROCR=1`/`VAHINI_WITH_SURYA=1`); (3) the
engine's `recognize_crop` did not raise on these lines (a failing call
keeps paddle's reading for that line).

#### Layout pre-filter (excludes photos, seals, charts: never handwriting)

Before a page's detected lines reach the printed/handwriting classifier,
an optional pass using PaddleOCR's own document-layout model (PP-DocLayout)
drops anything that clearly isn't ink-on-paper content at all: photos,
figures, charts, seals/stamps, and decorative header/footer images (e.g. a
printed letterhead crest). It is a NEGATIVE filter only: it never
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
behaviour) if even that is too slow: never a hard requirement. Building
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
