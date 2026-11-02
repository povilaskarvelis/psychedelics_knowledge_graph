"""Whether one statement that names several drugs can be attributed to each of them.

A review sentence such as "psilocybin, LSD and ketamine have been studied for
chronic pain" links each drug to the outcome. A sentence that sets the drugs
against each other ("MDMA for PTSD and psilocybin for depression", "esketamine
was more effective than ketamine") or gives each drug its own clause
("ketamine may produce dissociation, ibogaine is associated with QT
prolongation") gives each drug its own result, so copying it to every drug
would misattribute it. The drugs must therefore be named together, as one
list, wherever the statement names any of them. Both inputs are compared as
lower-case alphanumeric keys (see ``label_key`` in the normalizer).
"""

from __future__ import annotations

import re

CONTRAST_RE = re.compile(
    r"\b(?:whereas|while|unlike|in contrast|by contrast|but not|rather than|than|versus|vs|"
    r"compared with|compared to|comparison|respectively|however|differ\w*|instead|alternatively|although)\b"
)
# "Psilocybin is converted to psilocin, which acts at 5-HT2A": the effect
# belongs to the metabolite, not to every named drug.
CONVERSION_RE = re.compile(r"\b(?:convert\w*|metaboli[sz]\w*|metabolites?|prodrugs?|precursors?|derived)\b")
# Words that may stand between two drugs of one list ("psilocybin, LSD and
# ketamine", "MDMA-assisted therapy and psilocybin", "ketamine or esketamine").
LIST_WORDS = {
    "and", "or", "as", "well", "plus", "both", "either", "also", "including", "such", "e", "g", "i",
    "the", "its", "their", "intravenous", "intranasal", "oral", "racemic", "assisted", "therapy",
    "psychotherapy", "treatment", "treatments", "s", "r", "rs",
}
MAX_LIST_GAP_WORDS = 4


def drug_mention_clusters(statement_key: str, drug_keys: list[list[str]]) -> list[set[int]]:
    """Groups of drugs named next to each other, as indexes into ``drug_keys``.

    Where names overlap ("s ketamine" contains "ketamine") the longer name wins.
    """
    mentions = sorted(
        ((match.start(), match.end(), index)
         for index, keys in enumerate(drug_keys) for key in keys if key
         for match in re.finditer(rf"\b{re.escape(key)}\b", statement_key)),
        key=lambda mention: (mention[0], mention[0] - mention[1]),
    )
    clusters: list[set[int]] = []
    previous_end = None
    for start, end, index in mentions:
        if previous_end is not None and start < previous_end:
            continue
        gap = statement_key[previous_end:start].split() if previous_end is not None else None
        if gap is not None and len(gap) <= MAX_LIST_GAP_WORDS and set(gap) <= LIST_WORDS:
            clusters[-1].add(index)
        else:
            clusters.append({index})
        previous_end = end
    return clusters


def statement_contrasts_drugs(statement_key: str, drug_keys: list[list[str]], statement: str = "") -> bool:
    """True when the statement does not state one relationship for every named drug.

    ``drug_keys`` holds, for each drug, the name keys that identify it. The
    original ``statement`` is used for pairings written with a slash
    ("MDMA/PTSD, LSD/end-of-life anxiety"). A statement that names none of the
    drugs does not contrast them.
    """
    if CONTRAST_RE.search(statement_key) or CONVERSION_RE.search(statement_key):
        return True
    slashed = re.sub(r"[^a-z0-9/]+", " ", statement.casefold())
    all_keys = "|".join(re.escape(key) for keys in drug_keys for key in keys if key)
    if all_keys and sum(
        any(re.search(rf"\b{re.escape(key)} ?/ ?(?!(?:{all_keys})\b)[a-z]", slashed) for key in keys if key)
        for keys in drug_keys
    ) >= 2:
        return True
    with_own_purpose = 0
    for keys in drug_keys:
        if any(
            re.search(rf"\b{re.escape(key)}\b(?: assisted)?(?: \w+){{0,3}}? (?:for|in|on|to treat)\b", statement_key)
            for key in keys if key
        ):
            with_own_purpose += 1
    if with_own_purpose >= 2:
        return True
    every_drug = set(range(len(drug_keys)))
    return any(cluster != every_drug for cluster in drug_mention_clusters(statement_key, drug_keys))
