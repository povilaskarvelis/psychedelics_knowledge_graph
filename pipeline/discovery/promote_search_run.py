#!/usr/bin/env python3
"""Promote one complete discovery run into the canonical candidate corpus."""

from __future__ import annotations

import argparse
import hashlib
from collections import defaultdict
from difflib import SequenceMatcher
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
from pipeline.identity.abstracts import AbstractChecker, load_abstract_checker
from pipeline.identity.evidence import NOT_A_WORK_DOI_KINDS, OPENALEX_LEGACY_ID_MAX, doi_kind, openalex_number
from pipeline.identity.verify import Paper
from pipeline.ingest.abstract_quality import valid_abstract_rows


DEFAULT_RUN_ROOT = ROOT / "data" / "processed" / "discovery" / "runs"
DEFAULT_CANDIDATES = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_CONTEXTS = ROOT / "data" / "processed" / "corpus" / "candidate_contexts.parquet"
DEFAULT_UNRESOLVED = ROOT / "data" / "processed" / "discovery" / "unresolved_candidate_records.parquet"
PROMOTION_REPORT_NAME = "discovery_promotion_report.json"
PROMOTION_INTENT_NAME = "promotion_intent.json"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


def normalized_title(value: object) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", clean(value).casefold()))


def titles_are_coherent(left: object, right: object) -> bool:
    """Return whether two provider titles plausibly describe the same work."""

    left_key = normalized_title(left)
    right_key = normalized_title(right)
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    shorter, longer = sorted((left_key, right_key), key=len)
    if len(shorter) >= 24 and shorter in longer and len(shorter) / len(longer) >= 0.72:
        return True
    return SequenceMatcher(None, left_key, right_key).ratio() >= 0.90


def provider_priority(row: dict) -> int:
    return {
        "pubmed": 0,
        "crossref": 1,
        "openalex": 2,
        "semantic_scholar": 3,
    }.get(clean(row.get("provider")).casefold(), 10)


def legacy_openalex_record(row: dict) -> bool:
    """An OpenAlex record whose work ID is a PMID number (§2.1 of the source-identity design)."""
    number = openalex_number(row.get("openalex_id"))
    return clean(row.get("provider")).casefold() == "openalex" and number is not None and number < OPENALEX_LEGACY_ID_MAX


def corroborated(row: dict, rows: list[dict]) -> bool:
    """Another provider's record in the group gives an agreeing title."""
    return any(
        clean(other.get("provider")) != clean(row.get("provider"))
        and titles_are_coherent(other.get("title"), row.get("title"))
        for other in rows
    )


def anchor_record(rows: list[dict]) -> tuple[dict, list[dict]]:
    """The record the paper's bibliographic fields come from, and the records whose title agrees with it.

    The anchor is the record whose title agrees with most others, then the one
    from the most authoritative provider. A legacy OpenAlex record that no other
    provider corroborates is the anchor only when nothing else is available.
    """
    trusted = [row for row in rows if not legacy_openalex_record(row) or corroborated(row, rows)] or rows
    titled = [row for row in trusted if clean(row.get("title"))] or trusted
    anchor = max(
        titled,
        key=lambda row: (
            sum(titles_are_coherent(row.get("title"), other.get("title")) for other in titled),
            -provider_priority(row),
            len(clean(row.get("title"))),
        ),
    )
    agreeing = [row for row in rows if row is anchor or titles_are_coherent(row.get("title"), anchor.get("title"))]
    return anchor, agreeing


