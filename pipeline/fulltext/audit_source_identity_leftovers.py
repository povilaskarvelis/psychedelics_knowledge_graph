#!/usr/bin/env python3
"""Audit noncanonical JSON and raw-PDF leftovers after source-identity repair.

This is deliberately read-only.  It emits a complete inventory plus a narrow
quarantine manifest.  The manifest excludes files that are still referenced by
another candidate DOI, so applying it requires a separate, explicit step that
also reconciles the candidate table.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.fulltext.convert_pdfs import (  # noqa: E402
    doi_to_slug,
    normalize_doi,
    pdf_filename_prefix_for_doi,
)
from pipeline.fulltext.source_identity import title_similarity  # noqa: E402


DEFAULT_ARTICLE_DIR = ROOT / "data" / "processed" / "fulltext" / "articles"
DEFAULT_FULLTEXT_DIR = ROOT / "data" / "processed" / "fulltext"
DEFAULT_QUARANTINE_DIR = DEFAULT_FULLTEXT_DIR / "source_identity_quarantine_20260710"
DEFAULT_PAPER_DIR = ROOT / "data" / "raw" / "papers"
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_REPAIR_OUTPUT_DIR = ROOT / "outputs" / "source_identity_repair_20260710"
DEFAULT_INVENTORY_CSV = DEFAULT_REPAIR_OUTPUT_DIR / "pmc_identity_inventory.csv"
DEFAULT_QUARANTINE_REPORT = DEFAULT_REPAIR_OUTPUT_DIR / "artifact_quarantine_applied.json"
DEFAULT_MANUAL_REPAIRS = ROOT / "pipeline" / "fulltext" / "manual_source_identity_repairs.json"
DEFAULT_REPORT_JSON = DEFAULT_REPAIR_OUTPUT_DIR / "source_layer_leftover_audit.json"
DEFAULT_REPORT_CSV = DEFAULT_REPAIR_OUTPUT_DIR / "source_layer_leftover_pdf_inventory.csv"
DEFAULT_MANIFEST_JSON = DEFAULT_REPAIR_OUTPUT_DIR / "source_layer_leftover_quarantine_manifest.json"
DEFAULT_INVALID_CSV = DEFAULT_REPAIR_OUTPUT_DIR / "legacy_invalid_pdf_audit.csv"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in row.items()
                }
            )


def resolve_path(value: object) -> Path | None:
    raw = clean(value)
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def path_values(value: object) -> list[Path]:
    values: list[Path] = []
    for part in clean(value).replace(" | ", "|").split("|"):
        path = resolve_path(part)
        if path is not None and path not in values:
            values.append(path)
    return values


def sha256(path: Path, cache: dict[Path, str]) -> str:
    resolved = path.resolve()
    if resolved in cache:
        return cache[resolved]
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    cache[resolved] = digest.hexdigest()
    return cache[resolved]


def artifact_identity(artifact: dict) -> dict:
    value = artifact.get("source_identity")
    return value if isinstance(value, dict) else {}


def artifact_state(path: Path | None, artifact: dict) -> str:
    if path is None or not path.exists():
        return "quarantined_no_canonical_artifact"
    identity = artifact_identity(artifact)
    backend = clean(artifact.get("best_backend"))
    if (
        backend in {"europepmc_fulltext_xml", "pmc_oai_xml"}
        and clean(identity.get("status")) == "verified_exact_doi"
    ):
        return "replaced_by_verified_exact_jats"
    if bool(identity.get("verified")) or clean(identity.get("status")).startswith("verified"):
        return "retained_verified_canonical_artifact"
    return "canonical_artifact_requires_review"


def load_repair_artifacts(quarantine_dir: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    groups: list[dict[str, dict]] = []
    for name in ("quarantined_artifacts", "replaced_artifacts"):
        records: dict[str, dict] = {}
        for path in sorted((quarantine_dir / name).glob("*.json")):
            artifact = load_json(path)
            if not isinstance(artifact, dict):
                continue
            doi = normalize_doi(artifact.get("study_doi", ""))
            if doi:
                records[doi] = {"path": path, "artifact": artifact}
        groups.append(records)
    return groups[0], groups[1]


def candidate_references(frame: pd.DataFrame) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    by_doi: dict[str, list[dict]] = defaultdict(list)
    by_path: dict[str, list[dict]] = defaultdict(list)
    for index, row in frame.fillna("").iterrows():
        payload = row.to_dict()
        doi = normalize_doi(payload.get("doi", ""))
        summary = {
            "row_index": int(index),
            "doi": doi,
            "study_title": clean(payload.get("study_title")),
            "pdf_download_status": clean(payload.get("pdf_download_status")),
            "flag_has_local_pdf": bool(payload.get("flag_has_local_pdf")),
            "has_converted_full_text": bool(payload.get("has_converted_full_text")),
            "fulltext_artifact_paths": clean(payload.get("fulltext_artifact_paths")),
        }
        if doi:
            by_doi[doi].append({**summary, "row": payload})
        seen: dict[str, set[str]] = defaultdict(set)
        for field in ("pdf_local_path", "local_pdf_paths"):
            for path in path_values(payload.get(field, "")):
                seen[str(path)].add(field)
        for path, fields in seen.items():
            by_path[path].append({**summary, "fields": sorted(fields)})
    return dict(by_doi), dict(by_path)


def canonical_artifacts(article_dir: Path) -> tuple[dict[str, dict], dict[str, list[str]]]:
    by_doi: dict[str, dict] = {}
    pdf_references: dict[str, set[str]] = defaultdict(set)
    for path in sorted(article_dir.glob("*.json")):
        artifact = load_json(path)
        if not isinstance(artifact, dict):
            continue
        doi = normalize_doi(artifact.get("study_doi", ""))
        if doi:
            by_doi[doi] = {"path": path, "artifact": artifact}
        pdf = resolve_path(artifact.get("pdf_local_path", ""))
        if pdf is not None and doi:
            pdf_references[str(pdf)].add(doi)
    return by_doi, {path: sorted(dois) for path, dois in pdf_references.items()}


def load_inventory(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    frame = pd.read_csv(path, dtype=str).fillna("")
    return {
        doi: row
        for row in frame.to_dict("records")
        if (doi := normalize_doi(row.get("doi", "")))
    }


def load_quarantine_rows(path: Path) -> dict[str, dict]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        return {}
    return {
        doi: row
        for row in payload.get("records", [])
        if isinstance(row, dict) and (doi := normalize_doi(row.get("doi", "")))
    }


def load_manual_rows(path: Path) -> dict[str, dict]:
    payload = load_json(path)
    if not isinstance(payload, list):
        return {}
    return {
        doi: row
        for row in payload
        if isinstance(row, dict) and (doi := normalize_doi(row.get("doi", "")))
    }


def source_json_hits(fulltext_dir: Path, target_dois: set[str]) -> tuple[list[dict], list[dict]]:
    slug_to_dois: dict[str, set[str]] = defaultdict(set)
    for doi in target_dois:
        slug_to_dois[doi_to_slug(doi)].add(doi)
    hits: list[dict] = []
    for path in fulltext_dir.rglob("*.json"):
        relative = path.relative_to(fulltext_dir)
        if relative.parts[0] in {"articles", "source_identity_quarantine_20260710"}:
            continue
        if path.stem in slug_to_dois:
            hits.append({"path": str(path.resolve()), "possible_dois": sorted(slug_to_dois[path.stem])})
    layer_rows = []
    for name in ("disorder", "mechanistic", "pmc_xml", "europepmc_xml"):
        directory = fulltext_dir / name
        layer_rows.append(
            {
                "layer": name,
                "path": str(directory.resolve()),
                "exists": directory.exists(),
                "json_files": len(list(directory.glob("*.json"))) if directory.exists() else 0,
            }
        )
    return hits, layer_rows


def legacy_invalid_audit(
    paper_dir: Path,
    article_by_doi: dict[str, dict],
    digest_cache: dict[Path, str],
) -> list[dict]:
    rows: list[dict] = []
    active_dir = paper_dir / "pdfs"
    for invalid_path in sorted((paper_dir / "invalid").glob("*.pdf")):
        token = invalid_path.stem.split("__", 1)[0]
        doi = normalize_doi(token.replace("_", "/", 1))
        active = sorted(active_dir.glob(f"{pdf_filename_prefix_for_doi(doi)}__*.pdf"))
        invalid_hash = sha256(invalid_path, digest_cache)
        current = article_by_doi.get(doi, {})
        current_artifact = current.get("artifact", {}) if isinstance(current, dict) else {}
        identity = artifact_identity(current_artifact)
        active_rows = []
        for path in active:
            active_hash = sha256(path, digest_cache)
            active_rows.append(
                {
                    "path": str(path.resolve()),
                    "sha256": active_hash,
                    "same_bytes_as_invalid": active_hash == invalid_hash,
                    "bytes": path.stat().st_size,
                }
            )
        rows.append(
            {
                "doi": doi,
                "invalid_pdf_path": str(invalid_path.resolve()),
                "invalid_sha256": invalid_hash,
                "invalid_bytes": invalid_path.stat().st_size,
                "active_pdf_count": len(active_rows),
                "active_pdfs": active_rows,
                "identical_active_copy_count": sum(bool(row["same_bytes_as_invalid"]) for row in active_rows),
                "current_canonical_exists": bool(current),
                "current_backend": clean(current_artifact.get("best_backend")),
                "current_identity_status": clean(identity.get("status")),
                "action": "retain_distinct_active_replacement"
                if active_rows and not any(row["same_bytes_as_invalid"] for row in active_rows)
                else ("quarantine_identical_active_invalid_copy" if active_rows else "no_active_copy"),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article-dir", default=str(DEFAULT_ARTICLE_DIR))
    parser.add_argument("--fulltext-dir", default=str(DEFAULT_FULLTEXT_DIR))
    parser.add_argument("--quarantine-dir", default=str(DEFAULT_QUARANTINE_DIR))
    parser.add_argument("--paper-dir", default=str(DEFAULT_PAPER_DIR))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--inventory-csv", default=str(DEFAULT_INVENTORY_CSV))
    parser.add_argument("--quarantine-report", default=str(DEFAULT_QUARANTINE_REPORT))
    parser.add_argument("--manual-repairs", default=str(DEFAULT_MANUAL_REPAIRS))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    parser.add_argument("--report-csv", default=str(DEFAULT_REPORT_CSV))
    parser.add_argument("--manifest-json", default=str(DEFAULT_MANIFEST_JSON))
    parser.add_argument("--invalid-csv", default=str(DEFAULT_INVALID_CSV))
    args = parser.parse_args()

    article_dir = Path(args.article_dir).resolve()
    fulltext_dir = Path(args.fulltext_dir).resolve()
    quarantine_dir = Path(args.quarantine_dir).resolve()
    paper_dir = Path(args.paper_dir).resolve()
    active_pdf_dir = paper_dir / "pdfs"
    candidate_table = Path(args.candidate_table).resolve()

    quarantined, replaced = load_repair_artifacts(quarantine_dir)
    target_dois = set(quarantined) | set(replaced)
    article_by_doi, canonical_pdf_refs = canonical_artifacts(article_dir)
    candidate_frame = pd.read_parquet(candidate_table)
    candidate_by_doi, candidate_pdf_refs = candidate_references(candidate_frame)
    inventory = load_inventory(Path(args.inventory_csv).resolve())
    quarantine_rows = load_quarantine_rows(Path(args.quarantine_report).resolve())
    manual_rows = load_manual_rows(Path(args.manual_repairs).resolve())
    digest_cache: dict[Path, str] = {}

    prefix_to_dois: dict[str, set[str]] = defaultdict(set)
    for doi in target_dois:
        prefix_to_dois[pdf_filename_prefix_for_doi(doi)].add(doi)
    active_pdfs: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(active_pdf_dir.glob("*.pdf")):
        for doi in prefix_to_dois.get(path.stem.split("__", 1)[0].lower(), set()):
            active_pdfs[doi].append(path)

    repair_rows: list[dict] = []
    manifest_records: list[dict] = []
    action_dois: dict[str, set[str]] = defaultdict(set)
    active_action_files: Counter[str] = Counter()
    for doi in sorted(target_dois):
        current = article_by_doi.get(doi, {})
        current_path = current.get("path") if isinstance(current, dict) else None
        current_artifact = current.get("artifact", {}) if isinstance(current, dict) else {}
        current_identity = artifact_identity(current_artifact)
        state = artifact_state(current_path, current_artifact)
        backup = quarantined.get(doi) if state == "quarantined_no_canonical_artifact" else replaced.get(doi)
        if not backup:
            backup = replaced.get(doi) or quarantined.get(doi) or {}
        old_artifact = backup.get("artifact", {}) if isinstance(backup, dict) else {}
        old_pdf = resolve_path(old_artifact.get("pdf_local_path", ""))
        qrow = quarantine_rows.get(doi, {})
        irow = inventory.get(doi, {})
        mrow = manual_rows.get(doi, {})
        pdfs = active_pdfs.get(doi, [])
        if not pdfs:
            action = "no_active_pdf"
            action_dois[action].add(doi)
            repair_rows.append(
                {
                    "doi": doi,
                    "repair_groups": sorted(
                        group
                        for group, records in (("quarantined", quarantined), ("replaced", replaced))
                        if doi in records
                    ),
                    "current_state": state,
                    "current_canonical_path": str(current_path.resolve()) if isinstance(current_path, Path) else "",
                    "current_backend": clean(current_artifact.get("best_backend")),
                    "current_identity_status": clean(current_identity.get("status")),
                    "backup_artifact_path": str(backup.get("path", "")),
                    "old_artifact_backend": clean(old_artifact.get("best_backend")),
                    "old_artifact_pdf_local_path": clean(old_artifact.get("pdf_local_path")),
                    "old_artifact_pdf_path_exists": bool(old_pdf and old_pdf.exists()),
                    "active_pdf_path": "",
                    "active_pdf_sha256": "",
                    "active_pdf_bytes": 0,
                    "canonical_reference_dois": [],
                    "candidate_references": [],
                    "cross_doi_candidate_references": [],
                    "quarantine_reasons": qrow.get("reasons", []),
                    "quarantine_classification": clean(qrow.get("classification")),
                    "inventory_identity_class": clean(irow.get("identity_class")),
                    "inventory_artifact_header_doi": clean(irow.get("artifact_header_doi")),
                    "inventory_artifact_header_title": clean(irow.get("artifact_header_title")),
                    "inventory_title_similarity": clean(irow.get("title_similarity")),
                    "correct_acquisition_method": clean(irow.get("correct_acquisition_method"))
                    or clean(mrow.get("correct_acquisition_method")),
                    "action": action,
                }
            )
            continue

        for pdf_path in pdfs:
            resolved_pdf = str(pdf_path.resolve())
            candidate_refs = candidate_pdf_refs.get(resolved_pdf, [])
            canonical_refs = canonical_pdf_refs.get(resolved_pdf, [])
            cross_refs = sorted({row["doi"] for row in candidate_refs if row["doi"] and row["doi"] != doi})
            requested_title = clean(old_artifact.get("study_title")) or clean(current_artifact.get("study_title"))
            equivalent_alias_refs = [
                reference
                for reference in candidate_refs
                if reference.get("doi")
                and reference["doi"] != doi
                and doi_to_slug(reference["doi"]) == doi_to_slug(doi)
                and (
                    not clean(reference.get("study_title", ""))
                    or (title_similarity(reference.get("study_title", ""), requested_title) or 0) >= 0.9
                )
            ]
            equivalent_alias_dois = sorted({reference["doi"] for reference in equivalent_alias_refs})
            unsafe_cross_refs = sorted(set(cross_refs) - set(equivalent_alias_dois))
            if state in {"quarantined_no_canonical_artifact", "replaced_by_verified_exact_jats"}:
                if canonical_refs:
                    action = "manual_review_canonical_artifact_reference"
                elif unsafe_cross_refs:
                    action = "manual_review_cross_doi_candidate_reference"
                else:
                    action = "quarantine_candidate_clear_candidate_references"
            elif state == "retained_verified_canonical_artifact":
                action = "retain_validated_pdf"
            else:
                action = "manual_review_current_canonical_state"
            action_dois[action].add(doi)
            active_action_files[action] += 1
            digest = sha256(pdf_path, digest_cache)
            row = {
                "doi": doi,
                "repair_groups": sorted(
                    group
                    for group, records in (("quarantined", quarantined), ("replaced", replaced))
                    if doi in records
                ),
                "current_state": state,
                "current_canonical_path": str(current_path.resolve()) if isinstance(current_path, Path) else "",
                "current_backend": clean(current_artifact.get("best_backend")),
                "current_identity_status": clean(current_identity.get("status")),
                "backup_artifact_path": str(backup.get("path", "")),
                "old_artifact_backend": clean(old_artifact.get("best_backend")),
                "old_artifact_pdf_local_path": clean(old_artifact.get("pdf_local_path")),
                "old_artifact_pdf_path_exists": bool(old_pdf and old_pdf.exists()),
                "old_artifact_pdf_basename_matches_active": bool(old_pdf and old_pdf.name == pdf_path.name),
                "active_pdf_path": resolved_pdf,
                "active_pdf_sha256": digest,
                "active_pdf_bytes": pdf_path.stat().st_size,
                "canonical_reference_dois": canonical_refs,
                "candidate_references": candidate_refs,
                "cross_doi_candidate_references": cross_refs,
                "equivalent_alias_candidate_references": equivalent_alias_dois,
                "quarantine_reasons": qrow.get("reasons", []),
                "quarantine_classification": clean(qrow.get("classification")),
                "inventory_identity_class": clean(irow.get("identity_class")),
                "inventory_artifact_header_doi": clean(irow.get("artifact_header_doi")),
                "inventory_artifact_header_title": clean(irow.get("artifact_header_title")),
                "inventory_title_similarity": clean(irow.get("title_similarity")),
                "correct_acquisition_method": clean(irow.get("correct_acquisition_method"))
                or clean(mrow.get("correct_acquisition_method")),
                "action": action,
            }
            repair_rows.append(row)
            if action == "quarantine_candidate_clear_candidate_references":
                target_path = quarantine_dir / "residual_pdfs" / pdf_path.name
                manifest_records.append(
                    {
                        "doi": doi,
                        "current_state": state,
                        "source_path": resolved_pdf,
                        "target_path": str(target_path.resolve()),
                        "source_sha256": digest,
                        "source_bytes": pdf_path.stat().st_size,
                        "candidate_row_indices_to_reconcile": sorted(
                            {int(reference["row_index"]) for reference in candidate_refs}
                        ),
                        "candidate_reference_dois": sorted(
                            {reference["doi"] for reference in candidate_refs if reference["doi"]}
                        ),
                        "preconditions": {
                            "canonical_pdf_reference_count": 0,
                            "cross_doi_candidate_reference_count": len(unsafe_cross_refs),
                            "equivalent_alias_reference_count": len(equivalent_alias_refs),
                            "target_exists": target_path.exists(),
                        },
                    }
                )

    noncanonical_hits, source_layers = source_json_hits(fulltext_dir, target_dois)

    conflict_rows = []
    for path in sorted((paper_dir / "pdf_conflicts").glob("*.pdf")):
        matching = sorted(prefix_to_dois.get(path.stem.split("__", 1)[0].lower(), set()))
        if matching:
            conflict_rows.append(
                {
                    "path": str(path.resolve()),
                    "possible_dois": matching,
                    "candidate_reference_count": len(candidate_pdf_refs.get(str(path.resolve()), [])),
                    "classification": "nonactive_conflict_archive",
                }
            )

    invalid_rows = legacy_invalid_audit(paper_dir, article_by_doi, digest_cache)
    duplicate_active_hashes: dict[str, list[dict]] = defaultdict(list)
    quarantine_hashes: dict[str, list[str]] = defaultdict(list)
    for group in ("quarantined_pdfs", "replaced_pdfs"):
        for path in (quarantine_dir / group).glob("*.pdf"):
            quarantine_hashes[sha256(path, digest_cache)].append(str(path.resolve()))
    for row in repair_rows:
        digest = clean(row.get("active_pdf_sha256"))
        if digest and row.get("action") in {
            "quarantine_candidate_clear_candidate_references",
            "manual_review_cross_doi_candidate_reference",
        }:
            duplicate_active_hashes[digest].append({"doi": row["doi"], "path": row["active_pdf_path"]})
            row["same_hash_quarantined_pdf_paths"] = quarantine_hashes.get(digest, [])
    duplicate_groups = [
        {"sha256": digest, "records": records}
        for digest, records in duplicate_active_hashes.items()
        if len(records) > 1
    ]

    active_rows = [row for row in repair_rows if clean(row.get("active_pdf_path"))]
    suspect_actions = {
        "quarantine_candidate_clear_candidate_references",
        "manual_review_cross_doi_candidate_reference",
        "manual_review_canonical_artifact_reference",
    }
    suspect_rows = [row for row in active_rows if row.get("action") in suspect_actions]
    summary = {
        "target_dois": len(target_dois),
        "quarantined_artifact_dois": len(quarantined),
        "replaced_artifact_dois": len(replaced),
        "overlap_dois": len(set(quarantined) & set(replaced)),
        "active_pdf_files_for_target_dois": len(active_rows),
        "active_pdf_dois_for_target_dois": len({row["doi"] for row in active_rows}),
        "active_pdf_bytes_for_target_dois": sum(int(row.get("active_pdf_bytes", 0)) for row in active_rows),
        "suspect_active_pdf_files": len(suspect_rows),
        "suspect_quarantined_no_canonical_files": sum(
            row.get("current_state") == "quarantined_no_canonical_artifact" for row in suspect_rows
        ),
        "suspect_exact_jats_replacement_files": sum(
            row.get("current_state") == "replaced_by_verified_exact_jats" for row in suspect_rows
        ),
        "suspect_old_pdf_path_missing": sum(
            not bool(row.get("old_artifact_pdf_path_exists")) for row in suspect_rows
        ),
        "suspect_old_pdf_path_in_removed_source_subdir": sum(
            "/data/raw/papers/" in clean(row.get("old_artifact_pdf_local_path"))
            and "/data/raw/papers/pdfs/" not in clean(row.get("old_artifact_pdf_local_path"))
            for row in suspect_rows
        ),
        "suspect_old_pdf_basename_matches_active": sum(
            bool(row.get("old_artifact_pdf_basename_matches_active")) for row in suspect_rows
        ),
        "suspect_cross_doi_candidate_reference_files": sum(
            bool(row.get("cross_doi_candidate_references")) for row in suspect_rows
        ),
        "suspect_hash_matches_existing_quarantine_files": sum(
            bool(row.get("same_hash_quarantined_pdf_paths")) for row in suspect_rows
        ),
        "suspect_duplicate_hash_groups": len(duplicate_groups),
        "noncanonical_source_json_hits": len(noncanonical_hits),
        "conflict_archive_pdf_hits": len(conflict_rows),
        "legacy_invalid_pdfs": len(invalid_rows),
        "legacy_invalid_identical_active_copies": sum(
            int(row["identical_active_copy_count"]) for row in invalid_rows
        ),
        "action_doi_counts": {key: len(value) for key, value in sorted(action_dois.items())},
        "active_action_file_counts": dict(sorted(active_action_files.items())),
        "manifest_files": len(manifest_records),
        "manifest_bytes": sum(int(row["source_bytes"]) for row in manifest_records),
    }
    report = {
        "schema_version": "source_identity_leftover_audit_v1",
        "generated_at_utc": now_utc(),
        "inputs": {
            "article_dir": str(article_dir),
            "fulltext_dir": str(fulltext_dir),
            "quarantine_dir": str(quarantine_dir),
            "paper_dir": str(paper_dir),
            "candidate_table": str(candidate_table),
        },
        "summary": summary,
        "source_layers": source_layers,
        "noncanonical_source_json_hits": noncanonical_hits,
        "pdf_inventory": repair_rows,
        "conflict_archive_hits": conflict_rows,
        "legacy_invalid_pdf_audit": invalid_rows,
        "duplicate_active_pdf_groups": duplicate_groups,
    }
    manifest = {
        "schema_version": "source_identity_residual_pdf_quarantine_manifest_v1",
        "generated_at_utc": report["generated_at_utc"],
        "apply": False,
        "safety_note": (
            "Read-only manifest. Move each file and clear only its exact path from the listed candidate "
            "rows in one atomic operation; re-run the audit immediately before applying."
        ),
        "counts": {
            "files": len(manifest_records),
            "dois": len({row["doi"] for row in manifest_records}),
            "bytes": sum(int(row["source_bytes"]) for row in manifest_records),
        },
        "records": manifest_records,
    }

    write_json(Path(args.report_json).resolve(), report)
    write_csv(Path(args.report_csv).resolve(), repair_rows)
    write_json(Path(args.manifest_json).resolve(), manifest)
    write_csv(Path(args.invalid_csv).resolve(), invalid_rows)
    print(json.dumps(summary, indent=2))
    print(f"Report: {Path(args.report_json).resolve()}")
    print(f"Inventory: {Path(args.report_csv).resolve()}")
    print(f"Manifest: {Path(args.manifest_json).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
