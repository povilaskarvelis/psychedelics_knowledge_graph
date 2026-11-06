"""Identity evidence, read and compared the same way at every stage.

``verify.py`` applies the rule: a text belongs to a paper when an identifier
taken from the source itself and the source's title both agree with the paper.
This module reads that evidence and holds the comparisons:

- the kind of a DOI: an article, a preprint or repository deposit, a component
  of an article, or not a work at all (funder, ISSN, issue, placeholder);
- DOIs found in a source that say nothing about the paper: truncated or
  extended parses of the paper's own DOI and DOIs that name no work;
- title agreement with numbers kept, so that editions and years differ;
- agreement between a title and an abstract;
- the kind of document a full text is: an article, a supplement or a
  correction notice;
- the identity evidence in a stored full-text artifact.
"""

from __future__ import annotations

from difflib import SequenceMatcher
import hashlib
import html
from pathlib import Path
import re
import shutil
import subprocess

from pipeline.fulltext.source_identity import (
    extraction_identity,
    normalize_pmcid,
    split_dois,
    strip_markup,
    successful_extractions,
)
from pipeline.ingest.candidate_status import clean, normalize_doi


# Registrant prefixes of preprint servers and of repositories that mint DOIs
# for deposits of articles published elsewhere.
PREPRINT_PREFIXES = (
    "10.1101/",
    "10.21203/",
    "10.31234/",
    "10.20944/",
    "10.2139/",
    "10.31219/",
    "10.31235/",
    "10.17605/osf.io/",
    "10.31124/",
    "10.64898/",
    "10.2196/preprints",
    "10.22541/",
    "10.36227/",
    "10.26434/",
    "10.32388/",
    "10.48550/",
)
REPOSITORY_PREFIXES = (
    "10.5281/",
    "10.17615/",
    "10.48620/",
    "10.18452/",
    "10.25316/",
    "10.22028/",
    "10.5167/",
    "10.17863/",
    "10.14288/",
    "10.17169/",
    "10.3929/",
    "10.6084/",
)
FUNDER_PREFIXES = ("10.13039/",)
# Zero-padded figure, table and supporting-file numbers (".g001", ".s001"),
# supplement links, eLife assessments and reviews (".sa1"), Cambridge
# peer-review reports (".pr1") and Copernicus review comments
# ("-2017-472-rc1"). Article e-locators such as "bmj.e288" are works.
COMPONENT_RE = re.compile(
    r"(?:\.(?:g|t|s)0\d{2,3}|/supp-\d+|\.suppl?\d*|/-/dc\d+|\.sa\d+|\.pr\d+|\d{4}-\d+-(?:rc|ac|cc|ec)\d{1,2})$",
    re.IGNORECASE,
)
# A journal's ISSN DOI, which names the journal ("issn.1657-4923"). Article
# DOIs that start with an ISSN or a year ("1658-3175.8312", "2017-0034") are works.
ISSN_SUFFIX_RE = re.compile(r"^issn[._-]?\d{4}-?\d{3}[\dx]$", re.IGNORECASE)
ISSUE_RE = re.compile(r"[./_-]issue[-_.]?\d+$", re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r"tobeassigned|to-be-assigned|xxxx|pending", re.IGNORECASE)

# DOI kinds that do not name a work.
NOT_A_WORK_DOI_KINDS = frozenset({"funder", "issn", "issue", "placeholder"})
VERSION_DOI_KINDS = frozenset({"preprint", "repository"})

TITLE_AGREES = 0.9
TITLE_DIFFERS = 0.5
# Characters of raw artifact text read for front matter, and of stripped text kept.
FRONT_RAW_CHARS = 60000
FRONT_MATTER_CHARS = 12000

SUPPLEMENT_HEADING_RE = re.compile(
    r"^\W*(?:electronic |online )?(?:supplementa(?:l|ry)|supporting) "
    r"(?:information|materials?|data|appendix|methods|figures?|tables?|text|file)\b",
    re.IGNORECASE,
)
# A supplementary figure or table caption ("Supplementary Figure 1. S. divinorum
# genome size"). Articles cite these in brackets; a supplement starts with them.
SUPPLEMENT_CAPTION_RE = re.compile(r"\b(?i:supplementa(?:l|ry) (?:figure|fig\.|table|note)) ?S?\d+\s*[.:]\s+[A-Z]")
CORRECTION_TITLE_RE = re.compile(
    r"^\W*(?:correction|corrigendum|erratum|errata|retraction(?: notice)?|expression of concern)\b",
    re.IGNORECASE,
)
REFERENCES_START_RE = re.compile(
    r"<(?:listBibl|back)\b|\n#{1,6}\s*(?:references|bibliography)\b|\n(?:references|bibliography)\s*\n",
    re.IGNORECASE,
)
NON_ARTICLE_DOCUMENT_KINDS = frozenset({"supplement", "correction"})

