- The live benchmark reads every page and the sample photo with
  `lang=auto` and with `lang=en`, and fails unless both give the same
  number of lines and the same scores within 0.3 (#145). A named language
  once kept most lines twice and moved the score.
