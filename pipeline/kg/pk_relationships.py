"""Infer graph-worthy pharmacokinetic relationships from extraction rows."""

from __future__ import annotations

import re
import unicodedata

MISSING_VALUES = {
    "",
    "not_reported",
    "not reported",
    "not_applicable",
    "not applicable",
    "none",
    "n/a",
    "na",
    "unknown",
    "uncertain",
}

PK_RELATIONSHIP_LABELS = {
    "exposure_characterized": "exposure characterized",
    "metabolized_to": "metabolized to",
    "metabolized_by": "metabolized by",
    "metabolized_via": "metabolized via",
    "exposure_altered_by": "exposure altered by",
    "route_or_formulation_changes_exposure": "route/formulation changes exposure",
    "distributed_to": "distributed to",
    "eliminated_by": "eliminated by",
    "exposure_linked_to_effect": "exposure linked to effect",
    "detected_or_monitored_in": "detected/monitored in",
    "other_pk_relationship": "PK relationship",
    "uncertain": "uncertain",
}

METABOLIC_TARGET_RE = re.compile(
    r"\b(cyp\d|cytochrome|mao[- ]?[ab]?|monoamine oxidase|ugt|comt|aldh\d?|"
    r"aldehyde dehydrogenase|alkaline phosphatase|p[- ]?glycoprotein|p[- ]?gp|"
    r"abc[bgc]\d|bcrp|oatp?|oct\d|efflux transporter)\b",
    re.IGNORECASE,
)
NON_PK_TARGET_TRANSPORTER_RE = re.compile(r"\b(sert|dat|net|slc6a[234])\b", re.IGNORECASE)
METABOLISM_PATHWAY_RE = re.compile(
    r"\b(n[- ]?demethylation|o[- ]?demethylation|demethylenation|deamination|"
    r"dephosphorylation|glucuronidation|hydroxylation|oxidation|first[- ]pass|"
    r"hepatic metabolism|renal excretion|metabolism|metabolic)\b",
    re.IGNORECASE,
)
INTERACTION_RE = re.compile(
    r"\b(inhibit\w*|inhibitor|induc\w*|interaction|co[- ]?admin|pretreat\w*|"
    r"alter\w*|increase\w*|decrease\w*|potentiat\w*|attenuat\w*)\b",
    re.IGNORECASE,
)
METABOLITE_CONTEXT_RE = re.compile(
    r"\b(metabolite|metabolized|metabolised|converted|conversion|formation|formed|"
    r"biotransformation|dephosphorylat\w*|demethylat\w*|glucuronid\w*)\b",
    re.IGNORECASE,
)
EXPOSURE_RESPONSE_RE = re.compile(
    r"\b(exposure[- ]response|concentration[- ]response|dose[- ]response|pk/pd|"
    r"pharmacodynamic|receptor occupancy|occupancy|ec50|ic50|ed50|emax|effect)\b",
    re.IGNORECASE,
)
DISTRIBUTION_RE = re.compile(
    r"\b(brain|cerebrospinal|csf|tissue|volume of distribution|vd|blood[- ]brain|bbb|"
    r"penetration|distribution|protein binding|plasma protein binding)\b",
    re.IGNORECASE,
)
ELIMINATION_RE = re.compile(r"\b(clearance|half[- ]life|t1/2|excretion|elimination|urine|urinary)\b", re.IGNORECASE)
DETECTION_RE = re.compile(
    r"\b(detection|detected|presence|presence/absence|limit of detection|lod|loq|"
    r"forensic|hair|wastewater|oral fluid|postmortem|autopsy)\b",
    re.IGNORECASE,
)
BIOAVAILABILITY_ROUTE_RE = re.compile(
    r"\b(bioavailability|route|formulation|dissolution|drug release|delivery|oral|"
    r"intranasal|sublingual|buccal|inhal\w*|dry powder|transdermal)\b",
    re.IGNORECASE,
)

