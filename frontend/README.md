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

## Pictures on the report (optional)

Page 2 of the report can show Vahini and friends, one job each (approved
2026-10-11, #122). The host page sets `window.VAHINI_REPORT_ART`, an object
of same-site image paths:

```js
window.VAHINI_REPORT_ART = {
  cheer: '/site/assets/characters/vahini.webp',      // beside the opening line
  buddy: '/site/assets/characters/bheema.webp',      // at its right
  tip: '/site/assets/characters/pihu.webp',          // small, in every tip
  encourage: '/site/assets/characters/tara.webp',    // beside the closing line
};
```

Values are checked like `VAHINI_NOTICE_ART`: anything that is not a
same-site path is ignored. The pictures are decorative (`alt=""`); without
the map the report has none and keeps the same layout. The drawings are not
part of this repository.

## Saved checks and "Your progress"

Each check is saved in this browser's `localStorage` (`vahini_history`, the
last 60, by writer name; sample runs never), with the exercise and tip ids
its report printed so the next report moves on to the next ones.
`src/report/progress.js` shows "Your progress" under the report, on screen
only: the writer's saved checks, a comparison with an earlier one, a
progress file to download or load (JSON, checked strictly, no photo) and a
way to forget this writer's checks. It makes no network call.

## Print in another language, and Share on WhatsApp

Every sentence the report prints is looked up by id in
`src/report/strings/en.js` (the source) and `src/report/strings/te.js`
through `src/report/i18n.js`; a language that lacks an id prints the
English sentence. Exercises and tips carry their own translations in the
practice catalogue (`i18n.te`). A new sentence goes into every table,
never into the renderer as a literal; `tests/report-strings.test.mjs`
fails while a language misses an id.

A host page that wants the language choice and the share button puts these
beside `#print-report` (both are screen only):

```html
<label class="report-lang" for="report-lang">Print in <select id="report-lang"><option value="en">English</option><option value="te" lang="te">తెలుగు (Telugu)</option></select></label>
<button class="btn btn-share" id="share-whatsapp" type="button">Share on WhatsApp</button>
```

`src/report/report-share.js` wires them: the select redraws the report and
"Your progress" in that language (kept in `localStorage`
`vahini_report_lang`), and the button shares `VahiniReport.shareText()`,
a summary with no name, photo, crop or id, through the phone's share sheet
or `https://wa.me/?text=`. The Telugu wording is a draft until a native
speaker has checked it.

