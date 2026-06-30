# Third-Party Notices

The Vahini 20-Factor Handwriting Analyser is free software, licensed under the
GNU Affero General Public License v3.0 only (© 2026 Vahini Technologies — see
`LICENSE`). The **browser engine contains no
bundled third-party code libraries** — all computer-vision, scoring and report
code is first-party JavaScript. The components below are loaded at runtime, used
on an optional server path, or used only for deployment. Each remains under its
own licence and copyright.

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

Used **only** on the optional heavy-recognition *server* path to confirm which
characters were attempted. It is **not bundled in the browser app** and is never
the basis of a handwriting score. The Apache-2.0 licence requires preservation of
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

Used as the static web server in deployment (`deploy/nginx.conf`, `Dockerfile`).
Not part of the shipped client bundle.

---

*Questions about attribution or licensing: info@vahinitech.com*
