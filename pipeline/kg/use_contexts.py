#!/usr/bin/env python3
"""Controlled real-world use contexts and their aliases.

These definitions support a second graph projection: substances explicitly
reported as part of a real-world use context point to that context.  They do
not expand the compound scope; projected substances must still pass the main
psychedelic-graph compound registry and scope checks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class UseContextDefinition:
    label: str
    aliases: tuple[str, ...] = ()
    parent: str = ""


USE_CONTEXT_DEFINITIONS = {
    "Sexualized drug use": UseContextDefinition(
        label="Sexualized drug use",
        aliases=("sexualised drug use", "SDU", "substance-linked sex"),
    ),
    "Chemsex": UseContextDefinition(
        label="Chemsex",
        aliases=("chem sex",),
        parent="Sexualized drug use",
    ),
}


CHEMSEX_RE = re.compile(r"\bchem\s*sex\b", re.IGNORECASE)
SEXUALIZED_DRUG_USE_RE = re.compile(
    r"\b(?:sexuali[sz]ed drug use|substance[- ]linked sex|drug use (?:during|in combination with) sex|"
    r"drugs?(?:\s+\w+){0,3}\s+(?:during|in combination with) sex|drug[- ]facilitated sex)\b",
    re.IGNORECASE,
)


def use_context_definition(label: object) -> UseContextDefinition | None:
    key = str(label or "").strip().casefold()
    for definition in USE_CONTEXT_DEFINITIONS.values():
        if key == definition.label.casefold() or key in {alias.casefold() for alias in definition.aliases}:
            return definition
    return None


def use_context_label_from_text(text: object) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    if CHEMSEX_RE.search(value):
        return "Chemsex"
    if SEXUALIZED_DRUG_USE_RE.search(value):
        return "Sexualized drug use"
    return ""
