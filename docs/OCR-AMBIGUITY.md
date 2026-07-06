# OCR for ambiguous handwriting: what shipped, and what was explored but did not

This document started as an engineering exploration of one question: when a
letter is genuinely ambiguous at the pixel level, `l` vs `c`, `k` written as
two strokes that look like `ic`, `e` with a faint bar that looks like `c`,
what is the best recognition pipeline? That exploration considered training
a custom CRNN with language-model decoding. The system that actually
shipped took a different, simpler path: pretrained OCR engines combined
with reference-passage alignment. This document now describes both, and is
explicit about which one is real.

Recognition in Vahini is assistive, not the score. The 20 quality factors
are measured from geometry and do not depend on reading the words
correctly. OCR exists to confirm which letter was attempted and to produce
the text the Writing Craft page checks for grammar and homophones.

## What shipped

**Pretrained engines, not a custom-trained model.** PaddleOCR (PP-OCRv5,
optionally PP-OCRv6) detects every line and reads printed text well.
Hybrid mode adds two recognisers for handwriting specifically: TrOCR for
English, Surya for Telugu, Hindi, Tamil, Kannada and Malayalam, routed per
line by script. Paddle's own detection and printed-vs-handwriting
classification are kept either way; only the recognisers change. None of
this needed training data collection, a custom CTC decoder, or a language
model integration, because the pretrained checkpoints already carry that.

**A guarded acceptance policy instead of always trusting the specialist.**
TrOCR and Surya are language-model recognisers: excellent on clear input,
prone to inventing plausible-looking text on input they cannot actually
read (`recognizer.refine_handwriting_text` has a real example: "Hypothyoidum"
misread as "Transportation legislation"). A specialist's re-read is
accepted when it either roughly agrees with paddle's own reading, or the
specialist's own confidence is high enough on its own. Paddle is not a
handwriting specialist either, so on genuinely hard handwriting its
reading can itself be wrong; requiring agreement with a wrong baseline
would throw away real corrections, which is why the confidence path exists
alongside the agreement path.

**Reference-passage alignment, which is section 5 below, actually built.**
When a writer copies a known passage, `recognizer.align_to_expected` matches
each recognised line against the expected text by normalised string
similarity, not a custom decoder or lexicon bias. When the match is close
enough, the report shows the known correct text instead of the raw OCR
output, and the match score itself becomes a real per-line accuracy
number. This is the single biggest accuracy win described in the original
exploration, and it works with off-the-shelf OCR, no custom training
needed.

**A CPU-speed check, not a fixed setting.** Whether a machine can afford to
run the extra specialist recognisers is measured, not guessed: each engine
call is timed, and once it measures slower than a threshold it is skipped
for the rest of that scan and for a cooldown period, falling back to
paddle's own reading. See `analyser/server/README.md`'s hybrid-mode section.

## What was explored and not built

The rest of this document is the original engineering exploration of a
custom pipeline, kept for reference in case a from-scratch model is ever
worth building. None of it shipped: no CRNN was trained, no KenLM language
model exists in this codebase, and `pyctcdecode` is not a dependency.

### The key idea

`l` vs `c`, or `e` vs `c`, can be genuinely identical in isolation, even to
a human, without context. The fix explored was three layers: normalise the
image so style variation stops creating ambiguity, give a sequence model
enough context to resolve the rest the way a human would, and constrain
with a known reference text where one exists (the layer that did ship).

### A modified CRNN, if one were ever trained

A baseline CRNN is a CNN for visual features, a BiLSTM for sequence
context, and CTC for alignment-free decoding. Targeted changes considered,
cheapest first:

- Deslant each word and normalise stroke width and baseline height before
  the network sees it. Most of the listed confusions are style artifacts,
  not genuine ambiguity, and normalising removes them for free.
- Keep horizontal resolution high relative to vertical, since `k` read as
  `ic` is usually an over-segmentation artifact from a receptive field
  too narrow to see the whole letter as one unit.
- Add self-attention, or a small Transformer encoder in place of the
  BiLSTM, so a decision on an ambiguous glyph can lean on letters several
  positions away.
- Train with a confusion-aware loss: an auxiliary head that predicts a
  confusable group first (`{c, e, o}`, `{l, i, t, 1}`, `{k, h}`), then the
  exact character, with label smoothing within each group.
- Decode with CTC beam search plus an n-gram language model
  (`pyctcdecode` and KenLM), which is what actually resolves
  context-dependent ambiguity: "l, because lct is nonsense but let is a
  word."

### CRNN plus a language model versus a Vision Transformer decoder

TrOCR's decoder is itself a pretrained language model, so it tends to
resolve context-heavy ambiguity better out of the box than a CRNN with a
bolted-on n-gram model, at the cost of being heavier and slower. A CRNN
with CTC and KenLM was the pragmatic choice explored for a fully offline,
on-device deployment; TrOCR was the fallback for harder free-form text
where compute is available. In the shipped system, TrOCR is simply one of
the pretrained engines hybrid mode calls, not a fallback from a custom
CRNN that never existed.

### Data augmentation and hard-negative mining, if training were needed

Fixing a specific confusion pair needs many examples of both letters, in
context, in varied styles: synthetic handwriting fonts or GAN-based
synthesis for labelled data, style augmentations targeted at each
confusion (anisotropic scaling for round letters, stroke-width jitter for
faint marks, random shear so slant is not a shortcut), and hard-negative
mining: build a confusion matrix on real predictions, oversample the worst
pairs, and generate minimal-pair examples like `let`/`lct` as explicit
wrong answers to train against.

### KenLM and CTC beam-search decoding, if a custom decoder were built

`pyctcdecode` with a trained KenLM n-gram model is the standard way to add
context to CTC decoding. The language-model weight controls how strongly
context can override the raw pixels, a length bonus stops the decoder from
deleting characters to cheat, and a hotword list biases toward expected
words, which for Vahini would have meant the reference-passage words. This
is precisely what `align_to_expected` achieves today by a simpler route:
matching against the known passage directly, after recognition, rather
than biasing a custom decoder during recognition.

## Summary

Normalisation and a language-model tie-breaker were both correct
instincts. They arrived in the shipped system through pretrained engines
and post-hoc alignment against known text, not through training a custom
model. If per-letter confusion ever becomes the accuracy bottleneck again,
after Telugu and Hindi sample collection gives real numbers to act on, the
CRNN and KenLM path above is still the documented next step. Until then,
the pretrained-engine-plus-alignment approach reaches the same result for
far less engineering cost.
