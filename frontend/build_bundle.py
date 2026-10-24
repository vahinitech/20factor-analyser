# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# build_bundle.py — reproduce frontend/scripts/core/engine.bundle.js from src/.
#
# The browser only loads the packed bundle; the readable engine sources live in
# frontend/src/. This script concatenates the sources in the documented order
# (docs/14-build.md), base64-encodes the UTF-8 bytes, and wraps them in the same
# self-decoding loader the existing bundle uses:
#
#     (0, eval)(decodeURIComponent(escape(atob(_v))));
#
# which is the inverse of  btoa(unescape(encodeURIComponent(src))), i.e. the
# base64 of the UTF-8 encoding of the concatenated source. Run after editing any
# file under frontend/src/:
#
#     python frontend/build_bundle.py
#
# Then open  frontend/analyser.html?demo=report  and confirm a report
# renders with no console errors.

import base64
import glob
import hashlib
import html
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Order matters: app.js references globals defined by earlier modules.
# Scoring + CV now run server-side (server/app.py); the browser bundle is
# recognition-client + report rendering only.
SOURCES = [
    "src/engine/compact-client.js",
    "src/engine/account.js",
    "src/engine/ocr.js",
    "src/engine/imu.js",
    "src/engine/forecast.js",
    "src/engine/craft.js",
    "src/engine/narrate.js",
    "src/report/worksheet-catalog.js",
    "src/report/worksheets.js",
    "src/report/strings/en.js",
    "src/report/strings/en-us.js",
    "src/report/strings/te.js",
    "src/report/i18n.js",
    "src/report/progress.js",
    "src/report/practice-select.js",
    "src/report/report-render.js",
    "src/report/report-share.js",
    "src/app/scan-sweep.js",
    "src/app/app.js",
    "src/app/share.js",
]

OUT = os.path.join(HERE, "scripts", "core", "engine.bundle.js")

# Local scripts and stylesheets the pages load. Cloudflare and browsers keep
# them for 30 days (vahini-web nginx), so an unversioned URL serves the old
# file after a release while the HTML is already new. Each reference carries
# ?v=<content hash>; a changed file gets a new URL.
# scripts/vendor holds third-party files (sources.json there); the PDF
# libraries in it are named in a <template id="pdf-libs"> and loaded only
# when "Share PDF on WhatsApp" is pressed, so their stamps live there.
ASSET_REF = re.compile(
    r'((?:src|href)=")((?:scripts/core|scripts/vendor|styles)/[\w.-]+\.'
    r'(?:js|css))(?:\?v=[0-9a-f]*)?(")'
)


# "What's new" on the check page (owner, 2026-10-24): one line at the top
# showing the latest changes in turn, the newest first, one every 5 s
# (scripts/core/whats-new.js), over the full list. The lines are written
# for parents and teachers in whats-new.json, each naming the changelog
# fragments it comes from; tests/whats-new.test.mjs holds the rules. Like
# the stamps, the list is written into the page by --stamp and never
# committed, so two PRs never conflict on it.
WHATS_NEW = os.path.join(HERE, "whats-new.json")
WHATS_NEW_PAGE = os.path.join(HERE, "analyser.html")
WHATS_NEW_SHOWN = 10
WHATS_NEW_REGION = re.compile(
    r"(<!-- whats-new:begin[^>]*-->)[\s\S]*?(<!-- whats-new:end -->)"
)
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def _day(date):
    year, month, day = date.split("-")
    return f"{int(day)} {MONTHS[int(month) - 1]}", year


def _whats_new_item(item):
    day, _ = _day(item["date"])
    return (
        f'<time datetime="{item["date"]}">{day}</time> '
        f'<span>{html.escape(item["text"], quote=False)}</span>'
    )


def whats_new_html():
    """The check page's What's new block, from whats-new.json."""
    with open(WHATS_NEW, "r", encoding="utf-8") as f:
        items = json.load(f)["items"][:WHATS_NEW_SHOWN]
    day, year = _day(items[0]["date"])
    rows = "".join(
        f"\n        <li>{_whats_new_item(item)}</li>" for item in items
    )
    return (
        '\n    <details class="whats-new" id="whats-new">'
        '\n      <summary><span class="wn-dot" aria-hidden="true"></span>'
        f'<span class="wn-line">{_whats_new_item(items[0])}</span>'
        f'<span class="wn-count">1 of {len(items)}</span>'
        '<span class="wn-all">What\'s new</span></summary>'
        f'\n      <div class="wn-panel"><p class="wn-head">Updated {day}'
        f" {year}. The latest changes to the free check, newest first.</p>"
        f'\n      <ol class="wn-list">{rows}\n      </ol></div>'
        "\n    </details>\n    "
    )


def fill_whats_new(fill):
    """Write the What's new block into analyser.html, or empty it (the
    committed form). Returns True when the page changed."""
    with open(WHATS_NEW_PAGE, "r", encoding="utf-8") as f:
        text = f.read()
    body = whats_new_html() if fill else ""
    out = WHATS_NEW_REGION.sub(lambda m: m.group(1) + body + m.group(2), text)
    if out != text:
        with open(WHATS_NEW_PAGE, "w", encoding="utf-8", newline="\n") as f:
            f.write(out)
    return out != text


