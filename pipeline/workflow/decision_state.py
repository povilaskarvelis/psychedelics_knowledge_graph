"""Reconcile include/exclude transitions with downstream active state.

Decision artifacts and raw run outputs are historical provenance and are never
deleted here.  This module only updates the canonical candidate ledger and
filters explicitly declared *active derived views*.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import json
import os
from pathlib import Path
import tempfile
from typing import Iterable, Mapping

import pandas as pd

from pipeline.ingest.candidate_status import normalize_doi


STAGE_ORDER = (
    "prescreen",
    "model_screening",
    "post_retrieval",
    "extraction",
    "graph",
)

# Each field is owned by the earliest stage whose current decision/output it
# represents.  Invalidating a stage clears fields owned by later stages only.
CANDIDATE_STAGE_DEFAULTS: dict[str, dict[str, object]] = {
    "model_screening": {
        "literature_source_family": "",
        "literature_source_type": "",
        "literature_type_confidence": "",
        "primary_secondary_source_type": "",
        "secondary_source_types": "",
        "non_primary_flags": "",
        "retained_for_extraction_candidate": False,
        "extraction_domain_routes": "",
        "extraction_domain_screening_decisions": "",
        "extraction_domain_screening_reasons": "",
    },
    "extraction": {
        "extraction_route_status": "",
        "extraction_route_reason": "",
        "extraction_route_count": 0,
        "retained_extraction_route_count": 0,
        "extraction_route_actions": "",
        "extraction_prompt_profiles": "",
        "extraction_schema_profiles": "",
        "best_extraction_access_tier": "",
        "source_text_state": "",
        "source_text_state_reason": "",
        "extraction_routes_table_version": "",
        "extraction_routes_updated_at_utc": "",
    },
    "graph": {
        "graph_inclusion_status": "",
        "graph_inclusion_disposition": "",
        "graph_inclusion_reason": "",
        "graph_inclusion_next_action": "",
        "graph_inclusion_decision_source": "",
        "graph_inclusion_run_id": "",
        "graph_inclusion_release_id": "",
        "graph_inclusion_updated_at_utc": "",
    },
}


@dataclass(frozen=True)
class ActiveArtifact:
    """A mutable current view whose rows are keyed by DOI."""

    path: Path
    kind: str = "parquet"
    doi_fields: tuple[str, ...] = ("doi", "study_doi", "paper_doi")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalized_dois(values: Iterable[object]) -> set[str]:
    return {doi for value in values if (doi := normalize_doi(value))}


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "include", "retain"}


def downstream_candidate_defaults(stage: str) -> dict[str, object]:
    if stage not in STAGE_ORDER:
        raise ValueError(f"Unknown decision stage {stage!r}; expected one of {STAGE_ORDER}")
    stage_index = STAGE_ORDER.index(stage)
    defaults: dict[str, object] = {}
    for later_stage in STAGE_ORDER[stage_index + 1 :]:
        defaults.update(CANDIDATE_STAGE_DEFAULTS.get(later_stage, {}))
    return defaults


def included_dois_from_candidate(
    frame: pd.DataFrame,
    *,
    column: str,
) -> set[str]:
    if frame.empty or "doi" not in frame.columns or column not in frame.columns:
        return set()
    values = frame[column].map(truthy)
    return normalized_dois(frame.loc[values, "doi"])


def _different(left: pd.Series, right: pd.Series) -> pd.Series:
    equal = left.eq(right)
    if hasattr(equal, "fillna"):
        equal = equal.fillna(False)
    return ~(equal | (left.isna() & right.isna()))


def reconcile_candidate_frame(
    candidate_df: pd.DataFrame,
    *,
    decision_updates: pd.DataFrame,
    update_defaults: Mapping[str, object],
    stage: str,
    previous_included_dois: set[str],
    current_included_dois: set[str],
    pending_status: str = "",
    excluded_status: str = "",
) -> tuple[pd.DataFrame, dict]:
    """Apply current decisions and clear superseded downstream projections.

    Only records included at the same stage both previously and currently keep
    their downstream fields.  Every other record in the current decision scope
    has fields owned by later stages reset to their neutral defaults.
    """

    if "doi" not in candidate_df.columns:
        raise ValueError("Candidate table must contain a doi column")
    if "doi" not in decision_updates.columns:
        raise ValueError("Decision updates must contain a doi column")

    updates = decision_updates.copy()
    updates["_doi_key"] = updates["doi"].map(normalize_doi)
    updates = updates[updates["_doi_key"].astype(bool)].copy()
    duplicate_dois = sorted(
        updates.loc[updates["_doi_key"].duplicated(keep=False), "_doi_key"].unique()
    )
    if duplicate_dois:
        raise ValueError(f"Decision updates contain duplicate DOIs: {duplicate_dois[:20]}")

    out = candidate_df.copy()
    out["_doi_key"] = out["doi"].map(normalize_doi)
    decision_scope = set(updates["_doi_key"])
    missing = sorted(decision_scope - set(out["_doi_key"]))
    if missing:
        raise ValueError(f"Decision updates contain DOIs missing from candidate table: {missing[:20]}")

    changed_rows = pd.Series(False, index=out.index)
    updated_cells = 0
    updates = updates.set_index("_doi_key", drop=True)
    matched = out["_doi_key"].isin(decision_scope)
    update_columns = [column for column in updates.columns if column != "doi"]
    for column in update_columns:
        if column not in out.columns:
            out[column] = update_defaults.get(column, "")
        mapped = out["_doi_key"].map(updates[column])
        change = matched & mapped.notna() & _different(out[column], mapped)
        if change.any():
            out.loc[change, column] = mapped.loc[change].to_numpy()
            changed_rows |= change
            updated_cells += int(change.sum())

    stable_included = previous_included_dois.intersection(current_included_dois)
    reset_dois = decision_scope - stable_included
    reset_mask = out["_doi_key"].isin(reset_dois)
    reset_defaults = downstream_candidate_defaults(stage)
    for column, default in reset_defaults.items():
        if column not in out.columns:
            out[column] = default
        mapped = pd.Series(default, index=out.index)
        change = reset_mask & _different(out[column], mapped)
        if change.any():
            out.loc[change, column] = default
            changed_rows |= change
            updated_cells += int(change.sum())

    if pending_status or excluded_status:
        if "current_pipeline_status" not in out.columns:
            out["current_pipeline_status"] = ""
        newly_pending = reset_mask & out["_doi_key"].isin(current_included_dois)
        currently_excluded = reset_mask & ~out["_doi_key"].isin(current_included_dois)
        for mask, value in ((newly_pending, pending_status), (currently_excluded, excluded_status)):
            if not value:
                continue
            mapped = pd.Series(value, index=out.index)
            change = mask & _different(out["current_pipeline_status"], mapped)
            if change.any():
                out.loc[change, "current_pipeline_status"] = value
                changed_rows |= change
                updated_cells += int(change.sum())

    out = out.drop(columns=["_doi_key"])
    summary = {
        "candidate_rows": int(len(out)),
        "decision_rows": int(len(updates)),
        "previous_included_dois": len(previous_included_dois),
        "current_included_dois": len(current_included_dois),
        "stable_included_dois": len(stable_included),
        "newly_included_dois": len(current_included_dois - previous_included_dois),
        "newly_excluded_dois": len(previous_included_dois - current_included_dois),
        "downstream_reset_dois": len(reset_dois),
        "updated_candidate_rows": int(changed_rows.sum()),
        "updated_cells": updated_cells,
        "reset_columns": sorted(reset_defaults),
        "stable_included_examples": sorted(stable_included)[:20],
        "newly_included_examples": sorted(current_included_dois - previous_included_dois)[:20],
        "newly_excluded_examples": sorted(previous_included_dois - current_included_dois)[:20],
    }
    return out, summary


def write_parquet_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        frame.to_parquet(temporary_path, engine="pyarrow", index=False)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def write_json_atomic(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        temporary_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def filter_active_parquet(path: Path, *, allowed_dois: set[str]) -> dict:
    if not path.is_file():
        return {"path": str(path), "kind": "parquet", "status": "missing", "rows_removed": 0}
    frame = pd.read_parquet(path)
    if "doi" not in frame.columns:
        raise ValueError(f"Active Parquet view has no doi column: {path}")
    keep = frame["doi"].map(normalize_doi).isin(allowed_dois)
    rows_before = len(frame)
    filtered = frame[keep].copy()
    removed = rows_before - len(filtered)
    if removed:
        write_parquet_atomic(filtered, path)
    return {
        "path": str(path),
        "kind": "parquet",
        "status": "updated" if removed else "unchanged",
        "rows_before": rows_before,
        "rows_after": len(filtered),
        "rows_removed": removed,
        "dois_removed": len(normalized_dois(frame.loc[~keep, "doi"])),
    }


def _jsonl_row_doi(row: dict, fields: tuple[str, ...]) -> str:
    for field in fields:
        doi = normalize_doi(row.get(field, ""))
        if doi:
            return doi
    return ""


def filter_active_jsonl(
    path: Path,
    *,
    allowed_dois: set[str],
    doi_fields: tuple[str, ...],
) -> dict:
    if not path.is_file():
        return {"path": str(path), "kind": "jsonl", "status": "missing", "rows_removed": 0}
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    rows_before = 0
    rows_after = 0
    removed_dois: set[str] = set()
    blank_doi_rows = 0
    try:
        with path.open("r", encoding="utf-8") as source, temporary_path.open(
            "w", encoding="utf-8"
        ) as target:
            for line_number, line in enumerate(source, start=1):
                if not line.strip():
                    continue
                rows_before += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
                doi = _jsonl_row_doi(row, doi_fields) if isinstance(row, dict) else ""
                if not doi:
                    blank_doi_rows += 1
                    target.write(line if line.endswith("\n") else line + "\n")
                    rows_after += 1
                elif doi in allowed_dois:
                    target.write(line if line.endswith("\n") else line + "\n")
                    rows_after += 1
                else:
                    removed_dois.add(doi)
        removed = rows_before - rows_after
        if removed:
            os.replace(temporary_path, path)
        return {
            "path": str(path),
            "kind": "jsonl",
            "status": "updated" if removed else "unchanged",
            "rows_before": rows_before,
            "rows_after": rows_after,
            "rows_removed": removed,
            "dois_removed": len(removed_dois),
            "blank_doi_rows_preserved": blank_doi_rows,
        }
    finally:
        temporary_path.unlink(missing_ok=True)


def reconcile_workflow_decision(
    *,
    candidate_table: Path,
    decision_updates: pd.DataFrame,
    update_defaults: Mapping[str, object],
    stage: str,
    previous_included_dois: set[str],
    current_included_dois: set[str],
    active_artifacts: Iterable[ActiveArtifact] = (),
    active_artifact_allowed_dois: set[str] | None = None,
    pending_status: str = "",
    excluded_status: str = "",
    report_path: Path | None = None,
    context: Mapping[str, object] | None = None,
) -> dict:
    """Reconcile one stage decision and invalidate explicitly active views."""

    candidate_table = Path(candidate_table).resolve()
    if not candidate_table.is_file():
        raise FileNotFoundError(f"Candidate table not found: {candidate_table}")
    candidate_df = pd.read_parquet(candidate_table)
    reconciled, candidate_summary = reconcile_candidate_frame(
        candidate_df,
        decision_updates=decision_updates,
        update_defaults=update_defaults,
        stage=stage,
        previous_included_dois=normalized_dois(previous_included_dois),
        current_included_dois=normalized_dois(current_included_dois),
        pending_status=pending_status,
        excluded_status=excluded_status,
    )
    write_parquet_atomic(reconciled, candidate_table)

    stable_included = normalized_dois(previous_included_dois).intersection(
        normalized_dois(current_included_dois)
    )
    # Full-stage reconciliations historically filtered active artifacts to
    # stable includes.  A later scoped decision stage (for example a
    # post-retrieval eligibility assessment) sees only a small DOI subset, so
    # using that subset as the global allow-list would incorrectly delete
    # unrelated routes/tasks.  Callers for scoped stages provide the complete
    # downstream-eligible DOI set explicitly.
    artifact_allowed = (
        normalized_dois(active_artifact_allowed_dois)
        if active_artifact_allowed_dois is not None
        else stable_included
    )
    artifact_summaries: list[dict] = []
    for artifact in active_artifacts:
        path = Path(artifact.path).resolve()
        if artifact.kind == "parquet":
            artifact_summaries.append(filter_active_parquet(path, allowed_dois=artifact_allowed))
        elif artifact.kind == "jsonl":
            artifact_summaries.append(
                filter_active_jsonl(
                    path,
                    allowed_dois=artifact_allowed,
                    doi_fields=artifact.doi_fields,
                )
            )
        else:
            raise ValueError(f"Unsupported active artifact kind {artifact.kind!r}: {path}")

    report = {
        "schema_version": "workflow_decision_reconciliation_v1",
        "generated_at_utc": now_utc(),
        "decision_stage": stage,
        "policy": "preserve_stable_includes_reset_all_other_downstream_state",
        "candidate_table": str(candidate_table),
        "candidate": candidate_summary,
        "active_artifacts": artifact_summaries,
        "active_artifact_allowed_dois": len(artifact_allowed),
        "historical_artifact_policy": "preserved; only declared active views are filtered",
        "context": dict(context or {}),
    }
    if report_path is not None:
        write_json_atomic(report, Path(report_path).resolve())
        report["report_path"] = str(Path(report_path).resolve())
    return report
