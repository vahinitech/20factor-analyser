<!-- SPDX-License-Identifier: AGPL-3.0-only
     © 2026 Vahini Technologies. Contact: info@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
     Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json -->
# Frontend

The live app and its browser source. The `backend/` folder next to this one
is the Python server that computes every report; a report needs it running.

## Layout

- `analyser.html` is the app entrypoint.
- `src/` is the browser client source (app flow, OCR client, report renderer).
  Edit here, then rebuild the bundle.
- `scripts/core/` holds the packed build (`engine.bundle.js`) and `protect.js`,
  a small runtime helper loaded directly (not part of the bundle).
- `scripts/video/` holds the JSX scene files used by the two explainer pages.
- `styles/` has the report, studio and nav CSS.
- `static/` has the printable and informational pages.
- `assets/` has logos and static media.

## Run it

```bash
python ../backend/analyser-ocr-server.py     # or: python backend/analyser-ocr-server.py from the root
# open http://localhost:8080
```

The server hosts this folder under `/analyser` and the analysis APIs on the
same origin, so there is nothing else to configure. To host the static files
somewhere else, set `window.VAHINI_OCR_ENDPOINT` to your server's `/ocr` URL
before the engine bundle loads.

## After editing src/

```bash
python build_bundle.py     # or: python frontend/build_bundle.py from the root
```

The browser loads only the packed `scripts/core/engine.bundle.js`. CI fails
if the bundle is out of date with `src/`.
