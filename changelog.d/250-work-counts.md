- Each benchmark page's work is counted and committed (#250): every
  stage's runs, sizes and call counts from the replay through the
  server's scan, in `benchmarks/<set>/work.json`. Counts do not depend on
  the runner's speed, so the benchmark job fails when any count on any
  page rises, with the page, the count and both numbers, and asks for an
  update when one falls. `perf_budgets.py update-work` writes the file.
