- Benchmarks run only when a change can move them. `scripts/score_closure.py`
  follows the imports from the benchmark scripts (scores) and from the reader,
  stopping at the scorer (reader), and adds the data each reads. A first
  `changes` job in `ci.yml`, `factor-tests.yml` and `benchmark-live.yml`
  skips the replay, paired timing, history, factor, calibration and live
  reader jobs on a pull request that touches neither list; pushes to main,
  the weekly runs and runs by hand run everything. It replaces the
  hand-kept path lists of the two benchmark workflows, which had missed
  modules that reach a score. `test_score_closure.py` fails if the replay
  loads a file outside the scores list.
