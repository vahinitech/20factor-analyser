# Cursive reference pages by letter-model family (#342)

Schools teach different joined hands. Before the analyser says anything
new about joined writing (#277, #343, #344, #345, #350), it needs pages
that show how it behaves on each one. This note holds the numbers for
those pages, measured on 8 November 2026, so a later change can say
"this moved family 2 from X to Y" instead of guessing.

## The pages

Every page is adult model writing: the copy a pupil was asked to
imitate, from a public-domain book or a public-domain upload. None is a
child's writing. Each set's `source.md` gives the book, the scan, the
rights and the crop.

| Family | Set | Pages | What they are |
|---|---|---|---|
| 1. Looped cursive, slanted | `neat-penmanship` | 8 | Palmer (1915) and Zaner (1925 printing) engraved copies |
| 1. Looped cursive, upright | `cursive-looped-upright` | 6 | Barnes's National Vertical Penmanship No. 6 (1898) |
| 2. Joined, taught break letters | `cursive-breaks` | 5 | M. M. Bridges, A New Handwriting for Teachers (1907 printing), the italic the English joined schemes grew from |
| 3. French cursive | `cursive-french` | 8 | Meyrat's school copies (about 1900, one upright) and D'Avignon's engraved plates (early 19th century) |
| 4. German school scripts | `cursive-german` | 4 | One adult page in the GDR Schulausgangsschrift; three 1866 copy sheets of the englische Current, kept as precursors |
| 5. Print only (control) | `print-control`, `uji-clean` | 1 + 20 | A 1920 British manuscript-writing model; the 20 UJI benchmark pages, adult print letters written one at a time |

Each `set.json` names its family (`"family"`) and gives each page's
slant as written and its scheme (`"page_style"`). The control is all
adult writing, like the rest; no print page of children's age is used.

## How to run it

```
python scripts/benchmark.py families            # compare with the kept numbers
python scripts/benchmark.py families --update   # keep new numbers
```

It replays the kept reader output of every set that names a family,
exactly as `check` does, and reports per family:

- the style check's verdict (`vision/style_analysis.py`: cursive, print,
  mixed, or unavailable when it found too few words);
- the pages and rows read in pieces (`ink_geometry.fragment_rows`, #277);
- the factors that came out not measured.

It also gives each page's measured lean (`letter_styles.lean_label`,
#350) beside the slant the page was written in. The numbers are kept in
`benchmarks/cursive-families.json`, and CI's `benchmark` job fails when
they move, so a pull request that moves them runs `--update` and the
diff of that file shows which family moved.

The reader output was captured with the live reader in the production
analyser image (PP-OCRv5 mobile, English, the settings in each
`set.json`), as for `neat-penmanship`. French and German pages are
read with the English model, as the server reads them today.

## The numbers (8 November 2026)

| Family | Pages | Style verdict | Read in pieces (pages) | Rows on those pages | Not measured (factor: pages) |
|---|---|---|---|---|---|
| 1. Looped cursive | 14 | print 8, mixed 3, unavailable 3 | 3 of 14 | 14 of 46 | 3: 1, 6: 1, 8: 3, 10: 11 |
| 2. Joined, taught break letters | 5 | print 4, unavailable 1 | 0 of 5 | 0 of 22 | 3: 1, 8: 1, 10: 1 |
| 3. French cursive | 8 | cursive 1, print 7 | 7 of 8 | 27 of 30 | 3: 1, 8: 2, 9: 1, 10: 2 |
| 4. German school scripts | 4 | print 3, mixed 1 | 1 of 4 | 8 of 28 | none |
| 5. Print only (control) | 21 | print 21 | 0 of 21 | 0 of 81 | 10: 1 |

The page-by-page table is the output of `benchmark.py families`.

Character error rate of the reader on the lines it matched to the copy
(`reading.json` of each set):

| Set | Error rate | Characters matched |
|---|---|---|
| `neat-penmanship` | 31.8% | 836 |
| `cursive-looped-upright` | 19.0% | 526 |
| `cursive-breaks` | 34.1% | 784 |
| `cursive-french` | 50.9% | 699 |
| `cursive-german` | 36.4% | 1190 |
| `print-control` | 59.5% | 37 |
| `uji-clean` | 8.7% | 3040 |

## What they show

- **The style check does not tell these joined pages from print.** Of
  31 pages of joined writing, it calls 22 print, 4 mixed, 1 cursive
  (`meyrat-018-engagements`) and cannot classify 4. It calls all 21
  print pages print. So on model pages a "print" verdict says nothing
  about whether the writing was joined. Why the joins are not seen
  (the ink, the word clusters, or the reader's boxes the words are
  taken from) is not measured here; it is the first question for #343.
- **French pages are read in pieces most.** 7 of 8 French pages, 27 of
  their 30 rows, are measured from the ink instead of the reader's
  lines, against 3 of 14 looped pages, 1 of 4 German pages, none of the
  break-letter pages and none of the print pages. The reader's error
  rate is also highest on French (50.9%), read with the English model.
- **Margin Discipline (10) is often not measured on looped pages**: 11
  of 14. Most of these crops hold two to five lines, several indented
  like a paragraph, which is short for a margin.
- **Lean against slant as written.** All 6 upright model pages with a
  measured lean (four Barnes, one Meyrat, the 1920 print page) come out
  upright. Of 21 slanted pages with a measured lean, 19 come out leaning
  right and 2 upright, both Bridges pages, whose italic leans only a
  little. Five pages have no measured lean: the four the style check
  could not classify, and `meyrat-018-engagements`.
- **The print control is not clean in reading**: the 1920 broad-pen page
  matched only 2 of its 9 lines (37 characters), so its error rate is
  one page's and says little. Its style verdict is still print.
- Several of these pages break the limits `check` holds (a measured 0,
  a line scored twice; see each `update`'s output), so, like
  `neat-penmanship`, they are not in the `check` loop. `families` runs
  them in CI instead.

None of this changes a score or the report. The pages are reference
material for the issues above, not a scale to apply.

## Families still without licensed pages

These wait for consented pilot pages under the existing rule (testing
only, kept on the server, aggregates only, deleted after):

- Indian straight (upright) cursive as Indian school cursive books teach
  it: no openly licensed specimen found.
- The modern break-letter schemes (Victorian Modern Cursive, NSW
  Foundation, Nelson, Letterjoin, California joined italics): no adult
  model page under a licence that allows commercial reuse. Marion
  Richardson's books (1935) stay in copyright in the USA until 2030.
- Lateinische Ausgangsschrift (1953), Vereinfachte Ausgangsschrift
  (1969) and Grundschrift (2011): Wikimedia Commons has alphabet charts
  only, no running text. Family 4 has a single page in a named scheme,
  one adult's own Schulausgangsschrift.
- A print control of children's age: only adult pages are used.

Each set's `source.md` lists what was searched.
