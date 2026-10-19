- A page asked for as Telugu (`lang=te`) is no longer scored from a reading
  the reader did not manage. On 60 handwritten Telugu pages the Telugu reader
  read 395 Latin letters against 123 Telugu ones, and every page still got a
  20-factor report. The page now gets the `handwriting_not_read` refusal
  unless at least three in four letters read are Telugu and the mean reading
  confidence is 0.80 or more. The refusal is not cached and does not use a
  free check. English and `auto` scans are unchanged.
