#!/usr/bin/env python3
"""Promote one complete discovery run into the canonical candidate corpus."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.discovery.artifacts import contexts_from_hits_parquet
from pipeline.discovery.providers import normalize_doi, utc_now
from pipeline.discovery.runner import atomic_write_json, read_json
from pipeline.discovery.strategy import DEFAULT_HISTORY_PATH, clean, normalized_key
from pipeline.ingest.abstract_quality import best_valid_abstract


DEFAULT_RUN_ROOT = ROOT / "data" / "processed" / "discovery" / "runs"
DEFAULT_CANDIDATES = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_CONTEXTS = ROOT / "data" / "processed" / "corpus" / "candidate_contexts.parquet"
DEFAULT_UNRESOLVED = ROOT / "data" / "processed" / "discovery" / "unresolved_candidate_records.parquet"
PROMOTION_REPORT_NAME = "discovery_promotion_report.json"


class DisjointSet:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, value: str) -> str:
        self.parent.setdefault(value, value)
        if self.parent[value] != value:
            self.parent[value] = self.find(self.parent[value])
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def split_values(value: object) -> list[str]:
    return [item.strip() for item in re.split(r"\s*\|\s*", clean(value)) if item.strip()]


def join_values(values: list[object] | set[object]) -> str:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        for value in split_values(raw):
            marker = value.lower()
            if marker in seen:
                continue
            seen.add(marker)
            out.append(value)
    return " | ".join(out)


def identifiers_for_record(row: dict) -> list[str]:
    identifiers: list[str] = []
    fields = (
        ("doi", normalize_doi(row.get("doi"))),
        ("pmid", clean(row.get("pmid"))),
        ("pmcid", clean(row.get("pmcid")).upper()),
        ("openalex", clean(row.get("openalex_id")).upper()),
        ("semantic_scholar", clean(row.get("semantic_scholar_id"))),
    )
    for kind, value in fields:
        if value:
            identifiers.append(f"{kind}:{value}")
    if not identifiers:
        provider_record_id = clean(row.get("provider_record_id"))
        if provider_record_id:
            identifiers.append(f"provider:{clean(row.get('provider'))}:{provider_record_id}")
    return identifiers


def first_best(rows: list[dict], field: str) -> object:
    values = [row.get(field) for row in rows if clean(row.get(field))]
    if not values:
        return ""
    return max(values, key=lambda value: len(clean(value)))


def canonicalize_records(records: pd.DataFrame) -> list[dict]:
    rows = records.to_dict("records")
    disjoint = DisjointSet()
    row_identifiers: list[list[str]] = []
    for row in rows:
        identifiers = identifiers_for_record(row)
        row_identifiers.append(identifiers)
        for identifier in identifiers[1:]:
            disjoint.union(identifiers[0], identifier)
    groups: dict[str, list[dict]] = defaultdict(list)
    for row, identifiers in zip(rows, row_identifiers):
        root = disjoint.find(identifiers[0]) if identifiers else f"row:{len(groups)}"
        groups[root].append(row)

    canonical: list[dict] = []
    scalar_fields = (
        "doi",
        "pmid",
        "pmcid",
        "openalex_id",
        "semantic_scholar_id",
        "title",
        "authors",
        "publication_year",
        "publication_date",
        "journal",
        "publication_type",
        "language",
    )
    for group_rows in groups.values():
        row = {field: first_best(group_rows, field) for field in scalar_fields}
        abstract_row = best_valid_abstract(group_rows)
        row["abstract"] = clean(abstract_row.get("abstract", "")) if abstract_row else ""
        row["doi"] = normalize_doi(row["doi"])
        row["providers"] = join_values({item.get("provider", "") for item in group_rows})
        row["provider_record_ids"] = join_values({item.get("provider_record_id", "") for item in group_rows})
        row["search_ids"] = join_values({item.get("discovery_search_ids", "") for item in group_rows})
        row["execution_ids"] = join_values({item.get("discovery_execution_ids", "") for item in group_rows})
        identifiers = identifiers_for_record(row)
        row["record_key"] = identifiers[0] if identifiers else "title:" + normalized_key(row.get("title"))
        canonical.append(row)
    return sorted(canonical, key=lambda item: item["record_key"])


def default_for_dtype(dtype: object) -> object:
    if pd.api.types.is_bool_dtype(dtype):
        return False
    if pd.api.types.is_integer_dtype(dtype):
        return 0
    if pd.api.types.is_float_dtype(dtype):
        return 0.0
    return ""


def ensure_discovery_columns(frame: pd.DataFrame) -> pd.DataFrame:
    defaults = {
        "discovery_first_seen_at_utc": "",
        "discovery_last_seen_at_utc": "",
        "discovery_run_ids": "",
        "discovery_protocol_ids": "",
        "discovery_providers": "",
        "discovery_provider_record_ids": "",
    }
    for column, default in defaults.items():
        if column not in frame.columns:
            frame[column] = default
    return frame


def merge_candidates(
    candidates: pd.DataFrame,
    canonical_records: list[dict],
    *,
    run_id: str,
    protocol_id: str,
    promoted_at: str,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    candidates = ensure_discovery_columns(candidates.copy())
    candidates["_doi_key"] = candidates["doi"].map(normalize_doi)
    by_doi = {doi: index for index, doi in candidates["_doi_key"].items() if doi}
    new_dois: list[str] = []
    rediscovered_dois: list[str] = []
    new_rows: list[dict] = []
    defaults = {column: default_for_dtype(dtype) for column, dtype in candidates.drop(columns=["_doi_key"]).dtypes.items()}

    for record in canonical_records:
        doi = normalize_doi(record.get("doi"))
        if not doi:
            continue
        index = by_doi.get(doi)
        if index is None:
            row = dict(defaults)
            row.update(
                {
                    "doi": doi,
                    "study_title": clean(record.get("title")),
                    "study_year": clean(record.get("publication_year")),
                    "authors": clean(record.get("authors")),
                    "source_types": "living_discovery",
                    "source_count": 1,
                    "current_pipeline_status": "discovered_pending_metadata",
                    "abstract": clean(record.get("abstract")),
                    "study_journal": clean(record.get("journal")),
                    "publication_type": clean(record.get("publication_type")),
                    "publication_date": clean(record.get("publication_date")),
                    "pmid": clean(record.get("pmid")),
                    "pmcid": clean(record.get("pmcid")),
                    "openalex_id": clean(record.get("openalex_id")),
                    "semantic_scholar_id": clean(record.get("semantic_scholar_id")),
                    "language": clean(record.get("language")),
                    "flag_in_discovery_ledger": True,
                    "flag_in_discovery_queue": True,
                    "flag_in_discovery_report": True,
                    "discovery_first_seen_at_utc": promoted_at,
                    "discovery_last_seen_at_utc": promoted_at,
                    "discovery_run_ids": run_id,
                    "discovery_protocol_ids": protocol_id,
                    "discovery_providers": clean(record.get("providers")),
                    "discovery_provider_record_ids": clean(record.get("provider_record_ids")),
                }
            )
            new_rows.append(row)
            new_dois.append(doi)
            continue

        rediscovered_dois.append(doi)
        source_types = split_values(candidates.at[index, "source_types"])
        if "living_discovery" not in {value.lower() for value in source_types}:
            source_types.append("living_discovery")
            if "source_count" in candidates:
                candidates.at[index, "source_count"] = int(candidates.at[index, "source_count"] or 0) + 1
        candidates.at[index, "source_types"] = " | ".join(source_types)
        for field, source in (
            ("study_title", "title"),
            ("study_year", "publication_year"),
            ("authors", "authors"),
            ("abstract", "abstract"),
            ("study_journal", "journal"),
            ("publication_type", "publication_type"),
            ("publication_date", "publication_date"),
            ("pmid", "pmid"),
            ("pmcid", "pmcid"),
            ("openalex_id", "openalex_id"),
            ("semantic_scholar_id", "semantic_scholar_id"),
            ("language", "language"),
        ):
            if field in candidates and not clean(candidates.at[index, field]) and clean(record.get(source)):
                candidates.at[index, field] = clean(record.get(source))
        for flag in ("flag_in_discovery_ledger", "flag_in_discovery_queue", "flag_in_discovery_report"):
            if flag in candidates:
                candidates.at[index, flag] = True
        first_seen = clean(candidates.at[index, "discovery_first_seen_at_utc"])
        candidates.at[index, "discovery_first_seen_at_utc"] = first_seen or promoted_at
        candidates.at[index, "discovery_last_seen_at_utc"] = promoted_at
        candidates.at[index, "discovery_run_ids"] = join_values(
            [candidates.at[index, "discovery_run_ids"], run_id]
        )
        candidates.at[index, "discovery_protocol_ids"] = join_values(
            [candidates.at[index, "discovery_protocol_ids"], protocol_id]
        )
        candidates.at[index, "discovery_providers"] = join_values(
            [candidates.at[index, "discovery_providers"], record.get("providers", "")]
        )
        candidates.at[index, "discovery_provider_record_ids"] = join_values(
            [candidates.at[index, "discovery_provider_record_ids"], record.get("provider_record_ids", "")]
        )

    if new_rows:
        candidates = pd.concat([candidates.drop(columns=["_doi_key"]), pd.DataFrame(new_rows)], ignore_index=True)
    else:
        candidates = candidates.drop(columns=["_doi_key"])
    candidates = candidates.sort_values("doi").reset_index(drop=True)
    return candidates, sorted(set(new_dois)), sorted(set(rediscovered_dois))


def context_id(doi: str, compound: str, entity: str, entity_type: str) -> str:
    parts = [normalize_doi(doi), normalized_key(compound), normalized_key(entity), normalized_key(entity_type)]
    return "|".join(parts)


def contexts_from_hits(hits: pd.DataFrame, doi_by_provider_record: dict[str, str], run_artifact: str) -> list[dict]:
    rows: dict[str, dict] = {}
    for hit in hits.to_dict("records"):
        doi = normalize_doi(hit.get("doi")) or doi_by_provider_record.get(clean(hit.get("provider_record_id")), "")
        compound = clean(hit.get("compound"))
        entity = clean(hit.get("entity"))
        entity_type = clean(hit.get("entity_type"))
        if not doi or (not compound and not entity):
            continue
        identifier = context_id(doi, compound, entity, entity_type)
        row = rows.setdefault(
            identifier,
            {
                "context_id": identifier,
                "doi": doi,
                "compound": compound,
                "entity": entity,
                "entity_type": entity_type,
                "search_ids": set(),
                "source_artifacts": {run_artifact},
            },
        )
        row["search_ids"].add(clean(hit.get("search_id")))
    out: list[dict] = []
    for row in rows.values():
        row["search_ids"] = join_values(row["search_ids"])
        row["source_artifacts"] = join_values(row["source_artifacts"])
        out.append(row)
    return out


def merge_contexts(existing: pd.DataFrame, additions: list[dict]) -> pd.DataFrame:
    if existing.empty and not len(existing.columns):
        columns = [
            "context_id", "doi", "compound", "entity", "entity_type", "context_sources",
            "context_source_count", "verification_layer", "revalidation_status", "provenance_count",
            "selected_for_downstream", "screening_decisions", "source_artifacts",
            "flag_has_claim_stub", "flag_has_curated_claim", "flag_has_exploratory_claim",
            "flag_has_known_study_context", "flag_has_llm_verified_context", "flag_has_paper_library_context",
            "flag_has_seed_or_discovery_context", "flag_has_triage_matched_context",
            "flag_has_triage_synthesized_context", "flag_needs_revalidation", "flag_possible_acronym_collision",
            "discovery_search_ids",
        ]
        existing = pd.DataFrame(columns=columns)
    existing = existing.copy()
    if "discovery_search_ids" not in existing:
        existing["discovery_search_ids"] = ""
    by_id = {clean(value): index for index, value in existing["context_id"].items() if clean(value)}
    defaults = {column: default_for_dtype(dtype) for column, dtype in existing.dtypes.items()}
    new_rows: list[dict] = []
    for addition in additions:
        identifier = addition["context_id"]
        index = by_id.get(identifier)
        if index is None:
            row = dict(defaults)
            row.update(
                {
                    "context_id": identifier,
                    "doi": addition["doi"],
                    "compound": addition["compound"],
                    "entity": addition["entity"],
                    "entity_type": addition["entity_type"],
                    "context_sources": "living_discovery",
                    "context_source_count": 1,
                    "verification_layer": "candidate_context",
                    "revalidation_status": "candidate_needs_screening",
                    "provenance_count": len(split_values(addition["search_ids"])),
                    "selected_for_downstream": False,
                    "source_artifacts": addition["source_artifacts"],
                    "flag_has_seed_or_discovery_context": True,
                    "flag_needs_revalidation": True,
                    "discovery_search_ids": addition["search_ids"],
                }
            )
            new_rows.append(row)
            continue
        original_artifacts = split_values(existing.at[index, "source_artifacts"])
        new_artifacts = split_values(addition["source_artifacts"])
        if any(value not in original_artifacts for value in new_artifacts):
            existing.at[index, "provenance_count"] = int(existing.at[index, "provenance_count"] or 0) + len(
                split_values(addition["search_ids"])
            )
        sources = split_values(existing.at[index, "context_sources"])
        if "living_discovery" not in {value.lower() for value in sources}:
            sources.append("living_discovery")
        existing.at[index, "context_sources"] = " | ".join(sources)
        existing.at[index, "context_source_count"] = len(sources)
        existing.at[index, "source_artifacts"] = join_values([existing.at[index, "source_artifacts"], addition["source_artifacts"]])
        existing.at[index, "discovery_search_ids"] = join_values([existing.at[index, "discovery_search_ids"], addition["search_ids"]])
        existing.at[index, "flag_has_seed_or_discovery_context"] = True
        existing.at[index, "flag_needs_revalidation"] = True
    if new_rows:
        existing = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True)
    return existing.sort_values("context_id").reset_index(drop=True)


def merge_unresolved(
    existing: pd.DataFrame,
    unresolved: list[dict],
    *,
    run_id: str,
    observed_at: str,
) -> pd.DataFrame:
    columns = [
        "record_key", "title", "publication_year", "authors", "provider_record_ids", "providers",
        "pmid", "pmcid", "openalex_id", "semantic_scholar_id", "first_seen_at_utc",
        "last_seen_at_utc", "discovery_run_ids", "resolution_status",
    ]
    if existing.empty and not len(existing.columns):
        existing = pd.DataFrame(columns=columns)
    existing = existing.copy()
    for column in columns:
        if column not in existing:
            existing[column] = ""
    by_key = {clean(value): index for index, value in existing["record_key"].items() if clean(value)}
    new_rows: list[dict] = []
    for record in unresolved:
        key = clean(record.get("record_key"))
        index = by_key.get(key)
        if index is None:
            row = {column: "" for column in columns}
            row.update(
                {
                    "record_key": key,
                    "title": clean(record.get("title")),
                    "publication_year": clean(record.get("publication_year")),
                    "authors": clean(record.get("authors")),
                    "provider_record_ids": clean(record.get("provider_record_ids")),
                    "providers": clean(record.get("providers")),
                    "pmid": clean(record.get("pmid")),
                    "pmcid": clean(record.get("pmcid")),
                    "openalex_id": clean(record.get("openalex_id")),
                    "semantic_scholar_id": clean(record.get("semantic_scholar_id")),
                    "first_seen_at_utc": observed_at,
                    "last_seen_at_utc": observed_at,
                    "discovery_run_ids": run_id,
                    "resolution_status": "needs_identifier_resolution",
                }
            )
            new_rows.append(row)
            continue
        existing.at[index, "last_seen_at_utc"] = observed_at
        existing.at[index, "discovery_run_ids"] = join_values([existing.at[index, "discovery_run_ids"], run_id])
        existing.at[index, "provider_record_ids"] = join_values([existing.at[index, "provider_record_ids"], record.get("provider_record_ids", "")])
        existing.at[index, "providers"] = join_values([existing.at[index, "providers"], record.get("providers", "")])
    if new_rows:
        existing = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True)
    return existing[columns].sort_values("record_key").reset_index(drop=True)


def write_parquet_atomic(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, engine="pyarrow", index=False)
    temporary.replace(path)


def update_history(path: Path, manifest: dict, report: dict) -> None:
    history = read_json(path) if path.exists() else {"schema_version": "living_search_history_v2", "runs": []}
    runs = history.setdefault("runs", [])
    runs = [row for row in runs if row.get("run_id") != manifest["run_id"]]
    runs.append(
        {
            "run_id": manifest["run_id"],
            "protocol_id": manifest["protocol_id"],
            "status": "promoted",
            "mode": manifest["mode"],
            "coverage_start_date": manifest["coverage_start_date"],
            "coverage_end_date": manifest["coverage_end_date"],
            "strategy_hash": manifest["strategy_hash"],
            "scope_hash": manifest["scope_hash"],
            "scope_snapshot": manifest["scope_snapshot"],
            "providers": manifest["providers"],
            "datasets": manifest["datasets"],
            "layers": manifest["layers"],
            "advances_standard_update_coverage": bool(
                manifest.get("advances_standard_update_coverage", False)
            ),
            "establishes_scope_baseline": bool(manifest.get("establishes_scope_baseline", False)),
            "promoted_at_utc": report["promoted_at_utc"],
            "new_candidate_dois": report["counts"]["new_candidate_dois"],
            "rediscovered_candidate_dois": report["counts"]["rediscovered_candidate_dois"],
            "unresolved_records": report["counts"]["unresolved_records"],
        }
    )
    history["runs"] = sorted(runs, key=lambda row: (row.get("coverage_end_date", ""), row.get("run_id", "")))
    history["updated_at_utc"] = report["promoted_at_utc"]
    atomic_write_json(path, history)


def promote(
    *,
    run_dir: Path,
    candidates_path: Path = DEFAULT_CANDIDATES,
    contexts_path: Path = DEFAULT_CONTEXTS,
    unresolved_path: Path = DEFAULT_UNRESOLVED,
    history_path: Path = DEFAULT_HISTORY_PATH,
    dry_run: bool = False,
) -> dict:
    run_dir = Path(run_dir).resolve()
    manifest_path = run_dir / "run_manifest.json"
    report_path = run_dir / PROMOTION_REPORT_NAME
    manifest = read_json(manifest_path)
    if manifest.get("status") == "promoted" and report_path.exists():
        return read_json(report_path)
    if manifest.get("promotable_independently") is False:
        raise RuntimeError(
            "Refusing promotion: this run is a component reserved for a composite baseline"
        )
    if manifest.get("status") != "complete" or not manifest.get("completion_gate_passed"):
        raise RuntimeError(
            f"Refusing promotion: run status={manifest.get('status')} completion_gate_passed="
            f"{manifest.get('completion_gate_passed')}"
        )
    records_path = run_dir / "retrieved_records.parquet"
    hits_path = run_dir / "provider_hits.parquet"
    if not records_path.exists() or not hits_path.exists():
        raise FileNotFoundError("Complete run is missing retrieved-record or provider-hit artifacts")
    if not Path(candidates_path).exists():
        raise FileNotFoundError(f"Canonical candidate table not found: {candidates_path}")

    records = pd.read_parquet(records_path)
    candidates = pd.read_parquet(candidates_path)
    contexts = pd.read_parquet(contexts_path) if Path(contexts_path).exists() else pd.DataFrame()
    unresolved_existing = pd.read_parquet(unresolved_path) if Path(unresolved_path).exists() else pd.DataFrame()
    canonical = canonicalize_records(records) if not records.empty else []
    unresolved = [row for row in canonical if not normalize_doi(row.get("doi"))]
    promoted_at = utc_now()
    merged_candidates, new_dois, rediscovered_dois = merge_candidates(
        candidates,
        canonical,
        run_id=manifest["run_id"],
        protocol_id=manifest["protocol_id"],
        promoted_at=promoted_at,
    )
    doi_by_provider_record: dict[str, str] = {}
    for record in canonical:
        doi = normalize_doi(record.get("doi"))
        if not doi:
            continue
        for provider_record_id in split_values(record.get("provider_record_ids")):
            doi_by_provider_record[provider_record_id] = doi
    context_additions = contexts_from_hits_parquet(
        hits_path, doi_by_provider_record, str(run_dir)
    )
    merged_contexts = merge_contexts(contexts, context_additions)
    merged_unresolved = merge_unresolved(
        unresolved_existing,
        unresolved,
        run_id=manifest["run_id"],
        observed_at=promoted_at,
    )
    report = {
        "schema_version": "discovery_promotion_report_v2",
        "run_id": manifest["run_id"],
        "protocol_id": manifest["protocol_id"],
        "promoted_at_utc": promoted_at,
        "dry_run": dry_run,
        "completion_gate_passed": True,
        "counts": {
            "canonical_discovery_records": len(canonical),
            "new_candidate_dois": len(new_dois),
            "rediscovered_candidate_dois": len(rediscovered_dois),
            "unresolved_records": len(unresolved),
            "candidate_contexts_added_or_rediscovered": len(context_additions),
        },
        "outputs": {
            "candidate_papers": str(Path(candidates_path).resolve()),
            "candidate_contexts": str(Path(contexts_path).resolve()),
            "unresolved_candidate_records": str(Path(unresolved_path).resolve()),
            "new_doi_file": str((run_dir / "new_candidate_dois.txt").resolve()),
            "history": str(Path(history_path).resolve()),
        },
    }
    if dry_run:
        return report

    backup_dir = run_dir / "pre_promotion_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidates_path, backup_dir / Path(candidates_path).name)
    if Path(contexts_path).exists():
        shutil.copy2(contexts_path, backup_dir / Path(contexts_path).name)
    if Path(unresolved_path).exists():
        shutil.copy2(unresolved_path, backup_dir / Path(unresolved_path).name)
    write_parquet_atomic(Path(candidates_path), merged_candidates)
    write_parquet_atomic(Path(contexts_path), merged_contexts)
    write_parquet_atomic(Path(unresolved_path), merged_unresolved)
    (run_dir / "new_candidate_dois.txt").write_text(
        "".join(f"{doi}\n" for doi in new_dois), encoding="utf-8"
    )
    (run_dir / "rediscovered_candidate_dois.txt").write_text(
        "".join(f"{doi}\n" for doi in rediscovered_dois), encoding="utf-8"
    )
    atomic_write_json(report_path, report)
    update_history(Path(history_path), manifest, report)
    manifest["status"] = "promoted"
    manifest["promoted_at_utc"] = promoted_at
    manifest["promotion_report"] = str(report_path.resolve())
    manifest["updated_at_utc"] = promoted_at
    atomic_write_json(manifest_path, manifest)
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Promote a complete discovery run into the canonical candidate corpus.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-root", default=str(DEFAULT_RUN_ROOT))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--contexts-table", default=str(DEFAULT_CONTEXTS))
    parser.add_argument("--unresolved-table", default=str(DEFAULT_UNRESOLVED))
    parser.add_argument("--history", default=str(DEFAULT_HISTORY_PATH))
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    report = promote(
        run_dir=Path(args.run_root) / args.run_id,
        candidates_path=Path(args.candidate_table),
        contexts_path=Path(args.contexts_table),
        unresolved_path=Path(args.unresolved_table),
        history_path=Path(args.history),
        dry_run=args.dry_run,
    )
    print(f"Run ID: {report['run_id']}")
    print(f"New candidate DOIs: {report['counts']['new_candidate_dois']}")
    print(f"Rediscovered candidate DOIs: {report['counts']['rediscovered_candidate_dois']}")
    print(f"Unresolved no-DOI records: {report['counts']['unresolved_records']}")
    print(f"Dry run: {report['dry_run']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
