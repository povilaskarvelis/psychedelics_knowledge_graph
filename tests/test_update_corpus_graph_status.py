import unittest

import pandas as pd

from pipeline.kg.update_corpus_graph_status import build_updated_corpus


def candidate(doi: str, *, selected: bool = True, prescreened: bool = True) -> dict:
    return {
        "doi": doi,
        "prescreen_retained_for_extraction_candidate": prescreened,
        "retained_for_extraction_candidate": selected,
        "extraction_route_status": (
            "ready_for_article_text_extraction" if selected else "excluded_after_domain_screen"
        ),
    }


class UpdateCorpusGraphStatusTest(unittest.TestCase):
    def build(self, rows: list[dict], **kwargs) -> pd.DataFrame:
        return build_updated_corpus(
            pd.DataFrame(rows),
            represented_dois=kwargs.get("represented_dois", set()),
            audit_statuses=kwargs.get("audit_statuses", {}),
            extraction_outcomes=kwargs.get("extraction_outcomes", {}),
            doi_aliases=kwargs.get("doi_aliases", {}),
            disposition_overrides=kwargs.get("disposition_overrides", {}),
            run_id="run",
            release_id="run:release",
            updated_at_utc="2026-07-14T00:00:00+00:00",
        )

    def test_materializes_every_final_decision_in_the_corpus(self) -> None:
        out = self.build(
            [
                candidate("10.1000/included"),
                candidate("10.1000/unmapped"),
                candidate("10.1000/no-finding"),
                candidate("10.1000/excluded", selected=False),
            ],
            represented_dois={"10.1000/included"},
            audit_statuses={
                "10.1000/unmapped": {"entity_unmapped"},
                "10.1000/no-finding": {"paper_scope_not_graphable"},
            },
        )
        by_doi = out.set_index("doi")
        self.assertEqual(by_doi.loc["10.1000/included", "graph_inclusion_disposition"], "represented")
        self.assertEqual(
            by_doi.loc["10.1000/unmapped", "graph_inclusion_disposition"],
            "unsupported_finding_detail",
        )
        self.assertEqual(
            by_doi.loc["10.1000/no-finding", "graph_inclusion_disposition"],
            "no_extractable_finding",
        )
        self.assertEqual(by_doi.loc["10.1000/excluded", "graph_inclusion_disposition"], "not_reached")

    def test_rejects_selected_report_without_a_final_decision(self) -> None:
        with self.assertRaisesRegex(ValueError, "no completed extraction"):
            self.build([candidate("10.1000/missing")])

    def test_curated_extraction_failure_is_a_final_auditable_decision(self) -> None:
        out = self.build(
            [candidate("10.1000/model-failure")],
            disposition_overrides={
                "10.1000/model-failure": {
                    "disposition": "extraction_failed",
                    "reason": "Repeated model-output corruption.",
                    "next_action": "Retry with a different implementation.",
                }
            },
        )

        row = out.iloc[0]
        self.assertEqual(row["graph_inclusion_status"], "not_represented")
        self.assertEqual(row["graph_inclusion_disposition"], "extraction_failed")
        self.assertEqual(row["graph_inclusion_decision_source"], "curated_final_disposition")

    def test_completed_no_finding_outcome_is_auditable_terminal_decision(self) -> None:
        out = self.build(
            [candidate("10.1000/no-result")],
            extraction_outcomes={"10.1000/no-result": {"no_extractable_scoped_evidence"}},
        )
        row = out.iloc[0]
        self.assertEqual(row["graph_inclusion_disposition"], "no_extractable_finding")
        self.assertEqual(row["graph_inclusion_decision_source"], "completed_extraction_outcome")

    def test_candidate_alias_resolves_to_represented_canonical_paper(self) -> None:
        out = self.build(
            [candidate("10.1000/repository")],
            represented_dois={"10.1000/article"},
            doi_aliases={"10.1000/repository": "10.1000/article"},
        )
        self.assertEqual(out.iloc[0]["graph_inclusion_disposition"], "represented")

    def test_rejects_scope_exclusion_left_in_selected_set(self) -> None:
        with self.assertRaisesRegex(ValueError, "screening exclusion was left"):
            self.build(
                [candidate("10.1000/out")],
                disposition_overrides={
                    "10.1000/out": {
                        "disposition": "adjudicated_outside_scope",
                        "reason": "Outside scope.",
                        "next_action": "No extraction.",
                    }
                },
            )


if __name__ == "__main__":
    unittest.main()
