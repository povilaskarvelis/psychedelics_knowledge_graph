#!/usr/bin/env python3
"""Export curated claim datasets into deterministic graph payloads."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]

DATASET_CONFIG = {
    "mechanistic": {
        "curated_json": ROOT / "data" / "curated" / "claims.json",
        "schema": ROOT / "schema" / "claims.schema.json",
        "template": "Psychedelics: Mechanistic Targets",
        "all_evidence_file": "graph_payload_mechanistic.json",
        "primary_only_file": "graph_payload_mechanistic_primary_only.json",
        "id_fields": [
            "compound",
            "target",
            "study_doi",
            "openalex_id",
            "assay_type",
            "affinity_type",
            "affinity_value",
            "affinity_unit",
            "evidence_locator",
        ],
    },
    "disorder": {
        "curated_json": ROOT / "data" / "curated" / "disorder_claims.json",
        "schema": ROOT / "schema" / "disorder_claims.schema.json",
        "template": "Psychedelics: Disorder Outcomes",
        "all_evidence_file": "graph_payload_disorder.json",
        "primary_only_file": "graph_payload_disorder_primary_only.json",
        "id_fields": [
            "compound",
            "disorder",
            "study_doi",
            "openalex_id",
            "outcome_type",
            "outcome_measure",
            "evidence_locator",
        ],
    },
}

VIEW_NAMES = ("all_evidence", "primary_only")


def normalize(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json_array(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return data


def load_schema(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_schema(schema: dict) -> Tuple[List[str], Dict[str, Set[str]], Dict[str, str], List[Set[str]], Set[str]]:
    item = schema["items"]
    required = list(item.get("required", []))
    properties = item.get("properties", {})

    enums: Dict[str, Set[str]] = {}
    types: Dict[str, str] = {}
    for key, prop in properties.items():
        if "enum" in prop:
            enums[key] = set(prop["enum"])
        if "type" in prop:
            types[key] = prop["type"]

    one_of_groups: List[Set[str]] = []
    for group in item.get("oneOf", []):
        if isinstance(group, dict) and "required" in group:
            one_of_groups.append(set(group["required"]))

    return required, enums, types, one_of_groups, set(properties.keys())


def validate_row(
    row: dict,
    row_idx: int,
    required: List[str],
    enums: Dict[str, Set[str]],
    types: Dict[str, str],
    one_of_groups: List[Set[str]],
    allowed_keys: Set[str],
) -> List[str]:
    errors: List[str] = []

    cleaned = {key: row.get(key, "") for key in allowed_keys}

    for field in required:
        if normalize(cleaned.get(field, "")) == "":
            errors.append(f"row {row_idx}: missing required field `{field}`")

    if one_of_groups:
        any_group_satisfied = any(
            any(normalize(cleaned.get(field, "")) for field in group)
            for group in one_of_groups
        )
        if not any_group_satisfied:
            group_names = ["|".join(sorted(group)) for group in one_of_groups]
            errors.append(f"row {row_idx}: requires one of {group_names}")

    for field, allowed in enums.items():
        value = normalize(cleaned.get(field, ""))
        if value and value not in allowed:
            errors.append(f"row {row_idx}: invalid enum `{field}` value `{value}`")

    for field, type_name in types.items():
        value = normalize(cleaned.get(field, ""))
        if value == "":
            continue
        if type_name == "integer":
            try:
                int(float(value))
            except Exception:
                errors.append(f"row {row_idx}: invalid integer `{field}` value `{value}`")
        elif type_name == "number":
            try:
                float(value)
            except Exception:
                errors.append(f"row {row_idx}: invalid number `{field}` value `{value}`")

    return errors


def canonical_string(row: dict, id_fields: List[str]) -> str:
    return "|".join(f"{field}={normalize(row.get(field, ''))}" for field in id_fields)


def external_id(dataset: str, row: dict, id_fields: List[str]) -> str:
    digest = hashlib.sha1(canonical_string(row, id_fields).encode("utf-8")).hexdigest()[:16]
    prefix = "mech" if dataset == "mechanistic" else "dis"
    return f"{prefix}-{digest}"


def as_int(value) -> int | str:
    text = normalize(value)
    if text == "":
        return ""
    return int(float(text))


def as_float(value) -> float | str:
    text = normalize(value)
    if text == "":
        return ""
    return float(text)


def make_mechanistic_contribution(row: dict, id_fields: List[str], template: str) -> dict:
    return {
        "external_id": external_id("mechanistic", row, id_fields),
        "template": template,
        "paper": {
            "doi": normalize(row.get("study_doi", "")),
            "openalex_id": normalize(row.get("openalex_id", "")),
            "title": normalize(row.get("study_title", "")),
            "authors": normalize(row.get("authors", "")),
            "year": as_int(row.get("study_year", "")),
        },
        "resources": {
            "compound": normalize(row.get("compound", "")),
            "target": normalize(row.get("target", "")),
        },
        "properties": {
            "assay_type": normalize(row.get("assay_type", "")),
            "affinity_type": normalize(row.get("affinity_type", "")),
            "affinity_value": as_float(row.get("affinity_value", "")),
            "affinity_unit": normalize(row.get("affinity_unit", "")),
            "species": normalize(row.get("species", "")),
            "system": normalize(row.get("system", "")),
            "evidence_level": normalize(row.get("evidence_level", "")),
            "source": normalize(row.get("source", "")),
        },
        "provenance": {
            "paper_type": normalize(row.get("paper_type", "")),
            "source_type": normalize(row.get("source_type", "")),
            "access_level": normalize(row.get("access_level", "")),
            "evidence_location": normalize(row.get("evidence_location", "")),
            "evidence_locator": normalize(row.get("evidence_locator", "")),
            "study_design": normalize(row.get("study_design", "")),
            "notes": normalize(row.get("notes", "")),
        },
    }


def make_disorder_contribution(row: dict, id_fields: List[str], template: str) -> dict:
    return {
        "external_id": external_id("disorder", row, id_fields),
        "template": template,
        "paper": {
            "doi": normalize(row.get("study_doi", "")),
            "openalex_id": normalize(row.get("openalex_id", "")),
            "title": normalize(row.get("study_title", "")),
            "authors": normalize(row.get("authors", "")),
            "year": as_int(row.get("study_year", "")),
        },
        "resources": {
            "compound": normalize(row.get("compound", "")),
            "disorder": normalize(row.get("disorder", "")),
        },
        "properties": {
            "outcome_type": normalize(row.get("outcome_type", "")),
            "result_direction": normalize(row.get("result_direction", "")),
            "outcome_measure": normalize(row.get("outcome_measure", "")),
            "population": normalize(row.get("population", "")),
            "system": normalize(row.get("system", "")),
            "evidence_level": normalize(row.get("evidence_level", "")),
            "source": normalize(row.get("source", "")),
        },
        "provenance": {
            "paper_type": normalize(row.get("paper_type", "")),
            "source_type": normalize(row.get("source_type", "")),
            "access_level": normalize(row.get("access_level", "")),
            "evidence_location": normalize(row.get("evidence_location", "")),
            "evidence_locator": normalize(row.get("evidence_locator", "")),
            "study_design": normalize(row.get("study_design", "")),
            "notes": normalize(row.get("notes", "")),
        },
    }


def sort_rows(dataset: str, rows: List[dict]) -> List[dict]:
    if dataset == "mechanistic":
        return sorted(
            rows,
            key=lambda r: (
                normalize(r.get("compound", "")),
                normalize(r.get("target", "")),
                normalize(r.get("study_doi", "")),
                normalize(r.get("openalex_id", "")),
                normalize(r.get("assay_type", "")),
                normalize(r.get("evidence_locator", "")),
            ),
        )
    return sorted(
        rows,
        key=lambda r: (
            normalize(r.get("compound", "")),
            normalize(r.get("disorder", "")),
            normalize(r.get("study_doi", "")),
            normalize(r.get("openalex_id", "")),
            normalize(r.get("outcome_type", "")),
            normalize(r.get("evidence_locator", "")),
        ),
    )


def rows_for_view(rows: List[dict], view: str) -> List[dict]:
    if view == "all_evidence":
        return list(rows)
    if view == "primary_only":
        return [
            row
            for row in rows
            if normalize(row.get("source_type", "")) == "primary_study"
            and normalize(row.get("paper_type", "")) == "primary_results"
            and normalize(row.get("access_level", "")) != "secondary_summary"
        ]
    raise ValueError(f"Unsupported view: {view}")


def payload_file_for_view(cfg: dict, view: str) -> str:
    if view == "all_evidence":
        return cfg["all_evidence_file"]
    if view == "primary_only":
        return cfg["primary_only_file"]
    raise ValueError(f"Unsupported view: {view}")


def contributions_for_dataset(dataset: str, rows: List[dict], cfg: dict) -> List[dict]:
    contributions: List[dict] = []
    if dataset == "mechanistic":
        for row in rows:
            contributions.append(make_mechanistic_contribution(row, cfg["id_fields"], cfg["template"]))
    else:
        for row in rows:
            contributions.append(make_disorder_contribution(row, cfg["id_fields"], cfg["template"]))
    return contributions


def payload_sha256(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def export_dataset(dataset: str, out_dir: Path) -> Tuple[dict, Dict[str, List[str]]]:
    cfg = DATASET_CONFIG[dataset]
    rows = load_json_array(cfg["curated_json"])
    schema = load_schema(cfg["schema"])
    required, enums, types, one_of_groups, allowed_keys = parse_schema(schema)

    sorted_rows = sort_rows(dataset, rows)
    view_exports: dict = {}
    errors_by_view: Dict[str, List[str]] = {}

    for view in VIEW_NAMES:
        selected_rows = rows_for_view(sorted_rows, view=view)
        errors: List[str] = []
        for idx, row in enumerate(selected_rows, start=1):
            errors.extend(
                validate_row(
                    row=row,
                    row_idx=idx,
                    required=required,
                    enums=enums,
                    types=types,
                    one_of_groups=one_of_groups,
                    allowed_keys=allowed_keys,
                )
            )

        contributions = contributions_for_dataset(dataset=dataset, rows=selected_rows, cfg=cfg)
        payload = {
            "contract_version": "1.0",
            "dataset": dataset,
            "evidence_view": view,
            "template": cfg["template"],
            "input_file": str(cfg["curated_json"]),
            "row_count": len(contributions),
            "contributions": contributions,
        }

        out_file = out_dir / payload_file_for_view(cfg, view=view)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        view_exports[view] = {
            "payload": payload,
            "output_file": str(out_file),
            "row_count": payload["row_count"],
            "sha256": payload_sha256(payload),
        }
        errors_by_view[view] = errors

    return view_exports, errors_by_view


def main() -> int:
    parser = argparse.ArgumentParser(description="Export graph payload JSON from curated datasets")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder", "all"], default="all")
    parser.add_argument(
        "--out-dir",
        default=str(ROOT / "data" / "processed"),
        help="Output directory for graph payload files",
    )
    parser.add_argument(
        "--manifest",
        default="graph_payload_manifest.json",
        help="Manifest filename written to --out-dir",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    datasets = ["mechanistic", "disorder"] if args.dataset == "all" else [args.dataset]

    manifest = {
        "generated_at": now_utc(),
        "contract_version": "1.0",
        "datasets": {},
        "status": "ok",
        "errors": [],
    }

    for dataset in datasets:
        views, errors_by_view = export_dataset(dataset, out_dir)
        manifest["datasets"][dataset] = {
            "output_file": views["all_evidence"]["output_file"],
            "row_count": views["all_evidence"]["row_count"],
            "sha256": views["all_evidence"]["sha256"],
            "views": {
                view: {
                    "output_file": info["output_file"],
                    "row_count": info["row_count"],
                    "sha256": info["sha256"],
                }
                for view, info in views.items()
            },
        }
        dataset_errors = []
        for view, errors in errors_by_view.items():
            if errors:
                dataset_errors.append({"view": view, "messages": errors})
        if dataset_errors:
            manifest["status"] = "failed"
            manifest["errors"].append(
                {
                    "dataset": dataset,
                    "messages": [msg for item in dataset_errors for msg in item["messages"]],
                    "views": dataset_errors,
                }
            )

    manifest_path = out_dir / args.manifest
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Datasets: {', '.join(datasets)}")
    for dataset in datasets:
        info = manifest["datasets"][dataset]
        print(f"- {dataset}:")
        for view in VIEW_NAMES:
            view_info = info["views"][view]
            print(f"  - {view}: {view_info['row_count']} rows -> {view_info['output_file']}")
    print(f"Manifest: {manifest_path}")
    print(f"Status: {manifest['status']}")

    return 1 if manifest["status"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
