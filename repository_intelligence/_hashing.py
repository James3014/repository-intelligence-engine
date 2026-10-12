"""Canonical JSON identity hash for hash-bound advisory evidence.

Compatible with the existing receipt and report identity format: the self-hash
field is excluded, keys are sorted, JSON is compact and ASCII-escaped, and the
UTF-8 bytes are SHA-256 hashed. Changing these rules requires a schema migration.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence


def content_hash(
    payload: Mapping[str, Any],
    *,
    exclude: Sequence[str] = ("content_sha256",),
) -> str:
    unsigned = dict(payload)
    for key in exclude:
        unsigned.pop(key, None)
    canonical = json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hash_payload(
    payload: Mapping[str, Any],
    *,
    exclude: Sequence[str] = ("content_sha256",),
) -> str:
    """Equivalent compatibility alias with an explicit exclusion policy."""
    return content_hash(payload, exclude=exclude)
