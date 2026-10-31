"""Resolve fully described single targets using the existing registry identities.

This is a fallback for target fields, not a keyword search through findings.
Every non-descriptive token must be accounted for by aliases of the same target.
Ligands, ancestor families, unknown subtypes and engineered constructs therefore
cannot win merely because they occur within a longer target name.
"""

from __future__ import annotations

import re
from functools import lru_cache


_DESCRIPTORS = re.compile(
    r"\b(?:human|rat|mouse|murine|bovine|porcine|rabbit|guinea pig|"
    r"recombinant|cloned|native|wild type|protein|plasma membrane|cell surface)\b"
)
_SPECIES_PREFIXES = {
    "human": "h", "rat": "r", "mouse": "m", "bovine": "b", "porcine": "p",
}


def _target_phrase_key(text: str) -> str:
    """Grammatical equivalences; never erase a subtype, mutation or assay result."""
    text = re.sub(r"\b(receptor|channel|transporter)s\b", r"\1", text)
    text = re.sub(r"\breceptor s\b", "receptor", text)
    text = re.sub(r"\bbinding sites?\b", "binding site", text)
    text = re.sub(r"\b(?:voltage dependent|voltage operated|voltage sensitive)\b",
                  "voltage gated", text)
    text = re.sub(r"\bna(?= channel\b)", "sodium", text)
    text = re.sub(r"\bplasmalemmal\b", "plasma membrane", text)
    text = re.sub(r"\b(?:glutamate|glutamatergic) nmda receptor\b", "nmda glutamate receptor", text)
    return text


@lru_cache(maxsize=8)
def _alias_patterns(signature: tuple[tuple[str, str], ...]) -> tuple:
    aliases: dict[str, set[str]] = {}
    for label, key in signature:
        aliases.setdefault(label, set()).add(_target_phrase_key(key))
    return tuple(
        (label, keys, re.compile(r"\b(?:" + "|".join(
            re.escape(k) for k in sorted(keys, key=lambda k: (-len(k), k))
        ) + r")\b"))
        for label, keys in aliases.items()
    )


def single_registered_target(
    text_key: str,
    registry: dict[tuple[str, str], dict],
    allowed_statuses: set[str],
) -> dict | None:
    """Return one registry entry only if its aliases cover the complete field.

    ``text_key`` uses the caller's normal label normalization. The grammar adds
    word-order equivalence, not biological aliases. Original field text remains
    attached to the finding, including species and receptor variants.
    """
    text = _target_phrase_key(text_key)
    text = re.sub(
        r"\b(d[1-5](?: \d+)?) (?:dopamine|dopaminergic) receptors?\b",
        r"dopamine \1 receptor", text,
    )
    text = re.sub(r"\b(?:glutamate|glutamatergic) nmda receptors?\b",
                  "nmda glutamate receptor", text)
    signature = []
    items: dict[str, dict] = {}
    for (entity_type, key), item in registry.items():
        if entity_type != "mechanistic_entity" or item.get("status") not in allowed_statuses:
            continue
        # The short form D3 alone is ambiguous; complete registry aliases such
        # as "D3 receptor" are eligible. Avoid incidental one/two-letter hits.
        if len(key) < 3:
            continue
        label = item["label"]
        signature.append((label, key))
        items[label] = item

    matches = []
    for label, keys, pattern in _alias_patterns(tuple(signature)):
        remainder, n = pattern.subn(" ", text)
        if not n:
            continue
        # Species-prefixed transporter abbreviations are permitted only when
        # that species and the complete transporter name are also declared.
        if any(re.search(rf"\b{re.escape(k)}\b", text) for k in keys if "transporter" in k):
            for species, prefix in _SPECIES_PREFIXES.items():
                if re.search(rf"\b{species}\b", text):
                    for key in keys & {"dat", "sert", "net", "vmat1", "vmat2"}:
                        remainder = re.sub(rf"\b{prefix}{key}\b", " ", remainder)
        remainder = _DESCRIPTORS.sub(" ", remainder)
        # A binding site/channel description belongs to the named receptor;
        # no unspecified PCP site, subtype, subunit or mutant is inferred.
        if "receptor" in label.lower() or "adrenoceptor" in label.lower():
            remainder = re.sub(r"\bbinding site\b", " ", remainder)
            if re.search(r"nicotinic|nmda|ampa|5-ht3|gaba-a", label, re.I):
                remainder = re.sub(r"\b(?:associated |activated )?(?:ion|ionic|cation) channel\b", " ", remainder)
                remainder = re.sub(r"\bchannel\b", " ", remainder)
                remainder = re.sub(r"\bof the\b", " ", remainder)
        # Unspecified subtype qualifiers are safe only for an explicit family.
        # They must not turn a named unknown subtype into a familiar subtype.
        if items[label].get("status") == "broad_target_family":
            remainder = re.sub(r"\b(?:receptor )?subtype (?:not specified|not reported|unspecified)\b", " ", remainder)
        # A named target with a simple pharmacological action still identifies
        # that same target. The saved action and primary-assay gate remain intact.
        if re.fullmatch(r"\s*(?:agonism|antagonism)\s*", remainder):
            remainder = ""
        remainder = re.sub(r"\b(?:and|or)\b", " ", remainder)
        if not remainder.strip():
            matches.append(items[label])
    return matches[0] if len(matches) == 1 else None



