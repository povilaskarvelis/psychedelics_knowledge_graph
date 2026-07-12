import tempfile
from pathlib import Path

import pandas as pd

from pipeline.validate.evaluate_deterministic_projection import compare


def write_tables(directory: Path, findings: list[dict], audit: list[dict]) -> None:
    directory.mkdir(parents=True)
    pd.DataFrame(findings).to_parquet(directory / "findings.parquet", index=False)
    pd.DataFrame(findings).to_parquet(directory / "evidence_edges.parquet", index=False)
    pd.DataFrame(audit).to_parquet(directory / "normalization_audit.parquet", index=False)


def test_compare_counts_recovered_non_atomic_findings_without_claiming_centrality() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        baseline = root / "baseline"
        candidate = root / "candidate"
        write_tables(
            baseline,
            [],
            [{"study_doi": "10.1/example", "normalization_status": "compound_combo_not_graphable"}],
        )
        write_tables(
            candidate,
            [
                {
                    "study_doi": "10.1/example",
                    "graph_subject_kind": "compound_combination",
                    "proposition_group_id": "p1",
                    "direction_consistency": "consistent_or_not_applicable",
                    "graph_admission_status": "main_graph",
                }
            ],
            [],
        )

        report, papers = compare(baseline, candidate)

    assert report["counts"]["finding_delta"] == 1
    assert report["counts"]["papers_recovered_from_zero"] == 1
    assert report["counts"]["candidate_non_atomic_findings"] == 1
    assert papers.iloc[0]["representation_change"] == "recovered_from_zero"
