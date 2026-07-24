#!/usr/bin/env python3
"""Deterministic paper-level open-science feature extraction.

The user-facing features are intentionally small and strongly typed:

* ``registered_trial``
* ``open_data``
* ``shared_code``
* ``preregistered``

This module contains only normalization and evidence-classification logic.
Provider retrieval and corpus orchestration live in
``enrich_paper_open_science.py``.
"""

from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import re
from typing import Any, Iterable
from urllib.parse import urlsplit

from pipeline.ingest.metadata_utils import normalize, normalize_doi


ASSERTION_SCHEMA_VERSION = "paper_open_science_assertion_v1"
SUMMARY_SCHEMA_VERSION = "paper_open_science_features_v1"

FEATURE_REGISTERED_TRIAL = "registered_trial"
FEATURE_OPEN_DATA = "open_data"
FEATURE_SHARED_CODE = "shared_code"
FEATURE_PREREGISTERED = "preregistered"
FEATURES = (
    FEATURE_REGISTERED_TRIAL,
    FEATURE_OPEN_DATA,
    FEATURE_SHARED_CODE,
    FEATURE_PREREGISTERED,
)

ASSERTION_COLUMNS = (
    "schema_version",
    "assertion_key",
    "doi",
    "feature",
    "identifier",
    "identifier_type",
    "url",
    "repository",
    "provider",
    "provider_record_id",
    "source_type",
    "source_path",
    "source_section",
    "evidence_text",
    "evidence_method",
    "confidence",
    "retrieval_run_id",
    "retrieved_at_utc",
)

RESOURCE_CANDIDATE_COLUMNS = (
    "doi",
    "resource_id",
    "resource_id_type",
    "resource_url",
    "repository",
    "resource_type_hint",
    "source_type",
    "source_path",
    "source_section",
    "evidence_text",
    "bibliographic_context",
    "shared_data_context",
    "shared_code_context",
    "external_data_context",
    "planned_or_restricted_context",
)

TRIAL_PATTERNS = (
    re.compile(r"\bNCT\d{8}\b", re.IGNORECASE),
    re.compile(r"\bISRCTN\d{8}\b", re.IGNORECASE),
    re.compile(r"\bACTRN\d{14}\b", re.IGNORECASE),
    re.compile(r"\bDRKS\d{8}\b", re.IGNORECASE),
    re.compile(r"\bIRCT[0-9A-Z]{6,}\b", re.IGNORECASE),
    re.compile(r"\bRBR-[A-Z0-9]{3,}\b", re.IGNORECASE),
    re.compile(
        r"\b(?:EudraCT|EU\s*CT|EUCTR)\s*(?:number|no\.?|#|:)?\s*"
        r"(\d{4}-\d{6}-\d{2})\b",
        re.IGNORECASE,
    ),
)
PROSPERO_RE = re.compile(r"\bCRD420\d{6,12}\b", re.IGNORECASE)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

RESOURCE_DOI_PREFIXES = {
    "10.5061/dryad.": ("dryad", "dataset"),
    "10.5281/zenodo.": ("zenodo", "research_resource"),
    "10.6084/m9.figshare.": ("figshare", "research_resource"),
    "10.25384/": ("figshare", "research_resource"),
    "10.25387/": ("figshare", "research_resource"),
    "10.17605/osf.io/": ("osf", "research_resource"),
    "10.7910/dvn/": ("dataverse", "dataset"),
    "10.4121/": ("4tu_research_data", "research_resource"),
    "10.17504/protocols.io.": ("protocols_io", "protocol"),
    "10.7303/syn": ("synapse", "dataset"),
}

REPOSITORY_URL_PATTERNS = (
    ("dryad", "dataset", ("datadryad.org", "doi.org/10.5061/dryad")),
    ("zenodo", "research_resource", ("zenodo.org", "doi.org/10.5281/zenodo")),
    (
        "figshare",
        "research_resource",
        ("figshare.com", "doi.org/10.6084/m9.figshare", "doi.org/10.25384"),
    ),
    ("osf", "research_resource", ("osf.io", "doi.org/10.17605/osf.io")),
    ("dataverse", "dataset", ("dataverse", "doi.org/10.7910/dvn")),
    ("openneuro", "dataset", ("openneuro.org",)),
    ("neurovault", "dataset", ("neurovault.org",)),
    ("brainlife", "dataset", ("brainlife.io",)),
    ("synapse", "dataset", ("synapse.org",)),
    ("nda", "dataset", ("nda.nih.gov",)),
    ("dbgap", "dataset", ("dbgap.ncbi.nlm.nih.gov",)),
    ("geo", "dataset", ("ncbi.nlm.nih.gov/geo",)),
    ("github", "software", ("github.com",)),
    ("gitlab", "software", ("gitlab.com",)),
    ("bitbucket", "software", ("bitbucket.org",)),
)

