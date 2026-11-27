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
    ("write_accepted.json", "MemoryWriteAccepted"), ("demo_runs.json", "DemoRunList"), (receipt_name, "Receipt"), ("receipt_tampered.json", "Receipt"),
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

# Rulebook: every fixture verdict and risk_score must follow x-rulebook in openapi.yaml.
rb = spec["components"]["schemas"]["RuleFlag"]["x-rulebook"]
if sorted(rb["flags"]) != sorted(spec["components"]["schemas"]["RuleFlag"]["enum"]) or len(rb["flags"]) != 13:
    ok = False; print("FAIL x-rulebook flags do not match the 13 RuleFlag values")


def expected(flags):
    tiers = {rb["flags"][f]["verdict"] for f in flags}
    verdict = next((v for v in rb["precedence"] if v in tiers), "ALLOW")
    score = min(100, sum(rb["flags"][f]["weight"] for f in flags))
    return verdict, max(rb["fail_closed_floor"], score) if verdict == "FAIL_CLOSED" else score


def check_row(where, verdict, score, flags):
    global ok
    pre = [f for f in flags if f != "judge_failed"]
    if "judge_failed" in flags and expected(pre)[0] in ("NEEDS_REVIEW", "BLOCKED"):
        v0, s0 = expected(pre)  # post-freeze escalation: NEEDS_REVIEW -> FAIL_CLOSED (floor), BLOCKED unchanged
        want = ("FAIL_CLOSED", max(rb["fail_closed_floor"], s0)) if v0 == "NEEDS_REVIEW" else (v0, s0)
    else:
        want = expected(flags)
    if (verdict, score) != want:
        ok = False; print(f"FAIL {where}: verdict/risk_score {(verdict, score)} != rulebook {want}")


def boost(note):
    w = rb["judge_boost_when"]
    return rb["judge_priority_boost"] if note and note["recommended_action"] == w["recommended_action"] and note["risk_level"] in w["risk_level"] else 0


q = load("quarantine.json")
tops = []
for grp in q["sessions"]:
    keys = []
    for it in grp["items"]:
        check_row(f"quarantine {it['id']}", it["verdict"], it["risk_score"], it["rule_flags"])
        if it["effective_priority_score"] != it["risk_score"] + boost(it["judge_note"]):
            ok = False; print(f"FAIL quarantine {it['id']}: effective_priority_score")
        keys.append((it["effective_priority_score"], it["created_at"]))
    if keys != sorted(keys, reverse=True):
        ok = False; print(f"FAIL session {grp['session_id']}: items not sorted by (priority, created_at) DESC")
    tops.append((keys[0][0], grp["created_at"]))
if tops != sorted(tops, reverse=True):
    ok = False; print("FAIL sessions not sorted by top item priority")
for name in ("write_quarantined.json", receipt_name):
    r = load(name)
    check_row(name, r["verdict"], r["risk_score"], r["rule_flags"])

ok &= validate("chat_session.json", "ChatSession")
ok &= validate("chat_stream.json", "ChatStream")
stream = load("chat_stream.json")
kinds = [e["type"] for e in stream]
body = kinds[1:-2] if kinds[-1] == "done" else kinds[1:-1]
if kinds[0] != "run" or kinds[-1] not in ("done", "error") or (kinds[-1] == "done" and kinds[-2] != "reply") or any(k != "step" for k in body):
    ok = False; print("FAIL chat_stream.json: order must be run, step*, then reply+done or error")
steps = [e for e in stream if e["type"] == "step"]
if [s["index"] for s in steps] != list(range(len(steps))):
    ok = False; print("FAIL chat_stream.json: step indexes must count from 0")
for s in steps:
    d = s["detail"]
    if d is not None and d["kind"] != s["tool"]:
        ok = False; print(f"FAIL chat step {s['index']}: detail.kind {d['kind']} != tool {s['tool']}")
    if s["tool"] == "remember" and d:
        check_row(f"chat step {s['index']}", d["verdict"], d["risk_score"], d["rule_flags"])
        if d["payload_hash"] != sha(d["content"]) or (d["table"] == "memories") != (d["verdict"] == "ALLOW"):
            ok = False; print(f"FAIL chat step {s['index']}: payload_hash or table")
    if s["tool"] == "send_email" and s["status"] != "refused":
        ok = False; print(f"FAIL chat step {s['index']}: send_email must be refused")
if stream[-1]["type"] == "done" and stream[-1]["steps"] != len(steps):
    ok = False; print("FAIL chat_stream.json: done.steps")

print("contracts OK" if ok else "contracts FAILED")
sys.exit(0 if ok else 1)
