#!/usr/bin/env python3
"""Build a typed file-based KG projection from local pipeline artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
KG_VERSION = "0.1"

DATASETS = {
    "mechanistic": {
        "paper_library": ROOT / "data" / "processed" / "paper_library_mechanistic.json",
        "triage_report": ROOT / "data" / "processed" / "triage_report_mechanistic.json",
        "curated_claims": ROOT / "data" / "curated" / "claims.json",
        "exploratory_claims": ROOT / "data" / "curated" / "exploratory_claims.json",
        "fulltext_dir": ROOT / "data" / "processed" / "fulltext" / "mechanistic",
        "object_type": "Target",
        "claim_relation": "reports_binding",
    },
    "disorder": {
        "paper_library": ROOT / "data" / "processed" / "paper_library_disorder.json",
        "triage_report": ROOT / "data" / "processed" / "triage_report_disorder.json",
        "curated_claims": ROOT / "data" / "curated" / "disorder_claims.json",
        "exploratory_claims": ROOT / "data" / "curated" / "exploratory_disorder_claims.json",
        "fulltext_dir": ROOT / "data" / "processed" / "fulltext" / "disorder",
        "object_type": "Disorder",
        "claim_relation": "reports_outcome",
    },
}

ENTITY_REGISTRY = ROOT / "data" / "curated" / "entity_registry.json"

CLAIM_ID_FIELDS = {
    "mechanistic": [
        "compound",
        "target",
        "study_doi",
        "openalex_id",
        "assay_type",
        "affinity_type",
        "affinity_value",
        "affinity_unit",
        "evidence_locator",
    ],
    "disorder": [
        "compound",
        "disorder",
        "study_doi",
        "openalex_id",
        "outcome_type",
        "outcome_measure",
        "evidence_locator",
    ],
}

PAPER_METADATA_FIELDS = (
    "study_doi",
    "openalex_id",
    "study_title",
    "study_year",
    "study_journal",
    "authors",
    "pmid",
    "pmcid",
    "publication_type",
    "publication_date",
    "publisher",
    "language",
    "trial_registry_ids",
    "mesh_terms",
    "keywords",
    "funders",
    "grant_ids",
    "related_dois",
    "publication_relations",
    "is_retracted",
    "has_correction",
    "semantic_scholar_id",
    "open_access_status",
    "open_access_url",
    "pdf_download_status",
    "pdf_local_path",
    "pdf_size_bytes",
    "pdf_sha256",
    "library_status",
)

MECHANISTIC_PROPERTY_FIELDS = (
    "assay_type",
    "affinity_type",
    "affinity_value",
    "affinity_unit",
    "species",
    "system",
    "evidence_level",
)

DISORDER_PROPERTY_FIELDS = (
    "outcome_type",
    "result_direction",
    "outcome_measure",
    "population",
    "system",
    "evidence_level",
)

PROVENANCE_FIELDS = (
    "source",
    "source_type",
    "source_family",
    "paper_type",
    "access_level",
    "evidence_location",
    "evidence_locator",
    "study_design",
    "evidence_strength",
    "notes",
)

RELEVANT_RELEVANCE = {"likely_relevant", "possible_relevant"}
INCLUDED_SCREENING = {"included_context_match", "included_synthesized_context", "included_protected"}

PRISMA_SCREENING_REASON_LABELS = {
    "excluded_low_signal": "Low-signal abstract screen",
    "needs_context_review": "Possible or contextual signal only",
    "included_synthesized_context": "Synthesized context, not direct match",
    "needs_metadata_or_manual_screen": "Metadata or manual screen needed",
    "unknown": "Screening status not available",
}

PRISMA_RETRIEVAL_REASON_LABELS = {
    "not_open_access": "Not open access",
    "no_pdf_url": "No PDF URL found",
    "download_failed": "PDF download failed",
    "skipped": "Download not attempted",
    "missing_local_pdf": "Local PDF file missing",
    "invalid_pdf_existing": "Invalid local PDF",
    "invalid_pdf_content": "Invalid downloaded PDF",
    "not_downloaded": "Not downloaded",
    "pdf_url_known": "PDF URL known, not downloaded",
    "unknown": "Retrieval status not available",
}

PRISMA_CONVERSION_REASON_LABELS = {
    "not_converted": "Conversion not completed",
    "artifact_present": "Artifact present but not confirmed converted",
    "unknown": "Conversion status not available",
}

PRISMA_EXTRACTION_REASON_LABELS = {
    "not_started": "Awaiting LLM extraction",
    "unknown": "Extraction status not available",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def strip_markup(value: object) -> str:
    text = html.unescape(normalize(value))
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


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


def compact_key(value: object) -> str:
    text = strip_markup(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def slug(value: object, fallback_prefix: str = "id") -> str:
    key = compact_key(value)
    if not key:
        digest = hashlib.sha1(normalize(value).encode("utf-8")).hexdigest()[:12]
        return f"{fallback_prefix}_{digest}"
    return re.sub(r"[^a-z0-9]+", "_", key).strip("_")[:120]


def digest_id(*parts: object, length: int = 16) -> str:
    canonical = "|".join(normalize(part) for part in parts)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:length]


def as_int(value: object) -> int | str:
    text = normalize(value)
    if not text:
        return ""
    try:
        return int(float(text))
    except Exception:
        return text


def json_value(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return value


def read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_json_array(path: Path) -> list[dict]:
    data = read_json(path, [])
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return [row for row in data if isinstance(row, dict)]


def read_json_object(path: Path) -> dict:
    data = read_json(path, {})
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def node_sort_key(row: dict) -> tuple:
    return (normalize(row.get("type", "")), normalize(row.get("id", "")))


def edge_sort_key(row: dict) -> tuple:
    return (normalize(row.get("type", "")), normalize(row.get("source_id", "")), normalize(row.get("target_id", "")), normalize(row.get("id", "")))


def first_nonempty(*values: object) -> object:
    for value in values:
        if normalize(value):
            return value
    return ""


def listify(value: object) -> list:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    return [value]


def merge_unique(existing: list, values: Iterable[object]) -> list:
    seen = {json.dumps(item, sort_keys=True, ensure_ascii=False) for item in existing}
    out = list(existing)
    for value in values:
        if value is None or value == "":
            continue
        key = json.dumps(value, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        out.append(value)
        seen.add(key)
    return out


def paper_id_for(row: dict) -> str:
    doi = normalize_doi(row.get("study_doi", ""))
    if doi:
        return f"paper:{doi}"
    openalex = normalize(row.get("openalex_id", "")).lower()
    if openalex:
        return f"paper:openalex:{slug(openalex)}"
    title = strip_markup(row.get("study_title", ""))
    year = normalize(row.get("study_year", ""))
    return f"paper:title:{digest_id(title, year)}"


def claim_external_id(dataset: str, row: dict) -> str:
    canonical = "|".join(f"{field}={normalize(row.get(field, ''))}" for field in CLAIM_ID_FIELDS[dataset])
    prefix = "mech" if dataset == "mechanistic" else "dis"
    return f"{prefix}-{hashlib.sha1(canonical.encode('utf-8')).hexdigest()[:16]}"


def local_pdf_exists(row: dict) -> bool:
    raw_path = normalize(row.get("pdf_local_path", ""))
    if not raw_path:
        return False
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.exists() and path.is_file() and path.stat().st_size > 0


def pdf_status(row: dict) -> str:
    if local_pdf_exists(row):
        return "downloaded"
    status = normalize(row.get("pdf_download_status", ""))
    if status in {"downloaded", "already_present", "manual_import"}:
        return "missing_local_pdf"
    if status:
        return status
    if normalize(row.get("pdf_local_path", "")):
        return "missing_local_pdf"
    if normalize(row.get("best_pdf_url", "")):
        return "pdf_url_known"
    return "not_downloaded"


class EntityIndex:
    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.alias_to_id: dict[str, dict[str, str]] = defaultdict(dict)

    def _node_id(self, entity_type: str, label: str) -> str:
        return f"{entity_type.lower()}:{slug(label, fallback_prefix=entity_type.lower())}"

    def add_registry_entity(self, entity_type: str, row: dict) -> str:
        label = strip_markup(row.get("label", ""))
        if not label:
            return ""
        node_id = self._node_id(entity_type, label)
        aliases = [strip_markup(alias) for alias in listify(row.get("aliases", [])) if strip_markup(alias)]
        node = {
            "id": node_id,
            "type": entity_type,
            "label": label,
            "properties": {
                "aliases": aliases,
                "external_ids": row.get("ids", {}) if isinstance(row.get("ids", {}), dict) else {},
                "registry_status": normalize(row.get("status", "")) or "registered",
            },
        }
        if normalize(row.get("organism", "")):
            node["properties"]["organism"] = normalize(row.get("organism", ""))
        self.nodes[node_id] = node
        for alias in [label, *aliases]:
            key = compact_key(alias)
            if key:
                self.alias_to_id[entity_type][key] = node_id
        return node_id

    def resolve(self, entity_type: str, label: object, create: bool = True) -> tuple[str, str]:
        clean_label = strip_markup(label)
        if not clean_label:
            return "", ""
        key = compact_key(clean_label)
        node_id = self.alias_to_id[entity_type].get(key, "")
        if node_id:
            return node_id, self.nodes[node_id]["label"]
        if not create:
            return "", clean_label
        node_id = self._node_id(entity_type, clean_label)
        self.nodes.setdefault(
            node_id,
            {
                "id": node_id,
                "type": entity_type,
                "label": clean_label,
                "properties": {
                    "aliases": [],
                    "external_ids": {},
                    "registry_status": "unregistered",
                },
            },
        )
        self.alias_to_id[entity_type][key] = node_id
        return node_id, self.nodes[node_id]["label"]

    def add_registry(self, registry_path: Path) -> None:
        registry = read_json_object(registry_path)
        for entity_type, key in (("Compound", "compounds"), ("Disorder", "disorders"), ("Target", "targets")):
            for row in registry.get(key, []):
                if isinstance(row, dict):
                    self.add_registry_entity(entity_type, row)


class KgBuilder:
    def __init__(self, root: Path = ROOT) -> None:
        self.root = root
        self.entity_index = EntityIndex()
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, dict] = {}
        self.evidence_records: dict[str, dict] = {}
        self.papers: dict[str, dict] = {}
        self.fulltext_by_doi: dict[str, dict] = {}
        self.aggregate_records: dict[tuple[str, str, str], dict] = {}
        self.edge_to_evidence: dict[str, set[str]] = defaultdict(set)
        self.doi_to_paper_id: dict[str, str] = {}
        self.entity_to_node_id: dict[str, str] = {}
        self.input_files: list[str] = []
        self.warnings: list[str] = []

    def build(self) -> dict:
        self.entity_index.add_registry(ENTITY_REGISTRY)
        self.input_files.append(str(ENTITY_REGISTRY))
        self.nodes.update(self.entity_index.nodes)

        self.load_fulltext_status()
        self.load_paper_libraries()
        self.load_triage_reports()
        self.load_claims()
        self.finalize_paper_nodes()
        self.finalize_entity_index()
        return self.payloads()

    def add_edge(
        self,
        edge_type: str,
        source_id: str,
        target_id: str,
        *,
        evidence_record_id: str = "",
        properties: dict | None = None,
    ) -> str:
        if not source_id or not target_id:
            return ""
        edge_id = f"edge:{digest_id(edge_type, source_id, target_id, evidence_record_id or json.dumps(properties or {}, sort_keys=True))}"
        self.edges.setdefault(
            edge_id,
            {
                "id": edge_id,
                "type": edge_type,
                "source_id": source_id,
                "target_id": target_id,
                "evidence_record_ids": [],
                "properties": properties or {},
            },
        )
        if evidence_record_id:
            ids = self.edges[edge_id].setdefault("evidence_record_ids", [])
            if evidence_record_id not in ids:
                ids.append(evidence_record_id)
            self.edge_to_evidence[edge_id].add(evidence_record_id)
        return edge_id

    def add_evidence_node(self, record: dict) -> None:
        node_id = record["id"]
        subject_label = record.get("subject_label", "")
        object_label = record.get("object_label", "")
        relation = record.get("relation", record.get("record_type", "evidence"))
        label = f"{subject_label} -> {object_label}" if subject_label and object_label else node_id
        self.nodes[node_id] = {
            "id": node_id,
            "type": "EvidenceRecord",
            "label": label,
            "properties": {
                "record_type": record.get("record_type", ""),
                "dataset": record.get("dataset", ""),
                "relation": relation,
                "status": record.get("status", ""),
                "paper_id": record.get("paper_id", ""),
            },
        }

    def merge_paper(self, row: dict, dataset: str, source_file: Path) -> str:
        paper_id = paper_id_for(row)
        props = self.papers.setdefault(
            paper_id,
            {
                "id": paper_id,
                "type": "Paper",
                "label": "",
                "properties": {
                    "datasets": [],
                    "source_files": [],
                },
            },
        )["properties"]
        props["datasets"] = merge_unique(props.get("datasets", []), [dataset])
        props["source_files"] = merge_unique(props.get("source_files", []), [str(source_file)])

        for field in PAPER_METADATA_FIELDS:
            value = row.get(field, "")
            if normalize(value) and not normalize(props.get(field, "")):
                props[field] = json_value(value)
        title = strip_markup(first_nonempty(props.get("study_title", ""), row.get("study_title", "")))
        if title:
            self.papers[paper_id]["label"] = title
            props["study_title"] = title
        year = as_int(first_nonempty(props.get("study_year", ""), row.get("study_year", "")))
        if year != "":
            props["study_year"] = year
        abstract = strip_markup(row.get("abstract", ""))
        if abstract and not props.get("abstract_snippet"):
            props["abstract_present"] = True
            props["abstract_char_count"] = len(abstract)
            props["abstract_snippet"] = abstract[:500]
        props["pdf_status"] = strongest_pdf_status(normalize(props.get("pdf_status", "")), pdf_status(row))

        doi = normalize_doi(props.get("study_doi", "") or row.get("study_doi", ""))
        if doi:
            props["study_doi"] = doi
            self.doi_to_paper_id[doi] = paper_id
            if doi in self.fulltext_by_doi:
                props.update(self.fulltext_by_doi[doi])
        return paper_id

    def load_fulltext_status(self) -> None:
        for dataset, cfg in DATASETS.items():
            fulltext_dir = cfg["fulltext_dir"]
            if not fulltext_dir.exists():
                continue
            self.input_files.append(str(fulltext_dir))
            for path in sorted(fulltext_dir.glob("*.json")):
                try:
                    artifact = read_json_object(path)
                except Exception as err:
                    self.warnings.append(f"Could not read full-text artifact {path}: {err}")
                    continue
                doi = normalize_doi(artifact.get("study_doi", ""))
                if not doi:
                    continue
                best_backend = normalize(artifact.get("best_backend", ""))
                best_char_count = int(artifact.get("best_char_count", 0) or 0)
                self.fulltext_by_doi[doi] = {
                    "fulltext_status": "converted" if best_backend and best_char_count else "artifact_present",
                    "fulltext_dataset": dataset,
                    "fulltext_artifact_path": str(path),
                    "fulltext_backend": best_backend,
                    "fulltext_char_count": best_char_count,
                    "fulltext_section_count": int(artifact.get("best_section_count", 0) or 0),
                }

    def load_paper_libraries(self) -> None:
        for dataset, cfg in DATASETS.items():
            path = cfg["paper_library"]
            self.input_files.append(str(path))
            for row in read_json_array(path):
                self.merge_paper(row, dataset, path)

    def load_triage_reports(self) -> None:
        for dataset, cfg in DATASETS.items():
            path = cfg["triage_report"]
            report = read_json_object(path)
            self.input_files.append(str(path))
            object_type = cfg["object_type"]
            for row in report.get("rows", []):
                if not isinstance(row, dict):
                    continue
                paper_id = self.merge_paper(row, dataset, path)
                paper_props = self.papers[paper_id]["properties"]
                for field in (
                    "library_status",
                    "source_type_suggested",
                    "paper_type_suggested",
                    "relevance_suggested",
                    "relevance_score",
                    "screening_status",
                    "matched_context_count",
                    "synthesized_context_count",
                    "protected_context_count",
                    "needs_metadata_or_manual_screen",
                ):
                    value = row.get(field, "")
                    if normalize(value) != "":
                        paper_props[field] = value
                self.add_context_records(dataset, object_type, row, paper_id, path)

    def add_context_records(self, dataset: str, object_type: str, row: dict, paper_id: str, source_file: Path) -> None:
        context_rows = row.get("contexts") or row.get("contexts_all") or []
        if not isinstance(context_rows, list):
            return
        seen: set[tuple[str, str, str]] = set()
        for context in context_rows:
            if not isinstance(context, dict):
                continue
            compound = strip_markup(context.get("compound", ""))
            obj = strip_markup(context.get("entity", ""))
            if not compound or not obj:
                continue
            subject_id, subject_label = self.entity_index.resolve("Compound", compound)
            object_id, object_label = self.entity_index.resolve(object_type, obj)
            source = normalize(context.get("triage_match_source", "")) or "triage_context"
            key = (subject_id, object_id, source)
            if key in seen:
                continue
            seen.add(key)
            record_id = f"evidence:ctx:{digest_id(dataset, paper_id, subject_id, object_id, source)}"
            record = {
                "id": record_id,
                "record_type": "literature_context",
                "status": "provisional",
                "dataset": dataset,
                "paper_id": paper_id,
                "paper_doi": normalize_doi(row.get("study_doi", "")),
                "subject_id": subject_id,
                "subject_type": "Compound",
                "subject_label": subject_label,
                "object_id": object_id,
                "object_type": object_type,
                "object_label": object_label,
                "relation": "candidate_disorder_context" if object_type == "Disorder" else "candidate_target_context",
                "basis": source,
                "screening": {
                    "relevance_suggested": normalize(row.get("relevance_suggested", "")),
                    "relevance_score": row.get("relevance_score", ""),
                    "screening_status": normalize(row.get("screening_status", "")),
                    "source_type_suggested": normalize(row.get("source_type_suggested", "")),
                    "paper_type_suggested": normalize(row.get("paper_type_suggested", "")),
                    "relevance_reasons": row.get("relevance_reasons", []),
                    "source_type_reasons": row.get("source_type_reasons", []),
                    "paper_type_reasons": row.get("paper_type_reasons", []),
                },
                "context": {
                    key: value
                    for key, value in context.items()
                    if key in {"compound_match", "entity_match", "triage_match_source"}
                },
                "source": {
                    "file": str(source_file),
                    "stage": "triage_report",
                },
            }
            self.evidence_records[record_id] = record
            self.add_evidence_node(record)
            self.add_edge("paper_has_literature_context", paper_id, record_id, evidence_record_id=record_id)
            self.add_edge("evidence_about_compound", record_id, subject_id, evidence_record_id=record_id)
            self.add_edge(f"evidence_about_{object_type.lower()}", record_id, object_id, evidence_record_id=record_id)
            self.add_edge("mentions_compound", paper_id, subject_id, evidence_record_id=record_id, properties={"dataset": dataset, "basis": source})
            self.add_edge(f"mentions_{object_type.lower()}", paper_id, object_id, evidence_record_id=record_id, properties={"dataset": dataset, "basis": source})
            semantic_edge_id = self.add_edge(
                record["relation"],
                subject_id,
                object_id,
                evidence_record_id=record_id,
                properties={"dataset": dataset, "basis": source, "paper_id": paper_id},
            )
            self.add_to_aggregate(dataset, object_type, subject_id, object_id, record_id, paper_id, "candidate", semantic_edge_id)

    def load_claims(self) -> None:
        for dataset, cfg in DATASETS.items():
            for curation_layer, key in (("curated", "curated_claims"), ("exploratory", "exploratory_claims")):
                path = cfg[key]
                self.input_files.append(str(path))
                for row in read_json_array(path):
                    self.add_claim_record(dataset, cfg["object_type"], cfg["claim_relation"], row, curation_layer, path)

    def add_claim_record(
        self,
        dataset: str,
        object_type: str,
        relation: str,
        row: dict,
        curation_layer: str,
        source_file: Path,
    ) -> None:
        paper_id = self.merge_paper(row, dataset, source_file)
        compound_id, compound_label = self.entity_index.resolve("Compound", row.get("compound", ""))
        object_field = "target" if object_type == "Target" else "disorder"
        object_id, object_label = self.entity_index.resolve(object_type, row.get(object_field, ""))
        if not compound_id or not object_id:
            return
        external_id = claim_external_id(dataset, row)
        record_id = f"evidence:{external_id}"
        property_fields = MECHANISTIC_PROPERTY_FIELDS if dataset == "mechanistic" else DISORDER_PROPERTY_FIELDS
        record = {
            "id": record_id,
            "external_id": external_id,
            "record_type": "claim",
            "status": curation_layer,
            "dataset": dataset,
            "paper_id": paper_id,
            "paper_doi": normalize_doi(row.get("study_doi", "")),
            "subject_id": compound_id,
            "subject_type": "Compound",
            "subject_label": compound_label,
            "object_id": object_id,
            "object_type": object_type,
            "object_label": object_label,
            "relation": relation,
            "properties": {field: row.get(field, "") for field in property_fields if normalize(row.get(field, ""))},
            "provenance": {field: row.get(field, "") for field in PROVENANCE_FIELDS if normalize(row.get(field, ""))},
            "paper": {
                "doi": normalize_doi(row.get("study_doi", "")),
                "openalex_id": normalize(row.get("openalex_id", "")),
                "title": strip_markup(row.get("study_title", "")),
                "year": as_int(row.get("study_year", "")),
                "authors": normalize(row.get("authors", "")),
            },
            "source": {
                "file": str(source_file),
                "stage": f"{curation_layer}_claims",
            },
        }
        self.evidence_records[record_id] = record
        self.add_evidence_node(record)
        self.add_edge("paper_has_claim_evidence", paper_id, record_id, evidence_record_id=record_id)
        self.add_edge("evidence_about_compound", record_id, compound_id, evidence_record_id=record_id)
        self.add_edge(f"evidence_about_{object_type.lower()}", record_id, object_id, evidence_record_id=record_id)
        semantic_edge_id = self.add_edge(
            relation,
            compound_id,
            object_id,
            evidence_record_id=record_id,
            properties={
                "dataset": dataset,
                "curation_layer": curation_layer,
                "paper_id": paper_id,
                "evidence_role": evidence_role(record.get("provenance", {})),
            },
        )
        self.add_to_aggregate(dataset, object_type, compound_id, object_id, record_id, paper_id, "claim", semantic_edge_id)

    def add_to_aggregate(
        self,
        dataset: str,
        object_type: str,
        subject_id: str,
        object_id: str,
        record_id: str,
        paper_id: str,
        contribution_kind: str,
        semantic_edge_id: str,
    ) -> None:
        domain = "compound_disorder" if object_type == "Disorder" else "compound_target"
        key = (domain, subject_id, object_id)
        aggregate = self.aggregate_records.setdefault(
            key,
            {
                "id": f"aggregate:{domain}:{digest_id(subject_id, object_id)}",
                "type": domain,
                "source_id": subject_id,
                "target_id": object_id,
                "source_label": self.nodes.get(subject_id, self.entity_index.nodes.get(subject_id, {})).get("label", ""),
                "target_label": self.nodes.get(object_id, self.entity_index.nodes.get(object_id, {})).get("label", ""),
                "target_type": object_type,
                "datasets": set(),
                "evidence_record_ids": set(),
                "semantic_edge_ids": set(),
                "candidate_paper_ids": set(),
                "claim_paper_ids": set(),
                "candidate_context_count": 0,
                "curated_claim_count": 0,
                "exploratory_claim_count": 0,
                "primary_claim_count": 0,
                "secondary_claim_count": 0,
                "non_primary_claim_count": 0,
            },
        )
        aggregate["datasets"].add(dataset)
        aggregate["evidence_record_ids"].add(record_id)
        aggregate["semantic_edge_ids"].add(semantic_edge_id)
        if contribution_kind == "candidate":
            aggregate["candidate_context_count"] += 1
            aggregate["candidate_paper_ids"].add(paper_id)
        else:
            record = self.evidence_records.get(record_id, {})
            aggregate["claim_paper_ids"].add(paper_id)
            if record.get("status") == "curated":
                aggregate["curated_claim_count"] += 1
            else:
                aggregate["exploratory_claim_count"] += 1
            role = evidence_role(record.get("provenance", {}))
            if role == "primary_evidence":
                aggregate["primary_claim_count"] += 1
            elif role == "secondary_literature":
                aggregate["secondary_claim_count"] += 1
            else:
                aggregate["non_primary_claim_count"] += 1

    def finalize_paper_nodes(self) -> None:
        for paper_id, node in self.papers.items():
            props = node["properties"]
            props.setdefault("fulltext_status", "not_converted")
            props.setdefault("abstract_present", False)
            props.setdefault("candidate_context_count", 0)
            props.setdefault("claim_evidence_count", 0)
            props.setdefault("llm_extraction_status", "not_started")
            if not node.get("label"):
                node["label"] = props.get("study_doi", "") or props.get("openalex_id", "") or paper_id
            self.nodes[paper_id] = node
        for record in self.evidence_records.values():
            paper_id = record.get("paper_id", "")
            if paper_id not in self.nodes:
                continue
            props = self.nodes[paper_id]["properties"]
            if record.get("record_type") == "literature_context":
                props["candidate_context_count"] = int(props.get("candidate_context_count", 0) or 0) + 1
            elif record.get("record_type") == "claim":
                props["claim_evidence_count"] = int(props.get("claim_evidence_count", 0) or 0) + 1
                props["llm_extraction_status"] = "claim_available"

    def finalize_entity_index(self) -> None:
        self.nodes.update(self.entity_index.nodes)
        for node_id, node in self.entity_index.nodes.items():
            key = f"{node['type']}:{compact_key(node.get('label', ''))}"
            self.entity_to_node_id[key] = node_id
            for alias in node.get("properties", {}).get("aliases", []):
                self.entity_to_node_id[f"{node['type']}:{compact_key(alias)}"] = node_id

    def aggregate_content_profile(self, aggregate: dict, candidate_paper_ids: list[str], claim_paper_ids: list[str]) -> dict:
        paper_type_counts: Counter = Counter()
        source_type_counts: Counter = Counter()
        publication_type_counts: Counter = Counter()
        journal_counts: Counter = Counter()
        study_design_counts: Counter = Counter()
        system_counts: Counter = Counter()
        evidence_level_counts: Counter = Counter()
        outcome_type_counts: Counter = Counter()
        result_direction_counts: Counter = Counter()
        assay_type_counts: Counter = Counter()
        affinity_type_counts: Counter = Counter()
        species_counts: Counter = Counter()
        basis_counts: Counter = Counter()
        paper_profiles: dict[str, dict] = {}

        for paper_id in sorted(set(candidate_paper_ids) | set(claim_paper_ids)):
            props = self.nodes.get(paper_id, {}).get("properties", {})
            paper_profiles[paper_id] = {
                "paper_type": normalize(props.get("paper_type_suggested", "")),
                "source_type": normalize(props.get("source_type_suggested", "")),
                "publication_type": normalize(props.get("publication_type", "")),
                "journal": normalize(props.get("study_journal", "")),
                "year": props.get("study_year", ""),
            }

        for record_id in aggregate["evidence_record_ids"]:
            record = self.evidence_records.get(record_id, {})
            paper_id = normalize(record.get("paper_id", ""))
            profile = paper_profiles.setdefault(
                paper_id,
                {"paper_type": "", "source_type": "", "publication_type": "", "journal": "", "year": ""},
            )
            if record.get("record_type") == "claim":
                provenance = record.get("provenance", {})
                properties = record.get("properties", {})
                if not profile["paper_type"]:
                    profile["paper_type"] = normalize(provenance.get("paper_type", ""))
                if not profile["source_type"]:
                    profile["source_type"] = normalize(provenance.get("source_type", ""))
                count_value(study_design_counts, provenance.get("study_design", ""))
                count_value(system_counts, properties.get("system", ""))
                count_value(evidence_level_counts, properties.get("evidence_level", ""))
                count_value(outcome_type_counts, properties.get("outcome_type", ""))
                count_value(result_direction_counts, properties.get("result_direction", ""))
                count_value(assay_type_counts, properties.get("assay_type", ""))
                count_value(affinity_type_counts, properties.get("affinity_type", ""))
                count_value(species_counts, properties.get("species", ""))
            elif record.get("record_type") == "literature_context":
                screening = record.get("screening", {})
                if not profile["paper_type"]:
                    profile["paper_type"] = normalize(screening.get("paper_type_suggested", ""))
                if not profile["source_type"]:
                    profile["source_type"] = normalize(screening.get("source_type_suggested", ""))
                count_value(basis_counts, record.get("basis", ""))

        years: list[int] = []
        for profile in paper_profiles.values():
            count_value(paper_type_counts, profile.get("paper_type", ""))
            count_value(source_type_counts, profile.get("source_type", ""))
            count_value(publication_type_counts, profile.get("publication_type", ""))
            count_value(journal_counts, profile.get("journal", ""))
            year = profile.get("year", "")
            if isinstance(year, int):
                years.append(year)

        profile = {
            "paper_types": top_counts(paper_type_counts),
            "source_types": top_counts(source_type_counts),
            "publication_types": top_counts(publication_type_counts),
            "top_journals": top_counts(journal_counts),
            "year_range": year_range(years),
            "study_designs": top_counts(study_design_counts),
            "systems": top_counts(system_counts),
            "evidence_levels": top_counts(evidence_level_counts),
            "context_basis": top_counts(basis_counts),
            "representative_papers": self.representative_papers(candidate_paper_ids, claim_paper_ids),
        }
        if aggregate["target_type"] == "Disorder":
            profile["outcome_types"] = top_counts(outcome_type_counts)
            profile["result_directions"] = top_counts(result_direction_counts)
        else:
            profile["assay_types"] = top_counts(assay_type_counts)
            profile["affinity_types"] = top_counts(affinity_type_counts)
            profile["species"] = top_counts(species_counts)
        return profile

    def representative_papers(self, candidate_paper_ids: list[str], claim_paper_ids: list[str], limit: int = 8) -> list[dict]:
        ranked = []
        claim_set = set(claim_paper_ids)
        for paper_id in sorted(set(candidate_paper_ids) | claim_set):
            node = self.nodes.get(paper_id, {})
            props = node.get("properties", {})
            score = 0
            if paper_id in claim_set:
                score += 1000
            if normalize(props.get("relevance_suggested", "")) == "likely_relevant":
                score += 100
            elif normalize(props.get("relevance_suggested", "")) == "possible_relevant":
                score += 50
            score += int(props.get("claim_evidence_count", 0) or 0) * 20
            score += int(props.get("candidate_context_count", 0) or 0)
            year = props.get("study_year", 0)
            year_score = year if isinstance(year, int) else 0
            ranked.append((score, year_score, paper_id, props))

        out = []
        for _, _, paper_id, props in sorted(ranked, reverse=True)[:limit]:
            out.append(
                {
                    "paper_id": paper_id,
                    "doi": normalize(props.get("study_doi", "")),
                    "title": strip_markup(props.get("study_title", "")) or self.nodes.get(paper_id, {}).get("label", ""),
                    "year": props.get("study_year", ""),
                    "journal": normalize(props.get("study_journal", "")),
                    "paper_type": normalize(props.get("paper_type_suggested", "")),
                    "source_type": normalize(props.get("source_type_suggested", "")),
                    "relevance": normalize(props.get("relevance_suggested", "")),
                    "has_claim": paper_id in claim_set,
                }
            )
        return out

    def materialized_aggregates(self) -> list[dict]:
        rows = []
        for aggregate in self.aggregate_records.values():
            candidate_paper_ids = sorted(aggregate["candidate_paper_ids"])
            claim_paper_ids = sorted(aggregate["claim_paper_ids"])
            candidate_fulltext_count = sum(
                1
                for paper_id in candidate_paper_ids
                if self.nodes.get(paper_id, {}).get("properties", {}).get("fulltext_status") == "converted"
            )
            claim_fulltext_count = sum(
                1
                for paper_id in claim_paper_ids
                if self.nodes.get(paper_id, {}).get("properties", {}).get("fulltext_status") == "converted"
            )
            data_status = {
                "candidate_context_count": aggregate["candidate_context_count"],
                "candidate_paper_count": len(candidate_paper_ids),
                "candidate_fulltext_converted_paper_count": candidate_fulltext_count,
                "claim_paper_count": len(claim_paper_ids),
                "claim_fulltext_converted_paper_count": claim_fulltext_count,
                "curated_claim_count": aggregate["curated_claim_count"],
                "exploratory_claim_count": aggregate["exploratory_claim_count"],
                "primary_claim_count": aggregate["primary_claim_count"],
                "secondary_claim_count": aggregate["secondary_claim_count"],
                "non_primary_claim_count": aggregate["non_primary_claim_count"],
            }
            row = {
                "id": aggregate["id"],
                "type": aggregate["type"],
                "source_id": aggregate["source_id"],
                "source_label": self.nodes.get(aggregate["source_id"], {}).get("label", aggregate["source_label"]),
                "target_id": aggregate["target_id"],
                "target_label": self.nodes.get(aggregate["target_id"], {}).get("label", aggregate["target_label"]),
                "target_type": aggregate["target_type"],
                "datasets": sorted(aggregate["datasets"]),
                "status": "curated" if aggregate["curated_claim_count"] else "provisional",
                "candidate_context_count": aggregate["candidate_context_count"],
                "candidate_paper_count": len(candidate_paper_ids),
                "candidate_fulltext_converted_paper_count": candidate_fulltext_count,
                "claim_paper_count": len(claim_paper_ids),
                "claim_fulltext_converted_paper_count": claim_fulltext_count,
                "curated_claim_count": aggregate["curated_claim_count"],
                "exploratory_claim_count": aggregate["exploratory_claim_count"],
                "primary_claim_count": aggregate["primary_claim_count"],
                "secondary_claim_count": aggregate["secondary_claim_count"],
                "non_primary_claim_count": aggregate["non_primary_claim_count"],
                "evidence_record_ids": sorted(aggregate["evidence_record_ids"]),
                "semantic_edge_ids": sorted(edge for edge in aggregate["semantic_edge_ids"] if edge),
                "candidate_paper_ids": candidate_paper_ids,
                "claim_paper_ids": claim_paper_ids,
                "data_status": data_status,
                "content_profile": self.aggregate_content_profile(aggregate, candidate_paper_ids, claim_paper_ids),
            }
            rows.append(row)
        return sorted(rows, key=lambda r: (r["type"], r["source_label"], r["target_label"]))

    def semantic_graph_view(self, aggregates: list[dict]) -> dict:
        entity_ids = set()
        for edge in aggregates:
            entity_ids.add(edge["source_id"])
            entity_ids.add(edge["target_id"])
        nodes = [
            compact_node_for_view(self.nodes[node_id])
            for node_id in sorted(entity_ids)
            if node_id in self.nodes
        ]
        edges = []
        for edge in aggregates:
            edges.append(
                {
                    "id": edge["id"],
                    "type": edge["type"],
                    "source": edge["source_id"],
                    "target": edge["target_id"],
                    "status": edge["status"],
                    "candidate_paper_count": edge["candidate_paper_count"],
                    "curated_claim_count": edge["curated_claim_count"],
                    "primary_claim_count": edge["primary_claim_count"],
                    "secondary_claim_count": edge["secondary_claim_count"],
                    "candidate_fulltext_converted_paper_count": edge["candidate_fulltext_converted_paper_count"],
                    "claim_paper_count": edge["claim_paper_count"],
                    "datasets": edge["datasets"],
                    "content_profile": edge["content_profile"],
                    "data_status": edge["data_status"],
                    "evidence_record_ids": edge["evidence_record_ids"][:50],
                    "candidate_paper_ids": edge["candidate_paper_ids"][:50],
                    "claim_paper_ids": edge["claim_paper_ids"][:50],
                }
            )
        return {
            "contract_version": KG_VERSION,
            "view": "semantic_graph",
            "description": "Aggregated compound-disorder and compound-target graph for default visualization.",
            "generated_at": now_utc(),
            "nodes": nodes,
            "edges": edges,
        }

    def literature_graph_view(self) -> dict:
        relevant_paper_ids = {
            node_id
            for node_id, node in self.nodes.items()
            if node.get("type") == "Paper" and paper_is_relevant_for_view(node.get("properties", {}))
        }
        edge_rows = []
        entity_ids = set()
        for edge in self.edges.values():
            if edge.get("source_id") not in relevant_paper_ids:
                continue
            if not normalize(edge.get("type", "")).startswith("mentions_"):
                continue
            entity_ids.add(edge["target_id"])
            edge_rows.append(
                {
                    "id": edge["id"],
                    "type": edge["type"],
                    "source": edge["source_id"],
                    "target": edge["target_id"],
                    "evidence_record_ids": edge.get("evidence_record_ids", [])[:20],
                    "properties": edge.get("properties", {}),
                }
            )
        nodes = [compact_node_for_view(self.nodes[paper_id]) for paper_id in sorted(relevant_paper_ids)]
        nodes.extend(compact_node_for_view(self.nodes[node_id]) for node_id in sorted(entity_ids) if node_id in self.nodes)
        return {
            "contract_version": KG_VERSION,
            "view": "literature_graph",
            "description": "Relevant or possibly relevant papers linked to mentioned compounds and entities.",
            "generated_at": now_utc(),
            "nodes": nodes,
            "edges": sorted(edge_rows, key=lambda r: (r["source"], r["target"], r["type"])),
        }

    def pipeline_status_view(self) -> dict:
        counters: dict[str, Counter] = defaultdict(Counter)
        prisma_rows: dict[str, list[dict]] = defaultdict(list)
        for node in self.nodes.values():
            if node.get("type") != "Paper":
                continue
            props = node.get("properties", {})
            for dataset in props.get("datasets", []):
                counters[f"{dataset}:relevance"][normalize(props.get("relevance_suggested", "")) or "unknown"] += 1
                counters[f"{dataset}:screening"][normalize(props.get("screening_status", "")) or "unknown"] += 1
                counters[f"{dataset}:pdf"][normalize(props.get("pdf_status", "")) or "unknown"] += 1
                counters[f"{dataset}:fulltext"][normalize(props.get("fulltext_status", "")) or "unknown"] += 1
                counters[f"{dataset}:llm_extraction"][normalize(props.get("llm_extraction_status", "")) or "unknown"] += 1
                prisma_rows[dataset].append(props)
        return {
            "contract_version": KG_VERSION,
            "view": "pipeline_status",
            "generated_at": now_utc(),
            "counts": {key: dict(counter) for key, counter in sorted(counters.items())},
            "prisma_flow": {
                dataset: prisma_flow_for_dataset(dataset, rows)
                for dataset, rows in sorted(prisma_rows.items())
            },
        }

    def literature_gap_matrix(self, aggregates: list[dict]) -> dict:
        records = []
        for edge in aggregates:
            records.append(
                {
                    "compound_id": edge["source_id"],
                    "compound": edge["source_label"],
                    "object_id": edge["target_id"],
                    "object": edge["target_label"],
                    "object_type": edge["target_type"],
                    "relation_type": edge["type"],
                    "candidate_paper_count": edge["candidate_paper_count"],
                    "candidate_fulltext_converted_paper_count": edge["candidate_fulltext_converted_paper_count"],
                    "curated_claim_count": edge["curated_claim_count"],
                    "primary_claim_count": edge["primary_claim_count"],
                    "secondary_claim_count": edge["secondary_claim_count"],
                    "claim_paper_count": edge["claim_paper_count"],
                    "gap_status": gap_status(edge),
                    "content_profile": edge["content_profile"],
                    "data_status": edge["data_status"],
                }
            )
        return {
            "contract_version": KG_VERSION,
            "generated_at": now_utc(),
            "records": sorted(records, key=lambda r: (r["relation_type"], r["compound"], r["object"])),
        }

    def payloads(self) -> dict:
        aggregates = self.materialized_aggregates()
        return {
            "nodes": sorted(self.nodes.values(), key=node_sort_key),
            "edges": sorted(self.edges.values(), key=edge_sort_key),
            "evidence_records": sorted(self.evidence_records.values(), key=lambda r: r["id"]),
            "aggregates": aggregates,
            "semantic_graph": self.semantic_graph_view(aggregates),
            "literature_graph": self.literature_graph_view(),
            "pipeline_status": self.pipeline_status_view(),
            "literature_gap_matrix": self.literature_gap_matrix(aggregates),
            "indexes": {
                "doi_to_paper_id": dict(sorted(self.doi_to_paper_id.items())),
                "entity_to_node_id": dict(sorted(self.entity_to_node_id.items())),
                "edge_to_evidence_ids": {
                    edge_id: sorted(ids)
                    for edge_id, ids in sorted(self.edge_to_evidence.items())
                    if ids
                },
            },
            "manifest": {
                "contract_version": KG_VERSION,
                "generated_at": now_utc(),
                "input_files": sorted(set(self.input_files)),
                "warnings": self.warnings,
                "counts": {
                    "nodes": len(self.nodes),
                    "edges": len(self.edges),
                    "evidence_records": len(self.evidence_records),
                    "aggregate_edges": len(aggregates),
                    "paper_nodes": sum(1 for node in self.nodes.values() if node.get("type") == "Paper"),
                    "compound_nodes": sum(1 for node in self.nodes.values() if node.get("type") == "Compound"),
                    "disorder_nodes": sum(1 for node in self.nodes.values() if node.get("type") == "Disorder"),
                    "target_nodes": sum(1 for node in self.nodes.values() if node.get("type") == "Target"),
                },
            },
        }


def strongest_pdf_status(left: str, right: str) -> str:
    rank = {
        "": 0,
        "not_downloaded": 1,
        "needs_download": 1,
        "failed": 1,
        "pdf_url_known": 2,
        "already_present": 3,
        "downloaded": 4,
    }
    return right if rank.get(right, 1) > rank.get(left, 1) else left


def evidence_role(provenance: dict) -> str:
    source_type = normalize(provenance.get("source_type", ""))
    source_family = normalize(provenance.get("source_family", ""))
    paper_type = normalize(provenance.get("paper_type", ""))
    access_level = normalize(provenance.get("access_level", ""))
    if source_type == "primary_study" and paper_type == "primary_results" and access_level != "secondary_summary":
        return "primary_evidence"
    if source_family == "evidence_synthesis" or source_type in {"secondary_evidence", "review", "meta_analysis"}:
        return "secondary_literature"
    if paper_type in {"systematic_review", "meta_analysis", "review"}:
        return "secondary_literature"
    return "non_primary_context"


def paper_is_relevant_for_view(props: dict) -> bool:
    return (
        normalize(props.get("relevance_suggested", "")) in RELEVANT_RELEVANCE
        or normalize(props.get("screening_status", "")) in INCLUDED_SCREENING
        or int(props.get("claim_evidence_count", 0) or 0) > 0
    )


def count_value(counter: Counter, value: object) -> None:
    text = strip_markup(value)
    if text:
        counter[text] += 1


def top_counts(counter: Counter, limit: int = 8) -> list[dict]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def status_label(value: str) -> str:
    text = normalize(value).replace("_", " ")
    return text[:1].upper() + text[1:] if text else "Unknown"


def labeled_reason_counts(counter: Counter, labels: dict[str, str], order: tuple[str, ...]) -> list[dict]:
    ordered_keys = [key for key in order if counter.get(key)]
    ordered_keys.extend(sorted(key for key in counter if key not in set(ordered_keys) and counter[key]))
    return [
        {
            "key": key,
            "label": labels.get(key, status_label(key)),
            "count": counter[key],
        }
        for key in ordered_keys
    ]


def prisma_flow_for_dataset(dataset: str, props_rows: Iterable[dict]) -> dict:
    rows = list(props_rows)
    likely_rows = [
        props
        for props in rows
        if normalize(props.get("relevance_suggested", "")) == "likely_relevant"
    ]
    not_likely_rows = [
        props
        for props in rows
        if normalize(props.get("relevance_suggested", "")) != "likely_relevant"
    ]
    retrieved_rows = [
        props
        for props in likely_rows
        if normalize(props.get("pdf_status", "")) == "downloaded"
    ]
    converted_rows = [
        props
        for props in retrieved_rows
        if normalize(props.get("fulltext_status", "")) == "converted"
    ]
    extracted_rows = [
        props
        for props in converted_rows
        if normalize(props.get("llm_extraction_status", "")) == "claim_available"
    ]

    screening_reasons = Counter(normalize(props.get("screening_status", "")) or "unknown" for props in not_likely_rows)
    retrieval_reasons = Counter(
        normalize(props.get("pdf_status", "")) or "unknown"
        for props in likely_rows
        if normalize(props.get("pdf_status", "")) != "downloaded"
    )
    conversion_reasons = Counter(
        normalize(props.get("fulltext_status", "")) or "unknown"
        for props in retrieved_rows
        if normalize(props.get("fulltext_status", "")) != "converted"
    )
    extraction_reasons = Counter(
        normalize(props.get("llm_extraction_status", "")) or "unknown"
        for props in converted_rows
        if normalize(props.get("llm_extraction_status", "")) != "claim_available"
    )

    return {
        "dataset": dataset,
        "unit": "paper-context records",
        "steps": {
            "records_identified": {"label": "Records identified", "count": len(rows)},
            "records_screened": {"label": "Records screened", "count": len(rows)},
            "reports_sought": {"label": "Reports sought for retrieval", "count": len(likely_rows)},
            "reports_retrieved": {"label": "Reports retrieved", "count": len(retrieved_rows)},
            "reports_assessed": {"label": "Reports assessed for eligibility", "count": len(converted_rows)},
            "included": {"label": "Records included in KG evidence layer", "count": len(extracted_rows)},
        },
        "side_boxes": {
            "removed_before_screening": {
                "label": "Records removed before screening",
                "count": 0,
                "reasons": [],
                "note": "No separate de-duplication or pre-screen removal step is currently tracked.",
            },
            "records_excluded": {
                "label": "Records not advanced to retrieval",
                "count": len(not_likely_rows),
                "reasons": labeled_reason_counts(
                    screening_reasons,
                    PRISMA_SCREENING_REASON_LABELS,
                    (
                        "excluded_low_signal",
                        "needs_context_review",
                        "included_synthesized_context",
                        "needs_metadata_or_manual_screen",
                        "unknown",
                    ),
                ),
            },
            "reports_not_retrieved": {
                "label": "Not retrieved for full-text extraction",
                "count": len(likely_rows) - len(retrieved_rows),
                "reasons": labeled_reason_counts(
                    retrieval_reasons,
                    PRISMA_RETRIEVAL_REASON_LABELS,
                    (
                        "not_open_access",
                        "no_pdf_url",
                        "download_failed",
                        "skipped",
                        "missing_local_pdf",
                        "invalid_pdf_existing",
                        "invalid_pdf_content",
                        "not_downloaded",
                        "pdf_url_known",
                        "unknown",
                    ),
                ),
            },
            "reports_not_converted": {
                "label": "Reports not converted",
                "count": len(retrieved_rows) - len(converted_rows),
                "reasons": labeled_reason_counts(
                    conversion_reasons,
                    PRISMA_CONVERSION_REASON_LABELS,
                    ("not_converted", "artifact_present", "unknown"),
                ),
            },
            "reports_not_extracted": {
                "label": "Reports not yet extracted",
                "count": len(converted_rows) - len(extracted_rows),
                "reasons": labeled_reason_counts(
                    extraction_reasons,
                    PRISMA_EXTRACTION_REASON_LABELS,
                    ("not_started", "unknown"),
                ),
            },
        },
    }


def year_range(years: list[int]) -> dict:
    if not years:
        return {}
    return {
        "min": min(years),
        "max": max(years),
        "count": len(years),
    }


def compact_node_for_view(node: dict) -> dict:
    props = node.get("properties", {})
    out = {
        "id": node["id"],
        "type": node["type"],
        "label": node.get("label", ""),
        "properties": {},
    }
    for field in (
        "datasets",
        "study_doi",
        "study_year",
        "study_journal",
        "relevance_suggested",
        "screening_status",
        "source_type_suggested",
        "paper_type_suggested",
        "pdf_status",
        "fulltext_status",
        "fulltext_backend",
        "candidate_context_count",
        "claim_evidence_count",
        "registry_status",
        "aliases",
    ):
        if field in props and props[field] not in ("", [], None):
            out["properties"][field] = props[field]
    return out


def gap_status(edge: dict) -> str:
    if edge["curated_claim_count"] > 0:
        return "has_curated_claims"
    if edge["candidate_fulltext_converted_paper_count"] > 0:
        return "ready_for_extraction"
    if edge["candidate_paper_count"] > 0:
        return "needs_fulltext_or_extraction"
    return "no_signal"


def schema_payload() -> dict:
    return {
        "contract_version": KG_VERSION,
        "record_types": {
            "node": {
                "required": ["id", "type", "label", "properties"],
                "types": ["Paper", "Compound", "Disorder", "Target", "EvidenceRecord"],
            },
            "edge": {
                "required": ["id", "type", "source_id", "target_id", "properties"],
                "optional": ["evidence_record_ids"],
            },
            "evidence_record": {
                "required": [
                    "id",
                    "record_type",
                    "status",
                    "dataset",
                    "paper_id",
                    "subject_id",
                    "object_id",
                    "relation",
                    "source",
                ],
                "record_types": ["literature_context", "claim"],
            },
        },
    }


def write_outputs(payloads: dict, out_dir: Path) -> dict:
    outputs = {}
    outputs["schema"] = str(out_dir / "schema" / "kg_projection.schema.json")
    write_json(Path(outputs["schema"]), schema_payload())

    outputs["nodes"] = str(out_dir / "canonical" / "nodes.jsonl")
    outputs["edges"] = str(out_dir / "canonical" / "edges.jsonl")
    outputs["evidence_records"] = str(out_dir / "canonical" / "evidence_records.jsonl")
    write_jsonl(Path(outputs["nodes"]), payloads["nodes"])
    write_jsonl(Path(outputs["edges"]), payloads["edges"])
    write_jsonl(Path(outputs["evidence_records"]), payloads["evidence_records"])

    aggregate_edges = payloads["aggregates"]
    outputs["aggregate_edges"] = str(out_dir / "aggregates" / "aggregate_edges.jsonl")
    outputs["compound_disorder_edges"] = str(out_dir / "aggregates" / "compound_disorder_edges.jsonl")
    outputs["compound_target_edges"] = str(out_dir / "aggregates" / "compound_target_edges.jsonl")
    write_jsonl(Path(outputs["aggregate_edges"]), aggregate_edges)
    write_jsonl(Path(outputs["compound_disorder_edges"]), [row for row in aggregate_edges if row["type"] == "compound_disorder"])
    write_jsonl(Path(outputs["compound_target_edges"]), [row for row in aggregate_edges if row["type"] == "compound_target"])
    outputs["literature_gap_matrix"] = str(out_dir / "aggregates" / "literature_gap_matrix.json")
    write_json(Path(outputs["literature_gap_matrix"]), payloads["literature_gap_matrix"])

    for name, payload in (
        ("semantic_graph", payloads["semantic_graph"]),
        ("literature_graph", payloads["literature_graph"]),
        ("pipeline_status_graph", payloads["pipeline_status"]),
    ):
        outputs[name] = str(out_dir / "views" / f"{name}.json")
        write_json(Path(outputs[name]), payload)

    for name, payload in payloads["indexes"].items():
        outputs[name] = str(out_dir / "indexes" / f"{name}.json")
        write_json(Path(outputs[name]), payload)

    manifest = dict(payloads["manifest"])
    manifest["outputs"] = outputs
    outputs["manifest"] = str(out_dir / "manifests" / "build_manifest.json")
    write_json(Path(outputs["manifest"]), manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the file-based KG projection")
    parser.add_argument("--out-dir", default=str(ROOT / "data" / "kg"), help="Output directory for generated KG files")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    builder = KgBuilder(ROOT)
    payloads = builder.build()
    manifest = write_outputs(payloads, out_dir)

    print(f"KG outputs: {out_dir}")
    for key, value in manifest["counts"].items():
        print(f"- {key}: {value}")
    print(f"Manifest: {out_dir / 'manifests' / 'build_manifest.json'}")
    if manifest["warnings"]:
        print(f"Warnings: {len(manifest['warnings'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
