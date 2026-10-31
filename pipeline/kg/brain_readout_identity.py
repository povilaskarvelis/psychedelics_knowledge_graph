"""Recover explicit primary neural observations after ordinary matching fails.

Measurement identity and anatomical identity are separate: a saved neural assay
can remain useful without a registered region. Anatomical recovery, in contrast,
requires exact existing aliases and an existing child/ancestor relationship.
"""
from __future__ import annotations

import re
from typing import Callable

from pipeline.extract.assay_family import normalize_assay_family

MISSING = {"", "none", "null", "not_reported", "not reported", "not_applicable", "not applicable", "unknown", "n/a"}
NEURAL_ASSAY_FAMILIES = frozenset({
    "EEG", "Electrophysiology", "fMRI", "PET", "MRI", "Calcium imaging",
    "LFP", "MEG", "Fiber photometry", "MRS", "SPECT",
})
EXPLICIT_NEURAL_METHOD_RE = re.compile(
    r"\b(?:TMS|transcranial magnetic stimulation|polysomnograph\w*|"
    r"(?:multi[- ]?electrode|microelectrode) array|MEA|"
    r"multi[- ]?electrode neural recording|(?:intra|extra)cellular (?:voltage )?recordings?|"
    r"(?:auditory|visual|motor|cortical|sensory)[- ]evoked potentials?|"
    r"evoked potential recording|auditory brainstem response|fNIRS|"
    r"voltage[- ]sensitive dye.*imaging|intracranial electrograms?)\b", re.I,
)


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _present(value: object) -> bool:
    return _text(value).casefold() not in MISSING


def explicit_primary_observation(row: dict) -> bool:
    return (_text(row.get("source_item_type")) == "primary_item"
            and all(_present(row.get(k)) for k in ("readout", "assay_type", "finding_summary")))


def has_explicit_neural_assay(row: dict) -> bool:
    """Use the saved assay, never a modality mentioned in result/background prose.

    The family is derived from the assay text alone. Mixed
    assays remain one literal detail finding. Manipulation-only optogenetics,
    behavioral tasks, questionnaires and biochemical assays do not establish a
    neural recording. No particular measurement family is inferred here.
    """
    if not explicit_primary_observation(row):
        return False
    method = _text(row.get("assay_type"))
    if re.search(r"\bnot (?:performed|recorded|conducted|measured|acquired)\b|"
                 r"\b(?:without|no)\s+(?:EEG|fMRI|PET|MRI|MEG|neural recording)\b", method, re.I):
        return False
    return (normalize_assay_family("", method) in NEURAL_ASSAY_FAMILIES
            or bool(EXPLICIT_NEURAL_METHOD_RE.search(method)))


def recovered_anatomy_detail_reason(row: dict, overview_subject_kind: str) -> str:
    """A resolved location does not establish a single-drug or observed effect."""
    if any(_text(row.get(k)).casefold() == "computational"
           for k in ("system", "experimental_system_category")):
        return "computed_neural_anatomy_detail_only"
    exposure = next((_text(row.get(k)) for k in (
        "compound_or_exposure", "compound_original", "graph_subject_label",
    ) if _present(row.get(k))), "")
    if (overview_subject_kind == "atomic_compound"
            and re.search(r"\b(?:co[- ]exposure|co[- ]administration|combined|together|mixture)\b", exposure, re.I)
            and re.search(r"\b(?:and|plus)\b|\+", exposure, re.I)):
        return "joint_exposure_not_single_drug_neural_result"
    return ""


def nested_registered_brain_region(
    raw_label: str, vocabulary: dict, key: Callable[[object], str],
) -> dict | None:
    """Resolve a complete 'child of parent' phrase using declared vocabulary.

    Unknown subdivisions, wrong parents and peer lists cannot be reduced to a
    familiar substring. Inline abbreviations must independently resolve to the
    same existing node as their spelled-out form.
    """
    def exact(text: str) -> dict | None:
        return vocabulary.get(("brain_region", key(text)))

    def with_equivalent_abbreviation(text: str) -> dict | None:
        item = exact(text)
        if item:
            return item
        match = re.fullmatch(r"([^()]*)\s*\(([^()]+)\)([^()]*)", text)
        if not match:
            return None
        before, short, after = (x.strip() for x in match.groups())
        item = exact(f"{before} {after}")
        if not item:
            return None
        # 'Prelimbic (PL) cortex' -> both 'Prelimbic cortex' and 'PL cortex'.
        alternatives = [short, f"{short} {after}"]
        for alias in alternatives:
            other = exact(alias)
            if other and other["label"] == item["label"]:
                return item
        return None

    match = re.fullmatch(r"(.+?)\s+(?:of|within|in)\s+(?:the\s+)?(.+)", _text(raw_label), re.I)
    if not match:
        return None
    child_text, parent_text = match.groups()
    child_text = re.sub(r"^adult\s+", "", child_text, flags=re.I)
    child = with_equivalent_abbreviation(child_text)
    parent = with_equivalent_abbreviation(parent_text)
    if not child or not parent or child["label"] == parent["label"]:
        return None
    seen = {child["label"]}
    node = child
    while node.get("parent") and node["parent"] not in seen:
        ancestor = node["parent"]
        if ancestor == parent["label"]:
            return child
        seen.add(ancestor)
        node = exact(ancestor) or {}
    return None
