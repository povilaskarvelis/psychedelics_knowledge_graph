import unittest
import xml.etree.ElementTree as ET
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

from pipeline.ingest.metadata_utils import (
    PAPER_METADATA_SCHEMA_VERSION,
    crossref_title_with_subtitle,
    download_pdf_candidates,
    fetch_metadata_with_fallbacks,
    funding_from_openalex_work,
    lookup_crossref_metadata,
    lookup_openalex_work,
    lookup_openalex_work_by_id,
    lookup_pmc_metadata,
    metadata_pdf_candidates,
    metadata_from_unpaywall_payload,
    ncbi_common_params,
    parse_provider_order,
    pubmed_article_id,
    row_needs_core_metadata_refresh,
    row_needs_oa_refresh,
    strip_markup,
)


class FakeClient:
    def __init__(self, json_responses=None, bytes_responses=None):
        self.max_retries = 0
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


class NCBIParamTest(unittest.TestCase):
    def test_empty_ncbi_credentials_are_omitted_from_request_params(self) -> None:
        self.assertEqual(ncbi_common_params("", ""), {"tool": "psychedelics_kg"})
        self.assertEqual(
            ncbi_common_params("curator@example.org", "secret"),
            {
                "tool": "psychedelics_kg",
                "email": "curator@example.org",
                "api_key": "secret",
            },
        )


class SequencedPdfClient:
    def __init__(self, responses, max_retries=1):
        self.responses = {url: list(items) for url, items in responses.items()}
        self.max_retries = max_retries
        self.calls = []

    def get_bytes_once(self, url, headers=None):
        self.calls.append(url)
        items = self.responses.get(url, [])
        if not items:
            raise TimeoutError("timed out")
        item = items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def get_bytes(self, url, headers=None):
        return self.get_bytes_once(url, headers=headers)


