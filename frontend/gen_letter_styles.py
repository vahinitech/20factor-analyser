# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The letter-style picker on the check page, from the registry.

The owner decided on 2026-11-03 (#346) that the visitor picks the letter
style taught at school before Analyse, with "Not sure" chosen until they
pick. The styles, their names, the line under each and whether they show
at once or under "More styles" come from backend/styles/letter_styles.json
(#350); this writes them into analyser.html between the letter-styles
markers, so crawlers read the names without running a script.

Each joined style's name is drawn in its own Playwrite face, never in print
or Caveat (docs/12-report-rules.md). The faces are cut down to the letters
of the names they draw, so the page loads a few kilobytes per face instead
of the whole font, and self-hosted beside the report fonts with their
licence and source in assets/fonts/sources.json.

    python frontend/gen_letter_styles.py            rewrite the region and css
    python frontend/gen_letter_styles.py --check    fail if either is stale
    python frontend/gen_letter_styles.py --fonts <folder of Google Fonts'
        ofl/playwrite*/ files>                      cut the faces again

Cutting the faces needs fontTools and brotli (pip install fonttools
brotli); nothing else here does, and the page never needs them.
"""

import hashlib
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TABLE = os.path.join(ROOT, "backend", "styles", "letter_styles.json")
PAGE = os.path.join(HERE, "analyser.html")
CSS = os.path.join(HERE, "styles", "letter-style-fonts.css")
FONTS = os.path.join(HERE, "assets", "fonts")
SOURCES = os.path.join(FONTS, "sources.json")
REGION = re.compile(
    r"(<!-- letter-styles:begin[^>]*-->)[\s\S]*?(<!-- letter-styles:end -->)"
)
GOOGLE = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
LICENCE = "playwrite-OFL.txt"
# The weight the faces are cut at: a written line, not the hairline the
# variable fonts open at.
WEIGHT = 400


def styles():
    with open(TABLE, encoding="utf-8") as f:
        return json.load(f)["styles"]


def slug(font):
    """'Playwrite US Trad' -> 'playwrite-us-trad'."""
    return re.sub(r"[^a-z0-9]+", "-", font.lower()).strip("-")


def google_dir(font):
    """'Playwrite US Trad' -> 'playwriteustrad' (Google Fonts' folder)."""
    return re.sub(r"[^a-z0-9]", "", font.lower())


def faces():
    """{font: text it draws}, for every joined style's font."""
    out = {}
    for s in styles():
        if s["font"]:
            out[s["font"]] = out.get(s["font"], "") + s["label"]
    return out


def _option(s):
    name_style = (
        f' style="font-family:\'{s["font"]}\',cursive"' if s["font"] else ""
    )
    kind = " ls-print" if not s["font"] else ""
    return (
        f'<label class="ls-opt{kind}"><input type="radio" '
        f'name="letter-style" value="{s["id"]}">'
        f'<span class="ls-name"{name_style}>{html.escape(s["label"])}'
        f'</span><span class="ls-where">{html.escape(s["where"])}</span>'
        "</label>"
    )


def picker_html():
    """The picker, as the region holds it."""
    first = [s for s in styles() if s["picker"] == "first"]
    more = [s for s in styles() if s["picker"] == "more"]
    pad = "\n        "
    return (
        '\n    <fieldset class="letter-style" id="letter-style">'
        "\n      <legend>Letter style taught at school</legend>"
        '\n      <div class="ls-opts">'
        f"{pad}"
        '<label class="ls-opt ls-print"><input type="radio" '
        'name="letter-style" value="unsure" checked>'
        '<span class="ls-name">Not sure</span>'
        '<span class="ls-where">We find it from the page</span></label>'
        + "".join(pad + _option(s) for s in first)
        + "\n      </div>"
        '\n      <details class="ls-more"><summary>More styles</summary>'
        '<div class="ls-opts">'
        + "".join(pad + _option(s) for s in more)
        + "\n      </div></details>"
        '\n      <p class="ls-note">The style changes the tips and practice'
        " sheets in your report, never the score.</p>"
        "\n    </fieldset>\n    "
    )


def css_text():
    rules = "".join(
        f"@font-face {{font-family:'{font}';"
        f"src:url('../assets/fonts/{slug(font)}.woff2') format('woff2');"
        f"font-weight:{WEIGHT};font-display:swap;}}\n"
        for font in sorted(faces())
    )
    return (
        "/* SPDX-License-Identifier: AGPL-3.0-only\n"
        "   Written by frontend/gen_letter_styles.py from the letter-style\n"
        "   registry; do not edit. Each face holds only the letters of the\n"
        "   style names it draws on the check page. */\n" + rules
    )


def _page_with(region):
    with open(PAGE, encoding="utf-8") as f:
        text = f.read()
    if not REGION.search(text):
        raise SystemExit("analyser.html has no letter-styles region")
    return text, REGION.sub(lambda m: m.group(1) + region + m.group(2), text)


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def problems():
    """What is stale or missing, as sentences."""
    out = []
    text, want = _page_with(picker_html())
    if text != want:
        out.append("the picker in analyser.html is stale")
    css = ""
    if os.path.exists(CSS):
        with open(CSS, encoding="utf-8") as f:
            css = f.read()
    if css != css_text():
        out.append("styles/letter-style-fonts.css is stale")
    with open(SOURCES, encoding="utf-8") as f:
        listed = {e["file"]: e for e in json.load(f)}
    for name in [slug(font) + ".woff2" for font in faces()] + [LICENCE]:
        path = os.path.join(FONTS, name)
        if not os.path.exists(path):
            out.append(f"assets/fonts/{name} is missing (run with --fonts)")
        elif name not in listed or listed[name]["sha256"] != _sha(path):
            out.append(f"assets/fonts/{name} is not listed in sources.json")
    return out


def write():
    _text, want = _page_with(picker_html())
    with open(PAGE, "w", encoding="utf-8", newline="\n") as f:
        f.write(want)
    with open(CSS, "w", encoding="utf-8", newline="\n") as f:
        f.write(css_text())


def cut_fonts(folder):
    """Cut each face to the letters it draws, at WEIGHT, and list the
    results in sources.json beside the original's source and hash."""
    # pylint: disable=import-outside-toplevel
    from fontTools import subset
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    with open(SOURCES, encoding="utf-8") as f:
        sources = json.load(f)
    keep = {slug(font) + ".woff2" for font in faces()} | {LICENCE}
    sources = [
        e
        for e in sources
        if not e["file"].startswith("playwrite-") or e["file"] in keep
    ]
    by_file = {e["file"]: e for e in sources}
    for font, text in sorted(faces().items()):
        name = google_dir(font)
        src = os.path.join(folder, name + ".ttf")
        tt = instancer.instantiateVariableFont(TTFont(src), {"wght": WEIGHT})
        opts = subset.Options()
        opts.flavor = "woff2"
        opts.name_IDs = ["*"]
        opts.notdef_outline = True
        sub = subset.Subsetter(opts)
        sub.populate(text=text + " ")
        sub.subset(tt)
        out = os.path.join(FONTS, slug(font) + ".woff2")
        tt.flavor = "woff2"
        tt.save(out)
        by_file[slug(font) + ".woff2"] = {
            "file": slug(font) + ".woff2",
            "source": GOOGLE + name + "/" + _google_file(font),
            "sha256": _sha(out),
            "source_sha256": _sha(src),
            "license": "OFL-1.1",
            "note": (
                f"Cut to the letters of the style names it draws, at weight "
                f"{WEIGHT}, by frontend/gen_letter_styles.py --fonts."
            ),
        }
    lic = os.path.join(FONTS, LICENCE)
    with open(os.path.join(folder, "OFL.txt"), "rb") as f:
        body = f.read()
    with open(lic, "wb") as f:
        f.write(body)
    by_file[LICENCE] = {
        "file": LICENCE,
        "source": GOOGLE + "playwriteustrad/OFL.txt",
        "sha256": _sha(lic),
        "license": "OFL-1.1",
    }
    with open(SOURCES, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(list(by_file.values()), indent=2) + "\n")


def _google_file(font):
    """Google Fonts' file name, URL-encoded: PlaywriteUSTrad%5Bwght%5D.ttf."""
    return (
        "Playwrite"
        + google_dir(font)[9:].upper().replace("TRAD", "Trad")
        + "%5Bwght%5D.ttf"
    )


if __name__ == "__main__":
    if "--fonts" in sys.argv:
        cut_fonts(sys.argv[sys.argv.index("--fonts") + 1])
        write()
    elif "--check" in sys.argv:
        found = problems()
        if found:
            raise SystemExit("; ".join(found))
        print("letter-style picker ok")
    else:
        write()
