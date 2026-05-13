import unittest
from collections import Counter

from pipeline.kg.build_kg import (
    EntityIndex,
    evidence_role,
    normalize_doi,
    paper_id_for,
    pdf_status,
    prisma_flow_for_dataset,
    slug,
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
        self.assertEqual(flow["steps"]["reports_sought"]["count"], 2)
        self.assertEqual(flow["steps"]["reports_retrieved"]["count"], 1)
        self.assertEqual(flow["steps"]["included"]["count"], 1)
        self.assertEqual(flow["side_boxes"]["records_excluded"]["count"], 2)
        self.assertEqual(flow["side_boxes"]["reports_not_retrieved"]["reasons"][0]["key"], "not_open_access")


if __name__ == "__main__":
    unittest.main()
