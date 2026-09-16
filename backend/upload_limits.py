# SPDX-License-Identifier: AGPL-3.0-only
"""Bound multipart bodies before FastAPI spools or decodes uploads."""

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class UploadBodyLimit:
    """Count actual streamed bytes, including requests without Content-Length."""

    def __init__(self, app, max_bytes=32 * 1024 * 1024):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    raise HTTPException(413, "Request exceeds 32 MiB")
            return message

        for key, value in scope.get("headers", []):
            if key == b"content-length":
                try:
                    oversized = int(value) > self.max_bytes
                except ValueError:
                    oversized = True
                if oversized:
                    response = JSONResponse(
                        {"detail": "Request exceeds 32 MiB"},
                        status_code=413,
                        headers={"Cache-Control": "no-store"},
                    )
                    return await response(scope, receive, send)
        return await self.app(scope, bounded_receive, send)
