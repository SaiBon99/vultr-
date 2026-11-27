"""Run logs for POST /crawl (openspec/changes/add-run-logs): one transcript per started run."""

# ruff: noqa: F811  (fixtures imported from test_crawl are pytest arguments, not redefinitions)

import hashlib
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.storage import InMemoryObjectStore
from tests.conftest import REVIEWER
from tests.test_crawl import (  # noqa: F401  (fixtures)
    KEY,
    PAGE_URL,
    REVIEW,
    crawl_app,
    crawl_settings,
    guard,
    model,
    page,
    runner,
    schema_errors,
)


@pytest.fixture
def store():
    return InMemoryObjectStore()


@pytest.fixture
def client(crawl_app, store):
    crawl_app.state.store = store
    return TestClient(crawl_app)


def post(client, url=PAGE_URL):
    return client.post("/crawl", json={"url": url}, headers=REVIEW)


def lines(store, run_id):
    body = store.objects[f"logs/crawl/{run_id}.jsonl"]
    return [json.loads(x) for x in body.decode().splitlines()]


def test_successful_crawl_leaves_complete_transcript(client, store):
    r = post(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert schema_errors(body, "CrawlResult") == []
    run_id = body["run_id"]
    uuid.UUID(run_id)
    key = f"logs/crawl/{run_id}.jsonl"
    assert body["log_uri"] == f"s3://{store.bucket}/{key}"
    raw = store.objects[key]
    assert store.content_types[key] == "application/x-ndjson"
    assert store.head(key)["sha256"] == hashlib.sha256(raw).hexdigest()

    log = lines(store, run_id)
    start, end = log[0], log[-1]
    assert start["type"] == "run_start" and start["run_id"] == run_id
    assert start["kind"] == "crawl" and start["session_id"] is None
    assert start["limits"] == {"memory_mb": 512, "cpus": 1, "timeout_s": 30}
    assert start["image_id"].startswith("sha256:") and start["started_at"].endswith("Z")
    assert end["type"] == "run_end" and end["status"] == "ok" and end["http_status"] == 200
    assert end["error_code"] is None and end["lines_dropped"] == 0

    msgs = [x for x in log if x["type"] == "msg"]
    assert [(m["dir"], m["msg"]["type"]) for m in msgs] == [
        ("host_to_agent", "task"),
        ("agent_to_host", "fetch"),
        ("host_to_agent", "fetch_result"),
        ("agent_to_host", "model"),
        ("host_to_agent", "model_result"),
        ("agent_to_host", "result"),
    ]
    middle = log[1:-1]
    assert [x["seq"] for x in middle] == list(range(1, len(middle) + 1))
    assert all(x["t_ms"] >= 0 for x in middle)
    assert [x["t_ms"] for x in middle] == sorted(x["t_ms"] for x in middle)


def test_each_run_gets_a_fresh_run_id(client, store):
    ids = {post(client).json()["run_id"] for _ in range(2)}
    assert len(ids) == 2 and len(store.objects) == 2


def stand_in(body: str) -> str:
    return "import json, sys, time\ntask = json.loads(sys.stdin.readline())\n" + body


def test_agent_crash_502_carries_run_id_and_transcript(client, store, runner):
    runner.script = stand_in('print(json.dumps({"type": "shell"}), flush=True)\ntime.sleep(5)')
    r = post(client)
    assert r.status_code == 502 and r.json()["code"] == "agent_crash"
    run_id = r.json()["run_id"]
    assert schema_errors(r.json(), "Error") == []
    end = lines(store, run_id)[-1]
    assert end["type"] == "run_end" and end["status"] == "error"
    assert end["error_code"] == "agent_crash" and end["http_status"] == 502
    assert end["container_id"] and end["exit_code"] is not None and end["elapsed_ms"] >= 0


def test_timeout_504_carries_run_id_and_transcript(client, store, runner):
    from app.crawl.runner import Limits

    runner.limits = Limits(memory_mb=512, cpus=1, timeout_s=1)
    runner.script = "import time\ntime.sleep(10)"
    r = post(client)
    assert r.status_code == 504 and r.json()["code"] == "timeout"
    end = lines(store, r.json()["run_id"])[-1]
    assert end["status"] == "error" and end["error_code"] == "timeout"
    assert end["http_status"] == 504 and end["exit_code"] is not None


def test_unsafe_target_422_writes_nothing(client, store):
    r = post(client, "http://127.0.0.1/admin")
    assert r.status_code == 422 and r.json()["code"] == "unsafe_target"
    assert "run_id" not in r.json() and store.objects == {}


def test_sandbox_busy_503_writes_nothing(client, store, crawl_app):
    crawl_app.state.crawl_slots.free = 0
    r = post(client)
    assert r.status_code == 503 and r.json()["code"] == "sandbox_busy"
    assert "run_id" not in r.json() and store.objects == {}


def test_host_events_record_fetch_and_model_without_prompts(client, store):
    r = post(client)
    log = lines(store, r.json()["run_id"])
    hosts = {x["event"]: x for x in log if x["type"] == "host"}
    fetch, model_ev = hosts["fetch"], hosts["model"]
    assert fetch["final_url"] == PAGE_URL and fetch["status"] == 200
    assert fetch["bytes"] > 0 and fetch["content_type"].startswith("text/html")
    assert model_ev["model"] == "qwen3.8-27b" and model_ev["inference_id"] == "cmpl-test-1"
    assert model_ev["usage"]["total_tokens"] == 150 and model_ev["latency_ms"] >= 0
    assert set(model_ev) == {
        "type",
        "seq",
        "t_ms",
        "event",
        "model",
        "inference_id",
        "usage",
        "latency_ms",
    }
    assert b"untrusted" not in store.objects[f"logs/crawl/{r.json()['run_id']}.jsonl"].lower()
    order = [x.get("event") or x["msg"]["type"] for x in log[1:-1]]
    assert order.index("fetch_result") == order.index("fetch", 2) + 1


def test_malformed_agent_line_is_logged_raw_before_run_end(client, store, runner):
    runner.script = stand_in(
        'sys.stdout.buffer.write(b"not json \\xff" + b"x" * 9000 + b"\\n")\n'
        "sys.stdout.flush()\ntime.sleep(5)"
    )
    r = post(client)
    assert r.status_code == 502 and r.json()["code"] == "agent_crash"
    log = lines(store, r.json()["run_id"])
    raw = log[-2]
    assert raw["type"] == "msg" and raw["dir"] == "agent_to_host" and "msg" not in raw
    assert raw["raw"].startswith("not json \ufffd") and len(raw["raw"].encode()) <= 4096 + 3
    assert log[-1]["type"] == "run_end"


def test_agent_traceback_on_stderr_lands_in_run_end(client, store, runner):
    runner.script = stand_in('raise RuntimeError("agent blew up")')
    r = post(client)
    assert r.status_code == 502
    end = lines(store, r.json()["run_id"])[-1]
    assert "Traceback" in end["stderr"] and "RuntimeError: agent blew up" in end["stderr"]
    assert end["stderr_truncated"] is False


def test_noisy_stderr_is_capped_at_64_kb_and_never_stalls_the_run(client, store, runner):
    # 1 MB of stderr before speaking: a pipe nobody drains would block the agent (and time out).
    runner.script = stand_in(
        'sys.stderr.write("e" * 1_000_000); sys.stderr.flush()\n'
        'print(json.dumps({"type": "fetch", "url": task["url"]}), flush=True)\n'
        "fr = json.loads(sys.stdin.readline())\n"
        'print(json.dumps({"type": "model", "page_title": "t", "page_text": fr["body"]}),'
        " flush=True)\n"
        "mr = json.loads(sys.stdin.readline())\n"
        'mr["type"] = "result"\nprint(json.dumps(mr), flush=True)\n'
    )
    r = post(client)
    assert r.status_code == 200, r.text
    end = lines(store, r.json()["run_id"])[-1]
    assert end["stderr"] == "e" * 65536 and end["stderr_truncated"] is True


ECHO_AGENT = stand_in(
    'print(json.dumps({"type": "fetch", "url": task["url"]}), flush=True)\n'
    "fr = json.loads(sys.stdin.readline())\n"
    'print(json.dumps({"type": "model", "page_title": "t", "page_text": fr["body"]}), flush=True)\n'
    "mr = json.loads(sys.stdin.readline())\n"
    'mr["type"] = "result"\nprint(json.dumps(mr), flush=True)\n'
)


def test_secrets_are_redacted_before_hashing(client, store, runner, page):
    leak = f"token={REVIEWER} key={KEY}"
    page.routes["/article"] = (200, {"Content-Type": "text/plain"}, leak.encode())
    runner.script = f"import sys\nsys.stderr.write({leak!r})\n" + ECHO_AGENT
    r = post(client)
    assert r.status_code == 200, r.text
    key = f"logs/crawl/{r.json()['run_id']}.jsonl"
    raw = store.objects[key]
    assert REVIEWER.encode() not in raw and KEY.encode() not in raw
    log = [json.loads(x) for x in raw.decode().splitlines()]
    msgs = {x["msg"]["type"]: x["msg"] for x in log if x["type"] == "msg"}
    assert msgs["fetch_result"]["body"] == "token=[REDACTED] key=[REDACTED]"
    assert msgs["model"]["page_text"] == "token=[REDACTED] key=[REDACTED]"
    assert log[-1]["stderr"] == "token=[REDACTED] key=[REDACTED]"
    assert store.head(key)["sha256"] == hashlib.sha256(raw).hexdigest()


def test_short_and_empty_secrets_are_not_replaced():
    from app.crawl.runner import Limits
    from app.runlog import RunLog

    log = RunLog("r", "crawl", None, Limits(memory_mb=1, cpus=1, timeout_s=1))
    log.sent({"type": "task", "url": "https://abc.example/"})
    log.finish(status="ok", http_status=200, error_code=None, exit_code=0, container_id=None,
               elapsed_ms=1, stderr="", stderr_truncated=False)  # fmt: skip
    out = log.to_bytes(["abc", "", 'quote"secret\\x'])
    assert b"https://abc.example/" in out and b"[REDACTED]" not in out
    log.sent({"type": "task", "url": 'quote"secret\\x'})
    assert b"quote" not in log.to_bytes(['quote"secret\\x'])


def test_large_page_body_and_page_text_are_cut_to_16_kb_with_fingerprint(
    client, store, runner, page
):
    text = "".join(f"{i:07d}\n" for i in range(25_000))  # 200 KB
    page.routes["/article"] = (200, {"Content-Type": "text/plain"}, text.encode())
    runner.script = ECHO_AGENT
    r = post(client)
    assert r.status_code == 200, r.text
    msgs = {
        x["msg"]["type"]: x["msg"] for x in lines(store, r.json()["run_id"]) if x["type"] == "msg"
    }
    full_sha = hashlib.sha256(text.encode()).hexdigest()
    fr, m = msgs["fetch_result"], msgs["model"]
    assert fr["body"] == text[:16384] and fr["body_truncated"] is True
    assert fr["body_chars"] == 200_000 and fr["body_sha256"] == full_sha
    assert m["page_text"] == text[:16384] and m["page_text_truncated"] is True
    assert m["page_text_chars"] == 200_000 and m["page_text_sha256"] == full_sha


def test_small_body_is_kept_whole_and_marked_not_truncated(client, store):
    r = post(client)
    msgs = {
        x["msg"]["type"]: x["msg"] for x in lines(store, r.json()["run_id"]) if x["type"] == "msg"
    }
    assert msgs["fetch_result"]["body_truncated"] is False
    assert "body_chars" not in msgs["fetch_result"]


def test_object_over_1_mb_keeps_run_start_and_run_end_and_counts_dropped_lines():
    from app.crawl.runner import Limits
    from app.runlog import RunLog

    log = RunLog("r", "crawl", None, Limits(memory_mb=1, cpus=1, timeout_s=1))
    for i in range(100):  # each line about 12 KB: about 85 fit in 1 MB
        log.host("fetch", n=i, pad="x" * 12_000)
    log.finish(status="ok", http_status=200, error_code=None, exit_code=0, container_id=None,
               elapsed_ms=1, stderr="e" * 65536, stderr_truncated=True)  # fmt: skip
    out = log.to_bytes([])
    assert len(out) <= 1024 * 1024
    parsed = [json.loads(x) for x in out.decode().splitlines()]
    assert parsed[0]["type"] == "run_start" and parsed[-1]["type"] == "run_end"
    kept = [x["n"] for x in parsed[1:-1]]
    assert kept == list(range(len(kept))) and 70 < len(kept) < 100
    assert parsed[-1]["lines_dropped"] == 100 - len(kept)
    assert len(out) + 12_100 > 1024 * 1024  # the next line would not have fitted


def test_no_store_still_returns_200_with_null_log_uri(client, crawl_app):
    crawl_app.state.store = None
    r = post(client)
    assert r.status_code == 200 and r.json()["log_uri"] is None
    uuid.UUID(r.json()["run_id"])


def test_failing_store_never_changes_the_answer(client, store, runner, caplog):
    store.fail = True
    caplog.set_level("WARNING", logger="app.runlog")
    ok = post(client)
    assert ok.status_code == 200 and ok.json()["log_uri"] is None
    assert schema_errors(ok.json(), "CrawlResult") == []
    warnings = [r.getMessage() for r in caplog.records if r.name == "app.runlog"]
    assert warnings == [f"run log upload failed run_id={ok.json()['run_id']} err=ConnectionError"]

    runner.script = stand_in('print("{", flush=True)\ntime.sleep(5)')
    bad = post(client)
    assert bad.status_code == 502
    assert set(bad.json()) == {"detail", "code", "run_id"} and bad.json()["code"] == "agent_crash"


def test_upload_runs_after_the_sandbox_is_removed(client, store, runner):
    seen = []
    put = store.put_bytes
    store.put_bytes = lambda *a, **kw: seen.append(runner.cleanups) or put(*a, **kw)
    assert post(client).status_code == 200
    assert seen == [1]


def test_reviewer_reads_run_log_byte_for_byte(client, store):
    run_id = post(client).json()["run_id"]
    r = client.get(f"/crawl/runs/{run_id}/log", headers=REVIEW)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    assert r.content == store.objects[f"logs/crawl/{run_id}.jsonl"]


def test_run_log_requires_reviewer_token(client, store):
    run_id = post(client).json()["run_id"]
    for headers in ({}, {"X-Reviewer-Token": "wrong"}, {"X-Host-Secret": REVIEWER}):
        r = client.get(f"/crawl/runs/{run_id}/log", headers=headers)
        assert r.status_code == 401 and r.json()["code"] == "unauthorized"


def test_unknown_run_log_is_404(client):
    r = client.get(f"/crawl/runs/{uuid.uuid4()}/log", headers=REVIEW)
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    assert schema_errors(r.json(), "Error") == []


def test_run_log_without_storage_is_503(client, crawl_app):
    crawl_app.state.store = None
    r = client.get(f"/crawl/runs/{uuid.uuid4()}/log", headers=REVIEW)
    assert r.status_code == 503 and r.json()["code"] == "storage_missing"


def test_receipts_module_still_exports_the_stores():
    from app.receipts import InMemoryObjectStore as A
    from app.receipts import S3ObjectStore as B
    from app.storage import InMemoryObjectStore, S3ObjectStore

    assert (InMemoryObjectStore, S3ObjectStore) == (A, B)


def test_unreachable_storage_on_read_is_503_error_body(client, store):
    def down(key):
        raise ConnectionError("storage down")

    store.get = down
    r = client.get(f"/crawl/runs/{uuid.uuid4()}/log", headers=REVIEW)
    assert r.status_code == 503 and r.json()["code"] == "storage_unavailable"
    assert schema_errors(r.json(), "Error") == []


SECRET = "s3cr3t-value-0123456789"


def _finished(log, stderr=""):
    log.finish(status="ok", http_status=200, error_code=None, exit_code=0, container_id=None,
               elapsed_ms=1, stderr=stderr, stderr_truncated=False)  # fmt: skip
    return log.to_bytes([SECRET])


@pytest.mark.parametrize("where", ["body", "page_text", "raw", "stderr"])
def test_secret_straddling_a_cut_point_leaves_no_fragment(where):
    from app.crawl.runner import STDERR_LIMIT, Limits
    from app.runlog import RAW_CAP, TEXT_CAP, RunLog

    cap = {"body": TEXT_CAP, "page_text": TEXT_CAP, "raw": RAW_CAP, "stderr": STDERR_LIMIT}[where]
    text = "a" * (cap - 5) + SECRET + "tail"  # the cut lands inside the secret
    log = RunLog("r", "crawl", None, Limits(memory_mb=1, cpus=1, timeout_s=1))
    if where == "body":
        log.sent({"type": "fetch_result", "body": text})
    elif where == "page_text":
        log.received(b"{}", {"type": "model", "page_text": text})
    elif where == "raw":
        log.received(text.encode() + b"\n", None)
    out = _finished(log, text if where == "stderr" else "")
    assert SECRET[:5].encode() not in out


def test_text_caps_count_utf8_bytes():
    from app.crawl.runner import Limits
    from app.runlog import TEXT_CAP, RunLog

    text = "é" * TEXT_CAP  # 2 bytes each
    log = RunLog("r", "crawl", None, Limits(memory_mb=1, cpus=1, timeout_s=1))
    log.sent({"type": "fetch_result", "body": text})
    fr = json.loads(_finished(log).decode().splitlines()[1])["msg"]
    assert len(fr["body"].encode()) <= TEXT_CAP and fr["body"] == "é" * (TEXT_CAP // 2)
    assert fr["body_chars"] == TEXT_CAP and fr["body_truncated"] is True
