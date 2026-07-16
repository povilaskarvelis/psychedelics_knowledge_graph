from pathlib import Path
import tempfile

import pandas as pd

from pipeline.fulltext.convert_pdfs import doi_to_slug
from pipeline.fulltext.convert_routed_local_pdfs import conversion_rows_from_selection, selected_pdf_rows


def test_conversion_rows_from_postscreen_selection() -> None:
    selection = pd.DataFrame(
        [
            {
                "doi": "10.1000/local",
                "selected_for_downstream": True,
                "fulltext_enrichment_needed": True,
                "fulltext_enrichment_action": "convert_local_pdf",
            },
            {
                "doi": "10.1000/pmc",
                "selected_for_downstream": True,
                "fulltext_enrichment_needed": True,
                "fulltext_enrichment_action": "fetch_pmc_xml",
            },
        ]
    )

    rows = conversion_rows_from_selection(selection)

    assert rows["doi"].tolist() == ["10.1000/local"]
    assert rows["retained_for_extraction_candidate"].all()
    assert rows["route_action"].eq("convert_local_pdf_then_extract").all()


def test_selected_pdf_rows_reads_route_table_and_targets_articles_dir() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        doi = "10.1000/local"
        pdf_path = root / "pdfs" / "paper.pdf"
        pdf_path.parent.mkdir(parents=True)
        pdf_path.write_bytes(b"%PDF-1.7\n")
        out_dir = root / "fulltext" / "articles"
        routes = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "retained_for_extraction_candidate": True,
                    "route_action": "convert_local_pdf_then_extract",
                    "study_title": "Route title",
                    "study_year": "2024",
                    "local_pdf_paths": str(pdf_path),
                },
                {
                    "doi": "10.1000/abstract",
                    "retained_for_extraction_candidate": True,
                    "route_action": "extract_from_abstract_only",
                    "local_pdf_paths": str(pdf_path),
                },
            ]
        )
        metadata = pd.DataFrame([{"doi": doi, "openalex_id": "W1"}])

        rows, skipped = selected_pdf_rows(
            routes_df=routes,
            metadata_df=metadata,
            out_dir=out_dir,
            doi_filter=None,
            route_action="convert_local_pdf_then_extract",
            only_missing_artifacts=True,
        )

    assert skipped == {}
    assert len(rows) == 1
    assert rows[0]["study_doi"] == doi
    assert rows[0]["artifact_path"] == out_dir / f"{doi_to_slug(doi)}.json"
    assert rows[0]["pdf_path"] == pdf_path
