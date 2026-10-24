- A photo of a page taken sideways or upside down, with no EXIF turn, is
  turned upright before it is read (#297). A school's sideways notebook photo
  was scored as it lay: 3 lines on an 18-line page and Line alignment 8.0.
  The analyser now finds the direction of the lines and which way is up from
  the writing itself (`vision/page_turn.py`, no new model), asks its own
  reader about a few line crops when a turn is in question, and decodes the
  photo again turned, so the scores are exactly those of the upright photo.
  The report says `turned: 90`, 180 or 270, and the check page turns its
  copy of the photo the same way before drawing it. A page whose lines run
  up and down when the way up is unclear, and any sideways Telugu page, is
  refused with `turned_page` ("turn the photo so the lines run across")
  instead of scored. An upright page is never turned and never asks the
  reader, so the benchmarks do not move.
