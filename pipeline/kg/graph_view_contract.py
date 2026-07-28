from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GRAPH_VIEW_CONTRACT = ROOT / "schema" / "graph_view_contract.json"
GRAPH_VIEW_CONTRACT_SCHEMA_VERSION = "psychedelics_kg_graph_view_contract_v1"
REQUIRED_VIEW_FIELDS = {
    "id",
    "label",
    "singular",
    "lower_plural",
    "lower_singular",
    "object_kinds",
}


def _normalized_values(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


@lru_cache(maxsize=4)
def load_graph_view_contract(path: Path = DEFAULT_GRAPH_VIEW_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != GRAPH_VIEW_CONTRACT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported graph view contract schema: {contract.get('schema_version')}"
        )
    views = contract.get("views")
    if not isinstance(views, list) or not views:
        raise ValueError("Graph view contract must define at least one view")

    view_ids: list[str] = []
    for index, raw_view in enumerate(views):
        if not isinstance(raw_view, dict):
            raise ValueError(f"Graph view at index {index} must be an object")
        missing = sorted(REQUIRED_VIEW_FIELDS - set(raw_view))
        if missing:
            raise ValueError(
                f"Graph view at index {index} is missing required fields: {missing}"
            )
        view_id = str(raw_view.get("id") or "").strip()
        if not view_id:
            raise ValueError(f"Graph view at index {index} has an empty id")
        if not _normalized_values(raw_view.get("object_kinds")):
            raise ValueError(f"Graph view {view_id} must define object_kinds")
        view_ids.append(view_id)

    duplicates = sorted({view_id for view_id in view_ids if view_ids.count(view_id) > 1})
    if duplicates:
        raise ValueError(f"Graph view contract contains duplicate ids: {duplicates}")
    if contract.get("default_view") not in view_ids:
        raise ValueError("Graph view contract default_view is not a defined view")
    return contract


def graph_view_definitions() -> list[dict[str, Any]]:
    return [dict(view) for view in load_graph_view_contract()["views"]]


def graph_view_ids() -> tuple[str, ...]:
    return tuple(str(view["id"]) for view in graph_view_definitions())


def graph_view_kind_mapping() -> dict[str, set[str]]:
    return {
        str(view["id"]): set(_normalized_values(view.get("object_kinds")))
        for view in graph_view_definitions()
    }


def public_graph_view_facets() -> list[dict[str, Any]]:
    return [
        {
            "value": str(view["id"]),
            "label": str(view["label"]),
            "filters": {
                "object_kinds": _normalized_values(view.get("object_kinds")),
                "domains": _normalized_values(view.get("domains")),
                "object_labels": _normalized_values(view.get("object_labels")),
            },
        }
        for view in graph_view_definitions()
    ]


def record_matches_graph_view(record: Mapping[str, object], view_id: str) -> bool:
    views = {str(view["id"]): view for view in graph_view_definitions()}
    if view_id not in views:
        raise KeyError(f"Unknown graph view: {view_id}")
    view = views[view_id]
    object_kind = str(
        record.get("object_kind")
        or record.get("entity_kind")
        or record.get("kg_entity_kind")
        or ""
    ).strip().casefold()
    allowed_kinds = {value.casefold() for value in _normalized_values(view.get("object_kinds"))}
    if object_kind not in allowed_kinds:
        return False

    domains = {value.casefold() for value in _normalized_values(view.get("domains"))}
    if domains:
        domain = str(
            record.get("domain")
            or record.get("kg_domain")
            or record.get("finding_type")
            or ""
        ).strip().casefold()
        if domain not in domains:
            return False

    labels = {value.casefold() for value in _normalized_values(view.get("object_labels"))}
    if labels:
        label = str(
            record.get("object_label")
            or record.get("graph_entity_label")
            or record.get("entity_label")
            or ""
        ).strip().casefold()
        if label not in labels:
            return False
    return True
