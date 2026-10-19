# Scoring findings, 19 and 20 October 2026: the evidence

Pictures for the findings recorded as issues on 20 October 2026, kept so
each issue can point at what was seen. Pages: UJI Pen Characters
(Version 2), Prat, Castro, Llorens, Marzal and Vilar, 2008, UCI Machine
Learning Repository, doi:10.24432/C5FG8S, CC BY 4.0, written into pages by
`scripts/planted_pages.py`. No child's photo is here; the Telugu findings
have no pictures, as that dataset's licence for publishing is not
confirmed.

"Before" is the free check on stage on 19 October (`lang=en`) or the code
on `main` at 4055c6f; "after" is the fixes in #168, #169 and #175.

| Picture | Finding |
|---|---|
| `lines-W18-read-twice-and-lost.jpg` | A line kept twice ("seeta" and "seetha"), the first line dropped as a header, a line never detected |
| `lines-W42-split-into-pieces.jpg` | Four written lines read as ten pieces |
| `lines-W54-missed.jpg` | Two of four lines never read |
| `lines-W57-pieces.jpg` | A joined hand in eight pieces: Size 1.0, Baseline 4.5 |
| `word-spacing-W27-gap-between-boxes.jpg` | Word Spacing 0: the space between two pieces counted as one word gap |
| `size-W57-loops-counted-as-size.jpg` | Loops of tall letters measured as letter size; "the" and "fox" marked taller |
| `margin-W30-stray-piece-as-line-start.jpg` | Margin Discipline 0: a stray piece counted as a line's start |
| `planted-*-factor-N.jpg` | A mistake planted for factor N beside its clean twin, with the factor's score before and after, and how many of the 20 writers it was caught on (`scripts/factor_tests.py`) |