class MetadataUtilsTest(unittest.TestCase):
    def test_pubmed_article_id_ignores_cited_reference_identifiers(self) -> None:
        article = ET.fromstring(
            """
            <PubmedArticle>
              <MedlineCitation>
                <Article>
                  <ReferenceList>
                    <Reference>
                      <ArticleIdList>
                        <ArticleId IdType="doi">10.1000/cited</ArticleId>
                        <ArticleId IdType="pmc">PMC111111</ArticleId>
                      </ArticleIdList>
                    </Reference>
                  </ReferenceList>
                </Article>
              </MedlineCitation>
              <PubmedData>
                <ArticleIdList>
                  <ArticleId IdType="pubmed">12345678</ArticleId>
                  <ArticleId IdType="doi">10.1000/requested</ArticleId>
                </ArticleIdList>
              </PubmedData>
            </PubmedArticle>
            """
        )

        self.assertEqual(pubmed_article_id(article, "doi"), "10.1000/requested")
        self.assertEqual(pubmed_article_id(article, "pmc"), "")

    def test_pubmed_article_id_uses_own_pmcid_not_cited_reference(self) -> None:
        article = ET.fromstring(
            """
            <PubmedArticle>
              <MedlineCitation>
                <Article>
                  <ReferenceList>
                    <Reference>
                      <ArticleIdList>
                        <ArticleId IdType="pmc">PMC111111</ArticleId>
                      </ArticleIdList>
                    </Reference>
                  </ReferenceList>
                </Article>
              </MedlineCitation>
              <PubmedData>
                <ArticleIdList>
                  <ArticleId IdType="pmc">PMC999999</ArticleId>
                </ArticleIdList>
              </PubmedData>
            </PubmedArticle>
            """
        )

        self.assertEqual(pubmed_article_id(article, "pmc"), "PMC999999")

    def test_default_order_uses_unpaywall_before_broad_fallbacks(self) -> None:
        self.assertEqual(
            parse_provider_order(""),
            ["pubmed", "pmc", "unpaywall", "crossref", "openalex", "semantic_scholar"],
        )

    def test_strip_markup_keeps_escaped_subtitle_text(self) -> None:
        self.assertEqual(
            strip_markup("Main title&lt;subtitle&gt;A Randomized Trial&lt;/subtitle&gt;"),
            "Main title: A Randomized Trial",
        )
        self.assertEqual(strip_markup("Response in <i>DSM-5</i> drug use"), "Response in DSM-5 drug use")

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

    def test_core_metadata_refresh_ignores_abstract_only_gap(self) -> None:
        self.assertTrue(row_needs_core_metadata_refresh({"metadata_lookup_error": "failed"}))
        self.assertTrue(row_needs_core_metadata_refresh({"study_title": "", "abstract": "Has abstract"}))
        self.assertFalse(row_needs_core_metadata_refresh({"study_title": "Known title", "abstract": ""}))

    def test_unpaywall_adds_pdf_without_overriding_pubmed_abstract_provider(self) -> None:
        doi = "10.1000/example"
        pubmed_xml = b"""
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345</PMID>
        <Article>
        <Journal>
          <Title>Journal of Testing</Title>
          <ISSN IssnType="Print">1234-5678</ISSN>
          <ISSN IssnType="Electronic">8765-4321</ISSN>
          <JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue>
        </Journal>
        <ArticleDate><Year>2024</Year><Month>03</Month><Day>04</Day></ArticleDate>
        <ArticleTitle>PubMed title</ArticleTitle>
        <Abstract><AbstractText>PubMed abstract. Trial NCT01234567.</AbstractText></Abstract>
        <Language>eng</Language>
        <PublicationTypeList><PublicationType>Randomized Controlled Trial</PublicationType></PublicationTypeList>
        <GrantList><Grant><GrantID>R01-TEST</GrantID><Agency>NIMH</Agency></Grant></GrantList>
        <KeywordList><Keyword>psilocybin</Keyword><Keyword>depression</Keyword></KeywordList>
        <MeshHeadingList>
          <MeshHeading>
            <DescriptorName>Psilocybin</DescriptorName>
            <QualifierName>therapeutic use</QualifierName>
          </MeshHeading>
        </MeshHeadingList>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1000/example</ArticleId>
      </ArticleIdList>
      <CommentsCorrectionsList>
        <CommentsCorrections RefType="ErratumIn"><PMID>999</PMID><RefSource>J Test. 2025</RefSource></CommentsCorrections>
      </CommentsCorrectionsList>
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
        self.assertEqual(metadata["abstract"], "PubMed abstract. Trial NCT01234567.")
        self.assertEqual(metadata["study_journal"], "Journal of Testing")
        self.assertEqual(metadata["publication_type"], "Randomized Controlled Trial")
        self.assertEqual(metadata["trial_registry_ids"], "NCT01234567")
        self.assertEqual(metadata["publication_date"], "2024-03-04")
        self.assertEqual(metadata["journal_issn"], "1234-5678")
        self.assertEqual(metadata["journal_eissn"], "8765-4321")
        self.assertEqual(metadata["mesh_terms"], "Psilocybin / therapeutic use")
        self.assertEqual(metadata["keywords"], "psilocybin | depression")
        self.assertEqual(metadata["funders"], "NIMH")
        self.assertEqual(metadata["grant_ids"], "R01-TEST")
        self.assertEqual(metadata["has_correction"], "true")
        self.assertEqual(metadata["language"], "eng")
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
                            "publicationDate": "2024-05-06",
                            "abstract": "Semantic Scholar abstract.",
                            "authors": [{"name": "Doe J"}],
                            "externalIds": {"DOI": doi, "PubMed": "12345"},
                            "journal": {"name": "Semantic Medicine"},
                            "publicationVenue": {"name": "Semantic Medicine", "issn": "1111-2222;3333-4444"},
                            "publicationTypes": ["JournalArticle"],
                            "fieldsOfStudy": ["Medicine"],
                            "s2FieldsOfStudy": [{"category": "Psychology", "source": "external"}],
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
        self.assertEqual(metadata["study_journal"], "Semantic Medicine")
        self.assertEqual(metadata["publication_type"], "JournalArticle")
        self.assertEqual(metadata["publication_date"], "2024-05-06")
        self.assertEqual(metadata["journal_issn"], "1111-2222")
        self.assertEqual(metadata["journal_eissn"], "3333-4444")
        self.assertEqual(metadata["keywords"], "Medicine | Psychology | external")
        self.assertEqual(metadata["semantic_scholar_id"], "abc123")
        self.assertEqual(metadata["best_pdf_url"], "https://example.org/paper.pdf")

    @patch("pipeline.ingest.metadata_utils.metadata_from_openalex_work")
    @patch("pipeline.ingest.metadata_utils.lookup_openalex_work")
    @patch("pipeline.ingest.metadata_utils.lookup_pubmed_metadata")
    def test_later_provider_supplements_without_overwriting_preferred_abstract(
        self,
        mock_pubmed,
        mock_openalex_lookup,
        mock_openalex_metadata,
    ) -> None:
        doi = "10.1000/example"
        mock_pubmed.return_value = {
            "metadata_provider": "pubmed",
            "metadata_provider_chain": "pubmed",
            "study_title": "Preferred title",
            "abstract": "The complete PubMed abstract.",
            "publication_type": "Journal Article",
        }
        mock_openalex_lookup.return_value = {"id": "W1"}
        mock_openalex_metadata.return_value = {
            "metadata_provider": "openalex",
            "metadata_provider_chain": "openalex",
            "study_title": "Later title",
            "abstract": "A shorter or mismatched OpenAlex abstract.",
            "study_journal": "Journal supplied by OpenAlex",
            "openalex_id": "https://openalex.org/W1",
            "is_oa": "true",
            "oa_status": "green",
        }

        metadata, errors, queried = fetch_metadata_with_fallbacks(
            doi=doi,
            paper={"study_doi": doi},
            provider_order=["pubmed", "openalex"],
            clients={"pubmed": FakeClient(), "openalex": FakeClient()},
            openalex_email="curator@example.org",
            openalex_api_key="",
            ncbi_email="curator@example.org",
            ncbi_api_key="",
            crossref_email="curator@example.org",
            unpaywall_email="curator@example.org",
        )

        self.assertEqual(errors, [])
        self.assertEqual(queried, ["pubmed", "openalex"])
        self.assertEqual(metadata["metadata_provider"], "pubmed")
        self.assertEqual(metadata["metadata_provider_chain"], "pubmed|openalex")
        self.assertEqual(metadata["study_title"], "Preferred title")
        self.assertEqual(metadata["abstract"], "The complete PubMed abstract.")
        self.assertEqual(metadata["study_journal"], "Journal supplied by OpenAlex")
        self.assertEqual(metadata["openalex_id"], "https://openalex.org/W1")
        self.assertEqual(metadata["oa_status"], "green")

    def test_openalex_lookup_uses_current_select_fields(self) -> None:
        doi = "10.1000/example"
        client = FakeClient(
            json_responses=[
                (
                    lambda url, params: url == "https://api.openalex.org/works/doi:10.1000%2Fexample",
                    {"doi": "https://doi.org/10.1000/example"},
                )
            ]
        )

        work = lookup_openalex_work(client, doi=doi, email="curator@example.org", api_key="")

        self.assertEqual(work["doi"], "https://doi.org/10.1000/example")
        select = client.calls[0]["params"]["select"]
        self.assertIn("awards", select)
        self.assertIn("funders", select)
        self.assertNotIn("grants", select)

    def test_openalex_id_lookup_uses_free_singleton_endpoint(self) -> None:
        client = FakeClient(
            json_responses=[
                (
                    lambda url, params: url == "https://api.openalex.org/works/W123",
                    {"id": "https://openalex.org/W123"},
                )
            ]
        )

        work = lookup_openalex_work_by_id(
            client,
            openalex_id="https://openalex.org/W123",
            email="curator@example.org",
            api_key="key",
        )

        self.assertEqual(work["id"], "https://openalex.org/W123")
        self.assertEqual(client.calls[0]["params"]["api_key"], "key")

    def test_openalex_funding_reads_awards_and_funders(self) -> None:
        funders, grant_ids = funding_from_openalex_work(
            {
                "awards": [
                    {
                        "funder_display_name": "Gordon and Betty Moore Foundation",
                        "funder_award_id": "GBMF3834",
                    }
                ],
                "funders": [
                    {"display_name": "Gordon and Betty Moore Foundation"},
                    {"display_name": "Alfred P. Sloan Foundation"},
                ],
            }
        )

        self.assertEqual(funders, "Gordon and Betty Moore Foundation | Alfred P. Sloan Foundation")
        self.assertEqual(grant_ids, "GBMF3834")

    def test_unpaywall_pmc_landing_does_not_replace_direct_pdf_candidate(self) -> None:
        metadata = metadata_from_unpaywall_payload(
            {
                "doi": "10.1000/example",
                "title": "Example",
                "year": 2024,
                "published_date": "2024-07-08",
                "journal_name": "Unpaywall Journal",
                "journal_issn_l": "2222-3333",
                "journal_issns": "2222-3333,4444-5555",
                "publisher": "Unpaywall Publisher",
                "genre": "journal-article",
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
        self.assertEqual(candidates, ["https://publisher.example/paper.pdf"])
        self.assertEqual(metadata["best_pdf_url"], "https://publisher.example/paper.pdf")
        self.assertEqual(metadata["study_journal"], "Unpaywall Journal")
        self.assertEqual(metadata["publication_type"], "journal-article")
        self.assertEqual(metadata["publication_date"], "2024-07-08")
        self.assertEqual(metadata["journal_issn"], "2222-3333")
        self.assertEqual(metadata["journal_eissn"], "4444-5555")
        self.assertEqual(metadata["publisher"], "Unpaywall Publisher")

    def test_crossref_metadata_captures_publication_and_relation_details(self) -> None:
        doi = "10.1000/crossref-example"
        client = FakeClient(
            json_responses=[
                (
                    lambda url, params: url.endswith("10.1000%2Fcrossref-example"),
                    {
                        "message": {
                            "DOI": doi,
                            "title": ["Crossref title"],
                            "subtitle": ["subtitle retained"],
                            "abstract": "<jats:p>Crossref abstract. ISRCTN12345678.</jats:p>",
                            "issued": {"date-parts": [[2023, 11, 9]]},
                            "container-title": ["Crossref Journal"],
                            "type": "journal-article",
                            "ISSN": ["1357-2468", "2468-1357"],
                            "issn-type": [
                                {"type": "print", "value": "1357-2468"},
                                {"type": "electronic", "value": "2468-1357"},
                            ],
                            "publisher": "Crossref Publisher",
                            "subject": ["Psychiatry", "Neuroscience"],
                            "funder": [{"name": "Trial Funder", "award": ["ABC-123"]}],
                            "clinical-trial-number": [{"clinical-trial-number": "EudraCT number 2020-001234-56"}],
                            "relation": {
                                "is-correction-of": [
                                    {"id-type": "doi", "id": "10.1000/original", "asserted-by": "publisher"}
                                ]
                            },
                            "language": "en",
                        }
                    },
                )
            ]
        )

        metadata = lookup_crossref_metadata(
            client=client,
            doi=doi,
            email="curator@example.org",
            paper={"study_doi": doi},
        )

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["study_title"], "Crossref title: subtitle retained")
        self.assertEqual(metadata["publication_date"], "2023-11-09")
        self.assertEqual(metadata["journal_issn"], "1357-2468")
        self.assertEqual(metadata["journal_eissn"], "2468-1357")
        self.assertEqual(metadata["publisher"], "Crossref Publisher")
        self.assertEqual(metadata["keywords"], "Psychiatry | Neuroscience")
        self.assertEqual(metadata["funders"], "Trial Funder")
        self.assertEqual(metadata["grant_ids"], "ABC-123")
        self.assertEqual(metadata["related_dois"], "10.1000/original")
        self.assertIn("is-correction-of doi:10.1000/original", metadata["publication_relations"])
        self.assertEqual(metadata["has_correction"], "true")
        self.assertEqual(metadata["language"], "en")
        self.assertEqual(metadata["trial_registry_ids"], "ISRCTN12345678 | 2020-001234-56")

    def test_crossref_title_without_subtitle_strips_dangling_colon(self) -> None:
        title = crossref_title_with_subtitle({"title": ["Bioavailability of Ketamine:"]})

        self.assertEqual(title, "Bioavailability of Ketamine")

    def test_download_pdf_candidates_tries_next_candidate(self) -> None:
        client = FakeClient(
            bytes_responses=[
                (lambda url: url == "https://publisher.example/paper.pdf", b"<html>blocked</html>"),
                (lambda url: url == "https://repository.example/paper.pdf", b"%PDF-1.7\nbody"),
            ]
        )

        with TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "paper.pdf"
            with patch(
                "pipeline.ingest.metadata_utils.pdf_source_identity_result",
                return_value=(True, 1.0, "front_title_match"),
            ):
                status, error, size, selected, attempts = download_pdf_candidates(
                    client=client,
                    pdf_urls=["https://publisher.example/paper.pdf", "https://repository.example/paper.pdf"],
                    target_path=target,
                    study_title="Expected paper title",
                )

        self.assertEqual(status, "downloaded")
        self.assertEqual(error, "")
        self.assertEqual(size, len(b"%PDF-1.7\nbody"))
        self.assertEqual(selected, "https://repository.example/paper.pdf")
        self.assertIn("https://publisher.example/paper.pdf", attempts)

    def test_download_pdf_candidates_rotates_before_retrying_candidate(self) -> None:
        client = SequencedPdfClient(
            {
                "https://first.example/paper.pdf": [TimeoutError("timed out"), b"%PDF-1.7\nbody"],
                "https://second.example/paper.pdf": [TimeoutError("timed out")],
            },
            max_retries=1,
        )

        with TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "paper.pdf"
            with patch(
                "pipeline.ingest.metadata_utils.pdf_source_identity_result",
                return_value=(True, 1.0, "front_title_match"),
            ):
                status, error, size, selected, attempts = download_pdf_candidates(
                    client=client,
                    pdf_urls=["https://first.example/paper.pdf", "https://second.example/paper.pdf"],
                    target_path=target,
                    study_title="Expected paper title",
                )

        self.assertEqual(status, "downloaded")
        self.assertEqual(error, "")
        self.assertEqual(size, len(b"%PDF-1.7\nbody"))
        self.assertEqual(selected, "https://first.example/paper.pdf")
        self.assertEqual(
            client.calls,
            [
                "https://first.example/paper.pdf",
                "https://second.example/paper.pdf",
                "https://first.example/paper.pdf",
            ],
        )
        self.assertIn("https://second.example/paper.pdf", attempts)

    def test_download_pdf_candidates_removes_new_pdf_when_identity_is_unverified(self) -> None:
        client = FakeClient(
            bytes_responses=[
                (lambda url: True, b"%PDF-1.7\nwrong paper"),
            ]
        )

        with TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "paper.pdf"
            with patch(
                "pipeline.ingest.metadata_utils.pdf_source_identity_result",
                return_value=(False, 0.1, "front_title_match"),
            ):
                status, error, _size, _selected, _attempts = download_pdf_candidates(
                    client=client,
                    pdf_urls=["https://example.test/wrong.pdf"],
                    target_path=target,
                    study_title="Expected paper title",
                )

            self.assertFalse(target.exists())

        self.assertEqual(status, "download_failed")
        self.assertIn("source_identity_mismatch", error)

    def test_pdf_candidates_preserve_direct_pmc_url_without_europepmc_derivation(self) -> None:
        candidates = metadata_pdf_candidates(
            {
                "pdf_url_candidates": "https://pmc.ncbi.nlm.nih.gov/articles/PMC6067998/pdf/",
            },
            "",
        )

        self.assertEqual(
            candidates,
            ["https://pmc.ncbi.nlm.nih.gov/articles/PMC6067998/pdf/"],
        )

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
            "https://ftp.ncbi.nlm.nih.gov/pub/pmc/deprecated/oa_pdf/aa/bb/example.pdf",
        )
        self.assertEqual(
            metadata["best_pdf_url"],
            "https://ftp.ncbi.nlm.nih.gov/pub/pmc/deprecated/oa_pdf/aa/bb/example.pdf",
        )
        self.assertEqual(metadata["pmc_europepmc_pdf_url"], "")

    def test_pmc_rejects_unverified_pmcid_hint(self) -> None:
        doi = "10.1000/no-pmc-record"
        client = FakeClient(
            json_responses=[
                (
                    lambda url, params: "idconv" in url,
                    {"records": [{"doi": doi, "pmid": "123"}]},
                ),
            ]
        )

        metadata = lookup_pmc_metadata(
            client=client,
            doi=doi,
            email="curator@example.org",
            pmcid_hint="PMC111111",
            paper={"study_doi": doi},
        )

        self.assertIsNone(metadata)
        self.assertEqual(len(client.calls), 1)
        self.assertIn("idconv", client.calls[0]["url"])

    def test_pmc_idconv_overrides_conflicting_pmcid_hint(self) -> None:
        doi = "10.1000/verified-pmc-record"
        verified_pmcid = "PMC999999"
        client = FakeClient(
            json_responses=[
                (
                    lambda url, params: "idconv" in url,
                    {"records": [{"doi": doi, "pmcid": verified_pmcid, "pmid": "123"}]},
                ),
                (
                    lambda url, params: url.endswith(f"/{verified_pmcid}/unicode"),
                    {"documents": []},
                ),
            ],
            bytes_responses=[
                (
                    lambda url: "oa.fcgi" in url and f"id={verified_pmcid}" in url,
                    b'<OA><error code="idIsNotOpenAccess">not open</error></OA>',
                )
            ],
        )

        metadata = lookup_pmc_metadata(
            client=client,
            doi=doi,
            email="curator@example.org",
            pmcid_hint="PMC111111",
            paper={"study_doi": doi, "study_title": "Verified paper"},
        )

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["pmcid"], verified_pmcid)
        self.assertTrue(all("PMC111111" not in call["url"] for call in client.calls))


if __name__ == "__main__":
    unittest.main()
