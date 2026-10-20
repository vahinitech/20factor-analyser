# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Language packs (docs/20-languages.md). See registry.py."""

from .registry import DEFAULT_LANG, Pack, PackError, language, resolve

__all__ = ["DEFAULT_LANG", "Pack", "PackError", "language", "resolve"]
