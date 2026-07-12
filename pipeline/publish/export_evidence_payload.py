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
ACTIVE_SCHEMA_VERSION = "route_native_evidence_payload_active_v1"
MANIFEST_SCHEMA_VERSION = "route_native_evidence_manifest_v1"
GRAPH_BOOTSTRAP_SCHEMA_VERSION = "route_native_graph_bootstrap_v1"
DETAIL_BOOTSTRAP_SCHEMA_VERSION = "route_native_detail_bootstrap_v1"
PRIMARY_SOURCE_KEY = "primary"
META_ANALYSES_SOURCE_KEY = "meta_analyses"
REVIEWS_SOURCE_KEY = "reviews"
UI_SOURCE_KEYS = (PRIMARY_SOURCE_KEY, META_ANALYSES_SOURCE_KEY, REVIEWS_SOURCE_KEY)
META_ANALYSIS_SOURCE_TYPES = {
    "meta_analysis",
    "network_meta_analysis",
}
REVIEW_SOURCE_TYPES = {
    "review",
    "systematic_review",
    "scoping_review",
    "narrative_review",
    "literature_review",
    "umbrella_review",
}
GRAPH_BOOTSTRAP_ENTITY_KINDS = {
    "condition_indication",
    "safety_adverse_event",
    "cognitive_behavioral_construct",
    "subjective_experience_construct",
    "intervention_component",
    "public_health_measure",
    "brain_region",
    "brain_network",
    "neural_circuit",
    "pathway_process",
    "biomarker_readout",
    "target",
    "system_family",
}
GRAPH_BOOTSTRAP_EXCLUDED_DOMAINS = {
    "pharmacokinetics_exposure",
}
AUTHOR_TABLE_FILENAMES = (
    "authors.parquet",
    "paper_authors.parquet",
    "author_resolution_report.json",
)
UNKNOWN_AUTHOR_VALUES = {
    "",
    "unknown",
    "unknown author",
    "unknown authors",
    "not available",
    "n/a",
    "na",
    "none",
}

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
    "graph_subject_label",
    "graph_subject_kind",
    "graph_subject_source_field",
    "atomic_compound_candidate",
    "graph_overview_subject_label",
    "graph_overview_subject_kind",
    "graph_overview_subject_reason",
    "extraction_warnings",
    "raw_entity_label",
    "entity_role",
    "clinical_context_condition",
    "graph_entity_label",
    "graph_entity_type",
    "graph_parent_label",
    "graph_parent_kind",
    "graph_parent_entity_id",
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
    "result_direction_normalized",
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
    "evidence_design",
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
    "molecular_finding_subtopic",
    "specific_readout_or_marker",
    "mechanistic_relationship_type",
    "public_health_topic_category",
    "public_health_measure",
    "real_world_use_context",
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
    "graph_admission_status",
    "graph_admission_reason",
    "proposition_group_id",
    "proposition_conflict_group_id",
    "proposition_duplicate_count",
    "direction_consistency",
)

