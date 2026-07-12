from pipeline.validate.compare_review_relationships_to_manual_gold import compare, token_f1


def test_token_f1_detects_related_relationships() -> None:
    assert token_f1("ketamine plus lamotrigine antidepressant efficacy", "lamotrigine modifies ketamine efficacy") > 0.4
    assert token_f1("ketamine depression", "psilocybin visual perception") == 0.0


def test_comparison_builds_manual_review_surface() -> None:
    gold = [
        {
            "doi": "10.1/test",
            "relationship_id": "gold_1",
            "prominence": "paper_defining",
            "subject": "Ketamine plus lamotrigine",
            "relation": "reviewed for",
            "object": "antidepressant efficacy",
            "manual_summary": "Combination evidence is inconclusive",
            "graph_form": "combination_node",
        }
    ]
    baseline = [{"doi": "10.1/test", "source_depth": "article_text", "graph_capture": "poor"}]
    bundles = [
        {
            "status": "ok",
            "study_doi": "10.1/test",
            "result": {
                "relationships": [
                    {
                        "item_id": "rel_1",
                        "paper_prominence": "paper_defining",
                        "graph_form": "combination",
                        "relation_phrase": "has inconclusive evidence for",
                        "relationship_statement": "Ketamine plus lamotrigine has inconclusive antidepressant efficacy.",
                        "anchors": [
                            {"label": "Ketamine"},
                            {"label": "Lamotrigine"},
                            {"label": "Antidepressant efficacy"},
                        ],
                    }
                ]
            },
        }
    ]
    matches, papers, report = compare(gold, baseline, bundles, lexical_threshold=0.3)
    assert matches[0]["lexical_candidate_match"] is True
    assert papers[0]["baseline_graph_capture"] == "poor"
    assert report["counts"]["papers_with_new_central_relationships"] == 1