ROUTE_LABELS = {
    "oral": "Oral administration",
    "p.o.": "Oral administration",
    "po": "Oral administration",
    "oral gavage": "Oral administration",
    "gavage": "Oral administration",
    "intravenous": "Intravenous exposure",
    "intravenous infusion": "Intravenous exposure",
    "iv": "Intravenous exposure",
    "intranasal": "Intranasal delivery",
    "sublingual": "Sublingual delivery",
    "buccal": "Buccal delivery",
    "sublingual or buccal": "Sublingual/buccal delivery",
    "inhalation": "Inhaled delivery",
    "inhaled": "Inhaled delivery",
    "intraperitoneal": "Intraperitoneal exposure",
    "i.p.": "Intraperitoneal exposure",
    "subcutaneous": "Subcutaneous exposure",
    "s.c.": "Subcutaneous exposure",
}

MATRIX_LABELS = {
    "plasma": "plasma exposure",
    "serum": "serum exposure",
    "blood": "blood exposure",
    "whole blood": "blood exposure",
    "brain": "brain exposure",
    "brain tissue": "brain exposure",
    "brain_tissue": "brain exposure",
    "cerebrospinal fluid": "CSF exposure",
    "csf": "CSF exposure",
    "urine": "urinary excretion",
    "hair": "hair exposure monitoring",
    "wastewater": "wastewater exposure monitoring",
    "oral fluid": "oral-fluid exposure monitoring",
    "liver": "liver exposure",
    "tissue": "tissue exposure",
}


def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return re.sub(r"\s+", " ", text)


def meaningful(value: object) -> bool:
    return clean_text(value).casefold() not in MISSING_VALUES


def first_meaningful(row: dict, fields: tuple[str, ...]) -> str:
    for field in fields:
        value = clean_text(row.get(field, ""))
        if meaningful(value):
            return value
    return ""


def ascii_fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", clean_text(value))
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def label_key(value: object) -> str:
    text = ascii_fold(value).casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def chemical_core_key(value: object) -> str:
    key = label_key(value)
    key = re.sub(r"^(?:r|s|rs|racemic) ", "", key)
    key = re.sub(r"^(?:r|s) ketamine$", "ketamine", key)
    key = key.replace("esketamine", "ketamine")
    key = key.replace("s ketamine", "ketamine")
    key = key.replace("r ketamine", "ketamine")
    return key


def title_label(value: object) -> str:
    text = clean_text(value).replace("_", " ")
    if not text:
        return ""
    if text.isupper() or re.search(r"\b(?:CYP|MAO|UGT|COMT|ALDH|DMT|MDMA|LSD|CSF|BBB)\b", text):
        return text
    return text[:1].upper() + text[1:]


def canonical_route_label(value: object) -> str:
    key = label_key(value)
    if not key:
        return ""
    for route_key, label in ROUTE_LABELS.items():
        if label_key(route_key) in key:
            return label
    return title_label(value)


def exposure_label_for_matrix(matrix: str, analyte: str, compound: str) -> str:
    key = label_key(matrix)
    analyte_label = title_label(analyte) or title_label(compound)
    base = ""
    for matrix_key, label in MATRIX_LABELS.items():
        if label_key(matrix_key) == key or label_key(matrix_key) in key:
            base = label
            break
    if not base:
        base = "exposure"
    if base.startswith(("urinary", "hair", "wastewater", "oral-fluid")):
        return title_label(base)
    if analyte_label:
        return f"{analyte_label} {base}"
    return title_label(base)


def distinct_analyte(compound: str, analyte: str) -> bool:
    if not meaningful(compound) or not meaningful(analyte):
        return False
    compound_key = chemical_core_key(compound)
    analyte_key = chemical_core_key(analyte)
    if not compound_key or not analyte_key:
        return False
    if compound_key == analyte_key:
        return False
    return analyte_key not in {"parent", "parent compound", "parent drug", "dose", "exposure index"}


