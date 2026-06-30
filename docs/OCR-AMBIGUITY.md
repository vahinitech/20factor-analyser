# Vahini — OCR for Ambiguous Handwriting (CRNN, TrOCR, LM decoding)

### How Vahini reads hard, non-cursive letters — and why recognition is *assistive*, not the score

This note answers a specific engineering question: when handwriting recognition has to tell apart
letters that look almost identical at the pixel level — **`l` vs `c`**, **`k` written as `ic`**,
**`e` that looks like `c` with a faint bar**, **`o` from a tight oval to a wide circle** — what is the
best pipeline?

**First, where this fits in Vahini.** Our objective is to **improve handwriting quality with AI, so a
learner can progress self-paced with minimal coach or parent help.** The 20 quality factors are measured
from *geometry* and do **not** depend on perfect text recognition. Recognition (OCR) is the **assistive**
layer that:
1. confirms *which* letter was attempted (so we can say "your `e` looks like a `c` — close the loop"), and
2. produces the recognised text used by the **Writing Craft** page (grammar, homophones, sign-offs).

So we don't need flawless OCR to score handwriting — but better OCR makes the *feedback* sharper. Below
is how to make it robust to exactly the confusions you listed.

> **Abbreviations.** **CRNN** = Convolutional + Recurrent Neural Network. **CTC** = Connectionist
> Temporal Classification (the segmentation-free loss/decoder CRNNs use). **LM** = Language Model.
> **ViT** = Vision Transformer. **TrOCR** = Transformer OCR (Microsoft). **n-gram** = a statistical model
> of which character/word sequences are likely. **KenLM** = a fast n-gram language-model library.

---

## 0. The key insight: ambiguity is rarely solvable from pixels alone

`l` vs `c`, or `e` vs `c`, can be **genuinely identical** in isolation — even a human can't be sure
without context. The fix is therefore **not** "a bigger vision model"; it is **three layers working
together**:

1. **Normalise the image** so style variation (slant, stroke width, the open/closed `o`) stops *creating*
   ambiguity in the first place.
2. **Give the recognizer context** (a sequence model + a language model) so it resolves the rest the way
   a human does — from the surrounding letters and words.
3. **Constrain with what you know.** In Vahini's stall flow the writer copies a **known reference
   passage**, so we can *align to the expected text* and turn a hard recognition problem into an easy
   verification problem (see §5 — this is the single biggest win for us).

---

## 1. Modifying a standard CRNN for these ambiguities

A baseline CRNN is: `CNN (visual features) → BiLSTM (sequence context) → CTC (alignment-free decoding)`.
Here are the targeted changes, cheapest-first.

### 1.1 Preprocessing — kill the ambiguity before the network sees it
The confusions you listed are largely *style* artifacts. Normalise them:
- **Deslant each word** (shear-search / projection-profile — the *same* method Vahini already uses for
  the slant factor). A consistent upright reduces `l`/`c` and italic-induced confusions.
- **Stroke-width normalisation** (morphological open/close, or skeleton + re-dilate). This is exactly the
  `o`-open-vs-closed and `e`-faint-bar problem: normalising thickness makes the faint `e` bar survive and
  stabilises round letters.
- **Height/baseline normalisation** to a fixed x-height so ascenders/descenders are consistent (helps the
  `k`→`ic` split, which is partly a scale/segmentation artifact).
- **Contrast/binarisation** (adaptive threshold) so faint marks like the `e` bar aren't lost.

### 1.2 Backbone — more context, less accidental segmentation
- Use a **stronger CNN** (ResNet/DenseNet-style) and, crucially, **keep horizontal resolution high**
  (downsample vertically more than horizontally). `k` getting read as `i`+`c` is an *over-segmentation*
  symptom; a wider horizontal receptive field lets the network see the whole `k` as one unit.
- Add **self-attention** over the feature sequence (or replace the BiLSTM with a small Transformer
  encoder). Attention models long-range dependencies, so the decision on an ambiguous glyph can lean on
  letters several positions away.

### 1.3 Confusion-aware training
- **Hierarchical / grouped loss:** add an auxiliary head that first predicts a *confusable group*
  (e.g. {c, e, o}, {l, i, t, 1}, {k, h}) and then the exact character. Gradients concentrate where it
  matters.
- **Class-balanced / focal loss** so rare-but-confusable characters aren't drowned out.
- **Label smoothing within confusion sets** so the model is calibrated, not over-confident — which makes
  the downstream language-model tie-breaker (§4) far more effective.

### 1.4 Decoding — add a language model (the real tie-breaker)
Plain CTC "greedy" decoding picks the top character at each step with **no context**, so it cannot resolve
`l`/`c`. Replace it with **CTC beam search + an n-gram LM** (§4). The LM rescoring is what turns
"`c` or `l`?" into "`l`, because `lct` is nonsense but `let` is a word." For known domains, also add a
**lexicon / FST constraint** so only valid words survive.

