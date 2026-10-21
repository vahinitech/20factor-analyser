- A pull request that changes the analyser is timed against `main` on
  the same runner (#251). The `paired-timing` job in CI replays the
  benchmark pages with main's code and the pull request's, seven rounds,
  taking turns, and fails when the pull request's median CPU time is more
  than 10% above main's and the last three rounds agree. The job summary
  shows main, the pull request and the ratio for each step and page.
