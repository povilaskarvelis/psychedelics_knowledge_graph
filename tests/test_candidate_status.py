import tempfile
from pathlib import Path

import pandas as pd

from pipeline.ingest.candidate_status import apply_candidate_updates


def test_apply_candidate_updates_adds_columns_without_dropping_existing_data() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "candidate_papers.parquet"
        pd.DataFrame(
            [
                {"doi": "https://doi.org/10.1000/A", "study_title": "A"},
                {"doi": "10.1000/b", "study_title": "B"},
            ]
        ).to_parquet(path, engine="pyarrow", index=False)
        updates = pd.DataFrame(
            [
                {
                    "doi": "10.1000/a",
                    "publication_stage": "published",
                    "retained_for_extraction_candidate": True,
                    "extraction_route_count": 2,
                }
            ]
        )

        summary = apply_candidate_updates(
            candidate_table=path,
            updates=updates,
            column_defaults={
                "publication_stage": "",
                "retained_for_extraction_candidate": False,
                "extraction_route_count": 0,
            },
        )
        out = pd.read_parquet(path)

    assert summary["matched_candidate_rows"] == 1
    assert summary["updated_candidate_rows"] == 1
    assert list(out["study_title"]) == ["A", "B"]
    assert out.loc[0, "publication_stage"] == "published"
    assert bool(out.loc[0, "retained_for_extraction_candidate"])
    assert int(out.loc[0, "extraction_route_count"]) == 2
    assert out.loc[1, "publication_stage"] == ""


def test_apply_candidate_updates_preserves_existing_integer_dtype_for_subset_update() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "candidate_papers.parquet"
        pd.DataFrame(
            [
                {"doi": "10.1000/a", "local_pdf_count": 1},
                {"doi": "10.1000/b", "local_pdf_count": 2},
            ]
        ).to_parquet(path, engine="pyarrow", index=False)

        summary = apply_candidate_updates(
            candidate_table=path,
            updates=pd.DataFrame([{"doi": "10.1000/a", "local_pdf_count": 0}]),
        )
        out = pd.read_parquet(path)

    assert summary["updated_cells"] == 1
    assert out["local_pdf_count"].dtype == "int64"
    assert out["local_pdf_count"].tolist() == [0, 2]
