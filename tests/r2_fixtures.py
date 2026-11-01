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


def write_built_site(root: Path) -> Path:
    """A minimal built site with the URL patterns the real site uses."""
    site = root / "built_site"
    (site / "ui").mkdir(parents=True)
    (site / "methods").mkdir()
    (site / "compounds" / "psilocybin").mkdir(parents=True)
    (site / "schema").mkdir()
    (site / "index.html").write_text(
        """<!doctype html>
<html><head>
<meta name="robots" content="index,follow" />
<link rel="icon" href="/favicon.ico" />
<base href="./ui/" />
<link rel="preload" href="https://data.psychedelicskg.com/browser/active.json" as="fetch" />
<link rel="stylesheet" href="styles.css?v=1" />
</head><body>
<a href="/about/">About</a><a href="/methods/">Methods</a><a href="/feedback/?source=graph">Feedback</a>
<script src="/ui/site-nav.js?v=1"></script><script src="app.js?v=1"></script>
</body></html>
""",
        encoding="utf-8",
    )
    (site / "methods" / "index.html").write_text(
        """<!doctype html>
<html><head><link rel="stylesheet" href="/ui/styles.css?v=1" /></head><body>
<a href="/">Back</a><a href="/methods/#release-notes">Notes</a><a href="../">Up</a>
<script src="/ui/methods.js?v=1"></script>
</body></html>
""",
        encoding="utf-8",
    )
    (site / "compounds" / "psilocybin" / "index.html").write_text(
        """<!doctype html>
<html><head></head><body>
<main data-compound-data="/compounds/psilocybin/data.json" data-label="/not-a-path/"></main>
<a href="/">Back</a>
</body></html>
""",
        encoding="utf-8",
    )
    (site / "compounds" / "psilocybin" / "data.json").write_text("{}", encoding="utf-8")
    (site / "schema" / "graph_view_contract.json").write_text("{}", encoding="utf-8")
    (site / "ui" / "app.js").write_text(
        'const POINTER = "https://data.psychedelicskg.com/browser/active.json";\n'
        'function preview() { return ["/browser/active.json"]; }\n'
        'const worker = new Worker("/ui/analysis-worker.js?v=1");\n',
        encoding="utf-8",
    )
    (site / "ui" / "methods.js").write_text(
        'const PUBLIC = "https://data.psychedelicskg.com/browser/active.json";\n'
        'const PREVIEW = "/browser/active.json";\n',
        encoding="utf-8",
    )
    (site / "ui" / "styles.css").write_text("body { color: black; }\n", encoding="utf-8")
    (site / "ui" / "index.html").write_text("<html><head></head><body></body></html>", encoding="utf-8")
    return site
