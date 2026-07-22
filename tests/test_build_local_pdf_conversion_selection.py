from types import SimpleNamespace

import pandas as pd
import pytest

from pipeline.fulltext.build_local_pdf_conversion_selection import build


def write_pdf(path, body: bytes = b"test") -> None:
    path.write_bytes(b"%PDF-1.7\n" + body)


def args_for(tmp_path, **overrides):
    values = {
        "candidate_table": str(tmp_path / "candidate.parquet"),
        "prescreen_table": str(tmp_path / "prescreen.parquet"),
        "new_worklist": str(tmp_path / "new.parquet"),
        "historical_worklist": str(tmp_path / "historical.parquet"),
        "route_table": "",
        "doi_alias_registry": str(tmp_path / "aliases.json"),
        "output_table": str(tmp_path / "selection.parquet"),
        "output_dois": str(tmp_path / "selection.txt"),
        "report_json": str(tmp_path / "report.json"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_builds_current_deduplicated_selection(tmp_path) -> None:
    pdf = tmp_path / "paper.pdf"
    write_pdf(pdf)
    pd.DataFrame(
        [
            {
                "doi": "10.1000/paper",
                "study_title": "Current paper",
                "prescreen_retained_for_extraction_candidate": True,
                "retained_for_extraction_candidate": True,
                "pipeline_exclusion_stage": "",
                "post_retrieval_decision": "",
            }
        ]
    ).to_parquet(tmp_path / "candidate.parquet", index=False)
    pd.DataFrame(
        [{"doi": "10.1000/paper", "prescreen_decision": "retain"}]
    ).to_parquet(tmp_path / "prescreen.parquet", index=False)
    row = {
        "doi": "10.1000/paper",
        "selected_for_downstream": True,
        "fulltext_enrichment_needed": True,
        "fulltext_enrichment_action": "convert_local_pdf",
        "local_pdf_paths": str(pdf),
    }
    pd.DataFrame([row]).to_parquet(tmp_path / "new.parquet", index=False)
    pd.DataFrame([row]).to_parquet(tmp_path / "historical.parquet", index=False)
    (tmp_path / "aliases.json").write_text('{"records": []}\n')

    report = build(args_for(tmp_path))
    selection = pd.read_parquet(tmp_path / "selection.parquet")

    assert report["counts"]["source_conversion_rows"] == 2
    assert report["counts"]["selected_unique_dois"] == 1
    assert selection["doi"].tolist() == ["10.1000/paper"]
    assert selection.loc[0, "selection_cohorts"] == "new_postscreen|historical_backfill"


def test_reconciles_retained_local_pdf_route_missing_from_worklists(tmp_path) -> None:
    pdf = tmp_path / "legacy-local.pdf"
    write_pdf(pdf)
    doi = "10.1000/legacy-local"
    pd.DataFrame(
        [
            {
                "doi": doi,
                "study_title": "Legacy retained paper with a local PDF",
                "prescreen_retained_for_extraction_candidate": True,
                "retained_for_extraction_candidate": True,
                "pipeline_exclusion_stage": "",
                "post_retrieval_decision": "",
            }
        ]
    ).to_parquet(tmp_path / "candidate.parquet", index=False)
    pd.DataFrame([{"doi": doi, "prescreen_decision": "retain"}]).to_parquet(
        tmp_path / "prescreen.parquet", index=False
    )
    empty_columns = [
        "doi",
        "selected_for_downstream",
        "fulltext_enrichment_needed",
        "fulltext_enrichment_action",
    ]
    pd.DataFrame([], columns=empty_columns).to_parquet(tmp_path / "new.parquet", index=False)
    pd.DataFrame([], columns=empty_columns).to_parquet(tmp_path / "historical.parquet", index=False)
    route_table = tmp_path / "routes.parquet"
    pd.DataFrame(
        [
            {
                "doi": doi,
                "retained_for_extraction_candidate": True,
                "route_action": "convert_local_pdf_then_extract",
                "local_pdf_paths": str(pdf),
            }
        ]
    ).to_parquet(route_table, index=False)
    (tmp_path / "aliases.json").write_text('{"records": []}\n')

    report = build(args_for(tmp_path, route_table=str(route_table)))
    selection = pd.read_parquet(tmp_path / "selection.parquet")

    assert report["counts"]["selected_unique_dois"] == 1
    assert selection.loc[0, "doi"] == doi
    assert selection.loc[0, "selection_cohorts"] == "current_route_reconciliation"


def test_blocks_currently_excluded_candidate(tmp_path) -> None:
    pdf = tmp_path / "paper.pdf"
    write_pdf(pdf)
    pd.DataFrame(
        [
            {
                "doi": "10.1000/excluded",
                "prescreen_retained_for_extraction_candidate": False,
                "retained_for_extraction_candidate": False,
                "pipeline_exclusion_stage": "prescreen",
            }
        ]
    ).to_parquet(tmp_path / "candidate.parquet", index=False)
    pd.DataFrame(
        [{"doi": "10.1000/excluded", "prescreen_decision": "exclude"}]
    ).to_parquet(tmp_path / "prescreen.parquet", index=False)
    row = {
        "doi": "10.1000/excluded",
        "selected_for_downstream": True,
        "fulltext_enrichment_needed": True,
        "fulltext_enrichment_action": "convert_local_pdf",
        "local_pdf_paths": str(pdf),
    }
    pd.DataFrame([row]).to_parquet(tmp_path / "new.parquet", index=False)
    pd.DataFrame([], columns=row).to_parquet(tmp_path / "historical.parquet", index=False)
    (tmp_path / "aliases.json").write_text('{"records": []}\n')

    report = build(args_for(tmp_path))

    assert report["counts"]["selected_unique_dois"] == 0
    assert report["counts"]["blocked_current_prescreen"] == 1


def test_deduplicates_compatible_cross_doi_pdf_identity(tmp_path) -> None:
    pdf = tmp_path / "shared.pdf"
    write_pdf(pdf)
    dois = ["10.1000/one", "10.1000/two"]
    pd.DataFrame(
        [
            {
                "doi": doi,
                "study_title": "The same article title",
                "authors": "A. Author",
                "study_year": "2025",
                "prescreen_retained_for_extraction_candidate": True,
                "retained_for_extraction_candidate": True,
                "pipeline_exclusion_stage": "",
            }
            for doi in dois
        ]
    ).to_parquet(tmp_path / "candidate.parquet", index=False)
    pd.DataFrame(
        [{"doi": doi, "prescreen_decision": "retain"} for doi in dois]
    ).to_parquet(tmp_path / "prescreen.parquet", index=False)
    pd.DataFrame(
        [
            {
                "doi": doi,
                "selected_for_downstream": True,
                "fulltext_enrichment_needed": True,
                "fulltext_enrichment_action": "convert_local_pdf",
                "local_pdf_paths": str(pdf),
            }
            for doi in dois
        ]
    ).to_parquet(tmp_path / "new.parquet", index=False)
    pd.DataFrame([], columns=["doi", "selected_for_downstream", "fulltext_enrichment_needed", "fulltext_enrichment_action"]).to_parquet(
        tmp_path / "historical.parquet", index=False
    )
    (tmp_path / "aliases.json").write_text('{"records": []}\n')

    report = build(args_for(tmp_path))

    assert report["counts"]["selected_unique_dois"] == 1
    assert report["counts"]["pdf_identity_alias_dois_suppressed"] == 1


def test_rejects_incompatible_cross_doi_pdf_hash_conflict(tmp_path) -> None:
    pdf = tmp_path / "shared.pdf"
    write_pdf(pdf)
    dois = ["10.1000/one", "10.1000/two"]
    pd.DataFrame(
        [
            {
                "doi": doi,
                "study_title": title,
                "authors": author,
                "study_year": year,
                "prescreen_retained_for_extraction_candidate": True,
                "retained_for_extraction_candidate": True,
                "pipeline_exclusion_stage": "",
            }
            for doi, title, author, year in (
                (dois[0], "First unrelated paper", "A. Author", "2024"),
                (dois[1], "Second unrelated paper", "B. Author", "2025"),
            )
        ]
    ).to_parquet(tmp_path / "candidate.parquet", index=False)
    pd.DataFrame(
        [{"doi": doi, "prescreen_decision": "retain"} for doi in dois]
    ).to_parquet(tmp_path / "prescreen.parquet", index=False)
    pd.DataFrame(
        [
            {
                "doi": doi,
                "selected_for_downstream": True,
                "fulltext_enrichment_needed": True,
                "fulltext_enrichment_action": "convert_local_pdf",
                "local_pdf_paths": str(pdf),
            }
            for doi in dois
        ]
    ).to_parquet(tmp_path / "new.parquet", index=False)
    pd.DataFrame([], columns=["doi", "selected_for_downstream", "fulltext_enrichment_needed", "fulltext_enrichment_action"]).to_parquet(
        tmp_path / "historical.parquet", index=False
    )
    (tmp_path / "aliases.json").write_text('{"records": []}\n')

    with pytest.raises(ValueError, match="metadata-incompatible"):
        build(args_for(tmp_path))


def test_deduplicates_translated_title_with_matching_bibliographic_identity(tmp_path) -> None:
    pdf = tmp_path / "shared.pdf"
    write_pdf(pdf)
    dois = ["10.1000/portuguese", "10.1000/english"]
    common = {
        "study_year": "2014",
        "study_journal": "Revista Neurociências",
        "prescreen_retained_for_extraction_candidate": True,
        "retained_for_extraction_candidate": True,
        "pipeline_exclusion_stage": "",
    }
    pd.DataFrame(
        [
            {
                **common,
                "doi": dois[0],
                "study_title": "Quantificação neuronal no córtex cerebral",
                "authors": (
                    "Janille Santos Corrêa; Vanessa Almeida Amorin; Denismar Alves Nogueira; "
                    "Evelise Aline Soares; Flávia Da Ré Guerra; Geraldo José Medeiros "
                    "Fernandes; Wagner Costa Rossi; Alessandra Esteves"
                ),
            },
            {
                **common,
                "doi": dois[1],
                "study_title": "Neuronal quantification in the cerebral cortex",
                "authors": (
                    "Janille Santos Corrêa; Vanessa Almeida Amorin; Denismar Alves Nogueira; "
                    "Evelise Aline Soares; Flávia Da Ré Guerra; Geraldo José Medeiros "
                    "Fernandes; W. C. Rossi-Junior; Alessandra Esteves"
                ),
            },
        ]
    ).to_parquet(tmp_path / "candidate.parquet", index=False)
    pd.DataFrame(
        [{"doi": doi, "prescreen_decision": "retain"} for doi in dois]
    ).to_parquet(tmp_path / "prescreen.parquet", index=False)
    pd.DataFrame(
        [
            {
                "doi": doi,
                "selected_for_downstream": True,
                "fulltext_enrichment_needed": True,
                "fulltext_enrichment_action": "convert_local_pdf",
                "local_pdf_paths": str(pdf),
            }
            for doi in dois
        ]
    ).to_parquet(tmp_path / "new.parquet", index=False)
    pd.DataFrame(
        [],
        columns=[
            "doi",
            "selected_for_downstream",
            "fulltext_enrichment_needed",
            "fulltext_enrichment_action",
        ],
    ).to_parquet(tmp_path / "historical.parquet", index=False)
    (tmp_path / "aliases.json").write_text('{"records": []}\n')

    report = build(args_for(tmp_path))

    assert report["counts"]["selected_unique_dois"] == 1
    assert report["counts"]["pdf_identity_alias_dois_suppressed"] == 1
