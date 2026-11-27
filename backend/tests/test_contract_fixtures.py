"""Canonical JSON, audit chain and receipts reproduce contracts/fixtures."""

import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.audit import GENESIS_HASH, event_hash, format_ts, verify_chain
from app.canonical import canon, payload_hash
from app.models import (
    ActiveMemories,
    AuditLog,
    CreateSessionResponse,
    Health,
    MemoryWriteAccepted,
    MemoryWriteQuarantined,
    PublicKey,
    QuarantineList,
    Receipt,
)
from app.receipts import Signer, build_receipt, key_id_for, verify_receipt
from tests.conftest import FIXTURES, load_fixture

RECEIPT_FIXTURE = next((FIXTURES / "receipts").glob("*.json")).relative_to(FIXTURES).as_posix()


def test_canon_sorts_and_compacts():
    assert canon({"b": 1, "a": {"d": "é", "c": [2, 1]}}) == '{"a":{"c":[2,1],"d":"é"},"b":1}'


def test_canon_rejects_floats():
    with pytest.raises(TypeError):
        canon({"a": 1.5})


def test_payload_hash_known_value():
    assert payload_hash("") == (
        "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_format_ts_microseconds_z():
    from datetime import UTC, datetime

    assert format_ts(datetime(2026, 1, 2, 3, 4, 5, 6, tzinfo=UTC)) == "2026-01-02T03:04:05.000006Z"
    with pytest.raises(ValueError):
        format_ts(datetime(2026, 1, 2))


def test_audit_valid_chain():
    log = load_fixture("audit.json")
    res = verify_chain(log["events"])
    assert res.valid is True
    assert res.first_invalid_seq is None
    assert res.head_hash == log["head_hash"]


def test_audit_broken_chain_first_invalid_seq_5():
    log = load_fixture("audit_broken.json")
    res = verify_chain(log["events"])
    assert res.valid is False
    assert res.first_invalid_seq == 5
    assert (log["chain_valid"], log["first_invalid_seq"]) == (False, 5)


def test_event_hash_reproduces_first_event():
    ev = load_fixture("audit.json")["events"][0]
    assert ev["prev_hash"] == GENESIS_HASH
    got = event_hash(
        GENESIS_HASH,
        session_id=ev["session_id"],
        event_type=ev["event_type"],
        target_id=ev["target_id"],
        payload=ev["payload"],
        created_at=ev["created_at"],
    )
    assert got == ev["event_hash"]


def _fixture_pub() -> Ed25519PublicKey:
    key = load_fixture("keys_public.json")
    raw = base64.b64decode(key["public_key_b64"])
    assert key_id_for(Ed25519PublicKey.from_public_bytes(raw)) == key["key_id"]
    return Ed25519PublicKey.from_public_bytes(raw)


def test_signed_receipt_fixture_verifies():
    assert verify_receipt(load_fixture(RECEIPT_FIXTURE), _fixture_pub()) is True


def test_tampered_receipt_fixture_fails():
    assert verify_receipt(load_fixture("receipt_tampered.json"), _fixture_pub()) is False


def test_sign_roundtrip_and_tamper(key_path):
    signer = Signer.from_path(key_path)
    unsigned = build_receipt(
        event="purged",
        quarantine_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
        session_id="6f1d2c3b-0a4e-4b5f-8c7d-1e2f3a4b5c6d",
        verdict="POLICY_BLOCKED",
        rule_flags=["imperative_directive"],
        payload_hash=payload_hash("x"),
        audit_head_hash=GENESIS_HASH,
        override_reason=None,
    )
    receipt = signer.sign(unsigned)
    Receipt.model_validate(receipt)
    assert verify_receipt(receipt, signer.public_key)
    assert not verify_receipt({**receipt, "verdict": "INCONCLUSIVE"}, signer.public_key)


@pytest.mark.parametrize(
    ("name", "model"),
    [
        ("health.json", Health),
        ("keys_public.json", PublicKey),
        ("quarantine.json", QuarantineList),
        ("audit.json", AuditLog),
        ("audit_broken.json", AuditLog),
        ("memory_active.json", ActiveMemories),
        ("session_create.json", CreateSessionResponse),
        ("write_quarantined.json", MemoryWriteQuarantined),
        ("write_accepted.json", MemoryWriteAccepted),
        (RECEIPT_FIXTURE, Receipt),
        ("receipt_tampered.json", Receipt),
    ],
)
def test_models_validate_fixtures(name, model):
    model.model_validate(load_fixture(name))
