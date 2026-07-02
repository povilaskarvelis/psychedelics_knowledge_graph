#!/usr/bin/env python3
"""Normalize mechanistic assay labels into stable method-family buckets."""

from __future__ import annotations

import re

try:
    from pipeline.extract.io_utils import normalize
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from io_utils import normalize


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
    "Binding assays",
    "Receptor activity",
    "fMRI",
    "PET",
    "SPECT",
    "MRI",
    "MRS",
    "EEG",
    "MEG",
    "LFP",
    "Electrophysiology",
    "Calcium imaging",
    "Fiber photometry",
    "Behavioral assays",
    "Protein assays",
    "Proteomics",
    "Neurochemical assays",
    "Gene expression assays",
    "Immunoassays",
    "Histology",
    "Computational modeling",
    "Uptake assays",
    "Signaling assays",
    "Enzyme assays",
    "Other methods",
)

ASSAY_FAMILY_ALIASES = {
    **{label.casefold(): label for label in ASSAY_FAMILY_ORDER},
    "binding / affinity": "Binding assays",
    "functional activity": "Receptor activity",
    "imaging / connectivity": "Other methods",
    "behavioral assay": "Behavioral assays",
    "protein expression / proteomics": "Protein assays",
    "neurochemical levels": "Neurochemical assays",
    "gene expression": "Gene expression assays",
    "immunoassay / histology": "Immunoassays",
    "computational / in silico": "Computational modeling",
    "transporter / uptake": "Uptake assays",
    "signaling / phosphorylation": "Signaling assays",
    "enzyme / metabolism": "Enzyme assays",
    "other / mixed method": "Other methods",
}


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

    raw_family = normalize(assay_family).casefold()
    raw_type = normalize(assay_type).casefold()
    if raw_family in EMPTY_ASSAY_VALUES and raw_type in EMPTY_ASSAY_VALUES:
        return ""
    if raw_type in EMPTY_ASSAY_VALUES and raw_family in ASSAY_FAMILY_ALIASES:
        return ASSAY_FAMILY_ALIASES[raw_family]

    text = assay_text(assay_family, assay_type)
    if text in EMPTY_ASSAY_VALUES:
        return ""

    if has(
        r"\b("
        r"fmri|rs\s?fmri|phmri|functional mri|functional magnetic resonance|"
        r"asl|pcasl|arterial spin labell?ing"
        r")\b",
        text,
    ):
        return "fMRI"
    if has(r"\b(spect|single photon)\b", text):
        return "SPECT"
    if has(r"\b(pet|fdg|h2?15o|15o labeled|18f|radiotracer|positron emission)\b", text):
        return "PET"
    if has(r"\b(meg|magnetoencephalograph\w*)\b", text):
        return "MEG"
    if has(
        r"\b("
        r"eeg|erp|event related|event related potential|p300|p3a|p3b|mmn|mismatch negativity|"
        r"eloreta|sloreta|ecog|ieeg"
        r")\b",
        text,
    ):
        return "EEG"
    if has(r"\b(lfp|local field potential)\b", text):
        return "LFP"
    if has(
        r"\b("
        r"electrophysiolog\w*|patch clamp|voltage clamp|current clamp|field potential|field potentials|"
        r"f?epsp|ipsc|epsc|tevc|whole cell|extracellular recording|single unit|multiunit|mua|"
        r"synaptic transmission|synaptic plasticity|theta burst"
        r")\b",
        text,
    ):
        return "Electrophysiology"
    if has(r"\b(fiber photometry|fibre photometry|photometry)\b", text):
        return "Fiber photometry"
    if has(r"\b(calcium imaging|gcamp|two photon|2 photon|light sheet|functional ultrasound|fusi)\b", text):
        return "Calcium imaging"
    if has(
        r"\b(mrs|magnetic resonance spectroscopy|nmr spectroscopy|spectroscopy|7t mrs)\b",
        text,
    ):
        return "MRS"
    if has(r"\b(structural mri|dti|diffusion tensor|diffusion mri|mri|7t mri)\b", text):
        return "MRI"
    if has(
        r"\b(radioligand|binding|affinity|competition|displacement|scatchard|autoradiograph|autoradiography|"
        r"receptor density|receptor occupancy|binding potential|bpnd|bp nd)\b",
        text,
    ):
        return "Binding assays"
    if has(
        r"\b("
        r"behavior\w*|behaviour\w*|behavioral pharmacology|drug discrimination|head twitch|htr|"
        r"locomot|nocicept|antinocicept|forced swim|tail suspension|open field|prepulse"
        r")\b",
        text,
    ):
        return "Behavioral assays"
    if has(
        r"\b("
        r"microdialysis|hplc|uhplc|neurotransmitter|monoamine|dopamine|serotonin|"
        r"norepinephrine|noradrenaline|glutamate|gaba|release|metabolite|tissue content|"
        r"neurochemical assay|electrochemical|voltammetry|fscv"
        r")\b",
        text,
    ):
        return "Neurochemical assays"
    if has(r"\b(transport|transporter|uptake|reuptake|efflux|sert|dat|net)\b", text):
        return "Uptake assays"
    if has(
        r"\b(gene expression|mrna|qpcr|qrt pcr|rt qpcr|rna seq|rnaseq|transcript|microarray|"
        r"in situ hybridization|in situ hybridisation|genomic|immediate early gene|fos|arc|"
        r"rnascope|snrna seq|single nucleus rna)\b",
        text,
    ):
        return "Gene expression assays"
    if has(r"\b(phosphoproteomics?|proteomics?|proteomic|mass spectrometry)\b", text):
        return "Proteomics"
    if has(
        r"\b("
        r"western|immunoblot|protein expression|protein levels?|protein quantification|measurement of protein|"
        r"synaptic expression|brain derived neurotrophic factor|bdnf|psd"
        r")\b",
        text,
    ):
        return "Protein assays"
    if has(r"\b(histolog|staining|confocal|microscopy|golgi|stereology)\b", text):
        return "Histology"
    if has(
        r"\b("
        r"elisa|immunoassay|immunohistochemistry|immunocytochemistry|immunofluorescence|"
        r"cytometric bead array|flow cytometry|"
        r"cytokine production|cytokine assay|milliplex|chemokine"
        r")\b",
        text,
    ):
        return "Immunoassays"
    if has(
        r"\b(expression assay|expression measurement|expression in|expression analysis|detection of expression|gene expression|mrna|transcript)\b",
        text,
    ):
        return "Gene expression assays"
    if has(
        r"\b(phosphorylation|phospho|phosphoinositide|kinase|mtor|erk|akt|camp pathway|signal transduction|pathway activation)\b",
        text,
    ):
        return "Signaling assays"
    if has(r"\b(biochemical activity assay|proteasome|trypsin like|chymotrypsin like|ups activity)\b", text):
        return "Enzyme assays"
    if has(
        r"\b("
        r"functional|activity|activation|agonis\w*|antagonis\w*|pharmacological antagonism|pharmacological blockade|"
        r"pharmacological classification|g protein|beta arrestin|arrestin|bret|"
        r"camp|ip1|inositol|calcium|recruitment|potency|efficacy|modulation"
        r")\b",
        text,
    ):
        return "Receptor activity"
    if has(r"\b(computational|in silico|docking|modeling|modelling|prediction|admet|simulation|molecular dynamics)\b", text):
        return "Computational modeling"
    if has(r"\b(enzyme|enzymatic|metabolic|metabolism|esterase|pka|pk a|chemical assay|pka determination)\b", text):
        return "Enzyme assays"
    if raw_family in ASSAY_FAMILY_ALIASES:
        return ASSAY_FAMILY_ALIASES[raw_family]
    if raw_type in ASSAY_FAMILY_ALIASES:
        return ASSAY_FAMILY_ALIASES[raw_type]
    return "Other methods"
