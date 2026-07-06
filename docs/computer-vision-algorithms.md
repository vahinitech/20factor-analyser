# Computer Vision Algorithms in Vahini: How Each One Works

A plain-language walkthrough of **every computer-vision (CV) algorithm** the Vahini engine uses,
in the order they run. For each one: **what it is, why Vahini needs it, how it works step by step**,
and a tiny pseudocode sketch. No prior CV knowledge assumed.

> **Computer Vision (CV)** = software that "looks at" an image and extracts facts from it.
> Vahini's CV is **deterministic**: fixed maths, no randomness: so the same photo always
> produces the same measurements. Code: `analyser/server/computer_vision.py`, `geometry.py` (image, server-side), `imu.js` (pen motion, browser-side).

---

## 1. Grayscale conversion (luminance)

**What:** turns the colour photo into shades of gray.
**Why:** handwriting analysis cares about *where ink is*, not its colour. One brightness number per
pixel is simpler and faster than three colour numbers.
**How:** each pixel's red, green and blue are blended with weights matching how bright the human eye
perceives each colour:

```
brightness = 0.299·R + 0.587·G + 0.114·B      # green looks brightest to the eye
```

---

## 2. Otsu's threshold (global binarization)

**What:** automatically picks the single best brightness cut-off separating **ink** from **paper**.
**Why:** we must label every pixel "ink or paper". A fixed cut-off (say 128) fails on dark photos or
faint pencil. Otsu finds the right cut-off *for this photo* with zero user settings.
**How (intuition):** a handwriting photo's brightness histogram has two humps: dark ink, light
paper. Otsu tries every possible cut-off (0–255) and keeps the one that best separates the two humps
(maximises the *between-group variance*):

```
for t in 0..255:
    split pixels into darker-than-t and lighter-than-t
    score(t) = group_size_A · group_size_B · (mean_A − mean_B)²
threshold = t with the highest score
ink(pixel) = brightness(pixel) < threshold
```

**Reference:** Otsu (1979), *A threshold selection method from gray-level histograms.*

---

## 3. Adaptive mean threshold (local binarization)

**What:** a *local* ink/paper cut-off that adjusts across the page.
**Why:** if a shadow falls over half the page, one global cut-off calls the whole shadow "ink".
A local cut-off follows the lighting and stays correct everywhere.
**How:** for each pixel, compare it to the **average brightness of its neighbourhood**: ink must be
noticeably darker than its surroundings. Computing thousands of neighbourhood averages is made
instant by an **integral image** (a running-total table where any rectangle's sum is 4 lookups):

```
integral[x,y] = sum of all brightness above-left of (x,y)      # built once
local_mean    = (rectangle sum via 4 lookups) / area
ink(pixel)    = brightness(pixel) < local_mean − C             # C ≈ 8, a small margin
```

**When used:** Vahini checks the photo's four corners; if their brightness differs a lot (uneven
light), it picks Adaptive, otherwise Otsu. The report states which ran.
**Reference:** Bradley & Roth (2007), *Adaptive thresholding using the integral image.*

---

## 4. Connected components (finding the letters)

**What:** groups touching ink pixels into blobs: in practice, individual letters and marks.
**Why:** every later measurement (size, spacing, lines) needs to know where each letter is.
**How:** flood fill. Start at any unlabelled ink pixel, spread to all touching ink pixels
(including diagonals = "8-connectivity"), label them as one component; repeat:

```
for each ink pixel not yet labelled:
    new label L
    stack = [pixel]
    while stack: p = pop; label p as L; push p's 8 unlabelled ink neighbours
    record component L's bounding box, area, centre
```

---

## 5. Quality gate (filtering noise and non-letters)

**What:** rejects blobs that are not plausible letters before measuring.
**Why:** dust specks, underlines, ruled lines and smudges would poison the statistics.
**How:** simple geometric tests against the **median letter height** (`medH`):

```
reject if: too small (h < 0.28·medH) or too tall (h > 4.2·medH)
        or tiny area (< 8 px) or page-spanning (w > 60% of page)
        or underline-shaped (aspect > 3.5 and short)
        or fill-ratio of bounding box < 4% (hairline) or > 92% (solid blob)
```

---

## 6. Printed-text detection (mixed pages)