**Summary of the CRNN upgrade**

| Change | Fixes | Cost |
|---|---|---|
| Deslant + stroke/height normalise | `l/c`, `o` variation, faint `e` | low |
| Higher horizontal resolution backbone | `k → ic` over-segmentation | low–med |
| Self-attention / Transformer encoder | context-dependent letters | med |
| Grouped/confusion-aware loss + label smoothing | all confusable sets | med |
| **CTC beam search + KenLM (+ lexicon)** | every context-resolvable case | low |

---

## 2. CRNN+LM vs Vision Transformer (TrOCR) — which handles context better?

**Short answer.** TrOCR usually handles *context-heavy* ambiguity **better out of the box**, because its
decoder *is* a pretrained language model — but it is heavier, data-hungry and slower. For Vahini's
on-device/stall demo, **CRNN + CTC + KenLM (with reference-text constraint)** is the pragmatic choice;
TrOCR-small, fine-tuned, is the upgrade path for the genuinely hard free-form cases server-side.

| Dimension | CRNN + CTC (+ KenLM) | TrOCR / ViT encoder–decoder |
|---|---|---|
| **How it resolves ambiguity** | Vision features + RNN context, then an **external** n-gram LM rescoring | An **internal**, pretrained Transformer LM decoder attends over the whole line |
| **Context strength** | Good (n-gram window) | **Excellent** (full-sequence attention, learned language priors) |
| **Data needed** | Modest; trains well on synthetic + a few real | **Large**; benefits from big pretraining/fine-tuning |
| **Compute / latency** | **Light, fast, CPU-friendly** | Heavy; GPU preferred; slower per line |
| **Model size** | Small (a few MB–tens of MB) | Large (hundreds of MB) |
| **Explainability / control** | High — you can swap the LM, add a lexicon, force alignment | Lower — the LM is baked in |
| **Best when** | Known/limited vocabulary, edge/offline, speed matters | Free-form text, messy real-world pages, accuracy first |

**Why TrOCR is strong on your examples:** `e`-vs-`c` or `l`-vs-`c` are *language* decisions; TrOCR's
decoder was pretrained on huge text, so it "knows" `hello` not `hcllo`. A CRNN gets the same benefit only
when you bolt on the n-gram LM — which is exactly what §4 does, far more cheaply.

**Why not just use TrOCR for Vahini:** it's overkill for the stall demo (offline, instant, low-power) and
its size/latency hurt the experience. We get most of the contextual benefit from CRNN+KenLM, plus the
reference-text constraint (§5) that *neither* model needs heavy compute to exploit.

---

## 3. Data augmentation, synthetic text & hard negatives

You can't fix `l/c` confusion without showing the model many `l`s and `c`s in context, in many styles.

### 3.1 Synthetic handwriting generation
- **Handwriting fonts + a text corpus** (e.g. TextRecognitionDataGenerator / "trdg"): render real words in
  dozens of handwriting fonts → instant labelled data with perfect ground truth.
- **GAN-based synthesis** (e.g. ScrabbleGAN) for realistic, varied human-like styles when fonts look too
  clean.
- Render from a **real-word lexicon** (and the actual reference passages you use at the stall), so the LM
  and recognizer see the exact words they'll meet.

