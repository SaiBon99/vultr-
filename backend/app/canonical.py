"""Canonical JSON and payload hash (contracts/README.md wire rules 1 and 2)."""

import hashlib
import json
from typing import Any


def _reject_floats(obj: Any) -> None:
    if isinstance(obj, float):
        raise TypeError("floats are not allowed in canonical JSON")
    if isinstance(obj, dict):
        for v in obj.values():
            _reject_floats(v)
    elif isinstance(obj, list | tuple):
        for v in obj:
            _reject_floats(v)


def canon(obj: Any) -> str:
    _reject_floats(obj)
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def payload_hash(content: str) -> str:
    """`sha256:` + hex of utf8(content), content exactly as written."""
    return "sha256:" + sha256_hex(content)
