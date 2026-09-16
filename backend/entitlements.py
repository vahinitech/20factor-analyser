# SPDX-License-Identifier: AGPL-3.0-only
"""Server-owned customer entitlements and revocable, hashed API credentials."""

import hashlib
import os
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from fastapi import HTTPException

FREE_FACTORS = (1, 5, 7, 8, 18)
SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
 id TEXT PRIMARY KEY, tier TEXT NOT NULL DEFAULT 'free',
 status TEXT NOT NULL DEFAULT 'active', expires_at INTEGER,
 updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS api_keys (
 id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id),
 digest TEXT NOT NULL UNIQUE, revoked INTEGER NOT NULL DEFAULT 0,
 created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, customer_id TEXT NOT NULL,
 action TEXT NOT NULL, created_at INTEGER NOT NULL
);
"""


def connect(path):
    """Open an existing ledger; HTTP requests never create one implicitly."""
    connection = sqlite3.connect(
        Path(path).resolve().as_uri() + "?mode=rw", uri=True, timeout=10
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def initialize(path):
    """Explicit operator setup, with private file permissions."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(target, os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(descriptor)
    os.chmod(target, 0o600)
    with closing(connect(path)) as connection, connection:
        connection.executescript(SCHEMA)


def create_customer(path):
    """Issue an opaque identity without storing student names or scans."""
    customer_id = "cus_" + secrets.token_hex(12)
    with closing(connect(path)) as connection, connection:
        connection.execute(
            "INSERT INTO customers(id, updated_at) VALUES (?, ?)",
            (customer_id, int(time.time())),
        )
    return customer_id


def issue_key(path, customer_id):
    """Return the secret once; only its SHA-256 digest enters the ledger."""
    token = "vh_" + secrets.token_urlsafe(32)
    key_id = "key_" + secrets.token_hex(12)
    with closing(connect(path)) as connection, connection:
        connection.execute(
            "INSERT INTO api_keys(id, customer_id, digest, created_at) VALUES (?, ?, ?, ?)",
            (
                key_id,
                customer_id,
                hashlib.sha256(token.encode()).hexdigest(),
                int(time.time()),
            ),
        )
    return key_id, token


def revoke_key(path, key_id):
    """Revocation takes effect on the next entitlement lookup."""
    with closing(connect(path)) as connection, connection:
        changed = connection.execute(
            "UPDATE api_keys SET revoked=1 WHERE id=?", (key_id,)
        ).rowcount
        if not changed:
            raise ValueError("Unknown API key")


def set_subscription(path, customer_id, tier, status, expires_at=None):
    """Operator-only provisioner, also usable after verified billing events.

    No public route calls this function. Active and cancelled Pro grants
    require an explicit end time; cancelled grants retain access until then.
    """
    if tier not in ("free", "pro") or status not in (
        "active",
        "cancelled",
        "expired",
        "revoked",
    ):
        raise ValueError("Unsupported subscription state")
    if tier == "pro" and (type(expires_at) is not int or expires_at <= 0):
        raise ValueError("Pro requires an explicit expiry timestamp")
    now = int(time.time())
    with closing(connect(path)) as connection, connection:
        changed = connection.execute(
            "UPDATE customers SET tier=?, status=?, expires_at=?, updated_at=? WHERE id=?",
            (tier, status, expires_at, now, customer_id),
        ).rowcount
        if not changed:
            raise ValueError("Unknown customer")
        connection.execute(
            "INSERT INTO audit(customer_id, action, created_at) VALUES (?, ?, ?)",
            (customer_id, f"subscription:{tier}:{status}:{expires_at}", now),
        )


def access_for(authorization=None):
    """Never trust a client-provided tier, customer ID or purchase claim."""
    result = {
        "customer_id": None,
        "authenticated": False,
        "tier": "free",
        "plan_tier": "free",
        "subscription_status": "anonymous",
        "expires_at": None,
    }
    if not authorization:
        return result
    if not authorization.startswith("Bearer vh_") or len(authorization) > 200:
        raise HTTPException(401, "Invalid API credential")
    path = os.environ.get("VAHINI_ENTITLEMENTS_DB")
    if not path:
        raise HTTPException(503, "Subscription service is not configured")
    digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
    try:
        with closing(connect(path)) as connection:
            row = connection.execute(
                "SELECT c.* FROM customers c JOIN api_keys k ON k.customer_id=c.id WHERE k.digest=? AND k.revoked=0",
                (digest,),
            ).fetchone()
    except sqlite3.Error as error:
        raise HTTPException(
            503, "Subscription service is unavailable"
        ) from error
    if not row:
        raise HTTPException(401, "Invalid API credential")
    active = row["status"] in ("active", "cancelled")
    expired = (
        row["expires_at"] is not None and row["expires_at"] <= time.time()
    )
    pro = (
        row["tier"] == "pro"
        and active
        and not expired
        and row["expires_at"] is not None
    )
    result.update(
        customer_id=row["id"],
        authenticated=True,
        tier="pro" if pro else "free",
        plan_tier=row["tier"],
        subscription_status="expired" if expired else row["status"],
        expires_at=row["expires_at"],
    )
    return result


def capabilities(access):
    """One access policy for the JSON API and compatibility report."""
    pro = access["tier"] == "pro"
    return {
        "factor_numbers": list(range(1, 21)) if pro else list(FREE_FACTORS),
        "detailed_evidence": pro,
        "coaching": pro,
        "personalised_worksheets": pro,
    }
