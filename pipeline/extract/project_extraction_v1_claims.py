#!/usr/bin/env python3
"""Project extraction-v1 outputs into graph-claim rows."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

try:
    from jsonschema import Draft7Validator
except ModuleNotFoundError as err:  # pragma: no cover - environment guard
    raise SystemExit("jsonschema is required for extraction-v1 projection") from err

try:
    from pipeline.extract.extraction_v1_utils import (
        find_context_for_result,
        load_pilot_contexts,
        normalize,
        normalize_doi,
        read_jsonl,
        result_with_endpoint_role_defaults,
        write_json,
    )
    from pipeline.fulltext.convert_pdfs import DATASET_CONFIG as PAPER_CONFIG, load_json_array
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.extraction_v1_utils import (
        find_context_for_result,
        load_pilot_contexts,
        normalize,
        normalize_doi,
        read_jsonl,
        result_with_endpoint_role_defaults,
        write_json,
    )
    from pipeline.fulltext.convert_pdfs import DATASET_CONFIG as PAPER_CONFIG, load_json_array


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "processed" / "extraction"
EXTRACTION_SCHEMA_PATH = ROOT / "schema" / "extraction_v1.schema.json"
SCHEMA_PATHS = {
    "mechanistic": ROOT / "schema" / "claims.schema.json",
    "disorder": ROOT / "schema" / "disorder_claims.schema.json",
}
PAPER_METADATA_FIELDS = [
    "study_journal",
    "publication_type",
    "trial_registry_ids",
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
]
MECHANISTIC_AFFINITY_TYPES = {"Ki", "Kd", "IC50", "EC50", "EC90", "Other"}
SECONDARY_RELATIONSHIP_DOMAINS = {"compound_target", "compound_disorder"}
OUTCOME_MEASURE_PATTERNS = [
    ("MADRS-SI", [r"\bmadrs\s*[- ]?\s*si\b"]),
    ("MADRS", [r"\bmadrs\b", r"montgomery\s+asberg", r"montgomery\s+asberg"]),
    ("HAM-D", [r"\bham\s*[- ]?\s*d\b", r"\bhdrs\b", r"hamilton\s+depression"]),
    ("PHQ-9", [r"\bphq\s*[- ]?\s*9\b", r"patient\s+health\s+questionnaire\s*[- ]?\s*9"]),
    ("BDI", [r"\bbdi\b", r"beck\s+depression\s+inventory"]),
    ("QIDS", [r"\bqids\b", r"quick\s+inventory\s+of\s+depressive"]),
    ("C-SSRS", [r"\bc\s*[- ]?\s*ssrs\b", r"columbia\s+suicide\s+severity"]),
    ("PCL-5", [r"\bpcl\s*[- ]?\s*5\b"]),
    ("PCL-6", [r"\bpcl\s*[- ]?\s*6\b"]),
    ("CAPS-5", [r"\bcaps\s*[- ]?\s*5\b", r"clinician\s+administered\s+ptsd"]),
    ("DASS-21", [r"\bdass\s*[- ]?\s*21\b", r"depression\s+anxiety\s+stress\s+scales?\s*[- ]?\s*21"]),
    ("BSI-18", [r"\bbsi\s*[- ]?\s*18\b", r"brief\s+symptom\s+inventory\s*[- ]?\s*18"]),
    ("WEMWBS", [r"\bwemwbs\b", r"warwick\s+edinburgh\s+mental\s+well\s+being"]),
    ("DPES", [r"\bdpes\b", r"dispositional\s+positive\s+emotion"]),
    ("SWLS", [r"\bswls?\b", r"satisfaction\s+with\s+life\s+scale"]),
    ("FFMQ-15", [r"\bffmq\s*[- ]?\s*15\b", r"five\s+facets?\s+mindfulness\s+questionnaire\s*[- ]?\s*15"]),
    ("SDS", [r"\bsds\b", r"sheehan\s+disability\s+scale"]),
    ("GAD-7", [r"\bgad\s*[- ]?\s*7\b", r"generalized\s+anxiety\s+disorder\s*[- ]?\s*7"]),
    ("HAM-A", [r"\bham\s*[- ]?\s*a\b", r"hamilton\s+anxiety"]),
    ("ISI", [r"\bisi\b", r"insomnia\s+severity\s+index"]),
    ("AUDIT", [r"\baudit\b", r"alcohol\s+use\s+disorders?\s+identification\s+test"]),
    ("TLFB", [r"\btlfb\b", r"timeline\s+follow\s*back"]),
    ("PANSS", [r"\bpanss\b", r"positive\s+and\s+negative\s+syndrome\s+scale"]),
    ("BPRS", [r"\bbprs\b", r"brief\s+psychiatric\s+rating\s+scale"]),
    ("STAI", [r"\bstai\b", r"state\s+trait\s+anxiety\s+inventory"]),
]
NON_ARTICLE_PUBLICATION_RE = re.compile(
    r"\b(peer[- ]?review|editor[- ]?report|decision[- ]?letter|author[- ]?response|correction|erratum|retraction)\b",
    re.I,
)
NON_ARTICLE_TITLE_RE = re.compile(r"^\s*(decision letter|author response|editor(?:'s)? report|correction|erratum|retraction)\b", re.I)
IN_SCOPE_COMPOUND_RE = re.compile(
    r"(?i)\b("
    r"lsd|lysergic acid diethylamide|psilocybin|psilocin|"
    r"dmt|5[- ]?meo[- ]?dmt|mescaline|"
    r"mdma|methylenedioxymethamphetamine|mda|"
    r"ketamine|esketamine|arketamine|s[- ]?ketamine|r[- ]?ketamine|"
    r"norketamine|hydroxynorketamine|"
    r"ibogaine|noribogaine|"
    r"salvinorin|"
    r"doi|dob|dom|"
    r"2,?5[- ]?dimethoxy[- ]?4[- ]?iodoamphetamine|"
    r"2,?5[- ]?dimethoxy[- ]?4[- ]?iodophenyl"
    r")\b"
)
MECHANISTIC_CSV_ORDER = [
    "claim_type",
    "compound",
    "target",
    "raw_entity_label",
    "entity_role",
    "clinical_context_condition",
    "graph_entity_label",
    "graph_entity_type",
    "graph_include_candidate",
    "graph_exclusion_reason",
    "mechanism_type",
    "assay_type",
    "assay_family",
    "action_type",
    "affinity_type",
    "affinity_value",
    "affinity_unit",
    "result_direction",
    "species",
    "model_or_system",
    "system",
    "study_doi",
    "openalex_id",
    "study_title",
    "authors",
    "study_year",
    *PAPER_METADATA_FIELDS,
    "paper_type",
    "evidence_level",
    "source",
    "source_type",
    "source_family",
    "paper_assessment_route",
    "evidence_strength",
    "support",
    "confidence",
    "needs_human_review",
    "access_level",
    "source_access_level",
    "evidence_location",
    "evidence_locator",
    "study_design",
    "sample_size_total",
    "sample_size_by_arm",
    "comparator",
    "intervention_or_exposure",
    "dose",
    "route",
    "session_count_or_duration",
    "primary_outcome",
    "outcome_measure",
    "timepoint",
    "effect_size",
    "p_value",
    "confidence_interval",
    "adverse_events",
    "supporting_quote",
    "funding",
    "conflicts_of_interest",
    "risk_of_bias_summary",
    "notes",
]
DISORDER_CSV_ORDER = [
    "claim_type",
    "compound",
    "disorder",
    "raw_entity_label",
    "entity_role",
    "clinical_context_condition",
    "graph_entity_label",
    "graph_entity_type",
    "graph_include_candidate",
    "graph_exclusion_reason",
    "outcome_type",
    "outcome_domain",
    "result_direction",
    "outcome_measure",
    "outcome_measure_normalized",
    "population",
    "system",
    "study_doi",
    "openalex_id",
    "study_title",
    "authors",
    "study_year",
    *PAPER_METADATA_FIELDS,
    "paper_type",
    "evidence_level",
    "source",
    "source_type",
    "source_family",
    "paper_assessment_route",
    "evidence_strength",
    "support",
    "confidence",
    "needs_human_review",
    "access_level",
    "source_access_level",
    "evidence_location",
    "evidence_locator",
    "study_design",
    "sample_size_total",
    "comparator",
    "intervention_or_exposure",
    "dose",
    "route",
    "session_count_or_duration",
    "timepoint",
    "effect_size",
    "p_value",
    "confidence_interval",
    "adverse_events",
    "supporting_quote",
    "funding",
    "conflicts_of_interest",
    "risk_of_bias_summary",
    "notes",
]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def ascii_fold(value: object) -> str:
    text = normalize(value)
    text = unicodedata.normalize("NFKD", text)
    return text.encode("ascii", "ignore").decode("ascii")


def normalize_outcome_measure(value: object) -> str:
    text = ascii_fold(value).casefold()
    if not text or text in {"not_reported", "not reported", "not_applicable", "not applicable", "unknown"}:
        return ""
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    labels: list[str] = []
    for label, patterns in OUTCOME_MEASURE_PATTERNS:
        if any(re.search(pattern, text) for pattern in patterns):
            if label == "MADRS" and "MADRS-SI" in labels:
                continue
            labels.append(label)

    seen: set[str] = set()
    out: list[str] = []
    for label in labels:
        if label in seen:
            continue
        seen.add(label)
        out.append(label)
    return "; ".join(out)


def rows_by_doi(rows: list[dict]) -> dict[str, dict]:
    out = {}
    for row in rows:
        doi = normalize_doi(row.get("study_doi", ""))
        if doi:
            out[doi] = row
    return out


def pilot_metadata_for_result(result: dict, contexts: dict[tuple[str, str], dict]) -> dict:
    item = find_context_for_result(result, contexts) if contexts else {}
    record = item.get("pilot_record", {}) if isinstance(item.get("pilot_record"), dict) else {}
    metadata = record.get("paper_metadata", {}) if isinstance(record.get("paper_metadata"), dict) else {}
    return metadata


def metadata_for_result(result: dict, paper_libraries: dict[str, dict[str, dict]], contexts: dict[tuple[str, str], dict]) -> dict:
    dataset = normalize(result.get("dataset", ""))
    doi = normalize_doi(result.get("study_doi", ""))
    metadata = {}
    metadata.update(paper_libraries.get(dataset, {}).get(doi, {}))
    metadata.update({k: v for k, v in pilot_metadata_for_result(result, contexts).items() if normalize(v)})
    metadata["study_doi"] = doi or normalize_doi(metadata.get("study_doi", ""))
    metadata["openalex_id"] = normalize(result.get("openalex_id", "")) or normalize(metadata.get("openalex_id", ""))
    return metadata


def pilot_record_for_result(result: dict, contexts: dict[tuple[str, str], dict]) -> dict:
    item = find_context_for_result(result, contexts) if contexts else {}
    record = item.get("pilot_record", {}) if isinstance(item.get("pilot_record"), dict) else {}
    return record


def is_prior_irrelevant_control(result: dict, contexts: dict[tuple[str, str], dict]) -> bool:
    record = pilot_record_for_result(result, contexts)
    return (
        normalize(record.get("bucket", "")) == "abstract_irrelevant"
        or normalize(record.get("expected_screening_relevance", "")).lower() == "irrelevant"
    )


def is_non_article_artifact(metadata: dict, assessment: dict | None = None) -> bool:
    assessment = assessment or {}
    publication_type = normalize(metadata.get("publication_type", ""))
    title = normalize(metadata.get("study_title", "")) or normalize(metadata.get("title", ""))
    paper_type = normalize(assessment.get("paper_type", ""))
    source_type = normalize(assessment.get("source_type", ""))
    return (
        bool(NON_ARTICLE_PUBLICATION_RE.search(publication_type))
        or bool(NON_ARTICLE_TITLE_RE.search(title))
        or bool(NON_ARTICLE_PUBLICATION_RE.search(paper_type))
        or bool(NON_ARTICLE_PUBLICATION_RE.search(source_type))
    )


def is_in_scope_projected_compound(value: object) -> bool:
    return bool(IN_SCOPE_COMPOUND_RE.search(normalize(value)))


def parse_int(value: object) -> int | str:
    text = normalize(value)
    if not text:
        return ""
    try:
        return int(float(text))
    except Exception:
        return text


def parse_float(value: object) -> float | None:
    text = normalize(value)
    if not text or text == "not_reported":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def reported_text(value: object) -> str:
    text = normalize(value)
    empty_values = {
        "not_reported",
        "not reported",
        "not_applicable",
        "not applicable",
        "unknown",
        "n/a",
        "na",
    }
    return "" if text.lower() in empty_values else text


def numeric_or_reported_text(value: object) -> float | str:
    parsed = parse_float(value)
    return parsed if parsed is not None else reported_text(value)


def confidence_value(value: object) -> float:
    parsed = parse_float(value)
    if parsed is None:
        return 0.0
    return max(0.0, min(1.0, parsed))


def bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = normalize(value).lower()
    return text in {"true", "1", "yes", "y"}


def mechanism_type_for_claim(claim: dict) -> str:
    return (
        reported_text(claim.get("action_type", ""))
        or reported_text(claim.get("assay_family", ""))
        or reported_text(claim.get("assay_type", ""))
        or reported_text(claim.get("affinity_type", ""))
        or "target interaction"
    )


def dataset_for_claim(claim: dict) -> str:
    claim_type = normalize(claim.get("claim_type", ""))
    if claim_type == "compound_target":
        return "mechanistic"
    if claim_type == "compound_disorder":
        return "disorder"
    return ""


def legacy_evidence_level(dataset: str, assessment: dict, claim: dict) -> str:
    design = normalize(claim.get("study_design", "") or assessment.get("study_design", "")).lower()
    if dataset == "mechanistic":
        return "high" if parse_float(claim.get("affinity_value", "")) is not None else "medium"
    if any(marker in design for marker in ["randomized", "phase_3", "phase 3"]):
        return "high"
    if any(marker in design for marker in ["open_label", "open label", "phase_2", "phase 2", "pilot"]):
        return "medium"
    return "low"


def secondary_paper_type(assessment: dict) -> str:
    paper_type = normalize(assessment.get("paper_type", ""))
    if paper_type in {
        "systematic_review",
        "meta_analysis",
        "scoping_review",
        "review",
        "guideline",
        "editorial",
        "consensus",
        "commentary",
        "protocol",
        "correction",
        "erratum",
        "conference_abstract",
        "conference_or_poster_abstract",
        "other",
        "uncertain",
    }:
        return paper_type
    return "review"


def secondary_source_type(assessment: dict) -> str:
    source_type = normalize(assessment.get("source_type", ""))
    if source_type in {
        "secondary_evidence",
        "systematic_review",
        "review",
        "meta_analysis",
        "scoping_review",
        "commentary",
        "guideline",
        "editorial",
        "consensus",
        "study_protocol",
        "correction",
        "conference_abstract",
        "other",
        "uncertain",
    }:
        return source_type
    return "secondary_evidence"


def common_fields(result: dict, claim: dict, metadata: dict) -> dict:
    assessment = result.get("paper_assessment", {}) if isinstance(result.get("paper_assessment"), dict) else {}
    study_doi = normalize_doi(result.get("study_doi", "")) or normalize_doi(metadata.get("study_doi", ""))
    openalex_id = normalize(result.get("openalex_id", "")) or normalize(metadata.get("openalex_id", ""))
    study_design = reported_text(claim.get("study_design", "")) or reported_text(assessment.get("study_design", ""))
    row = {
        "study_title": normalize(metadata.get("study_title", "")),
        "authors": normalize(metadata.get("authors", "")) or "Unknown authors",
        "study_year": parse_int(metadata.get("study_year", "")),
        "paper_type": normalize(assessment.get("paper_type", "")),
        "source": "doi" if study_doi else "openalex",
        "source_type": normalize(assessment.get("source_type", "")),
        "source_family": normalize(assessment.get("source_family", "")),
        "paper_assessment_route": normalize(assessment.get("route", "")),
        "evidence_strength": "uncertain",
        "support": normalize(claim.get("support", "")) or "uncertain",
        "confidence": confidence_value(claim.get("confidence", "")),
        "needs_human_review": claim.get("needs_human_review") is True,
        "supporting_quote": normalize(claim.get("supporting_quote", "")),
        "access_level": normalize(result.get("access_level", "")),
        "source_access_level": normalize(result.get("access_level", "")),
        "evidence_location": normalize(claim.get("evidence_location", "")),
        "evidence_locator": normalize(claim.get("evidence_locator", "")),
        "study_design": study_design or "not_reported",
        "funding": reported_text(assessment.get("funding", "")),
        "conflicts_of_interest": reported_text(assessment.get("conflicts_of_interest", "")),
        "risk_of_bias_summary": reported_text(assessment.get("risk_of_bias_summary", "")),
        "notes": (
            "Projected from extraction_v1; "
            f"support={normalize(claim.get('support', ''))}; "
            f"confidence={normalize(claim.get('confidence', ''))}; "
            f"needs_human_review={normalize(claim.get('needs_human_review', ''))}"
        ),
    }
    if study_doi:
        row["study_doi"] = study_doi
    elif openalex_id:
        row["openalex_id"] = openalex_id
    for field in PAPER_METADATA_FIELDS:
        value = reported_text(metadata.get(field, ""))
        if value:
            row[field] = value
    trial_registry_ids = reported_text(assessment.get("trial_registry_ids", ""))
    if trial_registry_ids:
        row["trial_registry_ids"] = trial_registry_ids
    return row


def common_secondary_fields(result: dict, mention: dict, metadata: dict) -> dict:
    assessment = result.get("paper_assessment", {}) if isinstance(result.get("paper_assessment"), dict) else {}
    row = common_fields(result, mention, metadata)
    coverage_type = normalize(mention.get("coverage_type", ""))
    row.update(
        {
            "paper_type": secondary_paper_type(assessment),
            "source_type": secondary_source_type(assessment),
            "source_family": normalize(assessment.get("source_family", "")) or "evidence_synthesis",
            "paper_assessment_route": "secondary_literature",
            "evidence_strength": "uncertain",
            "evidence_level": "low",
            "support": "uncertain",
            "access_level": "secondary_summary",
            "study_design": reported_text(assessment.get("study_design", "")) or "secondary_literature",
            "notes": (
                "Projected from extraction_v1 coverage_mentions; "
                f"coverage_type={coverage_type}; "
                "relationship is discussed in secondary literature, not treated as primary evidence"
            ),
        }
    )
    return row


def mechanistic_row(result: dict, claim: dict, metadata: dict) -> tuple[dict | None, str]:
    if normalize(claim.get("claim_type", "")) != "compound_target":
        return None, f"unsupported mechanistic claim_type={normalize(claim.get('claim_type', ''))}"
    affinity_type = normalize(claim.get("affinity_type", ""))
    if affinity_type.lower() in {"not_reported", "not_applicable"}:
        affinity_type = "Other" if reported_text(claim.get("affinity_value", "")) or reported_text(claim.get("affinity_unit", "")) else ""
    elif affinity_type and affinity_type not in MECHANISTIC_AFFINITY_TYPES:
        affinity_type = "Other"
    assessment = result.get("paper_assessment", {}) if isinstance(result.get("paper_assessment"), dict) else {}
    row = {
        "claim_type": "compound_target",
        "compound": normalize(claim.get("compound", "")),
        "target": normalize(claim.get("target", "")),
        "raw_entity_label": normalize(claim.get("raw_entity_label", "")),
        "entity_role": normalize(claim.get("entity_role", "")),
        "clinical_context_condition": normalize(claim.get("clinical_context_condition", "")),
        "graph_entity_label": normalize(claim.get("graph_entity_label", "")),
        "graph_entity_type": normalize(claim.get("graph_entity_type", "")),
        "graph_include_candidate": bool_value(claim.get("graph_include_candidate", False)),
        "graph_exclusion_reason": normalize(claim.get("graph_exclusion_reason", "")),
        "mechanism_type": mechanism_type_for_claim(claim),
        "assay_type": reported_text(claim.get("assay_type", "")) or reported_text(claim.get("assay_family", "")),
        "assay_family": reported_text(claim.get("assay_family", "")),
        "action_type": reported_text(claim.get("action_type", "")),
        "affinity_type": affinity_type,
        "affinity_value": numeric_or_reported_text(claim.get("affinity_value", "")),
        "affinity_unit": reported_text(claim.get("affinity_unit", "")),
        "result_direction": normalize(claim.get("result_direction", "")) or "not_applicable",
        "species": normalize(claim.get("species", "")),
        "model_or_system": normalize(claim.get("model_or_system", "")),
        "system": normalize(claim.get("system", "")) or normalize(assessment.get("system", "")),
        **common_fields(result, claim, metadata),
        "sample_size_total": normalize(claim.get("sample_size_total", "")),
        "sample_size_by_arm": normalize(claim.get("sample_size_by_arm", "")),
        "comparator": normalize(claim.get("comparator", "")),
        "intervention_or_exposure": normalize(claim.get("intervention_or_exposure", "")),
        "dose": normalize(claim.get("dose", "")),
        "route": normalize(claim.get("route", "")),
        "session_count_or_duration": normalize(claim.get("session_count_or_duration", "")),
        "primary_outcome": normalize(claim.get("primary_outcome", "")),
        "outcome_measure": normalize(claim.get("outcome_measure", "")),
        "timepoint": normalize(claim.get("timepoint", "")),
        "effect_size": normalize(claim.get("effect_size", "")),
        "p_value": normalize(claim.get("p_value", "")),
        "confidence_interval": normalize(claim.get("confidence_interval", "")),
        "adverse_events": normalize(claim.get("adverse_events", "")),
    }
    row["evidence_level"] = legacy_evidence_level("mechanistic", assessment, claim)
    return row, ""


def mechanistic_secondary_row(result: dict, mention: dict, metadata: dict) -> tuple[dict | None, str]:
    if normalize(mention.get("relationship_domain", "")) != "compound_target":
        return None, f"unsupported mechanistic coverage relationship_domain={normalize(mention.get('relationship_domain', ''))}"
    if normalize(mention.get("entity_type", "")) != "target":
        return None, f"unsupported mechanistic coverage entity_type={normalize(mention.get('entity_type', ''))}"
    compound = normalize(mention.get("compound", ""))
    target = normalize(mention.get("entity", ""))
    if not compound or not target:
        return None, "coverage mention lacks compound or target"
    row = {
        "claim_type": "compound_target",
        "compound": compound,
        "target": target,
        "raw_entity_label": target,
        "entity_role": "molecular_target",
        "clinical_context_condition": "",
        "graph_entity_label": target,
        "graph_entity_type": "target",
        "graph_include_candidate": True,
        "graph_exclusion_reason": "",
        "mechanism_type": "secondary literature coverage",
        "assay_type": "",
        "assay_family": "",
        "action_type": "",
        "affinity_type": "",
        "affinity_value": "",
        "affinity_unit": "",
        "result_direction": "not_applicable",
        "species": "",
        "model_or_system": "",
        "system": "unknown",
        **common_secondary_fields(result, mention, metadata),
    }
    return row, ""


def disorder_row(result: dict, claim: dict, metadata: dict) -> tuple[dict | None, str]:
    if normalize(claim.get("claim_type", "")) != "compound_disorder":
        return None, f"unsupported disorder claim_type={normalize(claim.get('claim_type', ''))}"
    assessment = result.get("paper_assessment", {}) if isinstance(result.get("paper_assessment"), dict) else {}
    row = {
        "claim_type": "compound_disorder",
        "compound": normalize(claim.get("compound", "")),
        "disorder": normalize(claim.get("disorder", "")),
        "raw_entity_label": normalize(claim.get("raw_entity_label", "")),
        "entity_role": normalize(claim.get("entity_role", "")),
        "clinical_context_condition": normalize(claim.get("clinical_context_condition", "")),
        "graph_entity_label": normalize(claim.get("graph_entity_label", "")),
        "graph_entity_type": normalize(claim.get("graph_entity_type", "")),
        "graph_include_candidate": bool_value(claim.get("graph_include_candidate", False)),
        "graph_exclusion_reason": normalize(claim.get("graph_exclusion_reason", "")),
        "outcome_type": normalize(claim.get("outcome_type", "")),
        "outcome_domain": normalize(claim.get("outcome_domain", "")),
        "result_direction": normalize(claim.get("result_direction", "")),
        "outcome_measure": normalize(claim.get("outcome_measure", "")),
        "outcome_measure_normalized": normalize_outcome_measure(claim.get("outcome_measure", "")),
        "population": normalize(claim.get("population", "")),
        "system": normalize(claim.get("system", "")) or normalize(assessment.get("system", "")),
        **common_fields(result, claim, metadata),
        "sample_size_total": normalize(claim.get("sample_size_total", "")),
        "comparator": normalize(claim.get("comparator", "")),
        "intervention_or_exposure": normalize(claim.get("intervention_or_exposure", "")),
        "dose": normalize(claim.get("dose", "")),
        "route": normalize(claim.get("route", "")),
        "session_count_or_duration": normalize(claim.get("session_count_or_duration", "")),
        "timepoint": normalize(claim.get("timepoint", "")),
        "effect_size": normalize(claim.get("effect_size", "")),
        "p_value": normalize(claim.get("p_value", "")),
        "confidence_interval": normalize(claim.get("confidence_interval", "")),
        "adverse_events": normalize(claim.get("adverse_events", "")),
    }
    row["evidence_level"] = legacy_evidence_level("disorder", assessment, claim)
    return row, ""


def disorder_secondary_row(result: dict, mention: dict, metadata: dict) -> tuple[dict | None, str]:
    if normalize(mention.get("relationship_domain", "")) != "compound_disorder":
        return None, f"unsupported disorder coverage relationship_domain={normalize(mention.get('relationship_domain', ''))}"
    if normalize(mention.get("entity_type", "")) != "disorder":
        return None, f"unsupported disorder coverage entity_type={normalize(mention.get('entity_type', ''))}"
    compound = normalize(mention.get("compound", ""))
    disorder = normalize(mention.get("entity", ""))
    if not compound or not disorder:
        return None, "coverage mention lacks compound or disorder"
    row = {
        "claim_type": "compound_disorder",
        "compound": compound,
        "disorder": disorder,
        "raw_entity_label": disorder,
        "entity_role": "therapeutic_indication",
        "clinical_context_condition": "",
        "graph_entity_label": disorder,
        "graph_entity_type": "indication",
        "graph_include_candidate": True,
        "graph_exclusion_reason": "",
        "outcome_type": "secondary literature coverage",
        "outcome_domain": "",
        "result_direction": "unclear",
        "outcome_measure": "",
        "outcome_measure_normalized": "",
        "population": "",
        "system": "unknown",
        **common_secondary_fields(result, mention, metadata),
    }
    return row, ""


def project_results(
    results: list[dict],
    paper_libraries: dict[str, dict[str, dict]],
    contexts: dict[tuple[str, str], dict],
    result_indexes: list[int] | None = None,
    include_irrelevant_controls: bool = False,
) -> tuple[dict[str, list[dict]], list[dict]]:
    rows_by_dataset = {"mechanistic": [], "disorder": []}
    skipped = []
    for position, result in enumerate(results, start=1):
        result_index = result_indexes[position - 1] if result_indexes else position
        if not include_irrelevant_controls and is_prior_irrelevant_control(result, contexts):
            skipped.append({"row_index": result_index, "reason": "prior irrelevant screening control is not projected"})
            continue
        assessment = result.get("paper_assessment", {}) if isinstance(result.get("paper_assessment"), dict) else {}
        dataset = normalize(result.get("dataset", ""))
        if dataset not in rows_by_dataset:
            skipped.append({"row_index": result_index, "reason": f"unsupported dataset {dataset}"})
            continue
        metadata = metadata_for_result(result, paper_libraries, contexts)
        if is_non_article_artifact(metadata, assessment):
            skipped.append({"row_index": result_index, "reason": "non-article artifact is not projected"})
            continue
        if normalize(assessment.get("route", "")) != "primary_evidence":
            skipped.append({"row_index": result_index, "reason": f"route {normalize(assessment.get('route', ''))} is not projected"})
            continue
        claims = result.get("claims", []) if isinstance(result.get("claims"), list) else []
        for claim_index, claim in enumerate(claims):
            if not isinstance(claim, dict):
                skipped.append({"row_index": result_index, "claim_index": claim_index, "reason": "claim is not an object"})
                continue
            claim_dataset = dataset_for_claim(claim)
            if claim_dataset not in rows_by_dataset:
                skipped.append({"row_index": result_index, "claim_index": claim_index, "reason": f"unsupported claim_type={normalize(claim.get('claim_type', ''))}"})
                continue
            row, reason = mechanistic_row(result, claim, metadata) if claim_dataset == "mechanistic" else disorder_row(result, claim, metadata)
            if row is None:
                skipped.append({"row_index": result_index, "claim_index": claim_index, "reason": reason})
                continue
            rows_by_dataset[claim_dataset].append(row)
    return rows_by_dataset, skipped


def project_secondary_coverage(
    results: list[dict],
    paper_libraries: dict[str, dict[str, dict]],
    contexts: dict[tuple[str, str], dict],
    result_indexes: list[int] | None = None,
    include_irrelevant_controls: bool = False,
) -> tuple[dict[str, list[dict]], list[dict]]:
    rows_by_dataset = {"mechanistic": [], "disorder": []}
    skipped = []
    for position, result in enumerate(results, start=1):
        result_index = result_indexes[position - 1] if result_indexes else position
        if not include_irrelevant_controls and is_prior_irrelevant_control(result, contexts):
            continue
        assessment = result.get("paper_assessment", {}) if isinstance(result.get("paper_assessment"), dict) else {}
        if normalize(assessment.get("route", "")) != "secondary_literature":
            continue
        dataset = normalize(result.get("dataset", ""))
        if dataset not in rows_by_dataset:
            skipped.append({"row_index": result_index, "reason": f"unsupported dataset {dataset}"})
            continue
        metadata = metadata_for_result(result, paper_libraries, contexts)
        if is_non_article_artifact(metadata, assessment):
            skipped.append({"row_index": result_index, "reason": "non-article artifact is not projected"})
            continue
        mentions = result.get("coverage_mentions", []) if isinstance(result.get("coverage_mentions"), list) else []
        for mention_index, mention in enumerate(mentions):
            if not isinstance(mention, dict):
                skipped.append({"row_index": result_index, "mention_index": mention_index, "reason": "coverage mention is not an object"})
                continue
            domain = normalize(mention.get("relationship_domain", ""))
            if domain not in SECONDARY_RELATIONSHIP_DOMAINS:
                skipped.append({"row_index": result_index, "mention_index": mention_index, "reason": f"coverage relationship_domain {domain} is not projected"})
                continue
            row, reason = (
                mechanistic_secondary_row(result, mention, metadata)
                if domain == "compound_target"
                else disorder_secondary_row(result, mention, metadata)
            )
            if row is None:
                skipped.append({"row_index": result_index, "mention_index": mention_index, "reason": reason})
                continue
            row_dataset = dataset_for_claim(row)
            rows_by_dataset[row_dataset].append(row)
    return rows_by_dataset, skipped


def schema_errors_for_rows(dataset: str, rows: list[dict]) -> list[dict]:
    schema_path = SCHEMA_PATHS[dataset]
    with schema_path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    validator = Draft7Validator(schema)
    errors = []
    for error in sorted(validator.iter_errors(rows), key=lambda item: list(item.path)):
        errors.append(
            {
                "dataset": dataset,
                "path": ".".join(str(part) for part in error.path),
                "message": error.message,
            }
        )
    return errors


def extraction_schema_errors_for_results(results: list[dict]) -> list[dict]:
    with EXTRACTION_SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    validator = Draft7Validator(schema)
    errors = []
    for index, result in enumerate(results, start=1):
        normalized_result, _changes = result_with_endpoint_role_defaults(result)
        for error in sorted(validator.iter_errors(normalized_result), key=lambda item: list(item.path)):
            errors.append(
                {
                    "row_index": index,
                    "path": ".".join(str(part) for part in error.path),
                    "message": error.message,
                }
            )
    return errors


def invalid_input_indexes(errors: list[dict]) -> set[int]:
    return {int(error["row_index"]) for error in errors if str(error.get("row_index", "")).isdigit()}


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def output_stem(dataset: str, prefix: str) -> str:
    clean_prefix = normalize(prefix)
    return f"{clean_prefix}_{dataset}_claims" if clean_prefix else f"{dataset}_claims"


def secondary_output_stem(dataset: str, prefix: str) -> str:
    clean_prefix = normalize(prefix)
    return f"{clean_prefix}_{dataset}_secondary_claims" if clean_prefix else f"{dataset}_secondary_claims"


def report_filename(prefix: str) -> str:
    clean_prefix = normalize(prefix)
    return f"{clean_prefix}_projection_report.json" if clean_prefix else "projection_report.json"


def load_paper_libraries() -> dict[str, dict[str, dict]]:
    return {
        dataset: rows_by_doi(load_json_array(cfg["paper_db_json"]))
        for dataset, cfg in PAPER_CONFIG.items()
        if dataset in {"mechanistic", "disorder"}
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Project extraction-v1 outputs into graph claim rows")
    parser.add_argument("--input-jsonl", required=True, help="Extraction-v1 output JSONL")
    parser.add_argument("--pilot-input-jsonl", default="", help="Optional pilot/input JSONL for metadata lookup")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--prefix",
        default="",
        help="Optional output filename prefix. Empty default writes mechanistic_claims/disorder_claims.",
    )
    parser.add_argument(
        "--include-irrelevant-controls",
        action="store_true",
        help="Project records that came from old irrelevant-control pilot buckets; disabled by default",
    )
    args = parser.parse_args()

    input_jsonl = Path(args.input_jsonl).resolve()
    out_dir = Path(args.out_dir).resolve()
    results = read_jsonl(input_jsonl)
    contexts = load_pilot_contexts(Path(args.pilot_input_jsonl).resolve()) if args.pilot_input_jsonl else {}
    input_schema_errors = extraction_schema_errors_for_results(results)
    invalid_indexes = invalid_input_indexes(input_schema_errors)
    valid_result_indexes = [index for index in range(1, len(results) + 1) if index not in invalid_indexes]
    valid_results = [result for index, result in enumerate(results, start=1) if index not in invalid_indexes]
    rows_by_dataset, skipped = project_results(
        valid_results,
        paper_libraries := load_paper_libraries(),
        contexts,
        valid_result_indexes,
        include_irrelevant_controls=args.include_irrelevant_controls,
    )
    secondary_rows_by_dataset, secondary_skipped = project_secondary_coverage(
        valid_results,
        paper_libraries,
        contexts,
        valid_result_indexes,
        include_irrelevant_controls=args.include_irrelevant_controls,
    )
    skipped.extend(
        {"row_index": index, "reason": "input extraction_v1 schema validation failed"}
        for index in sorted(invalid_indexes)
    )
    schema_errors = []
    outputs = {}
    for dataset, rows in rows_by_dataset.items():
        stem = output_stem(dataset, args.prefix)
        json_path = out_dir / f"{stem}.json"
        csv_path = out_dir / f"{stem}.csv"
        write_json(json_path, rows)
        write_csv(csv_path, rows, MECHANISTIC_CSV_ORDER if dataset == "mechanistic" else DISORDER_CSV_ORDER)
        outputs[dataset] = {"json": str(json_path), "csv": str(csv_path), "rows": len(rows)}
        schema_errors.extend(schema_errors_for_rows(dataset, rows))
        secondary_stem = secondary_output_stem(dataset, args.prefix)
        secondary_json_path = out_dir / f"{secondary_stem}.json"
        secondary_csv_path = out_dir / f"{secondary_stem}.csv"
        secondary_rows = secondary_rows_by_dataset[dataset]
        write_json(secondary_json_path, secondary_rows)
        write_csv(secondary_csv_path, secondary_rows, MECHANISTIC_CSV_ORDER if dataset == "mechanistic" else DISORDER_CSV_ORDER)
        outputs[dataset]["secondary_json"] = str(secondary_json_path)
        outputs[dataset]["secondary_csv"] = str(secondary_csv_path)
        outputs[dataset]["secondary_rows"] = len(secondary_rows)
        schema_errors.extend(schema_errors_for_rows(dataset, secondary_rows))

    report = {
        "generated_at_utc": now_utc(),
        "schema_version": "extraction_v1_projection_report",
        "status": "ok" if not schema_errors and not input_schema_errors else "schema_errors",
        "inputs": {
            "input_jsonl": str(input_jsonl),
            "pilot_input_jsonl": str(Path(args.pilot_input_jsonl).resolve()) if args.pilot_input_jsonl else "",
            "include_irrelevant_controls": args.include_irrelevant_controls,
        },
        "outputs": outputs,
        "summary": {
            "input_results": len(results),
            "valid_input_results": len(valid_results),
            "input_schema_errors": len(input_schema_errors),
            "projected_rows": sum(len(rows) for rows in rows_by_dataset.values()),
            "projected_by_dataset": {dataset: len(rows) for dataset, rows in rows_by_dataset.items()},
            "secondary_rows": sum(len(rows) for rows in secondary_rows_by_dataset.values()),
            "secondary_by_dataset": {dataset: len(rows) for dataset, rows in secondary_rows_by_dataset.items()},
            "skipped": len(skipped),
            "skipped_reasons": dict(Counter(item["reason"] for item in skipped)),
            "secondary_skipped": len(secondary_skipped),
            "secondary_skipped_reasons": dict(Counter(item["reason"] for item in secondary_skipped)),
            "schema_errors": len(schema_errors),
        },
        "skipped": skipped[:500],
        "secondary_skipped": secondary_skipped[:500],
        "input_schema_errors": input_schema_errors[:500],
        "schema_errors": schema_errors[:500],
    }
    report_path = out_dir / report_filename(args.prefix)
    write_json(report_path, report)
    print(f"Valid input results: {report['summary']['valid_input_results']} / {report['summary']['input_results']}")
    print(f"Input schema errors: {report['summary']['input_schema_errors']}")
    print(f"Projected rows: {report['summary']['projected_rows']}")
    print(f"Projected by dataset: {report['summary']['projected_by_dataset']}")
    print(f"Secondary rows: {report['summary']['secondary_rows']}")
    print(f"Secondary by dataset: {report['summary']['secondary_by_dataset']}")
    print(f"Skipped: {report['summary']['skipped']}")
    print(f"Secondary skipped: {report['summary']['secondary_skipped']}")
    print(f"Schema errors: {report['summary']['schema_errors']}")
    print(f"Report: {report_path}")
    return 1 if schema_errors or input_schema_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
