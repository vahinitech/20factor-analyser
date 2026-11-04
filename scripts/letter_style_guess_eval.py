# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""How the letter-style guess does on pages drawn in each style's font.

A first measure of the "Not sure" guess (#350) until real handwriting per
family exists (#342). Each page is five lines set in a Playwrite face, the
fonts the registry names, plus a print control; the page runs through the
real scorer (scoring.build_analysis) with the lines as the reader would
give them, and the guess it attaches is compared with the style the font
stands for. Font-drawn letters are tidier than any child's, so this shows
whether the guess's rules fit each style, not how often it is right on a
real page.

    python scripts/letter_style_guess_eval.py <folder of TTF files>

The folder holds US.ttf, IN.ttf, AR.ttf, GB.ttf, AUVIC.ttf, FR.ttf,
LA.ttf, VA.ttf, SAS.ttf
(Google Fonts' ofl/playwrite* files, OFL) and a print font named
PRINT.ttf. Nothing is downloaded or written.
"""

import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# pylint: disable-next=wrong-import-position
import scoring  # noqa: E402

LINES = [
    "my mother writes a letter home",
    "seven quick brown foxes jump over",
    "we planted beans in the garden",
    "the river flows past our village",
    "please bring your notebook today",
]
# Font file stem -> the style ids it stands for (any of them is right).
FONTS = {
    "US": {"looped"},
    "IN": {"looped"},
    "AR": {"vertical", "straight-india"},
    "GB": {"joined-breaks"},
    "AUVIC": {"joined-breaks-au"},
    "FR": {"french"},
    "LA": {"german-la"},
    "VA": {"german-va"},
    "SAS": {"german-sas"},
    "PRINT": {"print"},
}
SIZES = (34, 44, 56)


def page(font_path, size):
    """A white page with LINES set in the font, and the reader's lines."""
    font = ImageFont.truetype(font_path, size)
    # Google's files are variable fonts that open at their lightest
    # weight, a hairline no pencil draws; 400 is a written line.
    try:
        font.set_variation_by_axes([400])
    except (OSError, ValueError):
        pass  # a static font (the print control)
    # Room between lines so one line's loops do not reach the next
    # line's crop (the French face's loops are tallest).
    gap = int(size * 3.2)
    img = Image.new("L", (1600, 120 + gap * len(LINES)), 255)
    draw = ImageDraw.Draw(img)
    lines = []
    for i, text in enumerate(LINES):
        x, y = 60, 60 + i * gap
        # Word by word, with the gap a hand leaves (about two small-letter
        # heights): a font's own space is narrower than the style check's
        # word gap, and would make each line one long word.
        cx, right, top, bottom = x, x, None, None
        for word in text.split():
            draw.text((cx, y), word, font=font, fill=20)
            l, t, r, b = draw.textbbox((cx, y), word, font=font)
            top = t if top is None else min(top, t)
            bottom = b if bottom is None else max(bottom, b)
            right = r
            cx = r + int(size * 0.9)
        l, t, r, b = x, top, right, bottom
        box = [float(l), float(t), float(r - l), float(b - t)]
        lines.append(
            {
                "text": text,
                "score": 0.9,
                "box": box,
                "poly": [[l, t], [r, t], [r, b], [l, b]],
                "lang": "en",
                "printed_hint": False,
            }
        )
    return np.asarray(img.convert("RGB")), lines


def main(folder):
    rows = []
    for stem, want in FONTS.items():
        path = os.path.join(folder, f"{stem}.ttf")
        for size in SIZES:
            arr, lines = page(path, size)
            prof = scoring.build_analysis(arr, lines, {}).style_profile
            g = prof.get("letterStyle") or {}
            rows.append(
                (
                    stem,
                    size,
                    prof.get("verdict", "-"),
                    (g.get("basis") or {}).get("leanDeg"),
                    g.get("style", "-"),
                    g.get("style") in want,
                    bool(want & set(g.get("candidates") or [])),
                )
            )
    print("font  size  writing  lean  guess            first  listed")
    for r in rows:
        print(
            f"{r[0]:<5} {r[1]:>4}  {r[2]:<8} {str(r[3]):>5}  {r[4]:<16} "
            f"{'yes' if r[5] else 'no':<5}  {'yes' if r[6] else 'no'}"
        )
    for stem in FONTS:
        mine = [r for r in rows if r[0] == stem]
        print(
            f"{stem}: first {sum(r[5] for r in mine)}/{len(mine)}, "
            f"listed {sum(r[6] for r in mine)}/{len(mine)}"
        )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: letter_style_guess_eval.py <font folder>")
    main(sys.argv[1])
