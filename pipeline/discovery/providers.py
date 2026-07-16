"""Provider adapters with count-first, exhaustive, auditable retrieval."""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
from http.client import IncompleteRead, RemoteDisconnected
import json
import os
import random
import re
import time
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .strategy import SearchExecution, clean


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
OPENALEX_RATE_LIMIT_ENDPOINT = "https://api.openalex.org/rate-limit"


class RequestBudgetExhausted(RuntimeError):
    """Raised before a request that would exceed the resumable run budget."""


class ProviderQuotaExhausted(RequestBudgetExhausted):
    """Raised when a provider reports that its external allowance is exhausted."""


@dataclass
class ProviderStats:
    provider: str
    requests: int = 0
    retries: int = 0
    throttled_seconds: float = 0.0
    errors: int = 0
    quota_pauses: int = 0

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "requests": self.requests,
            "retries": self.retries,
            "throttled_seconds": round(self.throttled_seconds, 3),
            "errors": self.errors,
            "quota_pauses": self.quota_pauses,
        }


class RateLimitedHttpClient:
    def __init__(
        self,
        *,
        provider: str,
        requests_per_second: float,
        max_requests: int = 0,
        max_retries: int = 4,
        timeout_seconds: int = 45,
        max_retry_after_seconds: int = 120,
        user_agent: str = "psychedelics-kg-living-search/2.0",
    ) -> None:
        self.provider = provider
        self.min_interval = 1.0 / max(0.01, requests_per_second)
        requested_limit = int(max_requests)
        self.max_requests: int | None = None if requested_limit == 0 else max(0, requested_limit)
        self.max_retries = max(0, int(max_retries))
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_retry_after_seconds = max(0, int(max_retry_after_seconds))
        self.user_agent = user_agent
        self.stats = ProviderStats(provider=provider)
        self.budget_context: dict[str, object] = {}
        self._last_request_monotonic = 0.0

    def _wait_for_slot(self) -> None:
        elapsed = time.monotonic() - self._last_request_monotonic
        delay = max(0.0, self.min_interval - elapsed)
        if delay:
            time.sleep(delay)
            self.stats.throttled_seconds += delay

    def _consume_budget(self) -> None:
        if self.max_requests is not None and self.stats.requests >= self.max_requests:
            raise RequestBudgetExhausted(
                f"{self.provider} request budget exhausted at {self.stats.requests}/{self.max_requests}; resume the run"
            )
        self.stats.requests += 1

    def _request_json(
        self,
        url: str,
        *,
        method: str,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        query = urlencode({key: value for key, value in (params or {}).items() if value not in (None, "")}, doseq=True)
        use_post = method.upper() == "POST"
        full_url = url if use_post else (f"{url}?{query}" if query else url)
        body = query.encode("utf-8") if use_post else None
        request_headers = {"Accept": "application/json", "User-Agent": self.user_agent}
        if use_post:
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        request_headers.update(headers or {})
        backoff = 2.0
        for attempt in range(self.max_retries + 1):
            self._consume_budget()
            self._wait_for_slot()
            try:
                request = Request(full_url, data=body, headers=request_headers, method=method.upper())
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    self._last_request_monotonic = time.monotonic()
                    payload = json.loads(response.read().decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError(f"{self.provider} returned a non-object JSON response")
                    return payload
            except HTTPError as error:
                self._last_request_monotonic = time.monotonic()
                retryable = error.code in RETRYABLE_STATUS_CODES
                retry_after = clean(error.headers.get("Retry-After") if error.headers else "")
                delay = float(retry_after) if retry_after.isdigit() else backoff
                if (
                    error.code == 429
                    and self.max_retry_after_seconds
                    and delay > self.max_retry_after_seconds
                ):
                    self.stats.quota_pauses += 1
                    raise ProviderQuotaExhausted(
                        f"{self.provider} allowance exhausted; Retry-After={delay:.0f}s"
                    ) from error
                if not retryable or attempt >= self.max_retries:
                    self.stats.errors += 1
                    raise
                if self.max_retry_after_seconds and delay > self.max_retry_after_seconds:
                    self.stats.errors += 1
                    raise RuntimeError(
                        f"{self.provider} Retry-After {delay:.0f}s exceeds "
                        f"max_retry_after_seconds={self.max_retry_after_seconds}"
                    ) from error
                self.stats.retries += 1
                delay = max(backoff, delay) + random.uniform(0.0, 0.25)
                time.sleep(delay)
                self.stats.throttled_seconds += delay
                backoff *= 1.8
            except (URLError, TimeoutError, ConnectionError, IncompleteRead, RemoteDisconnected):
                self._last_request_monotonic = time.monotonic()
                if attempt >= self.max_retries:
                    self.stats.errors += 1
                    raise
                self.stats.retries += 1
                delay = backoff + random.uniform(0.0, 0.25)
                time.sleep(delay)
                self.stats.throttled_seconds += delay
                backoff *= 1.8
        raise RuntimeError(f"Unreachable retry state for {self.provider}")

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        return self._request_json(url, method="GET", params=params, headers=headers)

    def post_json(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        return self._request_json(url, method="POST", params=params, headers=headers)


def openalex_budget_status(api_key: str, *, timeout_seconds: int = 30) -> dict[str, object] | None:
    """Return a sanitized OpenAlex allowance summary without exposing the API key."""

    key = clean(api_key)
    if not key:
        return None
    query = urlencode({"api_key": key})
    request = Request(
        f"{OPENALEX_RATE_LIMIT_ENDPOINT}?{query}",
        headers={"Accept": "application/json", "User-Agent": "psychedelics-kg-living-search/2.0"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=max(1, int(timeout_seconds))) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rate_limit = payload.get("rate_limit", {}) if isinstance(payload, dict) else {}
        credit_costs = rate_limit.get("credit_costs", {}) if isinstance(rate_limit, dict) else {}
        endpoint_costs = rate_limit.get("endpoint_costs_usd", {}) if isinstance(rate_limit, dict) else {}
        remaining = int(rate_limit["credits_remaining"])
        search_cost = int(credit_costs["search"])
        if search_cost <= 0:
            return None
        credit_based_calls = max(0, remaining // search_cost)

        search_cost_usd = float(endpoint_costs.get("search", 0) or 0)
        daily_remaining_usd = float(rate_limit.get("daily_remaining_usd", 0) or 0)
        prepaid_remaining_usd = float(rate_limit.get("prepaid_remaining_usd", 0) or 0)
        usd_based_calls = (
            max(0, int((daily_remaining_usd + prepaid_remaining_usd) / search_cost_usd))
            if search_cost_usd > 0
            else 0
        )
        # Some OpenAlex plans expose the combined balance in credits_remaining,
        # while others report prepaid dollars separately. Taking the maximum
        # supports both response shapes without double-counting.
        return {
            "source": "openalex_rate_limit",
            "daily_remaining_usd": daily_remaining_usd,
            "prepaid_remaining_usd": prepaid_remaining_usd,
            "search_cost_usd": search_cost_usd,
            "search_requests_remaining": max(credit_based_calls, usd_based_calls),
            "resets_at": clean(rate_limit.get("resets_at")),
        }
    except (HTTPError, URLError, TimeoutError, ConnectionError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def openalex_remaining_search_requests(api_key: str, *, timeout_seconds: int = 30) -> int | None:
    """Return available OpenAlex search calls across daily and prepaid balances."""

    status = openalex_budget_status(api_key, timeout_seconds=timeout_seconds)
    return int(status["search_requests_remaining"]) if status is not None else None


def normalize_doi(value: object) -> str:
    doi = clean(value).lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix) :]
            break
    return doi.strip().rstrip(".")


def normalize_openalex_id(value: object) -> str:
    text = clean(value)
    return text.rsplit("/", 1)[-1] if text else ""


def normalize_pmid(value: object) -> str:
    text = clean(value)
    match = re.search(r"(?:PMID:|/pubmed/)?(\d+)$", text, flags=re.IGNORECASE)
    return match.group(1) if match else text


def normalize_pmcid(value: object) -> str:
    text = clean(value).upper()
    if not text:
        return ""
    match = re.search(r"PMC\d+", text)
    return match.group(0) if match else text


def year_from_text(value: object) -> str:
    match = re.search(r"\b(?:18|19|20|21)\d{2}\b", clean(value))
    return match.group(0) if match else ""


def authors_from_pubmed(values: Iterable[dict], max_names: int = 30) -> str:
    names: list[str] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        name = clean(item.get("name")) or " ".join(
            part for part in (clean(item.get("lastname")), clean(item.get("initials"))) if part
        )
        if name and name not in names:
            names.append(name)
        if len(names) >= max_names:
            break
    return "; ".join(names)


def authors_from_openalex(values: Iterable[dict], max_names: int = 30) -> str:
    names: list[str] = []
    for item in values:
        author = item.get("author", {}) if isinstance(item, dict) else {}
        name = clean(author.get("display_name")) if isinstance(author, dict) else ""
        if name and name not in names:
            names.append(name)
        if len(names) >= max_names:
            break
    return "; ".join(names)


def doi_from_pubmed_ids(values: Iterable[dict]) -> str:
    for item in values:
        if not isinstance(item, dict):
            continue
        if clean(item.get("idtype")).lower() == "doi":
            return normalize_doi(item.get("value"))
    return ""


def pmcid_from_pubmed_ids(values: Iterable[dict]) -> str:
    for item in values:
        if not isinstance(item, dict):
            continue
        if clean(item.get("idtype")).lower() in {"pmc", "pmcid"}:
            return normalize_pmcid(item.get("value"))
    return ""


def source_from_openalex(item: dict) -> str:
    location = item.get("primary_location", {}) if isinstance(item, dict) else {}
    source = location.get("source", {}) if isinstance(location, dict) else {}
    return clean(source.get("display_name")) if isinstance(source, dict) else ""


def pubmed_date_params(execution: SearchExecution, start_date: str, end_date: str) -> dict[str, str]:
    datetype = {"publication": "pdat", "entrez": "edat"}.get(execution.date_basis)
    if not datetype:
        raise ValueError(f"Unsupported PubMed date basis: {execution.date_basis}")
    return {
        "datetype": datetype,
        "mindate": start_date.replace("-", "/"),
        "maxdate": end_date.replace("-", "/"),
    }


def openalex_filters(execution: SearchExecution, start_date: str, end_date: str) -> list[str]:
    if execution.date_basis == "publication":
        return [f"from_publication_date:{start_date}", f"to_publication_date:{end_date}"]
    if execution.date_basis == "created":
        return [f"from_created_date:{start_date}", f"to_created_date:{end_date}"]
    raise ValueError(f"Unsupported OpenAlex date basis: {execution.date_basis}")


class PubMedProvider:
    name = "pubmed"
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(self, client: RateLimitedHttpClient, *, email: str = "", api_key: str = "") -> None:
        self.client = client
        self.email = email
        self.api_key = api_key

    def _common(self) -> dict[str, object]:
        return {
            "tool": "psychedelics_kg_living_search",
            "email": self.email or None,
            "api_key": self.api_key or None,
        }

    def count(self, execution: SearchExecution, start_date: str, end_date: str) -> int:
        # POST avoids URL-length truncation for the broad controlled-vocabulary
        # queries while preserving the same ESearch semantics.
        payload = self.client.post_json(
            f"{self.base_url}/esearch.fcgi",
            params={
                **self._common(),
                **pubmed_date_params(execution, start_date, end_date),
                "db": "pubmed",
                "term": execution.query,
                "retmode": "json",
                "rettype": "count",
                "retmax": 0,
                "sort": "pub_date",
            },
        )
        return int(payload.get("esearchresult", {}).get("count", 0) or 0)

    def fetch_page(
        self,
        execution: SearchExecution,
        start_date: str,
        end_date: str,
        *,
        token: str,
        page_size: int,
    ) -> tuple[list[dict], str | None]:
        retstart = int(token or 0)
        payload = self.client.post_json(
            f"{self.base_url}/esearch.fcgi",
            params={
                **self._common(),
                **pubmed_date_params(execution, start_date, end_date),
                "db": "pubmed",
                "term": execution.query,
                "retmode": "json",
                "retstart": retstart,
                "retmax": page_size,
                "sort": "pub_date",
            },
        )
        ids = [clean(value) for value in payload.get("esearchresult", {}).get("idlist", []) if clean(value)]
        summaries: dict[str, dict] = {}
        for offset in range(0, len(ids), 200):
            batch = ids[offset : offset + 200]
            summary = self.client.get_json(
                f"{self.base_url}/esummary.fcgi",
                params={
                    **self._common(),
                    "db": "pubmed",
                    "id": ",".join(batch),
                    "retmode": "json",
                },
            )
            result = summary.get("result", {}) if isinstance(summary, dict) else {}
            if isinstance(result, dict):
                summaries.update({key: value for key, value in result.items() if isinstance(value, dict)})

        records: list[dict] = []
        for index, pmid in enumerate(ids):
            item = summaries.get(pmid, {})
            article_ids = item.get("articleids", []) if isinstance(item, dict) else []
            doi = doi_from_pubmed_ids(article_ids) or normalize_doi(item.get("elocationid"))
            records.append(
                {
                    "provider": "pubmed",
                    "provider_record_id": f"pmid:{pmid}",
                    "pmid": pmid,
                    "pmcid": pmcid_from_pubmed_ids(article_ids),
                    "doi": doi,
                    "openalex_id": "",
                    "semantic_scholar_id": "",
                    "title": clean(item.get("title")),
                    "authors": authors_from_pubmed(item.get("authors", []) if isinstance(item, dict) else []),
                    "publication_year": year_from_text(item.get("pubdate")),
                    "publication_date": clean(item.get("sortpubdate")) or clean(item.get("pubdate")),
                    "journal": clean(item.get("fulljournalname")) or clean(item.get("source")),
                    "publication_type": " | ".join(item.get("pubtype", []) if isinstance(item.get("pubtype"), list) else []),
                    "language": "",
                    "abstract": "",
                    "rank_in_partition": retstart + index + 1,
                }
            )
        next_start = retstart + len(ids)
        total = int(payload.get("esearchresult", {}).get("count", 0) or 0)
        next_token = str(next_start) if ids and next_start < total else None
        return records, next_token


class OpenAlexProvider:
    name = "openalex"
    endpoint = "https://api.openalex.org/works"

    def __init__(self, client: RateLimitedHttpClient, *, email: str = "", api_key: str = "") -> None:
        self.client = client
        self.email = email
        self.api_key = api_key

    def _params(
        self,
        execution: SearchExecution,
        start_date: str,
        end_date: str,
        *,
        per_page: int,
        cursor: str | None = None,
        select: str = "id",
    ) -> dict[str, object]:
        filters = openalex_filters(execution, start_date, end_date)
        params: dict[str, object] = {
            "per_page": per_page,
            "select": select,
            "mailto": self.email or None,
            "api_key": self.api_key or None,
        }
        if cursor is not None:
            params["cursor"] = cursor
        if execution.search_surface == "title_and_abstract":
            # OpenAlex currently deprecates field-specific search filters but
            # still supports them. We retain this explicit surface for noisy
            # direct pairs and record it in every execution row.
            filters.insert(0, f"title_and_abstract.search:{execution.query}")
        elif execution.search_surface in {"fulltext", "default"}:
            params["search"] = execution.query
        else:
            raise ValueError(f"Unsupported OpenAlex search surface: {execution.search_surface}")
        params["filter"] = ",".join(filters)
        return params

    def count(self, execution: SearchExecution, start_date: str, end_date: str) -> int:
        payload = self.client.get_json(
            self.endpoint,
            params=self._params(execution, start_date, end_date, per_page=1, select="id"),
        )
        return int(payload.get("meta", {}).get("count", 0) or 0)

    def fetch_page(
        self,
        execution: SearchExecution,
        start_date: str,
        end_date: str,
        *,
        token: str,
        page_size: int,
    ) -> tuple[list[dict], str | None]:
        select = (
            "id,doi,display_name,publication_year,publication_date,type,authorships,ids,"
            "primary_location,language,abstract_inverted_index"
        )
        payload = self.client.get_json(
            self.endpoint,
            params=self._params(
                execution,
                start_date,
                end_date,
                per_page=min(100, page_size),
                cursor=token or "*",
                select=select,
            ),
        )
        records: list[dict] = []
        for index, item in enumerate(payload.get("results", []) or []):
            if not isinstance(item, dict):
                continue
            ids = item.get("ids", {}) if isinstance(item.get("ids"), dict) else {}
            openalex_id = normalize_openalex_id(item.get("id") or ids.get("openalex"))
            if not openalex_id:
                continue
            records.append(
                {
                    "provider": "openalex",
                    "provider_record_id": f"openalex:{openalex_id}",
                    "pmid": normalize_pmid(ids.get("pmid")),
                    "pmcid": normalize_pmcid(ids.get("pmcid")),
                    "doi": normalize_doi(item.get("doi") or ids.get("doi")),
                    "openalex_id": openalex_id,
                    "semantic_scholar_id": "",
                    "title": clean(item.get("display_name")),
                    "authors": authors_from_openalex(item.get("authorships", [])),
                    "publication_year": clean(item.get("publication_year")),
                    "publication_date": clean(item.get("publication_date")),
                    "journal": source_from_openalex(item),
                    "publication_type": clean(item.get("type")),
                    "language": clean(item.get("language")),
                    "abstract": decode_openalex_abstract(item.get("abstract_inverted_index")),
                    "rank_in_partition": index + 1,
                }
            )
        next_cursor = clean(payload.get("meta", {}).get("next_cursor")) or None
        if not payload.get("results"):
            next_cursor = None
        return records, next_cursor


def decode_openalex_abstract(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    words: dict[int, str] = {}
    for token, positions in value.items():
        if not isinstance(token, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int) and position >= 0:
                words[position] = token
    return " ".join(words[index] for index in sorted(words))


def load_dotenv_if_present(path: str) -> None:
    """Load missing environment variables without logging secret values."""

    if not path or not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()