def target_subject_detail_reason(row: dict) -> str:
    """Do not assign an explicitly modified molecule/mixture to its parent.

    Read only the measured subject, never the title or comparator. These
    qualifiers require exact subject resolution; they are not drug synonyms.
    """
    if row.get("source_item_type") != "primary_item":
        return ""
    original = str(row.get("compound_original") or row.get("compound") or "")
    canonical = str(row.get("compound") or "")
    qualifier = r"deuter(?:ated|o)|\bd[2-9]-|\b(?:amino|nitro)[- ](?:pcp|phencyclidine)\b"
    if (re.search(qualifier, original, re.I)
            and not re.search(qualifier, canonical, re.I)):
        return "target_subject_requires_exact_identity"
    if (re.search(r"\bmixture\b", original, re.I)
            and not re.search(r"\bmixture\b", canonical, re.I)
            and canonical in {"R-ketamine", "S-ketamine"}
            and row.get("graph_subject_kind") == "atomic_compound"):
        return "target_subject_requires_exact_identity"
    return ""

def predicted_target_detail_reason(row: dict) -> str:
    """Explicit computational primary target evidence remains accessible in detail."""
    if row.get("source_item_type") != "primary_item":
        return ""
    # Structured categories describe this observation, unlike a paper title or
    # a mixed methods paragraph that may include both docking and wet assays.
    if any(str(row.get(k, "")).strip().lower() == "computational"
           for k in ("experimental_system_category", "study_design_category")):
        return "predicted_target_requires_experimental_validation"
    return ""


def unresolved_historical_pcp_site(text: str) -> bool:
    """A historically named PCP site is not itself a molecular identity.

    Saved studies distinguish PCP sites associated with several channels and
    carriers. Keep an explicit NMDA/nicotinic receptor on its normal path, but
    do not use a generic site name to infer either receptor.
    """
    return bool(re.search(r"\b(?:pcp|phencyclidine)(?: \(pcp\))? (?:binding |recognition )?(?:sites?|receptors?)\b", text, re.I)
                and not re.search(r"\bnmda\b|n methyl d aspartate|\bnicotinic\b", text, re.I))


def explicit_unresolved_target(row: dict, raw_label: str) -> bool:
    """Whether a saved primary assay can retain its literal unresolved target.

    This admits paper detail only. It does not validate the target's biological
    identity, infer direct binding, or turn an unidentified site into a named
    receptor. Review topics lack this primary assay contract.
    """
    if row.get("source_item_type") != "primary_item" or row.get("source_type") != "primary":
        return False
    if str(row.get("target", "")).strip() != raw_label.strip():
        return False
    missing = {"", "none", "null", "n/a", "na", "unknown", "not reported", "not specified",
               "not applicable", "uncertain", "unspecified"}
    def present(value: object) -> bool:
        return str(value or "").strip().lower().replace("_", " ") not in missing
    if not all(present(row.get(field)) for field in ("target", "target_type", "assay_type", "finding_summary")):
        return False
    # Preserve a measured but unidentified binding site; a bare statement that
    # the target is unknown is not itself an endpoint.
    return not re.fullmatch(
        r"(?:(?:molecular |biological |specific )?targets?|mechanisms?(?: of action)?)"
        r"(?: (?:is |was )?(?:unknown|unidentified|unspecified|not (?:identified|reported|specified)))?",
        raw_label.strip(), re.I,
    )


def recovered_target_detail_reason(row: dict) -> str:
    """Admission checks for newly recovered canonical primary target phrases.

    Finding a receptor's name does not establish that the psychedelic was
    assayed at it. Use the saved assay field, never a paper title or background.
    """
    if row.get("source_item_type") != "primary_item":
        return ""
    if reason := target_subject_detail_reason(row) or predicted_target_detail_reason(row):
        return reason
    subject = str(row.get("compound_original") or row.get("graph_subject_label") or row.get("compound") or "")
    if (re.search(r"\b(?:compound|analogue|analog|derivative)\s*#?\s*\d+[a-z]?\b", subject, re.I)
            and re.search(r"\b(?:modif\w*|derivative|analogue|analog)\b", subject, re.I)):
        return "target_subject_requires_exact_identity"
    assay = str(row.get("assay_type") or "")
    # Receptor abundance/availability is a readout of treatment, even when a
    # radioligand assay measures it. It does not establish drug-target binding.
    if re.search(r"(?:receptor|binding[- ]site).{0,40}(?:availability|density|abundance)",
                 str(row.get("target_type") or ""), re.I):
        return "target_mechanism_without_direct_assay"
    system = str(row.get("experimental_system_category") or row.get("system") or "")
    if re.search(r"computational|docking|in silico|molecular dynamics", assay + " " + system, re.I):
        return "predicted_target_requires_experimental_validation"
    if re.search(r"knockout|knockdown|pretreatment|blockade.{0,100}followed by|compared qualitatively", assay, re.I):
        return "target_mechanism_without_direct_assay"
    if (re.search(r"\bfunctional assay\b", assay, re.I)
            and str(row.get("experimental_system_category", "")).lower() == "in_vitro"):
        return ""
    if not re.search(
        r"binding|radioligand|displacement|voltage[- ]?clamp|patch[- ]?clamp|"
        r"uptake|influx|efflux|reverse transport|gtp|g protein|g-protein|"
        r"camp|cyclic amp|cyclic adenosine|ca2\+ mobilization|calcium (?:flux|mobilization)|"
        r"functional activit|receptor activat|arrestin|enzyme (?:activity|inhibition)|"
        r"calcium.*(?:release|current)|ca2\+.*(?:release|current)|"
        r"ip1 accumulation|inositol phosphate|phosphoinositide hydrolysis|"
        r"bret|trupath|thermal shift|cetsa|surface plasmon|isothermal titration|"
        r"single[- ]channel (?:current|lifetime|conductance)|end[- ]?plate current|"
        r"(?:22na|sodium|cation|ion)\+? (?:in)?flux",
        assay, re.I,
    ):
        return "target_mechanism_without_direct_assay"
    return ""
