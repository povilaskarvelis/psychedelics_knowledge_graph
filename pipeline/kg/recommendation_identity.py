"""Keep native recommendations as attributed guidance, not observed effects."""
from pipeline.extract.io_utils import normalize

SOURCE_TYPES = {"guideline", "consensus_statement", "position_statement", "expert_recommendation"}
MISSING = {"", "none", "null", "n/a", "na", "unknown", "uncertain", "not_reported", "not reported", "not_applicable", "not applicable"}
ENTITY_KIND = "recommendation_topic"
DETAIL_REASON = "recommendation_is_secondary_guidance_not_observed_effect"


def explicit_recommendation(row: dict) -> bool:
    return (
        row.get("extraction_schema_version") == "recommendation_consensus_v1"
        and row.get("source_item_type") == "recommendation_item"
        and row.get("source_type") in SOURCE_TYPES
        and row.get("paper_assessment_route") == "secondary_literature"
        and row.get("source_family") == "secondary_literature"
        and row.get("is_in_scope") is True
        and row.get("has_extractable_scoped_recommendation") is True
        and all(normalize(row.get(k, "")).casefold() not in MISSING
                for k in ("compound_or_class", "entity", "recommendation_statement"))
        and not normalize(row.get("entity_split_source_label", ""))
    )


def recommendation_identity_fields(row: dict) -> dict:
    if not explicit_recommendation(row):
        return {}
    return {
        "domain": "general_topic_coverage", "domain_route": "general_topic_coverage", "dataset": "general_topic_coverage",
        "kg_entity_kind_override": ENTITY_KIND, "graph_entity_label": normalize(row["entity"]),
        "kg_relation_type_override": "has_recommendation",
        "graph_admission_status": "paper_detail", "graph_admission_reason": DETAIL_REASON,
        "support": normalize(row["recommendation_statement"]),
    }
