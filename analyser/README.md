<!-- SPDX-License-Identifier: AGPL-3.0-only
     © 2026 Vahini Technologies. Contact: infor@vahinitech.com. Dual-IMU sensing: Indian Patent No. 584433.
     Distributed under GNU AGPL v3.0 only. Third-party notices: /THIRD-PARTY-NOTICES.md · SBOM: /sbom.spdx.json -->
# Analyser Layout

This folder contains the live handwriting analyser app, printable report assets,
video explainers, and the engine source used to build the packed browser bundle.

## Structure

- `Vahini Analyser.html` — analyser app entrypoint.
- `Vahini *.html`, `Why Handwriting Matters.html`, `20 Factors Explained.html` — printable and informational pages.
- `styles/` — analyser-only stylesheets (`report.css`, `studio.css`, `nav.css`).
- `scripts/core/` — runtime scripts (`engine.bundle.js`, `protect.js`, `report.js`, `image-slot.js`).
- `scripts/video/` — JSX scene helpers and motion files used by explainer pages.
- `assets/` — logos and static media consumed by analyser pages.
- `src/` — source-of-truth engine modules (not shipped raw in production).
- `server/` — optional local PP-OCR server.

## Build notes

- Browser runtime loads only `scripts/core/engine.bundle.js`.
- Engine source edits happen under `src/`.
- Rebuild flow is documented in `../docs/BUILD.md`.

## License

- License: GNU AGPL v3.0 only (`AGPL-3.0-only`).
- See `LICENSE` and `NOTICE` in this folder.
- Attribution contact: `infor@vahinitech.com`.

## Standalone run (independent)

You can run this analyser by itself, without the full repository portal:

1. Serve the `analyser/` directory as static files.
2. Open `Vahini Analyser.html`.
3. Optional: point OCR to your server by setting `window.VAHINI_OCR_ENDPOINT` before loading `scripts/core/engine.bundle.js`.

Example:

```bash
cd analyser
npx http-server . -p 8081 -c-1
# open http://127.0.0.1:8081/Vahini%20Analyser.html
```

## Integration into another repository/portal

To integrate this analyser into any repository:

1. Copy this full `analyser/` folder.
2. Keep relative subfolders intact: `styles/`, `scripts/`, `assets/`, `src/`.
3. Preserve `LICENSE`, `NOTICE`, SPDX headers, and third-party notices.
4. If your host has no `../site/`, the analyser still works; only shared nav/footer enrichment is skipped.

## Optional split deployment (separate analyser domain)

If you want `analyser.vahinitech.com` separated from the main portal domain:

1. Keep current containers as-is.
2. Add host vhost from `../deploy/analyser.vhost.nginx.conf`.
3. For production, change upstream in that file from `127.0.0.1:3016` to `127.0.0.1:3015`.
