# The real-handwriting benchmark

Every change to the analyser is checked against real handwritten pages: if
any page's score, line or reading moves, the pull request shows which, by
how much, and why the change was accepted. This page says how it works,
what is kept in the repository, and what to do when it fails. The code is
`scripts/benchmark.py`; the pages and results are in `benchmarks/`.

## Why two layers

Reading a page (PaddleOCR detection and recognition, the layout model)
needs the models and takes seconds a page. Everything after it is fast and
deterministic: repeated readings merged, missed writing read again, pieces
joined, the printed check, and the 20-factor scores. All four scoring bugs
found on 19 October 2026 were in that second part
([02-how-a-scan-works.md](02-how-a-scan-works.md), section 12).

So the reader's output is kept, once per page, and every change is checked
by replaying it through the code of the pull request:

| | Layer A: replay | Layer B: live reader |
|---|---|---|
| What | Kept reader output through this PR's code | Every page read again with the real models |
| Needs | Python and the core requirements, no models | The analyser image (PaddleOCR) |
| Time | Under a minute | Several minutes, plus the image build when its cache is cold |
| When | Every PR and every push to main (`ci.yml`, job `benchmark`) | PRs touching the reader, every Monday, by hand (`benchmark-live.yml`) |
| Fails when | Any number differs from `expected.json`, or a limit is crossed | A score moves by more than 0.3 (3 overall points) |

Both run on GitHub's standard runners. This repository is public, and those
runners are free and unlimited for public repositories; larger runners are
billed, so the workflows stay on `ubuntu-latest`. vahini-web is private and
pays for its minutes, so the benchmark lives here.

## What is kept

```
benchmarks/
  uji-clean/
    set.json        reader settings, the written sentences, the floor, the eye ranking
    source.md       where the pages come from and their licence
    pages/*.jpg     the pages, committed so their pixels never change
    reader/*.json   the reader's output per page
    expected.json   every page's result
    reading.json    how well the reader read each page (character error rate)
  planted/
    expected.json   how often planted mistakes are marked (scripts/planted_pages.py)
```