ACCESSION_PATTERNS = (
    ("geo", "dataset", re.compile(r"\bGSE\d{3,9}\b", re.IGNORECASE)),
    (
        "bioproject",
        "dataset",
        re.compile(r"\b(?:PRJNA|PRJEB|PRJDB)\d{3,10}\b", re.IGNORECASE),
    ),
)

SPACED_RESOURCE_DOI_PATTERNS = (
    (
        "dryad",
        "dataset",
        re.compile(
            r"10\s*\.\s*5061\s*/\s*dryad\s*\.\s*[A-Z0-9][A-Z0-9._-]*",
            re.IGNORECASE,
        ),
    ),
    (
        "zenodo",
        "research_resource",
        re.compile(
            r"10\s*\.\s*5281\s*/\s*zenodo\s*\.\s*\d+",
            re.IGNORECASE,
        ),
    ),
    (
        "figshare",
        "research_resource",
        re.compile(
            r"10\s*\.\s*6084\s*/\s*m9\s*\.\s*figshare\s*\.\s*"
            r"(?:c\s*\.\s*)?\d+(?:\s*\.\s*v\d+)?",
            re.IGNORECASE,
        ),
    ),
)

REGISTRATION_STATEMENT_RE = re.compile(
    r"(?:"
    r"\b(?:this|the|our)\s+(?:clinical\s+)?(?:study|trial)\s+"
    r"(?:was|is|has\s+been)\s+(?:prospectively\s+|retrospectively\s+)?registered\b"
    r"|\b(?:clinical\s+)?trial\s+registration(?:\s+(?:number|identifier|no\.?))?\b"
    r"|\bregistration\s+(?:number|identifier|no\.?)\s*[:#]?"
    r")",
    re.IGNORECASE,
)

PREREGISTRATION_RE = re.compile(
    r"\b(?:pre[\s-]?registered|preregistered|prospectively\s+registered|"
    r"registered\s+a\s+priori|registration\s+was\s+completed\s+before|"
    r"registered\s+before\s+(?:data\s+collection|enrolment|enrollment|analysis))\b",
    re.IGNORECASE,
)
FOCAL_PREREGISTRATION_RE = re.compile(
    r"(?:"
    r"\b(?:this|our|the\s+(?:current|present))\s+"
    r"(?:study|trial|protocol|hypotheses?|analysis\s+plan).{0,120}"
    r"\b(?:pre[\s-]?registered|preregistered|prospectively\s+registered)\b"
    r"|\bthe\s+study(?:\s+and\s+its\s+hypotheses?)?.{0,100}"
    r"\b(?:pre[\s-]?registered|preregistered)\b"
    r"|\b(?:we|the\s+authors?)\s+"
    r"(?:pre[\s-]?registered|preregistered|prospectively\s+registered)\b"
    r"|\b(?:our\s+)?(?:hypotheses?|analysis\s+plan).{0,100}"
    r"\b(?:was|were)\s+(?:pre[\s-]?registered|preregistered)\b"
    r")",
    re.IGNORECASE | re.DOTALL,
)

DATA_SECTION_RE = re.compile(
    r"\b(?:data(?:\s+and\s+materials)?\s+availability|availability\s+of\s+data|"
    r"data\s+sharing|data\s+accessibility|data\s+and\s+code\s+availability)\b",
    re.IGNORECASE,
)
CODE_SECTION_RE = re.compile(
    r"\b(?:code|software|scripts?)\s+availability\b", re.IGNORECASE
)

SHARED_DATA_PATTERNS = (
    re.compile(
        r"\b(?:(?:raw|processed|underlying|supporting|generated|study|our|"
        r"all\s+relevant)\s+(?:data|datasets?)|"
        r"data\s+supporting\s+(?:the\s+)?(?:findings|results|conclusions))"
        r".{0,220}\b(?:publicly\s+|freely\s+)?"
        r"(?:available|accessible|deposited|archived|uploaded|shared)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:data|datasets?).{0,120}\b(?:from|of)\s+"
        r"(?:this|the\s+current|our)\s+study.{0,140}\b"
        r"(?:available|deposited|archived|uploaded|shared)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:deposited|uploaded|archived|made\s+publicly\s+available).{0,140}"
        r"\b(?:data|datasets?|repository|accession)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:data|datasets?).{0,180}\b(?:repository|accession\s+(?:number|id)|"
        r"doi\s*[:/])",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:raw|processed|underlying)\s+(?:data|datasets?).{0,420}\b"
        r"(?:dryad|zenodo|figshare|osf|dataverse|doi(?:\.org)?[/:])",
        re.IGNORECASE | re.DOTALL,
    ),
)

