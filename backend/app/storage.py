"""Object storage for receipts and run logs: Vultr Object Storage or MinIO, or an in-memory fake."""

from typing import Protocol


class ObjectStore(Protocol):
    def put_bytes(
        self, key: str, body: bytes, *, content_type: str, metadata: dict[str, str] | None = None
    ) -> str:
        """Store and return the object URI."""
        ...

    def put_json(self, key: str, body: bytes) -> str: ...

    def get(self, key: str) -> bytes | None: ...

    def head(self, key: str) -> dict[str, str] | None:
        """The object's user metadata, or None if the key is absent."""
        ...

    def ping(self) -> bool: ...


class InMemoryObjectStore:
    def __init__(self, bucket: str = "quarantine-receipts") -> None:
        self.bucket = bucket
        self.objects: dict[str, bytes] = {}
        self.metadata: dict[str, dict[str, str]] = {}
        self.content_types: dict[str, str] = {}
        self.fail = False  # puts raise, for best-effort tests

    def put_bytes(
        self, key: str, body: bytes, *, content_type: str, metadata: dict[str, str] | None = None
    ) -> str:
        if self.fail:
            raise ConnectionError("in-memory store set to fail")
        self.objects[key] = body
        self.metadata[key] = dict(metadata or {})
        self.content_types[key] = content_type
        return f"s3://{self.bucket}/{key}"

    def put_json(self, key: str, body: bytes) -> str:
        return self.put_bytes(key, body, content_type="application/json")

    def get(self, key: str) -> bytes | None:
        return self.objects.get(key)

    def head(self, key: str) -> dict[str, str] | None:
        return self.metadata.get(key) if key in self.objects else None

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
        from botocore.config import Config

        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            # Path style works on MinIO and Vultr (https://<cluster>.vultrobjects.com/<bucket>/<key>).
            config=Config(
                connect_timeout=3,
                read_timeout=5,
                retries={"max_attempts": 2, "mode": "standard"},
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )

    def put_bytes(
        self, key: str, body: bytes, *, content_type: str, metadata: dict[str, str] | None = None
    ) -> str:
        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            Metadata=metadata or {},
        )
        return f"s3://{self.bucket}/{key}"

    def put_json(self, key: str, body: bytes) -> str:
        return self.put_bytes(key, body, content_type="application/json")

    def get(self, key: str) -> bytes | None:
        try:
            return self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except self._client.exceptions.NoSuchKey:
            return None

    def head(self, key: str) -> dict[str, str] | None:
        from botocore.exceptions import ClientError

        try:
            return self._client.head_object(Bucket=self.bucket, Key=key)["Metadata"]
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise

    def ping(self) -> bool:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except Exception:
            return False
        return True
