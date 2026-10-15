# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Stored reports hold no personal data (report_store.py).

Every successful compact report is kept so a later check can be compared
with it (owner decision, 2026-10-16). These tests are the proof that
what is kept is scores, counts and coordinates only:

- the record is checked against a closed list of keys and value shapes,
  so a field added to the report later cannot slip into the store;
- a page whose words name a child and a school, with evidence crops,
  captions, a typed passage, a named upload and an access key, is put
  through the real route, and every byte the store wrote is searched
  for each of them;
- a hostile report (wrong types, NaN, huge numbers, extra text fields)
  leaves nothing but checked values;
- a receipt is the only way back in, it expires, a later check renews
  it, and the family can delete it.

Planted pages only: drawn letters, cast names, no real handwriting.
"""

import importlib.util
import json
import os
import re
import stat
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# pylint: disable=wrong-import-position,protected-access
import compact_reports  # noqa: E402
import computer_vision as vision  # noqa: E402
import contract_schemas  # noqa: E402
import report_store  # noqa: E402
import scoring  # noqa: E402
from daily_limit import DailyLimit  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SERVER_DIR = ROOT / "backend"
_spec = importlib.util.spec_from_file_location(
    "planted_pages", ROOT / "scripts" / "planted_pages.py"
)
planted = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(planted)

PRO = {"tier": "pro", "customer_id": "cus_0123456789abcdef01234567"}
FREE = {"tier": "free", "subscription_status": "anonymous"}

# What a child might write at the top of the page, and what a family
# might type or name the file: none of it may reach the store.
NAME_LINE = "Bheema Kosuri Pihu Public School Class Two"
SECRETS = [
    "Bheema",
    "Kosuri",
    "Pihu Public",
    "School",
    "Class Two",
    "Seetha-Rama-homework",  # the uploaded file's name
    "Vidhya copies",  # the passage typed in
    "cus_0123456789abcdef01234567",  # the Pro customer
    "vk_live_secretkey",  # an access key
]
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"


def _box_letter(ch):
    h = 2.0 if ch in planted.TALL or ch in planted.LOW else 1.0
    return [np.array([[0, 0], [0.8, 0], [0.8, h], [0, h], [0, 0]])]


LETTERS = {
    ch: [_box_letter(ch), _box_letter(ch)]
    for ch in set("".join(planted.SENTENCES).replace(" ", ""))
}


def sensitive_payload(seed=3):
    """A planted page through the real scorer and evidence code, with
    the read text naming a child and a school."""
    img, lines, _truth = planted.build_page(
        LETTERS, np.random.default_rng(seed), "tilted_line", "plain"
    )
    vl = vision.vl_analyze(img, lines)
    height, width = img.shape[:2]
    lines[0] = {**lines[0], "text": NAME_LINE}
    return img, {
        "ok": True,
        "full_text": "\n".join(l["text"] for l in lines),
        "hand_lines": lines,
        "rec_langs": ["en"],
        "proc_w": width,
        "proc_h": height,
        "photo_w": width * 2,
        "photo_h": height * 2,
        "analysis": scoring.build_analysis(img, lines, {}).to_dict(),
        "factor_regions": vl["factor_regions"],
        "measurements": vl["measurements"],
    }


def everything(payload, access):
    """The biggest compact report there is: every include, Pro."""
    return compact_reports.build_compact(
        payload, access, {"text", "evidence", "inputs", "coaching"}
    )


# The closed list of what a record may hold, and the shape of each
# string. Adding a key to report_store.py without adding it here fails.
RECORD_KEYS = {
    "record_version",
    "day",
    "catalog_version",
    "tier",
    "score",
    "factors",
    "locked",
    "comparability",
    "sections",
    "marks",
}
NESTED_KEYS = {
    "n",
    "s",
    "st",
    "id",
    "w",
    "lines",
    "words",
    "characters",
    "script",
    "languages",
    "printed_lines",
    "page",
    "reading",
    "passage_aligned",
    "photo_width",
    "photo_height",
    "factors",
    "shape",
    "role",
    "measure",
    "box",
    "points",
}
STRING_SHAPES = [
    re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"),  # the day
    re.compile(r"^[0-9a-f]{20}$"),  # the catalogue version
    re.compile(r"^[a-z_-]{1,24}$"),  # enum labels and section ids
]


def walk(value, path="", keys=None):
    """Every (path, key) and (path, string) in a record."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield ("key", path, key)
            yield from walk(item, f"{path}.{key}")
    elif isinstance(value, list):
        for item in value:
            yield from walk(item, path + "[]")
    elif isinstance(value, str):
        yield ("str", path, value)


class RecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if vision.cv2 is None:
            raise unittest.SkipTest("OpenCV unavailable")
        cls.img, cls.payload = sensitive_payload()
        cls.report = everything(cls.payload, PRO)
        cls.record = report_store.record_from(cls.report, date(2026, 10, 3))

    def test_the_report_itself_carries_the_sensitive_parts(self):
        # Otherwise the tests below would prove nothing.
        dumped = json.dumps(self.report)
        self.assertIn("Bheema", dumped)
        self.assertIn("data:image/", dumped)
        self.assertTrue(
            any(
                r.get("caption")
                for r in self.report["evidence"]["factor_regions"].values()
            )
        )

    def test_the_record_keeps_scores_counts_and_marks(self):
        record = self.record
        self.assertEqual(record["score"], self.report["summary"]["score"])
        self.assertEqual(record["factors"], self.report["factors"])
        self.assertEqual(record["sections"], self.report["sections"])
        self.assertEqual(record["comparability"], self.report["comparability"])
        self.assertEqual(record["day"], "2026-10-03")
        self.assertEqual(record["tier"], "pro")
        seven = record["marks"]["factors"]["7"]
        self.assertIn("baseline", {m["role"] for m in seven})
        contract_schemas.validate(
            "stored-report",
            {"id": "0" * 32, "expires": "2027-10-03", **record},
        )

    def test_only_listed_keys_and_shapes(self):
        for kind, path, value in walk(self.record):
            if kind == "key":
                allowed = RECORD_KEYS if path == "" else NESTED_KEYS
                if path == ".marks.factors":
                    self.assertTrue(value.isdigit(), value)
                    continue
                self.assertIn(value, allowed, f"{path}.{value}")
            else:
                self.assertTrue(
                    any(rx.match(value) for rx in STRING_SHAPES),
                    f"{path} = {value!r}",
                )

    def test_nothing_personal_or_pictured_survives(self):
        dumped = json.dumps(self.record)
        for word in NAME_LINE.split() + SECRETS:
            self.assertNotIn(word, dumped)
        # The record's own words (keys and labels such as the "line" mark
        # shape) can match a word on the page; anything else cannot.
        vocabulary = RECORD_KEYS | NESTED_KEYS
        vocabulary |= {v for kind, _, v in walk(self.record) if kind == "str"}
        for line in self.payload["hand_lines"]:
            for word in line["text"].split():
                if len(word) >= 4 and word not in vocabulary:
                    self.assertNotIn(word, dumped, word)
        self.assertNotIn("data:", dumped)
        self.assertNotIn("base64", dumped)
        for region in self.report["evidence"]["factor_regions"].values():
            if region.get("caption"):
                self.assertNotIn(region["caption"], dumped)
        self.assertFalse(re.search(r"[A-Za-z0-9+/=]{41,}", dumped))

    def test_free_records_hold_only_free_scores(self):
        record = report_store.record_from(
            everything(self.payload, FREE), date(2026, 10, 3)
        )
        self.assertNotIn("sections", record)
        self.assertEqual(record["tier"], "free")
        self.assertEqual(len(record["factors"]), 5)

    def test_a_hostile_report_leaves_only_checked_values(self):
        hostile = {
            "ok": True,
            "text": "Bheema Kosuri",
            "name": "Bheema",
            "email": "bheema@example.com",
            "catalog_version": "../../etc/passwd",
            "access": {"tier": "admin", "customer_id": "cus_x"},
            "summary": {"score": float("nan"), "text": "Bheema"},
            "factors": [
                {"n": 7, "s": 6.5, "st": "e", "note": "Bheema"},
                {"n": 99, "s": 1, "st": "e"},
                {"n": True, "s": 2, "st": "e"},
                {"n": 8, "s": "Bheema", "st": "Bheema"},
                {"n": 9, "s": 1e309, "st": "m"},
            ],
            "locked": [1, "Bheema", 50],
            "sections": [{"id": "Bheema Kosuri", "s": 5, "w": 0.3}],
            "comparability": {
                "lines": -3,
                "words": "many",
                "script": "Bheema",
                "languages": ["en", "Bheema Kosuri", 3],
                "page": "handwriting",
                "reading": "high",
                "passage_aligned": "yes",
            },
            "evidence": {
                "photo_width": 1000,
                "photo_height": 800,
                "factor_regions": {
                    "7": {
                        "url": "data:image/png;base64,iVBORw0KGgo",
                        "caption": "Bheema wrote",
                        "marks": [
                            {
                                "shape": "box",
                                "role": "region",
                                "box": [1, 2, 3, 4],
                                "label": "Bheema",
                            },
                            {"shape": "box", "role": "Bheema", "box": [1]},
                            {
                                "shape": "line",
                                "role": "baseline",
                                "points": [[0, 1], [2, "x"]],
                            },
                        ],
                    },
                    "../x": {"marks": [{"shape": "box", "role": "region"}]},
                },
            },
        }
        record = report_store.record_from(hostile, date(2026, 10, 3))
        dumped = json.dumps(record, allow_nan=False)
        self.assertNotIn("Bheema", dumped)
        self.assertNotIn("data:", dumped)
        self.assertNotIn("cus_", dumped)
        self.assertIsNone(record["catalog_version"])
        self.assertEqual(record["tier"], "free")
        self.assertIsNone(record["score"])
        self.assertEqual(
            record["factors"],
            [
                {"n": 7, "s": 6.5, "st": "e"},
                {"n": 8, "s": None, "st": "u"},
                {"n": 9, "s": None, "st": "m"},
            ],
        )
        self.assertEqual(record["locked"], [1])
        self.assertNotIn("sections", record)
        self.assertEqual(record["comparability"]["languages"], ["en"])
        self.assertIsNone(record["comparability"]["lines"])
        self.assertIsNone(record["comparability"]["script"])
        self.assertFalse(record["comparability"]["passage_aligned"])
        self.assertEqual(
            record["marks"]["factors"],
            {"7": [{"shape": "box", "role": "region", "box": [1, 2, 3, 4]}]},
        )


