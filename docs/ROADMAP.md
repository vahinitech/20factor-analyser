# Vahini — Roadmap, Status & "Human Reading" Capability Matrix

*A single place that records: what the report does **today**, how much of it is a "human reading
the page line by line", what is **not** done yet, and the prioritised **TODO / future work**.
Companion to `ARCHITECTURE.md` (how it works) and `VISION-MODELS.md` (which OCR engine). Last
reviewed June 2026.*

---

## 1. Does Vahini "read the page like a human"? — the honest matrix

A human coach reads line by line and notices: spelling, punctuation, grammar, mixed cursive/print,
stray capitals, inconsistent letterforms, open loops, baseline drift, spacing. Here is **exactly**
what Vahini does for each — and the condition under which it fires.

| What a human notices | Vahini today | How | Fires when… |
|---|---|---|---|
| Neatness / size evenness | ✅ Done | F5, F20 geometry | always (any image) |
| Baseline drift / wavy lines | ✅ Done | F7, F11 geometry | always |
| Spacing (word & letter) | ✅ Done | F8, F9 geometry | always |
| Slant consistency | ✅ Done | F17 shear-search | always |
| Open vs closed loops | ✅ Done | F3 hole topology | always |
| Line quality / shakiness | ✅ Done | F4 stroke-width variance | always |
| **Mixed cursive vs print** | ✅ Done | `letters.js` style mix | needs aligned text* |
| **Stray capitals mid-word** | ✅ Done | `letters.js` zone height | needs aligned text* |
| **Missing sentence-start capitals** | ✅ Done | `letters.js` | needs aligned text* |
| **Same letter, different shapes** | ✅ Done | `letters.js` form variance | needs aligned text* |
| **Punctuation present/missing** (full stop, comma, hyphen) | ✅ Done | `letters.js` mark audit | needs aligned text* |
| **Spelling mistakes** | ◑ Partial | `letters.js` word audit | **OCR server only** |
| **Grammar / phrasing** | ✅ Done | `craft.js` rules | needs recognised text |
| **Homophones** (your/you're, its/it's) | ✅ Done | `craft.js` rules | needs recognised text |
| **Missing apostrophe / comma / full stop** | ✅ Done | `craft.js` + audit | needs recognised text |
| **Sign-off & letter formatting** | ✅ Done | `craft.js` completeness | letter type |
| Mixed small & CAPS (case mixing) | ✅ Done | `letters.js` caseMix | needs aligned text* |
| Telugu/Hindi letter reading | ◑ Partial | PP-OCRv5 server | **OCR server only** |

> **\* "needs aligned text"** = the engine must know what the words *should* be. Two ways that
> happens: **(a)** the writer copied a **known passage** we have on file (offline path), or **(b)**
> the **OCR server** recognised the text (any free-form upload). **Without either, these checks
> can't fire** and the report shows geometry only. This is the single biggest gap (see §3).

**Bottom line:** the "human reading" layer is **built and wired** (`letters.js` + `craft.js`,
rendered on the *Letter-Level Findings* page). It runs fully when the writer used a known passage,
and runs on **any** upload **once the PaddleOCR server is switched on**. The code is done; the
deployment is the missing link.

---

## 2. What's implemented today (status: ✅ live)

