from __future__ import annotations

from pipeline.extract.build_review_paper_complete_bundles import build_bundles


def cohort_row() -> dict:
    return {
        "doi": "10.1000/review",
        "study_title": "Review",
        "review_type": "review",
        "text_depth": "article_text",
        "routed_domains": ["clinical_outcome", "safety_tolerability"],
    }


def output_row(domain: str, item_id: str, focus: str = "main_focus") -> dict:
    return {
        "task_id": f"task-{domain}",
        "route_id": f"route-{domain}",
        "status": "ok",
        "result": {
            "task_id": f"task-{domain}",
            "route_id": f"route-{domain}",
            "study_doi": "10.1000/review",
            "domain_route": domain,
            "extraction_status": "extracted",
            "review_assessment": {
                "substantive_coverage_inventory": [
                    {
                        "inventory_id": f"inventory-{item_id}",
                        "has_coverage_item": True,
                        "coverage_item_ids": [item_id],
                        "reason_if_no_coverage_item": "not_applicable",
                    }
                ]
            },
            "coverage_items": [
                {
                    "item_id": item_id,
                    "coverage_focus": focus,
                    "coverage_type": "summarizes",
                    "compound_or_class": "Psilocybin",
                    "entity_type": "disorder",
                    "entity": "Depression",
                    "summary_statement": "The review summarizes the relationship.",
                }
            ],
            "extraction_warnings": [],
        },
    }


def test_complete_bundle_combines_all_domains() -> None:
    bundles, report = build_bundles(
        [cohort_row()],
        [output_row("clinical_outcome", "C1"), output_row("safety_tolerability", "S1")],
    )

    assert report["paper_complete"] is True
    assert report["counts"]["papers"] == 1
    assert report["counts"]["coverage_items"] == 2
    assert bundles[0]["missing_domains"] == []
    assert bundles[0]["paper_qa_issues"] == []


def test_bundle_flags_missing_domain_and_peripheral_item() -> None:
    bundles, report = build_bundles(
        [cohort_row()],
        [output_row("clinical_outcome", "C1", focus="brief_context")],
    )

    assert report["paper_complete"] is False
    assert bundles[0]["missing_domains"] == ["safety_tolerability"]
    assert "missing_domain_outputs" in bundles[0]["paper_qa_issues"]
    assert "no_main_focus_item_across_paper" in bundles[0]["paper_qa_issues"]
    assert bundles[0]["domain_outputs"][0]["coverage_items"][0]["qa_flags"] == [
        "non_graphable_focus:brief_context"
    ]


def test_bundle_flags_inventory_link_errors() -> None:
    row = output_row("clinical_outcome", "C1")
    row["result"]["review_assessment"]["substantive_coverage_inventory"][0]["coverage_item_ids"] = ["missing"]

    bundles, report = build_bundles([cohort_row()], [row, output_row("safety_tolerability", "S1")])

    issues = bundles[0]["domain_outputs"][0]["inventory_qa_issues"]
    assert "inventory_missing_coverage_item:inventory-C1:missing" in issues
    assert "coverage_item_not_in_inventory:C1" in issues
    assert report["issue_counts"]["inventory_missing_coverage_item"] == 1
