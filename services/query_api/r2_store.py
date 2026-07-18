from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

from .config import R2Settings


R2_ACTIVE_SCHEMA_VERSION = "psychedelics_kg_r2_active_release_v1"
R2_RELEASE_SIDECAR_NAME = "r2_release.json"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def safe_key_component(value: str, *, fallback: str = "release") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.")
    return (cleaned or fallback)[:80]


def release_object_prefix(settings: R2Settings, *, run_id: str, release_id: str) -> str:
    run_hash = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:8]
    release_hash = hashlib.sha256(release_id.encode("utf-8")).hexdigest()[:12]
    run_component = f"{safe_key_component(run_id, fallback='run')}-{run_hash}"
    release_component = f"{safe_key_component(release_id)}-{release_hash}"
    return f"{settings.prefix}/releases/{run_component}/{release_component}"


@dataclass(frozen=True)
class RemoteObject:
    key: str
    size: int
    metadata: dict[str, str]
    etag: str = ""


class ObjectStore(Protocol):
    def head(self, key: str) -> RemoteObject | None: ...

    def upload_file(
        self,
        key: str,
        path: Path,
        *,
        sha256: str,
        content_type: str,
        cache_control: str,
        content_disposition: str = "",
    ) -> None: ...

    def put_bytes(
        self,
        key: str,
        value: bytes,
        *,
        sha256: str,
        content_type: str,
        cache_control: str,
    ) -> None: ...

    def get_bytes(self, key: str) -> bytes: ...

    def download_file(self, key: str, path: Path) -> None: ...

    def download_url(self, key: str) -> str: ...


class R2ObjectStore:
    """Small S3-compatible wrapper used by both publishing and runtime sync."""

    def __init__(self, settings: R2Settings, *, client: Any | None = None) -> None:
        self.settings = settings
        if client is None:
            try:
                import boto3
                from botocore.config import Config
            except ModuleNotFoundError as exc:  # pragma: no cover - installation error
                raise RuntimeError(
                    "R2 support requires boto3; install services/query_api/requirements.txt"
                ) from exc
            client = boto3.client(
                "s3",
                region_name="auto",
                endpoint_url=settings.endpoint_url,
                aws_access_key_id=settings.access_key_id,
                aws_secret_access_key=settings.secret_access_key,
                config=Config(
                    signature_version="s3v4",
                    retries={"max_attempts": 5, "mode": "standard"},
                    s3={"addressing_style": "path"},
                ),
            )
        self.client = client

    @staticmethod
    def _is_missing_error(exc: BaseException) -> bool:
        response = getattr(exc, "response", {}) or {}
        error = response.get("Error", {}) if isinstance(response, dict) else {}
        code = str(error.get("Code") or "")
        status = (response.get("ResponseMetadata") or {}).get("HTTPStatusCode")
        return code in {"404", "NoSuchKey", "NotFound"} or status == 404

    def head(self, key: str) -> RemoteObject | None:
        try:
            response = self.client.head_object(Bucket=self.settings.bucket, Key=key)
        except Exception as exc:
            if self._is_missing_error(exc):
                return None
            raise
        metadata = {
            str(name).casefold(): str(value)
            for name, value in (response.get("Metadata") or {}).items()
        }
        return RemoteObject(
            key=key,
            size=int(response.get("ContentLength") or 0),
            metadata=metadata,
            etag=str(response.get("ETag") or ""),
        )

    def upload_file(
        self,
        key: str,
        path: Path,
        *,
        sha256: str,
        content_type: str,
        cache_control: str,
        content_disposition: str = "",
    ) -> None:
        extra_args: dict[str, Any] = {
            "Metadata": {"sha256": sha256},
            "ContentType": content_type,
            "CacheControl": cache_control,
        }
        if content_disposition:
            extra_args["ContentDisposition"] = content_disposition
        self.client.upload_file(
            str(path),
            self.settings.bucket,
            key,
            ExtraArgs=extra_args,
        )

    def put_bytes(
        self,
        key: str,
        value: bytes,
        *,
        sha256: str,
        content_type: str,
        cache_control: str,
    ) -> None:
        self.client.put_object(
            Bucket=self.settings.bucket,
            Key=key,
            Body=value,
            ContentLength=len(value),
            ContentType=content_type,
            CacheControl=cache_control,
            Metadata={"sha256": sha256},
        )

    def get_bytes(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.settings.bucket, Key=key)
        return response["Body"].read()

    def download_file(self, key: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.settings.bucket, key, str(path))

    def download_url(self, key: str) -> str:
        if self.settings.public_base_url:
            return f"{self.settings.public_base_url}/{quote(key, safe='/')}"
        return str(
            self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.settings.bucket, "Key": key},
                ExpiresIn=self.settings.signed_url_ttl_seconds,
            )
        )
