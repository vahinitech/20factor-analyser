# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Write this CI run's privacy test results for the website's status page.

    python scripts/privacy_results.py --out privacy-tests.json \\
        --unittest-log unittest.log
    python scripts/privacy_results.py --out privacy-tests.json \\
        privacy-card=success check-page-who=failure print-popup=skipped

vahinitech.com lists some of our tests under "Privacy tests we run" on
/status.html (vahini-web docs/06-status-page.md). CI runs them on every
push to main, and this script records how each one came out, as the
`privacy-tests-*` artifacts the website's release fetches for the
analyser commit it ships.

Browser tests are given as id=outcome, from their GitHub steps: "success"
is "pass" and "failure" is "fail". Python test files are read from the
discovery run's output (--unittest-log), so nothing runs twice: a file
named in a FAIL or ERROR line failed, and a file that ran with neither
passed. Anything else (a step skipped after an earlier failure, a run that
never finished, a file that never ran) is left out, so the page shows no
result rather than a guess. The file holds the ids, pass or fail and the
UTC time, and nothing else: the page is public, so no commit, path or log.
"""

import argparse
import datetime
import json
import os
import re
import sys

# The ids vahini-web's tools/privacy-tests-data.mjs gives these test files.
TESTS = {
    "privacy-card": "tests/privacy-card.mjs",
    "print-popup": "tests/print-popup.mjs",
    "check-page-who": "tests/check-page-who.mjs",
    "identifiers": "backend/tests/test_identifiers.py",
    "who-checks": "backend/tests/test_who_checks.py",
    "reader-down": "backend/tests/test_regression_functional.py",
    "page-turn": "backend/tests/test_page_turn.py",
    "handwriting-only": "backend/tests/test_handwriting_only.py",
    "not-writing-page": "backend/tests/test_not_writing_page.py",
    "telugu-not-read": "backend/tests/test_telugu_not_read.py",
    "benchmark": "backend/tests/test_benchmark.py",
}
OUTCOME = {"success": "pass", "failure": "fail"}


def module_of(path):
    """test_x for backend/tests/test_x.py, None for a browser test."""
    if not path.startswith("backend/tests/"):
        return None
    return os.path.splitext(os.path.basename(path))[0]


def results(pairs):
    """Map id=outcome pairs to {id: "pass" | "fail"}; raise on a bad one."""
    out = {}
    for pair in pairs:
        test_id, sep, outcome = pair.partition("=")
        if not sep or test_id not in TESTS or module_of(TESTS[test_id]):
            raise ValueError(f"not a known browser privacy test: {pair!r}")
        if outcome in OUTCOME:
            out[test_id] = OUTCOME[outcome]
    return out


def unittest_results(log):
    """{id: "pass" | "fail"} for the Python files, from a -v discovery log.

    Nothing when the run did not finish (no "Ran N tests" line)."""
    if not re.search(r"^Ran \d+ tests? in ", log, re.MULTILINE):
        return {}
    failed = re.findall(r"^(?:FAIL|ERROR): .*$", log, re.MULTILINE)
    out = {}
    for test_id, path in TESTS.items():
        module = module_of(path)
        if not module:
            continue
        word = re.compile(rf"\b{re.escape(module)}\b")
        if any(word.search(line) for line in failed):
            out[test_id] = "fail"
        elif f"(backend.tests.{module}." in log:
            out[test_id] = "pass"
    return out


def record(pairs, log=None, now=None):
    """The results file for these pairs and log, finished at `now` (UTC)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    found = results(pairs)
    if log is not None:
        found.update(unittest_results(log))
    return {
        "version": 1,
        "finished_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "results": found,
    }


def main(argv=None):
    """Write the file; exit 2 on an unknown id."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--unittest-log")
    parser.add_argument("pairs", nargs="*", metavar="id=outcome")
    args = parser.parse_args(argv)
    log = None
    if args.unittest_log:
        try:
            with open(args.unittest_log, encoding="utf-8") as handle:
                log = handle.read()
        except OSError:
            log = ""  # the run never started: no results, not an error
    try:
        data = record(args.pairs, log)
    except ValueError as err:
        print(f"privacy_results: {err}", file=sys.stderr)
        return 2
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
        handle.write("\n")
    print(f"privacy_results: {json.dumps(data['results'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
