# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Names, phone numbers, emails, schools and roll numbers are blanked in
every text a scan sends back or caches (reading/identifiers.py, DPDP
Act section 6(1)), and nothing else in the payload changes."""

import copy
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reading import identifiers  # noqa: E402
from backend.tests.test_comparison_data import read_payload  # noqa: E402

PAGE = (
    "My name is Bheema Rao.\n"
    "I study at Sunrise Public School, roll no 23.\n"
    "Call 98480 12345 or write to papa.rao@example.com\n"
    "Pihu can fly over the tall tree."
)
GONE = (
    "Bheema",
    "Rao",
    "Sunrise",
    "no 23",
    "98480",
    "12345",
    "papa.rao",
    "example.com",
)


class Blank(unittest.TestCase):
    def test_a_page_about_its_writer_keeps_none_of_it(self):
        out = identifiers.blank(PAGE)
        for text in GONE:
            self.assertNotIn(text, out, text)
        for label in ("[name]", "[school]", "[roll number]", "[phone]"):
            self.assertIn(label, out)
        self.assertIn("[email]", out)
        # The rest of the page is the page.
        self.assertIn("Pihu can fly over the tall tree.", out)

    def test_ordinary_sentences_are_left_alone(self):
        for text in (
            "I am happy today.",
            "I am Going to the market.",
            "The cat sat on the mat.",
            "Pihu has 3 feathers and 12 eggs.",
            "My name is written below.",
        ):
            self.assertEqual(identifiers.blank(text), text)

    def test_other_ways_a_page_names_its_writer(self):
        cases = {
            "Name: Tara": "Tara",
            "Name - Seetha Devi": "Seetha",
            "I'm Chinnu and I like mangoes": "Chinnu",
            "Phone +91 98480-12345": "98480",
            "Roll Number: A17": "A17",
            "Kendriya Vidyalaya Uppal": "Kendriya",
        }
        for text, gone in cases.items():
            self.assertNotIn(gone, identifiers.blank(text), text)

    def test_a_counting_line_is_not_a_phone_number(self):
        for text in (
            "1 2 3 4 5 6 7 8 9 10",
            "11 12 13 14 15 16 17 18 19 20",
            "10 20 30 40 50 60 70 80 90 100",
            "12345678910",
            "Pihu counted 2 4 6 8 10 12 14 16 18 20 berries.",
        ):
            self.assertEqual(identifiers.blank(text), text)

    def test_an_indian_mobile_number_is_blanked(self):
        for text in (
            "9848012345",
            "98480 12345",
            "98480-12345",
            "98480.12345",
            "+91 98480 12345",
            "+91-9848012345",
            "09848012345",
            "040-2345-6789",
        ):
            self.assertEqual(
                identifiers.blank(f"Call {text} today"),
                "Call [phone] today",
                text,
            )

    def test_number_words_and_school_words_are_not_names(self):
        for text in (
            "I am Seven years old.",
            "I am SEVEN years old.",
            "I am Ten.",
            "I am The best writer.",
            "I am Studying in Class Four.",
            "Name: Class Three",
        ):
            self.assertEqual(identifiers.blank(text), text)
        # A name after them is still a name.
        self.assertEqual(
            identifiers.blank("My name is Tara. I am Seven."),
            "My name is [name]. I am Seven.",
        )

    def test_a_name_found_once_is_blanked_wherever_it_appears(self):
        found = identifiers.find(PAGE)
        self.assertEqual(identifiers.blank("Bheema", found), "[name]")
        self.assertEqual(identifiers.blank("Bheemaraju", found), "Bheemaraju")


class Payload(unittest.TestCase):
    def payload(self):
        p = read_payload(PAGE)
        p["hand_lines"] = [
            {"text": line, "box": [0, i * 40, 300, 30], "score": 0.9}
            for i, line in enumerate(PAGE.split("\n"))
        ]
        p["rec_texts"] = PAGE.split("\n")
        p["language"] = {
            "lines": [
                {
                    "tokens": [
                        {"text": "My", "status": "word"},
                        {"text": "name", "status": "word"},
                        {"text": "is", "status": "word"},
                        {"text": "Bheema", "status": "word"},
                    ]
                }
            ]
        }
        return p

    def test_every_text_in_the_payload_is_blanked(self):
        out = identifiers.blank_payload(self.payload())
        body = json.dumps(out)
        for text in GONE:
            self.assertNotIn(text, body, text)
        self.assertEqual(
            out["language"]["lines"][0]["tokens"][3]["text"], "[name]"
        )

    def test_spelling_and_grammar_lists_are_blanked_alike(self):
        # The shape reading/language_check.py returns: each finding holds
        # what was written and what was meant.
        p = self.payload()
        p["language"].update(
            {
                "spelling": [
                    {"written": "Bheema", "suggestion": "Bheema", "kind": "x"}
                ],
                "grammar": [
                    {
                        "rule": "agreement",
                        "written": "Rao go",
                        "suggestion": "Rao goes",
                    }
                ],
            }
        )
        out = identifiers.blank_payload(p)["language"]
        self.assertEqual(
            out["grammar"][0],
            {
                "rule": "agreement",
                "written": "[name] go",
                "suggestion": "[name] goes",
            },
        )
        self.assertEqual(out["spelling"][0]["written"], "[name]")
        self.assertEqual(out["spelling"][0]["suggestion"], "[name]")
        self.assertEqual(out["spelling"][0]["kind"], "x")

    def test_scores_boxes_and_counts_do_not_change(self):
        before = self.payload()
        out = identifiers.blank_payload(copy.deepcopy(before))
        self.assertEqual(
            out["analysis"]["results"], before["analysis"]["results"]
        )
        self.assertEqual(
            [line["box"] for line in out["hand_lines"]],
            [line["box"] for line in before["hand_lines"]],
        )
        self.assertEqual(len(out["rec_texts"]), len(before["rec_texts"]))

    def test_the_input_is_not_changed(self):
        before = self.payload()
        kept = copy.deepcopy(before)
        identifiers.blank_payload(before)
        self.assertEqual(before, kept)


class ScanRoute(unittest.TestCase):
    """The real _report_payload: what the scan returns is blanked before
    the cache keeps it and before any report is built from it."""

    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "server/app.py"
        spec = importlib.util.spec_from_file_location("ident_server", path)
        cls.server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.server)

    def test_the_cache_and_the_answer_hold_no_name(self):
        server = self.server
        scanned = dict(read_payload(PAGE), ok=True)
        mocks = {
            "_read_upload": AsyncMock(return_value=b"photo-bytes-1"),
            "_decode_upload": AsyncMock(return_value=np.zeros((4, 4, 3))),
        }
        env = {
            "VAHINI_OCR_PRELOAD_ON_START": "0",
            "VAHINI_REQUIRE_WHO": "0",
            "VAHINI_ENFORCE_TIERS": "0",
        }
        with patch.multiple(server, **mocks), patch.object(
            server.scan_slots, "run", new=AsyncMock(return_value=scanned)
        ), patch.dict(os.environ, env):
            with TestClient(server.app) as client:
                answer = client.post(
                    "/report-python",
                    files={"image": ("test.png", b"synthetic")},
                )
            body = json.dumps(answer.json())
            cached = json.dumps(
                list(server.cache._CACHE.values()), default=str
            )
        for text in GONE:
            self.assertNotIn(text, body, text)
            self.assertNotIn(text, cached, text)


if __name__ == "__main__":
    unittest.main()
