"""Retain explicit PK observations without inventing resolved chemical identities.

The extracted relationship, object and method are evidence in their own right.
A registry miss should not discard them. Recovery is paper-detail only and never
splits a metabolite panel, enzyme comparison or bundled quantitative result.
"""
from __future__ import annotations

from pipeline.kg.pk_relationships import PK_RELATIONSHIP_EDGE_TYPES

MISSING = {"", "none", "null", "n/a", "na", "unknown", "uncertain", "not_reported",
           "not reported", "not_applicable", "not applicable", "unspecified"}
IDENTITY_KINDS = {
    "metabolite_or_analyte": "compound",
    "enzyme_or_transporter": "target",
    "metabolic_or_transport_pathway": "pathway_process",
}
EXPOSURE_RELATIONS = {"exposure_characterized", "detected_or_monitored_in"}


def text(value: object) -> str:
    return " ".join(str(value or "").split())


def explicit_pk_observation(row: dict) -> bool:
    """Check saved fields before the normalizer can infer relationship metadata."""
    return (
        row.get("domain", row.get("domain_route")) == "pharmacokinetics_exposure"
        and row.get("source_item_type") == "primary_item"
        and row.get("source_type") == "primary"
        and row.get("pk_relationship_type") in PK_RELATIONSHIP_EDGE_TYPES
        and row.get("pk_graph_object_kind") in IDENTITY_KINDS
        and all(text(row.get(k)).casefold() not in MISSING for k in (
            "pk_graph_object_label", "model_or_method", "finding_summary",
        ))
    )


def pk_observation_signature(row: dict) -> tuple[str, ...]:
    """Keep recovery tied to the unmodified saved contract, including its source."""
    return tuple(text(row.get(k)) for k in (
        "task_id", "source_item_index", "study_doi", "doi", "pk_relationship_type",
        "pk_graph_object_kind", "pk_graph_object_label", "model_or_method", "finding_summary",
    ))


def pk_observation_recovery(row: dict, *, self_reference: bool = False) -> dict | None:
    """Return one literal observation; a self-metabolism claim stays unresolved.

    A measured exposure may name the same analyte on both sides. That is a
    measurement, not a transformation into itself. The narrow exception requires
    an explicit exposure/detection relationship and a saved measurement parameter.
    """
    if not explicit_pk_observation(row):
        return None
    kind = row["pk_graph_object_kind"]
    label = text(row["pk_graph_object_label"])
    parameter = text(row.get("pk_or_exposure_parameter"))
    exposure = (kind == "metabolite_or_analyte"
                and row["pk_relationship_type"] in EXPOSURE_RELATIONS
                and parameter.casefold() not in MISSING)
    if self_reference and not exposure:
        return None
    if exposure:
        return {"kind": "pharmacokinetic_parameter", "label": f"{label}: {parameter}",
                "match_type": "explicit_pk_exposure_observation_detail_only",
                "reason": "pk_exposure_measurement_not_chemical_transformation"}
    return {"kind": IDENTITY_KINDS[kind], "label": label,
            "match_type": "unresolved_primary_pk_object_detail_only",
            "reason": "explicit_pk_object_requires_identity_resolution"}


def intact_pk_observation(row: dict, source: dict) -> dict:
    """Undo generic split decorations when the PK object itself was never split.

    This only operates on rows whose complete PK signature still equals the saved
    source. It cannot merge distinct source items or restore a different analyte.
    """
    if not row.get("entity_split_source_label"):
        return row
    assert pk_observation_signature(row) == pk_observation_signature(source)
    out = dict(row)
    split_field = {"enzyme_or_transporter": "target",
                   "metabolic_or_transport_pathway": "pathway_or_process",
                   "metabolite_or_analyte": "metabolite_or_analyte"}[row["pk_graph_object_kind"]]
    for field in (split_field, "graph_entity_label", "entity_label", "entity",
                  "graph_entity_original", "entity_split_source_label", "endpoint_label_source",
                  "kg_entity_kind_override"):
        if field in source:
            out[field] = source[field]
        else:
            out.pop(field, None)
    return out
