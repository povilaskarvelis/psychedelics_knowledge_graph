from pipeline.kg.convert_review_relationship_bundles_to_evidence_rows import (
    convert_bundles,
    legacy_review_row,
    review_scope_for_relationship,
    review_row,
)


def test_converts_one_paper_centered_relationship_to_one_evidence_row() -> None:
    bundles = [{
        "study_doi": "10.1/test", "study_title": "Ketamine review", "text_depth": "article_text", "status": "ok",
        "result": {
            "paper_frame": {"primary_subjects": ["Ketamine"]},
            "bundle_summary": "Ketamine is reviewed for depression.", "full_text_priority": "low",
            "relationships": [{
                "item_id": "rel_1", "relationship_kind": "review_synthesis",
                "relationship_statement": "Ketamine reduces depressive symptoms in treatment-resistant depression.",
                "anchors": [
                    {"role": "compound", "label": "Ketamine", "anchor_type": "named_entity"},
                    {"role": "condition", "label": "Treatment-resistant depression", "anchor_type": "named_entity"},
                ],
                "direction_or_tone": "supports", "paper_prominence": "paper_defining",
                "centrality_basis": ["review_conclusion"], "evidence_stratum": "human",
                "domain_labels": ["clinical_outcome"],
                "evidence_locators": [{"location": "conclusion", "locator": "Conclusion", "supporting_text": "Ketamine reduced symptoms."}],
                "limitations": ["Evidence remains limited."], "graph_eligibility": "main_graph",
                "graph_form": "atomic", "covers_major_aspect_ids": ["A1"],
            }],
        },
    }]
    tasks = [{"study_doi": "10.1/test", "paper_metadata": {"review_type": "systematic_review", "study_year": "2024"}}]
    registry = {"compounds": [{"label": "Ketamine", "aliases": []}], "targets": [], "disorders": []}

    rows, report = convert_bundles(bundles, tasks, registry)

    assert len(rows) == 1
    assert report["counts"]["papers_converted"] == 1
    assert rows[0]["source_item_type"] == "review_relationship"
    assert rows[0]["graph_subject_label"] == "Ketamine"
    assert rows[0]["graph_subject_kind"] == "atomic_compound"
    assert rows[0]["condition_or_indication"] == "Treatment-resistant depression"
    assert rows[0]["graph_admission_status"] == "main_graph"
    assert rows[0]["coverage_focus"] == "paper_defining"
    assert rows[0]["coverage_focus_normalized"] == "Main focus"


def test_secondary_context_is_kept_as_paper_detail() -> None:
    bundle = {
        "study_doi": "10.1/test", "study_title": "Review", "text_depth": "abstract_only", "status": "ok",
        "result": {"paper_frame": {"primary_subjects": ["Psychedelics"]}, "relationships": [{
            "item_id": "detail", "relationship_kind": "reviewed_relationship",
            "relationship_statement": "A background relationship is discussed.",
            "anchors": [
                {"role": "compound_class", "label": "Psychedelics", "anchor_type": "compound_class"},
                {"role": "research_topic", "label": "Background research", "anchor_type": "paper_topic"},
            ],
            "direction_or_tone": "descriptive_only", "paper_prominence": "secondary_context",
            "centrality_basis": ["dedicated_section"], "evidence_stratum": "field_or_method",
            "domain_labels": ["general_topic_coverage"],
            "evidence_locators": [{"location": "abstract", "locator": "Abstract", "supporting_text": ""}],
            "limitations": [], "graph_eligibility": "paper_detail_only", "graph_form": "class",
            "covers_major_aspect_ids": [],
        }]},
    }
    tasks = [{"study_doi": "10.1/test", "paper_metadata": {"review_type": "review"}}]
    registry = {"compounds": [], "targets": [], "disorders": []}

    rows, _report = convert_bundles([bundle], tasks, registry)

    assert rows[0]["graph_admission_status"] == "paper_detail"
    assert rows[0]["coverage_focus_normalized"] == "Context only"


