import tempfile
import unittest
from collections import Counter
from pathlib import Path

import pandas as pd

from pipeline.kg.build_methods_flow import (
    MethodsFlowBuilder,
    candidate_bibliography_payload,
    graph_inclusion_disposition_payload,
    labeled_reason_counts,
    normalize_doi,
    paper_id_for,
    prisma_flow_for_candidate_papers,
    public_candidate_pipeline_counts,
    slug,
)


def graph_fields(disposition: str) -> dict:
    provenance = {
        "graph_inclusion_run_id": "test_run",
        "graph_inclusion_release_id": "test_run:release",
        "graph_inclusion_updated_at_utc": "2026-07-14T00:00:00+00:00",
    }
    if disposition == "represented":
        return {
            "graph_inclusion_status": "represented",
            "graph_inclusion_disposition": "represented",
            "graph_inclusion_reason": "Represented in graph.",
            "graph_inclusion_next_action": "No action needed.",
            "graph_inclusion_decision_source": "test",
            **provenance,
        }
    if disposition == "not_reached":
        return {
            "graph_inclusion_status": "not_reached",
            "graph_inclusion_disposition": "not_reached",
            "graph_inclusion_reason": "Not selected for extraction.",
            "graph_inclusion_next_action": "No graph action required.",
            "graph_inclusion_decision_source": "test",
            **provenance,
        }
    return {
        "graph_inclusion_status": "not_represented",
        "graph_inclusion_disposition": disposition,
        "graph_inclusion_reason": f"Final reason for {disposition}.",
        "graph_inclusion_next_action": "Retain the decision.",
        "graph_inclusion_decision_source": "test",
        **provenance,
    }


