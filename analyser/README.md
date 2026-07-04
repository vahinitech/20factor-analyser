<!-- SPDX-License-Identifier: AGPL-3.0-only
     © 2026 Vahini Technologies. Contact: info@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
     Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json -->
# Analyser folder

The live app, its source, and the Python server that computes every report.

## Layout

- `Vahini Analyser.html` is the app entrypoint.
- `src/` is the browser client source (app flow, OCR client, report renderer).
  Edit here, then rebuild the bundle.
- `scripts/core/` holds the packed build (`engine.bundle.js`) and runtime helpers.
- `scripts/video/` holds the JSX scene files used by the two explainer pages.
- `styles/` has the report, studio and nav CSS.
- `static/` has the printable and informational pages.
- `server/` is the recognition and scoring server. A report needs it running.
- `assets/` has logos and static media.

## Run it

```bash
python server/analyser-ocr-server.py
# open http://localhost:8080
```

The server hosts the app under `/analyser` and the analysis APIs on the same
origin, so there is nothing else to configure. To host the static files
somewhere else, set `window.VAHINI_OCR_ENDPOINT` to your server's `/ocr` URL
before the engine bundle loads.

## After editing src/

```bash
python ../build_bundle.py     # or: python analyser/build_bundle.py from the root
```

The browser loads only the packed `scripts/core/engine.bundle.js`. CI fails
if the bundle is out of date with `src/`.

## Reusing the analyser elsewhere

Copy this whole folder and keep the subfolder layout intact. Preserve
`LICENSE`, `NOTICE`, the SPDX headers and third-party notices. License is
AGPL-3.0-only; attribution contact info@vahinitech.com.