# Words that carry no topic in a title, for title–abstract agreement.
STOPWORDS = frozenset(
    """a an the of and or in on for to with by from at as is are was were be been being this that these those its it into
than then via vs versus not no nor but if so such can may might will would should could do does did has have had their there
our your his her we they them who which what when where while about after before during under over between among within without
de la le les des du et en el los las del y por para con una un uno al se que da do dos das na no em um uma und der die das mit
von zu im ein eine fur für auf aus bei""".split()
)
GENERIC_TITLE_WORDS = frozenset(
    """study studies effect effects analysis review reviews case cases report reports patient patients treatment treatments
clinical new use using used role based journal letter letters editor reply comment comments response responses abstract abstracts
introduction conclusion conclusions research result results trial trials evaluation assessment approach article paper issue
information note notes part chapter volume index contents cover editorial news update vol book books summary""".split()
)


# --- DOIs -----------------------------------------------------------------


def doi_suffix(doi: str) -> str:
    return doi.split("/", 1)[1] if "/" in doi else ""


def same_doi(left: object, right: object) -> bool:
    """True when two DOIs are equal after normalization, ignoring punctuation."""
    a, b = normalize_doi(left), normalize_doi(right)
    if not a or not b:
        return False
    return a == b or re.sub(r"[^a-z0-9]", "", a) == re.sub(r"[^a-z0-9]", "", b)


def doi_kind(value: object) -> str:
    """Classify a DOI by what it names."""
    doi = normalize_doi(value)
    if not doi:
        return "missing"
    suffix = doi_suffix(doi)
    if doi.startswith(FUNDER_PREFIXES):
        return "funder"
    if ISSN_SUFFIX_RE.match(suffix):
        return "issn"
    if ISSUE_RE.search(doi):
        return "issue"
    if PLACEHOLDER_RE.search(suffix):
        return "placeholder"
    if COMPONENT_RE.search(doi):
        return "component"
    if doi.startswith(PREPRINT_PREFIXES):
        return "preprint"
    if doi.startswith(REPOSITORY_PREFIXES):
        return "repository"
    return "article"


def set_aside_reason(found: object, paper_doi: object) -> str:
    """Why a DOI found in a source says nothing about the paper, or ``""``.

    Parsers truncate DOIs at line breaks, run them into the next word or link,
    and pick up journal, issue and funder DOIs printed on page one. None of
    these names another work.
    """
    doi = normalize_doi(found)
    paper = normalize_doi(paper_doi)
    if not doi:
        return "empty"
    kind = doi_kind(doi)
    if kind in NOT_A_WORK_DOI_KINDS:
        return f"{kind}_doi"
    if re.search(r"[-./]$", doi) or len(doi_suffix(doi)) < 4:
        return "malformed"
    if paper and not same_doi(doi, paper):
        if paper.startswith(doi) and doi_kind(paper) != "component":
            return "truncated_paper_doi"
        if doi.startswith(paper):
            return "component_of_paper" if kind == "component" else "extended_paper_doi"
    return ""


# Set-aside reasons under which the source still prints the paper's full DOI,
# run on into a link, a path or a component suffix.
PAPER_DOI_RUN_ON = frozenset({"extended_paper_doi", "component_of_paper"})

VERSION_SUFFIX_RE = re.compile(r"(?:[._]v\d+|v\d+)$", re.IGNORECASE)
LANGUAGE_SUFFIX_RE = re.compile(r"[-_.](?:en|pt|es|fr|zh|ar|ru|de|it)$", re.IGNORECASE)
REVIEW_COMMENT_RE = re.compile(r"-(?:rc|ac|cc|ec)\d+$", re.IGNORECASE)
ISBN_DOI_RE = re.compile(r"^(10\.\d+/(?:[a-z.]*?)?97[89][\d-]{8,16}\d)", re.IGNORECASE)
ZENODO_RE = re.compile(r"^10\.5281/zenodo\.(\d+)$")


