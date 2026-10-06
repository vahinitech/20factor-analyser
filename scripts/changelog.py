#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-Vahini-Proprietary
# (c) 2026 Vahini Technologies. All rights reserved.
"""Changelog entries as files, one per PR, folded into CHANGELOG.md at release.

    python3 changelog.py --print            the next release's entries
    python3 changelog.py --check            fail on a bad entry, or on a bullet
                                            put back under "## Unreleased"
    python3 changelog.py --release X.Y.Z    fold every entry into CHANGELOG.md
                                            under "## X.Y.Z - <today>", delete
                                            the files, bump the version source

Why: when every PR added its line at the top of "## Unreleased", any two open
PRs edited the same lines of CHANGELOG.md, so whichever merged second
conflicted. Separate files never collide. git's merge=union attribute would
keep both lines too, but GitHub's merge button ignores it.

An entry is changelog.d/<branch topic>.md (claude/indexnow -> indexnow.md):
one or more "- " bullets, plain prose, no em dash. Entries come out oldest
first, by the commit that added each file.

The version source is found, in order: package.json "version", a VERSION
file, pyproject.toml's version. With none (a repository released only by
tags), --release writes the heading and changes no version.

Canonical copy: vahinitech/Umbrella scripts/changelog.py. Repositories copy
it unchanged; change it there first, then copy it again. Standard library
only, so it runs wherever Python 3 does.
"""
import datetime
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True,
    cwd=pathlib.Path(__file__).resolve().parent).stdout.strip())
DIR = ROOT / "changelog.d"
LOG = ROOT / "CHANGELOG.md"
EM_DASH = chr(0x2014)
NAME = re.compile(r"^[a-z0-9][a-z0-9.-]*\.md$")


def entries():
    return sorted(p.name for p in DIR.glob("*.md") if p.name != "README.md") if DIR.is_dir() else []


def added(name):
    """Time of the commit that added the file; uncommitted files sort last."""
    out = subprocess.run(["git", "-C", str(ROOT), "log", "--diff-filter=A", "--format=%ct", "-1", "--",
                          f"changelog.d/{name}"], capture_output=True, text=True, check=False).stdout.strip()
    return int(out) if out else float("inf")


def ordered():
    return sorted(entries(), key=lambda n: (added(n), n))


def read(name):
    return (DIR / name).read_text(encoding="utf-8").rstrip()


def unreleased(text):
    """(start, end) of the "## Unreleased" section, end exclusive."""
    start = text.find("## Unreleased")
    if start < 0:
        return None
    nxt = re.search(r"^## ", text[start + 1:], re.MULTILINE)
    return start, (start + 1 + nxt.start()) if nxt else len(text)


def problems():
    out = []
    for name in entries():
        body = read(name)
        if not NAME.match(name):
            out.append(f"changelog.d/{name}: name it <topic>.md in lower case")
        if not body:
            out.append(f"changelog.d/{name} is empty")
            continue
        lines = body.split("\n")
        if not lines[0].startswith("- "):
            out.append(f'changelog.d/{name}: start with a "- " bullet')
        if any(line and not line.startswith(("- ", "  ")) for line in lines):
            out.append(f'changelog.d/{name}: only "- " bullets and their indented continuation lines')
        if EM_DASH in body:
            out.append(f"changelog.d/{name}: no em dashes")
    if not LOG.exists():
        out.append("CHANGELOG.md is missing")
        return out
    text = LOG.read_text(encoding="utf-8")
    span = unreleased(text)
    if not span:
        out.append('CHANGELOG.md has no "## Unreleased" heading')
    elif re.search(r"^- ", text[span[0]:span[1]], re.MULTILINE):
        out.append('CHANGELOG.md has bullets under "## Unreleased"; move them into changelog.d/<topic>.md')
    return out


def bump(version):
    pkg = ROOT / "package.json"
    if pkg.exists() and '"version"' in pkg.read_text(encoding="utf-8"):
        text = pkg.read_text(encoding="utf-8")
        json.loads(text)  # refuse to touch a file that is not valid JSON
        pkg.write_text(re.sub(r'"version":\s*"[^"]*"', f'"version": "{version}"', text, count=1), encoding="utf-8")
        return "package.json"
    ver = ROOT / "VERSION"
    if ver.exists():
        ver.write_text(version + "\n", encoding="utf-8")
        return "VERSION"
    py = ROOT / "pyproject.toml"
    if py.exists() and re.search(r'^version\s*=\s*"', py.read_text(encoding="utf-8"), re.MULTILINE):
        py.write_text(re.sub(r'^version\s*=\s*"[^"]*"', f'version = "{version}"', py.read_text(encoding="utf-8"),
                             count=1, flags=re.MULTILINE), encoding="utf-8")
        return "pyproject.toml"
    return None


def main(argv):
    if "--check" in argv:
        bad = problems()
        if bad:
            print("changelog:\n  " + "\n  ".join(bad), file=sys.stderr)
            return 1
        print(f"changelog: {len(entries())} unreleased entr{'y' if len(entries()) == 1 else 'ies'}, "
              "none under Unreleased in CHANGELOG.md")
        return 0
    if "--print" in argv:
        for name in ordered():
            print(read(name))
        return 0
    if "--release" in argv:
        i = argv.index("--release")
        version = argv[i + 1] if i + 1 < len(argv) else ""
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            print("usage: changelog.py --release X.Y.Z", file=sys.stderr)
            return 2
        bad = problems()
        if bad:
            print("changelog: fix these first:\n  " + "\n  ".join(bad), file=sys.stderr)
            return 1
        names = ordered()
        if not names:
            print("changelog: no entries in changelog.d/; nothing to release", file=sys.stderr)
            return 1
        text = LOG.read_text(encoding="utf-8")
        _, end = unreleased(text)
        section = f"## {version} - {datetime.date.today().isoformat()}\n\n" + "\n".join(read(n) for n in names)
        LOG.write_text(text[:end].rstrip("\n") + "\n\n" + section + "\n\n" + text[end:].lstrip("\n"), encoding="utf-8")
        for name in names:
            (DIR / name).unlink()
        source = bump(version)
        print(f"changelog: {len(names)} entr{'y' if len(names) == 1 else 'ies'} released as {version}"
              + (f", {source} bumped" if source else ", no version file") + f"; tag v{version} after it merges")
        return 0
    print("usage: changelog.py --print | --check | --release X.Y.Z", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
