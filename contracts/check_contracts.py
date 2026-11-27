"""Contract self-check: fixtures match openapi.yaml schemas; Python canonical JSON, hash chain and
Ed25519 receipt verification agree with fixtures/generate.mjs. Exit 0 = contracts consistent.

Run from repo root:
  uv run --no-project --with jsonschema --with pyyaml --with cryptography python contracts/check_contracts.py
"""
import base64, hashlib, json, sys
from pathlib import Path

import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent
FX = ROOT / "fixtures"
GENESIS = "sha256:" + "0" * 64


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()


def load(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


spec = yaml.safe_load((ROOT / "openapi.yaml").read_text(encoding="utf-8"))
registry = Registry().with_resource("urn:openapi", Resource.from_contents(spec, default_specification=__import__("referencing.jsonschema").jsonschema.DRAFT202012))


def validate(name, schema_name, data=None):
    data = load(name) if data is None else data
    v = Draft202012Validator({"$ref": f"urn:openapi#/components/schemas/{schema_name}"}, registry=registry)
    errs = sorted(v.iter_errors(data), key=lambda e: e.path)
    for e in errs:
        print(f"FAIL {name} vs {schema_name}: {list(e.path)} {e.message}")
    return not errs


ok = True
receipt_name = next((FX / "receipts").glob("*.json")).relative_to(FX).as_posix()
for name, schema in [
    ("health.json", "Health"), ("keys_public.json", "PublicKey"), ("quarantine.json", "QuarantineList"),
    ("audit.json", "AuditLog"), ("audit_broken.json", "AuditLog"), ("memory_active.json", "ActiveMemories"),
    ("session_create.json", "CreateSessionResponse"), ("write_quarantined.json", "MemoryWriteQuarantined"),
    ("write_accepted.json", "MemoryWriteAccepted"), (receipt_name, "Receipt"), ("receipt_tampered.json", "Receipt"),
]:
    ok &= validate(name, schema)

receipt_schema = json.loads((ROOT / "receipt.schema.json").read_text(encoding="utf-8"))
for e in Draft202012Validator(receipt_schema).iter_errors(load(receipt_name)):
    ok = False; print("FAIL receipt.schema.json:", e.message)


def chain_valid(events):
    prev = GENESIS
    for ev in events:
        body = {k: ev[k] for k in ("session_id", "event_type", "target_id", "payload", "created_at")}
        if ev["prev_hash"] != prev or ev["event_hash"] != sha(prev + "|" + canon(body)):
            return False, ev["seq"]
        prev = ev["event_hash"]
    return True, None


for name in ("audit.json", "audit_broken.json"):
    log = load(name)
    valid, bad = chain_valid(log["events"])
    if (valid, bad) != (log["chain_valid"], log["first_invalid_seq"]):
        ok = False; print(f"FAIL {name}: computed chain_valid={valid} first_invalid_seq={bad}")

key = load("keys_public.json")
pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(key["public_key_b64"]))
if hashlib.sha256(base64.b64decode(key["public_key_b64"])).hexdigest()[:16] != key["key_id"]:
    ok = False; print("FAIL key_id does not match public key")


def verify(r):
    unsigned = {k: v for k, v in r.items() if k != "signature_b64"}
    try:
        pub.verify(base64.b64decode(r["signature_b64"]), canon(unsigned).encode("utf-8")); return True
    except Exception:
        return False


if not verify(load(receipt_name)):
    ok = False; print("FAIL signed receipt does not verify")
if verify(load("receipt_tampered.json")):
    ok = False; print("FAIL tampered receipt verifies")

print("contracts OK" if ok else "contracts FAILED")
sys.exit(0 if ok else 1)