- **20-factor geometry engine** — deterministic CV pipeline; runs offline in the browser.
- **Two overalls** — "Measured" (photo) vs full (pen), honestly labelled.
- **Document-type detection** — prose / short-answer / numeric / figures / sparse, with accuracy expectation.
- **Sample-quality gate** — Good/Usable/Limited + retake tips; rejects non-handwriting.
- **Print-vs-handwriting filter** — drops printed letterhead/Telugu print lines from scoring.
- **Auto-deskew** — median line-tilt removed (helps hand-held phone tilt).
- **Letter-level findings** (`letters.js`) — style mix, mid-word caps, sentence caps, letterform variance, punctuation audit, word audit, with cropped evidence.
- **Writing-craft layer** (`craft.js`) — grammar, homophones, formatting, sign-offs, completeness.
- **Personalised drills** — max 3, high-confidence, now using real handwriting-coach techniques (bottle-lid loop warm-up, magic strokes, two-line band, slant rails, light-grip).
- **Four Foundations panel** — grip, posture, pressure, warm-up (coaching pedagogy).
- **Growth forecast** — learning-curve projection over 8 weeks.
- **Progress vs last scan** — per-section deltas, stored locally.
- **PP-OCRv5 server** — coded (`src/server/ppocr-server.py`): English + Telugu, doc-unwarp, print hint. **Not yet deployed.**
- **Audience + feedback system** — local profile, private feedback widget, email backend script. **Endpoint not yet set.**

---

## 3. Not done yet / known gaps (status: ◻ open)

| Gap | Impact | Fix |
|---|---|---|
| **OCR server not deployed** | Spelling + Telugu reading + free-form craft checks don't fire | Deploy `ppocr-server.py` (see VISION-MODELS.md §4) |
| **Feedback endpoint not set** | Feedback stored locally only, not centralised | Deploy `docs/feedback-email-backend.gs`, paste URL in `site.js` |
| **No real IMU pen data** | Dynamics factors (13–16) are estimates/simulated | Capture from Battu hardware |
| **Indic geometry thresholds tuned on Latin** | Telugu/Hindi quality scores less reliable | Re-fit bands on Indic samples |
| **Letter-shape factors assume Latin (loops, a/o/e/g)** | F1/F19 not meaningful for Telugu | Script-aware letter models |
| **No clinical/coach calibration dataset** | F18/F20 use fixed blends, not human-rated | Collect rated samples → regression |
| **No perspective unwarp to mm** | Sizes/margins in relative units only | Page-quad warp (server OpenCV) |

---

## 4. Prioritised TODO / future work

### Near-term (highest leverage, low cost)
1. **Deploy PaddleOCR PP-OCRv5 self-hosted** → turns on spelling + Telugu/Hindi reading + free-form craft checks, privately and free. *Single biggest unlock.*
2. **Set the feedback endpoint** → centralise feedback + audience data.
3. **Collect 50–100 real Telugu/English handwriting samples** → measure true OCR line-accuracy; basis for everything below.

### Mid-term (needs data or modest infra)
4. **Re-fit geometry bands on Indic samples** → trustworthy Telugu/Hindi quality scores.
5. **Perspective unwarp → A4 mm** → real-world sizes/margins; fixes phone-photo distortion.
6. **Loop topology via contour hierarchy; skeleton-graph continuity** → richer F3/F15.
7. **Calibrate F18/F20 to coach ratings** (Ridge/SVR) once rated samples exist.

### Longer-term (research / hardware / model)
8. **Live IMU pen integration** → real Dynamics factors (13–16); the dataset moat.
9. **Script-aware letter models** (CNN/Siamese) for F1/F19 across Telugu/Hindi/Tamil/Kannada.
10. **Evaluate Chandra OCR 2** for Indic handwriting if PaddleOCR proves insufficient (privacy/cost review first — see VISION-MODELS.md).
11. **Age/grade norm bands**; **behaviour indicators** (hesitant/impulsive/fatigue) **only** after real IMU data, always labelled indicators — never diagnosis.

### Explicitly out of scope
- **Graphology / personality inference** — not evidence-based; contrary to Vahini's non-diagnostic stance.

---

## 5. The data moat (why the pen matters beyond one user)

There is **no large public dataset** of how Telugu/Hindi (or English-in-India) are written **by
hand, with motion**. Every Battu capture builds the first one. That dataset is what eventually lets
Vahini (a) tune geometry bands per script, (b) fine-tune OCR for its own users, and (c) train the
real Dynamics models. It is also the strongest answer to "why is this defensible?" for investors.

© 2026 Vahini Technologies · companion to ARCHITECTURE.md and VISION-MODELS.md