def files_under(folder):
    found = []
    for root, _dirs, names in os.walk(folder):
        found += [os.path.join(root, name) for name in names]
    return sorted(found)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=R1732
        self.day = date(2026, 10, 3)
        self.store = report_store.ReportStore(
            self.tmp.name, today=lambda: self.day
        )
        self.report = {
            "ok": True,
            "access": {"tier": "free"},
            "summary": {"score": 80},
            "factors": [{"n": 7, "s": 5.4, "st": "e"}],
            "locked": [],
            "comparability": {"lines": 4, "words": 30, "script": "latin"},
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_off_keeps_nothing(self):
        store = report_store.ReportStore.from_env({})
        self.assertFalse(store.enabled)
        self.assertIsNone(store.save(self.report))
        self.assertTrue(
            report_store.ReportStore.from_env(
                {"VAHINI_REPORT_STORE_DIR": "/data/reports"}
            ).enabled
        )

    def test_a_failed_check_is_not_kept(self):
        self.assertIsNone(self.store.save({**self.report, "ok": False}))
        self.assertEqual(files_under(self.tmp.name), [])

    def test_the_receipt_reads_the_record_back(self):
        receipt = self.store.save(self.report)
        self.assertRegex(receipt["id"], r"^[0-9a-f]{32}$")
        self.assertRegex(receipt["token"], r"^[A-Za-z0-9_-]{43}$")
        self.assertEqual(receipt["expires"], "2027-10-03")
        record = self.store.read(receipt["id"], receipt["token"])
        self.assertEqual(record["score"], 80)
        self.assertEqual(record["day"], "2026-10-03")

    def test_the_folder_alone_cannot_read_a_report(self):
        receipt = self.store.save(self.report)
        (path,) = files_under(self.tmp.name)
        self.assertEqual(os.path.basename(path), receipt["id"] + ".json")
        with open(path, "rb") as fh:
            body = fh.read()
        self.assertNotIn(receipt["token"].encode(), body)
        self.assertEqual(
            set(json.loads(body)), {"id", "token_sha256", "expires", "report"}
        )
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        folder = os.path.dirname(path)
        self.assertEqual(stat.S_IMODE(os.stat(folder).st_mode), 0o700)

    def test_a_wrong_or_malformed_receipt_reads_nothing(self):
        receipt = self.store.save(self.report)
        other = report_store.ReportStore(self.tmp.name).save(self.report)
        cases = [
            (receipt["id"], other["token"]),
            (receipt["id"], ""),
            (receipt["id"], None),
            ("../" + receipt["id"], receipt["token"]),
            (receipt["id"].upper(), receipt["token"]),
            ("0" * 32, receipt["token"]),
        ]
        for ident, token in cases:
            self.assertIsNone(self.store.read(ident, token), (ident, token))
            self.assertFalse(self.store.delete(ident, token))

    def test_expiry_renewal_and_sweep(self):
        old = self.store.save(self.report)
        self.day += timedelta(days=200)
        kept = self.store.save(self.report)
        # A check 200 days later renews the first receipt.
        self.assertEqual(self.store.renew([old, {"id": "x"}, "junk"]), 1)
        self.assertEqual(
            self.store.read(old["id"], old["token"])["expires"],
            (self.day + timedelta(days=365)).isoformat(),
        )
        self.day += timedelta(days=366)
        self.assertIsNone(self.store.read(old["id"], old["token"]))
        self.assertEqual(self.store.sweep(), 2)
        self.assertEqual(files_under(self.tmp.name), [])
        self.assertIsNone(self.store.read(kept["id"], kept["token"]))

    def test_a_new_day_sweeps_before_keeping(self):
        self.store.save(self.report)
        self.day += timedelta(days=400)
        self.store.save(self.report)
        self.assertEqual(len(files_under(self.tmp.name)), 1)

    def test_the_family_can_delete(self):
        receipt = self.store.save(self.report)
        self.assertTrue(self.store.delete(receipt["id"], receipt["token"]))
        self.assertIsNone(self.store.read(receipt["id"], receipt["token"]))
        self.assertEqual(files_under(self.tmp.name), [])


class EndpointTests(unittest.TestCase):
    """The real route, with the scan answered by a planted page."""

    @classmethod
    def setUpClass(cls):
        if vision.cv2 is None:
            raise unittest.SkipTest("OpenCV unavailable")
        spec = importlib.util.spec_from_file_location(
            "ppocr_server_report_store", SERVER_DIR / "ppocr-server.py"
        )
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)
        from fastapi.testclient import (  # pylint: disable=import-outside-toplevel
            TestClient,
        )

        cls.client = TestClient(cls.mod.app)
        cls.img, cls.payload = sensitive_payload()
        ok, png = vision.cv2.imencode(".png", cls.img)
        assert ok
        cls.png = png.tobytes()

    def setUp(self):
        self.saved = report_store.STORE
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=R1732
        self.mod.DAILY = DailyLimit(limit=0, exempt="")
        self.mod._cache_get = lambda _key: None
        self.mod._cache_set = lambda _key, _payload: None

        async def decode(raw):
            return raw

        self.mod._decode_upload = decode
        payload = self.payload
        self.mod._report_python_process = lambda *_args: json.loads(
            json.dumps(payload)
        )
        report_store.STORE = report_store.ReportStore(self.tmp.name)

    def tearDown(self):
        report_store.STORE = self.saved
        self.tmp.cleanup()

    def check(self, include="text,evidence"):
        return self.client.post(
            "/api/v2/reports?format=compact&include=" + include,
            files={
                "image": ("Seetha-Rama-homework.png", self.png, "image/png")
            },
            data={"lang": "en", "expected_text": "Vidhya copies a story"},
            headers={"X-Forwarded-For": "203.0.113.7"},
        )

    def test_the_check_returns_a_receipt_and_its_text(self):
        res = self.check()
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("Bheema", body["text"])  # the family still sees it
        self.assertRegex(body["receipt"]["id"], r"^[0-9a-f]{32}$")
        contract_schemas.validate("report-compact", body)

    def test_every_byte_written_is_free_of_personal_data(self):
        receipts = [self.check().json()["receipt"] for _ in range(2)]
        receipts.append(self.check("evidence").json()["receipt"])
        files = files_under(self.tmp.name)
        self.assertEqual(len(files), 3)
        for path in files:
            self.assertRegex(os.path.basename(path), r"^[0-9a-f]{32}\.json$")
            with open(path, "rb") as fh:
                body = fh.read()
            for word in NAME_LINE.split() + SECRETS + ["203.0.113.7"]:
                self.assertNotIn(word.encode(), body, (path, word))
            for magic in (PNG_MAGIC, JPEG_MAGIC, b"data:", b"base64"):
                self.assertNotIn(magic, body)
            for receipt in receipts:
                self.assertNotIn(receipt["token"].encode(), body)
            # No time of day: the only date is the day of the check.
            self.assertFalse(re.search(rb"T\d\d:\d\d", body))

    def test_read_renew_and_delete_through_the_api(self):
        receipt = self.check().json()["receipt"]
        url = "/api/v2/reports/" + receipt["id"]
        self.assertEqual(self.client.get(url).status_code, 404)
        wrong = {"X-Report-Token": "A" * 43}
        self.assertEqual(self.client.get(url, headers=wrong).status_code, 404)
        token = {"X-Report-Token": receipt["token"]}
        res = self.client.get(url, headers=token)
        self.assertEqual(res.status_code, 200)
        contract_schemas.validate("stored-report", res.json())
        self.assertNotIn("Bheema", res.text)
        renewed = self.client.post(
            "/api/v2/reports/renew",
            json={"receipts": [receipt, {"id": "nope", "token": "x"}]},
        )
        self.assertEqual(renewed.json(), {"renewed": 1})
        self.assertEqual(
            self.client.delete(url, headers=token).status_code, 204
        )
        self.assertEqual(self.client.get(url, headers=token).status_code, 404)

    def test_same_photo_same_scores_in_every_record(self):
        first = self.check().json()["receipt"]
        second = self.check().json()["receipt"]
        a = report_store.STORE.read(first["id"], first["token"])
        b = report_store.STORE.read(second["id"], second["token"])
        for key in ("score", "factors", "sections", "comparability", "marks"):
            self.assertEqual(a.get(key), b.get(key), key)

    def test_off_returns_no_receipt_and_writes_nothing(self):
        report_store.STORE = report_store.ReportStore(None)
        body = self.check().json()
        self.assertNotIn("receipt", body)
        self.assertEqual(files_under(self.tmp.name), [])
        self.assertIs(self.mod.health()["report_store"], False)


if __name__ == "__main__":
    unittest.main()
