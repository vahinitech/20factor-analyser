# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Write this CI run's privacy test results for the website's status page.

    python scripts/privacy_results.py --out privacy-tests.json \\
        privacy-card=success check-page-who=failure print-popup=skipped

vahinitech.com lists five of our tests under "Privacy tests we run" on
/status.html (vahini-web docs/06-status-page.md). CI runs them on every
push to main, and this script records how each one came out, as the
`privacy-tests-*` artifacts the website's release fetches for the
analyser commit it ships.

Each argument is a test id and its GitHub step outcome. "success" is
"pass" and "failure" is "fail". Anything else (skipped after an earlier
step failed, cancelled, empty) is left out, so the page shows no result
rather than a guess. The file holds the ids, pass or fail and the UTC
time, and nothing else: the page is public, so no commit, path or log.
"""

import argparse
import datetime
import json
import sys

# The ids vahini-web's tools/privacy-tests-data.mjs gives these test files.
TESTS = {
    "privacy-card": "tests/privacy-card.mjs",
    "print-popup": "tests/print-popup.mjs",
    "check-page-who": "tests/check-page-who.mjs",
    "identifiers": "backend/tests/test_identifiers.py",
    "who-checks": "backend/tests/test_who_checks.py",
}
OUTCOME = {"success": "pass", "failure": "fail"}


def results(pairs):
    """Map id=outcome pairs to {id: "pass" | "fail"}; raise on a bad one."""
    out = {}
    for pair in pairs:
        test_id, sep, outcome = pair.partition("=")
        if not sep or test_id not in TESTS:
            raise ValueError(f"not a known privacy test: {pair!r}")
        if outcome in OUTCOME:
            out[test_id] = OUTCOME[outcome]
    return out


def record(pairs, now=None):
    """The results file for these pairs, finished at `now` (UTC)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return {
        "version": 1,
        "finished_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "results": results(pairs),
    }


def main(argv=None):
    """Write the file; exit 2 on an unknown id."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("pairs", nargs="*", metavar="id=outcome")
    args = parser.parse_args(argv)
    try:
        data = record(args.pairs)
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
