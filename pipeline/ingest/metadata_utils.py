#!/usr/bin/env python3
"""Shared bibliographic metadata, open-access, and PDF retrieval helpers."""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import random
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_METADATA_PROVIDER_ORDER = ["pubmed", "pmc", "unpaywall", "crossref", "openalex", "semantic_scholar"]
PAPER_METADATA_SCHEMA_VERSION = "paper_metadata_v2"
PAPER_METADATA_FIELDS = [
    "study_journal",
    "publication_type",
    "trial_registry_ids",
    "publication_date",
    "journal_issn",
    "journal_eissn",
    "publisher",
    "mesh_terms",
    "keywords",
    "funders",
    "grant_ids",
    "related_dois",
    "publication_relations",
    "is_retracted",
    "has_correction",
    "language",
    "semantic_scholar_id",
]
PLACEHOLDER_EMAILS = {
    "test@example.com",
    "you@example.com",
    "your_real_email@domain.org",
    "your_email@example.com",
}
TRIAL_REGISTRY_PATTERNS = [
    re.compile(r"\bNCT\d{8}\b", re.IGNORECASE),
    re.compile(r"\bISRCTN\d{8}\b", re.IGNORECASE),
    re.compile(r"\bACTRN\d{14}\b", re.IGNORECASE),
    re.compile(r"\bDRKS\d{8}\b", re.IGNORECASE),
    re.compile(r"\bIRCT[0-9A-Z]{6,}\b", re.IGNORECASE),
    re.compile(r"\bRBR-[A-Z0-9]{3,}\b", re.IGNORECASE),
    re.compile(r"\b(?:EudraCT|EU\s*CT|EUCTR)\s*(?:number|no\.?|#|:)?\s*(\d{4}-\d{6}-\d{2})\b", re.IGNORECASE),
]
DOI_FIND_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_doi(raw: str) -> str:
    text = normalize(raw)
    if not text:
        return ""
    if text.lower().startswith("doi:"):
        text = text[4:]
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
    ):
        if text.lower().startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip()


def usable_email(value: str) -> str:
    email = normalize(value)
    if "@" not in email:
        return ""
    if email.lower() in PLACEHOLDER_EMAILS:
        return ""
    return email


def parse_simple_yaml(path: Path) -> dict:
    if not path.exists():
        return {}

    out: Dict[str, dict] = {}
    current = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" ") and stripped.endswith(":"):
            current = stripped[:-1]
            out[current] = {}
            continue
        if current and line.startswith("  ") and ":" in stripped:
            key, value = stripped.split(":", 1)
            value = value.strip().strip('"').strip("'")
            parsed: object = value
            if value == "":
                parsed = ""
            else:
                try:
                    parsed = float(value) if "." in value else int(value)
                except ValueError:
                    parsed = value
            out[current][key.strip()] = parsed
    return out


def merge_simple_config(base: dict, override: dict) -> dict:
    merged: Dict[str, dict] = {
        section: values.copy() if isinstance(values, dict) else values
        for section, values in base.items()
    }
    for section, values in override.items():
        if not isinstance(values, dict):
            if values != "":
                merged[section] = values
            continue
        current = merged.setdefault(section, {})
        if not isinstance(current, dict):
            current = {}
            merged[section] = current
        for key, value in values.items():
            if value != "":
                current[key] = value
    return merged


def load_config(path: Path) -> dict:
    config = parse_simple_yaml(path)
    local_path = path.parent / "config.local.yaml"
    if path.name == "config.example.yaml" and local_path.exists():
        config = merge_simple_config(config, parse_simple_yaml(local_path))
    return config


def read_float(maybe_value: object, default: float) -> float:
    if maybe_value is None:
        return default
    try:
        return float(maybe_value)
    except Exception:
        return default


def read_int(maybe_value: object, default: int) -> int:
    if maybe_value is None:
        return default
    try:
        return int(maybe_value)
    except Exception:
        return default


