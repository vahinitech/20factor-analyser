# Practice framework: exercises by factor, practice by score, report in the parent's language

Design for owner review, 2026-10-11. Nothing here changes a report until the
owner approves the mock-ups below (report format baseline,
[AI-REPORT-CONTRACT.md](AI-REPORT-CONTRACT.md)).

## 1. The problem

Feedback on the Free report:

- Page 1 says which skills are "Developing" or "Need support". Page 2 ("Your
  next small step") gives an exercise per card, but never says which skill it
  develops, what that skill scored, or why it was chosen.
- Every skill has exactly one exercise, hard-coded in
  `frontend/src/report/report-render.js` (`simpleDrills`), so a second check
  prints the same drill again.
- Every card says "do one row a day", whatever the score: a 3/10 and an 8/10
  get the same amount.
- The report is English only. A parent who reads only Telugu cannot use it,
  even when a volunteer who reads English ran the check for them.

| Today (stage, Free sample) | Proposed page 2, Free (printed PDF) | Earlier card layout, Pro (printed PDF) |
|---|---|---|
| ![before](practice-framework/free-page2-before.png) | ![free](practice-framework/free-page2-after.png) | ![pro](practice-framework/pro-page2-after.png) |

Both proposed versions were printed to A4 PDF through the report's own
`fitPrintPages()` and come out at **exactly two pages**. Printed in Telugu
(draft wording, earlier layout): [free-page2-telugu.png](practice-framework/free-page2-telugu.png).
Above the report, on screen only: [share-bar.png](practice-framework/share-bar.png)
(Print in, Print / Save as PDF, Share on WhatsApp).

## 2. Development areas: one node per skill, everything connected

Each factor is a **development area**. Everything the report says about that
skill hangs off the same node, so a weak loop score always brings loop
exercises and loop tips, never a generic drill:

```
development area (factor 3, loop closure)
├── meaning        "Round letters such as a, d and o are closed."
├── evidence       why it was flagged on THIS page (existing explanations, crops)
├── exercises[]    ordered by level: close the circle, gap hunt, tall loops
├── tips[]         short hacks: "close the door", "go back over the top of a and d"
├── worksheet      the printable that goes with it (letter-shapes)
└── i18n           the same, per language
```

The framework is agnostic in four ways:

- **Renderer:** the Free and Pro reports, the website's factor pages, the
  practice guide and the Android app all read the same nodes.
- **Language:** text is looked up by id per language (section 9).
- **Tier:** a policy table, not the code, decides how much each tier shows.
- **Measurement:** a node does not care whether its score came from a photo
  or the pen; `needs` filters what a report can offer.

Tier policy: no prices, only what each report shows. Only the skills the
report flags get practice: if letter spacing is the one to grow, the card
shows letter-spacing exercises and a letter-spacing tip and nothing else.

| Tier | Skills with practice | Exercises per skill | Tips per skill | Skills scored |
|---|---|---|---|---|
| Free | up to 3, the lowest scores first | 1 | 1 | 5 |
| Pro | up to 3, the lowest scores first | up to 2 (the band decides) | 2 | all photo-scored |

The numbers are configuration, not code. The server resolves them from the
visitor's plan and returns them with the access answer (`/api/v2/me`,
`practice: {areas_max, exercises_max, tips_max}`), so a new paid plan
changes what a report shows without a frontend release. The catalogue's
`tiers` block holds the defaults.

The full report's `coach_tips.py` keeps its cross-skill tips (style,
finishing letters, the labelled "fun" cards); a coach tip that belongs to one
skill moves into that skill's `tips`, so the two never repeat each other.

## 3. The exercise catalogue

One catalogue, owned by this repository, maps every factor to an ordered list
of exercises. Draft content for all 20 factors:
[practice-framework/practice-catalog.draft.json](practice-framework/practice-catalog.draft.json).

Each exercise:

| Field | Meaning |
|---|---|
| `id` | Stable, `<skill>.<name>`, never reused. Reports and events name exercises by id. |
| `level` | 1 is the first to try; higher levels come once the earlier ones are done. |
| `title` | Two or three words, shown in bold. |
| `steps` | One or two plain sentences, at most about 120 characters, for a child or a parent to follow. |
| `example` | What to write, shown in the handwriting face (empty when the exercise is about the page). |
| `check` | One self-check question, asked after the practice. |
| `unit` | What one try is: a row, sentence, word, line, letter or page ("1 try = 1 row"). How many tries comes from the band (section 4). |
| `script` | `any`, or `latin` when it only makes sense for the Latin alphabet (joined writing, a-o pairs). |
| `needs` | `photo` (scored from a photo today) or `pen` (factors 13 to 16, scored by the pen; never chosen from a photo report). |
| `worksheet` | Optional worksheet id from the website catalogue, the printable that goes with it. |
| `i18n` | Per language: `title`, `steps`, `check` (and `example` where the example is not Latin). Section 7. |

Each tip: `id` and `text` (one sentence, a hack the child can remember), plus `i18n`.

Composite factors (18 legibility, 20 neatness) carry their own exercises
but are chosen only when no single factor explains the low score, as today.

