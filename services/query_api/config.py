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


def normalize_r2_prefix(value: str, *, variable_name: str = "R2 prefix") -> str:
    prefix = value.strip().strip("/")
    if not prefix:
        return "query-api"
    parts = prefix.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{variable_name} must be a safe object-key prefix")
    return "/".join(parts)


@dataclass(frozen=True)
class R2Settings:
    account_id: str
    bucket: str
    access_key_id: str
    secret_access_key: str
    endpoint_url: str
    prefix: str = "query-api"

    @property
    def active_key(self) -> str:
        return f"{self.prefix}/active/{PUBLIC_QUERY_CONTRACT_KEY}.json"

    @property
    def legacy_active_key(self) -> str:
        return f"{self.prefix}/active.json"

    @classmethod
    def from_env(
        cls,
        *,
        required: bool = False,
        env_prefix: str = "PKG_R2",
        default_object_prefix: str = "query-api",
    ) -> "R2Settings | None":
        def name(suffix: str) -> str:
            return f"{env_prefix}_{suffix}"

        bucket_name = name("BUCKET")
        bucket = os.environ.get(bucket_name, "").strip()
        if not bucket:
            if required:
                raise ValueError(f"{bucket_name} is required")
            return None

        account_name = name("ACCOUNT_ID")
        endpoint_name = name("ENDPOINT_URL")
        jurisdiction_name = name("JURISDICTION")
        access_key_name = name("ACCESS_KEY_ID")
        secret_key_name = name("SECRET_ACCESS_KEY")
        object_prefix_name = name("PREFIX")

        account_id = os.environ.get(account_name, "").strip()
        endpoint_url = os.environ.get(endpoint_name, "").strip().rstrip("/")
        jurisdiction = os.environ.get(jurisdiction_name, "").strip().casefold()
        if jurisdiction not in {"", "eu", "fedramp"}:
            raise ValueError(
                f"{jurisdiction_name} must be blank, eu, or fedramp"
            )
        if not endpoint_url:
            if not account_id:
                raise ValueError(
                    f"{account_name} is required when {endpoint_name} is not set"
                )
            jurisdiction_part = f".{jurisdiction}" if jurisdiction else ""
            endpoint_url = (
                f"https://{account_id}{jurisdiction_part}.r2.cloudflarestorage.com"
            )

        access_key_id = os.environ.get(access_key_name, "").strip()
        secret_access_key = os.environ.get(secret_key_name, "").strip()
        missing = [
            name
            for name, value in (
                (access_key_name, access_key_id),
                (secret_key_name, secret_access_key),
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
            prefix=normalize_r2_prefix(
                os.environ.get(object_prefix_name, default_object_prefix),
                variable_name=object_prefix_name,
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
            # API runtime data must live in a private bucket. Browser payloads use
            # the separate PKG_R2_* publisher settings and a public custom domain.
            r2=R2Settings.from_env(
                env_prefix="PKG_API_R2",
                default_object_prefix="query-api",
            ),
        )
