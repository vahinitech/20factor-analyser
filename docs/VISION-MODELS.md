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
| Quality measurement (the 20 factors) | How neat, even, straight and well-spaced is the writing | The server's computer-vision pipeline (`analyser/server/scoring.py`, `geometry.py`, `computer_vision.py`) | No |
| Reading (words, spelling, craft) | Which letters and words are these, and are there spelling or grammar issues | The OCR backend registry (`analyser/server/ocr_backends.py`) | Yes |

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
free, and self-hosted, at the cost of extra CPU time per line, which is
why a per-machine speed check can turn either one off automatically on a
slow box rather than stalling every scan.

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
   the specialist recognisers. See `analyser/server/README.md`.
3. Collect real Telugu and English handwriting samples and measure actual
   per-line accuracy. This is the basis for deciding whether the current
   engines are good enough, not a guess.
4. Revisit Chandra OCR only if a GPU budget exists and Indic handwriting
   accuracy is still the bottleneck after real measurement. Trial on
   non-personal samples first if using the hosted API.
5. Keep building the sensor-pen dataset regardless. Every capture is
   labelled Indic-handwriting motion data, the asset that eventually lets
   Vahini fine-tune any of these engines for its own users. See the "data
   moat" section in `ROADMAP.md`.

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

Companion to `ARCHITECTURE.md` and `ROADMAP.md`.
