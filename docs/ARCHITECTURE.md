# Vahini 20-Factor Engine: Architecture & Algorithms

### A plain-language guide to how Vahini reads handwriting

This document explains **how the Vahini engine turns a photo of handwriting (or a pen recording)
into twenty scores and a forecast**: step by step, in everyday language, with the maths kept
honest underneath.

**Who this is for.** You do **not** need to be a programmer or a computer-vision expert. Every
technical term is spelled out the first time it appears, each step has an "**In plain words**"
explanation, and there is a [Glossary](#0-glossary--read-this-first) and an [FAQ](#8-faq) at the end.
If you only read two sections, read the **Glossary** and the **FAQ**.

**Where the code lives** (for developers): the CV pipeline and the 20-factor scoring run
**server-side** in Python; the browser is the recognition client + report renderer.
- `backend/ppocr-server.py`: the thin FastAPI layer serving `POST /report-python` and the
  other recognition endpoints; the CV, OCR and scoring logic itself lives in sibling modules:
  `computer_vision.py` (image decode/crop/layout), `detector.py` + `recognizer.py` (finding and
  reading handwriting across the pluggable `ocr_backends.py` engines), and `scoring.py`
  (`_extract_features` → `_score_factor_map` → `build_analysis`, the 20-factor scorer).
- `frontend/src/report/report-render.js`: renders the report from the server's `analysis`.
- `frontend/src/app/app.js`: capture → upload → render flow (calls `/report-python`).
- `frontend/src/engine/imu.js`: the **IMU pen** (smart pen) live-capture simulation.
- `frontend/src/engine/forecast.js`: projects future improvement from the returned scores.

The algorithm descriptions below explain *what* each step computes; they now run in the server.

A few conventions used throughout:
- Every factor is scored **0–10**. The report sometimes shows `score × 10` as a value out of **100**.
- "**§4C**" points to the engineering reference (the *Algorithm & Model Selection Guide, v3*) that
  defines the **target numbers** (called *bands*) each factor is compared against. Think of §4C as
  the "answer key" the scores are graded with.

---

## 0. Glossary: read this first

| Term / abbreviation | What it means, in plain words |
|---|---|
| **CV** (in "CV pipeline") | **Computer Vision**: software that "looks at" an image and understands its contents (here: finding letters, words and lines in a photo). A **pipeline** is just a series of steps where the output of one step feeds the next. So a **CV pipeline** = "the assembly line that turns a photo into measurements." |
| **CV** (in "coefficient of variation") | Confusingly, *CV* also means **Coefficient of Variation**: a measure of how *uneven* a set of numbers is (see below). Context tells them apart; we write "CV pipeline" for the first and "cv(...)" for the second. |
| **Coefficient of Variation, `cv`** | How spread out numbers are, **relative to their average**. `cv = standard deviation ÷ average`. `cv = 0` means everything is identical (perfectly even); a bigger `cv` means more variation. Example: if every letter is the same height, the height `cv` is near 0 (good for "Size Consistency"). |
| **Standard deviation, `std`** | A standard measure of how much numbers differ from their average. Small = tightly clustered; large = scattered. |
| **Mean / median** | **Mean** = the average. **Median** = the middle value when sorted (more robust to a few odd values). |
| **Tolerance** (`tol_good`, `tol_bad`) | The two cut-off numbers that decide a score. `tol_good` = "this good or better earns full marks." `tol_bad` = "this bad or worse earns zero." Between them the score slides smoothly. Like a teacher saying "≤2 mistakes = A, ≥10 = F, in between graded proportionally." |
| **Error** | How far a measurement is from the ideal. Smaller error = better. |
| **Pixel** | One tiny dot in a digital image. All measurements are ultimately counted in pixels. |
| **Grayscale** | A black-and-white version of the photo (shades of gray, no color). Easier to analyze. |
| **Binarize / threshold** | Turning the gray photo into pure **black ink vs white paper**: every pixel becomes "ink" or "not ink." (More below: Otsu and Adaptive.) |
| **Otsu** | A classic automatic method to choose the brightness cut-off between ink and paper. Named after its inventor, Nobuyuki Otsu. |
| **Adaptive mean threshold** | A smarter cut-off that adjusts across the page: used when lighting is uneven (e.g. a shadow on one side). |
| **Connected components** | Groups of touching ink pixels: i.e. individual letters or marks. "Connected" = the pixels touch each other. |
| **Baseline** | The invisible line writing sits on (like the lines in a ruled notebook). The engine re-discovers it for each line of text. |
| **x-height** | The height of a normal lowercase letter without its tall part or tail (the height of "x", "a", "o"). Used as a natural "ruler" so measurements work at any writing size. |
| **Zones** | Three bands of a line: **upper** (tall parts: l, h, t), **middle** (the body: a, e, o), **lower** (tails: g, y, p). |
| **Slant** | The lean of the letters (upright, leaning right, leaning left). |
| **RMS** | **Root Mean Square**: a way to measure average wobble/deviation that treats above and below equally. Used for "how wavy is the baseline." |
| **OCR** | **Optical Character Recognition**: software that reads the actual *words* in an image (turns handwriting into text). Vahini uses **PaddleOCR** for this when a server is connected. |
| **PaddleOCR** | A well-known open-source OCR system (detects where text is, then reads it). |
| **IMU** | **Inertial Measurement Unit**: a motion sensor that feels movement, tilt and rotation. The Vahini smart pen contains these. |
| **LSM6DSO** | The specific model name of the IMU chip used in the pen (a common 6-axis motion sensor). The pen uses two of them. |
| **Magnetometer** | A sensor that detects direction (like a compass), used to keep the pen's orientation accurate. |
| **Kalman filter** | A maths technique that smooths noisy sensor readings in real time: it removes the "jitter" so the numbers reflect your hand, not electrical noise. Named after Rudolf Kálmán. |
| **Hz (hertz)** | "Times per second." The pen samples at **208 Hz** = 208 readings every second. |
| **Deterministic** | Always gives the **same result for the same input** (no randomness, no guessing). Most Vahini factors are deterministic and so are repeatable. |
| **Proxy** | A stand-in measurement when the ideal one isn't available (e.g. estimating pressure from ink darkness in a photo, because only the pen can truly feel pressure). |

---

## 1. The big picture (one minute)

```
   A photo of handwriting
            │
            ▼
   ┌─────────────────────────────────────────────┐
   │  CV PIPELINE  (server: computer_vision.py,   │
   │  geometry.py, detector.py, recognizer.py)    │
   │  1. Shrink the image (for speed)             │
   │  2. Grayscale  (remove color)                │
   │  3. Binarize   (ink vs paper)                │
   │  4. Connected components (find letters)      │
   │  5. Group letters → words → lines            │
   │  6. Measure: baseline, slant, size, spacing… │
   └─────────────────────────────────────────────┘
            │  (a bundle of measurements)
            ▼
   ┌─────────────────────────────────────────────┐
   │  SCORING  (server: scoring.py)               │
   │  Compare each measurement to its target band │
   │  → 20 scores (0–10) → 4 section averages     │
   │  → one overall score (0–100)                 │
   └─────────────────────────────────────────────┘
            │
            ├──► FORECAST (browser: src/engine/forecast.js): predict improvement
            ▼
   The report
```

**In plain words:** we clean up the photo, find the letters, measure their shapes and spacing, grade
each measurement against a known "good range," then add everything up into a friendly report.

---

## 2. The scoring rules (the heart of everything)

Two small, transparent rules convert any measurement into a 0–10 score. They are deliberately simple
so a coach could redo any score with a calculator.

### Rule A: `score_from_error`: "closer to ideal = higher score"

```
function score_from_error(error, tol_good, tol_bad):
    if error <= tol_good: return 10            # as good as we ask for → full marks
    if error >= tol_bad:  return 0             # clearly off → zero
    return 10 * (tol_bad - error) / (tol_bad - tol_good)   # smoothly graded in between
```

**In plain words:** *"How far are you from perfect?"* If you're within the **good tolerance**, you get
10/10. If you're past the **bad tolerance**, you get 0. Anywhere in between slides proportionally.

**Everyday analogy:** parking a car. Within 5 cm of the kerb = perfect (10). Over 50 cm away = fail (0).
At 27 cm you get a middling score. `tol_good = 5 cm`, `tol_bad = 50 cm`.

### Rule B: `score_from_consistency`: "more even = higher score"

```
function cv(values):                  # Coefficient of Variation = unevenness
    return std(values) / mean(values) # 0 = perfectly even

function score_from_consistency(values, cv_good, cv_bad):
    if fewer than 2 values: return 5             # not enough to judge → neutral
    return score_from_error(cv(values), cv_good, cv_bad)
```

**In plain words:** many handwriting qualities are about **evenness**, not a single ideal number: e.g.
"are all your letters a similar height?" We measure unevenness with the **Coefficient of Variation (cv)**
and feed it into Rule A. Even writing → low `cv` → high score.

### What a "band" is (the source of truth)

For every factor we publish two numbers: either `(tol_good, tol_bad)` or `(cv_good, cv_bad)`. Together
these are the factor's **band**. They come from the §4C reference and are the calibration we grade
against. Tighten a band and scores get stricter; loosen it and they get more generous: predictably.

### Turning a 0–10 score into a label

- **7.5 and above → "Strong"**
- **5.0 to 7.4 → "Developing"**
- **below 5.0 → "Focus area"** (this is what the practice drills target)

---

## 3. The CV pipeline, explained step by step (server: computer_vision.py, geometry.py)

This is the "assembly line" that turns a photo into measurements. Here is each station and **why it
exists**.

### Step 1: Shrink the image
The photo is scaled down so its widest side is about **1100 pixels**. **Why:** phone photos are huge;
shrinking makes everything fast without losing the detail we need. The shape (aspect ratio) is kept.

### Step 2: Grayscale
Convert color to shades of gray using the standard brightness formula
`brightness = 0.299·Red + 0.587·Green + 0.114·Blue`. **Why:** color is irrelevant to handwriting shape;
gray is simpler and faster. (The weights reflect how the human eye perceives each color's brightness.)

### Step 3: Binarize (ink vs paper): **this is where Otsu and Adaptive come in**

We must decide, for every pixel: **is this ink, or is this paper?** That decision needs a *brightness
cut-off* (a "threshold"): darker than the cut-off = ink, lighter = paper. Choosing that cut-off well is
critical: too high and faint strokes vanish; too low and the paper texture becomes fake "ink."

Vahini picks one of two methods automatically:

**(a) Otsu's method: for evenly-lit photos**
> **What it is:** an automatic way to find the single best brightness cut-off for the whole image.
> **How it works (intuition):** a clean handwriting photo has two clumps of pixels: dark ink and light
> paper. Otsu tries every possible cut-off and picks the one that separates those two clumps most
> cleanly (technically, it maximizes the contrast *between* the two groups). **Why we need it:** it
> removes guesswork: the user never has to set a "brightness" slider; it adapts to each photo.

**(b) Adaptive mean threshold: for unevenly-lit photos (shadows, gradients)**
> **What it is:** instead of one cut-off for the whole page, it computes a **local** cut-off for every
> small neighbourhood of the image. **How it works (intuition):** it looks at the average brightness of
> the pixels *around* each pixel and marks ink if the pixel is noticeably darker than its
> neighbourhood. **Why we need it:** if one side of the page is in shadow, a single global cut-off
> would call the shadow "ink." A local cut-off follows the lighting and stays correct everywhere.
> (Implemented efficiently with an "integral image," a standard trick for fast neighbourhood averages.)

**How Vahini chooses:** it checks the four corners of the photo. If their brightness differs a lot, the
lighting is uneven → use **Adaptive**; otherwise → use **Otsu**. The report tells you which was used.

### Step 4: Connected components (find the letters)

> **What it is:** after binarizing, we have a sea of black "ink" pixels. **Connected components** are
> clusters of ink pixels that **touch each other**, and a cluster of touching ink is, usually, one
> letter or mark. **How it works (intuition):** start on an ink pixel and "flood" outward to every ink
> pixel it touches (including diagonals), labelling them all as one group; repeat until every ink pixel
> belongs to a group. **Why we need it:** this is how the engine goes from "raw dots" to "here are the
> individual letters," which everything else is built on. **In plain words:** it's like dropping ink in
> water and circling each separate blob.

Tiny specks (noise) and huge blobs (page-spanning marks, smudges, or **diagrams**) are filtered out by
size, **bounding-box fill ratio and aspect ratio** (a quality-gate adapted from public glyph-analysis
code), which also removes underlines, ruled lines and hairline noise: so only plausible letters remain.

### Step 5: Group letters into words and lines
- **Lines:** letters whose vertical centres are close together belong to the same line of text.
- **Words:** within a line, a horizontal gap wider than a threshold marks a space between words.

**Why:** spacing, margins and baseline only make sense once we know what a "line" and a "word" are.

### Step 6: Measure everything
For each line, the engine now computes the raw numbers the factors need:

- **Baseline (and why it matters).** Using the bottoms of the letters, it fits the best straight line
  through them: that's the **baseline**, the line the writing "sits on." **Why it matters:** the
  baseline is the reference for almost everything: how straight the writing is, whether it drifts
  uphill, and where the three zones (tall parts / body / tails) begin and end. Without a baseline you
  can't tell a tidy line from a wandering one.
- **x-height** (median letter-body height): the natural "ruler" so results work at any writing size.
- **Slant**: the dominant lean of strokes. Found by **shear-search deslanting**: the ink of each word is
  sheared at a set of candidate angles and we keep the angle that makes the vertical strokes most solid
  (strongest vertical projection). This gives one clean slant per word and the true average lean (e.g.
  "8° right"). See §12.1. (A per-pixel gradient method is the fallback for very short samples.)
- **Spacing**: gaps between letters and between words, measured in x-heights.
- **Margins**: where ink starts and ends on the left and right of each line.
- **Zones**: how much writing reaches into the upper (tall) and lower (tail) bands.
- **Loop closure**: whether round letters (a, o, e, g) are properly closed (see Factor 3).
- **Stroke width / ink darkness**: rough stand-ins (**proxies**) for pen pressure when no pen is used.

The result is one bundle of measurements (`metrics`) plus a **document-type** label (see §8) that the
scoring stage reads.

**Note on "deterministic":** all of the above is fixed maths with no randomness, so the **same photo
always produces the same scores**: important for fairly tracking progress over time.

---

## 4. The 20 factors

Each factor below shows: the **input** (what's measured), the **rule** (how it's scored), the **band**
(the target numbers / source of truth), and a **confidence** label. A short *In plain words* line keeps
it human.

**Confidence labels on the report:**
- **Measured**: computed directly from the image geometry (most reliable).
- **From image**: a reasonable estimate from a photo that the pen would measure better.
- **Needs the pen**: a motion quality a still photo can only guess; the IMU pen measures it properly.
- **Estimated**: a transparent blend of simpler measurements (clearly labelled, not a black box).

### Section 1: Structure (30% of the overall score): *letter shapes & control*

**F1 · Letter Formation Accuracy**: *From image*
`size_penalty = cv(letter heights); score = 10 − size_penalty·9 + (loopRatio − 0.85)·4`
*In plain words:* rewards even-sized, well-closed letters. A rough shape-quality proxy; a future version
compares each letter to an ideal template.

**F2 · Stroke Order Consistency**: *Needs the pen*
`score = 6 + (loopRatio − 0.8)·3`
*In plain words:* "did you build each letter in the usual order?" Order happens **in time**, so only the
pen truly sees it; a photo can barely guess.

**F3 · Loop Closure**: *Measured*
```
For each round letter, check whether it encloses a fully surrounded pocket of paper (a closed loop).
loopRatio = closed letters / loopable letters;  score = 10 · loopRatio
```
*In plain words:* are your a, o, e, g actually closed, or left open? Band: ≥95% closed = excellent.

**F4 · Line Quality (Smoothness)**: *Measured*
`jitter = cv(stroke widths); score = score_from_error(jitter, 0.18, 0.70)`
*In plain words:* smooth, steady strokes vs shaky ones. Uneven stroke width = the "wobble" signal.

**F5 · Size Consistency**: *Measured*
`score = score_from_consistency(letter heights, cv_good=0.12, cv_bad=0.45)`
*In plain words:* are all your letters a similar height? Very even = high score.

**F6 · Ascender / Descender Control**: *Measured*
`error = |upperZone − 0.30| + |lowerZone − 0.25|; score = score_from_error(error, 0.12, 0.60)`
*In plain words:* are tall letters tall enough and tails long enough, in good proportion?

### Section 2: Spatial (30%): *spacing, baseline & layout*

**F7 · Baseline Alignment**: *Measured*
`wobble = average RMS distance of letters from the fitted baseline; score = score_from_error(wobble, 0.08, 0.40)`
*In plain words:* do your letters sit neatly on the line, or bounce above and below it? (RMS = a fair
average of that up-and-down wobble.)

**F8 · Word Spacing**: *Measured*
```
gaps = word gaps measured in x-heights (ideal ≈ 1.0)
score = half from "is the gap about right" + half from "are the gaps even"
```
*In plain words:* are the spaces between words about one letter-width, and consistent?

**F9 · Letter Spacing**: *Measured*
`score = score_from_consistency(letter gaps, 0.30, 0.90)`
*In plain words:* are the spaces between letters even (not cramped here, sprawling there)?

**F10 · Margin Discipline**: *Measured*
`score = 0.6·consistency(left edges) + 0.4·consistency(right edges)`
*In plain words:* do your lines start at a tidy, even left margin down the page?

**F11 · Line Straightness**: *Measured*
`drift = average baseline tilt in degrees; score = score_from_error(drift, 1.0, 8.0)`
*In plain words:* do lines run straight across, or drift uphill/downhill?

**F12 · Vertical Alignment**: *Measured*
`score = score_from_consistency(|stroke angles|, 0.6, 1.6)`
*In plain words:* do your up-and-down strokes point a consistent direction?

### Section 3: Dynamics (20%): *speed, pressure & flow (the pen's specialty)*

> These describe **how the hand moves**, which lives in motion, not in the finished marks. From a photo
> they are honest estimates; with the **IMU pen** they become truly **Measured**. (Full pen details in §7.)

**F13 · Speed Consistency**: *Needs the pen* · pen: `consistency(per-stroke top speed, 0.20, 0.60)`
*In plain words:* do you write at a steady pace, or speed up and stall? Strokes are segmented at
**velocity minima** (motor-model method, §12.1), so each "stroke" is one real ballistic pen-movement.

**F14 · Pressure Consistency**: *Needs the pen* · pen: `consistency(per-stroke force, 0.20, 0.55)`
*In plain words:* do you press evenly, or bear down unevenly (which tires the hand)?

**F15 · Stroke Continuity**: *From image* · pen: velocity-minima segments + pen-contact breaks
*In plain words:* do strokes flow and join, or stop-start into many pieces?

**F16 · Pen-Lift Frequency**: *Needs the pen* · pen: `lifts ÷ characters`
*In plain words:* how often does the pen leave the page? Frequent lifts quietly slow writing down.
(Impossible to see in a still photo: it's an event **in time**.)

### Section 4: Style & Readability (20%): *slant, legibility & neatness*

**F17 · Slant Consistency**: *Measured*
`spread = std(per-word slant from shear-search); score = score_from_error(spread, 6, 26)`
*In plain words:* is your lean consistent (all letters lean the same way)? Uses the robust shear-search
slant (§12.1); falls back to per-pixel angles with a wider band (11, 40) for very short samples.

**F18 · Legibility Score**: *Estimated*
`score = 0.4·sizeEvenness + 0.3·spacingEvenness + 0.3·sittingOnTheLine` (the report names the weakest part)
*In plain words:* an overall "how easy to read" built transparently from the basics, and it tells you
which basic is holding it back.

**F19 · Character Distinction**: *Estimated*
`score = 5.5 + (loopRatio − 0.8)·4;  targets = (loops weak ? "a, o, e, g" : "n/h, r/v, c/e")`
*In plain words:* are easily-confused letters clearly different? It even **names the letters to drill**.

**F20 · Overall Neatness**: *Measured*
`score = average of (size evenness, spacing evenness, line straightness, baseline neatness)`
*In plain words:* a tidy-up summary of the visual basics.

---

## 5. Why OpenCV first, and would ML, deep learning or LLMs improve it?

A fair question: handwriting AI usually means neural networks. So why does Vahini lean on **OpenCV /
computer vision (measurement)** for most factors, and use machine learning only sparingly? And if we
*did* add ML to every factor (as the Model Selection Guide explores), would the scores get better?

Short answer: **for most factors there is nothing for a model to "predict": the measurement *is* the
answer: so ML would add cost and opacity for no accuracy gain. ML genuinely helps only a small,
specific set of factors, plus overall calibration and the pen's motion signals.**

### 5.1 The core principle: "structure is truth"

Most of the 20 factors ask for a **geometric fact**: a distance, a slope, a ratio, a variance, or a
count. For example:
- *Size Consistency* = the spread of letter heights → that's a **variance** you compute.
- *Line Straightness* = the tilt of the fitted baseline → that's a **slope** you compute.
- *Baseline Alignment* = how far letters sit off the line → that's a **distance** you measure.
- *Loop Closure* = is there a hole in the letter or not → that's a **count** of closed loops.

**In plain words:** if the question is "how tall, how far apart, how slanted, how even?", you don't
*guess* with a model: you **measure** it. Computing the number is the whole answer. A neural network
asked to do this would just try to *re-learn a ruler*: slower, heavier, and less trustworthy than the
ruler itself.

### 5.2 Why NOT default to ML / Deep Neural Networks / LLMs

| Concern | Measurement-first (OpenCV) | ML / Deep Learning | LLM |
|---|---|---|---|
| **Does it fit the job?** | ✅ The factor *is* a measurement | ◻ Only for shape-similarity / calibration | ❌ LLMs don't measure pixels at all |
| **Needs a big labelled dataset?** | ✅ No: works on day one | ❌ Yes (hundreds–thousands of rated samples) | ❌ Not a vision-geometry tool |
| **Explainable to a coach/parent?** | ✅ "Your gap is 0.6 of a letter wide" | ◻ Often a black box ("why a 6?") | ❌ Can sound confident yet be wrong |
| **Repeatable (same input → same score)?** | ✅ Deterministic | ◻ Depends on training/seed | ❌ Can vary run to run |
| **Bias risk** | ✅ Low (pure geometry) | ⚠ Inherits dataset bias (age, script, region) | ⚠ Inherits web-scale bias |
| **Speed / size / offline** | ✅ Tiny, instant, runs in the browser | ❌ Heavier; may need a server/GPU | ❌ Heavy; needs an API |
| **Defensibility** | ✅ Reproducible by hand, audit-friendly | ◻ Harder to defend in education | ❌ Hard to defend for assessment |

**Why LLMs specifically don't apply:** a Large Language Model predicts *text*. It has no native way to
measure a pixel distance or a baseline slope, and asked to "score this handwriting" it would **estimate
from appearance and could hallucinate** a number. For measuring geometry it is the wrong instrument.
(LLMs *can* help elsewhere: e.g. wording friendly feedback: but not in computing the factor scores.)

### 5.3 So is OpenCV "sufficient"? Yes: for the core, by design

For factors **3, 5, 7, 8, 9, 10, 11, 12** (and largely **17, 20**) the quantity is a direct geometric
measurement. Adding a trained model would only add opacity and a data requirement **for no accuracy
gain**: a ruler doesn't get more accurate by guessing. This is the technical justification for an
**OpenCV-first, measurement-first engine**, with ML reserved for the few factors that truly benefit.

### 5.4 Where ML *does* genuinely help (the honest exceptions)

The Model Selection Guide identifies a small set where learning adds real value: Vahini's roadmap uses
ML **here and only here**:

1. **Letter Formation (F1) & Character Distinction (F19)**: comparing a written letter to an ideal, and
   telling apart look-alikes (a/o, n/h), is a *similarity* problem. A **Siamese / metric-learning** or
   small **CNN** model judges "how close is this to the reference?" better than fixed rules on hard,
   messy inputs. *(Convolutional Neural Network: a vision model that learns shapes.)*
2. **Legibility (F18) & Overall Neatness (F20)**: these are *overall impressions* best matched to human
   coach ratings. A simple **regression** model (Ridge / SVR / Random Forest / gradient boosting) can
   blend the basic measurements to agree with expert scores better than a hand-set weighting: **once a
   few hundred rated samples exist.** Today Vahini uses a transparent fixed blend instead.
3. **The pen's Dynamics (F13–F16)**: speed, pressure, stroke flow and pen-lifts are **time-series**
   from the IMU pen. Once a dataset is collected, **1D-CNN / LSTM / TCN / DTW / HMM** models read these
   motion patterns far better than an image proxy ever could. This is the pen's whole point.
4. **OCR (optional, off the critical path)**: **PaddleOCR** can confirm *which* character was attempted.
   It is auxiliary, never the basis of a score.

### 5.5 "Would ML improve each factor?": the honest verdict

| Factor | Today's method | Would ML/DL improve accuracy? | Why |
|---|---|---|---|
| 1 Letter Formation | Contour / shape match | **Yes (on hard cases)** | Siamese/CNN similarity helps messy or ambiguous glyphs |
| 2 Stroke Order | Image proxy | **Yes: via the pen** | Order is temporal; IMU + RNN is the real fix, not image ML |
| 3 Loop Closure | Hole topology | **No** | A hole either exists or not: already exact |
| 4 Line Quality | Curvature variance | **Marginal** | A learned smoothness model could refine edge cases |
| 5 Size Consistency | Variance of heights | **No** | It's a statistic: computing it is the answer |
| 6 Ascender/Descender | Zone ratios vs baseline | **Marginal** | Mostly geometry; ML only for unusual scripts |
| 7 Baseline Alignment | Regression residual | **No** | Best-fit line + distance is already optimal |
| 8 Word Spacing | Measured gaps | **No** | A gap is a measured distance |
| 9 Letter Spacing | Measured gaps | **No** | Same: direct measurement |
| 10 Margin Discipline | First/last ink x | **No** | A coordinate read directly off the page |
| 11 Line Straightness | Fitted slope | **No** | Drift *is* the slope of a line |
| 12 Vertical Alignment | Shape moments / PCA | **No** | Orientation comes from image moments, no learning needed |
| 13 Speed Consistency | Image proxy | **Yes: via the pen** | Speed is a *process*; IMU velocity + time-series ML |
| 14 Pressure Consistency | Ink-darkness proxy | **Yes: via the pen** | Real force needs the sensor, not a photo |
| 15 Stroke Continuity | Connectivity proxy | **Yes: via the pen** | Pen-contact signal beats any image guess |
| 16 Pen-Lift Frequency | Not visible in a photo | **Yes: via the pen** | Lifts are events in time; only the pen sees them |
| 17 Slant Consistency | Stroke-angle spread | **No** | An angle statistic: already exact |
| 18 Legibility | Transparent blend | **Yes (with data)** | Regression calibrated to coach ratings blends features better |
| 19 Character Distinction | Loop heuristic | **Yes** | CNN/Siamese embedding separates look-alike letters |
| 20 Overall Neatness | Average of basics | **Marginal/Yes (with data)** | Could be calibrated to human "neatness" ratings |

**Reading the table:** roughly **half the factors cannot be improved by ML at all**: they are exact
measurements already. The clear ML wins are **shape similarity (1, 19)**, **human-calibrated overall
scores (18, 20)**, and above all the **pen's motion factors (13–16)**, where the *hardware*, not a
fancier image model, is the real upgrade.

### 5.6 The verdict

**OpenCV / measurement-first is the right default and is sufficient for the core engine.** It is
explainable, repeatable, bias-resistant, data-free at cold-start, and fast enough to run in a browser
offline. Machine learning is **layered in deliberately** for the few factors that benefit (1, 18, 19,
20) and for the patented pen's time-series (13–16); LLMs are not used to compute scores. This is exactly
the Model Selection Guide's principle: **"structure is truth; reserve ML for what genuinely needs it."**

---

## 6. The 20-factor weighting, one overall score (server: scoring.py)

```
Section averages (each = the average of its factor scores, 0–10):
   Structure  (weight 30%)
   Spatial    (weight 30%)
   Dynamics   (weight 20%)
   Style      (weight 20%)

overall (0–100) = Σ  section_average · 10 · weight
```

**In plain words:** average the factors inside each of the four families, then blend the four families
by importance. Structure and Spatial (the legibility fundamentals) count most.

The report also picks your **top strengths** (highest factors) and **focus areas** (anything below 5,
else the three lowest): the focus areas are exactly what the practice drills target.

---

## 7. The smart pen (`imu.js`): measuring motion

The Vahini pen carries **16 sensor channels ("axes")**, sampled **208 times per second (208 Hz)**:
- **1 × 9-axis IMU** near the nib = **9 axes** (acceleration in 3 directions + rotation in 3 directions
  + a built-in 3-axis magnetometer that keeps orientation accurate).
- **1 × 6-axis IMU** near the grip = **6 axes** (acceleration in 3 directions + rotation in 3 directions).
- **1 × tip force sensor** = **1 axis** (pen-tip pressure).

**The Kalman filter (why it's there).** Raw sensors are noisy: every reading jitters a little. A
**Kalman filter** continuously predicts where each signal *should* be and gently nudges that prediction
toward each new reading, cancelling the jitter in real time. **In plain words:** it's a smart smoother
that keeps the signal responsive while removing the electrical "fuzz," so the scores reflect your hand.

From the smoothed stream the pen computes the four **Dynamics** factors directly (speed evenness, force
evenness, stroke continuity, pen-lifts): turning them from photo *estimates* into true *measurements*.

> **Honest status:** there is no clinical training dataset yet, so the live demo **simulates** a
> realistic pen stream to show the experience and the maths. When the real pen sends data, only the
> data source changes: the smoothing, the formulas and the report stay identical.

---

## 8. Document-type detection (shown on every report)

Before scoring, a quick check classifies the page **by layout only** (it does **not** read the words):
how many lines/words, how short the tokens are, whether large non-text blobs (diagrams) are present.
It then labels the upload and sets an honest accuracy expectation:

| Detected type | Accuracy | Meaning |
|---|---|---|
| Handwritten prose | High | The content the engine is built for. |
| Short answers / few lines | Moderate | Usable but a small sample. |
| Numeric / symbolic (equations) | Reduced | Equations break the single-line assumptions. |
| Text with diagrams / figures | Reduced | Figures are detected and **excluded**; only text is scored. |
| Sparse / very short | Indicative | Too little writing for a confident read. |

**Why it matters:** a reader instantly sees whether the score is a confident assessment or a rough read
of an unusual page.

---

## 9. Growth Forecast (`forecast.js`): predicting improvement

Handwriting improves quickly at first, then levels off: a classic **learning curve**. The forecast
models each factor climbing toward a realistic ceiling:

```
projected_score(start, weeks) = start + (ceiling − start) · (1 − e^(−rate · weeks))
   rate = 0.30 per week,  shown over 8 weeks,  "fluent" threshold = 80% maturity
```

**In plain words:** "if you practise the prescribed drills, here's roughly where each score is heading
over the next 8 weeks": fast gains early, smaller gains later. From this the report shows: projected
overall score (now → +Δ), a fluency/"fast & efficient" band with weeks-to-fluent, and a writing-speed
(words-per-minute) estimate. It is clearly labelled an **estimate that assumes consistent practice**,
not a promise, and invites a re-test to track the real curve.

---

## 10. Writing-Craft layer & OCR (content-level feedback)

> **Note (June 2026):** the standalone Writing-Craft page was merged into the **Letter-Level
> Findings** page as its final block ("The craft of the words"): external feedback flagged the two
> pages as duplicative. The analysis layer below is unchanged; only its presentation moved.

The 20 factors grade **how letters look**. A separate **Writing-Craft** page grades **how the letter is
written**: so the same report can build good *writing habits*, not just neat strokes. This directly
serves Vahini's objective: help a learner improve **self-paced, with minimal coach or parent help**.

**What it does (`craft.js`).** It runs high-precision, rule-based checks on the **recognised text** and
flags only confident issues, each with a correction:
- **Grammar & phrasing**: e.g. "look forward to **hear**" → "**hearing**"; modal + "to" ("must **to**
  inform"); missing articles ("it was **pleasure**" → "a pleasure").
- **Homophones**: "**your** welcome" → "you're"; "**its** a" → "it's"; "**their** is" → "there".
- **Formatting & tone**: informal abbreviations (u, cu, pls…) in a formal letter; over-long block text.
- **Closings & sign-offs**: "Yours **Sincerely**" → "sincerely"; end a sign-off with a **comma**.

It always also shows a short teaching guide of these four areas, so the page is useful even when no issue
is found. (Rule-based, not ML, so a flagged issue is almost always real and fully explainable.)

**Where the text comes from (OCR).** Recognised text is produced by the OCR layer: **PaddleOCR** on the
server, or the reference passage offline. Recognition here is **assistive**: it confirms *which* letter
was attempted and supplies the text for the craft checks. It is **never** the basis of a handwriting
score, so imperfect OCR still yields useful guidance.

**Hard letters (l/c, k→ic, e/c, o-variation).** Telling near-identical handwritten letters apart is a
recognition problem in its own right. The full engineering answer: CRNN preprocessing/decoding changes,
TrOCR vs CRNN, hard-negative augmentation, and an n-gram-LM (KenLM) CTC beam-search tie-breaker, plus
Vahini's reference-text alignment shortcut: is documented in **`OCR-AMBIGUITY.md`**.

---

## 11. FAQ

**Q. What does "CV pipeline" actually mean?**
**CV = Computer Vision** (software that understands images). A **pipeline** is a chain of steps. So it's
the chain that turns a handwriting photo into measurements: shrink → grayscale → binarize → find letters
→ group into words/lines → measure. (Note: "CV" *also* abbreviates *Coefficient of Variation*, a
different thing: see the glossary.)

**Q. Why turn the photo black-and-white (binarize)? Why not just analyze the photo?**
Handwriting analysis is about **where the ink is**, not its color or brightness. Reducing the page to
"ink vs paper" makes finding and measuring letters reliable and fast, and removes distractions like
paper color or camera tint.

**Q. Why two different methods (Otsu vs Adaptive)? Isn't one cut-off enough?**
One global cut-off (**Otsu**) is perfect for evenly-lit photos. But if a shadow falls across the page,
a single cut-off would mistake the shadow for ink. **Adaptive** uses a *local* cut-off that follows the
lighting, so it stays correct on uneven photos. Vahini picks automatically based on the corners' lighting.

**Q. What are "connected components" in one sentence?**
Clusters of touching ink pixels: in practice, the individual letters and marks the engine then measures.

**Q. What is "tolerance" and why two numbers?**
Tolerances are the cut-offs that turn a measurement into a grade: `tol_good` (this good or better = 10/10)
and `tol_bad` (this bad or worse = 0). Between them the score slides smoothly, so small differences don't
cause big score jumps.

**Q. What does the baseline do, and why fit a new one each time?**
The baseline is the line writing sits on. Handwriting wanders, so the engine *re-discovers* the real
baseline for each line. It's the reference for straightness, drift, and where the tall/body/tail zones
sit: most spatial factors depend on it.

**Q. What's the difference between "Measured" and "Needs the pen"?**
**Measured** factors come straight from the image geometry and are highly reliable. **Needs the pen**
factors are about *motion* (speed, pressure, pen-lifts) that a still photo can only estimate: the IMU
pen measures them properly.

**Q. Will the same handwriting always get the same score?**
Yes for the **Measured** factors: the engine is **deterministic** (no randomness). Scores can differ
only if the *photo* differs (lighting, focus, crop), which is why we recommend a clear, even, square-on
photo.

**Q. Is this a medical or psychological test?**
**No.** It measures handwriting *quality* for **practice and improvement only**: not health, ability,
intelligence or personality, and never a diagnosis.

**Q. What's an IMU, and why 16 axes?**
An **IMU** is a motion sensor. "Axes" are the separate signals it reports (movement and rotation in each
direction). Combining a 9-axis IMU (motion + a built-in compass) + a 6-axis IMU + a tip force sensor gives
**16** signals, enough to reconstruct exactly how the pen moved and how hard it pressed.

**Q. Why a Kalman filter?**
To remove sensor "jitter" in real time so the motion scores reflect your hand, not electrical noise.

**Q. Does Vahini use OpenCV?**
Yes. The analysis runs on the Python recognition server, which uses **OpenCV** (via
`opencv-python-headless`, with NumPy fallbacks) for the image steps and **PaddleOCR** for recognition.
The browser sends the photo to the server and renders the returned scores, so a running server is
required for a report.

**Q. Why not just use AI / machine learning / a neural network for everything?**
Because most factors are **measurements, not predictions**: a distance, slope, ratio or count, where
computing the number *is* the answer. A model there adds cost, opacity and a data requirement for no
accuracy gain. ML is reserved for the few factors that genuinely benefit (letter-shape similarity and
human-calibrated overall scores) and for the pen's motion signals; LLMs aren't used to compute scores.
The full reasoning, with a per-factor "would ML help?" table, is in **§5**.

---

## 12. Reference algorithms adopted & how they improve the factors

Vahini's geometry is informed by well-established, openly-published handwriting computer-vision
techniques. We adopt the **measurement geometry** from these references and **deliberately reject the
graphology / personality-trait mapping** some of them include (inferring character or "emotional
stability" from letter shapes). That mapping is not scientifically validated and is contrary to our
improvement-only, **non-diagnostic** stance (see the disclaimer on every report).

### 12.1 Adopted now (live in the engine)

- **Velocity-minima stroke segmentation → Dynamics (F13, F15, F16).** The IMU pen now segments the pen
  path into **physical strokes at the local minima of the pen-tip velocity**: the classic handwriting
  *motor-model* method: handwriting is a chain of ballistic strokes, each separated by a brief slowdown.
  A 5-point minima test marks each boundary; the interval between two minima is one stroke, and its peak
  velocity is that stroke's ballistic amplitude. *In plain words:* instead of chopping the pen path on a
  fixed clock, we cut it where the hand naturally pauses: so a "stroke," its top speed, and the
  stroke-count are physically meaningful. This makes Speed Consistency (F13), Stroke Continuity (F15) and
  the stroke-based reading of Pen-Lifts (F16) genuinely credible. Falls back to the time-grid for very
  short captures. *Reference:* Schomaker, L.R.B. (1993), *Using Stroke- or Character-based Self-organizing
  Maps in the Recognition of On-line, Connected Cursive Script*, Pattern Recognition 26(3); Schomaker &
  Teulings (1990), IWFHR: NICI velocity-based-segmentation (`calc_vbs`) code.
- **Shear-search deslanting → Slant Consistency (F17).** Replaces noisy per-pixel gradient angles with a
  robust projection-profile method: the ink is sheared at a set of candidate angles and the angle that
  makes vertical strokes most solid (the strongest vertical projection) is taken as that word's dominant
  slant. *In plain words:* we "un-slant" each word a little at a time and keep the tilt that lines the
  strokes up best. This yields **one clean slant per word**, so the spread across words is a far better
  measure of consistency, and it reports the real average lean (e.g. "8° to the right"). On the sample
  page it cut the slant signal from ~5,000 noisy pixel angles to ~13 stable per-word angles. Falls back
  to the gradient method when there are too few words. *Reference:* the projection-profile / shear-transform
  deslant of Schomaker & Teulings (NICI `hwrslant`), standard in on-line handwriting analysis.
- **Stronger component quality-gate → all factors.** Before measuring, candidate ink blobs are filtered
  by size, **bounding-box fill ratio** and **aspect ratio**, removing underlines/ruled lines, hairline
  noise and solid smudges. *In plain words:* it throws out scribbles and stray marks so every factor
  measures real letters. *Reference:* the `is_bad_component` heuristic from public glyph-analysis code.

### 12.2 Planned (credited references, on the roadmap)

- **Boxcar / FIR trajectory smoothing before velocity.** A moving-average (boxcar) FIR filter on the X/Y
  pen path before differentiating, as an alternative/complement to the Kalman filter, gives cleaner
  velocity minima on noisy real-pen data. *Reference:* NICI `hwrfilter` boxcar FIR (Schomaker, 1996).
- **Perspective unwarp to A4 + real-world millimetres.** Detect the page quadrilateral and warp it flat
  to A4 at a known DPI. This removes phone-photo perspective distortion (a major error source for
  handheld capture) and lets margins and letter sizes be reported in **mm**, not just relative units.
  *Reference:* page-geometry/deskew modules (`detect_page_quad → getPerspectiveTransform →
  warpPerspective`). Best done in the native/server OpenCV path. *Would improve:* F5, F6, F7, F10, F11.
- **Loop topology via contour hierarchy.** Use connected-contour hierarchy to count interior holes and
  each loop's **circularity**, so Loop Closure (F3) reflects loop *quality*, not just presence, and helps
  Letter Formation (F1). *Reference:* `findContours(RETR_CCOMP)` loop-feature extraction.
- **Skeleton-graph stroke continuity.** Thin each letter to a one-pixel skeleton and count **junctions**
  and **endpoints**; this gives a real image-based signal for Stroke Continuity (F15), better than the
  current component-count proxy. *Reference:* skeletonize + junction/endpoint graph features. (The IMU
  pen remains the gold standard for the dynamics factors.)

### 12.3 Explicitly NOT adopted

- **Graphology / personality inference.** Several public repositories map handwriting features to
  personality traits (e.g. "emotional stability", "modesty", or darker labels). Vahini measures
  **handwriting quality only** and treats those mappings as out of scope and not evidence-based, in line
  with the disclaimer printed on every report.

---

## 13. Letter-level findings (retired)

Earlier versions aligned a known reference passage against the in-browser CV overlay to check
per-letter things a coach would notice: style mixing, stray mid-word capitals, missing
sentence-start capitals, inconsistent letterforms, a punctuation audit, and a spelling/word audit
(`letters.js`, report page *"Letter-Level Findings"*).

That layer read the browser's CV overlay directly and had no server-side equivalent, so it was
**removed** when the 20-factor scoring moved to the recognition server (mid-2026; see §15). The
report's `letters.js`-driven page no longer renders. The **writing-craft layer** (`craft.js`:
grammar, homophones, formatting, sign-offs; see §10) is unaffected and still runs whenever the
recognition server returns text with reasonable confidence.

Re-introducing per-letter findings would need a server-side rewrite against the server's own
detection geometry. Tracked in `ROADMAP.md` §3.

---

## 14. External-review upgrades (June 2026)

An external product/clinical review validated the 20-factor taxonomy (it maps onto the constructs
of **BHK** and **DASH**, the validated instruments occupational therapists use) and identified the
measurement/report gaps below. The following are now **implemented**:

- **Two overalls.** In photo mode the headline score is the **Measured overall**: computed only
  from factors actually measurable from an image (pen-pending Dynamics factors excluded, section
  weights re-normalised). The full 20-factor overall applies only in pen mode. The cover, scorecard
  and summary all say which one they show. (server: `scoring.py`'s `overall_measured` field,
  serialised as `overallMeasured`)
- **Honest photo-mode cover.** The IMU pen badge and "nothing here is guessed" claims no longer
  appear on image-only scans; the cover states "Measured from your photo: N of 20 factors."
- **Sample-quality validity gate.** The engine grades each upload (Good / Usable / Limited) from
  sample size, resolution, lighting evenness and writing size, and prints the issues plus a retake
  tip on the sample page. (server: `computer_vision.py`)
- **Per-factor sample size.** Factor cards display "based on 74 letters / 12 word gaps" so a coach
  can judge confidence. (server: `scoring.py`'s `based_on` field, serialised as `basedOn`)
- **Writer's-own-letter crops.** For size, baseline, word-gap, letter-gap and margin factors the
  card's hero image is an **annotated crop of the writer's own writing** (tallest vs shortest
  letter, wobbliest line with fitted baseline, widest gap shaded, and so on), generated from the
  connected-component boxes. (server: `computer_vision.py`)
- **Layered disclosure.** A one-page **Scorecard** (overall, section dials, top-3 strengths/focus,
  the prescribed drills, next milestone) follows the cover as the shareable unit; a one-page
  child-facing **Certificate** (score, stars, drills, mascot) renders for the student/parent tier.
- **Max 3 drills, high-confidence only.** The prescription never selects from pen-pending estimates
  in photo mode and caps at three active drills with a "because" sentence each.
- **Goal line.** "Next milestone: N/100: reachable by lifting X and Y" on the scorecard and the
  forecast page (which replaced the removed words-per-minute estimate).
- **Progress vs last scan.** Reports for a returning writer show "since last scan" deltas (overall
  + per section), stored locally on the device.
- **No false precision.** Estimated/pen-pending factors display rounded scores ("≈6"), not decimals.

**Roadmap (review items deferred, credited):** crowding index (S5), baseline recovery (B3),
within-word slant drift (SL4), corner sharpness (G9), template similarity (G10), correction
frequency (C1); age/grade norm bands once coach calibration data exists; behaviour indicators
(hesitant / impulsive / fatigue) **only after** real IMU data, always labelled indicators: never
diagnosis; script/language expansion (Hindi, Telugu, Tamil, Kannada).

See also **`computer-vision-algorithms.md`**: a learner-friendly walkthrough of every CV algorithm
used (what it is, why, and how it works step by step).

---

## 15. Calibration & roadmap (for developers)

| Part | Today | Next upgrade |
|---|---|---|
| Reading the actual words (OCR) | **PaddleOCR** server, plus TrOCR and Surya for handwriting in hybrid mode | Better Telugu/Hindi accuracy from real sample data; see `ROADMAP.md` |
| Motion factors (F13–F16) | Photo estimate / pen **simulation** | Live IMU pen data |
| Legibility (F18) | Transparent blend | Model calibrated to coach ratings |
| Character distinction (F19) | Letter-target heuristic | Learned letter-similarity model |
| Target bands (§4C) | Engineering defaults | Re-fit on a labelled Vahini dataset |

Everything in the Structure / Spatial / Style sections is **measured deterministically** and is stable
across runs of the same image.

---

© 2026 Vahini Technologies · IMU Sensor Pen, Patent No. 584433 · vahinitech.com
