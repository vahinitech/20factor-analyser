# Third-Party Notices

The Vahini 20-Factor Handwriting Analyser is free software, licensed under the
GNU Affero General Public License v3.0 only (© 2026 Vahini Technologies — see
`LICENSE`). The browser bundle contains first-party client and report code.
Computer vision and scoring run on the Python server. The browser lazily loads
PDF.js for PDF uploads and loads web fonts at runtime. Each third-party
component retains its own licence and copyright.

A machine-readable SBOM in SPDX 2.3 format is provided in `sbom.spdx.json`.

---

## Web fonts — loaded at runtime from Google Fonts

All four fonts are licensed under the **SIL Open Font License 1.1 (OFL-1.1)**.
<https://openfontlicense.org>

| Font | Author / Foundry | Licence |
|---|---|---|
| **Spectral** | Production Type | OFL-1.1 |
| **Hanken Grotesk** | Alfredo Marco Pradil | OFL-1.1 |
| **Caveat** | Impallari Type | OFL-1.1 |
| **Edu SA Beginner** | EduType | OFL-1.1 |

> The OFL permits use, study, modification and redistribution of the fonts,
> including bundling with proprietary software, provided the fonts themselves are
> not sold on their own and reserved font names are respected.

---

## Optional / server-side

**PaddleOCR (PP-OCRv5)** — © PaddlePaddle Authors — **Apache License 2.0**
<https://github.com/PaddlePaddle/PaddleOCR>

Used on the default recognition server path. It is not bundled in the browser
app. Some current scoring proxies consume its text and confidence outputs. The Apache-2.0 licence requires preservation of
copyright, licence and NOTICE files when redistributed; PaddleOCR is not
redistributed as part of the client build.

---

## Hosted runtime services (no code redistributed)

| Service | Provider | Terms |
|---|---|---|
| **QR image API** (`api.qrserver.com`) | goQR.me | Free for commercial & non-commercial use per goQR.me API terms. Used in the optional share flow; degrades gracefully offline. |
| **Google Analytics 4 + Google Tag Manager** | Google LLC | Google Analytics / APIs Terms of Service (proprietary hosted service, not OSS). |

---

## Deployment

**nginx** — © Igor Sysoev; © Nginx, Inc. / F5 — **BSD-2-Clause**
<https://nginx.org>

Optional reverse proxy for deployments. The default Docker image serves the
client and APIs through FastAPI/Uvicorn; nginx is not included in that image.

---

*Questions about attribution or licensing: info@vahinitech.com*


## PDF readers and dependency inventory

**PDF.js 6.3.289**, Mozilla Foundation and contributors, Apache-2.0, is loaded
from jsDelivr only for browser PDF uploads. Its worker uses the same pinned
version. Source: <https://github.com/mozilla/pdf.js>.

**pypdfium2 5.13.0** is a required core server dependency for PDF decoding.
Binding licensing and PDFium third-party notices are recorded by the package;
retain the upstream notices when distributing its binaries. Source:
<https://github.com/pypdfium2-team/pypdfium2>.

The SPDX source inventory includes npm test tooling and transitive lockfile
packages, plus declared core/default Python dependencies. Generate a separate
inventory from the built container for resolved Python transitives, operating
system packages and model weights. Refresh the source inventory with
`python backend/update_sbom.py` after dependency changes.
