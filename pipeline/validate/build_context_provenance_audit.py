#!/usr/bin/env python3
"""Build a paper corpus and DOI-context provenance audit from local artifacts."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
VERSION = "0.1"

DATASETS = {
    "mechanistic": {
        "entity_key": "target",
        "entity_type": "target",
        "paper_library": "data/processed/paper_library_mechanistic.json",
        "ledger": "data/processed/discovery_ledger_mechanistic.json",
        "discovery_report": "data/processed/discovery_report_mechanistic.json",
        "triage_report": "data/processed/triage_report_mechanistic.json",
        "llm_report": "data/processed/llm_abstract_screening_report_mechanistic.json",
        "stubs": "data/processed/mechanistic_claim_stubs.json",
        "curated": "data/curated/claims.json",
        "exploratory": "data/curated/exploratory_claims.json",
        "pdf_dir": "data/raw/papers/mechanistic/pdfs",
    },
    "disorder": {
        "entity_key": "disorder",
        "entity_type": "indication",
        "paper_library": "data/processed/paper_library_disorder.json",
        "ledger": "data/processed/discovery_ledger_disorder.json",
        "discovery_report": "data/processed/discovery_report_disorder.json",
        "triage_report": "data/processed/triage_report_disorder.json",
        "llm_report": "data/processed/llm_abstract_screening_report_disorder.json",
        "stubs": "data/processed/disorder_claim_stubs.json",
        "curated": "data/curated/disorder_claims.json",
        "exploratory": "data/curated/exploratory_disorder_claims.json",
        "pdf_dir": "data/raw/papers/disorder/pdfs",
    },
}

PAPER_FIELDS = (
    "study_title",
    "study_year",
    "authors",
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
    "pdf_local_path",
    "pdf_download_status",
    "pdf_sha256",
    "open_access_status",
    "library_status",
)

PROVENANCE_FIELDS = (
    "source",
    "source_artifact",
    "context_source",
    "selected_for_downstream",
    "screening_decision",
    "paper_type",
    "source_type",
    "source_family",
    "access_level",
    "study_design",
    "evidence_location",
    "evidence_locator",
    "stub_status",
)

COMPOUND_ALIASES = {
    "dmt": ("n,n-dimethyltryptamine", "dimethyltryptamine", "spl026", "ayahuasca"),
    "5-meo-dmt": ("5-meo-dmt", "5 methoxy n n dimethyltryptamine", "5-methoxy-dmt", "bpl-003"),
    "doi": ("2,5-dimethoxy-4-iodoamphetamine", "dimethoxy-4-iodoamphetamine"),
    "dob": ("2,5-dimethoxy-4-bromoamphetamine", "dimethoxy-4-bromoamphetamine"),
    "dom": ("2,5-dimethoxy-4-methylamphetamine", "dimethoxy-4-methylamphetamine", "stp"),
    "mda": ("3,4-methylenedioxyamphetamine", "methylenedioxyamphetamine"),
    "lsa": ("lysergic acid amide", "ergine"),
}

ACRONYM_FALSE_POSITIVE_HINTS = {
    "dmt": ("disease modifying therap", "disease-modifying therap"),
    "doi": ("digital object identifier",),
    "mda": ("malondialdehyde", "minimum detectable activity", "model driven architecture"),
    "dom": ("delirium observation", "document object model"),
    "dob": ("date of birth",),
    "lsa": ("latent semantic analysis",),
}

SHORT_RISKY_COMPOUNDS = set(COMPOUND_ALIASES) | {"tma"}
SHORT_RISKY_ENTITIES = {"sert", "dat", "net"}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


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


def compact_text(raw: object) -> str:
    text = normalize(raw).lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def key_text(raw: object) -> str:
    return compact_text(raw)


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def json_rows(path: Path) -> list[dict]:
    payload = read_json(path)
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "entries", "results"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def unique_append(items: list[dict], item: dict) -> None:
    marker = json.dumps(item, sort_keys=True, ensure_ascii=False)
    if not any(json.dumps(existing, sort_keys=True, ensure_ascii=False) == marker for existing in items):
        items.append(item)


def paper_record(papers: dict[str, dict], doi: str) -> dict:
    return papers.setdefault(
        doi,
        {
            "doi": doi,
            "datasets": [],
            "study_title": "",
            "study_year": "",
            "authors": "",
            "metadata": {},
            "source_types": [],
            "sources": [],
            "local_pdf_paths": [],
            "flags": {
                "in_discovery_queue": False,
                "in_discovery_ledger": False,
                "in_discovery_report": False,
                "in_paper_library": False,
                "in_triage_report": False,
                "in_llm_abstract_screening": False,
                "in_claim_stubs": False,
                "in_curated_claims": False,
                "in_exploratory_claims": False,
                "in_known_study_set": False,
                "has_local_pdf": False,
            },
        },
    )


def merge_paper(
    papers: dict[str, dict],
    doi: str,
    dataset: str,
    source_type: str,
    source_artifact: str,
    row: dict | None = None,
    extra: dict | None = None,
) -> None:
    doi = normalize_doi(doi)
    if not doi:
        return
    row = row or {}
    record = paper_record(papers, doi)
    if dataset and dataset not in record["datasets"]:
        record["datasets"].append(dataset)
    if source_type and source_type not in record["source_types"]:
        record["source_types"].append(source_type)

    title = normalize(row.get("study_title") or row.get("title"))
    year = normalize(row.get("study_year") or row.get("year"))
    authors = normalize(row.get("authors"))
    if title and (not record["study_title"] or len(title) > len(record["study_title"])):
        record["study_title"] = title
    if year and not record["study_year"]:
        record["study_year"] = year
    if authors and not record["authors"]:
        record["authors"] = authors

    for field in PAPER_FIELDS:
        value = normalize(row.get(field))
        if value and not normalize(record["metadata"].get(field)):
            record["metadata"][field] = value

    pdf_path = normalize(row.get("pdf_local_path"))
    if pdf_path:
        record["flags"]["has_local_pdf"] = True
        if pdf_path not in record["local_pdf_paths"]:
            record["local_pdf_paths"].append(pdf_path)

    source = {
        "source_type": source_type,
        "source_artifact": source_artifact,
        "dataset": dataset,
    }
    if extra:
        source.update({k: v for k, v in extra.items() if v not in ("", None, [], {})})
    unique_append(record["sources"], source)


def context_id(dataset: str, doi: str, compound: str, entity: str) -> str:
    return "|".join((dataset, normalize_doi(doi), key_text(compound), key_text(entity)))


def context_record(
    contexts: dict[str, dict],
    dataset: str,
    doi: str,
    compound: str,
    entity: str,
    entity_type: str,
) -> dict | None:
    doi = normalize_doi(doi)
    compound = normalize(compound)
    entity = normalize(entity)
    if not doi or not compound or not entity:
        return None
    key = context_id(dataset, doi, compound, entity)
    return contexts.setdefault(
        key,
        {
            "context_id": key,
            "dataset": dataset,
            "doi": doi,
            "compound": compound,
            "entity": entity,
            "entity_type": entity_type,
            "context_sources": [],
            "provenance": [],
            "flags": {
                "has_seed_or_discovery_context": False,
                "has_paper_library_context": False,
                "has_triage_matched_context": False,
                "has_triage_synthesized_context": False,
                "has_llm_verified_context": False,
                "has_claim_stub": False,
                "has_curated_claim": False,
                "has_exploratory_claim": False,
                "has_known_study_context": False,
                "possible_acronym_collision": False,
                "needs_revalidation": True,
            },
            "verification_layer": "candidate_context",
            "revalidation_status": "needs_revalidation",
        },
    )


def provenance_item(
    source: str,
    source_artifact: str,
    context_source: str,
    row: dict | None = None,
    selected_for_downstream: bool | None = None,
    screening_decision: str = "",
) -> dict:
    row = row or {}
    item = {
        "source": source,
        "source_artifact": source_artifact,
        "context_source": context_source,
    }
    if selected_for_downstream is not None:
        item["selected_for_downstream"] = selected_for_downstream
    if screening_decision:
        item["screening_decision"] = screening_decision
    for field in PROVENANCE_FIELDS:
        value = row.get(field)
        if value not in ("", None, [], {}):
            item[field] = value
    return item


def add_context(
    contexts: dict[str, dict],
    dataset: str,
    doi: str,
    compound: str,
    entity: str,
    entity_type: str,
    context_source: str,
    source: str,
    source_artifact: str,
    row: dict | None = None,
    selected_for_downstream: bool | None = None,
    screening_decision: str = "",
) -> None:
    record = context_record(contexts, dataset, doi, compound, entity, entity_type)
    if record is None:
        return
    if context_source not in record["context_sources"]:
        record["context_sources"].append(context_source)
    unique_append(
        record["provenance"],
        provenance_item(
            source=source,
            source_artifact=source_artifact,
            context_source=context_source,
            row=row,
            selected_for_downstream=selected_for_downstream,
            screening_decision=screening_decision,
        ),
    )

    flags = record["flags"]
    if context_source in {"seed_result_context", "queue_discovered_context", "discovery_ledger_context"}:
        flags["has_seed_or_discovery_context"] = True
    if context_source == "paper_library_context":
        flags["has_paper_library_context"] = True
    if context_source == "triage_matched_context":
        flags["has_triage_matched_context"] = True
    if context_source == "triage_synthesized_context":
        flags["has_triage_synthesized_context"] = True
    if context_source == "llm_verified_context":
        flags["has_llm_verified_context"] = True
    if context_source == "claim_stub":
        flags["has_claim_stub"] = True
    if context_source == "curated_claim":
        flags["has_curated_claim"] = True
    if context_source == "exploratory_claim":
        flags["has_exploratory_claim"] = True
    if context_source == "known_study_context":
        flags["has_known_study_context"] = True


def source_artifact(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def classify_queue_context(path: Path) -> str:
    name = path.name
    if ".discovered." in name:
        return "queue_discovered_context"
    if ".llm_relevant." in name:
        return "llm_verified_context"
    if ".llm_uncertain." in name:
        return "llm_uncertain_context"
    if ".triage_relevant." in name:
        return "triage_matched_context"
    if ".template." in name:
        return "manual_template_context"
    if ".deterministic_prescreen_retained." in name:
        return "deterministic_prescreen_retained_context"
    return "queue_context"


def iter_queue_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for line_no, parts in enumerate(reader, start=1):
            if not parts:
                continue
            first = normalize(parts[0])
            if not first or first.startswith("#"):
                continue
            parts = [normalize(part) for part in parts]
            rows.append(
                {
                    "study_doi": parts[0],
                    "compound": parts[1] if len(parts) > 1 else "",
                    "entity": parts[2] if len(parts) > 2 else "",
                    "study_title": parts[3] if len(parts) > 3 else "",
                    "study_year": parts[4] if len(parts) > 4 else "",
                    "authors": parts[5] if len(parts) > 5 else "",
                    "line_no": line_no,
                }
            )
    return rows


def dataset_from_queue_name(path: Path) -> str:
    name = path.name
    if ".mechanistic." in name:
        return "mechanistic"
    if ".disorder." in name:
        return "disorder"
    return ""


def add_contexts_from_row_contexts(
    contexts: dict[str, dict],
    dataset: str,
    doi: str,
    contexts_value: object,
    entity_type: str,
    source: str,
    source_artifact_name: str,
    context_source: str,
    selected_for_downstream: bool | None = None,
    screening_decision: str = "",
) -> None:
    if not isinstance(contexts_value, list):
        return
    for ctx in contexts_value:
        if not isinstance(ctx, dict):
            continue
        add_context(
            contexts=contexts,
            dataset=dataset,
            doi=doi,
            compound=ctx.get("compound", ""),
            entity=ctx.get("entity", ""),
            entity_type=entity_type,
            context_source=context_source,
            source=source,
            source_artifact=source_artifact_name,
            row=ctx,
            selected_for_downstream=selected_for_downstream,
            screening_decision=screening_decision,
        )


def paper_text_for_context(record: dict, paper: dict | None = None) -> str:
    parts = [
        record.get("compound", ""),
        record.get("entity", ""),
        paper.get("study_title", "") if paper else "",
        paper.get("metadata", {}).get("study_title", "") if paper else "",
        paper.get("metadata", {}).get("mesh_terms", "") if paper else "",
    ]
    for prov in record.get("provenance", []):
        for field in ("study_title", "evidence_locator", "notes", "source_type", "paper_type"):
            parts.append(prov.get(field, ""))
    return compact_text(" ".join(normalize(part) for part in parts))


def has_any(text: str, values: tuple[str, ...]) -> bool:
    return any(compact_text(value) and compact_text(value) in text for value in values)


def possible_acronym_collision(record: dict, paper: dict | None = None) -> bool:
    text = paper_text_for_context(record, paper)
    compound_key = key_text(record.get("compound", ""))
    entity_key = key_text(record.get("entity", ""))

    if compound_key in ACRONYM_FALSE_POSITIVE_HINTS and has_any(text, ACRONYM_FALSE_POSITIVE_HINTS[compound_key]):
        return True
    if compound_key in SHORT_RISKY_COMPOUNDS and not has_any(text, COMPOUND_ALIASES.get(compound_key, ())):
        return True
    if entity_key in SHORT_RISKY_ENTITIES:
        return True
    return False


def finalize_context(record: dict, paper: dict | None) -> None:
    record["context_sources"] = sorted(record["context_sources"])
    record["provenance"] = sorted(
        record["provenance"],
        key=lambda item: (
            normalize(item.get("context_source")),
            normalize(item.get("source_artifact")),
            normalize(item.get("source")),
        ),
    )
    flags = record["flags"]
    flags["possible_acronym_collision"] = possible_acronym_collision(record, paper)

    if flags["has_curated_claim"]:
        record["verification_layer"] = "verified_evidence"
    elif flags["has_llm_verified_context"] or flags["has_triage_matched_context"]:
        record["verification_layer"] = "screened_context"
    else:
        record["verification_layer"] = "candidate_context"

    flags["needs_revalidation"] = record["verification_layer"] != "verified_evidence" or flags["possible_acronym_collision"]
    if flags["possible_acronym_collision"]:
        record["revalidation_status"] = "possible_noise"
    elif record["verification_layer"] == "verified_evidence":
        record["revalidation_status"] = "verified_existing"
    elif record["verification_layer"] == "screened_context":
        record["revalidation_status"] = "screened_needs_extraction"
    else:
        record["revalidation_status"] = "candidate_needs_screening"


def finalize_paper(record: dict) -> None:
    record["datasets"] = sorted(record["datasets"])
    record["source_types"] = sorted(record["source_types"])
    record["sources"] = sorted(
        record["sources"],
        key=lambda item: (
            normalize(item.get("source_type")),
            normalize(item.get("dataset")),
            normalize(item.get("source_artifact")),
        ),
    )
    record["local_pdf_paths"] = sorted(record["local_pdf_paths"])
    for source_type in record["source_types"]:
        flag = {
            "discovery_queue": "in_discovery_queue",
            "discovery_ledger": "in_discovery_ledger",
            "discovery_report": "in_discovery_report",
            "paper_library": "in_paper_library",
            "triage_report": "in_triage_report",
            "llm_abstract_screening": "in_llm_abstract_screening",
            "claim_stub": "in_claim_stubs",
            "curated_claim": "in_curated_claims",
            "exploratory_claim": "in_exploratory_claims",
            "known_study": "in_known_study_set",
            "local_pdf": "has_local_pdf",
        }.get(source_type)
        if flag:
            record["flags"][flag] = True


def build_audit(root: Path = ROOT, datasets: list[str] | None = None) -> dict:
    root = root.resolve()
    selected = datasets or list(DATASETS.keys())
    papers: dict[str, dict] = {}
    contexts: dict[str, dict] = {}
    input_artifacts: list[str] = []

    raw_dir = root / "data" / "raw"
    for path in sorted(raw_dir.glob("doi_queue.*.txt")) if raw_dir.exists() else []:
        dataset = dataset_from_queue_name(path)
        if dataset not in selected:
            continue
        cfg = DATASETS[dataset]
        artifact = source_artifact(root, path)
        input_artifacts.append(artifact)
        context_source = classify_queue_context(path)
        for row in iter_queue_rows(path):
            doi = normalize_doi(row.get("study_doi"))
            merge_paper(papers, doi, dataset, "discovery_queue", artifact, row, {"queue_kind": context_source})
            add_context(
                contexts,
                dataset,
                doi,
                row.get("compound", ""),
                row.get("entity", ""),
                cfg["entity_type"],
                context_source,
                "queue",
                artifact,
                row,
                selected_for_downstream=context_source in {"llm_verified_context", "triage_matched_context"},
            )

    manifest_path = root / "data" / "raw" / "benchmark_manifest.json"
    if manifest_path.exists():
        input_artifacts.append(source_artifact(root, manifest_path))
        payload = read_json(manifest_path)
        entries = payload.get("entries", []) if isinstance(payload, dict) else []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            dataset = normalize(entry.get("dataset"))
            if dataset not in selected:
                continue
            cfg = DATASETS[dataset]
            doi = normalize_doi(entry.get("doi"))
            merge_paper(papers, doi, dataset, "known_study", source_artifact(root, manifest_path), entry)
            add_context(
                contexts,
                dataset,
                doi,
                entry.get("compound", ""),
                entry.get("target") or entry.get("disorder") or entry.get("entity", ""),
                cfg["entity_type"],
                "known_study_context",
                "known_study_manifest",
                source_artifact(root, manifest_path),
                entry,
            )

    for dataset in selected:
        cfg = DATASETS[dataset]
        entity_key = cfg["entity_key"]
        entity_type = cfg["entity_type"]

        ledger_path = root / cfg["ledger"]
        if ledger_path.exists():
            artifact = source_artifact(root, ledger_path)
            input_artifacts.append(artifact)
            ledger = read_json(ledger_path)
            for entry in (ledger.get("entries", []) if isinstance(ledger, dict) else []):
                if not isinstance(entry, dict):
                    continue
                doi = normalize_doi(entry.get("doi"))
                merge_paper(
                    papers,
                    doi,
                    dataset,
                    "discovery_ledger",
                    artifact,
                    {
                        "study_title": entry.get("title", ""),
                        "study_year": entry.get("year", ""),
                        "authors": entry.get("authors", ""),
                    },
                    {
                        "seen_in_latest_run": entry.get("seen_in_latest_run", False),
                        "retained_in_latest_queue": entry.get("retained_in_latest_queue", False),
                        "providers": entry.get("providers", []),
                        "latest_run_id": entry.get("latest_run_id", ""),
                    },
                )
                add_contexts_from_row_contexts(
                    contexts,
                    dataset,
                    doi,
                    entry.get("contexts", []),
                    entity_type,
                    "discovery_ledger",
                    artifact,
                    "discovery_ledger_context",
                    selected_for_downstream=bool(entry.get("retained_in_latest_queue", False)),
                )

        report_path = root / cfg["discovery_report"]
        if report_path.exists():
            artifact = source_artifact(root, report_path)
            input_artifacts.append(artifact)
            report = read_json(report_path)
            rows = report.get("rows", []) if isinstance(report, dict) else []
            run_id = normalize(report.get("run_id", "")) if isinstance(report, dict) else ""
            for row in rows:
                if not isinstance(row, dict):
                    continue
                doi = normalize_doi(row.get("doi") or row.get("study_doi"))
                merge_paper(
                    papers,
                    doi,
                    dataset,
                    "discovery_report",
                    artifact,
                    {
                        "study_title": row.get("title", "") or row.get("study_title", ""),
                        "study_year": row.get("year", "") or row.get("study_year", ""),
                        "authors": row.get("authors", ""),
                    },
                    {"providers": row.get("providers", []) or row.get("provider", ""), "run_id": run_id},
                )
                add_context(
                    contexts,
                    dataset,
                    doi,
                    row.get("compound", ""),
                    row.get("entity", ""),
                    entity_type,
                    "seed_result_context",
                    "discovery_report",
                    artifact,
                    row,
                    selected_for_downstream=True,
                )

        paper_path = root / cfg["paper_library"]
        for row in json_rows(paper_path):
            doi = normalize_doi(row.get("study_doi") or row.get("doi"))
            artifact = source_artifact(root, paper_path)
            merge_paper(papers, doi, dataset, "paper_library", artifact, row)
            add_contexts_from_row_contexts(
                contexts,
                dataset,
                doi,
                row.get("contexts", []),
                entity_type,
                "paper_library",
                artifact,
                "paper_library_context",
            )
        if paper_path.exists():
            input_artifacts.append(source_artifact(root, paper_path))

        triage_path = root / cfg["triage_report"]
        for row in json_rows(triage_path):
            doi = normalize_doi(row.get("study_doi") or row.get("doi"))
            artifact = source_artifact(root, triage_path)
            merge_paper(papers, doi, dataset, "triage_report", artifact, row)
            decision = normalize(row.get("screening_status") or row.get("relevance_suggested"))
            for ctx in row.get("contexts", []) if isinstance(row.get("contexts"), list) else []:
                if not isinstance(ctx, dict):
                    continue
                source_name = normalize(ctx.get("triage_match_source", ""))
                context_source = "triage_synthesized_context" if source_name == "synthesized_text" else "triage_matched_context"
                add_context(
                    contexts,
                    dataset,
                    doi,
                    ctx.get("compound", ""),
                    ctx.get("entity", ""),
                    entity_type,
                    context_source,
                    "triage_report",
                    artifact,
                    {**ctx, **{"screening_decision": decision}},
                    selected_for_downstream=True,
                    screening_decision=decision,
                )
            add_contexts_from_row_contexts(
                contexts,
                dataset,
                doi,
                row.get("contexts_all", []),
                entity_type,
                "triage_report",
                artifact,
                "triage_original_context",
                selected_for_downstream=False,
                screening_decision=decision,
            )
        if triage_path.exists():
            input_artifacts.append(source_artifact(root, triage_path))

        llm_path = root / cfg["llm_report"]
        for row in json_rows(llm_path):
            input_row = row.get("input_row", {}) if isinstance(row.get("input_row"), dict) else row.get("flat", {})
            doi = normalize_doi(input_row.get("study_doi") or row.get("study_doi"))
            artifact = source_artifact(root, llm_path)
            merge_paper(papers, doi, dataset, "llm_abstract_screening", artifact, input_row)
            decision = normalize(row.get("adjudication", {}).get("relevance", "") if isinstance(row.get("adjudication"), dict) else "")
            verification = row.get("verification", {}) if isinstance(row.get("verification"), dict) else {}
            add_contexts_from_row_contexts(
                contexts,
                dataset,
                doi,
                verification.get("verified_supported_contexts", []),
                entity_type,
                "llm_abstract_screening",
                artifact,
                "llm_verified_context",
                selected_for_downstream=True,
                screening_decision=decision,
            )
        if llm_path.exists():
            input_artifacts.append(source_artifact(root, llm_path))

        for source_type, context_source, rel_path in (
            ("claim_stub", "claim_stub", cfg["stubs"]),
            ("curated_claim", "curated_claim", cfg["curated"]),
            ("exploratory_claim", "exploratory_claim", cfg["exploratory"]),
        ):
            path = root / rel_path
            if path.exists():
                input_artifacts.append(source_artifact(root, path))
            for row in json_rows(path):
                doi = normalize_doi(row.get("study_doi") or row.get("doi"))
                merge_paper(papers, doi, dataset, source_type, source_artifact(root, path), row)
                add_context(
                    contexts,
                    dataset,
                    doi,
                    row.get("compound", ""),
                    row.get(entity_key, ""),
                    entity_type,
                    context_source,
                    source_type,
                    source_artifact(root, path),
                    row,
                    selected_for_downstream=context_source in {"curated_claim", "claim_stub"},
                )

        pdf_dir = root / cfg["pdf_dir"]
        if pdf_dir.exists():
            input_artifacts.append(source_artifact(root, pdf_dir))
            for pdf in sorted(pdf_dir.glob("*.pdf")):
                doi_guess = doi_from_pdf_filename(pdf.name)
                if not doi_guess:
                    continue
                merge_paper(
                    papers,
                    doi_guess,
                    dataset,
                    "local_pdf",
                    source_artifact(root, pdf),
                    {"pdf_local_path": str(pdf)},
                )

    for record in papers.values():
        finalize_paper(record)
    for record in contexts.values():
        finalize_context(record, papers.get(record["doi"]))

    paper_records = sorted(papers.values(), key=lambda row: row["doi"])
    context_records = sorted(contexts.values(), key=lambda row: (row["dataset"], row["doi"], row["compound"], row["entity"]))
    return {
        "version": VERSION,
        "generated_at_utc": now_utc(),
        "input_artifacts": sorted(set(input_artifacts)),
        "papers": paper_records,
        "contexts": context_records,
        "summary": build_summary(paper_records, context_records),
    }


def doi_from_pdf_filename(name: str) -> str:
    match = re.match(r"^(10\.\d{4,9})_(.+?)(?:__|\.pdf$)", name, re.IGNORECASE)
    if not match:
        return ""
    suffix = match.group(2).removesuffix(".pdf")
    suffix = suffix.replace("_", "/")
    return normalize_doi(f"{match.group(1)}/{suffix}")


def build_summary(papers: list[dict], contexts: list[dict]) -> dict:
    paper_source_counts = Counter(source for paper in papers for source in paper.get("source_types", []))
    context_source_counts = Counter(source for ctx in contexts for source in ctx.get("context_sources", []))
    layer_counts = Counter(ctx.get("verification_layer", "") for ctx in contexts)
    status_counts = Counter(ctx.get("revalidation_status", "") for ctx in contexts)
    dataset_counts = Counter(ctx.get("dataset", "") for ctx in contexts)
    return {
        "paper_count": len(papers),
        "context_count": len(contexts),
        "paper_source_counts": dict(sorted(paper_source_counts.items())),
        "context_source_counts": dict(sorted(context_source_counts.items())),
        "verification_layer_counts": dict(sorted(layer_counts.items())),
        "revalidation_status_counts": dict(sorted(status_counts.items())),
        "context_dataset_counts": dict(sorted(dataset_counts.items())),
        "possible_acronym_collision_contexts": sum(
            1 for ctx in contexts if ctx.get("flags", {}).get("possible_acronym_collision")
        ),
        "needs_revalidation_contexts": sum(1 for ctx in contexts if ctx.get("flags", {}).get("needs_revalidation")),
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build candidate DOI corpus and context provenance audit")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--dataset", choices=["all", "mechanistic", "disorder"], default="all")
    parser.add_argument("--out-dir", default=str(ROOT / "data" / "processed"))
    parser.add_argument("--paper-out", default="")
    parser.add_argument("--context-out", default="")
    parser.add_argument("--summary-out", default="")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    selected = list(DATASETS.keys()) if args.dataset == "all" else [args.dataset]
    out_dir = Path(args.out_dir).resolve()
    audit = build_audit(root=root, datasets=selected)

    paper_payload = {
        "version": audit["version"],
        "generated_at_utc": audit["generated_at_utc"],
        "input_artifacts": audit["input_artifacts"],
        "counts": {
            "paper_count": audit["summary"]["paper_count"],
            "paper_source_counts": audit["summary"]["paper_source_counts"],
        },
        "records": audit["papers"],
    }
    context_payload = {
        "version": audit["version"],
        "generated_at_utc": audit["generated_at_utc"],
        "input_artifacts": audit["input_artifacts"],
        "counts": {
            "context_count": audit["summary"]["context_count"],
            "context_source_counts": audit["summary"]["context_source_counts"],
            "verification_layer_counts": audit["summary"]["verification_layer_counts"],
            "revalidation_status_counts": audit["summary"]["revalidation_status_counts"],
            "possible_acronym_collision_contexts": audit["summary"]["possible_acronym_collision_contexts"],
            "needs_revalidation_contexts": audit["summary"]["needs_revalidation_contexts"],
        },
        "records": audit["contexts"],
    }
    summary_payload = {
        "version": audit["version"],
        "generated_at_utc": audit["generated_at_utc"],
        "input_artifacts": audit["input_artifacts"],
        "summary": audit["summary"],
    }

    paper_out = Path(args.paper_out).resolve() if args.paper_out else out_dir / "candidate_paper_corpus.json"
    context_out = Path(args.context_out).resolve() if args.context_out else out_dir / "context_provenance_audit.json"
    summary_out = Path(args.summary_out).resolve() if args.summary_out else out_dir / "context_provenance_summary.json"

    write_json(paper_out, paper_payload)
    write_json(context_out, context_payload)
    write_json(summary_out, summary_payload)

    print(f"Papers: {audit['summary']['paper_count']}")
    print(f"Contexts: {audit['summary']['context_count']}")
    print(f"Needs revalidation: {audit['summary']['needs_revalidation_contexts']}")
    print(f"Possible acronym collisions: {audit['summary']['possible_acronym_collision_contexts']}")
    print(f"Paper corpus: {paper_out}")
    print(f"Context audit: {context_out}")
    print(f"Summary: {summary_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