SHARED_CODE_PATTERNS = (
    re.compile(
        r"\b(?:our|custom|study[\s-]specific|analysis|source)\s+"
        r"(?:code|scripts?|software).{0,180}\b"
        r"(?:available|accessible|deposited|shared|github|gitlab|repository)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:all\s+)?custom\s+(?:code|scripts?).{0,160}\bavailable\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:code|scripts?).{0,120}\b(?:used\s+to|for)\s+"
        r"(?:generate|reproduce|produce|analy[sz]e).{0,120}\b"
        r"(?:results?|figures?|analyses?).{0,160}\bavailable\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\bwe\s+(?:have\s+)?(?:developed|wrote|created|published|provide).{0,100}"
        r"\b(?:code|scripts?|software|firmware|tool).{0,180}\b"
        r"(?:github|gitlab|bitbucket|zenodo|osf|repository|available)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:code|codes|scripts?|firmware).{0,140}\b"
        r"(?:used\s+in|for|to\s+reproduce).{0,120}\b"
        r"(?:this\s+study|the\s+(?:datasets?|analyses|results?|findings|figures?)|"
        r"(?:all\s+)?(?:bioinformatic[\s-]based\s+)?analyses)"
        r".{0,180}\b(?:available|accessible|accessed|provided|found|github|"
        r"gitlab|zenodo|osf|supplement)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\bfirmware.{0,100}\b(?:was|were)\s+(?:written|developed|created)"
        r".{0,240}\b(?:github|gitlab|repository)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:custom\s+)?(?:code|scripts?|firmware).{0,180}\b"
        r"(?:as\s+well\s+as|together\s+with|along\s+with).{0,100}\b"
        r"(?:raw|processed|underlying)?\s*(?:data|datasets?).{0,140}\b"
        r"(?:available|accessible|provided|github|figshare|zenodo|osf|doi)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\bcustom\s+(?:[A-Za-z0-9+#.-]+\s+)?"
        r"(?:code|scripts?|software).{0,160}\b"
        r"(?:https?://|doi(?:\.org)?[/:]|dryad|zenodo|figshare|osf|github)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:code|scripts?).{0,140}\b(?:to|for)\s+"
        r"(?:recreate|reproduce|generate|document).{0,100}\b"
        r"(?:tables?|plots?|figures?|results?|analyses?|steps?).{0,160}\b"
        r"(?:available|accessible|accessed|provided|github|gitlab|zenodo|osf|"
        r"repository)",
        re.IGNORECASE | re.DOTALL,
    ),
)

DATA_RESTRICTED_OR_PLANNED_RE = re.compile(
    r"\b(?:(?:data|datasets?).{0,120}(?:not\s+publicly\s+available|"
    r"cannot\s+be\s+shared|available.{0,100}(?:upon|on)\s+"
    r"(?:reasonable\s+)?request|will\s+be\s+(?:made\s+)?available|"
    r"available\s+after|will\s+(?:then\s+)?be\s+"
    r"(?:added|uploaded|deposited|archived|shared))|"
    r"no\s+(?:new|novel)\s+(?:data|datasets?)\s+(?:were|was)\s+"
    r"(?:created|generated|analy[sz]ed))\b",
    re.IGNORECASE,
)
EXTERNAL_DATA_RE = re.compile(
    r"\b(?:we\s+(?:downloaded|obtained|retrieved|used)|"
    r"originally\s+(?:reported|analy[sz]ed)|previous(?:ly)?\s+(?:published|reported)|"
    r"external\s+datasets?|publicly\s+available\s+datasets?\s+from)\b",
    re.IGNORECASE,
)
FOCAL_RESOURCE_RE = re.compile(
    r"\b(?:this\s+study|current\s+study|our\s+(?:study|data|code)|"
    r"custom\s+(?:code|script)|generated\s+(?:data|dataset)|"
    r"(?:data|datasets?).{0,80}(?:has|have|was|were)\s+(?:been\s+)?"
    r"(?:uploaded|deposited|archived|shared)|"
    r"supporting\s+the\s+(?:findings|conclusions)\s+of\s+this\s+(?:study|article))\b",
    re.IGNORECASE,
)
GENERIC_SOFTWARE_RE = re.compile(
    r"\b(?:third[\s-]party|toolbox|software\s+library|python\s+package|"
    r"r\s+package|available\s+library|version\s+\d)\b",
    re.IGNORECASE,
)

