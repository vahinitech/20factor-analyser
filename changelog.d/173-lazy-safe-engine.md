- The "safe" PaddleOCR engine, a second copy of the reader's models kept as
  a fallback, is built only when the normal engine fails to build or fails
  on a page (part of #173). Before, the startup warm-up and every scan built
  it for every configured language, so each container held two copies of
  `PP-OCRv5_server_rec` for English although the second is almost never
  used. What is read and the errors reported are unchanged. This lowers the
  container's baseline memory; whether memory still grows from scan to scan
  needs the stage load test the issue asks for.
