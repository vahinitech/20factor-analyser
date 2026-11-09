- The backend's 52 Python files are sorted into folders by job:
  `server/` (the API, keys, limits, capacity, stores), `reading/` (photo to
  text), `vision/` (measurements from the ink), `report/` (the report,
  practice, coaching and the schema generator) and `tools/` (run by hand).
  `ppocr-server.py` is now `server/app.py`, `factor_needs.py` is
  `scoring_parts/needs.py`, `lang_tags.py` is `languages/tags.py`, and the
  engine requirement tiers are `requirements/<tier>.txt`. The entry files
  (`analyser-ocr-server.py`, `warmup_models.py`, `scoring.py`), `config.py`,
  `schemas/` and `catalogs/` stay where they were, so vahini-web, Docker and
  the contracts are unaffected. Moves and imports only; no behaviour changes.
  `backend/README.md` is one screen, and its engine, settings and benchmark
  sections moved to docs 06, 14 and 18.
