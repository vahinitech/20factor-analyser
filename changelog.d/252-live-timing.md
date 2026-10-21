- The live benchmark times the reader and measures its memory against
  `main` (#252). On a pull request that touches the reader, main's
  analyser image and the pull request's read the same pages in the same
  job, each container held to the production limit of 2500 MiB with no
  swap. It fails when the 95th percentile page time is more than 15%
  above main's, the memory peak more than 10% above, or a page passes
  2500 MiB. The weekly run compares with the last weekly run and only
  reports.
