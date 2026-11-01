"""Statements in extraction outputs that the supplied text is not the paper.

The extraction prompts do not ask the model to compare the title with the
text, but the model often says so in its warnings and notes. ``classify``
finds these statements in free text. Categories:

| Code | Statement |
|---|---|
| ``D`` | the title, metadata or DOI and the supplied text describe different works |
| ``C`` | the text also contains material from another document |
| ``T`` | the text is another kind of document (erratum, protocol, conference abstract, letter, supplement) |
| ``L`` | the text is in another language or mixes language editions |
| ``M`` | the text is truncated, partial or metadata only |
| ``B`` | a year, DOI or other bibliographic field conflicts while the text seems right |

On the 1 November 2026 hand check, 40 of 43 ``D`` statements were correct
(33 of 36 papers). Only ``D`` is used as identity evidence; the other
categories are counted.
"""

from __future__ import annotations

from collections.abc import Iterator
import re


LANGS = (
    "german|french|spanish|russian|chinese|japanese|italian|portuguese|polish|czech|hungarian|"
    "dutch|korean|turkish|persian|farsi|swedish|danish|norwegian|finnish|greek|hebrew|arabic|"
    "romanian|croatian|serbian|slovak|slovenian|bulgarian|ukrainian|catalan|lithuanian|latvian|estonian"
)
ID_OBJ = r"(?:title|titles|metadata|bibliographic (?:details|record|metadata|information)|doi (?:metadata|and title)|record)"
# "doi" alone is left out: DOI is also a compound name (2,5-dimethoxy-4-iodoamphetamine).
TEXT_OBJ = (
    r"(?:abstract|abstracts|article text|supplied text|provided text|text|content|article body|body|article|"
    r"study content|study described|report|excerpt)"
)
DISAGREE = (
    r"(?:do(?:es)? not match|not match(?:ing)?|mismatch(?:ed|es)?|unrelated|incongruent|"
    r"(?:appears? |seems? |are |is )?inconsistent with|conflicts? with|disagrees? with|"
    r"do(?:es)? not correspond)"
)

