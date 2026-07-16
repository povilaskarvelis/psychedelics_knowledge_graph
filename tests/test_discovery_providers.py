import json
from http.client import IncompleteRead
from unittest.mock import patch

import pytest

from pipeline.discovery.providers import (
    OpenAlexProvider,
    PubMedProvider,
    RateLimitedHttpClient,
    RequestBudgetExhausted,
    openalex_budget_status,
    openalex_remaining_search_requests,
)
from pipeline.discovery.strategy import SearchExecution


def execution(**overrides) -> SearchExecution:
    values = {
        "execution_id": "exec_test",
        "search_id": "search_test",
        "dataset": "mechanistic",
        "provider": "openalex",
        "layer": "pair_grid",
        "search_type": "direct_pair",
        "module_id": "target_pairs",
        "query": 'psilocybin AND "5-HT2A"',
        "compound": "Psilocybin",
        "entity": "5-HT2A",
        "entity_type": "target",
        "search_surface": "title_and_abstract",
        "date_basis": "publication",
        "start_date": "2026-01-01",
        "end_date": "2026-07-15",
        "protocol_id": "protocol",
        "strategy_hash": "strategy",
        "scope_hash": "scope",
    }
    values.update(overrides)
    return SearchExecution(**values)


class CapturingClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get_json(self, url, *, params=None, headers=None):
        self.calls.append({"method": "GET", "url": url, "params": params or {}, "headers": headers or {}})
        return self.responses.pop(0)

    def post_json(self, url, *, params=None, headers=None):
        self.calls.append({"method": "POST", "url": url, "params": params or {}, "headers": headers or {}})
        return self.responses.pop(0)


class JsonResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'{"ok": true}'


class PayloadResponse(JsonResponse):
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_http_client_retries_connection_resets() -> None:
    client = RateLimitedHttpClient(
        provider="openalex",
        requests_per_second=100,
        max_requests=3,
        max_retries=1,
    )
    with patch(
        "pipeline.discovery.providers.urlopen",
        side_effect=[ConnectionResetError("reset"), JsonResponse()],
    ), patch("pipeline.discovery.providers.time.sleep"):
        assert client.get_json("https://example.test") == {"ok": True}
    assert client.stats.requests == 2
    assert client.stats.retries == 1


def test_http_client_retries_incomplete_response_reads() -> None:
    client = RateLimitedHttpClient(
        provider="pubmed",
        requests_per_second=100,
        max_requests=3,
        max_retries=1,
    )
    with patch(
        "pipeline.discovery.providers.urlopen",
        side_effect=[IncompleteRead(b"partial", 100), JsonResponse()],
    ), patch("pipeline.discovery.providers.time.sleep"):
        assert client.get_json("https://example.test") == {"ok": True}
    assert client.stats.requests == 2
    assert client.stats.retries == 1


def test_http_client_can_represent_verified_zero_request_budget() -> None:
    client = RateLimitedHttpClient(
        provider="openalex",
        requests_per_second=100,
        max_requests=-1,
    )
    with pytest.raises(RequestBudgetExhausted), patch("pipeline.discovery.providers.urlopen") as mocked:
        client.get_json("https://example.test")
    mocked.assert_not_called()


def test_openalex_remaining_search_requests_uses_live_credit_cost() -> None:
    response = PayloadResponse(
        {
            "rate_limit": {
                "credits_remaining": 240,
                "credit_costs": {"search": 10},
            }
        }
    )
    with patch("pipeline.discovery.providers.urlopen", return_value=response):
        assert openalex_remaining_search_requests("secret") == 24


def test_openalex_remaining_search_requests_includes_separate_prepaid_balance() -> None:
    response = PayloadResponse(
        {
            "rate_limit": {
                "credits_remaining": 0,
                "credit_costs": {"search": 10},
                "daily_remaining_usd": 0,
                "prepaid_remaining_usd": 10,
                "endpoint_costs_usd": {"search": 0.001},
            }
        }
    )
    with patch("pipeline.discovery.providers.urlopen", return_value=response):
        assert openalex_remaining_search_requests("secret") == 10_000


