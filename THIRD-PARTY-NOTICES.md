# Third-Party Notices

The Vahini 20-Factor Handwriting Analyser is free software, licensed under the
GNU Affero General Public License v3.0 only (© 2026 Vahini Technologies — see
`LICENSE`). The browser bundle contains first-party client and report code.
Computer vision and scoring run on the Python server. The browser lazily loads
PDF.js for PDF uploads and loads web fonts at runtime. Each third-party
component retains its own licence and copyright.

A machine-readable SBOM in SPDX 2.3 format is provided in `sbom.spdx.json`.

---

## Web fonts — site pages (loaded at runtime from Google Fonts); report fonts are served locally, see below

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

## Trained weights: the print-or-handwriting line reader

`backend/models/print_hand.json` holds weights trained by
`scripts/train_print_hand.py`. No training data is redistributed; the
weights were learned from:

- **UJI Pen Characters (Version 2)**: Prat, Castro, Llorens, Marzal and
  Vilar, 2008, UCI Machine Learning Repository, doi:10.24432/C5FG8S.
  **CC BY 4.0** <https://creativecommons.org/licenses/by/4.0/>. Pen
  trajectories of 60 writers; the 40 training writers trained the reader
  and the 20 test writers make `scripts/planted_pages.py`'s test pages.
- **Fonts from github.com/google/fonts** at commit
  `66928797f271fed5ee428544e7229685e2d90127`, listed with their SHA-256 in
  `scripts/print_hand_data.py`: Noto Serif, Noto Sans, Noto Sans Mono,
  Courier Prime, Andika, Lato, Space Mono, Oswald, PT Serif, PT Sans,
  Merriweather, Source Code Pro, Comic Neue, Libre Baskerville, Dancing
  Script, Pacifico, Caveat, Kalam, Patrick Hand, Great Vibes, Indie Flower,
  Shadows Into Light and Sacramento (**OFL-1.1**), and Special Elite
  (**Apache License 2.0**). Text drawn in them was the reader's printed
  examples; no font file is included.

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

**libheif-js 1.23.5** (libheif 1.23.5), Kiril Vatev, struktur AG and the
libheif contributors, LGPL-3.0, is loaded from jsDelivr only when someone
picks a HEIC photo (the iPhone's format) that their browser cannot open, and
converts it to JPEG in the browser. It is loaded unmodified as separate files:
the script with an SRI hash, the wasm file checked against its SHA-384 before
it runs. Sources: <https://github.com/catdad-experiments/libheif-js> and
<https://github.com/strukturag/libheif>.

**pypdfium2 5.13.0** is a required core server dependency for PDF decoding.
Binding licensing and PDFium third-party notices are recorded by the package;
retain the upstream notices when distributing its binaries. Source:
<https://github.com/pypdfium2-team/pypdfium2>.

The SPDX source inventory includes npm test tooling and transitive lockfile
packages, plus declared core/default Python dependencies. Generate a separate
inventory from the built container for resolved Python transitives, operating
system packages and model weights. Refresh the source inventory with
`python backend/update_sbom.py` after dependency changes.


## Locally served report fonts

Spectral, Hanken Grotesk, Caveat and Edu SA Beginner are distributed under the SIL Open Font License 1.1. Original license files, upstream URLs and SHA-256 hashes are preserved in `frontend/assets/fonts/`. These files are served locally so reports do not require Google Fonts at export time.

**Noto Sans Telugu** (Copyright 2022 The Noto Project Authors, <https://github.com/notofonts/telugu>), SIL Open Font License 1.1: the Telugu subset, regular and bold, taken unchanged from the `@fontsource/noto-sans-telugu` npm package version 5.3.0 (`NotoSansTelugu-Regular.woff2`, `NotoSansTelugu-Bold.woff2`, licence `notosanstelugu-OFL.txt`, sources and hashes in `frontend/assets/fonts/sources.json`). A report printed or saved in Telugu uses it, so the PDF shows Telugu on any device.

## Browser libraries served with the report

These files are vendored unchanged in `frontend/scripts/vendor/` (npm
package, version, tarball URL and SHA-256 in `sources.json` there; the SBOM
entries come from that file through `backend/update_sbom.py`).

**QR Code Generator for JavaScript** (`qrcode-generator` 2.0.4), Copyright (c) 2009 Kazuhiko Arase, MIT License: `qrcode.js`, which draws the QR code on report page 1. The licence notice is in the file's own header; the package ships no separate licence file. "QR Code" is a registered trademark of DENSO WAVE INCORPORATED.

**jsPDF** 4.2.1, (c) 2010-2025 James Hall and (c) 2015-2025 yWorks GmbH, MIT License: `jspdf.umd.min.js`, licence `jspdf-LICENSE.txt`. It makes the report PDF that "Share PDF on WhatsApp" shares, in the visitor's browser.

**html2canvas** 1.4.1, Copyright (c) 2012 Niklas von Hertzen, MIT License: `html2canvas.min.js`, licence `html2canvas-LICENSE.txt`. It draws each report page to an image for that PDF.

jsPDF and html2canvas are loaded only when the share button is pressed; nothing they make is sent to Vahini.
