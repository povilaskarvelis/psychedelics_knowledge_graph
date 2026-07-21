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
    discovery_output = tmp_path / "discovery.txt"
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
            output_discovery_dois=str(discovery_output),
            output_oa_landing_dois=str(oa_landing_output),
            output_table=str(table_output),
            report_json=str(report_output),
        )
    )

    assert selected_output.read_text(encoding="utf-8") == "10.1000/new\n10.1000/oa-landing\n10.1000/opaque\n"
    assert enrichment_output.read_text(encoding="utf-8") == "10.1000/new\n10.1000/oa-landing\n10.1000/opaque\n"
    assert discovery_output.read_text(encoding="utf-8") == "10.1000/oa-landing\n"
    assert oa_landing_output.read_text(encoding="utf-8") == "10.1000/oa-landing\n"
    worklist = pd.read_parquet(table_output)
    assert worklist[["doi", "fulltext_enrichment_action"]].to_dict("records") == [
        {"doi": "10.1000/new", "fulltext_enrichment_action": "fetch_pmc_xml"},
        {"doi": "10.1000/oa-landing", "fulltext_enrichment_action": "resolve_oa_landing_page"},
        {"doi": "10.1000/opaque", "fulltext_enrichment_action": "download_known_pdf"},
    ]
    assert report["counts"]["newly_selected_unprocessed_dois"] == 3
    assert report["counts"]["fulltext_enrichment_needed_dois"] == 3
    assert report["counts"]["fulltext_oa_landing_dois"] == 1
