- Loop, tall-letter and letter totals are counted from what the reader
  read in the ink, not from a copied passage that replaced the reading
  (#209, and #200's fallback). With a passage, the share of loop letters
  (factor 3 when fewer than three bowls are expected) and of tall letters
  (factor 6 on a page too short for zone bands) counted letters the ink
  never showed, so a passage could raise those scores. How many bowls are
  expected still comes from the passage. The benchmark job also keeps
  what `benchmark.py update` would write as an artifact, so a pull
  request that moves scores can take `expected.json` from CI.
