from scripts.build_analysis_index import build_index


def entity(payload: dict, lens: str, key: str) -> list:
    return next(entry for entry in payload["entities"][lens] if entry[0] == key)


def test_analysis_index_deduplicates_studies_and_indexes_every_filter_axis() -> None:
    primary = [
        {
            "study_doi": "10.1000/example",
            "study_year": "2021",
            "study_journal": "Journal of Testing",
            "domain": "clinical_outcomes",
            "entity_kind": "condition_indication",
            "graph_entity_label": "Depression",
            "graph_admission_status": "main_graph",
            "source_access_level": "full_text_seen",
            "graph_overview_subjects_json": '[{"label":"Psilocybin","kind":"atomic_compound"}]',
            "first_author": {"id": "orcid:0000-0001", "display_name": "Ada Author"},
            "last_author": {"id": "orcid:0000-0002", "display_name": "Lee Author"},
        },
        {
            "study_doi": "10.1000/example",
            "study_year": "2021",
            "study_journal": "Journal of Testing",
            "domain": "safety",
            "entity_kind": "safety_adverse_event",
            "graph_entity_label": "Headache",
            "graph_admission_status": "main_graph",
            "source_access_level": "full_text_seen",
            "graph_overview_subjects_json": '[{"label":"Psilocybin","kind":"atomic_compound"}]',
            "first_author": {"id": "orcid:0000-0001", "display_name": "Ada Author"},
            "last_author": {"id": "orcid:0000-0002", "display_name": "Lee Author"},
        },
    ]
    reviews = [
        {
            "study_doi": "10.1000/review",
            "study_year": "2023",
            "study_journal": "Review Quarterly",
            "domain": "clinical_outcomes",
            "entity_kind": "condition_indication",
            "graph_entity_label": "Anxiety",
            "graph_admission_status": "main_graph",
            "graph_overview_subjects_json": '[{"label":"Classic psychedelics","kind":"compound_class"}]',
            "authors": "Rita Reviewer",
        }
    ]

    payload = build_index(
        {"primary": primary, "meta_analyses": [], "reviews": reviews},
        "2026-01-01T00:00:00Z",
    )

    assert payload["study_count"] == 2
    psilocybin = entity(payload, "compound", "psilocybin")
    assert psilocybin[2] == [0]
    assert psilocybin[3] == {
        "condition_indication": [0],
        "safety_adverse_event": [0],
    }
    assert entity(payload, "author", "orcid:0000-0001")[2] == [0]
    assert entity(payload, "journal", "journal of testing")[2] == [0]
    assert payload["areas"]["condition_indication"][1] == [0, 1]
    assert payload["areas"]["safety_adverse_event"][1] == [0]
    condition_concepts = {entry[0]: entry[2] for entry in payload["concepts"]["condition_indication"]}
    assert condition_concepts == {"anxiety": [1], "depression": [0]}
