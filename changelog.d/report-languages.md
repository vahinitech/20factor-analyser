- Every language keeps the English report (owner, 23 October 2026): one
  font list per role for every language, a script's letters from a
  "Vahini Script" face scaled to the English face beside it (Telugu: Noto
  Serif Telugu 88%, Noto Sans Telugu 93% and 81% for handwriting), and no
  style rule that names a language. `tests/report-parity.mjs` fails on any
  element whose font size, weight, line height or font list differs from
  English, any block that moves, a print longer than two A4 pages, a face
  not scaled to its measure (`scripts/report_font_scale.mjs`), or a
  character no report font covers, and lists where longer words trim a
  practice row or zoom a page. The report's font lists now fall back to its
  own bundled faces on a page without the website theme.
