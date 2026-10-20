- A page whose fitted baseline runs steeply across a wide word no longer
  fails with "could not broadcast input array" and no report (#199, 16 of
  200 real GNHK pages). When levelling a word, a column that the slope moves
  wholly outside the levelled strip is left empty instead of copied with
  mismatched slices. Columns inside the strip are levelled exactly as before,
  so no score moves. The report handler now logs the traceback, so the next
  failure shows its line in the container log.
