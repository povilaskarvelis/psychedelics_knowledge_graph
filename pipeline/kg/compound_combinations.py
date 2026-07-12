#!/usr/bin/env python3
"""Controlled names and aliases for multi-compound psychedelic exposures.

The common ``flipping`` vocabulary is open-ended slang, so this module keeps a
curated set of chemically unambiguous names rather than treating every web list
as ontology.  Well-established names may be inferred from a complete component
set.  Less-established names are recognized only when the source uses the name
explicitly.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable


def component_key(value: object) -> str:
    text = unicodedata.normalize("NFKD", "" if value is None else str(value))
    text = text.encode("ascii", "ignore").decode("ascii").casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


NAMED_COMBINATION_DEFINITIONS = (
    {
        "canonical_alias": "pharmahuasca",
        "component_sets": (("DMT", "Harmine"), ("DMT", "Harmaline")),
        "aliases": ("pharmahuasca",),
        "pattern": re.compile(r"\bpharmahuasca\b", re.I),
        "infer_from_components": True,
    },
    {
        "canonical_alias": "candyflipping",
        "component_sets": (("LSD", "MDMA"),),
        "aliases": ("candyflip", "candy flip", "candyflipping", "candy flipping"),
        "pattern": re.compile(r"\bcandy[-\s]?flip(?:ping|ped)?\b", re.I),
        "infer_from_components": True,
    },
    {
        "canonical_alias": "hippy flipping",
        "component_sets": (("Psilocybin", "MDMA"),),
        "aliases": (
            "hippy flip",
            "hippy flipping",
            "hippyflip",
            "hippyflipping",
            "hippie flip",
            "hippie flipping",
            "hippieflip",
            "hippieflipping",
        ),
        "pattern": re.compile(r"\b(?:hippy|hippie)[-\s]?flip(?:ping|ped)?\b", re.I),
        "infer_from_components": True,
    },
    {
        "canonical_alias": "kitty flipping",
        "component_sets": (("Ketamine", "MDMA"),),
        "aliases": ("kitty flip", "kitty flipping", "kittyflip", "kittyflipping"),
        "pattern": re.compile(r"\bkitty[-\s]?flip(?:ping|ped)?\b", re.I),
        "infer_from_components": True,
    },
    {
        "canonical_alias": "nexus flipping",
        "component_sets": (("2C-B", "MDMA"),),
        "aliases": ("nexus flip", "nexus flipping", "nexusflip", "nexusflipping"),
        "pattern": re.compile(r"\bnexus[-\s]?flip(?:ping|ped)?\b", re.I),
        "infer_from_components": True,
    },
    {
        "canonical_alias": "Jedi flipping",
        "component_sets": (("LSD", "Psilocybin", "MDMA"),),
        "aliases": (
            "Jedi flip",
            "Jedi flipping",
            "Jediflip",
            "Jediflipping",
            "twilight flip",
            "twilight flipping",
        ),
        "pattern": re.compile(r"\b(?:jedi|twilight)[-\s]?flip(?:ping|ped)?\b", re.I),
        "infer_from_components": True,
    },
    # These names are chemically unambiguous but less consistently used in the
    # literature.  Preserve them when explicit; do not add them merely because
    # the component set happens to occur in a controlled study.
    {
        "canonical_alias": "soul bombing",
        "component_sets": (("LSD", "Psilocybin"),),
        "aliases": (
            "soul bomb",
            "soul bombing",
            "soulbomb",
            "soulbombing",
            "wizard flip",
            "wizard flipping",
        ),
        "pattern": re.compile(
            r"\bsoul[-\s]?bomb(?:ing|ed)?\b|\bwizard[-\s]?flip(?:ping|ped)?\b",
            re.I,
        ),
        "infer_from_components": False,
    },
    {
        "canonical_alias": "Ali flipping",
        "component_sets": (("LSD", "MDMA", "2C-B"),),
        "aliases": ("Ali flip", "Ali flipping", "Aliflip", "Aliflipping"),
        "pattern": re.compile(r"\bali[-\s]?flip(?:ping|ped)?\b", re.I),
        "infer_from_components": False,
    },
    {
        "canonical_alias": "love flipping",
        "component_sets": (("Mescaline", "MDMA"),),
        "aliases": ("love flip", "love flipping", "loveflip", "loveflipping", "love trip"),
        "pattern": re.compile(r"\blove[-\s]?(?:flip(?:ping|ped)?|trip)\b", re.I),
        "infer_from_components": False,
    },
    {
        "canonical_alias": "Selma flipping",
        "component_sets": (("Mescaline", "MDMA", "2C-B"),),
        "aliases": ("Selma flip", "Selma flipping", "Selmaflip", "Selmaflipping"),
        "pattern": re.compile(r"\bselma[-\s]?flip(?:ping|ped)?\b", re.I),
        "infer_from_components": False,
    },
)


def definition_component_keys(definition: dict) -> tuple[frozenset[str], ...]:
    return tuple(
        frozenset(component_key(label) for label in component_set)
        for component_set in definition["component_sets"]
    )


def named_combination_from_text(value: object) -> dict | None:
    text = "" if value is None else str(value)
    return next(
        (definition for definition in NAMED_COMBINATION_DEFINITIONS if definition["pattern"].search(text)),
        None,
    )


def is_named_combination_text(value: object) -> bool:
    return named_combination_from_text(value) is not None


def named_combination_for_components(
    labels: Iterable[object],
    *,
    infer_only: bool = False,
) -> dict | None:
    keys = frozenset(component_key(label) for label in labels if component_key(label))
    if not keys:
        return None
    for definition in NAMED_COMBINATION_DEFINITIONS:
        if infer_only and not definition["infer_from_components"]:
            continue
        if keys in definition_component_keys(definition):
            return definition
    return None


def canonical_components(definition: dict, keys: Iterable[object] | None = None) -> tuple[str, ...]:
    if keys is None:
        return tuple(definition["component_sets"][0])
    requested = frozenset(component_key(value) for value in keys if component_key(value))
    for component_set in definition["component_sets"]:
        if frozenset(component_key(value) for value in component_set) == requested:
            return tuple(component_set)
    return tuple(definition["component_sets"][0])


def aliases_for_components(labels: Iterable[object]) -> list[str]:
    definition = named_combination_for_components(labels)
    return list(definition["aliases"]) if definition else []

