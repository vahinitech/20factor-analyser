# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies. Server-side handwriting/print recognition.
# Third-party: PaddleOCR (Apache-2.0). See /THIRD-PARTY-NOTICES.md and server/README.md
#
# cache.py — response cache for the /ocr, /analyze-vl and /report-python
# endpoints: TTL + max-item eviction, keyed by endpoint + language + extra
# context + a hash of the raw upload. Configure once at startup via
# configure(); ttl_sec=0 disables caching entirely.

import copy
import hashlib
import threading
import time

_CACHE = {}
_LOCK = threading.Lock()

_CFG = {
    "ttl_sec": 180,
    "max_items": 128,
}


def configure(**kwargs):
    """Set the cache's TTL/size limits once at startup. Unknown keys are
    ignored so callers can pass a superset of _CFG."""
    for k, v in kwargs.items():
        if k in _CFG:
            _CFG[k] = v


def cache_key(endpoint: str, raw: bytes, lang: str, extra: str = "") -> str:
    h = hashlib.sha1(raw).hexdigest()
    return f"{endpoint}|{(lang or '').strip().lower()}|{extra}|{h}"


def cache_get(key: str):
    if _CFG["ttl_sec"] <= 0:
        return None
    now = time.time()
    with _LOCK:
        row = _CACHE.get(key)
        if not row:
            return None
        exp, payload = row
        if exp < now:
            _CACHE.pop(key, None)
            return None
        return copy.deepcopy(payload)


def cache_set(key: str, payload):
    if _CFG["ttl_sec"] <= 0:
        return
    now = time.time()
    with _LOCK:
        if len(_CACHE) >= _CFG["max_items"]:
            # Drop oldest by expiry timestamp.
            oldest = sorted(_CACHE.items(), key=lambda kv: kv[1][0])[
                : max(1, _CFG["max_items"] // 8)
            ]
            for k, _ in oldest:
                _CACHE.pop(k, None)
        _CACHE[key] = (now + _CFG["ttl_sec"], copy.deepcopy(payload))


def with_meta(payload: dict, cache_status: str, t0: float):
    out = dict(payload)
    out["_meta"] = {
        "cache": cache_status,
        "elapsed_ms": int(round((time.perf_counter() - t0) * 1000.0)),
    }
    return out
