"""Resumable search-run state machine and artifact materialization."""

from __future__ import annotations

from collections import defaultdict
import datetime as dt
import json
import math
from pathlib import Path
import time
from typing import Iterable

import pandas as pd

from .artifacts import (
    cleanup_temporary_directory,
    materialize_hits_from_checkpoint,
    materialize_records_from_hits,
    query_group_metrics,
)
from .calibration import (
    CALIBRATION_GROUPS_NAME,
    CALIBRATION_REPORT_NAME,
    KNOWN_COVERAGE_NAME,
    build_calibration_report,
)
from .providers import RequestBudgetExhausted, utc_now
from .strategy import SearchExecution, stable_hash


RUN_MANIFEST_NAME = "run_manifest.json"
RUN_STATE_NAME = "run_state.json"
PLAN_PARQUET_NAME = "search_plan.parquet"
PLAN_CSV_NAME = "search_plan.csv"
HITS_JSONL_NAME = "provider_hits.checkpoint.jsonl"
HITS_PARQUET_NAME = "provider_hits.parquet"
RECORDS_PARQUET_NAME = "retrieved_records.parquet"
EXECUTIONS_PARQUET_NAME = "query_executions.parquet"


def atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def append_jsonl(path: Path, rows: Iterable[dict]) -> int:
    values = list(rows)
    if not values:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in values:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
    return len(values)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    last_error: tuple[int, json.JSONDecodeError] | None = None
    for attempt in range(3):
        rows: list[dict] = []
        last_error = None
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, start=1):
                if not raw.strip():
                    continue
                try:
                    value = json.loads(raw)
                except json.JSONDecodeError as error:
                    last_error = (line_number, error)
                    break
                if isinstance(value, dict):
                    rows.append(value)
        if last_error is None:
            return rows
        if attempt < 2:
            time.sleep(0.2 * (attempt + 1))
    line_number, error = last_error
    raise ValueError(f"Malformed checkpoint JSONL at {path}:{line_number}") from error


def partition_id(execution_id: str, start_date: str, end_date: str) -> str:
    return f"part_{stable_hash([execution_id, start_date, end_date], 18)}"


def split_date_range(start_date: str, end_date: str) -> tuple[dict, dict]:
    start = dt.date.fromisoformat(start_date)
    end = dt.date.fromisoformat(end_date)
    if start >= end:
        raise ValueError(f"Cannot split one-day range {start_date}..{end_date}")
    midpoint = start + (end - start) // 2
    return (
        {"start_date": start.isoformat(), "end_date": midpoint.isoformat()},
        {"start_date": (midpoint + dt.timedelta(days=1)).isoformat(), "end_date": end.isoformat()},
    )


def initial_execution_state(execution: SearchExecution) -> dict:
    return {
        "status": "pending",
        "pending_ranges": [{"start_date": execution.start_date, "end_date": execution.end_date}],
        "active_partition": None,
        "completed_partitions": [],
        "expected_total": 0,
        "retrieved_total": 0,
        "page_count": 0,
        "count_request_count": 0,
        "error": "",
        "started_at_utc": "",
        "completed_at_utc": "",
    }


