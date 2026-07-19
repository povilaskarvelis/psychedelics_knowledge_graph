from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PUBLIC_QUERY_CONTRACT_KEY = "catalogue-v2"


def csv_env(name: str) -> tuple[str, ...]:
    return tuple(
        item.strip() for item in os.environ.get(name, "").split(",") if item.strip()
    )


def int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def normalize_r2_prefix(value: str) -> str:
    prefix = value.strip().strip("/")
    if not prefix:
        return "query-api"
    parts = prefix.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("PKG_R2_PREFIX must be a safe object-key prefix")
    return "/".join(parts)


@dataclass(frozen=True)
class R2Settings:
    account_id: str
    bucket: str
    access_key_id: str
    secret_access_key: str
    endpoint_url: str
    prefix: str = "query-api"
    public_base_url: str = ""
    signed_url_ttl_seconds: int = 900

    @property
    def active_key(self) -> str:
        return f"{self.prefix}/active/{PUBLIC_QUERY_CONTRACT_KEY}.json"

    @property
    def legacy_active_key(self) -> str:
        return f"{self.prefix}/active.json"

    @classmethod
    def from_env(cls, *, required: bool = False) -> "R2Settings | None":
        bucket = os.environ.get("PKG_R2_BUCKET", "").strip()
        if not bucket:
            if required:
                raise ValueError("PKG_R2_BUCKET is required")
            return None

        account_id = os.environ.get("PKG_R2_ACCOUNT_ID", "").strip()
        endpoint_url = os.environ.get("PKG_R2_ENDPOINT_URL", "").strip().rstrip("/")
        jurisdiction = os.environ.get("PKG_R2_JURISDICTION", "").strip().casefold()
        if jurisdiction not in {"", "eu", "fedramp"}:
            raise ValueError("PKG_R2_JURISDICTION must be blank, eu, or fedramp")
        if not endpoint_url:
            if not account_id:
                raise ValueError(
                    "PKG_R2_ACCOUNT_ID is required when PKG_R2_ENDPOINT_URL is not set"
                )
            jurisdiction_part = f".{jurisdiction}" if jurisdiction else ""
            endpoint_url = (
                f"https://{account_id}{jurisdiction_part}.r2.cloudflarestorage.com"
            )

        access_key_id = os.environ.get("PKG_R2_ACCESS_KEY_ID", "").strip()
        secret_access_key = os.environ.get("PKG_R2_SECRET_ACCESS_KEY", "").strip()
        missing = [
            name
            for name, value in (
                ("PKG_R2_ACCESS_KEY_ID", access_key_id),
                ("PKG_R2_SECRET_ACCESS_KEY", secret_access_key),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"Missing R2 credentials: {', '.join(missing)}")

        return cls(
            account_id=account_id,
            bucket=bucket,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            endpoint_url=endpoint_url,
            prefix=normalize_r2_prefix(os.environ.get("PKG_R2_PREFIX", "query-api")),
            public_base_url=os.environ.get("PKG_R2_PUBLIC_BASE_URL", "")
            .strip()
            .rstrip("/"),
            signed_url_ttl_seconds=int_env(
                "PKG_R2_SIGNED_URL_TTL_SECONDS",
                900,
                minimum=60,
                maximum=604800,
            ),
        )


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    active_pointer: Path
    query_runs_dir: Path
    public_base_url: str
    cors_origins: tuple[str, ...]
    mcp_allowed_hosts: tuple[str, ...]
    mcp_allowed_origins: tuple[str, ...]
    r2: R2Settings | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.environ.get("PKG_DATA_DIR") or ROOT / "data").resolve()
        return cls(
            data_dir=data_dir,
            active_pointer=Path(
                os.environ.get("PKG_ACTIVE_GRAPH_POINTER")
                or data_dir / "processed" / "graph_payload_active.json"
            ).resolve(),
            query_runs_dir=Path(
                os.environ.get("PKG_QUERY_RUNS_DIR")
                or data_dir / "processed" / "query_api_runs"
            ).resolve(),
            public_base_url=(
                os.environ.get("PKG_PUBLIC_BASE_URL") or "http://127.0.0.1:8000"
            ).rstrip("/"),
            cors_origins=csv_env("PKG_CORS_ORIGINS"),
            mcp_allowed_hosts=csv_env("PKG_MCP_ALLOWED_HOSTS"),
            mcp_allowed_origins=csv_env("PKG_MCP_ALLOWED_ORIGINS"),
            r2=R2Settings.from_env(),
        )
