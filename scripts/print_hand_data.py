# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Training and test lines for the print-or-handwriting line reader
(backend/reading/print_hand.py), written as one .npz.

Handwriting: UJI Pen Characters v2 (Prat, Castro, Llorens, Marzal and
Vilar, 2008, doi:10.24432/C5FG8S, CC BY 4.0). The 40 writers of its
published training split make the training lines; its 20 test writers
make the synthetic test lines. Letters are set into words with the
writer's own shapes, a little slant, size and baseline wobble, and
sometimes a joining stroke between letters.

Print: open-licence fonts from github.com/google/fonts at one commit,
each checked by SHA-256 (OFL, one Apache). Four fonts never train and
make the synthetic test lines. Fonts that imitate handwriting are on
both sides of that split, because a script font is print: two of the
committed sample pages are exactly that.

Both kinds go through the same photo effects (ink colour, pen or type
weight, ruled lines, light falling across the page, paper grain, blur,
rescaling, JPEG), so the reader cannot learn the drawing method.

Real test lines: every line PaddleOCR finds on the committed sample
pages, labelled by the page's description in
tests/fixtures/samples/README.md and the text rules in REAL_LABELS.
Needs the OCR models, so run it inside the analyser image:

    python scripts/print_hand_data.py --out lines.npz

