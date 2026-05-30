import unittest

import pandas as pd

from pipeline.ingest.refresh_paper_titles import (
    apply_title_updates,
    candidate_rows,
    comparable_title,
    lookup_crossref_title,
    preferred_title,
)


class FakeClient:
    def __init__(self, payload):
        self.payload = payload

    def get_json(self, url, params=None, headers=None):
        return self.payload


class RefreshPaperTitlesTests(unittest.TestCase):
    def test_preferred_title_adds_crossref_subtitle(self) -> None:
        title, reason = preferred_title(
            "Being for no-one",
            "Being for no-one: Psychedelic experience and minimal subjectivity",
            crossref_has_subtitle=True,
        )

        self.assertEqual(title, "Being for no-one: Psychedelic experience and minimal subjectivity")
        self.assertEqual(reason, "added_crossref_subtitle")

    def test_preferred_title_cleans_markup_without_crossref_change(self) -> None:
        title, reason = preferred_title(
            "Main title&lt;subtitle&gt;A Randomized Trial&lt;/subtitle&gt;",
            "",
            crossref_has_subtitle=False,
        )

        self.assertEqual(title, "Main title: A Randomized Trial")
        self.assertEqual(reason, "cleaned_current_title")

    def test_preferred_title_does_not_replace_different_title_without_subtitle(self) -> None:
        title, reason = preferred_title(
            "Known PubMed title",
            "Different Crossref title",
            crossref_has_subtitle=False,
        )

        self.assertEqual(title, "Known PubMed title")
        self.assertEqual(reason, "")

    def test_preferred_title_removes_dangling_colon_when_crossref_has_no_subtitle(self) -> None:
        title, reason = preferred_title(
            "Bioavailability of Ketamine After Oral or Sublingual Administration:",
            "Bioavailability of Ketamine After Oral or Sublingual Administration",
            crossref_has_subtitle=False,
        )

        self.assertEqual(title, "Bioavailability of Ketamine After Oral or Sublingual Administration")
        self.assertEqual(reason, "removed_dangling_title_colon")

    def test_lookup_crossref_title_treats_empty_subtitle_list_as_absent(self) -> None:
        title, has_subtitle = lookup_crossref_title(
            FakeClient(
                {
                    "message": {
                        "DOI": "10.example/title",
                        "title": ["Bioavailability of Ketamine:"],
                        "subtitle": [],
                    }
                }
            ),
            "10.example/title",
            email="",
        )

        self.assertEqual(title, "Bioavailability of Ketamine")
        self.assertFalse(has_subtitle)

    def test_candidate_rows_risk_scope_keeps_non_pubmed_and_crossref_chain(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "doi": "10.example/pubmed",
                    "study_title": "PubMed title",
                    "metadata_provider": "pubmed",
                    "metadata_provider_chain": "pubmed",
                },
                {
                    "doi": "10.example/crossref",
                    "study_title": "Crossref title",
                    "metadata_provider": "crossref",
                    "metadata_provider_chain": "crossref",
                },
                {
                    "doi": "10.example/pubmed-chain",
                    "study_title": "PubMed title from chain",
                    "metadata_provider": "pubmed",
                    "metadata_provider_chain": "pubmed|crossref",
                },
                {
                    "doi": "10.example/markup",
                    "study_title": "Title with &lt;i&gt;markup&lt;/i&gt;",
                    "metadata_provider": "pubmed",
                    "metadata_provider_chain": "pubmed",
                },
            ]
        )

        selected = candidate_rows(
            df,
            doi_file="",
            prescreen_table="/tmp/does-not-exist.parquet",
            only_retained=False,
            provider_scope="risk",
            limit=0,
        )

        self.assertEqual(
            set(selected["doi"]),
            {"10.example/crossref", "10.example/pubmed-chain", "10.example/markup"},
        )

    def test_apply_title_updates_updates_matching_dois(self) -> None:
        df = pd.DataFrame(
            [
                {"doi": "10.example/a", "study_title": "Old A"},
                {"doi": "10.example/b", "study_title": "Old B"},
            ]
        )

        updated, count = apply_title_updates(df, {"10.example/a": "New A"})

        self.assertEqual(count, 1)
        self.assertEqual(updated.loc[0, "study_title"], "New A")
        self.assertEqual(updated.loc[1, "study_title"], "Old B")

    def test_comparable_title_ignores_markup_and_case(self) -> None:
        self.assertEqual(comparable_title("<i>DSM-5</i> Drug Use"), "dsm 5 drug use")


if __name__ == "__main__":
    unittest.main()
