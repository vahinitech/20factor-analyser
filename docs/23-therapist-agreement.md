# Therapist agreement test: protocol

Do the analyser's factor scores agree with occupational therapists looking
at the same pages? This page says how to find out: who consents to what,
how the pages are collected, marked, scored and deleted, how many pages
and therapists are needed, and what the numbers mean. The tooling is
`scripts/therapist_agreement.py`; the marking sheet and its CSV template
are in [therapist-agreement/](therapist-agreement/).

Why it matters: school districts and their therapists will ask whether
our scores match a therapist's eye, and so far the only comparison is
weak. On 200 real GNHK photos the overall score agreed with a written
rubric at a rank correlation of 0.12, and that rubric was applied by one
reviewer who was not a therapist
([history/real-photos-gnhk-2026-10-19.md](history/real-photos-gnhk-2026-10-19.md)).

## What it tests, and what it does not

- **It tests** whether, factor by factor, the analyser puts pages in the
  same order as therapists do and in the same band; whether two
  therapists agree with each other (the ceiling for the analyser); and
  whether a low overall score picks out the pages therapists would want
  an occupational therapist to look at more closely.
- **It does not** test a diagnosis. Neither the analyser nor the marking
  sheet diagnoses anything, and no result of this test may be described
  as one. The yes or no question on the sheet is a therapist's judgement
  from one page, not a referral decision about a child.
- It compares the 16 factors a photo can measure. Factors 13 to 16
  (speed, pressure, continuity, pen lifts) need the pen; the sheet asks
  for them only from a therapist who watched the child write, and the
  report leaves them out until the analyser measures them.

## The rules for the pages

These follow the owner's rules for pupils' pages (consented pages are for
testing only, on the server only, aggregates only, deleted afterwards)
and the rule that the product never stores photos.

1. **Consent before any page is written.** Written permission from the
   school (or district), and written consent from each child's parent or
   guardian, with the child's own agreement. The form says, in plain
   words: the page is used to test how well the analyser agrees with
   therapists; it stays on Vahini's server and nowhere else; only totals
   are ever published; it is deleted by a stated date; and a family can
   withdraw it at any time before then. The school checks the request
   against its own policy and the law that applies to it (for a United
   States district, its FERPA policy).
2. **No names reach us.** Before a page is photographed, the school
   covers or cuts off the child's name, class and anything else that
   identifies the child, and writes a page number (P001, P002 ...) in a
   corner. The list joining page numbers to children stays with the
   school. Therapists sign their sheets with a code (T1, T2 ...), not a
   name.
3. **Server only.** Page photos go from the school straight to one
   folder on the server, readable by the operator's account alone
   (`chmod 700`). Never into this repository or any other, never through
   the website or the stage analyser (stage may have debug storage on,
   which keeps photos), never onto a laptop, into chat, an issue, a pull
   request or a document. The same holds for `scores.csv` and the marks.
4. **Aggregates only.** The report the script writes names no page and
   gives no number from fewer than 10 pages. Any write-up, slide or web
   page uses only that report.
5. **Deleted afterwards.** When the report is written, and by the date
   on the consent form at the latest, the operator deletes the folder
   (pages, scores and marks), and the school shreds or keeps the paper
   sheets under its own rules. The write-up records the day it was done.
   A family's withdrawal before then deletes that page and its marks at
   once.

## Steps

### 1. Agree the set-up with the school

- How many pages, from which year groups, and which therapists (see
  "How many pages and therapists" below).
- The deletion date, which goes on the consent form.
- The writing task. The analyser scores English handwriting. Ask for the
  child's usual writing on ruled paper, in pencil or pen, at least four
  lines: copying a short passage the school chooses, or a few sentences
  of the child's own. One task for the whole set, so pages differ by the
  writing and not by the task. Size Consistency counts in the overall
  score only from 10 measured words, so a page of a few words says
  little.
- A spread of handwriting, as it comes in the classes chosen. Do not ask
  which children already have support: that is health and education
  information we do not need, and the therapists' marks are the
  reference.