Neither the data nor the fonts nor the lines are committed.
"""

import argparse
import hashlib
import os
import re
import sys
import urllib.request

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cv2  # noqa: E402  pylint: disable=wrong-import-position
import planted_pages  # noqa: E402  pylint: disable=wrong-import-position
from reading import (
    print_hand,
)  # noqa: E402  pylint: disable=wrong-import-position

FONTS_COMMIT = "66928797f271fed5ee428544e7229685e2d90127"
FONTS_URL = "https://raw.githubusercontent.com/google/fonts/{}/{}"
# path in google/fonts, SHA-256, split, kind
# pylint: disable=line-too-long
FONTS = [
    ("ofl/notoserif/NotoSerif%5Bwdth,wght%5D.ttf", "4d8e6761424656867019081a1a01336f3cb086982682698714054fc33f782713", "train", "type"),
    ("ofl/notosans/NotoSans%5Bwdth,wght%5D.ttf", "bfb7bb691513f12e734dc346c03a03f784912432d7e3fa8e56efcf906fe86b3d", "train", "type"),
    ("ofl/courierprime/CourierPrime-Regular.ttf", "72f793376f8e2841656bf21d77a5de010f2929bd6956a22ee848ad0c7eb978af", "train", "type"),
    ("ofl/andika/Andika-Regular.ttf", "202b96b1f174a4a43baefe885b40dacacb81786755efd08ed4b7704e79c45515", "train", "type"),
    ("ofl/lato/Lato-Regular.ttf", "d636e4683231f931eda222d588e944d082bfd3bdba02f928bee461c0f185b251", "train", "type"),
    ("ofl/lato/Lato-Bold.ttf", "8a0aace75d33794eece4b28187bfc1df0bbd2888b5d8a56e01788c8d65d16be1", "train", "type"),
    ("ofl/spacemono/SpaceMono-Regular.ttf", "95837e182baeeada83368f7748db28357f0a1b75c6b84ff7065b5edf933c8e18", "train", "type"),
    ("ofl/oswald/Oswald%5Bwght%5D.ttf", "5b38c246e255a12f5712d640d56bcced0472466fc68983d2d0410ec0457c2817", "train", "type"),
    ("ofl/ptserif/PT_Serif-Web-Regular.ttf", "a4951fade06ff8f09b7673aa81ffb65a8cd409e24d3289a6dc670bc4dda2557a", "train", "type"),
    ("ofl/ptsans/PT_Sans-Web-Regular.ttf", "9cc831490532009bae2b3ce0d39c62adfc889060beb421593bfd9d2396d0f10a", "test", "type"),
    ("ofl/merriweather/Merriweather%5Bopsz,wdth,wght%5D.ttf", "d0ed0e359e396af7ad05e73dffd11a3a4c326ea0d0283c56bd9361cb2cc86a96", "test", "type"),
    ("ofl/notosansmono/NotoSansMono%5Bwdth,wght%5D.ttf", "2cb2adb378a8f574213e23df697050b83c54c27df465a2015552740b2769a081", "train", "type"),
    ("ofl/sourcecodepro/SourceCodePro%5Bwght%5D.ttf", "b400fc584e10aff25d0e775ce181b4fc1c5ea1b5dc37b81aeb2084375b945790", "train", "type"),
    ("ofl/comicneue/ComicNeue-Regular.ttf", "a0ee5a37c8b27c4db0700137d928598b1e23b0089e1546a8961909176b779360", "train", "type"),
    ("ofl/librebaskerville/LibreBaskerville%5Bwght%5D.ttf", "05a95421961341c5b2556285e8415df9db27dab4f4abe22b446b3c6a8b916c5d", "train", "type"),
    ("apache/specialelite/SpecialElite-Regular.ttf", "a776fcb4ceb8bdf03e2967688ebdad42680de5b91a7e62c17e718ae212d14bc4", "test", "type"),
    ("ofl/dancingscript/DancingScript%5Bwght%5D.ttf", "21808625578fe8d8cd10cb684be546dca077b27cd03a53a2f1ec11dc743c924c", "train", "script"),
    ("ofl/pacifico/Pacifico-Regular.ttf", "5b6c0d5334a7bf77dea52b975c5a0c408878c0f7115ed5b6fb151f634b7bf701", "train", "script"),
    ("ofl/caveat/Caveat%5Bwght%5D.ttf", "0bdb6b660482d31531b3945849fba5916b3ef8695da7024a9e6b9ee3c4157988", "train", "script"),
    ("ofl/kalam/Kalam-Regular.ttf", "57cecb63d4608019371954274ae1d8c397764debd5b19d4a33c1efa4dc923c0b", "test", "script"),
    ("ofl/patrickhand/PatrickHand-Regular.ttf", "0f173b3e6cb6d1af25babf7f0057c5ac4ee11f9992b0469bb817e967ef4ad0fc", "train", "script"),
    ("ofl/greatvibes/GreatVibes-Regular.ttf", "8d509802186f1b51572531ecf313e8098f9a5bfdfaca93f0c9b34467f9982d15", "train", "script"),
    ("ofl/indieflower/IndieFlower-Regular.ttf", "ccc94b22b156e9c5dfe50fd051f01b097600b252c24473e624bb43a143140a94", "train", "script"),
    ("ofl/shadowsintolight/ShadowsIntoLight.ttf", "1347863151acdc00fa281daaba1a3543dbce5870b55f9cf7479a15bb84007681", "train", "script"),
    ("ofl/sacramento/Sacramento-Regular.ttf", "9341fda10adbfeb7efc94302b34507a3e227d7e7f5c432df3f5ac8753ff73d24", "train", "script"),
]  # fmt: skip
# pylint: enable=line-too-long

# Words for both kinds, in the characters UJI has (letters and digits),
# so punctuation can never tell print from handwriting.
WORDS = (
    "vahini bheema pihu tara chinnu vidhya seetha rama arun vishnu raji "
    "madhuri keshava shivani the and a to of in is it you that he was for "
    "on are with as his they be at one have this from or had by word but "
    "what some we can out other were all there when up use your how said "
    "an each she which do their time if will way about many then them "
    "write would like so these her long make thing see him two has look "
    "more day could go come did number sound no most people my over know "
    "water than call first who may down side been now find any new work "
    "part take get place made live where after back little only round man "
    "year came show every good me give our under name very through just "
    "form sentence great think say help low line differ turn cause much "
    "mean before move right boy old too same tell does set three want air "
    "well also play small end put home read hand port large spell add even "
    "land here must big high such follow act why ask men change went light "
    "kind off need house picture try us again animal point mother world "
    "near build self earth father head stand own page should country found "
    "answer school grow study still learn plant cover food sun four between "
    "state keep eye never last let thought city tree cross farm hard start "
    "story saw far sea draw left late run while press close night real life "
    "few north open seem together next white children begin got walk "
    "example ease paper group always music those both mark often letter "
    "until mile river car feet care second book carry took science eat room "
    "friend began idea fish mountain stop once base hear horse cut sure "
    "watch color face wood main enough plain girl usual young ready above "
    "ever red list though feel talk bird soon body dog family direct pose "
    "leave song measure door product black short numeral class wind "
    "question happen complete ship area half rock order fire south problem "
    "piece told knew pass since top whole king space heard best hour better "
    "true during hundred five remember step early hold west ground interest "
    "reach fast verb sing listen six table travel less morning ten simple "
    "several vowel toward war lay against pattern slow center love person "
    "money serve appear road map rain rule govern pull cold notice voice "
    "unit power town fine certain fly fall lead cry dark machine note wait "
    "plan figure star box noun field rest correct able pound done beauty "
    "drive stood contain front teach week final gave green oh quick develop "
    "ocean warm free minute strong special mind behind clear tail produce "
    "fact street inch multiply nothing course stay wheel full force blue "
    "object decide surface deep moon island foot system busy test record "
    "boat common gold possible plane stead dry wonder laugh thousand ago "
    "ran check game shape equate hot miss brought heat snow tire bring yes "
    "distant fill east paint language among NAME DATE CLASS SCHOOL ROLL NO "
    "Patient Address Total Amount Date Name Class Section Page Signature "
    "1 2 3 4 5 6 7 8 9 10 12 15 20 25 30 45 50 100 2026 1929 4309"
).split()

# Real test lines. Pages labelled by tests/fixtures/samples/README.md;
# lines whose text matches a pattern take that label instead, and None
# leaves a line out (a watermark, or print and pen in one box).
REAL_PAGES = {
    "tests/fixtures/handwriting-sample.jpg": "hand",
    "tests/fixtures/samples/handwritten_letter_1.jpg": "hand",
    "tests/fixtures/samples/handwritten_letter_2.jpg": "hand",
    "tests/fixtures/samples/handwritten_script_1.jpg": "print",
    "tests/fixtures/samples/handwritten_printed_1.jpg": "print",
    "tests/fixtures/samples/handwritten_printed_2.jpg": "print",
    "tests/fixtures/samples/handwritten_printed_3.png": "print",
    "tests/fixtures/samples/handwritten_printed_mixed_1.jpg": "hand",
    "tests/fixtures/samples/printed_signature_1.jpg": "print",
}
REAL_LABELS = {
    "tests/fixtures/handwriting-sample.jpg": [(r"^NOTES$", "print")],
    "tests/fixtures/samples/handwritten_letter_2.jpg": [
        (r"getty|^\d{8,}$|^J\w?ling", None)
    ],
    "tests/fixtures/samples/handwritten_printed_2.jpg": [(r"^E\w?lt$", None)],
    "tests/fixtures/samples/handwritten_printed_mixed_1.jpg": [
        (r"Sum of|[£$]", None),
        (r"(?i)4309|borough|constable|from mr|^for$|^by$", "print"),
    ],
}

H = print_hand.H
MAX_W = print_hand.MAX_W


def fetch_font(path, sha, cache):
    name = path.rsplit("/", 1)[1].replace("%5B", "[").replace("%5D", "]")
    local = os.path.join(cache, name)
    if not os.path.exists(local):
        os.makedirs(cache, exist_ok=True)
        url = FONTS_URL.format(FONTS_COMMIT, path)
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = resp.read()
        with open(local, "wb") as f:
            f.write(data)
    with open(local, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    if digest != sha:
        raise SystemExit(f"{local}: SHA-256 {digest}, expected {sha}")
    return local


def parse_uji(path, split):
    """{writer: {char: [strokes]}} for one published split, all 62
    letters and digits, strokes in millimetres."""
    out, strokes, mm = {}, None, 1.0
    with open(path, encoding="utf-8") as f:
        for raw in f:
            parts = raw.split()
            if not parts or parts[0].startswith("//"):
                continue
            if parts[0] == "WORD":
                sp, site, rest = parts[2].split("_", 2)
                ch = parts[1]
                strokes = None
                if sp == split and len(ch) == 1 and ch.isalnum():
                    writer = f"{site}_{rest.split('-')[0]}"
                    strokes, mm = [], planted_pages.UNITS_PER_MM[site]
                    out.setdefault(writer, {}).setdefault(ch, []).append(
                        strokes
                    )
            elif parts[0] == "POINTS" and strokes is not None:
                xy = np.array(parts[3:], dtype=np.float64).reshape(-1, 2)
                strokes.append(xy / mm)
    return out


def _text(rng, letters=None):
    """A few words; with letters given, only words the writer can write."""
    words = WORDS
    if letters is not None:
        words = [w for w in WORDS if all(c in letters for c in w)]
    n = int(rng.integers(2, 7))
    text = " ".join(words[int(rng.integers(len(words)))] for _ in range(n))
    if rng.random() < 0.15:
        text = (
            text.upper()
            if letters is None
            or all(c.upper() in letters for c in text.replace(" ", ""))
            else text
        )
    return text


def hand_mask(letters, rng, xh):
    """Ink coverage (0-1) of one handwritten line at small-letter height
    xh pixels, drawn 4 times larger and shrunk for smooth strokes."""
    scale4 = 4
    text = _text(rng, letters)
    small = [
        s
        for ch, ss in letters.items()
        if ch in planted_pages.SMALL
        for s in ss
    ]
    hs = [np.ptp(np.concatenate(s)[:, 1]) for s in small] or [1.0]
    px_mm = xh * scale4 / float(np.median(hs))
    slant = np.tan(np.radians(rng.normal(0, 8)))
    x, base = 8.0 * scale4, 3.0 * xh * scale4
    paths = []
    prev_end = None
    for word in text.split():
        for i, ch in enumerate(word):
            sample = letters[ch][int(rng.integers(len(letters[ch])))]
            pts = np.concatenate(sample)
            lo, hi = pts.min(0), pts.max(0)
            grow = rng.normal(1.0, 0.08)
            s = px_mm * grow
            h = (hi[1] - lo[1]) * s
            if ch in planted_pages.LOW:
                top = base - xh * scale4 * grow
            else:
                top = base - h
            top += rng.normal(0, 0.06) * xh * scale4
            placed = []
            for st in sample:
                p = (st - lo) * s + [x, top]
                p[:, 0] -= (p[:, 1] - base) * slant
                placed.append(p)
            if (
                prev_end is not None
                and i > 0
                and ch.islower()
                and rng.random() < 0.35
            ):
                paths.append(np.array([prev_end, placed[0][0]]))
            paths.extend(placed)
            prev_end = placed[-1][-1]
            x += (hi[0] - lo[0]) * s + rng.uniform(0.05, 0.35) * xh * scale4
        x += rng.uniform(0.6, 1.3) * xh * scale4
        prev_end = None
    width = int(x + 8 * scale4)
    height = int(base + 2.2 * xh * scale4)
    big = np.zeros((height, width), np.uint8)
    pen = rng.uniform(0.08, 0.2) * xh * scale4
    for p in paths:
        n = len(p)
        walk = np.cumsum(rng.normal(0, 0.25, max(n, 2)))
        walk = (walk - walk.min()) / max(1e-6, np.ptp(walk))
        widths = pen * (0.55 + 0.9 * walk)
        for i in range(n - 1):
            a = tuple(int(v) for v in np.round(p[i]))
            b = tuple(int(v) for v in np.round(p[i + 1]))
            cv2.line(big, a, b, 255, max(1, int(round(widths[i]))))
    return (
        cv2.resize(
            big,
            (width // scale4, height // scale4),
            interpolation=cv2.INTER_AREA,
        ).astype(np.float64)
        / 255.0
    )


def print_mask(font_path, rng, xh):
    """Ink coverage of one printed line in one font at x-height xh."""
    scale4 = 4
    size = int(xh * scale4 / 0.5)  # x-height is about half the em
    font = ImageFont.truetype(font_path, size)
    text = _text(rng)
    probe = font.getbbox("x")
    xh_font = max(1, probe[3] - probe[1])
    size = max(4, int(size * xh * scale4 / xh_font))
    font = ImageFont.truetype(font_path, size)
    left, top, right, bottom = font.getbbox(text)
    pad = 8 * scale4
    img = Image.new("L", (right - left + 2 * pad, bottom - top + 2 * pad), 0)
    draw = ImageDraw.Draw(img)
    stroke = int(rng.random() < 0.2)  # heavier type, or ink spread
    draw.text(
        (pad - left, pad - top), text, fill=255, font=font, stroke_width=stroke
    )
    arr = np.array(img)
    return (
        cv2.resize(
            arr,
            (arr.shape[1] // scale4, arr.shape[0] // scale4),
            interpolation=cv2.INTER_AREA,
        ).astype(np.float64)
        / 255.0
    )


def photograph(mask, rng):
    """The same paper, light, blur and JPEG for every line."""
    h, w = mask.shape
    a = np.clip(mask * rng.uniform(0.75, 1.0), 0, 1)
    if rng.random() < 0.35:  # ruled or dotted lines on the paper
        y = int(h * rng.uniform(0.55, 0.8))
        rule = np.zeros_like(a)
        if rng.random() < 0.5:
            rule[y, :: int(rng.integers(3, 9))] = 1.0
        else:
            rule[y, :] = 1.0
        a = np.maximum(a, rule * rng.uniform(0.15, 0.5))
    yy, xx = np.mgrid[0:h, 0:w]
    light = 0.8 + 0.18 * rng.random() * (xx / max(1, w))
    light *= 1.0 - 0.1 * rng.random() * (yy / max(1, h))
    paper = np.array(
        [rng.uniform(205, 250), rng.uniform(200, 248), rng.uniform(185, 240)]
    )
    ink = rng.uniform(10, 110, 3)
    if rng.random() < 0.25:  # aged paper, faded ink
        paper = paper * np.array([1.0, 0.93, 0.8])
        ink = ink + rng.uniform(40, 90)
    grain = cv2.GaussianBlur(
        rng.normal(0, rng.uniform(2, 8), (h, w)), (0, 0), 1
    )
    img = (paper * light[..., None] + grain[..., None]) * (1 - a[..., None])
    img += ink * a[..., None]
    img = cv2.GaussianBlur(np.clip(img, 0, 255), (0, 0), rng.uniform(0.3, 1.4))
    if rng.random() < 0.4:  # a smaller photo, enlarged again
        f = rng.uniform(0.4, 0.8)
        small = cv2.resize(img, (max(4, int(w * f)), max(4, int(h * f))))
        img = cv2.resize(small, (w, h))
    img = np.clip(img, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(
        ".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(rng.integers(45, 92))]
    )
    assert ok
    return cv2.cvtColor(
        cv2.imdecode(buf, cv2.IMREAD_COLOR), cv2.COLOR_BGR2GRAY
    )


def crop_line(gray, mask, rng):
    """A box around the ink, padded as a reader's line box would be."""
    ys, xs = np.nonzero(mask > 0.2)
    if len(ys) == 0:
        return None
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    hh = y1 - y0 + 1
    pad_y = int(hh * rng.uniform(0.0, 0.25))
    pad_x = int(hh * rng.uniform(0.0, 0.4))
    return gray[
        max(0, y0 - pad_y) : y1 + pad_y + 1,
        max(0, x0 - pad_x) : x1 + pad_x + 1,
    ]