**What:** spots lines of *printed* text (letterheads, form labels, tables) and excludes them.
**Why:** a doctor's-prescription pad or worksheet mixes print and handwriting; only the
handwriting should be scored.
**How:** printed lines are unnaturally *regular*. Per line, measure the variation (CV =
coefficient of variation) of letter heights, baseline deviation, and spacing; lines that are
"too perfect" (very low variation on several tests at once) are flagged printed and skipped.
The report then says how many printed lines were excluded.

---

## 7. Line & word grouping

**What:** organises letters into lines of text, and lines into words.
**How:** letters whose vertical centres are within ~0.7·medH of each other share a line; within a
line, a horizontal gap wider than ~0.6·medH starts a new word. From here on, "line" and "word" are
known objects the spacing/margin factors can measure.

---

## 8. Least-squares baseline fitting

**What:** re-discovers the invisible line each row of writing sits on.
**Why:** the baseline is the reference for straightness, drift, zone heights and "do letters sit on
the line?": five factors depend on it.
**How:** take the **bottom point of every letter** in the line and fit the straight line that
minimises the squared distances to them (ordinary least squares):

```
m, c = argmin Σ (letter_bottom_y − (m·x + c))²     # slope m, intercept c
drift_angle = atan(m)                               # F11 line straightness
wobble = RMS distance of letter bottoms off the line, ÷ x-height   # F7 baseline
```

(**RMS** = root-mean-square: a fair average of deviations that treats above/below equally.)

---

## 9. x-height & zone analysis

**What:** the height of a normal lowercase letter body (the height of "x"), used as the natural
ruler so all measurements work at any writing size, plus the three vertical **zones**:
upper (l, h, t), middle (a, o, e), lower (g, y, p).
**How:** x-height = median letter height. A letter reaching well above the body band counts as
upper-zone; below the fitted baseline, lower-zone. The balance of the three gives F6.

---

## 10. Shear-search deslanting (slant measurement)

**What:** finds each word's dominant slant: robustly.
**Why:** per-pixel angle estimates are noisy on cursive. This classic method gives one clean slant
per word, so the spread across words is a true consistency measure (F17).
**How:** *try un-slanting the word at several candidate angles; the angle that makes the vertical
strokes stand most upright is the word's slant:*

```
for angle in [-42°…0°…+42°]:
    shear the word's ink columns by tan(angle)
    score = Σ (column height)²  over columns that are mostly solid ink
slant = angle with the best score
```

**Reference:** projection-profile deslanting as used in classical handwriting-recognition
pre-processing.

---

## 11. Loop-closure topology (flood fill from the border)

**What:** checks whether round letters (a, o, e, g) are properly **closed**.
**How:** flood-fill the *background* inward from the image border. Any background pocket that the
flood could **not** reach must be fully enclosed by ink: i.e. a closed loop:

```
flood background from all four borders
for each loop-bearing letter:
    closed if its box contains background pixels the flood never reached
loopRatio = closed letters ÷ eligible letters        # F3
```

---

## 12. Gradient-orientation analysis (stroke angles)

**What:** estimates the direction of every tiny piece of stroke from how brightness changes
around it (the **gradient**); stroke direction is perpendicular to the gradient.
**Why:** feeds vertical-alignment scatter (F12) and is the fallback slant method for very short
samples where shear-search lacks words to work on.

---

## 13. Document-type classification (layout only)

**What:** labels the upload: prose, short answers, equations, diagrams, mixed printed,
with an honest accuracy expectation printed on the report.
**How:** pure layout statistics (it never reads the words): number of lines and words, average
token length, presence of large non-text blobs, printed-line count, ink density. Rule-based and
fully explainable.

---

## 14. Sample-quality validity gate

**What:** judges whether the *photo itself* supports trustworthy scores, and says how to retake it.
**How:** checks sample size (letters, lines), source resolution, lighting evenness (corner spread)
and apparent writing size; grades **Good / Usable / Limited** and surfaces the issues plus one
retake tip ("fill the frame", "face a window") on the report's sample page.

---

## 15. Kalman filtering (pen signals: `imu.js`)

**What:** removes electrical jitter from the pen's 208 Hz sensor streams in real time.
**How:** a predict-then-correct loop per signal: predict where the value should be, then nudge
toward the new reading in proportion to how trustworthy it is (the **Kalman gain**):

```
p += q                  # uncertainty grows a little each step (process noise q)
k  = p / (p + r)        # gain: balance prediction vs new reading (sensor noise r)
x += k · (z − x)        # move estimate toward the reading z
p *= (1 − k)            # uncertainty shrinks after using the reading
```

