#!/usr/bin/env python3
"""Convert paper-centered review bundles into the canonical KG evidence-row format.

Each extracted relationship remains one evidence row. Its complete statement,
anchors, evidence locators, and paper frame are preserved in the raw row. The
overview graph receives one subject and one principal object, while secondary
anchors remain attached to the relationship for paper-detail display.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import re
import sys

import pandas as pd

try:
    from pipeline.extract.io_utils import normalize, read_jsonl, write_json
    from pipeline.kg.project_review_relationship_bundles import label_key, registry_index
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.io_utils import normalize, read_jsonl, write_json
    from pipeline.kg.project_review_relationship_bundles import label_key, registry_index


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUNDLES = (
    ROOT
    / "data"
    / "processed"
    / "extraction"
    / "review_relationship_runs"
    / "review_relationships_v2_main_20260712"
    / "paper_relationship_bundles.jsonl"
)
DEFAULT_TASKS = DEFAULT_BUNDLES.parent / "async_batches" / "batch_001_tasks.jsonl"
DEFAULT_REGISTRY = ROOT / "data" / "curated" / "entity_registry.json"
DEFAULT_CANDIDATES = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"

CANONICAL_METADATA_FIELDS = (
    "openalex_id",
    "pmid",
    "pmcid",
    "authors",
    "study_journal",
    "publication_type",
    "publication_date",
    "publisher",
    "journal_issn",
    "journal_eissn",
    "language",
    "mesh_terms",
    "keywords",
    "funders",
    "grant_ids",
    "trial_registry_ids",
    "open_access_is_oa",
    "open_access_status",
    "open_access_url",
)

REVIEW_TYPES = {
    "review",
    "systematic_review",
    "scoping_review",
    "narrative_review",
    "literature_review",
    "umbrella_review",
}
SUBJECT_ROLES = {"compound", "compound_class", "intervention", "co_intervention"}
OBJECT_ROLE_ORDER = {
    "safety_event": 10,
    "condition": 20,
    "outcome": 30,
    "target": 40,
    "pathway_or_process": 50,
    "brain_system": 60,
    "cognitive_or_behavioral_construct": 70,
    "subjective_construct": 80,
    "exposure_or_pk_parameter": 90,
    "intervention_context": 100,
    "public_health_topic": 110,
    "research_topic": 120,
    "population": 130,
    "comparator": 140,
    "other": 150,
    "compound": 160,
    "compound_class": 170,
    "intervention": 180,
    "co_intervention": 190,
}
ROLE_GRAPH_MAPPING = {
    "condition": ("clinical_outcome", "condition_indication", "condition_or_indication"),
    "outcome": ("clinical_outcome", "symptom_problem", "outcome_measure"),
    "safety_event": ("safety_tolerability", "safety_adverse_event", "safety_event_or_measure"),
    "target": ("molecular_target", "target", "target"),
    "pathway_or_process": ("molecular_pathway_readout", "pathway_process", "pathway_or_process"),
    "brain_system": ("brain_system", "brain_network", "brain_network"),
    "cognitive_or_behavioral_construct": (
        "cognitive_behavioral",
        "cognitive_behavioral_construct",
        "graph_construct_label",
    ),
    "subjective_construct": (
        "subjective_experience",
        "subjective_experience_construct",
        "subjective_construct",
    ),
    "exposure_or_pk_parameter": (
        "pharmacokinetics_exposure",
        "pharmacokinetic_parameter",
        "pk_or_exposure_parameter",
    ),
    "intervention_context": ("intervention_context", "intervention_component", "context_component"),
    "public_health_topic": ("real_world_public_health", "public_health_measure", "public_health_measure"),
    "research_topic": ("general_topic_coverage", "public_health_measure", "public_health_measure"),
    "population": ("clinical_outcome", "condition_indication", "condition_or_indication"),
    "comparator": ("intervention_context", "intervention_component", "context_component"),
    "compound": ("molecular_target", "compound", "graph_entity_label"),
    "compound_class": ("general_topic_coverage", "compound", "graph_entity_label"),
    "intervention": ("intervention_context", "intervention_component", "context_component"),
    "co_intervention": ("intervention_context", "intervention_component", "context_component"),
    "other": ("general_topic_coverage", "public_health_measure", "public_health_measure"),
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalized_doi(value: object) -> str:
    return normalize(value).lower()


def json_array(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON array: {path}")
    return [row for row in payload if isinstance(row, dict)]


def write_json_array(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def paper_type_for(task: dict) -> str:
    metadata = task.get("paper_metadata", {}) if isinstance(task.get("paper_metadata"), dict) else {}
    value = normalize(metadata.get("review_type", ""))
    return value if value in REVIEW_TYPES else "review"


def subject_for_relationship(
    relationship: dict,
    frame: dict,
    compound_registry: dict[tuple[str, str], str],
) -> tuple[dict, set[int]]:
    anchors = [anchor for anchor in relationship.get("anchors", []) if isinstance(anchor, dict)]
    candidates = [(index, anchor) for index, anchor in enumerate(anchors) if normalize(anchor.get("role", "")) in SUBJECT_ROLES]
    form = normalize(relationship.get("graph_form", ""))
    combine = form in {"combination", "interaction"} and len(candidates) > 1
    selected = candidates if combine else candidates[:1]

    if not selected:
        primary = [normalize(value) for value in frame.get("primary_subjects", []) if normalize(value)]
        label = primary[0] if primary else "Psychedelic research"
        return {
            "label": label,
            "kind": "paper_topic",
            "atomic_compound_candidate": "",
            "source_field": "paper_frame.primary_subjects",
        }, set()

    labels = [normalize(anchor.get("label", "")) for _, anchor in selected]
    selected_indexes = {index for index, _ in selected}
    if combine:
        return {
            "label": " + ".join(labels),
            "kind": "compound_combination" if form == "combination" else "treatment_regimen",
            "atomic_compound_candidate": next(
                (compound_registry.get(("compounds", label_key(label)), "") for label in labels if compound_registry.get(("compounds", label_key(label)), "")),
                "",
            ),
            "source_field": "anchors",
        }, selected_indexes

    index, anchor = selected[0]
    label = labels[0]
    role = normalize(anchor.get("role", ""))
    anchor_type = normalize(anchor.get("anchor_type", ""))
    canonical = compound_registry.get(("compounds", label_key(label)), "")
    if canonical:
        kind = "atomic_compound"
        label = canonical
    elif role == "compound_class" or anchor_type == "compound_class" or form == "class":
        kind = "compound_class"
    elif role in {"intervention", "co_intervention"}:
        kind = "treatment_regimen" if re.search(r"\b(therap|treatment|regimen|session|psychotherap)\w*\b", label, re.I) else "exposure_context"
    else:
        kind = "atomic_compound"
    return {
        "label": label,
        "kind": kind,
        "atomic_compound_candidate": canonical,
        "source_field": "anchors",
    }, {index}


def object_for_relationship(relationship: dict, subject_indexes: set[int]) -> dict:
    anchors = [anchor for anchor in relationship.get("anchors", []) if isinstance(anchor, dict)]
    choices = [
        (OBJECT_ROLE_ORDER.get(normalize(anchor.get("role", "")), 999), index, anchor)
        for index, anchor in enumerate(anchors)
        if index not in subject_indexes and normalize(anchor.get("label", ""))
    ]
    if not choices:
        choices = [
            (OBJECT_ROLE_ORDER.get(normalize(anchor.get("role", "")), 999), index, anchor)
            for index, anchor in enumerate(anchors)
            if normalize(anchor.get("label", ""))
        ]
    if not choices:
        return {"role": "other", "label": normalize(relationship.get("relation_phrase", "")) or "Review relationship"}
    return min(choices, key=lambda item: (item[0], item[1]))[2]


def evidence_locations(relationship: dict) -> tuple[str, str, str]:
    locators = [item for item in relationship.get("evidence_locators", []) if isinstance(item, dict)]
    locations = " | ".join(dict.fromkeys(normalize(item.get("location", "")) for item in locators if normalize(item.get("location", ""))))
    locator_text = " | ".join(dict.fromkeys(normalize(item.get("locator", "")) for item in locators if normalize(item.get("locator", ""))))
    support = " | ".join(dict.fromkeys(normalize(item.get("supporting_text", "")) for item in locators if normalize(item.get("supporting_text", ""))))
    return locations, locator_text, support


def relationship_row(bundle_row: dict, task: dict, relationship: dict, relationship_index: int, compound_registry: dict) -> dict:
    result = bundle_row.get("result", {}) if isinstance(bundle_row.get("result"), dict) else {}
    frame = result.get("paper_frame", {}) if isinstance(result.get("paper_frame"), dict) else {}
    metadata = task.get("paper_metadata", {}) if isinstance(task.get("paper_metadata"), dict) else {}
    subject, subject_indexes = subject_for_relationship(relationship, frame, compound_registry)
    object_anchor = object_for_relationship(relationship, subject_indexes)
    object_role = normalize(object_anchor.get("role", "")) or "other"
    object_label = normalize(object_anchor.get("label", ""))
    domain, entity_kind, role_field = ROLE_GRAPH_MAPPING.get(object_role, ROLE_GRAPH_MAPPING["other"])
    model_domains = [normalize(value) for value in relationship.get("domain_labels", []) if normalize(value)]
    if object_role == "other" and model_domains:
        domain = model_domains[0]
    location, locator, supporting_quote = evidence_locations(relationship)
    prominence = normalize(relationship.get("paper_prominence", ""))
    requested_eligibility = normalize(relationship.get("graph_eligibility", ""))
    admission = "main_graph" if requested_eligibility == "main_graph" and prominence in {"paper_defining", "major_supporting"} else "paper_detail"
    statement = normalize(relationship.get("relationship_statement", ""))
    limitations = [normalize(value) for value in relationship.get("limitations", []) if normalize(value)]
    anchors = [anchor for anchor in relationship.get("anchors", []) if isinstance(anchor, dict)]
    row = {
        "study_doi": normalized_doi(bundle_row.get("study_doi", "")),
        "study_title": normalize(bundle_row.get("study_title", "")) or normalize(metadata.get("study_title", "")),
        "study_year": normalize(metadata.get("study_year", "")),
        "study_journal": normalize(metadata.get("study_journal", "")),
        "publication_type": normalize(metadata.get("publication_type", "")),
        "abstract": normalize(metadata.get("abstract", "")),
        "source_access_level": normalize(bundle_row.get("text_depth", "")),
        "access_level": normalize(bundle_row.get("text_depth", "")),
        "paper_type": paper_type_for(task),
        "source_type": paper_type_for(task),
        "source_family": "secondary_literature",
        "paper_assessment_route": "secondary_literature",
        "source_item_type": "review_relationship",
        "source_item_index": relationship_index,
        "source_item_id": normalize(relationship.get("item_id", "")),
        "review_extraction_method": "paper_centered_one_pass_v2",
        "evidence_type": "secondary_literature",
        "domain": domain,
        "domain_route": domain,
        "dataset": domain,
        "claim_type": normalize(relationship.get("relationship_kind", "")),
        "coverage_type": normalize(relationship.get("relationship_kind", "")),
        "coverage_focus": prominence,
        "finding_summary": statement,
        "support": statement,
        "notes": "; ".join(limitations),
        "result_direction": normalize(relationship.get("direction_or_tone", "")),
        "evidence_level": normalize(relationship.get("evidence_stratum", "")),
        "evidence_location": location,
        "evidence_locator": locator,
        "supporting_quote": supporting_quote,
        "graph_subject_label": subject["label"],
        "graph_subject_kind": subject["kind"],
        "graph_subject_source_field": subject["source_field"],
        "atomic_compound_candidate": subject["atomic_compound_candidate"],
        "compound": subject["label"],
        "graph_entity_label": object_label,
        "kg_entity_kind_override": entity_kind,
        "entity_role": object_role,
        "graph_admission_status": admission,
        "graph_admission_reason": "review_relationship_prominence" if admission == "main_graph" else "review_relationship_paper_detail",
        "relationship_graph_form": normalize(relationship.get("graph_form", "")),
        "relationship_anchors_json": json.dumps(anchors, ensure_ascii=False),
        "relationship_domain_labels_json": json.dumps(model_domains, ensure_ascii=False),
        "covers_major_aspect_ids_json": json.dumps(relationship.get("covers_major_aspect_ids", []), ensure_ascii=False),
        "centrality_basis_json": json.dumps(relationship.get("centrality_basis", []), ensure_ascii=False),
        "paper_frame_json": json.dumps(frame, ensure_ascii=False),
        "bundle_summary": normalize(result.get("bundle_summary", "")),
        "full_text_priority": normalize(result.get("full_text_priority", "")),
    }
    row[role_field] = object_label
    return row


def convert_bundles(bundle_rows: list[dict], task_rows: list[dict], registry_payload: dict) -> tuple[list[dict], dict]:
    tasks = {normalized_doi(row.get("study_doi", "")): row for row in task_rows}
    compound_registry = registry_index(registry_payload)
    evidence_rows: list[dict] = []
    skipped: Counter = Counter()
    for bundle in bundle_rows:
        if normalize(bundle.get("status", "")) != "ok":
            skipped[normalize(bundle.get("status", "")) or "missing_status"] += 1
            continue
        doi = normalized_doi(bundle.get("study_doi", ""))
        task = tasks.get(doi)
        if task is None:
            skipped["missing_task"] += 1
            continue
        result = bundle.get("result", {}) if isinstance(bundle.get("result"), dict) else {}
        for index, relationship in enumerate(result.get("relationships", []), start=1):
            if isinstance(relationship, dict):
                evidence_rows.append(relationship_row(bundle, task, relationship, index, compound_registry))
    report = {
        "schema_version": "review_relationship_evidence_conversion_v1",
        "generated_at_utc": now_utc(),
        "counts": {
            "bundle_rows": len(bundle_rows),
            "papers_converted": len({row["study_doi"] for row in evidence_rows}),
            "relationship_rows": len(evidence_rows),
        },
        "by_text_depth": dict(Counter(row["access_level"] for row in evidence_rows)),
        "by_prominence": dict(Counter(row["coverage_focus"] for row in evidence_rows)),
        "by_graph_admission": dict(Counter(row["graph_admission_status"] for row in evidence_rows)),
        "by_subject_kind": dict(Counter(row["graph_subject_kind"] for row in evidence_rows)),
        "by_entity_kind": dict(Counter(row["kg_entity_kind_override"] for row in evidence_rows)),
        "skipped": dict(skipped),
    }
    return evidence_rows, report


def legacy_review_row(row: dict) -> bool:
    item_type = normalize(row.get("source_item_type", ""))
    paper_type = normalize(row.get("paper_type", ""))
    method = normalize(row.get("review_extraction_method", ""))
    return item_type == "review_coverage_item" or (paper_type in REVIEW_TYPES and method != "paper_centered_one_pass_v2")


def enrich_canonical_metadata(rows: list[dict], candidate_rows: list[dict]) -> int:
    candidates = {
        normalized_doi(row.get("doi", "")): row
        for row in candidate_rows
        if normalized_doi(row.get("doi", ""))
    }
    matched = 0
    seen: set[str] = set()
    for row in rows:
        doi = normalized_doi(row.get("study_doi", ""))
        candidate = candidates.get(doi)
        if not candidate:
            continue
        if doi not in seen:
            matched += 1
            seen.add(doi)
        row["study_title"] = normalize(candidate.get("study_title", "")) or row.get("study_title", "")
        row["study_year"] = normalize(candidate.get("study_year", "")) or row.get("study_year", "")
        row["abstract"] = normalize(candidate.get("abstract", "")) or row.get("abstract", "")
        for field in CANONICAL_METADATA_FIELDS:
            value = candidate.get(field, "")
            if field == "open_access_is_oa" and isinstance(value, bool):
                row[field] = value
            else:
                row[field] = normalize(value)
    return matched


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundles-jsonl", type=Path, default=DEFAULT_BUNDLES)
    parser.add_argument("--tasks-jsonl", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--registry-json", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--candidate-parquet", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--base-evidence-json", type=Path, default=None)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bundles = read_jsonl(args.bundles_jsonl)
    tasks = read_jsonl(args.tasks_jsonl)
    registry_payload = json.loads(args.registry_json.read_text(encoding="utf-8"))
    review_rows, report = convert_bundles(bundles, tasks, registry_payload)
    candidate_rows = pd.read_parquet(args.candidate_parquet).to_dict("records")
    report["counts"]["papers_with_canonical_metadata"] = enrich_canonical_metadata(review_rows, candidate_rows)
    base_rows = json_array(args.base_evidence_json) if args.base_evidence_json else []
    kept_base = [row for row in base_rows if not legacy_review_row(row)]
    removed = len(base_rows) - len(kept_base)
    combined = [*kept_base, *review_rows]
    write_json_array(args.out_json, combined)
    report["replacement"] = {
        "base_rows": len(base_rows),
        "legacy_review_rows_removed": removed,
        "base_rows_kept": len(kept_base),
        "paper_centered_review_rows_added": len(review_rows),
        "combined_rows": len(combined),
        "legacy_review_rows_remaining": sum(legacy_review_row(row) for row in combined),
    }
    report["outputs"] = {"evidence_json": str(args.out_json.resolve()), "report_json": str(args.report_json.resolve())}
    write_json(args.report_json, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
