import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import pandas as pd

from pipeline.kg.build_methods_flow import (
    MethodsFlowBuilder,
    labeled_reason_counts,
    normalize_doi,
    paper_id_for,
    pipeline_row_with_paper_artifacts,
    pdf_status,
    prisma_flow_for_candidate_papers,
    prisma_flow_for_dataset,
    prisma_retrieval_reason,
    slug,
    strongest_pdf_status,
)


class MethodsFlowBuilderHelpersTest(unittest.TestCase):
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
        builder = MethodsFlowBuilder()
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
        builder = MethodsFlowBuilder()
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

    def test_slug_strips_markup_and_normalizes(self) -> None:
        self.assertEqual(slug("<i>N</i>-Benzyl 5-HT<sub>2A</sub>"), "n_benzyl_5_ht2a")

    def test_prisma_flow_is_sequential_and_reasoned(self) -> None:
        flow = prisma_flow_for_dataset(
            "disorder",
            [
                {
                    "relevance_suggested": "likely_relevant",
                    "pdf_status": "downloaded",
                    "fulltext_status": "converted",
                    "llm_extraction_status": "claim_available",
                    "kg_claim_access_levels": {"full_text_seen": 1},
                },
                {
                    "relevance_suggested": "likely_relevant",
                    "pdf_status": "downloaded",
                    "fulltext_status": "converted",
                    "llm_extraction_status": "not_started",
                    "extraction_records": [{"access_level": "full_text_seen", "route": "exclude"}],
                },
                {
                    "relevance_suggested": "likely_relevant",
                    "pdf_status": "not_open_access",
                    "fulltext_status": "not_converted",
                    "llm_extraction_status": "not_started",
                },
                {
                    "relevance_suggested": "likely_relevant",
                    "pdf_status": "not_open_access",
                    "fulltext_status": "not_converted",
                    "llm_extraction_status": "claim_available",
                    "kg_claim_access_levels": {"abstract_only": 1},
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

        self.assertEqual(flow["steps"]["records_identified"]["count"], 6)
        self.assertEqual(flow["steps"]["reports_sought"]["count"], 5)
        self.assertEqual(flow["steps"]["reports_retrieved"]["count"], 2)
        self.assertEqual(flow["steps"]["included"]["count"], 2)
        self.assertEqual(flow["steps"]["fulltext_gemini_assessed"]["count"], 2)
        self.assertEqual(flow["steps"]["fulltext_included"]["count"], 1)
        self.assertEqual(flow["side_boxes"]["records_excluded"]["count"], 1)
        self.assertEqual(flow["side_boxes"]["reports_not_retrieved"]["reasons"][0]["key"], "not_open_access")
        non_fulltext_flow = flow["side_boxes"]["reports_not_retrieved"]["non_fulltext_flow"]
        self.assertEqual(non_fulltext_flow["candidates"]["count"], 3)
        self.assertEqual(non_fulltext_flow["not_extracted"]["count"], 2)
        self.assertEqual(non_fulltext_flow["assessed"]["count"], 1)
        self.assertEqual(non_fulltext_flow["included_abstract_only"]["count"], 1)
        fulltext_excluded_reasons = {
            reason["key"]: reason["count"]
            for reason in flow["side_boxes"]["fulltext_excluded_after_extraction"]["reasons"]
        }
        self.assertEqual(fulltext_excluded_reasons["gemini_excluded"], 1)

    def test_candidate_prisma_flow_uses_single_extraction_selection(self) -> None:
        flow = prisma_flow_for_candidate_papers(
            [
                {
                    "prescreen_actions": "retain_for_extraction_candidate",
                    "prescreen_decisions": "retain",
                    "prescreen_retained_for_extraction_candidate": True,
                    "retained_for_extraction_candidate": True,
                    "extraction_route_status": "ready_for_article_text_extraction",
                    "retained_extraction_route_count": 3,
                },
                {
                    "prescreen_actions": "retain_for_extraction_candidate",
                    "prescreen_decisions": "retain",
                    "prescreen_retained_for_extraction_candidate": True,
                    "retained_for_extraction_candidate": True,
                    "extraction_route_status": "ready_for_abstract_extraction",
                    "retained_extraction_route_count": 1,
                },
                {
                    "prescreen_actions": "retain_for_extraction_candidate",
                    "prescreen_decisions": "retain",
                    "prescreen_retained_for_extraction_candidate": True,
                    "retained_for_extraction_candidate": False,
                    "extraction_route_status": "excluded_after_domain_screen",
                },
                {
                    "prescreen_actions": "exclude_missing_abstract",
                    "prescreen_decisions": "exclude",
                    "prescreen_retained_for_extraction_candidate": False,
                    "retained_for_extraction_candidate": False,
                    "extraction_route_status": "not_retained_for_extraction",
                },
            ],
        )

        self.assertEqual(flow["dataset"], "overall")
        self.assertEqual(flow["steps"]["records_identified"]["count"], 4)
        self.assertEqual(flow["steps"]["prescreen_retained"]["count"], 3)
        self.assertEqual(flow["steps"]["extraction_selected"]["count"], 2)
        self.assertEqual(flow["side_boxes"]["records_excluded"]["reasons"][0]["key"], "exclude_missing_abstract")
        self.assertEqual(flow["side_boxes"]["route_not_selected"]["count"], 1)
        self.assertEqual(flow["metrics"]["selected_extraction_route_assignments"], 4)
        input_reasons = {
            reason["key"]: reason["count"]
            for reason in flow["side_boxes"]["extraction_input_split"]["reasons"]
        }
        self.assertEqual(input_reasons["ready_for_article_text_extraction"], 1)
        self.assertEqual(input_reasons["ready_for_abstract_extraction"], 1)

    def test_kg_claim_table_marks_pipeline_rows_as_claim_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            claims_table = Path(tmpdir) / "claims.parquet"
            pd.DataFrame(
                [
                    {
                        "dataset": "mechanistic",
                        "paper_id": "paper:10.123/example",
                        "study_doi": "10.123/example",
                        "access_level": "full_text_seen",
                    },
                    {
                        "dataset": "mechanistic",
                        "paper_id": "paper:10.123/example",
                        "study_doi": "10.123/example",
                        "access_level": "secondary_summary",
                    },
                    {
                        "dataset": "disorder",
                        "paper_id": "paper:10.999/other",
                        "study_doi": "10.999/other",
                        "access_level": "abstract_only",
                    },
                ]
            ).to_parquet(claims_table, index=False)

            builder = MethodsFlowBuilder()
            paper_id = "paper:10.123/example"
            builder.nodes[paper_id] = {
                "id": paper_id,
                "type": "Paper",
                "label": "Example",
                "properties": {},
            }
            builder.pipeline_rows["mechanistic"][paper_id] = {
                "paper_id": paper_id,
                "dataset": "mechanistic",
                "study_doi": "10.123/example",
                "llm_extraction_status": "not_started",
            }

            builder.load_kg_claim_status(claims_table, Path(tmpdir) / "missing_manifest.json")

            props = builder.pipeline_rows["mechanistic"][paper_id]
            self.assertEqual(props["llm_extraction_status"], "claim_available")
            self.assertEqual(props["kg_claim_count"], 2)
            self.assertEqual(props["kg_claim_access_levels"], {"full_text_seen": 1, "secondary_summary": 1})
            self.assertEqual(builder.kg_claim_rows_by_dataset["mechanistic"], 2)
            self.assertEqual(builder.kg_claim_access_rows_by_dataset["mechanistic"]["secondary_summary"], 1)
            self.assertEqual(builder.kg_claim_papers_by_dataset["mechanistic"], 1)
            self.assertEqual(builder.kg_claim_matched_pipeline_rows_by_dataset["mechanistic"], 1)
            self.assertEqual(builder.nodes[paper_id]["properties"]["kg_claim_count"], 2)

    def test_extraction_outputs_mark_gemini_assessed_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            results_path = tmp_path / "results.jsonl"
            report_path = tmp_path / "projection_report.json"
            results_path.write_text(
                json.dumps(
                    {
                        "dataset": "mechanistic",
                        "study_doi": "10.123/example",
                        "access_level": "full_text_seen",
                        "paper_assessment": {
                            "route": "exclude",
                            "relevance": "not_relevant",
                            "has_extractable_claims": False,
                            "exclusion_reason": "Not an in-scope mechanistic target claim.",
                        },
                        "claims": [],
                        "coverage_mentions": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            report_path.write_text(
                json.dumps({"inputs": {"input_jsonl": str(results_path)}}),
                encoding="utf-8",
            )

            builder = MethodsFlowBuilder()
            paper_id = "paper:10.123/example"
            builder.pipeline_rows["mechanistic"][paper_id] = {
                "paper_id": paper_id,
                "dataset": "mechanistic",
                "study_doi": "10.123/example",
            }

            builder.load_extraction_outcomes(report_path)

            records = builder.pipeline_rows["mechanistic"][paper_id]["extraction_records"]
            self.assertEqual(records[0]["route"], "exclude")
            self.assertEqual(records[0]["access_level"], "full_text_seen")
            self.assertEqual(builder.extraction_output_routes_by_dataset["mechanistic"]["exclude"], 1)
            self.assertEqual(builder.extraction_matched_pipeline_rows_by_dataset["mechanistic"], 1)


if __name__ == "__main__":
    unittest.main()
