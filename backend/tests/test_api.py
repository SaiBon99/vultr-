import json

from fastapi.testclient import TestClient

from app.main import create_app
from app.receipts import InMemoryObjectStore, receipt_object_key
from tests.conftest import HOST, REVIEWER, load_fixture

SESSION = {"X-Session-Token": "tok"}
REVIEW = {"X-Reviewer-Token": REVIEWER}
UUID_ = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"


def test_health_shape(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "checks": {"db": "skipped", "object_storage": "ok", "inference": "skipped"},
    }


def test_health_without_dependencies(settings):
    r = TestClient(create_app(settings)).get("/health")
    assert r.json()["checks"] == {
        "db": "skipped",
        "object_storage": "skipped",
        "inference": "skipped",
    }


def test_public_key_matches_contract_shape(client):
    r = client.get("/keys/public")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == set(load_fixture("keys_public.json"))
    assert body["alg"] == "Ed25519" and len(body["key_id"]) == 16


def test_public_key_503_without_key(settings):
    settings.RECEIPT_SIGNING_KEY_PATH = ""
    r = TestClient(create_app(settings)).get("/keys/public")
    assert r.status_code == 503


def test_host_auth_401(client):
    assert client.post("/proxy/sessions").status_code == 401
    assert client.post("/proxy/sessions", headers={"X-Host-Secret": "wrong"}).status_code == 401
    ok = client.post("/proxy/sessions", headers={"X-Host-Secret": HOST})
    assert ok.status_code == 501


def test_naive_gate_mode_forbidden_by_default(client):
    r = client.post(
        "/proxy/sessions",
        headers={"X-Host-Secret": HOST, **REVIEW},
        json={"gate_mode": "naive"},
    )
    assert r.status_code == 403 and r.json()["code"] == "naive_disabled"


def test_session_token_401(client):
    assert (
        client.post("/proxy/read", json={"source_ref": "a", "source_kind": "web"}).status_code
        == 401
    )
    assert client.post("/proxy/memory/write", json={"content": "x"}).status_code == 401
    assert client.get("/proxy/memory/active").status_code == 401


def test_reviewer_token_401(client):
    for method, path in [
        ("get", "/quarantine"),
        ("post", f"/quarantine/{UUID_}/decide"),
        ("get", "/audit"),
        ("get", f"/receipts/{UUID_}"),
    ]:
        assert getattr(client, method)(path).status_code == 401, path
        r = getattr(client, method)(path, headers={"X-Reviewer-Token": "nope"})
        assert r.status_code == 401, path


def test_reviewer_auth_disabled_opens_reviewer_routes_only(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    open_settings = settings.model_copy(update={"REVIEWER_AUTH_DISABLED": True})
    with TestClient(create_app(open_settings)) as c:
        for method, path in [("get", "/quarantine"), ("get", "/audit")]:
            assert getattr(c, method)(path).status_code != 401, path
        assert c.post("/proxy/sessions").status_code == 401  # host auth still enforced
        assert c.get("/proxy/memory/active").status_code == 401  # session auth still enforced


def test_spoofed_source_or_session_id_rejected_422(client):
    for extra in ({"source": "user"}, {"session_id": UUID_}):
        r = client.post("/proxy/memory/write", headers=SESSION, json={"content": "hi", **extra})
        assert r.status_code == 422
        assert r.json()["code"] == "validation_error"


def test_valid_write_reaches_phase1_stub(client):
    r = client.post("/proxy/memory/write", headers=SESSION, json={"content": "hi"})
    assert r.status_code == 501


def test_write_validation(client):
    for body in ({"content": ""}, {"content": "x" * 8001}, {"content": "a", "overwrite_id": "no"}):
        assert client.post("/proxy/memory/write", headers=SESSION, json=body).status_code == 422


def test_decide_validation_and_authed_stub(client):
    url = f"/quarantine/{UUID_}/decide"
    assert client.post(url, headers=REVIEW, json={"action": "nuke"}).status_code == 422
    assert client.post(url, headers=REVIEW, json={"action": "purge"}).status_code == 501


def test_memory_active_query_bounds(client):
    assert client.get("/proxy/memory/active?k=0", headers=SESSION).status_code == 422
    assert client.get("/proxy/memory/active?k=51", headers=SESSION).status_code == 422


def test_receipt_roundtrip_from_store(app, client):
    signer = app.state.signer
    base = {k: v for k, v in load_fixture("receipt_tampered.json").items() if k != "signature_b64"}
    receipt = signer.sign(base)
    rid = receipt["receipt_id"]
    store: InMemoryObjectStore = app.state.store
    store.put_json(receipt_object_key(rid), json.dumps(receipt).encode())
    r = client.get(f"/receipts/{rid}", headers=REVIEW)
    assert r.status_code == 200 and r.json()["receipt_id"] == rid
    assert client.get(f"/receipts/{UUID_}", headers=REVIEW).status_code == 404


def test_openapi_declares_every_contract_path(client):
    import yaml

    from tests.conftest import CONTRACTS

    spec = yaml.safe_load((CONTRACTS / "openapi.yaml").read_text(encoding="utf-8"))
    ours = client.get("/openapi.json").json()["paths"]
    for path, ops in spec["paths"].items():
        assert path in ours, path
        assert set(ops) <= set(ours[path]), path
