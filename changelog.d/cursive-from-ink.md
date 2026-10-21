- A page the reader reads in pieces is measured from the ink (#277).
  Joined cursive came back as short pieces ("Thi", "cmen") with most of
  each row unread, and every factor was measured on the pieces' boxes:
  neat penmanship scored Margin Discipline 0 on five of eight pages. The
  reader's lines are now grouped into rows and each row is widened to the
  ink on it (`ink_geometry.fragment_rows`); when the reader's boxes cover
  too little of the rows, or come in many or short pieces, the page is
  measured on the whole rows, and the reader's own lines still give the
  text. The response says so in `recognition.ink_reason`
  (`read_in_fragments`, or `language` for the Telugu ink mode).
- Letter Spacing (9) is "Not measured" on a page the style check calls
  joined cursive: there are no gaps between its letters, only pen lifts.
  The reason code is the factor's `scoring_inputs.method`,
  `letters_joined`; no new words are shown to families yet.
- `benchmark.py fragments` prints each page's reader boxes against its
  ink rows, and CI fails if a real benchmark page would be read in
  pieces. No UJI or planted page moves.
