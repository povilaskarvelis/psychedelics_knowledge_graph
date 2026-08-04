"""Route-aware extraction profile registry.

Profiles connect route-table labels to concrete prompt and schema files. The
route-aware runner uses this registry so model calls are driven by
`prompt_profile` and `schema_profile`, not by DOI or dataset alone.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path

try:
    from pipeline.extract.extraction_profile_matrix import (
        TEXT_DEPTH_ABSTRACT,
        TEXT_DEPTH_ARTICLE,
        normalize_text_depth,
        primary_spec_for_prompt,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    import sys

    ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT_FOR_IMPORT))
    from pipeline.extract.extraction_profile_matrix import (
        TEXT_DEPTH_ABSTRACT,
        TEXT_DEPTH_ARTICLE,
        normalize_text_depth,
        primary_spec_for_prompt,
    )


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_MODES = ("native", "prompt", "both")
PROFILE_STATUS_RUNNABLE = "runnable"
PROFILE_STATUS_SCAFFOLD = "scaffold"
PROFILE_STATUS_TERMINAL_NO_MODEL = "terminal_no_model"
PROFILE_STATUS_LEGACY_READ_ONLY = "legacy_read_only"
MODEL_PROFILE_STATUSES = {PROFILE_STATUS_RUNNABLE, PROFILE_STATUS_SCAFFOLD}
VALID_PROFILE_STATUSES = {
    PROFILE_STATUS_RUNNABLE,
    PROFILE_STATUS_SCAFFOLD,
    PROFILE_STATUS_TERMINAL_NO_MODEL,
    PROFILE_STATUS_LEGACY_READ_ONLY,
}

DOMAIN_PROMPT_PATHS = {
    "clinical_outcome": ROOT / "docs" / "extraction_domains" / "clinical_outcome.md",
    "safety_tolerability": ROOT / "docs" / "extraction_domains" / "safety_tolerability.md",
    "molecular_target": ROOT / "docs" / "extraction_domains" / "molecular_target.md",
    "molecular_pathway_readout": ROOT / "docs" / "extraction_domains" / "molecular_pathway_readout.md",
    "brain_system": ROOT / "docs" / "extraction_domains" / "brain_system.md",
    "cognitive_behavioral": ROOT / "docs" / "extraction_domains" / "cognitive_behavioral.md",
    "subjective_experience": ROOT / "docs" / "extraction_domains" / "subjective_experience.md",
    "pharmacokinetics_exposure": ROOT / "docs" / "extraction_domains" / "pharmacokinetics_exposure.md",
    "intervention_context": ROOT / "docs" / "extraction_domains" / "intervention_context.md",
    "real_world_public_health": ROOT / "docs" / "extraction_domains" / "real_world_public_health.md",
    "general_primary": ROOT / "docs" / "extraction_domains" / "general_primary.md",
    "general_topic_coverage": ROOT / "docs" / "extraction_domains" / "general_topic_coverage.md",
}


@dataclass(frozen=True)
class RouteExtractionProfile:
    prompt_profile: str
    schema_profile: str
    output_family: str
    output_schema_version: str
    status: str
    prompt_path: Path | None
    schema_path: Path | None
    default_max_output_tokens: int
    description: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.prompt_profile, self.schema_profile)

    @property
    def has_model_contract(self) -> bool:
        has_schema = self.schema_path is not None or self.schema_profile in {
            "meta_analysis_evidence_schema",
            "review_coverage_schema",
        }
        return self.status in MODEL_PROFILE_STATUSES and self.prompt_path is not None and has_schema


PRIMARY_PROMPT_PROFILES = (
    "primary_clinical",
    "primary_safety",
    "primary_molecular_target",
    "primary_molecular_pathway",
    "primary_brain_system",
    "primary_cognitive_behavioral",
    "primary_subjective_experience",
    "primary_pharmacokinetics_exposure",
    "primary_intervention_context",
    "primary_real_world_public_health",
    "primary_general",
)

REVIEW_COVERAGE_PROMPT_PROFILES = (
    "secondary_structured_review",
    "secondary_narrative_review",
    "secondary_review_coverage",
)

# These contracts remain registered only so historical v1 outputs can still be
# inspected and parsed.  New meta-analysis and review model calls must use the
# dedicated paper-centered v2 pipelines.
LEGACY_V1_SECONDARY_PROFILE_KEYS = frozenset(
    {
        ("secondary_meta_analysis", "meta_analysis_evidence_schema"),
        *((prompt, "review_coverage_schema") for prompt in REVIEW_COVERAGE_PROMPT_PROFILES),
    }
)


def is_legacy_v1_secondary_profile(prompt_profile: object, schema_profile: object) -> bool:
    return (str(prompt_profile or "").strip(), str(schema_profile or "").strip()) in LEGACY_V1_SECONDARY_PROFILE_KEYS


def task_uses_legacy_v1_secondary_profile(task: dict) -> bool:
    return is_legacy_v1_secondary_profile(*profile_key_for_task(task))


def legacy_v1_secondary_block_message(tasks: list[dict]) -> str:
    blocked = [task for task in tasks if task_uses_legacy_v1_secondary_profile(task)]
    counts: dict[str, int] = {}
    for task in blocked:
        prompt_profile, schema_profile = profile_key_for_task(task)
        key = f"{prompt_profile}/{schema_profile}"
        counts[key] = counts.get(key, 0) + 1
    details = ", ".join(f"{key}={count}" for key, count in sorted(counts.items()))
    return (
        "Legacy v1 secondary extraction is permanently disabled"
        + (f" ({details})" if details else "")
        + ". Meta-analyses must use build_meta_analysis_v2_tasks.py with "
        "run_meta_analysis_v2_batch_api.py; reviews must use "
        "build_review_relationship_tasks.py with run_review_relationship_batch_api.py."
    )

ENTITY_TYPES_BY_DOMAIN = {
    "clinical_outcome": {"disorder", "symptom_or_outcome", "not_applicable", "uncertain"},
    "safety_tolerability": {"safety_event", "not_applicable", "uncertain"},
    "molecular_target": {"target", "not_applicable", "uncertain"},
    "molecular_pathway_readout": {"pathway_process", "molecular_readout", "not_applicable", "uncertain"},
    "brain_system": {
        "brain_region",
        "brain_network",
        "neural_circuit",
        "biomarker_readout",
        "not_applicable",
        "uncertain",
    },
    "cognitive_behavioral": {"cognitive_behavioral_construct", "not_applicable", "uncertain"},
    "subjective_experience": {"subjective_experience_construct", "not_applicable", "uncertain"},
    "pharmacokinetics_exposure": {
        "pharmacokinetic_parameter",
        "compound",
        "target",
        "pathway_process",
        "not_applicable",
        "uncertain",
    },
    "intervention_context": {"intervention_component", "not_applicable", "uncertain"},
    "real_world_public_health": {"public_health_measure", "not_applicable", "uncertain"},
    "general_topic": {"general_topic", "not_applicable", "uncertain"},
    "general_topic_coverage": {"general_topic", "not_applicable", "uncertain"},
}

META_ANALYSIS_SCHEMA_DIR = ROOT / "schema" / "extraction_profiles" / "meta_analysis"
META_ANALYSIS_SCHEMA_PATHS = {
    domain: META_ANALYSIS_SCHEMA_DIR / f"{domain}.schema.json"
    for domain in ENTITY_TYPES_BY_DOMAIN
}
REVIEW_SCHEMA_DIR = ROOT / "schema" / "extraction_profiles" / "review"
REVIEW_SCHEMA_PATHS = {
    domain: REVIEW_SCHEMA_DIR / f"{domain}.schema.json"
    for domain in ENTITY_TYPES_BY_DOMAIN
}

RESULT_DIRECTION_NOT_APPLICABLE_DOMAINS = {
    domain
    for domain in ENTITY_TYPES_BY_DOMAIN
    if domain not in {"clinical_outcome", "safety_tolerability"}
}

PAPER_TYPE_PROMPT_PATHS = {
    ("primary", TEXT_DEPTH_ARTICLE): ROOT / "docs" / "extraction_profiles" / "paper_type" / "primary_article_text.md",
    ("primary", TEXT_DEPTH_ABSTRACT): ROOT / "docs" / "extraction_profiles" / "paper_type" / "primary_abstract_only.md",
    ("meta_analysis", TEXT_DEPTH_ARTICLE): ROOT / "docs" / "extraction_profiles" / "paper_type" / "meta_analysis_article_text.md",
    ("meta_analysis", TEXT_DEPTH_ABSTRACT): ROOT / "docs" / "extraction_profiles" / "paper_type" / "meta_analysis_abstract_only.md",
    ("review", TEXT_DEPTH_ARTICLE): ROOT / "docs" / "extraction_profiles" / "paper_type" / "review_article_text.md",
    ("review", TEXT_DEPTH_ABSTRACT): ROOT / "docs" / "extraction_profiles" / "paper_type" / "review_abstract_only.md",
}


def primary_profile(prompt_profile: str) -> RouteExtractionProfile:
    spec = primary_spec_for_prompt(prompt_profile)
    return RouteExtractionProfile(
        prompt_profile=prompt_profile,
        schema_profile=spec.schema_profile,
        output_family="primary_evidence",
        output_schema_version=spec.output_schema_version,
        status=PROFILE_STATUS_RUNNABLE,
        prompt_path=PAPER_TYPE_PROMPT_PATHS[("primary", TEXT_DEPTH_ARTICLE)],
        schema_path=spec.schema_path,
        default_max_output_tokens=16384,
        description=f"Extract primary empirical evidence for {spec.domain_route}.",
    )


def review_coverage_profile(prompt_profile: str) -> RouteExtractionProfile:
    return RouteExtractionProfile(
        prompt_profile=prompt_profile,
        schema_profile="review_coverage_schema",
        output_family="review_coverage",
        output_schema_version="review_coverage_v1",
        status=PROFILE_STATUS_LEGACY_READ_ONLY,
        prompt_path=PAPER_TYPE_PROMPT_PATHS[("review", TEXT_DEPTH_ARTICLE)],
        schema_path=None,
        default_max_output_tokens=16384,
        description="Legacy v1 review contract retained only for historical parsing; new model calls are blocked.",
    )


ROUTE_EXTRACTION_PROFILES: dict[tuple[str, str], RouteExtractionProfile] = {
    ("secondary_meta_analysis", "meta_analysis_evidence_schema"): RouteExtractionProfile(
        prompt_profile="secondary_meta_analysis",
        schema_profile="meta_analysis_evidence_schema",
        output_family="meta_analysis_evidence",
        output_schema_version="meta_analysis_evidence_v1",
        status=PROFILE_STATUS_LEGACY_READ_ONLY,
        prompt_path=PAPER_TYPE_PROMPT_PATHS[("meta_analysis", TEXT_DEPTH_ARTICLE)],
        schema_path=None,
        default_max_output_tokens=24576,
        description="Legacy v1 meta-analysis contract retained only for historical parsing; new model calls are blocked.",
    ),
    **{profile.key: profile for profile in (primary_profile(prompt) for prompt in PRIMARY_PROMPT_PROFILES)},
    **{profile.key: profile for profile in (review_coverage_profile(prompt) for prompt in REVIEW_COVERAGE_PROMPT_PROFILES)},
    ("guideline_consensus", "recommendation_consensus_schema"): RouteExtractionProfile(
        prompt_profile="guideline_consensus",
        schema_profile="recommendation_consensus_schema",
        output_family="recommendation_consensus",
        output_schema_version="recommendation_consensus_v1",
        status=PROFILE_STATUS_RUNNABLE,
        prompt_path=ROOT / "docs" / "extraction_profiles" / "paper_type" / "guideline_consensus.md",
        schema_path=ROOT / "schema" / "recommendation_consensus.schema.json",
        default_max_output_tokens=16384,
        description="Extract graphable recommendations and consensus positions from guideline/consensus papers.",
    ),
    ("context_only_or_skip", "context_only_schema"): RouteExtractionProfile(
        prompt_profile="context_only_or_skip",
        schema_profile="context_only_schema",
        output_family="context_only",
        output_schema_version="",
        status=PROFILE_STATUS_TERMINAL_NO_MODEL,
        prompt_path=None,
        schema_path=None,
        default_max_output_tokens=0,
        description="Terminal audit route for context-only papers; no model extraction.",
    ),
    ("no_extraction", "no_extraction_schema"): RouteExtractionProfile(
        prompt_profile="no_extraction",
        schema_profile="no_extraction_schema",
        output_family="no_extraction",
        output_schema_version="",
        status=PROFILE_STATUS_TERMINAL_NO_MODEL,
        prompt_path=None,
        schema_path=None,
        default_max_output_tokens=0,
        description="Terminal route for model-screened exclusions; no extraction.",
    ),
}


def profile_key_for_task(task: dict) -> tuple[str, str]:
    contract = task.get("extraction_contract", {}) if isinstance(task.get("extraction_contract"), dict) else {}
    prompt_profile = str(contract.get("prompt_profile", "")).strip()
    schema_profile = str(contract.get("schema_profile", "")).strip()
    return (prompt_profile, schema_profile)


def profile_for_key(prompt_profile: str, schema_profile: str) -> RouteExtractionProfile:
    key = (prompt_profile.strip(), schema_profile.strip())
    if key not in ROUTE_EXTRACTION_PROFILES:
        supported = ", ".join(f"{prompt}/{schema}" for prompt, schema in sorted(ROUTE_EXTRACTION_PROFILES))
        raise ValueError(f"Unsupported route extraction profile `{key[0]}/{key[1]}`. Supported: {supported}")
    return ROUTE_EXTRACTION_PROFILES[key]


def profile_for_task(task: dict) -> RouteExtractionProfile:
    prompt_profile, schema_profile = profile_key_for_task(task)
    return profile_for_key(prompt_profile, schema_profile)


def task_has_registered_profile(task: dict) -> bool:
    return profile_key_for_task(task) in ROUTE_EXTRACTION_PROFILES


def task_has_model_profile(task: dict, *, include_scaffold: bool = False) -> bool:
    key = profile_key_for_task(task)
    if key not in ROUTE_EXTRACTION_PROFILES:
        return False
    profile = ROUTE_EXTRACTION_PROFILES[key]
    if profile.status == PROFILE_STATUS_RUNNABLE:
        return True
    if include_scaffold and profile.status == PROFILE_STATUS_SCAFFOLD:
        return True
    return False


def supported_profile_keys() -> list[dict]:
    return [
        {
            "prompt_profile": profile.prompt_profile,
            "schema_profile": profile.schema_profile,
            "output_family": profile.output_family,
            "output_schema_version": profile.output_schema_version,
            "status": profile.status,
            "prompt_path": str(profile.prompt_path) if profile.prompt_path else "",
            "schema_path": str(profile.schema_path) if profile.schema_path else "",
            "default_max_output_tokens": profile.default_max_output_tokens,
            "description": profile.description,
        }
        for profile in sorted(ROUTE_EXTRACTION_PROFILES.values(), key=lambda item: item.key)
    ]


def load_schema(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def schema_path_for_profile(profile: RouteExtractionProfile, domain_route: str = "") -> Path | None:
    if profile.prompt_profile == "secondary_meta_analysis":
        domain = domain_route.strip()
        path = META_ANALYSIS_SCHEMA_PATHS.get(domain)
        if path is not None and path.exists():
            return path
        raise ValueError(f"No meta-analysis extraction schema for domain `{domain or '<missing>'}`")
    if profile.prompt_profile in REVIEW_COVERAGE_PROMPT_PROFILES:
        domain = domain_route.strip()
        path = REVIEW_SCHEMA_PATHS.get(domain)
        if path is not None and path.exists():
            return path
        raise ValueError(f"No review extraction schema for domain `{domain or '<missing>'}`")
    return profile.schema_path


def load_schema_for_profile(profile: RouteExtractionProfile, domain_route: str = "") -> dict:
    path = schema_path_for_profile(profile, domain_route)
    if path is None:
        raise ValueError(f"Profile `{profile.prompt_profile}/{profile.schema_profile}` has no schema path")
    return load_schema(path)


def compact_schema(schema: dict) -> str:
    return json.dumps(schema, ensure_ascii=False, separators=(",", ":"))


def schema_in_prompt(schema_mode: str) -> bool:
    return schema_mode in {"prompt", "both"}


def schema_in_native_config(schema_mode: str) -> bool:
    return schema_mode in {"native", "both"}


def resolve_schema_refs(value: object, definitions: dict) -> object:
    if isinstance(value, list):
        return [resolve_schema_refs(item, definitions) for item in value]
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        ref = str(value.get("$ref", "")).strip()
        prefix = "#/definitions/"
        if not ref.startswith(prefix):
            raise ValueError(f"Unsupported schema reference `{ref}`")
        name = ref.removeprefix(prefix)
        if name not in definitions:
            raise ValueError(f"Unknown schema definition `{name}`")
        resolved = copy.deepcopy(definitions[name])
        for key, item in value.items():
            if key != "$ref":
                resolved[key] = item
        return resolve_schema_refs(resolved, definitions)
    return {key: resolve_schema_refs(item, definitions) for key, item in value.items()}


def schema_for_native(schema: dict) -> dict:
    """Inline local refs for Gemini native `response_json_schema` mode."""
    view = copy.deepcopy(schema)
    definitions = view.get("definitions", {})
    view = resolve_schema_refs(view, definitions)
    if isinstance(view, dict):
        view.pop("definitions", None)
        view.pop("$schema", None)
    return view


def schema_for_assigned_domain(schema: dict, domain_route: str) -> dict:
    """Constrain reusable schemas to one selected evidence domain."""
    view = copy.deepcopy(schema)
    domain = domain_route.strip()
    if not domain:
        return view
    definitions = view.get("definitions")
    if isinstance(definitions, dict) and "domain_route" in definitions:
        definitions["domain_route"] = {"type": "string", "const": domain}
    properties = view.get("properties")
    if isinstance(properties, dict) and "domain_route" in properties:
        properties["domain_route"] = {"type": "string", "const": domain}
    allowed_entity_types = ENTITY_TYPES_BY_DOMAIN.get(domain)
    if allowed_entity_types:
        constrain_entity_type_enums(view, allowed_entity_types)
    if domain in RESULT_DIRECTION_NOT_APPLICABLE_DOMAINS:
        constrain_result_direction_to_not_applicable(view)
    return view


def constrain_entity_type_enums(value: object, allowed_entity_types: set[str]) -> None:
    if isinstance(value, list):
        for item in value:
            constrain_entity_type_enums(item, allowed_entity_types)
        return
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        if key == "entity_type" and isinstance(item, dict) and isinstance(item.get("enum"), list):
            item["enum"] = [candidate for candidate in item["enum"] if candidate in allowed_entity_types]
        else:
            constrain_entity_type_enums(item, allowed_entity_types)


def constrain_result_direction_to_not_applicable(value: object) -> None:
    if isinstance(value, list):
        for item in value:
            constrain_result_direction_to_not_applicable(item)
        return
    if not isinstance(value, dict):
        return
    definitions = value.get("definitions")
    if isinstance(definitions, dict) and "result_direction" in definitions:
        definitions["result_direction"] = {"type": "string", "const": "not_applicable"}
    for key, item in value.items():
        if key == "result_direction" and isinstance(item, dict):
            if "enum" in item or "const" in item:
                item.clear()
                item.update({"type": "string", "const": "not_applicable"})
        else:
            constrain_result_direction_to_not_applicable(item)


def domain_prompt_path(domain_route: str) -> Path | None:
    return DOMAIN_PROMPT_PATHS.get(domain_route.strip())


def should_append_domain_addendum(profile: RouteExtractionProfile) -> bool:
    return (
        profile.prompt_profile in PRIMARY_PROMPT_PROFILES
        or profile.prompt_profile == "secondary_meta_analysis"
        or profile.prompt_profile in REVIEW_COVERAGE_PROMPT_PROFILES
        or profile.prompt_profile == "guideline_consensus"
    )


def prompt_path_for_depth(profile: RouteExtractionProfile, text_depth: str) -> Path:
    assert profile.prompt_path is not None
    depth = normalize_text_depth(text_depth) if text_depth.strip() else TEXT_DEPTH_ARTICLE
    if profile.prompt_profile in PRIMARY_PROMPT_PROFILES:
        return PAPER_TYPE_PROMPT_PATHS[("primary", depth)]
    if profile.prompt_profile == "secondary_meta_analysis":
        return PAPER_TYPE_PROMPT_PATHS[("meta_analysis", depth)]
    if profile.prompt_profile in REVIEW_COVERAGE_PROMPT_PROFILES:
        return PAPER_TYPE_PROMPT_PATHS[("review", depth)]
    return profile.prompt_path


def insert_context_after_opening(prompt_text: str, context_parts: list[str]) -> str:
    if not context_parts:
        return prompt_text
    blocks = prompt_text.split("\n\n", 2)
    if len(blocks) == 3 and blocks[0].startswith("# "):
        return "\n\n".join([blocks[0], blocks[1], *context_parts, blocks[2]])
    return "\n\n".join([prompt_text, *context_parts])


def build_system_instruction(
    profile: RouteExtractionProfile,
    schema: dict,
    schema_mode: str,
    *,
    domain_route: str = "",
    text_depth: str = "",
) -> str:
    if schema_mode not in SCHEMA_MODES:
        raise ValueError(f"Unsupported schema mode `{schema_mode}`")
    if not profile.has_model_contract and profile.status != PROFILE_STATUS_LEGACY_READ_ONLY:
        raise ValueError(f"Profile `{profile.prompt_profile}/{profile.schema_profile}` is not model-runnable")
    assert profile.prompt_path is not None
    depth_key = TEXT_DEPTH_ARTICLE
    if text_depth.strip():
        depth_key = normalize_text_depth(text_depth)
    prompt_text = prompt_path_for_depth(profile, depth_key).read_text(encoding="utf-8").strip()
    context_parts = []
    route_prompt_path = domain_prompt_path(domain_route)
    if should_append_domain_addendum(profile) and route_prompt_path is not None and route_prompt_path.exists():
        context_parts.append("## Scope\n\n" + route_prompt_path.read_text(encoding="utf-8").strip())
    parts = [insert_context_after_opening(prompt_text, context_parts)]
    if schema_in_prompt(schema_mode):
        schema = schema_for_assigned_domain(schema, domain_route)
        parts.append(
            "## Output\n\n"
            "Return exactly one JSON object that validates against the provided "
            "JSON Schema. Return JSON only. Do not include Markdown, prose, "
            "comments, or code fences.\n\n"
            "Use the exact property names and enum values from this JSON "
            "Schema.\n\n" + compact_schema(schema)
        )
    else:
        parts.append(
            "## Output\n\n"
            "Return exactly one JSON object that validates against the provided "
            "JSON Schema. Return JSON only. Do not include Markdown, prose, "
            "comments, or code fences.\n\n"
            "The API response_json_schema defines the required output shape. "
            "Use the exact property names and enum values."
        )
    return "\n\n".join(parts)
