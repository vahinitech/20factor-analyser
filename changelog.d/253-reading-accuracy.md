- The benchmark measures how well the reader reads, not only what it
  scores (#253). Every scored line is compared with the written sentence
  it matches, in graphemes, so a dropped Telugu vowel sign counts as a
  wrong letter. The character error rate per page and per script is in
  the benchmark summary, with a baseline in `benchmarks/<set>/reading.json`
  (9.54% for the UJI pages). `check` and the live run fail when a page's
  rate rises by more than 0.5 points or the set's by more than 0.2;
  `update` only ever lowers the baseline.
