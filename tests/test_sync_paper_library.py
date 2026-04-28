import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from pipeline.ingest.sync_paper_library import (
    download_pdf_candidates,
    fetch_metadata_with_fallbacks,
    include_existing_metadata_refresh_rows,
    lookup_pmc_metadata,
    metadata_pdf_candidates,
    metadata_from_unpaywall_payload,
    parse_provider_order,
    row_needs_oa_refresh,
)


class FakeClient:
    def __init__(self, json_responses=None, bytes_responses=None):
        self.json_responses = json_responses or []
        self.bytes_responses = bytes_responses or []
        self.calls = []

    def get_json(self, url, params=None, headers=None):
        self.calls.append({"method": "json", "url": url, "params": params or {}, "headers": headers or {}})
        for matcher, payload in self.json_responses:
            if matcher(url, params or {}):
                return payload
        raise AssertionError(f"Unexpected JSON URL: {url} params={params}")

    def get_bytes(self, url, headers=None):
        self.calls.append({"method": "bytes", "url": url, "headers": headers or {}})
        for matcher, payload in self.bytes_responses:
            if matcher(url):
                return payload
        raise AssertionError(f"Unexpected bytes URL: {url}")


class SyncPaperLibraryTest(unittest.TestCase):
    def test_default_order_uses_unpaywall_before_broad_fallbacks(self) -> None:
        self.assertEqual(
            parse_provider_order(""),
            ["pubmed", "pmc", "unpaywall", "crossref", "openalex", "semantic_scholar"],
        )

    def test_existing_row_without_unpaywall_or_pdf_gets_oa_refresh(self) -> None:
        row = {
            "study_doi": "10.1000/example",
            "study_title": "Known paper",
            "abstract": "Already have the abstract.",
            "open_access_status": "closed",
            "best_pdf_url": "",
        }

        self.assertTrue(row_needs_oa_refresh(row, ["pubmed", "pmc", "unpaywall", "crossref"]))

        row["unpaywall_checked"] = "true"
        self.assertFalse(row_needs_oa_refresh(row, ["pubmed", "pmc", "unpaywall", "crossref"]))

        row["pdf_download_status"] = "invalid_pdf_content"
        self.assertTrue(row_needs_oa_refresh(row, ["pubmed", "pmc", "unpaywall", "crossref"]))

    def test_refresh_missing_metadata_includes_existing_rows_absent_from_queue(self) -> None:
        papers = [{"study_doi": "10.1000/in-queue", "study_title": "Queued"}]
        existing_rows = [
            {
                "study_doi": "10.1000/in-queue",
                "study_title": "Queued",
                "abstract": "",
            },
            {
                "study_doi": "10.1000/missing-abstract",
                "study_title": "Existing missing abstract",
                "abstract": "",
                "contexts": [{"compound": "psilocybin", "entity": "5-HT2A"}],
            },
            {
                "study_doi": "10.1000/complete",
                "study_title": "Complete",
                "abstract": "Already complete.",
            },
        ]

        out = include_existing_metadata_refresh_rows(papers, existing_rows)

        self.assertEqual([row["study_doi"] for row in out], ["10.1000/in-queue", "10.1000/missing-abstract"])
        self.assertEqual(out[1]["study_title"], "Existing missing abstract")
        self.assertEqual(out[1]["contexts"], [{"compound": "psilocybin", "entity": "5-HT2A"}])

    def test_unpaywall_adds_pdf_without_overriding_pubmed_abstract_provider(self) -> None:
        doi = "10.1000/example"
        pubmed_xml = b"""
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345</PMID>
      <Article>
        <Journal><JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue></Journal>
        <ArticleTitle>PubMed title</ArticleTitle>
        <Abstract><AbstractText>PubMed abstract.</AbstractText></Abstract>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1000/example</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""
        clients = {
            "pubmed": FakeClient(
                json_responses=[
                    (
                        lambda url, params: url.endswith("/esearch.fcgi"),
                        {"esearchresult": {"idlist": ["12345"]}},
                    )
                ],
                bytes_responses=[(lambda url: url.startswith("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"), pubmed_xml)],
            ),
            "pmc": FakeClient(
                json_responses=[
                    (
                        lambda url, params: "idconv" in url,
                        {"records": []},
                    )
                ]
            ),
            "unpaywall": FakeClient(
                json_responses=[
                    (
                        lambda url, params: url.endswith("10.1000%2Fexample"),
                        {
                            "doi": doi,
                            "title": "Unpaywall title",
                            "year": 2024,
                            "is_oa": True,
                            "oa_status": "green",
                            "best_oa_location": {
                                "url": "https://repository.example/paper",
                                "url_for_pdf": "https://repository.example/paper.pdf",
                                "url_for_landing_page": "https://repository.example/paper",
                                "host_type": "repository",
                                "version": "acceptedVersion",
                                "license": "cc-by",
                            },
                            "oa_locations": [],
                            "z_authors": [{"raw_author_name": "Doe J"}],
                        },
                    )
                ]
            ),
            "crossref": FakeClient(),
            "openalex": FakeClient(),
        }

        metadata, errors, queried = fetch_metadata_with_fallbacks(
            doi=doi,
            paper={"study_doi": doi},
            provider_order=["pubmed", "pmc", "unpaywall", "crossref", "openalex"],
            clients=clients,
            openalex_email="curator@example.org",
            openalex_api_key="",
            ncbi_email="curator@example.org",
            ncbi_api_key="",
            crossref_email="curator@example.org",
            unpaywall_email="curator@example.org",
        )

        self.assertEqual(errors, [])
        self.assertEqual(queried, ["pubmed", "pmc", "unpaywall"])
        self.assertEqual(metadata["metadata_provider"], "pubmed")
        self.assertEqual(metadata["metadata_provider_chain"], "pubmed|unpaywall")
        self.assertEqual(metadata["abstract"], "PubMed abstract.")
        self.assertEqual(metadata["best_pdf_url"], "https://repository.example/paper.pdf")
        self.assertEqual(metadata["unpaywall_checked"], "true")

    def test_semantic_scholar_backfills_missing_abstract(self) -> None:
        doi = "10.1000/example"
        clients = {
            "openalex": FakeClient(json_responses=[(lambda url, params: True, {"results": []})]),
            "semantic_scholar": FakeClient(
                json_responses=[
                    (
                        lambda url, params: url.endswith("DOI%3A10.1000%2Fexample"),
                        {
                            "paperId": "abc123",
                            "title": "Semantic Scholar title",
                            "year": 2024,
                            "abstract": "Semantic Scholar abstract.",
                            "authors": [{"name": "Doe J"}],
                            "externalIds": {"DOI": doi, "PubMed": "12345"},
                            "isOpenAccess": True,
                            "openAccessPdf": {"url": "https://example.org/paper.pdf"},
                        },
                    )
                ]
            ),
        }

        metadata, errors, queried = fetch_metadata_with_fallbacks(
            doi=doi,
            paper={"study_doi": doi, "study_title": "Existing title"},
            provider_order=["openalex", "semantic_scholar"],
            clients=clients,
            openalex_email="curator@example.org",
            openalex_api_key="",
            ncbi_email="curator@example.org",
            ncbi_api_key="",
            crossref_email="curator@example.org",
            unpaywall_email="curator@example.org",
        )

        self.assertEqual(errors, [])
        self.assertEqual(queried, ["openalex", "semantic_scholar"])
        self.assertEqual(metadata["metadata_provider"], "semantic_scholar")
        self.assertEqual(metadata["abstract"], "Semantic Scholar abstract.")
        self.assertEqual(metadata["authors"], "Doe J")
        self.assertEqual(metadata["best_pdf_url"], "https://example.org/paper.pdf")

    def test_unpaywall_pmc_landing_adds_europepmc_candidate(self) -> None:
        metadata = metadata_from_unpaywall_payload(
            {
                "doi": "10.1000/example",
                "title": "Example",
                "year": 2024,
                "is_oa": True,
                "oa_status": "bronze",
                "best_oa_location": {
                    "host_type": "publisher",
                    "version": "publishedVersion",
                    "url_for_pdf": "https://publisher.example/paper.pdf",
                    "url": "https://publisher.example/paper.pdf",
                },
                "oa_locations": [
                    {
                        "host_type": "repository",
                        "version": "submittedVersion",
                        "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/6865516",
                    }
                ],
            },
            {"study_doi": "10.1000/example"},
        )

        candidates = metadata["unpaywall_pdf_url_candidates"].split(" | ")
        self.assertEqual(candidates[0], "https://europepmc.org/api/getPdf?pmcid=PMC6865516")
        self.assertIn("https://publisher.example/paper.pdf", candidates)
        self.assertEqual(metadata["best_pdf_url"], "https://europepmc.org/api/getPdf?pmcid=PMC6865516")

    def test_download_pdf_candidates_tries_next_candidate(self) -> None:
        client = FakeClient(
            bytes_responses=[
                (lambda url: url == "https://publisher.example/paper.pdf", b"<html>blocked</html>"),
                (lambda url: url == "https://repository.example/paper.pdf", b"%PDF-1.7\nbody"),
            ]
        )

        with TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "paper.pdf"
            status, error, size, selected, attempts = download_pdf_candidates(
                client=client,
                pdf_urls=["https://publisher.example/paper.pdf", "https://repository.example/paper.pdf"],
                target_path=target,
            )

        self.assertEqual(status, "downloaded")
        self.assertEqual(error, "")
        self.assertEqual(size, len(b"%PDF-1.7\nbody"))
        self.assertEqual(selected, "https://repository.example/paper.pdf")
        self.assertIn("https://publisher.example/paper.pdf", attempts)

    def test_pdf_candidates_derive_europepmc_from_any_pmc_url(self) -> None:
        candidates = metadata_pdf_candidates(
            {
                "pdf_url_candidates": "https://pmc.ncbi.nlm.nih.gov/articles/PMC6067998/pdf/",
            },
            "",
        )

        self.assertEqual(candidates[0], "https://europepmc.org/api/getPdf?pmcid=PMC6067998")
        self.assertIn("https://pmc.ncbi.nlm.nih.gov/articles/PMC6067998/pdf/", candidates)

    def test_pmc_uses_oa_file_pdf_url_when_available(self) -> None:
        doi = "10.1000/pmc-example"
        client = FakeClient(
            json_responses=[
                (
                    lambda url, params: "idconv" in url,
                    {"records": [{"doi": doi, "pmcid": "PMC9540857", "pmid": "123"}]},
                ),
                (
                    lambda url, params: "BioC_json" in url,
                    {
                        "documents": [
                            {
                                "passages": [
                                    {"infons": {"section_type": "TITLE"}, "text": "PMC paper"},
                                    {"infons": {"section_type": "ABSTRACT"}, "text": "PMC abstract."},
                                ]
                            }
                        ]
                    },
                ),
            ],
            bytes_responses=[
                (
                    lambda url: "oa.fcgi" in url,
                    b"""<OA><records><record id=\"PMC9540857\" license=\"CC BY-NC-ND\"><link format=\"pdf\" href=\"ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/aa/bb/example.pdf\" /></record></records></OA>""",
                )
            ],
        )

        metadata = lookup_pmc_metadata(
            client=client,
            doi=doi,
            email="curator@example.org",
            pmcid_hint="",
            paper={"study_doi": doi},
        )

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["pmcid"], "PMC9540857")
        self.assertEqual(metadata["is_oa"], "true")
        self.assertEqual(metadata["pmc_oa_license"], "CC BY-NC-ND")
        self.assertEqual(
            metadata["pmc_oa_pdf_url"],
            "https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/aa/bb/example.pdf",
        )
        self.assertEqual(
            metadata["best_pdf_url"],
            "https://europepmc.org/api/getPdf?pmcid=PMC9540857",
        )


if __name__ == "__main__":
    unittest.main()
