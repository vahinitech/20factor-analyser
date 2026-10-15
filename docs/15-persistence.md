# Persistence: uploads, reports, feedback

`analyser.html` will optionally post three kinds of record to a
`/persist` service, if one is deployed in front of it: the uploaded image,
the generated report, and lead-capture feedback. None of this lives in this
repo. `ppocr-server.py` does not implement `/persist/*`, and
`docker-compose.yml` runs a single `analyser` service with no persistence
service alongside it. If nothing answers at `/persist`, every call below
fails silently and the app works exactly the same, since scoring and the
report never depend on it.

This document describes the contract the client expects, for whoever wires
up that service in a deployment.

## Endpoints the client calls

Base path defaults to `/persist` (`window.VAHINI_PERSIST_ENDPOINT`).

- `POST /persist/upload-image`
  ```json
  {
    "fileName": "upload.jpg",
    "mimeType": "image/jpeg",
    "dataUrl": "data:image/jpeg;base64,...",
    "source": "upload",
    "meta": { "size": 123456, "modified": 0, "page": "/analyser/analyser.html" }
  }
  ```
  Fires once per upload, before analysis runs. The image travels as a data
  URL in the JSON body, not multipart form data.

- `POST /persist/generated-report`
  ```json
  {
    "trigger": "print-click",
    "url": "http://localhost:8080/analyser/analyser.html",
    "lead": { "name": "...", "email": "...", "ts": 0 },
    "upload": { "ok": true },
    "reportHtml": "<section class=\"page\">...",
    "reportText": "first 40000 characters of the report, plain text",
    "extra": { "ua": "...", "lang": "en-US" }
  }
  ```
  Fires when the report is saved: a click on Print/Save as PDF, or the
  browser's own `afterprint` event. `reportHtml` strips any inline image
  data URL over 2 MB down to a placeholder string, so a page full of crops
  does not blow past a request body limit. If the first call does not come
  back `ok`, the client retries once with `reportHtml` empty and
  `extra.fallback: true`, so at least the lead and report text land
  somewhere.

- `POST /persist/feedback`
  ```json
  { "kind": "report_pdf_lead", "ts": "2026-07-05T12:00:00.000Z", "data": { "name": "...", "email": "..." } }
  ```
  Fires once, right after the lead-capture form in the PDF download dialog
  is submitted (see the `vgate` script in `analyser.html`). This call
  is hard-coded to `/persist/feedback`, not `VAHINI_PERSIST_ENDPOINT`, so a
  deployment that moves the base path needs to update both.

## What is NOT part of this repo

Storage location, retention, a `/persist/health` check, and the service
itself are all deployment concerns. Build them however fits the hosting
setup: a small Node/Python service, object storage, a queue, whatever. The
client only needs three POST endpoints that return `{"ok": true}` on
success; everything else is optional.

## Stage debug storage (the analyser's one write)

The analyser itself never keeps a photo, with one switch for stage only.
`backend/debug_store.py` keeps each answered upload's photo and response
when both `VAHINI_DEBUG_STORE=1` and `VAHINI_DEBUG_STORE_DIR` are set:

```
<dir>/analyser/2026-10-15/091502-3f9a0c1d2b4e5f60.jpg    the photo, as sent
<dir>/analyser/2026-10-15/091502-3f9a0c1d2b4e5f60.json   route, lang, saved_at,
                                                          photo, photo_bytes,
                                                          response
```

Dates and times are UTC. The routes are `/ocr`, `/analyze-vl`,
`/report-python` and `/api/v2/reports`; a cache hit is kept too, since the
photo still arrived. Files are created mode 600 in folders of mode 700, as
the container's user (10001).

Production never sets these variables. On vahinitech.com,
`deploy/stage-debug.sh on|off|status|export|purge` in vahini-web
provisions them for the stage analyser, mounts a Docker volume at
`/data/debug`, and shows a notice on every stage page while it is on.
Nothing is deleted automatically: `purge` does it. `/health` reports
`debug_store` so either host can be checked. The rule this is an
exception to, and the exception's limits, are in
[SECURITY.md](../SECURITY.md#upload-and-image-security-rules-for-every-change).

## Report records (kept for every family, no personal data)

So a family can compare a later check with an earlier one, the analyser
keeps a small record of every successful compact report (owner decision,
2026-10-16; `backend/report_store.py`). It is on when
`VAHINI_REPORT_STORE_DIR` names a writable folder:

```
<dir>/reports/<32 hex>.json    id, token_sha256, expires, report
```

`report` is built from an allowlist, never by deleting fields from the
response. It holds the day of the check (UTC, no time), the catalogue
version, the tier, the overall score, each factor's score and status, the
Pro section scores, the comparability counts (lines, words, characters,
script, reading languages, printed lines left out, reading level, passage
match) and where each factor was measured, as boxes and lines in the
photo's pixels. It never holds the photo, a cut-out of it, the words read
from the page, a caption, the uploaded file's name, the passage typed in,
the access key, the caller's address or browser, or a time of day. The
words are left out because children often write their name or school at
the top of the page.

| Call | What it does |
| --- | --- |
| `POST /api/v2/reports?format=compact` | The report, plus `receipt: {id, token, expires}` when a record was kept |
| `GET /api/v2/reports/{id}` with `X-Report-Token` | The record (`backend/schemas/stored-report.schema.json`), or 404 |
| `DELETE /api/v2/reports/{id}` with `X-Report-Token` | Deletes it: 204, or 404 |
| `POST /api/v2/reports/renew` `{"receipts": [...]}` | Moves each valid receipt's expiry to 12 months from today |

Unknown, expired and deleted records, and a wrong token, all answer 404.
Only the token's SHA-256 is stored, so a copy of the folder cannot read a
record back, and nothing links a record to a person, a device or another
record. The check page keeps each receipt with the browser's saved checks
(`frontend/src/report/progress.js`); a new check renews the earlier
receipts, and "Forget" deletes their records. Records expire 12 months
after the family's last check: `sweep()` deletes expired files at the first
save of each day. Files are mode 600 in a folder of mode 700. The expanded
format (`format=expanded`, for API partners) keeps nothing.

`backend/tests/test_report_store.py` is the proof that nothing personal is
kept: it puts a page whose words name a child and a school, with a named
upload and a typed passage, through the real route and searches every byte
written; it also checks every key and string of a record against a closed
list, and feeds a hostile report with extra text fields.
