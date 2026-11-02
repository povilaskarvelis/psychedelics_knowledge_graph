"""Recover an explicitly measured drug from real-world outcome fields.

The real-world extraction contract uses ``exposure_or_policy`` for a predictor,
which need not be a drug.  A demographic or policy predictor must not become a
compound merely because it is the first nonempty field.  This module resolves
only a single, corroborated drug/class identity in ``public_health_measure``.
It never obtains the identity from a paper title or another finding.
"""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata

from pipeline.extract.io_utils import normalize


DEFAULT_REGISTRY = Path(__file__).resolve().parents[2] / "data" / "curated" / "entity_registry.json"
RESOLUTION_VERSION = "real_world_measure_subject_v1"
MISSING = {"", "not_reported", "not reported", "not_applicable", "not applicable", "none", "unknown", "uncertain", "n/a"}
EXPLICIT_DRUG_FIELDS = (
    "compound", "canonical_compound", "compound_or_class", "compound_or_exposure",
    "compound_or_intervention", "compound_or_analyte", "intervention_or_exposure",
    "exposure_or_intervention",
)
# These are already recognized overview classes, not additions to scientific scope.
CLASS_RULES = (
    (r"\b(?:classic(?:al)?(?: serotonergic)?|serotonergic) (?:psychedelics?|hallucinogens?)\b", "Classic psychedelics"),
    (r"\bhallucinogens?\b", "Hallucinogens"),
    (r"\bdissociatives?\b", "Dissociatives"),
    (r"\bpsychedelics?\b", "Psychedelics"),
)
MEASUREMENT_RE = re.compile(
    r"\b(?:use|users?|using|consum\w*|prevalence|incidence|initiation|exposure|"
    r"availability|access|price|prices|market|purchase\w*|seizures?|overdos\w*|"
    r"poison\w*|death\w*|mortality|hospital\w*|admission\w*|emergency|"
    r"dependen\w*|disorder\w*|frequency|screen\w*|test\w*|positive|"
    r"urine|blood|hair|specimen\w*|content|purity|adulter\w*|drug.check\w*)\b", re.I,
)
MIXED_RE = re.compile(
    r"\b(?:chemsex|polydrug|poly[- ]?substance|mixed[- ]?drug|multi[- ]?drug|"
    r"other (?:illicit )?drugs?|any (?:illicit )?drug|cocaine|heroin|opioids?|"
    r"amphetamines?|methamphetamine|alcohol|cannabis|marijuana|benzodiazepines?|"
    r"GHB|GBL|tobacco|nicotine|prescription drugs?|inhalants?|stimulants?|sedatives?|"
    r"new psychoactive|novel psychoactive|NPS|combination\w*|combined|co[- ]use|"
    r"concurrent use|co[- ]consum\w*)\b", re.I,
)
IDENTITY_MODIFIER_RE = re.compile(r"\b(?:analog(?:ue)?s?|derivatives?|metabolites?|precursors?|endogenous|receptors?|ligands?|binding sites?)\b", re.I)
PREDICTOR_RE = re.compile(r"\b(?:status|policy|policies|laws?|legalization|decriminalization|availability|residence|gender|sex|age|race|ethnic\w*|income|education|employment|belief\w*|attitude\w*|perceived control)\b", re.I)
BACKGROUND_ONLY_RE = re.compile(r"^(?:introduction|background|discussion|references|bibliography)(?:\b|;)", re.I)


def _key(value: object) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", normalize(value)).casefold()).strip()


@lru_cache(maxsize=4)
def _registry_patterns(path: str, mtime_ns: int) -> tuple:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    patterns = []
    for item in payload.get("compounds", []):
        label = normalize(item.get("label", ""))
        if not label:
            continue
        allowed = not normalize(item.get("graph_scope", "")).startswith("out_of_scope")
        for value in [label, *item.get("aliases", [])]:
            alias = _key(value)
            # Very short aliases (for example "K" or "I") are not safe prose identities.
            if len(alias) < 3:
                continue
            pattern = re.compile(r"(?<![\w-])" + re.escape(alias) + r"(?![\w-])", re.I)
            patterns.append((pattern, label, allowed))
    return tuple(patterns)


def _identities(text: str, registry_path: Path) -> list[dict]:
    text = _key(text)
    hits = []
    for pattern, label, allowed in _registry_patterns(str(registry_path), registry_path.stat().st_mtime_ns):
        for match in pattern.finditer(text):
            before = text[max(0, match.start() - 28):match.start()]
            if re.search(r"\b(?:without|excluding|except|other than|non|not)[- ]*$", before):
                continue
            hits.append({"start": match.start(), "end": match.end(), "label": label, "allowed": allowed, "kind": "atomic_compound"})
    for raw_pattern, label in CLASS_RULES:
        for match in re.finditer(raw_pattern, text, re.I):
            before = text[max(0, match.start() - 28):match.start()]
            if re.search(r"\b(?:without|excluding|except|other than|non|not)[- ]*$", before):
                continue
            hits.append({"start": match.start(), "end": match.end(), "label": label, "allowed": True, "kind": "compound_class"})
    # A specific full alias owns its span: do not turn 5-MeO-DMT into DMT or
    # classic psychedelics into a second broad psychedelic identity.
    hits = [h for h in hits if not any(o["start"] <= h["start"] and o["end"] >= h["end"] and o["end"]-o["start"] > h["end"]-h["start"] for o in hits)]
    unique = {}
    for hit in hits:
        unique.setdefault((hit["label"], hit["kind"]), hit)
    return list(unique.values())


