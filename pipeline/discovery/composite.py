"""Plan non-duplicative historical gaps and compose complete search components."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from .artifacts import (
    cleanup_temporary_directory,
    compose_hits,
    materialize_records_from_hits,
    query_group_metrics,
)
from .calibration import (
    CALIBRATION_GROUPS_NAME,
    CALIBRATION_REPORT_NAME,
    KNOWN_COVERAGE_NAME,
    build_calibration_report,
)
from .providers import utc_now
from .runner import atomic_write_json, read_json
from .strategy import (
    SUPPORTED_LAYERS,
    SearchExecution,
    build_search_plan,
    clean,
    normalized_key,
)


def _previous_day(value: str) -> str:
    return (dt.date.fromisoformat(value) - dt.timedelta(days=1)).isoformat()


def _execution_counts(
    executions: list[SearchExecution], providers: list[str], datasets: list[str]
) -> dict:
    return {
        "by_provider": {
            provider: sum(item.provider == provider for item in executions) for provider in providers
        },
        "by_dataset": {
            dataset: sum(item.dataset == dataset for item in executions) for dataset in datasets
        },
        "by_layer": {
            layer: sum(item.layer == layer for item in executions) for layer in SUPPORTED_LAYERS
        },
        "by_date_basis": {
            basis: sum(item.date_basis == basis for item in executions)
            for basis in sorted({item.date_basis for item in executions})
        },
    }


def build_historical_gap_plan(
    *,
    reuse_run_dir: Path,
    strategy_path: Path,
    config_path: Path,
    history_path: Path,
    providers: list[str],
    datasets: list[str],
    layers: list[str],
    allow_large_plan: bool = False,
) -> tuple[list[SearchExecution], dict]:
    reuse_run_dir = Path(reuse_run_dir).resolve()
    manifest = read_json(reuse_run_dir / "run_manifest.json")
    if manifest.get("status") != "complete" or not manifest.get("completion_gate_passed"):
        raise RuntimeError("The reused update run must be complete before planning its historical gap")
    if manifest.get("mode") != "update":
        raise ValueError("Historical-gap reuse currently requires a completed update run")

    gap_end = _previous_day(clean(manifest.get("coverage_start_date")))
    executions, metadata = build_search_plan(
        strategy_path=Path(strategy_path),
        config_path=Path(config_path),
        history_path=Path(history_path),
        mode="full",
        providers=providers,
        datasets=datasets,
        layers=layers,
        end_date=gap_end,
        include_index_updates=False,
        include_openalex_index_updates=False,
        include_scope_delta=False,
        allow_large_plan=allow_large_plan,
    )
    if metadata["strategy_hash"] != manifest.get("strategy_hash"):
        raise ValueError("Reused update and historical-gap plan have different strategy hashes")
    if metadata["scope_hash"] != manifest.get("scope_hash"):
        raise ValueError("Reused update and historical-gap plan have different scope hashes")
    if metadata["protocol_id"] != manifest.get("protocol_id"):
        raise ValueError("Reused update and historical-gap plan have different protocols")

    source_plan = pd.read_parquet(reuse_run_dir / "search_plan.parquet")
    source_state = read_json(reuse_run_dir / "run_state.json").get("executions", {})
    full_start = metadata["coverage_start_date"]
    reuse_end = clean(manifest.get("coverage_end_date"))
    reusable_scope: set[tuple[str, str]] = set()
    for row in source_plan.to_dict("records"):
        execution_id = clean(row.get("execution_id"))
        state = source_state.get(execution_id, {})
        if (
            clean(row.get("layer")) == "scope_delta"
            and clean(row.get("search_type")) == "historical_compound_identity"
            and clean(row.get("date_basis")) == "publication"
            and clean(row.get("start_date")) <= full_start
            and clean(row.get("end_date")) >= reuse_end
            and state.get("status") == "complete"
        ):
            reusable_scope.add(
                (clean(row.get("provider")), normalized_key(row.get("compound")))
            )

    filtered = [
        execution
        for execution in executions
        if not (
            execution.layer == "scope"
            and (execution.provider, normalized_key(execution.compound)) in reusable_scope
        )
    ]
    excluded = len(executions) - len(filtered)
    if reusable_scope and excluded != len(reusable_scope):
        raise RuntimeError(
            f"Expected to reuse {len(reusable_scope)} provider-compound searches, excluded {excluded}"
        )
    metadata.update(
        {
            "schema_version": "living_search_plan_historical_gap_v1",
            "mode": "historical_gap",
            "coverage_start_date": full_start,
            "coverage_end_date": gap_end,
            "include_index_updates": False,
            "include_openalex_index_updates": False,
            "include_scope_delta": False,
            "advances_standard_update_coverage": False,
            "establishes_scope_baseline": False,
            "promotable_independently": False,
            "component_role": "historical_gap",
            "reused_run_ids": [manifest["run_id"]],
            "reused_all_time_scope_searches": [
                {"provider": provider, "compound_key": compound}
                for provider, compound in sorted(reusable_scope)
            ],
            "reused_execution_count": excluded,
            "coverage_contract": {
                "historical_gap": {"start_date": full_start, "end_date": gap_end},
                "recent_update": {
                    "run_id": manifest["run_id"],
                    "start_date": manifest["coverage_start_date"],
                    "end_date": manifest["coverage_end_date"],
                },
                "all_time_scope_reuse_count": excluded,
            },
            "execution_count": len(filtered),
            "execution_counts": _execution_counts(filtered, providers, datasets),
        }
    )
    return filtered, metadata


def mark_reused_component(run_dir: Path, *, role: str) -> dict:
    path = Path(run_dir) / "run_manifest.json"
    manifest = read_json(path)
    if manifest.get("status") == "promoted":
        raise RuntimeError("A promoted run cannot be converted into a composite component")
    manifest["promotable_independently"] = False
    manifest["component_role"] = role
    manifest["reserved_for_composite_baseline"] = True
    manifest["updated_at_utc"] = utc_now()
    atomic_write_json(path, manifest)
    return manifest


def _component(run_dir: Path) -> tuple[dict, pd.DataFrame, pd.DataFrame, Path]:
    run_dir = Path(run_dir).resolve()
    manifest = read_json(run_dir / "run_manifest.json")
    if manifest.get("status") != "complete" or not manifest.get("completion_gate_passed"):
        raise RuntimeError(f"Component run is not complete: {manifest.get('run_id', run_dir.name)}")
    plan = pd.read_parquet(run_dir / "search_plan.parquet")
    executions = pd.read_parquet(run_dir / "query_executions.parquet")
    if not executions["status"].astype(str).eq("complete").all():
        raise RuntimeError(f"Component has incomplete executions: {manifest.get('run_id')}")
    hits_path = run_dir / "provider_hits.parquet"
    if not hits_path.exists():
        raise FileNotFoundError(f"Component is missing provider hits: {manifest.get('run_id')}")
    return manifest, plan, executions, hits_path


def compose_search_runs(
    *,
    run_dir: Path,
    run_id: str,
    update_run_dir: Path,
    historical_gap_run_dir: Path,
) -> dict:
    run_dir = Path(run_dir).resolve()
    if run_dir.exists() and any(run_dir.iterdir()):
        if (run_dir / "run_manifest.json").exists():
            raise FileExistsError(f"Composite run directory is not empty: {run_dir}")
        allowed_partial = {
            "search_plan.parquet",
            "search_plan.csv",
            "query_executions.parquet",
            "provider_hits.parquet",
            "provider_hits.parquet.tmp",
            "retrieved_records.parquet.tmp",
            ".duckdb_tmp",
            ".duckdb_record_parts",
        }
        unexpected = {path.name for path in run_dir.iterdir()} - allowed_partial
        if unexpected:
            raise FileExistsError(
                f"Composite run directory contains unrecognized partial artifacts: "
                f"{', '.join(sorted(unexpected))}"
            )
    update, update_plan, update_exec, update_hits_path = _component(update_run_dir)
    gap, gap_plan, gap_exec, gap_hits_path = _component(historical_gap_run_dir)
    for field in ("protocol_id", "strategy_hash", "scope_hash"):
        if update.get(field) != gap.get(field):
            raise ValueError(f"Component {field} values differ")
    if gap.get("mode") != "historical_gap" or update["run_id"] not in gap.get("reused_run_ids", []):
        raise ValueError("Historical-gap component does not declare reuse of the update component")
    expected_gap_end = _previous_day(clean(update.get("coverage_start_date")))
    if clean(gap.get("coverage_end_date")) != expected_gap_end:
        raise ValueError("Component coverage windows are not contiguous")

    plan = pd.concat([gap_plan, update_plan], ignore_index=True)
    if plan["execution_id"].duplicated().any():
        raise ValueError("Composite plan contains duplicate execution IDs")
    executions = pd.concat([gap_exec, update_exec], ignore_index=True)

    run_dir.mkdir(parents=True, exist_ok=True)
    plan.to_parquet(run_dir / "search_plan.parquet", index=False)
    plan.to_csv(run_dir / "search_plan.csv", index=False)
    executions.to_parquet(run_dir / "query_executions.parquet", index=False)
    hits_path = run_dir / "provider_hits.parquet"
    records_path = run_dir / "retrieved_records.parquet"
    component_mtime = max(gap_hits_path.stat().st_mtime, update_hits_path.stat().st_mtime)
    if not hits_path.exists() or hits_path.stat().st_mtime < component_mtime:
        compose_hits(
            gap_hits_path=gap_hits_path,
            gap_run_id=gap["run_id"],
            update_hits_path=update_hits_path,
            update_run_id=update["run_id"],
            composite_run_id=run_id,
            output_path=hits_path,
        )
    artifact_counts = materialize_records_from_hits(hits_path, records_path)

    now = utc_now()
    manifest = {
        "schema_version": "living_search_composite_run_v1",
        "run_id": run_id,
        "protocol_id": update["protocol_id"],
        "strategy_path": update["strategy_path"],
        "strategy_hash": update["strategy_hash"],
        "config_path": update.get("config_path", ""),
        "provider_config_path": update.get("provider_config_path", ""),
        "scope_hash": update["scope_hash"],
        "scope_snapshot": update["scope_snapshot"],
        "mode": "composite_full",
        "coverage_start_date": gap["coverage_start_date"],
        "coverage_end_date": update["coverage_end_date"],
        "providers": update["providers"],
        "datasets": update["datasets"],
        "layers": ["core", "scope"],
        "include_index_updates": True,
        "include_openalex_index_updates": bool(update.get("include_openalex_index_updates", False)),
        "include_scope_delta": True,
        "advances_standard_update_coverage": True,
        "establishes_scope_baseline": True,
        "promotable_independently": True,
        "component_run_ids": [gap["run_id"], update["run_id"]],
        "coverage_contract": gap["coverage_contract"],
        "calibration": {
            "known_relevant_check_enabled": False,
            "required_for_promotion": False,
            "disabled_reason": "Known-record recall calibration was not requested for this baseline.",
        },
        "generated_at_utc": now,
        "updated_at_utc": now,
        "status": "materializing",
        "retrieval_completion_gate_passed": True,
        "calibration_gate_passed": False,
        "completion_gate_passed": False,
        "counts": {
            "query_executions": int(len(executions)),
            "complete_executions": int(executions["status"].astype(str).eq("complete").sum()),
            "failed_executions": 0,
            **artifact_counts,
        },
        "outputs": {
            "run_directory": str(run_dir),
            "search_plan_parquet": str((run_dir / "search_plan.parquet").resolve()),
            "search_plan_csv": str((run_dir / "search_plan.csv").resolve()),
            "query_executions_parquet": str((run_dir / "query_executions.parquet").resolve()),
            "provider_hits_parquet": str((run_dir / "provider_hits.parquet").resolve()),
            "retrieved_records_parquet": str((run_dir / "retrieved_records.parquet").resolve()),
            "search_calibration_report": str((run_dir / CALIBRATION_REPORT_NAME).resolve()),
            "search_calibration_groups": str((run_dir / CALIBRATION_GROUPS_NAME).resolve()),
            "known_relevant_coverage": str((run_dir / KNOWN_COVERAGE_NAME).resolve()),
        },
        "provider_errors": [],
        "resolved_component_provider_errors": update.get("provider_errors", []) + gap.get("provider_errors", []),
    }
    calibration_hits = pd.read_parquet(
        records_path,
        columns=["provider", "provider_record_id", "doi", "pmid", "openalex_id", "publication_date"],
    )
    group_metrics = query_group_metrics(hits_path, executions)
    calibration_report, calibration_gate = build_calibration_report(
        run_dir=run_dir,
        manifest=manifest,
        execution_rows=executions.to_dict("records"),
        hits=calibration_hits,
        retrieval_complete=True,
        group_metrics=group_metrics,
    )
    manifest["calibration_gate_passed"] = calibration_gate
    manifest["calibration_status"] = calibration_report["known_relevant_coverage"]["status"]
    manifest["completion_gate_passed"] = bool(calibration_gate)
    manifest["status"] = "complete" if calibration_gate else "calibration_failed"
    manifest["updated_at_utc"] = utc_now()
    atomic_write_json(run_dir / "run_manifest.json", manifest)
    cleanup_temporary_directory(run_dir)
    return manifest