### 2. Collect the pages

The school scans or photographs each page upright, flat and whole, one
page per file, named by its number (`P001.jpg`; JPEG, PNG or WebP), and
sends them by a route the school approves to the operator, who puts them
in the run folder on the server:

```
~/therapist-agreement/<run>/pages/P001.jpg ...
```

### 3. Therapists mark the pages

Print [therapist-agreement/marking-sheet.html](therapist-agreement/marking-sheet.html)
from a browser (A4, one sheet per page). For each page the therapist
gives every skill a whole mark from 0 to 10, on the report's own scale
(0 to 4 Learning, 5 to 6 Improving, 7 to 8 Mastering, 9 to 10 Strong;
the bands are `_band()` in `backend/scoring_parts/stats.py`), leaves a
box empty when the skill cannot be judged, and answers "Would you want
an occupational therapist to take a closer look at this child's
handwriting?". The skill names and "the analyser measures" lines come
from `_FACTOR_META` in `backend/scoring.py`, so the two sides mark the
same thing.

- Mark from the paper page or the same image the analyser gets.
- **Blind:** no therapist sees an analyser score for these pages until
  every sheet is in.
- **Independent:** two therapists marking the same page do not discuss
  it.
- The marks go into a copy of
  [therapist-agreement/marks-template.csv](therapist-agreement/marks-template.csv),
  one row per page and therapist: `page`, `therapist`, `f1` to `f20`,
  `ot_look` (`yes` or `no`). Several files are fine (one per therapist).
  A page marked twice by the same therapist is refused as a typing slip.

### 4. Score the pages

Once only, on the server, with the rules for test containers: one
analyser container at a time, only with more than 2.5 GB of memory free
(`free -g`) and swap not full, a 2.5 GB limit, and stop at the first
out-of-memory kill. Run it from a checkout of the analyser commit being
tested; the image supplies the libraries and the models.

```bash
docker run --rm --memory 2500m --memory-swap 2500m \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/repo:ro" -v "$HOME/therapist-agreement/<run>/pages:/pages:ro" \
  -w /repo vahini/analyser:stage \
  python scripts/therapist_agreement.py score /pages --out - \
  > "$HOME/therapist-agreement/<run>/scores.csv"
```

The container writes nothing: the scores come out on stdout and the
shell puts them in the run folder; anything the reader prints goes to
stderr. Before the first real run, do a dry run with the same command on
the public benchmark pages (`-v "$PWD/benchmarks/uji-clean/pages:/pages:ro"`,
output anywhere) to check the set-up; this command has not yet been run
on the server.

`score` reads each page the way `scripts/benchmark.py live` does: the
stage analyser's reader settings from `benchmarks/uji-clean/set.json`,
the server's own reader, then the scorer, with `lang=auto` as the website
sends. It writes the overall score and the factor scores per page, and
for a page that stopped, the kind of error (not its message, which can
quote the words read). It keeps no words read, no image and no crop. Say
which commit was scored in the write-up.

### 5. Write the report

```bash
python scripts/therapist_agreement.py report \
  --scores ~/therapist-agreement/<run>/scores.csv \
  --marks ~/therapist-agreement/<run>/marks-T1.csv \
  --marks ~/therapist-agreement/<run>/marks-T2.csv > agreement.md
```

Rows it had to skip are listed on the console only, since they name
pages; the report gives their count. To see the report's shape without
real data, `sample --out <folder>` writes made-up scores and marks for
the cast and those can be fed to `report`.

### 6. Delete

Delete `~/therapist-agreement/<run>` and record the date. Keep only
`agreement.md`.

## What the report gives

