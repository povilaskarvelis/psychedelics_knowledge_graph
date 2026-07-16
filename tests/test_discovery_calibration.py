import json
from pathlib import Path

import pandas as pd

from pipeline.discovery.calibration import build_calibration_report


def execution_rows() -> list[dict]:
    return [
        {
            "execution_id": "pubmed_core",
            "provider": "pubmed",
            "layer": "core",
            "search_type": "two_block_core",
            "status": "complete",
            "expected_total": 1,
            "retrieved_total": 1,
            "count_request_count": 1,
            "page_count": 1,
        },
        {
            "execution_id": "openalex_core",
            "provider": "openalex",
            "layer": "core",
            "search_type": "two_block_core",
            "status": "complete",
            "expected_total": 1,
            "retrieved_total": 1,
            "count_request_count": 1,
            "page_count": 1,
        },
    ]


def known_source(tmp_path: Path) -> Path:
    path = tmp_path / "candidate_papers.parquet"
    pd.DataFrame(
        [
            {
                "doi": "10.1000/known",
                "pmid": "123",
                "openalex_id": "https://openalex.org/W456",
                "study_title": "Known relevant report",
                "study_year": "2026",
                "publication_date": "2026-02-01",
                "flag_in_known_study_set": True,
            }
        ]
    ).to_parquet(path, index=False)
    return path


def manifest(tmp_path: Path) -> dict:
    exceptions = tmp_path / "exceptions.json"
    exceptions.write_text(
        json.dumps({"schema_version": "known_relevant_exceptions_v1", "exceptions": []}),
        encoding="utf-8",
    )
    return {
        "run_id": "run",
        "providers": ["pubmed", "openalex"],
        "layers": ["core", "scope"],
        "coverage_start_date": "2026-01-01",
        "coverage_end_date": "2026-12-31",
        "calibration": {
            "required_for_promotion": True,
            "known_relevant_source": str(known_source(tmp_path)),
            "known_relevant_flag_column": "flag_in_known_study_set",
            "exceptions_path": str(exceptions),
        },
    }


def hit(provider: str) -> dict:
    return {
        "provider": provider,
        "provider_record_id": "pmid:123" if provider == "pubmed" else "openalex:W456",
        "pmid": "123" if provider == "pubmed" else "",
        "openalex_id": "W456" if provider == "openalex" else "",
        "doi": "10.1000/known",
        "execution_id": f"{provider}_core",
        "layer": "core",
        "search_type": "two_block_core",
    }


def test_calibration_passes_when_known_records_are_retrieved(tmp_path: Path) -> None:
    report, gate = build_calibration_report(
        run_dir=tmp_path,
        manifest=manifest(tmp_path),
        execution_rows=execution_rows(),
        hits=pd.DataFrame([hit("pubmed"), hit("openalex")]),
        retrieval_complete=True,
    )

    assert gate
    assert report["known_relevant_coverage"]["status"] == "passed"
    assert report["known_relevant_coverage"]["expected_provider_record_checks"] == 2
    assert report["known_relevant_coverage"]["found"] == 2
    assert (tmp_path / "search_calibration_groups.csv").exists()
    assert (tmp_path / "known_relevant_coverage.csv").exists()


def test_calibration_blocks_unexplained_known_record_miss(tmp_path: Path) -> None:
    report, gate = build_calibration_report(
        run_dir=tmp_path,
        manifest=manifest(tmp_path),
        execution_rows=execution_rows(),
        hits=pd.DataFrame([hit("pubmed")]),
        retrieval_complete=True,
    )

    assert not gate
    assert report["known_relevant_coverage"]["status"] == "failed"
    assert report["known_relevant_coverage"]["unexplained_misses"] == 1


def test_documented_provider_exception_can_satisfy_calibration_gate(tmp_path: Path) -> None:
    payload = manifest(tmp_path)
    Path(payload["calibration"]["exceptions_path"]).write_text(
        json.dumps(
            {
                "schema_version": "known_relevant_exceptions_v1",
                "exceptions": [
                    {
                        "record_id": "doi:10.1000/known",
                        "provider": "openalex",
                        "status": "accepted",
                        "reason": "The record is not indexed by this provider.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report, gate = build_calibration_report(
        run_dir=tmp_path,
        manifest=payload,
        execution_rows=execution_rows(),
        hits=pd.DataFrame([hit("pubmed")]),
        retrieval_complete=True,
    )

    assert gate
    assert report["known_relevant_coverage"]["status"] == "passed"
    assert report["known_relevant_coverage"]["explained_misses"] == 1


def test_known_record_check_can_be_disabled_without_disabling_yield_report(tmp_path: Path) -> None:
    payload = manifest(tmp_path)
    payload["calibration"] = {
        "known_relevant_check_enabled": False,
        "required_for_promotion": False,
        "disabled_reason": "Not used for this expanding corpus.",
    }
    report, gate = build_calibration_report(
        run_dir=tmp_path,
        manifest=payload,
        execution_rows=execution_rows(),
        hits=pd.DataFrame([hit("pubmed")]),
        retrieval_complete=True,
    )

    assert gate
    assert report["known_relevant_coverage"]["status"] == "disabled_by_operator"
    assert report["query_group_count"] == 2
    assert (tmp_path / "search_calibration_groups.csv").exists()