def prepare_run(
    *,
    run_dir: Path,
    run_id: str,
    executions: list[SearchExecution],
    plan_metadata: dict,
    request_budgets: dict[str, int],
) -> dict:
    run_dir = Path(run_dir)
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"Run directory already exists and is not empty: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    plan_rows = [execution.to_dict() for execution in executions]
    pd.DataFrame(plan_rows).to_parquet(run_dir / PLAN_PARQUET_NAME, engine="pyarrow", index=False)
    pd.DataFrame(plan_rows).to_csv(run_dir / PLAN_CSV_NAME, index=False)
    generated_at = utc_now()
    manifest = {
        **plan_metadata,
        "schema_version": "living_search_run_v3",
        "run_id": run_id,
        "generated_at_utc": generated_at,
        "updated_at_utc": generated_at,
        "status": "planned",
        "retrieval_completion_gate_passed": False,
        "calibration_gate_passed": False,
        "completion_gate_passed": False,
        "request_budgets_per_session": request_budgets,
        "provider_sessions": [],
        "counts": {
            "query_executions": len(executions),
            "complete_executions": 0,
            "failed_executions": 0,
            "provider_hits": 0,
            "provider_records": 0,
            "records_with_doi": 0,
            "records_without_doi": 0,
        },
        "outputs": {
            "run_directory": str(run_dir.resolve()),
            "search_plan_parquet": str((run_dir / PLAN_PARQUET_NAME).resolve()),
            "search_plan_csv": str((run_dir / PLAN_CSV_NAME).resolve()),
            "query_executions_parquet": str((run_dir / EXECUTIONS_PARQUET_NAME).resolve()),
            "provider_hits_parquet": str((run_dir / HITS_PARQUET_NAME).resolve()),
            "retrieved_records_parquet": str((run_dir / RECORDS_PARQUET_NAME).resolve()),
            "checkpoint_jsonl": str((run_dir / HITS_JSONL_NAME).resolve()),
            "search_calibration_report": str((run_dir / CALIBRATION_REPORT_NAME).resolve()),
            "search_calibration_groups": str((run_dir / CALIBRATION_GROUPS_NAME).resolve()),
            "known_relevant_coverage": str((run_dir / KNOWN_COVERAGE_NAME).resolve()),
        },
        "provider_errors": [],
    }
    state = {
        "schema_version": "living_search_state_v3",
        "run_id": run_id,
        "updated_at_utc": generated_at,
        "executions": {execution.execution_id: initial_execution_state(execution) for execution in executions},
    }
    atomic_write_json(run_dir / RUN_MANIFEST_NAME, manifest)
    atomic_write_json(run_dir / RUN_STATE_NAME, state)
    return manifest


def load_plan(run_dir: Path) -> list[SearchExecution]:
    frame = pd.read_parquet(Path(run_dir) / PLAN_PARQUET_NAME)
    return [SearchExecution(**{field: row[field] for field in SearchExecution.__dataclass_fields__}) for row in frame.to_dict("records")]


def checkpoint_index(rows: Iterable[dict]) -> dict[tuple[str, str], set[str]]:
    index: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        execution_id = str(row.get("execution_id", ""))
        part_id = str(row.get("partition_id", ""))
        record_id = str(row.get("provider_record_id", ""))
        if execution_id and part_id and record_id:
            index[(execution_id, part_id)].add(record_id)
    return index


def _partition_limit(provider: str, provider_config: dict) -> int:
    return max(1, int(provider_config.get(provider, {}).get("partition_max_records", 5000)))


def _page_size(provider: str, provider_config: dict) -> int:
    return max(1, int(provider_config.get(provider, {}).get("page_size", 100)))


def _reconciliation_retries(provider: str, provider_config: dict) -> int:
    return max(0, int(provider_config.get(provider, {}).get("reconciliation_retries", 1)))


def _accepted_count_drift(
    *,
    provider: str,
    provider_config: dict,
    expected: int,
    retrieved: int,
) -> tuple[bool, int, int]:
    shortfall = max(0, expected - retrieved)
    config = provider_config.get(provider, {})
    absolute_limit = max(0, int(config.get("count_drift_tolerance_records", 3)))
    fraction_limit = max(0.0, float(config.get("count_drift_tolerance_fraction", 0.001)))
    proportional_limit = math.floor(max(0, expected) * fraction_limit)
    allowed = min(absolute_limit, proportional_limit) if expected else 0
    return shortfall > 0 and shortfall <= allowed, shortfall, allowed


def _recompute_execution_counts(execution_state: dict, hit_index: dict[tuple[str, str], set[str]], execution_id: str) -> None:
    completed = execution_state.get("completed_partitions", [])
    active = execution_state.get("active_partition")
    execution_state["expected_total"] = sum(int(item.get("expected_count", 0)) for item in completed)
    execution_state["retrieved_total"] = sum(
        len(hit_index.get((execution_id, str(item.get("partition_id", ""))), set())) for item in completed
    )
    if isinstance(active, dict):
        execution_state["expected_total"] += int(active.get("expected_count", 0))
        execution_state["retrieved_total"] += len(
            hit_index.get((execution_id, str(active.get("partition_id", ""))), set())
        )