| Part | Numbers |
|---|---|
| The analyser against the therapists | Per factor: pages, Spearman's rank correlation with an approximate 95% interval (Fisher), weighted kappa on the four bands (quadratic weights), share in the same band, share within one band. A page two therapists marked counts once, with the mean of their marks. |
| Therapist against therapist | The same numbers for pages two therapists marked (every pair once when three did), and how often their yes or no answers matched, with Cohen's kappa. |
| The overall score as a flag | The therapists' answer is the reference (the majority; an even split is left out). The analyser flags a page whose overall score is below a cut-off. Sensitivity and specificity with Wilson 95% intervals at overall 35, 45, 55 and 65, and the area under the curve. |

Bands use the report's cut-offs (4.5, 7.0 and 8.5), so a whole-number
mark falls in the stage printed beside it on the sheet. Quadratic
weights make a two-band miss cost four times a one-band miss; 0 is the
agreement chance alone would give, 1 is full agreement.

## How many pages and therapists

| | Recommended | Least that says anything |
|---|---|---|
| Pages | 100 | 60 |
| Therapists | 3 | 2 |
| Pages marked by two therapists | all of them | 30 |
| Pages the therapists flag | 25 or more | 15 |

Where these come from (Fisher's z for correlations, Wilson for shares,
95% confidence):

- **Telling a real correlation from chance.** With 80% power, a rank
  correlation of 0.5 needs 30 pages, 0.4 needs 47, and 0.3 needs 85. The
  five factors that tracked the rubric best on GNHK sat at 0.35 to 0.41.
- **How precise the number is.** A correlation of 0.6 measured on 30
  pages could be anywhere from 0.31 to 0.79; on 60 pages about 0.41 to
  0.74; on 100 pages 0.46 to 0.71. Below about 60 pages the interval is
  too wide to tell a factor that works from one that does not.
- **The flag.** A sensitivity of 80% measured on 15 flagged pages could
  be 55% to 93%; on 25, 61% to 91%. If about a quarter of pages are
  flagged, 100 pages give about 25.
- **Two therapists on every page** gives the inter-therapist ceiling on
  every factor and a steadier reference (the mean of two marks). Three
  therapists, each marking two thirds of the pages, keeps any one
  therapist's habits from setting the reference.
- **More than one class or school.** Pages from at least two classes, and
  better two schools, so the result is not about one teacher's ruled
  paper or one writing task.

Time each therapist's first few sheets in a trial before agreeing the
numbers with the school.

## Reading the results

- **The ceiling first.** A factor where therapists agree with each other
  at 0.5 cannot be expected to agree with the analyser at 0.8. Read each
  analyser row against its therapist row.
- **Known gaps on real photos.** On GNHK, Loop Closure (#200) and Margin
  Discipline (#201) measured something other than their names, and Word
  Spacing read lines in pieces (#168). Low agreement on those confirms
  the issues; it is not news. A test run after those fixes is the one
  that counts for them.
- **Choose the flag's cut-off before looking.** The report marks 45 (the
  Learning band, read on the overall's 0 to 100 scale) as the chosen
  cut-off unless `--flag-below` says otherwise. Fix the cut-off before
  scoring; the other rows show the trade-off, not a better cut-off to
  claim afterwards.
- **What may be said.** Only what the report shows, with the number of
  pages and therapists and the analyser commit, after the owner has
  read it. A good result supports "the analyser's scores agree with
  therapists' marks on factor X at Y"; it never supports a diagnosis or
  a claim that the analyser replaces a therapist.

## Files

| File | What it is |
|---|---|
| `scripts/therapist_agreement.py` | `sheet`, `score`, `report` and `sample` |
| `therapist-agreement/marking-sheet.html` | The printable sheet, generated by `sheet`; do not edit. It prints on one A4 sheet (checked in Chromium, 28 October 2026) |
| `therapist-agreement/marks-template.csv` | The columns `report` reads, generated by `sheet` |
| `backend/tests/test_therapist_agreement.py` | The maths on made-up pages named after the cast, the scale against the report's bands, and that the committed sheet is current |

When a factor's name or what it measures changes in `backend/scoring.py`,
run `python scripts/therapist_agreement.py sheet` and commit the sheet;
the test fails until then.
