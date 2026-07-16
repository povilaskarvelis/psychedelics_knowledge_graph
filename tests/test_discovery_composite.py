import json
from pathlib import Path

import pandas as pd

from pipeline.discovery.composite import compose_search_runs


def write_component(
    root: Path,
    *,
    run_id: str,
    mode: str,
    start_date: str,
    end_date: str,
    provider_record_id: str,
    reused_run_ids: list[str] | None = None,
) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    manifest = {
        "run_id": run_id,
        "protocol_id": "protocol",
        "strategy_path": "/strategy.json",
        "strategy_hash": "strategy",
        "config_path": "/scope.yaml",
        "provider_config_path": "/provider.yaml",
        "scope_hash": "scope",
        "scope_snapshot": {"allowed_compounds": ["Psilocybin"]},
        "mode": mode,
        "coverage_start_date": start_date,
        "coverage_end_date": end_date,
        "providers": ["pubmed"],
        "datasets": ["mechanistic"],
        "layers": ["core", "scope"],
        "status": "complete",
        "completion_gate_passed": True,
        "provider_errors": [],
        "reused_run_ids": reused_run_ids or [],
        "coverage_contract": {
            "historical_gap": {"start_date": "1800-01-01", "end_date": "2026-05-13"},
            "recent_update": {
                "run_id": "update",
                "start_date": "2026-05-14",
                "end_date": "2026-07-15",
            },
            "all_time_scope_reuse_count": 0,
        },
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    execution_id = f"exec_{run_id}"
    plan = pd.DataFrame(
        [
            {
                "execution_id": execution_id,
                "search_id": f"search_{run_id}",
                "dataset": "mechanistic",
                "provider": "pubmed",
                "layer": "core",
                "search_type": "two_block_core",
                "module_id": "target",
                "query": "psilocybin",
                "compound": "",
                "entity": "",
                "entity_type": "domain",
                "search_surface": "text_word_and_controlled_vocabulary",
                "date_basis": "publication",
                "start_date": start_date,
                "end_date": end_date,
                "protocol_id": "protocol",
                "strategy_hash": "strategy",
                "scope_hash": "scope",
            }
        ]
    )
    plan.to_parquet(run_dir / "search_plan.parquet", index=False)
    executions = plan.copy()
    executions["status"] = "complete"
    executions["expected_total"] = 1
    executions["retrieved_total"] = 1
    executions["partition_count"] = 1
    executions["pending_partition_count"] = 0
    executions["page_count"] = 1
    executions["count_request_count"] = 1
    executions["error"] = ""
    executions["started_at_utc"] = "2026-07-15T00:00:00+00:00"
    executions["completed_at_utc"] = "2026-07-15T00:01:00+00:00"
    executions.to_parquet(run_dir / "query_executions.parquet", index=False)
    hit = {
        "provider": "pubmed",
        "provider_record_id": provider_record_id,
        "pmid": provider_record_id.split(":")[-1],
        "pmcid": "",
        "doi": f"10.1000/{provider_record_id.split(':')[-1]}",
        "openalex_id": "",
        "semantic_scholar_id": "",
        "title": f"Record {provider_record_id}",
        "authors": "A Author",
        "publication_year": end_date[:4],
        "publication_date": end_date,
        "journal": "Journal",
        "publication_type": "article",
        "language": "eng",
        "abstract": "",
        "run_id": run_id,
        "protocol_id": "protocol",
        "execution_id": execution_id,
        "search_id": f"search_{run_id}",
        "dataset": "mechanistic",
        "layer": "core",
        "search_type": "two_block_core",
        "module_id": "target",
        "compound": "",
        "entity": "",
        "entity_type": "domain",
        "date_basis": "publication",
        "search_surface": "text_word_and_controlled_vocabulary",
        "partition_id": f"part_{run_id}",
        "partition_start_date": start_date,
        "partition_end_date": end_date,
        "page_index": 0,
        "retrieved_at_utc": "2026-07-15T00:00:30+00:00",
    }
    pd.DataFrame([hit]).to_parquet(run_dir / "provider_hits.parquet", index=False)
    return run_dir


def test_compose_search_runs_creates_one_promotable_full_baseline(tmp_path: Path) -> None:
    update = write_component(
        tmp_path,
        run_id="update",
        mode="update",
        start_date="2026-05-14",
        end_date="2026-07-15",
        provider_record_id="pmid:2",
    )
    gap = write_component(
        tmp_path,
        run_id="gap",
        mode="historical_gap",
        start_date="1800-01-01",
        end_date="2026-05-13",
        provider_record_id="pmid:1",
        reused_run_ids=["update"],
    )
    run_dir = tmp_path / "composite"
    manifest = compose_search_runs(
        run_dir=run_dir,
        run_id="composite",
        update_run_dir=update,
        historical_gap_run_dir=gap,
    )

    assert manifest["status"] == "complete"
    assert manifest["completion_gate_passed"]
    assert manifest["coverage_start_date"] == "1800-01-01"
    assert manifest["coverage_end_date"] == "2026-07-15"
    assert manifest["advances_standard_update_coverage"]
    assert manifest["establishes_scope_baseline"]
    assert manifest["calibration_status"] == "disabled_by_operator"
    assert manifest["counts"]["query_executions"] == 2
    assert manifest["counts"]["provider_records"] == 2
    hits = pd.read_parquet(run_dir / "provider_hits.parquet")
    assert set(hits["component_run_id"]) == {"update", "gap"}
    assert set(hits["run_id"]) == {"composite"}
    assert (run_dir / "search_calibration_groups.csv").exists()


def test_compose_search_runs_resumes_recognized_partial_materialization(tmp_path: Path) -> None:
    update = write_component(
        tmp_path,
        run_id="update",
        mode="update",
        start_date="2026-05-14",
        end_date="2026-07-15",
        provider_record_id="pmid:2",
    )
    gap = write_component(
        tmp_path,
        run_id="gap",
        mode="historical_gap",
        start_date="1800-01-01",
        end_date="2026-05-13",
        provider_record_id="pmid:1",
        reused_run_ids=["update"],
    )
    run_dir = tmp_path / "composite"
    run_dir.mkdir()
    pd.DataFrame([{"execution_id": "interrupted"}]).to_parquet(
        run_dir / "query_executions.parquet", index=False
    )

    manifest = compose_search_runs(
        run_dir=run_dir,
        run_id="composite",
        update_run_dir=update,
        historical_gap_run_dir=gap,
    )

    assert manifest["status"] == "complete"
    assert manifest["completion_gate_passed"]
    assert manifest["counts"]["provider_records"] == 2
