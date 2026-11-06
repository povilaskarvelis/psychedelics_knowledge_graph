import json
from pathlib import Path

import pytest

from pipeline.identity.migrate import run_migration
from pipeline.identity.register import (
    append_decisions,
    current_decisions,
    decision_errors,
    decision_id,
    read_decisions,
    validate_decisions,
)
from pipeline.identity.works import (
    DEFAULT_WORK_REGISTRY,
    load_work_relations,
    relation_for_legacy_alias_type,
)


def text_decision(**overrides: object) -> dict:
    decision = {
        "decision_id": decision_id("test", "10.1000/paper", "verified"),
        "doi": "10.1000/PAPER",
        "target": {"kind": "fulltext", "sha256": "a" * 64},
        "verdict": "verified",
        "basis": "DOI and title on page one agree with the record.",
        "evidence": ["data/processed/fulltext/articles/10_1000_paper.json"],
        "reviewer": "curator",
        "decided_at": "2026-11-01",
    }
    decision.update(overrides)
    return decision


def test_appended_decisions_keep_earlier_lines_byte_for_byte(tmp_path: Path) -> None:
    path = tmp_path / "decisions.jsonl"
    append_decisions([text_decision()], path)
    first_line = path.read_text(encoding="utf-8")

    second = text_decision(
        decision_id=decision_id("test", "10.1000/paper", "not_this_work"),
        verdict="not_this_work",
        basis="The PDF is the neighbouring article.",
        supersedes=[text_decision()["decision_id"]],
    )
    append_decisions([second], path)

    assert path.read_text(encoding="utf-8").startswith(first_line)
    decisions = read_decisions(path)
    assert decisions[0]["doi"] == "10.1000/paper"
    assert [d["verdict"] for d in current_decisions(decisions)] == ["not_this_work"]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"basis": ""}, "basis is missing"),
        ({"reviewer": ""}, "reviewer is missing"),
        ({"verdict": "hold"}, "not allowed for a fulltext target"),
        ({"target": {"kind": "fulltext"}}, "needs one of"),
        ({"target": {"kind": "fulltext", "sha256": "not-a-hash"}}, "SHA-256"),
        ({"verdict": "version_of"}, "needs a relation"),
        ({"verdict": "version_of", "relation": "repository_copy"}, "needs related_doi"),
        ({"decided_at": ""}, "decided_at is missing"),
        ({"decided_at": "yesterday"}, "ISO date"),
        ({"decision_id": "123"}, "decision_id"),
    ],
)
def test_invalid_decisions_are_refused(overrides: dict, message: str) -> None:
    errors = decision_errors(text_decision(**overrides))

    assert any(message in error for error in errors), errors


def test_record_corrections_need_fields_and_cannot_set_and_clear_one_field() -> None:
    base = {"target": {"kind": "record"}, "verdict": "record_corrected"}

    assert any("needs fields" in e for e in decision_errors(text_decision(**base)))
    assert any(
        "set and cleared" in e
        for e in decision_errors(text_decision(**base, fields={"abstract": "x"}, clear_fields=["abstract"]))
    )
    assert decision_errors(text_decision(**base, clear_fields=["abstract"])) == []


def test_duplicate_ids_and_unknown_supersedes_are_refused() -> None:
    with pytest.raises(ValueError, match="duplicate decision_id"):
        validate_decisions([text_decision(), text_decision()])
    with pytest.raises(ValueError, match="supersedes unknown decision"):
        validate_decisions([text_decision(supersedes=["sid-" + "0" * 20])])


