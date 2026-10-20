# Languages: one analyser, many scripts

This is a design, not a description of the code. Nothing below is built yet
except where a section says "today". It explains how the analyser should
grow from English (plus Telugu in development) to German, Hindi and the
English variants without copying the 20 factors once per language, and the
order to build it in. Builds on
[01-system-architecture.md](01-system-architecture.md),
[02-how-a-scan-works.md](02-how-a-scan-works.md),
[03-scoring-criteria.md](03-scoring-criteria.md) and
[06-reading-engines.md](06-reading-engines.md).

Line references are to `main` at 2ee37f4 (20 October 2026). Work is
tracked in #217, one issue per step of section 12.

## 1. The problem today

English is not a setting in the analyser; it is spread through the code as
letter lists and `[A-Za-z]` tests. Each module decided for itself what
"Latin" means:

| Where | What it assumes |
|---|---|
| `backend/scoring.py:502-505` | loop letters `[aodpegq]`, tall letters `[bdfhkltgjpqy]` |
| `backend/scoring.py:620` | `BOWL_LETTERS = set("abdegopq")` |
| `backend/scoring.py:673` | `_LATIN_ONLY = (3, 6)`, factors that count Latin letters |
| `backend/scoring.py:744` | about 5 letters per word as the ideal (factor 15) |
| `backend/zone_analysis.py:55-57` | ascenders `[bdfhklt]`, descenders `[gjpqy]`, `[A-Za-z]` |
| `backend/letter_geometry.py:43` | x-height letters `acemnorsuvwxz` |
| `backend/tbar_analysis.py:35-36` | the `tt` and `t[lhkb]` patterns |
| `backend/finishing_letters.py:22-24` | finishing letters `adhilmnrtu`, words `[A-Za-z]+` |
| `backend/style_analysis.py:44,56,69` | cursive check only above 90% ASCII letters |
| `backend/coach_tips.py:65` | `_latin_share`, gating seven tips at 0.9 (lines 264 to 612) |
| `backend/classify.py:49,200,291` | English form words, uppercase share, `[A-Z]{5,}` |
| `backend/computer_vision.py:275,865` | fallback lines tagged `"en"`, `[A-Za-z]` letter count |
| `backend/line_recovery.py:188,252` | `lang="en"` defaults |
| `backend/recognizer.py:53,232` | `_INDIC_LANGS` sends te/hi/ta/kn/ml to Surya, the rest to TrOCR |
| `backend/ocr_backends.py:55` | a line is Telugu if any character is in U+0C00 to U+0C7F |
| `backend/ocr_backends.py:661` | TrOCR model fixed to `microsoft/trocr-base-handwritten` (English) |

Telugu today is a set of exceptions on top of that. The script is known
only from the characters the reader returned (`ocr_backends.py:55`);
nothing looks at the ink to decide it. `recognizer.telugu_not_read`
(`recognizer.py:383-415`) refuses a Telugu page unless Telugu letters are
at least 75% of the letters read and the mean confidence is at least 0.80.
`VAHINI_INK_GEOMETRY_LANGS` (`config.py:153`, empty by default) measures a
Telugu page from rows found in the ink without reading it, and then only
factors 7, 8, 11, 12 and 20 are measured that way (`scoring.py:814`).
Factors 3 and 6 report "script_not_supported" when no Latin letters were
read (`scoring.py:941-945`, `1029-1033`).

One more gap shows how deep the assumption goes. The passage alignment
normalises text with `re.sub(r"[^\w ]", "", ...)` (`recognizer.py:441`).
Python's `\w` does not match combining marks, so every vowel sign and
virama is dropped: పిల్లి compares as పలల and हिंदी as हद. Alignment
against a Telugu or Hindi worksheet compares consonant skeletons.

Adding German this way would mean a third set of exceptions; Hindi a
fourth. The fix is to move every one of these facts into data, keyed by
script and language, and have the code ask for them.

## 2. Six layers