def canonicalize_records(records: pd.DataFrame, abstract_checker: AbstractChecker) -> list[dict]:
    """One candidate row per work found by the run.

    Records that share an identifier form a group. The paper's bibliographic
    fields (DOI, title, authors, journal, type, language, year and date) come
    together from one record (``anchor_record``), never field by field across
    records; identifiers may also come from records whose title agrees with it.
    The abstract is the first usable one whose provider record passes the
    identity check (``pipeline/identity/abstracts.py``, decision D5); without
    one the row has no abstract. A DOI that names no work (a funder, ISSN, issue
    or placeholder DOI) is not promoted as a paper.
    """
    rows = records.astype(object).where(records.notna(), "").to_dict("records")
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
    for group_rows in groups.values():
        anchor, agreeing = anchor_record(group_rows)
        row = {
            field: anchor.get(field, "")
            for field in ("title", "authors", "journal", "publication_type", "language", "publication_year", "publication_date")
        }
        for field in ("doi", "pmid", "pmcid", "openalex_id", "semantic_scholar_id"):
            row[field] = anchor.get(field) if clean(anchor.get(field)) else first_best(agreeing, field)
        row["doi"] = normalize_doi(row["doi"])
        kind = doi_kind(row["doi"])
        if kind in NOT_A_WORK_DOI_KINDS:
            row["resolution_status"] = f"doi_names_no_work:{kind}:{row['doi']}"
            row["doi"] = ""
        # A DOI already in the ledger keeps its record: its abstract must belong to that paper.
        paper = abstract_checker.papers.get(row["doi"]) or Paper(
            row["doi"], clean(row["title"]), clean(row["pmid"]), clean(row["pmcid"]), clean(row["journal"])
        )
        row["abstract"] = ""
        row["abstract_provider_record_id"] = ""
        for candidate in valid_abstract_rows(group_rows):
            if legacy_openalex_record(candidate) and not corroborated(candidate, group_rows):
                continue
            record = {
                "record_doi": candidate.get("doi", ""),
                "record_pmid": candidate.get("pmid", ""),
                "record_pmcid": candidate.get("pmcid", ""),
                "record_title": candidate.get("title", ""),
                "abstract": candidate.get("abstract", ""),
            }
            if row["doi"] and abstract_checker.check(row["doi"], record, paper).passes:
                row["abstract"] = clean(candidate.get("abstract", ""))
                row["abstract_provider_record_id"] = clean(candidate.get("provider_record_id", ""))
                abstract_checker.add(row["doi"], row["abstract"])
                break
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
        # Blank cells are filled from this run's record only when it describes the
        # ledger's paper; the abstract was checked against that paper already.
        same_work = titles_are_coherent(candidates.at[index, "study_title"], record.get("title")) if "study_title" in candidates else False
        if clean(record.get("abstract")) and "abstract" in candidates and not clean(candidates.at[index, "abstract"]):
            candidates.at[index, "abstract"] = clean(record.get("abstract"))
        for field, source in (
            ("study_title", "title"),
            ("study_year", "publication_year"),
            ("authors", "authors"),
            ("study_journal", "journal"),
            ("publication_type", "publication_type"),
            ("publication_date", "publication_date"),
            ("pmid", "pmid"),
            ("pmcid", "pmcid"),
            ("openalex_id", "openalex_id"),
            ("semantic_scholar_id", "semantic_scholar_id"),
            ("language", "language"),
        ):
            if (same_work or field == "study_title") and field in candidates and not clean(candidates.at[index, field]) and clean(record.get(source)):
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
                    "resolution_status": clean(record.get("resolution_status")) or "needs_identifier_resolution",
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
    completed_additions = []
    plan_path = Path(manifest.get("outputs", {}).get("search_plan_parquet", ""))
    if plan_path.is_file() and manifest.get("completion_gate_passed"):
        plan = pd.read_parquet(plan_path)
        historical = plan.loc[
            plan.layer.eq("scope_delta") & plan.search_type.eq("historical_compound_identity")
            & plan.start_date.le("1800-01-01") & plan.date_basis.eq("publication")
        ]
        for compound, group in historical.groupby("compound"):
            if {"pubmed", "openalex"} <= set(group.provider):
                completed_additions.append(compound)
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
            "completed_historical_compound_additions": sorted(completed_additions),
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

    # Persist the handoff before the first canonical write. A retry merges
    # idempotently into current tables but must retain the original new cohort.
    intent_path = run_dir / PROMOTION_INTENT_NAME
    identity = {
        "run_id": manifest["run_id"],
        "targets": [str(Path(p).resolve()) for p in
                    (candidates_path, contexts_path, unresolved_path, history_path)],
        "source_hashes": {p.name: file_sha256(p) for p in (records_path, hits_path)},
    }
    intent = read_json(intent_path) if intent_path.exists() else None
    if intent is not None and intent["identity"] != identity:
        raise RuntimeError("Promotion inputs or destinations changed since the saved promotion intent")

    records = pd.read_parquet(records_path)
    candidates = pd.read_parquet(candidates_path)
    contexts = pd.read_parquet(contexts_path) if Path(contexts_path).exists() else pd.DataFrame()
    unresolved_existing = pd.read_parquet(unresolved_path) if Path(unresolved_path).exists() else pd.DataFrame()
    canonical = canonicalize_records(records, load_abstract_checker(candidates_path)) if not records.empty else []
    unresolved = [row for row in canonical if not normalize_doi(row.get("doi"))]
    abstracts = candidates["abstract"] if "abstract" in candidates else pd.Series("", index=candidates.index)
    missing_abstract_dois = set(candidates.loc[abstracts.map(clean).eq(""), "doi"].map(normalize_doi))
    restored_abstract_dois = sorted({
        normalize_doi(row.get("doi")) for row in canonical
        if normalize_doi(row.get("doi")) in missing_abstract_dois and clean(row.get("abstract"))
    })
    promoted_at = intent["promoted_at_utc"] if intent is not None else utc_now()
    merged_candidates, new_dois, rediscovered_dois = merge_candidates(
        candidates,
        canonical,
        run_id=manifest["run_id"],
        protocol_id=manifest["protocol_id"],
        promoted_at=promoted_at,
    )
    if intent is not None:
        new_dois = intent["new_dois"]
        rediscovered_dois = intent["rediscovered_dois"]
        restored_abstract_dois = intent.get("restored_abstract_dois", [])
    screening_dois = sorted(set(new_dois) | set(restored_abstract_dois))
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
            "rediscovered_dois_with_restored_abstract": len(restored_abstract_dois),
            "screening_candidate_dois": len(screening_dois),
            "unresolved_records": len(unresolved),
            "candidate_contexts_added_or_rediscovered": len(context_additions),
        },
        "outputs": {
            "candidate_papers": str(Path(candidates_path).resolve()),
            "candidate_contexts": str(Path(contexts_path).resolve()),
            "unresolved_candidate_records": str(Path(unresolved_path).resolve()),
            "new_doi_file": str((run_dir / "new_candidate_dois.txt").resolve()),
            "screening_doi_file": str((run_dir / "screening_candidate_dois.txt").resolve()),
            "history": str(Path(history_path).resolve()),
        },
    }
    if dry_run:
        return report

    backup_dir = run_dir / "pre_promotion_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    if intent is None:
        for path in (candidates_path, contexts_path, unresolved_path, history_path):
            if Path(path).exists():
                shutil.copy2(path, backup_dir / Path(path).name)
        atomic_write_json(intent_path, {
            "schema_version": "discovery_promotion_intent_v1",
            "identity": identity,
            "promoted_at_utc": promoted_at,
            "new_dois": new_dois,
            "rediscovered_dois": rediscovered_dois,
            "restored_abstract_dois": restored_abstract_dois,
        })
    write_parquet_atomic(Path(candidates_path), merged_candidates)
    write_parquet_atomic(Path(contexts_path), merged_contexts)
    write_parquet_atomic(Path(unresolved_path), merged_unresolved)
    (run_dir / "new_candidate_dois.txt").write_text(
        "".join(f"{doi}\n" for doi in new_dois), encoding="utf-8"
    )
    (run_dir / "rediscovered_candidate_dois.txt").write_text(
        "".join(f"{doi}\n" for doi in rediscovered_dois), encoding="utf-8"
    )
    (run_dir / "screening_candidate_dois.txt").write_text(
        "".join(f"{doi}\n" for doi in screening_dois), encoding="utf-8"
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
