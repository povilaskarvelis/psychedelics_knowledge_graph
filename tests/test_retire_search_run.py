import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.discovery.retire_search_run import retire_run


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def make_run(tmp_path: Path, *, status: str = "paused_budget") -> Path:
    run_dir = tmp_path / "runs" / "test_run"
    run_dir.mkdir(parents=True)
    write_json(
        run_dir / "run_manifest.json",
        {
            "run_id": "test_run",
            "protocol_id": "test_protocol",
            "status": status,
            "completion_gate_passed": status == "complete",
        },
    )
    write_json(
        run_dir / "run_state.json",
        {
            "updated_at_utc": "2026-07-15T00:00:00+00:00",
            "executions": {
                "one": {"status": "complete", "expected_total": 2, "retrieved_total": 2},
                "two": {"status": "pending", "expected_total": 0, "retrieved_total": 0},
            },
        },
    )
    pd.DataFrame([{"execution_id": "one"}]).to_parquet(run_dir / "search_plan.parquet")
    pd.DataFrame([{"execution_id": "one", "status": "complete"}]).to_parquet(
        run_dir / "query_executions.parquet"
    )
    pd.DataFrame(
        [
            {
                "provider": "pubmed",
                "provider_record_id": "pmid:1",
                "search_type": "direct_pair",
                "title": "Exclusive pair record",
            },
            {
                "provider": "pubmed",
                "provider_record_id": "pmid:2",
                "search_type": "direct_pair",
                "title": "Rediscovered pair record",
            },
            {
                "provider": "pubmed",
                "provider_record_id": "pmid:2",
                "search_type": "two_block_core",
                "title": "Rediscovered pair record",
            },
        ]
    ).to_parquet(run_dir / "provider_hits.parquet")
    pd.DataFrame([{"provider_record_id": "pmid:1"}, {"provider_record_id": "pmid:2"}]).to_parquet(
        run_dir / "retrieved_records.parquet"
    )
    (run_dir / "provider_hits.checkpoint.jsonl").write_text("large cache\n", encoding="utf-8")
    return run_dir


def test_retirement_dry_run_does_not_change_files(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    report = retire_run(
        run_dir=run_dir,
        archive_root=tmp_path / "retired",
        reason="superseded strategy",
        apply=False,
    )
    assert run_dir.exists()
    assert not (tmp_path / "retired").exists()
    assert report["exclusive_direct_pair_record_count"] == 1
    assert report["retrieved_record_count"] == 2


def test_retirement_preserves_audit_bundle_and_removes_bulk_run(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    report = retire_run(
        run_dir=run_dir,
        archive_root=tmp_path / "retired",
        reason="superseded strategy",
        apply=True,
    )
    archive = tmp_path / "retired" / "test_run"
    assert not run_dir.exists()
    assert archive.exists()
    assert (archive / "run_manifest.json").exists()
    assert (archive / "search_plan.parquet").exists()
    assert (archive / "query_executions.parquet").exists()
    assert (archive / "run_state_summary.json").exists()
    assert (archive / "exclusive_direct_pair_records.csv").exists()
    assert not (archive / "provider_hits.parquet").exists()
    assert not (archive / "retrieved_records.parquet").exists()
    assert not (archive / "provider_hits.checkpoint.jsonl").exists()
    assert report["reclaimed_size_bytes"] > 0


def test_retirement_refuses_promoted_or_promotable_run(tmp_path: Path) -> None:
    promoted = make_run(tmp_path / "promoted", status="promoted")
    with pytest.raises(RuntimeError, match="promoted"):
        retire_run(run_dir=promoted, archive_root=tmp_path / "retired", reason="no", apply=True)

    complete = make_run(tmp_path / "complete", status="complete")
    with pytest.raises(RuntimeError, match="promotable"):
        retire_run(run_dir=complete, archive_root=tmp_path / "retired", reason="no", apply=True)
