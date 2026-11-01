"""Findings of retracted papers, or extracted from another publication's text, are held from the graph.

Curation can find, after extraction, that a paper's abstract or article text
belongs to a different publication. The KG build applies those decisions to
evidence already extracted: a paper marked ``source_not_verified`` loses all of
its rows, a paper whose abstract was cleared without a replacement loses only
its abstract-derived rows, and curated titles replace provider titles. A paper
that the retraction check found retracted loses all of its rows.
"""
import json

import pandas as pd

from pipeline.ingest.materialize_candidate_metadata import read_curated_overrides
from pipeline.kg import build_evidence_tables as b
from pipeline.kg.update_corpus_graph_status import build_updated_corpus, decision_from_audit, load_disposition_overrides


def clinical_row(doi: str, access_level: str, title: str = "Psilocybin for major depressive disorder") -> dict:
    return {
        "study_doi": doi,
        "study_title": title,
        "access_level": access_level,
        "domain": "clinical_outcome",
        "compound": "Psilocybin",
        "condition_or_indication": "MDD",
        "paper_assessment_route": "primary_evidence",
    }


def write_curation(tmp_path):
    dispositions = tmp_path / "graph_inclusion_disposition_overrides.json"
    dispositions.write_text(json.dumps({
        "schema_version": "graph_inclusion_disposition_overrides_v1",
        "overrides": [
            {"dois": ["10.1000/wrong-text-alias"], "disposition": "source_not_verified",
             "reason": "The article text belongs to another report.", "next_action": "Revisit if verified."},
            {"dois": ["10.1000/no-results"], "disposition": "insufficient_source_text",
             "reason": "The text stops before the results.", "next_action": "Revisit if verified."},
        ],
    }))
    metadata = tmp_path / "paper_metadata_overrides.json"
    metadata.write_text(json.dumps({
        "schema_version": "paper_metadata_overrides_v2",
        "records": [
            {"doi": "10.1000/wrong-abstract", "evidence_basis": "The abstract belongs to another paper.",
             "fields": {}, "clear_fields": ["abstract"]},
            {"doi": "10.1000/replaced-abstract", "evidence_basis": "PubMed supplies the abstract.",
             "fields": {"abstract": "The corrected abstract."}, "clear_fields": []},
            {"doi": "10.1000/wrong-title", "evidence_basis": "Crossref supplies the title.",
             "fields": {"study_title": "The registered title"}},
        ],
    }))
    aliases = tmp_path / "doi_alias_registry.json"
    aliases.write_text(json.dumps({"records": [
        {"alias_doi": "10.1000/wrong-text-alias", "canonical_doi": "10.1000/wrong-text"},
    ]}))
    return dispositions, metadata, aliases


def test_curated_decisions_resolve_aliases_and_skip_replaced_abstracts(tmp_path):
    dispositions, metadata, _ = write_curation(tmp_path)
    decisions = b.load_curated_paper_decisions(
        dispositions, metadata, {"10.1000/wrong-text-alias": "10.1000/wrong-text"}
    )
    assert decisions["held_papers"] == {"10.1000/wrong-text": "The article text belongs to another report."}
    assert decisions["cleared_abstracts"] == {"10.1000/wrong-abstract": "The abstract belongs to another paper."}
    assert decisions["curated_titles"] == {"10.1000/wrong-title": "The registered title"}


def test_build_holds_rows_extracted_from_another_publications_text(tmp_path):
    dispositions, metadata, aliases = write_curation(tmp_path)
    source = tmp_path / "routed_evidence_rows.json"
    source.write_text(json.dumps([
        clinical_row("10.1000/wrong-text", "article_text"),
        clinical_row("10.1000/wrong-abstract", "abstract_only"),
        clinical_row("10.1000/wrong-abstract", "article_text"),
        clinical_row("10.1000/replaced-abstract", "abstract_only"),
        clinical_row("10.1000/wrong-title", "abstract_only", title="Curing agents"),
        clinical_row("10.1000/no-results", "abstract_only"),
    ]))
    out_dir = tmp_path / "kg"
    manifest = b.build_tables(
        out_dir=out_dir,
        write_duckdb=False,
        doi_alias_registry_path=aliases,
        graph_disposition_overrides_path=dispositions,
        paper_metadata_overrides_path=metadata,
        retraction_status_path=None,
        graph_sources={"routed_extractions": {
            "path": source, "domain": "routed", "dataset": "routed",
            "default_evidence_type": "primary_evidence", "skip_audit": True,
        }},
    )
    findings = pd.read_parquet(out_dir / "findings.parquet")
    audit = pd.read_parquet(out_dir / "normalization_audit.parquet")
    papers = pd.read_parquet(out_dir / "papers.parquet")

    assert "10.1000/wrong-text" not in set(findings.study_doi)
    assert findings.loc[findings.study_doi.eq("10.1000/wrong-abstract"), "access_level"].tolist() == ["article_text"]
    # A replaced abstract was re-extracted; other final dispositions do not hold rows.
    assert {"10.1000/replaced-abstract", "10.1000/no-results", "10.1000/wrong-title"} <= set(findings.study_doi)
    assert papers.loc[papers.study_doi.eq("10.1000/wrong-title"), "title"].tolist() == ["The registered title"]

    held = audit[audit.normalization_status.eq(b.SOURCE_IDENTITY_HOLD_STATUS)].sort_values("study_doi")
    assert held.study_doi.tolist() == ["10.1000/wrong-abstract", "10.1000/wrong-text"]
    assert held.normalization_notes.tolist() == [
        "The abstract belongs to another paper.",
        "The article text belongs to another report.",
    ]
    decisions = manifest["curated_paper_decisions"]
    assert decisions["source_identity_held_rows"] == {"routed_extractions": 2}
    assert decisions["source_identity_held_paper_ids"] == ["paper:10.1000/wrong-abstract", "paper:10.1000/wrong-text"]
    assert len(decisions["paper_metadata_overrides"]["sha256"]) == 64


