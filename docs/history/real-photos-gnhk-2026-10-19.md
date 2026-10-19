# Real page photos: 200 GNHK pages on stage (19 October 2026)

Until today every number we had for the analyser came from pages we built
ourselves: UJI Pen Characters letters laid out on a ruled page. On 19 October
the 20 UJI writers' clean pages were scored on stage and the ranking did not
match a person's eye (the tidy cursive page came last). Before anyone puts a
"proof" page on the website, we wanted to know how the analyser ranks real
phone photos of real handwriting, and where it disagrees with a person.

Short answer: **on real photos the overall score barely tracks how neat a
person thinks the page is** (rank correlation 0.12 on 37 pages). Five factors
track their own part of neatness moderately (0.35 to 0.41). Four bugs and
two known problems explain most of the gap. Issues #199 to #202 are new;
#47, #145 and #168 already cover the rest.

## Where the photos came from

We looked for openly licensed photos of handwritten pages, English first.

**Roboflow Universe** (searches `class:handwriting` and "handwritten page
notebook", 19 October). Almost every project states CC BY 4.0, but none was
usable:

| Dataset | Images | Licence on its page | Why not |
|---|---|---|---|
| data_ns (navya), Handwriting New, Handwritting32, Handwritting_2050/2000 (New Workspace) | 286, 287, 287, 2,489, 2,490 | CC BY 4.0 | One pool of page photos whose file names (`download (2).jpg`, `images (17).jpg`, a Flickr id) show they came from web image search; the uploader can't license them. The 2.5k sets are rotated copies. |
| Segment individual Words (RoboflowProjects), Handwritten (ugur tuna) | 1,000, 451 | CC BY 4.0, Public Domain | IAM forms (IAM's own ids such as `a04-006`). IAM is licensed for non-commercial research only. |
| Dyslexia Detector, Dysgraphia Detector (DS181) | 2,931, 490 | CC BY 4.0 | Single letters, probably children's. Not pages. |
| handwriting detection, Handwritten032023, Handwriting (Ground DINO), HANDWRITTEN (xyz), handwriting-doc, form (MIT) | 120 to 2,738 | CC BY 4.0 / MIT | Printed forms with signatures or filled fields. |

Downloads from Universe also need a Roboflow account and key.
CEDAR (cedar.buffalo.edu) states no licence, so it needs its maintainers'
permission first.

**GNHK, the GoodNotes Handwriting Kollection**, is what we used, with the
owner's approval. 687 phone photos of English handwriting (shopping lists,
notes, diaries, cards) from Europe (330), North America (146), Africa (117)
and Asia (94), no more than five per writer. Licence: CC BY 4.0, stated in
the official repository, github.com/GoodNotes/GNHK-dataset. The official
download link (goodnotes.com/gnhk) now redirects to the app's home page, so
the files came from the Hugging Face mirror
`aryaman27/goodnotes-handwritten-dataset` at revision
`904297760a9fec813fdc1ecb5f8055cb1ca03550`; its counts match the paper's.

Attribution: A. W. C. Lee, J. Chung and M. Lee, "GNHK: A Dataset for
English Handwriting in the Wild", ICDAR 2021, licensed CC BY 4.0. We
resized the photos for scoring and changed nothing else.

The photos are not in this repository and must not be committed. They sit
in a folder outside both repositories on the server.

**Privacy.** GNHK is not a set of anonymous samples. Among the 40 pages we
looked at closely are tutoring cards and nursery reports with a child's full
name, a school exercise book, a poem signed with a child's name, a baptism
certificate with names and dates, a sticky note with a phone number and an
email address, and an essay about a parent's abuse. None of these may appear
on a public page. A proof page needs pages written for it with consent, or
GNHK pages checked one by one by a person. This note names pages only by
their GNHK id.

## How we scored them

- 200 of the 687 pages, picked at random within each region in proportion
  to the region's size (EU 70, NA 50, AF 45, AS 35; seed 20261019).
- Each photo was prepared the way the website prepares an upload
  (`frontend/src/app/app.js`, `imageToBlob`): turned upright from its EXIF
  orientation, long side capped at 2600 px, JPEG quality 0.92.
- Scored once each on the stage analyser (main at 4055c6f, #165), posted to
  `/report-python` from inside the container's network, one at a time, with
  a stage-only test Pro key so all 20 factors came back. The key was minted
  for the run with `subscription_admin.py` (Pro for 24 hours) and revoked
  afterwards. Stage and production keep separate key ledgers.
- Two passes: `lang=auto`, which is what the website sends, and `lang=en`,
  which the UJI run used. Unless a number says otherwise it is from `auto`.
- Stage had debug storage on, so stage kept a copy of each photo it scored
  (owner's choice; these are public dataset photos, not visitors' pages).
- Ground truth for reading: GNHK labels every word with its box, its line
  and whether it is handwritten or printed. We counted a handwritten word as
  read when its centre falls inside a handwriting line the analyser scored.
- A person's view: 40 of the 200 pages, picked at random within regions
  (seed 40), were scored on a written rubric **before any analyser score
  existed**. Five parts, 1 to 5 each: legibility and letter form, size
  consistency (x-height; tall cursive loops are not a fault), baseline,
  spacing, and tidiness (crossings-out, overwriting). Totals ran from 7 to 25,
  median 19. The rubric was applied by one reviewer, the AI assistant running
  this evaluation for the owner; a teacher's ranking of the same pages would
  be a better reference and the page list is kept for that.

Spearman's rank correlation compares two orderings: 1 is the same order,
0 is no relation. With 37 pages, values under about 0.33 are within what
chance alone gives (p < 0.05 needs 0.33 or more).

## What came back

| | `auto` | `en` |
|---|---|---|
| Pages with a report | 184 of 200 | 183 of 200 |
| Pages that crashed (#199) | 16 | 17 |
| Overall score, median (range) | 62 (26 to 92) | 61 (22 to 85) |
| Handwritten words inside a scored line, median | 74% | 82% |
| Pages with under 60% of words read | 47 | 31 |
| Pages with 20% or more of their handwriting marked printed (#202) | 46 | 30 |
| Pages with a line kept twice (#145) | 0 | 165 |
| Loop Closure at 100 (#200) | 173 of 184 | 174 of 183 |
| Margin Discipline at 0 (#201) | 145 of 184 | 145 of 183 |
| Word Spacing at 0 (#168) | 78 of 165 measured | 128 of 179 |

No page was refused as "no handwriting". The four pen-only factors (13 to
16) are not measured from a photo and are left out below.

### Against the rubric (37 pages, `auto`)

| Factor | Compared with | Rank correlation |
|---|---|---|
| Overall score | rubric total | 0.12 |
| 18 Legibility | legibility | 0.41 |
| 1 Letter Formation | legibility | 0.38 |
| 19 Character Distinction | legibility | 0.36 |
| 7 Baseline Alignment | baseline | 0.35 |
| 11 Line Straightness | baseline | 0.35 |
| 5 Size Consistency | size | 0.26 |
| 20 Overall Neatness | rubric total | 0.21 |
| 12 Vertical Alignment | baseline | 0.19 |
| 3 Loop Closure | legibility | 0.19 |
| 17 Slant Consistency | rubric total | 0.11 |
| 6 Ascender / Descender | size | 0.04 |
| 8 Word Spacing | spacing | 0.02 |
| 10 Margin Discipline | tidiness | -0.05 |
| 9 Letter Spacing | spacing | -0.08 |
| 2 Stroke Order | rubric total | -0.08 |
| 4 Line Quality | rubric total | -0.08 |

With `en` the overall correlation was 0.11 and the order of the factors
was much the same (Baseline 0.43, Line Straightness 0.42, Legibility 0.40).

### Where the analyser and the rubric disagree most

Rank 1 is the least neat of 37, rank 37 the neatest.

| Page | Rubric (rank) | Analyser (rank) | Why |
|---|---|---|---|
| eng_EU_213, large clear print on a card | 24 (35.5) | 55 (4.5) | 15 of its lines were marked printed; scored from fragments such as "5f", "il", "11". 38% of words read. (#202) |
| eng_AS_069, tiny neat notes in colour | 22 (32) | 47 (1.5) | Half its words marked printed (51%); Word Spacing 0. Crashed in the `en` pass. (#202, #199) |
| eng_EU_258, sticky note: name, phone, email | 15 (9.5) | 92 (37) | One line of six read, the email address, and the page scored on it alone: Size 100, Overall Neatness 95. (#47) |
| eng_AF_093, mixed capitals, uneven letters | 14 (6.5) | 69 (31.5) | The printed letterhead was kept as handwriting and scored; straight lines (Baseline 87) outweigh letter sizes that jump inside words. (#202) |
| eng_AF_086, faint small writing on ruled paper | 16 (11) | 74 (35) | Read well and the lines are straight, so it scores high; nothing measures faint or cramped writing. A judgement gap more than a bug. |
| eng_EU_302, a neat quotation | 22 (32) | 59 (9) | 32% of words marked printed, 3 lines read as 7 pieces, Word Spacing 9. (#202, #168) |
| eng_NA_006, finance notes with a table | 20 (28.5) | 60 (12) | Numbers, formulas and table cells count as size changes (Size 27); Word Spacing 0. (#168) |
| eng_NA_108, a neat letter | 24 (35.5) | 64 (23) | 7 lines read as 15 pieces; Word Spacing 2. (#168) |

Three of the 40 rubric pages crashed in both passes (eng_EU_098,
eng_AF_025, eng_NA_131), which is why 37 are compared; eng_AS_069 crashed
only with `en`.

## The bugs

- **#199, crash.** `letter_geometry._xheight` assigns slices of different
  lengths when a word's fitted baseline is steep: 16 of 200 pages get no
  report, the same pages every time. The handler returns the message and
  logs no traceback. #168 keeps this loop.
- **#200, Loop Closure** counts how many of the letters the OCR read are
  a, o, d, p, e, g or q. That is about spelling, not loops: about a third
  of English letters are in the set, so 173 of 184 pages score 100.
- **#201, Margin Discipline** takes the left edge of every handwriting box
  as a margin, so a date at the right or a table cell takes a page to 0
  (145 of 184).
- **#202, print or handwriting on real photos.** Neat print in marker or felt
  pen is marked printed and left out, and a printed letterhead can be kept.
  The neatest pages lose the most.
- **#145, `lang=en` keeps lines twice.** Confirmed on 165 of 183 pages; none
  with `auto`.
- **#47, minimum evidence.** A page read as one line gets a full report
  (eng_EU_258, 92).
- **#168** (open) fixes the line pieces, Word Spacing from the gaps between
  boxes, and tall loops counted as size. The `en` pass shows those on real
  photos too: Word Spacing 0 on 128 of 179 pages, a median of 2.2 pieces per
  written line.

## What this means

The analyser can't yet put real pages in the order a person would, so a
public page should not claim it ranks handwriting. It can honestly show
what it measures well (baseline, straight lines, letter shapes) on pages
written for the purpose. After #168 and #199 to #202 land, score the same
200 pages again the same way; the rubric scores and the page list are kept
with the photos for that, and the comparison above is the baseline to beat.
