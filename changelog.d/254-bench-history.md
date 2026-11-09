- Every push to main adds its benchmark numbers to a history on the
  `bench-history` branch, and every pull request is compared with the
  median of the last ten main runs (#254): replay CPU time and memory,
  work counts, the reading's error rate, lines scored, the agreement with
  the eye and each planted mistake's catch rate. A fall in accuracy
  fails; time, memory or work more than 15% up is flagged. The job
  summary shows each number's trend over the last 50 runs.
