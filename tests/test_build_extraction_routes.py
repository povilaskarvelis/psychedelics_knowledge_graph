import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pipeline.extract.build_extraction_routes import (
    build_candidate_status_updates,
    build_extraction_routes,
    build_route_rows,
    doi_to_slug,
    fulltext_status_for_doi,
    prescreen_context_by_doi,
    thesis_or_dissertation_flags,
)


def write_source_identity_audit(
    root: Path,
    rows: list[dict],
) -> Path:
    identity_registry = root / "source_identity_registry.json"
    hash_registry = root / "source_identity_pdf_hash_registry.json"
    identity_registry.write_text("{}\n", encoding="utf-8")
    hash_registry.write_text("{}\n", encoding="utf-8")
    audit = root / "source_identity_audit.json"
    audit.write_text(
        json.dumps(
            {
                "identity_registry": {"path": str(identity_registry)},
                "pdf_hash_attestation_registry": {"path": str(hash_registry)},
                "rows": rows,
            }
        ),
        encoding="utf-8",
    )
    return audit


class BuildExtractionRoutesTests(unittest.TestCase):
    def test_fulltext_status_rejects_unverified_canonical_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fulltext_dir = Path(tmp) / "fulltext"
            doi = "10.1000/unverified"
            canonical = fulltext_dir / "articles" / f"{doi_to_slug(doi)}.json"
            canonical.parent.mkdir(parents=True)
            canonical.write_text(json.dumps({"best_char_count": 2000}), encoding="utf-8")
            audit = write_source_identity_audit(Path(tmp), [])

            status = fulltext_status_for_doi(
                doi,
                fulltext_dir,
                source_identity_audit=audit,
            )

        self.assertFalse(status["has_converted_full_text"])
        self.assertEqual(status["fulltext_artifact_paths"], "")
        self.assertEqual(status["fulltext_char_count"], 0)

    def test_primary_paper_uses_general_route_without_domain_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fulltext_dir = Path(tmp) / "fulltext"
            doi = "10.1000/primary"
            artifact = fulltext_dir / "articles" / f"{doi_to_slug(doi)}.json"
            artifact.parent.mkdir(parents=True)
            artifact.write_text(
                json.dumps(
                    {
                        "best_char_count": 1200,
                        "source_identity": {"status": "verified_exact_doi"},
                    }
                ),
                encoding="utf-8",
            )
            audit = write_source_identity_audit(
                Path(tmp),
                [
                    {
                        "requested_doi": doi,
                        "artifact_path": str(artifact.resolve()),
                        "identity_verified": True,
                    }
                ],
            )

            metadata_df = pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "study_title": "Psilocybin trial with imaging outcomes",
                        "study_year": "2024",
                        "abstract": "Patients were randomized and brain network outcomes were measured.",
                        "publication_type": "Journal Article | Randomized Controlled Trial",
                        "trial_registry_ids": "NCT1",
                        "best_pdf_url": "https://example.org/paper.pdf",
                        "open_access_status": "gold",
                    }
                ]
            )
            prescreen_df = pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "prescreen_decision": "retain",
                        "retained_for_extraction_candidate": True,
                        "prescreen_action": "retain_for_extraction_candidate",
                        "routing_tags": "clinical_outcome|safety|bridge_clinical_mechanism",
                    }
                ]
            )
            literature_df = pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "retained_for_extraction_candidate": True,
                        "source_family": "primary_or_unclear",
                        "literature_type_confidence": "medium",
                    }
                ]
            )

            rows = build_route_rows(
                metadata_df,
                prescreen_df,
                literature_df,
                fulltext_dir=fulltext_dir,
                generated_at_utc="2026-05-28T00:00:00+00:00",
                source_identity_audit=audit,
            )

        self.assertEqual({row["domain_route"] for row in rows}, {"general_primary"})
        self.assertEqual({row["prompt_profile"] for row in rows}, {"primary_general"})
        self.assertTrue(all(row["access_tier"] == "full_text_available" for row in rows))
        self.assertTrue(all(row["has_converted_full_text"] for row in rows))
        self.assertTrue(all(row["bridge_clinical_mechanism"] for row in rows))
        self.assertTrue(all(row["route_action"] == "extract_from_full_text" for row in rows))

    def test_build_extraction_routes_uses_gemini_domain_table_for_paper_type_and_domain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metadata_table = root / "metadata.parquet"
            prescreen_table = root / "prescreen.parquet"
            domain_table = root / "domain.parquet"
            output_table = root / "routes.parquet"
            summary_json = root / "summary.json"
            counts_csv = root / "counts.csv"

            doi = "10.1000/gemini-route"
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "study_title": "Psilocybin trial outcomes",
                        "study_year": "2024",
                        "abstract": "A randomized trial reports depression outcomes.",
                        "publication_type": "Journal Article",
                    }
                ]
            ).to_parquet(metadata_table, engine="pyarrow", index=False)
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "prescreen_decision": "retain",
                        "retained_for_extraction_candidate": True,
                        "prescreen_action": "retain_for_extraction_candidate",
                        "routing_tags": "clinical_outcome",
                    }
                ]
            ).to_parquet(prescreen_table, engine="pyarrow", index=False)
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "retained_for_extraction_candidate": True,
                        "screening_decision": "include_in_scope",
                        "domain_route": "clinical_outcome",
                        "domain_tags": "clinical_outcome",
                        "paper_type_group": "primary",
                        "paper_type": "primary",
                        "paper_type_reason": "Reports original empirical outcomes.",
                        "domain_route_confidence": "high",
                    }
                ]
            ).to_parquet(domain_table, engine="pyarrow", index=False)

            build_extraction_routes(
                metadata_table=metadata_table,
                candidate_table=root / "candidate_papers.parquet",
                prescreen_table=prescreen_table,
                domain_table=domain_table,
                manual_overrides_path=None,
                manual_fulltext_access_overrides_path=None,
                fulltext_dir=root / "fulltext",
                paper_root=root / "papers",
                output_table=output_table,
                summary_json=summary_json,
                counts_csv=counts_csv,
                update_candidate_table=False,
            )

            routes = pd.read_parquet(output_table)

        self.assertEqual(routes.loc[0, "source_family"], "primary")
        self.assertEqual(routes.loc[0, "source_type"], "primary")
        self.assertEqual(routes.loc[0, "domain_route"], "clinical_outcome")
        self.assertEqual(routes.loc[0, "prompt_profile"], "primary_clinical")

    def test_dissertation_metadata_overrides_model_primary_classification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metadata_table = root / "metadata.parquet"
            prescreen_table = root / "prescreen.parquet"
            domain_table = root / "domain.parquet"
            output_table = root / "routes.parquet"
            summary_json = root / "summary.json"
            counts_csv = root / "counts.csv"

            doi = "10.1000/model-called-primary-thesis"
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "study_title": "Ketamine thesis",
                        "study_year": "2024",
                        "abstract": "This thesis reports original mixed-methods ketamine research.",
                        "publication_type": "dissertation",
                    }
                ]
            ).to_parquet(metadata_table, engine="pyarrow", index=False)
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "prescreen_decision": "retain",
                        "retained_for_extraction_candidate": True,
                        "prescreen_action": "retain_for_extraction_candidate",
                        "routing_tags": "clinical_outcome|intervention_context",
                    }
                ]
            ).to_parquet(prescreen_table, engine="pyarrow", index=False)
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "retained_for_extraction_candidate": True,
                        "screening_decision": "include_in_scope",
                        "domain_route": "clinical_outcome",
                        "all_domain_tags": "clinical_outcome|intervention_context",
                        "paper_type_group": "primary",
                        "paper_type": "primary",
                        "paper_type_reason": "Model says this thesis reports original empirical outcomes.",
                    }
                ]
            ).to_parquet(domain_table, engine="pyarrow", index=False)

            build_extraction_routes(
                metadata_table=metadata_table,
                candidate_table=root / "candidate_papers.parquet",
                prescreen_table=prescreen_table,
                domain_table=domain_table,
                manual_overrides_path=None,
                manual_fulltext_access_overrides_path=None,
                fulltext_dir=root / "fulltext",
                paper_root=root / "papers",
                output_table=output_table,
                summary_json=summary_json,
                counts_csv=counts_csv,
                update_candidate_table=False,
            )

            routes = pd.read_parquet(output_table)

        self.assertEqual(len(routes), 1)
        self.assertFalse(bool(routes.loc[0, "retained_for_extraction_candidate"]))
        self.assertEqual(routes.loc[0, "source_family"], "non_primary_publication")
        self.assertEqual(routes.loc[0, "source_type"], "non_primary_publication")
        self.assertEqual(
            routes.loc[0, "non_primary_flags"],
            "thesis_or_dissertation_publication_type|thesis_or_dissertation_title|thesis_or_dissertation_abstract",
        )
        self.assertEqual(routes.loc[0, "domain_route"], "context_only")
        self.assertEqual(routes.loc[0, "route_action"], "skip_or_context_only")
        self.assertEqual(routes.loc[0, "prompt_profile"], "context_only_or_skip")

    def test_abstract_only_thesis_mention_does_not_override_journal_article(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metadata_table = root / "metadata.parquet"
            prescreen_table = root / "prescreen.parquet"
            domain_table = root / "domain.parquet"
            output_table = root / "routes.parquet"
            summary_json = root / "summary.json"
            counts_csv = root / "counts.csv"

            doi = "10.1000/abstract-only-thesis-mention"
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "study_title": "Psilocybin clinical outcomes",
                        "study_year": "2024",
                        "abstract": "The background cites a doctoral thesis, but this paper reports a trial.",
                        "publication_type": "Journal Article",
                        "study_journal": "Example Medical Journal",
                    }
                ]
            ).to_parquet(metadata_table, engine="pyarrow", index=False)
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "prescreen_decision": "retain",
                        "retained_for_extraction_candidate": True,
                        "prescreen_action": "retain_for_extraction_candidate",
                        "routing_tags": "clinical_outcome",
                    }
                ]
            ).to_parquet(prescreen_table, engine="pyarrow", index=False)
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "retained_for_extraction_candidate": True,
                        "screening_decision": "include_in_scope",
                        "domain_route": "clinical_outcome",
                        "all_domain_tags": "clinical_outcome",
                        "paper_type_group": "primary",
                        "paper_type": "primary",
                        "paper_type_reason": "Reports original empirical outcomes.",
                    }
                ]
            ).to_parquet(domain_table, engine="pyarrow", index=False)

            build_extraction_routes(
                metadata_table=metadata_table,
                candidate_table=root / "candidate_papers.parquet",
                prescreen_table=prescreen_table,
                domain_table=domain_table,
                manual_overrides_path=None,
                manual_fulltext_access_overrides_path=None,
                fulltext_dir=root / "fulltext",
                paper_root=root / "papers",
                output_table=output_table,
                summary_json=summary_json,
                counts_csv=counts_csv,
                update_candidate_table=False,
            )

            routes = pd.read_parquet(output_table)

        self.assertEqual(thesis_or_dissertation_flags(routes.loc[0].to_dict()), "")
        self.assertTrue(bool(routes.loc[0, "retained_for_extraction_candidate"]))
        self.assertEqual(routes.loc[0, "source_family"], "primary")
        self.assertEqual(routes.loc[0, "domain_route"], "clinical_outcome")
        self.assertEqual(routes.loc[0, "route_action"], "extract_from_abstract_only")

    def test_secondary_meta_analysis_uses_general_review_profile_without_domain_table(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/meta",
                    "study_title": "A meta-analysis of MDMA treatment",
                    "study_year": "2022",
                    "abstract": "This meta-analysis reviewed randomized trials.",
                    "publication_type": "Journal Article | Meta-Analysis",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/meta",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome|molecular_target",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/meta",
                    "retained_for_extraction_candidate": True,
                    "source_family": "secondary_literature",
                    "primary_secondary_source_type": "meta_analysis",
                    "secondary_source_types": "meta_analysis|review",
                    "literature_type_confidence": "high",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual({row["domain_route"] for row in rows}, {"general_topic_coverage"})
        self.assertEqual({row["prompt_profile"] for row in rows}, {"secondary_meta_analysis"})
        self.assertEqual({row["schema_profile"] for row in rows}, {"meta_analysis_evidence_schema"})
        self.assertEqual({row["access_tier"] for row in rows}, {"abstract_only"})
        self.assertEqual({row["route_confidence"] for row in rows}, {"low"})
        self.assertIn("no model-assigned domain table supplied", rows[0]["route_basis"])

    def test_manual_fulltext_access_override_suppresses_pdf_download_route(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/not-oa",
                    "study_title": "Closed article with misleading PDF URL",
                    "study_year": "2024",
                    "abstract": "This retained article has enough abstract text for fallback extraction.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "https://example.org/article.pdf",
                    "pdf_url_candidates": "https://example.org/article.pdf",
                    "open_access_status": "green",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/not-oa",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/not-oa",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-06-20T00:00:00+00:00",
            manual_fulltext_access_overrides={
                "10.1000/not-oa": {
                    "manual_access_action": "suppress_pdf_download",
                    "open_access_status": "closed",
                    "open_access_is_oa": False,
                    "manual_reason": "Manual review: no open PDF access.",
                }
            },
        )

        self.assertEqual({row["access_tier"] for row in rows}, {"abstract_only"})
        self.assertEqual({row["route_action"] for row in rows}, {"extract_from_abstract_only"})
        self.assertEqual({row["open_access_status"] for row in rows}, {"closed"})
        self.assertEqual({row["best_pdf_url"] for row in rows}, {""})
        self.assertEqual({row["manual_fulltext_access_action"] for row in rows}, {"suppress_pdf_download"})
        self.assertEqual({row["source_text_state"] for row in rows}, {"public_abstract_only"})
        self.assertEqual({row["source_identity_verified"] for row in rows}, {False})

    def test_abstract_only_override_wins_over_a_valid_local_pdf(self) -> None:
        doi = "10.1000/non-english"
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "study_title": "A valid non-English full-text article",
                    "study_year": "2024",
                    "abstract": "An English abstract remains available for extraction.",
                    "publication_type": "Journal Article",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                }
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            paper_root = Path(tmp) / "papers"
            paper_root.mkdir(parents=True)
            (paper_root / f"{doi_to_slug(doi)}__reviewed.pdf").write_bytes(b"%PDF-1.4\n")
            rows = build_route_rows(
                metadata_df,
                prescreen_df,
                literature_df,
                fulltext_dir=Path(tmp) / "fulltext",
                generated_at_utc="2026-07-10T00:00:00+00:00",
                paper_root=paper_root,
                manual_fulltext_access_overrides={
                    doi: {
                        "manual_access_action": "abstract_only",
                        "manual_reason": "Full text retained, but current extraction uses the English abstract.",
                    }
                },
            )

        self.assertEqual({row["access_tier"] for row in rows}, {"abstract_only"})
        self.assertEqual({row["route_action"] for row in rows}, {"extract_from_abstract_only"})
        self.assertEqual({row["source_text_state"] for row in rows}, {"public_abstract_only"})
        self.assertEqual(
            {row["source_text_state_reason"] for row in rows},
            {"Full text retained, but current extraction uses the English abstract."},
        )

    def test_prescreen_excluded_preprint_does_not_route(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1101/2025.04.16.649217",
                    "study_title": "Speech markers of psychedelic-induced psychological change",
                    "study_year": "2025",
                    "abstract": "A preprint abstract.",
                    "publication_type": "posted-content",
                    "study_journal": "bioRxiv",
                    "publisher": "openRxiv",
                    "best_pdf_url": "https://www.biorxiv.org/content/10.1101/2025.04.16.649217.full.pdf",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1101/2025.04.16.649217",
                    "prescreen_decision": "exclude",
                    "retained_for_extraction_candidate": False,
                    "prescreen_action": "exclude_preprint_or_unpublished",
                    "routing_tags": "",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1101/2025.04.16.649217",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(rows, [])

    def test_non_evidence_artifact_blocks_stale_model_route_rows(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.3389/fnins.2025.1554049.s002",
                    "study_title": "Table 2_Dose-dependent changes in brain activity following psilocybin.xlsx",
                    "study_year": "2025",
                    "abstract": "Dose-dependent brain activity and functional connectivity are reported.",
                    "publication_type": "dataset",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.3389/fnins.2025.1554049.s002",
                    "prescreen_decision": "exclude",
                    "retained_for_extraction_candidate": False,
                    "prescreen_action": "exclude_non_evidence_artifact",
                    "routing_tags": "",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.3389/fnins.2025.1554049.s002",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": "10.3389/fnins.2025.1554049.s002",
                    "retained_for_extraction_candidate": True,
                    "domain_route": "brain_system",
                    "domain_tag": "brain_system",
                    "screening_decision": "include_in_scope",
                    "paper_type_group": "primary",
                    "paper_type": "primary",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            domain_df=domain_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(rows, [])

    def test_candidate_status_updates_summarize_routes_and_prescreen_exclusions(self) -> None:
        generated_at = "2026-05-28T00:00:00+00:00"
        candidate_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/article",
                    "publication_type": "Journal Article",
                    "study_title": "Published trial",
                    "abstract": "A trial abstract.",
                },
                {
                    "doi": "10.1101/2025.04.16.649217",
                    "publication_type": "posted-content",
                    "study_journal": "bioRxiv",
                    "study_title": "Preprint",
                    "abstract": "A preprint abstract.",
                },
                {
                    "doi": "10.1000/thesis",
                    "publication_type": "dissertation",
                    "study_title": "Ketamine thesis",
                    "abstract": "This thesis is concerned with ketamine.",
                },
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/article",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                },
                {
                    "doi": "10.1101/2025.04.16.649217",
                    "prescreen_decision": "exclude",
                    "retained_for_extraction_candidate": False,
                    "prescreen_action": "exclude_preprint_or_unpublished",
                    "prescreen_reason": "Record appears to be a preprint.",
                    "routing_tags": "",
                },
                {
                    "doi": "10.1000/thesis",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                },
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/article",
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "high",
                },
                {
                    "doi": "10.1000/thesis",
                    "source_family": "non_primary_publication",
                    "non_primary_flags": "thesis_or_dissertation_publication_type|thesis_or_dissertation_abstract",
                    "literature_type_confidence": "high",
                }
            ]
        )
        route_rows = [
            {
                "doi": "10.1000/article",
                "retained_for_extraction_candidate": True,
                "route_action": "extract_from_full_text",
                "access_tier": "full_text_available",
                "domain_route": "clinical_outcome",
                "domain_screening_decision": "include_in_scope",
                "prompt_profile": "primary_clinical",
                "schema_profile": "primary_evidence_schema",
                "has_converted_full_text": True,
                "fulltext_artifact_paths": "/tmp/article.json",
                "fulltext_char_count": 1234,
            },
            {
                "doi": "10.1000/thesis",
                "retained_for_extraction_candidate": False,
                "route_action": "skip_or_context_only",
                "access_tier": "full_text_available",
                "domain_route": "context_only",
                "prompt_profile": "context_only_or_skip",
                "schema_profile": "context_only_schema",
            }
        ]
        updates = build_candidate_status_updates(
            candidate_df=candidate_df,
            prescreen_df=prescreen_df,
            literature_df=literature_df,
            route_rows=route_rows,
            generated_at_utc=generated_at,
        )
        by_doi = {row["doi"]: row for row in updates.to_dict("records")}

        article = by_doi["10.1000/article"]
        self.assertEqual(article["publication_stage"], "published")
        self.assertTrue(article["retained_for_extraction_candidate"])
        self.assertEqual(article["extraction_route_status"], "ready_for_article_text_extraction")
        self.assertEqual(article["extraction_domain_routes"], "clinical_outcome")
        self.assertEqual(article["best_extraction_access_tier"], "full_text_available")
        self.assertTrue(article["has_converted_full_text"])
        self.assertEqual(article["source_text_state"], "public_full_text_verified")
        self.assertTrue(article["source_identity_verified"])

        preprint = by_doi["10.1101/2025.04.16.649217"]
        self.assertEqual(preprint["publication_stage"], "preprint")
        self.assertFalse(preprint["retained_for_extraction_candidate"])
        self.assertFalse(preprint["prescreen_retained_for_extraction_candidate"])
        self.assertEqual(preprint["prescreen_actions"], "exclude_preprint_or_unpublished")
        self.assertEqual(preprint["extraction_route_status"], "not_retained_for_extraction")
        self.assertEqual(preprint["source_text_state"], "excluded_from_extraction")

        thesis = by_doi["10.1000/thesis"]
        self.assertFalse(thesis["retained_for_extraction_candidate"])
        self.assertEqual(thesis["literature_source_family"], "non_primary_publication")
        self.assertEqual(
            thesis["non_primary_flags"],
            "thesis_or_dissertation_publication_type|thesis_or_dissertation_abstract",
        )
        self.assertEqual(thesis["extraction_route_status"], "context_only_or_skip")

    def test_published_article_with_preprint_pdf_url_is_not_held_out(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1021/acschemneuro.2c00123",
                    "study_title": "Acute behavioral and neurochemical effects in adult zebrafish",
                    "study_year": "2022",
                    "abstract": "A journal article abstract.",
                    "publication_type": "Journal Article | Research Support, Non-U.S. Gov't",
                    "study_journal": "ACS Chemical Neuroscience",
                    "publisher": "American Chemical Society (ACS)",
                    "best_pdf_url": "https://www.biorxiv.org/content/10.1101/2022.01.19.476767.full.pdf",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1021/acschemneuro.2c00123",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "molecular_target",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1021/acschemneuro.2c00123",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )
        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["route_action"], "download_pdf_then_extract")

    def test_valid_local_pdf_gets_local_pdf_route_before_pdf_url_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper_root = root / "papers"
            pdf_path = paper_root / "archive" / "excluded" / "10.1000_local_pdf__abc123.pdf"
            pdf_path.parent.mkdir(parents=True)
            pdf_path.write_bytes(b"%PDF-1.7\nvalid enough for the route audit")
            metadata_df = pd.DataFrame(
                [
                    {
                        "doi": "10.1000/local-pdf",
                        "study_title": "Psilocybin trial with a local PDF",
                        "abstract": "A clinical trial abstract.",
                        "publication_type": "Journal Article",
                        "best_pdf_url": "https://example.org/paper.pdf",
                    }
                ]
            )
            prescreen_df = pd.DataFrame(
                [
                    {
                        "doi": "10.1000/local-pdf",
                        "prescreen_decision": "retain",
                        "retained_for_extraction_candidate": True,
                        "prescreen_action": "retain_for_extraction_candidate",
                        "routing_tags": "clinical_outcome",
                    }
                ]
            )
            literature_df = pd.DataFrame(
                [
                    {
                        "doi": "10.1000/local-pdf",
                        "retained_for_extraction_candidate": True,
                        "source_family": "primary_or_unclear",
                        "literature_type_confidence": "medium",
                    }
                ]
            )

            rows = build_route_rows(
                metadata_df,
                prescreen_df,
                literature_df,
                fulltext_dir=root / "missing-fulltext",
                paper_root=paper_root,
                generated_at_utc="2026-05-28T00:00:00+00:00",
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["access_tier"], "local_pdf_available")
        self.assertEqual(rows[0]["route_action"], "convert_local_pdf_then_extract")
        self.assertTrue(rows[0]["has_local_pdf"])
        self.assertIn("10.1000_local_pdf__abc123.pdf", rows[0]["local_pdf_paths"])
        self.assertTrue(rows[0]["has_pdf_url"])
        self.assertTrue(rows[0]["has_probable_pdf_url"])
        self.assertEqual(rows[0]["pdf_url_quality"], "probable_pdf")
        self.assertFalse(rows[0]["has_converted_full_text"])

    def test_probable_pdf_url_routes_to_download(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/probable-pdf",
                    "study_title": "Psilocybin study with probable PDF URL",
                    "abstract": "A study abstract.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "https://publisher.example/content/pdf/10.1000/probable.pdf",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/probable-pdf",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/probable-pdf",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(rows[0]["access_tier"], "pdf_download_url_available")
        self.assertEqual(rows[0]["route_action"], "download_pdf_then_extract")
        self.assertTrue(rows[0]["has_pdf_url"])
        self.assertTrue(rows[0]["has_probable_pdf_url"])
        self.assertEqual(rows[0]["pdf_url_quality"], "probable_pdf")
        self.assertIn("content/pdf", rows[0]["probable_pdf_url_candidates"])

    def test_weak_pdf_url_stays_visible_but_does_not_route_to_automated_download(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/landing-url",
                    "study_title": "Psilocybin study with landing page URL",
                    "abstract": "A study abstract.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "https://doi.org/10.1000/landing-url",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/landing-url",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/landing-url",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(rows[0]["access_tier"], "abstract_only")
        self.assertEqual(rows[0]["route_action"], "extract_from_abstract_only")
        self.assertTrue(rows[0]["has_pdf_url"])
        self.assertFalse(rows[0]["has_probable_pdf_url"])
        self.assertEqual(rows[0]["pdf_url_quality"], "possible_landing_page")
        self.assertEqual(rows[0]["probable_pdf_url_candidates"], "")
        self.assertEqual(rows[0]["other_url_candidates"], "https://doi.org/10.1000/landing-url")

    def test_primary_gap_domain_tags_do_not_create_specific_routes_without_domain_table(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/gaps",
                    "study_title": "Psilocybin session and exposure study",
                    "abstract": "The study measured plasma concentration, mystical experience, and preparation.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/gaps",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "subjective_experience|pharmacokinetics_exposure|intervention_context|real_world_use_public_health",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/gaps",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual({row["domain_route"] for row in rows}, {"general_primary"})
        self.assertEqual({row["prompt_profile"] for row in rows}, {"primary_general"})
        self.assertEqual(rows[0]["domain_tags"], "")
        self.assertIn("no model-assigned domain table supplied", rows[0]["route_basis"])

    def test_domain_routing_table_overrides_prescreen_tag_fallback(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/domain-table",
                    "study_title": "Psilocybin and brain network connectivity",
                    "abstract": "Brain network outcomes were measured.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/domain-table",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome|brain_system",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/domain-table",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/domain-table",
                    "retained_for_extraction_candidate": True,
                    "domain_route": "brain_system",
                    "domain_tag": "brain_system",
                    "all_domain_tags": "clinical_outcome|brain_system",
                    "primary_domain": "brain_system",
                    "screening_decision": "include_for_extraction",
                    "screening_reason": "In-scope brain-system evidence.",
                    "methodological_validity_tags": "blinding_expectancy_validity",
                    "domain_route_confidence": "medium",
                    "domain_route_basis": "domain tag:brain_system",
                    "needs_human_review": True,
                    "model": "gemini-3-flash-preview",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            domain_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["domain_route"], "brain_system")
        self.assertEqual(rows[0]["prompt_profile"], "primary_brain_system")
        self.assertEqual(rows[0]["domain_routing_primary_domain"], "brain_system")
        self.assertEqual(rows[0]["domain_screening_decision"], "include_for_extraction")
        self.assertEqual(rows[0]["domain_screening_reason"], "In-scope brain-system evidence.")
        self.assertEqual(rows[0]["methodological_validity_tags"], "blinding_expectancy_validity")
        self.assertEqual(rows[0]["domain_routing_model"], "gemini-3-flash-preview")
        self.assertTrue(rows[0]["domain_needs_human_review"])
        self.assertIn("domain_route_basis:domain tag:brain_system", rows[0]["route_basis"])

    def test_methodological_validity_tags_do_not_replace_domain_route(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/methods",
                    "study_title": "Blinding in psychedelic trials",
                    "abstract": "The study evaluates expectancy and blinding validity.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/methods",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/methods",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/methods",
                    "retained_for_extraction_candidate": True,
                    "domain_route": "clinical_outcome",
                    "domain_tag": "clinical_outcome",
                    "all_domain_tags": "clinical_outcome",
                    "primary_domain": "clinical_outcome",
                    "screening_decision": "include_for_extraction",
                    "methodological_validity_tags": "blinding_expectancy_validity",
                    "domain_route_confidence": "high",
                    "domain_route_basis": "domain tag:clinical_outcome",
                    "needs_human_review": False,
                    "model": "gemini-3-flash-preview",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            domain_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["domain_route"], "clinical_outcome")
        self.assertEqual(rows[0]["prompt_profile"], "primary_clinical")
        self.assertEqual(rows[0]["methodological_validity_tags"], "blinding_expectancy_validity")
        self.assertEqual(rows[0]["schema_profile"], "primary_evidence_schema")

    def test_model_excluded_record_does_not_create_extraction_task(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/out",
                    "study_title": "Non-psychedelic depression paper",
                    "abstract": "This paper studies a non-psychedelic treatment.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/out",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/out",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/out",
                    "retained_for_extraction_candidate": False,
                    "domain_route": "general_topic",
                    "domain_tag": "",
                    "all_domain_tags": "",
                    "primary_domain": "general_topic",
                    "screening_decision": "exclude_out_of_scope",
                    "screening_reason": "No in-scope psychedelic evidence.",
                    "methodological_validity_tags": "",
                    "domain_route_confidence": "high",
                    "domain_route_basis": "Gemini title/abstract domain routing: out of scope",
                    "needs_human_review": False,
                    "model": "gemini-3-flash-preview",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            domain_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["domain_route"], "screening_excluded")
        self.assertEqual(rows[0]["route_action"], "exclude_after_model_screen")
        self.assertEqual(rows[0]["prompt_profile"], "no_extraction")
        self.assertEqual(rows[0]["schema_profile"], "no_extraction_schema")
        self.assertFalse(rows[0]["retained_for_extraction_candidate"])
        self.assertEqual(rows[0]["domain_screening_decision"], "exclude_out_of_scope")

    def test_curated_screening_exclusion_overrides_an_in_scope_model_route(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/out",
                    "study_title": "Broad treatment guideline",
                    "abstract": "A broad guideline that mentions ketamine only as background.",
                    "publication_type": "Journal Article",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/out",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/out",
                    "retained_for_extraction_candidate": True,
                    "domain_route": "clinical_outcome",
                    "screening_decision": "include_in_scope",
                }
            ]
        )
        reason = "No specific psychedelic, ketamine, or entactogen recommendation."

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            domain_df=domain_df,
            screening_overrides={
                "10.1000/out": {"decision": "exclude_out_of_scope", "reason": reason}
            },
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-07-14T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["retained_for_extraction_candidate"])
        self.assertEqual(rows[0]["domain_route"], "screening_excluded")
        self.assertEqual(rows[0]["domain_screening_decision"], "exclude_out_of_scope")
        self.assertEqual(rows[0]["domain_screening_reason"], reason)

    def test_non_primary_publication_collapses_to_context_route(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/editorial",
                    "study_title": "Editorial on psychedelic therapy",
                    "abstract": "This editorial discusses the field.",
                    "publication_type": "Editorial",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/editorial",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome|safety|molecular_target",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/editorial",
                    "retained_for_extraction_candidate": True,
                    "source_family": "non_primary_publication",
                    "non_primary_flags": "non_primary_publication_type",
                    "literature_type_confidence": "medium",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["domain_route"], "context_only")
        self.assertEqual(rows[0]["prompt_profile"], "context_only_or_skip")
        self.assertEqual(rows[0]["schema_profile"], "context_only_schema")
        self.assertEqual(rows[0]["route_action"], "skip_or_context_only")
        self.assertFalse(rows[0]["retained_for_extraction_candidate"])

    def test_manual_context_only_override_collapses_to_non_extraction_route(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/bibliometric",
                    "study_title": "Bibliometric analysis of psychedelic clinical studies",
                    "abstract": "This article maps the literature.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/bibliometric",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/bibliometric",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/bibliometric",
                    "domain_route": "general_topic",
                    "all_domain_tags": "clinical_outcome",
                    "primary_domain": "general_topic",
                    "screening_decision": "include_in_scope",
                    "screening_reason": "General topic.",
                    "model": "gemini-3-flash-preview",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            domain_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-30T00:00:00+00:00",
            manual_overrides={
                "10.1000/bibliometric": {
                    "manual_action": "context_only",
                    "manual_reason": "Manual review: field-mapping paper.",
                }
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["domain_route"], "context_only")
        self.assertEqual(rows[0]["prompt_profile"], "context_only_or_skip")
        self.assertEqual(rows[0]["route_action"], "skip_or_context_only")
        self.assertEqual(rows[0]["domain_screening_decision"], "manual_context_only")
        self.assertFalse(rows[0]["retained_for_extraction_candidate"])

    def test_manual_domain_override_replaces_general_topic_route(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/ibogaine-review",
                    "study_title": "Ibogaine: a comprehensive literature review",
                    "abstract": "This review covers anti-addiction evidence.",
                    "publication_type": "Review",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/ibogaine-review",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/ibogaine-review",
                    "retained_for_extraction_candidate": True,
                    "source_family": "secondary_literature",
                    "primary_secondary_source_type": "literature_review",
                    "secondary_source_types": "literature_review|review",
                    "literature_type_confidence": "medium",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/ibogaine-review",
                    "domain_route": "general_topic",
                    "all_domain_tags": "clinical_outcome",
                    "primary_domain": "general_topic",
                    "screening_decision": "include_in_scope",
                    "screening_reason": "General topic.",
                    "model": "gemini-3-flash-preview",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            domain_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-30T00:00:00+00:00",
            manual_overrides={
                "10.1000/ibogaine-review": {
                    "manual_action": "route_domains",
                    "manual_domain_routes": "clinical_outcome|safety_tolerability",
                    "manual_reason": "Manual review: ibogaine clinical review.",
                }
            },
        )

        self.assertEqual({row["domain_route"] for row in rows}, {"clinical_outcome", "safety_tolerability"})
        self.assertEqual({row["prompt_profile"] for row in rows}, {"secondary_narrative_review"})
        self.assertEqual({row["domain_screening_decision"] for row in rows}, {"manual_include_in_scope"})
        self.assertTrue(all(row["retained_for_extraction_candidate"] for row in rows))

    def test_manual_source_type_override_reclassifies_qualitative_meta_review(self) -> None:
        doi = "10.1000/qualitative-review"
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "study_title": "Integrating meta-analyses qualitatively",
                    "abstract": "A systematic review integrated prior meta-analyses qualitatively.",
                    "publication_type": "Systematic Review | Meta-Analysis",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "domain_route": "clinical_outcome",
                    "all_domain_tags": "clinical_outcome",
                    "screening_decision": "include_in_scope",
                    "paper_type_group": "secondary_literature",
                    "paper_type": "meta_analysis",
                    "primary_secondary_source_type": "meta_analysis",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            domain_df=domain_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-07-13T00:00:00+00:00",
            manual_overrides={
                doi: {
                    "manual_source_family": "secondary_literature",
                    "manual_source_type": "systematic_review",
                    "manual_primary_secondary_source_type": "systematic_review",
                    "manual_literature_type_confidence": "high",
                    "manual_paper_type_reason": "The paper integrates prior meta-analyses qualitatively.",
                }
            },
        )

        self.assertEqual({row["source_family"] for row in rows}, {"secondary_literature"})
        self.assertEqual({row["source_type"] for row in rows}, {"systematic_review"})
        self.assertEqual(
            {row["primary_secondary_source_type"] for row in rows}, {"systematic_review"}
        )
        self.assertEqual({row["prompt_profile"] for row in rows}, {"secondary_structured_review"})

    def test_prescreen_context_ignores_excluded_rows(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/a",
                    "prescreen_decision": "exclude",
                    "retained_for_extraction_candidate": False,
                    "routing_tags": "clinical_outcome",
                },
                {
                    "doi": "10.1000/a",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "routing_tags": "molecular_target",
                },
            ]
        )

        context = prescreen_context_by_doi(df)

        self.assertEqual(context["10.1000/a"]["routing_tags"], ["molecular_target"])


if __name__ == "__main__":
    unittest.main()
