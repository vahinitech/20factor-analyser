# SPDX-License-Identifier: AGPL-3.0-only
"""Internal access API: the only way another service changes the ledger.

The subscription ledger (``entitlements.py``) belongs to the analyser. A
service on the private network that sells, gives or takes back Pro calls
these routes instead of opening the SQLite file itself, so the ledger has
one writer and one documented contract (``backend/schemas/access-*``).

Every route is behind three guards, checked before routing or body
parsing so a refused caller learns nothing about the API:

1. Off unless ``VAHINI_ACCESS_API_TOKEN_FILE`` names a readable file
   holding a token of at least 32 characters: 404.
2. A request that came through a proxy (any forwarding header) is refused
   with 404. The public gateway adds these headers; a service talking to
   the container on the private network does not.
3. ``Authorization: Bearer <token>``, compared in constant time: 401.

The file is read on every request, so a token can be rotated without a
restart. Key secrets travel in request bodies only, never in a URL, and
no response contains a key digest.
"""

import hmac
import os
import sqlite3
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from server import entitlements

PREFIX = "/internal/access/v1"
TOKEN_FILE_ENV = "VAHINI_ACCESS_API_TOKEN_FILE"
TOKEN_MIN = 32
PROXY_HEADERS = (
    "x-forwarded-for",
    "x-real-ip",
    "forwarded",
    "cf-connecting-ip",
)
PRIVATE = {"Cache-Control": "no-store", "Vary": "Authorization"}

router = APIRouter(prefix=PREFIX)


def configured_token():
    """The shared token, or None when the API is switched off."""
    path = os.environ.get(TOKEN_FILE_ENV)
    if not path:
        return None
    try:
        with open(path, encoding="ascii") as handle:
            token = handle.read().strip()
    except (OSError, UnicodeDecodeError):
        return None
    return token if len(token) >= TOKEN_MIN else None


def refusal(headers):
    """(status, detail) for a refused request, or None to let it through."""
    token = configured_token()
    if token is None:
        return 404, "Not Found"
    if any(name in headers for name in PROXY_HEADERS):
        return 404, "Not Found"
    supplied = headers.get("authorization", "")
    expected = "Bearer " + token
    if not hmac.compare_digest(
        supplied.encode("utf-8", "replace"), expected.encode()
    ):
        return 401, "Invalid access API credential"
    return None


async def guard(request, call_next):
    """HTTP middleware: the three guards, then no-store on every answer."""
    if not request.url.path.startswith("/internal/"):
        return await call_next(request)
    refused = refusal(request.headers)
    if refused:
        status, detail = refused
        headers = dict(PRIVATE)
        if status == 401:
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse({"detail": detail}, status, headers=headers)
    response = await call_next(request)
    response.headers.update(PRIVATE)
    return response


def install(app):
    """Add the guard and the routes to an application."""
    app.middleware("http")(guard)
    app.include_router(router)


class Closed(BaseModel):
    """Request bodies reject fields they do not define (422)."""

    model_config = ConfigDict(extra="forbid")


class GrantRequest(Closed):
    expires_at: StrictInt = Field(gt=0)


class SubscriptionRequest(Closed):
    tier: Literal[entitlements.TIERS]
    status: Literal[entitlements.STATUSES]
    expires_at: Optional[StrictInt] = Field(default=None, gt=0)


class KeyLookupRequest(Closed):
    key: StrictStr = Field(min_length=1, max_length=200)


def ledger():
    path = os.environ.get("VAHINI_ENTITLEMENTS_DB")
    if not path:
        raise HTTPException(503, "Subscription service is not configured")
    return path


def call(function, *args):
    """Run one ledger operation and map its failures to HTTP answers."""
    try:
        return function(*args)
    except ValueError as error:
        message = str(error)
        status = 404 if message.startswith("Unknown") else 422
        raise HTTPException(status, message) from error
    except sqlite3.Error as error:
        raise HTTPException(
            503, "Subscription service is unavailable"
        ) from error


CUSTOMER_ID = Path(min_length=1, max_length=64)
KEY_ID = Path(min_length=1, max_length=64)


@router.post("/grants", status_code=201)
def create_grant(body: GrantRequest):
    """New customer with Pro until expires_at and its first key, at once."""
    return call(entitlements.grant, ledger(), body.expires_at)


@router.get("/customers/{customer_id}")
def read_customer(customer_id: str = CUSTOMER_ID):
    return call(entitlements.describe_customer, ledger(), customer_id)


@router.put("/customers/{customer_id}/subscription")
def change_subscription(
    body: SubscriptionRequest, customer_id: str = CUSTOMER_ID
):
    path = ledger()
    call(
        entitlements.set_subscription,
        path,
        customer_id,
        body.tier,
        body.status,
        body.expires_at,
    )
    return call(entitlements.describe_customer, path, customer_id)


@router.post("/customers/{customer_id}/keys", status_code=201)
def create_key(customer_id: str = CUSTOMER_ID):
    """Another key for an existing customer; the secret is shown once."""
    path = ledger()
    customer = call(entitlements.describe_customer, path, customer_id)
    key_id, token = call(entitlements.issue_key, path, customer_id)
    return {
        "customer_id": customer_id,
        "key_id": key_id,
        "key": token,
        "expires_at": customer["expires_at"],
    }


@router.post("/keys/{key_id}/revoke")
def revoke(key_id: str = KEY_ID):
    """Refused on its next lookup; answers with the owner's record."""
    path = ledger()
    customer_id = call(entitlements.revoke_key, path, key_id)
    return call(entitlements.describe_customer, path, customer_id)


@router.post("/keys/lookup")
def lookup(body: KeyLookupRequest):
    """Which key and customer a secret belongs to, read-only."""
    found = call(entitlements.find_key, ledger(), body.key)
    if found is None:
        raise HTTPException(404, "Unknown API key")
    return found
