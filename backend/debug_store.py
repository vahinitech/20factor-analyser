# SPDX-License-Identifier: AGPL-3.0-only
"""Stage-only debug storage: keep each checked photo and its answer.

The analyser never writes a photo to disk (SECURITY.md, "Nothing kept").
This module is the one exception, for stage.vahinitech.com only, so the
team can replay a child's page that scored oddly. Production never sets
it, and vahini-web's deploy/stage-debug.sh is the only thing that does.

It is on only when both are set:
  VAHINI_DEBUG_STORE=1            (any other value is off)
  VAHINI_DEBUG_STORE_DIR=<folder> (a writable volume; the container is
                                   otherwise read-only)

When on, every upload route the server answers (/ocr, /analyze-vl,
/report-python, /api/v2/reports) writes two files:
  <dir>/analyser/<YYYY-MM-DD>/<id>.<ext>   the photo bytes as received
  <dir>/analyser/<YYYY-MM-DD>/<id>.json    the route, language and the
                                            whole response sent back
The id is the UTC time plus random hex. The visitor's file name is never
used (it can carry a child's name), and nothing about the caller (address,
browser, access key) is written. A refused request (413, 422, 429, 503)
is not kept. A failed write is logged and the scan carries on.

When off, the routes run exactly as they did before this module existed.
"""

import asyncio
import contextvars
import functools
import json
import logging
import os
import secrets
from datetime import datetime, timezone

from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response

log = logging.getLogger("vahini.debug_store")

# The bytes of the photo the current request uploaded; set by
# received() from the server's _read_upload().
_RAW = contextvars.ContextVar("debug_store_raw", default=None)

# Magic bytes of the formats the server decodes (SECURITY.md, "Formats").
_SIGNATURES = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"%PDF", "pdf"),
)


def extension(raw):
    """The file extension for these bytes, from their content alone."""
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    for magic, ext in _SIGNATURES:
        if raw.startswith(magic):
            return ext
    return "bin"


class DebugStore:
    """Where (and whether) photos and answers are kept."""

    def __init__(self, folder=None):
        self.folder = folder or None

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        if env.get("VAHINI_DEBUG_STORE", "") != "1":
            return cls(None)
        return cls(env.get("VAHINI_DEBUG_STORE_DIR", "").strip() or None)

    @property
    def enabled(self):
        return self.folder is not None

    def save(self, route, raw, response, lang=None, now=None):
        """Write the photo and its answer; return the id, or None."""
        now = now or datetime.now(timezone.utc)
        day = os.path.join(self.folder, "analyser", now.strftime("%Y-%m-%d"))
        ident = f"{now.strftime('%H%M%S')}-{secrets.token_hex(8)}"
        ext = extension(raw)
        record = {
            "id": ident,
            "route": route,
            "lang": lang,
            "saved_at": now.isoformat(timespec="seconds"),
            "photo": f"{ident}.{ext}",
            "photo_bytes": len(raw),
            "response": response,
        }
        try:
            os.makedirs(day, mode=0o700, exist_ok=True)
            _write(os.path.join(day, f"{ident}.{ext}"), raw)
            _write(
                os.path.join(day, f"{ident}.json"),
                json.dumps(record, ensure_ascii=False, default=str).encode(),
            )
        except (OSError, TypeError, ValueError) as exc:
            log.warning("debug store: could not keep %s: %s", ident, exc)
            return None
        return ident


def _write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


STORE = DebugStore.from_env()


def received(raw):
    """Note the uploaded bytes for keeps(); does nothing when off."""
    if STORE.enabled:
        _RAW.set(raw)


def _response_body(result):
    if isinstance(result, Response):
        try:
            return json.loads(result.body)
        except (ValueError, AttributeError):
            return None
    return jsonable_encoder(result)


def keeps(route):
    """Decorate an upload route so its photo and answer are kept when on."""

    def wrap(endpoint):
        @functools.wraps(endpoint)
        async def run(*args, **kwargs):
            store = STORE
            if not store.enabled:
                return await endpoint(*args, **kwargs)
            token = _RAW.set(None)
            try:
                result = await endpoint(*args, **kwargs)
                raw = _RAW.get()
            finally:
                _RAW.reset(token)
            if raw is not None:
                try:
                    body = _response_body(result)
                    await asyncio.to_thread(
                        store.save, route, raw, body, kwargs.get("lang")
                    )
                except Exception as exc:  # pylint: disable=broad-except
                    # Debugging must never cost a family their report.
                    log.warning("debug store: %s not kept: %s", route, exc)
            return result

        return run

    return wrap
