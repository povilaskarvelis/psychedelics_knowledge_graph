#!/usr/bin/env python3
"""Convert paper-centered review bundles into the canonical KG evidence-row format.

Each extracted relationship retains its complete statement, anchors, evidence
locators, and paper frame. A principal object and explicit domain-compatible
named objects provide graph views of that same relationship; they are not new
independent observations. Context and comparator anchors remain in provenance.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import re
import sys

import pandas as pd

try:
    from pipeline.extract.io_utils import normalize, read_jsonl, write_json
    from pipeline.kg.project_review_relationship_bundles import label_key, registry_index
    from pipeline.kg.review_statement_attribution import statement_contrasts_drugs
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.io_utils import normalize, read_jsonl, write_json
    from pipeline.kg.project_review_relationship_bundles import label_key, registry_index
    from pipeline.kg.review_statement_attribution import statement_contrasts_drugs


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUNDLES = (
    ROOT
    / "data"
    / "processed"
    / "extraction"
    / "review_relationship_runs"
    / "review_relationships_v2_main_20260712"
    / "paper_relationship_bundles.jsonl"
)
DEFAULT_REGISTRY = ROOT / "data" / "curated" / "entity_registry.json"
DEFAULT_CANDIDATES = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"

CANONICAL_METADATA_FIELDS = (
    "openalex_id",
    "pmid",
    "pmcid",
    "authors",
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
    "trial_registry_ids",
    "open_access_is_oa",
    "open_access_status",
    "open_access_url",
)

from pipeline.extract.review_source_types import REVIEW_PATH_TYPES

REVIEW_TYPES = REVIEW_PATH_TYPES
READY_REVIEW_ROUTE_STATUSES = {
    "ready_for_article_text_extraction",
    "ready_for_abstract_extraction",
}
ACTIVE_CANDIDATE_FIELDS = {
    "doi",
    "prescreen_decisions",
    "retained_for_extraction_candidate",
    "extraction_route_status",
}
GRAPH_EXCLUDED_COMPOUND_SCOPES = {
    "out_of_scope",
    "out_of_scope_comparator",
    "out_of_scope_nonpsychedelic",
    "reference_control",
}
PSYCHEDELIC_SCOPE_CLASS_RE = re.compile(
    r"\b(?:psychedelic\w*|hallucinogen\w*|psychoplastogen\w*|entheogen\w*|microdos\w*|"
    r"entactogen\w*|empathogen\w*|dissociative\w*|tryptamine\w*|phenethylamine\w*|"
    r"ergoline\w*|nbome\w*|nboh\w*|iboga\w*|set and setting|chemsex|sexuali[sz]ed drug use|"
    r"substance[- ]assisted psychotherap\w*|serotonerg\w*\s+psychoaktiv\w*|"
    r"(?:nmda\W*|n[- ]methyl[- ]d[- ]aspartate\s+)(?:receptor\W*)?antagonist\w*)\b",
    re.IGNORECASE,
)
SUBJECT_ROLES = {"compound", "compound_class", "intervention", "co_intervention"}
OBJECT_ROLE_ORDER = {
    "safety_event": 10,
    "condition": 20,
    "outcome": 30,
    "target": 40,
    "pathway_or_process": 50,
    "brain_system": 60,
    "cognitive_or_behavioral_construct": 70,
    "subjective_construct": 80,
    "exposure_or_pk_parameter": 90,
    "intervention_context": 100,
    "public_health_topic": 110,
    "research_topic": 120,
    "population": 130,
    "comparator": 140,
    "other": 150,
    "compound": 160,
    "compound_class": 170,
    "intervention": 180,
    "co_intervention": 190,
}
ROLE_GRAPH_MAPPING = {
    "condition": ("clinical_outcome", "condition_indication", "condition_or_indication"),
    "outcome": ("clinical_outcome", "symptom_problem", "outcome_measure"),
    "safety_event": ("safety_tolerability", "safety_adverse_event", "safety_event_or_measure"),
    "target": ("molecular_target", "target", "target"),
    "pathway_or_process": ("molecular_pathway_readout", "pathway_process", "pathway_or_process"),
    "brain_system": ("brain_system", "brain_network", "brain_network"),
    "cognitive_or_behavioral_construct": (
        "cognitive_behavioral",
        "cognitive_behavioral_construct",
        "graph_construct_label",
    ),
    "subjective_construct": (
        "subjective_experience",
        "subjective_experience_construct",
        "subjective_construct",
    ),
    "exposure_or_pk_parameter": (
        "pharmacokinetics_exposure",
        "pharmacokinetic_parameter",
        "pk_or_exposure_parameter",
    ),
    "intervention_context": ("intervention_context", "intervention_component", "context_component"),
    "public_health_topic": ("real_world_public_health", "public_health_measure", "public_health_measure"),
    "research_topic": ("general_topic_coverage", "public_health_measure", "public_health_measure"),
    "population": ("clinical_outcome", "condition_indication", "condition_or_indication"),
    "comparator": ("intervention_context", "intervention_component", "context_component"),
    "compound": ("molecular_target", "compound", "graph_entity_label"),
    "compound_class": ("general_topic_coverage", "compound", "graph_entity_label"),
    "intervention": ("intervention_context", "intervention_component", "context_component"),
    "co_intervention": ("intervention_context", "intervention_component", "context_component"),
    "other": ("general_topic_coverage", "public_health_measure", "public_health_measure"),
}

# The generic ``outcome`` role does not imply a clinical symptom. When the
# extractor names the endpoint and supplies one unambiguous result domain,
# preserve that declared domain rather than routing every human outcome to
# Conditions. Mixed-domain or untyped broad outcomes retain the existing path.
NAMED_OUTCOME_DOMAIN_MAPPING = {
    "cognitive_behavioral": ("cognitive_behavioral", "cognitive_behavioral_construct", "graph_construct_label"),
    "subjective_experience": ("subjective_experience", "subjective_experience_construct", "subjective_construct"),
    "safety_tolerability": ("safety_tolerability", "safety_adverse_event", "safety_event_or_measure"),
    "molecular_pathway_readout": ("molecular_pathway_readout", "biomarker_readout", "readout"),
    "brain_system": ("brain_system", "brain_measure", "readout"),
    "real_world_public_health": ("real_world_public_health", "public_health_measure", "public_health_measure"),
}

# Secondary views require an explicit named object and a matching model domain.
# Neither a subject/comparator nor a contextual mention becomes a new endpoint.
PROJECTABLE_OBJECT_ROLES = {
    "condition", "outcome", "safety_event", "target", "pathway_or_process",
    "brain_system", "cognitive_or_behavioral_construct", "subjective_construct",
    "exposure_or_pk_parameter", "intervention_context", "public_health_topic",
}

REVIEW_COVERAGE_FOCUS_LABELS = {
    "paper_defining": "Main focus",
    "major_supporting": "Major supporting topic",
    "secondary_context": "Context only",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalized_doi(value: object) -> str:
    return normalize(value).lower()


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return normalize(value).lower() in {"1", "true", "yes", "y"}


def active_review_candidate_dois(candidate_rows: list[dict]) -> set[str]:
    """Return candidates that remain eligible for review evidence conversion.

    This gate deliberately uses the current canonical corpus rather than the
    historical task files associated with a completed model run. Missing
    eligibility fields are an error so an incomplete table cannot silently
    admit stale review outputs.
    """

    available_fields = {
        key
        for row in candidate_rows
        if isinstance(row, dict)
        for key in row
    }
    missing_fields = ACTIVE_CANDIDATE_FIELDS - available_fields
    if missing_fields:
        raise ValueError(
            "Candidate table is missing fields required for active review gating: "
            + ", ".join(sorted(missing_fields))
        )

    return {
        doi
        for row in candidate_rows
        if (doi := normalized_doi(row.get("doi", "")))
        and normalize(row.get("prescreen_decisions", "")).lower() == "retain"
        and truthy(row.get("retained_for_extraction_candidate", False))
        and normalize(row.get("extraction_route_status", ""))
        in READY_REVIEW_ROUTE_STATUSES
    }


def json_array(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON array: {path}")
    return [row for row in payload if isinstance(row, dict)]


def write_json_array(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def paper_type_for(task: dict) -> str:
    metadata = task.get("paper_metadata", {}) if isinstance(task.get("paper_metadata"), dict) else {}
    value = normalize(metadata.get("review_type", ""))
    return value if value in REVIEW_TYPES else "review"


def in_scope_compound_keys(registry_payload: dict) -> set[str]:
    keys: set[str] = set()
    for item in registry_payload.get("compounds", []):
        if not isinstance(item, dict):
            continue
        if normalize(item.get("graph_scope", "")).casefold() in GRAPH_EXCLUDED_COMPOUND_SCOPES:
            continue
        for value in [item.get("label", ""), *item.get("aliases", [])]:
            key = label_key(value)
            if key:
                keys.add(key)
    return keys


def review_scope_for_relationship(
    bundle_row: dict,
    subject_label: str,
    scoped_compound_keys: set[str],
) -> tuple[str, str]:
    """Admit globally scoped reviews or individually in-scope relationships."""

    for source, text in (
        ("title", normalize(bundle_row.get("study_title", ""))),
        ("relationship_subject", normalize(subject_label)),
    ):
        if PSYCHEDELIC_SCOPE_CLASS_RE.search(text):
            return "in_scope", f"{source}_has_in_scope_class_or_context"
        text_key = label_key(text)
        padded = f" {text_key} "
        if any(key == text_key or f" {key} " in padded for key in scoped_compound_keys):
            return "in_scope", f"{source}_has_in_scope_compound"
    return "psychedelics_peripheral_or_absent", "no_in_scope_subject_in_review_title_or_relationship"


def registered_subject_identity(label: object, registry: dict[tuple[str, str], str]) -> str:
    """Collapse an exact drug alias with ordinary administration descriptors.

    This is identity matching, not a substring search. Words denoting a different
    molecule (metabolite, analogue, derivative, stereoisomer) and co-interventions
    remain in the residual string and prevent a match. Raw anchors remain intact.
    """
    raw = normalize(label)
    exact = registry.get(("compounds", label_key(raw)), "")
    if exact:
        return exact
    parts = re.fullmatch(r"(.+?)\s*\(([^()]*)\)", raw)
    if parts:
        outer = registry.get(("compounds", label_key(parts.group(1))), "")
        inner = registry.get(("compounds", label_key(parts.group(2))), "")
        if outer and inner == outer:
            return outer
    # Self-administration is an administration protocol, not a second drug.
    # Match the complete descriptor so cessation, withdrawal, comparative
    # paradigms and additional interventions cannot be erased as stop words.
    self_administration = re.fullmatch(r"(.+?)\s+self[- ]administration(?:\s+paradigms?)?", raw, re.I)
    if self_administration:
        identity = registry.get(("compounds", label_key(self_administration.group(1))), "")
        if identity:
            return identity
    stripped = re.sub(
        r"\b(?:oral|intravenous|intranasal|nasal|sprays?|intramuscular|sublingual|subcutaneous|"
        r"iv|infusions?|administration|treatments?|therapy|assisted|psychotherapy|"
        r"use|sessions?|dosing|microdosing)\b", " ", raw, flags=re.I,
    )
    return registry.get(("compounds", label_key(stripped)), "")


def typed_single_drug_context_subject(relationship: dict, scoped: list[tuple[int, dict]], registry: dict) -> list[tuple[int, dict]]:
    """Keep one explicit contextual actor without pretending it is another drug.

    A drug plus its social setting or psychotherapy regimen is not a pooled
    chemical finding. Keep the literal contextual actor, rather than rewriting
    its effect as a drug-alone effect. This only applies to context-form rows
    with one registered chemical identity and one explicitly typed context.
    Distinct drugs, classes, analogues and comparisons retain attribution holds.
    """
    if normalize(relationship.get("graph_form")) != "context":
        return []
    chemical = [(i, a) for i, a in scoped if a.get("role") in {"compound", "compound_class"}]
    contextual = [(i, a) for i, a in scoped if a.get("role") in {"intervention", "co_intervention"}
                  and a.get("anchor_type") in {"context", "combination_or_regimen"}]
    if not chemical or len(chemical) + len(contextual) != len(scoped):
        return []
    identities = {registered_subject_identity(a.get("label"), registry) for _, a in chemical}
    distinct_contexts = {label_key(a.get("label")): (i, a) for i, a in contextual}
    if len(identities) != 1 or "" in identities or len(distinct_contexts) != 1:
        return []
    identity = next(iter(identities))
    # An unregistered or out-of-scope chemical actor is still a distinct drug;
    # filtering scope must not hide an adjunct such as an ordinary antidepressant.
    if any(registered_subject_identity(a.get("label"), registry) != identity
           for a in relationship.get("anchors", []) if isinstance(a, dict)
           and a.get("role") in {"compound", "compound_class"}):
        return []
    context = next(iter(distinct_contexts.values()))
    text = label_key(context[1].get("label"))
    aliases = sorted((key for (category, key), name in registry.items()
                      if category == "compounds" and name == identity), key=len, reverse=True)
    residual = text
    for alias in aliases:
        residual = re.sub(rf"\b{re.escape(alias)}\b", " ", residual)
    if residual == text:
        return []
    if re.search(r"\b(?:metabolit\w*|analog\w*|derivativ\w*|enantiomer\w*|stereoisomer\w*|"
                 r"medicines|drugs|agents|compounds|versus|vs|compared|alone|cessation|abstinence|withdrawal|discontinu\w*)\b", residual):
        return []
    if PSYCHEDELIC_SCOPE_CLASS_RE.search(residual):
        return []
    if any(re.search(rf"\b{re.escape(key)}\b", residual)
           for (category, key), name in registry.items()
           if category == "compounds" and name != identity and len(key) >= 3):
        return []
    return [context]


def inherited_drug_target_background(subject: dict, relationship: dict, registry: dict) -> bool:
    """Do not assign background receptor/enzyme biology to a paper's focal drug.

    Limit this guard to an exact inherited drug plus an explicit target anchor.
    General review topics/classes keep their existing coverage semantics. A
    direct drug action, negated action, drug-effect mechanism, or substrate
    relationship in the sentence can corroborate a missing subject anchor.
    A drug name inside an enzyme description or comparator is not corroboration.
    """
    if subject["source_field"] != "paper_frame.primary_subjects":
        return False
    identity = registered_subject_identity(subject["label"], registry)
    if not identity or not any(a.get("role") == "target" and a.get("anchor_type") == "named_entity"
                               for a in relationship.get("anchors", []) if isinstance(a, dict)):
        return False
    statement = normalize(relationship.get("relationship_statement", ""))
    aliases = [key for (category, key), name in registry.items() if category == "compounds" and name == identity]
    # label_key removes possessives; retain them for the drug-effect pattern.
    for alias in aliases:
        drug = r"\b" + r"[\W_]*".join(re.escape(word) for word in alias.split()) + r"\b"
        action = (r"\s+(?:(?:may|might|can|could|does|did|do|not|never|itself|directly|significantly)\s+){0,4}"
                  r"(?:bind\w*|activat\w*|inhibit\w*|antagoni[sz]\w*|agonis\w*|modulat\w*|"
                  r"increas\w*|decreas\w*|reduc\w*|enhanc\w*|suppress\w*|induc\w*|evok\w*|"
                  r"produc\w*|protect\w*|block\w*|improv\w*)\b")
        if re.search(drug + action, statement, re.I):
            return False
        if re.search(drug + r"(?:[- ](?:induced|mediated|evoked|associated)\b|['’]s\s+(?:[\w-]+\s+){0,2}(?:effects?|actions?|binding|affinity)\b)", statement, re.I):
            return False
        if re.search(r"\b(?:effects?|response|binding|affinity|biosynthesis|synthesis|metabolism|clearance)\s+(?:of|to|by)\s+" + drug, statement, re.I):
            return False
    return True


def explicit_class_example_subject(relationship: dict, scoped: list[tuple[int, dict]], registry: dict) -> list[tuple[int, dict]]:
    """Retain a source-defined class when other drug anchors are its examples.

    Only explicit 'class, including/such as drugs' text qualifies. A contrast of
    two actors, parent/metabolite statement, or class plus an unassigned drug
    continues to require attribution instead of silently narrowing the subject.
    """
    if normalize(relationship.get("graph_form")) != "class":
        return []
    classes = [(i, a) for i, a in scoped if a.get("role") == "compound_class" or a.get("anchor_type") == "compound_class"]
    if len(classes) != 1:
        return []
    class_index, class_anchor = classes[0]
    other = [a for i, a in scoped if i != class_index]
    identities = [registered_subject_identity(a.get("label"), registry) for a in other]
    if not other or not all(identities):
        return []
    statement = label_key(relationship.get("relationship_statement", ""))
    class_key = label_key(class_anchor.get("label", ""))
    match = re.search(rf"\b{re.escape(class_key)}\s+(?:including|such as)\s+", statement)
    if not match:
        return []
    examples = re.split(r"\b(?:but|whereas|while|unlike|versus|compared|however|contrast)\b", statement[match.end():], maxsplit=1)[0][:220]
    for identity in identities:
        keys = [key for (category, key), name in registry.items() if category == "compounds" and name == identity]
        if not any(re.search(rf"\b{re.escape(key)}\b", examples) for key in keys):
            return []
    return classes


def each_named_drug_attributable(
    relationship: dict,
    compound_registry: dict[tuple[str, str], str],
    scoped_compound_keys: set[str],
) -> bool:
    """Whether a statement naming several in-scope drugs states the same relationship for each.

    Every in-scope subject anchor must resolve to a registered drug, each drug
    must be named in the statement, and the statement must not contrast the
    drugs ("MDMA for PTSD and psilocybin for depression") or relate one to
    another ("psilocybin is converted to psilocin"). The normalizer then links
    each drug to the object, keeping the complete statement.
    """
    statement_key = label_key(relationship.get("relationship_statement", ""))
    identities: dict[str, list[str]] = {}
    for anchor in relationship.get("anchors", []):
        if not isinstance(anchor, dict) or normalize(anchor.get("role", "")) not in SUBJECT_ROLES:
            continue
        label = normalize(anchor.get("label", ""))
        if review_scope_for_relationship({}, label, scoped_compound_keys)[0] != "in_scope":
            continue
        identity = registered_subject_identity(label, compound_registry)
        if not identity:
            return False
        identities.setdefault(identity, [
            key for (category, key), name in compound_registry.items()
            if category == "compounds" and name == identity and (" " in key or len(key) > 2)
        ])
    if len(identities) < 2:
        return False
    if not all(any(re.search(rf"\b{re.escape(key)}\b", statement_key) for key in keys)
               for keys in identities.values()):
        return False
    return not statement_contrasts_drugs(statement_key, list(identities.values()),
                                         normalize(relationship.get("relationship_statement", "")))


def subject_for_relationship(
    relationship: dict,
    frame: dict,
    compound_registry: dict[tuple[str, str], str],
    scoped_compound_keys: set[str] | None = None,
) -> tuple[dict, set[int]]:
    anchors = [anchor for anchor in relationship.get("anchors", []) if isinstance(anchor, dict)]
    candidates = [(index, anchor) for index, anchor in enumerate(anchors) if normalize(anchor.get("role", "")) in SUBJECT_ROLES]
    form = normalize(relationship.get("graph_form", ""))
    combine = form in {"combination", "interaction"} and len(candidates) > 1
    selected = candidates if combine else candidates[:1]
    multiple_scoped_subjects = False
    typed_context_subject = False
    if not combine and scoped_compound_keys is not None:
        scoped = [(index, anchor) for index, anchor in candidates if
                  review_scope_for_relationship({}, normalize(anchor.get("label", "")), scoped_compound_keys)[0] == "in_scope"]
        # Repeated aliases identify one subject, whereas two eligible compounds
        # do not become a drug-specific finding just because one appeared first.
        distinct_scoped = {}
        for index, anchor in scoped:
            raw_key = label_key(anchor.get("label", ""))
            canonical = registered_subject_identity(anchor.get("label", ""), compound_registry)
            identity = label_key(canonical) if canonical else raw_key
            distinct_scoped.setdefault(identity, (index, anchor))
        if len(distinct_scoped) == 1:
            # Comparator/background anchors are not SUBJECT_ROLES. A unique
            # eligible subject must not disappear because another drug was
            # listed first. The full relationship remains intact in provenance.
            selected = list(distinct_scoped.values())
        elif len(distinct_scoped) > 1 and (class_subject := explicit_class_example_subject(relationship, scoped, compound_registry)):
            selected = class_subject
        elif len(distinct_scoped) > 1 and (context_subject := typed_single_drug_context_subject(relationship, scoped, compound_registry)):
            selected = context_subject
            typed_context_subject = True
        elif len(distinct_scoped) > 1:
            # Do not pick an arbitrary drug from a pooled relationship merely
            # to pass scope. Preserve all explicit scoped subjects as detail.
            selected = sorted(distinct_scoped.values(), key=lambda pair: label_key(pair[1].get("label", "")))
            multiple_scoped_subjects = True

    if not selected:
        primary = [normalize(value) for value in frame.get("primary_subjects", []) if normalize(value)]
        label = primary[0] if primary else "Psychedelic research"
        return {
            "label": label,
            "kind": "paper_topic",
            "atomic_compound_candidate": "",
            "source_field": "paper_frame.primary_subjects",
        }, set()

    labels = [normalize(anchor.get("label", "")) for _, anchor in selected]
    selected_indexes = {index for index, _ in selected}
    if multiple_scoped_subjects:
        return {
            "label": " / ".join(labels), "kind": "compound_class",
            "atomic_compound_candidate": "", "source_field": "anchors_scoped_multiple",
        }, {index for index, _anchor in candidates}
    if combine:
        return {
            "label": " + ".join(labels),
            "kind": "compound_combination" if form == "combination" else "treatment_regimen",
            "atomic_compound_candidate": next(
                (compound_registry.get(("compounds", label_key(label)), "") for label in labels if compound_registry.get(("compounds", label_key(label)), "")),
                "",
            ),
            "source_field": "anchors",
        }, selected_indexes

    index, anchor = selected[0]
    label = labels[0]
    role = normalize(anchor.get("role", ""))
    anchor_type = normalize(anchor.get("anchor_type", ""))
    canonical = registered_subject_identity(label, compound_registry)
    if typed_context_subject:
        kind = "treatment_regimen" if anchor_type == "combination_or_regimen" else "exposure_context"
        canonical = ""
    elif canonical:
        kind = "atomic_compound"
        label = canonical
    elif role == "compound_class" or anchor_type == "compound_class" or form == "class":
        kind = "compound_class"
    elif role in {"intervention", "co_intervention"}:
        kind = "treatment_regimen" if re.search(r"\b(therap|treatment|regimen|session|psychotherap)\w*\b", label, re.I) else "exposure_context"
    else:
        kind = "atomic_compound"
    return {
        "label": label,
        "kind": kind,
        "atomic_compound_candidate": canonical,
        "source_field": "anchors_typed_context" if typed_context_subject else "anchors",
    }, {candidate_index for candidate_index, _anchor in candidates}


def object_for_relationship(relationship: dict, subject_indexes: set[int]) -> dict:
    anchors = [anchor for anchor in relationship.get("anchors", []) if isinstance(anchor, dict)]
    choices = [
        (OBJECT_ROLE_ORDER.get(normalize(anchor.get("role", "")), 999), index, anchor)
        for index, anchor in enumerate(anchors)
        if index not in subject_indexes and normalize(anchor.get("label", ""))
    ]
    if not choices:
        return {"role": "other", "label": normalize(relationship.get("relation_phrase", "")) or "Review relationship"}
    # Generic outcome/context anchors used to win over an explicitly named
    # receptor or brain region solely because of the fixed role ordering. Honor
    # model-typed domains before using that ordering, without inferring a direct
    # target relationship from a pathway-only statement (for example AMPAR).
    named_choices = [choice for choice in choices if named_object_domain_supported(relationship, choice[2])]
    return min(named_choices or choices, key=lambda item: (item[0], item[1]))[2]


def named_object_domain_supported(relationship: dict, anchor: dict) -> bool:
    role = normalize(anchor.get("role", ""))
    if normalize(anchor.get("anchor_type", "")) != "named_entity" or role not in PROJECTABLE_OBJECT_ROLES:
        return False
    domains = {normalize(value) for value in relationship.get("domain_labels", [])}
    domain = object_graph_mapping(relationship, anchor)[0]
    # A generic outcome may be a molecular readout, not behavior. Do not use the
    # preclinical fallback to create an extra cognitive view of, for example,
    # BDNF release. Explicit cognitive anchors carry their own role.
    return domain in domains


def object_graph_mapping(relationship: dict, anchor: dict) -> tuple[str, str, str]:
    role = normalize(anchor.get("role", "")) or "other"
    domains = {normalize(value) for value in relationship.get("domain_labels", []) if normalize(value)}
    if role == "outcome" and normalize(anchor.get("anchor_type", "")) == "named_entity" and len(domains) == 1:
        explicit = next(iter(domains))
        if explicit in NAMED_OUTCOME_DOMAIN_MAPPING:
            return NAMED_OUTCOME_DOMAIN_MAPPING[explicit]
    if role == "outcome" and normalize(anchor.get("anchor_type", "")) == "paper_topic" and domains and "clinical_outcome" not in domains:
        # A historical/theoretical topic mentioning pain or depression is not
        # a clinical symptom result. Keep the exact proposition in paper detail
        # when its declared domains do not authorize a clinical projection.
        # The separately scoped preclinical behavioral rule still applies below.
        return "general_topic_coverage", "reported_measurement", "graph_entity_label"
    return ROLE_GRAPH_MAPPING.get(role, ROLE_GRAPH_MAPPING["other"])


def projection_object_key(anchor: dict, registry: dict) -> tuple[str, str]:
    role = normalize(anchor.get("role", ""))
    raw = label_key(anchor.get("label", ""))
    category = {"target": "targets", "condition": "disorders"}.get(role, "")
    canonical = registry.get((category, raw), "") if category else ""
    return role, label_key(canonical) if canonical else raw


def evidence_locations(relationship: dict) -> tuple[str, str, str]:
    locators = [item for item in relationship.get("evidence_locators", []) if isinstance(item, dict)]
    locations = " | ".join(dict.fromkeys(normalize(item.get("location", "")) for item in locators if normalize(item.get("location", ""))))
    locator_text = " | ".join(dict.fromkeys(normalize(item.get("locator", "")) for item in locators if normalize(item.get("locator", ""))))
    support = " | ".join(dict.fromkeys(normalize(item.get("supporting_text", "")) for item in locators if normalize(item.get("supporting_text", ""))))
    return locations, locator_text, support


def relationship_row(
    bundle_row: dict,
    task: dict,
    relationship: dict,
    relationship_index: int,
    compound_registry: dict,
    scoped_compound_keys: set[str],
    object_anchor_override: dict | None = None,
) -> dict:
    result = bundle_row.get("result", {}) if isinstance(bundle_row.get("result"), dict) else {}
    frame = result.get("paper_frame", {}) if isinstance(result.get("paper_frame"), dict) else {}
    metadata = task.get("paper_metadata", {}) if isinstance(task.get("paper_metadata"), dict) else {}
    subject, subject_indexes = subject_for_relationship(relationship, frame, compound_registry, scoped_compound_keys)
    scope_status, scope_reason = review_scope_for_relationship(
        bundle_row,
        subject["label"],
        scoped_compound_keys,
    )
    object_anchor = object_anchor_override or object_for_relationship(relationship, subject_indexes)
    object_role = normalize(object_anchor.get("role", "")) or "other"
    object_label = normalize(object_anchor.get("label", ""))
    domain, entity_kind, role_field = object_graph_mapping(relationship, object_anchor)
    fallback_object_mapping = object_role == "other" or object_role not in ROLE_GRAPH_MAPPING
    model_domains = [normalize(value) for value in relationship.get("domain_labels", []) if normalize(value)]
    # An explicitly behavioral animal outcome is not a patient symptom simply
    # because the schema calls it an outcome. Keep other outcomes on the existing
    # role/safety normalization path: a blanket preclinical fallback would also
    # suppress genuine hyperthermia, urinary toxicity and other safety findings.
    preclinical_outcome = object_role == "outcome" and normalize(relationship.get("evidence_stratum", "")) == "preclinical"
    if preclinical_outcome and "cognitive_behavioral" in model_domains:
        domain, entity_kind, role_field = "cognitive_behavioral", "cognitive_behavioral_construct", "graph_construct_label"
    location, locator, supporting_quote = evidence_locations(relationship)
    prominence = normalize(relationship.get("paper_prominence", ""))
    requested_eligibility = normalize(relationship.get("graph_eligibility", ""))
    admission = (
        "main_graph"
        if scope_status == "in_scope"
        and requested_eligibility == "main_graph"
        and prominence in {"paper_defining", "major_supporting"}
        and not fallback_object_mapping
        else "paper_detail"
    )
    each_drug_attributable = (
        subject["source_field"] == "anchors_scoped_multiple"
        and domain not in {"general_topic_coverage", "intervention_context"}
        and each_named_drug_attributable(relationship, compound_registry, scoped_compound_keys)
    )
    ambiguous_subject = subject["source_field"] == "anchors_scoped_multiple" and not each_drug_attributable
    paper_frame_only_subject = inherited_drug_target_background(subject, relationship, compound_registry)
    generic_measurement = entity_kind == "reported_measurement"
    comparison_or_population = object_role in {"comparator", "population"}
    if ambiguous_subject or paper_frame_only_subject or generic_measurement or comparison_or_population:
        admission = "paper_detail"
    statement = normalize(relationship.get("relationship_statement", ""))
    limitations = [normalize(value) for value in relationship.get("limitations", []) if normalize(value)]
    anchors = [anchor for anchor in relationship.get("anchors", []) if isinstance(anchor, dict)]
    row = {
        "study_doi": normalized_doi(bundle_row.get("study_doi", "")),
        "study_title": normalize(bundle_row.get("study_title", "")) or normalize(metadata.get("study_title", "")),
        "study_year": normalize(metadata.get("study_year", "")),
        "study_journal": normalize(metadata.get("study_journal", "")),
        "publication_type": normalize(metadata.get("publication_type", "")),
        "abstract": normalize(metadata.get("abstract", "")),
        "source_access_level": normalize(bundle_row.get("text_depth", "")),
        "access_level": normalize(bundle_row.get("text_depth", "")),
        "paper_type": paper_type_for(task),
        "source_type": paper_type_for(task),
        "source_family": "secondary_literature",
        "paper_assessment_route": "secondary_literature",
        "source_item_type": "review_relationship",
        "source_item_index": relationship_index,
        "source_item_id": normalize(relationship.get("item_id", "")),
        "relationship_source_group_key": f"{normalized_doi(bundle_row.get('study_doi', ''))}#{normalize(relationship.get('item_id', '')) or relationship_index}",
        "review_extraction_method": "paper_centered_one_pass_v2",
        "evidence_type": "secondary_literature",
        "domain": domain,
        "domain_route": domain,
        "dataset": domain,
        "claim_type": normalize(relationship.get("relationship_kind", "")),
        "coverage_type": normalize(relationship.get("relationship_kind", "")),
        "coverage_focus": prominence,
        "coverage_focus_normalized": REVIEW_COVERAGE_FOCUS_LABELS.get(prominence, ""),
        "finding_summary": statement,
        "support": statement,
        "notes": "; ".join(limitations),
        "result_direction": normalize(relationship.get("direction_or_tone", "")),
        "evidence_level": normalize(relationship.get("evidence_stratum", "")),
        "evidence_location": location,
        "evidence_locator": locator,
        "supporting_quote": supporting_quote,
        "graph_subject_label": subject["label"],
        "graph_subject_kind": subject["kind"],
        "graph_subject_source_field": subject["source_field"],
        "atomic_compound_candidate": subject["atomic_compound_candidate"],
        "compound": subject["label"],
        "graph_entity_label": object_label,
        "kg_entity_kind_override": entity_kind,
        "entity_role": object_role,
        "review_scope_status": scope_status,
        "review_scope_reason": scope_reason,
        "graph_admission_status": admission,
        "graph_admission_reason": (
            "review_multiple_drug_subjects_requires_attribution"
            if ambiguous_subject
            else "review_target_background_without_drug_actor"
            if paper_frame_only_subject
            else "review_comparator_or_population_is_context"
            if comparison_or_population
            else "nonclinical_review_topic_requires_domain_mapping"
            if generic_measurement and object_role == "outcome" and normalize(object_anchor.get("anchor_type", "")) == "paper_topic"
            else "generic_measurement_requires_domain_mapping"
            if generic_measurement
            else
            "review_relationship_prominence"
            if admission == "main_graph"
            else "review_relationship_untyped_object_detail_only"
            if fallback_object_mapping
            else "review_paper_scope_not_graphable"
            if scope_status != "in_scope"
            else "review_relationship_paper_detail"
        ),
        "review_subject_attribution": "each_named_drug" if each_drug_attributable else "",
        "relationship_graph_form": normalize(relationship.get("graph_form", "")),
        "relationship_anchors_json": json.dumps(anchors, ensure_ascii=False),
        "relationship_domain_labels_json": json.dumps(model_domains, ensure_ascii=False),
        "covers_major_aspect_ids_json": json.dumps(relationship.get("covers_major_aspect_ids", []), ensure_ascii=False),
        "centrality_basis_json": json.dumps(relationship.get("centrality_basis", []), ensure_ascii=False),
        "paper_frame_json": json.dumps(frame, ensure_ascii=False),
        "bundle_summary": normalize(result.get("bundle_summary", "")),
        "full_text_priority": normalize(result.get("full_text_priority", "")),
    }
    row[role_field] = object_label
    return row


def convert_bundles(
    bundle_rows: list[dict],
    task_rows: list[dict],
    registry_payload: dict,
    *,
    active_candidate_dois: set[str],
    allow_stale_bundles: bool = False,
    project_secondary_named_anchors: bool = True,
) -> tuple[list[dict], dict]:
    tasks = {normalized_doi(row.get("study_doi", "")): row for row in task_rows}
    compound_registry = registry_index(registry_payload)
    scoped_compound_keys = in_scope_compound_keys(registry_payload)
    evidence_rows: list[dict] = []
    skipped: Counter = Counter()
    for bundle in bundle_rows:
        if normalize(bundle.get("status", "")) != "ok":
            skipped[normalize(bundle.get("status", "")) or "missing_status"] += 1
            continue
        doi = normalized_doi(bundle.get("study_doi", ""))
        if doi not in active_candidate_dois:
            skipped["inactive_candidate"] += 1
            continue
        task = tasks.get(doi)
        if task is None:
            skipped[
                "stale_bundle_not_in_current_tasks"
                if allow_stale_bundles
                else "missing_task"
            ] += 1
            continue
        result = bundle.get("result", {}) if isinstance(bundle.get("result"), dict) else {}
        for index, relationship in enumerate(result.get("relationships", []), start=1):
            if isinstance(relationship, dict):
                evidence_rows.append(
                    relationship_row(
                        bundle,
                        task,
                        relationship,
                        index,
                        compound_registry,
                        scoped_compound_keys,
                    )
                )
                principal = evidence_rows[-1]
                principal["relationship_projection_basis"] = "principal_object"
                if project_secondary_named_anchors and principal["graph_admission_status"] == "main_graph":
                    # Preserve the entire proposition/package in each projection.
                    # Context, population and comparator anchors are not promoted
                    # into additional independent drug-effect objects.
                    projected = {projection_object_key({"role": principal["entity_role"], "label": principal["graph_entity_label"]}, compound_registry)}
                    for anchor_index, anchor in enumerate(relationship.get("anchors", [])):
                        if not isinstance(anchor, dict) or not named_object_domain_supported(relationship, anchor):
                            continue
                        key = projection_object_key(anchor, compound_registry)
                        if not key[1] or key in projected:
                            continue
                        row = relationship_row(bundle, task, relationship, index, compound_registry,
                                               scoped_compound_keys, object_anchor_override=anchor)
                        row["relationship_projection_basis"] = "explicit_named_domain_supported_anchor"
                        row["relationship_projection_anchor_index"] = anchor_index
                        evidence_rows.append(row)
                        projected.add(key)
    report = {
        "schema_version": "review_relationship_evidence_conversion_v3",
        "generated_at_utc": now_utc(),
        "counts": {
            "bundle_rows": len(bundle_rows),
            "papers_converted": len({row["study_doi"] for row in evidence_rows}),
            "relationship_rows": len(evidence_rows),
            "source_relationships": len({row["relationship_source_group_key"] for row in evidence_rows}),
            "additional_named_object_views": sum(row["relationship_projection_basis"] == "explicit_named_domain_supported_anchor" for row in evidence_rows),
        },
        "by_text_depth": dict(Counter(row["access_level"] for row in evidence_rows)),
        "by_prominence": dict(Counter(row["coverage_focus"] for row in evidence_rows)),
        "by_graph_admission": dict(Counter(row["graph_admission_status"] for row in evidence_rows)),
        "by_review_scope": dict(Counter(row["review_scope_status"] for row in evidence_rows)),
        "by_subject_kind": dict(Counter(row["graph_subject_kind"] for row in evidence_rows)),
        "by_entity_kind": dict(Counter(row["kg_entity_kind_override"] for row in evidence_rows)),
        "skipped": dict(skipped),
    }
    return evidence_rows, report


def legacy_review_row(row: dict) -> bool:
    item_type = normalize(row.get("source_item_type", ""))
    paper_type = normalize(row.get("paper_type", ""))
    method = normalize(row.get("review_extraction_method", ""))
    return item_type == "review_coverage_item" or (paper_type in REVIEW_TYPES and method != "paper_centered_one_pass_v2")


def review_row(row: dict) -> bool:
    """Identify every review row so a combined rebuild replaces, rather than appends, reviews."""

    item_type = normalize(row.get("source_item_type", ""))
    paper_type = normalize(row.get("paper_type", ""))
    return item_type in {"review_coverage_item", "review_relationship"} or paper_type in REVIEW_TYPES


def enrich_canonical_metadata(rows: list[dict], candidate_rows: list[dict]) -> int:
    candidates = {
        normalized_doi(row.get("doi", "")): row
        for row in candidate_rows
        if normalized_doi(row.get("doi", ""))
    }
    matched = 0
    seen: set[str] = set()
    for row in rows:
        doi = normalized_doi(row.get("study_doi", ""))
        candidate = candidates.get(doi)
        if not candidate:
            continue
        if doi not in seen:
            matched += 1
            seen.add(doi)
        row["study_title"] = normalize(candidate.get("study_title", "")) or row.get("study_title", "")
        row["study_year"] = normalize(candidate.get("study_year", "")) or row.get("study_year", "")
        row["abstract"] = normalize(candidate.get("abstract", "")) or row.get("abstract", "")
        for field in CANONICAL_METADATA_FIELDS:
            value = candidate.get(field, "")
            if field == "open_access_is_oa" and isinstance(value, bool):
                row[field] = value
            else:
                row[field] = normalize(value)
    return matched


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundles-jsonl", type=Path, default=DEFAULT_BUNDLES)
    parser.add_argument(
        "--tasks-jsonl",
        type=Path,
        action="append",
        default=[],
        help=(
            "Task JSONL to load; repeat for multiple batch files. By default, "
            "all batch_*_tasks.jsonl files beside the default bundle are loaded."
        ),
    )
    parser.add_argument("--registry-json", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--candidate-parquet", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--base-evidence-json", type=Path, default=None)
    parser.add_argument(
        "--allow-stale-bundles",
        action="store_true",
        help=(
            "Skip and count append-only bundle outputs whose DOI is no longer in the "
            "explicit current task set."
        ),
    )
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bundles = read_jsonl(args.bundles_jsonl)
    task_paths = args.tasks_jsonl or sorted(
        (args.bundles_jsonl.parent / "async_batches").glob("batch_*_tasks.jsonl")
    )
    if not task_paths:
        raise SystemExit("No review task JSONL files were found")
    tasks = [task for path in task_paths for task in read_jsonl(path)]
    registry_payload = json.loads(args.registry_json.read_text(encoding="utf-8"))
    candidate_rows = pd.read_parquet(args.candidate_parquet).to_dict("records")
    active_candidate_dois = active_review_candidate_dois(candidate_rows)
    review_rows, report = convert_bundles(
        bundles,
        tasks,
        registry_payload,
        active_candidate_dois=active_candidate_dois,
        allow_stale_bundles=args.allow_stale_bundles,
    )
    if report["skipped"].get("missing_task", 0):
        raise SystemExit(
            f"Refusing to write incomplete review evidence: "
            f"{report['skipped']['missing_task']} bundle rows have no matching task"
        )
    report["inputs"] = {
        "bundles_jsonl": str(args.bundles_jsonl.resolve()),
        "task_jsonl_files": [str(path.resolve()) for path in task_paths],
        "candidate_parquet": str(args.candidate_parquet.resolve()),
    }
    report["counts"]["active_candidate_dois"] = len(active_candidate_dois)
    report["counts"]["papers_with_canonical_metadata"] = enrich_canonical_metadata(review_rows, candidate_rows)
    base_rows = json_array(args.base_evidence_json) if args.base_evidence_json else []
    removed_review_rows = [row for row in base_rows if review_row(row)]
    kept_base = [row for row in base_rows if not review_row(row)]
    removed_legacy = sum(legacy_review_row(row) for row in removed_review_rows)
    removed_current = len(removed_review_rows) - removed_legacy
    combined = [*kept_base, *review_rows]
    write_json_array(args.out_json, combined)
    report["replacement"] = {
        "base_rows": len(base_rows),
        "review_rows_removed": len(removed_review_rows),
        "legacy_review_rows_removed": removed_legacy,
        "current_method_review_rows_removed": removed_current,
        "base_rows_kept": len(kept_base),
        "paper_centered_review_rows_added": len(review_rows),
        "combined_rows": len(combined),
        "review_rows_remaining": sum(review_row(row) for row in combined),
        "legacy_review_rows_remaining": sum(legacy_review_row(row) for row in combined),
    }
    report["outputs"] = {"evidence_json": str(args.out_json.resolve()), "report_json": str(args.report_json.resolve())}
    write_json(args.report_json, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
