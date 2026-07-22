import argparse
import json
from pathlib import Path

import pandas as pd

from pipeline.fulltext.build_fulltext_enrichment_worklist import build, load_pmc_outcomes


def test_load_pmc_outcomes_keeps_only_terminal_discovery_handoffs(tmp_path: Path) -> None:
    report = tmp_path / "pmc.json"
    report.write_text(
        json.dumps(
            {
                "records": [
                    {"doi": "10.1000/unavailable", "status": "not_available"},
                    {"doi": "10.1000/failed", "status": "failed"},
                    {"doi": "10.1000/written", "status": "written"},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert load_pmc_outcomes(report) == {
        "10.1000/unavailable": "not_available",
        "10.1000/failed": "failed",
    }


def test_load_pmc_outcomes_later_written_report_clears_prior_failure(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(
        json.dumps({"records": [{"doi": "10.1000/retry", "status": "failed"}]}),
        encoding="utf-8",
    )
    second.write_text(
        json.dumps({"records": [{"doi": "10.1000/retry", "status": "written"}]}),
        encoding="utf-8",
    )

    assert load_pmc_outcomes([first, second]) == {}


def test_build_selects_new_eligible_unprocessed_dois_without_routes(tmp_path: Path) -> None:
    raw = tmp_path / "screening.jsonl"
    raw.write_text(
        "\n".join(
            json.dumps({"doi": doi, "parsed": {"screening_decision": "include_in_scope"}})
            for doi in (
                "10.1000/new",
                "10.1000/oa-landing",
                "10.1000/opaque",
                "10.1000/closed",
                "10.1000/retry",
                "10.1000/terminal",
                "10.1000/unknown-access",
                "10.1000/processed",
                "10.1000/context",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    previous = tmp_path / "previous.parquet"
    pd.DataFrame(
        [
            {
                "doi": "10.1000/processed",
                "retained_for_extraction_candidate": True,
                "retained_extraction_route_count": 1,
                "graph_inclusion_status": "not_reached",
            }
        ]
    ).to_parquet(previous, index=False)
    queue = tmp_path / "queue.json"
    queue.write_text(
        json.dumps(
            {
                "inputs": {"previous_candidate_table": str(previous)},
                "parts": [{"raw_jsonl": str(raw)}],
            }
        ),
        encoding="utf-8",
    )
    screening = tmp_path / "screening.parquet"
    pd.DataFrame(
        [
            {
                "doi": "10.1000/new",
                "screening_decision": "include_in_scope",
                "paper_type_group": "primary",
                "paper_type": "primary",
                "source_family": "primary",
                "model": "test-model",
            },
            {
                "doi": "10.1000/oa-landing",
                "screening_decision": "include_in_scope",
                "paper_type_group": "primary",
                "paper_type": "primary",
                "source_family": "primary",
                "model": "test-model",
            },
            {
                "doi": "10.1000/opaque",
                "screening_decision": "include_in_scope",
                "paper_type_group": "primary",
                "paper_type": "primary",
                "source_family": "primary",
                "model": "test-model",
            },
            {
                "doi": "10.1000/closed",
                "screening_decision": "include_in_scope",
                "paper_type_group": "primary",
                "paper_type": "primary",
                "source_family": "primary",
                "model": "test-model",
            },
            {
                "doi": "10.1000/retry",
                "screening_decision": "include_in_scope",
                "paper_type_group": "primary",
                "paper_type": "primary",
                "source_family": "primary",
                "model": "test-model",
            },
            {
                "doi": "10.1000/terminal",
                "screening_decision": "include_in_scope",
                "paper_type_group": "primary",
                "paper_type": "primary",
                "source_family": "primary",
                "model": "test-model",
            },
            {
                "doi": "10.1000/unknown-access",
                "screening_decision": "include_in_scope",
                "paper_type_group": "primary",
                "paper_type": "primary",
                "source_family": "primary",
                "model": "test-model",
            },
            {
                "doi": "10.1000/processed",
                "screening_decision": "include_in_scope",
                "paper_type_group": "primary",
                "paper_type": "primary",
                "source_family": "primary",
                "model": "test-model",
            },
            {
                "doi": "10.1000/context",
                "screening_decision": "include_in_scope",
                "paper_type_group": "non_primary_publication",
                "paper_type": "commentary_editorial",
                "source_family": "non_primary_publication",
                "non_primary_flags": "commentary_editorial",
                "model": "test-model",
            },
        ]
    ).to_parquet(screening, index=False)
    candidate = tmp_path / "candidate.parquet"
    pd.DataFrame(
        [
            {"doi": "10.1000/new", "study_title": "New paper", "pmcid": "PMC123"},
            {"doi": "10.1000/oa-landing", "study_title": "OA landing paper"},
            {"doi": "10.1000/opaque", "study_title": "Opaque provider PDF"},
            {"doi": "10.1000/closed", "study_title": "Closed paper"},
            {
                "doi": "10.1000/retry",
                "study_title": "Retryable PDF paper",
                "pdf_download_status": "download_failed",
                "pdf_download_failure_category": "timeout",
                "pdf_download_failure_categories": "timeout",
                "pdf_download_retry_recommended": True,
            },
            {
                "doi": "10.1000/terminal",
                "study_title": "Terminal PDF paper",
                "pdf_download_status": "download_failed",
                "pdf_download_failure_category": "forbidden",
                "pdf_download_failure_categories": "forbidden",
                "pdf_download_retry_recommended": False,
            },
            {"doi": "10.1000/unknown-access", "study_title": "Unknown-access paper"},
            {"doi": "10.1000/processed", "study_title": "Old paper"},
            {"doi": "10.1000/context", "study_title": "Commentary"},
        ]
    ).to_parquet(candidate, index=False)
    metadata = tmp_path / "metadata.parquet"
    pd.DataFrame(
        [
            {"doi": "10.1000/new", "pmcid": "", "best_pdf_url": ""},
            {
                "doi": "10.1000/oa-landing",
                "pmcid": "",
                "best_pdf_url": "",
                "open_access_is_oa": "true",
                "open_access_status": "gold",
                "open_access_url": "https://publisher.example/article/oa-landing",
            },
            {
                "doi": "10.1000/opaque",
                "pmcid": "",
                "best_pdf_url": "https://publisher.example/action/showPdf?pii=ABC123",
            },
            {
                "doi": "10.1000/closed",
                "pmcid": "",
                "best_pdf_url": "",
                "open_access_is_oa": "false",
                "open_access_status": "closed",
            },
            {
                "doi": "10.1000/retry",
                "pmcid": "",
                "best_pdf_url": "https://publisher.example/retry.pdf",
            },
            {
                "doi": "10.1000/terminal",
                "pmcid": "",
                "best_pdf_url": "https://publisher.example/terminal.pdf",
            },
            {
                "doi": "10.1000/unknown-access",
                "pmcid": "",
                "best_pdf_url": "",
                "open_access_is_oa": "",
                "open_access_status": "",
            },
        ]
    ).to_parquet(metadata, index=False)
    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    pd.DataFrame({"doi": pd.Series(dtype="string")}).to_parquet(graph_dir / "papers.parquet", index=False)
    graph_pointer = tmp_path / "graph.json"
    graph_pointer.write_text(json.dumps({"kg_dir": str(graph_dir)}), encoding="utf-8")
    manual = tmp_path / "manual.json"
    manual.write_text(json.dumps({"records": []}), encoding="utf-8")
    screening_overrides = tmp_path / "screening_overrides.json"
    screening_overrides.write_text(json.dumps({"overrides": []}), encoding="utf-8")
    access_overrides = tmp_path / "access_overrides.json"
    access_overrides.write_text(json.dumps({"records": []}), encoding="utf-8")
    selected_output = tmp_path / "selected.txt"
    enrichment_output = tmp_path / "enrichment.txt"
    access_metadata_refresh_output = tmp_path / "access_metadata_refresh.txt"
    no_accessible_fulltext_output = tmp_path / "no_accessible_fulltext.txt"
    oa_landing_output = tmp_path / "oa_landing.txt"
    table_output = tmp_path / "worklist.parquet"
    report_output = tmp_path / "report.json"

    report = build(
        argparse.Namespace(
            queue_json=str(queue),
            screening_table=str(screening),
            candidate_table=str(candidate),
            metadata_table=str(metadata),
            previous_candidate_table="",
            active_graph_pointer=str(graph_pointer),
            manual_eligibility_overrides=str(manual),
            screening_decision_overrides=str(screening_overrides),
            manual_fulltext_access_overrides=str(access_overrides),
            pmc_report="",
            fulltext_dir=str(tmp_path / "fulltext"),
            source_identity_audit=str(tmp_path / "identity.json"),
            paper_root=str(tmp_path / "pdfs"),
            output_selected_dois=str(selected_output),
            output_enrichment_dois=str(enrichment_output),
            output_access_metadata_refresh_dois=str(access_metadata_refresh_output),
            output_no_accessible_fulltext_dois=str(no_accessible_fulltext_output),
            output_oa_landing_dois=str(oa_landing_output),
            output_table=str(table_output),
            report_json=str(report_output),
        )
    )

    assert selected_output.read_text(encoding="utf-8") == (
        "10.1000/closed\n10.1000/new\n10.1000/oa-landing\n10.1000/opaque\n"
        "10.1000/retry\n10.1000/terminal\n10.1000/unknown-access\n"
    )
    assert enrichment_output.read_text(encoding="utf-8") == (
        "10.1000/closed\n10.1000/new\n10.1000/oa-landing\n10.1000/opaque\n"
        "10.1000/retry\n10.1000/terminal\n10.1000/unknown-access\n"
    )
    assert access_metadata_refresh_output.read_text(encoding="utf-8") == "10.1000/unknown-access\n"
    assert no_accessible_fulltext_output.read_text(encoding="utf-8") == (
        "10.1000/closed\n10.1000/terminal\n"
    )
    assert oa_landing_output.read_text(encoding="utf-8") == "10.1000/oa-landing\n"
    worklist = pd.read_parquet(table_output)
    assert worklist[["doi", "fulltext_enrichment_action"]].to_dict("records") == [
        {"doi": "10.1000/closed", "fulltext_enrichment_action": "no_accessible_fulltext"},
        {"doi": "10.1000/new", "fulltext_enrichment_action": "fetch_pmc_xml"},
        {"doi": "10.1000/oa-landing", "fulltext_enrichment_action": "resolve_oa_landing_page"},
        {"doi": "10.1000/opaque", "fulltext_enrichment_action": "download_known_pdf"},
        {"doi": "10.1000/retry", "fulltext_enrichment_action": "download_known_pdf"},
        {"doi": "10.1000/terminal", "fulltext_enrichment_action": "no_accessible_fulltext"},
        {"doi": "10.1000/unknown-access", "fulltext_enrichment_action": "refresh_access_metadata"},
    ]
    terminal = worklist.loc[worklist["doi"].eq("10.1000/terminal")].iloc[0]
    assert terminal["pdf_download_status"] == "download_failed"
    assert terminal["pdf_download_failure_category"] == "forbidden"
    assert bool(terminal["pdf_download_terminal_failure"])
    assert terminal["fulltext_enrichment_basis"] == "terminal_pdf_download_failure"
    assert report["schema_version"] == "fulltext_enrichment_worklist_report_v4"
    assert report["counts"]["newly_selected_unprocessed_dois"] == 7
    assert report["counts"]["fulltext_enrichment_needed_dois"] == 7
    assert report["counts"]["fulltext_access_metadata_refresh_dois"] == 1
    assert report["counts"]["fulltext_no_accessible_fulltext_dois"] == 2
    assert report["counts"]["fulltext_oa_landing_dois"] == 1
    assert report["counts"]["fulltext_terminal_pdf_failure_dois"] == 1
    assert report["counts"]["candidate_terminal_pdf_failure_status_dois"] == 1
