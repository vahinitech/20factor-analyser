- A reader for handwritten Telugu, groundwork for scoring Telugu pages:
  `backend/telugu_reader.py` (numpy, 8-bit weights, the same text for the
  same crop) and `scripts/train_telugu_reader.py`, which trains it on
  IIIT-INDIC-HW-WORDS-Telugu (CC BY 4.0) on a CUDA GPU, Apple's GPU or the
  CPU. `scripts/train_guard.py` keeps a CPU run off a shared machine's
  memory: half the cores, niced, a checkpoint and a wait below a memory
  floor, a clean stop with `--resume` above its own ceiling. Not used by a
  scan until it passes a held-out test.
