#!/usr/bin/env python3
"""Reconcile canonical metadata after the source-identity repair refresh.

The tool is intentionally narrow:

- only metadata rows produced by the requested repair run may overwrite shared
  fields in ``candidate_papers.parquet``;
- DOI-verified PMID/PMCID mappings from the artifact resolution CSV are applied
  to both canonical tables;
- URLs containing a superseded or invalid PMCID are removed without changing
  unrelated URL candidates; and
- dry-run is the default. ``--apply`` stages both tables, creates backups, and
  then atomically replaces the canonical files.

It does not rebuild the corpus or touch extraction, full-text, or KG artifacts.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_ID = "source_identity_repair_20260710"
DEFAULT_METADATA_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_RESOLUTION_CSV = ROOT / "outputs" / DEFAULT_RUN_ID / "artifact_pmcid_resolution.csv"
DEFAULT_REPORT = ROOT / "outputs" / DEFAULT_RUN_ID / "canonical_metadata_reconciliation_report.json"
DEFAULT_BACKUP_ROOT = ROOT / "outputs" / DEFAULT_RUN_ID / "backups"

# Explicitly limit the refresh merge to metadata columns already present in the
# candidate table. Identifier and PMC URL corrections are applied separately
# from the resolution CSV below.
REFRESHED_METADATA_FIELDS = (
    "study_title",
    "study_year",
    "authors",
    "abstract",
    "study_journal",
    "publication_type",
    "trial_registry_ids",
    "publication_date",
    "publisher",
    "mesh_terms",
    "keywords",
    "language",
    "pmid",
    "pmcid",
    "openalex_id",
    "semantic_scholar_id",
    "metadata_provider",
    "metadata_provider_chain",
    "metadata_providers_queried",
    "metadata_lookup_error",
    "metadata_missing_reason",
    "metadata_enrichment_status",
    "metadata_enrichment_run_id",
    "metadata_enriched_at_utc",
    "open_access_is_oa",
    "open_access_status",
    "open_access_url",
    "best_pdf_url",
    "pdf_url_candidates",
)
PMC_URL_FIELDS = ("open_access_url", "best_pdf_url", "pdf_url_candidates")
INVALID_WITHOUT_VERIFIED_PMCID = {"stored_pmcid_not_verified_for_doi"}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def normalize_doi(value: Any) -> str:
    text = clean(value).lower()
    text = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", text)
    return text.strip()


def normalize_pmcid(value: Any) -> str:
    text = clean(value).upper()
    match = re.search(r"\bPMC\s*([0-9]+)\b", text)
    if match:
        return f"PMC{match.group(1)}"
    if text.isdigit():
        return f"PMC{text}"
    return ""


def dataframe_index_by_doi(frame: pd.DataFrame, *, label: str) -> dict[str, Any]:
    if "doi" not in frame.columns:
        raise ValueError(f"{label} is missing required column: doi")
    out: dict[str, Any] = {}
    duplicates: list[str] = []
    for index, value in frame["doi"].items():
        doi = normalize_doi(value)
        if not doi:
            continue
        if doi in out:
            duplicates.append(doi)
        else:
            out[doi] = index
    if duplicates:
        sample = ", ".join(sorted(set(duplicates))[:5])
        raise ValueError(f"{label} has duplicate DOI rows: {sample}")
    return out


def load_resolution_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Resolution CSV not found: {path}")
    frame = pd.read_csv(path, dtype=str).fillna("")
    required = {
        "doi",
        "mapping_status",
        "current_pmid",
        "verified_pmid",
        "current_pmcid",
        "verified_pmcid",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Resolution CSV is missing columns: {', '.join(missing)}")
    rows: dict[str, dict[str, str]] = {}
    for raw in frame.to_dict("records"):
        doi = normalize_doi(raw.get("doi", ""))
        if not doi:
            continue
        if doi in rows:
            raise ValueError(f"Resolution CSV has duplicate DOI row: {doi}")
        rows[doi] = {str(key): clean(value) for key, value in raw.items()}
    return rows


def remove_bad_pmc_urls(value: Any, bad_pmcids: set[str]) -> tuple[str, int]:
    text = clean(value)
    if not text or not bad_pmcids:
        return text, 0
    parts = [part.strip() for part in re.split(r"\s*\|\s*", text) if part.strip()]
    kept: list[str] = []
    removed = 0
    for part in parts:
        folded = part.casefold()
        if any(pmcid.casefold() in folded for pmcid in bad_pmcids):
            removed += 1
        elif part not in kept:
            kept.append(part)
    return " | ".join(kept), removed


def merge_repair_refresh_into_candidates(
    candidate_frame: pd.DataFrame,
    metadata_frame: pd.DataFrame,
    *,
    run_id: str,
) -> tuple[pd.DataFrame, dict]:
    candidates = candidate_frame.copy(deep=True)
    candidate_index = dataframe_index_by_doi(candidates, label="candidate table")
    dataframe_index_by_doi(metadata_frame, label="metadata table")
    if "metadata_enrichment_run_id" not in metadata_frame.columns:
        raise ValueError("Metadata table is missing metadata_enrichment_run_id")

    fields = [
        field
        for field in REFRESHED_METADATA_FIELDS
        if field in candidates.columns and field in metadata_frame.columns
    ]
    refreshed = metadata_frame[
        metadata_frame["metadata_enrichment_run_id"].map(clean) == clean(run_id)
    ]
    field_changes: Counter[str] = Counter()
    changed_dois: list[str] = []
    missing_candidate_dois: list[str] = []

    for row in refreshed.to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        index = candidate_index.get(doi)
        if index is None:
            missing_candidate_dois.append(doi)
            continue
        row_changed = False
        for field in fields:
            before = clean(candidates.at[index, field])
            after = clean(row.get(field, ""))
            if before == after:
                continue
            candidates.at[index, field] = after
            field_changes[field] += 1
            row_changed = True
        if row_changed:
            changed_dois.append(doi)

    return candidates, {
        "run_id": clean(run_id),
        "refreshed_metadata_rows": int(len(refreshed)),
        "eligible_field_count": len(fields),
        "matched_candidate_rows": int(len(refreshed) - len(missing_candidate_dois)),
        "candidate_rows_changed": len(changed_dois),
        "changed_dois": changed_dois,
        "missing_candidate_dois": missing_candidate_dois,
        "field_change_counts": dict(sorted(field_changes.items())),
    }


def apply_identifier_resolution(
    frame: pd.DataFrame,
    resolution_rows: dict[str, dict[str, str]],
    *,
    label: str,
) -> tuple[pd.DataFrame, dict]:
    out = frame.copy(deep=True)
    index_by_doi = dataframe_index_by_doi(out, label=label)
    for required in ("pmid", "pmcid"):
        if required not in out.columns:
            raise ValueError(f"{label} is missing required column: {required}")

    counts: Counter[str] = Counter()
    url_removals: Counter[str] = Counter()
    changed_dois: list[str] = []
    missing_dois: list[str] = []
    skipped_conflicts: list[dict[str, str]] = []

    for doi, resolution in resolution_rows.items():
        index = index_by_doi.get(doi)
        if index is None:
            missing_dois.append(doi)
            continue
        before_pmid = clean(out.at[index, "pmid"])
        before_pmcid = normalize_pmcid(out.at[index, "pmcid"])
        verified_pmid = clean(resolution.get("verified_pmid", ""))
        verified_pmcid = normalize_pmcid(resolution.get("verified_pmcid", ""))
        prior_pmcid = normalize_pmcid(resolution.get("current_pmcid", ""))
        status = clean(resolution.get("mapping_status", ""))
        row_changed = False

        if verified_pmid and before_pmid != verified_pmid:
            out.at[index, "pmid"] = verified_pmid
            counts["pmid_set_from_verified"] += 1
            row_changed = True

        bad_pmcids: set[str] = set()
        if verified_pmcid:
            if before_pmcid and before_pmcid != verified_pmcid:
                bad_pmcids.add(before_pmcid)
            if prior_pmcid and prior_pmcid != verified_pmcid:
                bad_pmcids.add(prior_pmcid)
            if before_pmcid != verified_pmcid:
                out.at[index, "pmcid"] = verified_pmcid
                counts["pmcid_set_from_verified"] += 1
                row_changed = True
        elif status in INVALID_WITHOUT_VERIFIED_PMCID and prior_pmcid:
            bad_pmcids.add(prior_pmcid)
            if before_pmcid == prior_pmcid:
                out.at[index, "pmcid"] = ""
                counts["pmcid_cleared_unverified"] += 1
                row_changed = True
            elif before_pmcid and before_pmcid != prior_pmcid:
                skipped_conflicts.append(
                    {
                        "doi": doi,
                        "mapping_status": status,
                        "resolution_current_pmcid": prior_pmcid,
                        "table_pmcid": before_pmcid,
                    }
                )

        for field in PMC_URL_FIELDS:
            if field not in out.columns:
                continue
            before = clean(out.at[index, field])
            after, removed = remove_bad_pmc_urls(before, bad_pmcids)
            if removed:
                out.at[index, field] = after
                url_removals[field] += removed
                counts["url_fields_changed"] += 1
                row_changed = True

        if row_changed:
            changed_dois.append(doi)
        counts[f"mapping_status:{status or 'missing'}"] += 1

    return out, {
        "table": label,
        "resolution_rows": len(resolution_rows),
        "matched_rows": len(resolution_rows) - len(missing_dois),
        "rows_changed": len(changed_dois),
        "changed_dois": changed_dois,
        "missing_dois": missing_dois,
        "skipped_identifier_conflicts": skipped_conflicts,
        "counts": dict(sorted(counts.items())),
        "url_candidate_removals": dict(sorted(url_removals.items())),
    }


def build_reconciled_tables(
    metadata_frame: pd.DataFrame,
    candidate_frame: pd.DataFrame,
    resolution_rows: dict[str, dict[str, str]],
    *,
    run_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    metadata_out, metadata_resolution = apply_identifier_resolution(
        metadata_frame,
        resolution_rows,
        label="metadata table",
    )
    candidate_merged, refresh_merge = merge_repair_refresh_into_candidates(
        candidate_frame,
        metadata_out,
        run_id=run_id,
    )
    candidate_out, candidate_resolution = apply_identifier_resolution(
        candidate_merged,
        resolution_rows,
        label="candidate table",
    )
    return metadata_out, candidate_out, {
        "refresh_merge": refresh_merge,
        "metadata_resolution": metadata_resolution,
        "candidate_resolution": candidate_resolution,
    }


def unique_backup_dir(root: Path, run_id: str) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = root / f"canonical_metadata_reconciliation_{run_id}_{stamp}"
    suffix = 1
    while candidate.exists():
        candidate = root / f"canonical_metadata_reconciliation_{run_id}_{stamp}_{suffix}"
        suffix += 1
    return candidate


def stage_parquet(frame: pd.DataFrame, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp.parquet",
        dir=destination.parent,
    )
    os.close(descriptor)
    staged = Path(raw_path)
    try:
        frame.to_parquet(staged, engine="pyarrow", index=False)
        if destination.exists():
            shutil.copymode(destination, staged)
        check = pd.read_parquet(staged)
        if len(check) != len(frame) or list(check.columns) != list(frame.columns):
            raise RuntimeError(f"Staged Parquet verification failed for {destination}")
        return staged
    except Exception:
        staged.unlink(missing_ok=True)
        raise


def replace_tables_with_backups(
    *,
    metadata_frame: pd.DataFrame,
    candidate_frame: pd.DataFrame,
    metadata_path: Path,
    candidate_path: Path,
    backup_root: Path,
    run_id: str,
) -> dict[str, str]:
    if not metadata_path.exists() or not candidate_path.exists():
        raise FileNotFoundError("Both canonical tables must exist before apply")
    staged_metadata = stage_parquet(metadata_frame, metadata_path)
    staged_candidate = stage_parquet(candidate_frame, candidate_path)
    backup_dir = unique_backup_dir(backup_root, run_id)
    backup_dir.mkdir(parents=True, exist_ok=False)
    metadata_backup = backup_dir / metadata_path.name
    candidate_backup = backup_dir / candidate_path.name
    shutil.copy2(metadata_path, metadata_backup)
    shutil.copy2(candidate_path, candidate_backup)

    metadata_replaced = False
    candidate_replaced = False
    try:
        os.replace(staged_metadata, metadata_path)
        metadata_replaced = True
        os.replace(staged_candidate, candidate_path)
        candidate_replaced = True
    except Exception:
        if metadata_replaced:
            shutil.copy2(metadata_backup, metadata_path)
        if candidate_replaced:
            shutil.copy2(candidate_backup, candidate_path)
        raise
    finally:
        staged_metadata.unlink(missing_ok=True)
        staged_candidate.unlink(missing_ok=True)

    return {
        "backup_dir": str(backup_dir),
        "metadata_backup": str(metadata_backup),
        "candidate_backup": str(candidate_backup),
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_reconciliation(
    *,
    metadata_path: Path,
    candidate_path: Path,
    resolution_path: Path,
    report_path: Path,
    backup_root: Path,
    run_id: str = DEFAULT_RUN_ID,
    apply: bool = False,
) -> dict:
    metadata_path = metadata_path.resolve()
    candidate_path = candidate_path.resolve()
    resolution_path = resolution_path.resolve()
    report_path = report_path.resolve()
    backup_root = backup_root.resolve()

    metadata = pd.read_parquet(metadata_path)
    candidates = pd.read_parquet(candidate_path)
    metadata_columns = list(metadata.columns)
    candidate_columns = list(candidates.columns)
    resolution_rows = load_resolution_rows(resolution_path)
    metadata_out, candidate_out, details = build_reconciled_tables(
        metadata,
        candidates,
        resolution_rows,
        run_id=run_id,
    )
    if len(metadata_out) != len(metadata) or list(metadata_out.columns) != metadata_columns:
        raise RuntimeError("Metadata row count or schema changed during reconciliation")
    if len(candidate_out) != len(candidates) or list(candidate_out.columns) != candidate_columns:
        raise RuntimeError("Candidate row count or schema changed during reconciliation")
    if apply and not details["refresh_merge"]["refreshed_metadata_rows"]:
        raise RuntimeError(f"No metadata rows found for repair run {run_id}; refusing apply")

    report = {
        "schema_version": "source_identity_metadata_reconciliation_v1",
        "generated_at_utc": now_utc(),
        "apply": bool(apply),
        "run_id": clean(run_id),
        "inputs": {
            "metadata_table": str(metadata_path),
            "candidate_table": str(candidate_path),
            "resolution_csv": str(resolution_path),
        },
        "table_shapes": {
            "metadata_rows": len(metadata),
            "metadata_columns": len(metadata_columns),
            "candidate_rows": len(candidates),
            "candidate_columns": len(candidate_columns),
        },
        "details": details,
        "backups": {},
        "status": "dry_run_complete",
    }
    if apply:
        report["backups"] = replace_tables_with_backups(
            metadata_frame=metadata_out,
            candidate_frame=candidate_out,
            metadata_path=metadata_path,
            candidate_path=candidate_path,
            backup_root=backup_root,
            run_id=run_id,
        )
        report["status"] = "applied"
    write_json(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--resolution-csv", default=str(DEFAULT_RESOLUTION_CSV))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--backup-root", default=str(DEFAULT_BACKUP_ROOT))
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--apply", action="store_true", help="Back up and replace both canonical tables")
    args = parser.parse_args()

    report = run_reconciliation(
        metadata_path=Path(args.metadata_table),
        candidate_path=Path(args.candidate_table),
        resolution_path=Path(args.resolution_csv),
        report_path=Path(args.report),
        backup_root=Path(args.backup_root),
        run_id=args.run_id,
        apply=bool(args.apply),
    )
    summary = {
        "status": report["status"],
        "run_id": report["run_id"],
        "refreshed_rows": report["details"]["refresh_merge"]["refreshed_metadata_rows"],
        "candidate_rows_merged": report["details"]["refresh_merge"]["candidate_rows_changed"],
        "candidate_resolution_rows_changed": report["details"]["candidate_resolution"]["rows_changed"],
        "metadata_rows_changed": report["details"]["metadata_resolution"]["rows_changed"],
        "report": str(Path(args.report).resolve()),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
