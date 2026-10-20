- The recognition ladders are now data (#219, part 1). `scripts/rank_stages.py`
  builds `backend/languages/ladders.json` from the stage table: for each OCR
  mode and script, the stages that may read a handwriting line, cheapest
  first, by the rules of docs/20-languages.md section 17.2 (hard filters,
  sort by cost, keep a stage only if it reads better than every cheaper one).
  No quality or cost is measured yet, so hybrid mode keeps its committed
  route and the file says which stages were not measured. The committed
  ladders give every line the engines it got before, in paddle, trocr and
  hybrid mode, and CI checks the file is up to date with `--check`. The
  stage table gains Paddle read stages for Hindi, Tamil, Kannada and
  Malayalam, with their model left unmeasured because PaddleOCR picks it.
  Nothing reads the ladders yet; the server is unchanged.