def doi_variant_relation(left: object, right: object) -> str:
    """Work relation implied by the form of two DOIs alone, or ``""``.

    Covers punctuation and double-slash variants, one suffix under two
    prefixes, SICI variants, JAMA legacy and current DOIs, version suffixes,
    language editions and consecutive Zenodo record DOIs.
    """
    a, b = normalize_doi(left), normalize_doi(right)
    if not a or not b or a == b:
        return ""
    compact = lambda value: re.sub(r"[^a-z0-9]", "", value)  # noqa: E731
    if compact(a) == compact(b) or a.replace("//", "/") == b.replace("//", "/"):
        return "same_publication"
    if doi_suffix(a) and compact(doi_suffix(a)) == compact(doi_suffix(b)):
        return "same_publication"
    if "co;2-" in a and re.sub(r"3\.\d\.co;2-.$", "", a) == re.sub(r"3\.\d\.co;2-.$", "", b):
        return "same_publication"
    for x, y in ((a, b), (b, a)):
        legacy = re.match(r"10\.1001/([a-z]+)\.\d{4}\.\d+$", x)
        current = re.match(r"10\.1001/([a-z]+)\.\d+\.\d+\.\d+", y)
        if legacy and current and legacy.group(1) == current.group(1):
            return "same_publication"
    if (VERSION_SUFFIX_RE.search(a) or VERSION_SUFFIX_RE.search(b)) and (
        VERSION_SUFFIX_RE.sub("", a) == VERSION_SUFFIX_RE.sub("", b)
    ):
        return "version_doi"
    if LANGUAGE_SUFFIX_RE.search(a) and LANGUAGE_SUFFIX_RE.search(b) and (
        LANGUAGE_SUFFIX_RE.sub("", a) == LANGUAGE_SUFFIX_RE.sub("", b)
    ):
        return "translation"
    za, zb = ZENODO_RE.match(a), ZENODO_RE.match(b)
    if za and zb and abs(int(za.group(1)) - int(zb.group(1))) == 1:
        return "version_doi"
    return ""


def doi_part_relation(left: object, right: object) -> bool:
    """True when one DOI names a part of the other's item, or both are chapters of one book."""
    a, b = normalize_doi(left), normalize_doi(right)
    if not a or not b or a == b:
        return False
    for x, y in ((a, b), (b, a)):
        for pattern in (COMPONENT_RE, REVIEW_COMMENT_RE):
            if pattern.search(x) and pattern.sub("", x) in {y, pattern.sub("", y)}:
                return True
        if ISSUE_RE.search(x):
            return True
    book_a, book_b = ISBN_DOI_RE.match(a), ISBN_DOI_RE.match(b)
    return bool(book_a and book_b and book_a.group(1) == book_b.group(1))


def version_relation(paper_doi: object, other_doi: object) -> str:
    """Work relation suggested by the kinds of two DOIs that carry the same title, or ``""``."""
    variant = doi_variant_relation(paper_doi, other_doi)
    if variant:
        return variant
    kinds = {doi_kind(paper_doi), doi_kind(other_doi)}
    if "preprint" in kinds:
        return "preprint"
    if "repository" in kinds:
        return "repository_copy"
    return ""


# --- Titles ---------------------------------------------------------------


def title_key(value: object) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"[^0-9a-z]", "", text.casefold())


def title_similarity(left: object, right: object) -> float | None:
    """Similarity of two titles with numbers kept; ``None`` when either is blank.

    A title that is the start of the other (a title without its subtitle) or is
    contained in it counts as the same title.
    """
    a, b = title_key(left), title_key(right)
    if not a or not b:
        return None
    short, long = sorted((a, b), key=len)
    if (len(short) >= 10 and long.startswith(short)) or (len(short) >= 20 and short in long):
        return 1.0
    return round(SequenceMatcher(None, a, b).ratio(), 4)


def title_numbers(value: object) -> frozenset[str]:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return frozenset(number.lstrip("0") or "0" for number in re.findall(r"\d+", text))


def numbers_differ(left: object, right: object) -> bool:
    """True when each title has a number the other lacks, as editions and years do.

    Numbers split differently by formatting ("H215O" and "H(2)(15)O") have the
    same digits in the same order and do not differ.
    """
    a, b = title_numbers(left), title_numbers(right)
    if not (a - b and b - a):
        return False
    digits = lambda value: "".join(re.findall(r"\d", html.unescape(str(value or ""))))  # noqa: E731
    return digits(left) != digits(right)


def is_translated_title(value: object) -> bool:
    """PubMed shows titles translated into English in square brackets."""
    text = clean(value)
    return text.startswith("[") and text.rstrip(".").endswith("]")


