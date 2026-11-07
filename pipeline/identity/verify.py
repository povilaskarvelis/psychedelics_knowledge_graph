"""One rule for whether a text belongs to a paper.

A text is verified for a paper when an identifier taken from the source itself
(a DOI, PMID or PMCID in the document header or provider record) and the
source's title both agree with the paper. An identifier alone leaves the text
unconfirmed, and so does a title alone, unless the source is an article whose
parsed title agrees with the paper's at ``TITLE_ONLY_VERIFIED`` or above and
which gives no other DOI as its own. The same rule applies to full texts and to
provider records; ``evidence.py`` reads the evidence.

Computed verdicts:

| Verdict | Meaning |
|---|---|
| ``verified`` | identifier and title agree, or the title alone agrees closely (decision of 8 November) |
| ``version_of`` | the source names another DOI of the same work, registered in the work registry |
| ``unconfirmed`` | only one kind of evidence, or none |
| ``conflict`` | identifier and title do not point to the same work |
| ``wrong_kind`` | the source or the paper's DOI is not an article: a supplement, a correction notice, a component, a funder or issue DOI |

Reviewed decisions (``register.py``) override computed verdicts; this module
does not read them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from pipeline.identity.evidence import (
    NON_ARTICLE_DOCUMENT_KINDS,
    NOT_A_WORK_DOI_KINDS,
    PAPER_DOI_RUN_ON,
    VERSION_DOI_KINDS,
    doi_kind,
    is_not_a_title,
    same_doi,
    set_aside_reason,
    title_printed_in,
    title_state,
)
from pipeline.identity.works import DEDUPLICATED_RELATIONS
from pipeline.ingest.candidate_status import clean, normalize_doi


COMPUTED_VERDICTS = ("verified", "version_of", "unconfirmed", "conflict", "wrong_kind")
# Decision of 8 November 2026, from decision D4: an article whose parsed title
# agrees with the paper's at this similarity or above, and which gives no other
# DOI as its own, is the paper even when it prints no identifier. Most PDFs do
# not print their DOI on the pages the parser reads.
TITLE_ONLY_VERIFIED = 0.95
# The paper's title counts as printed only near the start of the text, where a
# document prints its own title rather than titles it cites.
OPENING_TITLE_CHARS = 5000


@dataclass(frozen=True)
class Paper:
    doi: str
    title: str
    pmid: str = ""
    pmcid: str = ""
    journal: str = ""


@dataclass(frozen=True)
class Source:
    """Identity evidence of one text or provider record.

    ``own_dois`` are DOIs the source gives as its own. ``printed_dois`` are
    the DOIs printed at its start. The paper's DOI printed there confirms the
    paper when the source gives no other DOI as its own; other printed DOIs
    never contradict the paper, because page one also prints cited and related
    DOIs, but they mark a page that may hold several items. ``opening_text`` is
    the start of the text, where the paper's title may be printed when the
    parsed title is wrong.
    """

    titles: tuple[str, ...] = ()
    own_dois: tuple[str, ...] = ()
    printed_dois: tuple[str, ...] = ()
    pmids: tuple[str, ...] = ()
    pmcids: tuple[str, ...] = ()
    document_kind: str = "article"
    opening_text: str = ""


@dataclass(frozen=True)
class Verdict:
    verdict: str
    rule: str
    relation: str = ""
    related_doi: str = ""
    evidence: dict = field(default_factory=dict)


def best_title(paper_title: str, titles: tuple[str, ...]) -> tuple[str, str, float | None]:
    """The source title closest to the paper's, with its state and similarity."""
    best = ("", "missing", None)
    for title in titles:
        state, similarity = title_state(paper_title, title)
        if similarity is not None and (best[2] is None or similarity > best[2]):
            best = (clean(title), state, similarity)
    return best


