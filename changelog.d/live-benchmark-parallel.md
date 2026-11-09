- The live reader benchmark (`benchmark-live.yml`) runs as three jobs side
  by side: `live` (read every page again and compare), `langs` (auto
  against en, report only) and `timing` (main and the PR on one runner).
  A run takes about as long as the timing job, about 13 minutes, instead
  of about 21 with every step in a row. Its path filter names
  `backend/requirements.txt` and `backend/requirements/**`, so a change to
  an engine tier still runs it after the backend folder sort.
