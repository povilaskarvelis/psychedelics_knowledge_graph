"""Simple route-to-prompt/schema matrix for extraction profiles.

The profile identity is domain + paper type + text depth. This module keeps
that mapping explicit and reviewable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

TEXT_DEPTH_ARTICLE = "article_text"
TEXT_DEPTH_ABSTRACT = "abstract_only"
TEXT_DEPTHS = {TEXT_DEPTH_ARTICLE, TEXT_DEPTH_ABSTRACT}

ARTICLE_TEXT_ALIASES = {
    "",
    TEXT_DEPTH_ARTICLE,
    "paper_text",
    "body_text",
    "full_text",
    "full_text_seen",
    "full_text_available",
}
ABSTRACT_ONLY_ALIASES = {TEXT_DEPTH_ABSTRACT, "abstract"}

PAPER_TYPE_PRIMARY = "primary_study"
PAPER_TYPE_META_ANALYSIS = "meta_analysis"
PAPER_TYPE_REVIEW = "review"

PAPER_TYPE_PROMPT_PATHS = {
    (PAPER_TYPE_PRIMARY, TEXT_DEPTH_ARTICLE): ROOT / "docs" / "extraction_profiles" / "paper_type" / "primary_article_text.md",
    (PAPER_TYPE_PRIMARY, TEXT_DEPTH_ABSTRACT): ROOT / "docs" / "extraction_profiles" / "paper_type" / "primary_abstract_only.md",
    (PAPER_TYPE_META_ANALYSIS, TEXT_DEPTH_ARTICLE): ROOT / "docs" / "extraction_profiles" / "paper_type" / "meta_analysis_article_text.md",
    (PAPER_TYPE_META_ANALYSIS, TEXT_DEPTH_ABSTRACT): ROOT / "docs" / "extraction_profiles" / "paper_type" / "meta_analysis_abstract_only.md",
    (PAPER_TYPE_REVIEW, TEXT_DEPTH_ARTICLE): ROOT / "docs" / "extraction_profiles" / "paper_type" / "review_article_text.md",
    (PAPER_TYPE_REVIEW, TEXT_DEPTH_ABSTRACT): ROOT / "docs" / "extraction_profiles" / "paper_type" / "review_abstract_only.md",
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

PRIMARY_DOMAIN_BY_PROMPT = {prompt: domain for domain, prompt in PRIMARY_PROMPT_BY_DOMAIN.items()}

PRIMARY_SCHEMA_VERSION_BY_DOMAIN = {
    domain: f"primary_{domain}_v1"
    for domain in PRIMARY_PROMPT_BY_DOMAIN
}
PRIMARY_SCHEMA_VERSION_BY_DOMAIN["clinical_outcome"] = "primary_clinical_outcome_v1"
PRIMARY_SCHEMA_VERSION_BY_DOMAIN["general_primary"] = "primary_general_primary_v1"
PRIMARY_SCHEMA_VERSION_BY_DOMAIN["pharmacokinetics_exposure"] = "primary_pharmacokinetics_exposure_v3"


@dataclass(frozen=True)
class ExtractionProfileSpec:
    domain_route: str
    paper_type: str
    text_depth: str
    prompt_profile: str
    schema_profile: str
    prompt_path: Path | None
    schema_path: Path | None
    depth_prompt_path: Path | None
    output_schema_version: str
    extract: bool


def primary_prompt_path(domain_route: str) -> Path:
    return ROOT / "docs" / "extraction_profiles" / "primary" / f"{domain_route}.md"


def primary_schema_path(domain_route: str) -> Path:
    return ROOT / "schema" / "extraction_profiles" / "primary" / f"{domain_route}.schema.json"


def meta_analysis_schema_path(domain_route: str) -> Path:
    path = ROOT / "schema" / "extraction_profiles" / "meta_analysis" / f"{domain_route}.schema.json"
    if not path.exists():
        raise ValueError(f"No meta-analysis extraction schema for domain `{domain_route}`")
    return path


def review_schema_path(domain_route: str) -> Path:
    path = ROOT / "schema" / "extraction_profiles" / "review" / f"{domain_route}.schema.json"
    if not path.exists():
        raise ValueError(f"No review extraction schema for domain `{domain_route}`")
    return path


def paper_type_prompt_path(paper_type: str, text_depth: str) -> Path:
    return PAPER_TYPE_PROMPT_PATHS[(paper_type, normalize_text_depth(text_depth))]


def normalize_text_depth(text_depth: str) -> str:
    text = (text_depth or "").strip()
    if text in ABSTRACT_ONLY_ALIASES:
        return TEXT_DEPTH_ABSTRACT
    if text in ARTICLE_TEXT_ALIASES:
        return TEXT_DEPTH_ARTICLE
    raise ValueError(f"Unsupported text depth `{text_depth}`")


def text_depth_from_access(access_level: str) -> str:
    return normalize_text_depth(access_level)


def primary_spec_for_domain(domain_route: str, *, text_depth: str = TEXT_DEPTH_ARTICLE) -> ExtractionProfileSpec:
    text_depth = normalize_text_depth(text_depth)
    if domain_route not in PRIMARY_PROMPT_BY_DOMAIN:
        raise ValueError(f"Unsupported primary extraction domain `{domain_route}`")
    return ExtractionProfileSpec(
        domain_route=domain_route,
        paper_type=PAPER_TYPE_PRIMARY,
        text_depth=text_depth,
        prompt_profile=PRIMARY_PROMPT_BY_DOMAIN[domain_route],
        schema_profile="primary_evidence_schema",
        prompt_path=paper_type_prompt_path(PAPER_TYPE_PRIMARY, text_depth),
        schema_path=primary_schema_path(domain_route),
        depth_prompt_path=None,
        output_schema_version=PRIMARY_SCHEMA_VERSION_BY_DOMAIN[domain_route],
        extract=True,
    )


def primary_spec_for_prompt(prompt_profile: str, *, text_depth: str = TEXT_DEPTH_ARTICLE) -> ExtractionProfileSpec:
    if prompt_profile not in PRIMARY_DOMAIN_BY_PROMPT:
        raise ValueError(f"Unsupported primary prompt profile `{prompt_profile}`")
    return primary_spec_for_domain(PRIMARY_DOMAIN_BY_PROMPT[prompt_profile], text_depth=text_depth)


def spec_for_route(
    *,
    domain_route: str,
    paper_type: str,
    text_depth: str = TEXT_DEPTH_ARTICLE,
) -> ExtractionProfileSpec:
    text_depth = normalize_text_depth(text_depth)
    if paper_type == PAPER_TYPE_PRIMARY:
        return primary_spec_for_domain(domain_route, text_depth=text_depth)
    if paper_type == PAPER_TYPE_META_ANALYSIS:
        return ExtractionProfileSpec(
            domain_route=domain_route,
            paper_type=paper_type,
            text_depth=text_depth,
            prompt_profile="secondary_meta_analysis",
            schema_profile="meta_analysis_evidence_schema",
            prompt_path=paper_type_prompt_path(PAPER_TYPE_META_ANALYSIS, text_depth),
            schema_path=meta_analysis_schema_path(domain_route),
            depth_prompt_path=None,
            output_schema_version="meta_analysis_evidence_v1",
            extract=True,
        )
    if paper_type == PAPER_TYPE_REVIEW:
        return ExtractionProfileSpec(
            domain_route=domain_route,
            paper_type=paper_type,
            text_depth=text_depth,
            prompt_profile="secondary_review_coverage",
            schema_profile="review_coverage_schema",
            prompt_path=paper_type_prompt_path(PAPER_TYPE_REVIEW, text_depth),
            schema_path=review_schema_path(domain_route),
            depth_prompt_path=None,
            output_schema_version="review_coverage_v1",
            extract=True,
        )
    return ExtractionProfileSpec(
        domain_route=domain_route,
        paper_type=paper_type,
        text_depth=text_depth,
        prompt_profile="no_extraction",
        schema_profile="no_extraction_schema",
        prompt_path=None,
        schema_path=None,
        depth_prompt_path=None,
        output_schema_version="",
        extract=False,
    )
