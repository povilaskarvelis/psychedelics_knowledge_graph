#!/usr/bin/env python3
"""Assign extraction domains from title/abstract metadata with Gemini."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Iterable

import pandas as pd

try:
    from google import genai
    from google.genai import types
except ModuleNotFoundError as err:  # pragma: no cover - environment guard
    raise SystemExit("google-genai is required for Gemini domain routing") from err

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from pipeline.fulltext.convert_pdfs import normalize_doi
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(ROOT))
    from pipeline.fulltext.convert_pdfs import normalize_doi


DEFAULT_ENV = ROOT / ".env"
DEFAULT_METADATA_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"
DEFAULT_PRESCREEN_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_prescreen_decisions.parquet"
DEFAULT_OUTPUT_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_domain_routing_gemini.parquet"
DEFAULT_SUMMARY_JSON = ROOT / "data" / "processed" / "corpus" / "paper_domain_routing_gemini_summary.json"
DEFAULT_COUNTS_CSV = ROOT / "data" / "processed" / "corpus" / "paper_domain_routing_gemini_counts.csv"
DEFAULT_RAW_JSONL = ROOT / "data" / "processed" / "corpus" / "paper_domain_routing_gemini_raw.jsonl"

TABLE_VERSION = "0.1"
GENERAL_DOMAIN_ROUTE = "general_topic"
DOMAIN_ROUTES = (
    "clinical_outcome",
    "safety_tolerability",
    "molecular_target",
    "molecular_pathway_readout",
    "brain_system",
    "cognitive_behavioral",
    "subjective_experience",
    "pharmacokinetics_exposure",
    "intervention_context",
    "real_world_public_health",
)
DOMAIN_ROUTE_ORDER = DOMAIN_ROUTES + (GENERAL_DOMAIN_ROUTE,)
METHODOLOGICAL_VALIDITY_TAGS = (
    "blinding_expectancy_validity",
    "comparator_control_validity",
    "measurement_psychometric_validity",
    "evidence_quality_bias",
)
SCREENING_DECISIONS = (
    "include_in_scope",
    "exclude_out_of_scope",
    "unclear",
)
PAPER_TYPE_GROUPS = (
    "primary",
    "secondary_literature",
    "non_primary_publication",
)
PAPER_TYPES = (
    "primary",
    "meta_analysis",
    "network_meta_analysis",
    "systematic_review",
    "scoping_review",
    "umbrella_review",
    "narrative_review",
    "literature_review",
    "review",
    "guideline",
    "consensus_statement",
    "protocol",
    "trial_registration",
    "commentary_editorial",
    "correction_retraction",
    "peer_review_artifact",
    "thesis_or_dissertation",
    "book_chapter",
    "news_summary",
    "other_non_primary",
)
SECONDARY_PAPER_TYPES = {
    "meta_analysis",
    "network_meta_analysis",
    "systematic_review",
    "scoping_review",
    "umbrella_review",
    "narrative_review",
    "literature_review",
    "review",
    "guideline",
    "consensus_statement",
}
NON_PRIMARY_PAPER_TYPES = {
    "protocol",
    "trial_registration",
    "commentary_editorial",
    "correction_retraction",
    "peer_review_artifact",
    "thesis_or_dissertation",
    "book_chapter",
    "news_summary",
    "other_non_primary",
}
DOMAIN_DEFINITIONS = {
    "clinical_outcome": "Human clinical indications, symptoms, diagnoses, patient outcomes, functioning, quality of life, remission, response, relapse, or trial efficacy endpoints. Also use for systematic reviews/meta-analyses that synthesize human clinical outcome studies. Do not use for primary animal, cell, or other preclinical disease-model studies just because a human condition is named or translational relevance is discussed. Do not use for healthy-volunteer pharmacology unless clinical symptoms or patient outcomes are a substantive endpoint.",
    "safety_tolerability": "Adverse events, tolerability, abuse liability, toxicity, medical risk, contraindications, physiological safety, discontinuation, or safety monitoring.",
    "molecular_target": "Receptors, transporters, enzymes, ion channels, binding affinity, target engagement, agonism/antagonism, or molecular pharmacology.",
    "molecular_pathway_readout": "Cellular or molecular pathways and readouts, including plasticity, signaling cascades, gene/protein expression, inflammation, neurochemistry, hormones, or other biomarkers/readouts.",
    "brain_system": "Brain regions, circuits, networks, connectivity, neuroimaging, EEG/MEG, PET, oscillations, neural dynamics, or regional brain physiology.",
    "cognitive_behavioral": "Cognitive tasks, behavioral measures or phenotypes, learning, memory, attention, emotion processing, social behavior, addiction behavior, or animal/behavioral phenotypes. For human clinical studies, do not use for ordinary symptom scales, abstinence, response, remission, or functioning unless cognition or behavior is explicitly measured as a distinct construct.",
    "subjective_experience": "Acute subjective effects, altered states, mystical-type experience, ego dissolution, perceptual effects, phenomenology, experience questionnaires, or psychological insight during/after the drug experience. Do not use merely because consciousness, anesthesia, intoxication, or drug effects are mentioned unless subjective experience is measured or central.",
    "pharmacokinetics_exposure": "Pharmacokinetics, exposure-response, dose-response, plasma/serum/blood levels, concentration-time data, metabolism, metabolites, bioavailability, clearance, half-life, or PK/PD. Use for analytical exposure measurement only when exposure, metabolism, or dose/exposure interpretation is a main study question. Do not use merely because a clinical dose, bolus, infusion, route, or toxicology screen is described as part of another study.",
    "intervention_context": "Psychotherapy or treatment model, preparation, integration, set and setting, therapist/facilitator role, dosing-session structure, music, psychological support, manualized therapy such as CBT when it is central to the intervention, or implementation of assisted therapy. Do not use for ordinary trial methodology, blinding, comparator choice, washout, follow-up schedule, or the mere fact that a trial administered a drug.",
    "real_world_public_health": "Epidemiology, prevalence, population-level use patterns, nonmedical/recreational use as the study focus, naturalistic or retreat settings, emergency visits, poison-center data, harm reduction, policy, access, or public-health impact. Do not use merely because participants are described as drug users in a mechanistic or clinical study.",
}
METHODOLOGICAL_VALIDITY_DEFINITIONS = {
    "blinding_expectancy_validity": "The paper substantively evaluates blinding, masking, functional unblinding, expectancy effects, or how participant/rater expectations affect interpretation of psychedelic evidence.",
    "comparator_control_validity": "The paper substantively evaluates placebo, active-placebo, treatment-as-usual, open-label, antidepressant, psychotherapy, or other comparator/control choices and how they affect interpretation.",
    "measurement_psychometric_validity": "The paper substantively validates, critiques, or compares scales, questionnaires, outcome measures, factor structure, reliability, validity, or psychometric interpretation.",
    "evidence_quality_bias": "The paper substantively evaluates risk of bias, certainty/quality of evidence, heterogeneity, small-study effects, GRADE-style certainty, or other evidence-quality concerns.",
}
MAX_ABSTRACT_CHARS = 5000

DOMAIN_DEFINITION_TEXT = "\n".join(f"- {domain}: {description}" for domain, description in DOMAIN_DEFINITIONS.items())
METHODOLOGICAL_VALIDITY_TEXT = "\n".join(
    f"- {tag}: {description}" for tag, description in METHODOLOGICAL_VALIDITY_DEFINITIONS.items()
)


DOMAIN_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "domain_tags": {
            "type": "array",
            "items": {"type": "string", "enum": list(DOMAIN_ROUTES)},
        },
        "primary_domain": {"type": "string", "enum": list(DOMAIN_ROUTE_ORDER)},
        "screening_decision": {"type": "string", "enum": list(SCREENING_DECISIONS)},
        "screening_reason": {"type": "string"},
        "paper_type_group": {"type": "string", "enum": list(PAPER_TYPE_GROUPS)},
        "paper_type": {"type": "string", "enum": list(PAPER_TYPES)},
        "paper_type_labels": {
            "type": "array",
            "items": {"type": "string", "enum": list(PAPER_TYPES)},
        },
        "paper_type_reason": {"type": "string"},
        "methodological_validity_tags": {
            "type": "array",
            "items": {"type": "string", "enum": list(METHODOLOGICAL_VALIDITY_TAGS)},
        },
        "rationale": {"type": "string"},
    },
    "required": [
        "domain_tags",
        "primary_domain",
        "screening_decision",
        "screening_reason",
        "paper_type_group",
        "paper_type",
        "paper_type_labels",
        "paper_type_reason",
        "methodological_validity_tags",
        "rationale",
    ],
    "additionalProperties": False,
}


SYSTEM_INSTRUCTION = f"""Classify a scientific paper record by scope, evidence domain, and paper type.

