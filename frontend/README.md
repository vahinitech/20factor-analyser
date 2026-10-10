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

## Pictures on the error screens (optional)

Each refusal, upload notice and photo warning has an outcome code. A host
page can give any of them a picture by setting `window.VAHINI_NOTICE_ART`,
an object from code to an image path on the same site:

```js
window.VAHINI_NOTICE_ART = { busy: '/site/assets/characters/notices/busy.webp' };
```

The picture replaces the icon on a full-screen refusal and sits beside the
text in an upload notice or warning, with `alt=""` because the words carry
the message. A value that is not a same-site path is ignored, and without
the object every screen keeps its icon. The codes:

| Code | When |
|---|---|
| `busy` | the scan cap is full (503 with `Retry-After`) |
| `ocr_unavailable` | the server could not read the page (503, `error_code: "ocr_unavailable"`; from #116) |
| `daily_limit` | the free checks for today are used (429) |
| `no_handwriting` | the page is blank or fully printed |
| `server_down` | the server did not answer |
| `too_large` | the server refused the file's size (413) |
| `invalid_file` | the server could not open the file (422) |
| `key_problem` | the access key was refused (401, 403) |
| `account_unavailable` | the service that checks keys did not answer (503) |
| `too_big`, `heic`, `unreadable` | the upload box refused the file before sending |
| `pdf_unreadable`, `pdf_pages` | a PDF that could not be read, or has more than one page |
| `photo_warning` | the photo is small or blurry (the check can still run) |

vahinitech.com fills the map from its own drawings library; the drawings are
not part of this repository.
