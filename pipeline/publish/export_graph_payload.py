#!/usr/bin/env python3
"""Export graph-claim datasets into deterministic main-page graph payloads."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CLAIM_SOURCE = "gemini_extraction"
LEGACY_MECHANISTIC_SCHEMA = ROOT / "schema" / "legacy_mechanistic_affinity_claims.schema.json"
LEGACY_DISORDER_SCHEMA = ROOT / "schema" / "legacy_disorder_claims.schema.json"

CLAIM_SOURCES = {
    "gemini_extraction": {
        "label": "Gemini extraction-v1 projected claims",
        "mechanistic": {
            "claims_json": ROOT / "data" / "processed" / "extraction" / "mechanistic_claims.json",
            "secondary_json": ROOT / "data" / "processed" / "extraction" / "mechanistic_secondary_claims.json",
        },
        "disorder": {
            "claims_json": ROOT / "data" / "processed" / "extraction" / "disorder_claims.json",
            "secondary_json": ROOT / "data" / "processed" / "extraction" / "disorder_secondary_claims.json",
        },
    },
    "gemini_normalized": {
        "label": "Gemini extraction-v1 normalized graph claims",
        "mechanistic": {
            "claims_json": ROOT / "data" / "processed" / "extraction" / "mechanistic_graph_claims.json",
            "secondary_json": ROOT / "data" / "processed" / "extraction" / "mechanistic_secondary_graph_claims.json",
        },
        "disorder": {
            "claims_json": ROOT / "data" / "processed" / "extraction" / "disorder_graph_claims.json",
            "secondary_json": ROOT / "data" / "processed" / "extraction" / "disorder_secondary_graph_claims.json",
        },
    },
    "legacy_curated": {
        "label": "Legacy heuristic curated claims",
        "mechanistic": {
            "claims_json": ROOT / "data" / "curated" / "claims.json",
            "secondary_json": ROOT / "data" / "curated" / "exploratory_claims.json",
        },
        "disorder": {
            "claims_json": ROOT / "data" / "curated" / "disorder_claims.json",
            "secondary_json": ROOT / "data" / "curated" / "exploratory_disorder_claims.json",
        },
    },
}

DATASET_CONFIG = {
    "mechanistic": {
        "schema": ROOT / "schema" / "claims.schema.json",
        "template": "Psychedelics: Mechanistic Targets",
        "all_evidence_file": "graph_payload_mechanistic.json",
        "primary_only_file": "graph_payload_mechanistic_primary_only.json",
        "secondary_sources_file": "graph_payload_mechanistic_secondary_sources.json",
        "primary_with_secondary_file": "graph_payload_mechanistic_primary_with_secondary.json",
        "id_fields": [
            "claim_type",
            "compound",
            "target",
            "study_doi",
            "openalex_id",
            "mechanism_type",
            "assay_type",
            "assay_family",
            "action_type",
            "affinity_type",
            "affinity_value",
            "affinity_unit",
            "model_or_system",
            "evidence_locator",
            "supporting_quote",
        ],
    },
    "disorder": {
        "schema": ROOT / "schema" / "disorder_claims.schema.json",
        "template": "Psychedelics: Disorder Outcomes",
        "all_evidence_file": "graph_payload_disorder.json",
        "primary_only_file": "graph_payload_disorder_primary_only.json",
        "secondary_sources_file": "graph_payload_disorder_secondary_sources.json",
        "primary_with_secondary_file": "graph_payload_disorder_primary_with_secondary.json",
        "id_fields": [
            "claim_type",
            "compound",
            "disorder",
            "study_doi",
            "openalex_id",
            "outcome_type",
            "outcome_measure",
            "result_direction",
            "timepoint",
            "evidence_locator",
            "supporting_quote",
        ],
    },
}

VIEW_NAMES = ("all_evidence", "primary_only", "secondary_sources", "primary_with_secondary")
PRIMARY_SOURCE_TYPES = {"primary_study"}
PRIMARY_PAPER_TYPES = {"primary_results"}
SECONDARY_SOURCE_FAMILIES = {"evidence_synthesis"}
SECONDARY_SOURCE_TYPES = {"secondary_evidence", "review", "meta_analysis"}
SECONDARY_PAPER_TYPES = {"systematic_review", "meta_analysis", "review"}
PAPER_METADATA_FIELDS = (
    "publication_date",
    "journal_issn",
    "journal_eissn",
    "publisher",
    "mesh_terms",
    "keywords",
    "funders",
    "grant_ids",
    "related_dois",
    "publication_relations",
    "is_retracted",
    "has_correction",
    "language",
    "semantic_scholar_id",
)
EXTRACTED_VARIABLE_FIELDS = (
    "claim_type",
    "raw_entity_label",
    "entity_role",
    "clinical_context_condition",
    "graph_entity_label",
    "graph_entity_type",
    "graph_include_candidate",
    "graph_exclusion_reason",
    "mechanism_type",
    "assay_family",
    "action_type",
    "model_or_system",
    "support",
    "confidence",
    "needs_human_review",
    "supporting_quote",
    "paper_assessment_route",
    "normalization_status",
    "normalization_notes",
    "canonical_compound",
    "canonical_entity",
    "compound_original",
    "target_original",
    "disorder_original",
    "graph_entity_original",
    "compound_match_type",
    "entity_match_type",
    "compound_registry_status",
    "entity_registry_status",
    "compound_ids",
    "entity_ids",
    "sample_size_total",
    "sample_size_by_arm",
    "included_study_count",
    "included_participant_count",
    "search_databases",
    "synthesis_method",
    "heterogeneity",
    "publication_bias_assessment",
    "population_or_condition",
    "participant_age",
    "participant_sex_gender",
    "study_setting",
    "country_or_region",
    "comparator",
    "intervention_or_exposure",
    "dose",
    "route",
    "session_count_or_duration",
    "trial_phase",
    "randomization",
    "blinding",
    "follow_up_duration",
    "primary_outcome",
    "outcome_measure",
    "outcome_measure_normalized",
    "timepoint",
    "effect_size",
    "effect_direction",
    "p_value",
    "confidence_interval",
    "adverse_events",
    "serious_adverse_events",
    "trial_registry_ids",
    "funding",
    "conflicts_of_interest",
    "risk_of_bias_notes",
    "risk_of_bias_summary",
)


def normalize(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json_array(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return data


def claim_source_paths(dataset: str, claim_source: str) -> dict:
    source = CLAIM_SOURCES[claim_source]
    paths = source[dataset]
    return {
        "claim_source": claim_source,
        "claim_source_label": source["label"],
        "claims_json": paths["claims_json"],
        "secondary_json": paths["secondary_json"],
    }


def schema_path_for_claim_source(dataset: str, claim_source: str, cfg: dict) -> Path:
    if dataset == "mechanistic" and claim_source == "legacy_curated":
        return LEGACY_MECHANISTIC_SCHEMA
    if dataset == "disorder" and claim_source == "legacy_curated":
        return LEGACY_DISORDER_SCHEMA
    return cfg["schema"]


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
                if not is_secondary_literature_row(cleaned):
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
    try:
        return float(text)
    except ValueError:
        return text


def extracted_variables(row: dict) -> dict:
    out = {}
    for field in EXTRACTED_VARIABLE_FIELDS:
        value = row.get(field, "")
        if normalize(value):
            out[field] = normalize(value)
    return out


def is_primary_graph_row(row: dict) -> bool:
    if (
        normalize(row.get("paper_assessment_route", "")) == "primary_evidence"
        and normalize(row.get("access_level", "")) != "secondary_summary"
    ):
        return True
    return (
        normalize(row.get("source_type", "")) in PRIMARY_SOURCE_TYPES
        and normalize(row.get("paper_type", "")) in PRIMARY_PAPER_TYPES
        and normalize(row.get("access_level", "")) != "secondary_summary"
    )


def is_secondary_literature_row(row: dict) -> bool:
    return (
        normalize(row.get("source_family", "")) in SECONDARY_SOURCE_FAMILIES
        or normalize(row.get("source_type", "")) in SECONDARY_SOURCE_TYPES
        or normalize(row.get("paper_type", "")) in SECONDARY_PAPER_TYPES
    )


def evidence_role_for_row(row: dict) -> str:
    if is_primary_graph_row(row):
        return "primary_evidence"
    if is_secondary_literature_row(row):
        return "secondary_literature"
    return "non_primary_context"


def dedupe_rows(rows: List[dict], id_fields: List[str]) -> List[dict]:
    seen: Set[str] = set()
    out: List[dict] = []
    for row in rows:
        key = canonical_string(row, id_fields)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def paper_metadata(row: dict) -> dict:
    out = {
        "doi": normalize(row.get("study_doi", "")),
        "openalex_id": normalize(row.get("openalex_id", "")),
        "title": normalize(row.get("study_title", "")),
        "journal": normalize(row.get("study_journal", "")),
        "publication_type": normalize(row.get("publication_type", "")),
        "trial_registry_ids": normalize(row.get("trial_registry_ids", "")),
        "authors": normalize(row.get("authors", "")),
        "year": as_int(row.get("study_year", "")),
    }
    for field in PAPER_METADATA_FIELDS:
        value = normalize(row.get(field, ""))
        if value:
            out[field] = value
    return out


def make_mechanistic_contribution(row: dict, id_fields: List[str], template: str) -> dict:
    return {
        "external_id": external_id("mechanistic", row, id_fields),
        "template": template,
        "paper": paper_metadata(row),
        "resources": {
            "compound": normalize(row.get("compound", "")),
            "target": normalize(row.get("target", "")),
        },
        "properties": {
            "claim_type": normalize(row.get("claim_type", "")),
            "raw_entity_label": normalize(row.get("raw_entity_label", "")),
            "entity_role": normalize(row.get("entity_role", "")),
            "clinical_context_condition": normalize(row.get("clinical_context_condition", "")),
            "graph_entity_label": normalize(row.get("graph_entity_label", "")),
            "graph_entity_type": normalize(row.get("graph_entity_type", "")),
            "graph_include_candidate": row.get("graph_include_candidate") is True,
            "graph_exclusion_reason": normalize(row.get("graph_exclusion_reason", "")),
            "mechanism_type": normalize(row.get("mechanism_type", "")),
            "assay_type": normalize(row.get("assay_type", "")),
            "assay_family": normalize(row.get("assay_family", "")),
            "action_type": normalize(row.get("action_type", "")),
            "affinity_type": normalize(row.get("affinity_type", "")),
            "affinity_value": as_float(row.get("affinity_value", "")),
            "affinity_unit": normalize(row.get("affinity_unit", "")),
            "result_direction": normalize(row.get("result_direction", "")),
            "species": normalize(row.get("species", "")),
            "model_or_system": normalize(row.get("model_or_system", "")),
            "system": normalize(row.get("system", "")),
            "evidence_level": normalize(row.get("evidence_level", "")),
            "support": normalize(row.get("support", "")),
            "confidence": as_float(row.get("confidence", "")),
            "needs_human_review": row.get("needs_human_review") is True,
            "source": normalize(row.get("source", "")),
        },
        "extracted_variables": extracted_variables(row),
        "provenance": {
            "paper_type": normalize(row.get("paper_type", "")),
            "source_type": normalize(row.get("source_type", "")),
            "source_family": normalize(row.get("source_family", "")),
            "paper_assessment_route": normalize(row.get("paper_assessment_route", "")),
            "evidence_role": evidence_role_for_row(row),
            "access_level": normalize(row.get("access_level", "")),
            "source_access_level": normalize(row.get("source_access_level", "")) or normalize(row.get("access_level", "")),
            "evidence_location": normalize(row.get("evidence_location", "")),
            "evidence_locator": normalize(row.get("evidence_locator", "")),
            "study_design": normalize(row.get("study_design", "")),
            "evidence_strength": normalize(row.get("evidence_strength", "")),
            "notes": normalize(row.get("notes", "")),
        },
    }


def make_disorder_contribution(row: dict, id_fields: List[str], template: str) -> dict:
    return {
        "external_id": external_id("disorder", row, id_fields),
        "template": template,
        "paper": paper_metadata(row),
        "resources": {
            "compound": normalize(row.get("compound", "")),
            "disorder": normalize(row.get("disorder", "")),
        },
        "properties": {
            "claim_type": normalize(row.get("claim_type", "")),
            "raw_entity_label": normalize(row.get("raw_entity_label", "")),
            "entity_role": normalize(row.get("entity_role", "")),
            "clinical_context_condition": normalize(row.get("clinical_context_condition", "")),
            "graph_entity_label": normalize(row.get("graph_entity_label", "")),
            "graph_entity_type": normalize(row.get("graph_entity_type", "")),
            "graph_include_candidate": row.get("graph_include_candidate") is True,
            "graph_exclusion_reason": normalize(row.get("graph_exclusion_reason", "")),
            "outcome_type": normalize(row.get("outcome_type", "")),
            "outcome_domain": normalize(row.get("outcome_domain", "")),
            "result_direction": normalize(row.get("result_direction", "")),
            "outcome_measure": normalize(row.get("outcome_measure", "")),
            "outcome_measure_normalized": normalize(row.get("outcome_measure_normalized", "")),
            "population": normalize(row.get("population", "")),
            "system": normalize(row.get("system", "")),
            "evidence_level": normalize(row.get("evidence_level", "")),
            "support": normalize(row.get("support", "")),
            "confidence": as_float(row.get("confidence", "")),
            "needs_human_review": row.get("needs_human_review") is True,
            "source": normalize(row.get("source", "")),
        },
        "extracted_variables": extracted_variables(row),
        "provenance": {
            "paper_type": normalize(row.get("paper_type", "")),
            "source_type": normalize(row.get("source_type", "")),
            "source_family": normalize(row.get("source_family", "")),
            "paper_assessment_route": normalize(row.get("paper_assessment_route", "")),
            "evidence_role": evidence_role_for_row(row),
            "access_level": normalize(row.get("access_level", "")),
            "source_access_level": normalize(row.get("source_access_level", "")) or normalize(row.get("access_level", "")),
            "evidence_location": normalize(row.get("evidence_location", "")),
            "evidence_locator": normalize(row.get("evidence_locator", "")),
            "study_design": normalize(row.get("study_design", "")),
            "evidence_strength": normalize(row.get("evidence_strength", "")),
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


def rows_for_view(rows: List[dict], view: str, secondary_rows: List[dict] | None = None, id_fields: List[str] | None = None) -> List[dict]:
    secondary = list(secondary_rows or [])
    if view == "all_evidence":
        return list(rows)
    if view == "primary_only":
        return [row for row in rows if is_primary_graph_row(row)]
    if view == "secondary_sources":
        return secondary
    if view == "primary_with_secondary":
        primary_rows = [row for row in rows if is_primary_graph_row(row)]
        if not id_fields:
            return primary_rows + secondary
        primary_keys = {canonical_string(row, id_fields) for row in primary_rows}
        secondary_unique = [row for row in secondary if canonical_string(row, id_fields) not in primary_keys]
        return primary_rows + secondary_unique
    raise ValueError(f"Unsupported view: {view}")


def payload_file_for_view(cfg: dict, view: str) -> str:
    if view == "all_evidence":
        return cfg["all_evidence_file"]
    if view == "primary_only":
        return cfg["primary_only_file"]
    if view == "secondary_sources":
        return cfg["secondary_sources_file"]
    if view == "primary_with_secondary":
        return cfg["primary_with_secondary_file"]
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


def export_dataset(dataset: str, out_dir: Path, claim_source: str = DEFAULT_CLAIM_SOURCE) -> Tuple[dict, Dict[str, List[str]]]:
    cfg = DATASET_CONFIG[dataset]
    source_paths = claim_source_paths(dataset, claim_source)
    rows = load_json_array(source_paths["claims_json"])
    exploratory_rows = load_json_array(source_paths["secondary_json"])
    schema = load_schema(schema_path_for_claim_source(dataset, claim_source, cfg))
    required, enums, types, one_of_groups, allowed_keys = parse_schema(schema)

    sorted_rows = sort_rows(dataset, rows)
    secondary_rows = sort_rows(
        dataset,
        dedupe_rows(
            [row for row in [*rows, *exploratory_rows] if is_secondary_literature_row(row)],
            cfg["id_fields"],
        ),
    )
    view_exports: dict = {}
    errors_by_view: Dict[str, List[str]] = {}

    for view in VIEW_NAMES:
        selected_rows = rows_for_view(
            sorted_rows,
            view=view,
            secondary_rows=secondary_rows,
            id_fields=cfg["id_fields"],
        )
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
            "claim_source": source_paths["claim_source"],
            "claim_source_label": source_paths["claim_source_label"],
            "input_file": str(source_paths["claims_json"]),
            "secondary_source_file": str(source_paths["secondary_json"]),
            "view_policy": {
                "primary_evidence": view in {"all_evidence", "primary_only", "primary_with_secondary"},
                "secondary_literature": view in {"all_evidence", "secondary_sources", "primary_with_secondary"},
                "other_non_primary_context": view == "all_evidence",
            },
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
    parser.add_argument(
        "--claim-source",
        choices=sorted(CLAIM_SOURCES),
        default=DEFAULT_CLAIM_SOURCE,
        help="Claim source for main graph payloads. Default uses projected Gemini extraction claims.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    datasets = ["mechanistic", "disorder"] if args.dataset == "all" else [args.dataset]

    manifest = {
        "generated_at": now_utc(),
        "contract_version": "1.0",
        "claim_source": args.claim_source,
        "claim_source_label": CLAIM_SOURCES[args.claim_source]["label"],
        "datasets": {},
        "status": "ok",
        "errors": [],
    }

    for dataset in datasets:
        views, errors_by_view = export_dataset(dataset, out_dir, claim_source=args.claim_source)
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