def resolve_real_world_measure_subject(row: dict, registry_path: Path = DEFAULT_REGISTRY) -> dict | None:
    """Return a role-aware identity proposal, or None for ambiguous/mixed rows.

    Exact original exposure, estimates and finding text remain untouched.  A
    result is not made drug-specific merely because a drug occurs somewhere in
    the article or an accompanying population description.
    """
    if normalize(row.get("domain", row.get("domain_route", ""))) != "real_world_public_health":
        return None
    exposure = normalize(row.get("exposure_or_policy", ""))
    measure = normalize(row.get("public_health_measure", ""))
    if _key(exposure) in MISSING or _key(measure) in MISSING:
        return None
    if IDENTITY_MODIFIER_RE.search(measure):
        return None
    # Without a use, availability or harm word ("MDMA loads in river water"),
    # the drug must be named only in the measure: a drug predictor keeps its
    # existing subject.
    measurement_word = bool(MEASUREMENT_RE.search(measure))
    if BACKGROUND_ONLY_RE.search(normalize(row.get("evidence_location", ""))) and not re.search(r"\b(?:results|abstract|table|figure)\b", normalize(row.get("evidence_location", "")), re.I):
        return None
    # A named or pooled drug exposure is already a meaningful subject. This
    # repair targets non-drug predictors, not causal reorientation of an
    # existing drug→outcome relationship.
    if MIXED_RE.search(exposure) or IDENTITY_MODIFIER_RE.search(exposure):
        return None
    exposure_hits = _identities(exposure, registry_path)
    if not measurement_word and exposure_hits:
        return None
    measure_hits = _identities(measure, registry_path)
    if len(measure_hits) != 1 or not measure_hits[0]["allowed"]:
        return None
    subject = measure_hits[0]
    if MIXED_RE.search(measure):
        return None
    # An unregistered coded analogue joined to the recognized drug is still a
    # mixture/list; absence from the registry is not permission to drop it.
    if re.search(r"\b\d+[a-z]*[- ][a-z][a-z0-9-]+\b", _key(measure)) and re.search(r"\b(?:and|or|plus)\b|[/&+]", measure):
        return None
    if exposure_hits:
        if {h["label"] for h in exposure_hits} != {subject["label"]} or not PREDICTOR_RE.search(exposure):
            return None
    # Legacy schemas with a separately supplied compound retain their explicit
    # subject. The current schema falls back to exposure_or_policy in compound.
    for field in EXPLICIT_DRUG_FIELDS:
        value = normalize(row.get(field, ""))
        if _key(value) not in MISSING and _key(value) != _key(exposure):
            return None
    finding = " ".join(normalize(row.get(k, "")) for k in ("finding_summary", "association_or_trend"))
    corroborating = _identities(finding, registry_path)
    if subject["label"] not in {h["label"] for h in corroborating}:
        return None
    return {
        "label": subject["label"], "kind": subject["kind"],
        "source_field": "public_health_measure", "source_value": measure,
        "original_predictor": exposure,
        "reason": (
            "single_drug_in_measured_outcome_with_non_drug_predictor" if measurement_word
            else "single_drug_named_only_in_measured_outcome"
        ),
        "version": RESOLUTION_VERSION,
    }


def apply_real_world_measure_subject(row: dict) -> bool:
    """Apply the bounded proposal and keep derived provenance across replays."""
    if normalize(row.get("real_world_subject_resolution_version", "")) == RESOLUTION_VERSION:
        label = normalize(row.get("real_world_measure_subject_label", ""))
        kind = normalize(row.get("real_world_measure_subject_kind", ""))
        if label and kind in {"atomic_compound", "compound_class"}:
            row.update(compound=label, graph_subject_label=label, graph_subject_kind=kind,
                       graph_subject_source_field="public_health_measure", atomic_compound_candidate=label)
            return True
    proposal = resolve_real_world_measure_subject(row)
    if not proposal:
        return False
    row["real_world_original_graph_subject"] = normalize(row.get("compound", "")) or proposal["original_predictor"]
    row["real_world_measure_subject_label"] = proposal["label"]
    row["real_world_measure_subject_kind"] = proposal["kind"]
    row["real_world_subject_resolution_version"] = proposal["version"]
    row["real_world_subject_resolution_reason"] = proposal["reason"]
    row["real_world_subject_resolution_source_value"] = proposal["source_value"]
    row.update(compound=proposal["label"], graph_subject_label=proposal["label"],
               graph_subject_kind=proposal["kind"], graph_subject_source_field=proposal["source_field"],
               atomic_compound_candidate=proposal["label"])
    return True