def _execution_report_rows(plan: list[SearchExecution], state: dict) -> list[dict]:
    rows: list[dict] = []
    for execution in plan:
        item = state["executions"][execution.execution_id]
        completed_partitions = item.get("completed_partitions", [])
        accepted_drift = [
            partition
            for partition in completed_partitions
            if partition.get("reconciliation_status") == "accepted_provider_count_drift"
        ]
        rows.append(
            {
                **execution.to_dict(),
                "status": item.get("status", ""),
                "expected_total": int(item.get("expected_total", 0)),
                "retrieved_total": int(item.get("retrieved_total", 0)),
                "partition_count": len(completed_partitions),
                "pending_partition_count": len(item.get("pending_ranges", [])),
                "page_count": int(item.get("page_count", 0)),
                "count_request_count": int(item.get("count_request_count", 0)),
                "accepted_count_drift_partitions": len(accepted_drift),
                "accepted_count_drift_records": sum(
                    int(partition.get("reconciliation_shortfall", 0))
                    for partition in accepted_drift
                ),
                "error": item.get("error", ""),
                "started_at_utc": item.get("started_at_utc", ""),
                "completed_at_utc": item.get("completed_at_utc", ""),
            }
        )
    return rows


def materialize_artifacts(run_dir: Path, plan: list[SearchExecution], state: dict, manifest: dict) -> dict:
    run_dir = Path(run_dir)
    checkpoint_path = run_dir / HITS_JSONL_NAME
    hits_path = run_dir / HITS_PARQUET_NAME
    records_path = run_dir / RECORDS_PARQUET_NAME
    if not hits_path.exists() or hits_path.stat().st_mtime < checkpoint_path.stat().st_mtime:
        materialize_hits_from_checkpoint(checkpoint_path, hits_path)
    artifact_counts = materialize_records_from_hits(hits_path, records_path)
    execution_rows = _execution_report_rows(plan, state)
    executions_frame = pd.DataFrame(execution_rows)
    executions_frame.to_parquet(run_dir / EXECUTIONS_PARQUET_NAME, engine="pyarrow", index=False)

    statuses = [row["status"] for row in execution_rows]
    complete = sum(status == "complete" for status in statuses)
    failed = sum(status == "failed" for status in statuses)
    manifest["counts"] = {
        "query_executions": len(execution_rows),
        "complete_executions": complete,
        "failed_executions": failed,
        **artifact_counts,
        "accepted_count_drift_partitions": sum(
            int(row.get("accepted_count_drift_partitions", 0)) for row in execution_rows
        ),
        "accepted_count_drift_records": sum(
            int(row.get("accepted_count_drift_records", 0)) for row in execution_rows
        ),
    }
    retrieval_complete = bool(execution_rows) and complete == len(execution_rows) and failed == 0
    manifest["retrieval_completion_gate_passed"] = retrieval_complete
    calibration_hits = pd.read_parquet(
        records_path,
        columns=["provider", "provider_record_id", "doi", "pmid", "openalex_id", "publication_date"],
    )
    group_metrics = query_group_metrics(hits_path, executions_frame)
    calibration_report, calibration_gate = build_calibration_report(
        run_dir=run_dir,
        manifest=manifest,
        execution_rows=execution_rows,
        hits=calibration_hits,
        retrieval_complete=retrieval_complete,
        group_metrics=group_metrics,
    )
    manifest["calibration_gate_passed"] = calibration_gate
    manifest["calibration_status"] = calibration_report["known_relevant_coverage"]["status"]
    manifest["completion_gate_passed"] = retrieval_complete and calibration_gate
    manifest["updated_at_utc"] = utc_now()
    atomic_write_json(run_dir / RUN_MANIFEST_NAME, manifest)
    cleanup_temporary_directory(run_dir)
    return manifest


