import json
from pathlib import Path

from pipeline.extract.extraction_profile_matrix import PRIMARY_PROMPT_BY_DOMAIN
from pipeline.extract.route_extraction_profiles import ENTITY_TYPES_BY_DOMAIN
from pipeline.kg.build_evidence_tables import relation_type_for


ROOT = Path(__file__).resolve().parents[1]
MAPPING_PATH = ROOT / "schema" / "extraction_to_kg_mapping.json"
NODE_VOCABULARY_PATH = ROOT / "schema" / "kg_node_vocabularies.json"
REVIEW_SCHEMA_DIR = ROOT / "schema" / "extraction_profiles" / "review"
META_ANALYSIS_SCHEMA_DIR = ROOT / "schema" / "extraction_profiles" / "meta_analysis"


def load_mapping() -> dict:
    return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))


def test_mapping_covers_active_extraction_domains() -> None:
    mapping = load_mapping()
    domains = set(mapping["domain_mappings"])

    expected_domains = set(PRIMARY_PROMPT_BY_DOMAIN) | set(ENTITY_TYPES_BY_DOMAIN)

    assert expected_domains <= domains


def test_mapping_matches_route_entity_types() -> None:
    mapping = load_mapping()

    for domain, entity_types in ENTITY_TYPES_BY_DOMAIN.items():
        domain_mapping = mapping["domain_mappings"][domain]

        assert set(domain_mapping["extraction_entity_types"]) == entity_types


def test_current_node_kinds_match_current_relation_logic() -> None:
    mapping = load_mapping()

    for domain_mapping in mapping["domain_mappings"].values():
        if not domain_mapping["maps_to_graph"]:
            continue
        graph_domain = domain_mapping["graph_domain"]
        for node_kind in domain_mapping["node_kinds"]:
            if node_kind["status"] != "current":
                continue

            assert node_kind["primary_relation_type"] == relation_type_for(
                graph_domain,
                node_kind["kind"],
                "primary_evidence",
            )
            assert node_kind["secondary_relation_type"] == relation_type_for(
                graph_domain,
                node_kind["kind"],
                "secondary_literature",
            )


def test_mappable_domains_define_graph_anchors_and_attributes() -> None:
    mapping = load_mapping()

    assert "coverage_focus" in mapping["common_secondary_attributes"]

    for domain, domain_mapping in mapping["domain_mappings"].items():
        anchor_fields = domain_mapping["anchor_fields"]

        if domain_mapping["maps_to_graph"]:
            assert domain_mapping["node_kinds"], domain
            assert anchor_fields["compound"], domain
            assert anchor_fields["entity"], domain
            assert domain_mapping["attribute_fields"], domain
        else:
            assert domain_mapping["node_kinds"] == []
            assert domain_mapping["no_graph_mapping_reason"]


def test_planned_node_kinds_are_declared_in_mapping() -> None:
    mapping = load_mapping()
    declared_node_kinds = set(mapping["node_kinds"])

    for domain_mapping in mapping["domain_mappings"].values():
        for node_kind in domain_mapping["node_kinds"]:
            assert node_kind["kind"] in declared_node_kinds
            if node_kind["status"] == "planned":
                assert mapping["node_kinds"][node_kind["kind"]]["status"] == "planned"
                assert node_kind["primary_relation_type"] in mapping["relation_types"]


def test_anchor_alignment_for_brain_and_pk_schemas() -> None:
    brain_entity_types = [
        "brain_region",
        "brain_network",
        "neural_circuit",
        "biomarker_readout",
        "not_applicable",
        "uncertain",
    ]
    pk_entity_types = [
        "pharmacokinetic_parameter",
        "compound",
        "target",
        "pathway_process",
        "not_applicable",
        "uncertain",
    ]

    for schema_dir, item_key, expected_brain_required, expected_pk_required in [
        (
            REVIEW_SCHEMA_DIR,
            "coverage_items",
            {"primary_graph_anchor_kind", "brain_region", "brain_network", "neural_circuit"},
            {
                "primary_graph_anchor_kind",
                "metabolite_or_analyte",
                "metabolic_or_transport_target",
                "metabolic_or_transport_pathway",
            },
        ),
        (
            META_ANALYSIS_SCHEMA_DIR,
            "synthesis_results",
            {"primary_graph_anchor_kind", "brain_region", "brain_network"},
            {"primary_graph_anchor_kind", "metabolite_or_analyte"},
        ),
    ]:
        brain_schema = json.loads((schema_dir / "brain_system.schema.json").read_text(encoding="utf-8"))
        brain_item = brain_schema["properties"][item_key]["items"]
        brain_item = brain_schema["definitions"][brain_item["$ref"].removeprefix("#/definitions/")]
        brain_result = brain_item["properties"]["domain_result"]

        assert brain_item["properties"]["entity_type"]["enum"] == brain_entity_types
        assert "brain_region_or_network" not in brain_result["properties"]
        assert expected_brain_required <= set(brain_result["required"])

        pk_schema = json.loads((schema_dir / "pharmacokinetics_exposure.schema.json").read_text(encoding="utf-8"))
        pk_item = pk_schema["properties"][item_key]["items"]
        pk_item = pk_schema["definitions"][pk_item["$ref"].removeprefix("#/definitions/")]
        pk_result = pk_item["properties"]["domain_result"]

        assert pk_item["properties"]["entity_type"]["enum"] == pk_entity_types
        assert expected_pk_required <= set(pk_result["required"])


def test_node_vocabulary_covers_new_planned_node_kinds() -> None:
    mapping = load_mapping()
    vocabulary = json.loads(NODE_VOCABULARY_PATH.read_text(encoding="utf-8"))
    vocabulary_kinds = set(vocabulary["node_kinds"])
    planned_node_kinds = {
        node_kind["kind"]
        for domain_mapping in mapping["domain_mappings"].values()
        for node_kind in domain_mapping["node_kinds"]
        if node_kind["status"] == "planned"
    }

    assert planned_node_kinds <= vocabulary_kinds
    for kind in planned_node_kinds:
        assert vocabulary["node_kinds"][kind], kind