def to_input(gray):
    """A line crop as the reader sees it, as 8-bit (print_hand.to_input)."""
    x = print_hand.to_input(gray)
    return None if x is None else np.round(x * 255).astype(np.uint8)


def synth(kind_items, n, rng):
    out = []
    while len(out) < n:
        # Small-letter height from 4 to 40 pixels, evenly on a log scale:
        # a photo of a whole page can leave type only 4 pixels high.
        xh = float(np.exp(rng.uniform(np.log(4.0), np.log(40.0))))
        item = kind_items[int(rng.integers(len(kind_items)))]
        try:
            mask = item(rng, xh)
        except (ValueError, OSError):
            continue
        if mask.shape[0] < 4 or mask.shape[1] < 8:
            continue
        if rng.random() < 0.3:
            ang = rng.normal(0, 2.5)
            m = cv2.getRotationMatrix2D(
                (mask.shape[1] / 2, mask.shape[0] / 2), ang, 1.0
            )
            mask = cv2.warpAffine(mask, m, (mask.shape[1], mask.shape[0]))
        gray = photograph(mask, rng)
        crop = crop_line(gray, mask, rng)
        if crop is None:
            continue
        x = to_input(crop)
        if x is not None:
            out.append(x)
    return out


def real_lines():
    """(input, label, page, text) for every labelled line the reader finds
    on the committed sample pages."""
    from vision import (
        computer_vision,
    )  # pylint: disable=import-outside-toplevel
    from reading import detector  # pylint: disable=import-outside-toplevel
    from reading import recognizer  # pylint: disable=import-outside-toplevel

    out = []
    for page, default in REAL_PAGES.items():
        with open(os.path.join(ROOT, page), "rb") as f:
            arr = computer_vision.to_numpy(f.read())
        raw, _err, _backend, _meta = recognizer.collect_lines(arr, "en")
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        for line in detector.merge_lines(raw):
            text = str(line.get("text") or "").strip()
            label = default
            for pattern, lab in REAL_LABELS.get(page, []):
                if re.search(pattern, text):
                    label = lab
                    break
            if label is None or len(re.sub(r"\W", "", text)) < 2:
                continue
            x, y, w, h = [int(round(v)) for v in line["box"]]
            crop = gray[max(0, y) : y + h, max(0, x) : x + w]
            inp = to_input(crop)
            if inp is not None:
                out.append((inp, label, page, text))
    return out