class RateLimitedHttpClient:
    def __init__(
        self,
        rps: float,
        max_retries: int,
        timeout_sec: int = 40,
        max_retry_after_sec: int = 120,
        user_agent: str = "kg-pipeline/0.1",
    ):
        self.rps = max(0.01, rps)
        self.min_interval = 1.0 / self.rps
        self.max_retries = max_retries
        self.timeout_sec = timeout_sec
        self.max_retry_after_sec = max(0, max_retry_after_sec)
        self.user_agent = user_agent
        self._last_request_ts = 0.0

    def _wait_for_slot(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_ts
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def _request_bytes(self, url: str, headers: Optional[Dict[str, str]] = None) -> bytes:
        req_headers = {"User-Agent": self.user_agent}
        if headers:
            req_headers.update(headers)
        req = Request(url, headers=req_headers)
        with urlopen(req, timeout=self.timeout_sec) as response:
            self._last_request_ts = time.monotonic()
            return response.read()

    def get_bytes(self, url: str, headers: Optional[Dict[str, str]] = None) -> bytes:
        backoff = 2.5
        for attempt in range(self.max_retries + 1):
            self._wait_for_slot()
            try:
                return self._request_bytes(url=url, headers=headers)
            except HTTPError as err:
                self._last_request_ts = time.monotonic()
                retryable = err.code in {429, 500, 502, 503, 504}
                if attempt >= self.max_retries or not retryable:
                    raise
                retry_after = err.headers.get("Retry-After") if err.headers else None
                if retry_after and retry_after.isdigit():
                    delay = max(backoff, float(retry_after))
                else:
                    delay = backoff
                if self.max_retry_after_sec > 0 and delay > self.max_retry_after_sec:
                    raise RuntimeError(f"retry_after_exceeded:{delay:.1f}s")
                time.sleep(delay + random.uniform(0.0, 0.35))
                backoff *= 1.7
            except URLError:
                self._last_request_ts = time.monotonic()
                if attempt >= self.max_retries:
                    raise
                time.sleep(backoff + random.uniform(0.0, 0.35))
                backoff *= 1.7
        raise RuntimeError("Unreachable retry state")

    def get_bytes_once(self, url: str, headers: Optional[Dict[str, str]] = None) -> bytes:
        self._wait_for_slot()
        return self._request_bytes(url=url, headers=headers)

    def get_json(self, url: str, params: Optional[Dict[str, object]] = None, headers: Optional[Dict[str, str]] = None) -> dict:
        query = urlencode({k: v for k, v in (params or {}).items() if v is not None}, doseq=True)
        full_url = f"{url}?{query}" if query else url
        body = self.get_bytes(url=full_url, headers=headers)
        return json.loads(body.decode("utf-8"))


def authors_from_openalex(authorships: Iterable[dict], max_names: int = 10) -> str:
    names = []
    for authorship in authorships:
        author_obj = authorship.get("author") if isinstance(authorship, dict) else None
        if isinstance(author_obj, dict):
            name = normalize(author_obj.get("display_name", ""))
            if name:
                names.append(name)
        if len(names) >= max_names:
            break
    return "; ".join(names)


def authors_from_crossref(authors: Iterable[dict], max_names: int = 10) -> str:
    names = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        given = normalize(author.get("given", ""))
        family = normalize(author.get("family", ""))
        name = " ".join([part for part in (given, family) if part])
        if not name:
            name = normalize(author.get("name", ""))
        if name:
            names.append(name)
        if len(names) >= max_names:
            break
    return "; ".join(names)


def authors_from_unpaywall(authors: Iterable[dict], max_names: int = 10) -> str:
    names = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        name = normalize(author.get("raw_author_name", ""))
        if name:
            names.append(name)
        if len(names) >= max_names:
            break
    return "; ".join(names)


def authors_from_semantic_scholar(authors: Iterable[dict], max_names: int = 10) -> str:
    names = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        name = normalize(author.get("name", ""))
        if name:
            names.append(name)
        if len(names) >= max_names:
            break
    return "; ".join(names)


def strip_markup(value: object) -> str:
    text = normalize(value)
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"\s*<\s*subtitle\b[^>]*>\s*", ": ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*</\s*subtitle\s*>\s*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_dangling_title_colon(value: object) -> str:
    text = strip_markup(value)
    if text.endswith(":"):
        return text.rstrip(":").rstrip()
    return text


def first_list_value(value: object) -> str:
    if isinstance(value, list):
        for item in value:
            text = strip_markup(item)
            if text:
                return text
        return ""
    return strip_markup(value)


def crossref_title_with_subtitle(item: dict, fallback: object = "") -> str:
    title = first_list_value(item.get("title", ""))
    subtitle = first_list_value(item.get("subtitle", ""))
    if title and subtitle:
        separator = " " if title.rstrip().endswith((".", "?", "!", ":", ";")) else ": "
        return f"{title}{separator}{subtitle}".strip()
    return strip_dangling_title_colon(title) or strip_markup(fallback)


def join_list_values(value: object) -> str:
    values: List[str] = []
    raw_values = value if isinstance(value, list) else [value]
    for item in raw_values:
        text = strip_markup(item)
        if text and text not in values:
            values.append(text)
    return " | ".join(values)


def join_unique(values: Iterable[object]) -> str:
    out: List[str] = []
    for value in values:
        text = strip_markup(value)
        if text and text not in out:
            out.append(text)
    return " | ".join(out)


def extract_trial_registry_ids(*values: object) -> str:
    ids: List[str] = []

    def scan(value: object) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            for nested in value.values():
                scan(nested)
            return
        if isinstance(value, (list, tuple, set)):
            for nested in value:
                scan(nested)
            return
        text = strip_markup(value)
        for pattern in TRIAL_REGISTRY_PATTERNS:
            for match in pattern.finditer(text):
                identifier = match.group(1) if match.lastindex else match.group(0)
                identifier = re.sub(r"\s+", "", identifier).upper()
                if identifier and identifier not in ids:
                    ids.append(identifier)

    for value in values:
        scan(value)
    return " | ".join(ids)


def extract_dois(*values: object) -> str:
    out: List[str] = []

    def scan(value: object) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            for nested in value.values():
                scan(nested)
            return
        if isinstance(value, (list, tuple, set)):
            for nested in value:
                scan(nested)
            return
        for match in DOI_FIND_RE.findall(strip_markup(value)):
            doi = normalize_doi(match).rstrip(".,;)")
            if doi and doi not in out:
                out.append(doi)

    for value in values:
        scan(value)
    return " | ".join(out)


def normalize_date_parts(year: object, month: object = "", day: object = "") -> str:
    year_text = normalize(year)
    if not re.fullmatch(r"\d{4}", year_text):
        return ""

    month_map = {
        "jan": "01",
        "feb": "02",
        "mar": "03",
        "apr": "04",
        "may": "05",
        "jun": "06",
        "jul": "07",
        "aug": "08",
        "sep": "09",
        "oct": "10",
        "nov": "11",
        "dec": "12",
    }
    month_text = normalize(month)
    if month_text:
        month_norm = month_map.get(month_text[:3].lower(), month_text)
        if month_norm.isdigit() and 1 <= int(month_norm) <= 12:
            month_text = f"{int(month_norm):02d}"
        else:
            month_text = ""
    day_text = normalize(day)
    if day_text and day_text.isdigit() and 1 <= int(day_text) <= 31:
        day_text = f"{int(day_text):02d}"
    else:
        day_text = ""
    if month_text and day_text:
        return f"{year_text}-{month_text}-{day_text}"
    if month_text:
        return f"{year_text}-{month_text}"
    return year_text


def date_from_crossref_date(*values: object) -> str:
    for value in values:
        if not isinstance(value, dict):
            continue
        date_parts = value.get("date-parts")
        if not isinstance(date_parts, list) or not date_parts:
            continue
        first = date_parts[0]
        if isinstance(first, list) and first:
            return normalize_date_parts(
                first[0],
                first[1] if len(first) > 1 else "",
                first[2] if len(first) > 2 else "",
            )
    return ""


def bool_text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = normalize(value).lower()
    if text in {"true", "yes", "1"}:
        return "true"
    if text in {"false", "no", "0"}:
        return "false"
    return ""


def publication_date_from_pubmed_date_element(element: Optional[ET.Element]) -> str:
    if element is None:
        return ""
    date = normalize_date_parts(
        element.findtext("Year"),
        element.findtext("Month"),
        element.findtext("Day"),
    )
    if date:
        return date
    medline_date = normalize(element.findtext("MedlineDate"))
    match = re.search(r"\b((?:18|19|20|21)\d{2})(?:\s+([A-Za-z]{3,9}))?(?:\s+(\d{1,2}))?\b", medline_date)
    if match:
        return normalize_date_parts(match.group(1), match.group(2) or "", match.group(3) or "")
    return ""


def publication_date_from_pubmed_article(article: ET.Element) -> str:
    for element in article.findall(".//Article/ArticleDate"):
        date = publication_date_from_pubmed_date_element(element)
        if date:
            return date
    for path in (
        ".//Article/Journal/JournalIssue/PubDate",
        ".//PubmedData/History/PubMedPubDate",
    ):
        for element in article.findall(path):
            date = publication_date_from_pubmed_date_element(element)
            if date:
                return date
    return ""


def issns_from_pubmed_article(article: ET.Element) -> Tuple[str, str]:
    print_issn = ""
    electronic_issn = ""
    fallback_issns: List[str] = []
    for item in article.findall(".//Article/Journal/ISSN"):
        issn = normalize("".join(item.itertext()))
        if not issn:
            continue
        issn_type = normalize(item.attrib.get("IssnType", "")).lower()
        if issn_type == "electronic" and not electronic_issn:
            electronic_issn = issn
        elif issn_type == "print" and not print_issn:
            print_issn = issn
        elif issn not in fallback_issns:
            fallback_issns.append(issn)
    linking = normalize(article.findtext(".//MedlineJournalInfo/ISSNLinking"))
    if not print_issn:
        print_issn = linking or (fallback_issns[0] if fallback_issns else "")
    if not electronic_issn:
        electronic_issn = next((value for value in fallback_issns if value != print_issn), "")
    return print_issn, electronic_issn


def journal_from_openalex_work(work: dict) -> str:
    source = source_from_openalex_work(work)
    return normalize(source.get("display_name", "")) if source else ""


def source_from_openalex_work(work: dict) -> dict:
    def source_from_location(location: object) -> dict:
        if not isinstance(location, dict):
            return {}
        source = location.get("source", {})
        return source if isinstance(source, dict) else {}

    primary = source_from_location(work.get("primary_location", {}))
    if normalize(primary.get("display_name", "")):
        return primary
    for location in work.get("locations", []) if isinstance(work.get("locations", []), list) else []:
        source = source_from_location(location)
        if normalize(source.get("display_name", "")):
            return source
    return {}


def issns_from_openalex_work(work: dict) -> Tuple[str, str]:
    source = source_from_openalex_work(work)
    if not source:
        return "", ""
    issn_l = normalize(source.get("issn_l", ""))
    issns = source.get("issn", [])
    values = [normalize(value) for value in issns] if isinstance(issns, list) else [normalize(issns)]
    values = [value for value in values if value]
    journal_issn = issn_l or (values[0] if values else "")
    eissn = next((value for value in values if value != journal_issn), "")
    return journal_issn, eissn


def publisher_from_openalex_work(work: dict) -> str:
    source = source_from_openalex_work(work)
    if not source:
        return ""
    return (
        normalize(source.get("host_organization_name", ""))
        or normalize(source.get("publisher", ""))
        or normalize(source.get("host_organization", ""))
    )


def mesh_terms_from_openalex_work(work: dict) -> str:
    values: List[str] = []
    mesh = work.get("mesh", []) if isinstance(work, dict) else []
    for item in mesh if isinstance(mesh, list) else []:
        if not isinstance(item, dict):
            continue
        descriptor = normalize(item.get("descriptor_name", ""))
        qualifier = normalize(item.get("qualifier_name", ""))
        value = f"{descriptor} / {qualifier}" if descriptor and qualifier else descriptor or qualifier
        if value and value not in values:
            values.append(value)
    return " | ".join(values)


def keywords_from_openalex_work(work: dict, max_values: int = 20) -> str:
    values: List[str] = []
    keywords = work.get("keywords", []) if isinstance(work, dict) else []
    for item in keywords if isinstance(keywords, list) else []:
        if isinstance(item, dict):
            value = normalize(item.get("keyword", "")) or normalize(item.get("display_name", ""))
        else:
            value = normalize(item)
        if value and value not in values:
            values.append(value)
        if len(values) >= max_values:
            return " | ".join(values)
    concepts = work.get("concepts", []) if isinstance(work, dict) else []
    for item in concepts if isinstance(concepts, list) else []:
        if not isinstance(item, dict):
            continue
        value = normalize(item.get("display_name", ""))
        if value and value not in values:
            values.append(value)
        if len(values) >= max_values:
            break
    return " | ".join(values)


def funding_from_openalex_work(work: dict) -> Tuple[str, str]:
    funders: List[str] = []
    grant_ids: List[str] = []
    grants = work.get("grants", []) if isinstance(work, dict) else []
    for item in grants if isinstance(grants, list) else []:
        if not isinstance(item, dict):
            continue
        funder = normalize(item.get("funder_display_name", "")) or normalize(item.get("funder", ""))
        award_id = normalize(item.get("award_id", ""))
        if funder and funder not in funders:
            funders.append(funder)
        if award_id and award_id not in grant_ids:
            grant_ids.append(award_id)
    awards = work.get("awards", []) if isinstance(work, dict) else []
    for item in awards if isinstance(awards, list) else []:
        if not isinstance(item, dict):
            continue
        funder = normalize(item.get("funder_display_name", "")) or normalize(item.get("display_name", ""))
        award_id = normalize(item.get("funder_award_id", "")) or normalize(item.get("award_id", ""))
        if funder and funder not in funders:
            funders.append(funder)
        if award_id and award_id not in grant_ids:
            grant_ids.append(award_id)
    openalex_funders = work.get("funders", []) if isinstance(work, dict) else []
    for item in openalex_funders if isinstance(openalex_funders, list) else []:
        if not isinstance(item, dict):
            continue
        funder = normalize(item.get("display_name", "")) or normalize(item.get("name", ""))
        if funder and funder not in funders:
            funders.append(funder)
    return " | ".join(funders), " | ".join(grant_ids)


def publication_types_from_pubmed_article(article: ET.Element) -> str:
    values: List[str] = []
    for item in article.findall(".//PublicationTypeList/PublicationType"):
        text = strip_markup(" ".join(item.itertext()))
        if text and text not in values:
            values.append(text)
    return " | ".join(values)


def mesh_terms_from_pubmed_article(article: ET.Element) -> str:
    values: List[str] = []
    for heading in article.findall(".//MeshHeadingList/MeshHeading"):
        descriptor = strip_markup(" ".join(heading.find("DescriptorName").itertext())) if heading.find("DescriptorName") is not None else ""
        qualifiers = [
            strip_markup(" ".join(item.itertext()))
            for item in heading.findall("QualifierName")
            if strip_markup(" ".join(item.itertext()))
        ]
        if descriptor and qualifiers:
            for qualifier in qualifiers:
                value = f"{descriptor} / {qualifier}"
                if value not in values:
                    values.append(value)
        elif descriptor and descriptor not in values:
            values.append(descriptor)
    return " | ".join(values)


def keywords_from_pubmed_article(article: ET.Element) -> str:
    values: List[str] = []
    for item in article.findall(".//KeywordList/Keyword"):
        text = strip_markup(" ".join(item.itertext()))
        if text and text not in values:
            values.append(text)
    return " | ".join(values)


def funding_from_pubmed_article(article: ET.Element) -> Tuple[str, str]:
    funders: List[str] = []
    grant_ids: List[str] = []
    for grant in article.findall(".//GrantList/Grant"):
        agency = normalize(grant.findtext("Agency"))
        acronym = normalize(grant.findtext("Acronym"))
        funder = agency or acronym
        grant_id = normalize(grant.findtext("GrantID"))
        if funder and funder not in funders:
            funders.append(funder)
        if grant_id and grant_id not in grant_ids:
            grant_ids.append(grant_id)
    return " | ".join(funders), " | ".join(grant_ids)


def language_from_pubmed_article(article: ET.Element) -> str:
    return join_unique(" ".join(item.itertext()) for item in article.findall(".//Article/Language"))


def pubmed_publication_flags(article: ET.Element) -> Tuple[str, str]:
    publication_types = publication_types_from_pubmed_article(article).lower()
    relation_types = " | ".join(
        normalize(item.attrib.get("RefType", ""))
        for item in article.findall(".//CommentsCorrectionsList/CommentsCorrections")
    ).lower()
    text = f"{publication_types} | {relation_types}"
    is_retracted = "true" if "retract" in text else ""
    has_correction = "true" if any(token in text for token in ("correction", "erratum", "corrected")) else ""
    return is_retracted, has_correction


def publication_relations_from_pubmed_article(article: ET.Element) -> Tuple[str, str]:
    relation_values: List[str] = []
    relation_texts: List[str] = []
    for item in article.findall(".//CommentsCorrectionsList/CommentsCorrections"):
        ref_type = normalize(item.attrib.get("RefType", ""))
        pmid = normalize(item.findtext("PMID"))
        ref_source = normalize(item.findtext("RefSource"))
        note = normalize(item.findtext("Note"))
        relation_bits = []
        if ref_type:
            relation_bits.append(ref_type)
        if pmid:
            relation_bits.append(f"PMID:{pmid}")
        if ref_source:
            relation_bits.append(ref_source)
        if note:
            relation_bits.append(note)
        relation = " ".join(relation_bits)
        if relation and relation not in relation_values:
            relation_values.append(relation)
        relation_texts.extend([ref_source, note])
    return extract_dois(relation_texts), " | ".join(relation_values)


def year_from_crossref_date(*values: object) -> str:
    for value in values:
        if not isinstance(value, dict):
            continue
        date_parts = value.get("date-parts")
        if not isinstance(date_parts, list) or not date_parts:
            continue
        first = date_parts[0]
        if isinstance(first, list) and first:
            year = normalize(first[0])
            if re.match(r"^\d{4}$", year):
                return year
    return ""


def join_text_parts(parts: Iterable[object]) -> str:
    out = []
    for part in parts:
        text = strip_markup(" ".join(part.itertext()) if isinstance(part, ET.Element) else part)
        if text:
            label = normalize(part.attrib.get("Label", "")) if isinstance(part, ET.Element) else ""
            out.append(f"{label}: {text}" if label else text)
    return " ".join(out).strip()


def decode_openalex_abstract(index: object) -> str:
    if not isinstance(index, dict):
        return ""
    words_by_position: Dict[int, str] = {}
    max_position = -1
    for token, positions in index.items():
        if not isinstance(token, str) or not isinstance(positions, list):
            continue
        for pos in positions:
            if isinstance(pos, int) and pos >= 0:
                words_by_position[pos] = token
                if pos > max_position:
                    max_position = pos
    if max_position < 0:
        return ""
    ordered = [words_by_position.get(i, "") for i in range(max_position + 1)]
    return " ".join([w for w in ordered if w]).strip()


def lookup_openalex_work(client: RateLimitedHttpClient, doi: str, email: str, api_key: str) -> Optional[dict]:
    endpoint = "https://api.openalex.org/works"
    params = {
        "filter": f"doi:https://doi.org/{doi}",
        "per-page": 1,
        "select": (
            "doi,ids,display_name,publication_year,publication_date,type,authorships,"
            "abstract_inverted_index,open_access,best_oa_location,primary_location,locations,"
            "language,biblio,awards,funders,mesh,concepts,keywords,is_retracted"
        ),
    }
    if api_key:
        params["api_key"] = api_key
    if email:
        params["mailto"] = email
    payload = client.get_json(endpoint, params=params, headers={})
    results = payload.get("results", []) or []
    if not results:
        return None
    return results[0]


def metadata_from_openalex_work(work: dict, paper: dict) -> dict:
    ids = work.get("ids", {}) if isinstance(work, dict) else {}
    title = normalize(work.get("display_name", "")) or normalize(paper.get("study_title", ""))
    abstract = decode_openalex_abstract(work.get("abstract_inverted_index", {}))
    journal_issn, journal_eissn = issns_from_openalex_work(work)
    funders, grant_ids = funding_from_openalex_work(work)
    return {
        "metadata_provider": "openalex",
        "metadata_provider_chain": "openalex",
        "openalex_id": normalize(ids.get("openalex", "")) if isinstance(ids, dict) else "",
        "pmid": normalize(ids.get("pmid", "")).removeprefix("https://pubmed.ncbi.nlm.nih.gov/") if isinstance(ids, dict) else "",
        "pmcid": normalize(ids.get("pmcid", "")) if isinstance(ids, dict) else "",
        "study_title": title,
        "study_year": normalize(work.get("publication_year", "")) or normalize(paper.get("study_year", "")),
        "authors": authors_from_openalex(work.get("authorships", []) or []) or normalize(paper.get("authors", "")),
        "study_journal": journal_from_openalex_work(work) or normalize(paper.get("study_journal", "")),
        "publication_type": normalize(work.get("type", "")) or normalize(paper.get("publication_type", "")),
        "trial_registry_ids": extract_trial_registry_ids(
            title,
            abstract,
            paper.get("trial_registry_ids", ""),
        ),
        "publication_date": normalize(work.get("publication_date", "")) or normalize(paper.get("publication_date", "")),
        "journal_issn": journal_issn or normalize(paper.get("journal_issn", "")),
        "journal_eissn": journal_eissn or normalize(paper.get("journal_eissn", "")),
        "publisher": publisher_from_openalex_work(work) or normalize(paper.get("publisher", "")),
        "mesh_terms": mesh_terms_from_openalex_work(work) or normalize(paper.get("mesh_terms", "")),
        "keywords": keywords_from_openalex_work(work) or normalize(paper.get("keywords", "")),
        "funders": funders or normalize(paper.get("funders", "")),
        "grant_ids": grant_ids or normalize(paper.get("grant_ids", "")),
        "related_dois": normalize(paper.get("related_dois", "")),
        "publication_relations": normalize(paper.get("publication_relations", "")),
        "is_retracted": normalize(paper.get("is_retracted", "")),
        "has_correction": normalize(paper.get("has_correction", "")),
        "language": normalize(work.get("language", "")) or normalize(paper.get("language", "")),
        "semantic_scholar_id": normalize(paper.get("semantic_scholar_id", "")),
        "abstract": abstract,
        **extract_oa_fields(work),
    }


def ncbi_common_params(email: str, api_key: str) -> Dict[str, object]:
    params: Dict[str, object] = {"tool": "psychedelics_kg"}
    if email:
        params["email"] = email
    if api_key:
        params["api_key"] = api_key
    return params


def pubmed_article_id(article: ET.Element, id_type: str) -> str:
    wanted = id_type.lower()
    # Only the PubMed record's own identifiers belong to this article. A broad
    # descendant search also sees ArticleId elements in cited references and
    # can therefore attach a reference's PMCID to a paper that has no PMCID.
    for item in article.findall("./PubmedData/ArticleIdList/ArticleId"):
        if normalize(item.attrib.get("IdType", "")).lower() == wanted:
            return normalize("".join(item.itertext()))
    return ""


def year_from_pubmed_article(article: ET.Element) -> str:
    for path in (
        ".//Article/Journal/JournalIssue/PubDate/Year",
        ".//Article/ArticleDate/Year",
        ".//PubmedData/History/PubMedPubDate/Year",
    ):
        text = normalize(article.findtext(path))
        if re.match(r"^\d{4}$", text):
            return text
    medline_date = normalize(article.findtext(".//Article/Journal/JournalIssue/PubDate/MedlineDate"))
    match = re.search(r"\b(18|19|20|21)\d{2}\b", medline_date)
    return match.group(0) if match else ""


def authors_from_pubmed_article(article: ET.Element, max_names: int = 10) -> str:
    names = []
    for author in article.findall(".//AuthorList/Author"):
        collective = normalize(author.findtext("CollectiveName"))
        if collective:
            names.append(collective)
        else:
            last = normalize(author.findtext("LastName"))
            initials = normalize(author.findtext("Initials"))
            fore = normalize(author.findtext("ForeName"))
            name = " ".join([part for part in (last, initials or fore) if part])
            if name:
                names.append(name)
        if len(names) >= max_names:
            break
    return "; ".join(names)


def metadata_from_pubmed_article(article: ET.Element, paper: dict) -> dict:
    abstract_parts = article.findall(".//Article/Abstract/AbstractText")
    title = strip_markup("".join(article.find(".//ArticleTitle").itertext())) if article.find(".//ArticleTitle") is not None else normalize(paper.get("study_title", ""))
    abstract = join_text_parts(abstract_parts)
    journal = normalize(article.findtext(".//Article/Journal/Title")) or normalize(article.findtext(".//Article/Journal/ISOAbbreviation"))
    journal_issn, journal_eissn = issns_from_pubmed_article(article)
    funders, grant_ids = funding_from_pubmed_article(article)
    related_dois, publication_relations = publication_relations_from_pubmed_article(article)
    is_retracted, has_correction = pubmed_publication_flags(article)
    return {
        "metadata_provider": "pubmed",
        "metadata_provider_chain": "pubmed",
        "openalex_id": "",
        "pmid": normalize(article.findtext(".//MedlineCitation/PMID")),
        "pmcid": pubmed_article_id(article, "pmc"),
        "study_title": title,
        "study_year": year_from_pubmed_article(article) or normalize(paper.get("study_year", "")),
        "authors": authors_from_pubmed_article(article) or normalize(paper.get("authors", "")),
        "study_journal": journal or normalize(paper.get("study_journal", "")),
        "publication_type": publication_types_from_pubmed_article(article) or normalize(paper.get("publication_type", "")),
        "trial_registry_ids": extract_trial_registry_ids(
            title,
            abstract,
            " ".join(article.itertext()),
            paper.get("trial_registry_ids", ""),
        ),
        "publication_date": publication_date_from_pubmed_article(article) or normalize(paper.get("publication_date", "")),
        "journal_issn": journal_issn or normalize(paper.get("journal_issn", "")),
        "journal_eissn": journal_eissn or normalize(paper.get("journal_eissn", "")),
        "publisher": normalize(paper.get("publisher", "")),
        "mesh_terms": mesh_terms_from_pubmed_article(article) or normalize(paper.get("mesh_terms", "")),
        "keywords": keywords_from_pubmed_article(article) or normalize(paper.get("keywords", "")),
        "funders": funders or normalize(paper.get("funders", "")),
        "grant_ids": grant_ids or normalize(paper.get("grant_ids", "")),
        "related_dois": related_dois or normalize(paper.get("related_dois", "")),
        "publication_relations": publication_relations or normalize(paper.get("publication_relations", "")),
        "is_retracted": is_retracted or normalize(paper.get("is_retracted", "")),
        "has_correction": has_correction or normalize(paper.get("has_correction", "")),
        "language": language_from_pubmed_article(article) or normalize(paper.get("language", "")),
        "semantic_scholar_id": normalize(paper.get("semantic_scholar_id", "")),
        "abstract": abstract,
        "is_oa": "",
        "oa_status": "",
        "oa_url": "",
        "best_pdf_url": "",
    }


def lookup_pubmed_metadata(
    client: RateLimitedHttpClient,
    doi: str,
    email: str,
    api_key: str,
    paper: dict,
) -> Optional[dict]:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    search_payload = client.get_json(
        f"{base}/esearch.fcgi",
        params={
            **ncbi_common_params(email, api_key),
            "db": "pubmed",
            "term": f'"{doi}"[AID]',
            "retmode": "json",
            "retmax": 5,
        },
        headers={},
    )
    ids = search_payload.get("esearchresult", {}).get("idlist", []) if isinstance(search_payload, dict) else []
    ids = [normalize(value) for value in ids if normalize(value)]
    if not ids:
        return None

    raw = client.get_bytes(
        f"{base}/efetch.fcgi?"
        + urlencode(
            {
                **ncbi_common_params(email, api_key),
                "db": "pubmed",
                "id": ",".join(ids),
                "retmode": "xml",
            }
        ),
        headers={},
    )
    root = ET.fromstring(raw)
    articles = root.findall(".//PubmedArticle")
    if not articles:
        return None
    doi_norm = normalize_doi(doi).lower()
    selected = articles[0]
    for article in articles:
        if normalize_doi(pubmed_article_id(article, "doi")).lower() == doi_norm:
            selected = article
            break
    return metadata_from_pubmed_article(selected, paper)


def lookup_pmc_idconv(
    client: RateLimitedHttpClient,
    doi: str,
    email: str,
) -> dict:
    payload = client.get_json(
        "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/",
        params={
            "ids": doi,
            "idtype": "doi",
            "format": "json",
            "tool": "psychedelics_kg",
            "email": email or None,
        },
        headers={},
    )
    records = payload.get("records", []) if isinstance(payload, dict) else []
    for record in records:
        if isinstance(record, dict) and normalize_doi(record.get("doi", "")).lower() == normalize_doi(doi).lower():
            return record
    return {}


def ftp_to_https(url: str) -> str:
    text = normalize(url)
    if text.lower().startswith("ftp://ftp.ncbi.nlm.nih.gov/"):
        text = "https://ftp.ncbi.nlm.nih.gov/" + text[len("ftp://ftp.ncbi.nlm.nih.gov/") :]
    if text.lower().startswith("https://ftp.ncbi.nlm.nih.gov/pub/pmc/") and not text.lower().startswith(
        "https://ftp.ncbi.nlm.nih.gov/pub/pmc/deprecated/"
    ):
        return "https://ftp.ncbi.nlm.nih.gov/pub/pmc/deprecated/" + text[
            len("https://ftp.ncbi.nlm.nih.gov/pub/pmc/") :
        ]
    return text


def lookup_pmc_oa_links(client: RateLimitedHttpClient, pmcid: str) -> dict:
    pmcid = normalize(pmcid)
    if not pmcid:
        return {}
    payload = client.get_bytes(
        "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?"
        + urlencode({"id": pmcid}),
        headers={},
    )
    root = ET.fromstring(payload)
    error = root.find(".//error")
    if error is not None:
        return {
            "pmc_oa_checked": "true",
            "pmc_oa_error": normalize(error.attrib.get("code", "")) or strip_markup("".join(error.itertext())),
            "is_oa": "false",
        }

    record = root.find(".//record")
    if record is None:
        return {"pmc_oa_checked": "true", "is_oa": "false"}

    pdf_url = ""
    package_url = ""
    for link in record.findall(".//link"):
        link_format = normalize(link.attrib.get("format", "")).lower()
        href = ftp_to_https(link.attrib.get("href", ""))
        if link_format == "pdf" and href and not pdf_url:
            pdf_url = href
        elif link_format == "tgz" and href and not package_url:
            package_url = href

    return {
        "pmc_oa_checked": "true",
        "pmc_oa_error": "",
        "pmc_oa_license": normalize(record.attrib.get("license", "")),
        "pmc_oa_pdf_url": pdf_url,
        "pmc_europepmc_pdf_url": "",
        "pmc_oa_package_url": package_url,
        "is_oa": "true",
        "oa_status": "gold",
        "best_pdf_url": pdf_url,
        "pdf_url_candidates": join_candidates([pdf_url]),
    }


def lookup_pmc_metadata(
    client: RateLimitedHttpClient,
    doi: str,
    email: str,
    pmcid_hint: str,
    paper: dict,
) -> Optional[dict]:
    record = lookup_pmc_idconv(client, doi=doi, email=email)
    # `pmcid_hint` may come from previously merged metadata and is not proof
    # that the identifier belongs to this DOI. The id-converter response is
    # DOI-checked in lookup_pmc_idconv, so only its PMCID is safe to use. This
    # also makes a verified id-converter result override a conflicting hint.
    pmcid = normalize(record.get("pmcid", ""))
    if not pmcid:
        return None
    pmcid = pmcid if pmcid.upper().startswith("PMC") else f"PMC{pmcid}"
    oa_info: dict = {}
    try:
        oa_info = lookup_pmc_oa_links(client, pmcid=pmcid)
    except Exception as err:
        oa_info = {
            "pmc_oa_checked": "false",
            "pmc_oa_error": f"{type(err).__name__}: {err}",
        }
    payload = client.get_json(
        f"https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{quote(pmcid, safe='')}/unicode",
        params={},
        headers={},
    )
    docs = payload.get("documents", []) if isinstance(payload, dict) else []
    title = ""
    abstract_parts = []
    for doc in docs if isinstance(docs, list) else []:
        passages = doc.get("passages", []) if isinstance(doc, dict) else []
        for passage in passages if isinstance(passages, list) else []:
            if not isinstance(passage, dict):
                continue
            section = normalize(passage.get("infons", {}).get("section_type", "")).upper()
            text = strip_markup(passage.get("text", ""))
            if section == "TITLE" and text and not title:
                title = text
            elif section == "ABSTRACT" and text:
                abstract_parts.append(text)
    if not title and not abstract_parts and not record:
        return None
    return {
        "metadata_provider": "pmc",
        "metadata_provider_chain": "pmc",
        "openalex_id": "",
        "pmid": normalize(record.get("pmid", "")),
        "pmcid": pmcid,
        "study_title": title or normalize(paper.get("study_title", "")),
        "study_year": normalize(paper.get("study_year", "")),
        "authors": normalize(paper.get("authors", "")),
        "study_journal": normalize(paper.get("study_journal", "")),
        "publication_type": normalize(paper.get("publication_type", "")),
        "trial_registry_ids": extract_trial_registry_ids(
            title,
            abstract_parts,
            paper.get("trial_registry_ids", ""),
        ),
        **{field: normalize(paper.get(field, "")) for field in PAPER_METADATA_FIELDS if field not in {"study_journal", "publication_type", "trial_registry_ids"}},
        "abstract": " ".join(abstract_parts).strip(),
        "is_oa": normalize(oa_info.get("is_oa", "")),
        "oa_status": normalize(oa_info.get("oa_status", "")),
        "oa_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/",
        "best_pdf_url": normalize(oa_info.get("best_pdf_url", "")),
        "pmc_oa_checked": normalize(oa_info.get("pmc_oa_checked", "")),
        "pmc_oa_error": normalize(oa_info.get("pmc_oa_error", "")),
        "pmc_oa_license": normalize(oa_info.get("pmc_oa_license", "")),
        "pmc_oa_pdf_url": normalize(oa_info.get("pmc_oa_pdf_url", "")),
        "pmc_europepmc_pdf_url": normalize(oa_info.get("pmc_europepmc_pdf_url", "")),
        "pmc_oa_package_url": normalize(oa_info.get("pmc_oa_package_url", "")),
    }


def issns_from_crossref_item(item: dict) -> Tuple[str, str]:
    print_issn = ""
    electronic_issn = ""
    for entry in item.get("issn-type", []) if isinstance(item.get("issn-type", []), list) else []:
        if not isinstance(entry, dict):
            continue
        value = normalize(entry.get("value", ""))
        kind = normalize(entry.get("type", "")).lower()
        if kind == "electronic" and value and not electronic_issn:
            electronic_issn = value
        elif kind == "print" and value and not print_issn:
            print_issn = value
    issns = item.get("ISSN", [])
    values = [normalize(value) for value in issns] if isinstance(issns, list) else [normalize(issns)]
    values = [value for value in values if value]
    if not print_issn:
        print_issn = next((value for value in values if value != electronic_issn), values[0] if values else "")
    if not electronic_issn:
        electronic_issn = next((value for value in values if value != print_issn), "")
    return print_issn, electronic_issn


def funding_from_crossref_item(item: dict) -> Tuple[str, str]:
    funders: List[str] = []
    grant_ids: List[str] = []
    for funder_row in item.get("funder", []) if isinstance(item.get("funder", []), list) else []:
        if not isinstance(funder_row, dict):
            continue
        funder = normalize(funder_row.get("name", ""))
        if funder and funder not in funders:
            funders.append(funder)
        awards = funder_row.get("award", [])
        for award in awards if isinstance(awards, list) else [awards]:
            text = normalize(award)
            if text and text not in grant_ids:
                grant_ids.append(text)
    return " | ".join(funders), " | ".join(grant_ids)


def relations_from_crossref_item(item: dict) -> Tuple[str, str]:
    related_dois: List[str] = []
    relation_values: List[str] = []
    relation = item.get("relation", {})
    if not isinstance(relation, dict):
        return "", ""
    for relation_type, entries in relation.items():
        raw_entries = entries if isinstance(entries, list) else [entries]
        for entry in raw_entries:
            if not isinstance(entry, dict):
                continue
            identifier = normalize(entry.get("id", ""))
            id_type = normalize(entry.get("id-type", ""))
            asserted_by = normalize(entry.get("asserted-by", ""))
            parts = [normalize(relation_type)]
            if id_type and identifier:
                parts.append(f"{id_type}:{identifier}")
            elif identifier:
                parts.append(identifier)
            if asserted_by:
                parts.append(f"asserted-by:{asserted_by}")
            value = " ".join(parts)
            if value and value not in relation_values:
                relation_values.append(value)
            if id_type.lower() == "doi":
                doi = normalize_doi(identifier)
                if doi and doi not in related_dois:
                    related_dois.append(doi)
            else:
                for doi in extract_dois(identifier).split(" | "):
                    if doi and doi not in related_dois:
                        related_dois.append(doi)
    return " | ".join(related_dois), " | ".join(relation_values)


def crossref_publication_flags(item: dict) -> Tuple[str, str]:
    relation = item.get("relation", {})
    relation_text = " ".join(relation.keys()).lower() if isinstance(relation, dict) else ""
    item_type = normalize(item.get("type", "")).lower()
    text = f"{item_type} {relation_text}"
    is_retracted = "true" if "retract" in text else ""
    has_correction = "true" if any(token in text for token in ("correction", "erratum", "corrected")) else ""
    return is_retracted, has_correction


def lookup_crossref_metadata(
    client: RateLimitedHttpClient,
    doi: str,
    email: str,
    paper: dict,
) -> Optional[dict]:
    params = {"mailto": email} if email else {}
    payload = client.get_json(f"https://api.crossref.org/works/{quote(doi, safe='')}", params=params, headers={})
    item = payload.get("message", {}) if isinstance(payload, dict) else {}
    if not isinstance(item, dict) or normalize_doi(item.get("DOI", "")).lower() != normalize_doi(doi).lower():
        return None
    title = crossref_title_with_subtitle(item, paper.get("study_title", ""))
    abstract = strip_markup(item.get("abstract", ""))
    publication_date = date_from_crossref_date(
        item.get("published", {}),
        item.get("published-online", {}),
        item.get("published-print", {}),
        item.get("issued", {}),
    )
    journal_issn, journal_eissn = issns_from_crossref_item(item)
    funders, grant_ids = funding_from_crossref_item(item)
    related_dois, publication_relations = relations_from_crossref_item(item)
    is_retracted, has_correction = crossref_publication_flags(item)
    return {
        "metadata_provider": "crossref",
        "metadata_provider_chain": "crossref",
        "openalex_id": "",
        "pmid": "",
        "pmcid": "",
        "study_title": title,
        "study_year": year_from_crossref_date(
            item.get("published", {}),
            item.get("published-online", {}),
            item.get("published-print", {}),
            item.get("issued", {}),
        )
        or normalize(paper.get("study_year", "")),
        "authors": authors_from_crossref(item.get("author", []) or []) or normalize(paper.get("authors", "")),
        "study_journal": first_list_value(item.get("container-title", "")) or first_list_value(item.get("short-container-title", "")) or normalize(paper.get("study_journal", "")),
        "publication_type": normalize(item.get("type", "")) or normalize(paper.get("publication_type", "")),
        "trial_registry_ids": extract_trial_registry_ids(
            title,
            abstract,
            item.get("clinical-trial-number", ""),
            paper.get("trial_registry_ids", ""),
        ),
        "publication_date": publication_date or normalize(paper.get("publication_date", "")),
        "journal_issn": journal_issn or normalize(paper.get("journal_issn", "")),
        "journal_eissn": journal_eissn or normalize(paper.get("journal_eissn", "")),
        "publisher": normalize(item.get("publisher", "")) or normalize(paper.get("publisher", "")),
        "mesh_terms": normalize(paper.get("mesh_terms", "")),
        "keywords": join_list_values(item.get("subject", [])) or normalize(paper.get("keywords", "")),
        "funders": funders or normalize(paper.get("funders", "")),
        "grant_ids": grant_ids or normalize(paper.get("grant_ids", "")),
        "related_dois": related_dois or normalize(paper.get("related_dois", "")),
        "publication_relations": publication_relations or normalize(paper.get("publication_relations", "")),
        "is_retracted": is_retracted or normalize(paper.get("is_retracted", "")),
        "has_correction": has_correction or normalize(paper.get("has_correction", "")),
        "language": normalize(item.get("language", "")) or normalize(paper.get("language", "")),
        "semantic_scholar_id": normalize(paper.get("semantic_scholar_id", "")),
        "abstract": abstract,
        "is_oa": "",
        "oa_status": "",
        "oa_url": "",
        "best_pdf_url": "",
        "crossref_type": normalize(item.get("type", "")),
    }


def lookup_unpaywall_metadata(
    client: RateLimitedHttpClient,
    doi: str,
    email: str,
    paper: dict,
) -> Optional[dict]:
    usable = usable_email(email)
    if not usable:
        raise ValueError("unpaywall_email_missing_or_placeholder")
    try:
        payload = client.get_json(
            f"https://api.unpaywall.org/v2/{quote(doi, safe='')}",
            params={"email": usable},
            headers={},
        )
    except HTTPError as err:
        if err.code == 404:
            return None
        raise
    if not isinstance(payload, dict) or normalize_doi(payload.get("doi", "")).lower() != normalize_doi(doi).lower():
        return None
    return metadata_from_unpaywall_payload(payload, paper)


def issns_from_semantic_scholar_payload(payload: dict) -> Tuple[str, str]:
    venue = payload.get("publicationVenue", {}) if isinstance(payload.get("publicationVenue", {}), dict) else {}
    issns = venue.get("issn", "")
    values = [normalize(value) for value in issns] if isinstance(issns, list) else re.split(r"[,;]\s*", normalize(issns))
    values = [value for value in values if value]
    return (values[0] if values else "", values[1] if len(values) > 1 else "")


def keywords_from_semantic_scholar_payload(payload: dict) -> str:
    values: List[str] = []
    fields = payload.get("fieldsOfStudy", [])
    for value in fields if isinstance(fields, list) else [fields]:
        text = normalize(value)
        if text and text not in values:
            values.append(text)
    s2_fields = payload.get("s2FieldsOfStudy", [])
    for item in s2_fields if isinstance(s2_fields, list) else []:
        if not isinstance(item, dict):
            continue
        for key in ("category", "source"):
            text = normalize(item.get(key, ""))
            if text and text not in values:
                values.append(text)
    return " | ".join(values)


def lookup_semantic_scholar_metadata(
    client: RateLimitedHttpClient,
    doi: str,
    api_key: str,
    paper: dict,
) -> Optional[dict]:
    headers = {"x-api-key": api_key} if api_key else {}
    payload = client.get_json(
        f"https://api.semanticscholar.org/graph/v1/paper/{quote(f'DOI:{doi}', safe='')}",
        params={
            "fields": (
                "paperId,title,year,publicationDate,abstract,authors,externalIds,"
                "openAccessPdf,isOpenAccess,url,venue,publicationVenue,publicationTypes,"
                "journal,fieldsOfStudy,s2FieldsOfStudy"
            )
        },
        headers=headers,
    )
    if not isinstance(payload, dict) or payload.get("error"):
        return None
    external_ids = payload.get("externalIds", {}) if isinstance(payload.get("externalIds", {}), dict) else {}
    open_access_pdf = payload.get("openAccessPdf", {}) if isinstance(payload.get("openAccessPdf", {}), dict) else {}
    pdf_url = normalize(open_access_pdf.get("url", ""))
    is_oa = payload.get("isOpenAccess", "")
    title = normalize(payload.get("title", "")) or normalize(paper.get("study_title", ""))
    abstract = normalize(payload.get("abstract", ""))
    journal = payload.get("journal", {}) if isinstance(payload.get("journal", {}), dict) else {}
    publication_venue = payload.get("publicationVenue", {}) if isinstance(payload.get("publicationVenue", {}), dict) else {}
    journal_issn, journal_eissn = issns_from_semantic_scholar_payload(payload)
    return {
        "metadata_provider": "semantic_scholar",
        "metadata_provider_chain": "semantic_scholar",
        "semantic_scholar_id": normalize(payload.get("paperId", "")),
        "openalex_id": "",
        "pmid": normalize(external_ids.get("PubMed", "")),
        "pmcid": normalize(external_ids.get("PubMedCentral", "")),
        "study_title": title,
        "study_year": normalize(payload.get("year", "")) or normalize(paper.get("study_year", "")),
        "authors": authors_from_semantic_scholar(payload.get("authors", []) or []) or normalize(paper.get("authors", "")),
        "study_journal": normalize(journal.get("name", ""))
        or normalize(publication_venue.get("name", ""))
        or normalize(payload.get("venue", ""))
        or normalize(paper.get("study_journal", "")),
        "publication_type": join_list_values(payload.get("publicationTypes", [])) or normalize(paper.get("publication_type", "")),
        "trial_registry_ids": extract_trial_registry_ids(
            title,
            abstract,
            paper.get("trial_registry_ids", ""),
        ),
        "publication_date": normalize(payload.get("publicationDate", "")) or normalize(paper.get("publication_date", "")),
        "journal_issn": journal_issn or normalize(paper.get("journal_issn", "")),
        "journal_eissn": journal_eissn or normalize(paper.get("journal_eissn", "")),
        "publisher": normalize(paper.get("publisher", "")),
        "mesh_terms": normalize(paper.get("mesh_terms", "")),
        "keywords": keywords_from_semantic_scholar_payload(payload) or normalize(paper.get("keywords", "")),
        "funders": normalize(paper.get("funders", "")),
        "grant_ids": normalize(paper.get("grant_ids", "")),
        "related_dois": normalize(paper.get("related_dois", "")),
        "publication_relations": normalize(paper.get("publication_relations", "")),
        "is_retracted": normalize(paper.get("is_retracted", "")),
        "has_correction": normalize(paper.get("has_correction", "")),
        "language": normalize(paper.get("language", "")),
        "abstract": abstract,
        "is_oa": "true" if is_oa is True else "false" if is_oa is False else "",
        "oa_status": "",
        "oa_url": normalize(payload.get("url", "")),
        "best_pdf_url": pdf_url,
        "pdf_url_candidates": pdf_url,
        "semantic_scholar_checked": "true",
    }


def is_probable_pdf_url(url: str) -> bool:
    text = normalize(url)
    if not text:
        return False
    parsed = urlparse(text)
    lowered = text.lower()
    path = parsed.path.lower()
    query = parsed.query.lower()
    host = parsed.netloc.lower()
    if "europepmc.org" in host and ("/api/getpdf" in path or "pdf=render" in query):
        return False
    if path.endswith(".pdf") or ".pdf/" in path or ".pdf." in path or ".pdf?" in lowered:
        return True
    if path.endswith("/pdf") or path.endswith("/download"):
        return True
    if "ftp.ncbi.nlm.nih.gov" in host and "/pub/pmc/oa_pdf/" in path:
        return True
    if "pmc.ncbi.nlm.nih.gov" in host and "/pdf/" in path:
        return True
    if host.endswith("hal.science") and path.endswith("/document"):
        return True
    if "archive-ouverte" in host and path.endswith("/download"):
        return True
    strong_path_markers = (
        "/pdf/",
        "/pdfdirect/",
        "/content/pdf/",
        "/articlepdf/",
        "/doi/pdf/",
        "/download/",
        "/bitstream/",
    )
    if any(marker in path for marker in strong_path_markers):
        return True
    file_path_markers = (
        "/files/",
        "/fulltext",
        "/full-text",
        "/accepted-manuscript",
        "/manuscript",
    )
    if any(marker in path for marker in file_path_markers) and "pdf" in lowered:
        return True
    if "pdf=render" in query or "download=true" in query:
        return True
    return False


def add_unique(values: List[str], value: str) -> None:
    text = normalize(value)
    if text and text not in values:
        values.append(text)


def join_candidates(values: Iterable[str]) -> str:
    out: List[str] = []
    for value in values:
        add_unique(out, value)
    return " | ".join(out)


def split_candidates(value: object) -> List[str]:
    if isinstance(value, list):
        raw_values = value
    else:
        text = normalize(value)
        if not text:
            return []
        raw_values = text.split(" | ") if " | " in text else text.split("|")
    out: List[str] = []
    for item in raw_values:
        add_unique(out, item)
    return out


def extract_pmcid_from_url(url: str) -> str:
    text = normalize(url)
    if not text:
        return ""
    match = re.search(r"\bPMC\d+\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(0).upper()
    match = re.search(r"/pmc/articles/(\d+)", text, flags=re.IGNORECASE)
    if match:
        return f"PMC{match.group(1)}"
    return ""


def candidate_priority(url: str) -> Tuple[int, str]:
    lowered = normalize(url).lower()
    if "ftp.ncbi.nlm.nih.gov/pub/pmc" in lowered:
        return (0, lowered)
    if "pmc.ncbi.nlm.nih.gov" in lowered or "ncbi.nlm.nih.gov/pmc" in lowered:
        return (1, lowered)
    if "europepmc.org/api/getpdf" in lowered:
        return (2, lowered)
    if is_probable_pdf_url(url):
        return (5, lowered)
    return (10, lowered)


def rank_pdf_candidates(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    for value in values:
        add_unique(out, value)
    return sorted(out, key=candidate_priority)


def add_unpaywall_location_candidates(location: object, pdf_candidates: List[str], url_candidates: List[str]) -> None:
    if not isinstance(location, dict):
        return
    pdf_url = normalize(location.get("url_for_pdf", ""))
    url = normalize(location.get("url", ""))
    landing = normalize(location.get("url_for_landing_page", ""))
    if pdf_url:
        add_unique(pdf_candidates, pdf_url)
    if url and is_probable_pdf_url(url):
        add_unique(pdf_candidates, url)
    for candidate in (landing, url, pdf_url):
        add_unique(url_candidates, candidate)


def issns_from_unpaywall_payload(payload: dict) -> Tuple[str, str]:
    issn_l = normalize(payload.get("journal_issn_l", ""))
    raw_issns = payload.get("journal_issns", "")
    if isinstance(raw_issns, list):
        values = [normalize(value) for value in raw_issns]
    else:
        values = re.split(r"[,;]\s*", normalize(raw_issns))
    values = [value for value in values if value]
    journal_issn = issn_l or (values[0] if values else "")
    journal_eissn = next((value for value in values if value != journal_issn), "")
    return journal_issn, journal_eissn


def metadata_from_unpaywall_payload(payload: dict, paper: dict) -> dict:
    best_loc = payload.get("best_oa_location", {}) if isinstance(payload.get("best_oa_location", {}), dict) else {}
    first_loc = payload.get("first_oa_location", {}) if isinstance(payload.get("first_oa_location", {}), dict) else {}
    locations = payload.get("oa_locations", []) if isinstance(payload.get("oa_locations", []), list) else []

    pdf_candidates: List[str] = []
    url_candidates: List[str] = []
    add_unpaywall_location_candidates(best_loc, pdf_candidates, url_candidates)
    add_unpaywall_location_candidates(first_loc, pdf_candidates, url_candidates)
    for location in locations:
        add_unpaywall_location_candidates(location, pdf_candidates, url_candidates)

    is_oa = bool(payload.get("is_oa"))
    oa_status = normalize(payload.get("oa_status", "")) or ("closed" if not is_oa else "")
    best_url = normalize(best_loc.get("url", "")) if isinstance(best_loc, dict) else ""
    pdf_candidates = rank_pdf_candidates(pdf_candidates)
    best_pdf_url = pdf_candidates[0] if pdf_candidates else ""
    title = normalize(payload.get("title", "")) or normalize(paper.get("study_title", ""))
    journal_issn, journal_eissn = issns_from_unpaywall_payload(payload)

    return {
        "metadata_provider": "unpaywall",
        "metadata_provider_chain": "unpaywall",
        "openalex_id": "",
        "pmid": "",
        "pmcid": "",
        "study_title": title,
        "study_year": normalize(payload.get("year", "")) or normalize(paper.get("study_year", "")),
        "authors": authors_from_unpaywall(payload.get("z_authors", []) or []) or normalize(paper.get("authors", "")),
        "study_journal": normalize(payload.get("journal_name", "")) or normalize(paper.get("study_journal", "")),
        "publication_type": normalize(payload.get("genre", "")) or normalize(paper.get("publication_type", "")),
        "trial_registry_ids": extract_trial_registry_ids(
            title,
            paper.get("trial_registry_ids", ""),
        ),
        "publication_date": normalize(payload.get("published_date", "")) or normalize(paper.get("publication_date", "")),
        "journal_issn": journal_issn or normalize(paper.get("journal_issn", "")),
        "journal_eissn": journal_eissn or normalize(paper.get("journal_eissn", "")),
        "publisher": normalize(payload.get("publisher", "")) or normalize(paper.get("publisher", "")),
        "mesh_terms": normalize(paper.get("mesh_terms", "")),
        "keywords": normalize(paper.get("keywords", "")),
        "funders": normalize(paper.get("funders", "")),
        "grant_ids": normalize(paper.get("grant_ids", "")),
        "related_dois": normalize(paper.get("related_dois", "")),
        "publication_relations": normalize(paper.get("publication_relations", "")),
        "is_retracted": normalize(paper.get("is_retracted", "")),
        "has_correction": normalize(paper.get("has_correction", "")),
        "language": normalize(paper.get("language", "")),
        "semantic_scholar_id": normalize(paper.get("semantic_scholar_id", "")),
        "abstract": "",
        "is_oa": "true" if is_oa else "false",
        "oa_status": oa_status,
        "oa_url": url_candidates[0] if url_candidates else best_url,
        "best_pdf_url": best_pdf_url,
        "pdf_url_candidates": join_candidates(pdf_candidates),
        "unpaywall_is_oa": "true" if is_oa else "false",
        "unpaywall_oa_status": oa_status,
        "unpaywall_best_url": best_url,
        "unpaywall_best_pdf_url": best_pdf_url,
        "unpaywall_pdf_url_candidates": join_candidates(pdf_candidates),
        "unpaywall_host_type": normalize(best_loc.get("host_type", "")),
        "unpaywall_version": normalize(best_loc.get("version", "")),
        "unpaywall_license": normalize(best_loc.get("license", "")),
        "unpaywall_checked": "true",
    }


def extract_oa_fields(work: dict) -> Dict[str, str]:
    open_access = work.get("open_access", {}) if isinstance(work, dict) else {}
    best_loc = work.get("best_oa_location", {}) if isinstance(work, dict) else {}
    primary_loc = work.get("primary_location", {}) if isinstance(work, dict) else {}
    locations = work.get("locations", []) if isinstance(work, dict) else []

    pdf_candidates: List[str] = []

    best_pdf = normalize(best_loc.get("pdf_url", "")) if isinstance(best_loc, dict) else ""
    primary_pdf = normalize(primary_loc.get("pdf_url", "")) if isinstance(primary_loc, dict) else ""
    if best_pdf:
        pdf_candidates.append(best_pdf)
    if primary_pdf and primary_pdf not in pdf_candidates:
        pdf_candidates.append(primary_pdf)

    for loc in locations if isinstance(locations, list) else []:
        if not isinstance(loc, dict):
            continue
        pdf_url = normalize(loc.get("pdf_url", ""))
        if pdf_url and pdf_url not in pdf_candidates:
            pdf_candidates.append(pdf_url)
        landing_page = normalize(loc.get("landing_page_url", ""))
        if landing_page and is_probable_pdf_url(landing_page) and landing_page not in pdf_candidates:
            pdf_candidates.append(landing_page)

    oa_url = normalize(open_access.get("oa_url", "")) if isinstance(open_access, dict) else ""
    if oa_url and is_probable_pdf_url(oa_url) and oa_url not in pdf_candidates:
        pdf_candidates.append(oa_url)
    pdf_candidates = rank_pdf_candidates(pdf_candidates)

    return {
        "is_oa": "true" if bool(open_access.get("is_oa")) else "false",
        "oa_status": normalize(open_access.get("oa_status", "")),
        "oa_url": oa_url,
        "best_pdf_url": pdf_candidates[0] if pdf_candidates else "",
        "pdf_url_candidates": join_candidates(pdf_candidates),
    }


def pdf_filename_for_doi(doi: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "_", normalize_doi(doi).lower())
    slug = re.sub(r"_+", "_", slug).strip("._")
    if not slug:
        slug = "paper"
    digest = hashlib.sha1(normalize_doi(doi).encode("utf-8")).hexdigest()[:10]
    slug = slug[:90]
    return f"{slug}__{digest}.pdf"


def looks_like_pdf_bytes(raw: bytes) -> bool:
    if not raw:
        return False
    # Some providers prepend whitespace/newlines before the PDF header.
    lead = raw[:2048].lstrip(b"\x00\t\r\n\f ")
    return lead.startswith(b"%PDF-")


def file_is_valid_pdf(path: Path) -> bool:
    try:
        head = path.read_bytes()[:4096]
    except Exception:
        return False
    return looks_like_pdf_bytes(head)


def pdf_source_identity_result(
    path: Path,
    study_title: object,
    min_title_score: float = 0.86,
    study_doi: object = "",
) -> Tuple[bool, float, str]:
    """Validate a PDF against the expected title before marking it available."""

    try:
        from pipeline.fulltext.pdf_alternate_sources import title_validation_result
    except ModuleNotFoundError:  # pragma: no cover - direct script execution path
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from pipeline.fulltext.pdf_alternate_sources import title_validation_result

    try:
        body = path.read_bytes()
    except Exception:
        return False, 0.0, "pdf_read_failed"
    return title_validation_result(
        normalize(study_title),
        body,
        min_title_score,
        study_doi=normalize_doi(study_doi),
    )


def row_needs_metadata_refresh(row: dict) -> bool:
    if not row:
        return True
    if normalize(row.get("paper_metadata_schema_version", "")) != PAPER_METADATA_SCHEMA_VERSION:
        return True
    if normalize(row.get("metadata_lookup_error", "")):
        return True
    if metadata_has_open_access_conflict(row):
        return True
    for field in ("study_title", "abstract", "study_journal", "publication_type", "publication_date"):
        if not normalize(row.get(field, "")):
            return True
    if extract_trial_registry_ids(
        row.get("study_title", ""),
        row.get("abstract", ""),
        row.get("trial_registry_ids", ""),
    ) != normalize(row.get("trial_registry_ids", "")):
        return True
    return False


def row_needs_core_metadata_refresh(row: dict) -> bool:
    if not row:
        return True
    if normalize(row.get("metadata_lookup_error", "")):
        return True
    if not normalize(row.get("study_title", "")):
        return True
    return False


OPEN_ACCESS_STATUSES = {"gold", "green", "hybrid", "bronze", "diamond"}
CLOSED_ACCESS_STATUSES = {"closed", "not oa", "not open access", "paywalled", "false"}


def truthy_text(value: object) -> bool:
    return normalize(value).lower() in {"1", "true", "yes", "y"}


def status_is_open(value: object) -> bool:
    return normalize(value).lower().replace(" ", "_") in OPEN_ACCESS_STATUSES


def status_is_closed(value: object) -> bool:
    return normalize(value).lower().replace("_", " ") in CLOSED_ACCESS_STATUSES


def value_has_pmc_article_url(value: object) -> bool:
    text = normalize(value).lower()
    return bool(text and ("pmc.ncbi.nlm.nih.gov/articles/pmc" in text or "ncbi.nlm.nih.gov/pmc/articles/pmc" in text))


def metadata_has_pmc_fulltext_signal(metadata: dict) -> bool:
    if normalize(metadata.get("pmcid", "")).upper().startswith("PMC"):
        return True
    return any(
        value_has_pmc_article_url(metadata.get(field, ""))
        for field in (
            "oa_url",
            "open_access_url",
            "unpaywall_best_url",
            "best_pdf_url",
            "pdf_url_candidates",
            "unpaywall_pdf_url_candidates",
        )
    )


def metadata_has_open_access_signal(metadata: dict) -> bool:
    if any(truthy_text(metadata.get(field, "")) for field in ("is_oa", "open_access_is_oa", "unpaywall_is_oa")):
        return True
    if any(status_is_open(metadata.get(field, "")) for field in ("oa_status", "open_access_status", "unpaywall_oa_status")):
        return True
    return metadata_has_pmc_fulltext_signal(metadata)


def best_open_access_status(*sources: dict) -> str:
    for source in sources:
        for field in ("oa_status", "open_access_status", "unpaywall_oa_status"):
            status = normalize(source.get(field, "")).lower().replace(" ", "_")
            if status_is_open(status):
                return status
    return "green" if any(metadata_has_pmc_fulltext_signal(source) for source in sources) else "green"


def metadata_has_open_access_conflict(metadata: dict) -> bool:
    if not metadata_has_open_access_signal(metadata):
        return False
    canonical_status = normalize(metadata.get("oa_status", "") or metadata.get("open_access_status", ""))
    canonical_is_oa = normalize(metadata.get("is_oa", "") or metadata.get("open_access_is_oa", "")).lower()
    return canonical_is_oa == "false" or status_is_closed(canonical_status)


def reconcile_open_access_metadata(out: dict, *sources: dict) -> dict:
    if not any(metadata_has_open_access_signal(source) for source in (out, *sources)):
        return out
    status = best_open_access_status(out, *sources)
    out["is_oa"] = "true"
    out["open_access_is_oa"] = "true"
    out["oa_status"] = status
    out["open_access_status"] = status
    return out


def merge_metadata_values(primary: dict, fallback: dict) -> dict:
    out = dict(fallback)
    for key, value in primary.items():
        if normalize(value) != "":
            out[key] = value
    return reconcile_open_access_metadata(out, primary, fallback)


def provider_chain(metadata: dict) -> List[str]:
    return [
        value
        for value in normalize(metadata.get("metadata_provider_chain", "")).split("|")
        if value
    ]


def metadata_has_pdf_url(metadata: dict) -> bool:
    return bool(
        normalize(metadata.get("best_pdf_url", ""))
        or normalize(metadata.get("unpaywall_best_pdf_url", ""))
        or normalize(metadata.get("pdf_url_candidates", ""))
        or normalize(metadata.get("unpaywall_pdf_url_candidates", ""))
    )


def metadata_has_unpaywall_check(metadata: dict) -> bool:
    return normalize(metadata.get("unpaywall_checked", "")).lower() == "true" or "unpaywall" in provider_chain(metadata)


def metadata_needs_oa_resolution(metadata: dict) -> bool:
    if not metadata:
        return True
    if metadata_has_open_access_conflict(metadata):
        return True
    if metadata_has_pdf_url(metadata):
        return False
    if metadata_has_unpaywall_check(metadata):
        return False
    return True


def metadata_has_useful_fields(metadata: dict) -> bool:
    return any(
        normalize(metadata.get(field, ""))
        for field in (
            "study_title",
            "abstract",
            "authors",
            "study_journal",
            "publication_type",
            "trial_registry_ids",
            "publication_date",
            "journal_issn",
            "journal_eissn",
            "publisher",
            "mesh_terms",
            "keywords",
            "funders",
            "grant_ids",
            "related_dois",
            "publication_relations",
            "is_retracted",
            "has_correction",
            "language",
            "semantic_scholar_id",
            "openalex_id",
            "pmid",
            "pmcid",
            "is_oa",
            "oa_status",
            "best_pdf_url",
            "unpaywall_checked",
        )
    )


def should_try_more_metadata(metadata: dict) -> bool:
    if not metadata:
        return True
    if not normalize(metadata.get("abstract", "")):
        return True
    if not normalize(metadata.get("study_journal", "")):
        return True
    if not normalize(metadata.get("publication_type", "")):
        return True
    if not normalize(metadata.get("publication_date", "")):
        return True
    if normalize(metadata.get("study_journal", "")) and not (
        normalize(metadata.get("journal_issn", ""))
        or normalize(metadata.get("journal_eissn", ""))
        or normalize(metadata.get("publisher", ""))
    ):
        return True
    return metadata_needs_oa_resolution(metadata)


def provider_can_help(provider: str, metadata: dict) -> bool:
    if not metadata:
        return True
    needs_abstract = not normalize(metadata.get("abstract", ""))
    needs_journal = not normalize(metadata.get("study_journal", ""))
    needs_publication_type = not normalize(metadata.get("publication_type", ""))
    needs_publication_date = not normalize(metadata.get("publication_date", ""))
    needs_venue_details = normalize(metadata.get("study_journal", "")) and not (
        normalize(metadata.get("journal_issn", ""))
        or normalize(metadata.get("journal_eissn", ""))
        or normalize(metadata.get("publisher", ""))
    )
    needs_oa = metadata_needs_oa_resolution(metadata)
    if needs_abstract and provider in {"openalex", "pubmed", "pmc", "crossref", "semantic_scholar"}:
        return True
    if (needs_journal or needs_publication_type) and provider in {"openalex", "pubmed", "crossref", "semantic_scholar", "unpaywall"}:
        return True
    if needs_publication_date and provider in {"openalex", "pubmed", "crossref", "semantic_scholar", "unpaywall"}:
        return True
    if needs_venue_details and provider in {"openalex", "pubmed", "crossref", "semantic_scholar", "unpaywall"}:
        return True
    if needs_oa and provider in {"pmc", "unpaywall", "openalex"}:
        return True
    if provider == "crossref" and not (
        normalize(metadata.get("study_title", ""))
        and normalize(metadata.get("study_year", ""))
        and normalize(metadata.get("authors", ""))
        and normalize(metadata.get("study_journal", ""))
        and normalize(metadata.get("publication_type", ""))
    ):
        return True
    return False


def row_needs_oa_refresh(row: dict, provider_order: List[str]) -> bool:
    if not row or "unpaywall" not in provider_order:
        return False
    if normalize(row.get("pdf_download_status", "")) in {"downloaded", "already_present"} and normalize(row.get("pdf_local_path", "")):
        return False
    if normalize(row.get("pdf_download_status", "")) in {
        "download_failed",
        "invalid_pdf_content",
        "invalid_pdf_existing",
        "no_pdf_url",
    }:
        return True
    return metadata_needs_oa_resolution(row)


def parse_provider_order(raw: str) -> List[str]:
    allowed = {"openalex", "pubmed", "pmc", "crossref", "unpaywall", "semantic_scholar"}
    out = []
    for part in raw.split(","):
        provider = normalize(part).lower()
        if not provider:
            continue
        if provider not in allowed:
            raise ValueError(f"Unsupported metadata provider `{provider}`")
        if provider not in out:
            out.append(provider)
    return out or list(DEFAULT_METADATA_PROVIDER_ORDER)


def fetch_metadata_with_fallbacks(
    doi: str,
    paper: dict,
    provider_order: List[str],
    clients: Dict[str, RateLimitedHttpClient],
    openalex_email: str,
    openalex_api_key: str,
    ncbi_email: str,
    ncbi_api_key: str,
    crossref_email: str,
    unpaywall_email: str,
    semantic_scholar_api_key: str = "",
    initial_metadata: Optional[dict] = None,
) -> Tuple[dict, List[dict], List[str]]:
    metadata: dict = dict(initial_metadata or {})
    errors: List[dict] = []
    queried: List[str] = []

    for provider in provider_order:
        if metadata and not should_try_more_metadata(metadata):
            break
        if metadata and not provider_can_help(provider, metadata):
            continue
        queried.append(provider)
        try:
            current: Optional[dict]
            if provider == "openalex":
                work = lookup_openalex_work(
                    clients[provider],
                    doi=doi,
                    email=openalex_email,
                    api_key=openalex_api_key,
                )
                current = metadata_from_openalex_work(work, paper) if work else None
            elif provider == "pubmed":
                current = lookup_pubmed_metadata(
                    clients[provider],
                    doi=doi,
                    email=ncbi_email,
                    api_key=ncbi_api_key,
                    paper=paper,
                )
            elif provider == "pmc":
                current = lookup_pmc_metadata(
                    clients[provider],
                    doi=doi,
                    email=ncbi_email,
                    pmcid_hint=normalize(metadata.get("pmcid", "")),
                    paper=paper,
                )
            elif provider == "crossref":
                current = lookup_crossref_metadata(
                    clients[provider],
                    doi=doi,
                    email=crossref_email,
                    paper=paper,
                )
            elif provider == "unpaywall":
                current = lookup_unpaywall_metadata(
                    clients[provider],
                    doi=doi,
                    email=unpaywall_email,
                    paper=paper,
                )
            elif provider == "semantic_scholar":
                current = lookup_semantic_scholar_metadata(
                    clients[provider],
                    doi=doi,
                    api_key=semantic_scholar_api_key,
                    paper=paper,
                )
            else:
                current = None
        except Exception as err:
            errors.append({"provider": provider, "study_doi": doi, "error": f"{type(err).__name__}: {err}"})
            continue

        if not current or not metadata_has_useful_fields(current):
            continue
        previous_chain = [
            value
            for value in normalize(metadata.get("metadata_provider_chain", "")).split("|")
            if value
        ]
        previous_provider = normalize(metadata.get("metadata_provider", ""))
        had_abstract = bool(normalize(metadata.get("abstract", "")))
        # ``provider_order`` is a priority order. Once a preferred provider has
        # supplied a field, later providers should supplement the record rather
        # than replace it. This is especially important for abstracts: a later
        # OpenAlex record must not overwrite a PubMed abstract merely because we
        # also queried OpenAlex for venue or open-access metadata.
        metadata = merge_metadata_values(metadata, current)
        chain = previous_chain
        if provider not in chain:
            chain.append(provider)
        metadata["metadata_provider_chain"] = "|".join(chain)
        if not had_abstract and normalize(current.get("abstract", "")):
            metadata["metadata_provider"] = provider
        elif previous_provider:
            metadata["metadata_provider"] = previous_provider
        elif not normalize(metadata.get("metadata_provider", "")):
            metadata["metadata_provider"] = provider

    if metadata:
        metadata["metadata_providers_queried"] = "|".join(queried)
        if errors:
            metadata["metadata_lookup_warnings"] = " | ".join(
                f"{err['provider']}: {err['error']}" for err in errors
            )
        if not normalize(metadata.get("abstract", "")):
            metadata["metadata_missing_reason"] = "providers_returned_no_abstract"
        else:
            metadata["metadata_missing_reason"] = ""
        return metadata, errors, queried

    return {}, errors, queried


def download_pdf(
    client: RateLimitedHttpClient,
    pdf_url: str,
    target_path: Path,
    *,
    retry: bool = True,
) -> Tuple[str, str, int]:
    if target_path.exists() and target_path.stat().st_size > 0:
        if file_is_valid_pdf(target_path):
            return "already_present", "", int(target_path.stat().st_size)
        return "invalid_pdf_existing", "local_file_is_not_pdf", int(target_path.stat().st_size)

    headers = {
        "Accept": "application/pdf,*/*;q=0.9",
    }
    if retry or not hasattr(client, "get_bytes_once"):
        body = client.get_bytes(url=pdf_url, headers=headers)
    else:
        body = client.get_bytes_once(url=pdf_url, headers=headers)
    if not body:
        return "download_failed", "empty_response", 0
    if not looks_like_pdf_bytes(body):
        return "invalid_pdf_content", "response_not_pdf", 0

    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(".tmp")
    tmp_path.write_bytes(body)
    tmp_path.replace(target_path)
    return "downloaded", "", len(body)


def metadata_pdf_candidates(metadata: dict, best_pdf_url: str) -> List[str]:
    candidates: List[str] = []
    for value in (
        best_pdf_url,
        metadata.get("pmc_europepmc_pdf_url", ""),
        metadata.get("pmc_oa_pdf_url", ""),
        metadata.get("unpaywall_best_pdf_url", ""),
        metadata.get("unpaywall_pdf_url_candidates", ""),
        metadata.get("pdf_url_candidates", ""),
    ):
        for candidate in split_candidates(value):
            add_unique(candidates, candidate)
    return rank_pdf_candidates(candidates)


def pdf_candidate_host(url: str) -> str:
    return urlparse(normalize(url)).netloc.lower()


def download_error_is_transient_host_failure(status: str, error: str) -> bool:
    text = f"{normalize(status)} {normalize(error)}".lower()
    return (
        "http error 429" in text
        or "too many requests" in text
        or "rate limit" in text
        or "http error 500" in text
        or "http error 502" in text
        or "http error 503" in text
        or "http error 504" in text
        or "empty_response" in text
        or "timeouterror" in text
        or "timed out" in text
        or "timeout" in text
    )


def download_error_is_rate_limited(status: str, error: str) -> bool:
    return download_error_is_transient_host_failure(status, error)


def ready_pdf_candidates(candidates: List[str], cooldown_until_by_host: Optional[Dict[str, float]]) -> List[str]:
    if not cooldown_until_by_host:
        return list(candidates)
    now = time.monotonic()
    ready: List[str] = []
    for candidate in candidates:
        host = pdf_candidate_host(candidate)
        if cooldown_until_by_host.get(host, 0.0) <= now:
            ready.append(candidate)
    return ready


def wait_for_next_pdf_candidate(candidates: List[str], cooldown_until_by_host: Optional[Dict[str, float]]) -> None:
    if not cooldown_until_by_host:
        return
    waits: List[float] = []
    now = time.monotonic()
    for candidate in candidates:
        host = pdf_candidate_host(candidate)
        until = cooldown_until_by_host.get(host, 0.0)
        if until > now:
            waits.append(until - now)
    if waits:
        time.sleep(max(0.0, min(waits)))


def download_pdf_candidates(
    client: RateLimitedHttpClient,
    pdf_urls: List[str],
    target_path: Path,
    cooldown_until_by_host: Optional[Dict[str, float]] = None,
    rate_limit_cooldown_sec: float = 0.0,
    progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    preserve_candidate_order: bool = False,
    study_doi: str = "",
    study_title: str = "",
    min_title_score: float = 0.86,
) -> Tuple[str, str, int, str, str]:
    candidates = list(dict.fromkeys(pdf_urls)) if preserve_candidate_order else rank_pdf_candidates(pdf_urls)
    if target_path.exists() and target_path.stat().st_size > 0:
        if file_is_valid_pdf(target_path):
            accepted, score, basis = pdf_source_identity_result(
                target_path,
                study_title,
                min_title_score,
                study_doi,
            )
            if accepted:
                return "already_present", "", int(target_path.stat().st_size), "", join_candidates(candidates)
            return (
                "invalid_pdf_existing",
                f"source_identity_mismatch:{basis}:{score:.3f}",
                int(target_path.stat().st_size),
                "",
                join_candidates(candidates),
            )
        return "invalid_pdf_existing", "local_file_is_not_pdf", int(target_path.stat().st_size), "", join_candidates(candidates)

    errors: List[str] = []
    # Rotate candidates before retrying a bad endpoint. A slow/stale first URL
    # should not block us from trying another legal OA PDF candidate for the DOI.
    max_rounds = max(1, int(getattr(client, "max_retries", 0)) + 1)
    for round_idx in range(max_rounds):
        pending = list(candidates)
        while pending:
            ready = ready_pdf_candidates(pending, cooldown_until_by_host)
            if not ready:
                wait_for_next_pdf_candidate(pending, cooldown_until_by_host)
                ready = ready_pdf_candidates(pending, cooldown_until_by_host) or list(pending)
            pdf_url = ready[0]
            pending.remove(pdf_url)
            if progress_callback:
                progress_callback(
                    {
                        "event": "candidate_attempt",
                        "round": round_idx + 1,
                        "url": pdf_url,
                        "host": pdf_candidate_host(pdf_url),
                    }
                )
            try:
                status, error, size = download_pdf(
                    client=client,
                    pdf_url=pdf_url,
                    target_path=target_path,
                    retry=False,
                )
            except Exception as err:
                status = "download_failed"
                error = f"{type(err).__name__}: {err}"
                size = 0
            if progress_callback:
                progress_callback(
                    {
                        "event": "candidate_result",
                        "round": round_idx + 1,
                        "url": pdf_url,
                        "host": pdf_candidate_host(pdf_url),
                        "status": status,
                        "error": error,
                        "size": size,
                    }
                )
            if status in {"downloaded", "already_present"}:
                accepted, score, basis = pdf_source_identity_result(
                    target_path,
                    study_title,
                    min_title_score,
                    study_doi,
                )
                if accepted:
                    return status, "", size, pdf_url, join_candidates(candidates)
                identity_error = f"source_identity_mismatch:{basis}:{score:.3f}"
                if status == "downloaded":
                    target_path.unlink(missing_ok=True)
                status = "source_identity_mismatch"
                error = identity_error
            if (
                cooldown_until_by_host is not None
                and rate_limit_cooldown_sec > 0
                and download_error_is_transient_host_failure(status, error)
            ):
                host = pdf_candidate_host(pdf_url)
                if host:
                    until = time.monotonic() + rate_limit_cooldown_sec
                    cooldown_until_by_host[host] = max(cooldown_until_by_host.get(host, 0.0), until)
            errors.append(f"round {round_idx + 1}: {pdf_url} -> {status}: {error}")

    if not candidates:
        return "no_pdf_url", "no_pdf_url", 0, "", ""
    final_error = " || ".join(errors[:8])
    if len(errors) > 8:
        final_error += f" || ... {len(errors) - 8} more"
    return "download_failed", final_error, 0, "", join_candidates(candidates)
