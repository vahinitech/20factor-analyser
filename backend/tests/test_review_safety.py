# SPDX-License-Identifier: AGPL-3.0-only
"""Upload and credential failure regressions from PR review."""

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, File, UploadFile
from fastapi.testclient import TestClient
from PIL import Image
import computer_vision as cv
import entitlements
import subscription_admin
from upload_limits import MAX_UPLOAD_BYTES, UploadBodyLimit


class ReviewSafetyTests(unittest.TestCase):
    def test_stream_limit_without_content_length(self):
        app = FastAPI()
        app.add_middleware(UploadBodyLimit, max_bytes=128)

        @app.post("/upload")
        async def upload(image: UploadFile = File(...)):
            return {"bytes": len(await image.read())}

        body = (
            b'--abc\r\nContent-Disposition: form-data; name="image"; '
            b'filename="sample.png"\r\n\r\n' + b"x" * 200 + b"\r\n--abc--\r\n"
        )
        with TestClient(app) as client:
            response = client.post(
                "/upload",
                content=iter([body[:100], body[100:]]),
                headers={"Content-Type": "multipart/form-data; boundary=abc"},
            )
            self.assertEqual(response.status_code, 413)
            self.assertEqual(
                client.post("/upload", content=body).status_code, 413
            )

    def test_one_page_limits(self):
        """A page photo is at most 2600 px JPEG from the website: 5 MiB per
        file and 6 MiB per request, refused before anything is decoded."""
        self.assertEqual(MAX_UPLOAD_BYTES, 5 * 1024 * 1024)
        app = FastAPI()
        app.add_middleware(UploadBodyLimit)

        @app.post("/upload")
        async def upload(image: UploadFile = File(...)):
            return {"bytes": len(await image.read())}

        def body(size):
            return (
                b'--abc\r\nContent-Disposition: form-data; name="image"; '
                b'filename="page.jpg"\r\n\r\n'
                + b"x" * size
                + b"\r\n--abc--\r\n"
            )

        headers = {"Content-Type": "multipart/form-data; boundary=abc"}
        with TestClient(app) as client:
            ok = client.post(
                "/upload", content=body(2 * 1024 * 1024), headers=headers
            )
            self.assertEqual(ok.status_code, 200)
            big = client.post(
                "/upload", content=body(7 * 1024 * 1024), headers=headers
            )
            self.assertEqual(big.status_code, 413)
            self.assertIn("6 MiB", big.json()["detail"])

    def test_pixel_bound_precedes_color_conversion(self):
        image = Mock(size=(6000, 5000))
        image.__enter__ = Mock(return_value=image)
        image.__exit__ = Mock(return_value=False)
        with patch.object(cv.Image, "open", return_value=image):
            with self.assertRaises(cv.UploadLimitError):
                cv.decode_image(b"image")
        image.convert.assert_not_called()
        buffer = io.BytesIO()
        Image.new("RGB", (10, 10)).save(buffer, format="PNG")
        self.assertEqual(cv.to_numpy(buffer.getvalue()).shape, (10, 10, 3))

    def test_pdf_dimensions_checked_before_render(self):
        page = Mock()
        page.get_size.return_value = (100000, 100000)
        pdf = Mock()
        pdf.__len__ = Mock(return_value=1)
        pdf.__getitem__ = Mock(return_value=page)
        module = Mock()
        module.PdfDocument.return_value = pdf
        with patch.dict(sys.modules, {"pypdfium2": module}):
            with self.assertRaises(cv.UploadLimitError):
                cv.decode_image(b"%PDF")
        page.render.assert_not_called()
        pdf.close.assert_called_once()

    def test_failed_secret_delivery_revokes_key_and_removes_file(self):
        with tempfile.TemporaryDirectory() as folder:
            db = folder + "/ledger.sqlite"
            target = folder + "/key.txt"
            entitlements.initialize(db)
            customer = entitlements.create_customer(db)
            with patch.object(
                subscription_admin.os,
                "fsync",
                side_effect=OSError("disk full"),
            ):
                with self.assertRaises(OSError):
                    subscription_admin.write_customer_key(db, customer, target)
            self.assertFalse(os.path.exists(target))
            with entitlements.connect(db) as conn:
                self.assertEqual(
                    [
                        row[0]
                        for row in conn.execute("SELECT revoked FROM api_keys")
                    ],
                    [1],
                )
            with patch.object(
                subscription_admin,
                "issue_key",
                side_effect=ValueError("failed"),
            ):
                with self.assertRaises(ValueError):
                    subscription_admin.write_customer_key(db, customer, target)
            self.assertFalse(os.path.exists(target))
            Path(target).write_text("existing")
            with self.assertRaises(FileExistsError):
                subscription_admin.write_customer_key(db, customer, target)
            self.assertEqual(Path(target).read_text(), "existing")
