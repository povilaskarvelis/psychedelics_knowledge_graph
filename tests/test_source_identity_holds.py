"""Findings of retracted papers, or extracted from text the paper may not use, are held from the graph.

Curation can find, after extraction, that a paper's abstract or article text
belongs to a different publication. The KG build applies those decisions to
evidence already extracted: a paper the verdict table withholds loses all of
its rows, a row is held when the table does not allow the full text or abstract
it was read from (named by the hashes its task recorded), a paper whose
abstract was cleared without a replacement loses only its abstract-derived
rows, and curated titles replace provider titles. A paper that the retraction
check found retracted loses all of its rows.
"""
import hashlib
import json

import pandas as pd

from pipeline.ingest.materialize_candidate_metadata import read_curated_overrides
from pipeline.kg import build_evidence_tables as b
from pipeline.identity.bindings import verdict_table
from pipeline.kg.update_corpus_graph_status import (
    DEFAULT_DISPOSITION_OVERRIDES, build_updated_corpus, decision_from_audit, load_disposition_overrides,
)


def sha(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


def clinical_row(
    doi: str, access_level: str, title: str = "Psilocybin for major depressive disorder", *, text: str | None = None
) -> dict:
    """A finding row read from ``text``: by default the paper's own file or abstract."""
    text = f"{doi} {access_level}" if text is None else text
    return {
        "study_doi": doi,
        "study_title": title,
        "access_level": access_level,
        "source_artifact_sha256": sha(text) if text and access_level == "article_text" else "",
        "source_abstract_sha256": sha(text) if text and access_level == "abstract_only" else "",
        "domain": "clinical_outcome",
        "compound": "Psilocybin",
        "condition_or_indication": "MDD",
        "paper_assessment_route": "primary_evidence",
    }


def verdict_row(doi: str, target_kind: str, verdict: str, usable: bool, reason: str = "", *, text: str = "") -> dict:
    text = text or f"{doi} {'article_text' if target_kind == 'fulltext' else 'abstract_only'}"
    return {
        "doi": doi, "target_kind": target_kind, "artifact": f"{text}.json" if target_kind == "fulltext" else "",
        "artifact_sha256": sha(text) if target_kind == "fulltext" else "",
        "text_sha256": sha(text) if target_kind == "abstract" else "",
        "verdict": verdict, "usable": usable, "reason": reason or verdict,
    }


def write_curation(tmp_path):
    verdicts = tmp_path / "verdicts.parquet"
    verdict_table([
        verdict_row("10.1000/wrong-text-alias", "record", "hold", False, "hold: The article text belongs to another report."),
        verdict_row("10.1000/wrong-abstract", "fulltext", "verified", True),
        verdict_row("10.1000/merged", "fulltext", "version_of", True),
        verdict_row("10.1000/unverified-text", "fulltext", "unconfirmed", False),
        verdict_row("10.1000/two-texts", "fulltext", "verified", True, text="publisher copy"),
        verdict_row("10.1000/two-texts", "fulltext", "conflict", False, text="another report"),
        verdict_row("10.1000/shared-abstract", "abstract", "not_this_work", False, "not_this_work",
                    text="another paper's abstract"),
    ]).to_parquet(verdicts, index=False)
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
        {"alias_doi": "10.1000/merged", "canonical_doi": "10.1000/kept"},
    ]}))
    return verdicts, metadata, aliases


def test_curated_decisions_resolve_aliases_and_skip_replaced_abstracts(tmp_path):
    verdicts, metadata, _ = write_curation(tmp_path)
    decisions = b.load_curated_paper_decisions(
        verdicts, metadata, {"10.1000/wrong-text-alias": "10.1000/wrong-text", "10.1000/merged": "10.1000/kept"}
    )
    assert decisions["withheld_papers"] == {"10.1000/wrong-text": "hold: The article text belongs to another report."}
    # A merged DOI's usable text counts for the DOI that is kept.
    assert decisions["usable_fulltexts"] == {
        ("10.1000/wrong-abstract", sha("10.1000/wrong-abstract article_text")),
        ("10.1000/kept", sha("10.1000/merged article_text")),
        ("10.1000/two-texts", sha("publisher copy")),
    }
    assert decisions["unusable_abstracts"] == {("10.1000/shared-abstract", sha("another paper's abstract")): "not_this_work"}
    assert decisions["cleared_abstracts"] == {"10.1000/wrong-abstract": "The abstract belongs to another paper."}
    assert decisions["curated_titles"] == {"10.1000/wrong-title": "The registered title"}