def finalize_completed_retrieval(run_dir: Path) -> dict:
    """Recover or rerun artifact finalization after provider retrieval has stopped."""

    run_dir = Path(run_dir)
    manifest = read_json(run_dir / RUN_MANIFEST_NAME)
    state = read_json(run_dir / RUN_STATE_NAME)
    plan = load_plan(run_dir)
    statuses = [state["executions"][item.execution_id].get("status", "") for item in plan]
    if any(status in {"pending", "running"} for status in statuses):
        raise RuntimeError("Cannot finalize while query executions remain pending or running")
    manifest["status"] = "materializing"
    manifest["updated_at_utc"] = utc_now()
    atomic_write_json(run_dir / RUN_MANIFEST_NAME, manifest)
    manifest = materialize_artifacts(run_dir, plan, state, manifest)
    if manifest["completion_gate_passed"]:
        manifest["status"] = "complete"
    elif manifest.get("retrieval_completion_gate_passed") and not manifest.get(
        "calibration_gate_passed"
    ):
        manifest["status"] = "calibration_failed"
    elif any(status == "failed" for status in statuses):
        manifest["status"] = "failed"
    else:
        manifest["status"] = "incomplete"
    manifest["updated_at_utc"] = utc_now()
    atomic_write_json(run_dir / RUN_MANIFEST_NAME, manifest)
    return manifest


