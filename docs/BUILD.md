# Build: producing `engine.bundle.js`

The browser only ever loads **`frontend/scripts/core/engine.bundle.js`** (packed + base64-encoded). The readable
sources live in **`frontend/src/`** and are never shipped. This doc explains how the bundle is
produced so the build stays reproducible after edits.

> **Scoring runs server-side.** The 20-factor analysis and all computer vision now live in the
> Python recognition server (`backend/ppocr-server.py`, `POST /report-python`). The browser
> bundle is the **recognition client + report renderer** only: it sends the image and renders the
> analysis the server returns. There is no in-browser CV engine or scorer.

## Source order

The bundle concatenates the browser sources **in this order**, then base64-encodes the result and
wraps it in a tiny self-decoding loader:

```
frontend/src/engine/ocr.js
frontend/src/engine/imu.js
frontend/src/engine/forecast.js
frontend/src/engine/craft.js
frontend/src/engine/narrate.js
frontend/src/report/report-render.js
frontend/src/app/app.js
frontend/src/app/share.js
```

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

3. Commit the regenerated bundle. CI (`e2e` job) re-runs `build_bundle.py` and fails if the
   committed `engine.bundle.js` is stale.
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
