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
  commit `expected.json` with the change. The diff of `expected.json` is
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
  `backend/load_test.py` on stage.

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
