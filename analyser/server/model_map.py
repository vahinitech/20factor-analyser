# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Shared "lang:model,lang:model" parsing.

Used by both the recognition server (ppocr-server.py, via
VAHINI_OCR_REC_MODEL_MAP) and the standalone warm-up script
(warmup_models.py), so the two can't drift out of sync on how that
environment variable is parsed.
"""


def parse_model_map(raw):
    """Parse "en:ModelA,te:ModelB" into {"en": "ModelA", "te": "ModelB"}.

    Blank/malformed tokens (no ":", empty key or value) are skipped.
    """
    out = {}
    for item in (raw or "").split(","):
        token = item.strip()
        if not token or ":" not in token:
            continue
        key, value = token.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key and value:
            out[key] = value
    return out
