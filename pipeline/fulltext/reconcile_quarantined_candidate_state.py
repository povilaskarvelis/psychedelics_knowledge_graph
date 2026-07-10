#!/usr/bin/env python3
"""Clear stale full-text availability for DOIs with no active canonical artifact."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import shutil
import tempfile
import os

import pandas as pd

from pipeline.fulltext.source_identity import normalize_doi


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUARANTINE_REPORT = ROOT / "outputs" / "source_identity_repair_20260710" / "artifact_quarantine_applied.json"
DEFAULT_ARTIFACT_DIR = ROOT / "data" / "processed" / "fulltext" / "articles"
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_QUARANTINE_DIR = ROOT / "data" / "processed" / "fulltext" / "source_identity_quarantine_20260710"
DEFAULT_REPORT = (
    ROOT
    / "outputs"
    / "source_identity_repair_20260710"
    / "quarantined_candidate_state_reconciliation.json"
)

CLEARED_CANDIDATE_VALUES = {
    "pdf_local_path": "",
    "local_pdf_paths": "",
    "local_pdf_count": 0,
    "pdf_sha256": "",
    "pdf_download_status": "source_identity_quarantined",
    "flag_has_local_pdf": False,
    "best_extraction_access_tier": "",
    "has_converted_full_text": False,
    "fulltext_artifact_paths": "",
    "fulltext_char_count": 0,
}


def clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def active_artifact_dois(path: Path) -> set[str]:
    out: set[str] = set()
    for artifact_path in path.glob("*.json"):
        try:
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        doi = normalize_doi(artifact.get("study_doi", "")) if isinstance(artifact, dict) else ""
        if doi:
            out.add(doi)
    return out


def reconciliation_target_dois(payload: dict, artifact_dir: Path) -> tuple[set[str], set[str]]:
    reported = {
        normalize_doi(row.get("doi", ""))
        for row in payload.get("records", [])
        if isinstance(row, dict) and normalize_doi(row.get("doi", ""))
    }
    restored_active = reported & active_artifact_dois(artifact_dir)
    return reported - restored_active, restored_active


def reconcile_candidate_rows(frame: pd.DataFrame, target_dois: set[str]) -> tuple[pd.DataFrame, dict]:
    if "doi" not in frame.columns:
        raise ValueError("candidate table is missing DOI column")
    out = frame.copy(deep=True)
    normalized = out["doi"].map(normalize_doi)
    matched_dois = set(normalized[normalized.isin(target_dois)])
    changes: list[dict] = []
    for index in out.index[normalized.isin(target_dois)]:
        row_changes: dict[str, dict] = {}
        for field, value in CLEARED_CANDIDATE_VALUES.items():
            if field not in out.columns:
                continue
            before = out.at[index, field]
            if clean(before) == clean(value):
                continue
            out.at[index, field] = value
            row_changes[field] = {"before": clean(before), "after": value}
        if row_changes:
            changes.append({"row_index": int(index), "doi": clean(out.at[index, "doi"]), "changes": row_changes})
    return out, {
        "rows_changed": len(changes),
        "matched_target_dois": sorted(matched_dois),
        "missing_target_dois": sorted(target_dois - matched_dois),
        "changes": changes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quarantine-report", default=str(DEFAULT_QUARANTINE_REPORT))
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--quarantine-dir", default=str(DEFAULT_QUARANTINE_DIR))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    payload = json.loads(Path(args.quarantine_report).resolve().read_text(encoding="utf-8"))
    target_dois, restored_active_dois = reconciliation_target_dois(
        payload,
        Path(args.artifact_dir).resolve(),
    )
    candidate_path = Path(args.candidate_table).resolve()
    frame = pd.read_parquet(candidate_path)
    out, candidate_report = reconcile_candidate_rows(frame, target_dois)

    backup = ""
    if args.apply:
        descriptor, raw = tempfile.mkstemp(
            prefix=f".{candidate_path.name}.",
            suffix=".tmp.parquet",
            dir=candidate_path.parent,
        )
        os.close(descriptor)
        staged = Path(raw)
        try:
            out.to_parquet(staged, engine="pyarrow", index=False)
            check = pd.read_parquet(staged)
            if len(check) != len(frame) or list(check.columns) != list(frame.columns):
                raise RuntimeError("candidate table staging validation failed")
        except Exception:
            staged.unlink(missing_ok=True)
            raise
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = (
            Path(args.quarantine_dir).resolve()
            / "table_backups"
            / f"candidate_papers.pre_state_reconcile_{stamp}.parquet"
        )
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate_path, backup_path)
        os.replace(staged, candidate_path)
        backup = str(backup_path)

    report = {
        "apply": bool(args.apply),
        "target_dois": len(target_dois),
        "restored_active_dois": sorted(restored_active_dois),
        "restored_active_doi_count": len(restored_active_dois),
        "rows_changed": candidate_report["rows_changed"],
        "matched_target_dois": candidate_report["matched_target_dois"],
        "missing_target_dois": candidate_report["missing_target_dois"],
        "backup": backup,
        "changes": candidate_report["changes"],
    }
    report_path = Path(args.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
            default=lambda value: value.item() if hasattr(value, "item") else str(value),
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                key: report[key]
                for key in ("apply", "target_dois", "restored_active_doi_count", "rows_changed", "backup")
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
