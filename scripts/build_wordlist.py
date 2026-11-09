# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Build the English word list the spelling check reads
(backend/languages/words/en.txt.gz) from a SCOWL release.

SCOWL (Spell Checker Oriented Word Lists, Kevin Atkinson) is the list
aspell and hunspell dictionaries are made from. Its licence asks that the
copyright notice travels with every copy, so the release's Copyright file
is copied beside the list. Words come from the English, American, British
(both -ise and -ize), Canadian and Australian lists, their first variants
and contractions, at sizes 60 and below (SCOWL's own advice for spell
checking). Each line is "word size": the smallest SCOWL size the word is
in, 10 for the most common words, which ranks spelling suggestions.
SCOWL's own taboo lists (misc/profane.*, misc/offensive.*) become
never-suggest.txt.gz: words a child's report never offers as the right
spelling. It is gzipped so the words do not show up in a search of the
repository.

    curl -LO https://downloads.sourceforge.net/project/wordlist/SCOWL/2020.12.07/scowl-2020.12.07.tar.gz
    python scripts/build_wordlist.py scowl-2020.12.07.tar.gz

The release file must match SHA256 below; it is unpacked into a
temporary folder and never committed.

The output is byte for byte the same on every run (gzip without a time
stamp), so a rebuild that changes the committed file means the source or
this script changed."""

import gzip
import hashlib
import io
import os
import re
import shutil
import sys
import tarfile
import tempfile

VERSION = "2020.12.07"
SHA256 = "5587667caa20c4891390c2d42dbb4d5c4c3f41bee77af1457ece3ba23fb859cc"
MAX_SIZE = 60
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "backend", "languages", "words")

_LIST = re.compile(
    r"^(english|american|british|british_z|canadian|australian)"
    r"(_variant_1)?-(words|contractions)\.(\d+)$"
)
_WORD = re.compile(r"[a-z][a-z']*")


def build(release):
    """{word: smallest size} from a SCOWL release folder."""
    final = os.path.join(release, "final")
    sizes = {}
    for name in sorted(os.listdir(final)):
        m = _LIST.match(name)
        if not m or int(m.group(4)) > MAX_SIZE:
            continue
        size = int(m.group(4))
        with open(os.path.join(final, name), encoding="latin-1") as f:
            for word in f.read().split("\n"):
                if _WORD.fullmatch(word):
                    sizes[word] = min(sizes.get(word, 99), size)
    return sizes


def taboo(release):
    """SCOWL's lists of words not to say around children."""
    misc = os.path.join(release, "misc")
    out = set()
    for name in ("profane.1", "profane.3", "offensive.1", "offensive.2"):
        with open(os.path.join(misc, name), encoding="latin-1") as f:
            out |= {w.lower() for w in f.read().split() if w.isalpha()}
    return out


def _gzip(path, body):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, filename="") as g:
        g.write(body.encode("ascii"))
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def write(sizes, release):
    """The gzip lists and the licence notice, into
    backend/languages/words."""
    os.makedirs(OUT, exist_ok=True)
    _gzip(
        os.path.join(OUT, "en.txt.gz"),
        "".join(f"{w} {s}\n" for w, s in sorted(sizes.items())),
    )
    _gzip(
        os.path.join(OUT, "never-suggest.txt.gz"),
        "".join(f"{w}\n" for w in sorted(taboo(release))),
    )
    shutil.copyfile(
        os.path.join(release, "Copyright"),
        os.path.join(OUT, "SCOWL-Copyright.txt"),
    )
    return len(sizes)


def unpack(tarball, into):
    """The release folder inside a checked SCOWL tarball."""
    with open(tarball, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    if digest != SHA256:
        raise SystemExit(f"{tarball}: SHA-256 {digest}, expected {SHA256}")
    with tarfile.open(tarball, "r:gz") as tar:
        tar.extractall(into, filter="data")
    return os.path.join(into, f"scowl-{VERSION}")


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        release = unpack(argv[1], tmp)
        count = write(build(release), release)
    print(f"{count} words, SCOWL {VERSION}, sizes up to {MAX_SIZE}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
