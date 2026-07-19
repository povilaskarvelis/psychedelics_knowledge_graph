from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from pipeline.publish.export_query_api import materialize_query_artifacts


def write_minimal_kg(kg_dir: Path, *, run_id: str = "test_run") -> None:
    kg_dir.mkdir(parents=True, exist_ok=True)
    findings = pd.DataFrame(
        [
            {
                "finding_id": "finding:primary",
                "source_name": "routed_extractions",
                "domain": "clinical_outcome",
                "dataset": "clinical_outcome",
                "evidence_type": "primary_evidence",
                "paper_id": "paper:10.1000/primary",
                "study_doi": "10.1000/primary",
                "study_year": 2025,
                "compound": "Psilocybin",
                "entity_label": "Major depressive disorder",
                "graph_entity_label": "Major depressive disorder",
                "kg_entity_kind_override": "condition_indication",
                "graph_subject_kind": "atomic_compound",
                "graph_overview_subject_label": "Psilocybin",
                "graph_overview_subject_kind": "atomic_compound",
                "graph_admission_status": "main_graph",
                "graph_admission_reason": "normalized_main_graph",
                "result_direction_normalized": "positive",
                "access_level": "article_text",
                "source_type": "primary_study",
                "paper_type": "primary_study",
                "supporting_quote": "Symptoms improved in the treatment group.",
                "evidence_locator": "Results, paragraph 2",
                "proposition_group_id": "proposition:primary",
                "raw_row_json": "{}",
            },
            {
                "finding_id": "finding:review",
                "source_name": "routed_extractions",
                "domain": "clinical_outcome",
                "dataset": "clinical_outcome",
                "evidence_type": "secondary_literature",
                "paper_id": "paper:10.1000/review",
                "study_doi": "10.1000/review",
                "study_year": 2024,
                "compound": "Psilocybin",
                "entity_label": "Major depressive disorder",
                "graph_entity_label": "Major depressive disorder",
                "kg_entity_kind_override": "condition_indication",
                "graph_subject_kind": "atomic_compound",
                "graph_overview_subject_label": "Psilocybin",
                "graph_overview_subject_kind": "atomic_compound",
                "graph_admission_status": "paper_detail",
                "graph_admission_reason": "secondary_detail",
                "result_direction_normalized": "mixed",
                "access_level": "abstract_only",
                "source_type": "systematic_review",
                "paper_type": "systematic_review",
                "supporting_quote": "The evidence was mixed.",
                "evidence_locator": "Abstract",
                "proposition_group_id": "proposition:review",
                "raw_row_json": "{}",
            },
            {
                "finding_id": "finding:target",
                "source_name": "routed_extractions",
                "domain": "molecular_target",
                "dataset": "molecular_target",
                "evidence_type": "primary_evidence",
                "paper_id": "paper:10.1000/target",
                "study_doi": "10.1000/target",
                "study_year": 2023,
                "compound": "Ketamine",
                "entity_label": "NMDA receptor",
                "graph_entity_label": "NMDA receptor",
                "kg_entity_kind_override": "target",
                "graph_subject_kind": "atomic_compound",
                "graph_overview_subject_label": "Ketamine",
                "graph_overview_subject_kind": "atomic_compound",
                "graph_admission_status": "main_graph",
                "graph_admission_reason": "normalized_main_graph",
                "result_direction_normalized": "positive",
                "access_level": "article_text",
                "source_type": "primary_study",
                "paper_type": "primary_study",
                "supporting_quote": "Ketamine interacted with the NMDA receptor.",
                "evidence_locator": "Results",
                "proposition_group_id": "proposition:target",
                "raw_row_json": "{}",
            },
        ]
    )
    edges = pd.DataFrame(
        [
            {
                "evidence_id": "evidence:primary",
                "finding_id": "finding:primary",
                "projection_type": "outcome",
                "source_name": "routed_extractions",
                "domain": "clinical_outcome",
                "dataset": "clinical_outcome",
                "entity_kind": "condition_indication",
                "evidence_type": "primary_evidence",
                "relation_type": "studied_for_condition",
                "compound_id": "compound:psilocybin",
                "compound": "Psilocybin",
                "graph_subject_kind": "atomic_compound",
                "entity_id": "clinical_entity:major_depressive_disorder",
                "entity_label": "Major depressive disorder",
                "paper_id": "paper:10.1000/primary",
                "study_doi": "10.1000/primary",
                "study_year": 2025,
                "direction_normalized": "positive",
                "graph_admission_status": "main_graph",
                "graph_admission_reason": "normalized_main_graph",
                "source_type": "primary_study",
                "paper_type": "primary_results",
                "access_level": "article_text",
                "supporting_quote": "Symptoms improved in the treatment group.",
                "evidence_locator": "Results, paragraph 2",
                "proposition_group_id": "proposition:primary",
            },
            {
                "evidence_id": "evidence:review",
                "finding_id": "finding:review",
                "projection_type": "outcome",
                "source_name": "routed_extractions",
                "domain": "clinical_outcome",
                "dataset": "clinical_outcome",
                "entity_kind": "condition_indication",
                "evidence_type": "secondary_literature",
                "relation_type": "discusses_relationship",
                "compound_id": "compound:psilocybin",
                "compound": "Psilocybin",
                "graph_subject_kind": "atomic_compound",
                "entity_id": "clinical_entity:major_depressive_disorder",
                "entity_label": "Major depressive disorder",
                "paper_id": "paper:10.1000/review",
                "study_doi": "10.1000/review",
                "study_year": 2024,
                "direction_normalized": "mixed",
                "graph_admission_status": "paper_detail",
                "graph_admission_reason": "secondary_detail",
                "source_type": "systematic_review",
                "paper_type": "systematic_review",
                "access_level": "abstract_only",
                "supporting_quote": "The evidence was mixed.",
                "evidence_locator": "Abstract",
                "proposition_group_id": "proposition:review",
            },
            {
                "evidence_id": "evidence:target",
                "finding_id": "finding:target",
                "projection_type": "outcome",
                "source_name": "routed_extractions",
                "domain": "molecular_target",
                "dataset": "molecular_target",
                "entity_kind": "target",
                "evidence_type": "primary_evidence",
                "relation_type": "has_mechanistic_target",
                "compound_id": "compound:ketamine",
                "compound": "Ketamine",
                "graph_subject_kind": "atomic_compound",
                "entity_id": "target:nmda_receptor",
                "entity_label": "NMDA receptor",
                "paper_id": "paper:10.1000/target",
                "study_doi": "10.1000/target",
                "study_year": 2023,
                "direction_normalized": "positive",
                "graph_admission_status": "main_graph",
                "graph_admission_reason": "normalized_main_graph",
                "source_type": "primary_study",
                "paper_type": "primary_results",
                "access_level": "article_text",
                "supporting_quote": "Ketamine interacted with the NMDA receptor.",
                "evidence_locator": "Results",
                "proposition_group_id": "proposition:target",
            },
        ]
    )
    entities = pd.DataFrame(
        [
            {
                "entity_id": "compound:psilocybin",
                "entity_type": "compound",
                "domain": "compound",
                "entity_kind": "atomic_compound",
                "label": "Psilocybin",
                "registry_status": "canonical",
                "aliases_json": json.dumps(["magic mushrooms"]),
                "ids_json": "{}",
            },
            {
                "entity_id": "clinical_entity:major_depressive_disorder",
                "entity_type": "clinical_entity",
                "domain": "clinical_outcome",
                "entity_kind": "condition_indication",
                "label": "Major depressive disorder",
                "registry_status": "canonical",
                "aliases_json": json.dumps(["MDD", "depression"]),
                "ids_json": "{}",
            },
            {
                "entity_id": "compound:ketamine",
                "entity_type": "compound",
                "domain": "compound",
                "entity_kind": "atomic_compound",
                "label": "Ketamine",
                "registry_status": "canonical",
                "aliases_json": "[]",
                "ids_json": "{}",
            },
            {
                "entity_id": "target:nmda_receptor",
                "entity_type": "target",
                "domain": "molecular_target",
                "entity_kind": "target",
                "label": "NMDA receptor",
                "registry_status": "canonical",
                "aliases_json": json.dumps(["NMDAR"]),
                "ids_json": "{}",
            },
        ]
    ).fillna("")
    papers = pd.DataFrame(
        [
            {
                "paper_id": "paper:10.1000/primary",
                "doi": "10.1000/primary",
                "title": "Primary psilocybin study",
                "authors": "Ada Example",
                "year": 2025,
                "journal": "Example Journal",
                "study_doi": "10.1000/primary",
                "study_title": "Primary psilocybin study",
                "study_year": 2025,
                "study_journal": "Example Journal",
                "source_access_level": "article_text",
            },
            {
                "paper_id": "paper:10.1000/review",
                "doi": "10.1000/review",
                "title": "Psilocybin systematic review",
                "authors": "Grace Example",
                "year": 2024,
                "journal": "Review Journal",
                "study_doi": "10.1000/review",
                "study_title": "Psilocybin systematic review",
                "study_year": 2024,
                "study_journal": "Review Journal",
                "source_access_level": "abstract_only",
            },
            {
                "paper_id": "paper:10.1000/target",
                "doi": "10.1000/target",
                "title": "Ketamine target study",
                "authors": "Lin Example",
                "year": 2023,
                "journal": "Target Journal",
                "study_doi": "10.1000/target",
                "study_title": "Ketamine target study",
                "study_year": 2023,
                "study_journal": "Target Journal",
                "source_access_level": "article_text",
            },
        ]
    )
    authors = pd.DataFrame(
        [
            {
                "author_id": "openalex:A1001",
                "display_name": "Ada Example",
                "canonical_name": "ada example",
                "openalex_author_id": "https://openalex.org/A1001",
                "openalex_author_ids_json": json.dumps(["https://openalex.org/A1001"]),
                "orcid": "",
                "identity_confidence": "openalex_author_id",
                "display_names_json": json.dumps(["Ada Example"]),
                "paper_count": 1,
            },
            {
                "author_id": "openalex:A1002",
                "display_name": "Grace Example",
                "canonical_name": "grace example",
                "openalex_author_id": "https://openalex.org/A1002",
                "openalex_author_ids_json": json.dumps(["https://openalex.org/A1002"]),
                "orcid": "",
                "identity_confidence": "openalex_author_id",
                "display_names_json": json.dumps(["Grace Example"]),
                "paper_count": 1,
            },
            {
                "author_id": "orcid:0000-0001-2345-6789",
                "display_name": "Lin Example",
                "canonical_name": "lin example",
                "openalex_author_id": "",
                "openalex_author_ids_json": "[]",
                "orcid": "0000-0001-2345-6789",
                "identity_confidence": "orcid",
                "display_names_json": json.dumps(["Lin Example"]),
                "paper_count": 1,
            },
        ]
    )
    paper_authors = pd.DataFrame(
        [
            {
                "paper_id": "paper:10.1000/primary",
                "author_id": "openalex:A1001",
                "display_name": "Ada Example",
                "canonical_name": "ada example",
                "identity_confidence": "openalex_author_id",
                "author_position": 1,
                "is_first_author": True,
                "is_last_author": True,
            },
            {
                "paper_id": "paper:10.1000/review",
                "author_id": "openalex:A1002",
                "display_name": "Grace Example",
                "canonical_name": "grace example",
                "identity_confidence": "openalex_author_id",
                "author_position": 1,
                "is_first_author": True,
                "is_last_author": True,
            },
            {
                "paper_id": "paper:10.1000/target",
                "author_id": "orcid:0000-0001-2345-6789",
                "display_name": "Lin Example",
                "canonical_name": "lin example",
                "identity_confidence": "orcid",
                "author_position": 1,
                "is_first_author": True,
                "is_last_author": True,
            },
        ]
    )
    findings.to_parquet(kg_dir / "findings.parquet", index=False)
    edges.to_parquet(kg_dir / "evidence_edges.parquet", index=False)
    entities.to_parquet(kg_dir / "entities.parquet", index=False)
    papers.to_parquet(kg_dir / "papers.parquet", index=False)
    authors.to_parquet(kg_dir / "authors.parquet", index=False)
    paper_authors.to_parquet(kg_dir / "paper_authors.parquet", index=False)
    (kg_dir / "manifest.json").write_text(
        json.dumps(
            {
                "kg_table_version": "test",
                "run_id": run_id,
                "source_preset": "routed",
                "tables": {"findings": {"rows": len(findings)}},
            }
        ),
        encoding="utf-8",
    )


def build_active_query_release(root: Path, *, run_id: str = "test_run", release_id: str = "test_run:r1") -> tuple[Path, Path]:
    kg_dir = root / "kg" / run_id
    query_runs = root / "query_api_runs"
    write_minimal_kg(kg_dir, run_id=run_id)
    materialize_query_artifacts(
        kg_dir=kg_dir,
        out_dir=query_runs / run_id,
        run_id=run_id,
        generated_at="2026-07-17T00:00:00+00:00",
    )
    pointer = root / "graph_payload_active.json"
    pointer.write_text(
        json.dumps({"run_id": run_id, "release_id": release_id}),
        encoding="utf-8",
    )
    return pointer, query_runs
