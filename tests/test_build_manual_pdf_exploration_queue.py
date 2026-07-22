import unittest

import pandas as pd

from pipeline.fulltext.build_manual_pdf_exploration_queue import (
    build_host_summary,
    build_queue,
    pick_primary_route,
    priority_lane,
)


def test_empty_queue_produces_an_empty_host_summary_with_stable_schema() -> None:
    queue = build_queue(
        pd.DataFrame(columns=["doi", "fulltext_enrichment_action"]),
        pd.DataFrame(columns=["doi"]),
    )
    summary = build_host_summary(queue)

    assert queue.empty
    assert "doi" in queue.columns
    assert "route_host" in queue.columns
    assert summary.empty
    assert "route_host" in summary.columns
    assert "high_priority_count" in summary.columns


class ManualPdfExplorationQueueTests(unittest.TestCase):
    def test_primary_route_prefers_probable_pdf_over_doi_landing(self):
        route, route_type = pick_primary_route(
            {
                "doi": "10.1000/example",
                "probable_pdf_url_candidates": "https://repo.example.edu/bitstream/article.pdf",
                "pdf_url_candidates_current": "https://doi.org/10.1000/example",
            }
        )
        self.assertEqual(route, "https://repo.example.edu/bitstream/article.pdf")
        self.assertEqual(route_type, "probable_pdf_url")

    def test_identity_mismatch_is_review_lane(self):
        lane, _ = priority_lane(
            {
                "pdf_download_failure_category": "source_identity_mismatch",
                "pdf_url_quality": "probable_pdf",
                "route_host": "repo.example.edu",
                "open_access_is_oa": "true",
            }
        )
        self.assertEqual(lane, 5)

    def test_probable_oa_pdf_is_first_lane(self):
        lane, _ = priority_lane(
            {
                "pdf_download_failure_category": "forbidden",
                "pdf_url_quality": "probable_pdf",
                "route_host": "publisher.example",
                "open_access_is_oa": "true",
                "manual_doi_article_recovery_candidate": "true",
            }
        )
        self.assertEqual(lane, 1)

    def test_obvious_poster_session_is_review_lane(self):
        lane, reason = priority_lane(
            {
                "study_title": "Poster Sessions A",
                "pdf_download_failure_category": "forbidden",
                "pdf_url_quality": "probable_pdf",
                "route_host": "publisher.example",
                "open_access_is_oa": "true",
                "manual_doi_article_recovery_candidate": "true",
            }
        )
        self.assertEqual(lane, 5)
        self.assertIn("Publication-format review", reason)

    def test_build_queue_keeps_only_current_known_url_actions(self):
        worklist = pd.DataFrame(
            [
                {
                    "doi": "10.1000/keep",
                    "fulltext_enrichment_action": "download_known_pdf",
                    "open_access_is_oa": "true",
                    "open_access_status": "gold",
                    "pdf_url_quality": "probable_pdf",
                    "probable_pdf_url_candidates": "https://example.org/keep.pdf",
                    "pdf_url_candidates": "https://example.org/keep.pdf",
                    "best_pdf_url": "https://example.org/keep.pdf",
                    "open_access_url": "https://example.org/keep",
                    "study_title": "Keep",
                    "study_year": "2024",
                    "source_family": "primary",
                    "source_type": "primary",
                },
                {
                    "doi": "10.1000/drop",
                    "fulltext_enrichment_action": "no_accessible_fulltext",
                    "open_access_is_oa": "false",
                    "open_access_status": "closed",
                    "pdf_url_quality": "",
                    "probable_pdf_url_candidates": "",
                    "pdf_url_candidates": "",
                    "best_pdf_url": "",
                    "open_access_url": "",
                    "study_title": "Drop",
                    "study_year": "2024",
                    "source_family": "primary",
                    "source_type": "primary",
                },
            ]
        )
        ranked = pd.DataFrame(
            [
                {
                    "doi": "10.1000/keep",
                    "study_journal": "Journal",
                    "pdf_download_failure_category": "forbidden",
                    "manual_doi_article_recovery_candidate": "true",
                    "manual_doi_article_recovery_hint": "",
                },
                {
                    "doi": "10.1000/drop",
                    "study_journal": "Journal",
                    "pdf_download_failure_category": "forbidden",
                    "manual_doi_article_recovery_candidate": "true",
                    "manual_doi_article_recovery_hint": "",
                },
            ]
        )
        queue = build_queue(worklist, ranked)
        self.assertEqual(queue["doi"].tolist(), ["10.1000/keep"])
        self.assertEqual(queue.iloc[0]["priority_group"], "direct_pdf_browser_rescue")

    def test_language_audit_removes_non_english_record_from_actionable_lanes(self):
        worklist = pd.DataFrame(
            [{
                "doi": "10.1000/de",
                "fulltext_enrichment_action": "download_known_pdf",
                "open_access_is_oa": "true",
                "open_access_status": "gold",
                "pdf_url_quality": "probable_pdf",
                "probable_pdf_url_candidates": "https://example.org/de.pdf",
                "pdf_url_candidates": "https://example.org/de.pdf",
                "best_pdf_url": "https://example.org/de.pdf",
                "open_access_url": "https://example.org/de",
                "study_title": "Eine deutsche Studie",
                "study_year": "2024",
                "source_family": "primary",
                "source_type": "primary",
            }]
        )
        ranked = pd.DataFrame(
            [{
                "doi": "10.1000/de",
                "study_journal": "Journal",
                "pdf_download_failure_category": "forbidden",
                "manual_doi_article_recovery_candidate": "true",
                "manual_doi_article_recovery_hint": "",
            }]
        )
        language = {
            "10.1000/de": {
                "language_audit_decision": "exclude_non_english",
                "metadata_language": "de",
                "detected_title_language": "de",
                "detected_title_language_confidence": "0.99",
                "format_evidence": "title_language=de",
            }
        }
        queue = build_queue(worklist, ranked, language_audit=language)
        self.assertEqual(queue.iloc[0]["priority_lane"], 6)
        self.assertEqual(queue.iloc[0]["priority_group"], "non_english_excluded_from_manual_recovery")


if __name__ == "__main__":
    unittest.main()
