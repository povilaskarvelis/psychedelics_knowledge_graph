import json

from pipeline.fulltext.register_retrieved_pdf_exclusions import (
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


def test_legacy_migration_keeps_metadata_prescreen_evidence_separate(tmp_path) -> None:
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

    assert [row["doi"] for row in rows] == ["10.example/document"]
    assert rows[0]["decision_method"] == "legacy_curated_post_retrieval_evidence_migration"
