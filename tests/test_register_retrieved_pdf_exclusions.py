import json

from pipeline.fulltext.register_retrieved_pdf_exclusions import (
    audit_exclusions,
    browser_url_exclusions,
    legacy_post_retrieval_exclusions,
)


def test_browser_url_exclusions_accepts_only_deterministic_poster_outcomes() -> None:
    selected = browser_url_exclusions(
        [
            {
                "records": [
                    {
                        "doi": "10.7490/F1000RESEARCH.1111976.1",
                        "status": "excluded_publication_format",
                        "publication_format": "conference_poster",
                        "reason": "explicit_url_path_segment:posters",
                        "evidence_url": "https://f1000research.com/posters/5-997",
                    },
                    {
                        "doi": "10.example/unverified-note",
                        "status": "not_recovered",
                        "publication_format": "conference_poster",
                        "evidence_url": "https://example.org/posters/123",
                    },
                    {
                        "doi": "10.example/missing-evidence-url",
                        "status": "excluded_publication_format",
                        "publication_format": "conference_poster",
                    },
                    {
                        "doi": "10.example/proceedings",
                        "status": "excluded_publication_format",
                        "publication_format": "conference_proceedings",
                        "evidence_url": "https://example.org/proceedings/2026",
                    },
                ]
            }
        ]
    )

    assert selected == [
        {
            "doi": "10.7490/f1000research.1111976.1",
            "decision": "exclude",
            "reason_code": "conference_poster",
            "publication_format": "conference_poster",
            "reason": (
                "The retrieved record is a conference poster rather than an eligible source article, "
                "review, or meta-analysis."
            ),
            "evidence": (
                "DOI landing-page URL deterministically identifies a poster record: "
                "https://f1000research.com/posters/5-997 "
                "(explicit_url_path_segment:posters)"
            ),
            "decision_method": "deterministic_landing_url_format_rule",
            "reviewer": "pipeline_rule",
            "source_artifact": "",
        }
    ]


def test_legacy_migration_moves_all_doi_specific_evidence_out_of_prescreen(tmp_path) -> None:
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "doi": "10.example/metadata",
                        "publication_format": "conference_abstract",
                        "evidence_basis": "Crossref supplement metadata: page S12",
                        "reason": "Metadata-level exclusion.",
                    },
                    {
                        "doi": "10.example/document",
                        "publication_format": "conference_poster",
                        "evidence_basis": "The recovered publisher PDF explicitly says POSTER.",
                        "reason": "Document-level exclusion.",
                    },
                ]
            }
        )
    )

    rows = legacy_post_retrieval_exclusions(path)

    assert [row["doi"] for row in rows] == ["10.example/metadata", "10.example/document"]
    assert all(
        row["decision_method"] == "legacy_curated_post_retrieval_evidence_migration"
        for row in rows
    )


def test_audit_exclusions_accepts_video_lecture_format(tmp_path) -> None:
    path = tmp_path / "manual_review.csv"
    path.write_text(
        "doi,recommended_action,publication_format,format_evidence\n"
        "10.64239/pi-vl11508,exclude_publication_format,video_lecture,Publisher page labels a video lecture.\n"
    )

    rows = audit_exclusions(path)

    assert len(rows) == 1
    assert rows[0]["doi"] == "10.64239/pi-vl11508"
    assert rows[0]["publication_format"] == "video_lecture"
    assert "educational video lecture" in rows[0]["reason"]
