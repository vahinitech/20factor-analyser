# Spelling and grammar on the page (24 October 2026)

Children in the school pilot asked for more than a handwriting check:
which words they spelt wrong, which sentences are wrong, and where on the
page each one is (#317). The owner asked for it in the free report, with
a dictionary, and for the check to look at only part of the page so scans
do not slow down. This note records how the check works, what it was
measured on and why its limits are where they are, for free writing and
for a copied or dictated sentence. It adds a `language`
section to the report response; nothing displays it yet, and no score
changed.

## Why a dictionary alone does not work

The reader's misreads look exactly like a child's misspellings. On 200
real handwritten pages (GNHK, with a transcript for every word), a
dictionary run over the words the reader returned flagged 3,604 words, of
which 3,425 (95%) were the reader's misreads; 178 of the 200 pages got at
least one false flag. Keeping only lines the reader was 95% sure of still
left 80% of the flags wrong. Copying a known sentence does not fix this
on its own either: compared text to text, 48% of the correctly written
words on the 20 benchmark pages, and 52% on the GNHK pages, were not read
exactly (#317).

## How the check works

`backend/reading/language_check.py`, `spelling.py` and `grammar.py`.

1. **Which rows.** English handwriting rows in reading order. A row is
   read again only when the reader read it at 0.80 or better and it holds
   a word the word list does not: lower case, four letters or more, and
   not two listed words run together (`onthe` is a spacing matter).
   Capitalised words are never judged, so names the list cannot know
   (Ramesh, Lakshmi) are safe. At most 6 rows, the clearest first, and 4
   words a row. The limits are counts, never a clock: a time budget would
   give the same photo different findings on a busy server.
2. **The ink check.** Each chosen row is read again by the scan's own
   recogniser (`ocr_backends.read_line_scores`), which keeps the score of
   every character in every column. For a word the list does not hold,
   listed words one or two edits away are scored on the columns of that
   word (the CTC probability, the quantity the recogniser was trained
   on). A listed word that fits the ink within a factor of 20 means the
   reader misread it: the word is corrected for the grammar step and
   nothing is said. The writer's own spelling is reported only when the
   reading beats every listed word by a factor of 10,000 and every letter
   scored 0.9 or more. Anything in between says nothing.
3. **The suggestion.** Among the listed words, the most likely slip for a
   child: a vowel for a vowel, a doubled or missing double letter, s for
   z, two letters swapped, the first letter kept, the more common word
   (`spelling.slip_cost`). SCOWL's own lists of words not to say around
   children are never suggested.
4. **Grammar.** Fixed English rules, their words as data in
   `backend/languages/skills/en.json`: a capital for a name (days, months,
   the series' names), "I" on its own, a or an, he/she/it with -s, the past
   of go, run and eat (goed, runned, eated), and "me and Bheema" as the
   subject. A rule runs only on a sentence whose every word is trusted (a
   listed word on a clear row, or checked against the ink), and a rule
   about two or more words only when they are on one line as read.
5. **Where.** Each finding has its place on the page: from the letters'
   own columns on a row read again, estimated from the share of the line's
   text otherwise (`placed: estimated`).
6. **A copied or dictated sentence.** When the scan comes with
   `expected_text`, the words read on the whole page, in reading order,
   are lined up with the sentence's words (the whole page, because the
   reader often reads a row in pieces that match no sentence line on their
   own). A word read that stands against a different sentence word, at
   least three letters long, within one letter of its length and at least
   0.7 alike (difflib ratio), is scored against that one word: 1,000 times
   more likely as read, and every letter scoring 0.7 or more, means the
   child wrote it so; the suggestion is the sentence's word
   (`against: sentence`). Any word counts, listed or not (rite for write).
   Grammar is not run on such a page: the sentence was given.

The word list is SCOWL 2020.12.07 (Kevin Atkinson; its licence is in
`backend/languages/words/SCOWL-Copyright.txt`), sizes up to 60 from the
English, American, British, Canadian and Australian lists: 105,509 words,
328 KB gzipped. `scripts/build_wordlist.py` rebuilds it from the release
tarball, checked by SHA-256, byte for byte.

## What it was measured on

`scripts/language_eval.py`, in the stage analyser image with the stage
reader settings (PP-OCRv5 mobile, English), one container at a time on
the shared host with more than 2.5 GB free.

| Set | Pages | Spelling findings | The writer's own | Grammar marks |
|---|--:|--:|--:|--:|
| Benchmark pages, every word spelt right (`uji-clean`) | 20 | 0 | n/a | 5, each a lower-case name on pages written all in lower case |
| Real pages with transcripts (GNHK) | 183 | 2 | 2 (cretenism for cretinism, broden for broaden) | 0 |
| Benchmark writers' letters with 13 misspellings planted, 193 planted words | 20 | 1 | 1 of 193 (practis) | 0 |

So the check is strict: on these pages it never reported a word the
writer had spelt right, and it found very few of the words they had not.
How the limits were chosen, from every word the check judged with the
limits opened (101 of the writers' own words, 557 others):

| Reading beats every listed word by | Weakest letter | Writer's own | Others |
|---|---|--:|--:|
| 100 times | 0.5 | 40 | 88 |
| 1,000 times | 0.9 | 7 | 2 |
| 10,000 times | 0.8 | 6 | 5 |
| 10,000 times (chosen) | 0.9 | 4 | 0 |

The owner's suggested bar was at least 19 real flags in 20. Only the
chosen limits met it.

**Why it finds so little.** Of the 193 planted words, only 75 were read as
an unlisted word on a clear row at all: the reader turned the rest into
something else, or read the row too unsurely to judge. The rest of the
loss is the ink check refusing to call close cases. This is the reader's
limit on free writing, not the word list's.

### A copied or dictated sentence

The same 20 writers' letters, each writing four of the benchmark
sentences twice: once with 16 misspellings planted (the 13 of the free
writing test, plus rite, wile and ovr, which the free check cannot see
because they are words or too short), once correctly, each checked against the
correct sentences as `expected_text`. The limits were chosen on the first
set of 40 pages; the second set (another random draw of sentences and
letters) was run once afterwards, as a check.

| Pages | Planted words | Found | Other flags |
|---|--:|--:|--:|
| 20 with misspellings, used to choose the limits | 229 | 37 (16%) | 0 |
| 20 copied correctly, same draw | 0 | n/a | 0 |
| 20 with misspellings, the check | 232 | 22 (9%) | 2 |
| 20 copied correctly, the check | 0 | n/a | 0 |

Free writing found 1 of 193 planted words on the same writers; the
sentence finds 10 to 37 times as many, and no copied-correctly page got a
flag. Both other flags in the check set were at a planted misspelling with
the right suggestion, but the reader had read the child's word wrong
(prattis for practis, beters for leters). So the report must show the
child's own ink at the place, never our reading of it as "you wrote".

Why it still misses most: the reader often reads a misspelt word as the
right one (its training pulls towards real words), or as something too
far from either to pair, and then there is nothing to judge.

**Grammar.** A rule for a capital after a full stop was built and
removed: on GNHK all nine of its marks were wrong by the transcript. The
reader reads stray marks as full stops and loses small ones, and its
reading order across a line read in pieces can be wrong. A full-stop rule
was not built for the same reason.

**Time.** Two runs on GNHK, the second while the unit tests ran on the
same host: a row read again took 26 to 31 ms at the median and 47 to 62
ms at the 90th percentile; the whole step took about 100 ms at the median
per page, 245 to 300 ms at the 90th percentile, and 1.0 to 1.7 s on the
slowest page (six long rows). Every scan records it as the `language` stage
(`backend/server/perf.py`). A whole scan takes 6 to 8 seconds on stage.

## What it does not do

- It does not change any score, the recognised text or the passage
  alignment, and it stores nothing: the section is in the response only,
  never in the report store (`test_language_check.py` holds this).
- An empty list never means the page has no mistakes. `checked` false
  with a reason means the page was not checked (not English, no letter
  scores from the reader, no text, an error).
- Telugu and other scripts are not checked.
- Nothing displays it. The report change needs the owner's approval with
  screenshots (`docs/12-report-rules.md`); mock-ups are in #317.

## Next

- The report cards (#317 mock-up), after the owner's approval. Show the
  child's own ink at each place and the right word, never our reading of
  the child's word.
- Copy and dictation pages with a sentence picker at upload (#317 mock-up
  C), since that mode finds 10 to 37 times as much.
- Children's own pages from the pilot, with consent, marked by their
  teacher, for testing only and deleted after.
