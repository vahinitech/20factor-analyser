# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies
# Combined analyser + OCR service:
# - Reuses PP-OCRv5 endpoints from ppocr-server.py
# - Serves analyser static files under /analyser

from importlib import util
from pathlib import Path

from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

ROOT_DIR = Path(__file__).resolve().parents[2]
PP_OCR_SERVER_PATH = Path(__file__).resolve().parent / "ppocr-server.py"

spec = util.spec_from_file_location("ppocr_server", str(PP_OCR_SERVER_PATH))
if spec is None or spec.loader is None:
    raise RuntimeError("Failed to load ppocr-server.py")
module = util.module_from_spec(spec)
spec.loader.exec_module(module)
app = module.app


@app.middleware("http")
async def _revalidate_analyser_assets(request, call_next):
    """Force the browser to REVALIDATE analyser assets on every load instead of
    silently serving a long-cached copy. StaticFiles sends ETag/Last-Modified,
    so this is cheap (304 when unchanged) but guarantees a fresh engine bundle
    after any rebuild — preventing 'the page won't load' from a stale/broken
    cached bundle."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/analyser"):
        if path.endswith((".html", "/")) or path == "/analyser":
            response.headers["Cache-Control"] = "no-store"
        else:
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


ANALYSER_DIR = ROOT_DIR / "analyser"
if not ANALYSER_DIR.exists():
    raise RuntimeError(f"Analyser directory not found: {ANALYSER_DIR}")

app.mount("/analyser", StaticFiles(directory=str(ANALYSER_DIR), html=False), name="analyser")


@app.get("/analyser", include_in_schema=False)
def analyser_root():
    return RedirectResponse(url="/analyser/Vahini%20Analyser.html", status_code=302)


@app.get("/ocr/health", include_in_schema=False)
def ocr_health_alias():
    # Keep backward compatibility with existing gateway health probes.
    return module.health()


if __name__ == "__main__":
    import os

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8868")))