def compact_context(row: dict, *extra: object) -> str:
    fields = (
        "pk_relationship_type",
        "pk_graph_object_label",
        "pk_or_exposure_parameter",
        "analyte_type",
        "metabolite_or_analyte",
        "metabolic_or_transport_target",
        "metabolic_or_transport_pathway",
        "matrix",
        "matrix_or_sample",
        "matrix_or_sample_type",
        "route_of_administration",
        "comparator_or_reference",
        "co_exposure_or_modifier",
        "model_or_method",
        "finding_summary",
        "support",
        "effect_or_statistic",
        "exposure_response_or_pk_effect",
        "exposure_response_implication",
        "synthesis_interpretation",
    )
    return " ".join(ascii_fold(value) for value in (*extra, *(row.get(field, "") for field in fields)))


def effect_object_label(row: dict, target: str, parameter: str, context: str) -> str:
    target_label = title_label(target)
    if "occupancy" in context.casefold():
        if target_label:
            return f"{target_label} occupancy"
        return "Receptor occupancy"
    if target_label and re.search(r"\b(receptor|transport|channel|sert|dat|net|5[- ]?ht|nmda|ampa|gaba)\b", context, re.IGNORECASE):
        return f"{target_label} response"
    if re.search(r"\bblood pressure\b", context, re.IGNORECASE):
        return "Blood pressure response"
    if re.search(r"\bheart rate\b", context, re.IGNORECASE):
        return "Heart-rate response"
    if re.search(r"\bmadrs|depression|clinical response|symptom\b", context, re.IGNORECASE):
        return "Clinical response"
    if re.search(r"\bsubjective|drug effect|good drug effects?|questionnaire|rating\b", context, re.IGNORECASE):
        return "Subjective effects"
    if "dose" in label_key(parameter):
        return "Dose-response effect"
    return "Exposure-linked effect"


def explicit_pk_relationship(row: dict) -> dict | None:
    relationship_type = clean_text(row.get("pk_relationship_type", ""))
    object_kind = clean_text(row.get("pk_graph_object_kind", ""))
    object_label = clean_text(row.get("pk_graph_object_label", ""))
    if meaningful(relationship_type) and meaningful(object_kind) and meaningful(object_label):
        return {
            "pk_relationship_type": relationship_type,
            "pk_relationship_label": PK_RELATIONSHIP_LABELS.get(relationship_type, title_label(relationship_type)),
            "pk_graph_object_kind": object_kind,
            "pk_graph_object_label": object_label,
        }
    return None


