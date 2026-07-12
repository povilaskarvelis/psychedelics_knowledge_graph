#!/usr/bin/env python3
"""Project paper relationship bundles without dropping or flattening anchors.

The projection is isolated and review-specific. It preserves every raw anchor,
normalizes known entities when possible, and uses a relationship node whenever
an atomic edge would lose class, combination, interaction, or context meaning.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
import re
from pathlib import Path
import sys

try:
    from pipeline.extract.io_utils import normalize, read_jsonl, write_json
except ModuleNotFoundError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.io_utils import normalize, read_jsonl, write_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = (
    ROOT
    / "data"
    / "processed"
    / "extraction"
    / "review_relationship_runs"
    / "review_relationships_v2"
    / "paper_relationship_bundles.jsonl"
)
DEFAULT_REGISTRY = ROOT / "data" / "curated" / "entity_registry.json"
RELATIONSHIP_NODE_FORMS = {"combination", "interaction", "context", "paper_topic"}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def label_key(value: object) -> str:
    text = normalize(value).casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def registry_index(registry: dict) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for category in ("compounds", "targets", "disorders"):
        for item in registry.get(category, []):
            if not isinstance(item, dict):
                continue
            canonical = normalize(item.get("label", ""))
            if not canonical:
                continue
            for label in [canonical, *item.get("aliases", [])]:
                key = label_key(label)
                if key:
                    out[(category, key)] = canonical
    return out


def registry_categories_for_role(role: str) -> tuple[str, ...]:
    if role in {"compound", "intervention", "co_intervention", "comparator"}:
        return ("compounds",)
    if role == "target":
        return ("targets",)
    if role == "condition":
        return ("disorders",)
    return ()


def normalize_anchor(anchor: dict, registry: dict[tuple[str, str], str]) -> dict:
    raw_label = normalize(anchor.get("label", ""))
    role = normalize(anchor.get("role", ""))
    anchor_type = normalize(anchor.get("anchor_type", ""))
    canonical = ""
    for category in registry_categories_for_role(role):
        canonical = registry.get((category, label_key(raw_label)), "")
        if canonical:
            break
    if canonical:
        status = "registry_normalized"
    elif anchor_type == "compound_class" or role == "compound_class":
        canonical = raw_label
        status = "class_preserved"
    else:
        canonical = raw_label
        status = "provisional_preserved"
    return {
        "role": role,
        "anchor_type": anchor_type,
        "raw_label": raw_label,
        "normalized_label": canonical,
        "normalization_status": status,
    }


def projection_mode(relationship: dict) -> str:
    form = normalize(relationship.get("graph_form", ""))
    anchors = [anchor for anchor in relationship.get("anchors", []) if isinstance(anchor, dict)]
    if form in RELATIONSHIP_NODE_FORMS or len(anchors) != 2:
        return "relationship_node"
    return "lossless_edge_candidate"


def project_bundle_row(row: dict, registry: dict[tuple[str, str], str]) -> tuple[list[dict], list[dict]]:
    if normalize(row.get("status", "")) != "ok":
        return [], []
    result = row.get("result", {}) if isinstance(row.get("result"), dict) else {}
    doi = normalize(row.get("study_doi", "")).lower()
    relationship_rows: list[dict] = []
    anchor_rows: list[dict] = []
    for relationship in result.get("relationships", []) if isinstance(result.get("relationships"), list) else []:
        if not isinstance(relationship, dict):
            continue
        item_id = normalize(relationship.get("item_id", ""))
        anchors = [anchor for anchor in relationship.get("anchors", []) if isinstance(anchor, dict)]
        normalized_anchors = [normalize_anchor(anchor, registry) for anchor in anchors]
        prominence = normalize(relationship.get("paper_prominence", ""))
        requested_eligibility = normalize(relationship.get("graph_eligibility", ""))
        admitted_to_main_graph = requested_eligibility == "main_graph" and prominence in {
            "paper_defining",
            "major_supporting",
        }
        relationship_rows.append(
            {
                "study_doi": doi,
                "study_title": normalize(row.get("study_title", "")),
                "source_depth": normalize(row.get("text_depth", "")),
                "relationship_id": item_id,
                "relationship_kind": normalize(relationship.get("relationship_kind", "")),
                "relationship_statement": normalize(relationship.get("relationship_statement", "")),
                "relation_phrase": normalize(relationship.get("relation_phrase", "")),
                "direction_or_tone": normalize(relationship.get("direction_or_tone", "")),
                "evidence_status": normalize(relationship.get("evidence_status", "")),
                "paper_prominence": prominence,
                "graph_eligibility": requested_eligibility,
                "admitted_to_main_graph": admitted_to_main_graph,
                "admission_status": "main_graph" if admitted_to_main_graph else "paper_detail_only",
                "graph_form": normalize(relationship.get("graph_form", "")),
                "projection_mode": projection_mode(relationship),
                "domain_labels": relationship.get("domain_labels", []),
                "anchors": normalized_anchors,
                "anchor_count": len(anchors),
                "semantic_integrity": "preserved" if len(normalized_anchors) == len(anchors) else "error",
            }
        )
        for position, anchor in enumerate(normalized_anchors, start=1):
            anchor_rows.append(
                {
                    "study_doi": doi,
                    "relationship_id": item_id,
                    "anchor_position": position,
                    **anchor,
                }
            )
    return relationship_rows, anchor_rows


def project_bundles(rows: list[dict], registry_payload: dict) -> tuple[list[dict], list[dict], dict]:
    registry = registry_index(registry_payload)
    relationships: list[dict] = []
    anchors: list[dict] = []
    for row in rows:
        relationship_rows, anchor_rows = project_bundle_row(row, registry)
        relationships.extend(relationship_rows)
        anchors.extend(anchor_rows)
    main = [row for row in relationships if row["admitted_to_main_graph"]]
    report = {
        "schema_version": "review_relationship_projection_report_v2",
        "generated_at_utc": now_utc(),
        "counts": {
            "bundle_rows": len(rows),
            "relationships": len(relationships),
            "main_graph_relationships": len(main),
            "model_main_graph_rejected_by_prominence": sum(
                row["graph_eligibility"] == "main_graph" and not row["admitted_to_main_graph"]
                for row in relationships
            ),
            "anchors": len(anchors),
            "relationships_with_all_anchors_preserved": sum(
                row["semantic_integrity"] == "preserved" for row in relationships
            ),
            "anchors_preserved": len(anchors),
            "papers_with_main_graph_relationships": len({row["study_doi"] for row in main}),
        },
        "by_graph_form": dict(Counter(row["graph_form"] for row in main)),
        "by_projection_mode": dict(Counter(row["projection_mode"] for row in main)),
        "by_anchor_normalization_status": dict(Counter(row["normalization_status"] for row in anchors)),
    }
    return relationships, anchors, report


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-jsonl", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--registry-json", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--out-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = args.out_dir or args.input_jsonl.parent / "projection"
    rows = read_jsonl(args.input_jsonl)
    registry = json.loads(args.registry_json.read_text(encoding="utf-8"))
    relationships, anchors, report = project_bundles(rows, registry)
    relationship_path = out_dir / "review_relationships.jsonl"
    anchor_path = out_dir / "review_relationship_anchors.jsonl"
    report_path = out_dir / "projection_report.json"
    write_jsonl(relationship_path, relationships)
    write_jsonl(anchor_path, anchors)
    report["outputs"] = {
        "relationships_jsonl": str(relationship_path.resolve()),
        "anchors_jsonl": str(anchor_path.resolve()),
        "report_json": str(report_path.resolve()),
    }
    write_json(report_path, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