def test_openalex_budget_status_is_sanitized_and_auditable() -> None:
    response = PayloadResponse(
        {
            "api_key": "must-not-be-returned",
            "rate_limit": {
                "credits_remaining": 100,
                "credit_costs": {"search": 10},
                "daily_remaining_usd": 0.01,
                "prepaid_remaining_usd": 2,
                "endpoint_costs_usd": {"search": 0.001},
                "resets_at": "2026-07-16T00:00:00Z",
            },
        }
    )
    with patch("pipeline.discovery.providers.urlopen", return_value=response):
        status = openalex_budget_status("secret")
    assert status == {
        "source": "openalex_rate_limit",
        "daily_remaining_usd": 0.01,
        "prepaid_remaining_usd": 2.0,
        "search_cost_usd": 0.001,
        "search_requests_remaining": 2009,
        "resets_at": "2026-07-16T00:00:00Z",
    }


def test_http_client_treats_long_429_as_quota_pause() -> None:
    from urllib.error import HTTPError

    client = RateLimitedHttpClient(
        provider="openalex",
        requests_per_second=100,
        max_requests=2,
        max_retries=0,
        max_retry_after_seconds=120,
    )
    error = HTTPError(
        "https://example.test",
        429,
        "Too Many Requests",
        {"Retry-After": "3600"},
        None,
    )
    with patch("pipeline.discovery.providers.urlopen", side_effect=error):
        with pytest.raises(RequestBudgetExhausted, match="allowance exhausted"):
            client.get_json("https://example.test")
    assert client.stats.quota_pauses == 1
    assert client.stats.errors == 0

def test_openalex_search_surface_is_applied_to_the_actual_request() -> None:
    pair_client = CapturingClient([{"meta": {"count": 7}, "results": []}])
    pair_provider = OpenAlexProvider(pair_client)
    assert pair_provider.count(execution(), "2026-01-01", "2026-07-15") == 7
    pair_params = pair_client.calls[0]["params"]
    assert "search" not in pair_params
    assert pair_params["filter"].startswith("title_and_abstract.search:")
    assert "from_publication_date:2026-01-01" in pair_params["filter"]

    broad_client = CapturingClient([{"meta": {"count": 4}, "results": []}])
    broad_provider = OpenAlexProvider(broad_client)
    broad_execution = execution(search_surface="fulltext", layer="core", search_type="two_block_core")
    assert broad_provider.count(broad_execution, "2026-01-01", "2026-07-15") == 4
    broad_params = broad_client.calls[0]["params"]
    assert broad_params["search"] == broad_execution.query
    assert "title_and_abstract.search" not in broad_params["filter"]


def test_pubmed_keeps_provider_records_without_dois() -> None:
    client = CapturingClient(
        [
            {"esearchresult": {"count": "2", "idlist": ["11", "22"]}},
            {
                "result": {
                    "11": {
                        "uid": "11",
                        "title": "Older report without DOI",
                        "pubdate": "1962",
                        "authors": [{"name": "A Author"}],
                        "articleids": [],
                    },
                    "22": {
                        "uid": "22",
                        "title": "Report with DOI",
                        "pubdate": "2026",
                        "authors": [{"name": "B Author"}],
                        "articleids": [{"idtype": "doi", "value": "10.1000/example"}],
                    },
                }
            },
        ]
    )
    provider = PubMedProvider(client)
    pubmed_execution = execution(provider="pubmed", search_surface="text_word_and_controlled_vocabulary")

    records, next_token = provider.fetch_page(
        pubmed_execution,
        "1900-01-01",
        "2026-07-15",
        token="",
        page_size=1000,
    )

    assert next_token is None
    assert len(records) == 2
    assert records[0]["pmid"] == "11"
    assert records[0]["doi"] == ""
    assert records[1]["doi"] == "10.1000/example"
    assert client.calls[0]["method"] == "POST"