def test_every_relation_name_in_the_work_registry_is_mapped() -> None:
    relations = load_work_relations(DEFAULT_WORK_REGISTRY)

    assert relations
    assert {row["relation"] for row in relations} <= {
        "same_publication", "repository_copy", "preprint", "preprint_or_repository_copy",
        "accepted_manuscript", "version_doi", "translation", "correction_pair", "part_of",
    }
    with pytest.raises(ValueError, match="Unmapped"):
        relation_for_legacy_alias_type("a_new_unreviewed_name")


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def legacy_sources(root: Path) -> dict[str, Path]:
    return {
        "identity_registry": write_json(
            root / "identity_registry.json",
            {
                "reviewed_at": "2026-07-10",
                "records": [
                    {
                        "requested_doi": "10.1000/parse",
                        "observed_document_doi": "10.1000/pars",
                        "relationship_type": "doi_parse_truncation_or_suffix",
                        "identity_action": "ignore_incorrect_extracted_document_doi",
                    },
                    {
                        "requested_doi": "10.1000/published",
                        "observed_document_doi": "10.1101/preprint",
                        "relationship_type": "preprint_repository_version",
                        "identity_action": "accept_related_document_doi",
                    },
                ],
            },
        ),
        "pdf_hash_registry": write_json(
            root / "hash_registry.json",
            {
                "records": [
                    {
                        "requested_doi": "10.1000/hashed",
                        "pdf_sha256": "B" * 64,
                        "document_kind": "single_article_pdf",
                        "review_basis": "Reviewed PDF in Japanese script.",
                        "reviewed_at": "2026-07-21",
                        "source_url": "https://example.org/a.pdf",
                    }
                ]
            },
        ),
        "route_holds": write_json(
            root / "route_overrides.json",
            {
                "records": [
                    {"doi": "10.1000/held", "manual_action": "hold_source_review", "manual_reason": "Title and DOI disagree.",
                     "evidence_artifact": "plan.json", "reviewed_by": "curator"},
                    {"doi": "10.1000/routed", "manual_action": "route_domains", "domains": ["clinical_outcome"]},
                ]
            },
        ),
        "metadata_overrides": write_json(
            root / "metadata_overrides.json",
            {
                "records": [
                    {"doi": "pii: 13030/qt9pj4r3kv", "evidence_basis": "Abstract belongs to another report.",
                     "fields": {}, "clear_fields": ["abstract"]},
                ]
            },
        ),
        "graph_dispositions": write_json(
            root / "graph_dispositions.json",
            {
                "overrides": [
                    {"dois": ["10.1000/edition"], "disposition": "source_not_verified", "reason": "2025 edition retrieved."},
                    {"dois": ["10.1000/failed"], "disposition": "extraction_failed", "reason": "Model failure."},
                ]
            },
        ),
        "pdf_url_corrections": write_json(
            root / "url_corrections.json",
            {
                "records": [
                    {"doi": "10.1000/url", "rejected_url": "https://example.org/other.pdf",
                     "replacement_pdf_url": "https://example.org/right.pdf", "evidence": "The rejected PDF prints another DOI."}
                ]
            },
        ),
    }


def test_migration_maps_each_legacy_file_and_is_idempotent(tmp_path: Path) -> None:
    sources = legacy_sources(tmp_path)
    decisions_path = tmp_path / "decisions.jsonl"

    report = run_migration(decisions_path=decisions_path, sources=sources, work_registry=tmp_path / "none.json")

    assert report["written"] is True
    assert report["by_source"] == {
        "identity_registry": 2, "pdf_hash_registry": 1, "route_holds": 1,
        "metadata_overrides": 1, "graph_dispositions": 1, "pdf_url_corrections": 1,
    }
    by_doi = {d["doi"]: d for d in read_decisions(decisions_path)}
    assert by_doi["10.1000/parse"]["verdict"] == "verified"
    assert by_doi["10.1000/published"]["verdict"] == "version_of"
    assert by_doi["10.1000/published"]["relation"] == "preprint_or_repository_copy"
    assert by_doi["10.1000/published"]["related_doi"] == "10.1101/preprint"
    assert by_doi["10.1000/hashed"]["target"] == {"kind": "fulltext", "pdf_sha256": "b" * 64}
    assert by_doi["10.1000/held"]["verdict"] == "hold"
    assert by_doi["pii: 13030/qt9pj4r3kv"]["clear_fields"] == ["abstract"]
    assert by_doi["10.1000/edition"]["verdict"] == "hold"
    assert by_doi["10.1000/url"]["verdict"] == "not_this_work"
    assert "10.1000/routed" not in by_doi and "10.1000/failed" not in by_doi

    again = run_migration(decisions_path=decisions_path, sources=sources, work_registry=tmp_path / "none.json")
    assert again["in_sync_before"] is True and again["written"] is False


def test_migration_keeps_direct_decisions_and_check_reports_drift(tmp_path: Path) -> None:
    sources = legacy_sources(tmp_path)
    decisions_path = tmp_path / "decisions.jsonl"
    run_migration(decisions_path=decisions_path, sources=sources, work_registry=tmp_path / "none.json")
    append_decisions([text_decision()], decisions_path)
    direct_line = decisions_path.read_text(encoding="utf-8").splitlines()[-1]

    write_json(
        sources["route_holds"],
        {"records": [{"doi": "10.1000/held-later", "manual_action": "hold_source_review",
                      "manual_reason": "New hold.", "reviewed_by": "curator"}]},
    )
    before = decisions_path.read_text(encoding="utf-8")
    check = run_migration(decisions_path=decisions_path, sources=sources, work_registry=tmp_path / "none.json", check=True)
    assert check["in_sync_before"] is False
    assert decisions_path.read_text(encoding="utf-8") == before

    run_migration(decisions_path=decisions_path, sources=sources, work_registry=tmp_path / "none.json")
    lines = decisions_path.read_text(encoding="utf-8").splitlines()
    assert lines[-1] == direct_line
    dois = {d["doi"] for d in read_decisions(decisions_path)}
    assert "10.1000/held-later" in dois and "10.1000/held" not in dois
