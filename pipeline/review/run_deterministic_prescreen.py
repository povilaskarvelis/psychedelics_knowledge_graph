#!/usr/bin/env python3
"""Run deterministic title/abstract pre-screening on the unified corpus tables."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import hashlib
from pathlib import Path
import re
import sys
from typing import Iterable

import pandas as pd

try:
    from pipeline.review.run_local_llm_abstract_screening import (
        deterministic_prescreen_decision,
        normalize_doi,
        normalize_routing_tags,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.review.run_local_llm_abstract_screening import (
        deterministic_prescreen_decision,
        normalize_doi,
        normalize_routing_tags,
    )


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS_DIR = ROOT / "data" / "processed" / "corpus"
DEFAULT_PAPERS_TABLE = DEFAULT_CORPUS_DIR / "candidate_papers.parquet"
DEFAULT_METADATA_TABLE = DEFAULT_CORPUS_DIR / "paper_metadata_enrichment.parquet"
DEFAULT_CONTEXTS_TABLE = DEFAULT_CORPUS_DIR / "candidate_contexts.parquet"
DEFAULT_DECISIONS_TABLE = DEFAULT_CORPUS_DIR / "paper_prescreen_decisions.parquet"
DEFAULT_SUMMARY_TABLE = DEFAULT_CORPUS_DIR / "paper_prescreen_summary.parquet"
TABLE_VERSION = "0.1"
DATASETS = ("mechanistic", "disorder")

METADATA_FIELDS = [
    "study_title",
    "study_year",
    "authors",
    "abstract",
    "study_journal",
    "publication_type",
    "publication_date",
    "pmid",
    "pmcid",
    "openalex_id",
    "semantic_scholar_id",
    "trial_registry_ids",
    "mesh_terms",
    "keywords",
    "publisher",
    "language",
    "metadata_enrichment_status",
    "metadata_enrichment_run_id",
]

NON_PAPER_CONTAINER_PUBLICATION_TYPES = {
    "component",
    "journal",
    "journal-issue",
    "journal-volume",
    "paratext",
    "proceedings-series",
    "report-component",
}
NON_EVIDENCE_TITLE_PATTERNS = (
    re.compile(r"\bauthor correction\b", re.IGNORECASE),
    re.compile(r"\bcorrection:\b", re.IGNORECASE),
    re.compile(r"\berratum\b", re.IGNORECASE),
    re.compile(r"\bcorrigendum\b", re.IGNORECASE),
    re.compile(r"\bdecision letter for\b", re.IGNORECASE),
    re.compile(r"\breview for [\"“]", re.IGNORECASE),
    re.compile(r"\bfaculty opinions recommendation\b", re.IGNORECASE),
    re.compile(r"\bsupplementary material for\b", re.IGNORECASE),
    re.compile(r"\bstudy protocol\b", re.IGNORECASE),
    re.compile(r"\btrial protocol\b", re.IGNORECASE),
    re.compile(r"\bprotocol for\b", re.IGNORECASE),
    re.compile(r"\bstudy flow chart\b", re.IGNORECASE),
    re.compile(r"\bconsort diagram\b", re.IGNORECASE),
    re.compile(r"\bstudy-related adverse events\b", re.IGNORECASE),
    re.compile(r"\bsupporting information\b", re.IGNORECASE),
    re.compile(r"\bsupplementary information\b", re.IGNORECASE),
    re.compile(r"\bsupplemental information\b", re.IGNORECASE),
    re.compile(r"\bprism file\b", re.IGNORECASE),
)
NON_EVIDENCE_PUBLICATION_PATTERNS = (
    re.compile(r"\bpublished erratum\b", re.IGNORECASE),
    re.compile(r"\berratum\b", re.IGNORECASE),
    re.compile(r"\bretracted publication\b", re.IGNORECASE),
    re.compile(r"\bretraction\b", re.IGNORECASE),
    re.compile(r"\bclinical trial protocol\b", re.IGNORECASE),
)
NON_EVIDENCE_DOI_PATTERNS = (
    re.compile(r"^10\.1371/journal\.[^.]+\.\d+\.[fgst]\d+$", re.IGNORECASE),
    re.compile(r"^10\.1021/.+\.s\d+$", re.IGNORECASE),
    re.compile(r"^10\.6084/m9\.figshare", re.IGNORECASE),
)
PLACEHOLDER_ABSTRACTS = {
    "abstract not available",
    "international audience",
    "no abstract",
    "no abstract available",
    "not available",
}
CITATION_ONLY_ABSTRACT_PATTERNS = (
    re.compile(r"^\(\d{4}\)\.\s+.+\.\s+.+:\s+vol\.\s+\d+", re.IGNORECASE),
    re.compile(
        r"^[A-Z][A-Za-z& ]+:\s+[A-Za-z]+\s+\d{4}\s+-\s+Volume\s+\d+\s+-\s+Issue\b.*\bdoi\s*:",
        re.IGNORECASE,
    ),
)
CONTEXT_ENTITY_TYPE_TAGS = {
    "target": "molecular_target",
    "molecular_target": "molecular_target",
    "brain_region_or_network": "brain_system",
    "brain_system": "brain_system",
    "network": "brain_system",
    "circuit": "brain_system",
    "cognitive_behavioral_task": "cognitive_behavioral",
    "cognitive_behavioral": "cognitive_behavioral",
    "molecular_pathway": "molecular_pathway",
    "pathway": "molecular_pathway",
    "subjective_experience": "subjective_experience",
    "acute_subjective_effect": "subjective_experience",
    "pharmacokinetics_exposure": "pharmacokinetics_exposure",
    "pharmacokinetics": "pharmacokinetics_exposure",
    "exposure": "pharmacokinetics_exposure",
    "intervention_context": "intervention_context",
    "psychotherapy_context": "intervention_context",
    "real_world_use_public_health": "real_world_use_public_health",
    "public_health": "real_world_use_public_health",
    "naturalistic_use": "real_world_use_public_health",
    "clinical_symptom_function": "clinical_outcome",
    "clinical_safety": "safety",
    "clinical_mechanism_overlap": "bridge_clinical_mechanism",
    "indication": "clinical_outcome",
    "clinical": "clinical_outcome",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def default_run_id() -> str:
    return "deterministic_prescreen_" + dt.datetime.now(dt.timezone.utc).strftime("%Y_%m_%d")


def clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "nat"} else text


def clean_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = clean(value).lower()
    return text in {"1", "true", "yes", "y"}


def unusable_abstract_reason(value: object) -> str:
    text = re.sub(r"\s+", " ", clean(value)).strip()
    if not text:
        return "No abstract available for title/abstract screening."
    lowered = text.lower().strip(" .[]")
    if lowered in PLACEHOLDER_ABSTRACTS:
        return "Abstract field contains a placeholder rather than a substantive abstract."
    for pattern in CITATION_ONLY_ABSTRACT_PATTERNS:
        if pattern.search(text):
            return "Abstract field contains citation metadata rather than a substantive abstract."
    return ""


def split_values(value: object) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        raw_values = value
    else:
        raw_values = re.split(r"\s*[|,;]\s*", clean(value))
    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        text = clean(raw)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def join_values(values: Iterable[object]) -> str:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean(value)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return " | ".join(out)


def stable_id(*parts: object) -> str:
    payload = "\u241f".join(clean(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def read_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def write_table(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def read_doi_file(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"DOI file does not exist: {path}")
    dois: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        doi = normalize_doi(clean(line))
        if doi and not doi.startswith("#"):
            dois.add(doi)
    return dois


def scoped_dois_from_args(args: argparse.Namespace) -> set[str]:
    dois: set[str] = set()
    doi_file = clean(getattr(args, "doi_file", ""))
    if doi_file:
        dois.update(read_doi_file(Path(doi_file).resolve()))
    for value in getattr(args, "doi", []) or []:
        doi = normalize_doi(clean(value))
        if doi:
            dois.add(doi)
    return dois


def filter_table_to_dois(df: pd.DataFrame, dois: set[str]) -> pd.DataFrame:
    if df.empty or "doi" not in df.columns or not dois:
        return df
    doi_values = df["doi"].map(lambda value: normalize_doi(clean(value)))
    return df[doi_values.isin(dois)].copy()


def existing_run_id(decisions_df: pd.DataFrame) -> str:
    if decisions_df.empty or "run_id" not in decisions_df.columns:
        return ""
    run_ids = [clean(value) for value in decisions_df["run_id"].tolist()]
    run_ids = [value for value in run_ids if value]
    if not run_ids:
        return ""
    return Counter(run_ids).most_common(1)[0][0]


def merge_scoped_decisions(
    existing_rows: list[dict],
    updated_rows: list[dict],
    *,
    scoped_dois: set[str],
    datasets: Iterable[str],
) -> tuple[list[dict], int]:
    requested_datasets = set(datasets)
    retained_existing: list[dict] = []
    replaced = 0
    for row in existing_rows:
        doi = normalize_doi(clean(row.get("doi", "")))
        dataset = clean(row.get("dataset", ""))
        if doi in scoped_dois and dataset in requested_datasets:
            replaced += 1
            continue
        retained_existing.append(row)
    return [*retained_existing, *updated_rows], replaced


def rows_by_doi(df: pd.DataFrame) -> dict[str, dict]:
    if df.empty or "doi" not in df.columns:
        return {}
    out: dict[str, dict] = {}
    for row in df.to_dict("records"):
        doi = normalize_doi(clean(row.get("doi", "")))
        if doi and doi not in out:
            out[doi] = row
    return out


def datasets_for_paper(paper: dict, contexts: list[dict]) -> list[str]:
    values = set(split_values(paper.get("datasets", "")))
    values.update(clean(context.get("dataset", "")) for context in contexts)
    return [dataset for dataset in DATASETS if dataset in values]


def contexts_by_doi_and_dataset(contexts_df: pd.DataFrame) -> dict[tuple[str, str], list[dict]]:
    out: dict[tuple[str, str], list[dict]] = defaultdict(list)
    if contexts_df.empty or "doi" not in contexts_df.columns:
        return out
    for row in contexts_df.to_dict("records"):
        doi = normalize_doi(clean(row.get("doi", "")))
        dataset = clean(row.get("dataset", ""))
        if not doi or dataset not in DATASETS:
            continue
        out[(doi, dataset)].append(row)
    return out


def all_contexts_by_doi(contexts_by_dataset: dict[tuple[str, str], list[dict]]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for (doi, _dataset), rows in contexts_by_dataset.items():
        out[doi].extend(rows)
    return out


def compact_contexts(contexts: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for row in contexts:
        item = {
            "compound": clean(row.get("compound", "")),
            "entity": clean(row.get("entity", "")),
            "entity_type": clean(row.get("entity_type", "")),
        }
        marker = (item["compound"], item["entity"], item["entity_type"])
        if not item["compound"] and not item["entity"]:
            continue
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


def context_routing_tags(contexts: list[dict]) -> list[str]:
    tags: list[str] = []
    for context in contexts:
        entity_type = clean(context.get("entity_type", "")).lower().replace("-", "_").replace(" ", "_")
        tag = CONTEXT_ENTITY_TYPE_TAGS.get(entity_type)
        if tag:
            tags.append(tag)
    return normalize_routing_tags(tags)


def merged_screening_row(paper: dict, metadata: dict | None) -> dict:
    metadata = metadata or {}
    row = {"study_doi": normalize_doi(clean(paper.get("doi", "")))}
    for field in METADATA_FIELDS:
        row[field] = clean(metadata.get(field, "")) or clean(paper.get(field, ""))
    return row


def missing_abstract_decision(row: dict, contexts: list[dict], reason: str = "") -> dict:
    return {
        "action": "exclude_missing_abstract",
        "confidence": 1.0,
        "supporting_quote": clean(row.get("abstract", "")) or clean(row.get("study_title", "")) or "not_found",
        "reason": reason or "No abstract available for title/abstract screening.",
        "matched_terms": [],
        "routing_tags": context_routing_tags(contexts),
    }


def non_paper_container_without_title_decision(row: dict, contexts: list[dict]) -> dict | None:
    title = clean(row.get("study_title", ""))
    if title:
        return None
    publication_types = {value.lower() for value in split_values(row.get("publication_type", ""))}
    if not publication_types.intersection(NON_PAPER_CONTAINER_PUBLICATION_TYPES):
        return None
    publication_type = join_values(sorted(publication_types))
    return {
        "action": "exclude_non_paper_container",
        "confidence": 1.0,
        "supporting_quote": publication_type or "no paper title",
        "reason": (
            "Metadata identifies this DOI as a journal/container record rather than a titled source paper, "
            "and no paper title is available."
        ),
        "matched_terms": sorted(publication_types),
        "routing_tags": context_routing_tags(contexts),
    }


def non_evidence_artifact_decision(row: dict, contexts: list[dict]) -> dict | None:
    doi = normalize_doi(clean(row.get("study_doi", "")))
    title = clean(row.get("study_title", ""))
    publication_type = clean(row.get("publication_type", ""))
    matched_terms: list[str] = []
    for pattern in NON_EVIDENCE_DOI_PATTERNS:
        match = pattern.search(doi)
        if match:
            matched_terms.append(match.group(0))
    for pattern in NON_EVIDENCE_TITLE_PATTERNS:
        match = pattern.search(title)
        if match:
            matched_terms.append(match.group(0))
    for pattern in NON_EVIDENCE_PUBLICATION_PATTERNS:
        match = pattern.search(publication_type)
        if match:
            matched_terms.append(match.group(0))
    if not matched_terms:
        return None
    return {
        "action": "exclude_non_evidence_artifact",
        "confidence": 1.0,
        "supporting_quote": title or publication_type or doi,
        "reason": (
            "Record is a protocol, correction, review report, supplementary material, "
            "figure/table/data deposit, retraction, or citation artifact rather than source evidence."
        ),
        "matched_terms": matched_terms,
        "routing_tags": context_routing_tags(contexts),
    }


def final_prescreen_fields(decision: dict) -> tuple[str, str, str]:
    action = clean(decision.get("action", ""))
    if action.startswith("exclude"):
        return ("exclude", action, clean(decision.get("reason", "")))
    return ("retain", "retain_for_extraction_candidate", clean(decision.get("reason", "")))


def build_prescreen_decisions(
    papers_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    contexts_df: pd.DataFrame,
    *,
    run_id: str,
    generated_at_utc: str,
    datasets: Iterable[str] = DATASETS,
    exclude_missing_abstract: bool = True,
    progress_every: int = 0,
) -> list[dict]:
    requested_datasets = set(datasets)
    metadata_by_doi = rows_by_doi(metadata_df)
    contexts_lookup = contexts_by_doi_and_dataset(contexts_df)
    all_contexts_lookup = all_contexts_by_doi(contexts_lookup)
    rows: list[dict] = []

    paper_records = papers_df.to_dict("records")
    for paper_index, paper in enumerate(paper_records, start=1):
        if progress_every and paper_index % progress_every == 0:
            print(f"Processed {paper_index:,}/{len(paper_records):,} candidate papers...", flush=True)
        doi = normalize_doi(clean(paper.get("doi", "")))
        if not doi:
            continue
        paper_contexts = all_contexts_lookup.get(doi, [])
        paper_datasets = [dataset for dataset in datasets_for_paper(paper, paper_contexts) if dataset in requested_datasets]
        if not paper_datasets:
            continue
        screening_row = merged_screening_row(paper, metadata_by_doi.get(doi))
        abstract_status_reason = unusable_abstract_reason(screening_row.get("abstract", ""))
        has_abstract = not bool(abstract_status_reason)
        for dataset in paper_datasets:
            dataset_contexts = compact_contexts(contexts_lookup.get((doi, dataset), []))
            context_tags = context_routing_tags(dataset_contexts)
            non_paper_decision = non_paper_container_without_title_decision(screening_row, dataset_contexts)
            if non_paper_decision:
                decision = non_paper_decision
            elif artifact_decision := non_evidence_artifact_decision(screening_row, dataset_contexts):
                decision = artifact_decision
            elif exclude_missing_abstract and not has_abstract:
                decision = missing_abstract_decision(screening_row, dataset_contexts, abstract_status_reason)
            else:
                decision = deterministic_prescreen_decision(
                    dataset,
                    screening_row,
                    heuristic={},
                    candidate_contexts=dataset_contexts,
                )
            deterministic_tags = normalize_routing_tags(decision.get("routing_tags", []))
            routing_tags = normalize_routing_tags([*deterministic_tags, *context_tags])
            prescreen_decision, prescreen_action, prescreen_reason = final_prescreen_fields(decision)
            retained_for_extraction_candidate = prescreen_decision == "retain" and not clean(
                decision.get("action", "")
            ).startswith("exclude")
            rows.append(
                {
                    "table_version": TABLE_VERSION,
                    "run_id": run_id,
                    "generated_at_utc": generated_at_utc,
                    "prescreen_decision_id": stable_id(run_id, doi, dataset),
                    "doi": doi,
                    "dataset": dataset,
                    "study_title": clean(screening_row.get("study_title", "")),
                    "study_year": clean(screening_row.get("study_year", "")),
                    "has_abstract": has_abstract,
                    "abstract_char_count": len(clean(screening_row.get("abstract", ""))),
                    "candidate_context_count": len(dataset_contexts),
                    "context_compounds": join_values(context.get("compound", "") for context in dataset_contexts),
                    "context_entities": join_values(context.get("entity", "") for context in dataset_contexts),
                    "context_entity_types": join_values(context.get("entity_type", "") for context in dataset_contexts),
                    "context_routing_tags": "|".join(context_tags),
                    "deterministic_action": clean(decision.get("action", "")),
                    "deterministic_reason": clean(decision.get("reason", "")),
                    "deterministic_confidence": float(decision.get("confidence", 0) or 0),
                    "deterministic_matched_terms": join_values(decision.get("matched_terms", [])),
                    "deterministic_supporting_quote": clean(decision.get("supporting_quote", "")),
                    "deterministic_routing_tags": "|".join(deterministic_tags),
                    "routing_tags": "|".join(routing_tags),
                    "prescreen_decision": prescreen_decision,
                    "prescreen_action": prescreen_action,
                    "prescreen_reason": prescreen_reason,
                    "retained_for_extraction_candidate": retained_for_extraction_candidate,
                    "metadata_enrichment_status": clean(screening_row.get("metadata_enrichment_status", "")),
                    "metadata_enrichment_run_id": clean(screening_row.get("metadata_enrichment_run_id", "")),
                }
            )
    return rows


def build_summary_rows(decisions: list[dict], *, run_id: str, generated_at_utc: str) -> list[dict]:
    rows: list[dict] = []

    def add(dataset: str, metric: str, label: str, count: int) -> None:
        rows.append(
            {
                "table_version": TABLE_VERSION,
                "run_id": run_id,
                "generated_at_utc": generated_at_utc,
                "dataset": dataset,
                "metric": metric,
                "label": label,
                "count": int(count),
            }
        )

    for dataset in ["all", *DATASETS]:
        scoped = decisions if dataset == "all" else [row for row in decisions if row.get("dataset") == dataset]
        add(dataset, "decisions", "total", len(scoped))
        add(dataset, "papers", "unique_doi", len({row.get("doi") for row in scoped}))
        add(dataset, "abstract", "missing", sum(not row.get("has_abstract") for row in scoped))
        for field in ("prescreen_decision", "prescreen_action", "deterministic_action"):
            for label, count in Counter(clean(row.get(field, "")) for row in scoped).items():
                add(dataset, field, label, count)
        tag_counts: Counter = Counter()
        for row in scoped:
            for tag in normalize_routing_tags(row.get("routing_tags", "")):
                tag_counts[tag] += 1
        for tag, count in tag_counts.items():
            add(dataset, "routing_tag", tag, count)
    return rows


def parse_datasets(raw: str) -> list[str]:
    if clean(raw).lower() == "all":
        return list(DATASETS)
    datasets = [item for item in split_values(raw) if item in DATASETS]
    invalid = [item for item in split_values(raw) if item not in DATASETS]
    if invalid:
        raise ValueError(f"Invalid dataset(s): {', '.join(invalid)}")
    return datasets


def run(args: argparse.Namespace) -> tuple[list[dict], list[dict]]:
    datasets = parse_datasets(args.dataset)
    decisions_table = Path(args.decisions_table).resolve()
    summary_table = Path(args.summary_table).resolve()
    scoped_dois = scoped_dois_from_args(args)
    existing_decisions_df = read_table(decisions_table) if scoped_dois else pd.DataFrame()
    run_id = clean(args.run_id) or (existing_run_id(existing_decisions_df) if scoped_dois else "") or default_run_id()
    generated_at_utc = now_utc()

    papers_df = read_table(Path(args.papers_table).resolve())
    metadata_df = read_table(Path(args.metadata_table).resolve())
    contexts_df = read_table(Path(args.contexts_table).resolve())

    if papers_df.empty:
        raise SystemExit(f"No rows found in papers table: {args.papers_table}")
    if scoped_dois:
        if existing_decisions_df.empty:
            raise SystemExit(
                "Scoped deterministic pre-screen updates require an existing decisions table. "
                "Run a full pass first, or omit --doi/--doi-file."
            )
        papers_df = filter_table_to_dois(papers_df, scoped_dois)
        metadata_df = filter_table_to_dois(metadata_df, scoped_dois)
        contexts_df = filter_table_to_dois(contexts_df, scoped_dois)
        if papers_df.empty:
            raise SystemExit("No matching DOI rows found in the papers table for the requested scoped update.")

    updated_decisions = build_prescreen_decisions(
        papers_df,
        metadata_df,
        contexts_df,
        run_id=run_id,
        generated_at_utc=generated_at_utc,
        datasets=datasets,
        exclude_missing_abstract=not args.retain_missing_abstract,
        progress_every=getattr(args, "progress_every", 0),
    )
    if scoped_dois:
        decisions, replaced_count = merge_scoped_decisions(
            existing_decisions_df.to_dict("records"),
            updated_decisions,
            scoped_dois=scoped_dois,
            datasets=datasets,
        )
    else:
        decisions = updated_decisions
        replaced_count = 0
    summary = build_summary_rows(decisions, run_id=run_id, generated_at_utc=generated_at_utc)
    write_table(decisions_table, decisions)
    write_table(summary_table, summary)

    by_action = Counter(row["prescreen_action"] for row in decisions)
    print(f"Run ID: {run_id}")
    if scoped_dois:
        print(f"Scoped DOI update: requested={len(scoped_dois):,} matched_papers={len(papers_df):,}")
        print(f"Updated decision rows: {len(updated_decisions):,}")
        print(f"Replaced existing decision rows: {replaced_count:,}")
    print(f"Decision rows: {len(decisions):,}")
    print(f"Unique DOIs: {len({row['doi'] for row in decisions}):,}")
    print(f"Retained: {sum(row['prescreen_decision'] == 'retain' for row in decisions):,}")
    print(f"Excluded: {sum(row['prescreen_decision'] == 'exclude' for row in decisions):,}")
    print(f"Actions: {dict(by_action)}")
    print(f"Decisions table: {decisions_table}")
    print(f"Summary table: {summary_table}")
    return decisions, summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic pre-screening on corpus Parquet tables.")
    parser.add_argument("--papers-table", default=str(DEFAULT_PAPERS_TABLE))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--contexts-table", default=str(DEFAULT_CONTEXTS_TABLE))
    parser.add_argument("--decisions-table", default=str(DEFAULT_DECISIONS_TABLE))
    parser.add_argument("--summary-table", default=str(DEFAULT_SUMMARY_TABLE))
    parser.add_argument("--run-id", default="")
    parser.add_argument("--dataset", default="all", help="all, mechanistic, disorder, or a comma-separated subset")
    parser.add_argument("--doi-file", default="", help="Optional newline-delimited DOI list for a scoped update.")
    parser.add_argument("--doi", action="append", default=[], help="Single DOI for a scoped update; can be repeated.")
    parser.add_argument(
        "--retain-missing-abstract",
        action="store_true",
        help="Run title-only deterministic rules when abstracts are missing instead of excluding missing-abstract records.",
    )
    parser.add_argument("--progress-every", type=int, default=5000, help="Print progress every N candidate papers; 0 disables progress.")
    return parser


def main() -> None:
    run(build_arg_parser().parse_args())


if __name__ == "__main__":
    main()