def practice_source():
    """The practice catalogue for reports made without a server catalogue
    (the sample report). One source: backend/report/practice_catalog.py, which
    validates itself on import and uses only the standard library."""
    path = os.path.join(
        HERE, os.pardir, "backend", "report", "practice_catalog.py"
    )
    spec = importlib.util.spec_from_file_location("practice_catalog", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = json.dumps(module.browser_catalog(), ensure_ascii=False)
    return (
        "/* Generated from backend/report/practice_catalog.py by build_bundle.py */"
        f"\nwindow.VahiniPracticeCatalog = {data};\n"
    )


def build():
    parts = [practice_source()]
    for rel in SOURCES:
        path = os.path.join(HERE, *rel.split("/"))
        with open(path, "r", encoding="utf-8") as f:
            parts.append(f.read())
    # A newline between files prevents a trailing // comment in one file from
    # swallowing the first line of the next.
    combined = "\n;\n".join(parts)
    b64 = base64.b64encode(combined.encode("utf-8")).decode("ascii")
    loader = (
        "/* Vahini engine - packed build. Generated by build_bundle.py, do not edit by hand. */\n"
        "(function(){ try {\n"
        f'  var _v = "{b64}";\n'
        "  (0, eval)(decodeURIComponent(escape(atob(_v))));\n"
        '} catch (e) { console.error("engine load failed", e); } })();\n'
    )
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(loader)
    return len(combined), len(b64)


def file_hash(rel):
    with open(os.path.join(HERE, *rel.split("/")), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:10]


# An @import inside a stylesheet is cached for 30 days like the sheet
# itself, but the page's stamp only covers the importing file: on stage,
# report.css arrived new while Cloudflare kept serving the old
# report-fonts.css it imports, without the Telugu font (2026-10-11).
CSS_IMPORT = re.compile(
    r"(@import\s+url\(['\"]?\./)([\w.-]+\.css)(?:\?v=[0-9a-f]*)?(['\"]?\))"
)


def _rewrite_imports(stamp):
    changed = []
    for sheet in sorted(glob.glob(os.path.join(HERE, "styles", "*.css"))):
        with open(sheet, "r", encoding="utf-8") as f:
            text = f.read()
        out = CSS_IMPORT.sub(
            lambda m: m.group(1)
            + m.group(2)
            + (f"?v={file_hash('styles/' + m.group(2))}" if stamp else "")
            + m.group(3),
            text,
        )
        if out != text:
            with open(sheet, "w", encoding="utf-8", newline="\n") as f:
                f.write(out)
            changed.append("styles/" + os.path.basename(sheet))
    return changed


def stamp_pages():
    """Point every local css/js reference in frontend/*.html at ?v=<hash>,
    after stamping the @import URLs inside the stylesheets, so a sheet's
    own stamp also changes when a file it imports changes."""
    changed = _rewrite_imports(True)
    if fill_whats_new(True):
        changed.append("analyser.html (what's new)")
    for page in sorted(glob.glob(os.path.join(HERE, "*.html"))):
        with open(page, "r", encoding="utf-8") as f:
            text = f.read()
        stamped = ASSET_REF.sub(
            lambda m: f"{m.group(1)}{m.group(2)}?v={file_hash(m.group(2))}"
            f"{m.group(3)}",
            text,
        )
        if stamped != text:
            with open(page, "w", encoding="utf-8", newline="\n") as f:
                f.write(stamped)
            changed.append(os.path.basename(page))
    return changed


def strip_pages():
    """Remove every ?v= stamp from frontend/*.html and the stylesheets'
    @import URLs (the committed form)."""
    changed = _rewrite_imports(False)
    if fill_whats_new(False):
        changed.append("analyser.html (what's new)")
    for page in sorted(glob.glob(os.path.join(HERE, "*.html"))):
        with open(page, "r", encoding="utf-8") as f:
            text = f.read()
        plain = ASSET_REF.sub(
            lambda m: m.group(1) + m.group(2) + m.group(3), text
        )
        if plain != text:
            with open(page, "w", encoding="utf-8", newline="\n") as f:
                f.write(plain)
            changed.append(os.path.basename(page))
    return changed


if __name__ == "__main__":
    # The bundle and the ?v= stamps are build output, never committed: every
    # frontend PR changed both, so any two open PRs conflicted on them. The
    # image build (deployment/Dockerfile) and CI run this; so does anyone
    # serving frontend/ straight from a checkout.
    #   python frontend/build_bundle.py           build engine.bundle.js
    #   python frontend/build_bundle.py --stamp   ...and stamp the pages
    #   python frontend/build_bundle.py --strip   remove stamps from pages
    #   python frontend/build_bundle.py --whats-new   print the What's new block
    if "--whats-new" in sys.argv:
        print(whats_new_html())
        sys.exit(0)
    if "--strip" in sys.argv:
        for name in strip_pages():
            print(f"[build] removed asset stamps from {name}")
        sys.exit(0)
    src_len, b64_len = build()
    print(
        f"[build] packed {len(SOURCES)} sources and the practice catalogue: {src_len} src chars -> {b64_len} base64 chars"
    )
    print(f"[build] wrote {OUT}")
    if "--stamp" in sys.argv:
        for name in stamp_pages():
            print(f"[build] stamped asset URLs in {name}")
