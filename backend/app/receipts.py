"""Ed25519 cleanup receipts (contracts/README.md wire rule 4). Stores live in app.storage."""

import base64
import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.canonical import canon
from app.storage import InMemoryObjectStore, ObjectStore, S3ObjectStore  # noqa: F401


def raw_public_bytes(pub: Ed25519PublicKey) -> bytes:
    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def key_id_for(pub: Ed25519PublicKey) -> str:
    return hashlib.sha256(raw_public_bytes(pub)).hexdigest()[:16]


def _b64url_nopad(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def receipt_object_key(receipt_id: str) -> str:
    return f"receipts/{receipt_id}.json"


def now_second_ts() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_receipt(
    *,
    event: str,
    quarantine_id: str,
    session_id: str,
    verdict: str,
    rule_flags: list[str],
    payload_hash: str,
    audit_head_hash: str,
    override_reason: str | None,
    timestamp: str | None = None,
    receipt_id: str | None = None,
) -> dict[str, Any]:
    """Unsigned receipt body (key_id and signature_alg are added by Signer.sign)."""
    return {
        "receipt_id": receipt_id or str(uuid.uuid4()),
        "event": event,
        "quarantine_id": quarantine_id,
        "session_id": session_id,
        "verdict": verdict,
        "rule_flags": list(rule_flags),
        "payload_hash": payload_hash,
        "audit_head_hash": audit_head_hash,
        "override_reason": override_reason,
        "timestamp": timestamp or now_second_ts(),
    }


class Signer:
    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._key = private_key
        self.public_key = private_key.public_key()
        self.key_id = key_id_for(self.public_key)

    @classmethod
    def from_path(cls, path: str | Path) -> "Signer":
        """Load a PEM private key, or a raw 32-byte / base64 seed."""
        data = Path(path).read_bytes()
        if data.lstrip().startswith(b"-----BEGIN"):
            key = serialization.load_pem_private_key(data, password=None)
        elif len(data) == 32:
            key = Ed25519PrivateKey.from_private_bytes(data)
        else:
            key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(data.strip()))
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("signing key is not Ed25519")
        return cls(key)

    def public_key_doc(self) -> dict[str, Any]:
        raw = raw_public_bytes(self.public_key)
        return {
            "alg": "Ed25519",
            "key_id": self.key_id,
            "public_key_b64": base64.b64encode(raw).decode("ascii"),
            "jwk": {"kty": "OKP", "crv": "Ed25519", "x": _b64url_nopad(raw)},
        }

    def sign(self, unsigned: dict[str, Any]) -> dict[str, Any]:
        body = {**unsigned, "key_id": self.key_id, "signature_alg": "Ed25519"}
        sig = self._key.sign(canon(body).encode("utf-8"))
        return {**body, "signature_b64": base64.b64encode(sig).decode("ascii")}


def verify_receipt(receipt: dict[str, Any], public_key: Ed25519PublicKey) -> bool:
    try:
        unsigned = {k: v for k, v in receipt.items() if k != "signature_b64"}
        public_key.verify(base64.b64decode(receipt["signature_b64"]), canon(unsigned).encode())
    except Exception:
        return False
    return True
