# Build — producing `engine.bundle.js`

The browser only ever loads **`analyser/scripts/core/engine.bundle.js`** (packed + base64-encoded). The readable
algorithm sources live in **`analyser/src/`** and are never shipped. This doc explains how the bundle is
produced so the build stays reproducible after edits.

## Source order

The bundle concatenates the engine sources **in this order**, then base64-encodes the result and
wraps it in a tiny self-decoding loader:

```
analyser/src/engine/engine.js
analyser/src/engine/factors.js
analyser/src/engine/ocr.js
analyser/src/engine/imu.js
analyser/src/engine/forecast.js
analyser/src/engine/craft.js
analyser/src/engine/crops.js
analyser/src/engine/letters.js
analyser/src/engine/narrate.js
analyser/src/report/report-render.js
analyser/src/app/app.js
analyser/src/app/share.js
```

Order matters: `app.js` references the globals (`VahiniEngine`, `VahiniFactors`, `VahiniReport`,
…) defined by the earlier modules, so it must come last.

## Rebuild steps

1. Edit the relevant file(s) under `analyser/src/`.
2. Concatenate the files in the order above into one string.
3. Base64-encode (UTF-8 safe) and emit the loader:

   ```js
   /* Vahini engine — packed build. */
   (function(){ try {
     var _v = "<BASE64>";
     (0, eval)(decodeURIComponent(escape(atob(_v))));
   } catch (e) { console.error("engine load failed", e); } })();
   ```

4. Write the result to **`analyser/scripts/core/engine.bundle.js`**.
5. Open `analyser/Vahini Analyser.html?demo=report` and confirm a report renders with no console errors.

> In this project the concatenate-and-pack step is run by the tooling that generated the current
> `analyser/scripts/core/engine.bundle.js`. The bundle is self-contained — moving the `analyser/src/` files does not affect the
> already-built bundle; only a **rebuild** reads from `analyser/src/`.

## Why not just ship `src/`?

Shipping raw sources puts every algorithm in the browser's Sources panel. Packing removes them
from casual inspection; `analyser/scripts/core/protect.js` blocks the context menu and view-source / devtools shortcuts.
Neither is encryption — client code is ultimately inspectable — but together they raise the bar
well beyond copy-paste.
