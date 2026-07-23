#!/usr/bin/env python3
"""Export route-native evidence findings for the web UI."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]

try:
    from pipeline.extract.clinical_comparator import normalize_clinical_comparator
    from pipeline.extract.clinical_followup_window import normalize_clinical_followup_window
    from pipeline.extract.assay_family import normalize_assay_family
    from pipeline.ingest.materialize_candidate_funding import (
        DEFAULT_DOI_ALIAS_REGISTRY,
        load_doi_aliases,
        resolve_registered_doi,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(ROOT))
    from pipeline.extract.clinical_comparator import normalize_clinical_comparator
    from pipeline.extract.clinical_followup_window import normalize_clinical_followup_window
    from pipeline.extract.assay_family import normalize_assay_family
    from pipeline.ingest.materialize_candidate_funding import (
        DEFAULT_DOI_ALIAS_REGISTRY,
        load_doi_aliases,
        resolve_registered_doi,
    )


DEFAULT_KG_DIR = ROOT / "data" / "processed" / "kg"
DEFAULT_OUT_DIR = ROOT / "data" / "processed"
DEFAULT_ACTIVE_JSON = ROOT / "data" / "processed" / "graph_payload_active.json"
DEFAULT_CANDIDATE_PAPERS_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
ROUTED_SOURCE_NAME = "routed_extractions"
ROUTED_SOURCE_NAMES = {ROUTED_SOURCE_NAME, "routed_clinical_endpoints"}
ACTIVE_SCHEMA_VERSION = "route_native_evidence_payload_active_v1"
MANIFEST_SCHEMA_VERSION = "route_native_evidence_manifest_v1"
GRAPH_BOOTSTRAP_SCHEMA_VERSION = "route_native_graph_bootstrap_v1"
DASHBOARD_BOOTSTRAP_SCHEMA_VERSION = "route_native_dashboard_bootstrap_v3"
DETAIL_BOOTSTRAP_SCHEMA_VERSION = "route_native_detail_bootstrap_v3"
PRIMARY_SOURCE_KEY = "primary"
META_ANALYSES_SOURCE_KEY = "meta_analyses"
REVIEWS_SOURCE_KEY = "reviews"
UI_SOURCE_KEYS = (PRIMARY_SOURCE_KEY, META_ANALYSES_SOURCE_KEY, REVIEWS_SOURCE_KEY)
DASHBOARD_BOOTSTRAP_ENTITY_KINDS = {"condition_indication", "outcome_scale"}
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
    "exposure_context",
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
    "funding_metadata_status",
    "funding_providers",
    "funding_assertion_count",
    "funding_funder_count",
    "funding_award_count",
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
    "graph_overview_subjects_json",
    "graph_use_context_projections_json",
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
    "meta_analysis_result_role",
    "meta_analysis_primary_subject_area",
    "meta_analysis_subject_areas",
    "meta_analysis_study_count",
    "meta_analysis_effect_or_experiment_count",
    "meta_analysis_dataset_or_comparison_count",
    "meta_analysis_overall_study_count",
    "meta_analysis_overall_effect_or_experiment_count",
    "meta_analysis_overall_dataset_or_comparison_count",
    "meta_analysis_evidence_design_summary",
    "meta_analysis_search_end_date",
    "meta_analysis_effect_metric",
    "meta_analysis_interval_type",
    "meta_analysis_interval_lower",
    "meta_analysis_interval_upper",
    "meta_analysis_standard_error",
    "heterogeneity_i_squared",
    "heterogeneity_tau_squared",
    "heterogeneity_q_statistic",
    "heterogeneity_q_p_value",
    "heterogeneity_prediction_interval",
    "heterogeneity_interpretation",
    "meta_analysis_analysis_type",
    "meta_analysis_subgroup_or_moderator",
    "meta_analysis_regression_coefficient",
    "meta_analysis_sensitivity_method",
    "network_treatment_a",
    "network_treatment_b",
    "network_reference_treatment",
    "network_evidence_type",
    "network_ranking_metric",
    "network_ranking_value",
    "network_inconsistency_assessment",
    "network_transitivity_assessment",
    "adverse_events",
    "serious_adverse_events",
    "risk_of_bias_summary",
    "evidence_level",
    "support",
    "confidence",
    "needs_human_review",
    "evidence_location",
    "evidence_locator",
    "paper_assessment_route",
    "coverage_type",
    "coverage_focus",
    "coverage_focus_normalized",
    "source_type",
    "source_family",
    "paper_type",
    "review_contribution_type",
    "review_design_category",
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

# Explicit publication contract for row-level data sent to a browser. New
# extraction columns are private by default and appear here only after the UI
# needs them and their public meaning has been reviewed.
PUBLIC_BROWSER_DETAIL_FIELDS = (
    "domain",
    "finding_type",
    "evidence_type",
    "relation_type",
    "compound",
    "graph_subject_label",
    "graph_subject_kind",
    "graph_overview_subject_label",
    "graph_overview_subject_kind",
    "graph_overview_subject_reason",
    "graph_overview_subjects_json",
    "graph_use_context_projections_json",
    "entity_label",
    "entity_kind",
    "entity_aliases",
    "graph_entity_label",
    "graph_parent_label",
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
    "funders",
    "grant_ids",
    "funding_metadata_status",
    "funding_providers",
    "funding_assertion_count",
    "funding_funder_count",
    "funding_award_count",
    "open_access_is_oa",
    "open_access_status",
    "unpaywall_is_oa",
    "unpaywall_oa_status",
    "text_depth",
    "access_level",
    "source_access_level",
    "paper_type",
    "review_contribution_type",
    "review_design_category",
    "source_type",
    "source_family",
    "paper_assessment_route",
    "study_design",
    "study_design_category",
    "population_model_category",
    "outcome_type",
    "population",
    "population_or_subgroup",
    "clinical_context_condition",
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
    "p_value",
    "meta_analysis_result_role",
    "meta_analysis_study_count",
    "meta_analysis_overall_study_count",
    "heterogeneity_i_squared",
    "heterogeneity_tau_squared",
    "heterogeneity_interpretation",
    "meta_analysis_subgroup_or_moderator",
    "risk_of_bias_summary",
    "evidence_strength",
    "outcome_measure",
    "outcome_measure_normalized",
    "evidence_location",
    "evidence_locator",
    "coverage_type",
    "coverage_focus",
    "coverage_focus_normalized",
    "evidence_level",
    "graph_admission_status",
    "proposition_group_id",
    "first_author",
    "last_author",
    "authors",
    "trial_registry_ids",
    "data_source_type",
    "public_health_graph_label",
    "public_health_measure",
    "real_world_use_context",
    "assay_family_normalized",
    "normalized_assay_family",
    "mechanistic_relationship_type",
)

# These fields are useful internally but are not part of the browser contract.
# The export fails if a future edit attempts to add one without an explicit
# policy change and corresponding test review.
FORBIDDEN_BROWSER_DETAIL_FIELDS = {
    "raw_row_json",
    "supporting_quote",
    "confidence_interval",
    "extraction_warnings",
    "needs_human_review",
    "normalization_status",
    "normalization_notes",
    "graph_admission_reason",
    "proposition_conflict_group_id",
    "proposition_duplicate_count",
    "direction_consistency",
    "heterogeneity_q_statistic",
    "heterogeneity_q_p_value",
    "heterogeneity_prediction_interval",
    "meta_analysis_regression_coefficient",
    "meta_analysis_sensitivity_method",
    "network_inconsistency_assessment",
    "network_transitivity_assessment",
}
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
    return normalize_assay_family(
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


def json_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [normalize(item) for item in value if normalize(item)]
    text = normalize(value)
    if not text:
        return []
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return [normalize(item) for item in decoded if normalize(item)]


def public_author_row(record: dict) -> bool:
    author_id = normalize(record.get("author_id"))
    confidence = normalize(record.get("identity_confidence"))
    return author_id.startswith(("openalex:", "orcid:")) and confidence != (
        "openalex_author_id_orcid_conflict"
    )


def load_author_identities(kg_dir: Path) -> dict[str, dict]:
    paper_authors_path = kg_dir / "paper_authors.parquet"
    authors_path = kg_dir / "authors.parquet"
    missing = [
        path.name
        for path in (paper_authors_path, authors_path)
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError(
            f"Missing required author identity tables in {kg_dir}: {', '.join(missing)}"
        )
    try:
        import pandas as pd
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency failure path
        raise RuntimeError("pandas/pyarrow are required to load author identities") from exc

    paper_authors = pd.read_parquet(paper_authors_path)
    authors = pd.read_parquet(authors_path)
    if paper_authors.empty:
        return {}

    author_lookup: dict[str, dict] = {}
    for record in authors.to_dict(orient="records"):
        author_id = normalize(record.get("author_id"))
        if not author_id:
            continue
        author_lookup[author_id] = {
            "name": normalize(record.get("display_name")),
            "aliases": json_string_list(record.get("display_names_json")),
            "openalex_author_ids": json_string_list(
                record.get("openalex_author_ids_json")
            ),
        }

    identities: dict[str, dict] = {}
    ordered = paper_authors.sort_values(
        [column for column in ("paper_id", "author_position") if column in paper_authors.columns]
    )
    for record in ordered.to_dict(orient="records"):
        if not public_author_row(record):
            continue
        paper_id = normalize(record.get("paper_id"))
        if not paper_id:
            continue
        entry = identities.setdefault(paper_id, {"author_identities": []})
        author_id = normalize(record.get("author_id"))
        author = author_lookup.get(author_id, {})
        credited_name = normalize(record.get("display_name"))
        preferred_name = normalize(author.get("name")) or credited_name
        payload = {
            "id": author_id,
            "name": preferred_name,
            "credited_name": credited_name,
            "aliases": author.get("aliases", []),
            "openalex_author_id": normalize(record.get("openalex_author_id")),
            "openalex_author_ids": author.get("openalex_author_ids", []),
            "orcid": normalize(record.get("orcid")),
        }
        payload = {
            key: value
            for key, value in payload.items()
            if value not in (None, "", [])
        }
        entry["author_identities"].append(payload)
        if record.get("is_first_author") is True and payload:
            entry["first_author"] = payload
        if record.get("is_last_author") is True and payload:
            entry["last_author"] = payload
    return identities


def load_entity_aliases(kg_dir: Path) -> dict[str, list[str]]:
    path = kg_dir / "entities.parquet"
    if not path.exists():
        return {}
    try:
        import pandas as pd
    except ModuleNotFoundError:
        return {}

    df = pd.read_parquet(path)
    if df.empty or "entity_id" not in df.columns or "aliases_json" not in df.columns:
        return {}

    aliases_by_id: dict[str, list[str]] = {}
    for record in df.to_dict(orient="records"):
        entity_id = normalize(record.get("entity_id"))
        if not entity_id:
            continue
        raw_aliases = record.get("aliases_json", "")
        if isinstance(raw_aliases, str):
            try:
                raw_aliases = json.loads(raw_aliases)
            except json.JSONDecodeError:
                raw_aliases = []
        if not isinstance(raw_aliases, list):
            raw_aliases = []
        label = normalize(record.get("label"))
        aliases_by_id[entity_id] = sorted(
            {
                normalize(alias)
                for alias in raw_aliases
                if normalize(alias) and normalize(alias).casefold() != label.casefold()
            },
            key=str.casefold,
        )
    return aliases_by_id


def merge_edge_metadata(rows, kg_dir: Path):
    edge_path = kg_dir / "evidence_edges.parquet"
    join_key = "finding_id" if "finding_id" in rows.columns else ""
    if not join_key or not edge_path.exists() or rows.empty:
        return rows
    import pandas as pd

    edges = pd.read_parquet(edge_path)
    if edges.empty or join_key not in edges.columns:
        return rows
    if "projection_type" in edges.columns:
        # Findings remain one row each. Alternate use-context edges are carried
        # through their structured projection field and expanded separately.
        edges = edges[edges["projection_type"].fillna("outcome") != "use_context"].copy()
    edge_columns = [
        column
        for column in (
            join_key,
            "evidence_id",
            "entity_id",
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
            "graph_overview_subjects_json",
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


def merge_paper_metadata(rows, kg_dir: Path):
    """Attach canonical paper metadata to every finding before browser export.

    ``papers.parquet`` is the normalized paper-level source of truth. Finding
    rows intentionally do not repeat fields such as funders and grants, so the
    browser exporter must join them here rather than relying on extraction
    ``raw_row_json`` snapshots.
    """

    papers_path = kg_dir / "papers.parquet"
    if rows.empty or "paper_id" not in rows.columns or not papers_path.exists():
        return rows

    import pandas as pd

    papers = pd.read_parquet(papers_path)
    if papers.empty or "paper_id" not in papers.columns:
        return rows
    duplicate_ids = papers.loc[
        papers["paper_id"].fillna("").astype(str).str.strip().ne("")
        & papers["paper_id"].duplicated(keep=False),
        "paper_id",
    ]
    if not duplicate_ids.empty:
        raise ValueError(
            "papers.parquet contains duplicate paper_id values: "
            + ", ".join(sorted({normalize(value) for value in duplicate_ids})[:10])
        )

    paper_columns = [field for field in PAPER_FIELDS if field in papers.columns]
    if not paper_columns:
        return rows
    merged = rows.merge(
        papers[["paper_id", *paper_columns]],
        on="paper_id",
        how="left",
        suffixes=("", "_paper"),
    )
    for field in paper_columns:
        paper_field = f"{field}_paper" if field in rows.columns else field
        if paper_field not in merged.columns:
            continue
        paper_values = merged[paper_field]
        present = paper_values.notna()
        if paper_values.dtype == object:
            present &= paper_values.astype(str).str.strip().ne("")
        if field not in merged.columns:
            merged[field] = paper_values
        elif paper_field != field:
            # Canonical paper metadata may use string-backed columns while a
            # finding column (notably ``study_year``) is numeric. Build the
            # replacement as an object series so pandas does not reject the
            # authoritative value as a lossy in-place dtype change.
            combined = merged[field].astype(object)
            incoming = paper_values.astype(object)
            combined.loc[present] = incoming.loc[present]
            merged[field] = combined
        if paper_field != field:
            merged = merged.drop(columns=[paper_field])
    return merged


def finding_from_record(
    record: dict,
    author_identities: dict[str, dict],
    entity_aliases: dict[str, list[str]] | None = None,
) -> dict:
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

    entity_aliases = entity_aliases or {}
    entity_id = field_value(raw, record, "entity_id_edge", "entity_id")
    parent_entity_id = field_value(raw, record, "graph_parent_entity_id_edge", "graph_parent_entity_id")
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
        "entity_aliases": entity_aliases.get(entity_id, []),
        "graph_parent_aliases": entity_aliases.get(parent_entity_id, []),
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

    paper_authors = author_identities.get(finding.get("paper_id", ""), {})
    if paper_authors.get("first_author"):
        finding["first_author"] = paper_authors["first_author"]
    if paper_authors.get("last_author"):
        finding["last_author"] = paper_authors["last_author"]
    if paper_authors.get("author_identities"):
        finding["author_identities"] = paper_authors["author_identities"]

    return {key: value for key, value in finding.items() if value != ""}


def load_findings(
    kg_dir: Path,
    *,
    require_author_identities: bool = True,
) -> list[dict]:
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
    df = merge_paper_metadata(df, kg_dir)
    author_identities = (
        load_author_identities(kg_dir) if require_author_identities else {}
    )
    entity_aliases = load_entity_aliases(kg_dir)
    findings = [
        finding_from_record(record, author_identities, entity_aliases)
        for record in df.to_dict(orient="records")
    ]
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


def candidate_study_key(
    record: dict, doi_aliases: dict[str, str] | None = None
) -> str:
    doi = normalize(record.get("study_doi") or record.get("doi")).lower()
    if doi:
        doi = resolve_registered_doi(doi, doi_aliases)
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


def load_selected_candidate_study_key_sets(
    candidate_papers_table: Path,
    doi_aliases: dict[str, str] | None = None,
) -> dict[str, set[str]] | None:
    """Load the selected-paper denominator independently of extraction output.

    The KG tables only contain papers that reached extraction or normalization.
    Using them as the candidate denominator therefore hides genuine missing
    papers.  The canonical corpus table is the upstream source of truth for
    papers retained for extraction.
    """
    if not candidate_papers_table.exists():
        return None
    try:
        import pandas as pd
    except ModuleNotFoundError:
        return None

    df = pd.read_parquet(candidate_papers_table)
    if df.empty or "retained_for_extraction_candidate" not in df.columns:
        return None
    selected = df[df["retained_for_extraction_candidate"].fillna(False).astype(bool)]
    keys_by_source = {source_key: set() for source_key in UI_SOURCE_KEYS}
    for record in selected.to_dict(orient="records"):
        key = candidate_study_key(record, doi_aliases)
        if not key:
            continue
        source_type = source_type_token(
            record.get("literature_source_type")
            or record.get("primary_secondary_source_type")
        )
        source_family = source_type_token(record.get("literature_source_family"))
        if source_type in META_ANALYSIS_SOURCE_TYPES or "meta_analysis" in source_type:
            source_key = META_ANALYSES_SOURCE_KEY
        elif source_family == "secondary_literature" or source_type != "primary":
            source_key = REVIEWS_SOURCE_KEY
        else:
            source_key = PRIMARY_SOURCE_KEY
        keys_by_source[source_key].add(key)
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


MIN_OVERVIEW_NODE_STUDIES = 2


def summary_stats(
    findings: list[dict],
    candidate_study_keys: set[str] | None = None,
    *,
    minimum_node_studies: int = MIN_OVERVIEW_NODE_STUDIES,
) -> dict:
    projections, _projection_counts = overview_graph_projections(
        findings,
        minimum_node_studies=minimum_node_studies,
    )
    graph_findings = [projection["finding"] for projection in projections]
    studies = {key for finding in graph_findings if (key := study_key(finding))}
    normalized_finding_studies = {key for finding in findings if (key := study_key(finding))}
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
        "normalized_finding_study_count": len(normalized_finding_studies),
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
        represented_graph_keys = candidate_keys & studies
        represented_normalized_keys = candidate_keys & normalized_finding_studies
        not_in_graph_keys = candidate_keys - represented_graph_keys
        without_normalized_findings_keys = candidate_keys - represented_normalized_keys
        stats["graph_study_coverage"] = {
            "included_count": len(represented_graph_keys),
            "candidate_count": len(candidate_keys),
            "not_in_graph_count": len(not_in_graph_keys),
        }
        stats["normalized_finding_coverage"] = {
            "included_count": len(represented_normalized_keys),
            "candidate_count": len(candidate_keys),
            "without_findings_count": len(without_normalized_findings_keys),
        }
        stats["graph_candidate_study_count"] = len(candidate_keys)
        stats["graph_excluded_study_count"] = len(not_in_graph_keys)
    return stats


def source_type_token(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", normalize(value).lower()).strip("_")


def secondary_literature_source_key(finding: dict) -> str:
    explicit_tokens = {
        source_type_token(finding.get(field))
        for field in ("paper_type", "source_type")
        if source_type_token(finding.get(field))
    }
    if explicit_tokens & META_ANALYSIS_SOURCE_TYPES or any("meta_analysis" in token for token in explicit_tokens):
        return META_ANALYSES_SOURCE_KEY
    if explicit_tokens & REVIEW_SOURCE_TYPES or any("review" in token for token in explicit_tokens):
        return REVIEWS_SOURCE_KEY

    publication_token = source_type_token(finding.get("publication_type"))
    if publication_token in META_ANALYSIS_SOURCE_TYPES or "meta_analysis" in publication_token:
        return META_ANALYSES_SOURCE_KEY
    if publication_token in REVIEW_SOURCE_TYPES or "review" in publication_token:
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


def ui_dashboard_bootstrap_name(source_key: str) -> str:
    return f"dashboard_bootstrap_{source_key}.json"


def ui_detail_bootstrap_name(source_key: str) -> str:
    return f"detail_bootstrap_{source_key}.json"


OVERVIEW_PARENT_COLLAPSE_KINDS = {"pathway_process", "biomarker_readout", "intervention_component"}


def overview_graph_subjects(finding: dict) -> list[dict]:
    raw_subjects = finding.get("graph_overview_subjects_json")
    if isinstance(raw_subjects, str) and raw_subjects.strip():
        try:
            raw_subjects = json.loads(raw_subjects)
        except json.JSONDecodeError:
            raw_subjects = None
    subjects: list[dict] = []
    if isinstance(raw_subjects, list):
        for item in raw_subjects:
            if not isinstance(item, dict):
                continue
            label = normalize(item.get("label"))
            if not label:
                continue
            subjects.append(
                {
                    "label": label,
                    "kind": normalize(item.get("kind")) or "atomic_compound",
                    "reason": normalize(item.get("reason")),
                    "aliases": [
                        normalize(alias)
                        for alias in item.get("aliases", [])
                        if normalize(alias)
                    ],
                }
            )
    if subjects:
        return subjects

    exact_subject = normalize(finding.get("compound"))
    exact_subject_kind = normalize(finding.get("graph_subject_kind")) or "atomic_compound"
    subject = normalize(finding.get("graph_overview_subject_label"))
    subject_kind = normalize(finding.get("graph_overview_subject_kind"))
    if not subject and exact_subject_kind == "atomic_compound":
        subject = exact_subject
        subject_kind = exact_subject_kind
    if not subject:
        return []
    return [{"label": subject, "kind": subject_kind or exact_subject_kind, "reason": "legacy_singular_projection", "aliases": []}]


def overview_graph_projection(finding: dict, subject: dict | None = None) -> dict | None:
    subject = subject or next(iter(overview_graph_subjects(finding)), None)
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
    entity_aliases = finding.get("graph_parent_aliases", []) if used_parent else finding.get("entity_aliases", [])

    return {
        "finding": finding,
        "projection_type": "outcome",
        "relation_type": normalize(finding.get("relation_type")),
        "compound": subject["label"],
        "compound_aliases": list(subject.get("aliases", [])),
        "graph_subject_kind": subject["kind"],
        "entity_label": entity_label,
        "entity_kind": entity_kind,
        "entity_aliases": list(entity_aliases) if isinstance(entity_aliases, list) else [],
        "graph_parent_label": normalize(finding.get("graph_parent_label")),
        "graph_parent_kind": normalize(finding.get("graph_parent_kind")),
        "graph_parent_entity_id": normalize(finding.get("graph_parent_entity_id")),
        "used_parent": used_parent,
    }


def use_context_graph_projections(finding: dict) -> list[dict]:
    raw = finding.get("graph_use_context_projections_json")
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = None
    if not isinstance(raw, list):
        return []

    projections: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        subject_label = normalize(item.get("subject_label"))
        context_label = normalize(item.get("context_label"))
        if not subject_label or not context_label:
            continue
        projections.append(
            {
                "finding": finding,
                "projection_type": "use_context",
                "relation_type": normalize(item.get("relation_type")) or "reported_in_use_context",
                "compound": subject_label,
                "compound_aliases": [
                    normalize(alias)
                    for alias in item.get("subject_aliases", [])
                    if normalize(alias)
                ],
                "graph_subject_kind": normalize(item.get("subject_kind")) or "atomic_compound",
                "entity_label": context_label,
                "entity_kind": normalize(item.get("context_kind")) or "exposure_context",
                "entity_aliases": [
                    normalize(alias)
                    for alias in item.get("context_aliases", [])
                    if normalize(alias)
                ],
                "graph_parent_label": normalize(item.get("context_parent_label")),
                "graph_parent_kind": normalize(item.get("context_parent_kind")),
                "graph_parent_entity_id": normalize(item.get("context_parent_entity_id")),
                "used_parent": False,
            }
        )
    return projections


def overview_graph_projections(
    findings: list[dict], *, minimum_node_studies: int = MIN_OVERVIEW_NODE_STUDIES
) -> tuple[list[dict], dict[str, int]]:
    projected: list[dict] = []
    subject_studies: dict[tuple[str, str], set[str]] = {}
    entity_studies: dict[tuple[str, str], set[str]] = {}
    detail_only_subject_count = 0
    for finding in findings:
        if not is_graph_bootstrap_finding(finding):
            continue
        subjects = overview_graph_subjects(finding)
        finding_projections = [
            projection
            for subject in subjects
            if (projection := overview_graph_projection(finding, subject)) is not None
        ]
        finding_projections.extend(use_context_graph_projections(finding))
        if not finding_projections:
            detail_only_subject_count += 1
            continue
        for projection in finding_projections:
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
        if len(subject_studies.get(subject_key, set())) < minimum_node_studies:
            single_study_subject_finding_count += 1
            continue
        if len(entity_studies.get(entity_key, set())) < minimum_node_studies:
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
    edges: dict[tuple[str, str, str, str, str, str, str, str], dict] = {}
    minimum_node_studies = 1 if source_key == "meta_analyses" else MIN_OVERVIEW_NODE_STUDIES
    projected, projection_counts = overview_graph_projections(
        findings, minimum_node_studies=minimum_node_studies
    )
    graph_finding_count = 0
    for projection in projected:
        finding = projection["finding"]
        entity_label = projection["entity_label"]
        entity_kind = projection["entity_kind"]

        compound = projection["compound"]
        graph_subject_kind = projection["graph_subject_kind"]
        projection_type = normalize(projection.get("projection_type")) or "outcome"
        relation_type = normalize(projection.get("relation_type"))
        parent_label = normalize(projection.get("graph_parent_label"))
        parent_kind = normalize(projection.get("graph_parent_kind"))

        graph_finding_count += 1
        domain = normalize(finding.get("domain") or finding.get("kg_domain") or finding.get("finding_type"))
        key = (
            projection_type,
            relation_type,
            compound,
            graph_subject_kind,
            entity_kind,
            entity_label,
            parent_kind,
            parent_label,
        )
        entry = edges.setdefault(
            key,
            {
                "projection_type": projection_type,
                "relation_type": relation_type,
                "compound": compound,
                "compound_aliases": set(),
                "graph_subject_kind": graph_subject_kind,
                "entity_label": entity_label,
                "entity_kind": entity_kind,
                "entity_aliases": set(),
                "graph_parent_label": parent_label,
                "graph_parent_kind": parent_kind,
                "graph_parent_entity_id": normalize(projection.get("graph_parent_entity_id")),
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
        entry["compound_aliases"].update(projection.get("compound_aliases", []))
        entry["entity_aliases"].update(projection.get("entity_aliases", []))
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
        entry["compound_aliases"] = sorted(entry["compound_aliases"], key=str.casefold)
        entry["entity_aliases"] = sorted(entry["entity_aliases"], key=str.casefold)
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
            for key in (
                "id",
                "name",
                "credited_name",
                "aliases",
                "openalex_author_id",
                "openalex_author_ids",
                "orcid",
            )
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


def validate_public_browser_detail_contract() -> None:
    fields = list(PUBLIC_BROWSER_DETAIL_FIELDS)
    duplicates = sorted({field for field in fields if fields.count(field) > 1})
    if duplicates:
        raise ValueError(f"Duplicate public browser detail fields: {duplicates}")
    forbidden = sorted(set(fields) & FORBIDDEN_BROWSER_DETAIL_FIELDS)
    if forbidden:
        raise ValueError(
            "Forbidden internal fields were added to the public browser payload: "
            f"{forbidden}"
        )


def columnar_bootstrap_payload(
    findings: list[dict],
    generated_at: str,
    kg_dir: Path,
    source_key: str,
    *,
    schema_version: str,
    payload_scope: str | None = None,
) -> dict:
    validate_public_browser_detail_contract()
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
        rows.append(
            [value_index(finding.get(field)) for field in PUBLIC_BROWSER_DETAIL_FIELDS]
        )

    payload = {
        "schema_version": schema_version,
        "generated_at": generated_at,
        "evidence_source": "kg_tables",
        "kg_dir": relative_path(kg_dir),
        "literature_source": source_key,
        "source": source_key,
        "row_count": len(rows),
        "fields": list(PUBLIC_BROWSER_DETAIL_FIELDS),
        "values": values,
        "rows": rows,
    }
    if payload_scope:
        payload["payload_scope"] = payload_scope
    return payload


def dashboard_bootstrap_payload(findings: list[dict], generated_at: str, kg_dir: Path, source_key: str) -> dict:
    dashboard_findings = [
        finding
        for finding in findings
        if normalize(finding.get("entity_kind") or finding.get("kg_entity_kind")).lower()
        in DASHBOARD_BOOTSTRAP_ENTITY_KINDS
    ]
    payload = columnar_bootstrap_payload(
        dashboard_findings,
        generated_at,
        kg_dir,
        source_key,
        schema_version=DASHBOARD_BOOTSTRAP_SCHEMA_VERSION,
        payload_scope="initial_condition_dashboard",
    )
    payload["default_entity_view"] = "condition_indication"
    payload["source_row_count"] = len(findings)
    return payload


def detail_bootstrap_payload(findings: list[dict], generated_at: str, kg_dir: Path, source_key: str) -> dict:
    return columnar_bootstrap_payload(
        findings,
        generated_at,
        kg_dir,
        source_key,
        schema_version=DETAIL_BOOTSTRAP_SCHEMA_VERSION,
    )


def remove_stale_payload_files(out_dir: Path, keep_names: set[str]) -> None:
    for pattern in (
        "graph_payload_*.json",
        "graph_preview_*.json",
        "graph_bootstrap_*.json",
        "dashboard_bootstrap_*.json",
        "detail_bootstrap_*.json",
    ):
        for path in out_dir.glob(pattern):
            if path.name in keep_names:
                continue
            path.unlink()


def payload_file_entry(path: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": relative_path(path),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def write_active_pointer(
    active_json: Path,
    out_dir: Path,
    manifest_path: Path,
    graph_bootstrap_paths: dict[str, Path],
    dashboard_bootstrap_paths: dict[str, Path],
    detail_bootstrap_paths: dict[str, Path],
    kg_dir: Path,
) -> dict:
    payload = {
        "schema_version": ACTIVE_SCHEMA_VERSION,
        "active_graph_bootstraps": {source_key: relative_path(path) for source_key, path in graph_bootstrap_paths.items()},
        "active_dashboard_bootstraps": {
            source_key: relative_path(path) for source_key, path in dashboard_bootstrap_paths.items()
        },
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
    candidate_papers_table: Path | None = None,
    doi_alias_registry: Path | None = DEFAULT_DOI_ALIAS_REGISTRY,
    generated_at: str | None = None,
) -> dict:
    author_table_status = (
        validate_fresh_author_tables(kg_dir)
        if require_fresh_author_tables
        else {"status": "skipped", "reason": "freshness check disabled"}
    )
    findings = load_findings(
        kg_dir,
        require_author_identities=require_fresh_author_tables,
    )
    doi_aliases = load_doi_aliases(doi_alias_registry)
    candidate_study_key_sets = (
        load_selected_candidate_study_key_sets(candidate_papers_table, doi_aliases)
        if candidate_papers_table is not None
        else load_candidate_study_key_sets(kg_dir)
    )
    denominator_source = (
        "selected_candidate_corpus"
        if candidate_papers_table is not None and candidate_study_key_sets is not None
        else "kg_artifact_fallback"
    )
    candidate_study_keys = None if candidate_study_key_sets is None else candidate_study_key_sets["all"]
    stats = summary_stats(findings, candidate_study_keys)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = out_dir / manifest_name
    graph_bootstrap_paths = {
        source_key: out_dir / ui_graph_bootstrap_name(source_key)
        for source_key in UI_SOURCE_KEYS
    }
    dashboard_bootstrap_paths = {
        source_key: out_dir / ui_dashboard_bootstrap_name(source_key)
        for source_key in UI_SOURCE_KEYS
    }
    detail_bootstrap_paths = {
        source_key: out_dir / ui_detail_bootstrap_name(source_key)
        for source_key in UI_SOURCE_KEYS
    }
    keep_names = {manifest_path.name}
    keep_names.update(path.name for path in graph_bootstrap_paths.values())
    keep_names.update(path.name for path in dashboard_bootstrap_paths.values())
    keep_names.update(path.name for path in detail_bootstrap_paths.values())
    remove_stale_payload_files(out_dir, keep_names)

    generated_at = generated_at or now_utc()
    source_summary_stats: dict[str, dict] = {}
    for source_key in UI_SOURCE_KEYS:
        source_findings = findings_for_ui_source(findings, source_key)
        source_candidate_keys = None if candidate_study_key_sets is None else candidate_study_key_sets[source_key]
        minimum_node_studies = 1 if source_key == META_ANALYSES_SOURCE_KEY else MIN_OVERVIEW_NODE_STUDIES
        source_stats = summary_stats(
            source_findings,
            source_candidate_keys,
            minimum_node_studies=minimum_node_studies,
        )
        source_summary_stats[source_key] = source_stats
        graph_bootstrap = graph_bootstrap_payload(source_findings, generated_at, kg_dir, source_key)
        graph_bootstrap_paths[source_key].write_text(compact_json(graph_bootstrap), encoding="utf-8")
        dashboard_bootstrap = dashboard_bootstrap_payload(source_findings, generated_at, kg_dir, source_key)
        dashboard_bootstrap_paths[source_key].write_text(compact_json(dashboard_bootstrap), encoding="utf-8")
        detail_bootstrap = detail_bootstrap_payload(source_findings, generated_at, kg_dir, source_key)
        detail_bootstrap_paths[source_key].write_text(compact_json(detail_bootstrap), encoding="utf-8")

    overview_paper_counts = {
        "primary_studies": source_summary_stats[PRIMARY_SOURCE_KEY]["study_count"],
        "reviews": source_summary_stats[REVIEWS_SOURCE_KEY]["study_count"],
        "meta_analyses": source_summary_stats[META_ANALYSES_SOURCE_KEY]["study_count"],
    }
    overview_paper_counts["total"] = sum(overview_paper_counts.values())
    normalized_finding_paper_counts = {
        "primary_studies": source_summary_stats[PRIMARY_SOURCE_KEY]["normalized_finding_coverage"]["included_count"],
        "reviews": source_summary_stats[REVIEWS_SOURCE_KEY]["normalized_finding_coverage"]["included_count"],
        "meta_analyses": source_summary_stats[META_ANALYSES_SOURCE_KEY]["normalized_finding_coverage"]["included_count"],
    }
    normalized_finding_paper_counts["total"] = sum(normalized_finding_paper_counts.values())
    payload_files = {
        **{
            f"graph:{source_key}": payload_file_entry(path)
            for source_key, path in graph_bootstrap_paths.items()
        },
        **{
            f"dashboard:{source_key}": payload_file_entry(path)
            for source_key, path in dashboard_bootstrap_paths.items()
        },
        **{
            f"detail:{source_key}": payload_file_entry(path)
            for source_key, path in detail_bootstrap_paths.items()
        },
    }
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": generated_at,
        "evidence_source": "kg_tables",
        "kg_dir": relative_path(kg_dir),
        "graph_bootstraps": {source_key: relative_path(path) for source_key, path in graph_bootstrap_paths.items()},
        "dashboard_bootstraps": {
            source_key: relative_path(path) for source_key, path in dashboard_bootstrap_paths.items()
        },
        "detail_bootstraps": {source_key: relative_path(path) for source_key, path in detail_bootstrap_paths.items()},
        "release_id": "",
        "evidence_release_id": "",
        "files": payload_files,
        "row_count": len(findings),
        "author_tables": author_table_status,
        "browser_publication_contract": {
            "detail_schema_version": DETAIL_BOOTSTRAP_SCHEMA_VERSION,
            "default_private": True,
            "field_count": len(PUBLIC_BROWSER_DETAIL_FIELDS),
            "fields": list(PUBLIC_BROWSER_DETAIL_FIELDS),
        },
        "summary_stats": {
            "default": stats,
            "sources": source_summary_stats,
            "paper_counts": {
                **normalized_finding_paper_counts,
                "visualized_overview_represented": overview_paper_counts,
                "scope": "underlying_evidence_graph_represented",
                "denominator_source": denominator_source,
            },
        },
        "status": "ok",
    }
    if active_json:
        manifest["active_payload_pointer"] = write_active_pointer(
            active_json=active_json,
            out_dir=out_dir,
            manifest_path=manifest_path,
            graph_bootstrap_paths=graph_bootstrap_paths,
            dashboard_bootstrap_paths=dashboard_bootstrap_paths,
            detail_bootstrap_paths=detail_bootstrap_paths,
            kg_dir=kg_dir,
        )
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "graph_bootstrap_paths": graph_bootstrap_paths,
        "dashboard_bootstrap_paths": dashboard_bootstrap_paths,
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
        "--candidate-papers",
        default=str(DEFAULT_CANDIDATE_PAPERS_TABLE),
        help="Canonical selected-paper table used as the coverage denominator.",
    )
    parser.add_argument(
        "--doi-alias-registry",
        default=str(DEFAULT_DOI_ALIAS_REGISTRY),
        help="Registered DOI aliases used to reconcile candidate coverage with canonical graph papers.",
    )
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
    parser.add_argument(
        "--generated-at",
        default=None,
        help="Optional fixed ISO timestamp for reproducible release migrations.",
    )
    args = parser.parse_args()

    result = export_evidence_payload(
        kg_dir=Path(args.kg_dir).resolve(),
        out_dir=Path(args.out_dir).resolve(),
        manifest_name=args.manifest,
        active_json=Path(args.active_json).resolve() if args.activate_default else None,
        require_fresh_author_tables=not args.allow_stale_authors,
        candidate_papers_table=Path(args.candidate_papers).resolve(),
        doi_alias_registry=Path(args.doi_alias_registry).resolve(),
        generated_at=args.generated_at,
    )
    manifest = result["manifest"]
    print("Public evidence data: compact graph, dashboard, and detail bootstraps")
    print(f"Manifest: {result['manifest_path']}")
    if args.activate_default:
        print(f"Active payload pointer: {Path(args.active_json).resolve()}")
    print(f"Findings: {manifest['row_count']}")
    paper_counts = manifest["summary_stats"]["paper_counts"]
    print(f"Primary studies: {paper_counts['primary_studies']}")
    print(f"Reviews: {paper_counts['reviews']}")
    print(f"Meta-analyses: {paper_counts['meta_analyses']}")
    print(f"Total papers: {paper_counts['total']}")
    print("Status: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