def title_state(paper_title: object, source_title: object) -> tuple[str, float | None]:
    """Return ``agrees``, ``differs``, ``unclear`` or ``missing``, and the similarity."""
    similarity = title_similarity(paper_title, source_title)
    if similarity is None:
        return "missing", None
    if is_translated_title(paper_title) or is_translated_title(source_title):
        return "unclear", similarity
    if similarity >= TITLE_AGREES:
        # Otherwise equal titles with different numbers are different editions,
        # years or parts.
        return ("differs" if numbers_differ(paper_title, source_title) else "agrees"), similarity
    if similarity < TITLE_DIFFERS:
        return "differs", similarity
    return "unclear", similarity


# Parsed "titles" that are not the document's title: journal and repository
# mastheads, cover-sheet notices, section headings and letter-spaced text.
NOT_TITLE_START_RE = re.compile(
    r"^\W*(?:abbreviations|abstract|introduction|background|original (?:article|research|paper|contribution)|"
    r"research (?:article|paper|letter)|review article|short (?:communication|report)|brief (?:report|communication)|"
    r"letter to the editor|correspondence|editorial|commentary|case report|(?:table of )?contents|"
    r"suggested citation|citation for (?:the )?published version|downloaded from|you are prohibited|terms of use|"
    r"copyright|accepted (?:author )?manuscript|author manuscript|this is (?:a|an|the) |archive ouverte|"
    r"publication metadata|proceedings of\b|(?:the )?university of\b|(?:department|faculty|school|institute) of\b|orcid\b)",
    re.IGNORECASE,
)
NOT_TITLE_ANYWHERE_RE = re.compile(
    r"research portal|research online|e-?prints|institutional repository|digital commons|open access repository|"
    r"special (?:collection|issue)|themed (?:issue|section)",
    re.IGNORECASE,
)
LETTER_SPACED_RE = re.compile(r"^(?:\S ){5,}")
# A repository cover sheet: a page that describes a deposit and its terms before
# the attached text.
COVER_SHEET_RE = re.compile(
    r"citation for (?:the )?published version|document version|link to (?:the )?publication(?: record)?|"
    r"general rights|take ?down policy|copyright and moral rights|research portal|"
    r"this (?:version|file) (?:is|was) (?:available|made available|downloaded)|"
    r"(?:institutional|open access|university) repository",
    re.IGNORECASE,
)


def is_not_a_title(value: object, journal: object = "") -> bool:
    """True when a parsed document title is a heading other than the title.

    Parsers take the largest or first text on page one as the title. On many
    PDFs that is a journal or repository masthead, a cover-sheet notice, a
    section heading or letter-spaced text.
    """
    text = clean(value)
    letters = [char for char in text if char.isalpha()]
    if len(letters) >= 8 and sum(char.isupper() for char in letters) / len(letters) >= 0.8:
        return True
    if len(text) > 300 or LETTER_SPACED_RE.match(text) or len(re.findall(r"[^\W\d_]{2,}", text)) < 3:
        return True
    if clean(journal) and (title_similarity(text, journal) or 0) >= TITLE_AGREES:
        return True
    return bool(NOT_TITLE_START_RE.match(text) or (len(text) <= 80 and NOT_TITLE_ANYWHERE_RE.search(text)))


def is_cover_sheet(text: object) -> bool:
    """True when a page describes a repository deposit (two or more cover-sheet phrases)."""
    found = {match.group(0).casefold() for match in COVER_SHEET_RE.finditer(str(text or "")[:4000])}
    return len(found) >= 2


def title_printed_in(title: object, text: object, *, min_words: int = 4) -> bool:
    """True when the title's words appear in order in the text, numbers included."""
    def words(value: object) -> list[str]:
        plain = html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).casefold()
        return [word for word in re.findall(r"[0-9a-z]+", plain) if len(word) > 1 or word.isdigit()]

    wanted = words(title)
    if len(wanted) < min_words:
        return False
    return f" {' '.join(wanted)} " in f" {' '.join(words(text))} "


def text_words(value: object) -> list[str]:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).casefold()
    return [word for word in re.findall(r"[0-9a-zà-ɏͰ-ϿЀ-ӿ]+", text) if len(word) >= 3]


def title_abstract_agreement(title: object, abstract: object) -> float | None:
    """Share of the title's informative words (6-letter stems) found in the abstract.

    ``None`` when the title has fewer than two informative words.
    """
    stems = [
        word[:6]
        for word in text_words(title)
        if word not in STOPWORDS and word not in GENERIC_TITLE_WORDS and not word.isdigit()
    ]
    stems = list(dict.fromkeys(stems))
    if len(stems) < 2:
        return None
    present = {word[:6] for word in text_words(abstract)}
    return round(sum(1 for stem in stems if stem in present) / len(stems), 4)


# --- Texts ----------------------------------------------------------------


