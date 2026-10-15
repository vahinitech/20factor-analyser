# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Stored reports: what a later check is compared with.

Every successful version-2 report is kept as a small record, so a family
can compare a later check with an earlier one (owner decision,
2026-10-16). The record is built from an allowlist, never by deleting
fields from the response, and holds no personal data:

  kept     the scores (overall, each factor, Pro section scores), the
           counts that say whether two pages can be compared (lines,
           words, characters, script, reading languages, printed lines
           left out, reading level, passage match), where each factor was
           measured as numbers in the photo's pixels, the catalogue
           version, the tier and the day of the check
  never    the photo or any cut-out of it, the words read from the page
           (a child often writes a name or school at the top), captions,
           the uploaded file's name, the passage typed in, the access
           key, the caller's address or browser, or the time of day

A record is found only by its receipt: a random id and a random token
that go back to the family's browser. Only the token's SHA-256 is
stored, so a copy of the folder cannot read a report back, and nothing
links a record to a person, a device or another record.

Records expire 12 months after the family's last check: a new check can
renew the receipts the browser already holds (renew()), and expired
records are deleted by sweep(), which runs at start-up and once a day.
The family can delete a record with its receipt at any time.

On only when VAHINI_REPORT_STORE_DIR names a writable folder (the
container is otherwise read-only). A failed write never costs a family
their report: the report is sent without a receipt.
"""

import hashlib
import hmac
import json
import logging
import math
import os
import re
import secrets
from datetime import date, datetime, timedelta, timezone

log = logging.getLogger("vahini.report_store")

RECORD_VERSION = 1
KEEP_DAYS = 365
MAX_RENEW = 50  # receipts one renewal may name

ID_RE = re.compile(r"^[0-9a-f]{32}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")

STATUSES = {"e", "p", "m", "u"}
TIERS = {"free", "pro"}
SCRIPTS = {"latin", "telugu", "devanagari", "mixed", "other"}
PAGES = {"handwriting", "handwriting_with_print"}
READING = {"passage-verified", "high", "moderate", "low", "unavailable"}
LANG_RE = re.compile(r"^[a-z]{2,3}([_-][A-Za-z]{2,4})?$")
SECTION_RE = re.compile(r"^[a-z_]{1,24}$")
CATALOG_RE = re.compile(r"^[0-9a-f]{20}$")
SHAPES = {"box", "line"}
ROLES = {
    "region",
    "look",
    "keep",
    "baseline",
    "midline",
    "usual_start",
    "hardest_line",
    "underline",
    "letter",
}
MEASURES = {
    "line_height",
    "word_xheight",
    "line_angle",
    "read_confidence",
    "word_gap",
}


def _num(value, low=None, high=None):
    """A finite number within bounds, else None. Booleans are not."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if not math.isfinite(value):
        return None
    if (low is not None and value < low) or (
        high is not None and value > high
    ):
        return None
    return int(value) if value.is_integer() else round(value, 4)


def _count(value):
    value = _num(value, 0, 10**6)
    return int(value) if value is not None else None


def _label(value, allowed):
    return value if isinstance(value, str) and value in allowed else None


def _factors(report):
    out = []
    for factor in report.get("factors") or []:
        if not isinstance(factor, dict):
            continue
        n = _count(factor.get("n"))
        if n is None or not 1 <= n <= 20:
            continue
        out.append(
            {
                "n": n,
                "s": _num(factor.get("s"), 0, 10),
                "st": _label(factor.get("st"), STATUSES) or "u",
            }
        )
    return out


def _sections(report):
    out = []
    for section in report.get("sections") or []:
        if not isinstance(section, dict):
            continue
        ident = section.get("id")
        if not isinstance(ident, str) or not SECTION_RE.match(ident):
            continue
        out.append(
            {
                "id": ident,
                "s": _num(section.get("s"), 0, 10),
                "w": _num(section.get("w"), 0, 1),
            }
        )
    return out


def _comparability(facts):
    facts = facts if isinstance(facts, dict) else {}
    return {
        "lines": _count(facts.get("lines")),
        "words": _count(facts.get("words")),
        "characters": _count(facts.get("characters")),
        "script": _label(facts.get("script"), SCRIPTS),
        "languages": sorted(
            {
                lang
                for lang in facts.get("languages") or []
                if isinstance(lang, str) and LANG_RE.match(lang)
            }
        ),
        "printed_lines": _count(facts.get("printed_lines")),
        "page": _label(facts.get("page"), PAGES),
        "reading": _label(facts.get("reading"), READING),
        "passage_aligned": facts.get("passage_aligned") is True,
    }


def _mark(mark):
    if not isinstance(mark, dict):
        return None
    shape = _label(mark.get("shape"), SHAPES)
    role = _label(mark.get("role"), ROLES)
    if shape is None or role is None:
        return None
    out = {"shape": shape, "role": role}
    measure = _label(mark.get("measure"), MEASURES)
    if measure:
        out["measure"] = measure
    if shape == "box":
        box = [_num(v, -1e5, 1e5) for v in mark.get("box") or []]
        if len(box) != 4 or None in box:
            return None
        out["box"] = box
    else:
        points = mark.get("points") or []
        clean = [
            [_num(v, -1e5, 1e5) for v in point]
            for point in points
            if isinstance(point, (list, tuple))
        ]
        if len(clean) != 2 or any(len(p) != 2 or None in p for p in clean):
            return None
        out["points"] = clean
    return out


