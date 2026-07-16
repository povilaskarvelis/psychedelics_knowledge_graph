import argparse
import json
from pathlib import Path

import pandas as pd

from pipeline.fulltext.build_fulltext_enrichment_worklist import build


def test_build_selects_new_eligible_unprocessed_dois_without_routes(tmp_path: Path) -> None:
    raw = tmp_path / "screening.jsonl"
    raw.write_text(
        "\n".join(
            json.dumps({"doi": doi, "parsed": {"screening_decision": "include_in_scope"}})
            for doi in ("10.1000/new", "10.1000/processed", "10.1000/context")
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
            {"doi": "10.1000/processed", "study_title": "Old paper"},
            {"doi": "10.1000/context", "study_title": "Commentary"},
        ]
    ).to_parquet(candidate, index=False)
    metadata = tmp_path / "metadata.parquet"
    pd.DataFrame([{"doi": "10.1000/new", "pmcid": ""}]).to_parquet(metadata, index=False)
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
            fulltext_dir=str(tmp_path / "fulltext"),
            source_identity_audit=str(tmp_path / "identity.json"),
            paper_root=str(tmp_path / "pdfs"),
            output_selected_dois=str(selected_output),
            output_enrichment_dois=str(enrichment_output),
            output_table=str(table_output),
            report_json=str(report_output),
        )
    )

    assert selected_output.read_text(encoding="utf-8") == "10.1000/new\n"
    assert enrichment_output.read_text(encoding="utf-8") == "10.1000/new\n"
    worklist = pd.read_parquet(table_output)
    assert worklist[["doi", "fulltext_enrichment_action"]].to_dict("records") == [
        {"doi": "10.1000/new", "fulltext_enrichment_action": "fetch_pmc_xml"}
    ]
    assert report["counts"]["newly_selected_unprocessed_dois"] == 1
    assert report["counts"]["fulltext_enrichment_needed_dois"] == 1