def test_build_holds_rows_extracted_from_text_the_paper_may_not_use(tmp_path):
    verdicts, metadata, aliases = write_curation(tmp_path)
    source = tmp_path / "routed_evidence_rows.json"
    source.write_text(json.dumps([
        clinical_row("10.1000/wrong-text", "article_text"),
        clinical_row("10.1000/wrong-abstract", "abstract_only"),
        clinical_row("10.1000/wrong-abstract", "article_text"),
        clinical_row("10.1000/unverified-text", "article_text"),
        clinical_row("10.1000/unverified-text", "abstract_only"),
        clinical_row("10.1000/kept", "article_text", text="10.1000/merged article_text"),
        clinical_row("10.1000/two-texts", "article_text", text="publisher copy"),
        clinical_row("10.1000/two-texts", "article_text", text="another report"),
        clinical_row("10.1000/shared-abstract", "abstract_only", text="another paper's abstract"),
        clinical_row("10.1000/shared-abstract", "abstract_only"),
        clinical_row("10.1000/unrecorded", "article_text", text=""),
        clinical_row("10.1000/replaced-abstract", "abstract_only"),
        clinical_row("10.1000/wrong-title", "abstract_only", title="Curing agents"),
        clinical_row("10.1000/no-results", "abstract_only"),
    ]))
    out_dir = tmp_path / "kg"
    manifest = b.build_tables(
        out_dir=out_dir,
        write_duckdb=False,
        doi_alias_registry_path=aliases,
        identity_verdicts_path=verdicts,
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
    # Rows from text the table does not allow are held; the abstract rows of that paper stay.
    assert findings.loc[findings.study_doi.eq("10.1000/unverified-text"), "access_level"].tolist() == ["abstract_only"]
    # A replaced abstract was re-extracted, and a merged DOI's text counts for the kept DOI.
    assert {"10.1000/replaced-abstract", "10.1000/no-results", "10.1000/wrong-title", "10.1000/kept"} <= set(findings.study_doi)
    # Of two full texts of one paper, only the rows from the allowed one stay; likewise for abstracts.
    assert findings.study_doi.eq("10.1000/two-texts").sum() == 1
    assert findings.study_doi.eq("10.1000/shared-abstract").sum() == 1
    assert "10.1000/unrecorded" not in set(findings.study_doi)
    assert papers.loc[papers.study_doi.eq("10.1000/wrong-title"), "title"].tolist() == ["The registered title"]

    held = audit[audit.normalization_status.eq(b.SOURCE_IDENTITY_HOLD_STATUS)].sort_values("study_doi")
    assert held.study_doi.tolist() == [
        "10.1000/shared-abstract", "10.1000/two-texts", "10.1000/unrecorded",
        "10.1000/unverified-text", "10.1000/wrong-abstract", "10.1000/wrong-text",
    ]
    assert held.normalization_notes.tolist() == [
        "not_this_work",
        "the verdict table does not allow the full text the row was read from",
        "the row does not record the full text it was read from",
        "the verdict table does not allow the full text the row was read from",
        "The abstract belongs to another paper.",
        "hold: The article text belongs to another report.",
    ]
    decisions = manifest["curated_paper_decisions"]
    assert decisions["source_identity_held_rows"] == {"routed_extractions": 6}
    assert decisions["withheld_papers"] == 1
    assert decisions["usable_fulltexts"] == 3
    assert decisions["unusable_abstracts"] == 1
    assert len(decisions["identity_verdicts"]["sha256"]) == 64
    assert len(decisions["paper_metadata_overrides"]["sha256"]) == 64


def test_build_stops_when_decisions_changed_after_the_table_was_installed(tmp_path):
    verdicts, metadata, aliases = write_curation(tmp_path)
    decision_file = tmp_path / "decisions.jsonl"
    decision_file.write_text("{}\n")
    verdicts.with_suffix(".json").write_text(json.dumps({"inputs": {
        "decisions": str(decision_file), "decisions_sha256": "0" * 64,
    }}))
    try:
        b.load_curated_paper_decisions(verdicts, metadata, {})
    except RuntimeError as error:
        assert "apply --install" in str(error)
    else:
        raise AssertionError("a stale verdict table was read")


def test_build_holds_every_row_of_a_retracted_paper(tmp_path):
    _, metadata, aliases = write_curation(tmp_path)
    status = tmp_path / "retraction_status.json"
    status.write_text(json.dumps({
        "schema_version": "retraction_status_v1",
        "last_check": {"scope": {"kind": "evidence_run", "id": "run_1"}, "papers_checked": 3},
        "records": [
            {"doi": "10.1000/retracted-alias", "status": "retracted",
             "reason": "Retracted: Crossref (Retraction Watch): retraction, notice 10.1000/notice, 2021-05-01."},
            {"doi": "10.1000/concern", "status": "expression_of_concern", "reason": "Expression of concern.",
             "sources": {"crossref": {"identity": "doi_match", "notices": [
                 {"source": "crossref", "status": "expression_of_concern", "notice_doi": "10.1000/eoc", "date": "2024-12-03"},
             ]}}},
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
        identity_verdicts_path=None,
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
    # An expression of concern stays in the graph and travels with the paper.
    papers = pd.read_parquet(out_dir / "papers.parquet").set_index("study_doi")
    assert papers.loc["10.1000/concern", list(b.PUBLICATION_NOTICE_COLUMNS)].tolist() == [
        "expression_of_concern", "2024-12-03", "https://doi.org/10.1000/eoc",
    ]
    assert papers.loc["10.1000/conflict", "publication_notice"] == ""


def test_pubmed_only_notice_links_to_pubmed():
    record = {"status": "expression_of_concern", "sources": {
        "pubmed": {"identity": "doi_match", "notices": [
            {"source": "pubmed", "status": "expression_of_concern", "notice_pmid": "40044086"},
        ]},
        # A notice on another paper's record is never shown.
        "crossref": {"identity": "title_conflict", "notices": [
            {"source": "crossref", "status": "expression_of_concern", "notice_doi": "10.1000/other"},
        ]},
    }}
    assert b.publication_notice_fields(record) == {
        "publication_notice": "expression_of_concern",
        "publication_notice_date": "",
        "publication_notice_url": "https://pubmed.ncbi.nlm.nih.gov/40044086/",
    }
    from pipeline.publish.export_evidence_payload import PAPER_FIELDS
    assert set(b.PUBLICATION_NOTICE_COLUMNS) <= set(PAPER_FIELDS)


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
    dispositions = load_disposition_overrides(DEFAULT_DISPOSITION_OVERRIDES)
    # Withheld by its record verdict since 6 November, so no longer a selected paper.
    assert "10.26190/98dq-9g49" not in dispositions
