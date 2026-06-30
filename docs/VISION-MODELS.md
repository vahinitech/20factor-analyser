# Vahini — Vision & OCR Models: Options, Accuracy & Recommendation

*Plain-language comparison of the recognition engines Vahini can use, what each is good at,
how accurate they are on **handwriting** and **Indic scripts (Telugu/Hindi)**, and the honest
verdict on whether switching engines would improve Vahini's results. Last reviewed June 2026.*

> **Read this first — the one thing that surprises everyone.**
> OCR / vision models in Vahini are **auxiliary**. They power the *reading* layer (which words
> were written, spelling, the writing-craft checks). They do **NOT** compute the 20 handwriting
> **quality** scores — those come from geometry (size, spacing, baseline, slant, loops…), which
> needs no OCR at all. So a better OCR engine makes the **spelling / word / letter-ID layer**
> better; it does **not** change the neatness/legibility/spacing scores. Keep that split in mind
> through everything below.

---

## 0. The two jobs, kept separate

| Job | What it answers | Engine used | Needs OCR? |
|---|---|---|---|
| **Quality measurement** (the 20 factors) | "How neat, even, straight, well-spaced is the writing?" | Vahini CV pipeline (`engine.js`) | ❌ No |
| **Reading** (words, spelling, craft) | "*Which* letters/words are these? Any spelling/grammar/punctuation issues?" | An OCR / vision model | ✅ Yes |

Everything in this document is about the **second** job.

---

## 1. The candidates

### A. PaddleOCR — PP-OCRv5 (what Vahini is wired for today)
- **Type:** classic two-stage OCR — a **detector** (finds text boxes) + a **recognizer** (reads each line). Lightweight CNN/CRNN models.
- **Languages:** 100+ including **English, Telugu, Hindi (Devanagari), Tamil, Kannada**; explicitly supports **handwriting**.
- **Footprint:** tiny — mobile recognizer is ~2M parameters; **runs on a CPU**, even in-browser (PaddleOCR.js). No GPU required.
- **Cost / licence:** free, Apache-2.0, **fully self-hostable** → images never leave your server.
- **Accuracy notes:** PP-OCRv5 is ~30% better than v3 on multilingual text and adds real handwriting support; **but the public Indic training sets are small** (Telugu ≈ 2,478 line-images, Devanagari ≈ 3,611), so Telugu/Hindi **handwriting** accuracy is usable-but-modest, not stellar.
- **Best for:** privacy-sensitive, zero-cost, offline/edge use — exactly Vahini's children's-handwriting setting.

### B. Chandra OCR 2 (Datalab) — the vision-language model you asked about
- **Type:** **yes, it is a vision model** — a 4-billion-parameter **vision-language model (VLM)** that "looks" at the whole page and outputs Markdown/HTML/JSON **with layout**, not just plain text.
- **Accuracy:** **state-of-the-art among open OCR** — 85.9% on the olmOCR benchmark (hosted variant 86.7%); 77.8% on Datalab's 43-language multilingual benchmark.
- **Indic scripts:** this is its standout vs v1 — **Telugu +39.1, Kannada +42.6, Tamil +26.9, Malayalam +46.2, Bengali +27.2** points of improvement. Strong on **cursive/messy handwriting**, tables, forms, math.
- **Footprint:** heavy — needs a **GPU (≈H100-class) with vLLM** to self-host, or Datalab's **paid hosted API**.
- **Cost / licence:** open weights under **OpenRAIL** (broader commercial use needs a licence); hosted API is paid (small free credit to trial).
- **Best for:** maximum accuracy on hard handwriting + Indic scripts — **if** you can run a GPU, or accept sending images to a third party.

### C. Cloud vision APIs (Google Cloud Vision / Document AI, AWS Textract, Azure AI Vision)
- **Type:** managed OCR/handwriting APIs.
- **Accuracy:** very good on English handwriting and forms; Indic-handwriting support varies and is generally weaker than Chandra 2.
- **Cost / privacy:** per-page fees, and **images leave your infrastructure** to a third party — a real concern for children's/patient data.
- **Best for:** quick English-only pilots where privacy and cost are not constraints.

### D. TrOCR / Qwen-VL / other open VLMs (research-grade)
- **Type:** transformer OCR (TrOCR) or general vision-language models.
- **Accuracy:** TrOCR is strong on English handwriting lines; weak/none on Telugu out-of-the-box. General VLMs vary and can **hallucinate** text.
- **Best for:** research and English-line experiments; not a turnkey Indic solution.

