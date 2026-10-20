- Each handwriting line now climbs its recognition ladder (#219, part 2).
  `backend/escalation.py` replaces the hybrid and trocr refine loop. It reads
  `ladders.json`, keeps the 0.70 similarity or 0.75 confidence guard, reads
  the lines that reach one rung in one call when the engine can, and caches
  answers per engine by crop hash, stage version and prompt version. Today's
  ladders give every line the engines and the text it got before, so no
  score moves. What changes is a missing engine: when a line needs one that
  is not installed, fails, or is a remote stage with its circuit breaker
  open, the page is refused with `ocr_unavailable` and `Retry-After`,
  instead of keeping Paddle's reading for that line. The same photo now
  gets the same score or a "try again", never a different score. Each line
  in the legacy payloads records its trail, and the payload records the
  ladder and stage versions.