def verify(
    paper: Paper,
    source: Source,
    relations: Mapping[frozenset[str], str] | None = None,
) -> Verdict:
    paper_doi = normalize_doi(paper.doi)
    # A heading that is not a title is ignored unless it agrees with the paper's title.
    ignored = [
        title
        for title in source.titles
        if is_not_a_title(title, paper.journal) and title_state(paper.title, title)[0] != "agrees"
    ]
    titles = tuple(title for title in source.titles if title not in ignored)
    source_title, state, similarity = best_title(paper.title, titles)
    heading_agrees = state == "agrees"
    title_printed = title_printed_in(paper.title, source.opening_text[:OPENING_TITLE_CHARS])
    if title_printed and state != "agrees":
        # The paper's title is printed at the start. When the parsed heading is
        # another title, the document may hold the paper among other items.
        state = "unclear" if state == "differs" else "agrees"
    evidence: dict = {
        "title_state": state,
        "title_similarity": similarity,
        "source_title": source_title,
        "title_printed": title_printed,
        "ignored_titles": ignored,
        "document_kind": source.document_kind,
    }

    paper_kind = doi_kind(paper_doi)
    if paper_kind in NOT_A_WORK_DOI_KINDS or paper_kind == "component":
        return Verdict("wrong_kind", f"paper_doi_is_{paper_kind}", evidence=evidence)
    if source.document_kind in NON_ARTICLE_DOCUMENT_KINDS:
        return Verdict("wrong_kind", f"document_is_{source.document_kind}", evidence=evidence)

    own: list[str] = []
    set_aside: dict[str, str] = {}
    for value in source.own_dois:
        doi = normalize_doi(value)
        reason = set_aside_reason(doi, paper_doi)
        if reason:
            set_aside[doi] = reason
        elif doi and doi not in own:
            own.append(doi)
    others = sorted(doi for doi in own if not same_doi(doi, paper_doi))
    # A preprint or repository DOI given as the document's own marks a version
    # even when the paper's DOI is printed in it.
    version_others = [doi for doi in others if doi_kind(doi) in VERSION_DOI_KINDS]
    own_match = (
        any(same_doi(doi, paper_doi) for doi in own)
        or (bool(clean(paper.pmid)) and clean(paper.pmid) in {clean(value) for value in source.pmids})
        or (bool(clean(paper.pmcid)) and clean(paper.pmcid).upper() in {clean(value).upper() for value in source.pmcids})
    )
    printed_match = any(same_doi(doi, paper_doi) for doi in source.printed_dois) or any(
        reason in PAPER_DOI_RUN_ON for reason in set_aside.values()
    )
    printed_others = sorted(
        {
            normalize_doi(doi)
            for doi in source.printed_dois
            if not same_doi(doi, paper_doi) and not set_aside_reason(doi, paper_doi)
        }
    )
    evidence.update(
        {
            "own_dois": own,
            "other_dois": others,
            "set_aside_dois": set_aside,
            "paper_doi_printed": printed_match,
            "other_printed_dois": printed_others,
        }
    )

    if own_match or (printed_match and not others):
        if state == "agrees":
            if not heading_agrees and printed_others:
                # Only the printed title agrees, and the page also prints other
                # DOIs: an abstract book or news page holding several items.
                return Verdict("unconfirmed", "possible_multi_item_page", evidence=evidence)
            return Verdict("verified", "identifier_and_title", evidence=evidence)
        if state == "differs":
            return Verdict("conflict", "identifier_matches_title_differs", evidence=evidence)
        return Verdict("unconfirmed", "identifier_only", evidence=evidence)

    if printed_match and not version_others and state == "agrees":
        # The paper's DOI is printed, but the parser read another DOI as the
        # document's own: a cited article, or a cover sheet attached to another text.
        return Verdict("unconfirmed", "printed_doi_matches_parsed_doi_differs", related_doi=others[0], evidence=evidence)

    if others:
        registered = [(doi, (relations or {}).get(frozenset((paper_doi, doi)), "")) for doi in others]
        for doi, relation in registered:
            if relation in DEDUPLICATED_RELATIONS and state != "differs":
                return Verdict("version_of", "registered_relation", relation, doi, evidence)
            if relation and relation not in DEDUPLICATED_RELATIONS:
                return Verdict("wrong_kind", "registered_relation", relation, doi, evidence)
        related = (version_others or others)[0]
        if state == "agrees":
            return Verdict("conflict", "title_matches_identifier_differs", related_doi=related, evidence=evidence)
        if state == "differs":
            return Verdict("conflict", "identifier_and_title_differ", related_doi=related, evidence=evidence)
        return Verdict("conflict", "identifier_differs_title_unclear", related_doi=related, evidence=evidence)

    if state == "agrees":
        if heading_agrees and (similarity or 0) >= TITLE_ONLY_VERIFIED:
            return Verdict("verified", "title_only_close_match", evidence=evidence)
        return Verdict("unconfirmed", "title_only", evidence=evidence)
    if state == "differs":
        return Verdict("unconfirmed", "title_differs_no_identifier", evidence=evidence)
    return Verdict("unconfirmed", "no_identity_evidence", evidence=evidence)
