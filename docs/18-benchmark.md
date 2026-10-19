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

## Planted mistakes

`python scripts/benchmark.py planted` runs `scripts/planted_pages.py`
(seed 0, 120 pages, measured from ink outlines) and compares with
`benchmarks/planted/expected.json`: how often each planted mistake is
marked may not fall, and false marks on clean pages may not rise by more
than 0.1 a page. When the numbers move without getting worse, `planted
--update` keeps them. CI caches the UJI file the pages are made from.

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

The next step is Telugu geometry from the ink: rows as above, a baseline
fitted to the letter bodies rather than to the lowest ink, and Size and
Word Spacing measured against Telugu's own bands, each judged on these
pages and their planted copies (`tilted_line`, `wide_gap`) before any
Telugu score is shown.