Base the classification on the supplied title and abstract. Use publication
labels, MeSH terms, and keywords only as supporting context; these metadata can
be incomplete or misleading and should not override clear title or abstract
evidence.

Evidence domain options:
{DOMAIN_DEFINITION_TEXT}

Set domain_tags and primary_domain as follows:
- Choose domain_tags for every evidence domain that is substantively supported.
- A supported domain is a study question, analysis target, measured endpoint,
  original result type, or major synthesis topic.
- Multiple domain_tags are allowed, but prefer a compact set that reflects the
  central evidence rather than every term mentioned in the abstract.
- If no specific evidence domain is supported, use primary_domain
  "general_topic" with empty domain_tags only when the title/abstract is still
  broadly relevant to psychedelic evidence, such as a conceptual overview,
  cross-domain synthesis, or methodological context relevant to the domains
  above.
- "general_topic" is not a catch-all for out-of-scope records.
- For unclear, assign supported domains if possible; otherwise use no
  domain_tags and primary_domain "general_topic".
- An empty domain_tags list is not by itself an exclusion signal.

Special domain rules:
- A record is in scope only when the psychedelic-related substance,
  intervention, exposure, or evidence topic is a central study object or major
  synthesis topic.
- Exclude records where the psychedelic-related topic is only a background
  example, comparison point, assay reagent, radioligand, challenge probe for
  another drug's development, or one item in a broad list.
