# Source of the pages

**What these pages are, and are not.** Engraved model pages of adult
cursive from two American penmanship manuals of 1915 to 1925: the
writing a pupil was asked to copy, drawn by master penmen and printed
from engraved plates. They are the ideal end of the range, not
children's everyday writing. The set is a reference for the owner when
setting scales (`scripts/calibrate.py`, #197), not a scale to apply:
a child's page is not expected to look like these.

Only running sentences were cropped: no drills, ovals, single letters,
signatures or printed text. The crops were cut from the Internet
Archive's page images on 21 October 2026, each kept to the handwritten
block, and scaled down to 2600 pixels wide where wider (the stage
analyser reads at that size, `VAHINI_OCR_MAX_SIDE=2600`). Nothing else
was changed.

## A. N. Palmer, The Palmer Method of Business Writing (1915)

- A. N. (Austin Norman) Palmer, 1859-1927. New York: A. N. Palmer
  Company, 1915.
- Scan: University of California Libraries copy,
  https://archive.org/details/palmermethodofbu00palmrich
  (the text with images is also Project Gutenberg #66476,
  https://www.gutenberg.org/ebooks/66476).
- Rights: the Internet Archive item records "possible-copyright-status:
  NOT_IN_COPYRIGHT". Published in the USA in 1915, so in the public
  domain there; Palmer died in 1927, so it is also in the public domain
  in India (author's life plus 60 years).

| Page | Scan image | Printed page | Cropped |
|---|---|---|---|
| `palmer-092-specimen` | n95 | 92 | "This is a specimen of the Palmer Method penmanship..." (4 lines, below the drills) |
| `palmer-093-practice` | n96 | 93 | "It is not so much the amount of practice..." (the first 4 of the page's 12 lines; the other 8 repeat them) |

## C. P. Zaner, Zaner Method Writing: Arm Movement, Manual 144

- Charles Paxton Zaner, 1864-1918. Columbus, Ohio: Zaner & Bloser
  Company. This copy is the 1925 printing of the 1915 edition.
- Scan: Penpoints Archive,
  https://archive.org/details/zaner-method-writing-manual-144
- Rights: the item carries the Public Domain Mark 1.0
  (https://creativecommons.org/publicdomain/mark/1.0/), with the
  statement "Digitized by the Penpoints Archive from a privately owned
  original work, in the public domain. This digital edition is for
  research, study, and reuse." Published in the USA before 1931; Zaner
  died in 1918, so it is also in the public domain in India.

| Page | Scan image | Printed page | Cropped |
|---|---|---|---|
| `zaner-088-spacing` | n89 | 88 | "Spacing between letters should..." (3 lines) |
| `zaner-090-small-writing` | n91 | 90 | "Small writing may be quite plain..." (4 lines; the large copy above it, written at double size on purpose, is left out) |
| `zaner-093-short-loops` | n94 | 93 | "Many people prefer few, short loops..." (3 lines) |
| `zaner-095-good-writing` | n96 | 95 | "Good writing is more than an accomplishment..." (3 lines) |
| `zaner-096-commercial-asset` | n97 | 96 | "Good writing is a commercial asset..." (9 lines, three paragraphs) |
| `zaner-097-good-handwriting` | n98 | 97 | "A good handwriting can neither be bought nor sold..." (9 lines, three paragraphs) |

The written lines of each crop are in `set.json` (`page_text`), lower
case, with the words split across lines as the copy splits them.

The pages are committed, not cut again on each run, for the reason
`benchmarks/uji-clean/source.md` gives.
