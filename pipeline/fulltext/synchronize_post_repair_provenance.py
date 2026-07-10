#!/usr/bin/env python3
"""Synchronize canonical article/PDF provenance after source-identity repair.

Dry-run is the default. Apply mode backs up every changed artifact and the
candidate table, moves only unreferenced wrong PDFs into repair quarantine,
and never touches extraction or KG outputs.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.sync_paper_library import pdf_filename_for_doi  # noqa: E402


RUN_ID = "source_identity_repair_20260710"
XML_BACKENDS = {"europepmc_fulltext_xml", "pmc_oai_xml"}
DEFAULT_ARTIFACT_DIR = ROOT / "data" / "processed" / "fulltext" / "articles"
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_PDF_DIR = ROOT / "data" / "raw" / "papers" / "pdfs"
DEFAULT_RAW_ROOT = ROOT / "data" / "raw" / "papers"
DEFAULT_QUARANTINE = ROOT / "data" / "processed" / "fulltext" / "source_identity_quarantine_20260710"
DEFAULT_REPLACED_ARTIFACTS = DEFAULT_QUARANTINE / "replaced_artifacts"
DEFAULT_REPORT = ROOT / "outputs" / RUN_ID / "post_repair_provenance_sync.json"

PDF_FIELDS = (
    "pdf_local_path",
    "local_pdf_paths",
    "local_pdf_count",
    "pdf_sha256",
    "pdf_download_status",
    "flag_has_local_pdf",
)
FULLTEXT_FIELDS = (
    "best_extraction_access_tier",
    "has_converted_full_text",
    "fulltext_artifact_paths",
    "fulltext_char_count",
)


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
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip().rstrip(".")


def resolve_path(value: Any, *, workspace_root: Path = ROOT) -> Path | None:
    raw = clean(value)
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path.resolve() if path.is_absolute() else (workspace_root / path).resolve()


def split_paths(value: Any) -> list[str]:
    text = clean(value)
    if not text:
        return []
    return [part.strip() for part in text.replace(" | ", "|").split("|") if part.strip()]


def load_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def is_exact_jats_repair(artifact: dict) -> bool:
    identity = artifact.get("source_identity") if isinstance(artifact.get("source_identity"), dict) else {}
    return (
        clean(artifact.get("repair_run_id", "")) == RUN_ID
        and clean(identity.get("status", "")) == "verified_exact_doi"
        and clean(artifact.get("best_backend", "")) in XML_BACKENDS
    )


def index_frame_by_doi(frame: pd.DataFrame) -> dict[str, Any]:
    if "doi" not in frame.columns:
        raise ValueError("candidate table is missing DOI column")
    out: dict[str, Any] = {}
    for index, value in frame["doi"].items():
        doi = normalize_doi(value)
        if not doi:
            continue
        if doi in out:
            # Prefer the row whose stored DOI is already canonical (for
            # example, no trailing full stop) and treat the other as an alias
            # collision below.
            current_raw = clean(frame.at[out[doi], "doi"]).lower()
            incoming_raw = clean(value).lower()
            if incoming_raw == doi and current_raw != doi:
                out[doi] = index
        else:
            out[doi] = index
    return out


def artifact_records(
    *,
    artifact_dir: Path,
    pdf_dir: Path,
    replaced_artifacts_dir: Path,
    workspace_root: Path,
) -> list[dict]:
    records: list[dict] = []
    for path in sorted(artifact_dir.glob("*.json")):
        artifact = load_json(path)
        doi = normalize_doi(artifact.get("study_doi", ""))
        if not doi:
            continue
        canonical_pdf = (pdf_dir / pdf_filename_for_doi(doi)).resolve()
        current_pdf = resolve_path(artifact.get("pdf_local_path", ""), workspace_root=workspace_root)
        backup_path = replaced_artifacts_dir / path.name
        backup = load_json(backup_path) if backup_path.exists() else {}
        backup_pdf = resolve_path(backup.get("pdf_local_path", ""), workspace_root=workspace_root)
        exact_replaced_pdf = bool(is_exact_jats_repair(artifact) and backup and backup_pdf is not None)

        if exact_replaced_pdf:
            desired_pdf = None
        elif canonical_pdf.is_file():
            desired_pdf = canonical_pdf
        else:
            desired_pdf = current_pdf

        try:
            best_char_count = int(artifact.get("best_char_count", 0) or 0)
        except (TypeError, ValueError):
            best_char_count = 0
        records.append(
            {
                "doi": doi,
                "artifact_path": path.resolve(),
                "artifact": artifact,
                "best_char_count": best_char_count,
                "ready": best_char_count > 0,
                "current_pdf": current_pdf,
                "canonical_pdf": canonical_pdf,
                "desired_pdf": desired_pdf,
                "exact_jats_pdf_replacement": exact_replaced_pdf,
                "replaced_artifact_backup": backup_path.resolve() if backup_path.exists() else None,
                "backup_pdf": backup_pdf,
            }
        )
    return records


def candidate_artifact_collisions(
    frame: pd.DataFrame,
    *,
    workspace_root: Path,
) -> tuple[list[dict], set[Any]]:
    if "fulltext_artifact_paths" not in frame.columns:
        return [], set()
    references: dict[Path, list[dict]] = defaultdict(list)
    for index, row in frame.iterrows():
        doi = normalize_doi(row.get("doi", ""))
        if not doi:
            continue
        for raw in split_paths(row.get("fulltext_artifact_paths", "")):
            path = resolve_path(raw, workspace_root=workspace_root)
            if path is not None and path.is_file():
                references[path].append(
                    {
                        "index": index,
                        "raw_doi": clean(row.get("doi", "")).lower(),
                        "normalized_doi": doi,
                    }
                )

    collisions: list[dict] = []
    alias_indices: set[Any] = set()
    for path, candidate_rows in sorted(references.items(), key=lambda item: str(item[0])):
        artifact = load_json(path)
        canonical_doi = normalize_doi(artifact.get("study_doi", ""))
        if not canonical_doi:
            continue
        alias_rows = [
            row
            for row in candidate_rows
            if row["normalized_doi"] != canonical_doi or row["raw_doi"] != canonical_doi
        ]
        if not alias_rows:
            continue
        alias_indices.update(row["index"] for row in alias_rows)
        candidate_dois = sorted({row["raw_doi"] for row in candidate_rows})
        alias_dois = sorted({row["raw_doi"] for row in alias_rows})
        collisions.append(
            {
                "artifact_path": str(path),
                "canonical_doi": canonical_doi,
                "candidate_dois": candidate_dois,
                "alias_dois": alias_dois,
                "canonical_candidate_present": any(
                    row["normalized_doi"] == canonical_doi and row["raw_doi"] == canonical_doi
                    for row in candidate_rows
                ),
                "multiple_candidate_rows": len(candidate_rows) > 1,
            }
        )
    return collisions, alias_indices


def planned_pdf_references(records: list[dict]) -> dict[Path, set[str]]:
    out: dict[Path, set[str]] = defaultdict(set)
    for record in records:
        path = record.get("desired_pdf")
        if isinstance(path, Path):
            out[path.resolve()].add(record["doi"])
    return out


def unique_quarantine_destination(source: Path, quarantine_dir: Path) -> Path:
    target_dir = quarantine_dir / "provenance_sync_wrong_pdfs"
    target = target_dir / source.name
    if not target.exists():
        return target
    digest = sha256_file(source)[:12]
    target = target_dir / f"{source.stem}__{digest}{source.suffix}"
    suffix = 1
    while target.exists():
        target = target_dir / f"{source.stem}__{digest}_{suffix}{source.suffix}"
        suffix += 1
    return target


def wrong_pdf_actions(
    records: list[dict],
    *,
    raw_root: Path,
    quarantine_dir: Path,
) -> list[dict]:
    references = planned_pdf_references(records)
    sources: dict[Path, set[str]] = defaultdict(set)
    reasons: dict[Path, set[str]] = defaultdict(set)
    for record in records:
        if not record["exact_jats_pdf_replacement"]:
            continue
        old_path = record.get("backup_pdf")
        canonical_path = record.get("canonical_pdf")
        if isinstance(old_path, Path):
            sources[old_path.resolve()].add(record["doi"])
            reasons[old_path.resolve()].add("replaced_artifact_pdf_local_path")
        if isinstance(canonical_path, Path) and canonical_path.is_file():
            sources[canonical_path.resolve()].add(record["doi"])
            reasons[canonical_path.resolve()].add("canonical_copy_for_exact_jats_replacement")

    actions: list[dict] = []
    for source, dois in sorted(sources.items(), key=lambda item: str(item[0])):
        live_references = sorted(references.get(source, set()))
        if not source.exists():
            action = "missing"
            destination = ""
        elif not is_within(source, raw_root):
            action = "outside_active_raw_store"
            destination = ""
        elif live_references:
            action = "retained_referenced"
            destination = ""
        else:
            action = "planned_move"
            destination = str(unique_quarantine_destination(source, quarantine_dir))
        actions.append(
            {
                "source": str(source),
                "destination": destination,
                "action": action,
                "repair_dois": sorted(dois),
                "reasons": sorted(reasons[source]),
                "remaining_artifact_references": live_references,
                "sha256": sha256_file(source) if source.is_file() else "",
            }
        )
    return actions


def set_if_changed(frame: pd.DataFrame, index: Any, field: str, value: Any, changes: dict) -> None:
    if field not in frame.columns:
        return
    current = frame.at[index, field]
    if isinstance(value, bool):
        equal = bool(current) == value if not pd.isna(current) else False
    elif isinstance(value, int):
        try:
            equal = int(current or 0) == value
        except (TypeError, ValueError):
            equal = False
    else:
        equal = clean(current) == clean(value)
    if equal:
        return
    changes[field] = {"before": clean(current), "after": value}
    frame.at[index, field] = value


def clear_alias_candidate(frame: pd.DataFrame, index: Any, changes: dict) -> None:
    for field, value in (
        ("pdf_local_path", ""),
        ("local_pdf_paths", ""),
        ("local_pdf_count", 0),
        ("pdf_sha256", ""),
        ("pdf_download_status", "source_identity_alias_collision"),
        ("flag_has_local_pdf", False),
        ("best_extraction_access_tier", ""),
        ("has_converted_full_text", False),
        ("fulltext_artifact_paths", ""),
        ("fulltext_char_count", 0),
    ):
        set_if_changed(frame, index, field, value, changes)


def update_candidate_provenance(
    frame: pd.DataFrame,
    records: list[dict],
    *,
    alias_indices: set[Any],
) -> tuple[pd.DataFrame, dict]:
    out = frame.copy(deep=True)
    index_by_doi = index_frame_by_doi(out)
    changes_by_doi: dict[str, dict] = {}

    # Clear malformed alias rows first. A row with its own exact active artifact
    # may then be populated from that artifact below.
    for index in sorted(alias_indices, key=str):
        doi = clean(out.at[index, "doi"]).lower()
        changes: dict[str, dict] = {}
        clear_alias_candidate(out, index, changes)
        if changes:
            changes_by_doi.setdefault(doi, {}).update(changes)

    missing_dois: list[str] = []
    hash_cache: dict[Path, str] = {}
    for record in records:
        doi = record["doi"]
        index = index_by_doi.get(doi)
        if index is None:
            missing_dois.append(doi)
            continue
        changes = changes_by_doi.setdefault(doi, {})
        artifact_path = str(record["artifact_path"])
        if record["ready"]:
            fulltext_updates = (
                ("best_extraction_access_tier", "full_text_available"),
                ("has_converted_full_text", True),
                ("fulltext_artifact_paths", artifact_path),
                ("fulltext_char_count", record["best_char_count"]),
            )
        else:
            fulltext_updates = (
                ("best_extraction_access_tier", ""),
                ("has_converted_full_text", False),
                ("fulltext_artifact_paths", ""),
                ("fulltext_char_count", 0),
            )
        for field, value in fulltext_updates:
            set_if_changed(out, index, field, value, changes)

        desired_pdf = record.get("desired_pdf")
        if record["exact_jats_pdf_replacement"]:
            for field, value in (
                ("pdf_local_path", ""),
                ("local_pdf_paths", ""),
                ("local_pdf_count", 0),
                ("pdf_sha256", ""),
                ("pdf_download_status", "source_identity_quarantined"),
                ("flag_has_local_pdf", False),
            ):
                set_if_changed(out, index, field, value, changes)
        elif isinstance(desired_pdf, Path) and desired_pdf.is_file():
            if desired_pdf not in hash_cache:
                hash_cache[desired_pdf] = sha256_file(desired_pdf)
            digest = hash_cache[desired_pdf]
            current_status = clean(out.at[index, "pdf_download_status"]) if "pdf_download_status" in out.columns else ""
            status = (
                current_status
                if current_status in {"downloaded", "already_present", "manual_import"}
                else "already_present"
            )
            for field, value in (
                ("pdf_local_path", str(desired_pdf)),
                ("local_pdf_paths", str(desired_pdf)),
                ("local_pdf_count", 1),
                ("pdf_sha256", digest),
                ("pdf_download_status", status),
                ("flag_has_local_pdf", True),
            ):
                set_if_changed(out, index, field, value, changes)

        if not changes:
            changes_by_doi.pop(doi, None)

    field_counts: Counter[str] = Counter()
    for changes in changes_by_doi.values():
        field_counts.update(changes.keys())
    return out, {
        "rows_changed": len(changes_by_doi),
        "changed_dois": sorted(changes_by_doi),
        "missing_artifact_dois": sorted(set(missing_dois)),
        "field_change_counts": dict(sorted(field_counts.items())),
        "changes": changes_by_doi,
    }


def artifact_updates(records: list[dict]) -> tuple[dict[Path, dict], list[dict]]:
    updates: dict[Path, dict] = {}
    report: list[dict] = []
    for record in records:
        artifact = dict(record["artifact"])
        desired = record.get("desired_pdf")
        desired_text = str(desired) if isinstance(desired, Path) else ""
        current_text = clean(artifact.get("pdf_local_path", ""))
        should_update = bool(record["exact_jats_pdf_replacement"] or (isinstance(desired, Path) and desired.is_file()))
        changed = bool(should_update and current_text != desired_text)
        if changed:
            artifact["pdf_local_path"] = desired_text
            updates[record["artifact_path"]] = artifact
        report.append(
            {
                "doi": record["doi"],
                "artifact_path": str(record["artifact_path"]),
                "current_pdf_local_path": current_text,
                "desired_pdf_local_path": desired_text,
                "canonical_pdf_exists": bool(record["canonical_pdf"].is_file()),
                "exact_jats_pdf_replacement": bool(record["exact_jats_pdf_replacement"]),
                "changed": changed,
            }
        )
    return updates, report


def unique_backup_dir(quarantine_dir: Path) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = quarantine_dir / "provenance_sync_backups" / stamp
    candidate = base
    suffix = 1
    while candidate.exists():
        candidate = base.with_name(f"{base.name}_{suffix}")
        suffix += 1
    return candidate


def stage_candidate(frame: pd.DataFrame, destination: Path) -> Path:
    descriptor, raw = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp.parquet", dir=destination.parent)
    os.close(descriptor)
    path = Path(raw)
    try:
        frame.to_parquet(path, engine="pyarrow", index=False)
        shutil.copymode(destination, path)
        check = pd.read_parquet(path)
        if len(check) != len(frame) or list(check.columns) != list(frame.columns):
            raise RuntimeError("candidate table staging validation failed")
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, payload: dict) -> None:
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(descriptor)
    temp = Path(raw)
    try:
        temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        shutil.copymode(path, temp)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def apply_plan(
    *,
    candidate_path: Path,
    candidate_frame: pd.DataFrame,
    artifact_payloads: dict[Path, dict],
    pdf_actions: list[dict],
    quarantine_dir: Path,
) -> dict:
    staged_candidate = stage_candidate(candidate_frame, candidate_path)
    backup_dir = unique_backup_dir(quarantine_dir)
    artifact_backup_dir = backup_dir / "artifacts"
    candidate_backup = backup_dir / candidate_path.name
    artifact_backups: dict[Path, Path] = {}
    try:
        artifact_backup_dir.mkdir(parents=True, exist_ok=False)
        shutil.copy2(candidate_path, candidate_backup)
        for path in artifact_payloads:
            backup = artifact_backup_dir / path.name
            shutil.copy2(path, backup)
            artifact_backups[path] = backup
    except Exception:
        staged_candidate.unlink(missing_ok=True)
        raise

    moved: list[tuple[Path, Path]] = []
    candidate_replaced = False
    try:
        for action in pdf_actions:
            if action["action"] != "planned_move":
                continue
            source = Path(action["source"])
            destination = Path(action["destination"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            moved.append((source, destination))
            action["action"] = "moved"
        for path, payload in artifact_payloads.items():
            atomic_write_json(path, payload)
        os.replace(staged_candidate, candidate_path)
        candidate_replaced = True
    except Exception:
        if candidate_replaced:
            shutil.copy2(candidate_backup, candidate_path)
        for path, backup in artifact_backups.items():
            shutil.copy2(backup, path)
        for source, destination in reversed(moved):
            if destination.exists() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))
        raise
    finally:
        staged_candidate.unlink(missing_ok=True)

    return {
        "backup_dir": str(backup_dir),
        "candidate_backup": str(candidate_backup),
        "artifact_backups": {str(path): str(backup) for path, backup in artifact_backups.items()},
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_sync(
    *,
    artifact_dir: Path,
    candidate_path: Path,
    pdf_dir: Path,
    raw_root: Path,
    replaced_artifacts_dir: Path,
    quarantine_dir: Path,
    report_path: Path,
    workspace_root: Path = ROOT,
    apply: bool = False,
) -> dict:
    artifact_dir = artifact_dir.resolve()
    candidate_path = candidate_path.resolve()
    pdf_dir = pdf_dir.resolve()
    raw_root = raw_root.resolve()
    replaced_artifacts_dir = replaced_artifacts_dir.resolve()
    quarantine_dir = quarantine_dir.resolve()
    report_path = report_path.resolve()
    workspace_root = workspace_root.resolve()

    candidates = pd.read_parquet(candidate_path)
    candidate_columns = list(candidates.columns)
    records = artifact_records(
        artifact_dir=artifact_dir,
        pdf_dir=pdf_dir,
        replaced_artifacts_dir=replaced_artifacts_dir,
        workspace_root=workspace_root,
    )
    collisions, alias_indices = candidate_artifact_collisions(candidates, workspace_root=workspace_root)
    candidate_out, candidate_report = update_candidate_provenance(
        candidates,
        records,
        alias_indices=alias_indices,
    )
    if len(candidate_out) != len(candidates) or list(candidate_out.columns) != candidate_columns:
        raise RuntimeError("candidate row count or schema changed during provenance synchronization")
    artifact_payloads, artifact_report = artifact_updates(records)
    pdf_actions = wrong_pdf_actions(records, raw_root=raw_root, quarantine_dir=quarantine_dir)

    counts = Counter(action["action"] for action in pdf_actions)
    report = {
        "schema_version": "post_repair_provenance_sync_v1",
        "generated_at_utc": now_utc(),
        "apply": bool(apply),
        "status": "dry_run_complete",
        "inputs": {
            "artifact_dir": str(artifact_dir),
            "candidate_table": str(candidate_path),
            "pdf_dir": str(pdf_dir),
            "raw_root": str(raw_root),
            "replaced_artifacts_dir": str(replaced_artifacts_dir),
        },
        "counts": {
            "active_artifacts": len(records),
            "artifact_json_updates": len(artifact_payloads),
            "candidate_rows_changed": candidate_report["rows_changed"],
            "alias_collisions": sum(len(row["alias_dois"]) for row in collisions),
            **{f"wrong_pdf_{key}": value for key, value in sorted(counts.items())},
        },
        "artifact_updates": artifact_report,
        "candidate_updates": candidate_report,
        "alias_artifact_collisions": collisions,
        "wrong_pdf_actions": pdf_actions,
        "backups": {},
    }
    if apply:
        report["backups"] = apply_plan(
            candidate_path=candidate_path,
            candidate_frame=candidate_out,
            artifact_payloads=artifact_payloads,
            pdf_actions=pdf_actions,
            quarantine_dir=quarantine_dir,
        )
        report["status"] = "applied"
        report["counts"].update(
            {
                "wrong_pdf_moved": sum(action["action"] == "moved" for action in pdf_actions),
                "wrong_pdf_planned_move": 0,
            }
        )
    write_json(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--pdf-dir", default=str(DEFAULT_PDF_DIR))
    parser.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    parser.add_argument("--replaced-artifacts-dir", default=str(DEFAULT_REPLACED_ARTIFACTS))
    parser.add_argument("--quarantine-dir", default=str(DEFAULT_QUARANTINE))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    report = run_sync(
        artifact_dir=Path(args.artifact_dir),
        candidate_path=Path(args.candidate_table),
        pdf_dir=Path(args.pdf_dir),
        raw_root=Path(args.raw_root),
        replaced_artifacts_dir=Path(args.replaced_artifacts_dir),
        quarantine_dir=Path(args.quarantine_dir),
        report_path=Path(args.report),
        apply=bool(args.apply),
    )
    summary = {
        "status": report["status"],
        **report["counts"],
        "report": str(Path(args.report).resolve()),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
