import hashlib
import json
from pathlib import Path

import pytest

from scripts.serve_site import (
    LOCAL_POINTER_SCHEMA,
    build_local_preview,
    validated_published_preview,
)


def write_preview_fixture(root: Path) -> None:
    run_id = "candidate_run"
    run_dir = root / "data/processed/graph_payload_runs" / run_id
    run_dir.mkdir(parents=True)
    files = {}
    mappings = {
        "graph_bootstraps": {},
        "dashboard_bootstraps": {},
        "detail_bootstraps": {},
    }
    for manifest_key, logical_prefix in (
        ("graph_bootstraps", "graph"),
        ("dashboard_bootstraps", "dashboard"),
        ("detail_bootstraps", "detail"),
    ):
        for source_key in ("primary", "meta_analyses", "reviews"):
            filename = f"{logical_prefix}_bootstrap_{source_key}.json"
            path = run_dir / filename
            path.write_text(
                json.dumps({"kind": logical_prefix, "source": source_key}),
                encoding="utf-8",
            )
            relative = path.relative_to(root).as_posix()
            mappings[manifest_key][source_key] = relative
            files[f"{logical_prefix}:{source_key}"] = {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
    manifest = {
        "schema_version": "route_native_evidence_manifest_v1",
        "release_id": "candidate_run:public:test",
        "evidence_release_id": "candidate_run:evidence:test",
        "files": files,
        **mappings,
    }
    (run_dir / "graph_payload_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    active_pointer = root / "data/processed/graph_payload_active.json"
    active_pointer.write_text(
        json.dumps({"run_id": run_id, "intentionally_incomplete": True}),
        encoding="utf-8",
    )
    methods_dir = root / "data/kg/views"
    methods_dir.mkdir(parents=True)
    for filename in (
        "pipeline_status_graph.json",
        "methods_bibliography.json",
        "graph_inclusion_dispositions.json",
    ):
        (methods_dir / filename).write_text(
            json.dumps(
                {
                    "view": filename,
                    "run_id": run_id,
                    "release_id": "candidate_run:evidence:test",
                }
            ),
            encoding="utf-8",
        )


def test_local_preview_builds_one_verified_pointer_for_graph_and_methods(
    tmp_path: Path,
) -> None:
    write_preview_fixture(tmp_path)

    pointer, allowed_files = build_local_preview(tmp_path)

    assert pointer["schema_version"] == LOCAL_POINTER_SCHEMA
    assert pointer["run_id"] == "candidate_run"
    assert pointer["active_graph_bootstraps"]["primary"].endswith(
        "/graph_bootstrap_primary.json"
    )
    assert pointer["methods"]["bibliography"] == (
        "data/kg/views/methods_bibliography.json"
    )
    assert "/data/kg/views/methods_bibliography.json" in allowed_files
    assert len(allowed_files) == 13


def test_local_preview_can_select_an_unpublished_run_without_changing_active_pointer(
    tmp_path: Path,
) -> None:
    write_preview_fixture(tmp_path)
    active_pointer = tmp_path / "data/processed/graph_payload_active.json"
    active_pointer.write_text(json.dumps({"run_id": "another_run"}), encoding="utf-8")

    pointer, _ = build_local_preview(tmp_path, requested_run_id="candidate_run")

    assert pointer["run_id"] == "candidate_run"


def test_local_preview_rejects_a_corrupted_graph_payload(tmp_path: Path) -> None:
    write_preview_fixture(tmp_path)
    corrupt = (
        tmp_path
        / "data/processed/graph_payload_runs/candidate_run/graph_bootstrap_primary.json"
    )
    corrupt.write_text("corrupt", encoding="utf-8")

    with pytest.raises(ValueError, match="size mismatch"):
        build_local_preview(tmp_path)


def test_local_preview_rejects_methods_from_another_release(tmp_path: Path) -> None:
    write_preview_fixture(tmp_path)
    bibliography = tmp_path / "data/kg/views/methods_bibliography.json"
    payload = json.loads(bibliography.read_text(encoding="utf-8"))
    payload["release_id"] = "older:evidence:release"
    bibliography.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Methods data release ID mismatch"):
        build_local_preview(tmp_path)


def test_published_preview_proxies_only_active_immutable_r2_objects() -> None:
    prefix = "browser/releases/run/release"
    graph_key = f"{prefix}/graph_bootstrap_primary.json"
    pointer = {
        "schema_version": "psychedelics_kg_browser_r2_active_v1",
        "object_prefix": prefix,
        "active_manifest": f"{prefix}/graph_payload_manifest.json",
        "active_graph_bootstraps": {"primary": graph_key},
        "active_dashboard_bootstraps": {"primary": f"{prefix}/dashboard.json"},
        "active_detail_bootstraps": {"primary": f"{prefix}/detail.json"},
        "methods": {"bibliography": f"{prefix}/methods_bibliography.json"},
        "files": {"graph:primary": {"key": graph_key}},
    }

    allowed = validated_published_preview(pointer)

    assert allowed[f"/{graph_key}"] == f"https://data.psychedelicskg.com/{graph_key}"
    assert all(path.startswith(f"/{prefix}/") for path in allowed)


def test_published_preview_rejects_an_object_outside_the_active_release() -> None:
    prefix = "browser/releases/run/release"
    pointer = {
        "schema_version": "psychedelics_kg_browser_r2_active_v1",
        "object_prefix": prefix,
        "active_manifest": f"{prefix}/graph_payload_manifest.json",
        "active_graph_bootstraps": {"primary": f"{prefix}/graph.json"},
        "active_dashboard_bootstraps": {"primary": f"{prefix}/dashboard.json"},
        "active_detail_bootstraps": {"primary": f"{prefix}/detail.json"},
        "methods": {"bibliography": "browser/releases/other/bibliography.json"},
        "files": {"graph:primary": {"key": f"{prefix}/graph.json"}},
    }

    with pytest.raises(ValueError, match="Unsafe published preview object key"):
        validated_published_preview(pointer)
