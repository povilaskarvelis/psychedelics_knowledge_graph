from __future__ import annotations

from pipeline.kg.graph_view_contract import (
    GRAPH_VIEW_CONTRACT_SCHEMA_VERSION,
    graph_view_definitions,
    graph_view_ids,
    graph_view_kind_mapping,
    load_graph_view_contract,
    public_graph_view_facets,
    record_matches_graph_view,
)
from pipeline.publish.export_evidence_payload import DETAIL_VIEW_ENTITY_KINDS
from pipeline.publish.promote_routed_run import DETAIL_VIEW_KEYS


def test_contract_is_the_single_python_source_for_browser_view_membership() -> None:
    contract = load_graph_view_contract()
    assert contract["schema_version"] == GRAPH_VIEW_CONTRACT_SCHEMA_VERSION
    assert contract["default_view"] == "condition_indication"
    assert tuple(view["id"] for view in graph_view_definitions()) == graph_view_ids()
    assert DETAIL_VIEW_ENTITY_KINDS == graph_view_kind_mapping()
    assert DETAIL_VIEW_KEYS == graph_view_ids()


def test_shared_view_filters_preserve_contextual_category_semantics() -> None:
    assert record_matches_graph_view(
        {
            "entity_kind": "target",
            "domain": "molecular_target",
            "graph_entity_label": "NMDA receptor",
        },
        "target_system",
    )
    assert not record_matches_graph_view(
        {
            "entity_kind": "biomarker_readout",
            "domain": "molecular_pathway_readout",
            "graph_entity_label": "NMDA receptor expression",
        },
        "target_system",
    )
    assert record_matches_graph_view(
        {
            "entity_kind": "public_health_measure",
            "domain": "real_world_public_health",
            "graph_entity_label": "Lifetime prevalence",
        },
        "public_health_measure",
    )
    assert not record_matches_graph_view(
        {
            "entity_kind": "public_health_measure",
            "domain": "general_topic_coverage",
            "graph_entity_label": "Research landscape",
        },
        "public_health_measure",
    )


def test_public_graph_view_facets_expose_reproducible_atomic_filters() -> None:
    facets = {view["value"]: view for view in public_graph_view_facets()}
    assert facets["target_system"]["filters"] == {
        "object_kinds": ["target", "system_family"],
        "domains": [],
        "object_labels": [],
    }
    assert facets["behavioral_effect"]["filters"]["object_kinds"] == [
        "cognitive_behavioral_construct"
    ]
    assert "Head-twitch response" in facets["behavioral_effect"]["filters"][
        "object_labels"
    ]