def _marks(evidence):
    if not isinstance(evidence, dict):
        return None
    width = _count(evidence.get("photo_width"))
    height = _count(evidence.get("photo_height"))
    factors = {}
    for key, region in (evidence.get("factor_regions") or {}).items():
        if not (
            isinstance(key, str) and key.isdigit() and 1 <= int(key) <= 20
        ):
            continue
        if not isinstance(region, dict):
            continue
        marks = [m for m in map(_mark, region.get("marks") or []) if m]
        if marks:
            factors[key] = marks
    if not factors:
        return None
    return {"photo_width": width, "photo_height": height, "factors": factors}


def record_from(report, day):
    """The stored record for one compact report: the allowlist above,
    with every value re-checked for type and range. `day` is a
    datetime.date, the only time kept."""
    tier = _label((report.get("access") or {}).get("tier"), TIERS) or "free"
    catalog = report.get("catalog_version")
    record = {
        "record_version": RECORD_VERSION,
        "day": day.isoformat(),
        "catalog_version": (
            catalog
            if isinstance(catalog, str) and CATALOG_RE.match(catalog)
            else None
        ),
        "tier": tier,
        "score": _num((report.get("summary") or {}).get("score"), 0, 100),
        "factors": _factors(report),
        "locked": sorted(
            {
                n
                for n in (_count(v) for v in report.get("locked") or [])
                if n is not None and 1 <= n <= 20
            }
        ),
        "comparability": _comparability(report.get("comparability")),
    }
    sections = _sections(report)
    if sections:
        record["sections"] = sections
    marks = _marks(report.get("evidence"))
    if marks:
        record["marks"] = marks
    return record


def _hash(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _today():
    return datetime.now(timezone.utc).date()


class ReportStore:
    """Where (and whether) report records are kept."""

    def __init__(self, folder=None, today=_today):
        self.folder = folder or None
        self.today = today
        self._swept = None

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        return cls(env.get("VAHINI_REPORT_STORE_DIR", "").strip() or None)

    @property
    def enabled(self):
        return self.folder is not None

    def _path(self, ident):
        # Ids are checked before they reach a path.
        return os.path.join(self.folder, "reports", ident + ".json")

    def _expires(self):
        return (self.today() + timedelta(days=KEEP_DAYS)).isoformat()

    def save(self, report):
        """Keep one successful report; the receipt for the family's
        browser, or None when off, refused or the write failed."""
        if not self.enabled or not isinstance(report, dict):
            return None
        if report.get("ok") is not True:
            return None
        if self._swept != self.today():
            self._swept = self.today()
            self.sweep()
        ident = secrets.token_hex(16)
        token = secrets.token_urlsafe(32)
        stored = {
            "id": ident,
            "token_sha256": _hash(token),
            "expires": self._expires(),
            "report": record_from(report, self.today()),
        }
        try:
            os.makedirs(os.path.join(self.folder, "reports"), 0o700, True)
            _write_new(self._path(ident), _dump(stored))
        except (OSError, TypeError, ValueError) as exc:
            log.warning("report store: not kept: %s", exc)
            return None
        return {"id": ident, "token": token, "expires": stored["expires"]}

    def _load(self, ident, token):
        """The stored entry for a valid receipt, else None. A wrong
        token and an unknown id look the same to the caller."""
        if not (
            self.enabled
            and isinstance(ident, str)
            and isinstance(token, str)
            and ID_RE.match(ident)
            and TOKEN_RE.match(token)
        ):
            return None
        try:
            with open(self._path(ident), encoding="utf-8") as fh:
                stored = json.load(fh)
        except (OSError, ValueError):
            return None
        if not hmac.compare_digest(
            str(stored.get("token_sha256", "")), _hash(token)
        ):
            return None
        if str(stored.get("expires", "")) < self.today().isoformat():
            return None
        return stored

    def read(self, ident, token):
        stored = self._load(ident, token)
        if stored is None:
            return None
        return {
            "id": ident,
            "expires": stored["expires"],
            **stored["report"],
        }

    def delete(self, ident, token):
        if self._load(ident, token) is None:
            return False
        try:
            os.remove(self._path(ident))
        except OSError:
            return False
        return True

    def renew(self, receipts):
        """Move the expiry of each valid receipt to 12 months from
        today: the family has checked again. Returns how many."""
        renewed = 0
        for receipt in list(receipts or [])[:MAX_RENEW]:
            if not isinstance(receipt, dict):
                continue
            ident = receipt.get("id")
            stored = self._load(ident, receipt.get("token"))
            if stored is None:
                continue
            stored["expires"] = self._expires()
            try:
                _replace(self._path(ident), _dump(stored))
            except OSError as exc:
                log.warning("report store: not renewed: %s", exc)
                continue
            renewed += 1
        return renewed

    def sweep(self):
        """Delete expired and unreadable records. Returns how many."""
        if not self.enabled:
            return 0
        folder = os.path.join(self.folder, "reports")
        today = self.today().isoformat()
        removed = 0
        try:
            names = os.listdir(folder)
        except OSError:
            return 0
        for name in names:
            path = os.path.join(folder, name)
            if not (name.endswith(".json") and ID_RE.match(name[:-5])):
                continue
            try:
                with open(path, encoding="utf-8") as fh:
                    expires = str(json.load(fh).get("expires", ""))
            except (OSError, ValueError):
                expires = ""
            if expires < today:
                try:
                    os.remove(path)
                    removed += 1
                except OSError:
                    pass
        return removed


def _dump(stored):
    return json.dumps(stored, separators=(",", ":"), allow_nan=False).encode()


def _write_new(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def _replace(path, data):
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


STORE = ReportStore.from_env()


def day_of(value):
    """A YYYY-MM-DD string as a date (tests and tools)."""
    return date.fromisoformat(value)