- For broad clinical, therapeutic, biological, psychiatric, or conceptual
  reviews, include only when psychedelic-related evidence is a central topic of
  the title/abstract. Exclude when a psychedelic-related intervention or state
  is only one example among many treatments, mechanisms, or analogies.
- Exclude papers about non-psychedelic drugs, targets, therapies, cognitive
  systems, music, meditation, language, or consciousness when psychedelic
  evidence is used only as an analogy, motivation, or illustrative example.
- Generic serotonin, monoamine, receptor, neurobiology, psychiatry, biomarker,
  or therapy papers are out of scope unless they are directly centered on
  psychedelic-related evidence.
- Ketamine, esketamine, or arketamine records are out of scope when the focus is
  perioperative/procedural anesthesia, postoperative pain, general sedation,
  analgesia, or veterinary anesthesia rather than psychiatric, addiction,
  psychological-therapy, or psychedelic-related evidence.
- For primary animal, cell, tissue, in vitro, or ex vivo studies, do not assign
  clinical_outcome. Use cognitive_behavioral, brain_system,
  molecular_pathway_readout, safety_tolerability, or pharmacokinetics_exposure
  if those endpoints are actually measured.
- For reviews, assign a domain only if the review substantively synthesizes that
  evidence type, not because a mechanism or outcome is named in passing.
- Exclude protocols, trial registrations, corrections, errata, decision
  letters, peer-review reports, Faculty Opinions/recommendations, replies, and
  citation/container records unless the title/abstract contains substantive
  evidence synthesis or original results. Do not assign domain tags to a
  correction or protocol solely from the study described in its title.
- Use exclude_out_of_scope for records about cannabis, opioids, stimulants,
  alcohol, general psychiatry, general anesthesia, or unrelated neuroscience
  unless the title/abstract centrally links them to psychedelic-related evidence
  covered by the domains above.

Optional methodological validity modifiers:
{METHODOLOGICAL_VALIDITY_TEXT}

Use methodological_validity_tags only when the paper substantively evaluates
whether evidence in a clinical, subjective-experience, intervention-context, or
public-health domain is interpretable or well measured. Ordinary study design
descriptions, general laboratory assay development, analytical chemistry
methods, drug-checking methods, and computational tools do not need
methodological_validity_tags unless they directly evaluate interpretation of
psychedelic evidence.

For methodological papers about blinding, trial design, measurement bias, or
regulatory validity, keep the main domain tied to the evidence being judged,
usually clinical_outcome, subjective_experience, intervention_context, or
real_world_public_health, and add methodological_validity_tags when appropriate.

Set paper_type_group, paper_type, and paper_type_labels as follows:
- primary: original empirical research, including human trials,
  observational studies, case reports/series, animal studies, cell or tissue
  studies, pharmacokinetic studies, surveys, qualitative studies, and records
  that appear empirical but are too thin to classify more specifically. Do not
  use primary for analyses where the data are publications, citations, search
  records, or research-field metadata rather than participants, patients,
  animals, cells, tissues, assays, samples, or real-world exposure/outcome
  records. Use paper_type "primary" and paper_type_labels ["primary"].
- secondary_literature: papers that synthesize or summarize multiple studies,
  bodies of evidence, clinical guidance, expert consensus, or the research
  literature itself. Bibliometric, scientometric, citation-network, and
  research-trend or knowledge-map papers belong here, usually as paper_type
  "review", unless the input supports a more specific review type. Set
  paper_type to the most specific paper type supported by the input:
  meta_analysis, network_meta_analysis, systematic_review, scoping_review,
  umbrella_review, narrative_review, literature_review, review, guideline, or
  consensus_statement. Set paper_type_labels to every supported secondary label
  from that list. For example, a "systematic review and meta-analysis" should
  use paper_type "meta_analysis" and paper_type_labels including both
  "systematic_review" and "meta_analysis".
- non_primary_publication: records that are not usable as original evidence or
  evidence synthesis, such as protocols, trial registrations, commentaries,
  editorials, letters, replies, corrections, retractions, peer-review reports,
  author responses, dissertations, theses, book chapters, container/citation
  records, or news summaries. Set paper_type to the most specific paper type
  supported by the input: protocol, trial_registration, commentary_editorial,
  correction_retraction, peer_review_artifact,
  thesis_or_dissertation, book_chapter, news_summary, or other_non_primary. Set
  paper_type_labels to every supported non-primary label from that list.

Paper type rules:
- Prefer explicit title and abstract evidence over weak hints.
- If a protocol paper also reports pilot or completed study results, classify
  it as primary rather than protocol.
