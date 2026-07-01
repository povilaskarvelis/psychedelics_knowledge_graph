#!/usr/bin/env python3
"""Export route-native evidence findings for the web UI."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]

try:
    from pipeline.extract.clinical_comparator import normalize_clinical_comparator
    from pipeline.extract.clinical_followup_window import normalize_clinical_followup_window
    from pipeline.extract.mechanistic_assay_family import normalize_mechanistic_assay_family
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(ROOT))
    from pipeline.extract.clinical_comparator import normalize_clinical_comparator
    from pipeline.extract.clinical_followup_window import normalize_clinical_followup_window
    from pipeline.extract.mechanistic_assay_family import normalize_mechanistic_assay_family


DEFAULT_KG_DIR = ROOT / "data" / "processed" / "kg"
DEFAULT_OUT_DIR = ROOT / "data" / "processed"
DEFAULT_ACTIVE_JSON = ROOT / "data" / "processed" / "graph_payload_active.json"
ROUTED_SOURCE_NAME = "routed_extractions"
ROUTED_SOURCE_NAMES = {ROUTED_SOURCE_NAME, "routed_clinical_endpoints"}
SCHEMA_VERSION = "route_native_evidence_payload_v1"
ACTIVE_SCHEMA_VERSION = "route_native_evidence_payload_active_v1"
MANIFEST_SCHEMA_VERSION = "route_native_evidence_manifest_v1"

PAPER_FIELDS = (
    "study_doi",
    "openalex_id",
    "study_title",
    "authors",
    "study_year",
    "study_journal",
    "publication_type",
    "publication_date",
    "publisher",
    "journal_issn",
    "journal_eissn",
    "language",
    "mesh_terms",
    "keywords",
    "funders",
    "grant_ids",
    "related_dois",
    "publication_relations",
    "is_retracted",
    "has_correction",
    "open_access_is_oa",
    "open_access_status",
    "open_access_url",
    "unpaywall_is_oa",
    "unpaywall_oa_status",
    "unpaywall_license",
)

FINDING_FIELDS = (
    "raw_entity_label",
    "entity_role",
    "clinical_context_condition",
    "graph_entity_label",
    "graph_entity_type",
    "graph_exclusion_reason",
    "mechanism_type",
    "assay_type",
    "assay_family",
    "assay_family_normalized",
    "modality",
    "modality_or_evidence_type",
    "readout",
    "readout_or_measure",
    "action_type",
    "affinity_type",
    "affinity_value",
    "affinity_unit",
    "species",
    "model_or_system",
    "system",
    "outcome_type",
    "outcome_domain",
    "result_direction",
    "outcome_measure",
    "outcome_measure_normalized",
    "population",
    "sample_size_total",
    "sample_size_by_arm",
    "comparator",
    "comparator_normalized",
    "follow_up_duration",
    "follow_up_window_normalized",
    "intervention_or_exposure",
    "condition_or_indication",
    "population_or_subgroup",
    "population_model_category",
    "study_design_category",
    "administration_route",
    "dosing_schedule",
    "session_context",
    "graph_construct_label",
    "construct_family",
    "raw_task_or_measure",
    "cognitive_behavioral_graph_label",
    "subjective_experience_graph_label",
    "public_health_graph_label",
    "molecular_effect_label",
    "molecular_effect_category",
    "specific_readout_or_marker",
    "mechanistic_relationship_type",
    "public_health_topic_category",
    "public_health_measure",
    "data_source_type",
    "exposure_or_policy",
    "exposure_or_intervention",
    "setting",
    "estimate_value",
    "estimate_unit",
    "association_or_trend",
    "time_window",
    "data_source_or_study_design",
    "comparison_or_reference_group",
    "policy_or_practice_implication",
    "compound_or_analyte",
    "primary_graph_anchor_kind",
    "pharmacokinetic_display_label",
    "pk_relationship_type",
    "pk_relationship_label",
    "pk_graph_object_kind",
    "pk_graph_object_label",
    "analyte_type",
    "metabolite_or_analyte",
    "matrix",
    "matrix_or_sample_type",
    "pk_or_exposure_parameter",
    "value",
    "unit",
    "route_of_administration",
    "sampling_time_or_window",
    "study_design",
    "dose_standardization_or_equivalence",
    "comparator_or_reference",
    "co_exposure_or_modifier",
    "metabolic_or_transport_target",
    "metabolic_or_transport_pathway",
    "experimental_system_category",
    "model_or_method",
    "interaction_or_potentiation_context",
    "exposure_response_or_pk_effect",
    "exposure_response_implication",
    "synthesis_interpretation",
    "dose",
    "route",
    "session_count_or_duration",
    "primary_outcome",
    "effect_size",
    "p_value",
    "confidence_interval",
    "adverse_events",
    "serious_adverse_events",
    "evidence_level",
    "support",
    "confidence",
    "needs_human_review",
    "evidence_location",
    "evidence_locator",
    "paper_assessment_route",
    "source_type",
    "source_family",
    "paper_type",
    "evidence_strength",
    "notes",
    "normalization_status",
    "normalization_notes",
    "compound_original",
    "graph_entity_original",
    "compound_match_type",
    "entity_match_type",
    "compound_registry_status",
    "entity_registry_status",
    "endpoint_label_source",
)

PREVIEW_FIELDS = (
    "finding_id",
    "evidence_id",
    "paper_id",
    "domain",
    "finding_type",
    "evidence_type",
    "relation_type",
    "compound",
    "entity_label",
    "entity_kind",
    "study_doi",
    "openalex_id",
    "study_title",
    "study_year",
    "study_journal",
    "publication_type",
    "open_access_is_oa",
    "open_access_status",
    "text_depth",
    "paper_type",
    "source_type",
    "source_family",
    "paper_assessment_route",
    "study_design",
    "population",
    "sample_size_total",
    "sample_size_by_arm",
    "result_direction",
    "condition_or_indication",
    "population_or_subgroup",
    "population_model_category",
    "study_design_category",
    "administration_route",
    "dosing_schedule",
    "session_context",
    "graph_construct_label",
    "construct_family",
    "raw_task_or_measure",
    "cognitive_behavioral_graph_label",
    "subjective_experience_graph_label",
    "public_health_graph_label",
    "molecular_effect_label",
    "molecular_effect_category",
    "specific_readout_or_marker",
    "mechanistic_relationship_type",
    "public_health_topic_category",
    "public_health_measure",
    "data_source_type",
    "exposure_or_policy",
    "exposure_or_intervention",
    "setting",
    "estimate_value",
    "estimate_unit",
    "association_or_trend",
    "time_window",
    "data_source_or_study_design",
    "comparison_or_reference_group",
    "policy_or_practice_implication",
    "outcome_measure",
    "outcome_measure_normalized",
    "comparator",
    "comparator_normalized",
    "follow_up_duration",
    "follow_up_window_normalized",
    "compound_or_analyte",
    "primary_graph_anchor_kind",
    "pharmacokinetic_display_label",
    "pk_relationship_type",
    "pk_relationship_label",
    "pk_graph_object_kind",
    "pk_graph_object_label",
    "analyte_type",
    "metabolite_or_analyte",
    "matrix",
    "matrix_or_sample_type",
    "pk_or_exposure_parameter",
    "value",
    "unit",
    "route_of_administration",
    "sampling_time_or_window",
    "study_design",
    "dose_standardization_or_equivalence",
    "comparator_or_reference",
    "co_exposure_or_modifier",
    "metabolic_or_transport_target",
    "metabolic_or_transport_pathway",
    "experimental_system_category",
    "model_or_method",
    "interaction_or_potentiation_context",
    "exposure_response_or_pk_effect",
    "exposure_response_implication",
    "synthesis_interpretation",
    "assessment_timepoint",
    "mechanism_type",
    "assay_type",
    "assay_family",
    "assay_family_normalized",
    "action_type",
    "species",
    "model_or_system",
    "system",
    "evidence_level",
    "support",
    "confidence",
)
BOOL_FIELDS = {"needs_human_review", "is_retracted", "has_correction", "open_access_is_oa", "unpaywall_is_oa"}


def normalize(value: object) -> str:
    if value is None:
        return ""
    try:
        if value != value:
            return ""
    except Exception:
        pass
    return str(value).strip()


def meaningful(value: object) -> bool:
    text = normalize(value).lower()
    return text not in {"", "nan", "none", "not_reported", "not reported", "not_applicable", "not applicable"}


def first_meaningful(*values: object) -> str:
    for value in values:
        if meaningful(value):
            return normalize(value)
    return ""


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def compact_json(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n"


def relative_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def parse_raw_json(value: object) -> dict:
    if isinstance(value, dict):
        return value
    text = normalize(value)
    if not text:
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        return {}
    return data


def field_value(raw: dict, record: dict, *names: str) -> str:
    for name in names:
        value = first_meaningful(raw.get(name, ""), record.get(name, ""))
        if value:
            return value
    return ""


def field_bool(raw: dict, record: dict, *names: str) -> bool | str:
    for name in names:
        for source in (raw, record):
            value = source.get(name, "")
            if value is True or value is False:
                return value
            text = normalize(value).lower()
            if text in {"true", "false"}:
                return text == "true"
    return ""


def as_int_or_text(value: object) -> int | str:
    text = normalize(value)
    if not text:
        return ""
    match = re.search(r"\b(18|19|20)\d{2}\b", text)
    if match:
        return int(match.group(0))
    try:
        number = int(float(text))
    except ValueError:
        return text
    return number if 1800 <= number <= 3000 else text


def text_depth(value: object) -> str:
    text = normalize(value).lower()
    if text in {"article_text", "full_text", "full_text_seen"}:
        return "article_text"
    if text in {"abstract", "abstract_only"}:
        return "abstract_only"
    if text in {"secondary_summary"}:
        return "secondary_summary"
    return text or "abstract_only"


def normalized_source_family(value: object) -> str:
    text = normalize(value).lower()
    if text in {"primary", "primary_study"}:
        return "original_empirical"
    return normalize(value)


def normalized_assay_family(raw: dict, record: dict) -> str:
    existing = field_value(raw, record, "assay_family_normalized", "normalized_assay_family")
    if existing:
        return existing
    return normalize_mechanistic_assay_family(
        field_value(raw, record, "assay_family"),
        field_value(raw, record, "assay_type"),
    )


def normalized_comparator(raw: dict, record: dict) -> str:
    existing = field_value(raw, record, "comparator_normalized")
    if existing:
        return existing
    return normalize_clinical_comparator(field_value(raw, record, "comparator"))


def normalized_follow_up_window(raw: dict, record: dict) -> str:
    existing = field_value(raw, record, "follow_up_window_normalized")
    if existing:
        return existing
    return normalize_clinical_followup_window(
        field_value(raw, record, "follow_up_duration"),
        field_value(raw, record, "assessment_timepoint", "timepoint"),
    )


def load_author_roles(kg_dir: Path) -> dict[str, dict]:
    path = kg_dir / "paper_authors.parquet"
    if not path.exists():
        return {}
    try:
        import pandas as pd
    except ModuleNotFoundError:
        return {}

    df = pd.read_parquet(path)
    if df.empty:
        return {}
    roles: dict[str, dict] = {}
    for record in df.to_dict(orient="records"):
        paper_id = normalize(record.get("paper_id"))
        if not paper_id:
            continue
        entry = roles.setdefault(paper_id, {})
        payload = {
            "id": normalize(record.get("author_id")),
            "name": normalize(record.get("display_name")),
            "openalex_author_id": normalize(record.get("openalex_author_id")),
            "orcid": normalize(record.get("orcid")),
        }
        payload = {key: value for key, value in payload.items() if value}
        if record.get("is_first_author") is True and payload:
            entry["first_author"] = payload
        if record.get("is_last_author") is True and payload:
            entry["last_author"] = payload
    return roles


def merge_edge_metadata(rows, kg_dir: Path):
    edge_path = kg_dir / "evidence_edges.parquet"
    join_key = "finding_id" if "finding_id" in rows.columns else ""
    if not join_key or not edge_path.exists() or rows.empty:
        return rows
    import pandas as pd

    edges = pd.read_parquet(edge_path)
    if edges.empty or join_key not in edges.columns:
        return rows
    edge_columns = [
        column
        for column in (
            join_key,
            "evidence_id",
            "source_name",
            "domain",
            "entity_kind",
            "entity_label",
            "evidence_type",
            "relation_type",
        )
        if column in edges.columns
    ]
    edges = edges[edge_columns].drop_duplicates(join_key)
    return rows.merge(edges, on=join_key, how="left", suffixes=("", "_edge"))


def finding_from_record(record: dict, author_roles: dict[str, dict]) -> dict:
    raw = parse_raw_json(record.get("raw_row_json", ""))
    domain = field_value(raw, record, "domain_edge", "domain")
    evidence_type = field_value(raw, record, "evidence_type_edge", "evidence_type") or "primary_evidence"
    entity_label = first_meaningful(
        field_value(raw, record, "entity_label_edge"),
        field_value(raw, record, "graph_entity_label"),
        field_value(raw, record, "entity_label"),
        field_value(raw, record, "target"),
        field_value(raw, record, "disorder"),
        field_value(raw, record, "outcome_measure"),
        field_value(raw, record, "raw_entity_label"),
    )
    entity_kind = first_meaningful(
        field_value(raw, record, "entity_kind_edge", "kg_entity_kind_override", "entity_kind"),
        field_value(raw, record, "graph_entity_type"),
    )

    finding = {
        "finding_id": field_value(raw, record, "finding_id"),
        "evidence_id": field_value(raw, record, "evidence_id_edge", "evidence_id"),
        "paper_id": field_value(raw, record, "paper_id"),
        "domain": domain,
        "finding_type": domain or "routed_evidence",
        "evidence_type": evidence_type,
        "relation_type": field_value(raw, record, "relation_type_edge", "relation_type"),
        "compound": field_value(raw, record, "compound"),
        "entity_label": entity_label,
        "entity_kind": entity_kind,
        "text_depth": text_depth(field_value(raw, record, "access_level")),
        "assessment_timepoint": field_value(raw, record, "assessment_timepoint", "timepoint"),
    }

    for field in PAPER_FIELDS:
        value = field_bool(raw, record, field) if field in BOOL_FIELDS else field_value(raw, record, field)
        if field == "study_year":
            value = as_int_or_text(value)
        if value != "":
            finding[field] = value

    for field in FINDING_FIELDS:
        if field == "assay_family_normalized":
            value = normalized_assay_family(raw, record)
        elif field == "comparator_normalized":
            value = normalized_comparator(raw, record)
        elif field == "follow_up_window_normalized":
            value = normalized_follow_up_window(raw, record)
        elif field == "source_family":
            value = normalized_source_family(field_value(raw, record, field))
        elif field == "access_level":
            continue
        elif field in BOOL_FIELDS:
            value = field_bool(raw, record, field)
        else:
            value = field_value(raw, record, field)
        if value != "":
            finding[field] = value

    roles = author_roles.get(finding.get("paper_id", ""), {})
    if roles.get("first_author"):
        finding["first_author"] = roles["first_author"]
    if roles.get("last_author"):
        finding["last_author"] = roles["last_author"]

    return {key: value for key, value in finding.items() if value != ""}


def load_findings(kg_dir: Path) -> list[dict]:
    evidence_table = kg_dir / "findings.parquet"
    if not evidence_table.exists():
        raise FileNotFoundError(f"Missing findings table: {evidence_table}")
    try:
        import pandas as pd
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency failure path
        raise RuntimeError("pandas/pyarrow are required to load KG Parquet tables") from exc

    df = pd.read_parquet(evidence_table)
    if df.empty:
        return []
    if "source_name" in df.columns:
        df = df[df["source_name"].isin(ROUTED_SOURCE_NAMES)].copy()
    df = merge_edge_metadata(df, kg_dir)
    author_roles = load_author_roles(kg_dir)
    findings = [finding_from_record(record, author_roles) for record in df.to_dict(orient="records")]
    return sorted(
        findings,
        key=lambda item: (
            normalize(item.get("domain")),
            normalize(item.get("compound")),
            normalize(item.get("entity_label")),
            normalize(item.get("study_doi")),
            normalize(item.get("openalex_id")),
            normalize(item.get("finding_id")),
        ),
    )


def study_key(finding: dict) -> str:
    doi = normalize(finding.get("study_doi")).lower()
    if doi:
        return f"doi:{doi}"
    openalex = normalize(finding.get("openalex_id")).lower()
    if openalex:
        return f"openalex:{openalex}"
    title = normalize(finding.get("study_title")).lower()
    year = normalize(finding.get("study_year"))
    return f"title:{title}|{year}" if title or year else ""


def candidate_study_key(record: dict) -> str:
    doi = normalize(record.get("study_doi") or record.get("doi")).lower()
    if doi:
        return f"doi:{doi}"
    openalex = normalize(record.get("openalex_id")).lower()
    if openalex:
        return f"openalex:{openalex}"
    title = normalize(record.get("study_title") or record.get("title")).lower()
    year = normalize(record.get("study_year") or record.get("year"))
    if title or year:
        return f"title:{title}|{year}"
    paper_id = normalize(record.get("paper_id")).lower()
    return f"paper:{paper_id}" if paper_id else ""


def load_candidate_study_keys(kg_dir: Path) -> set[str] | None:
    path = kg_dir / "papers.parquet"
    if not path.exists():
        return None
    try:
        import pandas as pd
    except ModuleNotFoundError:
        return None

    df = pd.read_parquet(path)
    if df.empty:
        return set()
    return {key for record in df.to_dict(orient="records") if (key := candidate_study_key(record))}


def value_counts(findings: Iterable[dict], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        value = normalize(finding.get(field))
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def summary_stats(findings: list[dict], candidate_study_keys: set[str] | None = None) -> dict:
    studies = {key for finding in findings if (key := study_key(finding))}
    compounds = {normalize(finding.get("compound")) for finding in findings if normalize(finding.get("compound"))}
    entities = {normalize(finding.get("entity_label")) for finding in findings if normalize(finding.get("entity_label"))}
    conditions = {
        normalize(finding.get("entity_label"))
        for finding in findings
        if normalize(finding.get("entity_kind")) == "condition_indication" and normalize(finding.get("entity_label"))
    }
    targets = {
        normalize(finding.get("entity_label"))
        for finding in findings
        if normalize(finding.get("entity_kind")) == "target" and normalize(finding.get("entity_label"))
    }
    stats = {
        "row_count": len(findings),
        "study_count": len(studies),
        "compound_count": len(compounds),
        "entity_count": len(entities),
        "domain_count": len(value_counts(findings, "domain")),
        "condition_count": len(conditions),
        "target_count": len(targets),
        "domain_counts": value_counts(findings, "domain"),
        "entity_kind_counts": value_counts(findings, "entity_kind"),
        "evidence_type_counts": value_counts(findings, "evidence_type"),
        "text_depth_counts": value_counts(findings, "text_depth"),
    }
    if candidate_study_keys is not None:
        candidate_keys = {key for key in candidate_study_keys if key}
        not_in_graph_keys = candidate_keys - studies
        stats["graph_study_coverage"] = {
            "included_count": len(studies),
            "candidate_count": len(candidate_keys),
            "not_in_graph_count": len(not_in_graph_keys),
        }
        stats["graph_candidate_study_count"] = len(candidate_keys)
        stats["graph_excluded_study_count"] = len(not_in_graph_keys)
    return stats


def preview_findings(findings: list[dict]) -> list[dict]:
    out = []
    for finding in findings:
        preview = {field: finding[field] for field in PREVIEW_FIELDS if field in finding}
        if "first_author" in finding:
            preview["first_author"] = finding["first_author"]
        if "last_author" in finding:
            preview["last_author"] = finding["last_author"]
        out.append(preview)
    return out


def remove_stale_payload_files(out_dir: Path, keep_names: set[str]) -> None:
    for pattern in ("graph_payload_*.json", "graph_preview_*.json"):
        for path in out_dir.glob(pattern):
            if path.name in keep_names:
                continue
            path.unlink()


def write_active_pointer(active_json: Path, out_dir: Path, manifest_path: Path, payload_path: Path, preview_path: Path, kg_dir: Path) -> dict:
    payload = {
        "schema_version": ACTIVE_SCHEMA_VERSION,
        "active_evidence_payload": relative_path(payload_path),
        "active_evidence_preview": relative_path(preview_path),
        "active_manifest": relative_path(manifest_path),
        "evidence_source": "kg_tables",
        "kg_dir": relative_path(kg_dir),
    }
    active_json.parent.mkdir(parents=True, exist_ok=True)
    active_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def export_evidence_payload(
    *,
    kg_dir: Path,
    out_dir: Path,
    payload_name: str = "graph_payload_evidence.json",
    preview_name: str = "graph_preview_evidence.json",
    manifest_name: str = "graph_payload_manifest.json",
    active_json: Path | None = None,
) -> dict:
    findings = load_findings(kg_dir)
    candidate_study_keys = load_candidate_study_keys(kg_dir)
    stats = summary_stats(findings, candidate_study_keys)
    out_dir.mkdir(parents=True, exist_ok=True)

    payload_path = out_dir / payload_name
    preview_path = out_dir / preview_name
    manifest_path = out_dir / manifest_name
    remove_stale_payload_files(out_dir, {payload_path.name, preview_path.name, manifest_path.name})

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_utc(),
        "evidence_source": "kg_tables",
        "kg_dir": relative_path(kg_dir),
        "row_count": len(findings),
        "summary_stats": stats,
        "findings": findings,
    }
    preview_payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": payload["generated_at"],
        "evidence_source": payload["evidence_source"],
        "kg_dir": payload["kg_dir"],
        "row_count": len(findings),
        "summary_stats": stats,
        "findings": preview_findings(findings),
    }

    payload_path.write_text(compact_json(payload), encoding="utf-8")
    preview_path.write_text(compact_json(preview_payload), encoding="utf-8")

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": payload["generated_at"],
        "evidence_source": "kg_tables",
        "kg_dir": relative_path(kg_dir),
        "evidence_payload": relative_path(payload_path),
        "evidence_preview": relative_path(preview_path),
        "row_count": len(findings),
        "summary_stats": {
            "default": stats,
            "views": {
                "primary": summary_stats(
                    [f for f in findings if normalize(f.get("evidence_type")) == "primary_evidence"],
                    candidate_study_keys,
                ),
                "secondary": summary_stats([f for f in findings if normalize(f.get("evidence_type")) == "secondary_literature"]),
            },
        },
        "status": "ok",
    }
    if active_json:
        manifest["active_payload_pointer"] = write_active_pointer(
            active_json=active_json,
            out_dir=out_dir,
            manifest_path=manifest_path,
            payload_path=payload_path,
            preview_path=preview_path,
            kg_dir=kg_dir,
        )
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "payload_path": payload_path,
        "preview_path": preview_path,
        "manifest_path": manifest_path,
        "manifest": manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export route-native evidence findings for the web UI")
    parser.add_argument("--kg-dir", default=str(DEFAULT_KG_DIR), help="KG table directory to read.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory for web payload files.")
    parser.add_argument("--payload", default="graph_payload_evidence.json", help="Evidence payload filename.")
    parser.add_argument("--preview", default="graph_preview_evidence.json", help="Evidence preview filename.")
    parser.add_argument("--manifest", default="graph_payload_manifest.json", help="Manifest filename.")
    parser.add_argument(
        "--activate-default",
        action="store_true",
        help="Write data/processed/graph_payload_active.json so the browser UI loads this evidence payload by default.",
    )
    parser.add_argument(
        "--active-json",
        default=str(DEFAULT_ACTIVE_JSON),
        help="Active payload pointer written when --activate-default is used.",
    )
    args = parser.parse_args()

    result = export_evidence_payload(
        kg_dir=Path(args.kg_dir).resolve(),
        out_dir=Path(args.out_dir).resolve(),
        payload_name=args.payload,
        preview_name=args.preview,
        manifest_name=args.manifest,
        active_json=Path(args.active_json).resolve() if args.activate_default else None,
    )
    manifest = result["manifest"]
    print(f"Evidence payload: {result['payload_path']}")
    print(f"Evidence preview: {result['preview_path']}")
    print(f"Manifest: {result['manifest_path']}")
    if args.activate_default:
        print(f"Active payload pointer: {Path(args.active_json).resolve()}")
    print(f"Findings: {manifest['row_count']}")
    print(f"Studies: {manifest['summary_stats']['default']['study_count']}")
    print("Status: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
