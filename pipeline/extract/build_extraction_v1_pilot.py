#!/usr/bin/env python3
"""Build a deterministic pilot set for extraction-v1 model calls."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

try:
    from pipeline.extract.prepare_extraction_inputs import row_doi, row_relevance, screening_record
    from pipeline.fulltext.convert_pdfs import DATASET_CONFIG, compact_text, load_json_array, load_json_object, normalize, normalize_doi
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.prepare_extraction_inputs import row_doi, row_relevance, screening_record
    from pipeline.fulltext.convert_pdfs import DATASET_CONFIG, compact_text, load_json_array, load_json_object, normalize, normalize_doi


ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
EXTRACTION_DIR = PROCESSED_DIR / "extraction"
DEFAULT_MANIFEST = PROCESSED_DIR / "corpus_manifest.json"
PILOT_SCHEMA_VERSION = "extraction_v1_pilot_input"
OUTPUT_SCHEMA_VERSION = "extraction_v1"
DEFAULT_BUCKET_ORDER = [
    "full_text_relevant",
    "full_text_uncertain",
    "abstract_relevant",
    "abstract_uncertain",
]
IRRELEVANT_CONTROL_BUCKET = "abstract_irrelevant"
ALL_BUCKET_ORDER = [*DEFAULT_BUCKET_ORDER, IRRELEVANT_CONTROL_BUCKET]
BUCKET_ORDER = DEFAULT_BUCKET_ORDER
METADATA_FIELDS = [
    "study_doi",
    "openalex_id",
    "pmid",
    "pmcid",
    "study_title",
    "study_year",
    "authors",
    "study_journal",
    "publication_type",
    "trial_registry_ids",
    "publication_date",
    "journal_issn",
    "journal_eissn",
    "publisher",
    "mesh_terms",
    "keywords",
    "funders",
    "grant_ids",
    "related_dois",
    "publication_relations",
    "is_retracted",
    "has_correction",
    "language",
    "semantic_scholar_id",
    "abstract",
]
PUBLICATION_SECONDARY_RE = re.compile(r"\b(systematic review|meta-analysis|meta analysis|review|scoping review|umbrella review)\b", re.I)
META_ANALYSIS_RE = re.compile(
    r"\b(network\s+meta[- ]analysis|individual\s+patient\s+data\s+meta[- ]analysis|"
    r"meta[- ]analysis|mega[- ]analysis)\b",
    re.I,
)
PUBLICATION_CONTEXT_RE = re.compile(r"\b(protocol|comment|editorial|letter|guideline|practice guideline|consensus)\b", re.I)
PUBLICATION_ARTIFACT_RE = re.compile(
    r"\b(peer[- ]?review|editor[- ]?report|decision[- ]?letter|author[- ]?response|correction|erratum|retraction)\b",
    re.I,
)
PUBLICATION_PRIMARY_RE = re.compile(
    r"\b(randomized controlled trial|controlled clinical trial|clinical trial|case reports?|observational study|comparative study|validation study|multicenter study|research support)\b",
    re.I,
)
TITLE_SECONDARY_RE = re.compile(r"\b(systematic review|meta-analysis|meta analysis|scoping review|umbrella review|narrative review|literature review|review)\b", re.I)
TITLE_CONTEXT_RE = re.compile(r"\b(protocol|commentary|editorial|guideline|consensus statement)\b", re.I)
TITLE_ARTIFACT_RE = re.compile(r"^\s*(decision letter|author response|editor(?:'s)? report|correction|erratum|retraction)\b", re.I)
ABSTRACT_PRIMARY_RE = re.compile(r"\b(randomi[sz]ed|double-blind|placebo-controlled|participants were|patients were|we conducted|clinical trial)\b", re.I)
ABSTRACT_SECONDARY_RE = re.compile(r"\b(systematic review|meta-analysis|we reviewed|this review|literature search|scoping review)\b", re.I)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
    return rows


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def record_dataset_doi(row: dict) -> tuple[str, str]:
    return (normalize(row.get("dataset", "")), normalize_doi(row.get("study_doi", "")))


def excluded_dataset_dois(paths: Iterable[Path]) -> set[tuple[str, str]]:
    excluded: set[tuple[str, str]] = set()
    for path in paths:
        for row in read_jsonl(path):
            key = record_dataset_doi(row)
            if all(key):
                excluded.add(key)
    return excluded


def dataset_names(raw: str) -> list[str]:
    if raw == "all":
        return ["mechanistic", "disorder"]
    return [raw]


def default_candidate_jsonl(dataset: str) -> Path:
    return EXTRACTION_DIR / f"{dataset}_extraction_candidates.jsonl"


def default_fulltext_packets_jsonl(dataset: str) -> Path:
    return EXTRACTION_DIR / f"{dataset}_fulltext_packets.jsonl"


def fulltext_packets_path_for_dataset(args: argparse.Namespace, dataset: str) -> Path:
    overrides = {
        "mechanistic": normalize(getattr(args, "mechanistic_fulltext_packets_jsonl", "")),
        "disorder": normalize(getattr(args, "disorder_fulltext_packets_jsonl", "")),
    }
    override = overrides.get(dataset, "")
    if override:
        return Path(override).resolve()
    return default_fulltext_packets_jsonl(dataset)


def default_out_jsonl() -> Path:
    return EXTRACTION_DIR / "extraction_v1_pilot_inputs.jsonl"


def default_out_csv() -> Path:
    return EXTRACTION_DIR / "extraction_v1_pilot_inputs.csv"


def default_report_json() -> Path:
    return EXTRACTION_DIR / "extraction_v1_pilot_report.json"


def rows_by_doi(rows: Iterable[dict]) -> dict[str, dict]:
    out = {}
    for row in rows:
        doi = normalize_doi(row.get("study_doi", ""))
        if doi:
            out[doi] = row
    return out


def candidate_relevance(row: dict) -> str:
    summary = row.get("screening_summary", {}) if isinstance(row.get("screening_summary"), dict) else {}
    return normalize(summary.get("best_llm_relevance", "")).lower()


def candidate_readiness(row: dict) -> str:
    readiness = row.get("readiness", {}) if isinstance(row.get("readiness"), dict) else {}
    return normalize(readiness.get("status", ""))


def candidate_metadata(row: dict) -> dict:
    metadata = row.get("paper_metadata", {}) if isinstance(row.get("paper_metadata"), dict) else {}
    return metadata_for_row(metadata)


def metadata_for_row(row: dict) -> dict:
    return {field: compact_text(row.get(field, "")) for field in METADATA_FIELDS}


def merge_metadata(*rows: dict) -> dict:
    merged = {field: "" for field in METADATA_FIELDS}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for field in METADATA_FIELDS:
            if not merged[field] and compact_text(row.get(field, "")):
                merged[field] = compact_text(row.get(field, ""))
    merged["study_doi"] = normalize_doi(merged.get("study_doi", ""))
    return merged


def flattened_screening_row(row: dict) -> dict:
    flat = {}
    input_row = row.get("input_row")
    if isinstance(input_row, dict):
        flat.update(input_row)
    flat_row = row.get("flat")
    if isinstance(flat_row, dict):
        flat.update(flat_row)
    return flat


def stable_digest(*parts: object, length: int = 16) -> str:
    canonical = "|".join(normalize(part) for part in parts)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:length]


def route_hint_for_metadata(metadata: dict) -> dict:
    publication_type = normalize(metadata.get("publication_type", ""))
    title = normalize(metadata.get("study_title", ""))
    abstract = normalize(metadata.get("abstract", ""))
    mesh_terms = normalize(metadata.get("mesh_terms", ""))
    trial_registry_ids = normalize(metadata.get("trial_registry_ids", ""))
    basis = []

    pt_secondary = bool(PUBLICATION_SECONDARY_RE.search(publication_type))
    pt_context = bool(PUBLICATION_CONTEXT_RE.search(publication_type))
    pt_artifact = bool(PUBLICATION_ARTIFACT_RE.search(publication_type))
    pt_primary = bool(PUBLICATION_PRIMARY_RE.search(publication_type))
    title_secondary = bool(TITLE_SECONDARY_RE.search(title))
    title_context = bool(TITLE_CONTEXT_RE.search(title))
    title_artifact = bool(TITLE_ARTIFACT_RE.search(title))
    abstract_secondary = bool(ABSTRACT_SECONDARY_RE.search(abstract))
    abstract_primary = bool(ABSTRACT_PRIMARY_RE.search(abstract))
    mesh_secondary = bool(PUBLICATION_SECONDARY_RE.search(mesh_terms))
    mesh_primary = bool(PUBLICATION_PRIMARY_RE.search(mesh_terms))

    if pt_secondary:
        basis.append("publication_type_secondary")
    if pt_artifact:
        basis.append("publication_type_artifact")
    if pt_context:
        basis.append("publication_type_context")
    if pt_primary:
        basis.append("publication_type_primary")
    if title_secondary:
        basis.append("title_secondary")
    if title_artifact:
        basis.append("title_artifact")
    if title_context:
        basis.append("title_context")
    if trial_registry_ids:
        basis.append("trial_registry_present")
    if mesh_secondary:
        basis.append("mesh_secondary")
    if mesh_primary:
        basis.append("mesh_primary")

    if pt_artifact or title_artifact:
        return {"hint": "likely_context_only", "confidence": "high", "basis": basis}
    if pt_context:
        return {"hint": "likely_context_only", "confidence": "high", "basis": basis}
    if pt_secondary and pt_primary:
        return {"hint": "ambiguous", "confidence": "high", "basis": basis}
    if pt_secondary or mesh_secondary:
        return {"hint": "likely_secondary", "confidence": "high", "basis": basis}
    if pt_primary or trial_registry_ids or mesh_primary:
        return {"hint": "likely_primary", "confidence": "high", "basis": basis}
    if title_secondary:
        return {"hint": "likely_secondary", "confidence": "medium", "basis": basis}
    if title_context:
        return {"hint": "likely_context_only", "confidence": "medium", "basis": basis}
    if abstract_secondary and abstract_primary:
        return {"hint": "ambiguous", "confidence": "medium", "basis": basis + ["abstract_secondary", "abstract_primary"]}
    if abstract_secondary:
        return {"hint": "likely_secondary", "confidence": "low", "basis": basis + ["abstract_secondary"]}
    if abstract_primary:
        return {"hint": "likely_primary", "confidence": "low", "basis": basis + ["abstract_primary"]}
    if publication_type:
        return {"hint": "unknown", "confidence": "low", "basis": ["publication_type_generic"]}
    return {"hint": "unknown", "confidence": "low", "basis": ["metadata_sparse"]}


def is_non_article_artifact(metadata: dict) -> bool:
    publication_type = normalize(metadata.get("publication_type", ""))
    title = normalize(metadata.get("study_title", "")) or normalize(metadata.get("title", ""))
    return bool(PUBLICATION_ARTIFACT_RE.search(publication_type)) or bool(TITLE_ARTIFACT_RE.search(title))


def is_meta_analysis_metadata(metadata: dict) -> bool:
    text = " ".join(
        normalize(metadata.get(field, ""))
        for field in ["publication_type", "study_title", "mesh_terms", "keywords", "abstract"]
    )
    return bool(META_ANALYSIS_RE.search(text.replace("_", " ")))


def pilot_record(
    *,
    dataset: str,
    bucket: str,
    study_doi: str,
    input_tier: str,
    expected_relevance: str,
    paper_metadata: dict,
    screening_summary: dict,
    source: dict,
    content: dict,
) -> dict:
    doi = normalize_doi(study_doi)
    route_hint = route_hint_for_metadata(paper_metadata)
    return {
        "schema_version": PILOT_SCHEMA_VERSION,
        "pilot_record_id": f"pilot-{stable_digest(dataset, bucket, doi, paper_metadata.get('study_title', ''))}",
        "dataset": dataset,
        "bucket": bucket,
        "study_doi": doi,
        "input_tier": input_tier,
        "access_level": "full_text_seen" if input_tier == "full_text" else "abstract_only",
        "expected_screening_relevance": expected_relevance,
        "route_hint": route_hint,
        "extraction_contract": {
            "prompt_template": "docs/extraction_v1_prompt.md",
            "dataset_prompt_templates": {
                "mechanistic": "docs/extraction_v1_mechanistic_prompt.md",
                "disorder": "docs/extraction_v1_disorder_prompt.md",
            },
            "protocol": "docs/extraction_v1_protocol.md",
            "output_schema": "schema/extraction_v1.schema.json",
            "output_schema_version": OUTPUT_SCHEMA_VERSION,
        },
        "paper_metadata": paper_metadata,
        "screening_summary": screening_summary,
        "source": source,
        "content": content,
    }


def record_sort_key(row: dict) -> tuple:
    metadata = row.get("paper_metadata", {}) if isinstance(row.get("paper_metadata"), dict) else {}
    return (
        ALL_BUCKET_ORDER.index(row["bucket"]) if row.get("bucket") in ALL_BUCKET_ORDER else 999,
        normalize(row.get("dataset", "")),
        normalize(row.get("study_doi", "")),
        normalize(metadata.get("study_title", "")),
    )


def sample_sort_key(row: dict) -> tuple:
    metadata = row.get("paper_metadata", {}) if isinstance(row.get("paper_metadata"), dict) else {}
    return (
        stable_digest(row.get("dataset", ""), row.get("bucket", ""), row.get("study_doi", ""), metadata.get("study_title", "")),
        normalize(row.get("study_doi", "")),
        normalize(metadata.get("study_title", "")),
    )


def bucket_for(input_tier: str, relevance: str) -> str:
    if input_tier == "full_text":
        return "full_text_uncertain" if relevance == "uncertain" else "full_text_relevant"
    if relevance == "irrelevant":
        return "abstract_irrelevant"
    return "abstract_uncertain" if relevance == "uncertain" else "abstract_relevant"


def abstract_content_from_candidate(candidate: dict) -> dict:
    metadata = candidate_metadata(candidate)
    return {
        "title": metadata.get("study_title", ""),
        "abstract": metadata.get("abstract", ""),
        "screening_records": candidate.get("screening_records", []),
    }


def fulltext_records(
    dataset: str,
    candidates_by_doi: dict[str, dict],
    packet_path: Path,
    *,
    include_packet_content: bool,
) -> list[dict]:
    records = []
    for packet in read_jsonl(packet_path):
        doi = normalize_doi(packet.get("study_doi", ""))
        if not doi:
            continue
        candidate = candidates_by_doi.get(doi, {})
        relevance = candidate_relevance(candidate) or "relevant"
        if relevance not in {"relevant", "uncertain"}:
            continue
        metadata = merge_metadata(packet.get("paper_metadata", {}), candidate_metadata(candidate))
        if is_non_article_artifact(metadata):
            continue
        bucket = bucket_for("full_text", relevance)
        content = {"packet": packet} if include_packet_content else {
            "packet_id": packet.get("packet_id", ""),
            "document_summary": packet.get("document_summary", {}),
            "paper_metadata": packet.get("paper_metadata", {}),
        }
        records.append(
            pilot_record(
                dataset=dataset,
                bucket=bucket,
                study_doi=doi,
                input_tier="full_text",
                expected_relevance=relevance,
                paper_metadata=metadata,
                screening_summary=candidate.get("screening_summary", {}),
                source={"record_type": "fulltext_packet", "path": str(packet_path)},
                content=content,
            )
        )
    return records


def abstract_candidate_records(dataset: str, candidates: list[dict], candidate_jsonl: Path) -> list[dict]:
    records = []
    for candidate in candidates:
        doi = normalize_doi(candidate.get("study_doi", ""))
        if not doi:
            continue
        if candidate_readiness(candidate) != "abstract_only_needs_pdf_access":
            continue
        relevance = candidate_relevance(candidate)
        if relevance not in {"relevant", "uncertain"}:
            continue
        metadata = candidate_metadata(candidate)
        if is_non_article_artifact(metadata):
            continue
        records.append(
            pilot_record(
                dataset=dataset,
                bucket=bucket_for("abstract", relevance),
                study_doi=doi,
                input_tier="abstract",
                expected_relevance=relevance,
                paper_metadata=metadata,
                screening_summary=candidate.get("screening_summary", {}),
                source={"record_type": "extraction_candidate", "path": str(candidate_jsonl)},
                content=abstract_content_from_candidate(candidate),
            )
        )
    return records


def resolve_manifest_path(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else ROOT / path


def manifest_screening_reports(manifest_path: Path, dataset: str) -> list[dict]:
    if not manifest_path.exists():
        return []
    manifest = load_json_object(manifest_path)
    datasets = manifest.get("datasets", {})
    if not isinstance(datasets, dict):
        return []
    config = datasets.get(dataset, {})
    if not isinstance(config, dict):
        return []
    out = []
    for item in config.get("screening_reports", []):
        if not isinstance(item, dict) or item.get("include", True) is False:
            continue
        path = normalize(item.get("path", ""))
        if not path:
            continue
        out.append(
            {
                "run_id": normalize(item.get("run_id", "")) or Path(path).stem,
                "path": resolve_manifest_path(path),
            }
        )
    return out


def abstract_irrelevant_records(dataset: str, manifest_path: Path, paper_rows_by_doi: dict[str, dict]) -> list[dict]:
    records = []
    seen_dois = set()
    for report in manifest_screening_reports(manifest_path, dataset):
        path = report["path"]
        if not path.exists():
            continue
        payload = load_json_object(path)
        rows = payload.get("rows", [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict) or row_relevance(row) != "irrelevant":
                continue
            doi = row_doi(row)
            if not doi or doi in seen_dois:
                continue
            flat = flattened_screening_row(row)
            abstract = compact_text(flat.get("abstract", ""))
            if not abstract:
                continue
            seen_dois.add(doi)
            metadata = merge_metadata(flat, paper_rows_by_doi.get(doi, {}))
            record = screening_record(dataset, report["run_id"], row)
            records.append(
                pilot_record(
                    dataset=dataset,
                    bucket="abstract_irrelevant",
                    study_doi=doi,
                    input_tier="abstract",
                    expected_relevance="irrelevant",
                    paper_metadata=metadata,
                    screening_summary={
                        "best_llm_relevance": "irrelevant",
                        "included_from_runs": [report["run_id"]],
                        "screening_record_count": 1,
                        "has_quote_verified_screening_support": record.get("quote_verified", False),
                    },
                    source={"record_type": "screening_negative_control", "path": str(path), "run_id": report["run_id"]},
                    content={
                        "title": metadata.get("study_title", ""),
                        "abstract": abstract,
                        "screening_records": [record],
                    },
                )
            )
    return records


def select_per_bucket(
    records: list[dict],
    per_bucket: int,
    limit_total: int = 0,
    bucket_order: list[str] | None = None,
) -> tuple[list[dict], dict]:
    selected_bucket_order = bucket_order or DEFAULT_BUCKET_ORDER
    available = Counter(row["bucket"] for row in records)
    selected = []
    seen_dataset_doi: set[tuple[str, str]] = set()
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in records:
        grouped[(row["dataset"], row["bucket"])].append(row)

    for dataset in sorted({row["dataset"] for row in records}):
        for bucket in selected_bucket_order:
            bucket_rows = sorted(grouped.get((dataset, bucket), []), key=sample_sort_key)
            for row in bucket_rows[: max(0, per_bucket)]:
                key = (row["dataset"], row["study_doi"])
                if key in seen_dataset_doi:
                    continue
                seen_dataset_doi.add(key)
                selected.append(row)

    selected = sorted(selected, key=record_sort_key)
    if limit_total > 0:
        selected = selected[:limit_total]

    summary = {
        "available_by_bucket": dict(available),
        "available_by_dataset_bucket": {
            f"{dataset}:{bucket}": len(rows)
            for (dataset, bucket), rows in sorted(grouped.items())
        },
        "selection_strategy": "stable_hash_by_dataset_bucket",
        "bucket_order": selected_bucket_order,
        "selected_by_bucket": dict(Counter(row["bucket"] for row in selected)),
        "selected_by_dataset_bucket": dict(Counter(f"{row['dataset']}:{row['bucket']}" for row in selected)),
        "selected_by_route_hint": dict(Counter(row.get("route_hint", {}).get("hint", "unknown") for row in selected)),
        "selected_records": len(selected),
    }
    return selected, summary


def build_dataset_records(
    dataset: str,
    *,
    candidate_jsonl: Path,
    fulltext_packets_jsonl: Path,
    paper_library: Path,
    manifest_path: Path,
    include_packet_content: bool,
    include_irrelevant_controls: bool = False,
) -> tuple[list[dict], dict]:
    candidates = read_jsonl(candidate_jsonl)
    candidates_by_doi = rows_by_doi(candidates)
    paper_rows_by_doi = rows_by_doi(load_json_array(paper_library)) if paper_library.exists() else {}

    records = []
    records.extend(
        fulltext_records(
            dataset,
            candidates_by_doi,
            fulltext_packets_jsonl,
            include_packet_content=include_packet_content,
        )
    )
    records.extend(abstract_candidate_records(dataset, candidates, candidate_jsonl))
    if include_irrelevant_controls:
        records.extend(abstract_irrelevant_records(dataset, manifest_path, paper_rows_by_doi))

    summary = {
        "dataset": dataset,
        "inputs": {
            "candidate_jsonl": str(candidate_jsonl),
            "fulltext_packets_jsonl": str(fulltext_packets_jsonl),
            "paper_library": str(paper_library),
            "manifest": str(manifest_path),
            "include_irrelevant_controls": include_irrelevant_controls,
        },
        "available_by_bucket": dict(Counter(row["bucket"] for row in records)),
        "available_by_route_hint": dict(Counter(row.get("route_hint", {}).get("hint", "unknown") for row in records)),
        "available_records": len(records),
    }
    return records, summary


def filter_excluded_metadata_records(
    records: list[dict],
    *,
    exclude_meta_analyses: bool,
) -> tuple[list[dict], list[dict], Counter]:
    kept = []
    excluded = []
    reasons = Counter()
    for row in records:
        metadata = row.get("paper_metadata", {}) if isinstance(row.get("paper_metadata"), dict) else {}
        reason = ""
        if exclude_meta_analyses and is_meta_analysis_metadata(metadata):
            reason = "meta_analysis_reserved_for_synthesis_extraction"
        if reason:
            parked = {
                "reason": reason,
                "dataset": row.get("dataset", ""),
                "bucket": row.get("bucket", ""),
                "study_doi": row.get("study_doi", ""),
                "input_tier": row.get("input_tier", ""),
                "access_level": row.get("access_level", ""),
                "route_hint": row.get("route_hint", {}),
                "paper_metadata": metadata,
                "source": row.get("source", {}),
                "next_action": "Run later with a dedicated evidence-synthesis/meta-analysis extraction schema.",
            }
            excluded.append(parked)
            reasons[reason] += 1
            continue
        kept.append(row)
    return kept, excluded, reasons


def filter_input_tier(records: list[dict], input_tier: str) -> list[dict]:
    if input_tier == "all":
        return records
    return [row for row in records if normalize(row.get("input_tier", "")) == input_tier]


def csv_row(row: dict) -> dict:
    metadata = row.get("paper_metadata", {})
    screening = row.get("screening_summary", {})
    return {
        "pilot_record_id": row.get("pilot_record_id", ""),
        "dataset": row.get("dataset", ""),
        "bucket": row.get("bucket", ""),
        "study_doi": row.get("study_doi", ""),
        "input_tier": row.get("input_tier", ""),
        "access_level": row.get("access_level", ""),
        "expected_screening_relevance": row.get("expected_screening_relevance", ""),
        "route_hint": row.get("route_hint", {}).get("hint", ""),
        "route_hint_confidence": row.get("route_hint", {}).get("confidence", ""),
        "route_hint_basis": " | ".join(row.get("route_hint", {}).get("basis", [])),
        "study_title": metadata.get("study_title", ""),
        "study_year": metadata.get("study_year", ""),
        "authors": metadata.get("authors", ""),
        "study_journal": metadata.get("study_journal", ""),
        "publication_type": metadata.get("publication_type", ""),
        "screening_record_count": screening.get("screening_record_count", ""),
        "source_type": row.get("source", {}).get("record_type", ""),
        "source_path": row.get("source", {}).get("path", ""),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(csv_row(rows[0]).keys()) if rows else [
        "pilot_record_id",
        "dataset",
        "bucket",
        "study_doi",
        "input_tier",
        "access_level",
        "expected_screening_relevance",
        "route_hint",
        "route_hint_confidence",
        "route_hint_basis",
        "study_title",
        "study_year",
        "authors",
        "study_journal",
        "publication_type",
        "screening_record_count",
        "source_type",
        "source_path",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(csv_row(row))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic extraction-v1 pilot input set")
    parser.add_argument("--dataset", choices=["all", "mechanistic", "disorder"], default="all")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--per-bucket", type=int, default=10, help="Records selected per dataset and bucket")
    parser.add_argument("--limit-total", type=int, default=0, help="Optional cap across all selected records; 0 means no cap")
    parser.add_argument(
        "--input-tier",
        choices=["all", "full_text", "abstract"],
        default="all",
        help="Restrict selected records by extraction input tier",
    )
    parser.add_argument("--out-jsonl", default=str(default_out_jsonl()))
    parser.add_argument("--out-csv", default=str(default_out_csv()))
    parser.add_argument("--report-json", default=str(default_report_json()))
    parser.add_argument(
        "--excluded-jsonl",
        default="",
        help="Where to write records intentionally excluded from this extraction input build",
    )
    parser.add_argument("--mechanistic-fulltext-packets-jsonl", default="", help="Override mechanistic full-text packet JSONL")
    parser.add_argument("--disorder-fulltext-packets-jsonl", default="", help="Override disorder full-text packet JSONL")
    parser.add_argument(
        "--exclude-jsonl",
        action="append",
        default=[],
        help="Pilot/input JSONL to exclude by dataset+DOI; may be supplied multiple times",
    )
    parser.add_argument(
        "--omit-fulltext-packet-content",
        action="store_true",
        help="Write packet summaries instead of embedding full full-text packet content",
    )
    parser.add_argument(
        "--include-irrelevant-controls",
        action="store_true",
        help="Include old abstract-irrelevant DOI records as calibration controls; disabled by default for extraction runs",
    )
    parser.add_argument(
        "--exclude-meta-analyses",
        action="store_true",
        help="Exclude metadata/abstract-detected meta-analyses/mega-analyses from this extraction build and park them for a future synthesis schema",
    )
    args = parser.parse_args()

    selected_datasets = dataset_names(args.dataset)
    manifest_path = Path(args.manifest).resolve()
    all_records = []
    dataset_summaries = []
    for dataset in selected_datasets:
        cfg = DATASET_CONFIG[dataset]
        records, summary = build_dataset_records(
            dataset,
            candidate_jsonl=default_candidate_jsonl(dataset),
            fulltext_packets_jsonl=fulltext_packets_path_for_dataset(args, dataset),
            paper_library=cfg["paper_db_json"],
            manifest_path=manifest_path,
            include_packet_content=not args.omit_fulltext_packet_content,
            include_irrelevant_controls=args.include_irrelevant_controls,
        )
        all_records.extend(records)
        dataset_summaries.append(summary)

    exclude_paths = [Path(path).resolve() for path in args.exclude_jsonl]
    excluded = excluded_dataset_dois(exclude_paths)
    if excluded:
        all_records = [row for row in all_records if record_dataset_doi(row) not in excluded]

    metadata_excluded_records = []
    metadata_excluded_reasons = Counter()
    if args.exclude_meta_analyses:
        all_records, metadata_excluded_records, metadata_excluded_reasons = filter_excluded_metadata_records(
            all_records,
            exclude_meta_analyses=args.exclude_meta_analyses,
        )
    all_records = filter_input_tier(all_records, args.input_tier)

    bucket_order = ALL_BUCKET_ORDER if args.include_irrelevant_controls else DEFAULT_BUCKET_ORDER
    selected, selection_summary = select_per_bucket(
        all_records,
        per_bucket=args.per_bucket,
        limit_total=max(0, args.limit_total),
        bucket_order=bucket_order,
    )
    out_jsonl = Path(args.out_jsonl).resolve()
    out_csv = Path(args.out_csv).resolve()
    report_json = Path(args.report_json).resolve()
    excluded_jsonl = (
        Path(args.excluded_jsonl).resolve()
        if args.excluded_jsonl
        else out_jsonl.with_name(f"{out_jsonl.stem}.excluded.jsonl")
    )
    write_jsonl(out_jsonl, selected)
    write_csv(out_csv, selected)
    write_jsonl(excluded_jsonl, metadata_excluded_records)

    report = {
        "generated_at_utc": now_utc(),
        "schema_version": PILOT_SCHEMA_VERSION,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "status": "ok",
        "inputs": {
            "datasets": selected_datasets,
            "manifest": str(manifest_path),
            "per_bucket": args.per_bucket,
            "limit_total": max(0, args.limit_total),
            "input_tier": args.input_tier,
            "include_fulltext_packet_content": not args.omit_fulltext_packet_content,
            "include_irrelevant_controls": args.include_irrelevant_controls,
            "exclude_jsonl": [str(path) for path in exclude_paths],
            "excluded_dataset_dois": len(excluded),
            "exclude_meta_analyses": args.exclude_meta_analyses,
            "metadata_excluded_records": len(metadata_excluded_records),
            "metadata_excluded_reasons": dict(metadata_excluded_reasons),
            "metadata_excluded_by_dataset": dict(Counter(row.get("dataset", "") for row in metadata_excluded_records)),
            "metadata_excluded_by_bucket": dict(Counter(row.get("bucket", "") for row in metadata_excluded_records)),
        },
        "outputs": {
            "jsonl": str(out_jsonl),
            "csv": str(out_csv),
            "report_json": str(report_json),
            "excluded_jsonl": str(excluded_jsonl),
        },
        "datasets": dataset_summaries,
        "selection": selection_summary,
    }
    write_json(report_json, report)

    print(f"Datasets: {', '.join(selected_datasets)}")
    print(f"Selected records: {selection_summary['selected_records']}")
    print(f"Selected by bucket: {selection_summary['selected_by_bucket']}")
    print(f"JSONL: {out_jsonl}")
    print(f"CSV: {out_csv}")
    if metadata_excluded_records:
        print(f"Metadata-excluded records: {len(metadata_excluded_records)} -> {excluded_jsonl}")
    print(f"Report: {report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
