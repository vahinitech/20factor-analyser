# Build: producing `engine.bundle.js`

The browser only ever loads **`frontend/scripts/core/engine.bundle.js`** (packed + base64-encoded). The readable
sources live in **`frontend/src/`** and are never shipped. This doc explains how the bundle is
produced so the build stays reproducible after edits.

> **Scoring runs server-side.** The 20-factor analysis and all computer vision now live in the
> Python recognition server (`backend/server/app.py`, `POST /report-python`). The browser
> bundle is the **recognition client + report renderer** only: it sends the image and renders the
> analysis the server returns. There is no in-browser CV engine or scorer.

## Source order

The bundle concatenates the browser sources **in this order**, then base64-encodes the result and
wraps it in a tiny self-decoding loader:

```
(generated) window.VahiniPracticeCatalog, from backend/report/practice_catalog.py
frontend/src/engine/compact-client.js
frontend/src/engine/account.js
frontend/src/engine/ocr.js
frontend/src/engine/imu.js
frontend/src/engine/forecast.js
frontend/src/engine/craft.js
frontend/src/engine/narrate.js
frontend/src/report/worksheet-catalog.js
frontend/src/report/worksheets.js
frontend/src/report/progress.js
frontend/src/report/report-render.js
frontend/src/app/app.js
frontend/src/app/share.js
```

The first part is not a file: `build_bundle.py` imports `backend/report/practice_catalog.py` (standard
library only, validated on import) and packs its exercises, tips and practice settings, so the
sample report and any report without a served catalogue use the same practice as the server.

Order matters: `app.js` references the globals (`VahiniOCR`, `VahiniReport`, …) defined by the
earlier modules, so it must come last. The canonical list lives in `frontend/build_bundle.py`.

## Rebuild steps

1. Edit the relevant file(s) under `frontend/src/`.
2. Run the packer:

   ```
   python frontend/build_bundle.py
   ```

   It concatenates the sources in the order above, base64-encodes (UTF-8 safe) the result, and
   writes the self-decoding loader to **`frontend/scripts/core/engine.bundle.js`**:

   ```js
   /* Vahini engine: packed build. */
   (function(){ try {
     var _v = "<BASE64>";
     (0, eval)(decodeURIComponent(escape(atob(_v))));
   } catch (e) { console.error("engine load failed", e); } })();
   ```

3. Don't commit it: `engine.bundle.js` is gitignored build output. The image build runs
   `build_bundle.py --stamp` (bundle plus `?v=` stamps on the pages' scripts and styles), and
   CI builds it before the browser tests and fails if a bundle or stamp is committed. Both used
   to be committed, and every frontend PR conflicted with every other one on them.
4. With the recognition server running (`docker compose up -d`), open
   `http://localhost:8080/analyser/analyser.html`, upload a sample, and confirm a report renders
   with no console errors.

> The bundle is self-contained: moving the `frontend/src/` files does not affect the already-built
> bundle; only a **rebuild** reads from `frontend/src/`.

## Why not just ship `src/`?

Shipping raw sources puts every algorithm in the browser's Sources panel. Packing removes them
from casual inspection; `frontend/scripts/core/protect.js` blocks the context menu and view-source / devtools shortcuts.
Neither is encryption: client code is ultimately inspectable: but together they raise the bar
well beyond copy-paste.

## Running the service

Moved here from `backend/README.md` when the backend was sorted into folders.

### Common settings

| Env var | Default | What it does |
|---|---|---|
| `PORT` | `8080` | HTTP port |
| `VAHINI_OCR_BACKEND` | `paddle` | engine, see the table above |
| `VAHINI_OCR_LANGS` | `en,te` | languages to load; request one with `lang=` |
| `VAHINI_OCR_GPU` | auto | force GPU (`1`) or CPU (`0`); unset auto-detects |
| `VAHINI_OCR_VARIANTS` | `2` | max preprocessing variants for faint pages |
| `VAHINI_PRINTED_THRESHOLD` | `0.58` | printed vs handwriting split; higher keeps more as handwriting |
| `VAHINI_OCR_ENGINE_RETRY_SEC` | `300` | how long a failed engine build is remembered before retrying |
| `VAHINI_OCR_ORIGINS` | `*` | CORS allowlist for cross-origin deployments |
| `VAHINI_ENVIRONMENT` | unset (production) | `stage` on the stage analyser: new Pro keys start `vh_test_`, and production refuses those keys |
| `VAHINI_REFINE_MIN_SIM` | `0.70` | in `trocr`/`hybrid` mode, accept a re-read line if it's at least this similar to paddle's reading |
| `VAHINI_REFINE_MIN_CONF` | `0.75` | in `trocr`/`hybrid` mode, accept a re-read line if the specialist's own confidence is at least this high, even if it disagrees with paddle |
| `VAHINI_HYBRID_MAX_MS_PER_LINE` | `2500` | `/health` marks an engine slower than this per line as not `fast_enough`; information only, it never skips the engine |
| `VAHINI_HYBRID_RETRY_SEC` | `600` | how long a speed measurement stays in `/health` |

GPU is auto-detected per engine; force it per engine with `VAHINI_OCR_GPU`,
`VAHINI_TROCR_GPU`, `VAHINI_SURYA_GPU`.

### Pointing a website at it

The client tries `window.VAHINI_OCR_ENDPOINT`, then same-origin `/ocr`, then
`http://127.0.0.1:8080/ocr`. In production set one line before the bundle
loads and reverse-proxy `/ocr` to this service:

```html
<script>window.VAHINI_OCR_ENDPOINT = "https://example.com/ocr";</script>
```

Requests are `multipart/form-data` with `image` and optional `lang`
(`en`, `te`, `hi`, `ta`, `kn`, `ml`, or `auto`).

### Keep models on disk between deployments

Mount a host folder over the model cache so containers never re-download:

```bash
docker run --rm -p 8080:8080 \
  -e PADDLE_PDX_CACHE_HOME=/opt/paddle-models \
  -v /srv/paddle-models:/opt/paddle-models \
  vahini/20factor-analyser:local
```

`docker-compose.yml` already does this with a named volume.
