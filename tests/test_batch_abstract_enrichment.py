import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pandas as pd

from pipeline.ingest.enrich_paper_metadata import read_table, write_table
from pipeline.ingest.run_batch_abstract_enrichment import (
    BatchHttpClient,
    best_recovered_rows,
    build_missing_abstract_scope,
    fetch_crossref_work,
    fetch_pmc_batch_with_isolation,
    fetch_semantic_scholar_batch_with_isolation,
    load_checkpoint,
    merge_recovered_abstracts,
    parse_pmc_batch,
    parse_pubmed_batch,
    parse_crossref_work,
    parse_semantic_scholar_batch,
    save_checkpoint,
)


class BatchAbstractEnrichmentTest(unittest.TestCase):
    def test_parse_crossref_work_strips_markup_and_checks_doi(self) -> None:
        recovered = parse_crossref_work(
            {
                "message": {
                    "DOI": "10.1000/ONE",
                    "abstract": "<jats:p><jats:bold>Background:</jats:bold> Recovered text.</jats:p>",
                }
            },
            {"doi": "10.1000/one"},
            run_id="test_run",
            batch_id="crossref_000001",
        )
        mismatch = parse_crossref_work(
            {"message": {"DOI": "10.1000/other", "abstract": "Do not merge."}},
            {"doi": "10.1000/one"},
            run_id="test_run",
            batch_id="crossref_000001",
        )

        self.assertEqual(recovered["status"], "recovered")
        self.assertEqual(recovered["abstract"], "Background: Recovered text.")
        self.assertEqual(mismatch["status"], "identifier_mismatch")
        self.assertEqual(mismatch["abstract"], "")

    def test_crossref_404_is_recorded_as_not_found(self) -> None:
        client = MagicMock()
        client.get_json.side_effect = HTTPError("https://example.org", 404, "not found", {}, None)

        row = fetch_crossref_work(
            {"doi": "10.1000/missing"},
            client=client,
            run_id="test_run",
            batch_id="crossref_000001",
            email="test@example.org",
        )

        self.assertEqual(row["status"], "not_found")
        self.assertEqual(row["doi"], "10.1000/missing")

    def test_pmc_http_400_batch_is_split_and_continues(self) -> None:
        one = b"""<pmc-articleset><article><front><article-meta>
        <article-id pub-id-type='pmcid'>PMC1</article-id>
        <article-id pub-id-type='doi'>10.1000/one</article-id>
        <abstract><p>First abstract.</p></abstract>
        </article-meta></front></article></pmc-articleset>"""
        two = b"""<pmc-articleset><article><front><article-meta>
        <article-id pub-id-type='pmcid'>PMC2</article-id>
        <article-id pub-id-type='doi'>10.1000/two</article-id>
        <abstract><p>Second abstract.</p></abstract>
        </article-meta></front></article></pmc-articleset>"""
        error = HTTPError("https://example.org", 400, "bad request", {}, None)
        client = MagicMock()
        client.post_form.side_effect = [error, one, two]

        rows = fetch_pmc_batch_with_isolation(
            [
                {"doi": "10.1000/one", "pmcid": "PMC1"},
                {"doi": "10.1000/two", "pmcid": "PMC2"},
            ],
            client=client,
            run_id="test_run",
            batch_id="pmc_000001",
            email="test@example.org",
            api_key="key",
        )

        self.assertEqual([row["status"] for row in rows], ["recovered", "recovered"])
        self.assertEqual(client.post_form.call_count, 3)

    def test_batch_client_retries_connection_reset(self) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"ok"
        client = BatchHttpClient(
            rps=1000,
            max_retries=1,
            timeout_sec=1,
            max_retry_after_sec=1,
            user_agent="test",
        )

        with patch(
            "pipeline.ingest.run_batch_abstract_enrichment.urlopen",
            side_effect=[ConnectionResetError("reset"), response],
        ) as mocked, patch("pipeline.ingest.run_batch_abstract_enrichment.time.sleep"):
            body = client.post_bytes("https://example.org", body=b"x", headers={})

        self.assertEqual(body, b"ok")
        self.assertEqual(mocked.call_count, 2)

    def test_parse_pmc_batch_maps_articles_and_prefers_longest_abstract(self) -> None:
        body = b"""<?xml version='1.0' encoding='UTF-8'?>
        <pmc-articleset>
          <article>
            <front><article-meta>
              <article-id pub-id-type='pmcid'>PMC123</article-id>
              <article-id pub-id-type='doi'>10.1000/One</article-id>
              <abstract abstract-type='short'><p>Short summary.</p></abstract>
              <abstract><title>Background</title><p>This is the longer structured abstract.</p></abstract>
            </article-meta></front>
          </article>
          <article>
            <front><article-meta>
              <article-id pub-id-type='pmcid'>PMC456</article-id>
              <article-id pub-id-type='doi'>10.1000/two</article-id>
            </article-meta></front>
          </article>
        </pmc-articleset>"""

        rows = parse_pmc_batch(
            body,
            [
                {"doi": "10.1000/one", "pmcid": "PMC123"},
                {"doi": "10.1000/two", "pmcid": "456"},
                {"doi": "10.1000/missing", "pmcid": "PMC999"},
            ],
            run_id="test_run",
            batch_id="pmc_000001",
        )

        self.assertEqual([row["status"] for row in rows], ["recovered", "no_abstract", "not_found"])
        self.assertEqual(rows[0]["abstract"], "Background This is the longer structured abstract.")
        self.assertEqual(rows[0]["provider_doi"], "10.1000/one")

    def test_parse_pubmed_batch_maps_by_pmid_and_checks_doi(self) -> None:
        body = b"""<PubmedArticleSet>
          <PubmedArticle>
            <MedlineCitation><PMID>123</PMID><Article>
              <ArticleTitle>Paper</ArticleTitle>
              <Abstract><AbstractText Label='BACKGROUND'>Recovered text.</AbstractText></Abstract>
            </Article></MedlineCitation>
            <PubmedData><ArticleIdList><ArticleId IdType='doi'>10.1000/one</ArticleId></ArticleIdList></PubmedData>
          </PubmedArticle>
        </PubmedArticleSet>"""

        rows = parse_pubmed_batch(
            body,
            [
                {"doi": "10.1000/one", "pmid": "123"},
                {"doi": "10.1000/missing", "pmid": "999"},
            ],
            run_id="test_run",
            batch_id="pubmed_000001",
        )

        self.assertEqual([row["status"] for row in rows], ["recovered", "not_found"])
        self.assertIn("Recovered text.", rows[0]["abstract"])
        self.assertEqual(rows[0]["provider_doi"], "10.1000/one")

    def test_parse_semantic_scholar_batch_preserves_input_identity(self) -> None:
        rows = parse_semantic_scholar_batch(
            [
                {
                    "paperId": "s2-one",
                    "externalIds": {"DOI": "10.1000/ONE"},
                    "abstract": "  A recovered\nabstract. ",
                },
                None,
                {
                    "paperId": "s2-wrong",
                    "externalIds": {"DOI": "10.1000/other"},
                    "abstract": "Do not merge this.",
                },
            ],
            [
                {"doi": "10.1000/one"},
                {"doi": "10.1000/two"},
                {"doi": "10.1000/three"},
            ],
            run_id="test_run",
            batch_id="semantic_scholar_000001",
        )

        self.assertEqual([row["status"] for row in rows], ["recovered", "not_found", "identifier_mismatch"])
        self.assertEqual(rows[0]["abstract"], "A recovered abstract.")
        self.assertEqual(rows[2]["abstract"], "")

    def test_semantic_scholar_short_response_is_realigned_by_doi(self) -> None:
        rows = parse_semantic_scholar_batch(
            [
                {"paperId": "one", "externalIds": {"DOI": "10.1000/one"}, "abstract": "First."},
                {"paperId": "three", "externalIds": {"DOI": "10.1000/three"}, "abstract": "Third."},
            ],
            [
                {"doi": "10.1000/one"},
                {"doi": "10.1000/two"},
                {"doi": "10.1000/three"},
            ],
            run_id="test_run",
            batch_id="semantic_scholar_000001",
        )

        self.assertEqual([row["status"] for row in rows], ["recovered", "not_found", "recovered"])
        self.assertEqual(rows[2]["abstract"], "Third.")

    def test_semantic_scholar_http_400_batch_is_split_and_continues(self) -> None:
        error = HTTPError("https://example.org", 400, "bad request", {}, None)
        client = MagicMock()
        client.post_json.side_effect = [
            error,
            [{"paperId": "one", "externalIds": {"DOI": "10.1000/one"}, "abstract": "First."}],
            error,
        ]

        rows = fetch_semantic_scholar_batch_with_isolation(
            [{"doi": "10.1000/one"}, {"doi": "10.1000/bad"}],
            client=client,
            endpoint="https://example.org/batch",
            api_key="",
            run_id="test_run",
            batch_id="semantic_scholar_000001",
        )

        self.assertEqual([row["status"] for row in rows], ["recovered", "request_error"])
        self.assertEqual(client.post_json.call_count, 3)

    def test_semantic_scholar_skips_gbif_dataset_download_dois(self) -> None:
        client = MagicMock()

        rows = fetch_semantic_scholar_batch_with_isolation(
            [{"doi": "10.15468/dl.example"}],
            client=client,
            endpoint="https://example.org/batch",
            api_key="",
            run_id="test_run",
            batch_id="semantic_scholar_000001",
        )

        self.assertEqual(rows[0]["status"], "provider_ineligible")
        client.post_json.assert_not_called()

    def test_scope_uses_existing_metadata_and_only_keeps_missing_abstracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidates = root / "candidate_papers.parquet"
            metadata = root / "paper_metadata_enrichment.parquet"
            pd.DataFrame(
                [
                    {"doi": "10.1000/candidate-complete", "abstract": "Candidate abstract", "pmcid": ""},
                    {"doi": "10.1000/metadata-complete", "abstract": "", "pmcid": "PMC2"},
                    {"doi": "10.1000/missing", "abstract": "", "pmcid": "PMC3"},
                    {"doi": "10.1000/outside", "abstract": "", "pmcid": "PMC4"},
                ]
            ).to_parquet(candidates, index=False)
            write_table(
                metadata,
                [
                    {
                        "doi": "10.1000/metadata-complete",
                        "abstract": "Existing metadata abstract",
                        "pmcid": "PMC2",
                    }
                ],
            )

            scope = build_missing_abstract_scope(
                candidates,
                metadata,
                allowed_dois={
                    "10.1000/candidate-complete",
                    "10.1000/metadata-complete",
                    "10.1000/missing",
                },
            )

        self.assertEqual(scope["doi"].tolist(), ["10.1000/missing"])
        self.assertEqual(scope.iloc[0]["pmcid"], "PMC3")

    def test_checkpoint_round_trip_rejects_different_input_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "batch.json"
            records = [
                {
                    "doi": "10.1000/one",
                    "provider": "pmc",
                    "status": "recovered",
                    "abstract": "Abstract.",
                }
            ]
            save_checkpoint(
                path,
                provider="pmc",
                batch_id="pmc_000001",
                input_hash="correct",
                records=records,
            )

            loaded = load_checkpoint(path, expected_hash="correct")
            with self.assertRaises(ValueError):
                load_checkpoint(path, expected_hash="wrong")

        self.assertEqual(loaded, records)

    def test_merge_adds_only_missing_abstracts_and_preserves_existing_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidates = root / "candidate_papers.parquet"
            metadata = root / "paper_metadata_enrichment.parquet"
            run_dir = root / "run"
            pd.DataFrame(
                [
                    {
                        "doi": "10.1000/new",
                        "study_title": "New paper",
                        "abstract": "",
                        "publication_type": "article",
                    },
                    {
                        "doi": "10.1000/existing",
                        "study_title": "Existing paper",
                        "abstract": "Candidate abstract",
                        "publication_type": "article",
                    },
                ]
            ).to_parquet(candidates, index=False)
            write_table(
                metadata,
                [
                    {
                        "doi": "10.1000/existing",
                        "study_title": "Existing paper",
                        "abstract": "Canonical abstract",
                        "metadata_provider": "pubmed",
                    },
                    {
                        "doi": "10.1000/unrelated",
                        "study_title": "Unrelated paper",
                        "abstract": "Preserve me",
                    },
                ],
            )
            recovered = {
                "10.1000/new": {
                    "doi": "10.1000/new",
                    "provider": "semantic_scholar",
                    "provider_record_id": "s2-new",
                    "abstract": "Newly recovered abstract.",
                    "status": "recovered",
                },
                "10.1000/existing": {
                    "doi": "10.1000/existing",
                    "provider": "pmc",
                    "provider_record_id": "PMC1",
                    "abstract": "Do not overwrite.",
                    "status": "recovered",
                },
            }

            report = merge_recovered_abstracts(
                candidates_path=candidates,
                metadata_path=metadata,
                recovered_by_doi=recovered,
                run_id="test_run",
                run_dir=run_dir,
            )
            rows = {row["doi"]: row for row in read_table(metadata)}
            candidate_rows = pd.read_parquet(candidates).set_index("doi")

        self.assertEqual(report["abstracts_added"], 1)
        self.assertEqual(report["skipped_existing_abstract"], 1)
        self.assertEqual(rows["10.1000/new"]["abstract"], "Newly recovered abstract.")
        self.assertEqual(rows["10.1000/new"]["semantic_scholar_id"], "s2-new")
        self.assertEqual(rows["10.1000/existing"]["abstract"], "Canonical abstract")
        self.assertEqual(rows["10.1000/unrelated"]["abstract"], "Preserve me")
        self.assertEqual(
            candidate_rows.loc["10.1000/new", "abstract"], "Newly recovered abstract."
        )
        self.assertEqual(
            report["candidate_materialization"]["changed_candidate_rows"], 1
        )

    def test_best_recovered_rows_prefers_pmc(self) -> None:
        selected = best_recovered_rows(
            [
                {"doi": "10.1000/one", "provider": "semantic_scholar", "status": "recovered", "abstract": "S2"},
                {"doi": "10.1000/one", "provider": "pmc", "status": "recovered", "abstract": "PMC"},
            ]
        )

        self.assertEqual(selected["10.1000/one"]["abstract"], "PMC")

    def test_best_recovered_rows_prefers_pubmed_over_pmc(self) -> None:
        selected = best_recovered_rows(
            [
                {"doi": "10.1000/one", "provider": "pmc", "status": "recovered", "abstract": "PMC"},
                {"doi": "10.1000/one", "provider": "pubmed", "status": "recovered", "abstract": "PubMed"},
            ]
        )

        self.assertEqual(selected["10.1000/one"]["abstract"], "PubMed")


if __name__ == "__main__":
    unittest.main()
