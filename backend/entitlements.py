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
    """Return the secret once; only its SHA-256 digest enters the ledger.

    The audit row names the key id only, never the secret or its digest.
    """
    token = "vh_" + secrets.token_urlsafe(32)
    key_id = "key_" + secrets.token_hex(12)
    now = int(time.time())
    with closing(connect(path)) as connection, connection:
        connection.execute(
            "INSERT INTO api_keys(id, customer_id, digest, created_at) VALUES (?, ?, ?, ?)",
            (
                key_id,
                customer_id,
                hashlib.sha256(token.encode()).hexdigest(),
                now,
            ),
        )
        connection.execute(
            "INSERT INTO audit(customer_id, action, created_at) VALUES (?, ?, ?)",
            (customer_id, f"key:issue:{key_id}", now),
        )
    return key_id, token


def revoke_key(path, key_id):
    """Revocation takes effect on the next entitlement lookup."""
    with closing(connect(path)) as connection, connection:
        row = connection.execute(
            "SELECT customer_id FROM api_keys WHERE id=?", (key_id,)
        ).fetchone()
        if not row:
            raise ValueError("Unknown API key")
        connection.execute(
            "UPDATE api_keys SET revoked=1 WHERE id=?", (key_id,)
        )
        connection.execute(
            "INSERT INTO audit(customer_id, action, created_at) VALUES (?, ?, ?)",
            (row["customer_id"], f"key:revoke:{key_id}", int(time.time())),
        )


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


def effective_access(row, now=None):
    """The access a customer row grants now; access_for and the CLI agree."""
    now = time.time() if now is None else now
    active = row["status"] in ("active", "cancelled")
    expired = row["expires_at"] is not None and row["expires_at"] <= now
    pro = (
        row["tier"] == "pro"
        and active
        and not expired
        and row["expires_at"] is not None
    )
    return {
        "customer_id": row["id"],
        "tier": "pro" if pro else "free",
        "plan_tier": row["tier"],
        "subscription_status": "expired" if expired else row["status"],
        "expires_at": row["expires_at"],
    }


def connect_readonly(path):
    """Open the ledger for operator lookups that must never write."""
    connection = sqlite3.connect(
        Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=10
    )
    connection.row_factory = sqlite3.Row
    return connection


def list_customers(path, tier=None, expiring_within=None, now=None):
    """Every customer's plan, effective access and key counts, read-only.

    `tier` keeps customers whose effective tier is "pro" or "free";
    `expiring_within` (seconds) keeps Pro customers whose period ends
    within that time from now. Sorted by expiry, then id. No key ids,
    digests or audit rows: show-customer gives those for one customer.
    """
    now = time.time() if now is None else now
    with closing(connect_readonly(path)) as connection:
        rows = connection.execute("SELECT * FROM customers").fetchall()
        counts = {
            (row["customer_id"], row["revoked"]): row["n"]
            for row in connection.execute(
                "SELECT customer_id, revoked, COUNT(*) AS n FROM api_keys"
                " GROUP BY customer_id, revoked"
            )
        }
    out = []
    for row in rows:
        effective = effective_access(row, now)
        if tier is not None and effective["tier"] != tier:
            continue
        if expiring_within is not None and not (
            effective["tier"] == "pro"
            and row["expires_at"] <= now + expiring_within
        ):
            continue
        out.append(
            {
                "customer_id": row["id"],
                "tier": row["tier"],
                "status": row["status"],
                "expires_at": row["expires_at"],
                "updated_at": row["updated_at"],
                "effective_tier": effective["tier"],
                "subscription_status": effective["subscription_status"],
                "keys_active": counts.get((row["id"], 0), 0),
                "keys_revoked": counts.get((row["id"], 1), 0),
            }
        )
    out.sort(
        key=lambda c: (
            c["expires_at"] is None,
            c["expires_at"] or 0,
            c["customer_id"],
        )
    )
    return out


def describe_customer(path, customer_id):
    """Plan, effective access, keys and audit history for one customer.

    Read-only. Key digests are never returned.
    """
    with closing(connect_readonly(path)) as connection:
        row = connection.execute(
            "SELECT * FROM customers WHERE id=?", (customer_id,)
        ).fetchone()
        if not row:
            raise ValueError("Unknown customer")
        keys = connection.execute(
            "SELECT id, revoked, created_at FROM api_keys"
            " WHERE customer_id=? ORDER BY created_at, id",
            (customer_id,),
        ).fetchall()
        audit = connection.execute(
            "SELECT action, created_at FROM audit"
            " WHERE customer_id=? ORDER BY id",
            (customer_id,),
        ).fetchall()
    return {
        "customer_id": row["id"],
        "tier": row["tier"],
        "status": row["status"],
        "expires_at": row["expires_at"],
        "updated_at": row["updated_at"],
        "effective": effective_access(row),
        "keys": [
            {
                "key_id": key["id"],
                "revoked": bool(key["revoked"]),
                "created_at": key["created_at"],
            }
            for key in keys
        ],
        "audit": [
            {"action": entry["action"], "created_at": entry["created_at"]}
            for entry in audit
        ],
    }


def find_key(path, secret):
    """Map a secret to its key and customer by digest, read-only.

    Returns None when no key has this digest. A revoked key is reported
    with access None, since access_for refuses it.
    """
    digest = hashlib.sha256(secret.encode()).hexdigest()
    with closing(connect_readonly(path)) as connection:
        key = connection.execute(
            "SELECT id, customer_id, revoked, created_at FROM api_keys"
            " WHERE digest=?",
            (digest,),
        ).fetchone()
        if not key:
            return None
        row = connection.execute(
            "SELECT * FROM customers WHERE id=?", (key["customer_id"],)
        ).fetchone()
    return {
        "key_id": key["id"],
        "customer_id": key["customer_id"],
        "revoked": bool(key["revoked"]),
        "created_at": key["created_at"],
        "access": None if key["revoked"] else effective_access(row),
    }


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
    result.update(effective_access(row), authenticated=True)
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
