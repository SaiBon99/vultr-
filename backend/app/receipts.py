"""Ed25519 cleanup receipts and object storage (contracts/README.md wire rule 4)."""

import base64
import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.canonical import canon


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


class ObjectStore(Protocol):
    def put_json(self, key: str, body: bytes) -> str:
        """Store and return the object URI."""
        ...

    def get(self, key: str) -> bytes | None: ...

    def ping(self) -> bool: ...


class InMemoryObjectStore:
    def __init__(self, bucket: str = "quarantine-receipts") -> None:
        self.bucket = bucket
        self.objects: dict[str, bytes] = {}

    def put_json(self, key: str, body: bytes) -> str:
        self.objects[key] = body
        return f"s3://{self.bucket}/{key}"

    def get(self, key: str) -> bytes | None:
        return self.objects.get(key)

    def ping(self) -> bool:
        return True


class S3ObjectStore:
    """boto3 client for Vultr Object Storage or MinIO. Sync; call via a threadpool."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
    ) -> None:
        import boto3

        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    def put_json(self, key: str, body: bytes) -> str:
        self._client.put_object(
            Bucket=self.bucket, Key=key, Body=body, ContentType="application/json"
        )
        return f"s3://{self.bucket}/{key}"

    def get(self, key: str) -> bytes | None:
        try:
            return self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except self._client.exceptions.NoSuchKey:
            return None

    def ping(self) -> bool:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except Exception:
            return False
        return True
