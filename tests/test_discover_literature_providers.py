import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.ingest.discover_literature import (
    Seed,
    build_pubmed_query,
    enrich_rows_unpaywall,
    load_config,
    query_variants_for_backend,
    search_crossref,
    search_openalex,
    search_pubmed,
    search_semantic_scholar_edges,
)


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get_json(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params or {}, "headers": headers or {}})
        for matcher, payload in self.responses:
            if matcher(url, params or {}):
                return payload
        raise AssertionError(f"Unexpected URL: {url} params={params}")


class DiscoveryProviderParsingTest(unittest.TestCase):
    def test_pubmed_summary_rows_include_doi_and_pmid(self) -> None:
        client = FakeClient(
            [
                (
                    lambda url, params: url.endswith("/esearch.fcgi") and params.get("db") == "pubmed",
                    {"esearchresult": {"idlist": ["12345"]}},
                ),
                (
                    lambda url, params: url.endswith("/esummary.fcgi") and params.get("db") == "pubmed",
                    {
                        "result": {
                            "12345": {
                                "title": "A careful clinical paper",
                                "pubdate": "2023 Jul",
                                "authors": [{"name": "Doe J"}],
                                "articleids": [
                                    {"idtype": "pubmed", "value": "12345"},
                                    {"idtype": "doi", "value": "10.1000/example"},
                                    {"idtype": "pmc", "value": "PMC999"},
                                ],
                            }
                        }
                    },
                ),
            ]
        )

        rows = search_pubmed(
            client=client,
            email="curator@example.org",
            api_key="",
            seed=Seed("psilocybin depression", "Psilocybin", "Major depressive disorder"),
            max_results=5,
            require_doi=True,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["doi"], "10.1000/example")
        self.assertEqual(rows[0]["pmid"], "12345")
        self.assertEqual(rows[0]["pmcid"], "PMC999")
        self.assertEqual(rows[0]["year"], "2023")
        self.assertEqual(rows[0]["provider"], "pubmed")

    def test_crossref_rows_parse_title_author_and_year(self) -> None:
        client = FakeClient(
            [
                (
                    lambda url, params: url == "https://api.crossref.org/works",
                    {
                        "message": {
                            "items": [
                                {
                                    "DOI": "10.2000/example",
                                    "title": ["Binding assay paper"],
                                    "author": [{"given": "Jane", "family": "Doe"}],
                                    "published": {"date-parts": [[2021, 5, 1]]},
                                    "type": "journal-article",
                                }
                            ]
                        }
                    },
                )
            ]
        )

        rows = search_crossref(
            client=client,
            email="curator@example.org",
            seed=Seed("LSD 5-HT2A binding", "LSD", "5-HT2A"),
            max_results=5,
            require_doi=True,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["doi"], "10.2000/example")
        self.assertEqual(rows[0]["title"], "Binding assay paper")
        self.assertEqual(rows[0]["authors"], "Jane Doe")
        self.assertEqual(rows[0]["year"], "2021")
        self.assertEqual(rows[0]["crossref_type"], "journal-article")

    def test_openalex_search_sends_api_key_when_configured(self) -> None:
        client = FakeClient(
            [
                (
                    lambda url, params: url == "https://api.openalex.org/works",
                    {"results": []},
                )
            ]
        )

        search_openalex(
            client=client,
            email="curator@example.org",
            api_key="oa_test_key",
            seed=Seed("MDMA PTSD", "MDMA", "Post-traumatic stress disorder"),
            max_results=5,
            require_doi=True,
        )

        self.assertEqual(client.calls[0]["params"]["api_key"], "oa_test_key")
        self.assertEqual(client.calls[0]["params"]["mailto"], "curator@example.org")

    def test_load_config_merges_ignored_local_config(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "config.example.yaml"
            local_path = root / "config.local.yaml"
            config_path.write_text(
                """
openalex:
  api_key: ""
  rate_limit_per_sec: 2.0
semantic_scholar:
  max_retries: 4
""".strip()
                + "\n",
                encoding="utf-8",
            )
            local_path.write_text(
                """
openalex:
  api_key: "local-key"
  rate_limit_per_sec: 3.0
semantic_scholar:
  api_key: "s2-key"
""".strip()
                + "\n",
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config["openalex"]["api_key"], "local-key")
        self.assertEqual(config["openalex"]["rate_limit_per_sec"], 3.0)
        self.assertEqual(config["semantic_scholar"]["max_retries"], 4)
        self.assertEqual(config["semantic_scholar"]["api_key"], "s2-key")

    def test_unpaywall_enrichment_requires_real_email(self) -> None:
        rows = [{"doi": "10.2000/example"}]
        enriched, errors = enrich_rows_unpaywall(
            client=FakeClient([]),
            email="test@example.com",
            rows=rows,
        )

        self.assertIs(enriched, rows)
        self.assertEqual(errors, [{"error": "unpaywall_email_missing_or_placeholder"}])

    def test_pubmed_query_variant_uses_fielded_aliases(self) -> None:
        seed = Seed("MDMA SERT transporter", "MDMA", "SERT (SLC6A4)")

        query = build_pubmed_query(seed, "mechanistic")

        self.assertIn('"3,4-methylenedioxymethamphetamine"[Title/Abstract]', query)
        self.assertIn('SLC6A4[Title/Abstract]', query)
        self.assertIn('binding[Title/Abstract]', query)

    def test_conservative_variants_add_pubmed_fielded_query_only(self) -> None:
        seed = Seed("MDMA SERT transporter", "MDMA", "SERT (SLC6A4)")

        pubmed_variants = query_variants_for_backend(seed, "mechanistic", "pubmed", "conservative")
        openalex_variants = query_variants_for_backend(seed, "mechanistic", "openalex", "conservative")

        self.assertEqual(len(pubmed_variants), 2)
        self.assertEqual(len(openalex_variants), 1)

    def test_semantic_scholar_reference_edges_parse_cited_paper(self) -> None:
        client = FakeClient(
            [
                (
                    lambda url, params: url.endswith("/references"),
                    {
                        "data": [
                            {
                                "citedPaper": {
                                    "title": "Referenced paper",
                                    "year": 2020,
                                    "externalIds": {"DOI": "10.3000/reference"},
                                    "authors": [{"name": "Ref A"}],
                                }
                            }
                        ]
                    },
                )
            ]
        )

        rows = search_semantic_scholar_edges(
            client=client,
            api_key="s2-key",
            source_doi="10.1000/source",
            seed=Seed("Source paper", "MDMA", "SERT (SLC6A4)"),
            direction="references",
            max_results=5,
            require_doi=True,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["doi"], "10.3000/reference")
        self.assertEqual(rows[0]["provider"], "semantic_scholar_references")
        self.assertEqual(rows[0]["citation_source_doi"], "10.1000/source")


if __name__ == "__main__":
    unittest.main()