- If a review also reports a quantitative pooled analysis, classify it as
  meta_analysis or network_meta_analysis.
- Always include paper_type itself in paper_type_labels.
- Do not add the generic "review" label when a more specific review type is
  supported, unless the input itself only supports a generic review label.
- Generic "review" labels can indicate secondary_literature, but do not treat
  "peer review" or peer-review artifacts as evidence synthesis.
- For non_primary_publication records, normally use screening_decision
  "exclude_out_of_scope" unless the title/abstract contains substantive
  original results or evidence synthesis.

Set screening_decision after domain and paper-type assignment:
- include_in_scope: use when the title/abstract substantively supports at least
  one evidence domain, or when primary_domain is "general_topic" for a broadly
  relevant psychedelic evidence paper.
- exclude_out_of_scope: use when the title/abstract does not support any
  evidence domain and does not support in-scope "general_topic" relevance. Also
  use this for records that are only container/citation/issue records or contain
  only a passing/background mention of an in-scope topic.
- unclear: use when the title/abstract suggests possible relevance, but the
  information provided is too thin or ambiguous to decide confidently.
- For exclude_out_of_scope, return no domain_tags and primary_domain
  "general_topic".
- For non_primary_publication records that are excluded, return no domain_tags
  and primary_domain "general_topic" even if the title mentions an in-scope
  substance or disorder.

Return only compact JSON matching the provided schema.
"""


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


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


def load_dotenv(path: Path) -> dict[str, str]:
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def read_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def read_doi_file(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"DOI file not found: {path}")
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        doi = normalize_doi(line.split(",", 1)[0])
        if doi:
            out.add(doi)
    return out


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).lower() in {"1", "true", "yes", "y", "retain"}


def prescreen_row_is_extraction_candidate(row: dict) -> bool:
    if "retained_for_extraction_candidate" in row:
        return truthy(row.get("retained_for_extraction_candidate", False))
    return clean(row.get("prescreen_decision", "")) == "retain"


def retained_dois(prescreen_df: pd.DataFrame, scoped_dois: set[str]) -> set[str]:
    out = set()
    if prescreen_df.empty or "doi" not in prescreen_df.columns:
        return out
    for row in prescreen_df.to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        if not doi or (scoped_dois and doi not in scoped_dois):
            continue
        if prescreen_row_is_extraction_candidate(row):
            out.add(doi)
    return out


def aggregate_prescreen_context(prescreen_df: pd.DataFrame) -> dict[str, dict]:
    out: dict[str, dict] = defaultdict(lambda: {"datasets": [], "prescreen_run_ids": []})
    if prescreen_df.empty or "doi" not in prescreen_df.columns:
        return {}
    for row in prescreen_df.to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        if not doi:
            continue
        if not prescreen_row_is_extraction_candidate(row):
            continue
        entry = out[doi]
        for field, target in (("dataset", "datasets"), ("run_id", "prescreen_run_ids")):
            value = clean(row.get(field, ""))
            if value and value not in entry[target]:
                entry[target].append(value)
    return dict(out)


def row_by_doi(df: pd.DataFrame) -> dict[str, dict]:
    out = {}
    if df.empty or "doi" not in df.columns:
        return out
    for row in df.to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        if doi:
            out[doi] = row
    return out


def selected_records(
    metadata_df: pd.DataFrame,
    prescreen_df: pd.DataFrame,
    *,
    scoped_dois: set[str],
    limit: int,
    completed: set[str],
) -> list[dict]:
    retained = retained_dois(prescreen_df, scoped_dois)
    prescreen_context = aggregate_prescreen_context(prescreen_df)
    rows = []
    for row in metadata_df.to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        if not doi or doi not in retained or doi in completed:
            continue
        context = prescreen_context.get(doi, {})
        rows.append(
            {
                "doi": doi,
                "datasets": join_values(context.get("datasets", [])) or clean(row.get("datasets", "")),
                "study_title": clean(row.get("study_title", "")),
                "study_year": clean(row.get("study_year", "")),
                "abstract": clean(row.get("abstract", "")),
                "publication_type": clean(row.get("publication_type", "")),
                "mesh_terms": clean(row.get("mesh_terms", "")),
                "keywords": clean(row.get("keywords", "")),
                "prescreen_run_ids": join_values(context.get("prescreen_run_ids", [])),
            }
        )
    rows.sort(key=lambda record: record["doi"])
    if limit > 0:
        rows = rows[:limit]
    return rows


def completed_dois(raw_jsonl: Path) -> set[str]:
    out = set()
    if not raw_jsonl.exists():
        return out
    with raw_jsonl.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if clean(row.get("status", "")) == "ok":
                doi = normalize_doi(row.get("doi", ""))
                if doi:
                    out.add(doi)
    return out


def prompt_for_record(record: dict) -> str:
    abstract = clean(record.get("abstract", ""))
    if len(abstract) > MAX_ABSTRACT_CHARS:
        abstract = abstract[:MAX_ABSTRACT_CHARS] + " [truncated]"
    return f"""Paper record:
