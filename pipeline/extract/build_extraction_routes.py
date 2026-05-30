#!/usr/bin/env python3
"""Build table-native paper extraction routes from corpus tables.

This is the table-native handoff between screening/routing and model
extraction. It creates one row per DOI plus extraction task, so a paper can be
routed to multiple extraction profiles without reviving the old
mechanistic-vs-clinical pipeline split.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from pipeline.fulltext.convert_pdfs import doi_to_slug, normalize_doi
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(ROOT))
    from pipeline.fulltext.convert_pdfs import doi_to_slug, normalize_doi


DEFAULT_METADATA_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"
DEFAULT_PRESCREEN_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_prescreen_decisions.parquet"
DEFAULT_LITERATURE_TYPE_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_literature_type_routing.parquet"
DEFAULT_FULLTEXT_DIR = ROOT / "data" / "processed" / "fulltext"
DEFAULT_PAPER_ROOT = ROOT / "data" / "raw" / "papers" / "pdfs"
DEFAULT_OUTPUT_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes.parquet"
DEFAULT_SUMMARY_JSON = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes_summary.json"
DEFAULT_COUNTS_CSV = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes_counts.csv"
DEFAULT_MANUAL_ROUTE_OVERRIDES = ROOT / "pipeline" / "extract" / "manual_extraction_route_overrides.json"

TABLE_VERSION = "0.1"

PRIMARY_PROMPT_BY_DOMAIN = {
    "clinical_outcome": "primary_clinical",
    "safety_tolerability": "primary_safety",
    "molecular_target": "primary_molecular_target",
    "molecular_pathway_readout": "primary_molecular_pathway",
    "brain_system": "primary_brain_system",
    "cognitive_behavioral": "primary_cognitive_behavioral",
    "subjective_experience": "primary_subjective_experience",
    "pharmacokinetics_exposure": "primary_pharmacokinetics_exposure",
    "intervention_context": "primary_intervention_context",
    "real_world_public_health": "primary_real_world_public_health",
    "general_primary": "primary_general",
}
GENERAL_DOMAIN_ROUTE = "general_topic"

STRUCTURED_REVIEW_TYPES = {
    "systematic_review",
    "scoping_review",
    "umbrella_review",
}
META_ANALYSIS_TYPES = {
    "meta_analysis",
    "network_meta_analysis",
}
NARRATIVE_REVIEW_TYPES = {
    "review",
    "narrative_review",
    "literature_review",
}
GUIDELINE_TYPES = {
    "guideline",
    "consensus_statement",
}

STUDY_SYSTEM_PATTERNS = (
    (
        "clinical",
        re.compile(
            r"\b(clinical trial|randomi[sz]ed|placebo-controlled|patients?|participants?|"
            r"healthy volunteers?|subjects?|cohort|case-control|open-label|double-blind)\b",
            re.I,
        ),
    ),
    ("preclinical", re.compile(r"\b(mouse|mice|rat|rats|rodent|animal model|zebrafish|non-human primate)\b", re.I)),
    ("in_vitro", re.compile(r"\b(in vitro|cell line|cells?|binding assay|radioligand|transfected|recombinant)\b", re.I)),
    ("ex_vivo", re.compile(r"\b(ex vivo|brain slices?|tissue slices?)\b", re.I)),
)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).lower() in {"1", "true", "yes", "y", "retain"}


def prescreen_row_is_extraction_candidate(row: dict) -> bool:
    if "retained_for_extraction_candidate" in row:
        return truthy(row.get("retained_for_extraction_candidate", False))
    return clean(row.get("prescreen_decision", "")) == "retain"


def split_values(value: object) -> list[str]:
    out: list[str] = []
    for part in re.split(r"\s*[|,;]\s*", clean(value)):
        item = part.strip()
        if item and item not in out:
            out.append(item)
    return out


def join_values(values: Iterable[str]) -> str:
    out: list[str] = []
    for value in values:
        item = clean(value)
        if item and item not in out:
            out.append(item)
    return "|".join(out)


def stable_id(*parts: object, length: int = 20) -> str:
    payload = "|".join(clean(part) for part in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:length]


def read_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_counts_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["count_type", "value", "count"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_doi_file(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"DOI file not found: {path}")
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        doi = normalize_doi(line.split(",", 1)[0])
        if doi:
            out.add(doi)
    return out


def load_manual_route_overrides(path: Path | None) -> dict[str, dict]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records", []) if isinstance(payload, dict) else []
    out: dict[str, dict] = {}
    for row in records:
        if not isinstance(row, dict):
            continue
        doi = normalize_doi(row.get("doi", ""))
        if doi:
            out[doi] = row
    return out


def prescreen_context_by_doi(decisions_df: pd.DataFrame) -> dict[str, dict]:
    out: dict[str, dict] = defaultdict(
        lambda: {
            "datasets": [],
            "prescreen_actions": [],
            "routing_tags": [],
            "retained": False,
            "prescreen_reasons": [],
        }
    )
    if decisions_df.empty or "doi" not in decisions_df.columns:
        return {}
    for row in decisions_df.to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        if not doi:
            continue
        is_retained = prescreen_row_is_extraction_candidate(row)
        if not is_retained:
            continue
        entry = out[doi]
        entry["retained"] = True
        for field, target in [
            ("dataset", "datasets"),
            ("prescreen_action", "prescreen_actions"),
            ("prescreen_reason", "prescreen_reasons"),
        ]:
            value = clean(row.get(field, ""))
            if value and value not in entry[target]:
                entry[target].append(value)
        tags = []
        for field in ("routing_tags", "deterministic_routing_tags", "context_routing_tags"):
            tags.extend(split_values(row.get(field, "")))
        for tag in tags:
            tag_norm = tag.lower().replace("-", "_").replace(" ", "_")
            if tag_norm and tag_norm not in entry["routing_tags"]:
                entry["routing_tags"].append(tag_norm)
    return dict(out)


def row_by_doi(df: pd.DataFrame) -> dict[str, dict]:
    if df.empty or "doi" not in df.columns:
        return {}
    out = {}
    for row in df.to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        if doi:
            out[doi] = row
    return out


def domain_routing_by_doi(df: pd.DataFrame) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    if df.empty or "doi" not in df.columns:
        return {}
    for row in df.to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        if not doi:
            continue
        screening_decision = clean(row.get("screening_decision", ""))
        if (
            not screening_decision
            and "retained_for_extraction_candidate" in row
            and not truthy(row.get("retained_for_extraction_candidate"))
        ):
            continue
        route = clean(row.get("domain_route", ""))
        if not route and screening_decision != "exclude_out_of_scope":
            continue
        out[doi].append(row)
    return dict(out)


def artifact_ready(path: Path) -> tuple[bool, int]:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False, 0
    if not isinstance(artifact, dict):
        return False, 0
    try:
        char_count = int(artifact.get("best_char_count", 0) or 0)
    except (TypeError, ValueError):
        char_count = 0
    return char_count > 0, char_count


def fulltext_status_for_doi(doi: str, fulltext_dir: Path) -> dict:
    slug = doi_to_slug(doi)
    paths = sorted(path for path in fulltext_dir.glob(f"*/{slug}.json") if path.is_file())
    ready_paths: list[str] = []
    char_counts: list[int] = []
    for path in paths:
        ready, char_count = artifact_ready(path)
        if ready:
            ready_paths.append(str(path))
            char_counts.append(char_count)
    return {
        "has_converted_full_text": bool(ready_paths),
        "fulltext_artifact_paths": join_values(ready_paths),
        "fulltext_char_count": max(char_counts) if char_counts else 0,
    }


def local_pdf_slug(path: Path) -> str:
    prefix = path.stem.split("__", 1)[0].lower()
    return re.sub(r"[^a-z0-9]+", "_", prefix).strip("_")


def file_is_valid_pdf(path: Path) -> bool:
    try:
        raw = path.read_bytes()[:2048].lstrip(b"\x00\t\r\n\f ")
    except Exception:
        return False
    return raw.startswith(b"%PDF-")


@lru_cache(maxsize=8)
def build_local_pdf_index(paper_root: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    if not paper_root.exists():
        return {}
    for path in sorted(paper_root.glob("**/*.pdf")):
        if not path.is_file() or not file_is_valid_pdf(path):
            continue
        slug = local_pdf_slug(path)
        if slug:
            out[slug].append(str(path))
    return dict(out)


def local_pdf_status_for_doi(doi: str, local_pdf_index: dict[str, list[str]]) -> dict:
    paths = local_pdf_index.get(doi_to_slug(doi), [])
    return {
        "has_local_pdf": bool(paths),
        "local_pdf_paths": join_values(paths),
        "local_pdf_count": len(paths),
    }


def access_tier(metadata: dict, fulltext_status: dict, local_pdf_status: dict) -> str:
    if fulltext_status.get("has_converted_full_text"):
        return "full_text_available"
    if local_pdf_status.get("has_local_pdf"):
        return "local_pdf_available"
    if clean(metadata.get("best_pdf_url", "")):
        return "pdf_download_url_available"
    if clean(metadata.get("abstract", "")):
        return "abstract_only"
    return "no_usable_text"


def route_action_for_access(access: str, source_family: str) -> str:
    if source_family == "non_primary_publication":
        return "skip_or_context_only"
    if access == "full_text_available":
        return "extract_from_full_text"
    if access == "local_pdf_available":
        return "convert_local_pdf_then_extract"
    if access == "pdf_download_url_available":
        return "download_pdf_then_extract"
    if access == "abstract_only":
        return "extract_from_abstract_only"
    return "hold_until_text_available"


def domain_routes_for(tags: list[str], source_family: str) -> list[str]:
    if source_family == "non_primary_publication":
        return ["context_only"]
    if source_family == "secondary_literature":
        return ["general_topic_coverage"]
    return ["general_primary"]


def extraction_domain_route(domain_route: str, source_family: str) -> str:
    route = clean(domain_route)
    if source_family == "non_primary_publication":
        return "context_only"
    if route == GENERAL_DOMAIN_ROUTE:
        return "general_topic_coverage" if source_family == "secondary_literature" else "general_primary"
    return route


def domain_plan_for(
    *,
    doi: str,
    source_family: str,
    fallback_tags: list[str],
    domain_by_doi: dict[str, list[dict]],
    manual_override: dict | None = None,
) -> list[dict]:
    manual_override = manual_override or {}
    manual_action = clean(manual_override.get("manual_action", ""))
    manual_reason = clean(manual_override.get("manual_reason", "")) or "Manual extraction-route review."
    if manual_action == "context_only":
        return [
            {
                "domain_route": "context_only",
                "domain_tags": join_values(fallback_tags),
                "domain_route_confidence": "high",
                "domain_route_basis": manual_reason,
                "domain_routing_primary_domain": "context_only",
                "methodological_validity_tags": "",
                "domain_screening_decision": "manual_context_only",
                "domain_screening_reason": manual_reason,
                "domain_routing_model": "manual_extraction_route_review",
                "domain_needs_human_review": False,
                "manual_action": manual_action,
            }
        ]
    if manual_action == "route_domains":
        manual_routes = split_values(manual_override.get("manual_domain_routes", ""))
        if manual_routes:
            manual_tags = join_values(manual_routes)
            return [
                {
                    "domain_route": route,
                    "domain_tags": manual_tags,
                    "domain_route_confidence": "high",
                    "domain_route_basis": manual_reason,
                    "domain_routing_primary_domain": manual_routes[0],
                    "methodological_validity_tags": clean(manual_override.get("manual_methodological_validity_tags", "")),
                    "domain_screening_decision": "manual_include_in_scope",
                    "domain_screening_reason": manual_reason,
                    "domain_routing_model": "manual_extraction_route_review",
                    "domain_needs_human_review": False,
                    "manual_action": manual_action,
                }
                for route in manual_routes
            ]

    if source_family == "non_primary_publication":
        return [
            {
                "domain_route": "context_only",
                "domain_tags": join_values(fallback_tags),
                "domain_route_confidence": "medium" if fallback_tags else "low",
                "domain_route_basis": "non-primary publication routed as context-only",
                "domain_routing_primary_domain": "",
                "methodological_validity_tags": "",
                "domain_screening_decision": "",
                "domain_screening_reason": "",
                "domain_routing_model": "",
                "domain_needs_human_review": False,
            }
        ]

    domain_rows = domain_by_doi.get(doi, [])
    if domain_rows:
        screening_decision = clean(domain_rows[0].get("screening_decision", ""))
        if screening_decision == "exclude_out_of_scope":
            return [
                {
                    "domain_route": "screening_excluded",
                    "domain_tags": "",
                    "domain_route_confidence": clean(domain_rows[0].get("domain_route_confidence", "")),
                    "domain_route_basis": clean(domain_rows[0].get("domain_route_basis", "")),
                    "domain_routing_primary_domain": clean(domain_rows[0].get("primary_domain", "")),
                    "methodological_validity_tags": "",
                    "domain_screening_decision": screening_decision,
                    "domain_screening_reason": clean(domain_rows[0].get("screening_reason", "")),
                    "domain_routing_model": clean(domain_rows[0].get("model", "")),
                    "domain_needs_human_review": truthy(domain_rows[0].get("needs_human_review", False)),
                }
            ]
        plan: list[dict] = []
        seen_routes: set[str] = set()
        for row in domain_rows:
            route = extraction_domain_route(clean(row.get("domain_route", "")), source_family)
            if not route or route in seen_routes:
                continue
            seen_routes.add(route)
            plan.append(
                {
                    "domain_route": route,
                    "domain_tags": clean(row.get("all_domain_tags", "")) or join_values(fallback_tags),
                    "domain_route_confidence": clean(row.get("domain_route_confidence", "")),
                    "domain_route_basis": clean(row.get("domain_route_basis", "")),
                    "domain_routing_primary_domain": clean(row.get("primary_domain", "")),
                    "methodological_validity_tags": clean(row.get("methodological_validity_tags", "")),
                    "domain_screening_decision": clean(row.get("screening_decision", "")),
                    "domain_screening_reason": clean(row.get("screening_reason", "")),
                    "domain_routing_model": clean(row.get("model", "")),
                    "domain_needs_human_review": truthy(row.get("needs_human_review", False)),
                }
            )
        if plan:
            return plan

    return [
        {
            "domain_route": route,
            "domain_tags": "",
            "domain_route_confidence": "",
            "domain_route_basis": "no model-assigned domain table supplied",
            "domain_routing_primary_domain": "",
            "methodological_validity_tags": "",
            "domain_screening_decision": "",
            "domain_screening_reason": "",
            "domain_routing_model": "",
            "domain_needs_human_review": False,
        }
        for route in domain_routes_for(fallback_tags, source_family)
    ]


def source_type_for(literature_row: dict) -> str:
    source_family = clean(literature_row.get("source_family", ""))
    primary_secondary = clean(literature_row.get("primary_secondary_source_type", ""))
    if source_family == "secondary_literature":
        return primary_secondary or "review"
    if source_family == "non_primary_publication":
        flags = set(split_values(literature_row.get("non_primary_flags", "")))
        if "review_protocol" in flags:
            return "review_protocol"
        return "non_primary_publication"
    return "primary_or_unclear"


def prompt_profile_for(source_family: str, source_type: str, domain_route: str) -> str:
    if domain_route == "screening_excluded":
        return "no_extraction"
    if domain_route == "context_only":
        return "context_only_or_skip"
    if source_family == "non_primary_publication":
        return "context_only_or_skip"
    if source_family == "secondary_literature":
        if source_type in META_ANALYSIS_TYPES:
            return "secondary_meta_analysis"
        if source_type in STRUCTURED_REVIEW_TYPES:
            return "secondary_structured_review"
        if source_type in GUIDELINE_TYPES:
            return "guideline_consensus"
        if source_type in NARRATIVE_REVIEW_TYPES:
            return "secondary_narrative_review"
        return "secondary_review_coverage"
    return PRIMARY_PROMPT_BY_DOMAIN.get(domain_route, "primary_general")


def schema_profile_for(prompt_profile: str) -> str:
    if prompt_profile == "no_extraction":
        return "no_extraction_schema"
    if prompt_profile == "secondary_meta_analysis":
        return "synthesis_evidence_schema"
    if prompt_profile in {"secondary_structured_review", "secondary_narrative_review", "secondary_review_coverage"}:
        return "review_coverage_schema"
    if prompt_profile == "guideline_consensus":
        return "recommendation_consensus_schema"
    if prompt_profile == "context_only_or_skip":
        return "context_only_schema"
    return "primary_evidence_schema"


def study_system_hint(metadata: dict) -> str:
    publication_type = clean(metadata.get("publication_type", ""))
    trial_registry_ids = clean(metadata.get("trial_registry_ids", ""))
    text = " ".join(
        clean(metadata.get(field, ""))
        for field in ("study_title", "abstract", "mesh_terms", "keywords", "publication_type")
    )
    matches = [name for name, pattern in STUDY_SYSTEM_PATTERNS if pattern.search(text)]
    if trial_registry_ids:
        matches.insert(0, "clinical")
    if "Clinical Trial" in publication_type or "Randomized Controlled Trial" in publication_type:
        matches.insert(0, "clinical")
    unique = []
    for match in matches:
        if match not in unique:
            unique.append(match)
    if len(unique) > 1:
        return "mixed"
    return unique[0] if unique else "unknown"


def route_priority(source_family: str, source_type: str, domain_route: str, access: str) -> int:
    access_weight = {
        "full_text_available": 0,
        "local_pdf_available": 5,
        "pdf_download_url_available": 10,
        "abstract_only": 20,
        "no_usable_text": 80,
    }.get(access, 80)
    source_weight = {
        "primary_or_unclear": 10,
        "secondary_literature": 20,
        "non_primary_publication": 80,
    }.get(source_family, 50)
    if source_type in META_ANALYSIS_TYPES:
        source_weight = 15
    domain_weight = {
        "clinical_outcome": 0,
        "molecular_target": 1,
        "brain_system": 2,
        "cognitive_behavioral": 3,
        "molecular_pathway_readout": 4,
        "subjective_experience": 5,
        "pharmacokinetics_exposure": 6,
        "intervention_context": 7,
        "safety_tolerability": 8,
        "real_world_public_health": 9,
        "general_topic_coverage": 15,
        "general_primary": 15,
        "context_only": 20,
        "screening_excluded": 90,
    }.get(domain_route, 10)
    return source_weight + access_weight + domain_weight


def route_confidence(literature_row: dict, domain_route: str, tags: list[str], domain_confidence: str = "") -> str:
    lit_conf = clean(literature_row.get("literature_type_confidence", "")).lower()
    if domain_route == "screening_excluded":
        return clean(domain_confidence).lower() or "medium"
    if domain_route in {"general_primary", "general_topic_coverage", "context_only"} and not tags:
        return "low"
    if lit_conf == "high":
        return "high"
    if clean(domain_confidence).lower() == "high":
        return "high"
    if lit_conf == "medium":
        return "medium"
    return "medium" if tags else "low"


def route_basis(literature_row: dict, tags: list[str], domain_route: str, domain_route_basis: str = "") -> str:
    basis = []
    source_family = clean(literature_row.get("source_family", ""))
    if source_family:
        basis.append(f"source_family:{source_family}")
    source_type = source_type_for(literature_row)
    if source_type:
        basis.append(f"source_type:{source_type}")
    if tags:
        basis.append(f"domain_tags:{join_values(tags)}")
    if domain_route:
        basis.append(f"domain_route:{domain_route}")
    if clean(domain_route_basis):
        basis.append(f"domain_route_basis:{clean(domain_route_basis)}")
    for field in ("matched_metadata_terms", "matched_title_terms", "matched_abstract_terms"):
        value = clean(literature_row.get(field, ""))
        if value:
            basis.append(f"{field}:{value}")
    return " | ".join(basis)


def build_route_rows(
    metadata_df: pd.DataFrame,
    prescreen_df: pd.DataFrame,
    literature_df: pd.DataFrame,
    domain_df: pd.DataFrame | None = None,
    *,
    fulltext_dir: Path,
    generated_at_utc: str,
    include_non_retained: bool = False,
    scoped_dois: set[str] | None = None,
    manual_overrides: dict[str, dict] | None = None,
    paper_root: Path = DEFAULT_PAPER_ROOT,
) -> list[dict]:
    prescreen = prescreen_context_by_doi(prescreen_df)
    literature_by_doi = row_by_doi(literature_df)
    domain_by_doi = domain_routing_by_doi(domain_df if domain_df is not None else pd.DataFrame())
    rows: list[dict] = []
    scoped_dois = scoped_dois or set()
    manual_overrides = manual_overrides or {}
    local_pdf_index = build_local_pdf_index(paper_root)

    for metadata in metadata_df.to_dict("records"):
        doi = normalize_doi(metadata.get("doi", ""))
        if not doi:
            continue
        if scoped_dois and doi not in scoped_dois:
            continue
        context = prescreen.get(doi, {})
        literature_row = literature_by_doi.get(doi, {})
        retained = bool(context.get("retained")) or truthy(literature_row.get("retained_for_extraction_candidate", False))
        if not retained and not include_non_retained:
            continue

        source_family = clean(literature_row.get("source_family", "")) or "primary_or_unclear"
        source_type = source_type_for(literature_row)
        tags = [tag for tag in context.get("routing_tags", []) if tag != "uncertain"]
        manual_override = manual_overrides.get(doi, {})
        domains = domain_plan_for(
            doi=doi,
            source_family=source_family,
            fallback_tags=tags,
            domain_by_doi=domain_by_doi,
            manual_override=manual_override,
        )
        fulltext_status = fulltext_status_for_doi(doi, fulltext_dir)
        local_pdf_status = local_pdf_status_for_doi(doi, local_pdf_index)
        access = access_tier(metadata, fulltext_status, local_pdf_status)
        action = route_action_for_access(access, source_family)
        bridge = "bridge_clinical_mechanism" in tags
        system_hint = study_system_hint(metadata)

        for domain in domains:
            domain_route = clean(domain.get("domain_route", ""))
            domain_tags = split_values(domain.get("domain_tags", ""))
            domain_confidence = clean(domain.get("domain_route_confidence", ""))
            domain_basis = clean(domain.get("domain_route_basis", ""))
            domain_routing_primary_domain = clean(domain.get("domain_routing_primary_domain", ""))
            methodological_validity_tags = clean(domain.get("methodological_validity_tags", ""))
            domain_screening_decision = clean(domain.get("domain_screening_decision", ""))
            domain_screening_reason = clean(domain.get("domain_screening_reason", ""))
            domain_routing_model = clean(domain.get("domain_routing_model", ""))
            domain_needs_human_review = truthy(domain.get("domain_needs_human_review", False))
            manual_action = clean(domain.get("manual_action", ""))
            prompt_profile = prompt_profile_for(source_family, source_type, domain_route)
            schema_profile = schema_profile_for(prompt_profile)
            route_id = stable_id(doi, source_family, source_type, domain_route, access, prompt_profile)
            if manual_action == "context_only":
                row_action = "skip_or_context_only"
            elif domain_screening_decision == "exclude_out_of_scope":
                row_action = "exclude_after_model_screen"
            else:
                row_action = action
            route_retained = (
                retained
                and domain_screening_decision != "exclude_out_of_scope"
                and row_action != "skip_or_context_only"
            )
            rows.append(
                {
                    "table_version": TABLE_VERSION,
                    "generated_at_utc": generated_at_utc,
                    "route_id": route_id,
                    "doi": doi,
                    "datasets": join_values(context.get("datasets", [])) or clean(literature_row.get("datasets", "")) or clean(metadata.get("datasets", "")),
                    "retained_for_extraction_candidate": route_retained,
                    "study_title": clean(metadata.get("study_title", "")) or clean(literature_row.get("study_title", "")),
                    "study_year": clean(metadata.get("study_year", "")) or clean(literature_row.get("study_year", "")),
                    "publication_type": clean(metadata.get("publication_type", "")) or clean(literature_row.get("publication_type", "")),
                    "source_family": source_family,
                    "source_type": source_type,
                    "secondary_source_types": clean(literature_row.get("secondary_source_types", "")),
                    "primary_secondary_source_type": clean(literature_row.get("primary_secondary_source_type", "")),
                    "literature_type_confidence": clean(literature_row.get("literature_type_confidence", "")),
                    "domain_route": domain_route,
                    "domain_tags": join_values(domain_tags),
                    "domain_routing_primary_domain": domain_routing_primary_domain,
                    "methodological_validity_tags": methodological_validity_tags,
                    "domain_screening_decision": domain_screening_decision,
                    "domain_screening_reason": domain_screening_reason,
                    "domain_routing_model": domain_routing_model,
                    "domain_needs_human_review": domain_needs_human_review,
                    "domain_route_confidence": domain_confidence,
                    "bridge_clinical_mechanism": bridge or "bridge_clinical_mechanism" in domain_tags,
                    "study_system_hint": system_hint,
                    "access_tier": access,
                    "has_abstract": bool(clean(metadata.get("abstract", ""))),
                    "has_pdf_url": bool(clean(metadata.get("best_pdf_url", ""))),
                    "has_converted_full_text": bool(fulltext_status.get("has_converted_full_text")),
                    "fulltext_artifact_paths": clean(fulltext_status.get("fulltext_artifact_paths", "")),
                    "fulltext_char_count": int(fulltext_status.get("fulltext_char_count", 0) or 0),
                    "has_local_pdf": bool(local_pdf_status.get("has_local_pdf")),
                    "local_pdf_paths": clean(local_pdf_status.get("local_pdf_paths", "")),
                    "local_pdf_count": int(local_pdf_status.get("local_pdf_count", 0) or 0),
                    "open_access_status": clean(metadata.get("open_access_status", "")),
                    "best_pdf_url": clean(metadata.get("best_pdf_url", "")),
                    "route_action": row_action,
                    "prompt_profile": prompt_profile,
                    "schema_profile": schema_profile,
                    "route_priority": route_priority(source_family, source_type, domain_route, access),
                    "route_confidence": route_confidence(literature_row, domain_route, domain_tags, domain_confidence),
                    "route_basis": route_basis(literature_row, domain_tags, domain_route, domain_basis),
                }
            )
    rows.sort(key=lambda row: (int(row["route_priority"]), row["doi"], row["domain_route"], row["route_id"]))
    return rows


def count_rows(rows: list[dict], field: str) -> Counter:
    return Counter(clean(row.get(field, "")) or "<blank>" for row in rows)


def build_summary(rows: list[dict], *, inputs: dict) -> tuple[dict, list[dict]]:
    retained_dois = {row["doi"] for row in rows if row.get("retained_for_extraction_candidate")}
    summary = {
        "generated_at_utc": now_utc(),
        "table_version": TABLE_VERSION,
        "inputs": inputs,
        "route_rows": len(rows),
        "routed_dois": len({row["doi"] for row in rows}),
        "retained_routed_dois": len(retained_dois),
        "by_source_family": dict(count_rows(rows, "source_family")),
        "by_source_type": dict(count_rows(rows, "source_type")),
        "by_domain_route": dict(count_rows(rows, "domain_route")),
        "by_access_tier": dict(count_rows(rows, "access_tier")),
        "by_route_action": dict(count_rows(rows, "route_action")),
        "by_prompt_profile": dict(count_rows(rows, "prompt_profile")),
        "by_schema_profile": dict(count_rows(rows, "schema_profile")),
        "by_study_system_hint": dict(count_rows(rows, "study_system_hint")),
        "by_route_confidence": dict(count_rows(rows, "route_confidence")),
        "by_domain_routing_model": dict(count_rows(rows, "domain_routing_model")),
        "by_domain_screening_decision": dict(count_rows(rows, "domain_screening_decision")),
        "domain_needs_human_review": sum(1 for row in rows if row.get("domain_needs_human_review")),
    }
    counts: list[dict] = []
    for count_type, values in [
        ("source_family", summary["by_source_family"]),
        ("source_type", summary["by_source_type"]),
        ("domain_route", summary["by_domain_route"]),
        ("access_tier", summary["by_access_tier"]),
        ("route_action", summary["by_route_action"]),
        ("prompt_profile", summary["by_prompt_profile"]),
        ("schema_profile", summary["by_schema_profile"]),
        ("study_system_hint", summary["by_study_system_hint"]),
        ("route_confidence", summary["by_route_confidence"]),
        ("domain_routing_model", summary["by_domain_routing_model"]),
        ("domain_screening_decision", summary["by_domain_screening_decision"]),
    ]:
        for value, count in sorted(values.items()):
            counts.append({"count_type": count_type, "value": value, "count": count})
    return summary, counts


def write_route_table(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, engine="pyarrow", index=False)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build extraction-route table from corpus tables.")
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--prescreen-decisions-table", default=str(DEFAULT_PRESCREEN_TABLE))
    parser.add_argument("--literature-type-table", default=str(DEFAULT_LITERATURE_TYPE_TABLE))
    parser.add_argument(
        "--domain-routing-table",
        default="",
        help="Optional model-assigned domain routing table. If omitted, routes stay general by paper type/access.",
    )
    parser.add_argument("--fulltext-dir", default=str(DEFAULT_FULLTEXT_DIR))
    parser.add_argument("--paper-root", default=str(DEFAULT_PAPER_ROOT), help="Root directory containing local paper PDFs.")
    parser.add_argument("--output-table", default=str(DEFAULT_OUTPUT_TABLE))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY_JSON))
    parser.add_argument("--counts-csv", default=str(DEFAULT_COUNTS_CSV))
    parser.add_argument("--manual-route-overrides", default=str(DEFAULT_MANUAL_ROUTE_OVERRIDES))
    parser.add_argument("--doi-file", default="", help="Optional DOI list for a scoped route-table build.")
    parser.add_argument("--include-non-retained", action="store_true", help="Route all metadata rows, not only retained pre-screen candidates.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    metadata_table = Path(args.metadata_table).resolve()
    prescreen_table = Path(args.prescreen_decisions_table).resolve()
    literature_table = Path(args.literature_type_table).resolve()
    domain_table = Path(args.domain_routing_table).resolve() if clean(args.domain_routing_table) else None
    manual_overrides_path = Path(args.manual_route_overrides).resolve() if clean(args.manual_route_overrides) else None
    fulltext_dir = Path(args.fulltext_dir).resolve()
    paper_root = Path(args.paper_root).resolve()
    scoped_dois = read_doi_file(Path(args.doi_file).resolve()) if clean(args.doi_file) else set()

    metadata_df = read_table(metadata_table)
    prescreen_df = read_table(prescreen_table)
    literature_df = read_table(literature_table)
    domain_df = read_table(domain_table) if domain_table is not None else pd.DataFrame()
    manual_overrides = load_manual_route_overrides(manual_overrides_path)
    generated_at_utc = now_utc()
    rows = build_route_rows(
        metadata_df,
        prescreen_df,
        literature_df,
        domain_df,
        fulltext_dir=fulltext_dir,
        generated_at_utc=generated_at_utc,
        include_non_retained=bool(args.include_non_retained),
        scoped_dois=scoped_dois,
        manual_overrides=manual_overrides,
        paper_root=paper_root,
    )

    output_table = Path(args.output_table).resolve()
    summary_json = Path(args.summary_json).resolve()
    counts_csv = Path(args.counts_csv).resolve()
    write_route_table(output_table, rows)
    summary, counts = build_summary(
        rows,
        inputs={
            "metadata_table": str(metadata_table),
            "prescreen_decisions_table": str(prescreen_table),
            "literature_type_table": str(literature_table),
            "domain_routing_table": str(domain_table) if domain_table is not None else "",
            "manual_route_overrides": str(manual_overrides_path) if manual_overrides_path is not None else "",
            "manual_override_dois": len(manual_overrides),
            "fulltext_dir": str(fulltext_dir),
            "paper_root": str(paper_root),
            "doi_file": str(Path(args.doi_file).resolve()) if clean(args.doi_file) else "",
            "include_non_retained": bool(args.include_non_retained),
            "scoped_dois": len(scoped_dois),
        },
    )
    write_json(summary_json, summary)
    write_counts_csv(counts_csv, counts)

    print(f"Extraction route rows: {summary['route_rows']:,}")
    print(f"Routed DOIs: {summary['routed_dois']:,}")
    print(f"By prompt profile: {summary['by_prompt_profile']}")
    print(f"By access tier: {summary['by_access_tier']}")
    print(f"Route table: {output_table}")
    print(f"Summary: {summary_json}")
    print(f"Counts: {counts_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