PATTERNS: dict[str, list[tuple[str, re.Pattern]]] = {
    "D": [
        ("D_title_disagrees_text", re.compile(
            r"\b(?:the )?(?:supplied |provided |paper |article |study |publication |metadata |abstract )?"
            + ID_OBJ
            + r"\b[^.;]{0,90}?\b" + DISAGREE + r"\b[^.;]{0,140}?\b" + TEXT_OBJ + r"\b")),
        ("D_text_disagrees_title", re.compile(
            r"\b" + TEXT_OBJ + r"\b[^.;]{0,160}?\b(?:do(?:es)? not match|mismatched to|mismatch(?:ed)? with|"
            r"unrelated to|incongruent with|inconsistent with|do(?:es)? not correspond to)\b[^.;]{0,40}?"
            r"\b(?:the )?(?:supplied |provided |paper |article |stated |named |identified |titled )?"
            r"(?:title|metadata|doi|paper identified|study identified|titled|"
            r"[a-z0-9-]+ (?:study|paper|article|review|report) (?:title|metadata)|"
            r"(?:[a-z0-9-]+ ){0,2}(?:study|paper|article|review|report)\b(?! design))")),
        ("D_contrast", re.compile(
            r"\b" + ID_OBJ
            + r"(?: and (?:doi|metadata|publication metadata|doi metadata|\d{4} (?:\w+ )?(?:publication )?metadata))?"
            r"[^.;]{0,40}?\b(?:identif(?:y|ies)|describe|describes|concern|concerns|refer to|refers to|is about|"
            r"indicate|indicates)\b[^.;]{3,200}?\b(?:but|whereas|while)\b[^.;]{0,30}?\b(?:the )?(?:supplied |provided )?"
            r"(?:abstract|article text|supplied text|text|content)\b[^.;]{0,20}?"
            r"\b(?:describes|concerns|is about|discusses|consists of|contains no|is an?|reports an?|reports on)\b")),
        ("D_identity_vocab", re.compile(
            r"\bsource[- ](?:and \w+ )?identity\b|\bstudy identity\b|\bsource[- ]title\b|"
            r"\bidentity of the (?:source|paper|study|report|article)\b|"
            r"\b(?:refer|refers|belong|belongs|correspond|corresponds) to (?:two )?different "
            r"(?:papers?|stud(?:y|ies)|articles?|reports?|publications?|works?|documents?)\b|"
            r"\bappears? to (?:describe|be|concern) (?:a )?different (?:paper|study|article|report|publication|work|document)\b|"
            r"\bnot the titled\b|\bdoes not contain the titled\b|"
            r"\bcannot be (?:confidently |safely |reliably )?attributed to the (?:paper|study|article|report|publication)\b|"
            r"\bpaper identified (?:by|in) the (?:title|doi|metadata)\b|"
            r"\b(?:text and metadata|metadata and (?:text|abstract)|title and (?:text|abstract)) appear(?:s)? "
            r"(?:to be )?mismatched\b|"
            r"\bmismatched (?:to|with) the (?:title|metadata|titled)\b|"
            r"\bmay be mismatched\b|\bmismatched title\b")),
        ("D_text_has_other_doi", re.compile(
            r"\b(?:footer|header|article text|text|pdf|first page)\b[^.;]{0,40}\bdoi\b[^.;]{0,30}10\.\d{4,9}/[^\s,;]+"
            r"[^.;]{0,80}\b(?:differs|different|not the|does not match|whereas|but)\b")),
        ("D_metadata_abstract_vs_text", re.compile(
            r"\b(?:metadata abstract|abstract metadata|supplied metadata abstract)\b[^.;]{0,200}?"
            r"\b(?:whereas|but|while|does not match|inconsistent|different)\b")),
        ("D_bibliographic_inconsistent", re.compile(
            r"\binconsistent bibliographic details\b|"
            r"\bbibliographic (?:details|record|metadata)\b[^.;]{0,80}?\b(?:inconsistent|conflict|differ)")),
        ("D_weak_mismatched_task", re.compile(r"\bmismatched to (?:the|this) task\b")),
    ],
    "C": [
        ("C_text_contains_other", re.compile(
            r"\b(?:text|article|abstract|section)\b[^.;]{0,40}?\b(?:also )?"
            r"(?:contains|includes|begins with|ends with|is followed by|followed by)\b[^.;]{0,60}?"
            r"\b(?:unrelated|separate|second|another|appended|earlier|foreign)\b[^.;]{0,60}?"
            r"\b(?:abstracts?|articles?|letters?|errat(?:um|a)|passages?|material|protocol|commentar(?:y|ies)|"
            r"correspondence|tables?|figures?|text|stud(?:y|ies)|reports?|review)\b")),
        ("C_unrelated_material", re.compile(
            r"\b(?:apparently |a second,? |second |separate |appended )?unrelated\b[^.;]{0,50}?"
            r"\b(?:abstracts?|errat(?:um|a)|letters?|passages?|material|protocol|commentar(?:y|ies)|correspondence|"
            r"article text|text|table material|figure captions)\b")),
        ("C_dear_editor", re.compile(r"'dear editor'|\"dear editor\"")),
        ("C_appended", re.compile(
            r"\bappended (?:protocol|commentar(?:y|ies)|correspondence|figure|table|material|letters?|abstracts?|errat)")),
    ],
    "T": [
        ("T_is_other_doc", re.compile(
            r"\b(?:supplied |provided )?(?:text|document|source|material|item|record|article|abstract|paper|publication)\b"
            r"[^.;]{0,30}?\b(?:is|appears to be|consists of|is only|contains only|is actually)\b[^.;]{0,20}?"
            r"\b(?:an? |the )?(?:errat(?:um|a)|corrigend(?:um|a)|correction(?: notice)?|retraction(?: notice)?|"
            r"(?:study |trial |research )?protocol|conference abstract|meeting abstract|congress abstract|"
            r"poster(?: abstract| summary)?|symposium (?:abstract|summary|report)|abstract/poster summary|"
            r"letter(?: to the editor)?|reply|response letter|author reply|news (?:item|article)|book review|"
            r"book chapter|table of contents|supplement(?:ary material)?|front matter|journal index|errata)\b")),
        ("T_this_is_meeting_abstract", re.compile(
            r"\b(?:this|it|the source|the paper|the record)\b (?:is|appears to be) (?:a |an )?"
            r"(?:meeting|conference|congress|symposium|poster)\b")),
        ("T_meeting_phrases", re.compile(
            r"\bthis (?:meeting|conference|congress|symposium) abstract\b|\bsymposium abstract summariz|"
            r"\bcollection of symposium reports\b|\bposter sessions? [a-z0-9]\b|\btitle[^.;]{0,40}\bis generic\b")),
        ("T_rather_than_article", re.compile(
            r"\b(?:abstract|poster|summary|protocol|letter|erratum|correction|reply)\b[^.;]{0,30}\brather than "
            r"(?:a |an |the )?(?:complete|full|full-length|published|original|research) (?:article|paper|report|text)\b")),
    ],
    "L": [
        ("L_text_in_language", re.compile(
            r"\b(?:text|abstract|article|paper|source|excerpt|sections?)\b[^.;]{0,60}?"
            r"\b(?:is|was|are|were|written|supplied|available|provided|appears|given)\b[^.;]{0,25}?\bin (?:"
            + LANGS + r")\b")),
        ("L_rendered_language", re.compile(
            r"\b(?:imperfectly |poorly )?rendered (?:" + LANGS + r")\b|\b(?:text|abstract|article) (?:is |was )?"
            r"(?:not in english|non-english)\b|\bnon-english (?:text|abstract|article text)\b|\bmachine[- ]translat")),
        ("L_bilingual_conflict", re.compile(
            r"\b(?:english and (?:" + LANGS + r")|(?:" + LANGS + r") and english)(?: language)? "
            r"(?:abstracts?|texts?|versions?|abstract lists)\b")),
    ],
    "M": [
        ("M_text_missing", re.compile(
            r"\b(?:contains|consists of|includes|provides)\b[^.;]{0,30}?\b(?:only )?"
            r"(?:article |publication(?:-page)? |bibliographic |journal |page )?"
            r"(?:metadata|webpage|web page|navigation|boilerplate|publication-page|publication-interface|cookie|subscription)\b|"
            r"\bno (?:substantive |scientific |study |usable )?abstract\b|\bwithout an abstract\b|\btitle (?:alone|only)\b|"
            r"\bonly the title\b|\bstated in the title only\b|\bno (?:abstract )?findings beyond the title\b|"
            r"\bno case details beyond the title\b|\btitle is blank\b|\bno substantive (?:article )?content\b")),
        ("M_text_truncated", re.compile(
            r"\b(?:supplied |provided )?(?:abstract|article text|article|text|excerpt)\b (?:is|was|appears|appears to be) "
            r"(?:also )?(?:truncated|incomplete|cut off)\b|"
            r"\b(?:abstract|article text|text|article)\b[^.;]{0,20}?\bends? (?:abruptly|mid-?sentence|mid-?word|"
            r"mid-?discussion|mid\b)|\btruncated before\b|\bcontinue'|"
            r"\b(?:supplied |provided )?(?:article )?text\b[^.;]{0,30}?\b(?:contains|includes|consists of|provides)\b"
            r"[^.;]{0,10}?\bonly\b[^.;]{0,40}?\b(?:abstract|first page|introduction|introductory|references|summary)\b|"
            r"\bnot the full (?:review|article|text|paper)\b|\bonly the first page\b|\bfirst page only\b|"
            r"\babstract-level (?:results|text|content)\b|despite the (?:provided |supplied )?text_depth")),
    ],
    "B": [
        ("B_year_conflict", re.compile(
            r"\bmetadata\b[^.;]{0,80}?\byear\b[^.;]{0,140}?\b(?:conflict|inconsistent|differs|whereas|but|while)\b"
            r"[^.;]{0,80}?\b(?:article text|doi|publication date|text|article)\b")),
    ],
}

