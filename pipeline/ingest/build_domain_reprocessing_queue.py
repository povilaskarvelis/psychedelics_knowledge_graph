#!/usr/bin/env python3
"""Build screening queues for rediscovered DOIs that need domain reprocessing.

The DOI gate deduplicates bibliographic records, but a known DOI may not have
been screened or extracted for a newly added evidence domain. This script reads
rediscovered DOI rows from a discovery run, checks existing screening reports
for current-domain routing coverage, and writes queues for rediscovered papers
that should re-enter screening without duplicating the paper library.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
DEFAULT_CORPUS_MANIFEST = PROCESSED_DIR / "corpus_manifest.json"
VERSION = "0.1"

DATASETS = ("mechanistic", "disorder")
RELEVANT_VALUES = {"relevant", "uncertain"}
ROUTING_TAG_ALIASES = {
    "pathway_biomarker": "molecular_pathway",
}
MODULE_SCOPE_ROUTING_TAGS = {
    "molecular_target": {"molecular_target"},
    "molecular_pathway": {"molecular_pathway"},
    "systems_neuroscience": {"brain_system", "cognitive_behavioral", "bridge_clinical_mechanism"},
    "clinical_indication": {"clinical_outcome"},
    "clinical_symptom_function": {"clinical_outcome", "cognitive_behavioral", "bridge_clinical_mechanism"},
    "clinical_safety": {"safety", "clinical_outcome"},
    "subjective_experience": {"subjective_experience"},
    "pharmacokinetics_exposure": {"pharmacokinetics_exposure"},
    "intervention_context": {"intervention_context", "clinical_outcome"},
    "real_world_use_public_health": {"real_world_use_public_health", "safety"},
    "bridge_clinical_mechanism": {
        "bridge_clinical_mechanism",
        "brain_system",
        "cognitive_behavioral",
        "molecular_pathway",
        "clinical_outcome",
    },
}

PAPER_METADATA_FIELDS = [
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

DETAIL_FIELDS = [
    "doi",
    "decision",
    "ready_for_screening",
    "metadata_source",
    "has_abstract",
    "study_title",
    "study_year",
    "previous_relevance",
    "previous_routing_tags",
    "previous_reports",
    "existing_sources",
]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value: object) -> str:
    return "" if value is None else str(value).strip()


def normalize_doi(raw: object) -> str:
    text = normalize(raw)
    if not text:
        return ""
    lowered = text.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip().lower()


def normalize_tag(raw: object) -> str:
    tag = normalize(raw).lower().replace("-", "_").replace(" ", "_")
    return ROUTING_TAG_ALIASES.get(tag, tag)


def parse_csv_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def parse_tags(raw_tags: object) -> set[str]:
    if isinstance(raw_tags, str):
        values = re.split(r"[|,;]\s*", raw_tags)
    elif isinstance(raw_tags, list):
        values = raw_tags
    else:
        values = []
    return {tag for value in values if (tag := normalize_tag(value))}


def module_scopes_to_tags(scopes: Iterable[str]) -> set[str]:
    tags: set[str] = set()
    unknown = []
    for scope in scopes:
        normalized = normalize_tag(scope)
        scope_tags = MODULE_SCOPE_ROUTING_TAGS.get(normalized)
        if scope_tags is None:
            unknown.append(scope)
            continue
        tags.update(scope_tags)
    if unknown:
        available = ", ".join(sorted(MODULE_SCOPE_ROUTING_TAGS))
        raise ValueError(f"Unknown module scope(s): {', '.join(unknown)}. Available: {available}")
    return tags


def read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def json_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = read_json(path)
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("records", "rows", "entries", "results"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def read_rediscovered_rows(paths: Iterable[Path]) -> list[dict]:
    rows = []
    seen = set()
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Rediscovered DOI CSV not found: {path}")
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                doi = normalize_doi(row.get("doi", ""))
                if not doi or doi in seen:
                    continue
                seen.add(doi)
                item = dict(row)
                item["doi"] = doi
                rows.append(item)
    return rows


def row_doi(row: dict) -> str:
    flat = row.get("flat", {}) if isinstance(row.get("flat"), dict) else {}
    input_row = row.get("input_row", {}) if isinstance(row.get("input_row"), dict) else {}
    return normalize_doi(flat.get("study_doi", "") or input_row.get("study_doi", "") or row.get("study_doi", ""))


def row_relevance(row: dict) -> str:
    flat = row.get("flat", {}) if isinstance(row.get("flat"), dict) else {}
    adjudication = row.get("adjudication", {}) if isinstance(row.get("adjudication"), dict) else {}
    return normalize(flat.get("llm_relevance", "") or adjudication.get("relevance", "")).lower()


def row_routing_tags(row: dict) -> set[str]:
    flat = row.get("flat", {}) if isinstance(row.get("flat"), dict) else {}
    adjudication = row.get("adjudication", {}) if isinstance(row.get("adjudication"), dict) else {}
    tags = parse_tags(adjudication.get("routing_tags", []))
    if not tags:
        tags = parse_tags(flat.get("llm_routing_tags", ""))
    return tags


def manifest_screening_reports(manifest_path: Path, dataset: str) -> list[dict]:
    if not manifest_path.exists():
        return []
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        return []
    dataset_config = manifest.get("datasets", {}).get(dataset, {})
    if not isinstance(dataset_config, dict):
        return []
    reports = []
    for item in dataset_config.get("screening_reports", []):
        if not isinstance(item, dict) or item.get("include", True) is False:
            continue
        path = normalize(item.get("path", ""))
        if not path:
            continue
        report_path = Path(path)
        if not report_path.is_absolute():
            report_path = ROOT / report_path
        reports.append(
            {
                "run_id": normalize(item.get("run_id", "")) or report_path.stem,
                "path": report_path,
            }
        )
    return reports


def screening_index(reports: list[dict]) -> tuple[dict[str, list[dict]], dict]:
    by_doi: dict[str, list[dict]] = defaultdict(list)
    report_stats = []
    for report in reports:
        path = Path(report["path"])
        if not path.exists():
            report_stats.append({"run_id": report.get("run_id", ""), "path": str(path), "exists": False, "rows": 0})
            continue
        payload = read_json(path)
        rows = payload.get("rows", []) if isinstance(payload, dict) else []
        rows = rows if isinstance(rows, list) else []
        report_stats.append({"run_id": report.get("run_id", ""), "path": str(path), "exists": True, "rows": len(rows)})
        for row in rows:
            if not isinstance(row, dict):
                continue
            doi = row_doi(row)
            if not doi:
                continue
            by_doi[doi].append(
                {
                    "run_id": report.get("run_id", ""),
                    "relevance": row_relevance(row),
                    "routing_tags": sorted(row_routing_tags(row)),
                }
            )
    return by_doi, {"reports": report_stats, "indexed_dois": len(by_doi)}


def paper_row_from_candidate(record: dict) -> dict:
    metadata = record.get("metadata", {}) if isinstance(record.get("metadata"), dict) else {}
    row = dict(metadata)
    doi = normalize_doi(record.get("doi", "") or row.get("study_doi", ""))
    row["study_doi"] = doi
    for field in ("study_title", "study_year", "authors"):
        if not normalize(row.get(field, "")):
            row[field] = normalize(record.get(field, ""))
    if not normalize(row.get("pdf_local_path", "")):
        local_paths = record.get("local_pdf_paths")
        if isinstance(local_paths, list) and local_paths:
            row["pdf_local_path"] = normalize(local_paths[0])
    if not normalize(row.get("library_status", "")):
        row["library_status"] = "candidate_corpus"
    return row


def paper_indexes(
    dataset: str,
    extra_paper_db_jsons: Iterable[Path] = (),
    *,
    include_default_sources: bool = True,
) -> tuple[dict[str, tuple[str, dict]], dict]:
    sources: list[tuple[str, Path, bool]] = []
    if include_default_sources:
        target_path = PROCESSED_DIR / f"paper_library_{dataset}.json"
        sources.append((f"{dataset}:paper_library", target_path, False))
        for other in DATASETS:
            if other != dataset:
                sources.append((f"{other}:paper_library", PROCESSED_DIR / f"paper_library_{other}.json", False))
    for path in extra_paper_db_jsons:
        sources.append((f"extra:{path.name}", path, False))

    out: dict[str, tuple[str, dict]] = {}
    source_counts = Counter()
    for source_name, path, _ in sources:
        for row in json_rows(path):
            doi = normalize_doi(row.get("study_doi", "") or row.get("doi", ""))
            if not doi or doi in out:
                continue
            out[doi] = (source_name, row)
            source_counts[source_name] += 1

    if include_default_sources:
        candidate_path = PROCESSED_DIR / "candidate_paper_corpus.json"
        candidate_rows = json_rows(candidate_path)
        candidate_count = 0
        for record in candidate_rows:
            doi = normalize_doi(record.get("doi", "") or record.get("study_doi", ""))
            if not doi or doi in out:
                continue
            out[doi] = ("candidate_paper_corpus", paper_row_from_candidate(record))
            candidate_count += 1
        if candidate_count:
            source_counts["candidate_paper_corpus"] = candidate_count

    return out, {"sources": dict(source_counts), "indexed_dois": len(out)}


def queue_row_from_paper(row: dict) -> dict:
    return {
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "compound": "",
        "entity": "",
        "study_title": normalize(row.get("study_title", "")),
        "study_year": normalize(row.get("study_year", "")),
        "authors": normalize(row.get("authors", "")),
    }


def write_doi_queue(path: Path, rows: list[dict], description: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# {description} generated at {now_utc()}\n")
        handle.write("# doi,compound,target_or_disorder,optional_study_title,optional_study_year,optional_authors\n")
        writer = csv.writer(handle)
        for row in rows:
            writer.writerow(
                [
                    normalize_doi(row.get("study_doi", "")),
                    normalize(row.get("compound", "")),
                    normalize(row.get("entity", "")),
                    normalize(row.get("study_title", "")),
                    normalize(row.get("study_year", "")),
                    normalize(row.get("authors", "")),
                ]
            )
    return len(rows)


def compact_paper_row(row: dict) -> dict:
    out = dict(row)
    doi = normalize_doi(out.get("study_doi", "") or out.get("doi", ""))
    out["study_doi"] = doi
    for field in PAPER_METADATA_FIELDS:
        out.setdefault(field, "")
    return out


def domain_covered(previous: list[dict], target_tags: set[str]) -> bool:
    for item in previous:
        if item.get("relevance") not in RELEVANT_VALUES:
            continue
        if set(item.get("routing_tags", [])) & target_tags:
            return True
    return False


def summarize_previous(previous: list[dict]) -> tuple[str, str, str]:
    relevances = sorted({normalize(item.get("relevance", "")) for item in previous if normalize(item.get("relevance", ""))})
    tags = sorted({tag for item in previous for tag in item.get("routing_tags", [])})
    reports = sorted({normalize(item.get("run_id", "")) for item in previous if normalize(item.get("run_id", ""))})
    return "|".join(relevances), "|".join(tags), "|".join(reports)


def build_domain_reprocessing_queue(
    *,
    dataset: str,
    rediscovered_csvs: list[Path],
    target_tags: set[str],
    output_dir: Path,
    corpus_manifest: Path = DEFAULT_CORPUS_MANIFEST,
    extra_screening_reports: list[Path] | None = None,
    extra_paper_db_jsons: list[Path] | None = None,
    include_default_paper_sources: bool = True,
    output_label: str = "rediscovered_domain_reprocess",
) -> dict:
    if dataset not in DATASETS:
        raise ValueError(f"Unknown dataset: {dataset}")
    if not target_tags:
        raise ValueError("At least one target routing tag is required")
    output_dir.mkdir(parents=True, exist_ok=True)

    rediscovered_rows = read_rediscovered_rows(rediscovered_csvs)
    reports = manifest_screening_reports(corpus_manifest, dataset)
    for path in extra_screening_reports or []:
        reports.append({"run_id": path.stem, "path": path})
    screened_by_doi, screening_stats = screening_index(reports)
    papers_by_doi, paper_stats = paper_indexes(
        dataset,
        extra_paper_db_jsons or [],
        include_default_sources=include_default_paper_sources,
    )

    detail_rows = []
    ready_queue_rows = []
    metadata_queue_rows = []
    paper_db_rows = []
    counts = Counter()
    metadata_source_counts = Counter()
    previous_relevance_counts = Counter()

    for rediscovered in rediscovered_rows:
        doi = normalize_doi(rediscovered.get("doi", ""))
        previous = screened_by_doi.get(doi, [])
        previous_relevance, previous_tags, previous_reports = summarize_previous(previous)
        if domain_covered(previous, target_tags):
            decision = "already_domain_screened"
            ready = False
            counts[decision] += 1
        else:
            source_row = papers_by_doi.get(doi)
            if source_row is None:
                decision = "needs_metadata_or_abstract"
                ready = False
                metadata_source = ""
                paper_row = {
                    "study_doi": doi,
                    "study_title": normalize(rediscovered.get("title", "")),
                    "study_year": normalize(rediscovered.get("year", "")),
                    "authors": normalize(rediscovered.get("authors", "")),
                }
            else:
                metadata_source, source = source_row
                paper_row = compact_paper_row(source)
                if not normalize(paper_row.get("abstract", "")):
                    decision = "needs_metadata_or_abstract"
                    ready = False
                else:
                    decision = "ready_for_domain_screening"
                    ready = True
                    ready_queue_rows.append(queue_row_from_paper(paper_row))
                    paper_db_rows.append(paper_row)
                    metadata_source_counts[metadata_source] += 1
            if decision == "needs_metadata_or_abstract":
                metadata_queue_rows.append(queue_row_from_paper(paper_row))
            counts[decision] += 1
            if previous_relevance:
                previous_relevance_counts[previous_relevance] += 1

        source_row = papers_by_doi.get(doi)
        metadata_source = source_row[0] if source_row else ""
        source = source_row[1] if source_row else {}
        detail_rows.append(
            {
                "doi": doi,
                "decision": decision,
                "ready_for_screening": ready,
                "metadata_source": metadata_source,
                "has_abstract": bool(normalize(source.get("abstract", ""))),
                "study_title": normalize(source.get("study_title", "") or rediscovered.get("title", "")),
                "study_year": normalize(source.get("study_year", "") or rediscovered.get("year", "")),
                "previous_relevance": previous_relevance,
                "previous_routing_tags": previous_tags,
                "previous_reports": previous_reports,
                "existing_sources": normalize(rediscovered.get("existing_sources", "")),
            }
        )

    queue_path = output_dir / f"doi_queue.{dataset}.{output_label}.ready_for_screening.txt"
    metadata_queue_path = output_dir / f"doi_queue.{dataset}.{output_label}.needs_metadata_or_abstract.txt"
    paper_db_path = output_dir / f"paper_library_{dataset}.{output_label}.json"
    detail_csv_path = output_dir / f"{dataset}_{output_label}_details.csv"
    report_path = output_dir / f"{dataset}_{output_label}_report.json"

    write_doi_queue(queue_path, ready_queue_rows, f"Domain reprocessing DOI queue for {dataset}")
    write_doi_queue(metadata_queue_path, metadata_queue_rows, f"Rediscovered DOI queue needing metadata or abstract for {dataset}")
    write_json(paper_db_path, paper_db_rows)
    write_csv(detail_csv_path, detail_rows, DETAIL_FIELDS)

    report = {
        "version": VERSION,
        "generated_at_utc": now_utc(),
        "dataset": dataset,
        "target_routing_tags": sorted(target_tags),
        "inputs": {
            "rediscovered_csvs": [str(path) for path in rediscovered_csvs],
            "corpus_manifest": str(corpus_manifest),
            "extra_screening_reports": [str(path) for path in extra_screening_reports or []],
            "extra_paper_db_jsons": [str(path) for path in extra_paper_db_jsons or []],
        },
        "outputs": {
            "ready_for_screening_queue": str(queue_path),
            "needs_metadata_or_abstract_queue": str(metadata_queue_path),
            "screening_paper_db_json": str(paper_db_path),
            "details_csv": str(detail_csv_path),
            "report_json": str(report_path),
        },
        "counts": {
            "rediscovered_unique_dois": len(rediscovered_rows),
            "already_domain_screened": counts["already_domain_screened"],
            "needs_domain_reprocessing": counts["ready_for_domain_screening"] + counts["needs_metadata_or_abstract"],
            "ready_for_domain_screening": counts["ready_for_domain_screening"],
            "needs_metadata_or_abstract": counts["needs_metadata_or_abstract"],
        },
        "ready_metadata_source_counts": dict(sorted(metadata_source_counts.items())),
        "previous_relevance_counts_for_reprocess": dict(sorted(previous_relevance_counts.items())),
        "screening_index": screening_stats,
        "paper_index": paper_stats,
    }
    write_json(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a domain-aware reprocessing queue for rediscovered DOIs")
    parser.add_argument("--dataset", choices=DATASETS, required=True)
    parser.add_argument(
        "--rediscovered-csv",
        action="append",
        required=True,
        help="Rediscovered DOI CSV from add_new_dois.py. Can be supplied more than once.",
    )
    parser.add_argument(
        "--module-scopes",
        default="",
        help="Comma-separated module scopes used to derive target routing tags, e.g. systems_neuroscience.",
    )
    parser.add_argument(
        "--routing-tags",
        default="",
        help="Comma-separated routing tags to use directly or in addition to --module-scopes.",
    )
    parser.add_argument("--corpus-manifest", default=str(DEFAULT_CORPUS_MANIFEST))
    parser.add_argument("--extra-screening-report", action="append", default=[])
    parser.add_argument("--extra-paper-db-json", action="append", default=[])
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output-label", default="rediscovered_domain_reprocess")
    args = parser.parse_args()

    target_tags = set()
    if args.module_scopes:
        target_tags.update(module_scopes_to_tags(parse_csv_list(args.module_scopes)))
    if args.routing_tags:
        target_tags.update(normalize_tag(tag) for tag in parse_csv_list(args.routing_tags))
    if not target_tags:
        raise SystemExit("Supply --module-scopes, --routing-tags, or both")

    report = build_domain_reprocessing_queue(
        dataset=args.dataset,
        rediscovered_csvs=[Path(path).resolve() for path in args.rediscovered_csv],
        target_tags=target_tags,
        output_dir=Path(args.output_dir).resolve(),
        corpus_manifest=Path(args.corpus_manifest).resolve(),
        extra_screening_reports=[Path(path).resolve() for path in args.extra_screening_report],
        extra_paper_db_jsons=[Path(path).resolve() for path in args.extra_paper_db_json],
        output_label=args.output_label,
    )

    counts = report["counts"]
    print(f"Dataset: {args.dataset}")
    print(f"Target routing tags: {', '.join(report['target_routing_tags'])}")
    print(f"Rediscovered unique DOIs: {counts['rediscovered_unique_dois']}")
    print(f"Already domain-screened: {counts['already_domain_screened']}")
    print(f"Needs domain reprocessing: {counts['needs_domain_reprocessing']}")
    print(f"Ready for screening: {counts['ready_for_domain_screening']}")
    print(f"Needs metadata or abstract: {counts['needs_metadata_or_abstract']}")
    print(f"Ready queue: {report['outputs']['ready_for_screening_queue']}")
    print(f"Screening paper DB: {report['outputs']['screening_paper_db_json']}")
    print(f"Report: {report['outputs']['report_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