- **set.json** fixes the reader settings the pages were read with (the
  stage analyser's: `VAHINI_OCR_MAX_SIDE=2600`, English, PP-OCRv5 mobile).
  The replay decodes each page at that size, so the numbers match what the
  stage analyser gives.
- **reader/<page>.json** holds the raw lines exactly as `collect_lines`
  returns them, the layout regions, and every crop line recovery read again
  (`line_recovery.py`), keyed by the crop's bytes. If a change makes
  recovery read a crop that is not kept, the check says so instead of
  guessing; the live run reads it.
- **expected.json** holds, per page, the overall score, every factor a
  photo can measure (all but 13 to 16), the lines as read, how many of the
  written sentences were scored, and how many lines repeat one.
- **The pages are images, committed.** Making them again from the dataset
  on each run is not safe: another JPEG or OpenCV build changes a few
  pixels and the benchmark would report a move no code made. The UJI pages
  are CC BY 4.0, credited in `source.md`. **Children's photos are never
  added**: the analyser does not store photos (owner decision, 2026-10-09).

## What a failure means and what to do

`python scripts/benchmark.py check` prints, and writes to the job summary,
a table of every number that moved:

```
| Page    | What      | Expected | Now |
| UPV_W30 | factor 10 | 0.0      | 8.3 |
```

- **The move was meant.** Run `python scripts/benchmark.py update` and
  commit `expected.json` with the change. Where the replay cannot run
  (the shared production host), take the file from CI instead: the
  `benchmark` job keeps what `update` would write as the
  `benchmark-results` artifact (`check --results <dir>`); copy its
  `<set>/expected.json` over the committed one. The diff of `expected.json` is
  the record: every score that moved is in the pull request, for the
  reviewer to see, and `git log -p benchmarks/uji-clean/expected.json` is
  the history of every page.
- **The move was not meant.** The table names the page and factor. Replay
  that page with the old and new code to find what changed.

Some limits cannot be updated away; `check` fails on them whatever
`expected.json` says (`LIMITS` in the script):

- the written lines scored stay at or above the set's floor (77 of 80);
- no written line is scored twice;
- no measured score is exactly 0 (a measurement that failed is "Not
  measured", never 0);
- each page replayed twice gives the same result;
- agreement with the ranking by eye falls by at most 0.05.

## Matching a person's eye

The question behind the benchmark is whether the scores rank pages the way
a person would. `set.json` has an `eye_ranking`: the pages from best to
worst, as the owner ranks them by eye. When it is filled in, `check`
reports how well the overall scores follow it (Spearman's rank agreement,
-1 to 1) and fails when a change makes it fall by more than 0.05. It is
empty until the owner ranks the 20 pages.

## When the benchmarks run

A pull request runs a benchmark only when it can move it.
`scripts/score_closure.py` reads the imports, without running anything,
from the benchmark scripts through `backend/` and `scripts/`, and keeps
two lists of files:

- **scores**: what the replay, the factor and calibration tests, the
  paired timing and the history import, plus the data they read
  (`benchmarks/`, the language packs, the models, the budgets and the
  requirements). A change here runs those jobs.
- **reader**: what the reader imports, stopping at the scorer, plus the
  image, the models and the requirements. A change here runs the live
  reader. The reading never comes from the scorer
  (`vision/computer_vision.py` imports it inside one function, for the
  evidence boxes), and a scoring change is caught by the replay of the
  kept reading.

A first job in each workflow (`.github/actions/changes`) compares the
pull request with its base and says run or skip. A change to the server,
the report text, the practice catalogue, the website or a test skips the
benchmarks; the unit tests, e2e and CodeQL always run. A push to main,
the weekly runs and runs by hand run every benchmark. Run
`python scripts/score_closure.py groups` to see both lists, and
`python scripts/score_closure.py changed origin/main` for a branch.

`test_score_closure.py` replays one page of every set and fails if the
replay loads a file the scores list does not hold, so a module loaded by
name cannot let a pull request skip a benchmark it moves. It also fails if
a reader module imports the scorer at load time, which would end the
reason for the stop.

## The live reader (Layer B)

`benchmark-live.yml` builds the analyser image (the PaddleOCR layer is
cached and shared with CI), reads every page again, replays the new
reading and compares the scores with `expected.json` within 0.3. GitHub's
CPUs round differently from the server's, so a reading can move a little
with no change at all; the tolerance absorbs that. The new reading is
uploaded as the `reading` artifact. When the reader really changed (a
PaddleOCR or model update, a new detection setting): copy the artifact
over `benchmarks/uji-clean/reader/`, run `update`, and commit both, so
the PR shows what the new reader did to every page.

`python scripts/benchmark.py capture` does the same inside any analyser
container, writing straight into `reader/`. The kept output was captured
on the stage server's image on 19 October 2026.

A second job, alongside it, reads every page, and the sample photo
(`tests/fixtures/handwriting-sample.jpg`), twice more: with `lang=auto`,
as the website sends, and with `lang=en` (`benchmark.py langs`). Both
must give the same number of lines and every score within the same 0.3
(#145). A named language once read both image variants and kept most
lines twice, so the same photo scored 74 with `auto` and 71 with `en`.
The step reports without failing until #145 is fixed: on 20 October
2026 the doubled lines were gone, but only 4 of 21 photos agreed. Two
had a line more with `en` (the sample photo 18 against 15), and factor
scores moved by up to 4 points on the rest, since with `en` both image
variants are read and the merged lines have other boxes.

### Speed and memory of the live reader

A third job, alongside the other two, times the reader (#252,
`scripts/live_timing.py`). The three jobs run side by side, each building
the image from the shared cache, so the run takes as long as the timing
job (about 13 minutes) instead of all three in a row (about 21). The
timing stays one job, its sides one after the other on one runner, so
the runner's speed cancels out of the comparison. On
a pull request it builds main's analyser image next to the pull
request's and runs each as a container held to the production limit
(`--memory 2500m --memory-swap 2500m`). Each container reads and scores
every page with its own checkout's code, recording the page's wall time
and the container's memory peak after it (cgroup v2 `memory.peak`, the
number the limit is held to). One page is read first and not timed, so
loading the models is not charged to a page. There are two passes a
side, in the order main, PR, PR, main, and each page keeps its fastest
time and its highest peak.

It fails when the pull request's 95th percentile page time is more than
15% above main's, its memory peak more than 10% above main's, or any page
passes 2500 MiB. The summary has both numbers for each side and a row
per page; the `timing` artifact keeps every pass. The weekly run has no
main to compare with, so it compares with the last weekly run on `main`
and only reports.

## How well the reader reads

The set knows what was written, so every check also measures how well
the lines were read (#253). Each scored line is matched to the written
sentence it reads best, as for `sentences_found`, and compared with it in
graphemes (`backend/languages/graphemes.py`): what a reader sees as one
letter, so a Telugu letter with its vowel sign is one unit and a dropped
vowel sign is one wrong letter. Both sides are put in NFC, lower case
(the sentences carry no capitals) and one space between words; spaces
count, since a word read as two or two words read as one is a reading
mistake. The character error rate is the number of graphemes to insert,
delete or change, over the graphemes of the matched sentences. Lines that
match no sentence, or repeat one, are left out: `unmatched` and `repeats`
count them already, as `sentences_found` counts lines never read.

`check` adds a table to the summary: the rate per script, and per page
with its baseline from `benchmarks/<set>/reading.json`. It fails when a
page's rate rises by more than 0.5 points or the set's by more than 0.2.
`live` does the same for the reading the real models just made, so a
reader change that reads worse fails even when every score stays within
0.3. On 20 October 2026 the UJI set read at 9.54% (290 of 3040
graphemes), from 0.62% on UJI_W14 to 27.1% on UPV_W30.

`update` writes `reading.json` too, but only ever lowers it: a page that
reads better keeps its new rate, one that reads worse keeps the old one.
When a change is meant to read worse (a faster reader that reads a little
less well, say), edit `reading.json` by hand and say why in the pull
request, so the higher number is in the diff for review.

## Planted mistakes

`python scripts/benchmark.py planted` runs `scripts/planted_pages.py`
(seed 0, 120 pages, measured from ink outlines) and compares with
`benchmarks/planted/expected.json`: how often each planted mistake is
marked may not fall, and false marks on clean pages may not rise by more
than 0.1 a page. When the numbers move without getting worse, `planted
--update` keeps them. CI caches the UJI file the pages are made from.

## Each factor against its own mistake

`python scripts/benchmark.py factors` plants one mistake per factor on
the UJI writers' letters, beside a clean twin that differs only by the
mistake, and fails when a factor catches its mistake less often than
`benchmarks/factors/expected.json` records
([02-how-a-scan-works.md](02-how-a-scan-works.md), section 13). It takes
about a quarter of an hour, so `.github/workflows/factor-tests.yml` runs
it when the measuring code changes, weekly and by hand.

`factors --ruled` does the same for factor 6 on pages with a printed
four-line ruling (`planted_pages.build_page(ruled=True)`: the ascender
line, a dashed midline, the baseline and the descender line under each
line, drawn with no random numbers, so the writing is the same as on
the unruled page). It checks the planted long ascenders against
`benchmarks/factors-ruled/expected.json`, and how far factor 6 moves
between two pages of the same passage by one writer
(`variation_study.synthetic_pairs`, two pairs a writer): the 90th
percentile may not rise. On 21 October 2026, on ruled pages:

| | Caught | Same passage: median | 90th percentile | Largest |
|---|---|---|---|---|
| Measured against the ruling | 0.85 | 0.2 | 1.31 | 6.4 |
| Measured from the ink, as before | 0.60 | 1.15 | 5.33 | 9.4 |

(Unruled pages, from the ink: caught 0.75, same passage 1.4, 4.54 and
9.1.) The 90th percentile is above the 1.0 of #157's stability test,
which the drawn-letter version of it (`test_zone_ruling.py`) meets.

## Setting the scales from neat writing (#197)

Most factors turn a measured spread into a score along a straight line,
`10 x (1 - spread / scale)`, and the scale is set by hand in
`backend/scoring_parts/` (`WORD_GAP_SCALE` 1.0, `LETTER_GAP_SCALE` 0.5,
`SLANT_SCALE` 40, the size scale 0.60 and others). How high neat writing scores is that
setting, apart from whether the factor sees a mistake at all. The UJI
pages cannot set it: their page maker spaces letters with plus or minus
30% random gaps, so they are not neat writing. The scales stay as they
are until a set of pages that the owner or a teacher calls neat exists.

`scripts/calibrate.py` is the tool for that set:

```
python scripts/calibrate.py                     # every neat reference set
python scripts/calibrate.py --neat <set> --json report.json
python scripts/calibrate.py --write             # keep the passing scales
```

For each factor with a scale it reads the spread on every neat page,
replayed from the kept reader output as `check` does (no models), and
proposes the tightest scale that puts the set's median at 9.0 and its
10th percentile at 8.5 or above, the Strong band (`--target`,
`--strong`). Then it scores the planted-mistake pages of
`factor_tests.py` with each proposed scale and checks every mistake is
still caught at least as often as `benchmarks/factors/expected.json`
requires. Legibility (18) and Overall Neatness (20) blend other factors,
so they are checked with every passing proposal applied together.
Factor 6 is unstable (#194) and parked: its numbers are shown and no
scale is proposed. It takes about a quarter of an hour, like `factors`.

The tool changes no scale. `--write` keeps the passing proposals in
`backend/score_scales.json`; the scoring code does not read that file
yet. Reading it is a later change, after the owner has reviewed the
table, and that change runs `benchmark.py update` so the pull request
shows every score that moves.

### Adding a neat reference set

A neat set is a benchmark set like any other (see "Adding a set"): a
folder under `benchmarks/` with `set.json`, `source.md`, `pages/*.jpg`
and `reader/*.json`, captured with `capture --set <name>` in the
analyser image. Its `set.json` says what it is for:

```json
{
 "description": "Ten pages a teacher calls neat, ...",
 "role": "neat-reference",
 "source": "source.md",
 ...
}
```

- Only a set marked `"role": "neat-reference"` sets scales. A set named
  with `--neat` that is not marked is refused.
- `source.md` says who wrote the pages, who called them neat and when,
  and the licence: the pages need one that allows them in a public
  repository.
- **A child's writing is never committed to `benchmarks/`.** With the
  family's written consent, a child's neat pages can make a set kept
  outside the repository (`--root <folder>`, see "A set kept outside the
  repository"); without it they are not used at all. Adult writing (the
  owner's, a teacher's) can be committed with the writer's licence.
- Give `set.json` the sentences the pages carry, as the UJI set does, so
  `check` can count the lines scored.

### Reading the table

| Column | Meaning |
|---|---|
| Scale | The constant, or the number written into the formula |
| Current, Proposed | Today's scale and the tightest one that meets the target |
| Neat spread (median) | The raw measurement on the neat pages, before scaling |
| Neat median, Neat p10 | The neat pages' scores, before → after |
| Planted caught | Per planted mistake: share caught before → after (and the share needed) |

The verdicts:

- **ok**: the neat pages reach the target and every planted mistake is
  still caught. Only these are written by `--write`.
- **loses a planted mistake**: the scale that lifts neat writing to 9
  would hide a mistake the factor catches today. Not proposed; the
  factor's measurement needs work first.
- **target out of reach**: no scale between a tenth of today's and ten
  times it gets there, usually because a penalty term (words off their
  line or size) or a fallback measurement holds the score down.
- **not limited by the neat set**: neat pages score in the Strong band
  even at a tenth of today's scale; the scale stays.
- **planted check short before any change**: the planted check already
  fails on this code, so `factors` needs fixing before any proposal.
- **parked**: factor 6 (#194).

The tool also checks itself: at today's scales it must give every score
the scorer gave on every page, and each factor's score must stop falling
exactly at the scale it holds. Either check failing means the tool is
out of step with `scoring_parts/`; it says which factor and exits with
an error.

`factor-tests.yml` runs the tool on the UJI pages as if they were neat
(`--tool-test`), only to show it works end to end. The job summary says
so above the table. Those proposals are never applied, and `--write`
refuses a tool test.

### The engraved model pages (`neat-penmanship`, 21 October 2026)

`benchmarks/neat-penmanship` holds eight crops of running sentences
from two public-domain penmanship manuals: A. N. Palmer, *The Palmer
Method of Business Writing* (1915), and C. P. Zaner, *Zaner Method
Writing: Arm Movement, Manual 144* (1925 printing of the 1915 edition).
`source.md` has the titles, the scans, the rights statements and what
was cropped. They are engraved model pages of adult cursive, the ideal
end of the range and not children's everyday writing, so the table they
give is a reference for the owner, not a scale to apply. No scale was
changed with them.

The reader output was captured once with the live reader in the
analyser image, as for any set. What it shows is the main result: **the
reader reads this joined, engraved cursive in fragments.** It scored 26
of the 39 written lines, with a character error rate of 31.8%, and read
the small-writing crop (`zaner-090-small-writing`) as six punctuation
marks. Many lines come back as several short pieces ("Thi", "This is",
"cmen"). The factors are then measured on the pieces' boxes:

- Margin Discipline (10) scores 0 on five pages: the pieces start
  anywhere along a line, and the copies indent each paragraph.
- Line Quality (4) is still the spread of line box widths, so pieces of
  every length score it down (median 4.4).
- Size (5), Word Spacing (8), Letter Spacing (9) and Ascender/Descender
  Control (6) read joined letters, long loops and tall capitals that
  the measures were not built around: their medians are 1.1 to 5.5.

So these pages cannot set the scales either: on most factors the
measurement, not the scale, is what holds them down. Seven pages have a
measured score of exactly 0, which `check` refuses, so the set is not
in `ci.yml`'s `check` step; `expected.json` and `reading.json` keep
today's numbers for the record, and the `calibration` job of
`factor-tests.yml` runs `calibrate.py` and `score_ranges.py` on it.

### Neat, ordinary and poor side by side

`python scripts/score_ranges.py` scores four groups with today's code
and gives each factor's median and range per group:

- **neat**: the sets marked `"role": "neat-reference"`;
- **uji**: the 20 UJI benchmark pages;
- **clean**: the 20 planted-page writers with nothing planted;
- **poor**: the same writers with every mistake in
  `planted_pages.POOR` on one page (narrow gap, letters apart, a sunken
  word, a big word, a tall letter, open loops, long ascenders, an
  indented, wavy, slanted, shaky and sinking line; line mistakes spread
  over the lines, `planted_pages.mistake_lines`).

Clean and poor pages are measured without the reader, as `factors`
measures them, so the factors read from the reader's confidence (1, 2,
19, and part of 18) cannot tell them apart. The `calibration` job
writes the table to its summary.

## Is this pull request slower than main?

A pull request that changes `backend/` gets a `paired-timing` job in
`ci.yml` (#251). Seconds on GitHub's shared runners move by tens of
percent with no change at all, so the job never compares with a number
from another day. It checks out `main` next to the pull request and
replays the benchmark pages with each, seven rounds, each side in a fresh
process, taking turns at going first (`scripts/paired_timing.py`). The
runner's speed is the same for both, so it cancels out of the ratio.

It counts CPU time per page and per step: decoding the photo, finding the
hand lines from the kept reading, the layout pass, scoring, and the rest.
A step's time leaves out any other step it calls. Each page also runs
inside `perf.scan()` (#229), so the summary has a second table of the
stages `backend/server/perf.py` records (merge, printed check, recovery, join,
features, scoring and the rest); each of those includes the stages
inside it. The job fails when the
pull request's median total is more than 10% above main's and the pull
request was slower than main in each of the last three rounds; one slow
minute on the runner is not enough. The summary has the table per step
(main, PR, PR / main), the ratio in each round, and a folded table per
page. The `paired-timing` artifact keeps every round's numbers.

When it fails, the step with the largest ratio is where to look; the
profiling job (below) shows the functions inside it. A change that is
meant to cost more time says so and why in the pull request; the owner
decides whether to merge it over the failed check.

## Where the replay spends its time and memory

`.github/workflows/profile.yml` replays the pages through
`scripts/profile_benchmark.py`: once under `cProfile`, once under
`tracemalloc`, standard library only and no models, on GitHub's runners.
It runs every Monday, by hand (Actions, Profile, Run workflow), and on a
pull request that carries the `perf` label. Add the label when a change
might make scoring slower or hungrier; the run never fails the PR.

The job summary has two tables:

- **Time**: the 30 functions with the most cumulative time (the function
  and everything it calls). *Share* is that time over the whole run.
  Look for our own functions (`backend/...`) high in the list, and for a
  large *Self s*, which is time spent in the function's own lines.
- **Memory**: the 20 places holding the most memory at the run's peak.
  Each allocation is charged to the innermost line of our own code that
  led to it, so a numpy array shows up as the line that made it. This is
  Python's view of one replay, not the server's memory per scan; that is
  `backend/tools/load_test.py` on stage.

Each row is compared with the last successful scheduled or manual run on
`main` (its `profile.json` artifact). *Change* is the move in share of
time, or in MiB. A row is in bold when it entered the top 10 or grew by
more than 25%. Shares, not seconds, are compared, because one runner can
be a fifth slower than another with no change at all; even so, read a
mark as "look here", not as proof. When there is no earlier run the
summary says so and nothing is marked.

The `profile` artifact keeps `profile.prof` (open it with
`python -m pstats profile.prof` or any cProfile viewer), `profile.json`
and `profile.md`. To profile on your own machine, never the production
host: `python scripts/profile_benchmark.py --out profile-out`.

## Adding a set

A new set is a folder with the same files. Pages need a licence that
allows them in a public repository, and a `source.md` saying where they
came from. Capture the reader output with `capture --set <name>` in the
analyser image, then `update --set <name>`, and add the set to the
`check` step in `ci.yml`.

## A set kept outside the repository

A set whose pages may not be published yet lives in a folder of its own;
every command takes `--root <folder>`:

```
python scripts/benchmark.py capture --root ~/eval-data/benchmarks --set telugu-iiit-clean
python scripts/benchmark.py update  --root ~/eval-data/benchmarks --set telugu-iiit-clean
```

`set.json` may give each page its own written text (`page_text`) instead
of one list of sentences; text is matched in any script. Such a set runs
by hand on a machine that holds it, never in CI.

## Pages read in pieces (#277)

The reader reads joined cursive in pieces, and such a page is measured on
whole rows of its ink instead ([02-how-a-scan-works.md](02-how-a-scan-works.md),
section 2). The replay does the same. `benchmark.py fragments --set <name>`
prints, for each page, how the reader's lines sit on the rows: rows,
lines, the share of the rows' ink the lines span, lines per row, the share
of short lines, and whether the page counts as read in pieces. CI runs it
with `--none` on every real-handwriting set: no UJI page may be read in
pieces, and the table in the job summary shows how far each page is from
the thresholds (on 21 October 2026 the closest was UPV_W21: lines span 75%
of its rows, a quarter of them short).

## Telugu (19 October 2026)

Twenty pages of real Telugu handwriting (five writers, words from
IIIT-INDIC-HW-WORDS-Telugu, built by `eval-tools/telugu_pages.py`) are
kept outside the repository: the dataset is listed as CC BY 4.0 on the
AIKOSH portal, but the project's own pages state no licence for the
Telugu part, so the pages are not published until the authors confirm.
Read with `lang=te` and the Telugu recogniser, as production is set up:

- **7 of 80 written lines are scored.** PP-OCRv5's mobile detector finds
  almost no Telugu handwriting lines: 518 boxes on 20 pages, nearly all
  specks of a few pixels, at 900, 1400 or 2600 pixels wide. What is read
  comes out as Latin fragments ("ee", "n2"), and several factors score
  a measured 0. The server detector is killed for memory at the
  analyser's 2.5 GB limit.
- **With `lang=auto`** (the website's setting) English is read first and
  the Telugu recogniser never runs once three English "lines" are found.
- **Lines can be found without the reader.** The page's ink blobs, joined
  into rows by `detector.join_row_pieces`, give exactly four lines on 18
  of 20 pages. Their slope is not yet right: consonants written below the
  line (vottulu) pull the fitted baseline, so clean lines measure up to 5
  degrees and a line planted sinking 4 degrees stands out on 5 of 20
  pages.

### Measured from the ink (`ink_geometry.py`)

Telugu geometry no longer depends on the reader. When a check asks for a
language named in `VAHINI_INK_GEOMETRY_LANGS` (empty by default; the
website says Telugu scoring is in development), the server finds the
rows from the ink, still refuses printed pages, reads nothing, and
measures from the ink:

- **Rows.** The page's letter-sized ink blobs, counted row by row, give
  the row middles; every blob goes to the nearest one, so a consonant
  written below the line stays with its row and a sinking line stays one
  row. Rows found: **59 of 59 pages, every line** (20 clean, 20 with a
  sinking last line, 19 with a wide gap), against 7 of 80 lines read by
  PP-OCRv5.
- **Baseline**, through the bottoms of the row's letters, leaving out
  the strokes that sit wholly below the row's middle (vottulu, written
  apart in Telugu). On clean pages the median row slope is 0.8 degrees,
  with 0.6 rows a page at 2 degrees or more (English letter level: 0.5);
  part of that is real, as these pages place each word from its own
  scan. A last line sinking 4 degrees measures 3.3 and is the steepest
  row, over 2 degrees, on **14 of 20** pages (English: 18 of 20).
- **Size** compares the median height of every five letters: one letter
  alone varies with its shape (a top mark joined or not), so groups of
  five. Clean pages: median spread 0.16, a Size score near 7.4. The set
  has no planted size mistake, so how well this catches one is not yet
  measured.
- **Word Spacing** needs to know where words end. Some writers space the
  letters of a word as widely as their words (gaps of 30 to 57 pixels
  inside words, 44 to 60 between them, on one page), and the ink cannot
  tell them apart. With the passage the child copied (one line per row),
  the widest gaps of each row are its word gaps, as for English: the
  planted wide gap is the widest on **6 of 6** pages where it is real
  (13 planted gaps fell at a line's end, with no word after). Without a
  passage, word gaps are set only when the page's gaps fall into two
  clear groups, and Word Spacing is "Not measured" otherwise.
- Factors that need the words read (Letter Formation, Legibility,
  Character Distinction, loops and letter zones) stay "Not measured".

`scripts/ink_geometry_eval.py <pages folder>` gives these numbers from
the page maker's folder (`--known-words` for the passage case), and the
private sets `telugu-ink` and `telugu-ink-passage` keep every page's
scores for `benchmark.py check --root`.

## Engine speed (`backend/tools/benchmark_ocr.py`)

Moved here from `backend/README.md`.

Real, measured numbers only: this project's whole premise is auditable
geometry over guesswork, so a made-up speed table would contradict that.
Run it yourself and paste the output here (or open a PR):

```bash
pip install -r backend/requirements/core.txt   # + whichever engine tiers you want measured
python backend/tools/benchmark_ocr.py
```

It runs the SAME production code path (`recognizer.collect_lines_paddle` /
`recognizer.backend_recognize`) against the pages already committed under
`tests/fixtures/samples/`, times every call, and prints a Markdown table:
engine, sample, lines found, detection/recognition/total time, mean
confidence. Engines you haven't installed are skipped with a note, not an
error. See the script's own header comment for exactly what "detection"
vs "recognition" means for a recogniser-only engine like TrOCR or Surya
(PaddleOCR's API doesn't expose them as separately timeable steps, so one
of the two is an estimate: clearly labelled as such in the output).

`--samples <dir>` points it at a different folder of images, `--limit N`
caps how many it runs, `--lang en|te|hi|...` picks the language.

_No results are published here yet: be the first to run it on real
hardware and send a PR with your table and CPU/GPU details._