def test_legacy_review_rows_are_identified_but_meta_analysis_is_preserved() -> None:
    assert legacy_review_row({"source_item_type": "review_coverage_item", "paper_type": "review"})
    assert not legacy_review_row({"source_item_type": "meta_analysis_item", "paper_type": "meta_analysis"})
    assert not legacy_review_row({
        "source_item_type": "review_relationship", "paper_type": "review",
        "review_extraction_method": "paper_centered_one_pass_v2",
    })


def test_review_without_paper_defining_psychedelic_scope_is_marked_not_graphable() -> None:
    bundle = {
        "study_doi": "10.1/peripheral",
        "study_title": "Neurofeedback for substance use disorders",
        "text_depth": "article_text",
        "status": "ok",
        "result": {
            "paper_frame": {"primary_subjects": ["Neurofeedback", "Substance use disorders"]},
            "relationships": [{
                "item_id": "rel_1",
                "relationship_kind": "review_synthesis",
                "relationship_statement": "Neurofeedback may affect substance use outcomes.",
                "anchors": [
                    {"role": "intervention", "label": "Neurofeedback", "anchor_type": "named_entity"},
                    {"role": "condition", "label": "Substance use disorders", "anchor_type": "named_entity"},
                ],
                "direction_or_tone": "supports",
                "paper_prominence": "paper_defining",
                "centrality_basis": ["review_conclusion"],
                "evidence_stratum": "human",
                "domain_labels": ["clinical_outcome"],
                "evidence_locators": [],
                "limitations": [],
                "graph_eligibility": "main_graph",
                "graph_form": "atomic",
                "covers_major_aspect_ids": ["A1"],
            }],
        },
    }
    tasks = [{"study_doi": "10.1/peripheral", "paper_metadata": {"review_type": "systematic_review"}}]
    registry = {"compounds": [{"label": "Ketamine", "aliases": []}], "targets": [], "disorders": []}

    rows, report = convert_bundles([bundle], tasks, registry)

    assert rows[0]["review_scope_status"] == "psychedelics_peripheral_or_absent"
    assert rows[0]["graph_admission_status"] == "paper_detail"
    assert rows[0]["graph_admission_reason"] == "review_paper_scope_not_graphable"
    assert report["by_review_scope"] == {"psychedelics_peripheral_or_absent": 1}


def test_nmda_antagonist_review_title_establishes_review_scope() -> None:
    status, reason = review_scope_for_relationship(
        {
            "study_title": (
                "Translating the N-methyl-d-aspartate receptor antagonist model "
                "of schizophrenia"
            )
        },
        "Cognitive impairment",
        set(),
    )

    assert status == "in_scope"
    assert reason == "title_has_in_scope_class_or_context"


def test_all_review_rows_are_replaced_but_meta_analysis_is_preserved() -> None:
    assert review_row({"source_item_type": "review_coverage_item", "paper_type": "review"})
    assert review_row({
        "source_item_type": "review_relationship", "paper_type": "review",
        "review_extraction_method": "paper_centered_one_pass_v2",
    })
    assert not review_row({"source_item_type": "meta_analysis_item", "paper_type": "meta_analysis"})


def test_current_task_set_can_explicitly_skip_stale_append_only_bundle() -> None:
    bundles = [
        {"study_doi": "10.1/current", "status": "ok", "result": {"relationships": []}},
        {"study_doi": "10.1/stale", "status": "ok", "result": {"relationships": []}},
    ]
    tasks = [{"study_doi": "10.1/current", "paper_metadata": {}}]

    _rows, report = convert_bundles(
        bundles,
        tasks,
        {"compounds": [], "targets": [], "disorders": []},
        allow_stale_bundles=True,
    )

    assert report["skipped"] == {"stale_bundle_not_in_current_tasks": 1}
