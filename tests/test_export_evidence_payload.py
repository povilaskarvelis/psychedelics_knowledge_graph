import json
import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pipeline.publish.export_evidence_payload import (
    detail_bootstrap_payload,
    export_evidence_payload,
    graph_bootstrap_payload,
    load_selected_candidate_study_key_sets,
    load_findings,
    secondary_literature_source_key,
)


def detail_bootstrap_rows(payload: dict) -> list[dict]:
    fields = payload["fields"]
    values = payload["values"]
    rows = []
    for row in payload["rows"]:
        decoded = {}
        for index, field in enumerate(fields):
            value = values[row[index]]
            if value is not None:
                decoded[field] = value
        rows.append(decoded)
    return rows


def write_author_tables(kg_dir: Path, *, paper_id: str = "paper-1", authors: str = "Ada Example; Grace Example") -> None:
    pd.DataFrame(
        [
            {
                "paper_id": paper_id,
                "doi": "10.1000/authors",
                "authors": authors,
            }
        ]
    ).to_parquet(kg_dir / "papers.parquet", index=False)
    pd.DataFrame(
        [
            {
                "author_id": "openalex:A1",
                "display_name": "Ada Example",
                "canonical_name": "ada example",
                "openalex_author_id": "https://openalex.org/A1",
                "orcid": "",
                "source": "openalex",
                "identity_confidence": "openalex_author_id",
                "paper_count": 1,
                "authorship_count": 1,
                "first_author_paper_count": 1,
                "last_author_paper_count": 0,
            },
            {
                "author_id": "openalex:A2",
                "display_name": "Grace Example",
                "canonical_name": "grace example",
                "openalex_author_id": "https://openalex.org/A2",
                "orcid": "",
                "source": "openalex",
                "identity_confidence": "openalex_author_id",
                "paper_count": 1,
                "authorship_count": 1,
                "first_author_paper_count": 0,
                "last_author_paper_count": 1,
            },
        ]
    ).to_parquet(kg_dir / "authors.parquet", index=False)
    pd.DataFrame(
        [
            {
                "paper_id": paper_id,
                "doi": "10.1000/authors",
                "paper_openalex_id": "https://openalex.org/W1",
                "author_id": "openalex:A1",
                "display_name": "Ada Example",
                "canonical_name": "ada example",
                "openalex_author_id": "https://openalex.org/A1",
                "orcid": "",
                "author_position": 1,
                "author_position_label": "first",
                "is_first_author": True,
                "is_last_author": False,
                "source": "openalex",
                "identity_confidence": "openalex_author_id",
            },
            {
                "paper_id": paper_id,
                "doi": "10.1000/authors",
                "paper_openalex_id": "https://openalex.org/W1",
                "author_id": "openalex:A2",
                "display_name": "Grace Example",
                "canonical_name": "grace example",
                "openalex_author_id": "https://openalex.org/A2",
                "orcid": "",
                "author_position": 2,
                "author_position_label": "last",
                "is_first_author": False,
                "is_last_author": True,
                "source": "openalex",
                "identity_confidence": "openalex_author_id",
            },
        ]
    ).to_parquet(kg_dir / "paper_authors.parquet", index=False)
    (kg_dir / "author_resolution_report.json").write_text(
        json.dumps({"paper_count": 1, "paper_author_rows": 2}),
        encoding="utf-8",
    )


