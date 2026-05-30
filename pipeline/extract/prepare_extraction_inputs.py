#!/usr/bin/env python3
"""Prepare extraction inputs from manifest-listed LLM screening reports.

This script sits between abstract screening/PDF extraction and frontier-LLM
evidence extraction. It creates DOI-level inputs that are deliberately separate
from legacy claim rows: screening decides whether a paper should be considered,
and the later extraction step decides which graph claims the paper supports.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

try:
    from pipeline.fulltext.build_llm_evidence_packets import best_extraction
    from pipeline.fulltext.convert_pdfs import DATASET_CONFIG, compact_text, doi_to_slug, load_json_array, load_json_object, normalize, normalize_doi
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.build_llm_evidence_packets import best_extraction
    from pipeline.fulltext.convert_pdfs import DATASET_CONFIG, compact_text, doi_to_slug, load_json_array, load_json_object, normalize, normalize_doi


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
FULLTEXT_DIR = PROCESSED_DIR / "fulltext"
DEFAULT_OUTPUT_DIR = PROCESSED_DIR / "extraction"
DEFAULT_MANIFEST = PROCESSED_DIR / "corpus_manifest.json"
DEFAULT_RELEVANCE = ["relevant", "uncertain"]
SCHEMA_VERSION = "extraction_input"
ROUTING_TAGS = {
    "clinical_outcome",
    "molecular_target",
    "molecular_pathway",
    "brain_system",
    "cognitive_behavioral",
    "safety",
    "subjective_experience",
    "pharmacokinetics_exposure",
    "intervention_context",
    "real_world_use_public_health",
    "bridge_clinical_mechanism",
    "uncertain",
}
ROUTING_TAG_ALIASES = {
    "pathway_biomarker": "molecular_pathway",
}

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
    "open_access_is_oa",
    "open_access_status",
    "best_pdf_url",
    "pdf_local_path",
    "pdf_download_status",
    "library_status",
    "abstract",
]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_lines(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def rows_by_doi(rows: Iterable[dict]) -> dict[str, dict]:
    out = {}
    for row in rows:
        doi = normalize_doi(row.get("study_doi", ""))
        if doi:
            out[doi] = row
    return out


def resolve_path(path: str, *, base_dir: Path = ROOT) -> Path:
    value = Path(path)
    return value if value.is_absolute() else base_dir / value


def row_doi(row: dict) -> str:
    flat = row.get("flat", {}) if isinstance(row.get("flat"), dict) else {}
    input_row = row.get("input_row", {}) if isinstance(row.get("input_row"), dict) else {}
    return normalize_doi(flat.get("study_doi", "")) or normalize_doi(input_row.get("study_doi", ""))


def row_relevance(row: dict) -> str:
    flat = row.get("flat", {}) if isinstance(row.get("flat"), dict) else {}
    adjudication = row.get("adjudication", {}) if isinstance(row.get("adjudication"), dict) else {}
    return normalize(flat.get("llm_relevance", "") or adjudication.get("relevance", "")).lower()


def row_flat_value(row: dict, key: str) -> object:
    flat = row.get("flat", {}) if isinstance(row.get("flat"), dict) else {}
    return flat.get(key, "")


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return normalize(value).lower() in {"1", "true", "yes", "y"}


def normalize_routing_tags(value: object) -> list[str]:
    if isinstance(value, str):
        raw_values = value.replace(",", "|").replace(";", "|").split("|")
    elif isinstance(value, list):
        raw_values = value
    else:
        raw_values = []
    out = []
    seen = set()
    for raw in raw_values:
        tag = normalize(raw).lower().replace("-", "_").replace(" ", "_")
        tag = ROUTING_TAG_ALIASES.get(tag, tag)
        if tag not in ROUTING_TAGS or tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
    return out


def row_routing_tags(row: dict) -> list[str]:
    adjudication = row.get("adjudication", {}) if isinstance(row.get("adjudication"), dict) else {}
    tags = normalize_routing_tags(adjudication.get("routing_tags", []))
    if tags:
        return tags
    flat = row.get("flat", {}) if isinstance(row.get("flat"), dict) else {}
    return normalize_routing_tags(flat.get("llm_routing_tags", ""))


def supported_contexts(row: dict) -> list[dict]:
    verification = row.get("verification", {}) if isinstance(row.get("verification"), dict) else {}
    adjudication = row.get("adjudication", {}) if isinstance(row.get("adjudication"), dict) else {}
    contexts = verification.get("verified_supported_contexts")
    if not isinstance(contexts, list) or not contexts:
        contexts = adjudication.get("supported_contexts")
    if not isinstance(contexts, list):
        return []
    out = []
    seen = set()
    for context in contexts:
        if not isinstance(context, dict):
            continue
        compact = {
            "compound": compact_text(context.get("compound", "")),
            "entity": compact_text(context.get("entity", "")),
            "supporting_quote": compact_text(context.get("supporting_quote", "")),
            "confidence": context.get("confidence", ""),
            "reason": compact_text(context.get("reason", "")),
        }
        key = json.dumps(compact, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        out.append(compact)
    return out


def screening_record(dataset: str, run_id: str, row: dict) -> dict:
    relevance = row_relevance(row)
    contexts = supported_contexts(row)
    routing_tags = row_routing_tags(row)
    return {
        "dataset": dataset,
        "run_id": run_id,
        "llm_relevance": relevance,
        "status": compact_text(row_flat_value(row, "status")),
        "quote_verified": truthy(row_flat_value(row, "quote_verified")),
        "semantic_auto_eligible": truthy(row_flat_value(row, "semantic_auto_eligible")),
        "download_queue_eligible": truthy(row_flat_value(row, "download_queue_eligible")),
        "llm_confidence": row_flat_value(row, "llm_confidence"),
        "llm_needs_targeted_qa": truthy(row_flat_value(row, "llm_needs_targeted_qa")),
        "validation_flags": compact_text(row_flat_value(row, "validation_flags")),
        "supporting_abstract_quote": compact_text(row_flat_value(row, "llm_supporting_abstract_quote")),
        "routing_tags": routing_tags,
        "supported_context_count": len(contexts),
        "supported_contexts": contexts,
    }


def legacy_batch_screening_inputs(dataset: str, batches: list[str]) -> list[dict]:
    return [
        {
            "run_id": batch,
            "path": str(PROCESSED_DIR / f"llm_abstract_screening_report_{dataset}.{batch}.json"),
            "source": "batches_arg",
        }
        for batch in batches
    ]


def manifest_screening_inputs(manifest_path: Path, dataset: str) -> list[dict]:
    manifest = load_json_object(manifest_path)
    datasets = manifest.get("datasets", {})
    if not isinstance(datasets, dict):
        raise ValueError(f"Manifest must contain a datasets object: {manifest_path}")
    dataset_config = datasets.get(dataset, {})
    if not isinstance(dataset_config, dict):
        return []
    raw_reports = dataset_config.get("screening_reports", [])
    if not isinstance(raw_reports, list):
        raise ValueError(f"Manifest dataset screening_reports must be a list: {manifest_path} [{dataset}]")

    out = []
    seen = set()
    for index, item in enumerate(raw_reports, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Manifest screening report entry must be an object: {manifest_path} [{dataset}] #{index}")
        if item.get("include", True) is False:
            continue
        path = normalize(item.get("path", ""))
        if not path:
            raise ValueError(f"Manifest screening report entry is missing path: {manifest_path} [{dataset}] #{index}")
        run_id = normalize(item.get("run_id", "")) or Path(path).stem
        key = (run_id, path)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "run_id": run_id,
                "path": str(resolve_path(path)),
                "source": "manifest",
                "manifest_path": str(manifest_path),
                "description": normalize(item.get("description", "")),
            }
        )
    return out


def validate_screening_inputs(screening_inputs_by_dataset: dict[str, list[dict]]) -> dict[str, dict]:
    """Validate manifest-listed screening reports before building extraction files."""
    summary = {}
    errors = []
    for dataset, screening_inputs in screening_inputs_by_dataset.items():
        dataset_summary = {"included_reports": len(screening_inputs), "paths": []}
        if not screening_inputs:
            errors.append(f"{dataset}: no included screening reports")
        for item in screening_inputs:
            run_id = normalize(item.get("run_id", ""))
            path = resolve_path(normalize(item.get("path", "")))
            dataset_summary["paths"].append(str(path))
            if not run_id:
                errors.append(f"{dataset}: screening report is missing run_id ({path})")
            if not path.exists():
                errors.append(f"{dataset}: missing screening report {path}")
                continue
            try:
                report = load_json_object(path)
            except json.JSONDecodeError as err:
                errors.append(f"{dataset}: invalid JSON in {path}: {err}")
                continue
            rows = report.get("rows", [])
            if not isinstance(rows, list):
                errors.append(f"{dataset}: screening report rows must be a list ({path})")
        summary[dataset] = dataset_summary
    if errors:
        raise ValueError("Corpus manifest validation failed:\n" + "\n".join(f"- {error}" for error in errors))
    return summary


def collect_screened_records(dataset: str, screening_inputs: list[dict], relevance_values: set[str]) -> tuple[dict[str, dict], dict]:
    candidates: dict[str, dict] = {}
    report_stats = {}
    for item in screening_inputs:
        run_id = normalize(item.get("run_id", ""))
        if not run_id:
            raise ValueError(f"Screening input is missing run_id for {dataset}: {item}")
        path = resolve_path(normalize(item.get("path", "")))
        if not path.exists():
            raise FileNotFoundError(f"Missing screening report: {path}")
        report = load_json_object(path)
        rows = report.get("rows", [])
        if not isinstance(rows, list):
            raise ValueError(f"Screening report rows must be a list: {path}")
        stats = {
            "path": str(path),
            "run_id": run_id,
            "source": normalize(item.get("source", "")),
            "description": normalize(item.get("description", "")),
            "rows": len(rows),
            "selected_rows": 0,
            "selected_unique_dois": 0,
            "by_relevance": Counter(),
        }
        run_dois = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            doi = row_doi(row)
            relevance = row_relevance(row)
            stats["by_relevance"][relevance] += 1
            if not doi or relevance not in relevance_values:
                continue
            stats["selected_rows"] += 1
            run_dois.add(doi)
            candidate = candidates.setdefault(
                doi,
                {
                    "study_doi": doi,
                    "dataset": dataset,
                    "screening_records": [],
                },
            )
            candidate["screening_records"].append(screening_record(dataset, run_id, row))
        stats["selected_unique_dois"] = len(run_dois)
        stats["by_relevance"] = dict(stats["by_relevance"])
        report_stats[run_id] = stats
    return candidates, report_stats


def best_relevance(records: list[dict]) -> str:
    values = {normalize(record.get("llm_relevance", "")).lower() for record in records}
    if "relevant" in values:
        return "relevant"
    if "uncertain" in values:
        return "uncertain"
    return sorted(values)[0] if values else ""


def text_metadata(row: dict) -> dict:
    return {field: compact_text(row.get(field, "")) for field in METADATA_FIELDS}


def artifact_status(dataset: str, doi: str) -> dict:
    artifact_path = FULLTEXT_DIR / dataset / f"{doi_to_slug(doi)}.json"
    status = {
        "fulltext_artifact_path": str(artifact_path) if artifact_path.exists() else "",
        "fulltext_ready": False,
        "fulltext_backend": "",
        "fulltext_char_count": 0,
        "fulltext_section_count": 0,
        "fulltext_status_reason": "missing_fulltext_artifact",
    }
    if not artifact_path.exists():
        return status
    try:
        artifact = load_json_object(artifact_path)
    except json.JSONDecodeError:
        status["fulltext_status_reason"] = "invalid_fulltext_artifact_json"
        return status
    extraction = best_extraction(artifact)
    char_count = int(artifact.get("best_char_count", 0) or 0)
    status.update(
        {
            "fulltext_backend": compact_text(artifact.get("best_backend", "")),
            "fulltext_char_count": char_count,
            "fulltext_section_count": int(artifact.get("best_section_count", 0) or 0),
        }
    )
    if extraction and char_count > 0:
        status["fulltext_ready"] = True
        status["fulltext_status_reason"] = "successful_fulltext_artifact"
    else:
        status["fulltext_status_reason"] = "fulltext_artifact_without_successful_extraction"
    return status


def readiness_status(row: dict, artifact: dict) -> str:
    if artifact.get("fulltext_ready"):
        return "full_text_ready"
    pdf_path = compact_text(row.get("pdf_local_path", ""))
    if pdf_path and Path(pdf_path).exists():
        return "local_pdf_needs_fulltext_conversion"
    if compact_text(row.get("abstract", "")):
        return "abstract_only_needs_pdf_access"
    return "missing_text_needs_metadata_or_pdf"


def build_candidate_record(dataset: str, doi: str, candidate: dict, paper_row: dict) -> dict:
    records = candidate.get("screening_records", [])
    artifact = artifact_status(dataset, doi)
    readiness = readiness_status(paper_row, artifact)
    run_ids = sorted({record.get("run_id", "") for record in records if record.get("run_id", "")})
    supported_context_count = sum(int(record.get("supported_context_count", 0) or 0) for record in records)
    routing_tags = sorted({tag for record in records for tag in normalize_routing_tags(record.get("routing_tags", []))})
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": now_utc(),
        "dataset": dataset,
        "study_doi": doi,
        "extraction_scope": "psychedelic_compound_x_target" if dataset == "mechanistic" else "psychedelic_compound_x_indication",
        "screening_summary": {
            "best_llm_relevance": best_relevance(records),
            "included_from_runs": run_ids,
            "screening_record_count": len(records),
            "has_quote_verified_screening_support": any(record.get("quote_verified") for record in records),
            "supported_context_count_from_abstract_screening": supported_context_count,
            "routing_tags": routing_tags,
        },
        "readiness": {
            "status": readiness,
            "extraction_input_tier": "full_text" if artifact.get("fulltext_ready") else "abstract",
            **artifact,
            "has_abstract": bool(compact_text(paper_row.get("abstract", ""))),
            "pdf_local_path": compact_text(paper_row.get("pdf_local_path", "")),
            "pdf_download_status": compact_text(paper_row.get("pdf_download_status", "")),
            "best_pdf_url": compact_text(paper_row.get("best_pdf_url", "")),
        },
        "paper_metadata": text_metadata(paper_row),
        "screening_records": records,
    }


def csv_row(record: dict) -> dict:
    metadata = record["paper_metadata"]
    readiness = record["readiness"]
    screening = record["screening_summary"]
    return {
        "study_doi": record["study_doi"],
        "dataset": record["dataset"],
        "extraction_scope": record["extraction_scope"],
        "best_llm_relevance": screening["best_llm_relevance"],
        "routing_tags": "|".join(screening.get("routing_tags", [])),
        "included_from_runs": "|".join(screening["included_from_runs"]),
        "screening_record_count": screening["screening_record_count"],
        "readiness_status": readiness["status"],
        "extraction_input_tier": readiness["extraction_input_tier"],
        "fulltext_ready": readiness["fulltext_ready"],
        "fulltext_artifact_path": readiness["fulltext_artifact_path"],
        "fulltext_char_count": readiness["fulltext_char_count"],
        "has_abstract": readiness["has_abstract"],
        "pdf_local_path": readiness["pdf_local_path"],
        "pdf_download_status": readiness["pdf_download_status"],
        "study_title": metadata["study_title"],
        "study_year": metadata["study_year"],
        "authors": metadata["authors"],
        "study_journal": metadata["study_journal"],
        "publication_type": metadata["publication_type"],
        "publication_date": metadata["publication_date"],
        "pmid": metadata["pmid"],
        "pmcid": metadata["pmcid"],
    }


def write_candidates(dataset: str, records: list[dict], output_dir: Path, queue_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    queue_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / f"{dataset}_extraction_candidates.jsonl"
    csv_path = output_dir / f"{dataset}_extraction_candidates.csv"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    fieldnames = list(csv_row(records[0]).keys()) if records else [
        "study_doi",
        "dataset",
        "extraction_scope",
        "best_llm_relevance",
        "routing_tags",
        "included_from_runs",
        "screening_record_count",
        "readiness_status",
        "extraction_input_tier",
        "fulltext_ready",
        "fulltext_artifact_path",
        "fulltext_char_count",
        "has_abstract",
        "pdf_local_path",
        "pdf_download_status",
        "study_title",
        "study_year",
        "authors",
        "study_journal",
        "publication_type",
        "publication_date",
        "pmid",
        "pmcid",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(csv_row(record))

    all_dois = [record["study_doi"] for record in records]
    fulltext_dois = [record["study_doi"] for record in records if record["readiness"]["status"] == "full_text_ready"]
    abstract_only_dois = [record["study_doi"] for record in records if record["readiness"]["status"] == "abstract_only_needs_pdf_access"]
    needs_text_dois = [
        record["study_doi"]
        for record in records
        if record["readiness"]["status"] in {"local_pdf_needs_fulltext_conversion", "missing_text_needs_metadata_or_pdf"}
    ]
    queue_paths = {
        "all_candidates": queue_dir / f"doi_queue.{dataset}.extraction_candidates.txt",
        "fulltext_ready": queue_dir / f"doi_queue.{dataset}.extraction_fulltext_ready.txt",
        "abstract_only": queue_dir / f"doi_queue.{dataset}.extraction_abstract_only.txt",
        "needs_text": queue_dir / f"doi_queue.{dataset}.extraction_needs_text.txt",
    }
    write_lines(queue_paths["all_candidates"], all_dois)
    write_lines(queue_paths["fulltext_ready"], fulltext_dois)
    write_lines(queue_paths["abstract_only"], abstract_only_dois)
    write_lines(queue_paths["needs_text"], needs_text_dois)
    return {
        "jsonl": str(jsonl_path),
        "csv": str(csv_path),
        "doi_queues": {key: str(path) for key, path in queue_paths.items()},
    }


def dataset_names(raw: str) -> list[str]:
    if raw == "all":
        return ["mechanistic", "disorder"]
    return [raw]


def build_dataset(dataset: str, screening_inputs: list[dict], relevance_values: set[str], output_dir: Path, queue_dir: Path) -> dict:
    if not screening_inputs:
        raise ValueError(f"No screening reports configured for dataset: {dataset}")
    candidates, report_stats = collect_screened_records(dataset, screening_inputs, relevance_values)
    paper_rows = rows_by_doi(load_json_array(DATASET_CONFIG[dataset]["paper_db_json"]))
    missing_paper_library_rows = []
    records = []
    for doi in sorted(candidates):
        paper_row = paper_rows.get(doi, {})
        if not paper_row:
            missing_paper_library_rows.append(doi)
            paper_row = {"study_doi": doi}
        records.append(build_candidate_record(dataset, doi, candidates[doi], paper_row))

    outputs = write_candidates(dataset, records, output_dir=output_dir, queue_dir=queue_dir)
    readiness_counts = Counter(record["readiness"]["status"] for record in records)
    relevance_counts = Counter(record["screening_summary"]["best_llm_relevance"] for record in records)
    routing_tag_counts = Counter(tag for record in records for tag in record["screening_summary"].get("routing_tags", []))
    run_counts = Counter(run_id for record in records for run_id in record["screening_summary"]["included_from_runs"])
    duplicate_across_runs = sum(1 for record in records if len(record["screening_summary"]["included_from_runs"]) > 1)
    pdf_status_counts = Counter(record["readiness"]["pdf_download_status"] for record in records)
    summary = {
        "dataset": dataset,
        "selected_unique_dois": len(records),
        "by_best_llm_relevance": dict(relevance_counts),
        "by_routing_tag": dict(routing_tag_counts),
        "by_readiness_status": dict(readiness_counts),
        "selected_dois_by_run_membership": dict(run_counts),
        "dois_seen_in_multiple_runs": duplicate_across_runs,
        "missing_paper_library_rows": len(missing_paper_library_rows),
        "pdf_download_status": dict(pdf_status_counts),
    }
    return {
        "dataset": dataset,
        "inputs": {
            "screening_reports": report_stats,
            "paper_library": str(DATASET_CONFIG[dataset]["paper_db_json"]),
            "relevance_values_included": sorted(relevance_values),
        },
        "outputs": outputs,
        "summary": summary,
        "missing_paper_library_dois": missing_paper_library_rows[:200],
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Extraction Readiness",
        "",
        f"Generated: `{report['generated_at_utc']}`",
        "",
        "This report combines papers marked `relevant` or `uncertain` by LLM abstract screening across the screening reports included in the corpus manifest. Each DOI appears once per dataset. Final graph claims are not taken from these files; they will be extracted from the paper text in the next stage.",
        "",
    ]
    for dataset_report in report["datasets"]:
        summary = dataset_report["summary"]
        lines.extend(
            [
                f"## {summary['dataset'].title()}",
                "",
                f"- Candidate papers: `{summary['selected_unique_dois']}`",
                f"- Relevance: `{summary['by_best_llm_relevance']}`",
                f"- Routing tags: `{summary.get('by_routing_tag', {})}`",
                f"- Readiness: `{summary['by_readiness_status']}`",
                f"- Seen in multiple included runs: `{summary['dois_seen_in_multiple_runs']}`",
                "",
                "Outputs:",
                f"- Candidates JSONL: `{dataset_report['outputs']['jsonl']}`",
                f"- Candidates CSV: `{dataset_report['outputs']['csv']}`",
                f"- Full-text-ready DOI queue: `{dataset_report['outputs']['doi_queues']['fulltext_ready']}`",
                f"- Abstract-only DOI queue: `{dataset_report['outputs']['doi_queues']['abstract_only']}`",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare extraction candidate files from manifest-listed screening reports")
    parser.add_argument("--dataset", choices=["all", "mechanistic", "disorder"], default="all")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Corpus manifest listing screening reports to include")
    parser.add_argument(
        "--batches",
        nargs="+",
        default=None,
        help="Compatibility override: report labels under data/processed/llm_abstract_screening_report_<dataset>.<label>.json",
    )
    parser.add_argument("--relevance", nargs="+", default=DEFAULT_RELEVANCE, help="LLM relevance labels to include")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--queue-dir", default=str(RAW_DIR))
    parser.add_argument("--report-json", default="")
    parser.add_argument("--report-md", default="")
    parser.add_argument("--validate-manifest-only", action="store_true", help="Validate included manifest reports and exit")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    queue_dir = Path(args.queue_dir).resolve()
    relevance_values = {normalize(value).lower() for value in args.relevance if normalize(value)}
    if not relevance_values:
        raise SystemExit("At least one --relevance value is required")

    selected_datasets = dataset_names(args.dataset)
    manifest_path = Path(args.manifest).resolve()
    if args.batches:
        screening_inputs_by_dataset = {dataset: legacy_batch_screening_inputs(dataset, args.batches) for dataset in selected_datasets}
        manifest_input = None
    else:
        if not manifest_path.exists():
            raise SystemExit(f"Manifest not found: {manifest_path}. Create it or pass --batches explicitly.")
        screening_inputs_by_dataset = {dataset: manifest_screening_inputs(manifest_path, dataset) for dataset in selected_datasets}
        manifest_input = str(manifest_path)

    try:
        validation_summary = validate_screening_inputs(screening_inputs_by_dataset)
    except ValueError as err:
        raise SystemExit(str(err))
    if args.validate_manifest_only:
        for dataset, item in validation_summary.items():
            print(f"{dataset}: {item['included_reports']} included screening report(s)")
        return 0

    dataset_reports = [
        build_dataset(
            dataset,
            screening_inputs=screening_inputs_by_dataset[dataset],
            relevance_values=relevance_values,
            output_dir=output_dir,
            queue_dir=queue_dir,
        )
        for dataset in selected_datasets
    ]
    report = {
        "generated_at_utc": now_utc(),
        "schema_version": SCHEMA_VERSION,
        "status": "ok",
        "inputs": {
            "manifest": manifest_input,
            "batches_override": args.batches or [],
        },
        "datasets": dataset_reports,
    }
    report_json = Path(args.report_json).resolve() if args.report_json else output_dir / "extraction_readiness_report.json"
    report_md = Path(args.report_md).resolve() if args.report_md else output_dir / "extraction_readiness_report.md"
    write_json(report_json, report)
    report_md.parent.mkdir(parents=True, exist_ok=True)
    report_md.write_text(render_markdown(report) + "\n", encoding="utf-8")

    for dataset_report in dataset_reports:
        summary = dataset_report["summary"]
        print(f"Dataset: {summary['dataset']}")
        print(f"Candidate papers: {summary['selected_unique_dois']}")
        print(f"Relevance: {summary['by_best_llm_relevance']}")
        print(f"Readiness: {summary['by_readiness_status']}")
        print(f"Candidates JSONL: {dataset_report['outputs']['jsonl']}")
        print(f"Full-text-ready queue: {dataset_report['outputs']['doi_queues']['fulltext_ready']}")
        print(f"Abstract-only queue: {dataset_report['outputs']['doi_queues']['abstract_only']}")
    print(f"Report JSON: {report_json}")
    print(f"Report Markdown: {report_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
