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
        with self.assertRaisesRegex(ValueError, "neither an explicit final disposition"):
            self.build([candidate("10.1000/missing")])

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
