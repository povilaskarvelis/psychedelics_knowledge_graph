#!/usr/bin/env python3
"""Recover missing abstracts with resumable provider batch endpoints.

This command is intended for large, DOI-scoped discovery updates. It queries
PMC first for records with PMC identifiers, then queries Semantic Scholar for
the remaining DOI records. Each successful provider batch is checkpointed
before the next request, making the run safe to resume with the same run ID.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import json
from http.client import IncompleteRead, RemoteDisconnected
from pathlib import Path
import random
import shutil
import sys
import threading
import time
from typing import Any, Iterable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.enrich_paper_metadata import (  # noqa: E402
    OUTPUT_COLUMNS,
    candidate_metadata_row,
    clean,
    merge_rows,
    merged_output_rows,
    read_table,
    write_table,
)
from pipeline.ingest.metadata_utils import (  # noqa: E402
    PAPER_METADATA_SCHEMA_VERSION,
    load_config,
    metadata_from_pubmed_article,
    normalize_doi,
    pubmed_article_id,
    read_float,
    read_int,
    strip_markup,
)


DEFAULT_CANDIDATES = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_METADATA = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"
DEFAULT_RUNS_DIR = ROOT / "data" / "processed" / "corpus" / "metadata_enrichment_runs"
DEFAULT_CONFIG = ROOT / "pipeline" / "config.example.yaml"
RESULT_COLUMNS = (
    "run_id",
    "provider",
    "batch_id",
    "doi",
    "provider_record_id",
    "provider_doi",
    "status",
    "abstract",
    "retrieved_at_utc",
    "error",
)
CHECKPOINT_SCHEMA = "batch_abstract_checkpoint_v1"
MANIFEST_SCHEMA = "batch_abstract_enrichment_run_v1"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def default_run_id() -> str:
    return "batch_abstract_enrichment_" + dt.datetime.now(dt.timezone.utc).strftime("%Y_%m_%d_%H%M%S")


def normalized_text(value: Any) -> str:
    return " ".join(clean(value).split())


def normalized_doi(value: Any) -> str:
    return normalize_doi(clean(value)).lower()


def normalized_pmcid(value: Any) -> str:
    text = clean(value).upper()
    if not text:
        return ""
    return text if text.startswith("PMC") else f"PMC{text}"


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def element_text(element: ET.Element) -> str:
    return normalized_text(" ".join(part for part in element.itertext() if clean(part)))


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def atomic_write_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.stem + ".tmp.parquet")
    frame.to_parquet(temporary, engine="pyarrow", index=False)
    temporary.replace(path)


def chunks(values: Sequence[dict], size: int) -> Iterable[list[dict]]:
    size = max(1, int(size))
    for start in range(0, len(values), size):
        yield list(values[start : start + size])


def append_pipe_token(raw: Any, token: str) -> str:
    values = [part.strip() for part in clean(raw).split("|") if part.strip()]
    if token and token not in values:
        values.append(token)
    return "|".join(values)


class BatchHttpClient:
    """Minimal HTTP client with provider-specific pacing and retry handling."""

    def __init__(
        self,
        *,
        rps: float,
        max_retries: int,
        timeout_sec: int,
        max_retry_after_sec: int,
        user_agent: str,
    ) -> None:
        self.min_interval = 1.0 / max(0.01, float(rps))
        self.max_retries = max(0, int(max_retries))
        self.timeout_sec = max(1, int(timeout_sec))
        self.max_retry_after_sec = max(0, int(max_retry_after_sec))
        self.user_agent = user_agent
        self._last_request_at = 0.0
        self._rate_lock = threading.Lock()

    def _wait(self) -> None:
        # Reserve request-start slots under one lock so a documented small
        # worker pool cannot exceed the provider-level request budget.
        with self._rate_lock:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last_request_at = time.monotonic()

    def post_bytes(self, url: str, *, body: bytes, headers: dict[str, str]) -> bytes:
        backoff = 2.5
        for attempt in range(self.max_retries + 1):
            self._wait()
            request_headers = {"User-Agent": self.user_agent, **headers}
            request = Request(url, data=body, headers=request_headers, method="POST")
            try:
                with urlopen(request, timeout=self.timeout_sec) as response:
                    result = response.read()
                return result
            except HTTPError as err:
                if attempt >= self.max_retries or err.code not in {429, 500, 502, 503, 504}:
                    raise
                retry_after = err.headers.get("Retry-After", "") if err.headers else ""
                delay = max(backoff, float(retry_after)) if retry_after.isdigit() else backoff
                if self.max_retry_after_sec and delay > self.max_retry_after_sec:
                    raise RuntimeError(f"retry_after_exceeded:{delay:.1f}s") from err
            except (URLError, TimeoutError, IncompleteRead, RemoteDisconnected, ConnectionError, OSError):
                if attempt >= self.max_retries:
                    raise
                delay = backoff
            time.sleep(delay + random.uniform(0.0, 0.35))
            backoff *= 1.7
        raise RuntimeError("Unreachable retry state")

    def post_form(self, url: str, fields: dict[str, Any]) -> bytes:
        body = urlencode({key: value for key, value in fields.items() if value not in (None, "")}).encode("utf-8")
        return self.post_bytes(
            url,
            body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def post_json(self, url: str, payload: dict, *, headers: dict[str, str] | None = None) -> Any:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        raw = self.post_bytes(
            url,
            body=body,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        return json.loads(raw.decode("utf-8"))

    def get_bytes(self, url: str, *, headers: dict[str, str] | None = None) -> bytes:
        backoff = 2.5
        for attempt in range(self.max_retries + 1):
            self._wait()
            request_headers = {"User-Agent": self.user_agent, **(headers or {})}
            request = Request(url, headers=request_headers, method="GET")
            try:
                with urlopen(request, timeout=self.timeout_sec) as response:
                    return response.read()
            except HTTPError as err:
                if attempt >= self.max_retries or err.code not in {429, 500, 502, 503, 504}:
                    raise
                retry_after = err.headers.get("Retry-After", "") if err.headers else ""
                delay = max(backoff, float(retry_after)) if retry_after.isdigit() else backoff
                if self.max_retry_after_sec and delay > self.max_retry_after_sec:
                    raise RuntimeError(f"retry_after_exceeded:{delay:.1f}s") from err
            except (URLError, TimeoutError, IncompleteRead, RemoteDisconnected, ConnectionError, OSError):
                if attempt >= self.max_retries:
                    raise
                delay = backoff
            time.sleep(delay + random.uniform(0.0, 0.35))
            backoff *= 1.7
        raise RuntimeError("Unreachable retry state")

    def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        query = urlencode({key: value for key, value in (params or {}).items() if value not in (None, "")})
        endpoint = f"{url}?{query}" if query else url
        return json.loads(self.get_bytes(endpoint, headers={"Accept": "application/json"}).decode("utf-8"))


def element_identifiers(article: ET.Element) -> dict[str, str]:
    identifiers: dict[str, str] = {}
    for element in article.iter():
        if local_name(element.tag) != "article-id":
            continue
        id_type = clean(element.attrib.get("pub-id-type", "")).lower()
        value = element_text(element)
        if id_type and value and id_type not in identifiers:
            identifiers[id_type] = value
    return identifiers


def longest_article_abstract(article: ET.Element) -> str:
    candidates: list[str] = []
    for element in article.iter():
        if local_name(element.tag) != "abstract":
            continue
        text = element_text(element)
        if text:
            candidates.append(text)
    return max(candidates, key=len) if candidates else ""


def parse_pmc_batch(body: bytes, requested: Sequence[dict], *, run_id: str, batch_id: str) -> list[dict]:
    root = ET.fromstring(body)
    articles_by_pmcid: dict[str, tuple[dict[str, str], str]] = {}
    articles_by_doi: dict[str, tuple[dict[str, str], str]] = {}
    for article in root.iter():
        if local_name(article.tag) != "article":
            continue
        identifiers = element_identifiers(article)
        abstract = longest_article_abstract(article)
        pmcid = normalized_pmcid(identifiers.get("pmcid") or identifiers.get("pmc"))
        doi = normalized_doi(identifiers.get("doi"))
        if pmcid:
            articles_by_pmcid[pmcid] = (identifiers, abstract)
        if doi:
            articles_by_doi[doi] = (identifiers, abstract)

    timestamp = now_utc()
    rows: list[dict] = []
    for item in requested:
        doi = normalized_doi(item.get("doi"))
        pmcid = normalized_pmcid(item.get("pmcid"))
        match = articles_by_pmcid.get(pmcid) or articles_by_doi.get(doi)
        if not match:
            rows.append(result_row(run_id, "pmc", batch_id, doi, pmcid, "", "not_found", "", timestamp))
            continue
        identifiers, abstract = match
        provider_doi = normalized_doi(identifiers.get("doi"))
        status = "recovered" if abstract else "no_abstract"
        rows.append(result_row(run_id, "pmc", batch_id, doi, pmcid, provider_doi, status, abstract, timestamp))
    return rows


def parse_pubmed_batch(body: bytes, requested: Sequence[dict], *, run_id: str, batch_id: str) -> list[dict]:
    root = ET.fromstring(body)
    articles_by_pmid: dict[str, tuple[str, str]] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid = clean(article.findtext(".//MedlineCitation/PMID"))
        if not pmid:
            continue
        metadata = metadata_from_pubmed_article(article, {})
        articles_by_pmid[pmid] = (
            normalized_doi(pubmed_article_id(article, "doi")),
            normalized_text(metadata.get("abstract", "")),
        )

    timestamp = now_utc()
    rows: list[dict] = []
    for item in requested:
        doi = normalized_doi(item.get("doi"))
        pmid = clean(item.get("pmid", ""))
        match = articles_by_pmid.get(pmid)
        if not match:
            rows.append(result_row(run_id, "pubmed", batch_id, doi, pmid, "", "not_found", "", timestamp))
            continue
        provider_doi, abstract = match
        if provider_doi and provider_doi != doi:
            rows.append(
                result_row(
                    run_id,
                    "pubmed",
                    batch_id,
                    doi,
                    pmid,
                    provider_doi,
                    "identifier_mismatch",
                    "",
                    timestamp,
                    error=f"requested={doi};returned={provider_doi}",
                )
            )
            continue
        rows.append(
            result_row(
                run_id,
                "pubmed",
                batch_id,
                doi,
                pmid,
                provider_doi,
                "recovered" if abstract else "no_abstract",
                abstract,
                timestamp,
            )
        )
    return rows


def parse_semantic_scholar_batch(
    payload: Any,
    requested: Sequence[dict],
    *,
    run_id: str,
    batch_id: str,
) -> list[dict]:
    if not isinstance(payload, list):
        raise ValueError("Semantic Scholar batch response must be a list")
    responses: list[Any]
    if len(payload) == len(requested):
        responses = payload
    else:
        # The API occasionally omits an unsupported identifier instead of
        # returning a null placeholder.  Positional zipping would then attach
        # every later abstract to the wrong DOI, so realign by returned DOI.
        by_doi: dict[str, dict] = {}
        for response in payload:
            if not isinstance(response, dict):
                continue
            external = response.get("externalIds", {}) if isinstance(response.get("externalIds"), dict) else {}
            doi = normalized_doi(external.get("DOI", ""))
            if doi:
                by_doi[doi] = response
        responses = [by_doi.get(normalized_doi(item.get("doi"))) for item in requested]
    timestamp = now_utc()
    rows: list[dict] = []
    for item, response in zip(requested, responses):
        doi = normalized_doi(item.get("doi"))
        if not isinstance(response, dict):
            rows.append(result_row(run_id, "semantic_scholar", batch_id, doi, "", "", "not_found", "", timestamp))
            continue
        external = response.get("externalIds", {}) if isinstance(response.get("externalIds"), dict) else {}
        provider_doi = normalized_doi(external.get("DOI", ""))
        provider_record_id = clean(response.get("paperId", ""))
        if provider_doi and provider_doi != doi:
            rows.append(
                result_row(
                    run_id,
                    "semantic_scholar",
                    batch_id,
                    doi,
                    provider_record_id,
                    provider_doi,
                    "identifier_mismatch",
                    "",
                    timestamp,
                    error=f"requested={doi};returned={provider_doi}",
                )
            )
            continue
        abstract = normalized_text(response.get("abstract", ""))
        rows.append(
            result_row(
                run_id,
                "semantic_scholar",
                batch_id,
                doi,
                provider_record_id,
                provider_doi,
                "recovered" if abstract else "no_abstract",
                abstract,
                timestamp,
            )
        )
    return rows


def parse_crossref_work(
    payload: Any,
    requested: dict,
    *,
    run_id: str,
    batch_id: str,
) -> dict:
    doi = normalized_doi(requested.get("doi"))
    message = payload.get("message", {}) if isinstance(payload, dict) else {}
    if not isinstance(message, dict):
        return result_row(run_id, "crossref", batch_id, doi, "", "", "not_found", "", now_utc())
    provider_doi = normalized_doi(message.get("DOI", ""))
    if provider_doi and provider_doi != doi:
        return result_row(
            run_id,
            "crossref",
            batch_id,
            doi,
            "",
            provider_doi,
            "identifier_mismatch",
            "",
            now_utc(),
            error=f"requested={doi};returned={provider_doi}",
        )
    abstract = normalized_text(strip_markup(message.get("abstract", "")))
    return result_row(
        run_id,
        "crossref",
        batch_id,
        doi,
        provider_doi,
        provider_doi,
        "recovered" if abstract else "no_abstract",
        abstract,
        now_utc(),
    )


def result_row(
    run_id: str,
    provider: str,
    batch_id: str,
    doi: str,
    provider_record_id: str,
    provider_doi: str,
    status: str,
    abstract: str,
    retrieved_at_utc: str,
    *,
    error: str = "",
) -> dict:
    return {
        "run_id": run_id,
        "provider": provider,
        "batch_id": batch_id,
        "doi": normalized_doi(doi),
        "provider_record_id": clean(provider_record_id),
        "provider_doi": normalized_doi(provider_doi),
        "status": clean(status),
        "abstract": normalized_text(abstract),
        "retrieved_at_utc": clean(retrieved_at_utc),
        "error": clean(error),
    }


def load_doi_scope(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    if not path.exists():
        raise FileNotFoundError(path)
    values: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or text.lower() in {"doi", "study_doi"}:
            continue
        doi = normalized_doi(text.split(",", 1)[0])
        if doi:
            values.add(doi)
    return values


def build_missing_abstract_scope(
    candidates_path: Path,
    metadata_path: Path,
    *,
    allowed_dois: set[str] | None,
    limit: int = 0,
) -> pd.DataFrame:
    candidates = pd.read_parquet(candidates_path)
    if "doi" not in candidates.columns:
        raise ValueError(f"Candidate table has no DOI column: {candidates_path}")
    candidates = candidates.copy()
    candidates["doi_norm"] = candidates["doi"].map(normalized_doi)
    candidates = candidates[candidates["doi_norm"].ne("")].drop_duplicates("doi_norm", keep="first")
    if allowed_dois is not None:
        candidates = candidates[candidates["doi_norm"].isin(allowed_dois)]

    metadata_by_doi: dict[str, dict] = {}
    if metadata_path.exists():
        metadata_rows = read_table(metadata_path)
        metadata_by_doi = {normalized_doi(row.get("doi")): row for row in metadata_rows if normalized_doi(row.get("doi"))}

    rows: list[dict] = []
    for row in candidates.to_dict("records"):
        doi = row["doi_norm"]
        existing = metadata_by_doi.get(doi, {})
        abstract = clean(existing.get("abstract", "")) or clean(row.get("abstract", ""))
        if abstract:
            continue
        rows.append(
            {
                "doi": doi,
                "pmcid": normalized_pmcid(existing.get("pmcid", "") or row.get("pmcid", "")),
                "pmid": clean(existing.get("pmid", "") or row.get("pmid", "")),
                "study_title": clean(existing.get("study_title", "") or row.get("study_title", "")),
                "study_year": clean(existing.get("study_year", "") or row.get("study_year", "")),
            }
        )
    scope = pd.DataFrame(rows, columns=["doi", "pmcid", "pmid", "study_title", "study_year"])
    scope = scope.sort_values("doi", kind="stable").reset_index(drop=True)
    if limit > 0:
        scope = scope.head(limit).copy()
    return scope


def batch_input_hash(rows: Sequence[dict], provider: str) -> str:
    if provider == "pmc":
        values = [f"{normalized_doi(row.get('doi'))}\t{normalized_pmcid(row.get('pmcid'))}" for row in rows]
    elif provider == "pubmed":
        values = [f"{normalized_doi(row.get('doi'))}\t{clean(row.get('pmid', ''))}" for row in rows]
    else:
        values = [normalized_doi(row.get("doi")) for row in rows]
    return sha256_bytes("\n".join(values).encode("utf-8"))


def checkpoint_path(run_dir: Path, provider: str, batch_index: int) -> Path:
    return run_dir / "checkpoints" / provider / f"batch_{batch_index:06d}.json"


def load_checkpoint(path: Path, *, expected_hash: str) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != CHECKPOINT_SCHEMA:
        raise ValueError(f"Unsupported checkpoint schema: {path}")
    if payload.get("input_hash") != expected_hash:
        raise ValueError(f"Checkpoint input mismatch: {path}")
    records = payload.get("records", [])
    if not isinstance(records, list):
        raise ValueError(f"Checkpoint records are invalid: {path}")
    return records


def save_checkpoint(
    path: Path,
    *,
    provider: str,
    batch_id: str,
    input_hash: str,
    records: list[dict],
) -> None:
    atomic_write_json(
        path,
        {
            "schema_version": CHECKPOINT_SCHEMA,
            "provider": provider,
            "batch_id": batch_id,
            "input_hash": input_hash,
            "completed_at_utc": now_utc(),
            "counts": dict(Counter(clean(row.get("status", "")) for row in records)),
            "records": records,
        },
    )


def fetch_pmc_batch_with_isolation(
    rows: Sequence[dict],
    *,
    client: BatchHttpClient,
    run_id: str,
    batch_id: str,
    email: str,
    api_key: str,
) -> list[dict]:
    """Fetch a PMC batch, splitting HTTP-400 batches to isolate bad IDs."""
    try:
        body = client.post_form(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            {
                "db": "pmc",
                "id": ",".join(normalized_pmcid(row["pmcid"]).removeprefix("PMC") for row in rows),
                "retmode": "xml",
                "tool": "psychedelics_kg",
                "email": email,
                "api_key": api_key,
            },
        )
        return parse_pmc_batch(body, rows, run_id=run_id, batch_id=batch_id)
    except HTTPError as error:
        if error.code != 400:
            raise
        if len(rows) > 1:
            midpoint = max(1, len(rows) // 2)
            return [
                *fetch_pmc_batch_with_isolation(
                    rows[:midpoint],
                    client=client,
                    run_id=run_id,
                    batch_id=batch_id,
                    email=email,
                    api_key=api_key,
                ),
                *fetch_pmc_batch_with_isolation(
                    rows[midpoint:],
                    client=client,
                    run_id=run_id,
                    batch_id=batch_id,
                    email=email,
                    api_key=api_key,
                ),
            ]
        row = rows[0]
        return [
            result_row(
                run_id,
                "pmc",
                batch_id,
                normalized_doi(row.get("doi")),
                normalized_pmcid(row.get("pmcid")),
                "",
                "request_error",
                "",
                now_utc(),
                error="HTTP 400 for single PMC identifier",
            )
        ]


def fetch_pubmed_batch_with_isolation(
    rows: Sequence[dict],
    *,
    client: BatchHttpClient,
    run_id: str,
    batch_id: str,
    email: str,
    api_key: str,
) -> list[dict]:
    """Fetch PubMed records by PMID, splitting HTTP-400 batches if needed."""
    try:
        body = client.post_form(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            {
                "db": "pubmed",
                "id": ",".join(clean(row.get("pmid", "")) for row in rows),
                "retmode": "xml",
                "tool": "psychedelics_kg",
                "email": email,
                "api_key": api_key,
            },
        )
        return parse_pubmed_batch(body, rows, run_id=run_id, batch_id=batch_id)
    except HTTPError as error:
        if error.code != 400:
            raise
        if len(rows) > 1:
            midpoint = max(1, len(rows) // 2)
            return [
                *fetch_pubmed_batch_with_isolation(
                    rows[:midpoint],
                    client=client,
                    run_id=run_id,
                    batch_id=batch_id,
                    email=email,
                    api_key=api_key,
                ),
                *fetch_pubmed_batch_with_isolation(
                    rows[midpoint:],
                    client=client,
                    run_id=run_id,
                    batch_id=batch_id,
                    email=email,
                    api_key=api_key,
                ),
            ]
        row = rows[0]
        return [
            result_row(
                run_id,
                "pubmed",
                batch_id,
                normalized_doi(row.get("doi")),
                clean(row.get("pmid", "")),
                "",
                "request_error",
                "",
                now_utc(),
                error="HTTP 400 for single PubMed identifier",
            )
        ]


def run_pubmed_batches(
    rows: Sequence[dict],
    *,
    run_id: str,
    run_dir: Path,
    client: BatchHttpClient,
    batch_size: int,
    email: str,
    api_key: str,
    manifest: dict,
    manifest_path: Path,
) -> list[dict]:
    eligible = [row for row in rows if clean(row.get("pmid", ""))]
    all_results: list[dict] = []
    batches = list(chunks(eligible, batch_size))
    for batch_index, batch in enumerate(batches, start=1):
        batch_id = f"pubmed_{batch_index:06d}"
        input_hash = batch_input_hash(batch, "pubmed")
        path = checkpoint_path(run_dir, "pubmed", batch_index)
        if path.exists():
            records = load_checkpoint(path, expected_hash=input_hash)
        else:
            records = fetch_pubmed_batch_with_isolation(
                batch,
                client=client,
                run_id=run_id,
                batch_id=batch_id,
                email=email,
                api_key=api_key,
            )
            save_checkpoint(
                path,
                provider="pubmed",
                batch_id=batch_id,
                input_hash=input_hash,
                records=records,
            )
        all_results.extend(records)
        update_live_manifest(manifest, manifest_path, "pubmed", batch_index, len(batches), all_results)
        print(
            f"PubMed batches {batch_index:,}/{len(batches):,}: "
            f"recovered={sum(row['status'] == 'recovered' for row in all_results):,}",
            flush=True,
        )
    return all_results


def run_pmc_batches(
    rows: Sequence[dict],
    *,
    run_id: str,
    run_dir: Path,
    client: BatchHttpClient,
    batch_size: int,
    email: str,
    api_key: str,
    manifest: dict,
    manifest_path: Path,
) -> list[dict]:
    eligible = [row for row in rows if normalized_pmcid(row.get("pmcid"))]
    all_results: list[dict] = []
    batches = list(chunks(eligible, batch_size))
    for batch_index, batch in enumerate(batches, start=1):
        batch_id = f"pmc_{batch_index:06d}"
        input_hash = batch_input_hash(batch, "pmc")
        path = checkpoint_path(run_dir, "pmc", batch_index)
        if path.exists():
            records = load_checkpoint(path, expected_hash=input_hash)
        else:
            records = fetch_pmc_batch_with_isolation(
                batch,
                client=client,
                run_id=run_id,
                batch_id=batch_id,
                email=email,
                api_key=api_key,
            )
            save_checkpoint(
                path,
                provider="pmc",
                batch_id=batch_id,
                input_hash=input_hash,
                records=records,
            )
        all_results.extend(records)
        update_live_manifest(manifest, manifest_path, "pmc", batch_index, len(batches), all_results)
        print(
            f"PMC batches {batch_index:,}/{len(batches):,}: "
            f"recovered={sum(row['status'] == 'recovered' for row in all_results):,}",
            flush=True,
        )
    return all_results


def run_semantic_scholar_batches(
    rows: Sequence[dict],
    *,
    run_id: str,
    run_dir: Path,
    client: BatchHttpClient,
    batch_size: int,
    api_key: str,
    manifest: dict,
    manifest_path: Path,
) -> list[dict]:
    all_results: list[dict] = []
    batches = list(chunks(list(rows), min(500, batch_size)))
    endpoint = (
        "https://api.semanticscholar.org/graph/v1/paper/batch?"
        + urlencode({"fields": "paperId,externalIds,title,abstract,year"})
    )
    for batch_index, batch in enumerate(batches, start=1):
        batch_id = f"semantic_scholar_{batch_index:06d}"
        input_hash = batch_input_hash(batch, "semantic_scholar")
        path = checkpoint_path(run_dir, "semantic_scholar", batch_index)
        if path.exists():
            records = load_checkpoint(path, expected_hash=input_hash)
        else:
            records = fetch_semantic_scholar_batch_with_isolation(
                batch,
                client=client,
                endpoint=endpoint,
                api_key=api_key,
                run_id=run_id,
                batch_id=batch_id,
            )
            save_checkpoint(
                path,
                provider="semantic_scholar",
                batch_id=batch_id,
                input_hash=input_hash,
                records=records,
            )
        all_results.extend(records)
        update_live_manifest(manifest, manifest_path, "semantic_scholar", batch_index, len(batches), all_results)
        print(
            f"Semantic Scholar batches {batch_index:,}/{len(batches):,}: "
            f"recovered={sum(row['status'] == 'recovered' for row in all_results):,}",
            flush=True,
        )
    return all_results


def fetch_semantic_scholar_batch_with_isolation(
    rows: Sequence[dict],
    *,
    client: BatchHttpClient,
    endpoint: str,
    api_key: str,
    run_id: str,
    batch_id: str,
) -> list[dict]:
    """Fetch an S2 batch, isolating a DOI that causes a batch-level HTTP 400."""
    eligible = [row for row in rows if semantic_scholar_identifier_eligible(row.get("doi", ""))]
    if len(eligible) != len(rows):
        eligible_dois = {normalized_doi(row.get("doi")) for row in eligible}
        fetched = (
            fetch_semantic_scholar_batch_with_isolation(
                eligible,
                client=client,
                endpoint=endpoint,
                api_key=api_key,
                run_id=run_id,
                batch_id=batch_id,
            )
            if eligible
            else []
        )
        fetched_by_doi = {normalized_doi(row.get("doi")): row for row in fetched}
        timestamp = now_utc()
        return [
            fetched_by_doi[normalized_doi(row.get("doi"))]
            if normalized_doi(row.get("doi")) in eligible_dois
            else result_row(
                run_id,
                "semantic_scholar",
                batch_id,
                normalized_doi(row.get("doi")),
                "",
                "",
                "provider_ineligible",
                "",
                timestamp,
                error="Semantic Scholar does not index GBIF dataset-download DOIs",
            )
            for row in rows
        ]
    try:
        payload = client.post_json(
            endpoint,
            {"ids": [f"DOI:{normalized_doi(row['doi'])}" for row in rows]},
            headers={"x-api-key": api_key} if api_key else {},
        )
        return parse_semantic_scholar_batch(payload, rows, run_id=run_id, batch_id=batch_id)
    except HTTPError as error:
        if error.code != 400:
            raise
        if len(rows) > 1:
            midpoint = max(1, len(rows) // 2)
            return [
                *fetch_semantic_scholar_batch_with_isolation(
                    rows[:midpoint],
                    client=client,
                    endpoint=endpoint,
                    api_key=api_key,
                    run_id=run_id,
                    batch_id=batch_id,
                ),
                *fetch_semantic_scholar_batch_with_isolation(
                    rows[midpoint:],
                    client=client,
                    endpoint=endpoint,
                    api_key=api_key,
                    run_id=run_id,
                    batch_id=batch_id,
                ),
            ]
        row = rows[0]
        return [
            result_row(
                run_id,
                "semantic_scholar",
                batch_id,
                normalized_doi(row.get("doi")),
                "",
                "",
                "request_error",
                "",
                now_utc(),
                error="HTTP 400 for single Semantic Scholar DOI",
            )
        ]


def semantic_scholar_identifier_eligible(doi: object) -> bool:
    return not normalized_doi(doi).startswith("10.15468/dl.")


def fetch_crossref_work(
    row: dict,
    *,
    client: BatchHttpClient,
    run_id: str,
    batch_id: str,
    email: str,
) -> dict:
    doi = normalized_doi(row.get("doi"))
    try:
        payload = client.get_json(
            f"https://api.crossref.org/works/{quote(doi, safe='')}",
            params={"mailto": email},
        )
        return parse_crossref_work(payload, row, run_id=run_id, batch_id=batch_id)
    except HTTPError as error:
        if error.code == 404:
            return result_row(run_id, "crossref", batch_id, doi, "", "", "not_found", "", now_utc())
        return result_row(
            run_id,
            "crossref",
            batch_id,
            doi,
            "",
            "",
            "request_error",
            "",
            now_utc(),
            error=f"HTTPError: {error.code}",
        )
    except Exception as error:
        return result_row(
            run_id,
            "crossref",
            batch_id,
            doi,
            "",
            "",
            "request_error",
            "",
            now_utc(),
            error=f"{type(error).__name__}: {error}",
        )


def run_crossref_batches(
    rows: Sequence[dict],
    *,
    run_id: str,
    run_dir: Path,
    client: BatchHttpClient,
    batch_size: int,
    workers: int,
    email: str,
    manifest: dict,
    manifest_path: Path,
) -> list[dict]:
    all_results: list[dict] = []
    batches = list(chunks(list(rows), batch_size))
    started_at = time.monotonic()
    worker_count = max(1, min(3, int(workers)))
    for batch_index, batch in enumerate(batches, start=1):
        batch_id = f"crossref_{batch_index:06d}"
        input_hash = batch_input_hash(batch, "crossref")
        path = checkpoint_path(run_dir, "crossref", batch_index)
        if path.exists():
            records = load_checkpoint(path, expected_hash=input_hash)
        else:
            def fetch(row: dict) -> dict:
                return fetch_crossref_work(
                    row,
                    client=client,
                    run_id=run_id,
                    batch_id=batch_id,
                    email=email,
                )

            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                records = list(executor.map(fetch, batch))
            save_checkpoint(
                path,
                provider="crossref",
                batch_id=batch_id,
                input_hash=input_hash,
                records=records,
            )
        all_results.extend(records)
        update_live_manifest(manifest, manifest_path, "crossref", batch_index, len(batches), all_results)
        elapsed = max(0.001, time.monotonic() - started_at)
        rate = len(all_results) / elapsed
        remaining = max(0, len(rows) - len(all_results))
        eta_hours = remaining / rate / 3600.0 if rate > 0 else 0.0
        print(
            f"Crossref batches {batch_index:,}/{len(batches):,}: "
            f"attempted={len(all_results):,}/{len(rows):,}; "
            f"recovered={sum(row['status'] == 'recovered' for row in all_results):,}; "
            f"request_errors={sum(row['status'] == 'request_error' for row in all_results):,}; "
            f"rate={rate:.2f}/s; eta={eta_hours:.2f}h",
            flush=True,
        )
    return all_results


def update_live_manifest(
    manifest: dict,
    manifest_path: Path,
    provider: str,
    completed_batches: int,
    total_batches: int,
    records: Sequence[dict],
) -> None:
    manifest["status"] = "running"
    manifest["updated_at_utc"] = now_utc()
    manifest.setdefault("providers", {})[provider] = {
        "completed_batches": int(completed_batches),
        "total_batches": int(total_batches),
        "records_attempted": int(len(records)),
        "status_counts": dict(Counter(clean(row.get("status", "")) for row in records)),
    }
    atomic_write_json(manifest_path, manifest)


def best_recovered_rows(results: Sequence[dict]) -> dict[str, dict]:
    priority = {"pubmed": 0, "pmc": 1, "crossref": 2, "semantic_scholar": 3}
    recovered = [
        row
        for row in results
        if clean(row.get("status", "")) == "recovered" and normalized_text(row.get("abstract", ""))
    ]
    recovered.sort(key=lambda row: (normalized_doi(row.get("doi")), priority.get(clean(row.get("provider")), 99)))
    out: dict[str, dict] = {}
    for row in recovered:
        doi = normalized_doi(row.get("doi"))
        if doi and doi not in out:
            out[doi] = row
    return out


def merge_recovered_abstracts(
    *,
    candidates_path: Path,
    metadata_path: Path,
    recovered_by_doi: dict[str, dict],
    run_id: str,
    run_dir: Path,
) -> dict:
    candidate_frame = pd.read_parquet(candidates_path)
    candidate_by_doi = {
        normalized_doi(row.get("doi")): row
        for row in candidate_frame.to_dict("records")
        if normalized_doi(row.get("doi")) in recovered_by_doi
    }
    existing_rows = read_table(metadata_path)
    existing_by_doi = {
        normalized_doi(row.get("doi")): row for row in existing_rows if normalized_doi(row.get("doi"))
    }
    updates: dict[str, dict] = {}
    skipped_existing = 0
    provider_counts: Counter[str] = Counter()
    timestamp = now_utc()
    for doi, result in recovered_by_doi.items():
        candidate = candidate_by_doi.get(doi)
        if candidate is None:
            continue
        base = merge_rows(existing_by_doi.get(doi, {}), candidate_metadata_row(candidate))
        if normalized_text(base.get("abstract", "")):
            skipped_existing += 1
            continue
        provider = clean(result.get("provider", ""))
        base["abstract"] = normalized_text(result.get("abstract", ""))
        base["metadata_provider"] = provider
        base["metadata_provider_chain"] = append_pipe_token(base.get("metadata_provider_chain", ""), provider)
        base["metadata_providers_queried"] = append_pipe_token(base.get("metadata_providers_queried", ""), provider)
        if provider == "semantic_scholar" and clean(result.get("provider_record_id", "")):
            base["semantic_scholar_id"] = clean(result.get("provider_record_id", ""))
        prior_error = clean(base.get("metadata_lookup_error", ""))
        if prior_error:
            warning = append_pipe_token(base.get("metadata_lookup_warnings", ""), f"pre_batch_error:{prior_error}")
            base["metadata_lookup_warnings"] = warning
            base["metadata_lookup_error"] = ""
        base["metadata_missing_reason"] = ""
        base["metadata_enrichment_status"] = "enriched"
        base["metadata_enrichment_run_id"] = run_id
        base["metadata_enriched_at_utc"] = timestamp
        base["paper_metadata_schema_version"] = PAPER_METADATA_SCHEMA_VERSION
        updates[doi] = {column: clean(base.get(column, "")) for column in OUTPUT_COLUMNS}
        provider_counts[provider] += 1

    backup_path = run_dir / "pre_merge_metadata_backup.parquet"
    if metadata_path.exists() and not backup_path.exists():
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(metadata_path, backup_path)
    merged_rows = merged_output_rows(updates, existing_by_doi)
    temporary = metadata_path.with_name(metadata_path.stem + ".batch_abstract_tmp.parquet")
    write_table(temporary, merged_rows)
    temporary.replace(metadata_path)
    return {
        "schema_version": "batch_abstract_merge_report_v1",
        "run_id": run_id,
        "merged_at_utc": timestamp,
        "metadata_table": str(metadata_path),
        "pre_merge_backup": str(backup_path) if backup_path.exists() else "",
        "rows_before": len(existing_rows),
        "rows_after": len(merged_rows),
        "abstracts_added": len(updates),
        "skipped_existing_abstract": skipped_existing,
        "abstracts_added_by_provider": dict(provider_counts),
        "metadata_table_sha256": sha256_file(metadata_path),
    }


def configuration_for(args: argparse.Namespace) -> dict:
    doi_path = Path(args.doi_file).resolve() if clean(args.doi_file) else None
    return {
        "candidate_table": str(Path(args.candidate_table).resolve()),
        "metadata_table": str(Path(args.metadata_table).resolve()),
        "doi_file": str(doi_path) if doi_path else "",
        "doi_file_sha256": sha256_file(doi_path) if doi_path and doi_path.exists() else "",
        "providers": [provider for provider in args.providers.split(",") if provider],
        "pubmed_batch_size": int(args.pubmed_batch_size),
        "pmc_batch_size": int(args.pmc_batch_size),
        "semantic_scholar_batch_size": min(500, int(args.semantic_scholar_batch_size)),
        "crossref_batch_size": int(args.crossref_batch_size),
        "crossref_workers": max(1, min(3, int(args.crossref_workers))),
        "limit": int(args.limit),
    }


def validate_or_initialize_manifest(
    manifest_path: Path,
    *,
    run_id: str,
    configuration: dict,
    scope_path: Path,
) -> dict:
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != MANIFEST_SCHEMA:
            raise ValueError(f"Unsupported run manifest: {manifest_path}")
        if manifest.get("configuration") != configuration:
            raise ValueError("Existing run configuration differs; choose a new run ID")
        manifest.setdefault("scope_sha256", sha256_file(scope_path))
        manifest.setdefault("scope_records", len(pd.read_parquet(scope_path, columns=["doi"])))
        return manifest
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "run_id": run_id,
        "status": "planned",
        "created_at_utc": now_utc(),
        "updated_at_utc": now_utc(),
        "configuration": configuration,
        "scope_table": str(scope_path),
        "scope_sha256": sha256_file(scope_path),
        "scope_records": len(pd.read_parquet(scope_path, columns=["doi"])),
        "providers": {},
    }
    atomic_write_json(manifest_path, manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=default_run_id())
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA))
    parser.add_argument("--doi-file", default="", help="Optional DOI scope, normally discovery new_candidate_dois.txt")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--providers", default="pubmed,pmc,semantic_scholar")
    parser.add_argument("--pubmed-batch-size", type=int, default=200)
    parser.add_argument("--pmc-batch-size", type=int, default=50)
    parser.add_argument("--semantic-scholar-batch-size", type=int, default=500)
    parser.add_argument("--crossref-batch-size", type=int, default=100)
    parser.add_argument("--pubmed-rps", type=float, default=None)
    parser.add_argument("--pmc-rps", type=float, default=None)
    parser.add_argument("--semantic-scholar-rps", type=float, default=None)
    parser.add_argument("--crossref-rps", type=float, default=None)
    parser.add_argument("--crossref-workers", type=int, default=3)
    parser.add_argument("--max-retries", type=int, default=None)
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--max-retry-after-sec", type=int, default=120)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--no-merge", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    providers = [part.strip() for part in args.providers.split(",") if part.strip()]
    unknown = set(providers) - {"pubmed", "pmc", "semantic_scholar", "crossref"}
    if unknown:
        raise SystemExit(f"Unsupported providers: {', '.join(sorted(unknown))}")
    args.providers = ",".join(providers)
    candidates_path = Path(args.candidate_table).resolve()
    metadata_path = Path(args.metadata_table).resolve()
    doi_path = Path(args.doi_file).resolve() if clean(args.doi_file) else None
    run_dir = Path(args.run_dir).resolve() if clean(args.run_dir) else (DEFAULT_RUNS_DIR / args.run_id).resolve()
    scope_path = run_dir / "missing_abstract_scope.parquet"
    manifest_path = run_dir / "run_manifest.json"

    allowed_dois = load_doi_scope(doi_path)
    if scope_path.exists():
        scope = pd.read_parquet(scope_path)
    else:
        scope = build_missing_abstract_scope(
            candidates_path,
            metadata_path,
            allowed_dois=allowed_dois,
            limit=max(0, args.limit),
        )

    pmc_eligible = int(scope["pmcid"].fillna("").astype(str).str.strip().ne("").sum()) if not scope.empty else 0
    pubmed_eligible = int(scope["pmid"].fillna("").astype(str).str.strip().ne("").sum()) if not scope.empty else 0
    print(f"Missing-abstract scope: {len(scope):,}", flush=True)
    print(f"PubMed-eligible: {pubmed_eligible:,}", flush=True)
    print(f"PMC-eligible: {pmc_eligible:,}", flush=True)
    print(f"Semantic Scholar-eligible: {len(scope):,}", flush=True)
    print(f"Crossref-eligible: {len(scope):,}", flush=True)
    if args.dry_run:
        return 0

    run_dir.mkdir(parents=True, exist_ok=True)
    if not scope_path.exists():
        atomic_write_parquet(scope_path, scope)
    configuration = configuration_for(args)
    manifest = validate_or_initialize_manifest(
        manifest_path,
        run_id=args.run_id,
        configuration=configuration,
        scope_path=scope_path,
    )
    if manifest.get("status") == "complete":
        print(f"Run already complete: {manifest_path}", flush=True)
        return 0
    if manifest.get("status") == "retrieval_complete" and args.no_merge:
        print(f"Retrieval already complete: {manifest_path}", flush=True)
        return 0
    config = load_config(Path(args.config).resolve())
    pubmed_config = config.get("pubmed", {}) if isinstance(config.get("pubmed"), dict) else {}
    pmc_config = config.get("pmc", {}) if isinstance(config.get("pmc"), dict) else {}
    semantic_config = config.get("semantic_scholar", {}) if isinstance(config.get("semantic_scholar"), dict) else {}
    crossref_config = config.get("crossref", {}) if isinstance(config.get("crossref"), dict) else {}
    max_retries = args.max_retries if args.max_retries is not None else read_int(semantic_config.get("max_retries"), 4)
    scope_rows = scope.to_dict("records")
    results: list[dict] = []

    try:
        if "pubmed" in providers:
            pubmed_client = BatchHttpClient(
                rps=(
                    args.pubmed_rps
                    if args.pubmed_rps is not None
                    else read_float(pubmed_config.get("rate_limit_per_sec"), 3.0)
                ),
                max_retries=max_retries,
                timeout_sec=args.timeout_sec,
                max_retry_after_sec=args.max_retry_after_sec,
                user_agent="kg-pipeline/batch-abstract-pubmed",
            )
            results.extend(
                run_pubmed_batches(
                    scope_rows,
                    run_id=args.run_id,
                    run_dir=run_dir,
                    client=pubmed_client,
                    batch_size=args.pubmed_batch_size,
                    email=clean(pubmed_config.get("email", "")),
                    api_key=clean(pubmed_config.get("api_key", "")),
                    manifest=manifest,
                    manifest_path=manifest_path,
                )
            )
        recovered_dois = set(best_recovered_rows(results))
        pmc_scope = [row for row in scope_rows if normalized_doi(row.get("doi")) not in recovered_dois]
        if "pmc" in providers:
            pmc_client = BatchHttpClient(
                rps=args.pmc_rps if args.pmc_rps is not None else read_float(pmc_config.get("rate_limit_per_sec"), 3.0),
                max_retries=max_retries,
                timeout_sec=args.timeout_sec,
                max_retry_after_sec=args.max_retry_after_sec,
                user_agent="kg-pipeline/batch-abstract-pmc",
            )
            results.extend(
                run_pmc_batches(
                    pmc_scope,
                    run_id=args.run_id,
                    run_dir=run_dir,
                    client=pmc_client,
                    batch_size=args.pmc_batch_size,
                    email=clean(pubmed_config.get("email", "")),
                    api_key=clean(pubmed_config.get("api_key", "")),
                    manifest=manifest,
                    manifest_path=manifest_path,
                )
            )
        recovered_dois = set(best_recovered_rows(results))
        semantic_scope = [row for row in scope_rows if normalized_doi(row.get("doi")) not in recovered_dois]
        if "semantic_scholar" in providers:
            semantic_client = BatchHttpClient(
                rps=(
                    args.semantic_scholar_rps
                    if args.semantic_scholar_rps is not None
                    else read_float(semantic_config.get("rate_limit_per_sec"), 0.5)
                ),
                max_retries=max_retries,
                timeout_sec=args.timeout_sec,
                max_retry_after_sec=args.max_retry_after_sec,
                user_agent="kg-pipeline/batch-abstract-semantic-scholar",
            )
            results.extend(
                run_semantic_scholar_batches(
                    semantic_scope,
                    run_id=args.run_id,
                    run_dir=run_dir,
                    client=semantic_client,
                    batch_size=args.semantic_scholar_batch_size,
                    api_key=clean(semantic_config.get("api_key", "")),
                    manifest=manifest,
                    manifest_path=manifest_path,
                )
            )

        recovered_dois = set(best_recovered_rows(results))
        crossref_scope = [row for row in scope_rows if normalized_doi(row.get("doi")) not in recovered_dois]
        if "crossref" in providers:
            crossref_client = BatchHttpClient(
                rps=(
                    args.crossref_rps
                    if args.crossref_rps is not None
                    else read_float(crossref_config.get("rate_limit_per_sec"), 8.0)
                ),
                max_retries=max_retries,
                timeout_sec=args.timeout_sec,
                max_retry_after_sec=args.max_retry_after_sec,
                user_agent="kg-pipeline/batch-abstract-crossref",
            )
            results.extend(
                run_crossref_batches(
                    crossref_scope,
                    run_id=args.run_id,
                    run_dir=run_dir,
                    client=crossref_client,
                    batch_size=args.crossref_batch_size,
                    workers=args.crossref_workers,
                    email=clean(crossref_config.get("email", "")),
                    manifest=manifest,
                    manifest_path=manifest_path,
                )
            )

        result_frame = pd.DataFrame(results, columns=list(RESULT_COLUMNS))
        results_path = run_dir / "abstract_enrichment_results.parquet"
        atomic_write_parquet(results_path, result_frame)
        recovered = best_recovered_rows(results)
        summary = {
            "schema_version": "batch_abstract_enrichment_summary_v1",
            "run_id": args.run_id,
            "generated_at_utc": now_utc(),
            "scope_records": len(scope),
            "provider_attempt_rows": len(results),
            "unique_abstracts_recovered": len(recovered),
            "recovery_pct": round(100.0 * len(recovered) / len(scope), 3) if len(scope) else 0.0,
            "status_counts_by_provider": {
                provider: dict(Counter(row["status"] for row in results if row["provider"] == provider))
                for provider in providers
            },
            "results_table": str(results_path),
        }
        summary_path = run_dir / "abstract_enrichment_summary.json"
        atomic_write_json(summary_path, summary)
        merge_report = None
        if not args.no_merge:
            merge_report = merge_recovered_abstracts(
                candidates_path=candidates_path,
                metadata_path=metadata_path,
                recovered_by_doi=recovered,
                run_id=args.run_id,
                run_dir=run_dir,
            )
            atomic_write_json(run_dir / "metadata_merge_report.json", merge_report)
        manifest["status"] = "complete" if merge_report is not None else "retrieval_complete"
        manifest["updated_at_utc"] = now_utc()
        manifest["completed_at_utc"] = now_utc()
        manifest["summary"] = summary
        if merge_report is not None:
            manifest["merge_report"] = merge_report
        atomic_write_json(manifest_path, manifest)
        print(f"Unique abstracts recovered: {len(recovered):,}", flush=True)
        if merge_report is not None:
            print(f"Abstracts added to metadata table: {merge_report['abstracts_added']:,}", flush=True)
        print(f"Run manifest: {manifest_path}", flush=True)
        return 0
    except Exception as error:
        manifest["status"] = "failed"
        manifest["updated_at_utc"] = now_utc()
        manifest["error"] = f"{type(error).__name__}: {error}"
        atomic_write_json(manifest_path, manifest)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