---

## 2. Side-by-side

| | **PaddleOCR PP-OCRv5** | **Chandra OCR 2** | **Cloud APIs** | **TrOCR / VLMs** |
|---|---|---|---|---|
| English print | Very good | Excellent | Excellent | Good |
| **English handwriting** | Good | **Excellent** | Very good | Good |
| **Telugu / Hindi print** | Good | **Excellent** | Mixed | Weak |
| **Telugu / Hindi handwriting** | Modest | **Best available** | Weak–mixed | Very weak |
| Layout / tables / forms | Basic | **Excellent** | Good | Basic |
| Runs offline / on CPU | ✅ Yes | ❌ Needs GPU | ❌ Cloud only | ❌ Usually GPU |
| Keeps data on your server | ✅ Yes | ✅ (self-host) / ❌ (API) | ❌ No | ✅ (self-host) |
| Cost | Free | Free weights*/paid API | Per-page | Free weights |
| Setup effort | Low | High (GPU/vLLM) | Low | High |
| Privacy fit for kids' data | **Strong** | Strong (self-host) | Weak | Strong (self-host) |

*Open weights under OpenRAIL; broader commercial use needs a Datalab licence.

---

## 3. "Will switching engines improve Vahini's accuracy?" — the honest answer

**For the 20 handwriting-quality scores: NO.** Those are geometric measurements (height variance,
gap consistency, baseline RMS, slant spread, loop topology). They don't use OCR, so no OCR engine —
not even Chandra 2 — changes them. A ruler doesn't get more accurate by adding a language model.

**For the reading layer (spelling, word audit, letter ID, craft checks): YES, materially —
especially for Telugu/Hindi handwriting.** This is where engine choice matters:
- Today, with **no OCR server**, the reading layer only works when the writer copied a **known
  passage** we can align to. On a free-form upload it falls back to geometry-only hints.
- **PaddleOCR self-hosted** turns on real reading for English + Indic at zero cost, on a CPU, with
  data staying on your server — the right **first** step.
- **Chandra 2** would push Indic-handwriting reading from "modest" to "best available" — the right
  step **later**, once you have a GPU budget or are comfortable with the hosted API's privacy/cost
  trade-offs.

**Net:** engine upgrades improve *what Vahini can read*, not *how it scores neatness*. Both matter,
but they're different products inside the report.

---

## 4. Recommendation for Vahini (in order)

1. **Now — deploy PaddleOCR PP-OCRv5 self-hosted** (already coded in `src/server/ppocr-server.py`).
   Free, CPU-friendly, English + Telugu + Hindi, **data never leaves your server**. This alone
   switches the spelling/word/craft layer from "needs a known passage" to "works on any upload."
2. **Measure on real samples.** Collect a small set of real Telugu/English handwriting and record
   line-accuracy. This tells you whether PaddleOCR is *good enough* before spending on a GPU.
3. **If Indic handwriting accuracy is the bottleneck — pilot Chandra 2.** Trial via the hosted API's
   free credits on **non-personal** samples first; if it clearly wins and you need it in production,
   either license + self-host on a GPU (keeps data private) or use the API with explicit consent.
4. **Build the dataset regardless.** Every Battu-pen capture is labelled Indic-handwriting motion
   data — the asset that, in time, lets Vahini fine-tune *any* of these engines for its own users.
   (This is the "data moat" story; see `ROADMAP.md`.)

> **Privacy guardrail:** Vahini's promise is that handwriting images are processed and **not
> retained**. PaddleOCR self-hosted upholds that literally. Any cloud API or hosted VLM means images
> leave your infrastructure — only adopt with explicit consent and a privacy review.

---

## 5. Glossary

- **OCR** — Optical Character Recognition: software that turns an image of text into characters.
- **VLM (vision-language model)** — a neural model that "sees" an image and produces text/structure;
  Chandra 2 is one. Heavier and more capable than classic OCR, but needs a GPU.
- **olmOCR benchmark** — a widely used document-OCR accuracy test; higher % = better.
- **Detector vs recognizer** — classic OCR finds *where* text is (detector), then reads each line
  (recognizer). PaddleOCR works this way; VLMs do both at once.
- **Self-host** — run the model on your own machine, so data never leaves it.

© 2026 Vahini Technologies · companion to ARCHITECTURE.md and ROADMAP.md