| # | Layer | Language-aware? | Output |
|---|---|---|---|
| 1 | Photo and ink | No | cleaned image, ink mask, rows with baselines, ink blobs |
| 2 | Script and language decision | Yes | one decision per line: tag, source, confidence |
| 3 | Recognition | Yes, by registry | lines, words and graphemes with boxes and confidence |
| 4 | Measurements | Through pack data only | named features (row slopes, gaps, zone heights, loop closure) |
| 5 | 20-factor scoring | Through pack data only | 20 results, each scored or "Not measured" with a reason |
| 6 | Report and practice | Yes | words, tips and worksheets in the family's language |

Layers 1, 4 and 5 hold no language names. They receive a resolved
language pack and read facts from it ("which letters close a loop", "where
are the zones"). A test enforces this (section 12, step 1).

Layer 1 is mostly built: `ink_geometry.py` already finds rows and
baselines without reading anything, and that is what makes it the common
ground for every script.

## 3. Names

Every language is a BCP 47 tag with an explicit script subtag inside the
analyser: `en-Latn-IN`, `en-Latn-US`, `en-Latn-GB`, `de-Latn-DE`,
`te-Telu-IN`, `hi-Deva-IN`. Script codes are ISO 15924 (`Latn`, `Telu`,
`Deva`). The request may keep sending short tags (`en`, `te`); the server
fills in the script and a default region, so `te` resolves to
`te-Telu-IN`.

## 4. Language packs

A pack is a JSON file of facts. Packs inherit, most general first:

```
base  ->  script (Latn, Telu, Deva)  ->  language (en, de, te, hi)  ->  locale (en-IN, en-US, en-GB, de-DE)
```

JSON rather than YAML because the backend has no YAML dependency today and
the contracts are JSON Schema already. Proposed layout:

```
backend/languages/
  registry.py               load, inherit, validate, cache
  pack.schema.json
  scripts/Latn.json  Telu.json  Deva.json
  langs/en.json  de.json  te.json  hi.json
  locales/en-IN.json  en-US.json  en-GB.json  de-DE.json
```

What lives at each level:

| Level | Holds |
|---|---|
| Script | Unicode ranges; the writing unit (letter for Latin, akshara for Telugu and Devanagari); the zone model; letter classes (closes a loop, rises above the body, drops below the baseline, carries a mark above); confusable pairs |
| Language | alphabet and marks in use; average word length; finishing letters; words that mark a printed form; recogniser preferences; tip and exercise catalogue ids |
| Locale | the letter model taught in school; spelling variant; ruling (four-line notebook, single line); norm bands by age |

The Latin pack starts as exactly today's constants, so the first version
changes no score:

```json
{
  "script": "Latn",
  "unicode": ["0041-005A", "0061-007A", "00C0-024F"],
  "unit": "letter",
  "zones": ["ascender", "body", "descender"],
  "zone_ratio": {"body_to_ascender": 0.5},
  "classes": {
    "loop": "aodpegqAODPEGQ",
    "bowl": "abdegopq",
    "ascender": "bdfhklt",
    "descender": "gjpqy",
    "body_only": "acemnorsuvwxz"
  }
}
```

The zone models differ by script, and this is where most of the real work
is:

- **Latin:** ascender line, body (x-height), baseline, descender line.
  Today's 1:2 rule in `zone_analysis.py`.
- **Devanagari:** a headline (shirorekha) joins the letters of a word along
  the top; some vowel signs sit above it, others below the body. The
  headline is a strong anchor that Latin does not have: a straight,
  continuous headline is a measurable sign of control.
- **Telugu:** no headline. The tick on top of many consonants (talakattu)
  belongs to the letter, vowel signs attach above and to the right, and
  the subjoined consonants (vattulu) sit below the row, often written
  apart (`ink_geometry.py` already allows for this when it fits
  baselines).

The Telugu and Devanagari letter classes are not written by an engineer
guessing. Each list is reviewed by a teacher of that script, checked
against the script sheets from vahinitech/EdTechBooks, and the reviewer is
recorded in the pack.

## 5. Script and language decision

Decided per line, because an Indian page often mixes English and Telugu.
Sources, strongest first:

1. **The worksheet.** When the page is one of our sheets, its manifest
   already says the script and the exact text.
2. **The family's choice** (the request `lang`).
3. **An image classifier** on each line crop that never reads a letter.
   It is the same kind of small model as `print_hand.py`, trained on line
   crops of Latin, Telugu and Devanagari writing.
4. **The reader's output** as a cross-check: the Unicode script of the
   recognised characters, which is the only signal used today.

If the sources disagree beyond a set margin (the family chose Telugu, the
classifier and the reader both see Latin), the page is refused with a
clear message, as `telugu_not_read` does now. A guessed language gives a
different score for the same photo, which breaks the rule in
[02-how-a-scan-works.md](02-how-a-scan-works.md) that the same photo gets
the same score. "auto" without a worksheet uses 3 and 4 only.

The image settles the script, not the language. English and German are
both Latin, and no ink classifier tells them apart. Within a script the
language comes from the recognised text: a small language-identification
model over the line's words, with a language model as the tie-breaker
only when that is unsure (section 16).

The decision goes into the response with its source, so a report can be
traced back to why it was scored as Telugu.

## 6. Recognition registry

`_INDIC_LANGS` and the TrOCR default become one table: for each script, the
engines in order of preference, each with the model id and the maturity it
has reached on our pages.

| Script | Today | Registry entry, first try |
|---|---|---|
| Latn | Paddle PP-OCRv5 server rec; TrOCR base handwritten in hybrid | same; German needs a model that reads ä ö ü ß |
| Telu | Paddle `te_PP-OCRv5_mobile_rec`; Surya in hybrid | same, plus the trained line reader when it lands |
| Deva | Surya in hybrid | Surya; Chandra OCR 2 is listed in 06 as stronger on Indic and is not deployed |

Every engine returns the same shape: lines, words and graphemes, each with
a box and a confidence, text in Unicode NFC. Layers 4 and 5 never see an
engine name.

## 7. Graphemes and copy tasks

Counting characters is wrong for Indic scripts: one written akshara can be
three code points (consonant, virama, consonant) plus a vowel sign. The
measuring unit is the grapheme cluster (Unicode extended grapheme clusters,
with the akshara rule for Telu and Deva), and every per-letter feature
counts in those units.

The copy task is the strongest tool we have for every language.
`align_to_expected` (`recognizer.py:417`) and the request's
`expected_text` already turn free reading into checking a known passage.
The design keeps that and fixes it for Indic scripts: compare grapheme by
grapheme with marks kept, so a missing vowel sign is a difference and not
an invisible one. Worksheets give the expected text, so a child writing on
our Telugu sheet can be measured long before open Telugu reading is good.

## 8. Measurements and what each factor needs

Each factor declares what it needs; the scoring layer checks the needs
against what layers 1 to 3 produced for this page and this script. When a
need is missing, the factor is "Not measured" with the reason, never a
number estimated from the wrong script. Today's three special lists
(`_LATIN_ONLY`, `_NEEDS_RECOGNITION` at `scoring.py:804`, `_INK_MEASURED`)
are replaced by this one rule.

Needs: `rows` (ink rows with baselines), `words` (word boxes), `graphemes`
(read graphemes with boxes), `confidence` (reader confidence), `zones` (the
pack's zone model fitted to the page), `classes` (a letter class from the
pack), `sensor` (pen data).

| # | Factor | Needs | Notes |
|---|---|---|---|
| 1 | Letter Formation Accuracy | rows, confidence | |
| 2 | Stroke Order Consistency | graphemes, confidence | |
| 3 | Loop Closure | graphemes, classes.loop | Telugu has many closed shapes; needs the reviewed list |
| 4 | Line Quality (Smoothness) | rows | |
| 5 | Size Consistency | rows | body-only class sharpens it where the pack has one |
| 6 | Ascender / Descender Control | zones | becomes "zone control" per script (see section 10) |
| 7 | Baseline Alignment | rows | |
| 8 | Word Spacing | words | from a passage when the script has no reliable word reader |
| 9 | Letter Spacing | rows or graphemes | |
| 10 | Margin Discipline | rows | |
| 11 | Line Straightness | rows | |
| 12 | Vertical Alignment | rows | |
| 13 | Speed Consistency | sensor | |
| 14 | Pressure Consistency | sensor | |
| 15 | Stroke Continuity | sensor | its word-length term moves to the language pack |
| 16 | Pen Lift Frequency | sensor | |
| 17 | Slant Consistency | words | |
| 18 | Legibility | composite of 1, 5, 7, 8 | measured when its parts are |
| 19 | Character Distinction | graphemes, confidence | confusable pairs from the pack |
| 20 | Overall Neatness | composite of 5, 8, 10, 11, 17 | measured when its parts are |

Two thirds of the factors need only rows and words. That is why a new
script can start giving useful, honest results before anyone can read it.

## 9. Norms

The target bands in `scoring.py` were fitted on Latin writing, and the
roadmap already lists that as a gap for Telugu
([16-roadmap.md](16-roadmap.md)). Bands become a table keyed by factor,
script and age band, stored with the locale pack. A cell with no fitted
band falls back to the script's band, then to today's band marked
provisional. A provisional band is never shown as a firm score; how that
looks on the report is an owner decision (section 10).

## 10. Report and practice

The practice catalogue already has a language list (`practice_catalog.py:130`,
`LANGUAGES = ("te",)`) and a `script` field on each exercise that must be
`any` or `latin` (`practice_catalog.py:1920`). That field grows to script
codes. Tips gated by `_latin_share` move to the same pack lookup.

**Report changes need the owner's approval first.** Renaming factor 6 to
"zone control", showing which language a page was scored as, marking a
band as provisional, or showing a Telugu factor name on the printed page
all change the report. Each needs before and after screenshots and
@vkosuri's approval in the issue or PR, under
[12-report-rules.md](12-report-rules.md#report-format-baseline-owner-approval-required).
Until then the report keeps its current labels, and the new fields live
only in the JSON.

## 11. Maturity levels

Each language pack carries its level. The server never scores above it.

| Level | What runs | Example today |
|---|---|---|
| 0 | Practice sheets only; the check refuses the page | Hindi, Tamil, Kannada |
| 1 | Ink geometry: factors from rows and passages; the rest "Not measured" | Telugu, behind `VAHINI_INK_GEOMETRY_LANGS` |
| 2 | Reading: a recogniser passes a held-out set of real pages; letter-shape factors turn on | |
| 3 | Calibrated and public: bands fitted on children's pages in that script, and a public test page passes | English |

Level 3 is the only one the website may claim. vahini-web holds the same
rule: Telugu scoring is not claimed until a public test shows it works (a
test on 19 October 2026 found the sinking line on 1 page in 20). The bar
for each step (pages, accuracy) is set per language by the owner and
written into the pack, the way `TELUGU_MIN_SHARE` and
`TELUGU_MIN_CONFIDENCE` are constants today.

## 12. Build order

Each step is one PR, and each keeps the benchmark green
([18-benchmark.md](18-benchmark.md)). Steps 1 to 3 must not move a single
number in `benchmarks/*/expected.json`.

1. **Packs for what exists, no behaviour change.** (#206) Add
   `backend/languages/` with the registry, the schema and `Latn`/`en`
   packs holding today's constants. Point `scoring.py`, `zone_analysis.py`,
   `letter_geometry.py`, `tbar_analysis.py`, `finishing_letters.py`,
   `style_analysis.py`, `coach_tips.py` and `classify.py` at the pack.
   Add a test that fails on a letter list, `[A-Za-z]`, a Unicode script
   range or `isascii()` in a scoring module outside `backend/languages/`.
2. **Factor needs.** (#207) Declare `needs` for the 20 factors and replace
   `_LATIN_ONLY`, `_NEEDS_RECOGNITION` and `_INK_MEASURED` with the one
   check. The "Not measured" reasons stay word for word.
3. **Recognition registry.** (#208) Replace `_INDIC_LANGS`
   (`recognizer.py:53`) and the TrOCR default (`ocr_backends.py:661`) with
   registry lookups; engines return graphemes.
4. **Graphemes and alignment.** (#209) A grapheme splitter, and
   `align_to_expected` comparing graphemes with marks kept. English is
   unchanged; Telugu alignment gets stricter, which is the point.
5. **Script decision, logging only.** (#210) The per-line decision from section
   5, recorded next to today's character-based tag on every scan but not
   used, until the two have been compared on real pages.
6. **Script decision in charge** (#211), with the refusal on disagreement.
   `telugu_not_read` becomes the general case.
7. **Request contract** (#212, section 13).
8. **Telugu pack:** (#213) zones, loop and mark classes reviewed by a Telugu
   teacher; ink geometry reads it. Level 1 to 2 when the reader passes.
9. **German pack:** (#214) `de` and `de-DE`, the letter models taught in German
   schools, ä ö ü ß in the classes, a reader that keeps them, and the
   English form words in `classify.py` checked against German pages.
10. **Hindi pack:** (#215) `Deva` zones with the headline, a headline continuity
    measurement, and Surya as the first reader.

11. **Language-model service** (#218), off by default: the `ScriptJudge`
    and `Reader` interface, a local adapter first, measured like any
    other reader before it enters the registry (section 16). It can start
    after steps 3 and 5; an API adapter waits for the owner's privacy
    decision.

Norm tables (section 9, #216) start as soon as there are real children's
pages for a script; they do not wait for step 10.

## 13. Contract change

The request schema allows `^([a-z]{2,8}|auto)$`
(`schemas/report-request.schema.json:54`). `resolve_langs`
(`recognizer.py:64-73`) already accepts comma lists such as `en,te`, which
that pattern rejects, so the schema is already narrower than the server.

Proposed pattern, which keeps every value valid today:

```
^(auto|[a-z]{2,3}(-[A-Z][a-z]{3})?(-[A-Z]{2})?(,[a-z]{2,3}(-[A-Z][a-z]{3})?(-[A-Z]{2})?)*)$
```

The response gains, additively: a `language` object (resolved tag, source
of the decision, pack level) and a `script` per line. The cache key
already includes `lang` (`cache.py:32`); it should use the resolved tag so
`te` and `te-Telu-IN` share an entry.

Order across repositories, as always: this repository's PR first, then the
contracts sync and tag in Umbrella, then vahini-web and the app.

## 14. Which language next

**English variants are not new languages here.** `en-US`, `en-GB` and
`en-IN` share the script, the reader and every factor. They differ in the
letter model taught in school, spelling (colour and color), the paper (the
four-line notebook common in Indian primary schools) and, once there is
data, the age bands. That is a locale file each, not code.

**German is mostly a pack.** It is Latin, so steps 1 to 4 do most of the
work. The new facts are ä ö ü ß, nouns written with a capital, longer
compound words (the word-length term in factor 15), and the school
scripts: German states choose between Lateinische Ausgangsschrift,
Vereinfachte Ausgangsschrift, Schulausgangsschrift and the print-based
Grundschrift, so `de-DE` needs a way to say which one a child learned.

**Hindi is the strongest choice after those.** In the 2011 Census 43.6% of
people in India gave Hindi as their mother tongue, and in 2024 Hindi was
the most chosen medium for the class 10 and 12 board exams (39.3%). It
shares Telugu's structure (consonants with vowel signs, conjuncts), so the
akshara work for Telugu carries over, and its headline gives a new
measurement for free. Surya already reads it in hybrid mode. The weak spot
is data: DohaScript (February 2026, 531 writers) is adult handwriting, and
there is no public set of children's Devanagari writing that we found. We
would collect our own, as for Telugu.

After Hindi, Kannada is the cheapest next Indic script because its letter
shapes are close to Telugu's.

## 15. What this does not cover

Spelling, grammar and phonetics are a separate layer and stay out of the
20 factors. Handwriting quality does not depend on whether a word is spelt
right. When that layer comes, it runs on copy tasks and dictation only,
where the expected text is known. On 7 October 2026 a 104,000-word
English dictionary run over one fixture photo flagged 31 of 81 recognised
words, nearly all of them reader mistakes rather than the child's, so a
dictionary on open writing measures the reader, not the writer. For Telugu
the useful checks are phonetic: short and long vowel signs, aspirated and
plain consonants, and conjuncts.

## 16. Language models: where they help and where they do not

A vision-language model (a local one, or an API such as Claude, Gemini or
GPT) can help in two layers: deciding the script and language (layer 2)
and reading (layer 3). Measuring and scoring (layers 4 and 5) stay with
OpenCV and the deterministic code in `scoring.py`. A language model never
produces a number that goes into a factor. Every score has to trace to
code ([03-scoring-criteria.md](03-scoring-criteria.md)), and the same
photo has to get the same score.

**Script and language decision.** A language model is a fifth source in
section 5, asked only when the cheaper sources are unsure: the image
classifier gives no clear script, or the language-identification model
cannot choose between two languages of one script. It never overrides
the worksheet or the family's choice; if it disagrees with them the page
is refused, as with any other disagreement.

**Reading.** A language model is one more engine in the registry (section
6), not a replacement for it. The analyser already runs two
vision-language readers, Surya and PaddleOCR-VL (`ocr_backends.py:785`,
`:905`), and already guards against them: a stronger engine's reading
replaces Paddle's only when the two are at least 0.70 similar or the
engine is very sure (`config.py:133-143`), because below that the
difference was mostly invented text. A general language model gets the
same guard, and three more rules:

- **It must copy, not correct.** A language model reads what the child
  meant: it fixes a misspelling, closes an open letter, finishes a word.
  For a handwriting check that is wrong, because the mistakes are what we
  measure. The prompt asks for an exact transcription, the answer is
  compared with the classic reader, and on a copy task with the
  worksheet's text. When the model's text matches the worksheet better
  than the ink does, that is a warning sign, not a success.
- **Its confidence is not used.** Factors 1, 2 and 19 use the reader's
  per-character confidence. Language models do not give a calibrated one,
  so those factors keep the classic reader's confidence, or are "Not
  measured" when only the language model could read the line. The model
  may mark words it is unsure of; that marks a line, it is not a score.
- **Fixed answers.** A pinned model version (weights hash for a local
  model, the dated version for an API), greedy decoding, a versioned
  prompt, a JSON schema for the answer, and the answer cached by photo,
  model and prompt version. An answer outside the schema counts as no
  answer. An API that changes the model behind the same name changes
  scores, so the version goes into the response and into the benchmark's
  Layer B run.

**Where it runs.** Not in the analyser container. That container has a
2.5 GB memory limit on a shared CPU host and one scan already peaks near
1.6 GB ([13-api-and-capacity.md](13-api-and-capacity.md)); a 3 to 7
billion parameter vision model needs a GPU. The language model is a
separate service behind one internal interface (`ScriptJudge` and
`Reader`), with adapters for a local server (vLLM, llama.cpp or Ollama on
a GPU machine) and for API providers. Off by default. The analyser works
the same without it, with a timeout and a recorded "not asked" when it is
slow or down.

**Privacy.** An API model means a child's handwriting leaves our server.
Today's rule is that no deployed engine does that, and that a cloud API
needs explicit consent and a privacy review first
([06-reading-engines.md](06-reading-engines.md)); Chandra OCR 2 was removed
for this reason. That rule stands. A local model on our own GPU keeps the
photo on our machines and is the default path. An API path needs the
owner's decision, a provider that keeps nothing, a consent line for the
family, and the matching change to vahini-web's privacy page. Even then it
gets line crops after the layout filter, never the whole page, so a name
written at the top does not travel.

**Words, not runtime.** Language models are useful for drafting tips,
exercises and report strings in a new language at build time. A teacher
of that language edits them, and they go into the practice catalogue like
any other text. They are never generated per child at scan time.

**How it is judged.** Like any reader: character error rate per script on
the benchmark sets and on real photos, the share of lines where it
"corrected" the child, the share of answers outside the schema, and
repeat runs on the same photo. It enters the registry at the level those
numbers support (section 11), the same as Surya or Paddle.

## Open questions for the owner

1. The bar for each maturity step per language: how many real pages, and
   what reading accuracy.
2. Whether the report names the language a page was scored as, and where.
3. Whether factor 6 is renamed for non-Latin scripts, and to what.
4. For German, whether to ask the family which school script the child
   learned, or detect it.
5. Whether a language-model API may ever see a child's handwriting, and
   on what terms, or whether only a local model on our own GPU is allowed.
   Whether there is a GPU budget for that local model.

Sources for section 14: [Census 2011 mother-tongue shares](https://www.thenewsminute.com/news/what-india-speaks-south-indian-languages-are-growing-not-fast-hindi-83823);
[2024 board-exam medium](https://www.legacyias.com/hindi-english-top-choice-as-medium-of-instruction-for-class-10-12-exams/);
[DohaScript](https://arxiv.org/abs/2602.18089); [German school scripts by
state](https://phbl-opus.phlb.de/files/619/Mesch_Barkow_Wild_Effekte_der_Handschrift.pdf).
