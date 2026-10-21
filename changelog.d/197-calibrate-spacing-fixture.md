- The calibration tool's unit tests build their neat pages with the
  feature factor 9's scale divides, read from the tool's scale table
  (#197). They named the old `letter_gap_cv`, which the tool no longer
  reads since spacing moved to the distance from the median, so those
  pages' values were dropped without a test noticing.
