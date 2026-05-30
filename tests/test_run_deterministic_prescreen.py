import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from pipeline.review.run_deterministic_prescreen import (
    build_prescreen_decisions,
    build_summary_rows,
    run,
)


class TableDeterministicPrescreenTest(unittest.TestCase):
    def test_builds_one_decision_per_doi_dataset_and_uses_metadata_abstract(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/psilo",
                    "datasets": "disorder",
                    "study_title": "Metadata title should win",
                    "abstract": "",
                    "current_pipeline_status": "metadata_enriched",
                    "source_types": "metadata_enrichment",
                },
                {
                    "doi": "10.example/exercise",
                    "datasets": "disorder",
                    "study_title": "Exercise intervention for depression",
                    "abstract": "This randomized trial tested exercise for depression.",
                    "current_pipeline_status": "metadata_enriched",
                    "source_types": "metadata_enrichment",
                },
            ]
        )
        metadata = pd.DataFrame(
            [
                {
                    "doi": "10.example/psilo",
                    "study_title": "Psilocybin therapy for depression",
                    "abstract": "Psilocybin therapy reduced depression symptoms.",
                    "metadata_enrichment_status": "enriched",
                    "metadata_enrichment_run_id": "test_metadata",
                }
            ]
        )
        contexts = pd.DataFrame(
            [
                {
                    "doi": "10.example/psilo",
                    "dataset": "disorder",
                    "compound": "Psilocybin",
                    "entity": "Major depressive disorder",
                    "entity_type": "indication",
                }
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            metadata,
            contexts,
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )
        by_doi = {row["doi"]: row for row in rows}

        self.assertEqual(len(rows), 2)
        self.assertEqual(by_doi["10.example/psilo"]["study_title"], "Psilocybin therapy for depression")
        self.assertEqual(by_doi["10.example/psilo"]["prescreen_decision"], "retain")
        self.assertEqual(by_doi["10.example/psilo"]["metadata_enrichment_run_id"], "test_metadata")
        self.assertEqual(by_doi["10.example/exercise"]["prescreen_action"], "exclude_obvious_irrelevant")
        self.assertFalse(by_doi["10.example/exercise"]["retained_for_extraction_candidate"])

    def test_missing_abstract_excluded_unless_downstream_protected(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/missing",
                    "datasets": "mechanistic",
                    "study_title": "Psilocybin and default mode network",
                    "abstract": "",
                    "current_pipeline_status": "metadata_enriched",
                    "source_types": "metadata_enrichment",
                },
                {
                    "doi": "10.example/protected",
                    "datasets": "mechanistic",
                    "study_title": "Curated paper without abstract",
                    "abstract": "",
                    "current_pipeline_status": "curated_claim",
                    "source_types": "curated_claim",
                },
            ]
        )
        contexts = pd.DataFrame(
            [
                {
                    "doi": "10.example/protected",
                    "dataset": "mechanistic",
                    "compound": "Psilocybin",
                    "entity": "Default mode network",
                    "entity_type": "brain_region_or_network",
                    "flag_has_curated_claim": True,
                }
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            contexts,
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )
        by_doi = {row["doi"]: row for row in rows}

        self.assertEqual(by_doi["10.example/missing"]["prescreen_action"], "exclude_missing_abstract")
        self.assertEqual(by_doi["10.example/missing"]["prescreen_decision"], "exclude")
        self.assertEqual(by_doi["10.example/protected"]["deterministic_action"], "exclude_missing_abstract")
        self.assertEqual(by_doi["10.example/protected"]["prescreen_action"], "retain_existing_downstream")
        self.assertTrue(by_doi["10.example/protected"]["downstream_protected"])
        self.assertFalse(by_doi["10.example/protected"]["retained_for_extraction_candidate"])
        self.assertIn("brain_system", by_doi["10.example/protected"]["routing_tags"])

    def test_placeholder_and_citation_only_abstracts_are_treated_as_missing(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/placeholder",
                    "datasets": "disorder",
                    "study_title": "Esketamine for Treatment-Resistant Depression",
                    "abstract": "International audience",
                    "current_pipeline_status": "metadata_enriched",
                    "source_types": "metadata_enrichment",
                },
                {
                    "doi": "10.example/citation-parenthetical",
                    "datasets": "mechanistic",
                    "study_title": "Cultural Therapy - A New Conception of Treatment",
                    "abstract": (
                        "(1974). Cultural Therapy - A New Conception of Treatment. "
                        "Journal of Psychedelic Drugs: Vol. 6, No. 2, pp. 173-177."
                    ),
                    "current_pipeline_status": "metadata_enriched",
                    "source_types": "metadata_enrichment",
                },
                {
                    "doi": "10.example/citation-journal",
                    "datasets": "disorder",
                    "study_title": "S.7.3 - KETAMINE AND NMDA RECEPTOR MODULATION",
                    "abstract": (
                        "Behavioural Pharmacology: October 2013 - Volume 24 - Issue - "
                        "p e8-e9 doi: 10.example/citation-journal"
                    ),
                    "current_pipeline_status": "metadata_enriched",
                    "source_types": "metadata_enrichment",
                },
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-05-30T00:00:00+00:00",
        )
        by_doi = {row["doi"]: row for row in rows}

        for doi in by_doi:
            self.assertEqual(by_doi[doi]["prescreen_action"], "exclude_missing_abstract")
            self.assertEqual(by_doi[doi]["prescreen_decision"], "exclude")
            self.assertFalse(by_doi[doi]["has_abstract"])
            self.assertFalse(by_doi[doi]["retained_for_extraction_candidate"])

    def test_no_title_container_record_excluded_even_with_matching_abstract(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/issue",
                    "datasets": "mechanistic",
                    "study_title": "",
                    "abstract": "Psilocybin was discussed in a neuroscience context.",
                    "publication_type": "journal-issue",
                }
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(rows[0]["prescreen_decision"], "exclude")
        self.assertEqual(rows[0]["prescreen_action"], "exclude_non_paper_container")
        self.assertFalse(rows[0]["retained_for_extraction_candidate"])

    def test_non_evidence_artifacts_are_excluded_before_routing(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/correction",
                    "datasets": "disorder",
                    "study_title": "Author Correction: MDMA-assisted therapy for PTSD",
                    "abstract": "MDMA-assisted therapy reduced PTSD symptoms.",
                    "publication_type": "Published Erratum",
                },
                {
                    "doi": "10.example/protocol",
                    "datasets": "disorder",
                    "study_title": "Ketamine-Assisted Recovery: protocol for an open-label pilot trial",
                    "abstract": "This protocol describes ketamine-assisted psychotherapy for addiction.",
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.1371/journal.pmed.1004519.g001",
                    "datasets": "disorder",
                    "study_title": "Study flow chart.",
                    "abstract": "Psilocybin and MBSR were studied in health care workers.",
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.1021/acsptsci.5c00324.s001",
                    "datasets": "mechanistic",
                    "study_title": "The Medial Prefrontal Cortex Modulates Psychedelic-like Effects of Psilocin",
                    "abstract": "Psilocin effects were tested in medial prefrontal cortex.",
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.6084/m9.figshare.24531073",
                    "datasets": "mechanistic",
                    "study_title": "Spinogenesis Data - Prism file",
                    "abstract": "Psilocybin and ketamine spinogenesis data are provided.",
                    "publication_type": "Dataset",
                },
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-05-30T00:00:00+00:00",
        )
        by_doi = {row["doi"]: row for row in rows}

        self.assertEqual(by_doi["10.example/correction"]["prescreen_decision"], "exclude")
        self.assertEqual(by_doi["10.example/correction"]["prescreen_action"], "exclude_non_evidence_artifact")
        self.assertEqual(by_doi["10.example/protocol"]["prescreen_decision"], "exclude")
        self.assertEqual(by_doi["10.example/protocol"]["prescreen_action"], "exclude_non_evidence_artifact")
        self.assertEqual(by_doi["10.1371/journal.pmed.1004519.g001"]["prescreen_action"], "exclude_non_evidence_artifact")
        self.assertEqual(by_doi["10.1021/acsptsci.5c00324.s001"]["prescreen_action"], "exclude_non_evidence_artifact")
        self.assertEqual(by_doi["10.6084/m9.figshare.24531073"]["prescreen_action"], "exclude_non_evidence_artifact")
        self.assertFalse(by_doi["10.example/correction"]["retained_for_extraction_candidate"])
        self.assertFalse(by_doi["10.example/protocol"]["retained_for_extraction_candidate"])
        self.assertFalse(by_doi["10.1371/journal.pmed.1004519.g001"]["retained_for_extraction_candidate"])
        self.assertFalse(by_doi["10.1021/acsptsci.5c00324.s001"]["retained_for_extraction_candidate"])
        self.assertFalse(by_doi["10.6084/m9.figshare.24531073"]["retained_for_extraction_candidate"])

    def test_writes_parquet_decisions_and_summary_without_json_outputs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            papers_path = root / "candidate_papers.parquet"
            metadata_path = root / "paper_metadata_enrichment.parquet"
            contexts_path = root / "candidate_contexts.parquet"
            sources_path = root / "candidate_sources.parquet"
            decisions_path = root / "paper_prescreen_decisions.parquet"
            summary_path = root / "paper_prescreen_summary.parquet"
            pd.DataFrame(
                [
                    {
                        "doi": "10.example/psilo",
                        "datasets": "disorder",
                        "study_title": "Psilocybin therapy for depression",
                        "abstract": "Psilocybin therapy reduced depression symptoms.",
                    }
                ]
            ).to_parquet(papers_path, index=False)
            pd.DataFrame([]).to_parquet(metadata_path, index=False)
            pd.DataFrame([]).to_parquet(contexts_path, index=False)
            pd.DataFrame([]).to_parquet(sources_path, index=False)

            args = type(
                "Args",
                (),
                {
                    "papers_table": str(papers_path),
                    "metadata_table": str(metadata_path),
                    "contexts_table": str(contexts_path),
                    "sources_table": str(sources_path),
                    "decisions_table": str(decisions_path),
                    "summary_table": str(summary_path),
                    "run_id": "test_run",
                    "dataset": "all",
                    "doi_file": "",
                    "doi": [],
                    "retain_missing_abstract": False,
                    "progress_every": 0,
                },
            )()
            decisions, summary = run(args)

            self.assertEqual(len(decisions), 1)
            self.assertTrue(summary)
            self.assertTrue(decisions_path.exists())
            self.assertTrue(summary_path.exists())
            self.assertEqual(list(root.glob("*.json")), [])
            written = pd.read_parquet(decisions_path)
            self.assertEqual(written.loc[0, "prescreen_decision"], "retain")

    def test_scoped_update_replaces_only_requested_doi_rows_and_reuses_existing_run_id(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            papers_path = root / "candidate_papers.parquet"
            metadata_path = root / "paper_metadata_enrichment.parquet"
            contexts_path = root / "candidate_contexts.parquet"
            sources_path = root / "candidate_sources.parquet"
            decisions_path = root / "paper_prescreen_decisions.parquet"
            summary_path = root / "paper_prescreen_summary.parquet"
            doi_file = root / "update_dois.txt"

            pd.DataFrame(
                [
                    {
                        "doi": "10.example/psilo",
                        "datasets": "disorder",
                        "study_title": "Psilocybin therapy for depression",
                        "abstract": "",
                    },
                    {
                        "doi": "10.example/exercise",
                        "datasets": "disorder",
                        "study_title": "Exercise intervention for depression",
                        "abstract": "This randomized trial tested exercise for depression.",
                    },
                ]
            ).to_parquet(papers_path, index=False)
            pd.DataFrame(
                [
                    {
                        "doi": "10.example/psilo",
                        "study_title": "Psilocybin therapy for depression",
                        "abstract": "Psilocybin therapy reduced depression symptoms.",
                        "metadata_enrichment_status": "enriched",
                    }
                ]
            ).to_parquet(metadata_path, index=False)
            pd.DataFrame([]).to_parquet(contexts_path, index=False)
            pd.DataFrame([]).to_parquet(sources_path, index=False)
            pd.DataFrame(
                [
                    {
                        "table_version": "0.1",
                        "run_id": "existing_prescreen_run",
                        "generated_at_utc": "old",
                        "prescreen_decision_id": "old-psilo",
                        "doi": "10.example/psilo",
                        "dataset": "disorder",
                        "has_abstract": False,
                        "downstream_protected": False,
                        "prescreen_decision": "exclude",
                        "prescreen_action": "exclude_missing_abstract",
                        "deterministic_action": "exclude_missing_abstract",
                        "routing_tags": "",
                    },
                    {
                        "table_version": "0.1",
                        "run_id": "existing_prescreen_run",
                        "generated_at_utc": "old",
                        "prescreen_decision_id": "old-exercise",
                        "doi": "10.example/exercise",
                        "dataset": "disorder",
                        "has_abstract": True,
                        "downstream_protected": False,
                        "prescreen_decision": "retain",
                        "prescreen_action": "retain_for_extraction_candidate",
                        "deterministic_action": "escalate",
                        "routing_tags": "",
                    },
                ]
            ).to_parquet(decisions_path, index=False)
            doi_file.write_text("10.example/psilo\n", encoding="utf-8")

            args = type(
                "Args",
                (),
                {
                    "papers_table": str(papers_path),
                    "metadata_table": str(metadata_path),
                    "contexts_table": str(contexts_path),
                    "sources_table": str(sources_path),
                    "decisions_table": str(decisions_path),
                    "summary_table": str(summary_path),
                    "run_id": "",
                    "dataset": "all",
                    "doi_file": str(doi_file),
                    "doi": [],
                    "retain_missing_abstract": False,
                    "progress_every": 0,
                },
            )()
            decisions, summary = run(args)
            written = pd.read_parquet(decisions_path)
            by_doi = {row["doi"]: row for row in written.to_dict("records")}

        self.assertEqual(len(decisions), 2)
        self.assertTrue(summary)
        self.assertEqual(by_doi["10.example/psilo"]["run_id"], "existing_prescreen_run")
        self.assertEqual(by_doi["10.example/psilo"]["prescreen_action"], "retain_for_extraction_candidate")
        self.assertEqual(by_doi["10.example/exercise"]["prescreen_decision_id"], "old-exercise")
        self.assertEqual(by_doi["10.example/exercise"]["prescreen_action"], "retain_for_extraction_candidate")

    def test_scoped_update_adds_new_doi_rows(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            papers_path = root / "candidate_papers.parquet"
            metadata_path = root / "paper_metadata_enrichment.parquet"
            contexts_path = root / "candidate_contexts.parquet"
            sources_path = root / "candidate_sources.parquet"
            decisions_path = root / "paper_prescreen_decisions.parquet"
            summary_path = root / "paper_prescreen_summary.parquet"
            doi_file = root / "new_dois.txt"

            pd.DataFrame(
                [
                    {
                        "doi": "10.example/existing",
                        "datasets": "disorder",
                        "study_title": "Existing paper",
                        "abstract": "Psilocybin therapy reduced depression symptoms.",
                    },
                    {
                        "doi": "10.example/new",
                        "datasets": "disorder",
                        "study_title": "New psilocybin paper",
                        "abstract": "Psilocybin therapy was evaluated for depression symptoms.",
                    },
                ]
            ).to_parquet(papers_path, index=False)
            pd.DataFrame([]).to_parquet(metadata_path, index=False)
            pd.DataFrame([]).to_parquet(contexts_path, index=False)
            pd.DataFrame([]).to_parquet(sources_path, index=False)
            pd.DataFrame(
                [
                    {
                        "table_version": "0.1",
                        "run_id": "existing_prescreen_run",
                        "generated_at_utc": "old",
                        "prescreen_decision_id": "old-existing",
                        "doi": "10.example/existing",
                        "dataset": "disorder",
                        "has_abstract": True,
                        "downstream_protected": False,
                        "prescreen_decision": "retain",
                        "prescreen_action": "retain_for_extraction_candidate",
                        "deterministic_action": "escalate",
                        "routing_tags": "",
                    },
                ]
            ).to_parquet(decisions_path, index=False)
            doi_file.write_text("10.example/new\n", encoding="utf-8")

            args = type(
                "Args",
                (),
                {
                    "papers_table": str(papers_path),
                    "metadata_table": str(metadata_path),
                    "contexts_table": str(contexts_path),
                    "sources_table": str(sources_path),
                    "decisions_table": str(decisions_path),
                    "summary_table": str(summary_path),
                    "run_id": "",
                    "dataset": "all",
                    "doi_file": str(doi_file),
                    "doi": [],
                    "retain_missing_abstract": False,
                    "progress_every": 0,
                },
            )()
            decisions, summary = run(args)
            written = pd.read_parquet(decisions_path)
            by_doi = {row["doi"]: row for row in written.to_dict("records")}

        self.assertEqual(len(decisions), 2)
        self.assertTrue(summary)
        self.assertEqual(by_doi["10.example/existing"]["prescreen_decision_id"], "old-existing")
        self.assertEqual(by_doi["10.example/new"]["run_id"], "existing_prescreen_run")
        self.assertEqual(by_doi["10.example/new"]["prescreen_action"], "retain_for_extraction_candidate")

    def test_summary_counts_actions_and_routing_tags(self) -> None:
        decisions = [
            {
                "doi": "10.example/a",
                "dataset": "mechanistic",
                "has_abstract": True,
                "downstream_protected": False,
                "prescreen_decision": "retain",
                "prescreen_action": "retain_for_extraction_candidate",
                "deterministic_action": "escalate",
                "routing_tags": "brain_system|molecular_target",
            },
            {
                "doi": "10.example/b",
                "dataset": "mechanistic",
                "has_abstract": False,
                "downstream_protected": False,
                "prescreen_decision": "exclude",
                "prescreen_action": "exclude_missing_abstract",
                "deterministic_action": "exclude_missing_abstract",
                "routing_tags": "",
            },
        ]

        summary = build_summary_rows(decisions, run_id="test_run", generated_at_utc="now")
        keyed = {(row["dataset"], row["metric"], row["label"]): row["count"] for row in summary}

        self.assertEqual(keyed[("mechanistic", "prescreen_decision", "retain")], 1)
        self.assertEqual(keyed[("mechanistic", "prescreen_action", "exclude_missing_abstract")], 1)
        self.assertEqual(keyed[("mechanistic", "routing_tag", "brain_system")], 1)
        self.assertEqual(keyed[("all", "abstract", "missing")], 1)


if __name__ == "__main__":
    unittest.main()
