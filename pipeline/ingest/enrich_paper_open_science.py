#!/usr/bin/env python3
"""Build standalone paper-level open-science feature tables.

The stage materializes four conservative, user-facing paper facets without
modifying ``candidate_papers`` or the knowledge graph:

* Registered trial
* Open data
* Shared code
* Preregistered

Local article evidence is combined with structured PubMed trial accessions,
ClinicalTrials.gov publication links and registration dates, and typed
DataCite resource metadata. Every positive assertion retains its evidence and
provenance. Provider calls are bounded by an explicit request budget.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request
import xml.etree.ElementTree as ET

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.http_safety import (  # noqa: E402
    build_public_http_opener,
    read_bounded_response,
    validate_public_http_url,
)
from pipeline.ingest.metadata_utils import normalize, normalize_doi  # noqa: E402
from pipeline.ingest.open_science_features import (  # noqa: E402
    ASSERTION_COLUMNS,
    FEATURE_OPEN_DATA,
    FEATURE_PREREGISTERED,
    FEATURE_REGISTERED_TRIAL,
    FEATURE_SHARED_CODE,
    FEATURES,
    RESOURCE_CANDIDATE_COLUMNS,
    SUMMARY_SCHEMA_VERSION,
    deduplicate_assertions,
    deduplicate_resource_candidates,
    extract_trial_identifiers,
    finalize_assertion,
    has_nonnegated_preregistration,
    load_best_fulltext,
    local_assertions_and_resource_candidates,
    normalized_doi,
    now_utc,
    prospective_registration,
    repository_identifier_url,
    split_paths,
    trial_url,
)


DEFAULT_CANDIDATES = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "processed" / "corpus"
DEFAULT_MANUAL_VALIDATION = (
    ROOT
    / "data"
    / "processed"
    / "corpus"
    / "research_resource_pilot_20260723"
    / "manual_validation.json"
)

PUBMED_API = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
CLINICAL_TRIALS_API = "https://clinicaltrials.gov/api/v2/studies"
DATACITE_API = "https://api.datacite.org/dois"
USER_AGENT = "psychedelics-knowledge-graph-open-science-enrichment/1.0"
MAX_RESPONSE_BYTES = 128 * 1024 * 1024
ATTEMPT_SCHEMA_VERSION = "paper_open_science_provider_attempt_v1"
TRIAL_RECORD_SCHEMA_VERSION = "open_science_trial_registry_record_v1"
DATACITE_RECORD_SCHEMA_VERSION = "open_science_datacite_resource_record_v1"

ATTEMPT_COLUMNS = (
    "schema_version",
    "provider",
    "request_kind",
    "request_index",
    "endpoint",
    "request_ids",
    "request_ids_sha256",
    "requested_count",
    "returned_count",
    "http_status",
    "http_attempt_count",
    "result",
    "error",
    "elapsed_seconds",
    "retrieval_run_id",
    "retrieved_at_utc",
)

TRIAL_RECORD_COLUMNS = (
    "schema_version",
    "nct_id",
    "nct_id_aliases",
    "clinicaltrials_url",
    "brief_title",
    "study_type",
    "study_start_date",
    "study_first_submitted_date",
    "prospective_registration",
    "registration_timing_status",
    "publication_reference_count",
    "result_reference_count",
    "derived_reference_count",
    "linked_scope_paper_count",
    "linked_scope_paper_dois",
    "provider",
    "retrieval_run_id",
    "retrieved_at_utc",
)

DATACITE_RECORD_COLUMNS = (
    "schema_version",
    "resource_doi",
    "resource_url",
    "resource_title",
    "resource_type_general",
    "resource_type",
    "publisher",
    "repository",
    "linked_scope_paper_count",
    "linked_scope_paper_dois",
    "provider",
    "retrieval_run_id",
    "retrieved_at_utc",
)

SUMMARY_COLUMNS = (
    "schema_version",
    "doi",
    "has_registered_trial",
    "registered_trial_ids",
    "registered_trial_urls",
    "registered_trial_count",
    "has_open_data",
    "open_data_resource_ids",
    "open_data_urls",
    "open_data_repositories",
    "open_data_resource_count",
    "has_shared_code",
    "shared_code_resource_ids",
    "shared_code_urls",
    "shared_code_repositories",
    "shared_code_resource_count",
    "has_preregistered",
    "preregistration_ids",
    "preregistration_urls",
    "preregistration_repositories",
    "preregistration_count",
    "open_science_features",
    "feature_count",
    "assertion_count",
    "evidence_providers",
    "evidence_source_types",
    "has_fulltext_evidence_source",
    "open_science_enrichment_status",
    "retrieval_run_id",
    "retrieved_at_utc",
)

CLINICAL_FIELDS = ",".join(
    (
        "NCTId",
        "NCTIdAlias",
        "BriefTitle",
        "StudyType",
        "StartDate",
        "StudyFirstSubmitDate",
        "ReferencePMID",
        "ReferenceType",
        "ReferenceCitation",
    )
)
ACCEPTED_TRIAL_REFERENCE_TYPES = {"RESULT", "DERIVED"}
REVIEW_PUBLICATION_RE = re.compile(
    r"\b(?:review|meta-analysis|systematic review)\b",
    re.IGNORECASE,
)
REVIEW_TITLE_RE = re.compile(
    r"\b(?:systematic|scoping|narrative|umbrella|integrative)\s+review\b|"
    r"\bmeta[\s-]analysis\b|\breview\s+of\b",
    re.IGNORECASE,
)
TRIAL_PUBLICATION_RE = re.compile(
    r"\b(?:randomized controlled trial|controlled clinical trial|clinical trial"
    r"(?:,\s*phase\s+[ivx]+)?)\b",
    re.IGNORECASE,
)


def clean(value: object) -> str:
    return normalize(value)


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).casefold() in {"1", "true", "yes", "y", "include", "retain"}


def default_run_id() -> str:
    return "open_science_" + dt.datetime.now(dt.timezone.utc).strftime(
        "%Y_%m_%d_%H%M%S"
    )


def chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def pipe(values: Iterable[object]) -> str:
    return " | ".join(sorted({clean(value) for value in values if clean(value)}))


def percent(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 2) if denominator else 0.0


def atomic_write_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}.", suffix=".parquet", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        frame.to_parquet(temporary, engine="pyarrow", index=False)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def frame_with_columns(
    rows: Iterable[dict[str, Any]],
    columns: tuple[str, ...],
) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows))
    for column in columns:
        if column not in frame.columns:
            frame[column] = ""
    return frame.loc[:, list(columns)].copy()


def build_scope(path: Path, limit: int = 0) -> pd.DataFrame:
    required = (
        "doi",
        "pmid",
        "study_title",
        "abstract",
        "publication_type",
        "trial_registry_ids",
        "retained_for_extraction_candidate",
        "fulltext_artifact_paths",
    )
    frame = pd.read_parquet(path)
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"Candidate table is missing required columns: {missing}")
    frame = frame.loc[
        frame["retained_for_extraction_candidate"].map(truthy), list(required)
    ].copy()
    frame["doi"] = frame["doi"].map(normalized_doi)
    frame = frame[frame["doi"].astype(bool)].sort_values("doi", kind="stable")
    if frame["doi"].duplicated().any():
        duplicates = frame.loc[frame["doi"].duplicated(False), "doi"].unique()
        raise ValueError(f"Duplicate normalized post-screening DOIs: {duplicates[:10]}")
    if limit > 0:
        frame = frame.head(limit)
    return frame.reset_index(drop=True)


def review_only_dois(scope: pd.DataFrame) -> set[str]:
    out: set[str] = set()
    for row in scope.to_dict("records"):
        publication_type = clean(row.get("publication_type", ""))
        title = clean(row.get("study_title", ""))
        review_signal = bool(
            REVIEW_PUBLICATION_RE.search(publication_type)
            or REVIEW_TITLE_RE.search(title)
        )
        trial_signal = bool(TRIAL_PUBLICATION_RE.search(publication_type))
        if review_signal and not trial_signal:
            out.add(row["doi"])
    return out


def apply_publication_semantic_guards(
    scope: pd.DataFrame,
    assertions: list[dict[str, str]],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    review_dois = review_only_dois(scope)
    kept: list[dict[str, str]] = []
    suppressed_review: list[dict[str, str]] = []
    suppressed_negated: list[dict[str, str]] = []
    for row in assertions:
        is_trial_feature = row["feature"] == FEATURE_REGISTERED_TRIAL
        is_trial_preregistration = (
            row["feature"] == FEATURE_PREREGISTERED
            and row["identifier_type"] == "trial_registry_id"
        )
        negated_explicit_preregistration = (
            row["feature"] == FEATURE_PREREGISTERED
            and row["evidence_method"]
            in {
                "explicit_preregistration_statement",
                "explicit_prospective_trial_registration_statement",
            }
            and not has_nonnegated_preregistration(row["evidence_text"])
        )
        if negated_explicit_preregistration:
            suppressed_negated.append(row)
        elif (
            row["doi"] in review_dois
            and (
                is_trial_feature or is_trial_preregistration
            )
        ):
            suppressed_review.append(row)
        else:
            kept.append(row)
    return deduplicate_assertions(kept), {
        "review_only_papers_in_scope": len(review_dois),
        "suppressed_review_trial_assertion_rows": len(suppressed_review),
        "suppressed_review_trial_papers": len(
            {row["doi"] for row in suppressed_review}
        ),
        "suppressed_negated_preregistration_assertion_rows": len(
            suppressed_negated
        ),
        "suppressed_negated_preregistration_papers": len(
            {row["doi"] for row in suppressed_negated}
        ),
    }


class ProviderClient:
    def __init__(
        self,
        *,
        max_requests: int,
        retrieval_run_id: str,
        retrieved_at_utc: str,
    ) -> None:
        self.max_requests = max_requests
        self.retrieval_run_id = retrieval_run_id
        self.retrieved_at_utc = retrieved_at_utc
        self.request_count = 0
        self.opener = build_public_http_opener()

    def fetch(
        self,
        *,
        provider: str,
        request_kind: str,
        request_index: int,
        endpoint: str,
        params: list[tuple[str, str]],
        request_ids: list[str],
        expect: str,
        pause_seconds: float = 0.15,
        http_method: str = "GET",
    ) -> tuple[Any, dict[str, Any]]:
        encoded_params = urlencode(params)
        method = http_method.upper()
        if method not in {"GET", "POST"}:
            raise ValueError(f"Unsupported HTTP method: {http_method}")
        request_url = f"{endpoint}?{encoded_params}" if method == "GET" else endpoint
        validate_public_http_url(request_url)
        started = time.monotonic()
        status = 0
        error = ""
        payload: Any = None
        attempts = 0
        for attempt in range(1, 5):
            if self.request_count >= self.max_requests:
                raise RuntimeError(
                    f"Provider request budget exhausted ({self.max_requests})"
                )
            self.request_count += 1
            attempts = attempt
            request = Request(
                request_url,
                data=encoded_params.encode("utf-8") if method == "POST" else None,
                headers={
                    "Accept": "*/*",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": USER_AGENT,
                },
                method=method,
            )
            try:
                with self.opener.open(request, timeout=90) as response:
                    status = int(getattr(response, "status", 200))
                    body = read_bounded_response(response, MAX_RESPONSE_BYTES)
                if expect == "json":
                    payload = json.loads(body.decode("utf-8"))
                elif expect == "xml":
                    payload = ET.fromstring(body)
                else:
                    raise ValueError(f"Unsupported response type: {expect}")
                error = ""
                break
            except (
                HTTPError,
                URLError,
                TimeoutError,
                json.JSONDecodeError,
                ET.ParseError,
            ) as exc:
                status = int(exc.code) if isinstance(exc, HTTPError) else 0
                error = f"{type(exc).__name__}: {exc}"
                if status and status not in {408, 429, 500, 502, 503, 504}:
                    break
                time.sleep(min(8.0, 0.75 * (2 ** (attempt - 1))))
        time.sleep(pause_seconds)
        ids_text = " | ".join(request_ids)
        attempt_row = {
            "schema_version": ATTEMPT_SCHEMA_VERSION,
            "provider": provider,
            "request_kind": request_kind,
            "request_index": request_index,
            "endpoint": endpoint,
            "request_ids": ids_text,
            "request_ids_sha256": hashlib.sha256(
                ids_text.encode("utf-8")
            ).hexdigest(),
            "requested_count": len(request_ids),
            "returned_count": 0,
            "http_status": status,
            "http_attempt_count": attempts,
            "result": "ok" if payload is not None and not error else "error",
            "error": error,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "retrieval_run_id": self.retrieval_run_id,
            "retrieved_at_utc": self.retrieved_at_utc,
        }
        if error or payload is None:
            raise RuntimeError(
                f"{provider} {request_kind} batch {request_index} failed: {error}"
            )
        return payload, attempt_row


def scan_local_evidence(
    scope: pd.DataFrame,
    *,
    retrieval_run_id: str,
    retrieved_at_utc: str,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], dict[str, Any]]:
    assertions: list[dict[str, str]] = []
    candidates: list[dict[str, Any]] = []
    fulltext_loaded = 0
    fulltext_missing = 0
    artifact_errors: list[dict[str, str]] = []
    for index, row in enumerate(scope.to_dict("records"), start=1):
        paths = split_paths(row.get("fulltext_artifact_paths", ""))
        fulltext, fulltext_path, load_error = load_best_fulltext(paths)
        if fulltext:
            fulltext_loaded += 1
        else:
            fulltext_missing += 1
        if load_error and paths and not fulltext:
            artifact_errors.append(
                {"doi": row["doi"], "error": load_error, "paths": pipe(paths)}
            )
        local_assertions, local_candidates = local_assertions_and_resource_candidates(
            doi=row["doi"],
            title=clean(row.get("study_title", "")),
            abstract=clean(row.get("abstract", "")),
            publication_type=clean(row.get("publication_type", "")),
            fulltext=fulltext,
            fulltext_path=fulltext_path,
            retrieval_run_id=retrieval_run_id,
            retrieved_at_utc=retrieved_at_utc,
        )
        assertions.extend(local_assertions)
        candidates.extend(local_candidates)
        if index % 250 == 0 or index == len(scope):
            print(
                f"Local scan {index:,}/{len(scope):,}: "
                f"{len(assertions):,} assertions, "
                f"{len(candidates):,} resource candidates",
                flush=True,
            )
    return (
        deduplicate_assertions(assertions),
        deduplicate_resource_candidates(candidates),
        {
            "papers_with_fulltext_loaded": fulltext_loaded,
            "papers_without_fulltext_loaded": fulltext_missing,
            "artifact_error_count": len(artifact_errors),
            "artifact_errors": artifact_errors[:100],
        },
    )


def pubmed_trial_assertions(
    scope: pd.DataFrame,
    *,
    client: ProviderClient,
    batch_size: int,
) -> tuple[
    list[dict[str, str]],
    dict[tuple[str, str], dict[str, str]],
    list[dict[str, Any]],
]:
    pmid_to_doi = {
        clean(pmid): doi
        for doi, pmid in scope[["doi", "pmid"]].itertuples(index=False, name=None)
        if clean(pmid)
    }
    assertions: list[dict[str, str]] = []
    links: dict[tuple[str, str], dict[str, str]] = {}
    attempts: list[dict[str, Any]] = []
    pmids = sorted(pmid_to_doi, key=lambda value: (len(value), value))
    batches = list(chunks(pmids, batch_size))
    for index, batch in enumerate(batches, start=1):
        root, attempt = client.fetch(
            provider="pubmed",
            request_kind="structured_trial_accessions",
            request_index=index,
            endpoint=PUBMED_API,
            params=[
                ("db", "pubmed"),
                ("id", ",".join(batch)),
                ("retmode", "xml"),
            ],
            request_ids=batch,
            expect="xml",
            pause_seconds=0.35,
            http_method="POST",
        )
        articles = root.findall(".//PubmedArticle")
        attempt["returned_count"] = len(articles)
        attempts.append(attempt)
        for article in articles:
            pmid = clean(article.findtext("./MedlineCitation/PMID"))
            doi = pmid_to_doi.get(pmid, "")
            if not doi:
                continue
            for data_bank in article.findall("./MedlineCitation/Article/DataBankList/DataBank"):
                bank_name = clean(data_bank.findtext("./DataBankName"))
                for accession_node in data_bank.findall(
                    "./AccessionNumberList/AccessionNumber"
                ):
                    accession = clean(accession_node.text)
                    for identifier, _, _ in extract_trial_identifiers(accession):
                        registry = (
                            "clinicaltrials_gov"
                            if identifier.startswith("NCT")
                            else re.sub(r"[^a-z0-9]+", "_", bank_name.casefold()).strip(
                                "_"
                            )
                            or "trial_registry"
                        )
                        assertions.append(
                            finalize_assertion(
                                doi=doi,
                                feature=FEATURE_REGISTERED_TRIAL,
                                identifier=identifier,
                                identifier_type="trial_registry_id",
                                url=trial_url(identifier),
                                repository=registry,
                                provider="pubmed",
                                provider_record_id=pmid,
                                source_type="pubmed_databank",
                                source_path="",
                                source_section="DataBankList",
                                evidence_text=(
                                    f"DataBankName={bank_name}; "
                                    f"AccessionNumber={identifier}"
                                ),
                                evidence_method="pubmed_structured_trial_accession",
                                retrieval_run_id=client.retrieval_run_id,
                                retrieved_at_utc=client.retrieved_at_utc,
                            )
                        )
                        links[(identifier, doi)] = {
                            "pmid": pmid,
                            "method": "pubmed_structured_trial_accession",
                        }
        print(
            f"PubMed batch {index}/{len(batches)}: "
            f"{len(batch)} requested, {len(articles)} returned",
            flush=True,
        )
    return deduplicate_assertions(assertions), links, attempts


def date_value(module: dict[str, Any], field: str) -> str:
    value = module.get(field) or {}
    return clean(value.get("date")) if isinstance(value, dict) else clean(value)


def citation_dois(value: str) -> set[str]:
    from pipeline.ingest.open_science_features import DOI_RE

    return {normalized_doi(match.group(0)) for match in DOI_RE.finditer(value)}


def trial_registry_enrichment(
    scope: pd.DataFrame,
    *,
    nct_ids: set[str],
    pubmed_links: dict[tuple[str, str], dict[str, str]],
    client: ProviderClient,
    batch_size: int,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], list[dict[str, Any]]]:
    doi_set = set(scope["doi"])
    pmid_to_doi = {
        clean(pmid): doi
        for doi, pmid in scope[["doi", "pmid"]].itertuples(index=False, name=None)
        if clean(pmid)
    }
    assertions: list[dict[str, str]] = []
    records: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    batches = list(chunks(sorted(nct_ids), batch_size))
    for index, batch in enumerate(batches, start=1):
        payload, attempt = client.fetch(
            provider="clinicaltrials_gov",
            request_kind="registration_timing_and_publication_links",
            request_index=index,
            endpoint=CLINICAL_TRIALS_API,
            params=[
                ("filter.ids", "|".join(batch)),
                ("pageSize", str(max(1, len(batch)))),
                ("format", "json"),
                ("fields", CLINICAL_FIELDS),
            ],
            request_ids=batch,
            expect="json",
        )
        studies = payload.get("studies") or []
        attempt["returned_count"] = len(studies)
        attempts.append(attempt)
        for study in studies:
            protocol = study.get("protocolSection") or {}
            identification = protocol.get("identificationModule") or {}
            status = protocol.get("statusModule") or {}
            design = protocol.get("designModule") or {}
            references_module = protocol.get("referencesModule") or {}
            nct_id = clean(identification.get("nctId")).upper()
            aliases = {
                clean(value).upper()
                for value in identification.get("nctIdAliases") or []
                if clean(value)
            }
            all_ids = {nct_id, *aliases}
            start_date = date_value(status, "startDateStruct")
            first_submitted = clean(status.get("studyFirstSubmitDate"))
            prospective = prospective_registration(first_submitted, start_date)
            timing_status = (
                "prospective"
                if prospective is True
                else "retrospective"
                if prospective is False
                else "indeterminate"
            )
            linked_papers: set[str] = set()
            references = references_module.get("references") or []
            type_counts = Counter(
                clean(reference.get("type")).upper() for reference in references
            )
            for reference in references:
                reference_type = clean(reference.get("type")).upper()
                if reference_type not in ACCEPTED_TRIAL_REFERENCE_TYPES:
                    continue
                citation = clean(reference.get("citation"))
                pmid = clean(reference.get("pmid"))
                matched_dois = set()
                if pmid in pmid_to_doi:
                    matched_dois.add(pmid_to_doi[pmid])
                matched_dois.update(citation_dois(citation) & doi_set)
                for doi in matched_dois:
                    linked_papers.add(doi)
                    assertions.append(
                        finalize_assertion(
                            doi=doi,
                            feature=FEATURE_REGISTERED_TRIAL,
                            identifier=nct_id,
                            identifier_type="trial_registry_id",
                            url=trial_url(nct_id),
                            repository="clinicaltrials_gov",
                            provider="clinicaltrials_gov",
                            provider_record_id=nct_id,
                            source_type="registry_publication_reference",
                            source_path="",
                            source_section=f"ReferenceType={reference_type}",
                            evidence_text=citation or f"ReferencePMID={pmid}",
                            evidence_method=(
                                "clinicaltrials_gov_structured_publication_link"
                            ),
                            retrieval_run_id=client.retrieval_run_id,
                            retrieved_at_utc=client.retrieved_at_utc,
                        )
                    )
                    if prospective is True and reference_type == "RESULT":
                        assertions.append(
                            finalize_assertion(
                                doi=doi,
                                feature=FEATURE_PREREGISTERED,
                                identifier=nct_id,
                                identifier_type="trial_registry_id",
                                url=trial_url(nct_id),
                                repository="clinicaltrials_gov",
                                provider="clinicaltrials_gov",
                                provider_record_id=nct_id,
                                source_type="registry_registration_timing",
                                source_path="",
                                source_section=f"ReferenceType={reference_type}",
                                evidence_text=(
                                    f"StudyFirstSubmitDate={first_submitted}; "
                                    f"StartDate={start_date}; publication={citation}"
                                ),
                                evidence_method=(
                                    "prospective_registration_before_start_and_"
                                    "registry_result_link"
                                ),
                                retrieval_run_id=client.retrieval_run_id,
                                retrieved_at_utc=client.retrieved_at_utc,
                            )
                        )
            for trial_identifier in all_ids:
                for linked_id, doi in pubmed_links:
                    if linked_id == trial_identifier:
                        linked_papers.add(doi)
            records.append(
                {
                    "schema_version": TRIAL_RECORD_SCHEMA_VERSION,
                    "nct_id": nct_id,
                    "nct_id_aliases": pipe(aliases),
                    "clinicaltrials_url": trial_url(nct_id),
                    "brief_title": clean(identification.get("briefTitle")),
                    "study_type": clean(design.get("studyType")),
                    "study_start_date": start_date,
                    "study_first_submitted_date": first_submitted,
                    "prospective_registration": prospective,
                    "registration_timing_status": timing_status,
                    "publication_reference_count": len(references),
                    "result_reference_count": type_counts.get("RESULT", 0),
                    "derived_reference_count": type_counts.get("DERIVED", 0),
                    "linked_scope_paper_count": len(linked_papers),
                    "linked_scope_paper_dois": pipe(linked_papers),
                    "provider": "clinicaltrials_gov",
                    "retrieval_run_id": client.retrieval_run_id,
                    "retrieved_at_utc": client.retrieved_at_utc,
                }
            )
        print(
            f"ClinicalTrials.gov batch {index}/{len(batches)}: "
            f"{len(batch)} requested, {len(studies)} returned",
            flush=True,
        )
    return deduplicate_assertions(assertions), records, attempts


def datacite_resource_enrichment(
    candidates: list[dict[str, Any]],
    *,
    client: ProviderClient,
    batch_size: int,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], list[dict[str, Any]]]:
    doi_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        if row["resource_id_type"] != "doi":
            continue
        if not (row["shared_data_context"] or row["shared_code_context"]):
            continue
        doi_candidates[normalized_doi(row["resource_id"])].append(row)
    resource_dois = sorted(value for value in doi_candidates if value)
    assertions: list[dict[str, str]] = []
    records: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    batches = list(chunks(resource_dois, batch_size))
    for index, batch in enumerate(batches, start=1):
        query = " OR ".join(f'doi:"{value}"' for value in batch)
        payload, attempt = client.fetch(
            provider="datacite",
            request_kind="typed_resource_metadata",
            request_index=index,
            endpoint=DATACITE_API,
            params=[
                ("query", query),
                ("page[size]", str(max(1, len(batch)))),
            ],
            request_ids=batch,
            expect="json",
        )
        returned = payload.get("data") or []
        attempt["returned_count"] = len(returned)
        attempts.append(attempt)
        for item in returned:
            attributes = item.get("attributes") or {}
            resource_doi = normalized_doi(attributes.get("doi") or item.get("id"))
            if resource_doi not in doi_candidates:
                continue
            types = attributes.get("types") or {}
            type_general = clean(types.get("resourceTypeGeneral"))
            resource_type = clean(types.get("resourceType"))
            titles = attributes.get("titles") or []
            title = clean(titles[0].get("title")) if titles else ""
            linked_dois = {row["doi"] for row in doi_candidates[resource_doi]}
            repository = pipe(
                row["repository"] for row in doi_candidates[resource_doi]
            )
            records.append(
                {
                    "schema_version": DATACITE_RECORD_SCHEMA_VERSION,
                    "resource_doi": resource_doi,
                    "resource_url": clean(attributes.get("url"))
                    or f"https://doi.org/{resource_doi}",
                    "resource_title": title,
                    "resource_type_general": type_general,
                    "resource_type": resource_type,
                    "publisher": clean(attributes.get("publisher")),
                    "repository": repository,
                    "linked_scope_paper_count": len(linked_dois),
                    "linked_scope_paper_dois": pipe(linked_dois),
                    "provider": "datacite",
                    "retrieval_run_id": client.retrieval_run_id,
                    "retrieved_at_utc": client.retrieved_at_utc,
                }
            )
            general = type_general.casefold()
            for candidate in doi_candidates[resource_doi]:
                feature = ""
                evidence_method = ""
                if candidate["shared_data_context"] and general in {
                    "dataset",
                    "collection",
                }:
                    feature = FEATURE_OPEN_DATA
                    evidence_method = (
                        "datacite_typed_dataset_plus_explicit_sharing_statement"
                    )
                elif (
                    general == "software"
                    and (
                        candidate["shared_code_context"]
                        or candidate["shared_data_context"]
                    )
                ):
                    feature = FEATURE_SHARED_CODE
                    evidence_method = (
                        "datacite_typed_software_plus_explicit_sharing_statement"
                    )
                if not feature:
                    continue
                assertions.append(
                    finalize_assertion(
                        doi=candidate["doi"],
                        feature=feature,
                        identifier=resource_doi,
                        identifier_type="doi",
                        url=clean(attributes.get("url"))
                        or f"https://doi.org/{resource_doi}",
                        repository=candidate["repository"],
                        provider="datacite",
                        provider_record_id=resource_doi,
                        source_type=candidate["source_type"],
                        source_path=candidate["source_path"],
                        source_section=candidate["source_section"],
                        evidence_text=candidate["evidence_text"],
                    evidence_method=evidence_method,
                        retrieval_run_id=client.retrieval_run_id,
                        retrieved_at_utc=client.retrieved_at_utc,
                    )
                )
        print(
            f"DataCite batch {index}/{len(batches)}: "
            f"{len(batch)} requested, {len(returned)} returned",
            flush=True,
        )
    return deduplicate_assertions(assertions), records, attempts


def add_accession_urls(
    assertions: list[dict[str, str]],
) -> list[dict[str, str]]:
    for row in assertions:
        if row["url"]:
            continue
        inferred = repository_identifier_url(row["repository"], row["identifier"])
        if inferred:
            row["url"] = inferred
            row["assertion_key"] = ""
            row["assertion_key"] = hashlib.sha256(
                "\x1f".join(
                    clean(row.get(field, "")).casefold()
                    for field in (
                        "doi",
                        "feature",
                        "identifier",
                        "url",
                        "provider",
                        "provider_record_id",
                        "source_type",
                        "evidence_method",
                    )
                ).encode("utf-8")
            ).hexdigest()
    return deduplicate_assertions(assertions)


def materialize_summary(
    scope: pd.DataFrame,
    assertions: list[dict[str, str]],
    *,
    retrieval_run_id: str,
    retrieved_at_utc: str,
) -> pd.DataFrame:
    by_doi: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in assertions:
        by_doi[row["doi"]].append(row)

    def values(rows: list[dict[str, str]], field: str) -> str:
        return pipe(row[field] for row in rows)

    summary_rows: list[dict[str, Any]] = []
    for paper in scope.to_dict("records"):
        doi = paper["doi"]
        paper_assertions = by_doi.get(doi, [])
        grouped = {
            feature: [
                row for row in paper_assertions if row["feature"] == feature
            ]
            for feature in FEATURES
        }
        registered = grouped[FEATURE_REGISTERED_TRIAL]
        open_data = grouped[FEATURE_OPEN_DATA]
        code = grouped[FEATURE_SHARED_CODE]
        prereg = grouped[FEATURE_PREREGISTERED]
        present_features = [feature for feature in FEATURES if grouped[feature]]
        summary_rows.append(
            {
                "schema_version": SUMMARY_SCHEMA_VERSION,
                "doi": doi,
                "has_registered_trial": bool(registered),
                "registered_trial_ids": values(registered, "identifier"),
                "registered_trial_urls": values(registered, "url"),
                "registered_trial_count": len(
                    {row["identifier"] or row["assertion_key"] for row in registered}
                ),
                "has_open_data": bool(open_data),
                "open_data_resource_ids": values(open_data, "identifier"),
                "open_data_urls": values(open_data, "url"),
                "open_data_repositories": values(open_data, "repository"),
                "open_data_resource_count": len(
                    {row["identifier"] or row["url"] for row in open_data}
                ),
                "has_shared_code": bool(code),
                "shared_code_resource_ids": values(code, "identifier"),
                "shared_code_urls": values(code, "url"),
                "shared_code_repositories": values(code, "repository"),
                "shared_code_resource_count": len(
                    {row["identifier"] or row["url"] for row in code}
                ),
                "has_preregistered": bool(prereg),
                "preregistration_ids": values(prereg, "identifier"),
                "preregistration_urls": values(prereg, "url"),
                "preregistration_repositories": values(prereg, "repository"),
                "preregistration_count": len(
                    {row["identifier"] or row["assertion_key"] for row in prereg}
                ),
                "open_science_features": " | ".join(present_features),
                "feature_count": len(present_features),
                "assertion_count": len(paper_assertions),
                "evidence_providers": values(paper_assertions, "provider"),
                "evidence_source_types": values(paper_assertions, "source_type"),
                "has_fulltext_evidence_source": any(
                    row["source_type"] == "fulltext" for row in paper_assertions
                ),
                "open_science_enrichment_status": (
                    "features_asserted" if paper_assertions else "no_feature_asserted"
                ),
                "retrieval_run_id": retrieval_run_id,
                "retrieved_at_utc": retrieved_at_utc,
            }
        )
    return frame_with_columns(summary_rows, SUMMARY_COLUMNS).sort_values(
        "doi", kind="stable"
    )


def manual_validation_metrics(
    summary: pd.DataFrame,
    path: Path,
) -> dict[str, Any]:
    if not path.is_file():
        return {"status": "not_available", "path": str(path)}
    payload = json.loads(path.read_text(encoding="utf-8"))
    reviewed = payload.get("papers") or []
    predictions = summary.set_index("doi")
    mappings = {
        FEATURE_OPEN_DATA: ("shares_data", "has_open_data"),
        FEATURE_SHARED_CODE: ("shares_code", "has_shared_code"),
    }
    metrics: dict[str, Any] = {}
    for feature, (gold_role, prediction_column) in mappings.items():
        tp = fp = fn = tn = 0
        missing_scope = 0
        for paper in reviewed:
            doi = normalized_doi(paper.get("doi"))
            gold = gold_role in set(paper.get("roles") or [])
            if doi not in predictions.index:
                missing_scope += 1
                continue
            predicted = bool(predictions.at[doi, prediction_column])
            if predicted and gold:
                tp += 1
            elif predicted:
                fp += 1
            elif gold:
                fn += 1
            else:
                tn += 1
        metrics[feature] = {
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "true_negative": tn,
            "precision_percent": percent(tp, tp + fp),
            "recall_percent": percent(tp, tp + fn),
            "reviewed_in_scope": tp + fp + fn + tn,
            "reviewed_missing_from_scope": missing_scope,
        }
    metrics["preregistered"] = {
        "status": "not_scored",
        "reason": (
            "The pilot gold label combines preregistrations with protocols, "
            "while this feature deliberately represents preregistration only."
        ),
    }
    return {
        "status": "evaluated",
        "path": str(path),
        "review_method": payload.get("review_method", ""),
        "features": metrics,
    }


def build_report(
    *,
    scope: pd.DataFrame,
    assertions: pd.DataFrame,
    candidates: pd.DataFrame,
    summary: pd.DataFrame,
    trial_records: pd.DataFrame,
    datacite_records: pd.DataFrame,
    attempts: pd.DataFrame,
    local_stats: dict[str, Any],
    manual_validation: dict[str, Any],
    retrieval_run_id: str,
    run_started_at_utc: str,
) -> dict[str, Any]:
    feature_counts = {
        feature: int(summary[f"has_{feature}"].sum())
        for feature in FEATURES
    }
    assertion_feature_counts = dict(
        sorted(Counter(assertions["feature"]).items())
    )
    scope_dois = set(scope["doi"])
    assertion_dois = set(assertions["doi"]) if not assertions.empty else set()
    returned_nct = set(trial_records["nct_id"]) if not trial_records.empty else set()
    returned_nct_aliases: set[str] = set()
    if not trial_records.empty:
        for value in trial_records["nct_id_aliases"]:
            returned_nct_aliases.update(
                part for part in clean(value).split(" | ") if part
            )
    requested_nct: set[str] = set()
    if not attempts.empty:
        for value in attempts.loc[
            attempts["provider"].eq("clinicaltrials_gov"), "request_ids"
        ]:
            requested_nct.update(part for part in clean(value).split(" | ") if part)
    resolved_requested_nct = requested_nct & (
        returned_nct | returned_nct_aliases
    )
    requested_datacite: set[str] = set()
    if not attempts.empty:
        for value in attempts.loc[
            attempts["provider"].eq("datacite"), "request_ids"
        ]:
            requested_datacite.update(
                part for part in clean(value).split(" | ") if part
            )
    returned_datacite = (
        set(datacite_records["resource_doi"])
        if not datacite_records.empty
        else set()
    )
    pubmed_attempts = (
        attempts.loc[attempts["provider"].eq("pubmed")]
        if not attempts.empty
        else pd.DataFrame()
    )
    return {
        "audit": "paper_open_science_enrichment",
        "schema_version": "paper_open_science_enrichment_report_v1",
        "retrieval_run_id": retrieval_run_id,
        "run_started_at_utc": run_started_at_utc,
        "run_completed_at_utc": now_utc(),
        "scope": {
            "definition": "candidate_papers.retained_for_extraction_candidate = true",
            "papers": len(scope),
            **local_stats,
        },
        "coverage": {
            feature: {
                "papers": count,
                "percent": percent(count, len(scope)),
            }
            for feature, count in feature_counts.items()
        },
        "evidence": {
            "assertion_rows": len(assertions),
            "assertions_by_feature": assertion_feature_counts,
            "assertions_by_provider": dict(
                sorted(Counter(assertions["provider"]).items())
            ),
            "papers_with_any_feature": int(summary["feature_count"].gt(0).sum()),
            "papers_with_any_feature_percent": percent(
                int(summary["feature_count"].gt(0).sum()), len(scope)
            ),
            "resource_candidate_rows": len(candidates),
        },
        "providers": {
            "network_request_count": int(attempts["http_attempt_count"].sum())
            if not attempts.empty
            else 0,
            "logical_request_count": len(attempts),
            "failed_logical_requests": int(attempts["result"].ne("ok").sum())
            if not attempts.empty
            else 0,
            "incomplete_logical_responses": int(
                attempts["returned_count"].lt(attempts["requested_count"]).sum()
            )
            if not attempts.empty
            else 0,
            "logical_requests_by_provider": dict(
                sorted(Counter(attempts["provider"]).items())
            )
            if not attempts.empty
            else {},
            "trial_registry_records": len(trial_records),
            "datacite_resource_records": len(datacite_records),
            "clinicaltrials_requested_ids": len(requested_nct),
            "clinicaltrials_registry_records": len(returned_nct),
            "clinicaltrials_requested_ids_resolved": len(resolved_requested_nct),
            "clinicaltrials_requested_aliases_resolved": sorted(
                (requested_nct & returned_nct_aliases) - returned_nct
            ),
            "clinicaltrials_missing_ids": sorted(
                requested_nct - resolved_requested_nct
            ),
            "pubmed_unique_pmids_requested": int(
                pubmed_attempts["requested_count"].sum()
            )
            if not pubmed_attempts.empty
            else 0,
            "pubmed_records_returned": int(
                pubmed_attempts["returned_count"].sum()
            )
            if not pubmed_attempts.empty
            else 0,
            "pubmed_record_shortfall": int(
                (
                    pubmed_attempts["requested_count"]
                    - pubmed_attempts["returned_count"]
                ).sum()
            )
            if not pubmed_attempts.empty
            else 0,
            "datacite_dois_requested": len(requested_datacite),
            "datacite_dois_returned": len(returned_datacite),
            "datacite_dois_not_returned": sorted(
                requested_datacite - returned_datacite
            ),
        },
        "manual_validation": manual_validation,
        "count_reconciliation": {
            "summary_rows": len(summary),
            "scope_rows": len(scope),
            "summary_unique_dois": int(summary["doi"].nunique()),
            "assertion_dois_outside_scope": sorted(assertion_dois - scope_dois),
            "feature_boolean_counts": feature_counts,
            "feature_grouped_assertion_paper_counts": {
                feature: int(
                    assertions.loc[
                        assertions["feature"].eq(feature), "doi"
                    ].nunique()
                )
                for feature in FEATURES
            },
        },
        "interpretation_guards": [
            "Registered trial means the paper is linked to a trial registration "
            "through structured PubMed metadata, a focal article statement, or a "
            "ClinicalTrials.gov RESULT/DERIVED publication reference; review-only "
            "and meta-analysis papers are excluded from this feature.",
            "Preregistered is not inferred from a registry identifier alone. It "
            "requires an explicit preregistration statement or an unambiguously "
            "prospective ClinicalTrials.gov registration with a RESULT link.",
            "Open data excludes data available only on request, planned future "
            "releases, and reuse of an external public dataset.",
            "Shared code requires evidence for study-specific code and excludes "
            "ordinary citations of third-party software or packages.",
            "These tables are standalone enrichment outputs and are not integrated "
            "into the graph by this run.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--manual-validation", type=Path, default=DEFAULT_MANUAL_VALIDATION)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--network",
        action="store_true",
        help="Query PubMed, ClinicalTrials.gov, and DataCite.",
    )
    parser.add_argument(
        "--rematerialize-existing",
        action="store_true",
        help=(
            "Reuse the existing assertion/provider tables and only reapply "
            "semantic guards, validation, and summary materialization."
        ),
    )
    parser.add_argument(
        "--refresh-local-reuse-providers",
        action="store_true",
        help=(
            "Rescan local article evidence but reuse existing PubMed, "
            "ClinicalTrials.gov, and DataCite assertions and provider tables."
        ),
    )
    parser.add_argument("--max-requests", type=int, default=80)
    parser.add_argument("--pubmed-batch-size", type=int, default=500)
    parser.add_argument("--clinicaltrials-batch-size", type=int, default=100)
    parser.add_argument("--datacite-batch-size", type=int, default=40)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_started_at_utc = now_utc()
    retrieved_at_utc = run_started_at_utc
    scope = build_scope(args.candidates, args.limit)
    print(f"Open-science scope: {len(scope):,} post-screening papers", flush=True)

    retrieval_run_id = args.run_id or default_run_id()
    assertions: list[dict[str, str]]
    resource_candidates: list[dict[str, Any]]
    provider_attempts: list[dict[str, Any]] = []
    trial_records: list[dict[str, Any]] = []
    datacite_records: list[dict[str, Any]] = []
    pubmed_links: dict[tuple[str, str], dict[str, str]] = {}

    if args.rematerialize_existing and args.refresh_local_reuse_providers:
        raise ValueError(
            "--rematerialize-existing and --refresh-local-reuse-providers "
            "are mutually exclusive"
        )
    paths = {
        "assertions": args.output_dir / "paper_open_science_assertions.parquet",
        "resource_candidates": (
            args.output_dir / "paper_open_science_resource_candidates.parquet"
        ),
        "trial_records": (
            args.output_dir / "open_science_trial_registry_records.parquet"
        ),
        "datacite_records": (
            args.output_dir / "open_science_datacite_resource_records.parquet"
        ),
        "provider_attempts": (
            args.output_dir / "paper_open_science_provider_attempts.parquet"
        ),
        "report": args.output_dir / "paper_open_science_enrichment_report.json",
    }

    if args.rematerialize_existing or args.refresh_local_reuse_providers:
        missing = [str(path) for path in paths.values() if not path.is_file()]
        if missing:
            raise FileNotFoundError(
                "Cannot reuse existing outputs because files are missing: "
                + ", ".join(missing)
            )
        existing_assertions = pd.read_parquet(paths["assertions"])
        trial_records = pd.read_parquet(paths["trial_records"]).to_dict("records")
        datacite_records = pd.read_parquet(paths["datacite_records"]).to_dict(
            "records"
        )
        provider_attempts = pd.read_parquet(paths["provider_attempts"]).to_dict(
            "records"
        )
        existing_report = json.loads(paths["report"].read_text(encoding="utf-8"))
        existing_assertion_rows = existing_assertions.to_dict("records")
        if args.rematerialize_existing:
            assertions = existing_assertion_rows
            resource_candidates = pd.read_parquet(
                paths["resource_candidates"]
            ).to_dict("records")
        else:
            assertions, resource_candidates, local_stats = scan_local_evidence(
                scope,
                retrieval_run_id=retrieval_run_id,
                retrieved_at_utc=retrieved_at_utc,
            )
            assertions.extend(
                row
                for row in existing_assertion_rows
                if row["provider"]
                in {"pubmed", "clinicaltrials_gov", "datacite"}
            )
        if args.rematerialize_existing and not args.run_id and assertions:
            retrieval_run_id = clean(assertions[0].get("retrieval_run_id"))
        if args.rematerialize_existing and assertions:
            retrieved_at_utc = clean(assertions[0].get("retrieved_at_utc"))
        existing_scope = existing_report.get("scope") or {}
        if args.rematerialize_existing:
            local_stats = {
                key: existing_scope.get(key)
                for key in (
                    "papers_with_fulltext_loaded",
                    "papers_without_fulltext_loaded",
                    "artifact_error_count",
                    "artifact_errors",
                )
                if key in existing_scope
            }
            local_stats["rematerialized_from_existing_evidence"] = True
        else:
            local_stats["local_evidence_refreshed_with_reused_provider_data"] = True
        print(
            f"Using {len(assertions):,} assertions and "
            f"{len(provider_attempts):,} provider request records",
            flush=True,
        )
    else:
        assertions, resource_candidates, local_stats = scan_local_evidence(
            scope,
            retrieval_run_id=retrieval_run_id,
            retrieved_at_utc=retrieved_at_utc,
        )

    if (
        args.network
        and not args.rematerialize_existing
        and not args.refresh_local_reuse_providers
    ):
        client = ProviderClient(
            max_requests=args.max_requests,
            retrieval_run_id=retrieval_run_id,
            retrieved_at_utc=retrieved_at_utc,
        )
        pubmed_assertions, pubmed_links, attempts = pubmed_trial_assertions(
            scope,
            client=client,
            batch_size=args.pubmed_batch_size,
        )
        assertions.extend(pubmed_assertions)
        provider_attempts.extend(attempts)

        nct_ids = {
            identifier
            for value in scope["trial_registry_ids"]
            for identifier, _, _ in extract_trial_identifiers(clean(value))
            if identifier.startswith("NCT")
        }
        nct_ids.update(
            identifier
            for identifier, _doi in pubmed_links
            if identifier.startswith("NCT")
        )
        nct_ids.update(
            row["identifier"]
            for row in assertions
            if row["identifier"].startswith("NCT")
        )
        clinical_assertions, trial_records, attempts = trial_registry_enrichment(
            scope,
            nct_ids=nct_ids,
            pubmed_links=pubmed_links,
            client=client,
            batch_size=args.clinicaltrials_batch_size,
        )
        assertions.extend(clinical_assertions)
        provider_attempts.extend(attempts)

        datacite_assertions, datacite_records, attempts = datacite_resource_enrichment(
            resource_candidates,
            client=client,
            batch_size=args.datacite_batch_size,
        )
        assertions.extend(datacite_assertions)
        provider_attempts.extend(attempts)

    assertions = add_accession_urls(deduplicate_assertions(assertions))
    assertions, semantic_guard_stats = apply_publication_semantic_guards(
        scope, assertions
    )
    local_stats.update(semantic_guard_stats)
    assertion_frame = frame_with_columns(assertions, ASSERTION_COLUMNS).sort_values(
        ["doi", "feature", "identifier", "provider"], kind="stable"
    )
    candidate_frame = frame_with_columns(
        resource_candidates, RESOURCE_CANDIDATE_COLUMNS
    ).sort_values(["doi", "repository", "resource_id"], kind="stable")
    trial_frame = frame_with_columns(trial_records, TRIAL_RECORD_COLUMNS).sort_values(
        "nct_id", kind="stable"
    )
    datacite_frame = frame_with_columns(
        datacite_records, DATACITE_RECORD_COLUMNS
    ).sort_values("resource_doi", kind="stable")
    attempt_frame = frame_with_columns(
        provider_attempts, ATTEMPT_COLUMNS
    ).sort_values(["provider", "request_index"], kind="stable")
    summary = materialize_summary(
        scope,
        assertions,
        retrieval_run_id=retrieval_run_id,
        retrieved_at_utc=retrieved_at_utc,
    )
    validation = manual_validation_metrics(summary, args.manual_validation)
    report = build_report(
        scope=scope,
        assertions=assertion_frame,
        candidates=candidate_frame,
        summary=summary,
        trial_records=trial_frame,
        datacite_records=datacite_frame,
        attempts=attempt_frame,
        local_stats=local_stats,
        manual_validation=validation,
        retrieval_run_id=retrieval_run_id,
        run_started_at_utc=run_started_at_utc,
    )

    output_paths = {
        "assertions": args.output_dir / "paper_open_science_assertions.parquet",
        "features": args.output_dir / "paper_open_science_features.parquet",
        "resource_candidates": (
            args.output_dir / "paper_open_science_resource_candidates.parquet"
        ),
        "trial_records": (
            args.output_dir / "open_science_trial_registry_records.parquet"
        ),
        "datacite_records": (
            args.output_dir / "open_science_datacite_resource_records.parquet"
        ),
        "provider_attempts": (
            args.output_dir / "paper_open_science_provider_attempts.parquet"
        ),
        "report": args.output_dir / "paper_open_science_enrichment_report.json",
    }
    run_report = (
        args.output_dir
        / "open_science_enrichment_runs"
        / retrieval_run_id
        / "report.json"
    )
    report["outputs"] = {key: str(path) for key, path in output_paths.items()}
    report["outputs"]["run_report"] = str(run_report)
    atomic_write_parquet(output_paths["assertions"], assertion_frame)
    atomic_write_parquet(output_paths["features"], summary)
    atomic_write_parquet(output_paths["resource_candidates"], candidate_frame)
    atomic_write_parquet(output_paths["trial_records"], trial_frame)
    atomic_write_parquet(output_paths["datacite_records"], datacite_frame)
    atomic_write_parquet(output_paths["provider_attempts"], attempt_frame)
    atomic_write_json(output_paths["report"], report)
    atomic_write_json(run_report, report)
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
