#!/usr/bin/env python3
"""Audit study-linked datasets, code, registrations, and research materials.

This is a bounded pilot, not a graph integration step. It combines:

* deterministic signals from a stratified sample of converted full text;
* reverse DOI relations registered with DataCite;
* non-full-text PubMed LinkOut records; and
* typed Crossref relations for a small known-signal benchmark.

Every retained assertion preserves its source and retrieval timestamp. The
network pass has an explicit request ceiling so it can be run safely while
assessing likely enrichment yield.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.http_safety import (  # noqa: E402
    build_public_http_opener,
    read_bounded_response,
    validate_public_http_url,
)
from pipeline.ingest.metadata_utils import normalize_doi  # noqa: E402


DEFAULT_CANDIDATES = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_OUTPUT_DIR = (
    ROOT / "data" / "processed" / "corpus" / "research_resource_pilot_20260723"
)
USER_AGENT = "psychedelics-knowledge-graph-resource-audit/0.1"
MAX_RESPONSE_BYTES = 32 * 1024 * 1024

RESOURCE_COLUMNS = (
    "paper_doi",
    "resource_id",
    "resource_id_type",
    "resource_url",
    "resource_title",
    "resource_type",
    "repository",
    "relation_type",
    "provider",
    "extraction_method",
    "confidence",
    "evidence",
    "retrieved_at_utc",
)

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)

RESOURCE_DOI_PREFIXES = {
    "10.5061/dryad.": ("dryad", "dataset"),
    "10.5281/zenodo.": ("zenodo", "research_resource"),
    "10.6084/m9.figshare.": ("figshare", "research_resource"),
    "10.25387/g3.": ("figshare", "research_resource"),
    "10.17605/osf.io/": ("osf", "research_resource"),
    "10.7910/dvn/": ("dataverse", "dataset"),
    "10.4121/": ("4tu_research_data", "research_resource"),
    "10.17504/protocols.io.": ("protocols_io", "protocol"),
    "10.7303/syn": ("synapse", "dataset"),
}

REPOSITORY_URL_PATTERNS = (
    ("dryad", "dataset", ("datadryad.org", "doi.org/10.5061/dryad")),
    ("zenodo", "research_resource", ("zenodo.org", "doi.org/10.5281/zenodo")),
    ("figshare", "research_resource", ("figshare.com", "doi.org/10.6084/m9.figshare")),
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
    ("addgene", "research_material", ("addgene.org",)),
    ("protocols_io", "protocol", ("protocols.io",)),
)

DATA_HEADING_RE = re.compile(
    r"\b(data(?:\s+and\s+materials)?\s+availability|availability\s+of\s+data|"
    r"data\s+sharing|data\s+accessibility|data\s+and\s+code\s+availability)\b",
    re.IGNORECASE,
)
PUBLIC_REPOSITORY_RE = re.compile(
    r"\b(public(?:ly)?\s+(?:available|accessible)|deposited|archived|repository|"
    r"data\s+(?:are|is)\s+available|code\s+(?:is|are)\s+available)\b",
    re.IGNORECASE,
)
AVAILABLE_ON_REQUEST_RE = re.compile(
    r"\b(?:data|materials|code).{0,80}\bavailable\s+(?:from|upon|on)\s+(?:reasonable\s+)?request\b",
    re.IGNORECASE | re.DOTALL,
)
INCLUDED_IN_ARTICLE_RE = re.compile(
    r"\b(?:data|information).{0,100}\b(?:included|contained)\s+in\s+"
    r"(?:the\s+)?(?:article|paper|manuscript|supplement)",
    re.IGNORECASE | re.DOTALL,
)
NO_NEW_DATA_RE = re.compile(
    r"\bno\s+(?:new|novel)\s+(?:data|datasets?)\s+(?:were|was)\s+"
    r"(?:created|generated|analy[sz]ed)\b",
    re.IGNORECASE,
)
SUPPLEMENT_RE = re.compile(r"\bsupplement(?:ary|al)?\b", re.IGNORECASE)

ACCESSION_PATTERNS = (
    ("geo", "dataset", re.compile(r"\bGSE\d{3,9}\b", re.IGNORECASE)),
    (
        "bioproject",
        "dataset",
        re.compile(r"\b(?:PRJNA|PRJEB|PRJDB)\d{3,10}\b", re.IGNORECASE),
    ),
    ("clinicaltrials", "study_registration", re.compile(r"\bNCT\d{8}\b")),
    ("isrctn", "study_registration", re.compile(r"\bISRCTN\d{8}\b", re.IGNORECASE)),
    ("prospero", "protocol_registration", re.compile(r"\bCRD420\d{6,12}\b", re.IGNORECASE)),
    (
        "addgene",
        "research_material",
        re.compile(r"\bAddgene(?:\s+plasmid)?\s*#?\s*(\d{3,9})\b", re.IGNORECASE),
    ),
)

DATACITE_URL = "https://api.datacite.org/dois"
NCBI_ELINK_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
CROSSREF_URL = "https://api.crossref.org/works"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def normalize_doi_value(value: object) -> str:
    return normalize_doi(clean(value)).lower()


def percent(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 2) if denominator else 0.0


def year_band(value: object) -> str:
    match = re.search(r"\b(18|19|20)\d{2}\b", clean(value))
    if not match:
        return "unknown"
    year = int(match.group(0))
    if year <= 1999:
        return "through_1999"
    if year <= 2009:
        return "2000_2009"
    if year <= 2019:
        return "2010_2019"
    if year <= 2024:
        return "2020_2024"
    return "2025_plus"


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_stratified_sample(
    frame: pd.DataFrame,
    *,
    total: int,
    strata_columns: tuple[str, ...],
) -> pd.DataFrame:
    if total <= 0 or frame.empty:
        return frame.iloc[0:0].copy()
    work = frame.copy()
    work["_sample_hash"] = work["doi"].map(stable_hash)
    work = work.sort_values([*strata_columns, "_sample_hash", "doi"], kind="stable")
    groups = list(work.groupby(list(strata_columns), sort=True, dropna=False))
    per_group = total // max(1, len(groups))
    selected_indexes: list[int] = []
    for _, group in groups:
        selected_indexes.extend(group.head(per_group).index.tolist())
    remaining = total - len(selected_indexes)
    if remaining > 0:
        unused = work.loc[~work.index.isin(selected_indexes)]
        selected_indexes.extend(unused.head(remaining).index.tolist())
    return (
        work.loc[selected_indexes]
        .sort_values(["_sample_hash", "doi"], kind="stable")
        .drop(columns=["_sample_hash"])
        .head(total)
        .reset_index(drop=True)
    )


def split_paths(value: object) -> list[Path]:
    paths: list[Path] = []
    for item in clean(value).split(" | "):
        if item.strip():
            paths.append(Path(item.strip()))
    return paths


def normalized_url(value: str) -> str:
    return value.rstrip(".,;:)]}").replace("&amp;", "&")


def doi_from_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.hostname and parsed.hostname.casefold() in {"doi.org", "dx.doi.org"}:
        return normalize_doi_value(parsed.path.lstrip("/"))
    return ""


def doi_repository(doi: str) -> tuple[str, str] | None:
    lowered = doi.casefold()
    for prefix, classification in RESOURCE_DOI_PREFIXES.items():
        if lowered.startswith(prefix):
            return classification
    return None


def url_repository(url: str) -> tuple[str, str] | None:
    lowered = url.casefold()
    if "github.com/kermitt2/grobid" in lowered:
        return None
    for repository, resource_type, needles in REPOSITORY_URL_PATTERNS:
        if any(needle in lowered for needle in needles):
            return repository, resource_type
    return None


def context_window(text: str, start: int, end: int, radius: int = 220) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return " ".join(text[left:right].split())


def evidence_confidence(context: str, resource_type: str) -> str:
    lowered = context.casefold()
    direct_terms = (
        "available",
        "deposited",
        "archived",
        "data",
        "code",
        "script",
        "material",
        "plasmid",
        "accession",
        "registered",
    )
    if any(term in lowered for term in direct_terms):
        return "high"
    if resource_type in {"study_registration", "protocol_registration"}:
        return "medium"
    return "candidate"


def relation_for_resource(resource_type: str) -> str:
    return {
        "dataset": "has_associated_dataset",
        "software": "references_code_or_software",
        "protocol": "has_associated_protocol",
        "research_material": "uses_or_provides_research_material",
        "study_registration": "has_study_registration",
        "protocol_registration": "has_protocol_registration",
    }.get(resource_type, "has_associated_research_resource")


def best_fulltext(artifact: dict[str, Any]) -> str:
    extractions = artifact.get("extractions") or []
    best_backend = clean(artifact.get("best_backend"))
    for extraction in extractions:
        if clean(extraction.get("backend")) == best_backend and clean(extraction.get("text")):
            return clean(extraction.get("text"))
    for extraction in extractions:
        if clean(extraction.get("text")):
            return clean(extraction.get("text"))
    return ""


def base_resource_row(
    *,
    paper_doi: str,
    resource_id: str,
    resource_id_type: str,
    resource_url: str,
    resource_type: str,
    repository: str,
    relation_type: str,
    provider: str,
    extraction_method: str,
    confidence: str,
    evidence: str,
    retrieved_at_utc: str,
    resource_title: str = "",
) -> dict[str, str]:
    return {
        "paper_doi": paper_doi,
        "resource_id": resource_id,
        "resource_id_type": resource_id_type,
        "resource_url": resource_url,
        "resource_title": resource_title,
        "resource_type": resource_type,
        "repository": repository,
        "relation_type": relation_type,
        "provider": provider,
        "extraction_method": extraction_method,
        "confidence": confidence,
        "evidence": evidence[:800],
        "retrieved_at_utc": retrieved_at_utc,
    }


def scan_fulltext_sample(
    sample: pd.DataFrame,
    *,
    retrieved_at_utc: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    signals: list[dict[str, Any]] = []
    resources: list[dict[str, str]] = []
    failures: dict[str, str] = {}
    for index, row in enumerate(sample.itertuples(index=False), start=1):
        paper_doi = normalize_doi_value(row.doi)
        text = ""
        source_path = ""
        last_error = ""
        for path in split_paths(row.fulltext_artifact_paths):
            try:
                artifact = json.loads(path.read_text(encoding="utf-8"))
                candidate = best_fulltext(artifact)
            except (OSError, json.JSONDecodeError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                continue
            if len(candidate) > len(text):
                text = candidate
                source_path = str(path)
        if not text:
            failures[paper_doi] = last_error or "No readable full-text extraction"
            continue

        paper_resources: list[dict[str, str]] = []
        for match in URL_RE.finditer(text):
            url = normalized_url(match.group(0))
            classification = url_repository(url)
            if classification is None:
                continue
            repository, resource_type = classification
            resource_doi = doi_from_url(url)
            context = context_window(text, match.start(), match.end())
            confidence = evidence_confidence(context, resource_type)
            paper_resources.append(
                base_resource_row(
                    paper_doi=paper_doi,
                    resource_id=resource_doi or url,
                    resource_id_type="doi" if resource_doi else "url",
                    resource_url=url,
                    resource_type=resource_type,
                    repository=repository,
                    relation_type=relation_for_resource(resource_type),
                    provider="fulltext",
                    extraction_method="deterministic_repository_url",
                    confidence=confidence,
                    evidence=context,
                    retrieved_at_utc=retrieved_at_utc,
                )
            )

        for match in DOI_RE.finditer(text):
            resource_doi = normalize_doi_value(match.group(0))
            classification = doi_repository(resource_doi)
            if classification is None or resource_doi == paper_doi:
                continue
            repository, resource_type = classification
            context = context_window(text, match.start(), match.end())
            paper_resources.append(
                base_resource_row(
                    paper_doi=paper_doi,
                    resource_id=resource_doi,
                    resource_id_type="doi",
                    resource_url=f"https://doi.org/{resource_doi}",
                    resource_type=resource_type,
                    repository=repository,
                    relation_type=relation_for_resource(resource_type),
                    provider="fulltext",
                    extraction_method="deterministic_repository_doi",
                    confidence=evidence_confidence(context, resource_type),
                    evidence=context,
                    retrieved_at_utc=retrieved_at_utc,
                )
            )

        for repository, resource_type, pattern in ACCESSION_PATTERNS:
            for match in pattern.finditer(text):
                value = match.group(1) if repository == "addgene" else match.group(0)
                value = value.upper() if repository != "addgene" else value
                context = context_window(text, match.start(), match.end())
                paper_resources.append(
                    base_resource_row(
                        paper_doi=paper_doi,
                        resource_id=value,
                        resource_id_type="accession",
                        resource_url="",
                        resource_type=resource_type,
                        repository=repository,
                        relation_type=relation_for_resource(resource_type),
                        provider="fulltext",
                        extraction_method="deterministic_accession",
                        confidence=evidence_confidence(context, resource_type),
                        evidence=context,
                        retrieved_at_utc=retrieved_at_utc,
                    )
                )

        deduplicated: dict[tuple[str, str, str], dict[str, str]] = {}
        confidence_order = {"candidate": 0, "medium": 1, "high": 2}
        for item in paper_resources:
            key = (
                item["resource_id"].casefold(),
                item["repository"],
                item["relation_type"],
            )
            previous = deduplicated.get(key)
            if previous is None or confidence_order[item["confidence"]] > confidence_order[
                previous["confidence"]
            ]:
                deduplicated[key] = item
        paper_resources = list(deduplicated.values())
        resources.extend(paper_resources)
        repository_counts = Counter(item["repository"] for item in paper_resources)
        resource_type_counts = Counter(item["resource_type"] for item in paper_resources)
        signals.append(
            {
                "doi": paper_doi,
                "study_year": clean(row.study_year),
                "year_band": clean(row.year_band),
                "has_pmcid": bool(row.has_pmcid),
                "source_path": source_path,
                "data_availability_heading": bool(DATA_HEADING_RE.search(text)),
                "public_repository_statement": bool(PUBLIC_REPOSITORY_RE.search(text)),
                "available_on_request": bool(AVAILABLE_ON_REQUEST_RE.search(text)),
                "included_in_article_or_supplement": bool(INCLUDED_IN_ARTICLE_RE.search(text)),
                "no_new_data": bool(NO_NEW_DATA_RE.search(text)),
                "mentions_supplement": bool(SUPPLEMENT_RE.search(text)),
                "resource_count": len(paper_resources),
                "resource_repositories": " | ".join(sorted(repository_counts)),
                "resource_types": " | ".join(sorted(resource_type_counts)),
                "high_confidence_resource_count": sum(
                    item["confidence"] == "high" for item in paper_resources
                ),
                "scan_order": index,
            }
        )
        if index % 100 == 0:
            print(f"Scanned {index}/{len(sample)} full-text artifacts", flush=True)

    return (
        pd.DataFrame(signals),
        pd.DataFrame(resources, columns=RESOURCE_COLUMNS),
        failures,
    )


class JsonClient:
    def __init__(self, *, request_cap: int, min_interval_seconds: float = 0.12):
        self.opener = build_public_http_opener()
        self.request_cap = request_cap
        self.min_interval_seconds = min_interval_seconds
        self.request_count = 0
        self.last_request_monotonic = 0.0
        self.log: list[dict[str, Any]] = []

    def fetch(
        self,
        *,
        provider: str,
        url: str,
        params: list[tuple[str, str]] | None = None,
        method: str = "GET",
        attempts: int = 4,
    ) -> dict[str, Any]:
        if self.request_count >= self.request_cap:
            raise RuntimeError(f"Network request cap reached ({self.request_cap})")
        method = method.upper()
        query = urlencode(params or [])
        if method == "GET" and query:
            request_url = f"{url}?{query}"
            body = None
        else:
            request_url = url
            body = query.encode("utf-8") if query else None
        validate_public_http_url(request_url)
        query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest() if query else ""
        last_error = ""
        for attempt in range(1, attempts + 1):
            elapsed = time.monotonic() - self.last_request_monotonic
            if elapsed < self.min_interval_seconds:
                time.sleep(self.min_interval_seconds - elapsed)
            self.request_count += 1
            started = now_utc()
            request = Request(
                request_url,
                data=body,
                method=method,
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            )
            try:
                with self.opener.open(request, timeout=45) as response:
                    payload = read_bounded_response(response, MAX_RESPONSE_BYTES)
                    status = int(getattr(response, "status", 200))
                self.last_request_monotonic = time.monotonic()
                decoded = json.loads(payload.decode("utf-8"))
                self.log.append(
                    {
                        "provider": provider,
                        "endpoint": url,
                        "method": method,
                        "query_sha256": query_hash,
                        "attempt": attempt,
                        "status": status,
                        "result": "ok",
                        "error": "",
                        "retrieved_at_utc": started,
                    }
                )
                return decoded
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
                self.last_request_monotonic = time.monotonic()
                status = int(exc.code) if isinstance(exc, HTTPError) else 0
                last_error = f"{type(exc).__name__}: {exc}"
                self.log.append(
                    {
                        "provider": provider,
                        "endpoint": url,
                        "method": method,
                        "query_sha256": query_hash,
                        "attempt": attempt,
                        "status": status,
                        "result": "error",
                        "error": last_error,
                        "retrieved_at_utc": started,
                    }
                )
                if status and status not in {429, 500, 502, 503, 504}:
                    break
                if self.request_count >= self.request_cap:
                    break
                time.sleep(min(8.0, 0.75 * (2 ** (attempt - 1))))
        raise RuntimeError(f"{provider} request failed: {last_error}")


def chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def datacite_reverse_relations(
    client: JsonClient,
    cohort: pd.DataFrame,
    *,
    batch_size: int,
    retrieved_at_utc: str,
) -> tuple[list[dict[str, str]], dict[str, str]]:
    doi_to_title = dict(zip(cohort["doi"], cohort["study_title"], strict=False))
    output: list[dict[str, str]] = []
    failures: dict[str, str] = {}
    doi_values = sorted(doi_to_title)
    for batch_number, batch in enumerate(chunks(doi_values, batch_size), start=1):
        query = "relatedIdentifiers.relatedIdentifier:(" + " OR ".join(
            f'"{doi}"' for doi in batch
        ) + ")"
        try:
            payload = client.fetch(
                provider="datacite",
                url=DATACITE_URL,
                params=[
                    ("query", query),
                    ("page[size]", "100"),
                    (
                        "fields[dois]",
                        "doi,titles,types,relatedIdentifiers,url,publisher,publicationYear",
                    ),
                ],
            )
        except RuntimeError as exc:
            for doi in batch:
                failures[doi] = str(exc)
            continue
        total = int((payload.get("meta") or {}).get("total") or 0)
        if total > 100:
            for doi in batch:
                failures[doi] = f"DataCite batch truncated at 100 of {total} results"
        batch_set = set(batch)
        for item in payload.get("data") or []:
            attributes = item.get("attributes") or {}
            resource_doi = normalize_doi_value(item.get("id") or attributes.get("doi"))
            titles = attributes.get("titles") or []
            title = clean(titles[0].get("title")) if titles else ""
            resource_type = clean((attributes.get("types") or {}).get("resourceTypeGeneral"))
            repository = clean(attributes.get("publisher"))
            resource_url = clean(attributes.get("url")) or (
                f"https://doi.org/{resource_doi}" if resource_doi else ""
            )
            for relation in attributes.get("relatedIdentifiers") or []:
                paper_doi = normalize_doi_value(relation.get("relatedIdentifier"))
                if paper_doi not in batch_set:
                    continue
                output.append(
                    base_resource_row(
                        paper_doi=paper_doi,
                        resource_id=resource_doi,
                        resource_id_type="doi",
                        resource_url=resource_url,
                        resource_title=title,
                        resource_type=resource_type.casefold() or "research_resource",
                        repository=repository,
                        relation_type=clean(relation.get("relationType")),
                        provider="datacite",
                        extraction_method="registered_reverse_doi_relation",
                        confidence="high",
                        evidence=(
                            f"DataCite resource {resource_doi} declares "
                            f"{clean(relation.get('relationType'))} {paper_doi}"
                        ),
                        retrieved_at_utc=retrieved_at_utc,
                    )
                )
        print(
            f"DataCite batch {batch_number}: {len(batch)} papers, {total} candidate resources",
            flush=True,
        )
    return output, failures


def datacite_resource_metadata(
    client: JsonClient,
    fulltext_resources: pd.DataFrame,
    *,
    batch_size: int,
    retrieved_at_utc: str,
) -> list[dict[str, str]]:
    if fulltext_resources.empty:
        return []
    doi_rows = fulltext_resources.loc[
        fulltext_resources["resource_id_type"].eq("doi")
        & fulltext_resources["resource_id"].map(bool)
    ].copy()
    if doi_rows.empty:
        return []
    resource_to_papers: dict[str, set[str]] = defaultdict(set)
    for paper_doi, resource_doi in doi_rows[["paper_doi", "resource_id"]].itertuples(
        index=False, name=None
    ):
        resource_to_papers[normalize_doi_value(resource_doi)].add(paper_doi)
    output: list[dict[str, str]] = []
    for batch_number, batch in enumerate(
        chunks(sorted(resource_to_papers), batch_size), start=1
    ):
        query = "doi:(" + " OR ".join(f'"{doi}"' for doi in batch) + ")"
        try:
            payload = client.fetch(
                provider="datacite",
                url=DATACITE_URL,
                params=[
                    ("query", query),
                    ("page[size]", "100"),
                    (
                        "fields[dois]",
                        "doi,titles,types,relatedIdentifiers,url,publisher,publicationYear",
                    ),
                ],
            )
        except RuntimeError:
            continue
        returned = 0
        for item in payload.get("data") or []:
            attributes = item.get("attributes") or {}
            resource_doi = normalize_doi_value(item.get("id") or attributes.get("doi"))
            if resource_doi not in resource_to_papers:
                continue
            returned += 1
            titles = attributes.get("titles") or []
            title = clean(titles[0].get("title")) if titles else ""
            resource_type = clean((attributes.get("types") or {}).get("resourceTypeGeneral"))
            repository = clean(attributes.get("publisher"))
            resource_url = clean(attributes.get("url")) or f"https://doi.org/{resource_doi}"
            for paper_doi in resource_to_papers[resource_doi]:
                output.append(
                    base_resource_row(
                        paper_doi=paper_doi,
                        resource_id=resource_doi,
                        resource_id_type="doi",
                        resource_url=resource_url,
                        resource_title=title,
                        resource_type=resource_type.casefold() or "research_resource",
                        repository=repository,
                        relation_type="fulltext_asserted_association",
                        provider="datacite",
                        extraction_method="resource_doi_metadata_lookup",
                        confidence="high",
                        evidence=(
                            "The paper full text names this repository DOI; DataCite "
                            "supplies resource type, title, and publisher."
                        ),
                        retrieved_at_utc=retrieved_at_utc,
                    )
                )
        print(
            f"DataCite resource batch {batch_number}: {len(batch)} requested, {returned} found",
            flush=True,
        )
    return output


def classify_linkout(
    provider_name: str,
    category: str,
    url: str,
) -> tuple[str, str]:
    repository_class = url_repository(url)
    if repository_class:
        return repository_class
    lowered = f"{provider_name} {category}".casefold()
    if "plasmid" in lowered or "research material" in lowered:
        return provider_name or "linkout", "research_material"
    if "data" in lowered or "repository" in lowered:
        return provider_name or "linkout", "dataset"
    if "protocol" in lowered:
        return provider_name or "linkout", "protocol"
    return provider_name or "linkout", "research_resource"


def pubmed_linkouts(
    client: JsonClient,
    cohort: pd.DataFrame,
    *,
    batch_size: int,
    retrieved_at_utc: str,
) -> tuple[list[dict[str, str]], dict[str, str]]:
    pmid_to_doi = {
        clean(pmid): doi
        for doi, pmid in cohort[["doi", "pmid"]].itertuples(index=False, name=None)
        if clean(pmid).isdigit()
    }
    output: list[dict[str, str]] = []
    failures: dict[str, str] = {}
    pmids = sorted(pmid_to_doi, key=int)
    for batch_number, batch in enumerate(chunks(pmids, batch_size), start=1):
        params = [
            ("dbfrom", "pubmed"),
            ("cmd", "llinks"),
            ("retmode", "json"),
            ("tool", "psychedelics_kg_resource_audit"),
        ]
        params.extend(("id", pmid) for pmid in batch)
        try:
            payload = client.fetch(
                provider="pubmed_linkout",
                url=NCBI_ELINK_URL,
                params=params,
                method="POST",
            )
        except RuntimeError as exc:
            for pmid in batch:
                failures[pmid_to_doi[pmid]] = str(exc)
            continue
        useful_count = 0
        for linkset in payload.get("linksets") or []:
            for id_urls in linkset.get("idurllist") or []:
                pmid = clean(id_urls.get("id"))
                paper_doi = pmid_to_doi.get(pmid)
                if not paper_doi:
                    continue
                for objurl in id_urls.get("objurls") or []:
                    categories = [clean(value) for value in objurl.get("categories") or []]
                    if any(value.casefold() == "full text sources" for value in categories):
                        continue
                    category = " | ".join(categories)
                    url = clean((objurl.get("url") or {}).get("value"))
                    provider_name = clean((objurl.get("provider") or {}).get("name"))
                    repository, resource_type = classify_linkout(
                        provider_name, category, url
                    )
                    useful_count += 1
                    output.append(
                        base_resource_row(
                            paper_doi=paper_doi,
                            resource_id=url,
                            resource_id_type="url",
                            resource_url=url,
                            resource_title=clean(objurl.get("linkname")),
                            resource_type=resource_type,
                            repository=repository,
                            relation_type=relation_for_resource(resource_type),
                            provider="pubmed_linkout",
                            extraction_method="registered_linkout",
                            confidence="high",
                            evidence=(
                                f"PubMed LinkOut category={category}; "
                                f"provider={provider_name}"
                            ),
                            retrieved_at_utc=retrieved_at_utc,
                        )
                    )
        print(
            f"PubMed LinkOut batch {batch_number}: {len(batch)} PMIDs, "
            f"{useful_count} non-full-text links",
            flush=True,
        )
    return output, failures


def crossref_relations(
    client: JsonClient,
    cohort: pd.DataFrame,
    *,
    limit: int,
    retrieved_at_utc: str,
) -> tuple[list[dict[str, str]], dict[str, str], list[str]]:
    selected = (
        cohort.assign(_hash=cohort["doi"].map(stable_hash))
        .sort_values(["_hash", "doi"], kind="stable")
        .head(limit)
    )
    output: list[dict[str, str]] = []
    failures: dict[str, str] = {}
    selected_dois = selected["doi"].tolist()
    for index, paper_doi in enumerate(selected_dois, start=1):
        endpoint = f"{CROSSREF_URL}/{quote(paper_doi, safe='')}"
        try:
            payload = client.fetch(provider="crossref", url=endpoint)
        except RuntimeError as exc:
            failures[paper_doi] = str(exc)
            continue
        message = payload.get("message") or {}
        for relation_type, relations in (message.get("relation") or {}).items():
            for relation in relations or []:
                resource_id = clean(relation.get("id"))
                id_type = clean(relation.get("id-type")).casefold()
                resource_doi = normalize_doi_value(resource_id) if id_type == "doi" else ""
                classification = doi_repository(resource_doi) if resource_doi else None
                repository, resource_type = classification or ("", "related_work")
                output.append(
                    base_resource_row(
                        paper_doi=paper_doi,
                        resource_id=resource_doi or resource_id,
                        resource_id_type=id_type or "identifier",
                        resource_url=(
                            f"https://doi.org/{resource_doi}" if resource_doi else ""
                        ),
                        resource_type=resource_type,
                        repository=repository,
                        relation_type=relation_type,
                        provider="crossref",
                        extraction_method="registered_typed_relation",
                        confidence="high",
                        evidence=(
                            f"Crossref relation asserted-by="
                            f"{clean(relation.get('asserted-by'))}"
                        ),
                        retrieved_at_utc=retrieved_at_utc,
                    )
                )
        if index % 5 == 0 or index == len(selected_dois):
            print(f"Crossref benchmark {index}/{len(selected_dois)} papers", flush=True)
    return output, failures, selected_dois


def deduplicate_resources(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=RESOURCE_COLUMNS)
    output = frame.copy()
    for column in RESOURCE_COLUMNS:
        if column not in output.columns:
            output[column] = ""
        output[column] = output[column].map(clean)
    output["_identity"] = output.apply(
        lambda row: "|".join(
            (
                row["paper_doi"].casefold(),
                row["resource_id"].casefold(),
                row["relation_type"].casefold(),
                row["provider"].casefold(),
                row["extraction_method"].casefold(),
            )
        ),
        axis=1,
    )
    output = (
        output.sort_values(
            ["paper_doi", "provider", "repository", "resource_id"], kind="stable"
        )
        .drop_duplicates("_identity", keep="first")
        .drop(columns="_identity")
        .reset_index(drop=True)
    )
    return output.loc[:, RESOURCE_COLUMNS]


def counter_dict(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(value for value in values if value).items()))


def build_report(
    *,
    scope: pd.DataFrame,
    provider_sample: pd.DataFrame,
    fulltext_sample: pd.DataFrame,
    fulltext_signals: pd.DataFrame,
    resources: pd.DataFrame,
    requests: pd.DataFrame,
    failures: dict[str, dict[str, str]],
    crossref_selected: list[str],
    run_started_at_utc: str,
) -> dict[str, Any]:
    provider_resources = resources.loc[
        resources["paper_doi"].isin(set(provider_sample["doi"]))
    ]
    fulltext_resources = resources.loc[resources["provider"].eq("fulltext")]
    high_precision_datacite = provider_resources.loc[
        provider_resources["provider"].eq("datacite")
        & provider_resources["extraction_method"].eq("registered_reverse_doi_relation")
        & provider_resources["relation_type"].eq("IsSupplementTo")
        & provider_resources["resource_type"].isin(
            {"dataset", "software", "collection", "image", "text"}
        )
    ]
    high_precision_linkout = provider_resources.loc[
        provider_resources["provider"].eq("pubmed_linkout")
        & (
            provider_resources["repository"].eq("figshare")
            | provider_resources["resource_url"].str.contains(
                r"data\.niaid\.nih\.gov/resources\?id=(?:gse|prj)",
                case=False,
                regex=True,
                na=False,
            )
        )
    ]
    high_precision_crossref = provider_resources.loc[
        provider_resources["provider"].eq("crossref")
        & provider_resources["relation_type"]
        .str.replace(r"[^a-z]", "", regex=True)
        .str.casefold()
        .eq("issupplementedby")
    ]
    high_precision_papers = {
        "datacite": set(high_precision_datacite["paper_doi"]),
        "pubmed_linkout": set(high_precision_linkout["paper_doi"]),
        "crossref": set(high_precision_crossref["paper_doi"]),
    }
    high_precision_union = set().union(*high_precision_papers.values())
    by_provider: dict[str, Any] = {}
    for provider, frame in resources.groupby("provider", sort=True):
        by_provider[provider] = {
            "assertion_rows": len(frame),
            "papers_with_assertions": int(frame["paper_doi"].nunique()),
            "resource_types": counter_dict(frame["resource_type"]),
            "repositories": counter_dict(frame["repository"]),
            "relation_types": counter_dict(frame["relation_type"]),
        }

    random_provider_papers: dict[str, set[str]] = {}
    sample_dois = set(provider_sample["doi"])
    for provider in ("datacite", "pubmed_linkout"):
        random_provider_papers[provider] = set(
            resources.loc[
                resources["provider"].eq(provider)
                & resources["paper_doi"].isin(sample_dois),
                "paper_doi",
            ]
        )
    overlap_counts = {
        "datacite_only": len(
            random_provider_papers["datacite"]
            - random_provider_papers["pubmed_linkout"]
        ),
        "pubmed_linkout_only": len(
            random_provider_papers["pubmed_linkout"]
            - random_provider_papers["datacite"]
        ),
        "both": len(
            random_provider_papers["datacite"]
            & random_provider_papers["pubmed_linkout"]
        ),
        "neither": len(
            sample_dois
            - random_provider_papers["datacite"]
            - random_provider_papers["pubmed_linkout"]
        ),
    }

    signal_papers = set(
        fulltext_resources.loc[
            fulltext_resources["confidence"].isin({"high", "medium"}), "paper_doi"
        ]
    )
    benchmark = set(crossref_selected)
    benchmark_coverage = {}
    for provider in ("datacite", "pubmed_linkout", "crossref"):
        found = set(resources.loc[resources["provider"].eq(provider), "paper_doi"])
        denominator = benchmark if provider == "crossref" else signal_papers
        benchmark_coverage[provider] = {
            "denominator_papers": len(denominator),
            "papers_found": len(found & denominator),
            "percent": percent(len(found & denominator), len(denominator)),
        }

    local_signal_counts = {}
    for column in (
        "data_availability_heading",
        "public_repository_statement",
        "available_on_request",
        "included_in_article_or_supplement",
        "no_new_data",
        "mentions_supplement",
    ):
        count = int(fulltext_signals[column].sum()) if column in fulltext_signals else 0
        local_signal_counts[column] = {
            "papers": count,
            "percent": percent(count, len(fulltext_signals)),
        }

    request_result_counts = (
        requests.groupby(["provider", "result"]).size().to_dict() if not requests.empty else {}
    )
    return {
        "audit": "paper_research_resource_pilot",
        "schema_version": "paper_research_resource_pilot_v0.1",
        "run_started_at_utc": run_started_at_utc,
        "run_completed_at_utc": now_utc(),
        "scope": {
            "screened_unique_dois": int(scope["doi"].nunique()),
            "provider_sample_papers": len(provider_sample),
            "provider_sample_valid_pmids": int(
                provider_sample["pmid"].map(lambda value: clean(value).isdigit()).sum()
            ),
            "fulltext_sample_papers": len(fulltext_sample),
            "fulltext_scanned_successfully": len(fulltext_signals),
            "fulltext_scan_failures": len(fulltext_sample) - len(fulltext_signals),
        },
        "fulltext_signals": local_signal_counts,
        "fulltext_resource_candidates": {
            "assertion_rows": len(fulltext_resources),
            "papers_with_any_candidate": int(fulltext_resources["paper_doi"].nunique()),
            "papers_with_high_or_medium_confidence_candidate": len(signal_papers),
            "repositories": counter_dict(fulltext_resources["repository"]),
            "resource_types": counter_dict(fulltext_resources["resource_type"]),
        },
        "provider_yield": by_provider,
        "provider_sample_union": {
            "status": "raw_unfiltered_candidate_links",
            "papers_with_any_datacite_or_linkout_assertion": int(
                provider_resources.loc[
                    provider_resources["provider"].isin({"datacite", "pubmed_linkout"}),
                    "paper_doi",
                ].nunique()
            ),
            "percent": percent(
                int(
                    provider_resources.loc[
                        provider_resources["provider"].isin(
                            {"datacite", "pubmed_linkout"}
                        ),
                        "paper_doi",
                    ].nunique()
                ),
                len(provider_sample),
            ),
            "overlap": overlap_counts,
        },
        "high_precision_provider_sample": {
            "papers_with_registered_supplement_or_repository_dataset_link": len(
                high_precision_union
            ),
            "percent": percent(len(high_precision_union), len(provider_sample)),
            "papers_by_provider": {
                provider: len(values)
                for provider, values in high_precision_papers.items()
            },
            "selection_rule": (
                "DataCite IsSupplementTo relations to dataset/software/collection/image/text; "
                "PubMed LinkOut figshare links or NIAID GSE/PRJ records; Crossref "
                "is-supplemented-by relations."
            ),
        },
        "known_fulltext_signal_recall": benchmark_coverage,
        "network": {
            "request_attempts": len(requests),
            "successful_requests": int(requests["result"].eq("ok").sum())
            if not requests.empty
            else 0,
            "failed_request_attempts": int(requests["result"].eq("error").sum())
            if not requests.empty
            else 0,
            "by_provider_and_result": {
                f"{provider}:{result}": int(count)
                for (provider, result), count in sorted(request_result_counts.items())
            },
        },
        "failures": {
            provider: {
                "count": len(values),
                "examples": dict(list(sorted(values.items()))[:10]),
            }
            for provider, values in failures.items()
        },
        "count_reconciliation": {
            "resource_rows_total": len(resources),
            "resource_rows_by_provider_sum": sum(
                value["assertion_rows"] for value in by_provider.values()
            ),
            "provider_sample_overlap_sum": sum(overlap_counts.values()),
            "provider_sample_expected": len(provider_sample),
        },
        "interpretation_guards": [
            "Full-text repository and accession detection is deterministic and may include "
            "resources cited as tools or prior data rather than outputs of the focal study.",
            "A DataCite reverse relation is high precision but incomplete because repositories "
            "do not consistently register the article DOI in dataset metadata.",
            "PubMed LinkOut categories include research materials as well as datasets and must "
            "not be collapsed into a single has_dataset edge.",
            "Crossref relations include preprints, versions, and corrections; only explicitly "
            "typed resource relations should be promoted to dataset or software edges.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--provider-sample-size", type=int, default=500)
    parser.add_argument("--fulltext-sample-size", type=int, default=1000)
    parser.add_argument("--datacite-batch-size", type=int, default=20)
    parser.add_argument("--linkout-batch-size", type=int, default=100)
    parser.add_argument("--crossref-limit", type=int, default=20)
    parser.add_argument("--request-cap", type=int, default=90)
    parser.add_argument(
        "--network",
        action="store_true",
        help="Query DataCite, PubMed LinkOut, and Crossref within --request-cap.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_started_at_utc = now_utc()
    candidates = pd.read_parquet(args.candidates)
    required = {
        "doi",
        "study_title",
        "study_year",
        "pmid",
        "pmcid",
        "fulltext_artifact_paths",
        "retained_for_extraction_candidate",
    }
    missing = sorted(required - set(candidates.columns))
    if missing:
        raise ValueError(f"{args.candidates} is missing required columns: {missing}")
    scope = candidates.loc[
        candidates["retained_for_extraction_candidate"].fillna(False).astype(bool),
        list(required),
    ].copy()
    scope["doi"] = scope["doi"].map(normalize_doi_value)
    scope = scope.loc[scope["doi"].map(bool)].drop_duplicates("doi", keep="first")
    scope["study_title"] = scope["study_title"].map(clean)
    scope["study_year"] = scope["study_year"].map(clean)
    scope["pmid"] = scope["pmid"].map(clean)
    scope["pmcid"] = scope["pmcid"].map(clean)
    scope["year_band"] = scope["study_year"].map(year_band)
    scope["has_pmcid"] = scope["pmcid"].map(bool)

    provider_sample = stable_stratified_sample(
        scope,
        total=min(args.provider_sample_size, len(scope)),
        strata_columns=("year_band", "has_pmcid"),
    )
    fulltext_scope = scope.loc[scope["fulltext_artifact_paths"].map(lambda value: bool(clean(value)))]
    fulltext_sample = stable_stratified_sample(
        fulltext_scope,
        total=min(args.fulltext_sample_size, len(fulltext_scope)),
        strata_columns=("year_band", "has_pmcid"),
    )
    retrieved_at_utc = now_utc()
    fulltext_signals, fulltext_resources, fulltext_failures = scan_fulltext_sample(
        fulltext_sample,
        retrieved_at_utc=retrieved_at_utc,
    )

    network_resources: list[dict[str, str]] = []
    request_log = pd.DataFrame()
    failures: dict[str, dict[str, str]] = {"fulltext": fulltext_failures}
    crossref_selected: list[str] = []
    if args.network:
        client = JsonClient(request_cap=args.request_cap)
        datacite_rows, datacite_failures = datacite_reverse_relations(
            client,
            provider_sample,
            batch_size=args.datacite_batch_size,
            retrieved_at_utc=retrieved_at_utc,
        )
        network_resources.extend(datacite_rows)
        failures["datacite"] = datacite_failures
        network_resources.extend(
            datacite_resource_metadata(
                client,
                fulltext_resources,
                batch_size=args.datacite_batch_size,
                retrieved_at_utc=retrieved_at_utc,
            )
        )
        linkout_cohort = pd.concat(
            [
                provider_sample,
                scope.loc[
                    scope["doi"].isin(set(fulltext_resources["paper_doi"]))
                    & scope["pmid"].map(lambda value: clean(value).isdigit())
                ],
            ],
            ignore_index=True,
        ).drop_duplicates("doi", keep="first")
        linkout_rows, linkout_failures = pubmed_linkouts(
            client,
            linkout_cohort,
            batch_size=args.linkout_batch_size,
            retrieved_at_utc=retrieved_at_utc,
        )
        network_resources.extend(linkout_rows)
        failures["pubmed_linkout"] = linkout_failures
        signal_cohort = scope.loc[
            scope["doi"].isin(set(fulltext_resources["paper_doi"]))
        ].copy()
        crossref_rows, crossref_failures, crossref_selected = crossref_relations(
            client,
            signal_cohort,
            limit=args.crossref_limit,
            retrieved_at_utc=retrieved_at_utc,
        )
        network_resources.extend(crossref_rows)
        failures["crossref"] = crossref_failures
        request_log = pd.DataFrame(client.log)

    resources = deduplicate_resources(
        pd.concat(
            [
                fulltext_resources,
                pd.DataFrame(network_resources, columns=RESOURCE_COLUMNS),
            ],
            ignore_index=True,
        )
    )
    report = build_report(
        scope=scope,
        provider_sample=provider_sample,
        fulltext_sample=fulltext_sample,
        fulltext_signals=fulltext_signals,
        resources=resources,
        requests=request_log,
        failures=failures,
        crossref_selected=crossref_selected,
        run_started_at_utc=run_started_at_utc,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    provider_sample.to_parquet(args.output_dir / "provider_sample.parquet", index=False)
    fulltext_sample.to_parquet(args.output_dir / "fulltext_sample.parquet", index=False)
    fulltext_signals.to_parquet(args.output_dir / "fulltext_signals.parquet", index=False)
    resources.to_parquet(args.output_dir / "paper_research_resources.parquet", index=False)
    request_log.to_parquet(args.output_dir / "request_log.parquet", index=False)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
