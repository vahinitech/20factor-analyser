# SPDX-License-Identifier: AGPL-3.0-only
"""The image attack surface (owner decision, 2026-10-09).

Only JPEG, PNG and WebP are decoded (computer_vision.IMAGE_FORMATS); every
other format Pillow knows is refused before its decoder runs, through the
real endpoint as a 422. The image runs as an ordinary user, and Pillow, the
library that parses visitors' files, is pinned to an exact version.
"""

import importlib.util
import io
import os
import re
import sys
import unittest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPO = os.path.dirname(SERVER_DIR)
sys.path.insert(0, SERVER_DIR)

from PIL import (  # noqa: E402  pylint: disable=wrong-import-position
    Image,
    UnidentifiedImageError,
)
import computer_vision as cv  # noqa: E402  pylint: disable=wrong-import-position

# White-box: the endpoint test swaps the server's daily limit off.
# pylint: disable=protected-access


def encoded(fmt, mode="RGB"):
    img = Image.new(mode, (64, 48), "white")
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


ALLOWED = ("JPEG", "PNG", "WEBP")
# Formats Pillow can both write and open: each one decoded before this
# change, and each one's decoder is attack surface the analyser never needs.
REFUSED = (
    ("BMP", "RGB"),
    ("GIF", "P"),
    ("TIFF", "RGB"),
    ("ICO", "RGB"),
    ("PPM", "RGB"),
    ("TGA", "RGB"),
    ("PCX", "RGB"),
    ("SGI", "RGB"),
    ("DDS", "RGBA"),
    ("IM", "RGB"),
    ("SPIDER", "F"),
)


class ImageFormatTests(unittest.TestCase):
    def test_only_jpeg_png_and_webp_are_decoded(self):
        self.assertEqual(cv.IMAGE_FORMATS, ALLOWED)
        for fmt in ALLOWED:
            arr = cv.to_numpy(encoded(fmt))
            self.assertEqual(arr.shape, (48, 64, 3), fmt)

    def test_every_other_format_is_refused_before_decoding(self):
        for fmt, mode in REFUSED:
            raw = encoded(fmt, mode)
            with Image.open(io.BytesIO(raw)) as probe:  # Pillow would open it
                self.assertEqual(probe.format, fmt)
            with self.assertRaises(UnidentifiedImageError, msg=fmt):
                cv.decode_image(raw)

    def test_a_disguised_file_is_refused(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>'
        for raw in (svg, b"<?php system($_GET[0]); ?>", b"\x89PNG broken"):
            with self.assertRaises((UnidentifiedImageError, OSError)):
                cv.decode_image(raw)

    def test_the_endpoint_answers_422(self):
        spec = importlib.util.spec_from_file_location(
            "ppocr_server_formats", os.path.join(SERVER_DIR, "ppocr-server.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        from fastapi.testclient import (  # pylint: disable=import-outside-toplevel
            TestClient,
        )

        client = TestClient(mod.app)
        for fmt, mode in REFUSED[:4]:
            res = client.post(
                "/ocr",
                files={"image": ("page.png", encoded(fmt, mode), "image/png")},
            )
            self.assertEqual(res.status_code, 422, fmt)
            self.assertEqual(
                res.json()["detail"], "Upload a valid image or PDF."
            )


class HardeningTests(unittest.TestCase):
    def test_the_image_runs_as_an_ordinary_user(self):
        with open(
            os.path.join(REPO, "deployment", "Dockerfile"), encoding="utf-8"
        ) as f:
            docker = f.read()
        users = re.findall(r"^USER\s+(\S+)", docker, re.M)
        self.assertEqual(users, ["10001:10001"], "one USER line, not root")
        after = docker[docker.index("USER 10001:10001") :]
        self.assertNotRegex(after, r"(?m)^RUN ", "nothing runs as root after")
        self.assertIn("PYTHONDONTWRITEBYTECODE=1", docker)
        self.assertIn("chown -R 10001:10001 /opt/paddle-models", docker)

    def test_pillow_is_pinned_exactly(self):
        with open(
            os.path.join(SERVER_DIR, "requirements-core.txt"), encoding="utf-8"
        ) as f:
            reqs = f.read()
        self.assertRegex(reqs, r"(?m)^pillow==\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