def infer_pk_relationship(row: dict) -> dict:
    explicit = explicit_pk_relationship(row)
    if explicit:
        return explicit

    compound = first_meaningful(row, ("compound_or_analyte", "compound", "canonical_compound"))
    analyte = first_meaningful(row, ("metabolite_or_analyte", "compound_or_analyte"))
    target = first_meaningful(row, ("metabolic_or_transport_target", "target"))
    pathway = first_meaningful(row, ("metabolic_or_transport_pathway", "pathway_or_process", "pathway_or_readout"))
    parameter = first_meaningful(row, ("pk_or_exposure_parameter", "outcome_measure"))
    matrix = first_meaningful(row, ("matrix", "matrix_or_sample", "matrix_or_sample_type"))
    route = first_meaningful(row, ("route_of_administration", "route", "dose_route_or_formulation"))
    modifier = first_meaningful(row, ("co_exposure_or_modifier", "comparator_or_reference", "interaction_or_potentiation_context"))
    context = compact_context(row, compound, analyte, target, pathway, parameter, matrix, route, modifier)

    target_is_metabolic = bool(METABOLIC_TARGET_RE.search(target)) and not bool(NON_PK_TARGET_TRANSPORTER_RE.search(target))
    if target_is_metabolic:
        relationship_type = "exposure_altered_by" if INTERACTION_RE.search(context) else "metabolized_by"
        return {
            "pk_relationship_type": relationship_type,
            "pk_relationship_label": PK_RELATIONSHIP_LABELS[relationship_type],
            "pk_graph_object_kind": "enzyme_or_transporter",
            "pk_graph_object_label": title_label(target),
        }

    if modifier:
        return {
            "pk_relationship_type": "exposure_altered_by",
            "pk_relationship_label": PK_RELATIONSHIP_LABELS["exposure_altered_by"],
            "pk_graph_object_kind": "modifier_or_interaction",
            "pk_graph_object_label": title_label(modifier),
        }

    if distinct_analyte(compound, analyte) and (METABOLITE_CONTEXT_RE.search(context) or label_key(row.get("primary_graph_anchor_kind", "")) == "compound"):
        return {
            "pk_relationship_type": "metabolized_to",
            "pk_relationship_label": PK_RELATIONSHIP_LABELS["metabolized_to"],
            "pk_graph_object_kind": "metabolite_or_analyte",
            "pk_graph_object_label": title_label(analyte),
        }

    if target and EXPOSURE_RESPONSE_RE.search(context):
        return {
            "pk_relationship_type": "exposure_linked_to_effect",
            "pk_relationship_label": PK_RELATIONSHIP_LABELS["exposure_linked_to_effect"],
            "pk_graph_object_kind": "effect_or_response",
            "pk_graph_object_label": effect_object_label(row, target, parameter, context),
        }

    if pathway and METABOLISM_PATHWAY_RE.search(pathway):
        relationship_type = "eliminated_by" if ELIMINATION_RE.search(pathway) else "metabolized_via"
        return {
            "pk_relationship_type": relationship_type,
            "pk_relationship_label": PK_RELATIONSHIP_LABELS[relationship_type],
            "pk_graph_object_kind": "metabolic_or_transport_pathway",
            "pk_graph_object_label": title_label(pathway),
        }

    if EXPOSURE_RESPONSE_RE.search(context):
        return {
            "pk_relationship_type": "exposure_linked_to_effect",
            "pk_relationship_label": PK_RELATIONSHIP_LABELS["exposure_linked_to_effect"],
            "pk_graph_object_kind": "effect_or_response",
            "pk_graph_object_label": effect_object_label(row, target, parameter, context),
        }

    if ELIMINATION_RE.search(context):
        label = "Urinary excretion" if "urine" in label_key(matrix) or "urinary" in label_key(context) else "Elimination profile"
        return {
            "pk_relationship_type": "eliminated_by",
            "pk_relationship_label": PK_RELATIONSHIP_LABELS["eliminated_by"],
            "pk_graph_object_kind": "excretion_or_elimination",
            "pk_graph_object_label": label,
        }

    if DETECTION_RE.search(context):
        return {
            "pk_relationship_type": "detected_or_monitored_in",
            "pk_relationship_label": PK_RELATIONSHIP_LABELS["detected_or_monitored_in"],
            "pk_graph_object_kind": "detection_or_monitoring",
            "pk_graph_object_label": exposure_label_for_matrix(matrix, analyte, compound),
        }

    if DISTRIBUTION_RE.search(context):
        return {
            "pk_relationship_type": "distributed_to",
            "pk_relationship_label": PK_RELATIONSHIP_LABELS["distributed_to"],
            "pk_graph_object_kind": "compartment_or_tissue",
            "pk_graph_object_label": exposure_label_for_matrix(matrix, analyte, compound),
        }

    if BIOAVAILABILITY_ROUTE_RE.search(context) and route:
        route_label = canonical_route_label(route)
        if "bioavailability" in label_key(context) and route_label == "Oral administration":
            route_label = "Oral bioavailability"
        return {
            "pk_relationship_type": "route_or_formulation_changes_exposure",
            "pk_relationship_label": PK_RELATIONSHIP_LABELS["route_or_formulation_changes_exposure"],
            "pk_graph_object_kind": "route_or_formulation",
            "pk_graph_object_label": route_label,
        }

    return {
        "pk_relationship_type": "exposure_characterized",
        "pk_relationship_label": PK_RELATIONSHIP_LABELS["exposure_characterized"],
        "pk_graph_object_kind": "parent_or_analyte_exposure",
        "pk_graph_object_label": exposure_label_for_matrix(matrix, analyte, compound),
    }


def add_pk_relationship_fields(row: dict) -> dict:
    out = dict(row)
    if clean_text(out.get("domain", out.get("domain_route", ""))) != "pharmacokinetics_exposure":
        return out
    inferred = infer_pk_relationship(out)
    for key, value in inferred.items():
        if value and not meaningful(out.get(key, "")):
            out[key] = value
    return out
