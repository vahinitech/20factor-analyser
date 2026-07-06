# Roadmap and honest capability matrix

What the report actually does today, what a human coach would notice that
Vahini does not check yet, and the open gaps in priority order. Companion to
`ARCHITECTURE.md` (how it works) and `VISION-MODELS.md` (which OCR engine).
Last reviewed July 2026.

## Does Vahini read the page like a human coach would?

A human coach reads line by line and notices spelling, punctuation,
grammar, mixed cursive and print, stray capitals, inconsistent
letterforms, open loops, baseline drift, and spacing. Here is what Vahini
checks for each, and the condition under which it runs.

| What a coach notices | Vahini today | How | Runs when |
|---|---|---|---|
| Neatness, size evenness | Done | factors 5, 20, geometry | every scan |
| Baseline drift, wavy lines | Done | factors 7, 11, geometry | every scan |
| Word and letter spacing | Done | factors 8, 9, geometry | every scan |
| Slant consistency | Done | factor 17, geometry | every scan |
| Open vs closed loops | Done | factor 3, a proxy from which letters OCR read, not per-letter contour tracing | needs recognised text |
| Line quality, shakiness | Done | factor 4, stroke-width variance | every scan |
| Grammar, phrasing | Done | `craft.js` rules | needs recognised text with reasonable confidence |
| Homophones (your/you're, its/it's) | Done | `craft.js` rules | needs recognised text |
| Missing apostrophe, comma, full stop | Done | `craft.js` | needs recognised text |
| Letter formatting, sign-off | Done | `craft.js` | letter-type documents only |
| Mixed cursive and print, stray capitals, per-letter shape variance | Not done | was a browser-side pass (`letters.js`), removed when scoring moved server-side | — |
| Spelling mistakes | Not done | same as above | — |
| Telugu, Hindi letter reading | Partial | the recognition server, engine and accuracy vary by script | needs recognition server |

The geometry factors run on every scan and do not depend on reading the
words correctly. The recognised-text checks (`craft.js`, grammar and
homophones) only run once the recognition server returns text with
reasonable confidence. See the root README's "What the geometry actually
checks" section for exactly which factors read pixels versus which lean on
OCR text as a secondary signal.

## What works today

- **20-factor geometry engine.** Deterministic computer vision, not a
  language model. Runs on the recognition server
  (`backend/ppocr-server.py`); the browser sends the photo and
  renders the result.
- **Handwriting-only rule.** Printed text is detected and excluded from
  scoring and from the reference crops shown as evidence. Never scored,
  never shown as a handwriting sample.
- **Pluggable OCR backends.** PaddleOCR (PP-OCRv5/v6) is the default and
  reads printed text well. Hybrid mode adds TrOCR for English handwriting
  and Surya for Telugu, Hindi, Tamil, Kannada and Malayalam, routed per
  line by script, and only re-reads lines paddle already classified as
  handwriting. A CPU-speed check decides per engine whether to use it at
  all on this machine, measured, not guessed.
- **Layout pre-filter.** A document-layout model drops photos, seals,
  charts and letterhead images before recognition, so a scanned exam paper
  with a printed logo does not get scored on the logo.
- **Document-type detection.** Prose, short-answer, numeric, figures,
  sparse, each with its own accuracy expectation.
- **Sample-quality gate.** Good, usable or limited, with retake tips.
  Rejects a page with no detectable handwriting.
- **Auto-deskew.** Removes the median line tilt, which mostly comes from
  photographing at an angle rather than the writing itself.
- **Writing-craft layer** (`craft.js`). Grammar, homophones, formatting,
  sign-offs, completeness, on the recognised text only.
- **Personalised drills.** Up to three, chosen from the lowest-scoring
  factors on this specific scan, not generic.
- **Growth forecast.** A learning-curve projection over 8 weeks of
  practice, labelled as an estimate.
- **Progress vs last scan.** Per-section deltas, stored locally on the
  device.

## Known gaps

| Gap | Impact | Fix |
|---|---|---|
| Letter-level findings retired | Style mix, stray capitals, letterform variance and punctuation audit no longer run; these were a browser-side pass (`letters.js`) with no server equivalent | Reimplement server-side once there is budget for it |
| No spelling check | Spelling mistakes are not flagged at all | Same rewrite as above, or a dictionary pass on recognised text |
| Feedback endpoint not centralised | Lead-capture data from the PDF download dialog is stored in the browser's local storage and posted to `/persist/feedback`, but nothing in this repo implements that service | Deploy `docs/feedback-email-backend.gs` (or an equivalent) and point the deployment's reverse proxy at it; see `docs/PERSISTENCE-VOLUMES.md` |
| No real IMU pen data | The four Dynamics factors are estimated from a photo, not measured from pen motion | Capture from the dual-IMU sensor pen |
| Indic geometry thresholds tuned on Latin samples | Telugu and Hindi quality scores are less reliable than English | Refit the reference bands on Indic handwriting samples |
| Letter-shape factors assume Latin letterforms | Loop closure and ascender/descender proxies (a/o/e/g, b/d/f/h/k/l/t/g/j/p/q/y) are not meaningful for Telugu | Script-aware letter models |
| No calibration against human coach ratings | Two blended factors use fixed weights, not a model fit to how a coach would actually score them | Collect rated samples, fit a regression |
| No perspective correction to real-world units | Sizes and margins are relative to the page image, not millimetres | Page-quad unwarp on the server |

## Priorities

### Near-term
1. Collect 50 to 100 real Telugu and English handwriting samples and
   measure true per-line OCR accuracy. Everything below depends on having
   real numbers here instead of estimates.
2. Deploy the feedback endpoint so lead-capture data is centralised
   instead of living only in the browser.
3. Reimplement a server-side pass for the retired letter-level findings
   (style mix, stray capitals, spelling), the single biggest gap against
   what a human coach checks.

### Mid-term
4. Refit geometry reference bands on Indic samples.
5. Perspective unwarp to real-world millimetres, fixing the size and
   margin distortion a hand-held photo introduces.
6. Calibrate the two blended factors against real coach ratings.

### Longer-term
7. Live IMU pen integration for real Dynamics factors, not estimates.
8. Script-aware letter models for the loop-closure and letter-formation
   factors across Telugu, Hindi, Tamil and Kannada.
9. Age and grade norm bands, and behaviour indicators such as hesitant or
   rushed writing, only once real IMU data exists, and always labelled as
   indicators, never as a diagnosis.

### Out of scope
Graphology and personality inference. Not evidence-based, and against
Vahini's non-diagnostic stance.

## Why the pen matters beyond one user

There is no large public dataset of Telugu or Hindi handwriting captured
with pen motion, not just an image of the result. Every scan with the
sensor pen builds toward the first one, and that dataset is what
eventually lets Vahini tune geometry bands per script, improve OCR for its
own users, and train real Dynamics models from measured pressure and
speed instead of estimating them from a photo.
