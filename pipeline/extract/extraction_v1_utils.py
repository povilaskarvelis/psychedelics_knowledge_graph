"""Shared helpers for extraction-v1 validation, QA, and projection."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Iterable


MISSING_QUOTE_VALUES = {
    "",
    "not_found",
    "not reported",
    "not_reported",
    "none",
    "n/a",
    "na",
}

ELLIPSIS_PATTERN = r"\[\s*(?:\.{2,}|…)\s*\]|\.{3,}|…"

CONTEXT_ONLY_SOURCE_TYPES = {
    "commentary",
    "study_protocol",
    "correction",
}

CONTEXT_ONLY_PAPER_TYPES = {
    "commentary",
    "protocol",
    "correction",
    "erratum",
    "editorial",
}

SECONDARY_LITERATURE_SOURCE_TYPES = {
    "secondary_evidence",
    "systematic_review",
    "review",
    "meta_analysis",
    "scoping_review",
}

SECONDARY_LITERATURE_PAPER_TYPES = {
    "systematic_review",
    "meta_analysis",
    "scoping_review",
    "review",
}

COVERAGE_MENTION_ALLOWED_FIELDS = {
    "coverage_type",
    "relationship_domain",
    "compound",
    "entity_type",
    "entity",
    "evidence_location",
    "evidence_locator",
    "supporting_quote",
    "confidence",
    "needs_human_review",
    "notes",
}

ALLOWED_ENTITY_ROLES = {
    "therapeutic_indication",
    "symptom_or_problem",
    "outcome_measure",
    "physiological_measure",
    "safety_or_adverse_event",
    "biomarker",
    "functional_outcome",
    "patient_reported_outcome",
    "population_or_context",
    "molecular_target",
    "gene_or_variant",
    "pathway_or_process",
    "brain_region_or_circuit",
    "assay_readout",
    "compound_or_class",
    "not_applicable",
    "uncertain",
}

ENTITY_ROLE_NORMALIZATION = {
    "drug_consumption_measure": "outcome_measure",
    "drug use measure": "outcome_measure",
    "drug_use_measure": "outcome_measure",
    "substance_use_measure": "outcome_measure",
}

NON_GRAPH_ENDPOINT_ROLES = {
    "physiological_measure",
    "safety_or_adverse_event",
    "biomarker",
    "functional_outcome",
    "patient_reported_outcome",
    "population_or_context",
    "gene_or_variant",
    "pathway_or_process",
    "brain_region_or_circuit",
    "assay_readout",
    "compound_or_class",
}

AFFINITY_TYPE_NORMALIZATION = {
    "ki": "Ki",
    "kd": "Kd",
    "ic50": "IC50",
    "ec50": "EC50",
    "ec90": "EC90",
    "km": "Other",
    "emax": "Other",
    "other": "Other",
    "not reported": "not_reported",
    "not_reported": "not_reported",
    "not applicable": "not_applicable",
    "not_applicable": "not_applicable",
    "n/a": "not_applicable",
    "na": "not_applicable",
}
VALID_AFFINITY_TYPES = set(AFFINITY_TYPE_NORMALIZATION.values())

SYSTEM_NORMALIZATION = {
    "in vitro": "in_vitro",
    "in-vitro": "in_vitro",
    "in vivo": "in_vivo",
    "in-vivo": "in_vivo",
    "ex vivo": "ex_vivo",
    "ex-vivo": "ex_vivo",
    "not applicable": "not_applicable",
    "not_applicable": "not_applicable",
}


def normalize(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalized_entity_role(value: object) -> str:
    role = normalize(value)
    if role in ALLOWED_ENTITY_ROLES:
        return role
    return ENTITY_ROLE_NORMALIZATION.get(role.lower(), "uncertain")


def result_with_endpoint_role_defaults(result: dict) -> tuple[dict, list[str]]:
    """Backfill extraction-v1 endpoint-role fields added after early pilots."""
    changes: list[str] = []
    out = copy.deepcopy(result)
    claims = out.get("claims", []) if isinstance(out, dict) else []
    if not isinstance(claims, list):
        return out, changes

    def add_change(name: str) -> None:
        if name not in changes:
            changes.append(name)

    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_type = normalize(claim.get("claim_type", ""))
        if "raw_entity_label" not in claim or normalize(claim.get("raw_entity_label", "")) == "":
            fallback_entity = (
                normalize(claim.get("target", ""))
                if claim_type == "compound_target"
                else normalize(claim.get("disorder", "")) or normalize(claim.get("outcome_measure", ""))
            )
            claim["raw_entity_label"] = fallback_entity or "not_reported"
            add_change("endpoint_role_fields_defaulted")
        for field, default in [
            ("entity_role", "uncertain"),
            ("clinical_context_condition", "not_reported"),
            ("graph_entity_label", "not_reported"),
            ("graph_entity_type", "uncertain"),
            ("graph_exclusion_reason", "not_reported"),
        ]:
            if field not in claim or normalize(claim.get(field, "")) == "":
                claim[field] = default
                add_change("endpoint_role_fields_defaulted")
        role = normalized_entity_role(claim.get("entity_role", ""))
        if claim.get("entity_role") != role:
            claim["entity_role"] = role
            add_change("entity_role_normalized")
        if "graph_include_candidate" not in claim or not isinstance(claim.get("graph_include_candidate"), bool):
            claim["graph_include_candidate"] = False
            add_change("endpoint_role_fields_defaulted")
        if claim.get("graph_include_candidate") is True and claim.get("entity_role") in NON_GRAPH_ENDPOINT_ROLES:
            claim["graph_include_candidate"] = False
            if normalize(claim.get("graph_exclusion_reason", "")).lower() in {"", "not_applicable"}:
                claim["graph_exclusion_reason"] = f"{claim.get('entity_role')} is not a graph endpoint"
            add_change("non_graph_endpoint_candidate_removed")
        if claim_type == "compound_disorder" and normalize(claim.get("outcome_domain", "")) == "":
            claim["outcome_domain"] = "not_reported"
            add_change("endpoint_role_fields_defaulted")
    return out, changes


def normalize_extraction_v1_result(result: dict) -> tuple[dict, list[str]]:
    """Apply deterministic cleanup to common model-formatting slips."""
    changes: list[str] = []

    def add_change(name: str) -> None:
        if name not in changes:
            changes.append(name)

    def nulls_to_empty(value: object) -> object:
        if isinstance(value, dict):
            return {key: nulls_to_empty(item) for key, item in value.items()}
        if isinstance(value, list):
            return [nulls_to_empty(item) for item in value]
        if value is None:
            add_change("json_null_to_empty_string")
            return ""
        return value

    out = nulls_to_empty(result)
    if not isinstance(out, dict):
        return result, changes

    assessment = out.get("paper_assessment")
    if not isinstance(assessment, dict):
        return out, changes

    if "confidence" not in assessment or normalize(assessment.get("confidence", "")) == "":
        assessment["confidence"] = 0.0
        add_change("paper_assessment_required_defaults")
    if "reasoning_summary" not in assessment or normalize(assessment.get("reasoning_summary", "")) == "":
        assessment["reasoning_summary"] = "not_reported"
        add_change("paper_assessment_required_defaults")
    normalized_system = SYSTEM_NORMALIZATION.get(normalize(assessment.get("system", "")).lower())
    if normalized_system and assessment.get("system") != normalized_system:
        assessment["system"] = normalized_system
        add_change("system_normalized")

    if not isinstance(out.get("claims"), list):
        out["claims"] = []
        add_change("claims_reset_to_empty_array")
    if not isinstance(out.get("coverage_mentions"), list):
        out["coverage_mentions"] = []
        add_change("coverage_mentions_reset_to_empty_array")

    claims = out.get("claims", [])
    if isinstance(claims, list):
        quoted_claims = [
            claim
            for claim in claims
            if not (
                isinstance(claim, dict)
                and normalize(claim.get("supporting_quote", "")).lower() in MISSING_QUOTE_VALUES
            )
        ]
        if len(quoted_claims) != len(claims):
            out["claims"] = quoted_claims
            add_change("unquoted_claims_removed")

    coverage_mentions = out.get("coverage_mentions", [])
    if isinstance(coverage_mentions, list):
        quoted_mentions = [
            mention
            for mention in coverage_mentions
            if not (
                isinstance(mention, dict)
                and normalize(mention.get("supporting_quote", "")).lower() in MISSING_QUOTE_VALUES
            )
        ]
        if len(quoted_mentions) != len(coverage_mentions):
            out["coverage_mentions"] = quoted_mentions
            add_change("unquoted_coverage_mentions_removed")

    route = normalize(assessment.get("route", ""))
    relevance = normalize(assessment.get("relevance", ""))
    source_type = normalize(assessment.get("source_type", ""))
    paper_type = normalize(assessment.get("paper_type", ""))

    if route == "secondary_literature" and (
        source_type in CONTEXT_ONLY_SOURCE_TYPES or paper_type in CONTEXT_ONLY_PAPER_TYPES
    ):
        assessment["route"] = "context_only"
        route = "context_only"
        add_change("context_source_routed_context_only")

    if route == "secondary_literature" and (
        source_type not in SECONDARY_LITERATURE_SOURCE_TYPES
        or paper_type not in SECONDARY_LITERATURE_PAPER_TYPES
    ):
        if out.get("claims", []):
            assessment["route"] = "human_review"
            assessment["needs_human_review"] = True
            route = "human_review"
            add_change("secondary_metadata_conflict_routed_human_review")
        else:
            assessment["route"] = "context_only"
            route = "context_only"
            add_change("secondary_metadata_conflict_routed_context_only")

    if relevance == "not_relevant":
        if route != "exclude":
            assessment["route"] = "exclude"
            route = "exclude"
            add_change("not_relevant_routed_exclude")
        if normalize(assessment.get("exclusion_reason", "")) == "":
            assessment["exclusion_reason"] = "not_reported"
            add_change("missing_exclusion_reason_set_not_reported")

    claims = out.get("claims", [])
    coverage_mentions = out.get("coverage_mentions", [])

    if route == "primary_evidence":
        if claims:
            if coverage_mentions:
                out["coverage_mentions"] = []
                add_change("primary_coverage_mentions_removed")
            if assessment.get("has_original_results") is not True:
                assessment["has_original_results"] = True
                add_change("primary_flags_normalized")
            if assessment.get("has_extractable_claims") is not True:
                assessment["has_extractable_claims"] = True
                add_change("primary_flags_normalized")
        else:
            assessment["route"] = "human_review"
            assessment["has_extractable_claims"] = False
            assessment["needs_human_review"] = True
            route = "human_review"
            add_change("primary_without_claims_routed_human_review")

    if route == "secondary_literature":
        if claims:
            out["claims"] = []
            add_change("secondary_claims_removed")
        if assessment.get("source_family") != "evidence_synthesis":
            assessment["source_family"] = "evidence_synthesis"
            add_change("secondary_source_family_normalized")
        if assessment.get("has_original_results") is not False:
            assessment["has_original_results"] = False
            add_change("secondary_flags_normalized")
        if assessment.get("has_extractable_claims") is not False:
            assessment["has_extractable_claims"] = False
            add_change("secondary_flags_normalized")

    if route == "context_only":
        if claims:
            out["claims"] = []
            add_change("context_claims_removed")
        if assessment.get("has_original_results") is not False:
            assessment["has_original_results"] = False
            add_change("context_flags_normalized")
        if assessment.get("has_extractable_claims") is not False:
            assessment["has_extractable_claims"] = False
            add_change("context_flags_normalized")

    if route == "exclude":
        if claims:
            out["claims"] = []
            add_change("exclude_claims_removed")
        if coverage_mentions:
            out["coverage_mentions"] = []
            add_change("exclude_coverage_mentions_removed")
        if assessment.get("has_extractable_claims") is not False:
            assessment["has_extractable_claims"] = False
            add_change("exclude_flags_normalized")

    if route == "human_review" and assessment.get("needs_human_review") is not True:
        assessment["needs_human_review"] = True
        add_change("human_review_flag_normalized")

    for claim in out.get("claims", []) if isinstance(out.get("claims"), list) else []:
        if not isinstance(claim, dict):
            continue
        claim_type = normalize(claim.get("claim_type", ""))
        if "raw_entity_label" not in claim or normalize(claim.get("raw_entity_label", "")) == "":
            fallback_entity = (
                normalize(claim.get("target", ""))
                if claim_type == "compound_target"
                else normalize(claim.get("disorder", "")) or normalize(claim.get("outcome_measure", ""))
            )
            claim["raw_entity_label"] = fallback_entity or "not_reported"
            add_change("endpoint_role_fields_defaulted")
        for field, default in [
            ("entity_role", "uncertain"),
            ("clinical_context_condition", "not_reported"),
            ("graph_entity_label", "not_reported"),
            ("graph_entity_type", "uncertain"),
            ("graph_exclusion_reason", "not_reported"),
        ]:
            if field not in claim or normalize(claim.get(field, "")) == "":
                claim[field] = default
                add_change("endpoint_role_fields_defaulted")
        role = normalized_entity_role(claim.get("entity_role", ""))
        if claim.get("entity_role") != role:
            claim["entity_role"] = role
            add_change("entity_role_normalized")
        if "graph_include_candidate" not in claim or not isinstance(claim.get("graph_include_candidate"), bool):
            claim["graph_include_candidate"] = False
            add_change("endpoint_role_fields_defaulted")
        if claim.get("graph_include_candidate") is True and claim.get("entity_role") in NON_GRAPH_ENDPOINT_ROLES:
            claim["graph_include_candidate"] = False
            if normalize(claim.get("graph_exclusion_reason", "")).lower() in {"", "not_applicable"}:
                claim["graph_exclusion_reason"] = f"{claim.get('entity_role')} is not a graph endpoint"
            add_change("non_graph_endpoint_candidate_removed")
        if claim_type == "compound_disorder" and normalize(claim.get("outcome_domain", "")) == "":
            claim["outcome_domain"] = "not_reported"
            add_change("endpoint_role_fields_defaulted")
        normalized_system = SYSTEM_NORMALIZATION.get(normalize(claim.get("system", "")).lower())
        if normalized_system and claim.get("system") != normalized_system:
            claim["system"] = normalized_system
            add_change("system_normalized")
        affinity_type = normalize(claim.get("affinity_type", ""))
        normalized_affinity_type = AFFINITY_TYPE_NORMALIZATION.get(affinity_type.lower())
        if normalized_affinity_type and claim.get("affinity_type") != normalized_affinity_type:
            claim["affinity_type"] = normalized_affinity_type
            add_change("affinity_type_normalized")
        elif claim_type == "compound_target" and affinity_type and affinity_type not in VALID_AFFINITY_TYPES:
            claim["affinity_type"] = "Other"
            add_change("affinity_type_normalized")
        if claim_type == "compound_target":
            if claim.get("disorder") != "not_applicable":
                claim["disorder"] = "not_applicable"
                add_change("compound_target_slots_normalized")
            if claim.get("result_direction") != "not_applicable":
                claim["result_direction"] = "not_applicable"
                add_change("compound_target_slots_normalized")
            if claim.get("affinity_type") == "not_applicable":
                claim["affinity_type"] = "not_reported"
                add_change("compound_target_affinity_type_normalized")
        elif claim_type == "compound_disorder" and claim.get("target") != "not_applicable":
            claim["target"] = "not_applicable"
            add_change("compound_disorder_slots_normalized")

    for mention in out.get("coverage_mentions", []) if isinstance(out.get("coverage_mentions"), list) else []:
        if not isinstance(mention, dict):
            continue
        extra_fields = [field for field in mention if field not in COVERAGE_MENTION_ALLOWED_FIELDS]
        for field in extra_fields:
            mention.pop(field, None)
        if extra_fields:
            add_change("coverage_extra_fields_removed")
        domain = normalize(mention.get("relationship_domain", ""))
        expected_entity_type = {
            "compound_target": "target",
            "compound_disorder": "disorder",
            "compound_only": "compound",
            "target_only": "target",
            "disorder_only": "disorder",
            "general_topic": "general_topic",
            "not_applicable": "not_applicable",
        }.get(domain)
        if expected_entity_type and mention.get("entity_type") != expected_entity_type:
            mention["entity_type"] = expected_entity_type
            add_change("coverage_entity_type_normalized")

    if out.get("access_level") == "abstract_only":
        for item in [assessment] + [
            entry
            for collection in (out.get("claims", []), out.get("coverage_mentions", []))
            if isinstance(collection, list)
            for entry in collection
            if isinstance(entry, dict)
        ]:
            if item.get("evidence_location") == "text":
                item["evidence_location"] = "abstract"
                add_change("abstract_only_text_location_normalized")

    return out, changes


def normalize_doi(raw: object) -> str:
    text = normalize(raw)
    if not text:
        return ""
    lowered = text.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip().lower()


def normalize_for_match(value: object) -> str:
    text = re.sub(r"\s+", " ", normalize(value).lower()).strip()
    return text.strip("\"'“”‘’ ")


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
    return rows


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def quote_fragments_for_match(quote: object, min_chars: int = 6) -> list[str]:
    text = normalize_for_match(quote)
    if not text:
        return []
    if not re.search(ELLIPSIS_PATTERN, text):
        return [text]
    fragments = [normalize_for_match(part) for part in re.split(ELLIPSIS_PATTERN, text)]
    return [fragment for fragment in fragments if len(fragment) >= min_chars]


def quote_tokens(value: object) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalize_for_match(value))


def quote_token_anchor_found(quote: object, context: str, min_tokens: int = 8, min_coverage: float = 0.9, window: int = 6) -> bool:
    quote_token_list = quote_tokens(quote)
    if len(quote_token_list) < min_tokens:
        return False
    context_token_list = quote_tokens(context)
    if not context_token_list:
        return False
    context_tokens = set(context_token_list)
    coverage = sum(1 for token in quote_token_list if token in context_tokens) / len(quote_token_list)
    if coverage < min_coverage:
        return False
    context_token_text = " ".join(context_token_list)
    max_start = len(quote_token_list) - min(window, len(quote_token_list))
    for start in range(max_start + 1):
        phrase = " ".join(quote_token_list[start : start + window])
        if phrase and phrase in context_token_text:
            return True
    return False


def quote_found_in_context(quote: object, context: str) -> bool:
    quote_norm = normalize_for_match(quote)
    if quote_norm in MISSING_QUOTE_VALUES:
        return False
    context_norm = normalize_for_match(context)
    if quote_norm in context_norm:
        return True
    fragments = quote_fragments_for_match(quote_norm)
    if len(fragments) > 1 and all(fragment in context_norm for fragment in fragments):
        return True
    return quote_token_anchor_found(quote_norm, context_norm)


def text_parts_from_packet(packet: dict) -> list[str]:
    parts = []
    metadata = packet.get("paper_metadata", {}) if isinstance(packet.get("paper_metadata"), dict) else {}
    parts.extend(metadata_text_parts(metadata))
    title = normalize(metadata.get("study_title", ""))
    abstract = normalize(metadata.get("abstract", ""))
    if title:
        parts.append(f"Title: {title}")
    if abstract:
        parts.append(f"Abstract: {abstract}")

    for chunk in packet.get("llm_chunks", []) if isinstance(packet.get("llm_chunks"), list) else []:
        if not isinstance(chunk, dict):
            continue
        text = normalize(chunk.get("text", ""))
        if not text:
            continue
        chunk_id = normalize(chunk.get("chunk_id", ""))
        heading = normalize(chunk.get("heading", ""))
        label = " ".join(part for part in [chunk_id, heading] if part)
        parts.append(f"[{label}] {text}" if label else text)

    for table in packet.get("tables", []) if isinstance(packet.get("tables"), list) else []:
        if not isinstance(table, dict):
            continue
        text = normalize(table.get("text", ""))
        caption = normalize(table.get("caption", ""))
        label = normalize(table.get("table_id", "")) or normalize(table.get("label", ""))
        if text or caption:
            parts.append(f"[{label}] {caption} {text}".strip())

    for figure in packet.get("figures", []) if isinstance(packet.get("figures"), list) else []:
        if not isinstance(figure, dict):
            continue
        text = normalize(figure.get("text", ""))
        caption = normalize(figure.get("caption", ""))
        label = normalize(figure.get("figure_id", "")) or normalize(figure.get("label", ""))
        if text or caption:
            parts.append(f"[{label}] {caption} {text}".strip())
    return parts


def metadata_text_parts(metadata: dict) -> list[str]:
    parts = []
    for label, key in [
        ("Publication type", "publication_type"),
        ("Journal", "study_journal"),
        ("Publication year", "study_year"),
        ("Trial registry IDs", "trial_registry_ids"),
        ("Funders", "funders"),
        ("MeSH terms", "mesh_terms"),
        ("Keywords", "keywords"),
    ]:
        value = metadata.get(key)
        if isinstance(value, list):
            text = " | ".join(normalize(item) for item in value if normalize(item))
        else:
            text = normalize(value)
        if text:
            parts.append(f"{label}: {text}")
    return parts


def context_text_from_pilot_record(record: dict) -> str:
    content = record.get("content", {}) if isinstance(record.get("content"), dict) else {}
    if isinstance(content.get("packet"), dict):
        return "\n\n".join(text_parts_from_packet(content["packet"]))

    parts = []
    metadata = record.get("paper_metadata", {}) if isinstance(record.get("paper_metadata"), dict) else {}
    parts.extend(metadata_text_parts(metadata))
    title = normalize(content.get("title", ""))
    abstract = normalize(content.get("abstract", ""))
    if title:
        parts.append(f"Title: {title}")
    if abstract:
        parts.append(f"Abstract: {abstract}")
    for screening in content.get("screening_records", []) if isinstance(content.get("screening_records"), list) else []:
        if not isinstance(screening, dict):
            continue
        quote = normalize(screening.get("supporting_abstract_quote", ""))
        if quote:
            parts.append(f"Screening quote: {quote}")
        for context in screening.get("supported_contexts", []) if isinstance(screening.get("supported_contexts"), list) else []:
            if not isinstance(context, dict):
                continue
            supporting_quote = normalize(context.get("supporting_quote", ""))
            if supporting_quote:
                parts.append(f"Context quote: {supporting_quote}")
    return "\n\n".join(parts)


def pilot_record_keys(record: dict) -> list[tuple[str, str]]:
    keys = []
    dataset = normalize(record.get("dataset", ""))
    doi = normalize_doi(record.get("study_doi", ""))
    pilot_id = normalize(record.get("pilot_record_id", ""))
    if pilot_id:
        keys.append(("input_record_id", pilot_id))
    if dataset and doi:
        keys.append(("dataset_doi", f"{dataset}|{doi}"))
    content = record.get("content", {}) if isinstance(record.get("content"), dict) else {}
    packet = content.get("packet") if isinstance(content.get("packet"), dict) else None
    packet_id = normalize((packet or content).get("packet_id", ""))
    if packet_id:
        keys.append(("input_packet_id", packet_id))
    return keys


def load_pilot_contexts(path: Path) -> dict[tuple[str, str], dict]:
    out = {}
    for record in read_jsonl(path):
        context = context_text_from_pilot_record(record)
        item = {
            "pilot_record": record,
            "context_text": context,
        }
        for key in pilot_record_keys(record):
            out[key] = item
    return out


def context_lookup_keys_for_result(result: dict) -> list[tuple[str, str]]:
    keys = []
    input_record_id = normalize(result.get("input_record_id", ""))
    if input_record_id:
        keys.append(("input_record_id", input_record_id))
    input_packet_id = normalize(result.get("input_packet_id", ""))
    if input_packet_id:
        keys.append(("input_packet_id", input_packet_id))
    dataset = normalize(result.get("dataset", ""))
    doi = normalize_doi(result.get("study_doi", ""))
    if dataset and doi:
        keys.append(("dataset_doi", f"{dataset}|{doi}"))
    return keys


def find_context_for_result(result: dict, contexts: dict[tuple[str, str], dict]) -> dict:
    for key in context_lookup_keys_for_result(result):
        item = contexts.get(key)
        if item:
            return item
    return {}
