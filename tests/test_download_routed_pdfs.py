import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import pandas as pd

from pipeline.fulltext.pdf_alternate_sources import AlternatePdfCandidate
from pipeline.ingest.metadata_utils import (
    download_pdf_candidates,
    ftp_to_https,
    is_probable_pdf_url,
    pdf_filename_for_doi,
    rank_pdf_candidates,
)
from pipeline.fulltext.download_routed_pdfs import (
    apply_result_to_candidate_table,
    build_download_tasks,
    classify_download_failure,
    deprioritize_candidates_by_host,
    download_rows_from_selection,
    download_routed_pdfs,
    filter_tasks_by_candidate_status,
    interleave_tasks_by_host,
    rate_limited_hosts_from_error,
    transient_failure_hosts_from_error,
    update_rate_limit_cooldowns,
)


class TestDownloadRoutedPdfs(unittest.TestCase):
    def test_download_rows_from_postscreen_selection(self) -> None:
        selection = pd.DataFrame(
            [
                {
                    "doi": "10.1000/known",
                    "selected_for_downstream": True,
                    "fulltext_enrichment_needed": True,
                    "fulltext_enrichment_action": "download_known_pdf",
                },
                {
                    "doi": "10.1000/discover",
                    "selected_for_downstream": True,
                    "fulltext_enrichment_needed": True,
                    "fulltext_enrichment_action": "discover_fulltext",
                },
                {
                    "doi": "10.1000/reuse",
                    "selected_for_downstream": True,
                    "fulltext_enrichment_needed": False,
                    "fulltext_enrichment_action": "reuse_existing_fulltext",
                },
            ]
        )

        direct = download_rows_from_selection(selection, include_discovery=False)
        discovery = download_rows_from_selection(selection, include_discovery=True)

        self.assertEqual(direct["doi"].tolist(), ["10.1000/known"])
        self.assertEqual(set(discovery["doi"]), {"10.1000/known", "10.1000/discover"})
        self.assertTrue(discovery["retained_for_extraction_candidate"].all())
        self.assertTrue(discovery["route_action"].eq("download_pdf_then_extract").all())

    def test_probable_pdf_url_classifier_accepts_common_pdf_patterns(self) -> None:
        positives = [
            "https://example.org/article.pdf",
            "https://example.org/article.pdf?download=1",
            "https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/aa/bb/article.PMC123.pdf",
            "https://ftp.ncbi.nlm.nih.gov/pub/pmc/deprecated/oa_pdf/aa/bb/article.PMC123.pdf",
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/pdf/article.pdf",
            "https://publisher.example/content/pdf/10.1000/example.pdf",
            "https://www.cell.com/article/S0092867420302105/pdf",
            "https://www.biologicalpsychiatryjournal.com/article/S000632231400910X/pdf",
            "https://repo.example/bitstream/123/456/download",
            "https://repo.example/bitstream/123/456/fulltext.pdf",
            "https://hal.science/hal-04567580/document",
            "https://archive-ouverte.unige.ch/access/metadata/c9a909e0-efcf-4ce5-9d80-c0cfeede1ef1/download",
            "https://publisher.example/article?pdf=render",
        ]
        negatives = [
            "https://doi.org/10.1000/example",
            "https://publisher.example/articles/10.1000/example",
            "https://example.org/landing-page",
            "https://europepmc.org/api/getPdf?pmcid=PMC123",
            "https://europepmc.org/articles/PMC123?pdf=render",
        ]

        for url in positives:
            self.assertTrue(is_probable_pdf_url(url), url)
        for url in negatives:
            self.assertFalse(is_probable_pdf_url(url), url)

    def test_ftp_to_https_uses_current_pmc_deprecated_path(self) -> None:
        self.assertEqual(
            ftp_to_https("ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/aa/bb/article.PMC123.pdf"),
            "https://ftp.ncbi.nlm.nih.gov/pub/pmc/deprecated/oa_pdf/aa/bb/article.PMC123.pdf",
        )

    def test_pdf_candidate_ranking_prefers_direct_pmc_before_europepmc(self) -> None:
        ranked = rank_pdf_candidates(
            [
                "https://europepmc.org/api/getPdf?pmcid=PMC123",
                "https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/aa/bb/article.PMC123.pdf",
                "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/pdf/article.pdf",
            ]
        )

        self.assertEqual(ranked[0], "https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/aa/bb/article.PMC123.pdf")
        self.assertEqual(ranked[1], "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/pdf/article.pdf")
        self.assertEqual(ranked[2], "https://europepmc.org/api/getPdf?pmcid=PMC123")

    def test_build_download_tasks_deduplicates_routes_and_combines_pdf_candidates(self) -> None:
        routes = pd.DataFrame(
            [
                {
                    "doi": "10.1000/example",
                    "retained_for_extraction_candidate": True,
                    "route_action": "download_pdf_then_extract",
                    "route_id": "r1",
                    "domain_route": "clinical_outcome",
                    "prompt_profile": "primary_clinical",
                    "best_pdf_url": "https://example.org/route.pdf",
                },
                {
                    "doi": "10.1000/example",
                    "retained_for_extraction_candidate": True,
                    "route_action": "download_pdf_then_extract",
                    "route_id": "r2",
                    "domain_route": "safety_tolerability",
                    "prompt_profile": "primary_safety",
                    "best_pdf_url": "https://example.org/route.pdf",
                },
                {
                    "doi": "10.1000/skip",
                    "retained_for_extraction_candidate": True,
                    "route_action": "extract_from_abstract_only",
                    "best_pdf_url": "https://example.org/skip.pdf",
                },
            ]
        )
        metadata = pd.DataFrame(
            [
                {
                    "doi": "10.1000/example",
                    "best_pdf_url": "https://example.org/meta.pdf",
                    "pdf_url_candidates": "https://example.org/route.pdf | https://example.org/other.pdf",
                }
            ]
        )

        tasks = build_download_tasks(routes, metadata)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["doi"], "10.1000/example")
        self.assertEqual(tasks[0]["route_count"], 2)
        self.assertEqual(tasks[0]["domain_routes"], "clinical_outcome|safety_tolerability")
        self.assertIn("https://example.org/route.pdf", tasks[0]["pdf_url_candidates"])
        self.assertIn("https://example.org/other.pdf", tasks[0]["pdf_url_candidates"])
        self.assertIn("https://example.org/meta.pdf", tasks[0]["pdf_url_candidates"])

    def test_apply_result_updates_candidate_row_for_downloaded_pdf(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/example",
                    "pdf_local_path": "",
                    "local_pdf_paths": "",
                    "local_pdf_count": 0,
                    "pdf_download_status": "skipped",
                    "pdf_sha256": "",
                    "flag_has_local_pdf": False,
                    "library_status": "",
                    "best_pdf_url": "",
                    "pdf_url_candidates": "",
                }
            ]
        )
        result = {
            "doi": "10.1000/example",
            "status": "downloaded",
            "pdf_local_path": "/tmp/example.pdf",
            "pdf_sha256": "abc123",
            "selected_url": "https://example.org/example.pdf",
            "pdf_url_candidates": "https://example.org/example.pdf",
            "failure_category": "",
            "failure_categories": "",
            "retry_recommended": False,
        }

        changed = apply_result_to_candidate_table(df, result)

        self.assertTrue(changed)
        self.assertEqual(df.loc[0, "pdf_local_path"], "/tmp/example.pdf")
        self.assertEqual(df.loc[0, "local_pdf_count"], 1)
        self.assertEqual(df.loc[0, "pdf_download_status"], "downloaded")
        self.assertTrue(bool(df.loc[0, "flag_has_local_pdf"]))
        self.assertEqual(df.loc[0, "library_status"], "in_database")
        self.assertEqual(df.loc[0, "pdf_download_failure_category"], "")
        self.assertFalse(bool(df.loc[0, "pdf_download_retry_recommended"]))

    def test_apply_result_records_retryable_failure_category(self) -> None:
        df = pd.DataFrame([{"doi": "10.1000/example", "pdf_download_status": "skipped"}])
        result = {
            "doi": "10.1000/example",
            "status": "download_failed",
            "error": "HTTPError: HTTP Error 429: Too Many Requests",
            "best_pdf_url": "https://europepmc.org/api/getPdf?pmcid=PMC1",
            "pdf_url_candidates": "https://europepmc.org/api/getPdf?pmcid=PMC1",
            **classify_download_failure("download_failed", "HTTPError: HTTP Error 429: Too Many Requests"),
        }

        changed = apply_result_to_candidate_table(df, result)

        self.assertTrue(changed)
        self.assertEqual(df.loc[0, "pdf_download_status"], "download_failed")
        self.assertEqual(df.loc[0, "pdf_download_failure_category"], "rate_limited")
        self.assertIn("rate_limited", df.loc[0, "pdf_download_failure_categories"])
        self.assertTrue(bool(df.loc[0, "pdf_download_retry_recommended"]))

    def test_download_routed_pdfs_dry_run_does_not_write_pdf_or_candidate_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            routes = root / "routes.parquet"
            metadata = root / "metadata.parquet"
            candidates = root / "candidate_papers.parquet"
            pdf_dir = root / "pdfs"
            report = root / "report.json"
            pd.DataFrame(
                [
                    {
                        "doi": "10.1000/example",
                        "retained_for_extraction_candidate": True,
                        "route_action": "download_pdf_then_extract",
                        "best_pdf_url": "https://example.org/example.pdf",
                    }
                ]
            ).to_parquet(routes, engine="pyarrow", index=False)
            pd.DataFrame(
                [{"doi": "10.1000/example", "best_pdf_url": "https://example.org/example.pdf", "pdf_url_candidates": ""}]
            ).to_parquet(metadata, engine="pyarrow", index=False)
            pd.DataFrame(
                [
                    {
                        "doi": "10.1000/example",
                        "pdf_local_path": "",
                        "local_pdf_paths": "",
                        "local_pdf_count": 0,
                        "pdf_download_status": "",
                    }
                ]
            ).to_parquet(candidates, engine="pyarrow", index=False)

            payload = download_routed_pdfs(
                route_table=routes,
                metadata_table=metadata,
                candidate_table=candidates,
                pdf_dir=pdf_dir,
                report_path=report,
                dry_run=True,
            )

            updated = pd.read_parquet(candidates)
            self.assertEqual(payload["counts"]["tasks"], 1)
            self.assertEqual(payload["counts"]["status"], {"dry_run": 1})
            self.assertEqual(updated.loc[0, "pdf_local_path"], "")
            self.assertFalse(any(pdf_dir.glob("*.pdf")))

    def test_download_routed_pdfs_can_use_alternate_pdf_source_after_direct_urls_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            routes = root / "routes.parquet"
            metadata = root / "metadata.parquet"
            candidates = root / "candidate_papers.parquet"
            pdf_dir = root / "pdfs"
            report = root / "report.json"
            doi = "10.1000/alternate"
            selected_url = "https://pmc.ncbi.nlm.nih.gov/articles/PMC1/pdf/article.pdf"

            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "study_title": "Alternate source paper",
                        "retained_for_extraction_candidate": True,
                        "route_action": "download_pdf_then_extract",
                    }
                ]
            ).to_parquet(routes, engine="pyarrow", index=False)
            pd.DataFrame([{"doi": doi, "study_title": "Alternate source paper"}]).to_parquet(
                metadata,
                engine="pyarrow",
                index=False,
            )
            pd.DataFrame([{"doi": doi, "pdf_download_status": ""}]).to_parquet(
                candidates,
                engine="pyarrow",
                index=False,
            )

            def fake_collect(**kwargs):
                return {
                    "candidates": [AlternatePdfCandidate(url=selected_url, source="pmc")],
                    "candidate_urls": selected_url,
                    "events": [{"event": "pmc_idconv_response", "pmcid_count": 1}],
                }

            def fake_download(**kwargs):
                target_path = kwargs["target_path"]
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_bytes(b"%PDF-1.7\nAlternate source paper\n%%EOF\n")
                return {
                    "status": "downloaded",
                    "error": "",
                    "size": target_path.stat().st_size,
                    "selected_url": selected_url,
                    "attempted_pdf_url_candidates": selected_url,
                    "events": [{"event": "pmc_pow_success"}],
                    "source": "pmc",
                    "download_mode": "pmc_pow",
                }

            with patch("pipeline.fulltext.download_routed_pdfs.collect_alternate_pdf_candidates", side_effect=fake_collect), patch(
                "pipeline.fulltext.download_routed_pdfs.download_alternate_pdf_candidates",
                side_effect=fake_download,
            ):
                payload = download_routed_pdfs(
                    route_table=routes,
                    metadata_table=metadata,
                    candidate_table=candidates,
                    pdf_dir=pdf_dir,
                    report_path=report,
                    alternate_pdf_sources={"pmc"},
                    max_retries=0,
                    attempt_log_every=0,
                    candidate_log_every=0,
                    progress_every=0,
                    rebuild_routes_after=False,
                )

            updated = pd.read_parquet(candidates)
            record = payload["records"][0]
            downloaded_path_exists = Path(updated.loc[0, "pdf_local_path"]).exists()

        self.assertEqual(payload["counts"]["status"], {"downloaded": 1})
        self.assertEqual(record["selected_url"], selected_url)
        self.assertEqual(record["alternate_pdf_sources"], "pmc")
        self.assertEqual(record["alternate_pdf_status"], "downloaded")
        self.assertEqual(record["alternate_pdf_candidate_count"], 1)
        self.assertEqual(updated.loc[0, "pdf_download_status"], "downloaded")
        self.assertTrue(downloaded_path_exists)

    def test_download_routed_pdfs_can_rebuild_routes_after_local_pdf_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            doi = "10.1000/auto-route"
            routes = root / "routes.parquet"
            metadata = root / "metadata.parquet"
            candidates = root / "candidate_papers.parquet"
            prescreen = root / "prescreen.parquet"
            fulltext_dir = root / "fulltext"
            pdf_dir = root / "pdfs"
            report = root / "report.json"
            summary = root / "routes_summary.json"
            counts = root / "routes_counts.csv"
            pdf_dir.mkdir()
            (pdf_dir / pdf_filename_for_doi(doi)).write_bytes(b"%PDF-1.7\nalready here\n%%EOF\n")

            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "retained_for_extraction_candidate": True,
                        "route_action": "download_pdf_then_extract",
                        "best_pdf_url": "https://example.org/paper.pdf",
                    }
                ]
            ).to_parquet(routes, engine="pyarrow", index=False)
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "study_title": "Psilocybin study with existing local PDF",
                        "abstract": "A retained paper.",
                        "publication_type": "Journal Article",
                        "best_pdf_url": "https://example.org/paper.pdf",
                    }
                ]
            ).to_parquet(metadata, engine="pyarrow", index=False)
            pd.DataFrame([{"doi": doi, "pdf_download_status": "download_failed"}]).to_parquet(
                candidates,
                engine="pyarrow",
                index=False,
            )
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "prescreen_decision": "retain",
                        "retained_for_extraction_candidate": True,
                        "prescreen_action": "retain_for_extraction_candidate",
                        "routing_tags": "clinical_outcome",
                    }
                ]
            ).to_parquet(prescreen, engine="pyarrow", index=False)
            with patch(
                "pipeline.fulltext.pdf_alternate_sources.title_validation_result",
                return_value=(True, 1.0, "title_match"),
            ):
                payload = download_routed_pdfs(
                    route_table=routes,
                    metadata_table=metadata,
                    candidate_table=candidates,
                    pdf_dir=pdf_dir,
                    report_path=report,
                    limit=1,
                    max_retries=0,
                    rebuild_routes_after=True,
                    prescreen_table=prescreen,
                    domain_routing_table=None,
                    fulltext_dir=fulltext_dir,
                    route_summary_json=summary,
                    route_counts_csv=counts,
                    manual_route_overrides=None,
                    attempt_log_every=0,
                    candidate_log_every=0,
                    progress_every=0,
                )

            updated_candidate = pd.read_parquet(candidates)
            rebuilt_routes = pd.read_parquet(routes)

        self.assertEqual(payload["counts"]["status"], {"already_present": 1})
        self.assertTrue(payload["route_rebuild"]["performed"])
        self.assertEqual(updated_candidate.loc[0, "pdf_download_status"], "already_present")
        self.assertEqual(rebuilt_routes.loc[0, "access_tier"], "local_pdf_available")
        self.assertEqual(rebuilt_routes.loc[0, "route_action"], "convert_local_pdf_then_extract")

    def test_download_limit_applies_after_candidate_status_skip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            routes = root / "routes.parquet"
            metadata = root / "metadata.parquet"
            candidates = root / "candidate_papers.parquet"
            pdf_dir = root / "pdfs"
            report = root / "report.json"
            route_rows = [
                {
                    "doi": f"10.1000/{idx}",
                    "retained_for_extraction_candidate": True,
                    "route_action": "download_pdf_then_extract",
                    "best_pdf_url": f"https://example.org/{idx}.pdf",
                }
                for idx in range(5)
            ]
            pd.DataFrame(route_rows).to_parquet(routes, engine="pyarrow", index=False)
            pd.DataFrame(
                [{"doi": f"10.1000/{idx}", "best_pdf_url": f"https://example.org/{idx}.pdf"} for idx in range(5)]
            ).to_parquet(metadata, engine="pyarrow", index=False)
            pd.DataFrame(
                [
                    {"doi": "10.1000/0", "pdf_download_status": "download_failed"},
                    {"doi": "10.1000/1", "pdf_download_status": "download_failed"},
                    {"doi": "10.1000/2", "pdf_download_status": "skipped"},
                    {"doi": "10.1000/3", "pdf_download_status": "skipped"},
                    {"doi": "10.1000/4", "pdf_download_status": "skipped"},
                ]
            ).to_parquet(candidates, engine="pyarrow", index=False)

            payload = download_routed_pdfs(
                route_table=routes,
                metadata_table=metadata,
                candidate_table=candidates,
                pdf_dir=pdf_dir,
                report_path=report,
                dry_run=True,
                limit=2,
                skip_candidate_statuses={"download_failed"},
            )

            self.assertEqual(payload["counts"]["tasks_before_candidate_filter"], 5)
            self.assertEqual(payload["counts"]["skipped_by_candidate_status"], 2)
            self.assertEqual(payload["counts"]["tasks"], 2)
        self.assertEqual(payload["counts"]["deferred_by_limit"], 1)

    def test_filter_tasks_by_candidate_status_skips_prior_failures_when_requested(self) -> None:
        tasks = [
            {"doi": "10.1000/failed", "best_pdf_url": "https://example.org/a.pdf"},
            {"doi": "10.1000/fresh", "best_pdf_url": "https://example.org/b.pdf"},
        ]
        candidates = pd.DataFrame(
            [
                {"doi": "10.1000/failed", "pdf_download_status": "download_failed", "pdf_local_path": ""},
                {"doi": "10.1000/fresh", "pdf_download_status": "skipped", "pdf_local_path": ""},
            ]
        )

        kept, skipped = filter_tasks_by_candidate_status(
            tasks,
            candidates,
            skip_candidate_statuses={"download_failed"},
        )

        self.assertEqual([task["doi"] for task in kept], ["10.1000/fresh"])
        self.assertEqual([task["doi"] for task in skipped], ["10.1000/failed"])
        self.assertEqual(skipped[0]["skip_reason"], "candidate_status:download_failed")

    def test_filter_tasks_can_select_retryable_failure_categories(self) -> None:
        tasks = [
            {"doi": "10.1000/retry", "best_pdf_url": "https://europepmc.org/a.pdf"},
            {"doi": "10.1000/nope", "best_pdf_url": "https://example.org/b.pdf"},
        ]
        candidates = pd.DataFrame(
            [
                {
                    "doi": "10.1000/retry",
                    "pdf_download_status": "download_failed",
                    "pdf_download_failure_category": "rate_limited",
                    "pdf_download_failure_categories": "rate_limited",
                },
                {
                    "doi": "10.1000/nope",
                    "pdf_download_status": "download_failed",
                    "pdf_download_failure_category": "forbidden",
                    "pdf_download_failure_categories": "forbidden",
                },
            ]
        )

        kept, skipped = filter_tasks_by_candidate_status(
            tasks,
            candidates,
            skip_candidate_statuses=set(),
            only_failure_categories={"rate_limited", "timeout"},
        )

        self.assertEqual([task["doi"] for task in kept], ["10.1000/retry"])
        self.assertEqual([task["doi"] for task in skipped], ["10.1000/nope"])
        self.assertEqual(skipped[0]["skip_reason"], "failure_category_filter")

    def test_interleave_tasks_by_host_round_robins_primary_pdf_hosts(self) -> None:
        tasks = [
            {"doi": "10.1000/a1", "pdf_url_candidates": "https://a.example/1.pdf"},
            {"doi": "10.1000/a2", "pdf_url_candidates": "https://a.example/2.pdf"},
            {"doi": "10.1000/b1", "pdf_url_candidates": "https://b.example/1.pdf"},
            {"doi": "10.1000/c1", "pdf_url_candidates": "https://c.example/1.pdf"},
            {"doi": "10.1000/b2", "pdf_url_candidates": "https://b.example/2.pdf"},
        ]

        interleaved = interleave_tasks_by_host(tasks)

        self.assertEqual(
            [task["doi"] for task in interleaved],
            ["10.1000/a1", "10.1000/b1", "10.1000/c1", "10.1000/a2", "10.1000/b2"],
        )

    def test_deprioritize_candidates_by_host_moves_problem_host_to_end(self) -> None:
        candidates = [
            "https://europepmc.org/api/getPdf?pmcid=PMC1",
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC1/pdf/article.pdf",
            "https://publisher.example/article.pdf",
        ]

        ordered = deprioritize_candidates_by_host(candidates, {"europepmc.org"})

        self.assertEqual(ordered[-1], "https://europepmc.org/api/getPdf?pmcid=PMC1")
        self.assertEqual(ordered[0], "https://pmc.ncbi.nlm.nih.gov/articles/PMC1/pdf/article.pdf")

    def test_interleave_tasks_can_use_deprioritized_primary_hosts(self) -> None:
        tasks = [
            {
                "doi": "10.1000/europe-first",
                "probable_pdf_url_candidates": (
                    "https://europepmc.org/api/getPdf?pmcid=PMC1 | "
                    "https://publisher.example/article.pdf"
                ),
            },
            {
                "doi": "10.1000/publisher-second",
                "probable_pdf_url_candidates": "https://publisher.example/other.pdf",
            },
            {
                "doi": "10.1000/europe-only",
                "probable_pdf_url_candidates": "https://europepmc.org/api/getPdf?pmcid=PMC2",
            },
        ]

        interleaved = interleave_tasks_by_host(tasks, {"europepmc.org"})

        self.assertEqual([task["doi"] for task in interleaved], ["10.1000/europe-first", "10.1000/europe-only", "10.1000/publisher-second"])

    def test_cooldown_targets_only_hosts_with_transient_errors(self) -> None:
        error = (
            "round 1: https://rate.example/a.pdf -> download_failed: HTTPError: HTTP Error 429: Too Many Requests"
            " || round 1: https://ok.example/b.pdf -> invalid_pdf_content: response_not_pdf"
            " || round 1: https://provider.example/c.pdf -> download_failed: HTTPError: HTTP Error 500:"
            " || round 1: https://slow.example/d.pdf -> download_failed: TimeoutError: timed out"
        )
        result = {
            "failure_categories": "rate_limited|provider_error|timeout|non_pdf_response",
            "error": error,
            "pdf_url_candidates": (
                "https://rate.example/a.pdf|https://ok.example/b.pdf|"
                "https://provider.example/c.pdf|https://slow.example/d.pdf"
            ),
        }
        cooldowns: dict[str, float] = {}

        update_rate_limit_cooldowns(
            result=result,
            cooldown_until_by_host=cooldowns,
            cooldown_sec=10,
        )

        self.assertIn("rate.example", cooldowns)
        self.assertIn("provider.example", cooldowns)
        self.assertIn("slow.example", cooldowns)
        self.assertNotIn("ok.example", cooldowns)
        self.assertEqual(
            transient_failure_hosts_from_error(error),
            ["rate.example", "provider.example", "slow.example"],
        )
        self.assertEqual(rate_limited_hosts_from_error(error), transient_failure_hosts_from_error(error))

    def test_download_pdf_candidates_tries_alternative_host_after_rate_limit(self) -> None:
        class FakeClient:
            max_retries = 0

            def __init__(self) -> None:
                self.calls: list[str] = []

            def get_bytes_once(self, url: str, headers: dict | None = None) -> bytes:
                self.calls.append(url)
                if "a-rate.example" in url:
                    raise HTTPError(url, 429, "Too Many Requests", hdrs=None, fp=None)
                return b"%PDF-1.4\n% test\n%%EOF\n"

        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "paper.pdf"
            cooldowns: dict[str, float] = {}
            client = FakeClient()

            with patch(
                "pipeline.ingest.metadata_utils.pdf_source_identity_result",
                return_value=(True, 1.0, "front_title_match"),
            ):
                status, error, size, selected_url, attempts = download_pdf_candidates(
                    client=client,  # type: ignore[arg-type]
                    pdf_urls=[
                        "https://a-rate.example/paper.pdf",
                        "https://b-ok.example/paper.pdf",
                    ],
                    target_path=target,
                    cooldown_until_by_host=cooldowns,
                    rate_limit_cooldown_sec=60,
                    study_title="Expected paper title",
                )

        self.assertEqual(status, "downloaded")
        self.assertEqual(error, "")
        self.assertGreater(size, 0)
        self.assertEqual(selected_url, "https://b-ok.example/paper.pdf")
        self.assertEqual(client.calls, ["https://a-rate.example/paper.pdf", "https://b-ok.example/paper.pdf"])
        self.assertIn("a-rate.example", cooldowns)
        self.assertIn("https://a-rate.example/paper.pdf", attempts)

    def test_download_pdf_candidates_can_preserve_recovery_candidate_order(self) -> None:
        class FakeClient:
            max_retries = 0

            def __init__(self) -> None:
                self.calls: list[str] = []

            def get_bytes_once(self, url: str, headers: dict | None = None) -> bytes:
                self.calls.append(url)
                return b"%PDF-1.4\n% test\n%%EOF\n"

        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "paper.pdf"
            client = FakeClient()
            with patch(
                "pipeline.ingest.metadata_utils.pdf_source_identity_result",
                return_value=(True, 1.0, "front_title_match"),
            ):
                status, _error, _size, selected_url, _attempts = download_pdf_candidates(
                    client=client,  # type: ignore[arg-type]
                    pdf_urls=[
                        "https://publisher.example/paper.pdf",
                        "https://europepmc.org/api/getPdf?pmcid=PMC123",
                    ],
                    target_path=target,
                    preserve_candidate_order=True,
                    study_title="Expected paper title",
                )

        self.assertEqual(status, "downloaded")
        self.assertEqual(selected_url, "https://publisher.example/paper.pdf")
        self.assertEqual(client.calls, ["https://publisher.example/paper.pdf"])

    def test_classify_download_failure_prioritizes_retryable_categories(self) -> None:
        failure = classify_download_failure(
            "download_failed",
            "HTTPError: HTTP Error 403: Forbidden || HTTPError: HTTP Error 429: Too Many Requests",
        )

        self.assertEqual(failure["failure_category"], "rate_limited")
        self.assertEqual(failure["failure_categories"], "rate_limited|forbidden")
        self.assertTrue(failure["retry_recommended"])

    def test_classify_download_failure_marks_non_retryable_forbidden(self) -> None:
        failure = classify_download_failure(
            "download_failed",
            "HTTPError: HTTP Error 403: Forbidden",
        )

        self.assertEqual(failure["failure_category"], "forbidden")
        self.assertFalse(failure["retry_recommended"])

    def test_classify_download_failure_marks_access_control_as_non_retryable(self) -> None:
        failure = classify_download_failure(
            "download_failed",
            "challenge_or_access_control: Get access; log in, subscribe or purchase",
        )

        self.assertEqual(failure["failure_category"], "access_controlled")
        self.assertFalse(failure["retry_recommended"])


if __name__ == "__main__":
    unittest.main()
