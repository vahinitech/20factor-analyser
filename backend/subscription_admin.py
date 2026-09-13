# SPDX-License-Identifier: AGPL-3.0-only
"""Server-only provisioning. Never ship operator access in a mobile app."""

import argparse
import json
import os
from contextlib import suppress

from entitlements import (
    initialize,
    create_customer,
    issue_key,
    revoke_key,
    set_subscription,
)


def write_customer_key(path, customer, secret_file):
    """Revoke an issued credential if its private delivery file fails."""
    descriptor = os.open(
        secret_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
    )
    key_id = None
    try:
        with os.fdopen(descriptor, "w") as output:
            key_id, secret = issue_key(path, customer)
            output.write(secret + "\n")
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        try:
            if key_id is not None:
                revoke_key(path, key_id)
        finally:
            with suppress(OSError):
                os.close(descriptor)
            with suppress(FileNotFoundError):
                os.unlink(secret_file)
        raise
    return key_id


def main():
    """Manage subscriptions locally; secrets are written to private files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    commands.add_parser("create-customer")
    key = commands.add_parser("issue-key")
    key.add_argument("customer")
    key.add_argument("--secret-file", required=True)
    revoke = commands.add_parser("revoke-key")
    revoke.add_argument("key_id")
    grant = commands.add_parser("subscription")
    grant.add_argument("customer")
    grant.add_argument("--tier", choices=("free", "pro"), required=True)
    grant.add_argument(
        "--status",
        choices=("active", "cancelled", "expired", "revoked"),
        required=True,
    )
    grant.add_argument("--expires-at", type=int)
    args = parser.parse_args()
    if args.command == "init":
        initialize(args.db)
    elif args.command == "create-customer":
        print(json.dumps({"customer_id": create_customer(args.db)}))
    elif args.command == "issue-key":
        key_id = write_customer_key(args.db, args.customer, args.secret_file)
        print(json.dumps({"key_id": key_id, "secret_file": args.secret_file}))
    elif args.command == "revoke-key":
        revoke_key(args.db, args.key_id)
    else:
        set_subscription(
            args.db, args.customer, args.tier, args.status, args.expires_at
        )


if __name__ == "__main__":
    main()