## 4. Practice by score: tries, a week at a time

Children understand "try it 10 times" better than sessions or minutes. A
**try** is doing the exercise once: one row, one sentence, one word, as the
exercise says ("1 try = 1 row"). Practice runs a week at a time: try it a set
number of times a day for 7 days, then check again.

| Band | This week | Then |
|---|---|---|
| Just starting (below 4.5) | try it 15 times a day, 7 days | check again |
| Growing (4.5 to 6.9) | try it 10 times a day, 7 days | check again |
| Getting strong (7 to 8.4) | try it 5 times a day, 7 days | check again |
| Strong (8.5 and up) | 10 tries once a week, to keep it | check again in 4 weeks |

Each skill also shows where the child is on the path, by band:
**Learning** (below 4.5) → **Improving** (4.5 to 6.9) → **Mastering** (7 to
8.4) → **Strong** (8.5 and up). A check after each week of tries moves the
child along; about 100 tries usually come before a move, which the card
does not promise. These are
practice targets, not predictions: the next check decides the stage, and the
report never promises a score. A 20-minute daily cap still applies when a
child has several cards; past it, later cards ask for fewer tries.

## 5. Choosing exercises and tips (only for the skills the report flags)

1. Priorities are chosen as today (up to three; a spelling finding may take
   one slot; lowest measured non-composite factors below 8.5).
2. For each priority, and only for it, take min(band exercises, tier `exercises_max`)
   exercises in `level` order, and the tier's number of tips in list order,
   skipping `needs: pen` on a photo report and `script: latin` when the page
   is in another script.
3. A re-check moves on: the browser already keeps the last check (scores and
   date, `history`); it will also keep the exercise ids printed last time, so
   the next report starts after them and comes back to level 1 when the list
   runs out. Nothing about it leaves the browser.

## 6. Page 2: each skill beside its exercise

Page 2 is a two-column table, one row per skill to grow, so the exercise is
always next to the skill it develops:

| Left: the skill, from your page | Right: your exercise for it |
|---|---|
| Number, skill name, score and stage ("5.0/10 · Improving") | Exercise title and what one try is ("1 try = 1 row") |
| The stage path: Learning → Improving → Mastering → Strong, current stage filled in, earlier ones ticked | The steps, and what to write, in the handwriting face |
| What we saw on this page, in encouraging words | "This week: 10 tries a day, for 7 days. Then check again!" |
| The example cut from the child's own photo (the same crop as page 1) | Pihu's tip, and a writing line to try it once |

- **Up to three skill rows**, the lowest-scoring flagged skills first.
- **A spelling row** when the limited spelling check found a word: "We read
  recieve. Did you mean receive? Check it against your page." with a
  look-cover-write exercise. It is extra to the three skills, and appears
  only when there is a finding. (The mock-up shows an example row; the
  sample photo has no misspelling.)
- **Other skills we checked**, at the end: the remaining scored skills by
  name with score and stage, a word of praise for the strong ones, then
  "Want practice for every skill? Pro checks 15 more skills ... and gives
  exercises and tips for each one." No prices.
- Little Vahini and Bheema open the page, Tara closes it (section 8).

Stage names follow the band: Learning (below 4.5), Improving (4.5 to 6.9),
Mastering (7 to 8.4), Strong (8.5 and up). Page 1 keeps the photo and the
five skill cards, with the same stage names.

The whole report is two A4 pages: the mock-up above, with three skills, a
spelling row and the other-skills box, was printed through
`fitPrintPages()` and is exactly two pages, with room to spare.

## 7. Words for children

Children read this report, often with a parent. A child who feels judged
stops practising, so every sentence encourages:

- **Start with a strength.** Page 2 opens with the best-scoring skill:
  "Great work on letter shapes!"
- **Skills to grow, not weaknesses.** Never "weak", "poor", "bad", "wrong",
  "problem", "inadequate", "fail" or "lowest". Say "skills to grow" and
  "your next step".
- **Describe the writing, not the child.** "A few small letters grew taller
  than the rest", never "you write untidily".
- **Friendly band labels** on both pages:

  | Band | Today | Proposed | Telugu (draft) |
  |---|---|---|---|
  | below 4.5 | Needs support | Learning | నేర్చుకుంటోంది |
  | 4.5 to 6.9 | Developing | Improving | మెరుగవుతోంది |
  | 7 to 8.4 | Good | Mastering | పట్టు సాధిస్తోంది |
  | 8.5 and up | Strong | Strong | బలంగా ఉంది |

- **Short and doable.** "A few minutes a day is plenty."
- **Celebrate progress.** A gain since the last check is named first
  ("+0.6 since last time!"), and the page ends on encouragement: "You are
  getting better with every page."
- Scores stay visible (parents and teachers need them) but are framed as
  tracking, not marks: "Scores are practice guides, not school grades."

A test scans every report string and catalogue text (all languages) for the
banned words, and the `natural-writing` skill carries the list.

## 8. Vahini and friends on the report

The story characters make the report friendly for children, each with one
job they can recognise:

| Character | Where | Job |
|---|---|---|
| Little Vahini | top of page 2 | cheers the strength: "Great work on letter shapes!" |
| Bheema | beside that line | the practice buddy: "a few tries a day is plenty!" |
| Pihu | every tip | "Pihu's tip:" |
| Tara | end of page 2 | "You are getting better with every page!" |

The drawings are proprietary and never enter this AGPL repository. As with
the error-screen pictures (`window.VAHINI_NOTICE_ART`), the host page passes
a map of same-site image paths, `window.VAHINI_REPORT_ART`
(`cheer`, `buddy`, `tip`, `encourage`); vahinitech.com fills it from the
drawings library's cut-outs. Without the map (a self-hosted analyser) the
report has no pictures and the same layout. The pictures are small (26 to
52 px) and printed; the printed Free mock-up with all four is two pages.

## 9. Print in the parent's language

Many parents who need this most do not read English. The planned drives work
like this: a volunteer who reads English runs the check with the family,
then prints or saves the report **in the family's language**.

- A "Print in" dropdown sits next to Print / Save as PDF: English, then
  తెలుగు (Telugu) first, then other languages as their translations are
  reviewed (Hindi, Tamil, Kannada, Malayalam). Choosing one re-renders both
  pages in that language; scores, crops and the page photo do not change.
- Every sentence in the report comes from string tables keyed by id
  (`report-strings/<lang>.json`) and from the catalogue's `i18n`. A
  missing translation falls back to English for that sentence only, and a
  test lists what is missing.
- Fonts: Noto Sans Telugu (OFL) and the other Noto faces are bundled with the
  analyser frontend, so a printed or saved PDF shows the script correctly
  on any device.
- Translations are written and checked by a native speaker before a
  language appears in the dropdown. Machine translation may draft, never
  ship unchecked. Factor names keep a short English term in brackets on
  first use so a teacher and a parent can talk about the same thing.
- The spelling note stays honest: in another language it says the check
  covered English words only.
- The anonymous `report_printed` event gains the language code, so the
  Friday report shows which languages families print in. Nothing else.
- Later, not in this change: the analyser page itself in Telugu, for
  families who run the check on their own.

## 10. Share on WhatsApp

Next to Print / Save as PDF (screen only, never printed):

- **Phase 1:** "Share on WhatsApp" sends a short summary in the chosen
  language: the overall score, one strength, the next skills with this
  week's plan and the first exercise, and a link to the free check. On a
  phone it uses the share sheet (`navigator.share`), elsewhere
  `https://wa.me/?text=`. No child's name, no photo, no crops. Nothing passes
  through our server; the only record is an anonymous `report_shared` event
  with the channel and language.
- **Phase 2 (owner decision):** share the PDF file itself. The report prints
  through the browser today and cannot make a PDF file on its own; doing so
  needs a PDF library in the page (about 300 KB). On Android, "Save as PDF"
  and then sharing the file already works.

## 11. Who owns what

| Piece | Where | Notes |
|---|---|---|
| Catalogue data | `backend/practice_catalog.py`, validated at import | Draft JSON here becomes this module |
| Served to clients | the versioned factor catalogue (`/api/v2/catalog/<version>`): `factors[n].exercises`, `practice.dosage` | Schema change in `backend/schemas/catalog.schema.json`; the version hash changes, clients refetch |
| Report rendering | `frontend/src/report/report-render.js` reads the catalogue; `simpleDrills` is removed | Same cards for Free and Pro |
| String tables | `frontend/src/report/strings/<lang>.json` | English is the source |
| vahini-web | factor pages show "How to practise" from the same catalogue (`tools/gen-factor-pages.mjs --sync`); Bheema's practice plan can use it later | One source, so a page never promises an exercise the report does not have |
| Android app | reads the same catalogue | No API change needed |

## 12. Tests

- Catalogue: every photo-scored factor has at least two exercises; ids
  unique and stable; every `worksheet` exists in the worksheet catalogue;
  dosage covers every band; every factor has at least two tips; the tier
  table covers free and pro; steps within the length limit; no em dashes.
- Report: only flagged skills get cards; Free shows one exercise and one tip per card; each card names its factor, score, band, stage and plan; the exercise
  count follows the band and the tier, the tips follow the tier, and every
  exercise and tip shown belongs to that card's factor; the daily cap holds; a re-check starts
  after last time's exercises.
- Characters: with `VAHINI_REPORT_ART` the four pictures appear and the report still prints on two sheets; without it, none appear and nothing breaks.
- Words: no banned word in any report string or catalogue text, in any language.
- Share: the WhatsApp text holds no name and no image, and follows the chosen language.
- Print: one A4 sheet per page in English and in Telugu, longest case;
  Telugu glyphs render (no boxes) in the saved PDF.
- i18n: every key in English exists in each listed language, or is reported.

## 13. Rollout

1. Owner approves this design and the mock-ups.
2. Analyser PR: catalogue module, schema, renderer, tests (English only).
3. Analyser PR: string tables, Telugu translation reviewed by a native
   speaker, fonts, "Print in" dropdown.
4. vahini-web: pin bump; factor pages gain "How to practise".
