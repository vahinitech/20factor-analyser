# SPDX-License-Identifier: AGPL-3.0-only
"""No tracked file may look like malware to a server's scanner.

The vahinitech.com server runs maldet nightly over home folders and /tmp.
On 2026-10-16 it flagged scratch copies of test_image_formats.py, because a
fake upload held a PHP open tag joined to a shell call (signature
php.generic.globals.503). Test payloads are built from parts at run time;
this test keeps it that way.

Python folds "a" + "b" into one constant when it compiles a file, so on
2026-10-19 the scan found the joined payload in a cached .pyc although the
source held only the parts. Payloads are joined with b"".join(...), which the
compiler leaves alone, and every tracked .py is compiled here and its
constants checked the same way.

Built-in patterns run everywhere. Where maldet's signature file is readable,
every literal hex signature in it is checked too, so the test sees what the
scanner sees. VAHINI_MALDET_SIGS points at another hex.dat; "none" skips it.
"""

import os
import re
import types
import subprocess
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Every pattern is assembled from parts at run time, so this file and its
# compiled form pass themselves.
OPEN = b"".join((b"<", b"?php"))
CALLS = (
    b"system|eval|exec|passthru|shell_exec|popen|proc_open|assert"
    b"|base64_decode"
)
BUILT_IN = (
    (
        "PHP open tag joined to a shell or eval call",
        re.compile(re.escape(OPEN) + rb"\s*@?(" + CALLS + rb")\s*\(", re.I),
    ),
    (
        "EICAR test string",
        re.compile(
            b"".join((b"EICAR-", b"STANDARD-ANTIVIRUS-", b"TEST-FILE"))
        ),
    ),
)
SHELL_NAMES = re.compile(
    r"(^|/)(shell|cmd|c99|r57|wso|b374k|webshell|backdoor)\d*"
    r"\.(php\d?|phtml|asp|aspx|jsp)$",
    re.I,
)
# Images, fonts, PDFs and model files are not text a person writes; checking
# them against 2,000+ signatures is slow, so the maldet half skips them.
MEDIA = re.compile(
    r"\.(pdf|png|jpe?g|webp|gif|ico|heic|woff2?|ttf|otf|onnx|pt|bin)$", re.I
)


def load_maldet():
    """Literal hex signatures from maldet's hex.dat, if it is readable."""
    path = os.environ.get(
        "VAHINI_MALDET_SIGS", "/usr/local/maldetect/sigs/hex.dat"
    )
    if path == "none":
        return []
    try:
        with open(path, encoding="latin-1") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return []
    sigs = []
    for line in lines:
        parts = line.strip().split(":")
        if len(parts) < 2 or not re.fullmatch(r"([0-9a-fA-F]{2})+", parts[0]):
            continue  # "*" wildcard lines target binaries and archives
        sigs.append((parts[1], bytes.fromhex(parts[0])))
    return sigs


def find_hits(rel, data, maldet):
    """Reasons a scanner would flag this file, or an empty list."""
    hits = []
    if SHELL_NAMES.search(rel):
        hits.append("file name looks like a web shell")
    hits += [name for name, pattern in BUILT_IN if pattern.search(data)]
    if not MEDIA.search(rel):
        hits += ["maldet " + name for name, sig in maldet if sig in data]
    return hits


def constants(code):
    """Every str and bytes constant in a code object, nested ones included."""
    for value in code.co_consts:
        if isinstance(value, types.CodeType):
            yield from constants(value)
        elif isinstance(value, (tuple, frozenset)):
            for item in value:
                if isinstance(item, (str, bytes)):
                    yield item
        elif isinstance(value, (str, bytes)):
            yield value


def compiled_hits(rel, source, maldet):
    """Reasons a scanner would flag this file's .pyc, or an empty list."""
    try:
        code = compile(source, rel, "exec", dont_inherit=True)
    except SyntaxError:
        return []
    hits = []
    for value in constants(code):
        if isinstance(value, str):
            value = value.encode("utf-8", "surrogatepass")
        hits += [h for h in find_hits("a.py", value, maldet) if h not in hits]
    return hits


class ScannerStringsTest(unittest.TestCase):
    """Tracked files and names stay clear of malware signatures."""

    joined = b"x" + OPEN + b" system($_GET[0]); ?>"

    def test_the_checker_catches_the_joined_payload(self):
        self.assertTrue(find_hits("a.py", self.joined, []))
        split = b'x"' + OPEN + b' " + b"system($_GET[0]); ?>"'
        self.assertEqual(find_hits("a.py", split, []), [])
        self.assertTrue(find_hits("frontend/shell.php", b"ok", []))
        self.assertEqual(find_hits("backend/shell_check.py", b"ok", []), [])

    def test_the_checker_catches_a_folded_literal(self):
        quote = b'"'
        folded = b"".join(
            (
                b"x = b",
                quote,
                OPEN,
                b" ",
                quote,
                b" + b",
                quote,
                b"system($_GET[0]); ?>",
                quote,
                b"\n",
            )
        )
        self.assertEqual(find_hits("a.py", folded, []), [])
        self.assertTrue(compiled_hits("a.py", folded, []))
        unfolded = (
            folded.replace(b"x = b", b"x = b''.join((b")
            .replace(b" + b", b", b")
            .replace(b"\n", b"))\n")
        )
        self.assertEqual(compiled_hits("a.py", unfolded, []), [])

    def test_maldet_signatures_load_when_present(self):
        maldet = load_maldet()
        if not maldet:
            self.skipTest("maldet signatures not readable here")
        hits = find_hits("a.py", self.joined, maldet)
        self.assertTrue(any(h.startswith("maldet ") for h in hits))

    def test_no_tracked_file_matches(self):
        maldet = load_maldet()
        files = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=REPO,
            capture_output=True,
            check=True,
        ).stdout.split(b"\0")
        bad = []
        for raw in filter(None, files):
            rel = raw.decode("utf-8", "surrogateescape")
            path = os.path.join(REPO, rel)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            with open(path, "rb") as handle:
                data = handle.read()
            hits = find_hits(rel, data, maldet)
            if rel.endswith(".py"):
                hits += [
                    "compiled " + h for h in compiled_hits(rel, data, maldet)
                ]
            if hits:
                bad.append(f"{rel}: {', '.join(hits)}")
        self.assertEqual(
            bad,
            [],
            "these files would be flagged as malware; build the payload "
            'from parts at run time with b"".join, not + (CLAUDE.md)',
        )


if __name__ == "__main__":
    unittest.main()
