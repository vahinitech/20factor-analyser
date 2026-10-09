# Security Policy

## Reporting a vulnerability

Please report security issues **privately**. Do not open a public issue for a
vulnerability.

- Preferred: open a private security advisory via GitHub
  ("Security" tab → "Report a vulnerability") on
  https://github.com/vahinitech/20factor-analyser
- Or email: **info@vahinitech.com** with the subject `SECURITY:`

Include a description, reproduction steps, affected version/commit, and impact.
We aim to acknowledge within 5 business days and to provide a remediation
timeline after triage. Please give us reasonable time to fix before any public
disclosure.

## Scope

- The browser engine and app (`frontend/`).
- The Python OCR / 20-factor server (`backend/`).
- Deployment config (`deployment/`, `docker-compose.yml`).

## Handling user data

This project processes handwriting images, which can be sensitive.

- Do not commit real user images. `samples/` is git-ignored; CI fixtures are
  synthetic.
- Every supported OCR backend (`paddle`, `trocr`, `surya`, `hybrid`) runs
  locally; no image data leaves the machine.
- Never put personal data or secrets in URLs, logs, issues, or commits.

## Upload and image security (rules for every change)

Visitors' photos are the main way into this service, so every limit below is
deliberate and tested. Loosen one only with a reason recorded in the PR, a
test for the new boundary, and the owner's agreement. Owner decisions of
2026-10-09.

**Sizes, checked before anything is decoded**
- 5 MiB per file and 6 MiB per request (`backend/upload_limits.py`), counted
  as the bytes arrive. vahini-web's nginx refuses more than 6 MB first.
- 24 million pixels at most, read from the file header before decoding
  (`computer_vision._check_dimensions`): a decompression bomb never expands.
- PDFs: 1 to 100 pages, the first page's size checked before it is rendered,
  only that page analysed.
- One page is all an upload ever is. The website sends at most 2600 px and the
  Android app 2200 px, both as JPEG: the largest of 127 real uploads came to
  1.8 MB as sent.

**Formats**
- Only JPEG, PNG and WebP are decoded (`computer_vision.IMAGE_FORMATS`), plus
  PDF through pypdfium2. Pillow knows about forty formats; the rest are
  refused as 422 before their decoder runs. Never widen the list for
  convenience: each format is another decoder an attacker can reach through
  the public `/ocr`. `backend/tests/test_image_formats.py` sends eleven
  others and fails if one is decoded.
- Pillow is pinned to an exact version (`requirements-core.txt`). A Pillow
  bump is a security change: read its release notes and run the image tests.

**Nothing kept**
- The server never writes a photo to disk. Results stay in an in-memory cache
  for `VAHINI_OCR_CACHE_TTL_SEC` (180 s), and vahinitech.com's privacy page
  says so; change one, change the other.
- The website never sends the photo to its own store; only a family that
  ticks "Keep my pages" keeps one, encrypted, in vahini-web
  (`services/persist-api/lib/keepstore.js`).

**Abuse limits**
- Free tier: 3 checks a day per IP address, Pro never limited
  (`backend/daily_limit.py`). `X-Real-IP` is trusted only from a private peer.
  nginx adds 12 checks a minute per IP.
- Scans run one at a time with a short queue inside a memory-limited
  container (`backend/scan_slots.py`, `backend/capacity.py`).

**The container**
- Runs as user 10001, never root (`deployment/Dockerfile`, checked by
  `test_image_formats.HardeningTests`). vahini-web's compose files add a
  read-only filesystem, no Linux capabilities, `no-new-privileges` and a
  read-only model folder; `/tmp` (also `HOME`) and the subscription database
  volume are the only writable places. A new path the server must write to
  goes on a tmpfs or a volume, never back to a writable image.
- A local `paddle_models` volume made by an image older than 2026-10-09 is
  owned by root, and the non-root server cannot add models to it. Remove it
  once (`docker compose down -v`) or `chown -R 10001:10001` its folder.

**In the browser** (`frontend/`)
- A picked file over 10 MB is refused before decoding.
- Every photo is redrawn and sent as a new JPEG of at most 2600 px, so EXIF
  (location, camera) and anything appended to the file never leave the page.
- HEIC is converted by libheif-js loaded only when needed: the script with an
  SRI hash, the wasm file checked against its SHA-384 before it runs.
- PDFs are rendered with PDF.js (pinned, `isEvalSupported: false`), page 1.

