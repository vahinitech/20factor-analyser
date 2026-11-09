# SPDX-License-Identifier: AGPL-3.0-only
"""Bound multipart bodies before FastAPI spools or decodes uploads.

One page photo is all an upload ever is: the website sends at most 2600 px
and the Android app 2200 px, both re-encoded as JPEG (1.8 MB was the largest
of 127 real uploads, measured 2026-10-09). 5 MiB per file leaves room for a
direct API caller's single-page PDF; anything bigger is refused before it is
spooled or decoded."""

from starlette.exceptions import HTTPException

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_REQUEST_BYTES = (
    6 * 1024 * 1024
)  # the upload plus multipart framing and fields
from starlette.responses import JSONResponse


class UploadBodyLimit:
    """Count actual streamed bytes, including requests without Content-Length."""

    def __init__(self, app, max_bytes=MAX_REQUEST_BYTES):
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
                    raise HTTPException(413, "Request exceeds 6 MiB")
            return message

        for key, value in scope.get("headers", []):
            if key == b"content-length":
                try:
                    oversized = int(value) > self.max_bytes
                except ValueError:
                    oversized = True
                if oversized:
                    response = JSONResponse(
                        {"detail": "Request exceeds 6 MiB"},
                        status_code=413,
                        headers={"Cache-Control": "no-store"},
                    )
                    return await response(scope, receive, send)
        return await self.app(scope, bounded_receive, send)