BIBLIOGRAPHIC_MARKERS = (
    "<biblstruct",
    "<mixed-citation",
    "citation-string",
    "<ref-list",
    "<listbibl",
)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(value: object) -> str:
    return normalize(value)


def normalized_doi(value: object) -> str:
    return normalize_doi(clean(value)).lower().rstrip(".,;)")


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def assertion_identity(row: dict[str, Any]) -> str:
    fields = (
        "doi",
        "feature",
        "identifier",
        "url",
        "provider",
        "provider_record_id",
        "source_type",
        "evidence_method",
    )
    value = "\x1f".join(clean(row.get(field, "")).casefold() for field in fields)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def finalize_assertion(
    *,
    doi: str,
    feature: str,
    identifier: str = "",
    identifier_type: str = "",
    url: str = "",
    repository: str = "",
    provider: str,
    provider_record_id: str = "",
    source_type: str,
    source_path: str = "",
    source_section: str = "",
    evidence_text: str,
    evidence_method: str,
    confidence: str = "high",
    retrieval_run_id: str,
    retrieved_at_utc: str,
) -> dict[str, str]:
    if feature not in FEATURES:
        raise ValueError(f"Unsupported open-science feature: {feature}")
    row = {column: "" for column in ASSERTION_COLUMNS}
    row.update(
        {
            "schema_version": ASSERTION_SCHEMA_VERSION,
            "doi": normalized_doi(doi),
            "feature": feature,
            "identifier": clean(identifier),
            "identifier_type": clean(identifier_type),
            "url": clean(url),
            "repository": clean(repository).lower(),
            "provider": clean(provider).lower(),
            "provider_record_id": clean(provider_record_id),
            "source_type": clean(source_type),
            "source_path": clean(source_path),
            "source_section": clean(source_section),
            "evidence_text": " ".join(clean(evidence_text).split())[:1200],
            "evidence_method": clean(evidence_method),
            "confidence": clean(confidence).lower(),
            "retrieval_run_id": clean(retrieval_run_id),
            "retrieved_at_utc": clean(retrieved_at_utc),
        }
    )
    row["assertion_key"] = assertion_identity(row)
    return row


def best_fulltext(artifact: dict[str, Any]) -> str:
    extractions = artifact.get("extractions") or []
    best_backend = clean(artifact.get("best_backend"))
    for extraction in extractions:
        if (
            clean(extraction.get("backend")) == best_backend
            and clean(extraction.get("text"))
        ):
            return clean(extraction.get("text"))
    for extraction in extractions:
        if clean(extraction.get("text")):
            return clean(extraction.get("text"))
    return ""


