"""Prepare the S3 bucket shared by receipts and run logs (logs/). Idempotent; never prints keys. Exit 1 on any FAIL.

Steps: create bucket if missing, warn on public ACL grants, optional logs/ expiry rule, logs/_probe round trip.
Run: uv run --no-project --with boto3 python infra/scripts/setup_object_storage.py [--logs-expire-days N]
"""
import argparse
import hashlib
import sys
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

import _env

RULE_ID = "expire-run-logs"
PUBLIC_GROUPS = ("http://acs.amazonaws.com/groups/global/AllUsers",
                 "http://acs.amazonaws.com/groups/global/AuthenticatedUsers")
changes: list[str] = []
failed = False


def report(status: str, name: str, detail: str = "") -> None:
    global failed
    failed = failed or status == "FAIL"
    print(f"{status}  {name}" + (f"  ({detail})" if detail else ""))


def code(e: ClientError) -> str:
    return str(e.response.get("Error", {}).get("Code", ""))


def ensure_bucket(s3, bucket: str, region: str) -> bool:
    try:
        s3.head_bucket(Bucket=bucket)
        report("PASS", "bucket exists", bucket)
        return True
    except ClientError as e:
        if code(e) in ("403", "Forbidden", "AccessDenied"):
            s3.list_buckets()  # raises if the keys themselves are rejected, so 403 is not misreported
            report("FAIL", "bucket owned by someone else",
                   f"{bucket}: pick a unique S3_BUCKET (names are unique on the cluster)")
            return False
        if code(e) not in ("404", "NoSuchBucket", "NotFound"):
            raise
    try:
        s3.create_bucket(Bucket=bucket)
    except ClientError as e:
        if "LocationConstraint" not in code(e):
            raise
        # Endpoints outside us-east-1 (e.g. AWS) need the region spelled out.
        s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": region})
    changes.append("created bucket")
    report("PASS", "bucket created", bucket)
    return True


def check_private(s3, bucket: str) -> None:
    grants = s3.get_bucket_acl(Bucket=bucket).get("Grants", [])
    public = [g["Permission"] for g in grants if g.get("Grantee", {}).get("URI") in PUBLIC_GROUPS]
    if public:
        report("WARN", "bucket ACL has public grants", ",".join(public))
    else:
        report("PASS", "bucket ACL private")


def ensure_lifecycle(s3, bucket: str, days: int) -> None:
    ours = {"ID": RULE_ID, "Filter": {"Prefix": "logs/"}, "Status": "Enabled", "Expiration": {"Days": days}}
    try:
        try:
            rules = s3.get_bucket_lifecycle_configuration(Bucket=bucket).get("Rules", [])
        except ClientError as e:
            if code(e) != "NoSuchLifecycleConfiguration":
                raise
            rules = []
        wide = [r.get("ID", "?") for r in rules if r.get("ID") != RULE_ID
                and not (r.get("Filter", {}).get("Prefix") or r.get("Prefix") or "").startswith("logs/")]
        if wide:  # kept as found, but they could expire receipts/
            report("WARN", "lifecycle rules not scoped to logs/", ", ".join(wide))
        current = next((r for r in rules if r.get("ID") == RULE_ID), None)
        if current and current.get("Filter", {}).get("Prefix") == "logs/" and current.get("Status") == "Enabled" \
                and current.get("Expiration", {}).get("Days") == days:
            report("PASS", "lifecycle logs/ expiry", f"{days} days, unchanged")
            return
        others = [r for r in rules if r.get("ID") != RULE_ID]
        s3.put_bucket_lifecycle_configuration(Bucket=bucket, LifecycleConfiguration={"Rules": others + [ours]})
        changes.append(f"lifecycle {RULE_ID}={days}d")
        report("PASS", "lifecycle logs/ expiry", f"set {days} days, kept {len(others)} other rule(s)")
    except ClientError as e:
        report("WARN", "lifecycle not supported by endpoint, continuing", f"{code(e)}: {str(e)[:120]}")


def probe(s3, bucket: str) -> None:
    key = f"logs/_probe/{uuid.uuid4()}.jsonl"
    body = b'{"probe":true}\n'
    digest = hashlib.sha256(body).hexdigest()
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/x-ndjson",
                  Metadata={"sha256": digest})
    try:
        got = s3.get_object(Bucket=bucket, Key=key)
        data = got["Body"].read()
        assert data == body, "bytes differ"
        assert got.get("Metadata", {}).get("sha256") == digest, "sha256 metadata missing or wrong"
        assert hashlib.sha256(data).hexdigest() == digest, "sha256 mismatch"
    finally:
        s3.delete_object(Bucket=bucket, Key=key)
    report("PASS", "logs/ put-get-delete", key)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    _env.load_env()
    ap.add_argument("--logs-expire-days", type=int, default=int(_env.get("S3_LOGS_EXPIRE_DAYS", "0")),
                    help="expire objects under logs/ after N days (default: S3_LOGS_EXPIRE_DAYS; 0 = no rule)")
    args = ap.parse_args()
    if args.logs_expire_days < 0:
        ap.error("--logs-expire-days must be >= 0")

    region = _env.get("S3_REGION", "us-east-1")
    bucket = _env.get("S3_BUCKET", "quarantine-receipts")
    s3 = boto3.client(
        "s3", endpoint_url=_env.get("S3_ENDPOINT_URL", "http://localhost:9000"),
        aws_access_key_id=_env.get("S3_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=_env.get("S3_SECRET_KEY", "minioadmin"), region_name=region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                      connect_timeout=5, retries={"max_attempts": 1}))

    steps = [("bucket", lambda: ensure_bucket(s3, bucket, region)),
             ("bucket ACL", lambda: check_private(s3, bucket))]
    if args.logs_expire_days:
        steps.append(("lifecycle", lambda: ensure_lifecycle(s3, bucket, args.logs_expire_days)))
    steps.append(("logs/ put-get-delete", lambda: probe(s3, bucket)))
    for name, fn in steps:
        try:
            if fn() is False:
                break
        except Exception as e:  # noqa: BLE001
            report("FAIL", name, f"{type(e).__name__}: {str(e).splitlines()[0][:120]}")
            if name == "bucket":
                break
    print("changes: " + (", ".join(changes) if changes else "none"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