def pack(lines):
    """Ragged lines as one padded array plus widths."""
    widths = np.array([x.shape[1] for x in lines], np.int32)
    arr = np.zeros((len(lines), H, MAX_W), np.uint8)
    for i, x in enumerate(lines):
        arr[i, :, : x.shape[1]] = x
    return arr, widths


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--uji",
        default=os.path.join(
            os.path.expanduser("~"), ".cache", "vahini", "ujipenchars2.txt"
        ),
    )
    ap.add_argument(
        "--fonts",
        default=os.path.join(
            os.path.expanduser("~"), ".cache", "vahini", "fonts"
        ),
    )
    ap.add_argument("--train", type=int, default=6000, help="lines per kind")
    ap.add_argument("--test", type=int, default=800, help="lines per kind")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-real", action="store_true")
    args = ap.parse_args(argv)

    uji = planted_pages.fetch(args.uji)
    rng = np.random.default_rng(args.seed)
    data = {}
    for split, n in (("train", args.train), ("test", args.test)):
        writers = parse_uji(uji, "trn" if split == "train" else "tst")
        hands = [
            (lambda r, xh, L=letters: hand_mask(L, r, xh))
            for letters in writers.values()
        ]
        fonts = [
            fetch_font(path, sha, args.fonts)
            for path, sha, sp, _kind in FONTS
            if sp == split
        ]
        prints = [(lambda r, xh, f=f: print_mask(f, r, xh)) for f in fonts]
        hand = synth(hands, n, rng)
        printed = synth(prints, n, rng)
        x, w = pack(hand + printed)
        data[f"{split}_x"], data[f"{split}_w"] = x, w
        data[f"{split}_y"] = np.array(
            [0] * len(hand) + [1] * len(printed), np.uint8
        )
        print(f"{split}: {len(hand)} handwriting, {len(printed)} print")
    if not args.no_real:
        real = real_lines()
        x, w = pack([r[0] for r in real])
        data["real_x"], data["real_w"] = x, w
        data["real_y"] = np.array([r[1] == "print" for r in real], np.uint8)
        data["real_page"] = np.array([r[2] for r in real])
        data["real_text"] = np.array([r[3] for r in real])
        print(
            f"real: {int((data['real_y'] == 0).sum())} handwriting, "
            f"{int(data['real_y'].sum())} print"
        )
    np.savez_compressed(args.out, **data)


if __name__ == "__main__":
    main()
