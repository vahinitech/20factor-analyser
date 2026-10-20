- The browser's health probe asks for `/ocr/health` instead of `/health`
  (#34). It replaced the `/ocr` suffix instead of appending to it, so behind
  a proxy that routes `/ocr` to the server the probe reached the website,
  and it passed only because the website answered unknown paths with its
  home page. The probe now also needs the server's JSON health payload with
  `ok: true`; an HTML page with status 200 no longer counts as up.
  `ppocr-server.py` serves `/ocr/health` itself, so running it alone answers
  the probe too, not only the combined `analyser-ocr-server.py`.
