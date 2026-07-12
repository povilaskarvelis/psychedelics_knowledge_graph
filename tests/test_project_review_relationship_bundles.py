from pipeline.kg.project_review_relationship_bundles import project_bundles


def test_projection_preserves_combination_and_unmapped_anchors() -> None:
    rows = [
        {
            "status": "ok",
            "study_doi": "10.1/test",
            "study_title": "Test",
            "text_depth": "article_text",
            "result": {
                "relationships": [
                    {
                        "item_id": "rel_1",
                        "relationship_kind": "review_synthesis",
                        "relationship_statement": "Ketamine plus lamotrigine has inconclusive efficacy.",
                        "relation_phrase": "has inconclusive evidence for",
                        "direction_or_tone": "insufficient_evidence",
                        "evidence_status": "preliminary_or_mixed_evidence",
                        "paper_prominence": "paper_defining",
                        "graph_eligibility": "main_graph",
                        "graph_form": "combination",
                        "domain_labels": ["clinical_outcome"],
                        "anchors": [
                            {"role": "compound", "label": "Ketamine", "anchor_type": "named_entity"},
                            {"role": "co_intervention", "label": "Lamotrigine", "anchor_type": "named_entity"},
                            {"role": "outcome", "label": "Antidepressant efficacy", "anchor_type": "other"},
                        ],
                    }
                ]
            },
        }
    ]
    registry = {"compounds": [{"label": "Ketamine", "aliases": []}], "targets": [], "disorders": []}
    relationships, anchors, report = project_bundles(rows, registry)

    assert relationships[0]["projection_mode"] == "relationship_node"
    assert relationships[0]["evidence_status"] == "preliminary_or_mixed_evidence"
    assert relationships[0]["admitted_to_main_graph"] is True
    assert relationships[0]["semantic_integrity"] == "preserved"
    assert len(anchors) == 3
    assert anchors[1]["raw_label"] == "Lamotrigine"
    assert anchors[1]["normalization_status"] == "provisional_preserved"
    assert report["counts"]["main_graph_relationships"] == 1


def test_secondary_relationship_cannot_enter_main_projection() -> None:
    rows = [
        {
            "status": "ok",
            "study_doi": "10.1/test",
            "text_depth": "article_text",
            "result": {
                "relationships": [
                    {
                        "item_id": "rel_2",
                        "relationship_kind": "review_synthesis",
                        "relationship_statement": "Peripheral detail",
                        "relation_phrase": "mentions",
                        "direction_or_tone": "descriptive_only",
                        "paper_prominence": "secondary_context",
                        "graph_eligibility": "main_graph",
                        "graph_form": "atomic",
                        "domain_labels": [],
                        "anchors": [
                            {"role": "compound", "label": "Ketamine", "anchor_type": "named_entity"},
                            {"role": "outcome", "label": "Detail", "anchor_type": "other"},
                        ],
                    }
                ]
            },
        }
    ]
    relationships, _anchors, report = project_bundles(rows, {"compounds": [], "targets": [], "disorders": []})
    assert relationships[0]["admitted_to_main_graph"] is False
    assert report["counts"]["main_graph_relationships"] == 0
    assert report["counts"]["model_main_graph_rejected_by_prominence"] == 1
