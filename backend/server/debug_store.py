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

When on, every upload route (/ocr, /analyze-vl, /report-python,
/api/v2/reports) writes two files as soon as the photo has been read:
  <dir>/analyser/<YYYY-MM-DD>/<id>.<ext>   the photo bytes as received
  <dir>/analyser/<YYYY-MM-DD>/<id>.json    the route, language and outcome
The record starts as outcome "started" and is rewritten when the request
ends: "answered" with the whole response, "refused" with the HTTP status
and message, or "failed" with the error's type and message. A record still
"started" means the analyser died mid-scan (2026-10-23: a crash on stage
left nothing to replay, because only answered checks were kept). A request
turned away before its photo is read (too large) has nothing to keep.
The id is the UTC time plus random hex. The visitor's file name is never
used (it can carry a child's name), and nothing about the caller (address,
browser, access key) is written. A failed write is logged and the scan
carries on.

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

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response

log = logging.getLogger("vahini.debug_store")

# (route, lang) of the upload route the current request is in, set by
# keeps(); received() keeps the photo only inside such a route.
_ROUTE = contextvars.ContextVar("debug_store_route", default=None)
# What received() wrote for the current request: (store, day, ident, record).
_KEPT = contextvars.ContextVar("debug_store_kept", default=None)

# Error messages are cut to this length in a record.
DETAIL_MAX = 500

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

    def begin(self, route, raw, lang=None, now=None):
        """Keep the photo and a "started" record; return what finish() needs.

        None when nothing could be written (logged; the scan carries on).
        """
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
            "outcome": "started",
        }
        try:
            os.makedirs(day, mode=0o700, exist_ok=True)
            _write(os.path.join(day, f"{ident}.{ext}"), raw)
            _replace(os.path.join(day, f"{ident}.json"), record)
        except (OSError, TypeError, ValueError) as exc:
            log.warning("debug store: could not keep %s: %s", ident, exc)
            return None
        return (day, ident, record)

    def finish(self, kept, outcome, now=None, **fields):
        """Rewrite the record with how the request ended."""
        day, ident, record = kept
        now = now or datetime.now(timezone.utc)
        done = dict(record, outcome=outcome, **fields)
        done["finished_at"] = now.isoformat(timespec="seconds")
        try:
            _replace(os.path.join(day, f"{ident}.json"), done)
        except (OSError, TypeError, ValueError) as exc:
            log.warning("debug store: could not finish %s: %s", ident, exc)
            return None
        return ident


def _write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


STORE = DebugStore.from_env()


def _replace(path, record):
    """Write a record whole: a reader never sees half of it."""
    data = json.dumps(record, ensure_ascii=False, default=str).encode()
    tmp = f"{path}.tmp"
    _write(tmp, data)
    os.replace(tmp, path)


def received(raw):
    """Keep the uploaded photo now, before the scan can fail or crash.

    Does nothing when off, or outside an upload route keeps() wraps.
    """
    route = _ROUTE.get()
    if not STORE.enabled or route is None or _KEPT.get() is not None:
        return
    name, lang = route
    kept = STORE.begin(name, raw, lang)
    if kept is not None:
        _KEPT.set((STORE, *kept))


def _response_body(result):
    if isinstance(result, Response):
        try:
            return json.loads(result.body)
        except (ValueError, AttributeError):
            return None
    return jsonable_encoder(result)


def _error(exc):
    """("refused" or "failed", fields) for an exception, cut to size."""
    if isinstance(exc, HTTPException):
        return "refused", {
            "error": {
                "status": exc.status_code,
                "detail": str(exc.detail)[:DETAIL_MAX],
            }
        }
    return "failed", {
        "error": {
            "type": type(exc).__name__,
            "detail": str(exc)[:DETAIL_MAX],
        }
    }


def keeps(route):
    """Decorate an upload route so its photo and outcome are kept when on."""

    def wrap(endpoint):
        @functools.wraps(endpoint)
        async def run(*args, **kwargs):
            if not STORE.enabled:
                return await endpoint(*args, **kwargs)
            route_token = _ROUTE.set((route, kwargs.get("lang")))
            kept_token = _KEPT.set(None)
            try:
                try:
                    result = await endpoint(*args, **kwargs)
                except Exception as exc:  # pylint: disable=broad-except
                    await _finish(*_error(exc))
                    raise
                status = getattr(result, "status_code", 200)
                await _finish(
                    "answered",
                    {"status": status, "response": _response_body(result)},
                )
                return result
            finally:
                _KEPT.reset(kept_token)
                _ROUTE.reset(route_token)

        return run

    return wrap


async def _finish(outcome, fields):
    kept = _KEPT.get()
    if kept is None:
        return
    store, day, ident, record = kept
    try:
        await asyncio.to_thread(
            store.finish, (day, ident, record), outcome, **fields
        )
    except Exception as exc:  # pylint: disable=broad-except
        # Debugging must never cost a family their report.
        log.warning("debug store: %s not finished: %s", ident, exc)
