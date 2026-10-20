# Performance, complexity and coverage

This is a design. It says how the analyser will show where each scan's
time and memory go, catch a function that starts growing faster than it
should, and show what the tests do not reach. Nothing below is built yet
except where a section says "today". Builds on
[13-api-and-capacity.md](13-api-and-capacity.md),
[18-benchmark.md](18-benchmark.md) and
[20-languages.md](20-languages.md). Work is tracked in #217.

## Why now

The language framework adds steps to every scan: a script decision per
line, reading ladders that can call two or three engines for a hard line,
profiles to resolve, and later a language-model rung on another machine.
Each is cheap alone. Together they can turn one page into dozens of calls,
on a shared host where the analyser container has 2.5 GB and one scan
already peaks near 1.6 GB. We need to see that before production does.

## What exists today

Checked on `main` at d24cf63 (20 October 2026):

| What | Where | What it covers |
|---|---|---|
| Whole request time | `_with_meta`, `ppocr-server.py:530`, `:696`, `:998` | one number per request, no steps |
| Engine time per line | `recognizer.py:306-315`, `engine_speed_snapshot` in `/health` | hybrid engines only, information only since #112 |
| Memory plan | `capacity.py`, [13-api-and-capacity.md](13-api-and-capacity.md) | scan slots from the container limit |
| Peak memory under load | `backend/load_test.py` on stage | by hand |
| Backend tests | `python -m unittest` with a hand-written list, `ci.yml:115` (replaced by discovery in #228) | 38 of 46 test files |
| Coverage | none (since #232: section 6) | |
| Profiler | none | |

(Since fixed by #228: every test file now runs.) Eight test files ran in no workflow at all: `test_baseline_track`,
`test_capacity`, `test_coach_tips`, `test_plain_groups`, `test_scan_slots`,
`test_style_finishing`, `test_tbar_analysis` and `test_zone_analysis`.
Two of them guard the memory protections. A change that breaks them passes
CI today. That is the first thing to fix, because coverage numbers mean
nothing while some tests never run.

## The rules every part follows

- **Measuring never decides.** No timer, budget or profile changes which
  engine runs or what score a page gets. #112 came from runtime speed
  choosing what ran, and the same photo scored differently on a busy
  server.
- **Numbers only.** Timings, counts and sizes. Never text, images, crops,
  profile contents, a name or an IP address.
- **Heavy measuring happens in CI.** Profilers, scaling runs and coverage
  run on GitHub's runners. The production host only keeps the cheap
  per-stage timers; peak memory on the real deployment is still measured
  with `load_test.py` on stage.

## 1. Every test runs (#228)

Switch the backend run to `python -m unittest discover -s backend/tests -t .`,
or keep the list and add a check that fails when a `test_*.py` file is
missing from every workflow. Discovery is better: the list has already
drifted by eight files. Each of the eight is fixed or explained once it
runs; one that finds a real bug gets its own issue.

## 2. Stage timings on every scan (#229)

A small module, `backend/perf.py`, standard library only:

```python
with perf.stage("read.rung", rung="paddle", lines=len(todo)):
    answers = rung.read_batch(todo)
```

Each stage records wall time, CPU time, the change in the container's
`memory.current`, its input sizes (pixels, lines, words, graphemes) and
its call counts (reader calls per rung, model calls). The steps wrapped:
decode, layout filter, detection, each reading rung, the printed check,
line recovery, passage alignment, features, scoring, evidence and
practice.

Where the numbers go:

| Output | Holds | Who sees it |
|---|---|---|
| `Server-Timing` HTTP header | stage names and milliseconds | the browser's developer tools, our own tests |
| `/health` | rolling p50 and p95 per stage, in memory, reset on restart | operators |
| one log line per scan | stage numbers only | the server log |
| weekly report, later | p95 per stage and budget breaches, anonymous, read by vahini-web from `/health` (no service reads another's files) | the team |

## 3. Large-call budgets (#229)

`backend/perf/budgets.json` says how much one page may cost:

| Budget | Limit |
|---|---|
| Reader calls | at most lines times rungs on the ladder |
| Language-model calls | one batched call per rung per page |
| Decoded image | 24 MP, as the upload limit already says |
| CPU time per stage | a cap per stage, set from the benchmark pages |

In CI a benchmark page that breaks a budget fails the build, which is
where a loop that calls a reader once per word instead of once per line
shows up. In production a breach is counted in `/health` and the weekly
report, never refused: the page was already admitted and paid for.

## 4. Recording growth: big O per function (#230)

Built in #230: `backend/perf/complexity.json`, `scripts/complexity.py` and
the `complexity` job in `ci.yml`, which writes the table to the job
summary and uploads it as the `complexity` artifact. The inputs are
synthetic pages of handwriting-like strokes, reader lines and passage
text, the same at every run. Lines past the ladder's 40 are held, so
`escalation.climb` is measured up to 40 lines. A test plants a quadratic
function declared O(n) and checks the job would fail
(`backend/tests/test_complexity.py`); it is never in the real table.

`backend/perf/complexity.json` lists every function that runs once per
page, what its n is, and how fast it should grow:

```json
{
  "scoring.build_analysis": {"n": "lines", "declared": "O(n)"},
  "ink_geometry.find_rows": {"n": "pixels", "declared": "O(n)"},
  "recognizer.align_to_expected": {"n": "graphemes", "declared": "O(n^2)",
    "why": "edit distance between the line and its passage line"}
}
```

A CI job builds deterministic synthetic inputs at four sizes (n, 2n, 4n,
8n), runs each function five times, takes the median CPU time, and fits
the slope of log time against log n. A slope near 1 is linear, near 2 is
quadratic. The job fails when the slope is more than 0.3 above the
declared class, and prints the table on every PR:

| Function | n | Declared | Measured slope |
|---|---|---|---|
| `scoring.build_analysis` | lines | O(n) | 1.04 |
| `recognizer.align_to_expected` | graphemes | O(n^2) | 1.91 |

(Example rows, not measurements.)

Anything above O(n log n) needs a reason in the file, so a reviewer sees
it. Model inference is not in this table: its cost is fixed per crop and
Perf 1's call counts show how many crops there were. Shared runners are
noisy, so only slopes are compared, never absolute times.

## 5. Profiling hot paths (#231)

A workflow, `profile.yml`, runs weekly and on PRs labelled `perf`. It
replays the benchmark pages (Layer A, no models) under `cProfile`, then
again under `tracemalloc`, and writes two tables to the job summary: the
top 30 functions by cumulative time and the top 20 allocation sites,
each compared with the last run on `main`. A function that entered the
top 10 or grew by more than a quarter is marked. It never fails a PR;
the raw profiles are kept as artifacts for anyone who wants to dig.
The script is `scripts/profile_benchmark.py`; how to run it and read the
tables is in [18-benchmark.md](18-benchmark.md#where-the-replay-spends-its-time-and-memory).

## 6. Coverage (#232)

`coverage.py` with branch coverage around the backend unit tests, and
`c8` around the node unit tests (`tests/*.test.mjs`). Each PR gets a
table per file in the job summary and an HTML report as an artifact.

`coverage-baseline.json` is a ratchet: the total and each file may not
drop by more than 0.5 points, and the new packages (`backend/languages/`,
`backend/scoring_parts/`) have a floor of 90%. A PR that raises coverage
raises the baseline in the same PR. No third-party coverage service; the
numbers stay in GitHub.

Coverage waits for #228, so it counts every test.

### Reading the report (built in #232)

Both CI jobs measure on every PR. `python-tests` runs the unittest
discovery under `python -m coverage run --branch` (settings in
`.coveragerc`), and `e2e` runs every `tests/*.test.mjs` under c8
(`npm run coverage:frontend`, settings in `.c8rc.json`). A file's number
is its covered lines and branches over all its lines and branches. Every
file under `backend/` and `frontend/src/` is listed, including files no
test loads, which show 0%.

- **Job summary.** Open the run, then the job. The summary starts with
  the total against the baseline, any rule the run breaks, and the ten
  least covered files, followed by one row per file: its number, lines
  and branches covered, the baseline and the change.
- **HTML report.** The run's artifacts `coverage-backend` and
  `coverage-frontend` hold the full report. Download, unzip, open
  `index.html`; red lines never ran, yellow ones took only one way
  through a branch.

The node tests load frontend files with `vm`. They go through
`tests/run-source.mjs`, which gives V8 each file's real path; code run
without one is named "evalmachine" and c8 cannot count it.

### The ratchet and updating the baseline

`scripts/coverage_ratchet.py --check` fails the job when the total or any
file is more than 0.5 points under `coverage-baseline.json`, when a file
in `backend/languages/` or `backend/scoring_parts/` is under 90%, or when
a file the baseline lists still exists but is no longer measured. A file
in those two packages that was under 90% when the rule came in has a
dated entry under `exceptions`: its number then is its floor, which can
only go up, and the entry goes away once the file reaches 90%. When the
ratchet came in (20 October 2026) the backend stood at 82.96% and the
frontend at 31.27%, and one file needed an exception:
`backend/scoring_parts/advisory.py` at 84.73%. The frontend number is low
because most browser code runs only in the Playwright tests, which c8
does not measure.

When a PR raises coverage, raise the baseline in the same PR. Download
the run's report artifact into `coverage/` and run, for whichever part
changed:

```bash
python scripts/coverage_ratchet.py backend coverage/backend.json --update
```

```bash
python scripts/coverage_ratchet.py frontend coverage/frontend/coverage-summary.json --update
```

`--update` refuses while the check fails and never lowers a number. If a
change has to lower one (a file split in two, tests moved elsewhere),
edit `coverage-baseline.json` by hand and say why in the PR, so the lower
number is in the diff for review.

## Order

| Step | Issue | Can start |
|---|---|---|
| Every test runs | #228 | done (#236) |
| Profiling job | #231 | now (a workflow and a script, no pipeline change) |
| Coverage | #232 | done (#247) |
| Stage timings and budgets | #229 | now; it wraps the steps in `backend/scoring_parts/` from the split (#227) |
| Big O per function | #230 | built (#230) |
