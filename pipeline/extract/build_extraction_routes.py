#!/usr/bin/env python3
"""Build table-native paper extraction routes from corpus tables.

This is the table-native handoff between screening/routing and model
extraction. It creates one row per DOI plus extraction task, so a paper can be
routed to multiple extraction profiles without reviving the old split-source
pipeline shape.
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
    from pipeline.fulltext.source_identity_audit_gate import (
        DEFAULT_SOURCE_IDENTITY_AUDIT,
        SourceIdentityAuditGate,
    )
    from pipeline.ingest.candidate_status import apply_candidate_updates
    from pipeline.ingest.sync_paper_library import (
        is_probable_pdf_url,
        join_candidates,
        rank_pdf_candidates,
        split_candidates,
    )
    from pipeline.ingest.preprint_detection import classify_publication_stage
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(ROOT))
    from pipeline.fulltext.convert_pdfs import doi_to_slug, normalize_doi
    from pipeline.fulltext.source_identity_audit_gate import (
        DEFAULT_SOURCE_IDENTITY_AUDIT,
        SourceIdentityAuditGate,
    )
    from pipeline.ingest.candidate_status import apply_candidate_updates
    from pipeline.ingest.preprint_detection import classify_publication_stage
    from pipeline.ingest.sync_paper_library import (
        is_probable_pdf_url,
        join_candidates,
        rank_pdf_candidates,
        split_candidates,
    )


DEFAULT_METADATA_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_PRESCREEN_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_prescreen_decisions.parquet"
DEFAULT_DOMAIN_ROUTING_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_domain_routing_gemini.parquet"
DEFAULT_FULLTEXT_DIR = ROOT / "data" / "processed" / "fulltext"
CANONICAL_FULLTEXT_ARTICLE_DIR = "articles"
DEFAULT_PAPER_ROOT = ROOT / "data" / "raw" / "papers" / "pdfs"
DEFAULT_OUTPUT_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes.parquet"
DEFAULT_SUMMARY_JSON = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes_summary.json"
DEFAULT_COUNTS_CSV = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes_counts.csv"
DEFAULT_MANUAL_ROUTE_OVERRIDES = ROOT / "pipeline" / "extract" / "manual_extraction_route_overrides.json"
DEFAULT_MANUAL_FULLTEXT_ACCESS_OVERRIDES = ROOT / "pipeline" / "fulltext" / "manual_fulltext_access_overrides.json"

TABLE_VERSION = "0.4"
CANDIDATE_STATUS_DEFAULTS = {
    "publication_stage": "",
    "is_preprint_like": False,
    "preprint_signal_strength": "",
    "preprint_detection_basis": "",
    "published_version_lookup_status": "",
    "published_version_doi": "",
    "prescreen_retained_for_extraction_candidate": False,
    "prescreen_decisions": "",
    "prescreen_actions": "",
    "prescreen_reasons": "",
    "prescreen_routing_tags": "",
    "literature_source_family": "",
    "literature_source_type": "",
    "literature_type_confidence": "",
    "primary_secondary_source_type": "",
    "secondary_source_types": "",
    "non_primary_flags": "",
    "retained_for_extraction_candidate": False,
    "extraction_route_status": "",
    "extraction_route_reason": "",
    "extraction_route_count": 0,
    "retained_extraction_route_count": 0,
    "extraction_route_actions": "",
    "extraction_domain_routes": "",
    "extraction_domain_screening_decisions": "",
    "extraction_prompt_profiles": "",
    "extraction_schema_profiles": "",
    "best_extraction_access_tier": "",
    "source_text_state": "",
    "source_text_state_reason": "",
    "source_identity_verified": False,
    "has_converted_full_text": False,
    "fulltext_artifact_paths": "",
    "fulltext_char_count": 0,
    "manual_fulltext_access_action": "",
    "manual_fulltext_access_reason": "",
    "extraction_routes_table_version": "",
    "extraction_routes_updated_at_utc": "",
}
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
THESIS_OR_DISSERTATION_RE = re.compile(r"\b(dissertation|thesis|doctoral|phd|master'?s thesis)\b", re.I)


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


def thesis_or_dissertation_flags(row: dict) -> str:
    publication_type = clean(row.get("publication_type", ""))
    title = clean(row.get("study_title", "")) or clean(row.get("title", ""))
    journal = clean(row.get("study_journal", "")) or clean(row.get("journal", ""))
    abstract = clean(row.get("abstract", ""))
    url_text = " ".join(
        clean(row.get(field, ""))
        for field in ("best_pdf_url", "open_access_url", "pdf_url_candidates", "unpaywall_best_pdf_url")
    )
    flags: list[str] = []
    if THESIS_OR_DISSERTATION_RE.search(publication_type):
        flags.append("thesis_or_dissertation_publication_type")
    if THESIS_OR_DISSERTATION_RE.search(journal):
        flags.append("thesis_or_dissertation_venue")
    if THESIS_OR_DISSERTATION_RE.search(title):
        flags.append("thesis_or_dissertation_title")
    if THESIS_OR_DISSERTATION_RE.search(url_text):
        flags.append("thesis_or_dissertation_url")
    if flags and THESIS_OR_DISSERTATION_RE.search(abstract):
        flags.append("thesis_or_dissertation_abstract")
    return join_values(flags)


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


def load_manual_fulltext_access_overrides(path: Path | None) -> dict[str, dict]:
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


def truthy_override(value: object) -> bool | None:
    text = clean(value).lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


def apply_fulltext_access_override(metadata: dict, override: dict | None) -> dict:
    override = override or {}
    action = clean(override.get("manual_access_action", ""))
    if action not in {"suppress_pdf_download", "abstract_only"}:
        return metadata
    out = dict(metadata)
    out["best_pdf_url"] = ""
    out["pdf_url_candidates"] = ""
    out["probable_pdf_url_candidates"] = ""
    out["other_url_candidates"] = ""
    status = clean(override.get("open_access_status", ""))
    if status:
        out["open_access_status"] = status
    is_oa = truthy_override(override.get("open_access_is_oa", ""))
    if is_oa is not None:
        out["open_access_is_oa"] = is_oa
    return out


def prescreen_context_by_doi(decisions_df: pd.DataFrame) -> dict[str, dict]:
    out: dict[str, dict] = defaultdict(
        lambda: {
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


def prescreen_status_by_doi(decisions_df: pd.DataFrame) -> dict[str, dict]:
    out: dict[str, dict] = defaultdict(
        lambda: {
            "prescreen_retained_for_extraction_candidate": False,
            "prescreen_decisions": [],
            "prescreen_actions": [],
            "prescreen_reasons": [],
            "prescreen_routing_tags": [],
        }
    )
    if decisions_df.empty or "doi" not in decisions_df.columns:
        return {}
    for row in decisions_df.to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        if not doi:
            continue
        entry = out[doi]
        if prescreen_row_is_extraction_candidate(row):
            entry["prescreen_retained_for_extraction_candidate"] = True
        for field, target in [
            ("prescreen_decision", "prescreen_decisions"),
            ("prescreen_action", "prescreen_actions"),
            ("prescreen_reason", "prescreen_reasons"),
        ]:
            value = clean(row.get(field, ""))
            if value and value not in entry[target]:
                entry[target].append(value)
        for field in ("routing_tags", "deterministic_routing_tags", "context_routing_tags"):
            for tag in split_values(row.get(field, "")):
                tag_norm = tag.lower().replace("-", "_").replace(" ", "_")
                if tag_norm and tag_norm not in entry["prescreen_routing_tags"]:
                    entry["prescreen_routing_tags"].append(tag_norm)
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


def literature_status_by_doi(df: pd.DataFrame) -> dict[str, dict]:
    if df.empty or "doi" not in df.columns:
        return {}
    out: dict[str, dict] = {}
    for row in df.to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        if not doi:
            continue
        out[doi] = {
            "literature_source_family": clean(row.get("source_family", "")),
            "literature_source_type": source_type_for(row),
            "literature_type_confidence": clean(row.get("literature_type_confidence", "")),
            "primary_secondary_source_type": clean(row.get("primary_secondary_source_type", "")),
            "secondary_source_types": clean(row.get("secondary_source_types", "")),
            "non_primary_flags": clean(row.get("non_primary_flags", "")),
        }
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


def artifact_ready(
    path: Path,
    doi: str,
    source_identity_gate: SourceIdentityAuditGate,
) -> tuple[bool, int]:
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
    return char_count > 0 and source_identity_gate.is_verified(doi, path), char_count


def fulltext_status_for_doi(
    doi: str,
    fulltext_dir: Path,
    *,
    source_identity_gate: SourceIdentityAuditGate | None = None,
    source_identity_audit: Path = DEFAULT_SOURCE_IDENTITY_AUDIT,
) -> dict:
    slug = doi_to_slug(doi)
    canonical_path = fulltext_dir / CANONICAL_FULLTEXT_ARTICLE_DIR / f"{slug}.json"
    ready_paths: list[str] = []
    char_counts: list[int] = []
    if canonical_path.is_file():
        gate = source_identity_gate or SourceIdentityAuditGate(source_identity_audit)
        ready, char_count = artifact_ready(canonical_path, doi, gate)
        if ready:
            ready_paths.append(str(canonical_path))
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


def metadata_pdf_url_candidates(metadata: dict) -> list[str]:
    candidates: list[str] = []
    for field in ("best_pdf_url", "pdf_url_candidates"):
        for value in split_candidates(metadata.get(field, "")):
            if value and value not in candidates:
                candidates.append(value)
    return rank_pdf_candidates(candidates)


def metadata_probable_pdf_url_candidates(metadata: dict) -> list[str]:
    return rank_pdf_candidates(value for value in metadata_pdf_url_candidates(metadata) if is_probable_pdf_url(value))


def metadata_other_url_candidates(metadata: dict) -> list[str]:
    probable = set(metadata_probable_pdf_url_candidates(metadata))
    return [value for value in metadata_pdf_url_candidates(metadata) if value not in probable]


def metadata_pdf_url_quality(metadata: dict) -> str:
    if metadata_probable_pdf_url_candidates(metadata):
        return "probable_pdf"
    if metadata_pdf_url_candidates(metadata):
        return "possible_landing_page"
    return "no_url"


def access_tier(metadata: dict, fulltext_status: dict, local_pdf_status: dict) -> str:
    if fulltext_status.get("has_converted_full_text"):
        return "full_text_available"
    if local_pdf_status.get("has_local_pdf"):
        return "local_pdf_available"
    if metadata_probable_pdf_url_candidates(metadata):
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


def source_text_state_for_access(access: str) -> tuple[str, str, bool]:
    mapping = {
        "full_text_available": (
            "public_full_text_verified",
            "A converted article-text artifact passes the source-identity gate.",
            True,
        ),
        "local_pdf_available": (
            "public_full_text_pending_conversion",
            "A locally stored public PDF is ready for identity-gated conversion.",
            False,
        ),
        "pdf_download_url_available": (
            "public_full_text_candidate",
            "A probable public PDF URL still requires download and identity validation.",
            False,
        ),
        "abstract_only": (
            "public_abstract_only",
            "The paper remains eligible using its public abstract; no verified public full text is active.",
            False,
        ),
        "no_usable_text": (
            "no_usable_public_text",
            "Neither a usable public abstract nor verified public full text is available.",
            False,
        ),
    }
    return mapping.get(
        clean(access),
        ("source_state_unknown", "The current source state could not be classified.", False),
    )


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
    if source_family == "primary":
        return "primary"
    return "primary_or_unclear"


def secondary_source_types_for(source_type: str) -> str:
    if source_type in META_ANALYSIS_TYPES:
        return join_values([source_type, "review"])
    if source_type in STRUCTURED_REVIEW_TYPES | NARRATIVE_REVIEW_TYPES:
        return join_values([source_type, "review"]) if source_type != "review" else "review"
    if source_type in GUIDELINE_TYPES:
        return source_type
    return ""


def source_status_from_domain_rows(domain_rows: list[dict], literature_row: dict | None = None, metadata: dict | None = None) -> dict:
    literature_row = literature_row or {}
    metadata = metadata or {}
    metadata_non_primary_flags = thesis_or_dissertation_flags(metadata)
    if metadata_non_primary_flags:
        return {
            "source_family": "non_primary_publication",
            "source_type": "non_primary_publication",
            "secondary_source_types": "",
            "primary_secondary_source_type": "",
            "non_primary_flags": metadata_non_primary_flags,
            "literature_type_confidence": "high",
            "paper_type_reason": "Deterministic publication metadata indicates thesis or dissertation.",
        }
    model_row = domain_rows[0] if domain_rows else {}
    source_family = clean(model_row.get("paper_type_group", "")) or clean(model_row.get("source_family", ""))
    source_family = source_family or clean(literature_row.get("source_family", "")) or "primary_or_unclear"
    source_type = (
        clean(model_row.get("paper_type", ""))
        or clean(model_row.get("source_type", ""))
        or clean(model_row.get("primary_secondary_source_type", ""))
        or source_type_for(literature_row)
    )
    if source_family == "primary" and source_type == "primary_or_unclear":
        source_type = "primary"
    if source_family in {"primary", "primary_or_unclear"} and not source_type:
        source_type = source_family
    secondary_source_types = (
        clean(model_row.get("secondary_source_types", ""))
        or clean(literature_row.get("secondary_source_types", ""))
        or secondary_source_types_for(source_type)
    )
    primary_secondary_source_type = (
        clean(model_row.get("primary_secondary_source_type", ""))
        or clean(literature_row.get("primary_secondary_source_type", ""))
    )
    if source_family == "secondary_literature" and not primary_secondary_source_type:
        primary_secondary_source_type = source_type
    non_primary_flags = clean(model_row.get("non_primary_flags", "")) or clean(literature_row.get("non_primary_flags", ""))
    if source_family == "non_primary_publication" and not non_primary_flags and source_type:
        non_primary_flags = source_type
    return {
        "source_family": source_family,
        "source_type": source_type,
        "secondary_source_types": secondary_source_types,
        "primary_secondary_source_type": primary_secondary_source_type,
        "non_primary_flags": non_primary_flags,
        "literature_type_confidence": clean(model_row.get("literature_type_confidence", ""))
        or clean(literature_row.get("literature_type_confidence", "")),
        "paper_type_reason": clean(model_row.get("paper_type_reason", "")),
    }


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
        return "meta_analysis_evidence_schema"
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
        "primary": 10,
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
    literature_df: pd.DataFrame | None = None,
    domain_df: pd.DataFrame | None = None,
    *,
    fulltext_dir: Path,
    generated_at_utc: str,
    include_non_retained: bool = False,
    scoped_dois: set[str] | None = None,
    manual_overrides: dict[str, dict] | None = None,
    manual_fulltext_access_overrides: dict[str, dict] | None = None,
    paper_root: Path = DEFAULT_PAPER_ROOT,
    source_identity_audit: Path = DEFAULT_SOURCE_IDENTITY_AUDIT,
) -> list[dict]:
    prescreen = prescreen_context_by_doi(prescreen_df)
    prescreen_dois = {
        normalize_doi(row.get("doi", ""))
        for row in prescreen_df.to_dict("records")
        if normalize_doi(row.get("doi", ""))
    }
    literature_by_doi = row_by_doi(literature_df if literature_df is not None else pd.DataFrame())
    domain_by_doi = domain_routing_by_doi(domain_df if domain_df is not None else pd.DataFrame())
    rows: list[dict] = []
    scoped_dois = scoped_dois or set()
    manual_overrides = manual_overrides or {}
    manual_fulltext_access_overrides = manual_fulltext_access_overrides or {}
    local_pdf_index = build_local_pdf_index(paper_root)
    canonical_artifact_dir = fulltext_dir / CANONICAL_FULLTEXT_ARTICLE_DIR
    source_identity_gate = (
        SourceIdentityAuditGate(source_identity_audit)
        if canonical_artifact_dir.is_dir() and next(canonical_artifact_dir.glob("*.json"), None)
        else None
    )

    for metadata in metadata_df.to_dict("records"):
        doi = normalize_doi(metadata.get("doi", ""))
        if not doi:
            continue
        if scoped_dois and doi not in scoped_dois:
            continue
        context = prescreen.get(doi, {})
        literature_row = literature_by_doi.get(doi, {})
        domain_rows = domain_by_doi.get(doi, [])
        source_status = source_status_from_domain_rows(domain_rows, literature_row, metadata)
        route_literature_row = {**literature_row, **source_status}
        if doi in prescreen_dois:
            retained = bool(context.get("retained"))
        elif domain_rows:
            retained = any(truthy(row.get("retained_for_extraction_candidate", True)) for row in domain_rows)
        else:
            retained = truthy(literature_row.get("retained_for_extraction_candidate", False))
        if not retained and not include_non_retained:
            continue

        source_family = clean(source_status.get("source_family", "")) or "primary_or_unclear"
        source_type = clean(source_status.get("source_type", "")) or source_type_for(route_literature_row)

        tags = [tag for tag in context.get("routing_tags", []) if tag != "uncertain"]
        manual_override = manual_overrides.get(doi, {})
        fulltext_access_override = manual_fulltext_access_overrides.get(doi, {})
        access_metadata = apply_fulltext_access_override(metadata, fulltext_access_override)
        manual_fulltext_access_action = clean(fulltext_access_override.get("manual_access_action", ""))
        manual_fulltext_access_reason = clean(fulltext_access_override.get("manual_reason", ""))
        domains = domain_plan_for(
            doi=doi,
            source_family=source_family,
            fallback_tags=tags,
            domain_by_doi=domain_by_doi,
            manual_override=manual_override,
        )
        fulltext_status = fulltext_status_for_doi(
            doi,
            fulltext_dir,
            source_identity_gate=source_identity_gate,
            source_identity_audit=source_identity_audit,
        )
        local_pdf_status = local_pdf_status_for_doi(doi, local_pdf_index)
        pdf_candidates = metadata_pdf_url_candidates(access_metadata)
        probable_pdf_candidates = metadata_probable_pdf_url_candidates(access_metadata)
        other_url_candidates = metadata_other_url_candidates(access_metadata)
        pdf_quality = metadata_pdf_url_quality(access_metadata)
        access = access_tier(access_metadata, fulltext_status, local_pdf_status)
        if manual_fulltext_access_action == "abstract_only":
            # Keep a valid local/full-text artifact in the corpus while making
            # the selected extraction source explicitly abstract-only. This is
            # used when the full text is valid but unsuitable for the current
            # extraction workflow (for example, an unvalidated language).
            access = "abstract_only" if clean(access_metadata.get("abstract", "")) else "no_usable_text"
        action = route_action_for_access(access, source_family)
        source_text_state, source_text_state_reason, source_identity_verified = (
            source_text_state_for_access(access)
        )
        if manual_fulltext_access_action == "abstract_only" and manual_fulltext_access_reason:
            source_text_state_reason = manual_fulltext_access_reason
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
                    "retained_for_extraction_candidate": route_retained,
                    "study_title": clean(metadata.get("study_title", "")) or clean(literature_row.get("study_title", "")),
                    "study_year": clean(metadata.get("study_year", "")) or clean(literature_row.get("study_year", "")),
                    "publication_type": clean(metadata.get("publication_type", "")) or clean(literature_row.get("publication_type", "")),
                    "source_family": source_family,
                    "source_type": source_type,
                    "secondary_source_types": clean(route_literature_row.get("secondary_source_types", "")),
                    "primary_secondary_source_type": clean(route_literature_row.get("primary_secondary_source_type", "")),
                    "literature_type_confidence": clean(route_literature_row.get("literature_type_confidence", "")),
                    "paper_type_reason": clean(route_literature_row.get("paper_type_reason", "")),
                    "non_primary_flags": clean(route_literature_row.get("non_primary_flags", "")),
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
                    "source_text_state": source_text_state,
                    "source_text_state_reason": source_text_state_reason,
                    "source_identity_verified": source_identity_verified,
                    "has_abstract": bool(clean(metadata.get("abstract", ""))),
                    "has_pdf_url": bool(pdf_candidates),
                    "has_probable_pdf_url": bool(probable_pdf_candidates),
                    "has_converted_full_text": bool(fulltext_status.get("has_converted_full_text")),
                    "fulltext_artifact_paths": clean(fulltext_status.get("fulltext_artifact_paths", "")),
                    "fulltext_char_count": int(fulltext_status.get("fulltext_char_count", 0) or 0),
                    "has_local_pdf": bool(local_pdf_status.get("has_local_pdf")),
                    "local_pdf_paths": clean(local_pdf_status.get("local_pdf_paths", "")),
                    "local_pdf_count": int(local_pdf_status.get("local_pdf_count", 0) or 0),
                    "open_access_status": clean(access_metadata.get("open_access_status", "")),
                    "best_pdf_url": probable_pdf_candidates[0] if probable_pdf_candidates else clean(access_metadata.get("best_pdf_url", "")),
                    "pdf_url_candidates": join_candidates(pdf_candidates),
                    "probable_pdf_url_candidates": join_candidates(probable_pdf_candidates),
                    "other_url_candidates": join_candidates(other_url_candidates),
                    "pdf_url_quality": pdf_quality,
                    "manual_fulltext_access_action": manual_fulltext_access_action,
                    "manual_fulltext_access_reason": manual_fulltext_access_reason,
                    "route_action": row_action,
                    "prompt_profile": prompt_profile,
                    "schema_profile": schema_profile,
                    "route_priority": route_priority(source_family, source_type, domain_route, access),
                    "route_confidence": route_confidence(route_literature_row, domain_route, domain_tags, domain_confidence),
                    "route_basis": route_basis(route_literature_row, domain_tags, domain_route, domain_basis),
                }
            )
    rows.sort(key=lambda row: (int(row["route_priority"]), row["doi"], row["domain_route"], row["route_id"]))
    return rows


def route_rows_by_doi(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        doi = normalize_doi(row.get("doi", ""))
        if doi:
            out[doi].append(row)
    return dict(out)


def literature_status_from_route_rows(rows: list[dict]) -> dict:
    if not rows:
        return {}
    row = rows[0]
    return {
        "literature_source_family": clean(row.get("source_family", "")),
        "literature_source_type": clean(row.get("source_type", "")),
        "literature_type_confidence": clean(row.get("literature_type_confidence", "")),
        "primary_secondary_source_type": clean(row.get("primary_secondary_source_type", "")),
        "secondary_source_types": clean(row.get("secondary_source_types", "")),
        "non_primary_flags": clean(row.get("non_primary_flags", "")),
    }


def join_route_values(rows: list[dict], field: str) -> str:
    values: list[str] = []
    for row in rows:
        for value in split_values(row.get(field, "")):
            if value and value not in values:
                values.append(value)
    return join_values(values)


def best_access_tier(rows: list[dict]) -> str:
    access_order = {
        "full_text_available": 0,
        "local_pdf_available": 1,
        "pdf_download_url_available": 2,
        "abstract_only": 3,
        "no_usable_text": 4,
    }
    best = ""
    best_rank = 999
    for row in rows:
        access = clean(row.get("access_tier", ""))
        rank = access_order.get(access, 999)
        if rank < best_rank:
            best = access
            best_rank = rank
    return best


def route_status_for_candidate(
    *,
    route_rows: list[dict],
    prescreen_retained: bool,
) -> tuple[str, str, bool]:
    if not route_rows:
        if prescreen_retained:
            return (
                "not_routed_for_extraction",
                "Retained at pre-screening, but no active extraction route was produced.",
                False,
            )
        return (
            "not_retained_for_extraction",
            "Not retained by the current screening and routing inputs.",
            False,
        )

    retained_rows = [row for row in route_rows if truthy(row.get("retained_for_extraction_candidate", False))]
    status_rows = retained_rows or route_rows
    actions = {clean(row.get("route_action", "")) for row in status_rows}
    access = best_access_tier(status_rows)
    action_text = join_values(sorted(action for action in actions if action))
    reason = f"route_action={action_text or '<blank>'}; access_tier={access or '<blank>'}"
    if retained_rows:
        if "extract_from_full_text" in actions:
            return "ready_for_article_text_extraction", "Converted article text is available.", True
        if "extract_from_abstract_only" in actions:
            return "ready_for_abstract_extraction", "Only abstract-level extraction is currently available.", True
        if "convert_local_pdf_then_extract" in actions:
            return "needs_pdf_conversion", "A valid local PDF exists and needs article-text conversion.", True
        if "download_pdf_then_extract" in actions:
            return "needs_pdf_download", "A probable PDF URL exists and should be downloaded before article-text extraction.", True
        if "hold_until_text_available" in actions:
            return "hold_until_text_available", "No usable abstract or article text is available yet.", True
        return "retained_for_extraction", reason, True

    if "exclude_after_model_screen" in actions:
        return "excluded_after_domain_screen", reason, False
    if "skip_or_context_only" in actions:
        return "context_only_or_skip", reason, False
    return "not_retained_for_extraction", reason, False


def build_candidate_status_updates(
    *,
    candidate_df: pd.DataFrame,
    prescreen_df: pd.DataFrame,
    literature_df: pd.DataFrame | None = None,
    route_rows: list[dict],
    generated_at_utc: str,
) -> pd.DataFrame:
    if candidate_df.empty or "doi" not in candidate_df.columns:
        return pd.DataFrame()

    prescreen_by_doi = prescreen_status_by_doi(prescreen_df)
    literature_by_doi = literature_status_by_doi(literature_df if literature_df is not None else pd.DataFrame())
    routes_by_doi = route_rows_by_doi(route_rows)
    records: list[dict] = []

    for candidate in candidate_df.to_dict("records"):
        doi = normalize_doi(candidate.get("doi", ""))
        if not doi:
            continue
        publication_classification = classify_publication_stage(candidate)
        prescreen = prescreen_by_doi.get(doi, {})
        rows = routes_by_doi.get(doi, [])
        literature = dict(literature_by_doi.get(doi, {}))
        for key, value in literature_status_from_route_rows(rows).items():
            if clean(value):
                literature[key] = value
        prescreen_retained = bool(prescreen.get("prescreen_retained_for_extraction_candidate", False))
        route_status, route_reason, retained_for_extraction = route_status_for_candidate(
            route_rows=rows,
            prescreen_retained=prescreen_retained,
        )
        publication_stage = clean(publication_classification.get("publication_stage", ""))
        is_preprint_like = bool(publication_classification.get("is_preprint_like", False))
        preprint_signal_strength = clean(publication_classification.get("preprint_signal_strength", ""))
        preprint_detection_basis = clean(publication_classification.get("preprint_detection_basis", ""))
        retained_rows = [row for row in rows if truthy(row.get("retained_for_extraction_candidate", False))]
        best_access = best_access_tier(retained_rows or rows)
        source_text_state, source_text_state_reason, source_identity_verified = (
            source_text_state_for_access(best_access)
        )
        if not retained_for_extraction:
            source_text_state = "excluded_from_extraction"
            source_text_state_reason = route_reason
            source_identity_verified = False
        published_lookup_status = clean(candidate.get("published_version_lookup_status", ""))
        published_version_doi = clean(candidate.get("published_version_doi", ""))

        records.append(
            {
                "doi": doi,
                "publication_stage": publication_stage,
                "is_preprint_like": is_preprint_like,
                "preprint_signal_strength": preprint_signal_strength,
                "preprint_detection_basis": preprint_detection_basis,
                "published_version_lookup_status": published_lookup_status,
                "published_version_doi": published_version_doi,
                "prescreen_retained_for_extraction_candidate": prescreen_retained,
                "prescreen_decisions": join_values(prescreen.get("prescreen_decisions", [])),
                "prescreen_actions": join_values(prescreen.get("prescreen_actions", [])),
                "prescreen_reasons": join_values(prescreen.get("prescreen_reasons", [])),
                "prescreen_routing_tags": join_values(prescreen.get("prescreen_routing_tags", [])),
                "literature_source_family": clean(literature.get("literature_source_family", "")),
                "literature_source_type": clean(literature.get("literature_source_type", "")),
                "literature_type_confidence": clean(literature.get("literature_type_confidence", "")),
                "primary_secondary_source_type": clean(literature.get("primary_secondary_source_type", "")),
                "secondary_source_types": clean(literature.get("secondary_source_types", "")),
                "non_primary_flags": clean(literature.get("non_primary_flags", "")),
                "retained_for_extraction_candidate": retained_for_extraction,
                "extraction_route_status": route_status,
                "extraction_route_reason": route_reason,
                "extraction_route_count": len(rows),
                "retained_extraction_route_count": len(retained_rows),
                "extraction_route_actions": join_route_values(rows, "route_action"),
                "extraction_domain_routes": join_route_values(rows, "domain_route"),
                "extraction_domain_screening_decisions": join_route_values(rows, "domain_screening_decision"),
                "extraction_prompt_profiles": join_route_values(rows, "prompt_profile"),
                "extraction_schema_profiles": join_route_values(rows, "schema_profile"),
                "best_extraction_access_tier": best_access_tier(rows),
                "source_text_state": source_text_state,
                "source_text_state_reason": source_text_state_reason,
                "source_identity_verified": source_identity_verified,
                "has_converted_full_text": any(truthy(row.get("has_converted_full_text", False)) for row in rows),
                "fulltext_artifact_paths": join_route_values(rows, "fulltext_artifact_paths"),
                "fulltext_char_count": max((int(row.get("fulltext_char_count", 0) or 0) for row in rows), default=0),
                "manual_fulltext_access_action": join_route_values(rows, "manual_fulltext_access_action"),
                "manual_fulltext_access_reason": join_route_values(rows, "manual_fulltext_access_reason"),
                "extraction_routes_table_version": TABLE_VERSION,
                "extraction_routes_updated_at_utc": generated_at_utc,
            }
        )

    return pd.DataFrame(records)


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


def build_extraction_routes(
    *,
    metadata_table: Path = DEFAULT_METADATA_TABLE,
    candidate_table: Path = DEFAULT_CANDIDATE_TABLE,
    prescreen_table: Path = DEFAULT_PRESCREEN_TABLE,
    domain_table: Path | None = None,
    manual_overrides_path: Path | None = DEFAULT_MANUAL_ROUTE_OVERRIDES,
    manual_fulltext_access_overrides_path: Path | None = DEFAULT_MANUAL_FULLTEXT_ACCESS_OVERRIDES,
    fulltext_dir: Path = DEFAULT_FULLTEXT_DIR,
    source_identity_audit: Path = DEFAULT_SOURCE_IDENTITY_AUDIT,
    paper_root: Path = DEFAULT_PAPER_ROOT,
    output_table: Path = DEFAULT_OUTPUT_TABLE,
    summary_json: Path = DEFAULT_SUMMARY_JSON,
    counts_csv: Path = DEFAULT_COUNTS_CSV,
    scoped_dois: set[str] | None = None,
    doi_file_label: str = "",
    include_non_retained: bool = False,
    update_candidate_table: bool = True,
) -> dict:
    metadata_table = Path(metadata_table).resolve()
    candidate_table = Path(candidate_table).resolve()
    prescreen_table = Path(prescreen_table).resolve()
    domain_table = Path(domain_table).resolve() if domain_table is not None else None
    manual_overrides_path = Path(manual_overrides_path).resolve() if manual_overrides_path is not None else None
    manual_fulltext_access_overrides_path = (
        Path(manual_fulltext_access_overrides_path).resolve()
        if manual_fulltext_access_overrides_path is not None
        else None
    )
    fulltext_dir = Path(fulltext_dir).resolve()
    source_identity_audit = Path(source_identity_audit).resolve()
    paper_root = Path(paper_root).resolve()
    output_table = Path(output_table).resolve()
    summary_json = Path(summary_json).resolve()
    counts_csv = Path(counts_csv).resolve()
    scoped_dois = scoped_dois or set()

    metadata_df = read_table(metadata_table)
    prescreen_df = read_table(prescreen_table)
    domain_df = read_table(domain_table) if domain_table is not None else pd.DataFrame()
    manual_overrides = load_manual_route_overrides(manual_overrides_path)
    manual_fulltext_access_overrides = load_manual_fulltext_access_overrides(manual_fulltext_access_overrides_path)
    generated_at_utc = now_utc()
    rows = build_route_rows(
        metadata_df,
        prescreen_df,
        domain_df=domain_df,
        fulltext_dir=fulltext_dir,
        generated_at_utc=generated_at_utc,
        include_non_retained=include_non_retained,
        scoped_dois=scoped_dois,
        manual_overrides=manual_overrides,
        manual_fulltext_access_overrides=manual_fulltext_access_overrides,
        paper_root=paper_root,
        source_identity_audit=source_identity_audit,
    )

    write_route_table(output_table, rows)
    candidate_update = {}
    if update_candidate_table:
        candidate_df = read_table(candidate_table)
        if scoped_dois and not candidate_df.empty and "doi" in candidate_df.columns:
            candidate_df = candidate_df[candidate_df["doi"].map(lambda value: normalize_doi(value) in scoped_dois)].copy()
        updates = build_candidate_status_updates(
            candidate_df=candidate_df,
            prescreen_df=prescreen_df,
            route_rows=rows,
            generated_at_utc=generated_at_utc,
        )
        candidate_update = apply_candidate_updates(
            candidate_table=candidate_table,
            updates=updates,
            column_defaults=CANDIDATE_STATUS_DEFAULTS,
        )
    summary, counts = build_summary(
        rows,
        inputs={
            "metadata_table": str(metadata_table),
            "candidate_table": str(candidate_table),
            "prescreen_decisions_table": str(prescreen_table),
            "domain_routing_table": str(domain_table) if domain_table is not None else "",
            "manual_route_overrides": str(manual_overrides_path) if manual_overrides_path is not None else "",
            "manual_override_dois": len(manual_overrides),
            "manual_fulltext_access_overrides": str(manual_fulltext_access_overrides_path)
            if manual_fulltext_access_overrides_path is not None
            else "",
            "manual_fulltext_access_override_dois": len(manual_fulltext_access_overrides),
            "fulltext_dir": str(fulltext_dir),
            "source_identity_audit": str(source_identity_audit),
            "paper_root": str(paper_root),
            "doi_file": doi_file_label,
            "include_non_retained": include_non_retained,
            "update_candidate_table": update_candidate_table,
            "scoped_dois": len(scoped_dois),
        },
    )
    summary["output_table"] = str(output_table)
    summary["summary_json"] = str(summary_json)
    summary["counts_csv"] = str(counts_csv)
    summary["candidate_table_update"] = candidate_update
    write_json(summary_json, summary)
    write_counts_csv(counts_csv, counts)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build extraction-route table from corpus tables.")
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--prescreen-decisions-table", default=str(DEFAULT_PRESCREEN_TABLE))
    parser.add_argument(
        "--domain-routing-table",
        default=str(DEFAULT_DOMAIN_ROUTING_TABLE),
        help="Optional model-assigned domain and paper-type routing table. If omitted, routes stay on coarse fallback routes by access.",
    )
    parser.add_argument("--fulltext-dir", default=str(DEFAULT_FULLTEXT_DIR))
    parser.add_argument("--source-identity-audit", default=str(DEFAULT_SOURCE_IDENTITY_AUDIT))
    parser.add_argument("--paper-root", default=str(DEFAULT_PAPER_ROOT), help="Root directory containing local paper PDFs.")
    parser.add_argument("--output-table", default=str(DEFAULT_OUTPUT_TABLE))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY_JSON))
    parser.add_argument("--counts-csv", default=str(DEFAULT_COUNTS_CSV))
    parser.add_argument("--manual-route-overrides", default=str(DEFAULT_MANUAL_ROUTE_OVERRIDES))
    parser.add_argument("--manual-fulltext-access-overrides", default=str(DEFAULT_MANUAL_FULLTEXT_ACCESS_OVERRIDES))
    parser.add_argument("--doi-file", default="", help="Optional DOI list for a scoped route-table build.")
    parser.add_argument("--include-non-retained", action="store_true", help="Route all metadata rows, not only retained pre-screen candidates.")
    parser.add_argument(
        "--no-update-candidate-table",
        action="store_true",
        help="Build route artifacts without writing DOI-level route status back to candidate_papers.parquet.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    metadata_table = Path(args.metadata_table).resolve()
    candidate_table = Path(args.candidate_table).resolve()
    prescreen_table = Path(args.prescreen_decisions_table).resolve()
    domain_table = Path(args.domain_routing_table).resolve() if clean(args.domain_routing_table) else None
    if domain_table is not None and not domain_table.exists():
        domain_table = None
    manual_overrides_path = Path(args.manual_route_overrides).resolve() if clean(args.manual_route_overrides) else None
    manual_fulltext_access_overrides_path = (
        Path(args.manual_fulltext_access_overrides).resolve()
        if clean(args.manual_fulltext_access_overrides)
        else None
    )
    fulltext_dir = Path(args.fulltext_dir).resolve()
    source_identity_audit = Path(args.source_identity_audit).resolve()
    paper_root = Path(args.paper_root).resolve()
    scoped_dois = read_doi_file(Path(args.doi_file).resolve()) if clean(args.doi_file) else set()

    output_table = Path(args.output_table).resolve()
    summary_json = Path(args.summary_json).resolve()
    counts_csv = Path(args.counts_csv).resolve()
    summary = build_extraction_routes(
        metadata_table=metadata_table,
        candidate_table=candidate_table,
        prescreen_table=prescreen_table,
        domain_table=domain_table,
        manual_overrides_path=manual_overrides_path,
        manual_fulltext_access_overrides_path=manual_fulltext_access_overrides_path,
        fulltext_dir=fulltext_dir,
        source_identity_audit=source_identity_audit,
        paper_root=paper_root,
        output_table=output_table,
        summary_json=summary_json,
        counts_csv=counts_csv,
        scoped_dois=scoped_dois,
        doi_file_label=str(Path(args.doi_file).resolve()) if clean(args.doi_file) else "",
        include_non_retained=bool(args.include_non_retained),
        update_candidate_table=not bool(args.no_update_candidate_table),
    )

    print(f"Extraction route rows: {summary['route_rows']:,}")
    print(f"Routed DOIs: {summary['routed_dois']:,}")
    print(f"By prompt profile: {summary['by_prompt_profile']}")
    print(f"By access tier: {summary['by_access_tier']}")
    print(f"Route table: {output_table}")
    print(f"Summary: {summary_json}")
    print(f"Counts: {counts_csv}")
    update = summary.get("candidate_table_update", {})
    if update:
        print(
            "Candidate table update: "
            f"matched_rows={update.get('matched_candidate_rows', 0):,} "
            f"updated_rows={update.get('updated_candidate_rows', 0):,} "
            f"updated_cells={update.get('updated_cells', 0):,}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