### 3.2 Style augmentations that target *your* confusions
| Confusion | Augmentation that teaches the fix |
|---|---|
| `o` circle ↔ oval | **affine/anisotropic scaling** (squash/stretch width), **elastic distortion** |
| `e` looks like `c` | **stroke-width jitter** (morphological dilate/erode) so the model learns the bar matters; **random thinning** |
| `l` vs `c` / `i` `1` | **random slant/shear** (so slant isn't a cue), **elastic warp** |
| `k → ic` split | **random spacing/kerning** + **blur** so the model learns to keep the glyph whole; vary stroke joins |
| general | rotation ±5°, perspective, background paper textures, ink-bleed, JPEG noise, line removal |

### 3.3 Hard-negative mining (the part most people skip)
- Build a **confusion matrix** on a validation set, find the top confused pairs, then **oversample**
  training crops of those exact characters *in context*.
- Generate **minimal pairs**: render `let`/`lct`, `book`/`bcok`, `kid`/`icid`, `code`/`codc` … and feed the
  wrong ones as **hard negatives** so the model learns the boundary.
- **Confusion-driven batch sampling:** each batch reserves a fraction for the currently-hardest pairs;
  refresh from the live confusion matrix every few epochs (a simple curriculum).
- **Triplet / metric-learning auxiliary loss** on glyph embeddings to push `c`, `e`, `o` apart in feature
  space.

---

## 4. Python: KenLM + CTC beam-search decoding (the contextual tie-breaker)

This integrates an n-gram language model into CTC decoding so context resolves the ambiguous characters.
The standard, production-grade tool is **`pyctcdecode`** (used with KenLM). It works for **character-** or
**word-level** n-grams.

```python
# pip install pyctcdecode kenlm numpy
#
# 1) Train a KenLM n-gram once (offline), e.g. a 5-gram char LM:
#      lmplz -o 5 < corpus_chars.txt > char5.arpa
#      build_binary char5.arpa char5.binary
#    (corpus_chars.txt = your text with spaces between characters for a char-LM,
#     or normal words for a word-LM.)

import numpy as np
from pyctcdecode import build_ctcdecoder

# The label set your CRNN's softmax produces. Index 0 is the CTC "blank".
# Order MUST match the model's output classes (blank first for pyctcdecode).
labels = [""] + list("abcdefghijklmnopqrstuvwxyz '")   # "" == CTC blank

decoder = build_ctcdecoder(
    labels,
    kenlm_model_path="char5.binary",   # the n-gram LM that knows real letter sequences
    alpha=0.5,    # LM weight  — how much context overrides the vision model
    beta=1.0,     # length/word bonus — discourages dropping characters
)

def decode(logits, beam_width=100, hotwords=None):
    """
    logits: np.ndarray of shape (T, num_labels) — per-timestep log-probs from the CRNN.
    hotwords: optional list of expected words to bias toward (great for Vahini —
              pass the reference-passage words so 'let' beats 'lct').
    """
    return decoder.decode(
        logits,
        beam_width=beam_width,
        hotwords=hotwords,            # e.g. ["the","quick","brown","fox"]
        hotword_weight=10.0,
    )

# --- usage ---
# logits = crnn_model.predict(preprocessed_word_image)   # (T, num_labels), log-softmax
# text   = decode(logits, hotwords=reference_passage.split())
# print(text)   # 'hello' instead of 'hcllo'; 'kite' instead of 'icite'
```

**What each knob does (in plain words):**
- **`alpha` (LM weight):** how strongly the language model is allowed to overrule the pixels. Raise it when
  the handwriting is ambiguous; lower it if the LM starts "correcting" genuinely odd spellings.
- **`beta` (word/length bonus):** stops the LM from cheating by deleting characters.
- **`hotwords`:** a soft bias toward words you expect — for Vahini, the **reference-passage words**, which
  makes the decoder strongly prefer the intended text.

> No KenLM? A pure-Python **character n-gram** (a dict of `P(next_char | previous k chars)`) plugged into a
> hand-rolled beam search gives most of the benefit for small alphabets — but `pyctcdecode`+KenLM is the
> robust, fast default.

---

## 5. Vahini's strongest lever: you already know the expected text

At the stall, the writer copies a **known reference passage** (`Vahini Sample Text.html`). That changes
the problem profoundly:

- **Alignment-constrained decoding.** Instead of free recognition, align the CRNN output to the *expected*
  string with edit-distance / forced alignment (or pass the expected words as `hotwords`/lexicon). Now
  `l` vs `c` is trivial: we already know the target letter, so we only ask **"how well does the written
  glyph match the expected letter?"**
- **This directly powers the feedback.** Per-letter match scores tell us *exactly* which letters were
  malformed — "your `e` is closing like a `c`", "your `k` is splitting" — which is precisely the
  improvement guidance our objective calls for, and feeds the per-factor and Writing-Craft pages.
- **It's cheap and offline.** No big model needed; a light CRNN (or even the geometry + alignment) plus the
  known text yields reliable, explainable results on low-power hardware.

**Recommended Vahini pipeline:**
```
Preprocess (deslant + normalise)
   → light CRNN + CTC  (logits)
   → CTC beam search + KenLM, biased by the reference passage (hotwords/lexicon)
   → align to expected text  → per-letter match + recognised text
   → feeds: Writing-Craft checks + "which letters to fix" guidance
(Server option for free-form pages: fine-tuned TrOCR-small.)
```

---

## 6. Practical recommendations (TL;DR)

1. **Normalise first** (deslant, stroke-width, height) — removes most `l/c`, `o`, faint-`e` ambiguity for free.
2. **Keep horizontal resolution high** so `k` isn't split into `ic`.
3. **Always decode with an n-gram LM** (`pyctcdecode` + KenLM) — the cheapest, biggest accuracy jump.
4. **Use a lexicon / reference-text constraint** whenever the expected words are known (the Vahini stall case).
5. **Mine hard negatives** (minimal pairs of your confusable letters) and **augment** with slant, stroke-width
   and elastic distortion.
6. **CRNN+LM for edge/offline/known-vocab; TrOCR-small (fine-tuned) server-side for hard free-form text.**
7. Remember the bigger picture: in Vahini, recognition is **assistive**. Even imperfect OCR still yields
   useful, encouraging, self-paced handwriting guidance — which is the whole objective.

---

© 2026 Vahini Technologies · IMU Sensor Pen, Patent No. 584433 · vahinitech.com