---

## 16. Velocity-minima stroke segmentation (pen)

**What:** cuts the pen's continuous motion into individual **ballistic strokes** at the moments the
pen-tip speed dips to a minimum: the natural "joints" of handwriting in motor-control research.
**Why:** per-stroke peak velocity and per-stroke force feed the Dynamics factors (F13, F14).
**Reference:** Schomaker & Teulings (1990); Schomaker (1993): the handwriting motor-model school.

---

## 17. Letter-crop evidence (annotated examples)

**What:** crops the writer's **own** letters from the photo as visual proof on factor cards: the
shortest vs tallest letter (size), the wobbliest line with its fitted baseline drawn in, the widest
word gap shaded, the closest letter pair boxed, and the left-margin dot plot.
**How:** the bounding boxes from step 4 plus the fits from step 8 directly identify each example;
the crop is drawn on a small canvas with the annotation overlaid and embedded as a compact JPEG.

---

## 18. Learning-curve forecast (`forecast.js`)

**What:** projects each factor's score over 8 weeks of practice along an exponential learning curve
(fast early gains, then levelling off) toward a realistic ceiling:

```
projected(start, weeks) = start + (ceiling − start) · (1 − e^(−0.30·weeks))
```

Clearly labelled an estimate that assumes ~10 min practice, 3×/week: never a guarantee.

---

## 19. Expected-text alignment & letter-level checks

**What:** lines up the letters of the **known reference passage** with the detected ink blobs, so
the engine can reason about *specific letters* the way a coach does.
**Why:** coaches don't stop at "spacing is uneven": they say "your r changes shape", "that capital
doesn't belong mid-word", "where are your full stops?". Alignment makes those checks computable
without full handwriting recognition.
**How:** the writer copies a known passage, so expected word *k* of line *i* corresponds to detected
word *k* of line *i*. A word whose ink-piece count equals its expected letter count gets a 1:1
letter map:

```
for each line: pair expected words with detected words in order
word style: pieces ÷ letters ≤ 0.62 → joined (cursive);  ≈ 1.0 → print
if pieces == letters: letter k of the word ↔ ink blob k     # 1:1 map
checks on mapped letters:
    mid-word blob taller than 1.55× x-height where a small letter
    is expected → suspected stray capital
    all repeats of one letter: high width/height spread → "written 3 ways"
punctuation: expected marks counted vs dot-sized ink marks
word audit: piece count vs letter count (offline) or OCR word match (server)
```

Joined words are **excluded** from per-letter checks rather than guessed: conservative by design.
Every finding ships with a crop of the writer's own ink as evidence.

---

## One-page cheat sheet

| # | Algorithm | Question it answers | Feeds |
|---|---|---|---|
| 1 | Grayscale | "How bright is each pixel?" | everything |
| 2 | Otsu | "Ink or paper?" (even light) | everything |
| 3 | Adaptive mean | "Ink or paper?" (shadows) | everything |
| 4 | Connected components | "Where is each letter?" | everything |
| 5 | Quality gate | "Is this blob really a letter?" | all factors |
| 6 | Printed-text detection | "Which lines are printed?" | doc type, scoring scope |
| 7 | Line/word grouping | "Which letters form words & lines?" | spacing, margins |
| 8 | Baseline fit | "What line does the writing sit on?" | F7, F11, zones |
| 9 | x-height & zones | "How big is the letter body?" | F5, F6, all ratios |
| 10 | Shear deslant | "How slanted is each word?" | F17 |
| 11 | Loop topology | "Are round letters closed?" | F3, F1, F19 |
| 12 | Gradient angles | "Which way do strokes point?" | F12 |
| 13 | Doc-type classifier | "What kind of page is this?" | report honesty |
| 14 | Quality gate (photo) | "Can these scores be trusted?" | report honesty |
| 15 | Kalman filter | "What's the true pen signal?" | F13–F16 (pen) |
| 16 | Velocity minima | "Where does each stroke start/end?" | F13–F16 (pen) |
| 17 | Letter crops | "Show me MY letters as proof" | factor cards |
| 18 | Learning curve | "Where is this heading?" | forecast page |
| 19 | Expected-text alignment | "Which letter is which: and is it right?" | letter-level findings |

---

© 2026 Vahini Technologies · vahinitech.com · See `ARCHITECTURE.md` for the factor formulas and scoring bands.