WEB_PAGE_TEXT_RE = re.compile(
    r"\bcookies?\b|\blog ?in\b|\bsign ?in\b|\bregister\b|\bsubscribe\b|\bjavascript\b|"
    r"\b(?:this|our) (?:web)?site\b|\bprivacy policy\b|\bterms of (?:use|service)\b|\bget (?:new issue )?alerts\b",
    re.IGNORECASE,
)


def is_web_page_text(value: object) -> bool:
    """True when an abstract is web-page text: cookie, log-in or subscription notices."""
    found = {match.group(0).casefold() for match in WEB_PAGE_TEXT_RE.finditer(str(value or "")[:400])}
    return len(found) >= 2


def text_sha256(value: object) -> str:
    """SHA-256 of a text as stored; decisions name abstracts by this hash."""
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def text_group_key(value: object) -> str:
    """Key under which the same abstract on several records is grouped."""
    return re.sub(r"[^0-9a-z]", "", html.unescape(str(value or "")).casefold())


def word_count(value: object) -> int:
    return len(str(value or "").split())


def document_kind(document_title: object, front_text: object, paper_title: object) -> str:
    """``supplement``, ``correction`` or ``article``.

    A paper whose own title names a supplement or a correction is not
    reclassified by the same words in its text.
    """
    heading = clean(document_title)
    opening = clean(front_text)[:300]
    if not SUPPLEMENT_HEADING_RE.match(clean(paper_title)) and (
        SUPPLEMENT_HEADING_RE.match(heading)
        or SUPPLEMENT_HEADING_RE.match(opening)
        or SUPPLEMENT_CAPTION_RE.search(str(front_text or "")[:2000])
    ):
        return "supplement"
    if CORRECTION_TITLE_RE.match(heading) and not CORRECTION_TITLE_RE.match(clean(paper_title)):
        return "correction"
    return "article"


# A DOI broken across lines after one of its separators.
DOI_LINE_BREAK_RE = re.compile(r"(?<=10\.\d{4})\s*\n\s*(?=/)|(?<=[./_-])[ \t]*\n\s*(?=[0-9a-z])", re.IGNORECASE)


def printed_dois(text: object) -> set[str]:
    """DOIs printed in a text, with DOIs broken across lines rejoined."""
    return split_dois(DOI_LINE_BREAK_RE.sub("", str(text or "")))


def front_matter(text: object) -> str:
    """Opening text of a document before its reference list, without markup."""
    raw = str(text or "")[:FRONT_RAW_CHARS]
    cut = REFERENCES_START_RE.search(raw)
    if cut:
        raw = raw[: cut.start()]
    return strip_markup(raw)[:FRONT_MATTER_CHARS]


def pdf_opening_text(path: object, *, pages: int = 2, timeout_sec: int = 30, max_chars: int = FRONT_MATTER_CHARS) -> str:
    """Text of a PDF's first pages, including running headers and footers.

    Parsed full texts drop page headers and footers, where many publishers
    print the DOI. Pages are separated by form feeds. Returns ``""`` when the
    file or ``pdftotext`` is missing.
    """
    pdf = Path(clean(path)).expanduser() if clean(path) else None
    if pdf is None or not pdf.is_file() or not shutil.which("pdftotext"):
        return ""
    try:
        proc = subprocess.run(
            ["pdftotext", "-f", "1", "-l", str(pages), "-enc", "UTF-8", str(pdf), "-"],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout[:max_chars] if proc.returncode == 0 else ""


def artifact_evidence(artifact: dict) -> dict:
    """Identity evidence in a stored full-text artifact, over all successful parses.

    ``header_dois`` are the DOIs a parser read as the document's own (JATS or
    TEI header, or the first DOI of plain text). ``printed_dois`` are all DOIs
    in the front matter; they confirm the paper's DOI but do not contradict it,
    because page one also prints cited and related DOIs.
    """
    headers: list[dict] = []
    printed: set[str] = set()
    opening = ""
    for extraction in successful_extractions(artifact):
        identity = extraction_identity(extraction)
        front = front_matter(extraction.get("text", ""))
        opening = opening or front
        printed |= printed_dois(front)
        headers.append(
            {
                "backend": clean(extraction.get("backend", "")),
                "format": clean(identity.get("format", "")),
                "doi": normalize_doi(identity.get("doi", "")),
                "title": clean(identity.get("title", "")),
                "pmid": clean(identity.get("pmid", "")),
                "pmcid": normalize_pmcid(identity.get("pmcid", "")),
            }
        )
    return {"headers": headers, "printed_dois": sorted(printed), "opening": opening[:5000]}
