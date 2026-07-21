"""Conservative quality checks for text stored in bibliographic abstract fields.

The discovery providers do not all expose equivalent fields.  In particular,
OpenAlex and Semantic Scholar can occasionally return reconstructed article
text, publisher-page text, or a multi-record container in the field labelled
as an abstract.  These checks intentionally identify only evidence that the
field is not a single-paper abstract; they do not judge scientific relevance.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


LOW_TRUST_LONG_TEXT_PROVIDERS = {"openalex", "semantic_scholar"}
PROVIDER_PRIORITY = {
    "pubmed": 0,
    "pmc": 1,
    "crossref": 2,
    "semantic_scholar": 3,
    "openalex": 4,
}
LOW_TRUST_MAX_ABSTRACT_CHARS = 5000
EXTREME_MAX_ABSTRACT_CHARS = 15000

NAVIGATION_PHRASES = (
    "back to table of contents previous article next article",
    "full text figures and data side by side abstract",
    "article figures and data abstract",
    "article and author information",
    "download citation track citations permissions reprints",
    "pdf add to favorites download citation",
)
PEER_REVIEW_TITLE_RE = re.compile(
    r"(?:^|\b)(?:decision letter|author response|eLife assessment|reviewer\s*#?\d+\s*\(public review\))",
    re.IGNORECASE,
)
COLLECTION_TITLE_RE = re.compile(
    r"\b(?:congress|conference|annual meeting|poster presentations?|abstracts? book|book of abstracts)\b",
    re.IGNORECASE,
)
COLLECTION_BODY_RE = re.compile(
    r"\b(?:no\.\s*:\s*abs\d+|abstract\s*(?:no\.|number)?\s*\d+|publishing number\s+\d+)\b",
    re.IGNORECASE,
)
ISSUE_POINTERS_RE = re.compile(r"^\s*Pointers\b", re.IGNORECASE)
ISSUE_PAGE_POINTER_RE = re.compile(r"\(p\.\s*\d+\)", re.IGNORECASE)
NON_ABSTRACT_LEADING_TEXT_RE = re.compile(
    r"(?:click to (?:increase|decrease) image size|previous article|next article|"
    r"back to table of contents|you have access|full access|book review|"
    r"\bISBN\b|\bBSS subject index\b|\bNotes?\s+\d+[\s.]|"
    r"\b\d+\s+pp\b|\$\d|download citation|track citations)",
    re.IGNORECASE,
)
NON_ABSTRACT_LEADING_TITLE_RE = re.compile(
    r"(?:^review:|\b(?:editorial|book review|websites of note|this month in|pediatrics digest|"
    r"science, medicine, and the anesthesiologist|ISBN|\d+\s*pp\.)\b)",
    re.IGNORECASE,
)
SECTION_PATTERNS = {
    "introduction": re.compile(r"\bintroduction\b", re.IGNORECASE),
    "methods": re.compile(r"\b(?:materials and methods|methods?)\b", re.IGNORECASE),
    "results": re.compile(r"\bresults?\b", re.IGNORECASE),
    "discussion": re.compile(r"\bdiscussion\b", re.IGNORECASE),
    "references": re.compile(r"\breferences\b", re.IGNORECASE),
    "acknowledgments": re.compile(r"\backnowledg(?:e)?ments?\b", re.IGNORECASE),
}


@dataclass(frozen=True)
class AbstractQuality:
    status: str
    reasons: tuple[str, ...]
    char_count: int

    @property
    def usable(self) -> bool:
        return self.status == "valid"


@dataclass(frozen=True)
class EmbeddedAbstract:
    text: str
    method: str
    boundary: str


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def normalize_provider(value: object) -> str:
    provider = clean_text(value).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "semantic_scholar_api": "semantic_scholar",
        "s2": "semantic_scholar",
        "pub_med": "pubmed",
        "pub_med_central": "pmc",
    }
    return aliases.get(provider, provider)


def split_providers(value: object) -> list[str]:
    return [normalize_provider(part) for part in re.split(r"\s*[|,;]\s*", clean_text(value)) if part]


def provider_is_low_trust_for_long_text(provider: object) -> bool:
    return any(item in LOW_TRUST_LONG_TEXT_PROVIDERS for item in split_providers(provider))


def section_labels(text: str) -> set[str]:
    return {name for name, pattern in SECTION_PATTERNS.items() if pattern.search(text)}


def contamination_reasons(
    abstract: object,
    *,
    provider: object = "",
    title: object = "",
) -> tuple[str, ...]:
    """Return high-confidence reasons that a field is not a usable abstract."""

    text = clean_text(abstract)
    if not text:
        return ()
    lowered = text.lower()
    reasons: list[str] = []

    if ISSUE_POINTERS_RE.search(text) and len(ISSUE_PAGE_POINTER_RE.findall(text)) >= 3:
        reasons.append("journal_issue_contents_not_article_abstract")

    if any(phrase in lowered for phrase in NAVIGATION_PHRASES):
        reasons.append("publisher_page_or_fulltext_navigation")

    if len(text) >= 2500 and PEER_REVIEW_TITLE_RE.search(clean_text(title)):
        reasons.append("peer_review_artifact_contains_article_text")

    if len(text) > LOW_TRUST_MAX_ABSTRACT_CHARS and COLLECTION_TITLE_RE.search(clean_text(title)):
        if COLLECTION_BODY_RE.search(text) or lowered.count("abstract") >= 3:
            reasons.append("multi_record_abstract_collection")

    if len(text) > LOW_TRUST_MAX_ABSTRACT_CHARS:
        labels = section_labels(text)
        full_article_sequence = {
            "introduction",
            "methods",
            "results",
            "discussion",
        }.issubset(labels)
        end_matter = "references" in labels or "acknowledgments" in labels
        if full_article_sequence and end_matter:
            reasons.append("full_article_section_sequence")

    if len(text) > EXTREME_MAX_ABSTRACT_CHARS:
        reasons.append("extreme_length_in_abstract_field")
    elif len(text) > LOW_TRUST_MAX_ABSTRACT_CHARS and provider_is_low_trust_for_long_text(provider):
        reasons.append("overlong_low_trust_provider_field")

    return tuple(dict.fromkeys(reasons))


def assess_abstract(
    abstract: object,
    *,
    provider: object = "",
    title: object = "",
) -> AbstractQuality:
    text = clean_text(abstract)
    if not text:
        return AbstractQuality(status="missing", reasons=(), char_count=0)
    reasons = contamination_reasons(text, provider=provider, title=title)
    return AbstractQuality(
        status="contaminated" if reasons else "valid",
        reasons=reasons,
        char_count=len(text),
    )


def _usable_extracted_segment(text: str) -> bool:
    if not 200 <= len(text) <= LOW_TRUST_MAX_ABSTRACT_CHARS:
        return False
    if len(text.split()) < 40:
        return False
    if sum(text.count(mark) for mark in (".", "?", "!")) < 2:
        return False
    return assess_abstract(text, provider="embedded_abstract_extraction").usable


def extract_embedded_abstract(value: object, *, title: object = "") -> EmbeddedAbstract | None:
    """Conservatively salvage a bounded abstract section from article text.

    This is intentionally not equivalent to truncation.  A segment is returned
    only when a recognizable abstract start/end boundary exists, or when a
    plausible article-leading summary is followed by an explicit Introduction.
    """

    text = clean_text(value)
    if not text:
        return None

    abstract_match = re.search(r"\babstract\b\s*:?[\s-]*", text[:2500], re.IGNORECASE)
    if abstract_match:
        marker_context = text[max(0, abstract_match.start() - 40) : abstract_match.end()].lower()
        if "does not have an abstract" in marker_context or "no abstract" in marker_context:
            abstract_match = None
    if abstract_match:
        start = abstract_match.end()
        tail = text[start : start + LOW_TRUST_MAX_ABSTRACT_CHARS + 1200]
        boundary_matches: list[tuple[int, str]] = []
        for label, pattern in (
            ("introduction", r"\bintroduction\b"),
            ("elife_digest", r"\belife digest\b"),
            ("plain_language_summary", r"\bplain language summary\b"),
            ("author_summary", r"\bauthor summary\b"),
            ("article_information", r"\barticle and author information\b"),
            ("figures_and_data", r"\bfigures and data\b"),
            ("keywords", r"\bkeywords?\b\s*:"),
        ):
            match = re.search(pattern, tail[200:], re.IGNORECASE)
            if match:
                boundary_matches.append((200 + match.start(), label))
        if boundary_matches:
            end, boundary = min(boundary_matches)
            segment = clean_text(tail[:end]).strip(" :-")
            no_abstract_notice = "does not have an abstract" in segment[:150].lower()
            if not no_abstract_notice and not NON_ABSTRACT_LEADING_TEXT_RE.search(segment) and _usable_extracted_segment(segment):
                return EmbeddedAbstract(segment, "explicit_abstract_section", boundary)

    introduction = re.search(r"\bintroduction\b", text, re.IGNORECASE)
    if introduction and 300 <= introduction.start() <= LOW_TRUST_MAX_ABSTRACT_CHARS:
        segment = clean_text(text[: introduction.start()]).strip(" :-")
        unsuitable_title = NON_ABSTRACT_LEADING_TITLE_RE.search(clean_text(title))
        if not unsuitable_title and not NON_ABSTRACT_LEADING_TEXT_RE.search(segment):
            if not any(phrase in segment.lower() for phrase in NAVIGATION_PHRASES):
                if _usable_extracted_segment(segment):
                    return EmbeddedAbstract(segment, "leading_summary_before_introduction", "introduction")
    return None


def best_valid_abstract(rows: Iterable[dict]) -> dict | None:
    """Choose the highest-provenance usable abstract, never the longest text."""

    candidates: list[tuple[tuple[int, int, str], dict]] = []
    for row in rows:
        abstract = clean_text(row.get("abstract", ""))
        provider = normalize_provider(row.get("provider", ""))
        quality = assess_abstract(abstract, provider=provider, title=row.get("title", ""))
        if not quality.usable:
            continue
        # Prefer provider provenance first.  Length only breaks ties within the
        # same provider, where a structured abstract can legitimately be more
        # complete than a short summary.
        key = (PROVIDER_PRIORITY.get(provider, 50), -len(abstract), abstract)
        candidates.append((key, row))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]