DETAIL_BOOTSTRAP_FIELDS = (
    "domain",
    "finding_type",
    "evidence_type",
    "relation_type",
    "compound",
    "graph_subject_label",
    "graph_subject_kind",
    "atomic_compound_candidate",
    "graph_overview_subject_label",
    "graph_overview_subject_kind",
    "graph_overview_subject_reason",
    "entity_label",
    "entity_kind",
    "graph_entity_label",
    "graph_parent_label",
    "graph_parent_kind",
    "graph_parent_entity_id",
    "molecular_finding_subtopic",
    "mechanism_type",
    "assay_type",
    "assay_family",
    "action_type",
    "affinity_type",
    "affinity_value",
    "study_doi",
    "openalex_id",
    "study_title",
    "study_year",
    "study_journal",
    "publication_type",
    "open_access_is_oa",
    "open_access_status",
    "unpaywall_is_oa",
    "unpaywall_oa_status",
    "text_depth",
    "access_level",
    "source_access_level",
    "paper_type",
    "source_type",
    "source_family",
    "paper_assessment_route",
    "study_design",
    "study_design_category",
    "evidence_design",
    "population_model_category",
    "outcome_type",
    "sample_size_total",
    "sample_size_by_arm",
    "comparator",
    "comparator_normalized",
    "normalized_comparator",
    "follow_up_duration",
    "follow_up_window_normalized",
    "normalized_follow_up_window",
    "assessment_timepoint",
    "timepoint",
    "administration_route",
    "route",
    "route_of_administration",
    "dose",
    "dosing_schedule",
    "session_context",
    "system",
    "support",
    "effect_size",
    "outcome_measure",
    "outcome_measure_normalized",
    "evidence_location",
    "evidence_locator",
    "supporting_quote",
    "result_direction_normalized",
    "graph_admission_status",
    "graph_admission_reason",
    "proposition_group_id",
    "proposition_duplicate_count",
    "direction_consistency",
    "first_author",
    "last_author",
    "authors",
    "trial_registry_ids",
    "data_source_type",
    "public_health_graph_label",
    "public_health_topic_category",
    "public_health_measure",
    "real_world_use_context",
    "assay_family_normalized",
    "normalized_assay_family",
    "mechanistic_relationship_type",
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


def author_rebuild_command(kg_dir: Path) -> str:
    papers = kg_dir / "papers.parquet"
    cache = kg_dir / "openalex_author_cache.json"
    return (
        "python pipeline/kg/build_author_tables.py "
        f'--papers "{papers}" '
        f'--out-dir "{kg_dir}" '
        f'--cache "{cache}"'
    )


def author_check_error(kg_dir: Path, reasons: list[str]) -> RuntimeError:
    details = "; ".join(reasons)
    return RuntimeError(
        "Author tables are not fresh for this KG run. "
        f"{details}. Run `{author_rebuild_command(kg_dir)}` before exporting the public payload, "
        "or pass --allow-stale-authors only for a deliberate diagnostic export."
    )


def validate_fresh_author_tables(kg_dir: Path) -> dict:
    papers_path = kg_dir / "papers.parquet"
    paths = {name: kg_dir / name for name in AUTHOR_TABLE_FILENAMES}
    reasons: list[str] = []

    if not papers_path.exists():
        raise author_check_error(kg_dir, [f"missing papers.parquet in {kg_dir}"])

    missing = [name for name, path in paths.items() if not path.exists()]
    if missing:
        raise author_check_error(kg_dir, [f"missing {', '.join(missing)}"])

    papers_mtime = papers_path.stat().st_mtime
    stale = [name for name, path in paths.items() if path.stat().st_mtime + 0.001 < papers_mtime]
    if stale:
        reasons.append(f"{', '.join(stale)} older than papers.parquet")

    try:
        import pandas as pd
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency failure path
        raise RuntimeError("pandas/pyarrow are required to validate author tables") from exc

    papers = pd.read_parquet(papers_path)
    paper_authors = pd.read_parquet(paths["paper_authors.parquet"])
    if "paper_id" not in papers.columns:
        reasons.append("papers.parquet has no paper_id column")
        paper_ids: set[str] = set()
    else:
        paper_ids = {normalize(value) for value in papers["paper_id"] if normalize(value)}

    if "paper_id" not in paper_authors.columns:
        reasons.append("paper_authors.parquet has no paper_id column")
        paper_author_ids: set[str] = set()
    else:
        paper_author_ids = {normalize(value) for value in paper_authors["paper_id"] if normalize(value)}

    unexpected_ids = sorted(paper_author_ids - paper_ids)
    if unexpected_ids:
        reasons.append(f"paper_authors.parquet contains {len(unexpected_ids)} paper_ids not in papers.parquet")

    if "authors" in papers.columns and paper_ids:
        papers_with_author_text = {
            normalize(row.get("paper_id"))
            for row in papers[["paper_id", "authors"]].fillna("").to_dict(orient="records")
            if normalize(row.get("paper_id"))
            and normalize(row.get("authors")).strip().lower() not in UNKNOWN_AUTHOR_VALUES
        }
        missing_author_rows = sorted(papers_with_author_text - paper_author_ids)
        if missing_author_rows:
            reasons.append(
                f"paper_authors.parquet is missing {len(missing_author_rows)} papers with author strings"
            )

    try:
        report = json.loads(paths["author_resolution_report.json"].read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise author_check_error(kg_dir, [f"invalid author_resolution_report.json: {exc}"]) from exc

    report_paper_count = report.get("paper_count")
    if report_paper_count != len(papers):
        reasons.append(
            f"author_resolution_report.json paper_count is {report_paper_count}, expected {len(papers)}"
        )

    report_rows = report.get("paper_author_rows")
    if report_rows != len(paper_authors):
        reasons.append(
            f"author_resolution_report.json paper_author_rows is {report_rows}, expected {len(paper_authors)}"
        )

    if reasons:
        raise author_check_error(kg_dir, reasons)

    return {
        "status": "ok",
        "paper_count": len(papers),
        "paper_author_rows": len(paper_authors),
        "unique_author_papers": len(paper_author_ids),
    }


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
    return normalize_mechanistic_assay_family(
        existing or field_value(raw, record, "assay_family"),
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
            "graph_parent_label",
            "graph_parent_kind",
            "graph_parent_entity_id",
            "evidence_type",
            "relation_type",
            "graph_subject_kind",
            "graph_overview_subject_label",
            "graph_overview_subject_kind",
            "graph_overview_subject_reason",
            "direction_normalized",
            "evidence_design",
            "graph_admission_status",
            "graph_admission_reason",
            "proposition_group_id",
            "proposition_conflict_group_id",
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


def candidate_source_key(record: dict) -> str:
    raw = parse_raw_json(record.get("raw_row_json", ""))
    combined = dict(raw)
    combined.update({key: value for key, value in record.items() if meaningful(value)})
    route = normalize(combined.get("paper_assessment_route")).lower()
    evidence_type = normalize(combined.get("evidence_type") or combined.get("kg_evidence_type")).lower()
    source_item_type = normalize(combined.get("source_item_type")).lower()
    if route == "secondary_literature" or evidence_type == "secondary_literature" or source_item_type == "review_coverage_item":
        return secondary_literature_source_key(combined)
    return PRIMARY_SOURCE_KEY


def load_candidate_study_key_sets(kg_dir: Path) -> dict[str, set[str]] | None:
    paths = [kg_dir / "findings.parquet", kg_dir / "normalization_audit.parquet"]
    existing_paths = [path for path in paths if path.exists()]
    if not existing_paths:
        return None
    try:
        import pandas as pd
    except ModuleNotFoundError:
        return None

    keys_by_source = {source_key: set() for source_key in UI_SOURCE_KEYS}
    for path in existing_paths:
        df = pd.read_parquet(path)
        if df.empty:
            continue
        for record in df.to_dict(orient="records"):
            key = candidate_study_key(record)
            if key:
                keys_by_source[candidate_source_key(record)].add(key)
    keys_by_source["all"] = set().union(*(keys_by_source[source_key] for source_key in UI_SOURCE_KEYS))
    return keys_by_source


def load_candidate_study_keys(kg_dir: Path) -> set[str] | None:
    key_sets = load_candidate_study_key_sets(kg_dir)
    return None if key_sets is None else key_sets["all"]


def value_counts(findings: Iterable[dict], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        value = normalize(finding.get(field))
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def summary_stats(findings: list[dict], candidate_study_keys: set[str] | None = None) -> dict:
    projections, _projection_counts = overview_graph_projections(findings)
    graph_findings = [projection["finding"] for projection in projections]
    studies = {key for finding in graph_findings if (key := study_key(finding))}
    compounds = {projection["compound"] for projection in projections if projection["compound"]}
    entities = {projection["entity_label"] for projection in projections if projection["entity_label"]}
    conditions = {
        projection["entity_label"]
        for projection in projections
        if projection["entity_kind"] == "condition_indication" and projection["entity_label"]
    }
    targets = {
        projection["entity_label"]
        for projection in projections
        if projection["entity_kind"] == "target" and projection["entity_label"]
    }
    stats = {
        "row_count": len(findings),
        "graph_finding_count": len(projections),
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


def source_type_token(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", normalize(value).lower()).strip("_")


def secondary_literature_source_key(finding: dict) -> str:
    tokens = {
        source_type_token(finding.get(field))
        for field in ("paper_type", "source_type", "publication_type")
        if source_type_token(finding.get(field))
    }
    if tokens & META_ANALYSIS_SOURCE_TYPES or any("meta_analysis" in token for token in tokens):
        return META_ANALYSES_SOURCE_KEY
    if tokens & REVIEW_SOURCE_TYPES or any("review" in token for token in tokens):
        return REVIEWS_SOURCE_KEY
    return REVIEWS_SOURCE_KEY


def ui_source_key_for_finding(finding: dict) -> str:
    evidence_type = normalize(finding.get("evidence_type") or finding.get("kg_evidence_type")).lower()
    if evidence_type == "secondary_literature":
        return secondary_literature_source_key(finding)
    return PRIMARY_SOURCE_KEY


def findings_for_ui_source(findings: list[dict], source_key: str) -> list[dict]:
    return [finding for finding in findings if ui_source_key_for_finding(finding) == source_key]


def is_graph_bootstrap_finding(finding: dict) -> bool:
    admission = normalize(finding.get("graph_admission_status")).lower()
    if admission and admission != "main_graph":
        return False
    domain = normalize(finding.get("domain") or finding.get("kg_domain") or finding.get("finding_type")).lower()
    if domain in GRAPH_BOOTSTRAP_EXCLUDED_DOMAINS:
        return False
    entity_kind = normalize(finding.get("entity_kind") or finding.get("kg_entity_kind")).lower()
    return entity_kind in GRAPH_BOOTSTRAP_ENTITY_KINDS


def ui_graph_bootstrap_name(source_key: str) -> str:
    return f"graph_bootstrap_{source_key}.json"


def ui_detail_bootstrap_name(source_key: str) -> str:
    return f"detail_bootstrap_{source_key}.json"


OVERVIEW_PARENT_COLLAPSE_KINDS = {"pathway_process", "biomarker_readout", "intervention_component"}
MIN_OVERVIEW_NODE_STUDIES = 2


def overview_graph_projection(finding: dict) -> dict | None:
    exact_subject = normalize(finding.get("compound"))
    exact_subject_kind = normalize(finding.get("graph_subject_kind")) or "atomic_compound"
    subject = normalize(finding.get("graph_overview_subject_label"))
    subject_kind = normalize(finding.get("graph_overview_subject_kind"))
    if not subject and exact_subject_kind == "atomic_compound":
        subject = exact_subject
        subject_kind = exact_subject_kind
    if not subject:
        return None

    entity_label = normalize(finding.get("entity_label") or finding.get("graph_entity_label") or finding.get("raw_entity_label"))
    entity_kind = normalize(finding.get("entity_kind") or finding.get("kg_entity_kind"))
    if not entity_label or not entity_kind:
        return None
    parent_label = normalize(finding.get("graph_parent_label"))
    parent_kind = normalize(finding.get("graph_parent_kind"))
    used_parent = bool(parent_label and parent_kind and entity_kind in OVERVIEW_PARENT_COLLAPSE_KINDS)
    if used_parent:
        entity_label = parent_label
        entity_kind = parent_kind

    return {
        "finding": finding,
        "compound": subject,
        "graph_subject_kind": subject_kind or exact_subject_kind,
        "entity_label": entity_label,
        "entity_kind": entity_kind,
        "used_parent": used_parent,
    }


def overview_graph_projections(findings: list[dict]) -> tuple[list[dict], dict[str, int]]:
    projected: list[dict] = []
    subject_studies: dict[tuple[str, str], set[str]] = {}
    entity_studies: dict[tuple[str, str], set[str]] = {}
    detail_only_subject_count = 0
    for finding in findings:
        if not is_graph_bootstrap_finding(finding):
            continue
        projection = overview_graph_projection(finding)
        if projection is None:
            detail_only_subject_count += 1
            continue
        projected.append(projection)
        subject_key = (projection["graph_subject_kind"], projection["compound"])
        entity_key = (projection["entity_kind"], projection["entity_label"])
        study = study_key(finding)
        if study:
            subject_studies.setdefault(subject_key, set()).add(study)
            entity_studies.setdefault(entity_key, set()).add(study)

    kept: list[dict] = []
    single_study_subject_finding_count = 0
    detail_only_entity_count = 0
    for projection in projected:
        subject_key = (projection["graph_subject_kind"], projection["compound"])
        entity_label = projection["entity_label"]
        entity_kind = projection["entity_kind"]
        entity_key = (entity_kind, entity_label)
        if len(subject_studies.get(subject_key, set())) < MIN_OVERVIEW_NODE_STUDIES:
            single_study_subject_finding_count += 1
            continue
        if len(entity_studies.get(entity_key, set())) < MIN_OVERVIEW_NODE_STUDIES:
            detail_only_entity_count += 1
            continue
        kept.append(projection)

    return kept, {
        "projection_candidate_count": len(projected),
        "detail_only_subject_count": detail_only_subject_count,
        "single_study_subject_finding_count": single_study_subject_finding_count,
        "detail_only_entity_count": detail_only_entity_count,
    }


def graph_bootstrap_payload(findings: list[dict], generated_at: str, kg_dir: Path, source_key: str) -> dict:
    edges: dict[tuple[str, str, str, str, str, str], dict] = {}
    projected, projection_counts = overview_graph_projections(findings)
    graph_finding_count = 0
    for projection in projected:
        finding = projection["finding"]
        entity_label = projection["entity_label"]
        entity_kind = projection["entity_kind"]

        compound = projection["compound"]
        graph_subject_kind = projection["graph_subject_kind"]
        parent_label = normalize(finding.get("graph_parent_label"))
        parent_kind = normalize(finding.get("graph_parent_kind"))

        graph_finding_count += 1
        domain = normalize(finding.get("domain") or finding.get("kg_domain") or finding.get("finding_type"))
        key = (compound, graph_subject_kind, entity_kind, entity_label, parent_kind, parent_label)
        entry = edges.setdefault(
            key,
            {
                "compound": compound,
                "graph_subject_kind": graph_subject_kind,
                "entity_label": entity_label,
                "entity_kind": entity_kind,
                "graph_parent_label": parent_label,
                "graph_parent_kind": parent_kind,
                "graph_parent_entity_id": normalize(finding.get("graph_parent_entity_id")),
                "domain": domain,
                "finding_type": normalize(finding.get("finding_type")) or domain,
                "evidence_type": normalize(finding.get("evidence_type") or finding.get("kg_evidence_type")) or "primary_evidence",
                "finding_count": 0,
                "proposition_group_ids": set(),
                "study_keys": set(),
                "full_text_study_keys": set(),
                "abstract_only_study_keys": set(),
                "full_text_seen_count": 0,
                "abstract_only_count": 0,
            },
        )
        entry["finding_count"] += 1
        proposition_group_id = normalize(finding.get("proposition_group_id"))
        if proposition_group_id:
            entry["proposition_group_ids"].add(proposition_group_id)
        study = study_key(finding)
        if study:
            entry["study_keys"].add(study)
        depth = normalize(finding.get("text_depth") or finding.get("access_level") or finding.get("source_access_level")).lower()
        if depth in {"article_text", "full_text", "full_text_seen"}:
            entry["full_text_seen_count"] += 1
            if study:
                entry["full_text_study_keys"].add(study)
        else:
            entry["abstract_only_count"] += 1
            if study:
                entry["abstract_only_study_keys"].add(study)

    edge_entries = []
    for entry in edges.values():
        proposition_group_ids = entry.pop("proposition_group_ids")
        study_keys = entry.pop("study_keys")
        full_text_study_keys = entry.pop("full_text_study_keys")
        abstract_only_study_keys = entry.pop("abstract_only_study_keys")
        entry["study_count"] = len(study_keys)
        entry["raw_finding_count"] = entry["finding_count"]
        if proposition_group_ids:
            entry["finding_count"] = len(proposition_group_ids)
        entry["full_text_seen_study_count"] = len(full_text_study_keys)
        entry["abstract_only_study_count"] = len(abstract_only_study_keys)
        edge_entries.append(entry)
    edge_entries.sort(key=lambda item: (-item["finding_count"], item["compound"].lower(), item["entity_kind"], item["entity_label"].lower()))

    return {
        "schema_version": GRAPH_BOOTSTRAP_SCHEMA_VERSION,
        "generated_at": generated_at,
        "evidence_source": "kg_tables",
        "kg_dir": relative_path(kg_dir),
        "literature_source": source_key,
        "source": source_key,
        "edge_count": len(edge_entries),
        "finding_count": graph_finding_count,
        "source_row_count": len(findings),
        **projection_counts,
        "edges": edge_entries,
    }


def detail_bootstrap_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, dict):
        slim = {
            key: value[key]
            for key in ("id", "name", "openalex_author_id", "orcid")
            if meaningful(value.get(key))
        }
        return slim or None
    if isinstance(value, list):
        slim = [detail_bootstrap_value(item) for item in value]
        slim = [item for item in slim if item is not None]
        return slim or None
    if isinstance(value, str):
        return value if meaningful(value) else None
    return value


def detail_bootstrap_payload(findings: list[dict], generated_at: str, kg_dir: Path, source_key: str) -> dict:
    values: list[object] = [None]
    value_indexes = {json.dumps(None): 0}
    rows: list[list[int]] = []

    def value_index(value: object) -> int:
        normalized = detail_bootstrap_value(value)
        key = json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        if key not in value_indexes:
            value_indexes[key] = len(values)
            values.append(normalized)
        return value_indexes[key]

    for finding in findings:
        rows.append([value_index(finding.get(field)) for field in DETAIL_BOOTSTRAP_FIELDS])

    return {
        "schema_version": DETAIL_BOOTSTRAP_SCHEMA_VERSION,
        "generated_at": generated_at,
        "evidence_source": "kg_tables",
        "kg_dir": relative_path(kg_dir),
        "literature_source": source_key,
        "source": source_key,
        "row_count": len(rows),
        "fields": list(DETAIL_BOOTSTRAP_FIELDS),
        "values": values,
        "rows": rows,
    }


def remove_stale_payload_files(out_dir: Path, keep_names: set[str]) -> None:
    for pattern in ("graph_payload_*.json", "graph_preview_*.json", "graph_bootstrap_*.json", "detail_bootstrap_*.json"):
        for path in out_dir.glob(pattern):
            if path.name in keep_names:
                continue
            path.unlink()


def write_active_pointer(
    active_json: Path,
    out_dir: Path,
    manifest_path: Path,
    graph_bootstrap_paths: dict[str, Path],
    detail_bootstrap_paths: dict[str, Path],
    kg_dir: Path,
) -> dict:
    payload = {
        "schema_version": ACTIVE_SCHEMA_VERSION,
        "active_graph_bootstraps": {source_key: relative_path(path) for source_key, path in graph_bootstrap_paths.items()},
        "active_detail_bootstraps": {source_key: relative_path(path) for source_key, path in detail_bootstrap_paths.items()},
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
    manifest_name: str = "graph_payload_manifest.json",
    active_json: Path | None = None,
    require_fresh_author_tables: bool = True,
) -> dict:
    author_table_status = (
        validate_fresh_author_tables(kg_dir)
        if require_fresh_author_tables
        else {"status": "skipped", "reason": "freshness check disabled"}
    )
    findings = load_findings(kg_dir)
    candidate_study_key_sets = load_candidate_study_key_sets(kg_dir)
    candidate_study_keys = None if candidate_study_key_sets is None else candidate_study_key_sets["all"]
    stats = summary_stats(findings, candidate_study_keys)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = out_dir / manifest_name
    graph_bootstrap_paths = {
        source_key: out_dir / ui_graph_bootstrap_name(source_key)
        for source_key in UI_SOURCE_KEYS
    }
    detail_bootstrap_paths = {
        source_key: out_dir / ui_detail_bootstrap_name(source_key)
        for source_key in UI_SOURCE_KEYS
    }
    keep_names = {manifest_path.name}
    keep_names.update(path.name for path in graph_bootstrap_paths.values())
    keep_names.update(path.name for path in detail_bootstrap_paths.values())
    remove_stale_payload_files(out_dir, keep_names)

    generated_at = now_utc()
    source_summary_stats: dict[str, dict] = {}
    for source_key in UI_SOURCE_KEYS:
        source_findings = findings_for_ui_source(findings, source_key)
        source_candidate_keys = None if candidate_study_key_sets is None else candidate_study_key_sets[source_key]
        source_stats = summary_stats(source_findings, source_candidate_keys)
        source_summary_stats[source_key] = source_stats
        graph_bootstrap = graph_bootstrap_payload(source_findings, generated_at, kg_dir, source_key)
        graph_bootstrap_paths[source_key].write_text(compact_json(graph_bootstrap), encoding="utf-8")
        detail_bootstrap = detail_bootstrap_payload(source_findings, generated_at, kg_dir, source_key)
        detail_bootstrap_paths[source_key].write_text(compact_json(detail_bootstrap), encoding="utf-8")

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": generated_at,
        "evidence_source": "kg_tables",
        "kg_dir": relative_path(kg_dir),
        "graph_bootstraps": {source_key: relative_path(path) for source_key, path in graph_bootstrap_paths.items()},
        "detail_bootstraps": {source_key: relative_path(path) for source_key, path in detail_bootstrap_paths.items()},
        "row_count": len(findings),
        "author_tables": author_table_status,
        "summary_stats": {
            "default": stats,
            "sources": source_summary_stats,
        },
        "status": "ok",
    }
    if active_json:
        manifest["active_payload_pointer"] = write_active_pointer(
            active_json=active_json,
            out_dir=out_dir,
            manifest_path=manifest_path,
            graph_bootstrap_paths=graph_bootstrap_paths,
            detail_bootstrap_paths=detail_bootstrap_paths,
            kg_dir=kg_dir,
        )
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "graph_bootstrap_paths": graph_bootstrap_paths,
        "detail_bootstrap_paths": detail_bootstrap_paths,
        "manifest_path": manifest_path,
        "manifest": manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export route-native evidence findings for the web UI")
    parser.add_argument("--kg-dir", default=str(DEFAULT_KG_DIR), help="KG table directory to read.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory for web payload files.")
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
    parser.add_argument(
        "--allow-stale-authors",
        action="store_true",
        help="Skip author-table freshness checks. Use only for diagnostic exports.",
    )
    args = parser.parse_args()

    result = export_evidence_payload(
        kg_dir=Path(args.kg_dir).resolve(),
        out_dir=Path(args.out_dir).resolve(),
        manifest_name=args.manifest,
        active_json=Path(args.active_json).resolve() if args.activate_default else None,
        require_fresh_author_tables=not args.allow_stale_authors,
    )
    manifest = result["manifest"]
    print("Public evidence data: compact graph and detail bootstraps")
    print(f"Manifest: {result['manifest_path']}")
    if args.activate_default:
        print(f"Active payload pointer: {Path(args.active_json).resolve()}")
    print(f"Findings: {manifest['row_count']}")
    print(f"Studies: {manifest['summary_stats']['default']['study_count']}")
    print("Status: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