def execute_run(
    *,
    run_dir: Path,
    providers: dict[str, object],
    provider_config: dict,
    session_request_budgets: dict[str, int] | None = None,
    continue_on_error: bool = False,
    retry_failed: bool = True,
) -> dict:
    run_dir = Path(run_dir)
    manifest = read_json(run_dir / RUN_MANIFEST_NAME)
    state = read_json(run_dir / RUN_STATE_NAME)
    plan = load_plan(run_dir)
    # Publish the live state before loading a potentially large checkpoint or
    # making provider requests. Without this, a resumed process can be healthy
    # while the manifest continues to advertise its previous terminal status.
    manifest["status"] = "running"
    manifest["updated_at_utc"] = utc_now()
    atomic_write_json(run_dir / RUN_MANIFEST_NAME, manifest)
    raw_rows = read_jsonl(run_dir / HITS_JSONL_NAME)
    hit_index = checkpoint_index(raw_rows)
    paused_providers: set[str] = set()
    stopped_on_error = False

    for execution in plan:
        execution_state = state["executions"][execution.execution_id]
        if execution_state.get("status") == "complete":
            continue
        if execution.provider not in providers:
            continue
        if execution.provider in paused_providers:
            continue
        if execution_state.get("status") == "failed":
            if not retry_failed:
                continue
            # A failed execution can retain an active partition whose bounded
            # reconciliation attempts were exhausted in the prior session.
            # Resuming is an explicit new retry session, so give that partition
            # a fresh bounded recrawl allowance without weakening the count
            # reconciliation tolerance or discarding checkpointed provider IDs.
            active_partition = execution_state.get("active_partition")
            if isinstance(active_partition, dict):
                active_partition["reconciliation_attempts"] = 0
            execution_state["retry_count"] = int(execution_state.get("retry_count", 0)) + 1
            execution_state["status"] = "running"
            execution_state["error"] = ""
            execution_state["completed_at_utc"] = ""
        if not execution_state.get("started_at_utc"):
            execution_state["started_at_utc"] = utc_now()
        execution_state["status"] = "running"
        provider = providers[execution.provider]
        try:
            while execution_state.get("pending_ranges") or execution_state.get("active_partition"):
                active = execution_state.get("active_partition")
                if not active:
                    # Keep the range queued until its count request succeeds.
                    # A provider error or exhausted request budget can occur
                    # before any response; popping first would silently lose
                    # that range when the run resumes.
                    date_range = execution_state["pending_ranges"][0]
                    expected = int(provider.count(execution, date_range["start_date"], date_range["end_date"]))
                    execution_state["count_request_count"] += 1
                    execution_state["pending_ranges"].pop(0)
                    if expected > _partition_limit(execution.provider, provider_config):
                        if date_range["start_date"] == date_range["end_date"]:
                            raise RuntimeError(
                                f"provider_limit_unresolvable: {execution.provider} returned {expected} records "
                                f"for one day {date_range['start_date']}"
                            )
                        left, right = split_date_range(date_range["start_date"], date_range["end_date"])
                        execution_state["pending_ranges"] = [left, right, *execution_state["pending_ranges"]]
                        state["updated_at_utc"] = utc_now()
                        atomic_write_json(run_dir / RUN_STATE_NAME, state)
                        continue
                    part_id = partition_id(execution.execution_id, date_range["start_date"], date_range["end_date"])
                    active = {
                        "partition_id": part_id,
                        "start_date": date_range["start_date"],
                        "end_date": date_range["end_date"],
                        "expected_count": expected,
                        "initial_expected_count": expected,
                        "final_expected_count": expected,
                        "reconciliation_attempts": 0,
                        "next_token": "",
                        "page_index": 0,
                    }
                    execution_state["active_partition"] = active
                    _recompute_execution_counts(execution_state, hit_index, execution.execution_id)
                    if expected == 0:
                        execution_state["completed_partitions"].append(
                            {**active, "retrieved_count": 0, "completed_at_utc": utc_now()}
                        )
                        execution_state["active_partition"] = None
                        _recompute_execution_counts(execution_state, hit_index, execution.execution_id)
                        state["updated_at_utc"] = utc_now()
                        atomic_write_json(run_dir / RUN_STATE_NAME, state)
                        continue
                    state["updated_at_utc"] = utc_now()
                    atomic_write_json(run_dir / RUN_STATE_NAME, state)

                records, next_token = provider.fetch_page(
                    execution,
                    active["start_date"],
                    active["end_date"],
                    token=str(active.get("next_token", "")),
                    page_size=_page_size(execution.provider, provider_config),
                )
                retrieved_at = utc_now()
                part_key = (execution.execution_id, active["partition_id"])
                new_rows: list[dict] = []
                for record in records:
                    record_id = str(record.get("provider_record_id", ""))
                    if not record_id or record_id in hit_index[part_key]:
                        continue
                    hit_index[part_key].add(record_id)
                    new_rows.append(
                        {
                            **record,
                            "run_id": manifest["run_id"],
                            "protocol_id": execution.protocol_id,
                            "execution_id": execution.execution_id,
                            "search_id": execution.search_id,
                            "dataset": execution.dataset,
                            "layer": execution.layer,
                            "search_type": execution.search_type,
                            "module_id": execution.module_id,
                            "compound": execution.compound,
                            "entity": execution.entity,
                            "entity_type": execution.entity_type,
                            "date_basis": execution.date_basis,
                            "search_surface": execution.search_surface,
                            "partition_id": active["partition_id"],
                            "partition_start_date": active["start_date"],
                            "partition_end_date": active["end_date"],
                            "page_index": int(active.get("page_index", 0)),
                            "retrieved_at_utc": retrieved_at,
                        }
                    )
                append_jsonl(run_dir / HITS_JSONL_NAME, new_rows)
                execution_state["page_count"] += 1
                active["page_index"] = int(active.get("page_index", 0)) + 1
                active["next_token"] = next_token or ""
                _recompute_execution_counts(execution_state, hit_index, execution.execution_id)

                if next_token is None:
                    retrieved = len(hit_index[part_key])
                    expected = int(active["expected_count"])
                    if retrieved != expected:
                        final_expected = int(
                            provider.count(execution, active["start_date"], active["end_date"])
                        )
                        execution_state["count_request_count"] += 1
                        active.setdefault("initial_expected_count", expected)
                        active["final_expected_count"] = final_expected
                        active["expected_count"] = final_expected
                        active["count_drift"] = final_expected - int(active["initial_expected_count"])
                        if retrieved < final_expected:
                            attempts = int(active.get("reconciliation_attempts", 0))
                            max_attempts = _reconciliation_retries(
                                execution.provider, provider_config
                            )
                            if attempts < max_attempts:
                                active["reconciliation_attempts"] = attempts + 1
                                active["next_token"] = ""
                                state["updated_at_utc"] = utc_now()
                                atomic_write_json(run_dir / RUN_STATE_NAME, state)
                                continue
                            accepted, shortfall, allowed = _accepted_count_drift(
                                provider=execution.provider,
                                provider_config=provider_config,
                                expected=final_expected,
                                retrieved=retrieved,
                            )
                            if accepted:
                                active["reconciliation_status"] = "accepted_provider_count_drift"
                                active["reconciliation_shortfall"] = shortfall
                                active["reconciliation_tolerance_records"] = allowed
                            else:
                                raise RuntimeError(
                                    "count_reconciliation_failed: "
                                    f"initial_expected {active['initial_expected_count']}, "
                                    f"final_expected {final_expected}, retrieved {retrieved}, "
                                    f"shortfall {shortfall}, tolerance {allowed}, retries {attempts} for "
                                    f"{active['start_date']}..{active['end_date']}"
                                )
                    execution_state["completed_partitions"].append(
                        {**active, "retrieved_count": retrieved, "completed_at_utc": utc_now()}
                    )
                    execution_state["active_partition"] = None
                    _recompute_execution_counts(execution_state, hit_index, execution.execution_id)
                state["updated_at_utc"] = utc_now()
                atomic_write_json(run_dir / RUN_STATE_NAME, state)

            execution_state["status"] = "complete"
            execution_state["completed_at_utc"] = utc_now()
            execution_state["error"] = ""
            _recompute_execution_counts(execution_state, hit_index, execution.execution_id)
            state["updated_at_utc"] = utc_now()
            atomic_write_json(run_dir / RUN_STATE_NAME, state)
        except RequestBudgetExhausted:
            execution_state["status"] = "running"
            paused_providers.add(execution.provider)
            state["updated_at_utc"] = utc_now()
            atomic_write_json(run_dir / RUN_STATE_NAME, state)
        except Exception as error:
            execution_state["status"] = "failed"
            execution_state["error"] = f"{type(error).__name__}: {error}"
            manifest.setdefault("provider_errors", []).append(
                {
                    "execution_id": execution.execution_id,
                    "search_id": execution.search_id,
                    "provider": execution.provider,
                    "error": execution_state["error"],
                    "occurred_at_utc": utc_now(),
                }
            )
            state["updated_at_utc"] = utc_now()
            atomic_write_json(run_dir / RUN_STATE_NAME, state)
            if not continue_on_error:
                stopped_on_error = True
                break

    provider_session_stats: dict[str, dict] = {}
    for name, adapter in providers.items():
        if not hasattr(adapter, "client"):
            continue
        provider_stats = adapter.client.stats.to_dict()
        budget_context = getattr(adapter.client, "budget_context", {})
        if budget_context:
            provider_stats["budget_context"] = dict(budget_context)
        provider_session_stats[name] = provider_stats

    session = {
        "started_or_resumed_at_utc": manifest.get("updated_at_utc", manifest.get("generated_at_utc", "")),
        "ended_at_utc": utc_now(),
        "request_budgets": dict(
            session_request_budgets or manifest.get("request_budgets_per_session", {})
        ),
        "providers": provider_session_stats,
    }
    manifest.setdefault("provider_sessions", []).append(session)
    manifest["status"] = "materializing"
    manifest["updated_at_utc"] = utc_now()
    atomic_write_json(run_dir / RUN_MANIFEST_NAME, manifest)
    manifest = materialize_artifacts(run_dir, plan, state, manifest)
    manifest.pop("paused_providers", None)
    if manifest["completion_gate_passed"]:
        manifest["status"] = "complete"
    elif manifest.get("retrieval_completion_gate_passed") and not manifest.get("calibration_gate_passed"):
        manifest["status"] = "calibration_failed"
    elif any(item.get("status") == "failed" for item in state["executions"].values()) or stopped_on_error:
        manifest["status"] = "failed"
    elif paused_providers:
        manifest["status"] = "paused_budget"
        manifest["paused_providers"] = sorted(paused_providers)
    else:
        manifest["status"] = "incomplete"
    manifest["updated_at_utc"] = utc_now()
    atomic_write_json(run_dir / RUN_MANIFEST_NAME, manifest)
    return manifest
