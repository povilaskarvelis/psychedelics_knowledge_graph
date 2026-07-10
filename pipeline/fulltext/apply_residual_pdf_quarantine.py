#!/usr/bin/env python3
"""Apply a verified residual-PDF quarantine manifest with candidate rollback."""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "outputs" / "source_identity_repair_20260710" / "source_layer_leftover_quarantine_manifest_final_plan.json"
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_ARTIFACT_DIR = ROOT / "data" / "processed" / "fulltext" / "articles"
DEFAULT_QUARANTINE_DIR = ROOT / "data" / "processed" / "fulltext" / "source_identity_quarantine_20260710"
DEFAULT_REPORT = ROOT / "outputs" / "source_identity_repair_20260710" / "residual_pdf_quarantine_applied.json"


def clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def split_paths(value: object) -> list[str]:
    return [part.strip() for part in clean(value).replace(" | ", "|").split("|") if part.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("records", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        raise ValueError("Manifest records must be a list")
    return [row for row in rows if isinstance(row, dict)]


def active_artifact_pdf_paths(artifact_dir: Path) -> set[str]:
    out: set[str] = set()
    for path in artifact_dir.glob("*.json"):
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        raw = clean(artifact.get("pdf_local_path", "")) if isinstance(artifact, dict) else ""
        if raw:
            out.add(str(Path(raw).expanduser().resolve()))
    return out


def candidate_path_reference_map(frame: pd.DataFrame) -> dict[str, list[int]]:
    references: dict[str, list[int]] = {}
    for index, row in frame.fillna("").iterrows():
        for field in ("pdf_local_path", "local_pdf_paths"):
            for raw in split_paths(row.get(field, "")):
                resolved = str(Path(raw).expanduser().resolve())
                values = references.setdefault(resolved, [])
                if int(index) not in values:
                    values.append(int(index))
    return references


def clear_candidate_reference(frame: pd.DataFrame, index: int, source: Path) -> dict:
    changes: dict[str, dict] = {}
    resolved = str(source.resolve())

    def set_value(field: str, value: object) -> None:
        if field not in frame.columns:
            return
        before = frame.at[index, field]
        if clean(before) == clean(value):
            return
        changes[field] = {"before": clean(before), "after": value}
        frame.at[index, field] = value

    if "pdf_local_path" in frame.columns:
        raw = clean(frame.at[index, "pdf_local_path"])
        if raw and str(Path(raw).expanduser().resolve()) == resolved:
            set_value("pdf_local_path", "")
    if "local_pdf_paths" in frame.columns:
        # The record has no verified canonical full text. Retaining a second,
        # unaudited local candidate would let the next run silently reuse it.
        set_value("local_pdf_paths", "")
    for field, value in (
        ("local_pdf_count", 0),
        ("pdf_sha256", ""),
        ("pdf_download_status", "source_identity_quarantined"),
        ("flag_has_local_pdf", False),
        ("best_extraction_access_tier", ""),
        ("has_converted_full_text", False),
        ("fulltext_artifact_paths", ""),
        ("fulltext_char_count", 0),
    ):
        set_value(field, value)
    return changes


def stage_parquet(frame: pd.DataFrame, destination: Path) -> Path:
    descriptor, raw = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp.parquet", dir=destination.parent)
    os.close(descriptor)
    path = Path(raw)
    try:
        frame.to_parquet(path, engine="pyarrow", index=False)
        check = pd.read_parquet(path)
        if len(check) != len(frame) or list(check.columns) != list(frame.columns):
            raise RuntimeError("staged candidate table failed schema/row validation")
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--quarantine-dir", default=str(DEFAULT_QUARANTINE_DIR))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    candidate_path = Path(args.candidate_table).resolve()
    artifact_dir = Path(args.artifact_dir).resolve()
    quarantine_dir = Path(args.quarantine_dir).resolve()
    rows = load_manifest(manifest_path)
    candidates = pd.read_parquet(candidate_path)
    candidate_out = candidates.copy(deep=True)
    candidate_refs = candidate_path_reference_map(candidate_out)
    active_refs = active_artifact_pdf_paths(artifact_dir)
    records: list[dict] = []
    counts: Counter[str] = Counter()

    for row in rows:
        source = Path(clean(row.get("source_path", ""))).resolve()
        target = Path(clean(row.get("target_path", ""))).resolve()
        expected = clean(row.get("source_sha256", "")).lower()
        status = "validated"
        error = ""
        indices = candidate_refs.get(str(source.resolve()), [])
        declared = {int(value) for value in row.get("candidate_row_indices_to_reconcile", [])}
        if not source.exists():
            status, error = "invalid", "source_missing"
        elif not expected or sha256(source).lower() != expected:
            status, error = "invalid", "source_hash_mismatch"
        elif str(source) in active_refs:
            status, error = "invalid", "active_artifact_still_references_pdf"
        elif target.exists():
            status, error = "invalid", "quarantine_target_exists"
        elif set(indices) - declared:
            status, error = "invalid", "unexpected_candidate_reference"

        changes: dict[str, dict] = {}
        if status == "validated":
            for index in indices:
                row_changes = clear_candidate_reference(candidate_out, index, source)
                if row_changes:
                    changes[str(index)] = row_changes
            status = "planned" if not args.apply else "ready_to_move"
        counts[status] += 1
        records.append(
            {
                "doi": clean(row.get("doi", "")),
                "source_path": str(source),
                "target_path": str(target),
                "status": status,
                "error": error,
                "candidate_row_indices": indices,
                "candidate_changes": changes,
            }
        )

    if counts["invalid"]:
        raise RuntimeError(f"Residual quarantine preconditions failed for {counts['invalid']} file(s)")

    backups: dict[str, str] = {}
    if args.apply:
        staged = stage_parquet(candidate_out, candidate_path)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = quarantine_dir / "residual_pdf_quarantine_backups" / stamp
        backup_dir.mkdir(parents=True, exist_ok=False)
        candidate_backup = backup_dir / candidate_path.name
        shutil.copy2(candidate_path, candidate_backup)
        moved: list[tuple[Path, Path]] = []
        replaced = False
        try:
            for record in records:
                source = Path(record["source_path"])
                target = Path(record["target_path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(target))
                moved.append((source, target))
                record["status"] = "moved"
            os.replace(staged, candidate_path)
            replaced = True
        except Exception:
            if replaced:
                shutil.copy2(candidate_backup, candidate_path)
            for source, target in reversed(moved):
                if target.exists() and not source.exists():
                    source.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(target), str(source))
            raise
        finally:
            staged.unlink(missing_ok=True)
        counts = Counter(record["status"] for record in records)
        backups = {"backup_dir": str(backup_dir), "candidate_backup": str(candidate_backup)}

    report = {
        "apply": bool(args.apply),
        "manifest": str(manifest_path),
        "counts": {"files": len(records), **dict(counts)},
        "backups": backups,
        "records": records,
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
    print(json.dumps(report["counts"], indent=2))
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
