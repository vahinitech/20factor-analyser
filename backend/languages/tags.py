# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies. Server-side handwriting/print recognition.
#
# lang_tags.py: the request's `lang` in the form the reading engine knows.
# A caller may name a language as a BCP 47 tag with a script and a region
# (`te-Telu-IN`, `en-Latn-GB`); the engines are loaded by their short code
# (VAHINI_OCR_LANGS=en,te), so the server keeps only the language subtag.
# Every value the request schema allowed before (`auto`, one short code)
# comes back unchanged, so `te` and `te-Telu-IN` read, score and cache the
# same way. Design: docs/20-languages.md, sections 3 and 13 (#212).


def engine_lang(tag: str) -> str:
    """One tag to its engine code: `te-Telu-IN` -> `te`, `en` -> `en`."""
    return (tag or "").strip().lower().split("-", 1)[0]


def engine_langs(lang: str) -> str:
    """A request `lang` (`auto`, one tag, or a comma list of tags) with
    each tag reduced to its engine code: `en-Latn-GB,te-Telu-IN` ->
    `en,te`. Empty entries are dropped, as resolve_langs always did."""
    codes = [engine_lang(x) for x in (lang or "").split(",")]
    return ",".join(x for x in codes if x)
