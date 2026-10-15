# SPDX-License-Identifier: AGPL-3.0-only
"""Server-only provisioning. Never ship operator access in a mobile app."""

import argparse
import json
import os
import stat
import sys
from contextlib import suppress

from entitlements import (
    initialize,
    create_customer,
    describe_customer,
    find_key,
    issue_key,
    list_customers,
    revoke_key,
    set_subscription,
)

# access_for refuses a header over 200 characters, "Bearer " included.
MAX_SECRET = 193


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


def read_secret_file(secret_file):
    """Read a key from a private file without ever echoing it.

    The file must be a regular file owned by this user with no group or
    other permissions (0600 or stricter). Errors never include the text.
    """
    try:
        descriptor = os.open(secret_file, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise ValueError(
            f"Cannot open secret file: {error.strerror}"
        ) from error
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Secret file is not a regular file")
        if info.st_uid != os.geteuid():
            raise ValueError("Secret file is not owned by this user")
        if info.st_mode & 0o077:
            raise ValueError("Secret file must be mode 0600 or stricter")
        raw = source.read(MAX_SECRET + 2)
    try:
        secret = raw.decode("ascii").strip()
    except UnicodeDecodeError:
        raise ValueError("Secret file does not hold an API key") from None
    if not secret.startswith("vh_") or len(secret) > MAX_SECRET:
        raise ValueError("Secret file does not hold an API key")
    return secret


def check_key(path, secret_file):
    """What a key maps to, for support; the secret is never printed."""
    found = find_key(path, read_secret_file(secret_file))
    if found is None:
        return {"found": False}
    return {"found": True, **found}


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
    show = commands.add_parser("show-customer")
    show.add_argument("customer")
    listing = commands.add_parser("list-customers")
    listing.add_argument("--tier", choices=("free", "pro"))
    listing.add_argument("--expiring-within-days", type=int)
    check = commands.add_parser("check-key")
    check.add_argument("--secret-file", required=True)
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
    try:
        run(args)
    except ValueError as error:
        parser.exit(1, f"subscription_admin: {error}\n")


def run(args):
    """Carry out one parsed command."""
    if args.command == "init":
        initialize(args.db)
    elif args.command == "create-customer":
        print(json.dumps({"customer_id": create_customer(args.db)}))
    elif args.command == "issue-key":
        key_id = write_customer_key(args.db, args.customer, args.secret_file)
        print(json.dumps({"key_id": key_id, "secret_file": args.secret_file}))
    elif args.command == "revoke-key":
        revoke_key(args.db, args.key_id)
    elif args.command == "show-customer":
        print(json.dumps(describe_customer(args.db, args.customer), indent=2))
    elif args.command == "list-customers":
        days = args.expiring_within_days
        if days is not None and days < 0:
            raise ValueError("--expiring-within-days must be 0 or more")
        found = list_customers(
            args.db,
            tier=args.tier,
            expiring_within=None if days is None else days * 86400,
        )
        print(json.dumps({"count": len(found), "customers": found}, indent=2))
    elif args.command == "check-key":
        result = check_key(args.db, args.secret_file)
        print(json.dumps(result, indent=2))
        if not result["found"]:
            sys.exit(1)
    else:
        set_subscription(
            args.db, args.customer, args.tier, args.status, args.expires_at
        )


if __name__ == "__main__":
    main()
