<!-- SPDX-License-Identifier: AGPL-3.0-only
     © 2026 Vahini Technologies. Contact: info@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
     Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json -->
# Recognition server

The Python service behind the analyser. It reads the page, measures the
ink and returns the 20-factor report; the browser uploads a photo and
draws what comes back.

```bash
./backend/setup.sh                      # venv, core packages and PaddleOCR
python backend/analyser-ocr-server.py   # then open http://localhost:8080
```

Docker: `docker compose up -d --build` from the repository root.

## What is where

| Folder or file | What it does |
|---|---|
| `analyser-ocr-server.py` | Starts the service: the app under `/analyser` and the API |
| `config.py` | Every `VAHINI_*` setting, read once |
| `scoring.py`, `scoring_parts/` | The 20 factors: inputs, formulas and "Not measured" rules |
| `server/` | The API (`app.py`), keys, daily limits, capacity, caches, the report store |
| `reading/` | From photo to text: detection, the readers, printed or handwritten |
| `vision/` | Measurements from the ink: lines, letters, zones, slant, spacing |
| `languages/` | Language packs, recognition stages and ladders |
| `report/` | The report, practice and coaching; the JSON Schema generator and the one validator (draft-07) |
| `schemas/`, `catalogs/` | API contracts and versioned report dictionaries (both generated) |
| `models/`, `perf/` | Small trained models; per-page cost budgets |
| `requirements.txt`, `requirements/` | The default install; one file per engine tier |
| `warmup_models.py` | Downloads and warms the models before the first scan |
| `tools/` | Run by hand: the SBOM, a load test, engine timing |
| `tests/` | `python -m unittest discover -s backend/tests -t .` |

## Read more

- Engines, settings, hybrid mode and the layout filter: [docs/06](../docs/06-reading-engines.md#engine-settings-and-modes)
- Settings, pointing a website at it, keeping models between deployments: [docs/14](../docs/14-build.md#running-the-service)
- The API: [API-V2.md](API-V2.md); capacity: [docs/13](../docs/13-api-and-capacity.md)
- Giving, renewing and taking back Pro (operators): [docs/17](../docs/17-access-and-trials.md) and `deployment/grant-pro.sh`
- Benchmarks: [docs/18](../docs/18-benchmark.md)

Reading is assistive: it labels what was written so the report can show
it. The 20 factors are measured from the pixels whether or not the words
could be read. *PaddleOCR is Apache-2.0, see /THIRD-PARTY-NOTICES.md.*