class MethodsFlowBuilderHelpersTest(unittest.TestCase):
    def test_graph_disposition_ledger_reconciles_selected_papers(self) -> None:
        rows = [
            {
                "doi": "10.1000/included",
                "study_title": "Included",
                "literature_source_family": "primary",
                "literature_source_type": "primary",
                "retained_for_extraction_candidate": True,
                **graph_fields("represented"),
            },
            {
                "doi": "10.1000/unmapped",
                "study_title": "Unmapped",
                "literature_source_family": "primary",
                "literature_source_type": "primary",
                "retained_for_extraction_candidate": True,
                **graph_fields("unsupported_finding_detail"),
            },
            {
                "doi": "10.1000/guideline",
                "study_title": "Guideline",
                "literature_source_family": "secondary_literature",
                "literature_source_type": "guideline",
                "retained_for_extraction_candidate": True,
                **graph_fields("no_extractable_finding"),
            },
        ]
        payload = graph_inclusion_disposition_payload(rows)

        self.assertEqual(payload["counts"]["selected_papers"], 3)
        self.assertEqual(payload["unit"], "selected reports")
        self.assertEqual(payload["counts"]["represented_papers"], 1)
        self.assertEqual(payload["counts"]["not_represented_papers"], 2)
        self.assertTrue(payload["counts"]["final_reasons_complete"])
        self.assertEqual(payload["counts"]["transitional_reason_papers"], 0)
        self.assertEqual(len(payload["rows"]), 2)
        by_doi = {row["doi"]: row for row in payload["rows"]}
        self.assertEqual(by_doi["10.1000/unmapped"]["disposition"], "unsupported_finding_detail")
        self.assertEqual(by_doi["10.1000/guideline"]["disposition"], "no_extractable_finding")

    def test_normalize_doi_removes_common_prefixes(self) -> None:
        self.assertEqual(normalize_doi("https://doi.org/10.1000/ABC"), "10.1000/abc")
        self.assertEqual(normalize_doi("doi:10.1000/Example"), "10.1000/example")

    def test_paper_id_prefers_doi(self) -> None:
        row = {"study_doi": "https://doi.org/10.1000/ABC", "openalex_id": "W1", "study_title": "Title"}
        self.assertEqual(paper_id_for(row), "paper:10.1000/abc")

    def test_methods_builder_has_no_legacy_input_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "missing_candidate_papers.parquet"
            builder = MethodsFlowBuilder(candidate_table=missing)
            with self.assertRaises(FileNotFoundError):
                builder.build()

    def test_labeled_reason_counts_keeps_all_nonzero_reasons(self) -> None:
        reasons = labeled_reason_counts(
            Counter({"known": 2, "new_reason": 3, "zero_reason": 0}),
            {"known": "Known reason"},
            ("known",),
        )

        self.assertEqual([reason["key"] for reason in reasons], ["known", "new_reason"])
        self.assertEqual(reasons[1]["label"], "New reason")

    def test_slug_strips_markup_and_normalizes(self) -> None:
        self.assertEqual(slug("<i>N</i>-Benzyl 5-HT<sub>2A</sub>"), "n_benzyl_5_ht2a")

    def test_candidate_prisma_flow_uses_single_evidence_extraction_selection(self) -> None:
        flow = prisma_flow_for_candidate_papers(
            [
                {
                    "doi": "10.1000/in-graph",
                    "prescreen_actions": "retain_for_extraction_candidate",
                    "prescreen_decisions": "retain",
                    "prescreen_retained_for_extraction_candidate": True,
                    "retained_for_extraction_candidate": True,
                    "extraction_route_status": "ready_for_article_text_extraction",
                    "retained_extraction_route_count": 3,
                    **graph_fields("represented"),
                },
                {
                    "doi": "10.1000/not-graphable",
                    "prescreen_actions": "retain_for_extraction_candidate",
                    "prescreen_decisions": "retain",
                    "prescreen_retained_for_extraction_candidate": True,
                    "retained_for_extraction_candidate": True,
                    "extraction_route_status": "ready_for_abstract_extraction",
                    "retained_extraction_route_count": 1,
                    **graph_fields("no_extractable_finding"),
                },
                {
                    "doi": "10.1000/screened-out",
                    "prescreen_actions": "retain_for_extraction_candidate",
                    "prescreen_decisions": "retain",
                    "prescreen_retained_for_extraction_candidate": True,
                    "retained_for_extraction_candidate": False,
                    "extraction_route_status": "excluded_after_domain_screen",
                    **graph_fields("not_reached"),
                },
                {
                    "doi": "10.1000/no-abstract",
                    "prescreen_actions": "exclude_missing_abstract",
                    "prescreen_decisions": "exclude",
                    "prescreen_retained_for_extraction_candidate": False,
                    "retained_for_extraction_candidate": False,
                    "extraction_route_status": "not_retained_for_extraction",
                    **graph_fields("not_reached"),
                },
            ]
        )

        self.assertEqual(flow["dataset"], "overall")
        self.assertEqual(flow["label"], "Search and graph-inclusion flow")
        self.assertEqual(flow["unit"], "records and reports")
        self.assertEqual(flow["current_stage"], "kg_inclusion_summary")
        self.assertEqual(flow["steps"]["records_identified"]["label"], "Records found by the search")
        self.assertEqual(flow["steps"]["records_screened"]["label"], "Records screened for relevance")
        self.assertEqual(flow["steps"]["prescreen_retained"]["label"], "Records kept after initial screening")
        self.assertEqual(
            flow["steps"]["evidence_extraction_selected"]["label"],
            "Reports selected for evidence extraction",
        )
        self.assertEqual(
            flow["steps"]["kg_included"]["label"],
            "Reports represented in the knowledge graph",
        )
        self.assertEqual(flow["steps"]["records_identified"]["count"], 4)
        self.assertEqual(flow["steps"]["prescreen_retained"]["count"], 3)
        self.assertEqual(flow["steps"]["evidence_extraction_selected"]["count"], 2)
        self.assertEqual(flow["steps"]["kg_included"]["count"], 1)
        self.assertEqual(flow["side_boxes"]["records_excluded"]["reasons"][0]["key"], "exclude_missing_abstract")
        self.assertEqual(flow["side_boxes"]["route_not_selected"]["count"], 1)
        self.assertEqual(
            flow["side_boxes"]["route_not_selected"]["label"],
            "Records not selected for evidence extraction",
        )
        self.assertEqual(
            flow["side_boxes"]["route_not_selected"]["reasons"][0]["key"],
            "excluded_during_llm_screening",
        )
        self.assertEqual(
            flow["side_boxes"]["route_not_selected"]["reasons"][0]["label"],
            "Excluded during title and abstract screening",
        )
        self.assertEqual(flow["side_boxes"]["kg_not_included"]["count"], 1)
        self.assertEqual(
            flow["side_boxes"]["kg_not_included"]["label"],
            "Selected reports not represented in graph",
        )
        self.assertEqual(
            flow["side_boxes"]["kg_not_included"]["reasons"][0]["key"],
            "no_extractable_finding",
        )
        self.assertEqual(flow["rows"][-2]["side_box"], "kg_not_included")
        self.assertEqual(flow["rows"][-1]["step"], "kg_included")
        self.assertEqual(
            public_candidate_pipeline_counts(flow)["represented_in_knowledge_graph"],
            1,
        )
        self.assertEqual(
            public_candidate_pipeline_counts(flow)["not_represented_in_knowledge_graph"],
            1,
        )
        self.assertNotIn("extraction_input_split", flow["side_boxes"])

    def test_candidate_bibliography_payload_explains_sequential_decisions(self) -> None:
        payload = candidate_bibliography_payload(
            [
                {
                    "doi": "10.1000/selected",
                    "study_title": "Selected Paper",
                    "authors": "Ada Lovelace; Grace Hopper",
                    "study_year": 2024,
                    "study_journal": "Example Journal",
                    "datasets": "mechanistic",
                    "literature_source_family": "primary",
                    "publication_stage": "published",
                    "prescreen_actions": "retain_for_extraction_candidate",
                    "prescreen_decisions": "retain",
                    "prescreen_reasons": "in-scope compound/intervention term appears in title or abstract",
                    "prescreen_retained_for_extraction_candidate": True,
                    "retained_for_extraction_candidate": True,
                    "extraction_route_status": "ready_for_article_text_extraction",
                    "extraction_route_reason": "route_action=extract_from_full_text; access_tier=full_text_available",
                    "best_extraction_access_tier": "full_text_available",
                    "retained_extraction_route_count": 2,
                    "extraction_schema_profiles": "primary_evidence_schema",
                    **graph_fields("no_extractable_finding"),
                },
                {
                    "doi": "10.1000/excluded",
                    "study_title": "Excluded Paper",
                    "authors": "Barbara McClintock",
                    "study_year": 2023,
                    "prescreen_actions": "exclude_missing_abstract",
                    "prescreen_decisions": "exclude",
                    "prescreen_reasons": "No abstract available for screening.",
                    "prescreen_retained_for_extraction_candidate": False,
                    "retained_for_extraction_candidate": False,
                    "extraction_route_status": "not_retained_for_extraction",
                    **graph_fields("not_reached"),
                },
            ]
        )

        interned = set(payload["interned_columns"])
        string_table = payload["string_table"]
        rows = []
        for raw_row in payload["rows"]:
            row = {}
            for column, value in zip(payload["columns"], raw_row):
                row[column] = string_table[value] if column in interned else value
            rows.append(row)
        by_doi = {row["doi"]: row for row in rows}

        forbidden_public_columns = {
            "datasets",
            "dataset",
            "source_table",
            "search_source",
            "literature_source_family",
            "publication_stage",
        }
        self.assertTrue(forbidden_public_columns.isdisjoint(payload["columns"]))
        self.assertEqual(payload["unit"], "records")
        self.assertIn("papers", payload["counts"])
        self.assertEqual(payload["counts"]["by_kg_status"]["No specific finding to represent"], 1)
        self.assertEqual(payload["counts"]["by_kg_status"]["Not reached"], 1)
        self.assertNotIn("candidate_papers", payload["counts"])
        self.assertNotIn("mechanistic", payload["string_table"])
        self.assertNotIn("disorder", payload["string_table"])

        selected = by_doi["10.1000/selected"]
        self.assertEqual(selected["initial_screening_status"], "pass")
        self.assertEqual(selected["initial_screening_label"], "Passed")
        self.assertEqual(selected["llm_screening_status"], "pass")
        self.assertEqual(selected["llm_screening_label"], "Passed")
        self.assertEqual(selected["extraction_status"], "pass")
        self.assertEqual(selected["extraction_label"], "Selected")
        self.assertEqual(selected["kg_status"], "fail")
        self.assertEqual(selected["kg_label"], "No specific finding to represent")
        self.assertIn("no_extractable_finding", selected["kg_note"])
        self.assertEqual(selected["stage_key"], "selected_for_extraction")
        self.assertTrue(selected["selected_for_extraction"])

        excluded = by_doi["10.1000/excluded"]
        self.assertEqual(excluded["initial_screening_status"], "fail")
        self.assertEqual(excluded["initial_screening_label"], "Did not pass")
        self.assertEqual(excluded["initial_screening_note"], "No abstract")
        self.assertEqual(excluded["llm_screening_status"], "not_reached")
        self.assertEqual(excluded["extraction_status"], "not_reached")
        self.assertEqual(excluded["kg_status"], "not_reached")
        self.assertEqual(excluded["kg_label"], "Not reached")
        self.assertEqual(excluded["stage_key"], "excluded_during_initial_screening")
        self.assertFalse(excluded["selected_for_extraction"])

    def test_candidate_prisma_and_bibliography_share_kg_status_counts(self) -> None:
        rows = [
            {
                "doi": "10.1000/in-graph",
                "study_title": "In Graph",
                "prescreen_actions": "retain_for_extraction_candidate",
                "prescreen_decisions": "retain",
                "prescreen_retained_for_extraction_candidate": True,
                "retained_for_extraction_candidate": True,
                "extraction_route_status": "ready_for_article_text_extraction",
                **graph_fields("represented"),
            },
            {
                "doi": "10.1000/not-graphable",
                "study_title": "Not Graphable",
                "prescreen_actions": "retain_for_extraction_candidate",
                "prescreen_decisions": "retain",
                "prescreen_retained_for_extraction_candidate": True,
                "retained_for_extraction_candidate": True,
                "extraction_route_status": "ready_for_article_text_extraction",
                **graph_fields("no_extractable_finding"),
            },
            {
                "doi": "10.1000/not-normalized",
                "study_title": "Not Normalized",
                "prescreen_actions": "retain_for_extraction_candidate",
                "prescreen_decisions": "retain",
                "prescreen_retained_for_extraction_candidate": True,
                "retained_for_extraction_candidate": True,
                "extraction_route_status": "ready_for_article_text_extraction",
                **graph_fields("unsupported_finding_detail"),
            },
            {
                "doi": "10.1000/no-finding",
                "study_title": "No Finding",
                "prescreen_actions": "retain_for_extraction_candidate",
                "prescreen_decisions": "retain",
                "prescreen_retained_for_extraction_candidate": True,
                "retained_for_extraction_candidate": True,
                "extraction_route_status": "ready_for_article_text_extraction",
                **graph_fields("insufficient_source_text"),
            },
        ]

        flow = prisma_flow_for_candidate_papers(rows)
        bibliography = candidate_bibliography_payload(rows)

        self.assertEqual(flow["steps"]["kg_included"]["count"], bibliography["counts"]["by_kg_status"]["In graph"])
        flow_not_in_graph = {
            reason["label"]: reason["count"]
            for reason in flow["side_boxes"]["kg_not_included"]["reasons"]
        }
        for label in (
            "No specific finding to represent",
            "Finding too broad or ambiguous",
            "Available text is too limited",
        ):
            self.assertEqual(flow_not_in_graph[label], bibliography["counts"]["by_kg_status"][label])

    def test_methods_builder_reads_only_the_canonical_candidate_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            table = root / "candidate_papers.parquet"
            row = {
                "doi": "10.1000/in-graph",
                "prescreen_actions": "retain_for_extraction_candidate",
                "prescreen_retained_for_extraction_candidate": True,
                "retained_for_extraction_candidate": True,
                "extraction_route_status": "ready_for_article_text_extraction",
                **graph_fields("represented"),
            }
            pd.DataFrame([row]).to_parquet(table, index=False)

            builder = MethodsFlowBuilder(root, candidate_table=table)
            payloads = builder.build()

        self.assertEqual(payloads["pipeline_status"]["counts"]["papers_found_by_search"], 1)
        self.assertEqual(payloads["manifest"]["counts"], {"papers_found_by_search": 1})
        self.assertEqual([Path(path).resolve() for path in builder.input_files], [table.resolve()])

    def test_methods_builder_rejects_missing_final_graph_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            table = Path(tmpdir) / "candidate_papers.parquet"
            pd.DataFrame(
                [
                    {
                        "doi": "10.1000/missing",
                        "prescreen_retained_for_extraction_candidate": True,
                        "retained_for_extraction_candidate": True,
                        "extraction_route_status": "ready_for_article_text_extraction",
                    }
                ]
            ).to_parquet(table, index=False)
            builder = MethodsFlowBuilder(candidate_table=table)
            with self.assertRaisesRegex(ValueError, "missing required decision columns"):
                builder.build()

if __name__ == "__main__":
    unittest.main()