DOI: {record['doi']}
Title: {record['study_title']}
Year: {record['study_year']}
Abstract: {abstract}

Context metadata:
Publication labels: {record['publication_type']}
MeSH terms: {record['mesh_terms']}
Keywords: {record['keywords']}
"""


def generation_config(args: argparse.Namespace) -> types.GenerateContentConfig:
    config = {
        "system_instruction": SYSTEM_INSTRUCTION,
        "response_mime_type": "application/json",
        "response_json_schema": DOMAIN_RESPONSE_SCHEMA,
        "temperature": args.temperature,
        "max_output_tokens": args.max_output_tokens,
    }
    if args.thinking_budget is not None:
        config["thinking_config"] = types.ThinkingConfig(thinking_budget=args.thinking_budget)
    return types.GenerateContentConfig(**config)


def parse_response_text(text: str) -> dict:
    stripped = clean(text)
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        payload = salvage_partial_json_response(stripped)
        if not payload:
            raise exc
    if not isinstance(payload, dict):
        raise ValueError("Gemini domain routing response was not a JSON object")
    return payload


def json_string_field(text: str, field: str) -> str:
    match = re.search(rf'"{re.escape(field)}"\s*:\s*"((?:\\.|[^"\\])*)"', text, flags=re.DOTALL)
    if not match:
        return ""
    try:
        return json.loads(f'"{match.group(1)}"')
    except json.JSONDecodeError:
        return match.group(1)


def json_array_field(text: str, field: str) -> list:
    match = re.search(rf'"{re.escape(field)}"\s*:\s*(\[[^\]]*\])', text, flags=re.DOTALL)
    if not match:
        return []
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def salvage_partial_json_response(text: str) -> dict:
    payload = {
        "domain_tags": json_array_field(text, "domain_tags"),
        "primary_domain": json_string_field(text, "primary_domain"),
        "screening_decision": json_string_field(text, "screening_decision"),
        "screening_reason": json_string_field(text, "screening_reason"),
        "paper_type_group": json_string_field(text, "paper_type_group"),
        "paper_type": json_string_field(text, "paper_type"),
        "paper_type_labels": json_array_field(text, "paper_type_labels"),
        "paper_type_reason": json_string_field(text, "paper_type_reason"),
        "methodological_validity_tags": json_array_field(text, "methodological_validity_tags"),
        "rationale": json_string_field(text, "rationale"),
    }
    if payload["domain_tags"] or payload["primary_domain"] or payload["screening_decision"] or payload["paper_type"]:
        return payload
    return {}


def paper_type_group_for(paper_type: str) -> str:
    if paper_type in SECONDARY_PAPER_TYPES:
        return "secondary_literature"
    if paper_type in NON_PRIMARY_PAPER_TYPES:
        return "non_primary_publication"
    return "primary"


def normalize_paper_type_labels(paper_type: str, raw_labels: object) -> list[str]:
    expected_group = paper_type_group_for(paper_type)
    labels: list[str] = []
    raw_values = raw_labels if isinstance(raw_labels, list) else []
    for item in raw_values:
        value = clean(item)
        if value in PAPER_TYPES and paper_type_group_for(value) == expected_group and value not in labels:
            labels.append(value)
    if paper_type not in labels:
        labels.insert(0, paper_type)
    if expected_group == "primary":
        return ["primary"]
    return labels


def normalize_payload(payload: dict) -> dict:
    tags = []
    for tag in payload.get("domain_tags", []) or []:
        value = clean(tag)
        if value in DOMAIN_ROUTES and value not in tags:
            tags.append(value)
    validity_tags = []
    for tag in payload.get("methodological_validity_tags", []) or []:
        value = clean(tag)
        if value in METHODOLOGICAL_VALIDITY_TAGS and value not in validity_tags:
            validity_tags.append(value)
    primary = clean(payload.get("primary_domain", ""))
    if primary not in DOMAIN_ROUTE_ORDER:
        primary = tags[0] if tags else GENERAL_DOMAIN_ROUTE
    if primary == GENERAL_DOMAIN_ROUTE and tags:
        primary = tags[0]
    if primary != GENERAL_DOMAIN_ROUTE and primary not in tags:
        tags.insert(0, primary)
    screening_decision = clean(payload.get("screening_decision", "")).lower()
    if screening_decision not in SCREENING_DECISIONS:
        if screening_decision == "include_for_extraction":
            screening_decision = "include_in_scope"
        else:
            screening_decision = "include_in_scope" if tags else "unclear"
    if screening_decision == "exclude_out_of_scope":
        tags = []
        validity_tags = []
        primary = GENERAL_DOMAIN_ROUTE
    paper_type = clean(payload.get("paper_type", ""))
    if paper_type not in PAPER_TYPES:
        paper_type = "primary"
    paper_type_group = clean(payload.get("paper_type_group", ""))
    expected_group = paper_type_group_for(paper_type)
    if paper_type_group not in PAPER_TYPE_GROUPS or paper_type_group != expected_group:
        paper_type_group = expected_group
    paper_type_labels = normalize_paper_type_labels(paper_type, payload.get("paper_type_labels", []))
    return {
        "domain_tags": tags,
        "primary_domain": primary,
        "screening_decision": screening_decision,
        "screening_reason": clean(payload.get("screening_reason", "")),
        "paper_type_group": paper_type_group,
        "paper_type": paper_type,
        "paper_type_labels": paper_type_labels,
        "paper_type_reason": clean(payload.get("paper_type_reason", "")),
        "methodological_validity_tags": validity_tags,
        "rationale": clean(payload.get("rationale", "")),
    }


def usage_dict(response: object) -> dict:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return {}
    try:
        return usage.model_dump(mode="json", exclude_none=True)
    except Exception:
        return {}


def retry_delay_for_error(exc: Exception, default_sleep: float) -> float:
    text = str(exc)
    match = re.search(r"retry_delay\\s*{\\s*seconds:\\s*(\\d+)", text)
    if match:
        return max(float(match.group(1)), default_sleep)
    return max(0.0, default_sleep)


def run_gemini(args: argparse.Namespace) -> list[dict]:
    env_values = load_dotenv(Path(args.env_file).resolve())
    api_key = env_values.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    model = clean(args.model) or env_values.get("GEMINI_MODEL") or os.environ.get("GEMINI_MODEL", "") or "gemini-2.5-flash"
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is missing. Add it to project .env or the environment.")

    scoped_dois = read_doi_file(Path(args.doi_file).resolve()) if clean(args.doi_file) else set()
    completed = completed_dois(Path(args.raw_jsonl).resolve()) if args.resume else set()
    records = selected_records(
        read_table(Path(args.metadata_table).resolve()),
        read_table(Path(args.prescreen_decisions_table).resolve()),
        scoped_dois=scoped_dois,
        limit=args.limit,
        completed=completed,
    )
    client = genai.Client(api_key=api_key)
    config = generation_config(args)
    raw_jsonl = Path(args.raw_jsonl).resolve()
    raw_jsonl.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if args.resume else "w"
    rows = []
    with raw_jsonl.open(mode, encoding="utf-8") as handle:
        for index, record in enumerate(records, start=1):
            print(f"[{index}/{len(records)}] {record['doi']} {record['study_title'][:90]}", flush=True)
            raw_row = {
                "generated_at_utc": now_utc(),
                "doi": record["doi"],
                "model": model,
                "status": "error",
                "response_text": "",
                "parsed": {},
                "usage": {},
                "error": "",
            }
            attempts = max(1, args.max_retries + 1)
            for attempt in range(1, attempts + 1):
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=prompt_for_record(record),
                        config=config,
                    )
                    text = response.text or ""
                    parsed = normalize_payload(parse_response_text(text))
                    raw_row.update(
                        {
                            "status": "ok",
                            "response_text": text,
                            "parsed": parsed,
                            "usage": usage_dict(response),
                            "attempts_used": attempt,
                        }
                    )
                    rows.append({**record, **parsed, "model": model})
                    break
                except Exception as exc:  # pragma: no cover - network/API behavior
                    if attempt >= attempts:
                        raw_row.update(
                            {
                                "error": str(exc).replace(api_key, "[REDACTED]"),
                                "attempts_used": attempt,
                            }
                        )
                    else:
                        time.sleep(retry_delay_for_error(exc, args.retry_sleep_sec))
            handle.write(json.dumps(raw_row, ensure_ascii=False) + "\n")
            handle.flush()
            if args.sleep_sec > 0:
                time.sleep(args.sleep_sec)
    return rows


def parsed_rows_from_raw(raw_jsonl: Path, metadata_df: pd.DataFrame, prescreen_df: pd.DataFrame) -> list[dict]:
    metadata_by_doi = row_by_doi(metadata_df)
    prescreen_context = aggregate_prescreen_context(prescreen_df)
    rows = []
    if not raw_jsonl.exists():
        return rows
    with raw_jsonl.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            raw = json.loads(line)
            if clean(raw.get("status", "")) != "ok":
                continue
            doi = normalize_doi(raw.get("doi", ""))
            parsed = raw.get("parsed", {})
            if not doi or not isinstance(parsed, dict):
                continue
            meta = metadata_by_doi.get(doi, {})
            context = prescreen_context.get(doi, {})
            parsed = normalize_payload(parsed)
            rows.append(
                {
                    "doi": doi,
                    "datasets": join_values(context.get("datasets", [])) or clean(meta.get("datasets", "")),
                    "study_title": clean(meta.get("study_title", "")),
                    "study_year": clean(meta.get("study_year", "")),
                    "prescreen_run_ids": join_values(context.get("prescreen_run_ids", [])),
                    "domain_tags": parsed.get("domain_tags", []),
                    "primary_domain": clean(parsed.get("primary_domain", "")),
                    "screening_decision": clean(parsed.get("screening_decision", "")),
                    "screening_reason": clean(parsed.get("screening_reason", "")),
                    "paper_type_group": clean(parsed.get("paper_type_group", "")),
                    "paper_type": clean(parsed.get("paper_type", "")),
                    "paper_type_labels": parsed.get("paper_type_labels", []),
                    "paper_type_reason": clean(parsed.get("paper_type_reason", "")),
                    "methodological_validity_tags": parsed.get("methodological_validity_tags", []),
                    "rationale": clean(parsed.get("rationale", "")),
                    "model": clean(raw.get("model", "")),
                }
            )
    return rows


def secondary_source_types_for(paper_type: str, paper_type_labels: Iterable[str] = ()) -> str:
    if paper_type not in SECONDARY_PAPER_TYPES:
        return ""
    labels = [label for label in paper_type_labels if label in SECONDARY_PAPER_TYPES]
    if paper_type not in labels:
        labels.insert(0, paper_type)
    if "review" not in labels:
        labels.append("review")
    return join_values(labels)


def literature_route_for(paper_type_group: str) -> str:
    if paper_type_group == "secondary_literature":
        return "secondary_literature_extraction"
    if paper_type_group == "non_primary_publication":
        return "non_primary_context_or_skip"
    return "primary_literature_extraction"


def route_rows_from_parsed(parsed_rows: list[dict], generated_at_utc: str) -> list[dict]:
    route_rank = {route: rank for rank, route in enumerate(DOMAIN_ROUTE_ORDER)}
    rows = []
    for row in parsed_rows:
        tags = [tag for tag in row.get("domain_tags", []) if tag in DOMAIN_ROUTES]
        validity_tags = [
            tag for tag in row.get("methodological_validity_tags", []) if tag in METHODOLOGICAL_VALIDITY_TAGS
        ]
        screening_decision = clean(row.get("screening_decision", "")) or "include_in_scope"
        if screening_decision == "include_for_extraction":
            screening_decision = "include_in_scope"
        if screening_decision not in SCREENING_DECISIONS:
            screening_decision = "include_in_scope" if tags else "unclear"
        paper_type = clean(row.get("paper_type", ""))
        if paper_type not in PAPER_TYPES:
            paper_type = "primary"
        paper_type_group = clean(row.get("paper_type_group", ""))
        expected_group = paper_type_group_for(paper_type)
        if paper_type_group not in PAPER_TYPE_GROUPS or paper_type_group != expected_group:
            paper_type_group = expected_group
        paper_type_labels = normalize_paper_type_labels(paper_type, row.get("paper_type_labels", []))
        secondary_source_types = secondary_source_types_for(paper_type, paper_type_labels)
        primary_secondary_source_type = paper_type if paper_type_group == "secondary_literature" else ""
        non_primary_flags = paper_type if paper_type_group == "non_primary_publication" else ""
        routes = tags or [GENERAL_DOMAIN_ROUTE]
        all_tags = join_values(tags)
        all_validity_tags = join_values(validity_tags)
        for route in routes:
            rows.append(
                {
                    "table_version": TABLE_VERSION,
                    "generated_at_utc": generated_at_utc,
                    "doi": row["doi"],
                    "datasets": clean(row.get("datasets", "")),
                    "retained_for_extraction_candidate": screening_decision != "exclude_out_of_scope",
                    "study_title": clean(row.get("study_title", "")),
                    "study_year": clean(row.get("study_year", "")),
                    "prescreen_run_ids": clean(row.get("prescreen_run_ids", "")),
                    "paper_type_group": paper_type_group,
                    "paper_type": paper_type,
                    "paper_type_labels": join_values(paper_type_labels),
                    "paper_type_reason": clean(row.get("paper_type_reason", "")),
                    "source_family": paper_type_group,
                    "literature_route": literature_route_for(paper_type_group),
                    "secondary_source_types": secondary_source_types,
                    "primary_secondary_source_type": primary_secondary_source_type,
                    "metadata_secondary_types": "",
                    "title_abstract_secondary_types": "",
                    "non_primary_flags": non_primary_flags,
                    "literature_type_confidence": "model",
                    "all_domain_tags": all_tags,
                    "primary_domain": clean(row.get("primary_domain", "")),
                    "screening_decision": screening_decision,
                    "screening_reason": clean(row.get("screening_reason", "")),
                    "methodological_validity_tags": all_validity_tags,
                    "domain_route": route,
                    "domain_tag": "" if route == GENERAL_DOMAIN_ROUTE else route,
                    "domain_route_basis": f"Gemini title/abstract domain routing: {clean(row.get('rationale', ''))}",
                    "tag_source_fields": "gemini_title_abstract",
                    "model": clean(row.get("model", "")),
                }
            )
    rows.sort(key=lambda item: (item["doi"], route_rank.get(item["domain_route"], 999)))
    return rows


def write_table(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, engine="pyarrow", index=False)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_counts_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["count_type", "value", "count"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_summary(rows: list[dict], *, inputs: dict) -> tuple[dict, list[dict]]:
    routed_dois = {row["doi"] for row in rows}
    screening_by_doi: dict[str, str] = {}
    methodological_tag_by_doi: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        doi = clean(row.get("doi", ""))
        if not doi:
            continue
        if doi not in screening_by_doi:
            screening_by_doi[doi] = clean(row.get("screening_decision", "")) or "unclear"
        for tag in split_values(row.get("methodological_validity_tags", "")):
            if tag in METHODOLOGICAL_VALIDITY_TAGS:
                methodological_tag_by_doi[doi].add(tag)
    methodological_counts = Counter(
        tag for tags in methodological_tag_by_doi.values() for tag in tags
    )
    summary = {
        "generated_at_utc": now_utc(),
        "table_version": TABLE_VERSION,
        "inputs": inputs,
        "route_rows": len(rows),
        "routed_dois": len(routed_dois),
        "by_domain_route": dict(Counter(row["domain_route"] for row in rows)),
        "by_screening_decision": dict(Counter(clean(row.get("screening_decision", "")) for row in rows)),
        "by_screening_decision_doi": dict(Counter(screening_by_doi.values())),
        "by_paper_type_group": dict(Counter(clean(row.get("paper_type_group", "")) for row in rows)),
        "by_paper_type": dict(Counter(clean(row.get("paper_type", "")) for row in rows)),
        "by_paper_type_label": dict(Counter(label for row in rows for label in split_values(row.get("paper_type_labels", "")))),
        "by_methodological_validity_tag": dict(methodological_counts),
        "methodological_validity_dois": len(methodological_tag_by_doi),
    }
    counts = []
    for count_type, values in (
        ("domain_route", summary["by_domain_route"]),
        ("screening_decision", summary["by_screening_decision"]),
        ("screening_decision_doi", summary["by_screening_decision_doi"]),
        ("paper_type_group", summary["by_paper_type_group"]),
        ("paper_type", summary["by_paper_type"]),
        ("paper_type_label", summary["by_paper_type_label"]),
        ("methodological_validity_tag", summary["by_methodological_validity_tag"]),
    ):
        for value, count in sorted(values.items()):
            counts.append({"count_type": count_type, "value": value, "count": count})
    return summary, counts


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assign paper domain routes from title/abstract metadata with Gemini.")
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--prescreen-decisions-table", default=str(DEFAULT_PRESCREEN_TABLE))
    parser.add_argument("--output-table", default=str(DEFAULT_OUTPUT_TABLE))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY_JSON))
    parser.add_argument("--counts-csv", default=str(DEFAULT_COUNTS_CSV))
    parser.add_argument("--raw-jsonl", default=str(DEFAULT_RAW_JSONL))
    parser.add_argument("--doi-file", default="", help="Optional DOI list for a scoped Gemini routing run.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    parser.add_argument("--model", default="", help="Override GEMINI_MODEL from .env")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--parse-only", action="store_true", help="Rebuild the Parquet table from an existing raw JSONL without calling Gemini.")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=512)
    parser.add_argument("--thinking-budget", type=int, default=0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-sleep-sec", type=float, default=5.0)
    parser.add_argument("--sleep-sec", type=float, default=0.0)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    metadata_table = Path(args.metadata_table).resolve()
    prescreen_table = Path(args.prescreen_decisions_table).resolve()
    raw_jsonl = Path(args.raw_jsonl).resolve()
    if not args.parse_only:
        run_gemini(args)
    metadata_df = read_table(metadata_table)
    prescreen_df = read_table(prescreen_table)
    parsed_rows = parsed_rows_from_raw(raw_jsonl, metadata_df, prescreen_df)
    generated_at_utc = now_utc()
    rows = route_rows_from_parsed(parsed_rows, generated_at_utc)
    output_table = Path(args.output_table).resolve()
    summary_json = Path(args.summary_json).resolve()
    counts_csv = Path(args.counts_csv).resolve()
    write_table(output_table, rows)
    summary, counts = build_summary(
        rows,
        inputs={
            "metadata_table": str(metadata_table),
            "prescreen_decisions_table": str(prescreen_table),
            "raw_jsonl": str(raw_jsonl),
            "doi_file": str(Path(args.doi_file).resolve()) if clean(args.doi_file) else "",
            "limit": int(args.limit),
            "model": clean(args.model) or load_dotenv(Path(args.env_file).resolve()).get("GEMINI_MODEL", ""),
            "parse_only": bool(args.parse_only),
        },
    )
    write_json(summary_json, summary)
    write_counts_csv(counts_csv, counts)
    print(f"Gemini domain route rows: {summary['route_rows']:,}")
    print(f"Routed DOIs: {summary['routed_dois']:,}")
    print(f"By domain route: {summary['by_domain_route']}")
    print(f"Domain routing table: {output_table}")
    print(f"Summary: {summary_json}")
    print(f"Counts: {counts_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
