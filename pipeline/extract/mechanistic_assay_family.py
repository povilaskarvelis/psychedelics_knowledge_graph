#!/usr/bin/env python3
"""Normalize mechanistic assay labels into stable method-family buckets."""

from __future__ import annotations

import re

try:
    from pipeline.extract.extraction_v1_utils import normalize
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from extraction_v1_utils import normalize


EMPTY_ASSAY_VALUES = {
    "",
    "none",
    "not applicable",
    "not_applicable",
    "not reported",
    "not_reported",
    "unknown",
    "uncertain",
}

ASSAY_FAMILY_ORDER = (
    "Binding / affinity",
    "Functional activity",
    "Behavioral assay",
    "Protein expression / proteomics",
    "Electrophysiology",
    "Neurochemical levels",
    "Gene expression",
    "Imaging / connectivity",
    "Immunoassay / histology",
    "Computational / in silico",
    "Transporter / uptake",
    "Signaling / phosphorylation",
    "Enzyme / metabolism",
    "Other / mixed method",
)


def assay_text(*values: object) -> str:
    parts = [normalize(value) for value in values if normalize(value)]
    text = " ".join(parts).casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[_/()+-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def normalize_mechanistic_assay_family(assay_family: object = "", assay_type: object = "") -> str:
    """Return a compact, stable assay-family label for mechanistic evidence.

    The raw extraction field is intentionally free text. This mapper keeps the
    UI and KG tables readable while preserving the original raw labels.
    """

    text = assay_text(assay_family, assay_type)
    if text in EMPTY_ASSAY_VALUES:
        return ""

    if has(r"\b(radioligand|binding|affinity|competition|displacement|scatchard|autoradiograph|receptor density)\b", text):
        return "Binding / affinity"
    if has(
        r"\b("
        r"electrophysiolog\w*|patch clamp|voltage clamp|current clamp|field potential|field potentials|"
        r"f?epsp|ipsc|epsc|tevc|whole cell|extracellular recording|eeg|ecog|synaptic transmission|"
        r"synaptic plasticity|theta burst"
        r")\b",
        text,
    ):
        return "Electrophysiology"
    if has(
        r"\b("
        r"behavior\w*|behaviour\w*|behavioral pharmacology|drug discrimination|head twitch|htr|"
        r"locomot|nocicept|antinocicept|forced swim|tail suspension|open field|prepulse"
        r")\b",
        text,
    ):
        return "Behavioral assay"
    if has(
        r"\b("
        r"functional connectivity|neuroimaging|imaging|fmri|phmri|pet|mri|connectivity|"
        r"calcium imaging|autoradiography|magnetic resonance spectroscopy|spectroscopy|mrs"
        r")\b",
        text,
    ):
        return "Imaging / connectivity"
    if has(
        r"\b("
        r"microdialysis|hplc|uhplc|neurotransmitter|monoamine|dopamine|serotonin|"
        r"norepinephrine|noradrenaline|glutamate|gaba|release|metabolite|tissue content|"
        r"neurochemical assay|electrochemical|voltammetry|fscv"
        r")\b",
        text,
    ):
        return "Neurochemical levels"
    if has(r"\b(transport|transporter|uptake|reuptake|efflux|sert|dat|net)\b", text):
        return "Transporter / uptake"
    if has(
        r"\b(gene expression|mrna|qpcr|qrt pcr|rt qpcr|rna seq|rnaseq|transcript|microarray|"
        r"in situ hybridization|genomic|immediate early gene|fos|arc)\b",
        text,
    ):
        return "Gene expression"
    if has(
        r"\b("
        r"western|immunoblot|protein expression|protein levels?|protein quantification|measurement of protein|"
        r"proteomics?|mass spectrometry|synaptic expression|brain derived neurotrophic factor|bdnf|psd"
        r")\b",
        text,
    ):
        return "Protein expression / proteomics"
    if has(
        r"\b("
        r"elisa|immunoassay|immunohistochemistry|immunofluorescence|histolog|staining|confocal|"
        r"light sheet|cytometric bead array|flow cytometry|cytokine production|cytokine assay|milliplex|chemokine"
        r")\b",
        text,
    ):
        return "Immunoassay / histology"
    if has(
        r"\b(expression assay|expression measurement|expression in|expression analysis|detection of expression|gene expression|mrna|transcript)\b",
        text,
    ):
        return "Gene expression"
    if has(
        r"\b(phosphorylation|phospho|phosphoinositide|kinase|mtor|erk|akt|camp pathway|signal transduction|pathway activation)\b",
        text,
    ):
        return "Signaling / phosphorylation"
    if has(
        r"\b("
        r"functional|activity|activation|agonis\w*|antagonis\w*|pharmacological antagonism|pharmacological blockade|"
        r"pharmacological classification|g protein|beta arrestin|arrestin|bret|"
        r"camp|ip1|inositol|calcium|recruitment|potency|efficacy|modulation"
        r")\b",
        text,
    ):
        return "Functional activity"
    if has(r"\b(computational|in silico|docking|modeling|modelling|prediction|admet|simulation|molecular dynamics)\b", text):
        return "Computational / in silico"
    if has(r"\b(enzyme|enzymatic|metabolic|metabolism|esterase|pka|pk a|chemical assay|pka determination)\b", text):
        return "Enzyme / metabolism"
    return "Other / mixed method"
