from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from .jsonutil import sha256_json


class S3DependencyMissing(RuntimeError):
    pass


@dataclass(frozen=True)
class S3BlobStoreConfig:
    bucket: str
    prefix: str = "agentledger/blobs"
    endpoint_url: str | None = None
    region_name: str | None = None
    profile_name: str | None = None

    @classmethod
    def from_env(
        cls,
        environ: dict[str, str] | None = None,
        *,
        bucket: str | None = None,
        prefix: str | None = None,
        endpoint_url: str | None = None,
        region_name: str | None = None,
        profile_name: str | None = None,
    ) -> "S3BlobStoreConfig":
        env = environ if environ is not None else os.environ
        resolved_bucket = bucket or env.get("AGENTLEDGER_S3_BUCKET")
        if not resolved_bucket:
            raise ValueError("S3 bucket is required; pass --bucket or set AGENTLEDGER_S3_BUCKET")
        return cls(
            bucket=resolved_bucket,
            prefix=prefix if prefix is not None else env.get("AGENTLEDGER_S3_PREFIX", "agentledger/blobs"),
            endpoint_url=endpoint_url if endpoint_url is not None else env.get("AGENTLEDGER_S3_ENDPOINT_URL"),
            region_name=region_name if region_name is not None else env.get("AGENTLEDGER_S3_REGION"),
            profile_name=profile_name if profile_name is not None else env.get("AGENTLEDGER_S3_PROFILE"),
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "bucket": self.bucket,
            "prefix": self.prefix,
            "endpoint_url": self.endpoint_url,
            "region_name": self.region_name,
            "profile_name": self.profile_name,
        }


class S3BlobStore:
    """Content-addressed JSON blob store for S3-compatible backends.

    MinIO and other S3-compatible services can use `endpoint_url`. The runtime
    core keeps boto3 optional; tests and enterprise wiring can inject a client.
    """

    def __init__(self, config: S3BlobStoreConfig, *, client: Any | None = None):
        self.config = config
        self.client = client if client is not None else self._connect()

    def put_json(self, value: Any) -> tuple[str, str]:
        digest = sha256_json(value)
        key = self._key_for_digest(digest)
        body = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        self.client.put_object(
            Bucket=self.config.bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            Metadata={"agentledger-digest": digest},
        )
        return digest, f"s3://{self.config.bucket}/{key}"

    def get_json(self, ref: str) -> Any:
        bucket, key = self._parse_ref(ref)
        obj = self.client.get_object(Bucket=bucket, Key=key)
        body = obj["Body"]
        if hasattr(body, "read"):
            body = body.read()
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        return json.loads(body)

    def _connect(self) -> Any:
        try:
            import boto3  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise S3DependencyMissing("boto3 is not installed; inject an S3 client or install a future s3 extra") from exc
        if self.config.profile_name:
            session = boto3.Session(profile_name=self.config.profile_name, region_name=self.config.region_name)
            return session.client("s3", endpoint_url=self.config.endpoint_url)
        return boto3.client("s3", endpoint_url=self.config.endpoint_url, region_name=self.config.region_name)

    def _key_for_digest(self, digest: str) -> str:
        algo, hex_digest = digest.split(":", 1)
        prefix = self.config.prefix.strip("/")
        suffix = f"{algo}/{hex_digest}.json"
        return f"{prefix}/{suffix}" if prefix else suffix

    def _parse_ref(self, ref: str) -> tuple[str, str]:
        if not ref.startswith("s3://"):
            raise ValueError(f"unsupported blob ref: {ref}")
        rest = ref.removeprefix("s3://")
        if "/" not in rest:
            raise ValueError(f"invalid s3 blob ref: {ref}")
        bucket, key = rest.split("/", 1)
        if not key:
            raise ValueError(f"invalid s3 blob ref: {ref}")
        if bucket != self.config.bucket:
            raise ValueError(f"s3 blob ref bucket {bucket!r} does not match configured bucket {self.config.bucket!r}")
        return bucket, key