class ExportEvidencePayloadTest(unittest.TestCase):
    def test_target_aliases_flow_from_entities_into_findings_and_graph_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            kg_dir = Path(tmpdir)
            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-1",
                        "paper_id": "paper-1",
                        "source_name": "routed_extractions",
                        "compound": "Psilocybin",
                        "entity_label": "5-HT2A",
                        "entity_kind": "target",
                        "domain": "molecular_target",
                        "raw_row_json": "{}",
                    }
                ]
            ).to_parquet(kg_dir / "findings.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-1",
                        "evidence_id": "evidence-1",
                        "entity_id": "target:5_ht2a",
                        "source_name": "routed_extractions",
                        "entity_label": "5-HT2A",
                        "entity_kind": "target",
                        "domain": "molecular_target",
                        "relation_type": "has_mechanistic_target",
                    }
                ]
            ).to_parquet(kg_dir / "evidence_edges.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "entity_id": "target:5_ht2a",
                        "label": "5-HT2A",
                        "aliases_json": json.dumps(["HTR2A", "5-HT2A receptor"]),
                    }
                ]
            ).to_parquet(kg_dir / "entities.parquet", index=False)

            findings = load_findings(kg_dir)
            self.assertEqual(findings[0]["entity_aliases"], ["5-HT2A receptor", "HTR2A"])

            graph_findings = [
                {**findings[0], "study_doi": "10.1000/alias-1"},
                {**findings[0], "study_doi": "10.1000/alias-2"},
            ]
            payload = graph_bootstrap_payload(graph_findings, "2026-07-14T00:00:00Z", kg_dir, "primary")
            self.assertEqual(payload["edges"][0]["entity_aliases"], ["5-HT2A receptor", "HTR2A"])

            detail = detail_bootstrap_payload(findings, "2026-07-14T00:00:00Z", kg_dir, "primary")
            detail_rows = detail_bootstrap_rows(detail)
            self.assertEqual(detail_rows[0]["entity_aliases"], ["5-HT2A receptor", "HTR2A"])

    def test_graph_bootstrap_adds_substance_to_use_context_edges_as_separate_projections(self) -> None:
        findings = []
        for index in (1, 2):
            findings.append(
                {
                    "compound": "Chemsex",
                    "graph_subject_kind": "exposure_context",
                    "graph_overview_subject_label": "Chemsex",
                    "graph_overview_subject_kind": "exposure_context",
                    "entity_label": "Population use & trends",
                    "entity_kind": "public_health_measure",
                    "domain": "real_world_public_health",
                    "relation_type": "has_public_health_evidence",
                    "study_doi": f"10.1000/chemsex-context-{index}",
                    "graph_use_context_projections_json": json.dumps(
                        [
                            {
                                "projection_type": "use_context",
                                "subject_label": "Ketamine",
                                "subject_kind": "atomic_compound",
                                "subject_aliases": [],
                                "context_label": "Chemsex",
                                "context_kind": "exposure_context",
                                "context_aliases": ["chem sex"],
                                "context_parent_label": "Sexualized drug use",
                                "context_parent_kind": "exposure_context",
                                "context_parent_entity_id": "compound:sexualized_drug_use",
                                "relation_type": "reported_in_use_context",
                            },
                            {
                                "projection_type": "use_context",
                                "subject_label": "MDMA",
                                "subject_kind": "atomic_compound",
                                "subject_aliases": ["ecstasy"],
                                "context_label": "Chemsex",
                                "context_kind": "exposure_context",
                                "context_aliases": ["chem sex"],
                                "context_parent_label": "Sexualized drug use",
                                "context_parent_kind": "exposure_context",
                                "context_parent_entity_id": "compound:sexualized_drug_use",
                                "relation_type": "reported_in_use_context",
                            },
                        ]
                    ),
                }
            )

        payload = graph_bootstrap_payload(findings, "2026-07-13T00:00:00Z", Path("kg"), "primary")
        context_edges = [edge for edge in payload["edges"] if edge["projection_type"] == "use_context"]
        outcome_edges = [edge for edge in payload["edges"] if edge["projection_type"] == "outcome"]

        self.assertEqual(len(outcome_edges), 1)
        self.assertEqual({edge["compound"] for edge in context_edges}, {"Ketamine", "MDMA"})
        self.assertEqual({edge["entity_label"] for edge in context_edges}, {"Chemsex"})
        self.assertEqual({edge["relation_type"] for edge in context_edges}, {"reported_in_use_context"})
        self.assertTrue(all(edge["graph_parent_label"] == "Sexualized drug use" for edge in context_edges))
        self.assertEqual(next(edge for edge in context_edges if edge["compound"] == "MDMA")["compound_aliases"], ["ecstasy"])
        self.assertEqual(context_edges[0]["entity_aliases"], ["chem sex"])

    def test_explicit_umbrella_review_type_wins_over_meta_analysis_publication_tag(self) -> None:
        finding = {
            "paper_type": "umbrella_review",
            "source_type": "umbrella_review",
            "publication_type": "Journal Article | Meta-Analysis | Systematic Review",
        }
        self.assertEqual(secondary_literature_source_key(finding), "reviews")

    def test_overview_projection_uses_controlled_subjects_and_parent_families(self) -> None:
        findings = [
            {
                "compound": "Psilocybin and MDMA at study-specific doses",
                "graph_subject_kind": "compound_combination",
                "graph_overview_subject_label": "Psilocybin",
                "graph_overview_subject_kind": "atomic_compound",
                "graph_overview_subjects_json": json.dumps(
                    [
                        {"label": "Psilocybin", "kind": "atomic_compound"},
                        {"label": "MDMA", "kind": "atomic_compound"},
                    ]
                ),
                "entity_label": "Major depressive disorder",
                "entity_kind": "condition_indication",
                "domain": "clinical_outcome",
                "study_doi": "10.1000/controlled-combo",
            },
            {
                "compound": "MDMA and Psilocybin in another regimen",
                "graph_subject_kind": "compound_combination",
                "graph_overview_subject_label": "Psilocybin",
                "graph_overview_subject_kind": "atomic_compound",
                "graph_overview_subjects_json": json.dumps(
                    [
                        {"label": "Psilocybin", "kind": "atomic_compound"},
                        {"label": "MDMA", "kind": "atomic_compound"},
                    ]
                ),
                "entity_label": "Major depressive disorder",
                "entity_kind": "condition_indication",
                "domain": "clinical_outcome",
                "study_doi": "10.1000/controlled-combo-replication",
            },
            {
                "compound": "arbitrary one-off exposure prose",
                "graph_subject_kind": "exposure_context",
                "entity_label": "Major depressive disorder",
                "entity_kind": "condition_indication",
                "domain": "clinical_outcome",
                "study_doi": "10.1000/uncontrolled-context",
            },
            {
                "compound": "Ketamine",
                "graph_subject_kind": "atomic_compound",
                "entity_label": "study-specific phosphorylation wording",
                "entity_kind": "pathway_process",
                "graph_parent_label": "Intracellular signal transduction",
                "graph_parent_kind": "pathway_process",
                "domain": "molecular_pathway_readout",
                "study_doi": "10.1000/parent-family",
            },
            {
                "compound": "Ketamine",
                "graph_subject_kind": "atomic_compound",
                "entity_label": "another study-specific signaling phrase",
                "entity_kind": "pathway_process",
                "graph_parent_label": "Intracellular signal transduction",
                "graph_parent_kind": "pathway_process",
                "domain": "molecular_pathway_readout",
                "study_doi": "10.1000/parent-family-replication",
            },
            {
                "compound": "Salvinorin A",
                "graph_subject_kind": "atomic_compound",
                "entity_label": "Major depressive disorder",
                "entity_kind": "condition_indication",
                "domain": "clinical_outcome",
                "study_doi": "10.1000/single-study-node",
            },
            {
                "compound": "LSD + MDMA (candyflipping)",
                "graph_subject_kind": "compound_combination",
                "graph_overview_subjects_json": json.dumps(
                    [
                        {
                            "label": "LSD + MDMA (candyflipping)",
                            "kind": "compound_combination",
                            "aliases": ["candyflip", "candy flip", "candy flipping"],
                        }
                    ]
                ),
                "entity_label": "Altered state profile",
                "entity_kind": "subjective_experience_construct",
                "domain": "subjective_experience",
                "study_doi": "10.1000/candyflip-one",
            },
            {
                "compound": "LSD + MDMA (candyflipping)",
                "graph_subject_kind": "compound_combination",
                "graph_overview_subjects_json": json.dumps(
                    [
                        {
                            "label": "LSD + MDMA (candyflipping)",
                            "kind": "compound_combination",
                            "aliases": ["candyflipping"],
                        }
                    ]
                ),
                "entity_label": "Altered state profile",
                "entity_kind": "subjective_experience_construct",
                "domain": "subjective_experience",
                "study_doi": "10.1000/candyflip-two",
            },
        ]

        payload = graph_bootstrap_payload(findings, "2026-07-11T00:00:00Z", Path("kg"), "primary")

        self.assertEqual(payload["finding_count"], 8)
        self.assertEqual(payload["detail_only_subject_count"], 1)
        self.assertEqual(payload["single_study_subject_finding_count"], 1)
        self.assertEqual(
            {edge["compound"] for edge in payload["edges"]},
            {"Ketamine", "Psilocybin", "MDMA", "LSD + MDMA (candyflipping)"},
        )
        self.assertIn("Intracellular signal transduction", {edge["entity_label"] for edge in payload["edges"]})
        candyflip_edge = next(edge for edge in payload["edges"] if edge["compound"].startswith("LSD + MDMA"))
        self.assertEqual(
            candyflip_edge["compound_aliases"],
            ["candy flip", "candy flipping", "candyflip", "candyflipping"],
        )

    def test_meta_analysis_graph_keeps_single_paper_nodes(self) -> None:
        findings = [
            {
                "compound": "Salvinorin A",
                "graph_subject_kind": "atomic_compound",
                "entity_label": "Major depressive disorder",
                "entity_kind": "condition_indication",
                "domain": "clinical_outcome",
                "study_doi": "10.1000/single-meta-analysis",
            }
        ]

        payload = graph_bootstrap_payload(findings, "2026-07-12T00:00:00Z", Path("kg"), "meta_analyses")

        self.assertEqual(payload["finding_count"], 1)
        self.assertEqual(payload["edge_count"], 1)
        self.assertEqual(payload["single_study_subject_finding_count"], 0)
        self.assertEqual(payload["detail_only_entity_count"], 0)

    def test_requires_author_tables_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            kg_dir = root / "kg"
            out_dir = root / "payload"
            kg_dir.mkdir()

            pd.DataFrame([{"paper_id": "paper-1", "authors": "Ada Example"}]).to_parquet(
                kg_dir / "papers.parquet", index=False
            )

            with self.assertRaisesRegex(RuntimeError, "build_author_tables"):
                export_evidence_payload(kg_dir=kg_dir, out_dir=out_dir)

    def test_rejects_author_tables_older_than_papers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            kg_dir = root / "kg"
            out_dir = root / "payload"
            kg_dir.mkdir()
            write_author_tables(kg_dir)

            for name in ("authors.parquet", "paper_authors.parquet", "author_resolution_report.json"):
                os.utime(kg_dir / name, (1000, 1000))
            os.utime(kg_dir / "papers.parquet", (2000, 2000))

            with self.assertRaisesRegex(RuntimeError, "older than papers.parquet"):
                export_evidence_payload(kg_dir=kg_dir, out_dir=out_dir)

    def test_exports_fresh_author_roles_into_detail_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            kg_dir = root / "kg"
            out_dir = root / "payload"
            kg_dir.mkdir()
            write_author_tables(kg_dir)

            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-1",
                        "paper_id": "paper-1",
                        "source_name": "routed_extractions",
                        "domain": "clinical_outcome",
                        "evidence_type": "primary_evidence",
                        "study_doi": "10.1000/authors",
                        "compound": "Psilocybin",
                        "entity_label": "Major depressive disorder",
                        "raw_row_json": "{}",
                    }
                ]
            ).to_parquet(kg_dir / "findings.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-1",
                        "evidence_id": "evidence-1",
                        "domain": "clinical_outcome",
                        "entity_kind": "condition_indication",
                        "entity_label": "Major depressive disorder",
                        "evidence_type": "primary_evidence",
                        "relation_type": "studied_for_condition",
                    }
                ]
            ).to_parquet(kg_dir / "evidence_edges.parquet", index=False)

            result = export_evidence_payload(kg_dir=kg_dir, out_dir=out_dir)
            detail = json.loads(result["detail_bootstrap_paths"]["primary"].read_text())
            rows = detail_bootstrap_rows(detail)

        self.assertEqual(rows[0]["first_author"]["name"], "Ada Example")
        self.assertEqual(rows[0]["first_author"]["id"], "openalex:A1")
        self.assertEqual(rows[0]["last_author"]["name"], "Grace Example")
        self.assertEqual(rows[0]["last_author"]["id"], "openalex:A2")

    def test_exports_route_native_findings_without_legacy_split_or_claim_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            kg_dir = root / "kg"
            out_dir = root / "payload"
            active_json = root / "graph_payload_active.json"
            kg_dir.mkdir()

            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-1",
                        "paper_id": "paper-1",
                        "source_name": "routed_extractions",
                        "domain": "brain_system",
                        "evidence_type": "primary_evidence",
                        "study_doi": "10.1000/example",
                        "study_year": 2024,
                        "compound": "Psilocybin",
                        "entity_label": "Raw CA1 label",
                        "raw_row_json": json.dumps(
                            {
                                "compound": "Psilocybin",
                                "graph_entity_label": "Raw CA1 label",
                                "access_level": "article_text",
                                "paper_type": "primary_study",
                                "source_type": "primary",
                                "source_family": "primary_study",
                                "real_world_use_context": "Microdosing; Self-treatment",
                                "assessment_timepoint": "2 hours post-dose",
                                "open_access_is_oa": True,
                                "support": "Psilocybin altered activity in hippocampal CA1 after dosing.",
                                "effect_size": "Reduced functional connectivity",
                            }
                        ),
                    },
                    {
                        "finding_id": "legacy-1",
                        "paper_id": "paper-2",
                        "source_name": "legacy_primary",
                        "domain": "legacy",
                        "evidence_type": "primary_evidence",
                        "raw_row_json": "{}",
                    },
                ]
            ).to_parquet(kg_dir / "findings.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-1",
                        "evidence_id": "evidence-1",
                        "domain": "brain_system",
                        "entity_kind": "brain_region",
                        "entity_label": "Hippocampal CA1",
                        "graph_parent_label": "Hippocampus",
                        "graph_parent_kind": "brain_region",
                        "graph_parent_entity_id": "brain-system-entity:hippocampus",
                        "evidence_type": "primary_evidence",
                        "relation_type": "modulates_brain_system",
                    }
                ]
            ).to_parquet(kg_dir / "evidence_edges.parquet", index=False)

            result = export_evidence_payload(
                kg_dir=kg_dir,
                out_dir=out_dir,
                active_json=active_json,
                require_fresh_author_tables=False,
            )

            graph_bootstrap = json.loads(result["graph_bootstrap_paths"]["primary"].read_text())
            detail_bootstrap = json.loads(result["detail_bootstrap_paths"]["primary"].read_text())
            active = json.loads(active_json.read_text())
            manifest = json.loads(result["manifest_path"].read_text())
            rows = detail_bootstrap_rows(detail_bootstrap)

        self.assertEqual(manifest["schema_version"], "route_native_evidence_manifest_v1")
        self.assertEqual(manifest["row_count"], 1)
        self.assertNotIn("evidence_payload", manifest)
        self.assertNotIn("evidence_payloads", manifest)
        self.assertNotIn("evidence_preview", manifest)
        finding = rows[0]
        self.assertEqual(finding["domain"], "brain_system")
        self.assertEqual(finding["finding_type"], "brain_system")
        self.assertEqual(finding["entity_label"], "Hippocampal CA1")
        self.assertEqual(finding["entity_kind"], "brain_region")
        self.assertEqual(finding["graph_parent_label"], "Hippocampus")
        self.assertEqual(finding["graph_parent_kind"], "brain_region")
        self.assertEqual(finding["text_depth"], "article_text")
        self.assertEqual(finding["assessment_timepoint"], "2 hours post-dose")
        self.assertEqual(finding["real_world_use_context"], "Microdosing; Self-treatment")
        self.assertEqual(finding["support"], "Psilocybin altered activity in hippocampal CA1 after dosing.")
        self.assertEqual(finding["effect_size"], "Reduced functional connectivity")
        self.assertIs(finding["open_access_is_oa"], True)
        self.assertNotIn("claim_type", finding)
        self.assertNotIn("target", finding)
        self.assertNotIn("disorder", finding)
        self.assertEqual(graph_bootstrap["edge_count"], 0)
        self.assertEqual(graph_bootstrap["finding_count"], 0)
        self.assertEqual(detail_bootstrap["schema_version"], "route_native_detail_bootstrap_v1")
        self.assertEqual(detail_bootstrap["row_count"], 1)
        self.assertIn("study_year", detail_bootstrap["fields"])
        self.assertIn("evidence_locator", detail_bootstrap["fields"])
        self.assertIn("support", detail_bootstrap["fields"])
        self.assertIn("effect_size", detail_bootstrap["fields"])
        self.assertIn("supporting_quote", detail_bootstrap["fields"])
        self.assertIn("molecular_finding_subtopic", detail_bootstrap["fields"])
        self.assertEqual(len(detail_bootstrap["rows"]), 1)
        self.assertEqual(active["schema_version"], "route_native_evidence_payload_active_v1")
        self.assertNotIn("active_evidence_payload", active)
        self.assertNotIn("active_evidence_payloads", active)
        self.assertNotIn("active_evidence_preview", active)
        self.assertIn("active_graph_bootstraps", active)
        self.assertIn("primary", active["active_graph_bootstraps"])
        self.assertIn("active_detail_bootstraps", active)
        self.assertIn("primary", active["active_detail_bootstraps"])
        self.assertEqual(set(active["active_graph_bootstraps"]), {"primary", "meta_analyses", "reviews"})
        self.assertEqual(set(active["active_detail_bootstraps"]), {"primary", "meta_analyses", "reviews"})
        self.assertNotIn("active_payload_dir", active)
        self.assertNotIn("claim_source", active)

    def test_exports_primary_meta_analysis_and_review_sources_separately(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            kg_dir = root / "kg"
            out_dir = root / "payload"
            active_json = root / "graph_payload_active.json"
            kg_dir.mkdir()

            pd.DataFrame(
                [
                    {
                        "finding_id": "primary-1",
                        "paper_id": "paper-primary",
                        "source_name": "routed_extractions",
                        "domain": "clinical_outcome",
                        "evidence_type": "primary_evidence",
                        "study_doi": "10.1000/primary",
                        "study_year": 2024,
                        "compound": "Psilocybin",
                        "entity_label": "Major depressive disorder",
                        "paper_type": "primary_results",
                        "source_type": "primary_study",
                        "raw_row_json": "{}",
                    },
                    {
                        "finding_id": "meta-1",
                        "paper_id": "paper-meta",
                        "source_name": "routed_extractions",
                        "domain": "clinical_outcome",
                        "evidence_type": "secondary_literature",
                        "study_doi": "10.1000/meta",
                        "study_year": 2023,
                        "compound": "Psilocybin",
                        "entity_label": "Major depressive disorder",
                        "paper_type": "meta_analysis",
                        "source_type": "meta_analysis",
                        "text_depth": "article_text",
                        "meta_analysis_result_role": "primary_synthesis",
                        "meta_analysis_overall_study_count": "29",
                        "heterogeneity_i_squared": "I² = 61%",
                        "confidence_interval": "95% CI -1.20 to -0.44",
                        "support": "Pooled estimates favored ketamine over control.",
                        "raw_row_json": "{}",
                    },
                    {
                        "finding_id": "review-1",
                        "paper_id": "paper-review",
                        "source_name": "routed_extractions",
                        "domain": "brain_system",
                        "evidence_type": "secondary_literature",
                        "study_doi": "10.1000/review",
                        "study_year": 2022,
                        "compound": "LSD",
                        "entity_label": "Thalamocortical circuit",
                        "paper_type": "review",
                        "source_type": "review",
                        "coverage_type": "review_synthesis",
                        "evidence_level": "human_and_preclinical",
                        "result_direction": "mixed",
                        "review_contribution_type": "mechanistic_or_conceptual_review",
                        "review_design_category": "narrative_or_literature_review",
                        "support": "Review coverage discusses thalamocortical connectivity.",
                        "raw_row_json": "{}",
                    },
                ]
            ).to_parquet(kg_dir / "findings.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "finding_id": "primary-1",
                        "evidence_id": "edge-primary",
                        "domain": "clinical_outcome",
                        "entity_kind": "condition_indication",
                        "entity_label": "Major depressive disorder",
                        "evidence_type": "primary_evidence",
                        "relation_type": "studied_for_condition",
                    },
                    {
                        "finding_id": "meta-1",
                        "evidence_id": "edge-meta",
                        "domain": "clinical_outcome",
                        "entity_kind": "condition_indication",
                        "entity_label": "Major depressive disorder",
                        "evidence_type": "secondary_literature",
                        "relation_type": "meta_analyzes_relationship",
                    },
                    {
                        "finding_id": "review-1",
                        "evidence_id": "edge-review",
                        "domain": "brain_system",
                        "entity_kind": "neural_circuit",
                        "entity_label": "Thalamocortical circuit",
                        "evidence_type": "secondary_literature",
                        "relation_type": "reviews_relationship",
                    },
                ]
            ).to_parquet(kg_dir / "evidence_edges.parquet", index=False)

            result = export_evidence_payload(
                kg_dir=kg_dir,
                out_dir=out_dir,
                active_json=active_json,
                require_fresh_author_tables=False,
            )
            active = json.loads(active_json.read_text())
            primary_rows = detail_bootstrap_rows(json.loads(result["detail_bootstrap_paths"]["primary"].read_text()))
            meta_rows = detail_bootstrap_rows(json.loads(result["detail_bootstrap_paths"]["meta_analyses"].read_text()))
            review_rows = detail_bootstrap_rows(json.loads(result["detail_bootstrap_paths"]["reviews"].read_text()))

        self.assertEqual(set(active["active_detail_bootstraps"]), {"primary", "meta_analyses", "reviews"})
        self.assertNotIn("secondary", active["active_detail_bootstraps"])
        self.assertEqual([row["study_doi"] for row in primary_rows], ["10.1000/primary"])
        self.assertEqual([row["study_doi"] for row in meta_rows], ["10.1000/meta"])
        self.assertEqual(meta_rows[0]["meta_analysis_result_role"], "primary_synthesis")
        self.assertEqual(meta_rows[0]["meta_analysis_overall_study_count"], "29")
        self.assertEqual(meta_rows[0]["heterogeneity_i_squared"], "I² = 61%")
        self.assertEqual(meta_rows[0]["confidence_interval"], "95% CI -1.20 to -0.44")
        self.assertEqual([row["study_doi"] for row in review_rows], ["10.1000/review"])
        self.assertEqual(review_rows[0]["coverage_type"], "review_synthesis")
        self.assertEqual(review_rows[0]["evidence_level"], "human_and_preclinical")
        self.assertEqual(review_rows[0]["review_contribution_type"], "mechanistic_or_conceptual_review")
        self.assertEqual(review_rows[0]["review_design_category"], "narrative_or_literature_review")
        self.assertEqual(
            result["manifest"]["summary_stats"]["paper_counts"],
            {
                "primary_studies": 1,
                "reviews": 1,
                "meta_analyses": 1,
                "total": 3,
                "awaiting_graph_inclusion": {
                    "primary_studies": 0,
                    "reviews": 0,
                    "meta_analyses": 0,
                    "total": 0,
                },
                "visualized_overview_represented": {
                    "primary_studies": 0,
                    "reviews": 0,
                    "meta_analyses": 1,
                    "total": 1,
                },
                "scope": "underlying_evidence_graph_represented",
                "awaiting_scope": "selected_papers_without_normalized_finding",
                "denominator_source": "kg_artifact_fallback",
            },
        )

    def test_selected_candidate_table_sets_the_upstream_denominator(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            table = Path(tmpdir) / "candidate_papers.parquet"
            pd.DataFrame(
                [
                    {
                        "doi": "10.1000/primary",
                        "literature_source_family": "primary",
                        "literature_source_type": "primary",
                        "retained_for_extraction_candidate": True,
                    },
                    {
                        "doi": "10.1000/review",
                        "literature_source_family": "secondary_literature",
                        "literature_source_type": "systematic_review",
                        "retained_for_extraction_candidate": True,
                    },
                    {
                        "doi": "10.1000/meta",
                        "literature_source_family": "secondary_literature",
                        "literature_source_type": "network_meta_analysis",
                        "retained_for_extraction_candidate": True,
                    },
                    {
                        "doi": "10.1000/excluded",
                        "literature_source_family": "primary",
                        "literature_source_type": "primary",
                        "retained_for_extraction_candidate": False,
                    },
                ]
            ).to_parquet(table, index=False)

            keys = load_selected_candidate_study_key_sets(table)

        self.assertIsNotNone(keys)
        assert keys is not None
        self.assertEqual(keys["primary"], {"doi:10.1000/primary"})
        self.assertEqual(keys["reviews"], {"doi:10.1000/review"})
        self.assertEqual(keys["meta_analyses"], {"doi:10.1000/meta"})
        self.assertEqual(len(keys["all"]), 3)

    def test_exports_pharmacokinetics_with_all_other_domains(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            kg_dir = root / "kg"
            out_dir = root / "payload"
            kg_dir.mkdir()

            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-pk",
                        "paper_id": "paper-pk",
                        "source_name": "routed_extractions",
                        "domain": "pharmacokinetics_exposure",
                        "evidence_type": "primary_evidence",
                        "study_doi": "10.1000/pk",
                        "study_year": 2025,
                        "compound": "Ketamine",
                        "entity_label": "Cmax",
                        "raw_row_json": json.dumps(
                            {
                                "compound": "Ketamine",
                                "graph_entity_label": "Cmax",
                                "access_level": "article_text",
                                "primary_graph_anchor_kind": "pharmacokinetic_parameter",
                                "pharmacokinetic_display_label": "Ketamine plasma exposure",
                                "pk_relationship_type": "exposure_characterized",
                                "pk_relationship_label": "exposure characterized",
                                "pk_graph_object_kind": "parent_or_analyte_exposure",
                                "pk_graph_object_label": "Ketamine plasma exposure",
                                "pk_or_exposure_parameter": "Cmax",
                                "analyte_type": "parent",
                                "metabolite_or_analyte": "ketamine",
                                "matrix": "plasma",
                                "value": "123",
                                "unit": "ng/mL",
                                "dose": "0.5 mg/kg",
                                "route_of_administration": "intravenous",
                                "sampling_time_or_window": "40 minutes post-dose",
                                "model_or_method": "noncompartmental analysis",
                                "exposure_response_or_pk_effect": "higher peak exposure",
                            }
                        ),
                    }
                ]
            ).to_parquet(kg_dir / "findings.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-pk",
                        "evidence_id": "evidence-pk",
                        "domain": "pharmacokinetics_exposure",
                        "entity_kind": "pharmacokinetic_parameter",
                        "entity_label": "Cmax",
                        "evidence_type": "primary_evidence",
                        "relation_type": "has_pharmacokinetic_exposure",
                    }
                ]
            ).to_parquet(kg_dir / "evidence_edges.parquet", index=False)

            result = export_evidence_payload(kg_dir=kg_dir, out_dir=out_dir, require_fresh_author_tables=False)
            manifest = json.loads(result["manifest_path"].read_text())
            graph = json.loads(result["graph_bootstrap_paths"]["primary"].read_text())
            detail = json.loads(result["detail_bootstrap_paths"]["primary"].read_text())
            rows = detail_bootstrap_rows(detail)

        self.assertEqual(manifest["row_count"], 1)
        self.assertEqual(graph["edge_count"], 0)
        self.assertEqual(graph["finding_count"], 0)
        self.assertEqual(graph["source_row_count"], 1)
        self.assertEqual(detail["row_count"], 1)
        self.assertEqual(rows[0]["domain"], "pharmacokinetics_exposure")
        self.assertEqual(rows[0]["entity_kind"], "pharmacokinetic_parameter")

    def test_metadata_entity_kinds_remain_detail_rows_not_graph_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            kg_dir = root / "kg"
            out_dir = root / "payload"
            kg_dir.mkdir()

            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-condition",
                        "paper_id": "paper-1",
                        "source_name": "routed_extractions",
                        "domain": "clinical_outcome",
                        "evidence_type": "primary_evidence",
                        "study_doi": "10.1000/condition",
                        "compound": "Psilocybin",
                        "entity_label": "Major depressive disorder",
                        "raw_row_json": "{}",
                    },
                    {
                        "finding_id": "finding-scale",
                        "paper_id": "paper-1",
                        "source_name": "routed_extractions",
                        "domain": "clinical_outcome",
                        "evidence_type": "primary_evidence",
                        "study_doi": "10.1000/condition",
                        "compound": "Psilocybin",
                        "entity_label": "MADRS",
                        "raw_row_json": "{}",
                    },
                    {
                        "finding_id": "finding-compound-class",
                        "paper_id": "paper-1",
                        "source_name": "routed_extractions",
                        "domain": "intervention_context",
                        "evidence_type": "primary_evidence",
                        "study_doi": "10.1000/condition",
                        "compound": "Psilocybin",
                        "entity_label": "Classic psychedelics",
                        "raw_row_json": "{}",
                    },
                    {
                        "finding_id": "finding-symptom",
                        "paper_id": "paper-1",
                        "source_name": "routed_extractions",
                        "domain": "clinical_outcome",
                        "evidence_type": "primary_evidence",
                        "study_doi": "10.1000/condition",
                        "compound": "Psilocybin",
                        "entity_label": "Depressive symptoms",
                        "raw_row_json": "{}",
                    },
                    {
                        "finding_id": "finding-brain-measure",
                        "paper_id": "paper-1",
                        "source_name": "routed_extractions",
                        "domain": "brain_system",
                        "evidence_type": "primary_evidence",
                        "study_doi": "10.1000/condition",
                        "compound": "Psilocybin",
                        "entity_label": "Functional connectivity",
                        "raw_row_json": "{}",
                    },
                ]
            ).to_parquet(kg_dir / "findings.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-condition",
                        "evidence_id": "evidence-condition",
                        "domain": "clinical_outcome",
                        "entity_kind": "condition_indication",
                        "entity_label": "Major depressive disorder",
                        "evidence_type": "primary_evidence",
                        "relation_type": "studied_for_condition",
                    },
                    {
                        "finding_id": "finding-scale",
                        "evidence_id": "evidence-scale",
                        "domain": "clinical_outcome",
                        "entity_kind": "outcome_scale",
                        "entity_label": "MADRS",
                        "evidence_type": "primary_evidence",
                        "relation_type": "measured_with",
                    },
                    {
                        "finding_id": "finding-compound-class",
                        "evidence_id": "evidence-compound-class",
                        "domain": "intervention_context",
                        "entity_kind": "compound",
                        "entity_label": "Classic psychedelics",
                        "evidence_type": "primary_evidence",
                        "relation_type": "has_compound_class",
                    },
                    {
                        "finding_id": "finding-symptom",
                        "evidence_id": "evidence-symptom",
                        "domain": "clinical_outcome",
                        "entity_kind": "symptom_problem",
                        "entity_label": "Depressive symptoms",
                        "evidence_type": "primary_evidence",
                        "relation_type": "studied_for_symptom",
                    },
                    {
                        "finding_id": "finding-brain-measure",
                        "evidence_id": "evidence-brain-measure",
                        "domain": "brain_system",
                        "entity_kind": "brain_measure",
                        "entity_label": "Functional connectivity",
                        "evidence_type": "primary_evidence",
                        "relation_type": "measured_with",
                    },
                ]
            ).to_parquet(kg_dir / "evidence_edges.parquet", index=False)

            result = export_evidence_payload(kg_dir=kg_dir, out_dir=out_dir, require_fresh_author_tables=False)
            graph = json.loads(result["graph_bootstrap_paths"]["primary"].read_text())
            detail = json.loads(result["detail_bootstrap_paths"]["primary"].read_text())
            rows = detail_bootstrap_rows(detail)

        self.assertEqual(detail["row_count"], 5)
        self.assertEqual(graph["source_row_count"], 5)
        self.assertEqual(graph["finding_count"], 0)
        self.assertEqual(graph["edge_count"], 0)
        self.assertEqual(
            {row["entity_kind"] for row in rows},
            {"condition_indication", "outcome_scale", "compound", "symptom_problem", "brain_measure"},
        )

    def test_exports_graph_study_coverage_from_findings_plus_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            kg_dir = root / "kg"
            out_dir = root / "payload"
            kg_dir.mkdir()

            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-a",
                        "paper_id": "paper-a",
                        "source_name": "routed_extractions",
                        "domain": "clinical_outcome",
                        "evidence_type": "primary_evidence",
                        "study_doi": "10.1000/included-a",
                        "compound": "Psilocybin",
                        "entity_label": "Major depressive disorder",
                        "raw_row_json": "{}",
                    },
                    {
                        "finding_id": "finding-b",
                        "paper_id": "paper-b",
                        "source_name": "routed_extractions",
                        "domain": "clinical_outcome",
                        "evidence_type": "primary_evidence",
                        "study_doi": "10.1000/included-b",
                        "compound": "Psilocybin",
                        "entity_label": "Major depressive disorder",
                        "raw_row_json": "{}",
                    },
                ]
            ).to_parquet(kg_dir / "findings.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-a",
                        "evidence_id": "evidence-a",
                        "domain": "clinical_outcome",
                        "entity_kind": "condition_indication",
                        "entity_label": "Major depressive disorder",
                        "evidence_type": "primary_evidence",
                        "relation_type": "studied_for_condition",
                    },
                    {
                        "finding_id": "finding-b",
                        "evidence_id": "evidence-b",
                        "domain": "clinical_outcome",
                        "entity_kind": "condition_indication",
                        "entity_label": "Major depressive disorder",
                        "evidence_type": "primary_evidence",
                        "relation_type": "studied_for_condition",
                    },
                ]
            ).to_parquet(kg_dir / "evidence_edges.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "study_doi": "10.1000/not-in-graph",
                        "study_title": "Not in graph",
                        "normalization_status": "compound_unmapped",
                    },
                ]
            ).to_parquet(kg_dir / "normalization_audit.parquet", index=False)

            result = export_evidence_payload(kg_dir=kg_dir, out_dir=out_dir, require_fresh_author_tables=False)
            manifest = json.loads(result["manifest_path"].read_text())

        self.assertEqual(manifest["summary_stats"]["default"]["study_count"], 2)
        self.assertEqual(
            manifest["summary_stats"]["default"]["graph_study_coverage"],
            {"included_count": 2, "candidate_count": 3, "not_in_graph_count": 1},
        )
        self.assertEqual(manifest["summary_stats"]["default"]["graph_candidate_study_count"], 3)
        self.assertEqual(manifest["summary_stats"]["default"]["graph_excluded_study_count"], 1)
        self.assertEqual(manifest["summary_stats"]["default"]["graph_study_coverage"]["not_in_graph_count"], 1)
        self.assertEqual(
            manifest["summary_stats"]["default"]["normalized_finding_coverage"],
            {"included_count": 2, "candidate_count": 3, "without_findings_count": 1},
        )

    def test_exports_routed_clinical_endpoint_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            kg_dir = root / "kg"
            out_dir = root / "payload"
            kg_dir.mkdir()

            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-condition",
                        "paper_id": "paper-1",
                        "source_name": "routed_extractions",
                        "domain": "clinical_outcome",
                        "evidence_type": "primary_evidence",
                        "study_doi": "10.1000/condition",
                        "compound": "Psilocybin",
                        "entity_label": "Major depressive disorder",
                        "raw_row_json": json.dumps(
                            {
                                "compound": "Psilocybin",
                                "graph_entity_label": "Major depressive disorder",
                                "access_level": "article_text",
                            }
                        ),
                    },
                    {
                        "finding_id": "finding-symptom",
                        "paper_id": "paper-1",
                        "source_name": "routed_clinical_endpoints",
                        "domain": "clinical_outcome",
                        "evidence_type": "primary_evidence",
                        "study_doi": "10.1000/symptom",
                        "compound": "Psilocybin",
                        "entity_label": "Depression",
                        "raw_row_json": json.dumps(
                            {
                                "compound": "Psilocybin",
                                "graph_entity_label": "Depression",
                                "kg_entity_kind_override": "symptom_problem",
                                "endpoint_label_source": "clinical_symptom_endpoint",
                                "access_level": "article_text",
                            }
                        ),
                    },
                    {
                        "finding_id": "legacy-1",
                        "paper_id": "paper-2",
                        "source_name": "legacy_primary",
                        "domain": "legacy",
                        "evidence_type": "primary_evidence",
                        "raw_row_json": "{}",
                    },
                ]
            ).to_parquet(kg_dir / "findings.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-condition",
                        "evidence_id": "evidence-condition",
                        "domain": "clinical_outcome",
                        "entity_kind": "condition_indication",
                        "entity_label": "Major depressive disorder",
                        "evidence_type": "primary_evidence",
                        "relation_type": "studied_for_condition",
                    },
                    {
                        "finding_id": "finding-symptom",
                        "evidence_id": "evidence-symptom",
                        "domain": "clinical_outcome",
                        "entity_kind": "symptom_problem",
                        "entity_label": "Depression",
                        "evidence_type": "primary_evidence",
                        "relation_type": "studied_for_symptom",
                    },
                ]
            ).to_parquet(kg_dir / "evidence_edges.parquet", index=False)

            result = export_evidence_payload(kg_dir=kg_dir, out_dir=out_dir, require_fresh_author_tables=False)
            detail = json.loads(result["detail_bootstrap_paths"]["primary"].read_text())
            rows = detail_bootstrap_rows(detail)

        self.assertEqual(detail["row_count"], 2)
        labels = {finding["entity_label"] for finding in rows}
        self.assertEqual(labels, {"Major depressive disorder", "Depression"})
        symptom = next(finding for finding in rows if finding["entity_label"] == "Depression")
        self.assertEqual(symptom["entity_kind"], "symptom_problem")
        self.assertEqual(symptom["relation_type"], "studied_for_symptom")


if __name__ == "__main__":
    unittest.main()