def test_build_holds_every_row_of_a_retracted_paper(tmp_path):
    dispositions, metadata, aliases = write_curation(tmp_path)
    status = tmp_path / "retraction_status.json"
    status.write_text(json.dumps({
        "schema_version": "retraction_status_v1",
        "last_check": {"scope": {"kind": "evidence_run", "id": "run_1"}, "papers_checked": 3},
        "records": [
            {"doi": "10.1000/retracted-alias", "status": "retracted",
             "reason": "Retracted: Crossref (Retraction Watch): retraction, notice 10.1000/notice, 2021-05-01."},
            {"doi": "10.1000/concern", "status": "expression_of_concern", "reason": "Expression of concern."},
            {"doi": "10.1000/conflict", "status": "identity_conflict", "reason": "Another paper's record."},
        ],
    }))
    aliases.write_text(json.dumps({"records": [
        {"alias_doi": "10.1000/retracted-alias", "canonical_doi": "10.1000/retracted"},
    ]}))
    source = tmp_path / "routed_evidence_rows.json"
    source.write_text(json.dumps([
        clinical_row("10.1000/retracted", "article_text"),
        clinical_row("10.1000/retracted", "abstract_only"),
        clinical_row("10.1000/concern", "article_text"),
        clinical_row("10.1000/conflict", "article_text"),
    ]))
    out_dir = tmp_path / "kg"
    manifest = b.build_tables(
        out_dir=out_dir,
        write_duckdb=False,
        doi_alias_registry_path=aliases,
        graph_disposition_overrides_path=dispositions,
        paper_metadata_overrides_path=metadata,
        retraction_status_path=status,
        graph_sources={"routed_extractions": {
            "path": source, "domain": "routed", "dataset": "routed",
            "default_evidence_type": "primary_evidence", "skip_audit": True,
        }},
    )
    findings = pd.read_parquet(out_dir / "findings.parquet")
    audit = pd.read_parquet(out_dir / "normalization_audit.parquet")

    # Only a retraction holds rows; a concern or a conflicting registry record does not.
    assert set(findings.study_doi) == {"10.1000/concern", "10.1000/conflict"}
    held = audit[audit.normalization_status.eq(b.RETRACTED_HOLD_STATUS)]
    assert held.study_doi.tolist() == ["10.1000/retracted", "10.1000/retracted"]
    assert held.normalization_notes.str.startswith("Retracted: Crossref").all()
    decisions = manifest["curated_paper_decisions"]
    assert decisions["retracted_papers"] == 1
    assert decisions["retracted_held_rows"] == {"routed_extractions": 2}
    assert decisions["retracted_held_paper_ids"] == ["paper:10.1000/retracted"]
    assert decisions["source_identity_held_rows"] == {"routed_extractions": 0}
    assert decisions["retraction_status"]["last_check"]["papers_checked"] == 3
    # The custom sources here are not the checked evidence run.
    assert decisions["retraction_status"]["check_covers_evidence_run"] is False


def test_fully_held_paper_is_reported_as_source_not_verified():
    decision = decision_from_audit({b.SOURCE_IDENTITY_HOLD_STATUS, "entity_unmapped"})
    assert decision["disposition"] == "source_not_verified"


def test_retracted_paper_is_reported_as_retracted():
    decision = decision_from_audit({b.RETRACTED_HOLD_STATUS, b.SOURCE_IDENTITY_HOLD_STATUS})
    assert decision["disposition"] == "retracted"
    ledger = build_updated_corpus(
        pd.DataFrame([{
            "doi": "10.1000/retracted",
            "prescreen_retained_for_extraction_candidate": True,
            "retained_for_extraction_candidate": True,
            "extraction_route_status": "ready_for_article_text_extraction",
        }]),
        represented_dois=set(),
        audit_statuses={"10.1000/retracted": {b.RETRACTED_HOLD_STATUS}},
        extraction_outcomes={},
        doi_aliases={},
        disposition_overrides={},
        run_id="run",
        release_id="run:release",
        updated_at_utc="2026-11-01T00:00:00+00:00",
    )
    assert ledger.loc[0, "graph_inclusion_disposition"] == "retracted"


def test_curated_identity_decisions_load():
    overrides = read_curated_overrides(b.DEFAULT_PAPER_METADATA_OVERRIDES)
    for doi in ("10.1136/adc.2006.094854", "10.1136/bmj.3.5722.81", "10.1016/0306-3747(94)90197-x"):
        assert overrides[doi]["clear_fields"] == {"abstract"}
    assert overrides["10.1016/0014-2999(93)90482-w"]["fields"]["study_title"].startswith("Ketamine relaxes rabbit femoral arteries")
    dispositions = load_disposition_overrides(b.DEFAULT_GRAPH_DISPOSITION_OVERRIDES)
    assert dispositions["10.26190/98dq-9g49"]["disposition"] == "source_not_verified"
