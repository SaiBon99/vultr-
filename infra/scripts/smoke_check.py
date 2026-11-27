"""Smoke check: DB, vector extension, 4 tables, role isolation, audit append-only, S3 bucket, logs/ round trip.
Exit 1 on any failure.

Run: uv run --no-project --with "psycopg[binary]" --with boto3 python infra/scripts/smoke_check.py
"""
import sys
import uuid

import boto3
import psycopg
from botocore.config import Config

import _env

_env.load_env()
TABLES = {"sessions", "memories", "quarantine_queue", "audit_events"}
results: list[tuple[str, bool, str]] = []


def check(name, fn):
    try:
        detail = fn() or ""
        results.append((name, True, detail))
    except Exception as e:  # noqa: BLE001
        results.append((name, False, f"{type(e).__name__}: {str(e).splitlines()[0][:120]}"))


def denied(url: str, stmt: str) -> str:
    """Return the error class if stmt is rejected; raise if it succeeds."""
    with psycopg.connect(url, autocommit=True, connect_timeout=5) as c:
        try:
            c.execute(stmt)
        except psycopg.errors.InsufficientPrivilege:
            return "permission denied"
        except psycopg.Error as e:
            if "append-only" in str(e):
                return "append-only trigger"
            raise
    raise AssertionError(f"statement was allowed: {stmt}")


def db_checks() -> None:
    def reach():
        with psycopg.connect(_env.proxy_url(), connect_timeout=5) as c:
            c.execute("SELECT 1")

    def ext():
        with psycopg.connect(_env.proxy_url(), connect_timeout=5) as c:
            assert c.execute("SELECT 1 FROM pg_extension WHERE extname='vector'").fetchone(), "vector missing"

    def tables():
        with psycopg.connect(_env.proxy_url(), connect_timeout=5) as c:
            have = {r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")}
        assert TABLES <= have, f"missing {sorted(TABLES - have)}"

    check("db reachable (proxy role)", reach)
    check("vector extension", ext)
    check("4 tables exist", tables)
    check("memory_reader cannot SELECT quarantine_queue",
          lambda: denied(_env.reader_url(), "SELECT 1 FROM quarantine_queue LIMIT 1"))
    check("audit_events rejects UPDATE",
          lambda: denied(_env.proxy_url(), "UPDATE audit_events SET event_type = event_type"))


def s3_client():
    return boto3.client(
        "s3", endpoint_url=_env.get("S3_ENDPOINT_URL", "http://localhost:9000"),
        aws_access_key_id=_env.get("S3_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=_env.get("S3_SECRET_KEY", "minioadmin"),
        region_name=_env.get("S3_REGION", "us-east-1"),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                      connect_timeout=5, retries={"max_attempts": 1}))


BUCKET = _env.get("S3_BUCKET", "quarantine-receipts")


def s3_check() -> str:
    s3_client().head_bucket(Bucket=BUCKET)
    return BUCKET


def s3_logs_check() -> str:
    s3, key, body = s3_client(), f"logs/_probe/{uuid.uuid4()}.jsonl", b'{"probe":true}\n'
    s3.put_object(Bucket=BUCKET, Key=key, Body=body)
    try:
        assert s3.get_object(Bucket=BUCKET, Key=key)["Body"].read() == body, "bytes differ"
    finally:
        s3.delete_object(Bucket=BUCKET, Key=key)
    return key


def main() -> int:
    db_checks()
    check("s3 bucket reachable", s3_check)
    check("s3 logs/ put-get-delete", s3_logs_check)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
