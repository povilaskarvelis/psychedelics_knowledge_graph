import unittest
from collections import Counter
from pathlib import Path

from pipeline.kg.build_kg import (
    EntityIndex,
    KgBuilder,
    evidence_role,
    labeled_reason_counts,
    normalize_doi,
    paper_id_for,
    pipeline_row_with_paper_artifacts,
    pdf_status,
    prisma_flow_for_dataset,
    prisma_retrieval_reason,
    slug,
    strongest_pdf_status,
    top_counts,
    year_range,
)


class KgBuilderHelpersTest(unittest.TestCase):
    def test_normalize_doi_removes_common_prefixes(self) -> None:
        self.assertEqual(normalize_doi("https://doi.org/10.1000/ABC"), "10.1000/abc")
        self.assertEqual(normalize_doi("doi:10.1000/Example"), "10.1000/example")

    def test_paper_id_prefers_doi(self) -> None:
        row = {"study_doi": "https://doi.org/10.1000/ABC", "openalex_id": "W1", "study_title": "Title"}
        self.assertEqual(paper_id_for(row), "paper:10.1000/abc")

    def test_pdf_status_does_not_treat_stale_paths_as_downloaded(self) -> None:
        row = {"pdf_local_path": "/definitely/not/a/real/local.pdf", "pdf_download_status": ""}
        self.assertEqual(pdf_status(row), "missing_local_pdf")

    def test_pdf_status_does_not_infer_final_status_from_attempt_log(self) -> None:
        row = {"pdf_download_status": "", "action_reason": "https://example.test/file -> invalid_pdf_content: response_not_pdf"}
        self.assertEqual(pdf_status(row), "not_downloaded")

    def test_prisma_retrieval_reason_groups_pdf_validation_failures(self) -> None:
        self.assertEqual(prisma_retrieval_reason({"pdf_status": "invalid_pdf_existing"}), "pdf_validation_failed")
        self.assertEqual(prisma_retrieval_reason({"pdf_status": "invalid_pdf_content"}), "pdf_validation_failed")

    def test_pipeline_row_reuses_paper_level_retrieval_artifacts(self) -> None:
        props = pipeline_row_with_paper_artifacts(
            {"pdf_status": "skipped", "fulltext_status": "not_converted", "relevance_suggested": "likely_relevant"},
            {"pdf_status": "downloaded", "fulltext_status": "converted", "llm_extraction_status": "claim_available"},
        )
        self.assertEqual(props["pdf_status"], "downloaded")
        self.assertEqual(props["fulltext_status"], "converted")
        self.assertNotEqual(props.get("llm_extraction_status"), "claim_available")

    def test_pipeline_row_does_not_reuse_paper_level_failure_labels(self) -> None:
        props = pipeline_row_with_paper_artifacts(
            {"pdf_status": "download_failed", "fulltext_status": "not_converted"},
            {"pdf_status": "invalid_pdf_existing", "fulltext_status": "not_converted"},
        )

        self.assertEqual(props["pdf_status"], "download_failed")

    def test_pipeline_row_reuses_paper_level_failure_for_unattempted_rows(self) -> None:
        props = pipeline_row_with_paper_artifacts(
            {"pdf_status": "skipped", "fulltext_status": "not_converted"},
            {"pdf_status": "download_failed", "fulltext_status": "not_converted"},
        )

        self.assertEqual(props["pdf_status"], "download_failed")

    def test_pipeline_reconciliation_prefers_library_retrieval_and_triage_screening(self) -> None:
        builder = KgBuilder()
        paper_id = "paper:10.123/example"
        builder.merge_pipeline_row(
            {
                "study_doi": "10.123/example",
                "pdf_download_status": "not_open_access",
                "pdf_local_path": "/stale/path.pdf",
                "relevance_suggested": "possible_relevant",
            },
            "mechanistic",
            paper_id,
            Path("paper_library_mechanistic.json"),
        )
        builder.merge_pipeline_row(
            {
                "study_doi": "10.123/example",
                "pdf_local_path": "/other/stale/path.pdf",
                "relevance_suggested": "likely_relevant",
                "screening_status": "included_context_match",
            },
            "mechanistic",
            paper_id,
            Path("triage_report_mechanistic.json"),
        )

        props = builder.pipeline_rows["mechanistic"][paper_id]
        self.assertEqual(props["pdf_status"], "not_open_access")
        self.assertEqual(props["relevance_suggested"], "likely_relevant")
        self.assertEqual(props["screening_status"], "included_context_match")

    def test_pipeline_status_uses_dataset_row_abstract_for_unscreened_records(self) -> None:
        builder = KgBuilder()
        paper_id = "paper:10.123/example"
        builder.nodes[paper_id] = {
            "id": paper_id,
            "type": "Paper",
            "label": "Cross-dataset paper",
            "properties": {
                "study_doi": "10.123/example",
                "abstract_present": True,
                "pdf_status": "skipped",
                "fulltext_status": "not_converted",
            },
        }
        builder.pipeline_rows["disorder"][paper_id] = {
            "paper_id": paper_id,
            "dataset": "disorder",
            "abstract_present": False,
            "pdf_status": "skipped",
            "fulltext_status": "not_converted",
            "llm_extraction_status": "not_started",
        }

        flow = builder.pipeline_status_view()["prisma_flow"]["disorder"]

        self.assertEqual(flow["side_boxes"]["removed_before_screening"]["reasons"][0]["key"], "not_screened_no_abstract")

    def test_labeled_reason_counts_keeps_all_nonzero_reasons(self) -> None:
        reasons = labeled_reason_counts(
            Counter({"known": 2, "new_reason": 3, "zero_reason": 0}),
            {"known": "Known reason"},
            ("known",),
        )

        self.assertEqual([reason["key"] for reason in reasons], ["known", "new_reason"])
        self.assertEqual(reasons[1]["label"], "New reason")

    def test_download_failure_outranks_stale_local_pdf_path(self) -> None:
        self.assertEqual(strongest_pdf_status("download_failed", "missing_local_pdf"), "download_failed")

    def test_explicit_access_status_outranks_stale_local_pdf_path(self) -> None:
        self.assertEqual(strongest_pdf_status("not_open_access", "missing_local_pdf"), "not_open_access")
        self.assertEqual(strongest_pdf_status("missing_local_pdf", "not_open_access"), "not_open_access")

    def test_entity_index_resolves_alias_to_canonical_node(self) -> None:
        index = EntityIndex()
        index.add_registry_entity(
            "Compound",
            {"label": "Psilocybin", "aliases": ["4-phosphoryloxy-DMT"], "ids": {}, "status": "ok"},
        )

        node_id, label = index.resolve("Compound", "4-phosphoryloxy dmt")

        self.assertEqual(node_id, "compound:psilocybin")
        self.assertEqual(label, "Psilocybin")

    def test_evidence_role_splits_primary_secondary_and_context(self) -> None:
        self.assertEqual(
            evidence_role({"source_type": "primary_study", "paper_type": "primary_results", "access_level": "full_text_seen"}),
            "primary_evidence",
        )
        self.assertEqual(evidence_role({"paper_type": "systematic_review"}), "secondary_literature")
        self.assertEqual(evidence_role({"source_type": "commentary", "paper_type": "commentary"}), "non_primary_context")

    def test_slug_strips_markup_and_normalizes(self) -> None:
        self.assertEqual(slug("<i>N</i>-Benzyl 5-HT<sub>2A</sub>"), "n_benzyl_5_ht2a")

    def test_content_summary_helpers_are_ui_shaped(self) -> None:
        self.assertEqual(top_counts(Counter({"primary_results": 3, "review": 1})), [{"value": "primary_results", "count": 3}, {"value": "review", "count": 1}])
        self.assertEqual(year_range([2020, 2024, 2021]), {"min": 2020, "max": 2024, "count": 3})

    def test_prisma_flow_is_sequential_and_reasoned(self) -> None:
        flow = prisma_flow_for_dataset(
            "disorder",
            [
                {
                    "relevance_suggested": "likely_relevant",
                    "pdf_status": "downloaded",
                    "fulltext_status": "converted",
                    "llm_extraction_status": "claim_available",
                },
                {
                    "relevance_suggested": "likely_relevant",
                    "pdf_status": "not_open_access",
                    "fulltext_status": "not_converted",
                    "llm_extraction_status": "not_started",
                },
                {
                    "relevance_suggested": "possible_relevant",
                    "screening_status": "needs_context_review",
                    "pdf_status": "skipped",
                    "fulltext_status": "not_converted",
                    "llm_extraction_status": "not_started",
                },
                {
                    "relevance_suggested": "likely_irrelevant",
                    "screening_status": "excluded_low_signal",
                    "pdf_status": "skipped",
                    "fulltext_status": "not_converted",
                    "llm_extraction_status": "not_started",
                },
            ],
        )

        self.assertEqual(flow["steps"]["records_identified"]["count"], 4)
        self.assertEqual(flow["steps"]["reports_sought"]["count"], 3)
        self.assertEqual(flow["steps"]["reports_retrieved"]["count"], 1)
        self.assertEqual(flow["steps"]["included"]["count"], 1)
        self.assertEqual(flow["side_boxes"]["records_excluded"]["count"], 1)
        self.assertEqual(flow["side_boxes"]["reports_not_retrieved"]["reasons"][0]["key"], "not_open_access")


if __name__ == "__main__":
    unittest.main()
