from __future__ import annotations

from pathlib import Path

from services.query_api.r2_store import RemoteObject, sha256_bytes


class FakeObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.metadata: dict[str, dict[str, str]] = {}
        self.operations: list[tuple[str, str]] = []

    def head(self, key: str) -> RemoteObject | None:
        if key not in self.objects:
            return None
        return RemoteObject(
            key=key,
            size=len(self.objects[key]),
            metadata=dict(self.metadata.get(key) or {}),
            etag=f'"{sha256_bytes(self.objects[key])}"',
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
        self.operations.append(("upload_file", key))
        self.objects[key] = path.read_bytes()
        self.metadata[key] = {
            "sha256": sha256,
            "content_type": content_type,
            "cache_control": cache_control,
            "content_disposition": content_disposition,
        }

    def put_bytes(
        self,
        key: str,
        value: bytes,
        *,
        sha256: str,
        content_type: str,
        cache_control: str,
    ) -> None:
        self.operations.append(("put_bytes", key))
        self.objects[key] = bytes(value)
        self.metadata[key] = {
            "sha256": sha256,
            "content_type": content_type,
            "cache_control": cache_control,
        }

    def get_bytes(self, key: str) -> bytes:
        self.operations.append(("get_bytes", key))
        return self.objects[key]

    def download_file(self, key: str, path: Path) -> None:
        self.operations.append(("download_file", key))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.objects[key])