def load_best_fulltext(paths: Iterable[Path]) -> tuple[str, str, str]:
    best_text = ""
    best_path = ""
    last_error = ""
    for path in paths:
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
            candidate = best_fulltext(artifact)
        except (OSError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            continue
        if len(candidate) > len(best_text):
            best_text = candidate
            best_path = str(path)
    return best_text, best_path, last_error


def split_paths(value: object) -> list[Path]:
    return [Path(item.strip()) for item in clean(value).split(" | ") if item.strip()]


def strip_markup(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(text).split())


def normalized_url(value: str) -> str:
    return html.unescape(value).rstrip(".,;:)]}")


def doi_from_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ""
    if parsed.hostname and parsed.hostname.casefold() in {
        "doi.org",
        "dx.doi.org",
        "www.doi.org",
    }:
        return normalized_doi(parsed.path.lstrip("/"))
    return ""


def doi_repository(doi: str) -> tuple[str, str] | None:
    lowered = normalized_doi(doi)
    for prefix, classification in RESOURCE_DOI_PREFIXES.items():
        if lowered.startswith(prefix):
            return classification
    return None


def valid_resource_doi(value: str) -> bool:
    doi = normalized_doi(value)
    if not doi or doi_repository(doi) is None:
        return False
    if any(character in doi for character in (" ", "%", "&", "<", ">")):
        return False
    if doi.startswith("10.5061/dryad."):
        return bool(doi.removeprefix("10.5061/dryad."))
    if doi.startswith("10.5281/zenodo."):
        return bool(re.fullmatch(r"10\.5281/zenodo\.\d+", doi))
    if doi.startswith("10.6084/m9.figshare."):
        return bool(
            re.fullmatch(
                r"10\.6084/m9\.figshare\.(?:c\.)?\d+(?:\.v\d+)?",
                doi,
            )
        )
    if doi.startswith("10.17605/osf.io/"):
        return bool(re.fullmatch(r"10\.17605/osf\.io/[a-z0-9]+", doi))
    return True


def compact_spaced_resource_doi(value: str) -> str:
    return normalized_doi(re.sub(r"\s+", "", value))


def url_repository(url: str) -> tuple[str, str] | None:
    lowered = normalized_url(url).casefold()
    if "github.com/kermitt2/grobid" in lowered:
        return None
    for repository, resource_type, needles in REPOSITORY_URL_PATTERNS:
        if any(needle in lowered for needle in needles):
            return repository, resource_type
    return None


def useful_repository_url(url: str, repository: str) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    path = parsed.path.strip("/")
    if repository in {"github", "gitlab", "bitbucket"}:
        return bool(path)
    if repository == "openneuro":
        return "/datasets/" in parsed.path.casefold()
    if repository == "osf":
        return bool(path) and not path.casefold().startswith(("preprints/", "search"))
    return True


def nearest_heading(raw_text: str, position: int) -> str:
    before = raw_text[max(0, position - 4000) : position]
    matches = list(
        re.finditer(
            r"<(?:head|title)(?:\s[^>]*)?>(.*?)</(?:head|title)>",
            before,
            re.IGNORECASE | re.DOTALL,
        )
    )
    if not matches:
        return ""
    return strip_markup(matches[-1].group(1))[:240]


def evidence_window(
    raw_text: str,
    start: int,
    end: int,
    *,
    radius: int = 650,
) -> tuple[str, str, bool]:
    raw = raw_text[max(0, start - radius) : min(len(raw_text), end + radius)]
    heading = nearest_heading(raw_text, start)
    bibliographic = is_bibliographic_position(raw_text, start, heading)
    return strip_markup(raw), heading, bibliographic


def is_bibliographic_position(raw_text: str, position: int, heading: str = "") -> bool:
    if re.fullmatch(
        r"\s*(?:references|bibliography|literature\s+cited)\s*",
        heading,
        re.IGNORECASE,
    ):
        return True
    before = raw_text[max(0, position - 12000) : position].casefold()
    element_pairs = (
        ("<ref-list", "</ref-list>"),
        ("<listbibl", "</listbibl>"),
        ("<biblstruct", "</biblstruct>"),
        ("<mixed-citation", "</mixed-citation>"),
        ("<element-citation", "</element-citation>"),
    )
    return any(
        before.rfind(opening) > before.rfind(closing)
        for opening, closing in element_pairs
    )


def extract_trial_identifiers(value: str) -> list[tuple[str, int, int]]:
    out: list[tuple[str, int, int]] = []
    seen: set[tuple[str, int]] = set()
    for pattern in TRIAL_PATTERNS:
        for match in pattern.finditer(value):
            identifier = match.group(1) if match.lastindex else match.group(0)
            identifier = re.sub(r"\s+", "", identifier).upper()
            key = (identifier, match.start())
            if identifier and key not in seen:
                seen.add(key)
                out.append((identifier, match.start(), match.end()))
    return sorted(out, key=lambda item: item[1])


def registry_for_trial_id(identifier: str) -> str:
    value = identifier.upper()
    if value.startswith("NCT"):
        return "clinicaltrials_gov"
    if value.startswith("ISRCTN"):
        return "isrctn"
    if value.startswith("ACTRN"):
        return "anzctr"
    if value.startswith("DRKS"):
        return "drks"
    if value.startswith("IRCT"):
        return "irct"
    if value.startswith("RBR-"):
        return "rebec"
    if re.fullmatch(r"\d{4}-\d{6}-\d{2}", value):
        return "eudract"
    return "trial_registry"


def trial_url(identifier: str) -> str:
    value = identifier.upper()
    if value.startswith("NCT"):
        return f"https://clinicaltrials.gov/study/{value}"
    if value.startswith("ISRCTN"):
        return f"https://www.isrctn.com/{value}"
    return ""


def is_registration_statement(context: str, heading: str = "") -> bool:
    text = f"{heading} {context}"
    return bool(REGISTRATION_STATEMENT_RE.search(text))


def is_preregistration_statement(context: str, heading: str = "") -> bool:
    text = f"{heading} {context}"
    return bool(PREREGISTRATION_RE.search(text))


def is_focal_preregistration_statement(context: str, heading: str = "") -> bool:
    text = f"{heading} {context}"
    return bool(
        PREREGISTRATION_RE.search(text) and FOCAL_PREREGISTRATION_RE.search(text)
    )


def is_negated_match(raw_text: str, match_start: int) -> bool:
    prefix = strip_markup(raw_text[max(0, match_start - 60) : match_start])
    return bool(
        re.search(
            r"\b(?:not|never|was\s+not|were\s+not|is\s+not|are\s+not|"
            r"wasn't|weren't|isn't|aren't)\s*$",
            prefix,
            re.IGNORECASE,
        )
    )


def has_nonnegated_preregistration(value: str) -> bool:
    return any(
        not is_negated_match(value, match.start())
        for match in PREREGISTRATION_RE.finditer(value)
    )


def data_context_flags(
    context: str,
    heading: str,
    *,
    bibliographic: bool,
) -> dict[str, bool]:
    text = f"{heading} {context}"
    planned_or_restricted = bool(DATA_RESTRICTED_OR_PLANNED_RE.search(text))
    external = bool(EXTERNAL_DATA_RE.search(text))
    focal = bool(FOCAL_RESOURCE_RE.search(text))
    strong = any(pattern.search(text) for pattern in SHARED_DATA_PATTERNS)
    in_data_section = bool(DATA_SECTION_RE.search(heading))
    shared = (
        not planned_or_restricted
        and not bibliographic
        and not (external and not focal)
        and (strong or (in_data_section and re.search(r"\bdata(?:sets?)?\b", text, re.I)))
    )
    return {
        "shared": bool(shared),
        "external": external,
        "planned_or_restricted": planned_or_restricted,
        "focal": focal,
    }


def code_context_flags(
    context: str,
    heading: str,
    *,
    bibliographic: bool,
) -> dict[str, bool]:
    text = f"{heading} {context}"
    focal = bool(FOCAL_RESOURCE_RE.search(text))
    strong = any(pattern.search(text) for pattern in SHARED_CODE_PATTERNS)
    in_code_section = bool(CODE_SECTION_RE.search(heading))
    generic = bool(GENERIC_SOFTWARE_RE.search(text))
    shared = (
        not bibliographic
        and strong
        and not (generic and not focal)
    )
    return {"shared": bool(shared), "focal": focal, "generic": generic}


def local_assertions_and_resource_candidates(
    *,
    doi: str,
    title: str,
    abstract: str,
    publication_type: str,
    fulltext: str,
    fulltext_path: str,
    retrieval_run_id: str,
    retrieved_at_utc: str,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    assertions: list[dict[str, str]] = []
    candidates: list[dict[str, Any]] = []
    sources = [
        ("title_abstract", f"{clean(title)}\n{clean(abstract)}", ""),
    ]
    if fulltext:
        sources.append(("fulltext", fulltext, fulltext_path))

    for source_type, raw_text, source_path in sources:
        if not raw_text:
            continue
        for identifier, start, end in extract_trial_identifiers(raw_text):
            context, heading, bibliographic = evidence_window(raw_text, start, end)
            if bibliographic or not is_registration_statement(context, heading):
                continue
            repository = registry_for_trial_id(identifier)
            assertions.append(
                finalize_assertion(
                    doi=doi,
                    feature=FEATURE_REGISTERED_TRIAL,
                    identifier=identifier,
                    identifier_type="trial_registry_id",
                    url=trial_url(identifier),
                    repository=repository,
                    provider=source_type,
                    provider_record_id=identifier,
                    source_type=source_type,
                    source_path=source_path,
                    source_section=heading,
                    evidence_text=context,
                    evidence_method="explicit_focal_trial_registration_statement",
                    retrieval_run_id=retrieval_run_id,
                    retrieved_at_utc=retrieved_at_utc,
                )
            )
            if is_preregistration_statement(context, heading):
                assertions.append(
                    finalize_assertion(
                        doi=doi,
                        feature=FEATURE_PREREGISTERED,
                        identifier=identifier,
                        identifier_type="trial_registry_id",
                        url=trial_url(identifier),
                        repository=repository,
                        provider=source_type,
                        provider_record_id=identifier,
                        source_type=source_type,
                        source_path=source_path,
                        source_section=heading,
                        evidence_text=context,
                        evidence_method="explicit_prospective_trial_registration_statement",
                        retrieval_run_id=retrieval_run_id,
                        retrieved_at_utc=retrieved_at_utc,
                    )
                )

        for match in PREREGISTRATION_RE.finditer(raw_text):
            if is_negated_match(raw_text, match.start()):
                continue
            context, heading, bibliographic = evidence_window(
                raw_text, match.start(), match.end()
            )
            if bibliographic or not is_focal_preregistration_statement(
                context, heading
            ):
                continue
            identifier = ""
            identifier_type = ""
            repository = ""
            url = ""
            prospero = PROSPERO_RE.search(context)
            if prospero:
                identifier = prospero.group(0).upper()
                identifier_type = "prospero_id"
                repository = "prospero"
            for url_match in URL_RE.finditer(context):
                candidate_url = normalized_url(url_match.group(0))
                lowered = candidate_url.casefold()
                if any(
                    value in lowered
                    for value in ("osf.io", "aspredicted.org", "prospero")
                ):
                    url = candidate_url
                    repository = (
                        "osf"
                        if "osf.io" in lowered
                        else "aspredicted"
                        if "aspredicted.org" in lowered
                        else "prospero"
                    )
                    identifier = identifier or url
                    identifier_type = identifier_type or "url"
                    break
            assertions.append(
                finalize_assertion(
                    doi=doi,
                    feature=FEATURE_PREREGISTERED,
                    identifier=identifier,
                    identifier_type=identifier_type,
                    url=url,
                    repository=repository,
                    provider=source_type,
                    provider_record_id=identifier,
                    source_type=source_type,
                    source_path=source_path,
                    source_section=heading,
                    evidence_text=context,
                    evidence_method="explicit_preregistration_statement",
                    retrieval_run_id=retrieval_run_id,
                    retrieved_at_utc=retrieved_at_utc,
                )
            )

        resource_matches: list[tuple[str, str, str, str, int, int]] = []
        for match in URL_RE.finditer(raw_text):
            url = normalized_url(match.group(0))
            resource_doi = doi_from_url(url)
            classification = (
                doi_repository(resource_doi)
                if resource_doi
                else url_repository(url)
            )
            if classification is None:
                continue
            repository, type_hint = classification
            if not useful_repository_url(url, repository):
                continue
            if resource_doi and not valid_resource_doi(resource_doi):
                continue
            resource_matches.append(
                (
                    resource_doi or url,
                    "doi" if resource_doi else "url",
                    url,
                    repository,
                    match.start(),
                    match.end(),
                )
            )
        for match in DOI_RE.finditer(raw_text):
            resource_doi = normalized_doi(match.group(0))
            classification = doi_repository(resource_doi)
            if (
                classification is None
                or not valid_resource_doi(resource_doi)
                or resource_doi == normalized_doi(doi)
            ):
                continue
            repository, _type_hint = classification
            resource_matches.append(
                (
                    resource_doi,
                    "doi",
                    f"https://doi.org/{resource_doi}",
                    repository,
                    match.start(),
                    match.end(),
                )
            )
        for repository, type_hint, pattern in SPACED_RESOURCE_DOI_PATTERNS:
            for match in pattern.finditer(raw_text):
                resource_doi = compact_spaced_resource_doi(match.group(0))
                if (
                    not valid_resource_doi(resource_doi)
                    or resource_doi == normalized_doi(doi)
                ):
                    continue
                resource_matches.append(
                    (
                        resource_doi,
                        "doi",
                        f"https://doi.org/{resource_doi}",
                        repository,
                        match.start(),
                        match.end(),
                    )
                )
        for repository, type_hint, pattern in ACCESSION_PATTERNS:
            for match in pattern.finditer(raw_text):
                resource_matches.append(
                    (
                        match.group(0).upper(),
                        "accession",
                        "",
                        repository,
                        match.start(),
                        match.end(),
                    )
                )

        seen_resources: set[tuple[str, str]] = set()
        for resource_id, id_type, url, repository, start, end in resource_matches:
            identity = (resource_id.casefold(), repository)
            if identity in seen_resources:
                continue
            seen_resources.add(identity)
            context, heading, bibliographic = evidence_window(raw_text, start, end)
            data_flags = data_context_flags(
                context, heading, bibliographic=bibliographic
            )
            code_flags = code_context_flags(
                context, heading, bibliographic=bibliographic
            )
            type_hint = (
                url_repository(url)[1]
                if url and url_repository(url)
                else doi_repository(resource_id)[1]
                if id_type == "doi" and doi_repository(resource_id)
                else "dataset"
                if repository in {"geo", "bioproject"}
                else "research_resource"
            )
            candidates.append(
                {
                    "doi": normalized_doi(doi),
                    "resource_id": resource_id,
                    "resource_id_type": id_type,
                    "resource_url": url,
                    "repository": repository,
                    "resource_type_hint": type_hint,
                    "source_type": source_type,
                    "source_path": source_path,
                    "source_section": heading,
                    "evidence_text": context[:1200],
                    "bibliographic_context": bibliographic,
                    "shared_data_context": data_flags["shared"],
                    "shared_code_context": code_flags["shared"],
                    "external_data_context": data_flags["external"],
                    "planned_or_restricted_context": data_flags[
                        "planned_or_restricted"
                    ],
                }
            )
            if data_flags["shared"] and type_hint in {
                "dataset",
                "research_resource",
            }:
                assertions.append(
                    finalize_assertion(
                        doi=doi,
                        feature=FEATURE_OPEN_DATA,
                        identifier=resource_id,
                        identifier_type=id_type,
                        url=url,
                        repository=repository,
                        provider=source_type,
                        provider_record_id=resource_id,
                        source_type=source_type,
                        source_path=source_path,
                        source_section=heading,
                        evidence_text=context,
                        evidence_method="explicit_public_study_data_repository_statement",
                        retrieval_run_id=retrieval_run_id,
                        retrieved_at_utc=retrieved_at_utc,
                    )
                )
            if code_flags["shared"] and type_hint != "protocol":
                assertions.append(
                    finalize_assertion(
                        doi=doi,
                        feature=FEATURE_SHARED_CODE,
                        identifier=resource_id,
                        identifier_type=id_type,
                        url=url,
                        repository=repository,
                        provider=source_type,
                        provider_record_id=resource_id,
                        source_type=source_type,
                        source_path=source_path,
                        source_section=heading,
                        evidence_text=context,
                        evidence_method="explicit_public_study_code_repository_statement",
                        retrieval_run_id=retrieval_run_id,
                        retrieved_at_utc=retrieved_at_utc,
                    )
                )

    return deduplicate_assertions(assertions), deduplicate_resource_candidates(candidates)


def deduplicate_assertions(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        key = clean(row.get("assertion_key", ""))
        if key:
            out[key] = row
    return sorted(
        out.values(),
        key=lambda row: (
            row["doi"],
            row["feature"],
            row["identifier"].casefold(),
            row["provider"],
        ),
    )


def deduplicate_resource_candidates(
    rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            clean(row.get("doi", "")).casefold(),
            clean(row.get("resource_id", "")).casefold(),
            clean(row.get("repository", "")).casefold(),
            clean(row.get("source_type", "")).casefold(),
        )
        previous = out.get(key)
        if previous is None:
            out[key] = row
            continue
        previous_score = sum(
            bool(previous.get(field))
            for field in ("shared_data_context", "shared_code_context")
        )
        score = sum(
            bool(row.get(field))
            for field in ("shared_data_context", "shared_code_context")
        )
        if score > previous_score:
            out[key] = row
    return sorted(
        out.values(),
        key=lambda row: (
            row["doi"],
            row["repository"],
            row["resource_id"].casefold(),
        ),
    )


def parse_partial_date(value: object) -> tuple[dt.date, dt.date] | None:
    text = clean(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        date = dt.date.fromisoformat(text)
        return date, date
    if re.fullmatch(r"\d{4}-\d{2}", text):
        year, month = (int(part) for part in text.split("-"))
        last_day = calendar.monthrange(year, month)[1]
        return dt.date(year, month, 1), dt.date(year, month, last_day)
    if re.fullmatch(r"\d{4}", text):
        year = int(text)
        return dt.date(year, 1, 1), dt.date(year, 12, 31)
    return None


def prospective_registration(
    first_submitted_date: object,
    study_start_date: object,
) -> bool | None:
    submitted = parse_partial_date(first_submitted_date)
    started = parse_partial_date(study_start_date)
    if submitted is None or started is None:
        return None
    submitted_date = submitted[0]
    start_earliest, start_latest = started
    if submitted_date < start_earliest:
        return True
    if submitted_date > start_latest:
        return False
    return None


def repository_identifier_url(repository: str, identifier: str) -> str:
    repo = clean(repository).casefold()
    value = clean(identifier)
    if repo == "geo" and re.fullmatch(r"GSE\d+", value, re.IGNORECASE):
        return f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={value.upper()}"
    if repo == "bioproject" and re.fullmatch(
        r"(?:PRJNA|PRJEB|PRJDB)\d+", value, re.IGNORECASE
    ):
        return f"https://www.ncbi.nlm.nih.gov/bioproject/{value.upper()}"
    return ""