# Statements about publication type or emphasis that read like a mismatch.
D_EXCLUDE = re.compile(
    r"\b(?:labels?|labeled|labelled|classif(?:y|ies|ied)|categoriz|publication[- ]type|article type|review-related|"
    r"review-oriented|non-primary|review type|source type)\b|"
    r"\bidentif(?:y|ies|ied) (?:the |this )?(?:item |article |publication |paper |record )?as (?:a|an)\b"
)
C_SUBJECT = re.compile(r"\b(?:appended|figure|table|caption|passage|dear editor|separate|reference|commentar|correspondence)\b")
IDENTITY_TERMS = re.compile(r"\bsource[- ](?:and \w+ )?identity\b|different papers?\b|unrelated|does not match|mismatch")


def classify(text: str) -> dict[str, list[str]]:
    """Return the categories found in one statement, with the patterns that matched."""
    t = text.casefold().replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    t = re.sub(r"\s+", " ", t)
    out: dict[str, list[str]] = {}
    for category, patterns in PATTERNS.items():
        for name, pattern in patterns:
            if not pattern.search(t):
                continue
            if name == "D_contrast" and D_EXCLUDE.search(t):
                continue
            out.setdefault(category, []).append(name)
    if "D" in out:
        kept = []
        for name in out["D"]:
            if name == "D_text_disagrees_title" and C_SUBJECT.search(t):
                continue
            if (
                name == "D_identity_vocab"
                and re.search(r"paper identified (?:by|in) the", t)
                and not re.search(r"cannot|not be|uncertain|mismatch|verify|verification", t)
                and not re.search(r"source[- ](?:and \w+ )?identity|different papers?|not the titled|does not contain the titled|mismatched", t)
            ):
                continue
            if (
                name in {"D_title_disagrees_text", "D_text_disagrees_title"}
                and D_EXCLUDE.search(t)
                and not IDENTITY_TERMS.search(t)
            ):
                continue
            kept.append(name)
        if kept:
            out["D"] = kept
        else:
            del out["D"]
    return out


def iter_strings(value: object, path: str = "$") -> Iterator[tuple[str, str]]:
    """Every string in a parsed output, with its JSON path."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from iter_strings(child, f"{path}.{key}")
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child, f"{path}[]")
