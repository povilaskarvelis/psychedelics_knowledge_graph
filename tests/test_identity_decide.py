import json
from pathlib import Path

import pytest

from pipeline.fulltext.convert_pdfs import doi_to_slug
from pipeline.identity.__main__ import main
from pipeline.identity.audit import run_audit
from pipeline.identity.decide import Texts, decisions_from_queue, make_decision, record_decisions, registry_additions, registry_pair
from pipeline.identity.register import current_decisions, decision_errors, read_decisions
from pipeline.identity.works import load_work_relations
from tests.identity_fixtures import build_inputs, file_digest


def audit_queue(tmp_path: Path, inputs: dict) -> Path:
    run_audit(**inputs, out_root=tmp_path / "audits", read_pdfs=False, audit_id="test")
    return tmp_path / "audits" / "test"


def texts_for(inputs: dict) -> Texts:
    return Texts(inputs["artifact_dir"], inputs["ledger_path"], inputs["decisions_path"])


def record(inputs: dict, decisions: list[dict], **options) -> dict:
    return record_decisions(
        decisions,
        decisions_path=inputs["decisions_path"],
        work_registry=inputs["work_registry"],
        texts=texts_for(inputs),
        **options,
    )


def test_suggested_versions_are_recorded_once_and_registered(tmp_path: Path) -> None:
    inputs = build_inputs(tmp_path)
    queue = audit_queue(tmp_path, inputs)
    before = inputs["decisions_path"].read_text(encoding="utf-8")

    decisions, counts = decisions_from_queue(
        queue,
        ["check=fulltext", "suggested_verdict=version_of"],
        basis="The preprint's title and authors match the paper.",
        reviewer="curator",
        decided_at="2026-11-02",
    )
    report = record(inputs, decisions)

    assert counts == {"selected": 1}
    assert report["counts"] == {"given": 1, "already_recorded": 0, "superseding": 0, "recorded": 1}
    text = inputs["decisions_path"].read_text(encoding="utf-8")
    assert text.startswith(before)
    added = json.loads(text.splitlines()[-1])
    assert (added["doi"], added["verdict"], added["relation"], added["related_doi"]) == (
        "10.1000/preprinted",
        "version_of",
        "preprint",
        "10.1101/2021.01.01.000001",
    )
    assert added["target"]["sha256"] == file_digest(inputs["artifact_dir"] / f"{doi_to_slug('10.1000/preprinted')}.json")
    assert added["evidence"][0].startswith("audit test, item idq-")
    # The preprint DOI becomes the alias of the article DOI.
    relations = load_work_relations(inputs["work_registry"])
    assert [(r["alias_doi"], r["canonical_doi"], r["relation"]) for r in relations] == [
        ("10.1101/2021.01.01.000001", "10.1000/preprinted", "preprint")
    ]

    registry = inputs["work_registry"].read_text(encoding="utf-8")
    again = record(inputs, decisions)
    assert again["counts"] == {"given": 1, "already_recorded": 1, "superseding": 0, "recorded": 0}
    assert inputs["decisions_path"].read_text(encoding="utf-8") == text
    assert inputs["work_registry"].read_text(encoding="utf-8") == registry


def test_a_decision_on_a_text_no_longer_stored_is_refused_and_nothing_is_written(tmp_path: Path) -> None:
    inputs = build_inputs(tmp_path)
    before = inputs["decisions_path"].read_text(encoding="utf-8")
    good = make_decision(
        doi="10.1000/good",
        target={"kind": "fulltext", "sha256": file_digest(inputs["artifact_dir"] / f"{doi_to_slug('10.1000/good')}.json")},
        verdict="verified",
        basis="b",
        reviewer="r",
    )
    stale = make_decision(
        doi="10.1000/supp", target={"kind": "fulltext", "sha256": "0" * 64}, verdict="wrong_kind", basis="b", reviewer="r"
    )
    no_basis = make_decision(doi="10.1000/wrong", target={"kind": "record"}, verdict="hold", basis="", reviewer="r")

    with pytest.raises(ValueError) as error:
        record(inputs, [good, stale, no_basis])

    message = str(error.value)
    assert "2 decision(s) failed the checks" in message
    assert "no longer stored" in message and "basis is missing" in message
    assert inputs["decisions_path"].read_text(encoding="utf-8") == before


def test_a_later_decision_supersedes_the_current_one_about_the_same_text_or_record(tmp_path: Path) -> None:
    inputs = build_inputs(tmp_path)
    supp = inputs["artifact_dir"] / f"{doi_to_slug('10.1000/supp')}.json"
    first = make_decision(
        doi="10.1000/supp", target={"kind": "fulltext", "sha256": file_digest(supp)}, verdict="wrong_kind", basis="a supplement", reviewer="r"
    )
    hold = make_decision(doi="10.1000/wrong", target={"kind": "record"}, verdict="hold", basis="unclear source", reviewer="r")
    record(inputs, [first, hold])

    second = make_decision(
        doi="10.1000/supp",
        target={"kind": "fulltext", "sha256": file_digest(supp)},
        verdict="verified",
        basis="the main article with its supplement appended",
        reviewer="r",
    )
    second_hold = make_decision(doi="10.1000/wrong", target={"kind": "record"}, verdict="hold", basis="still unclear", reviewer="r")
    report = record(inputs, [second, second_hold])

    assert report["counts"]["superseding"] == 2
    current = {d["decision_id"] for d in current_decisions(read_decisions(inputs["decisions_path"]))}
    assert {second["decision_id"], second_hold["decision_id"]} <= current
    assert not {first["decision_id"], hold["decision_id"]} & current


def test_registry_direction_for_versions() -> None:
    fulltext = {"doi": "10.1000/paper", "related_doi": "10.5281/zenodo.123", "target": {"kind": "fulltext"}}
    abstract = {"doi": "10.1000/member", "related_doi": "10.1000/anchor", "target": {"kind": "abstract"}}
    published_text = {"doi": "10.1101/2020.01.01.1", "related_doi": "10.1000/journal", "target": {"kind": "fulltext"}}

    assert registry_pair(fulltext) == ("10.5281/zenodo.123", "10.1000/paper")
    assert registry_pair(abstract) == ("10.1000/member", "10.1000/anchor")
    assert registry_pair(published_text) == ("10.1101/2020.01.01.1", "10.1000/journal")


def test_command_records_one_decision_and_a_dry_run_writes_nothing(tmp_path: Path, capsys) -> None:
    inputs = build_inputs(tmp_path)
    common = [
        "decide",
        "--decisions", str(inputs["decisions_path"]),
        "--work-registry", str(inputs["work_registry"]),
        "--ledger", str(inputs["ledger_path"]),
        "--artifact-dir", str(inputs["artifact_dir"]),
        "--doi", "10.1000/wrong",
        "--target", '{"kind": "record"}',
        "--verdict", "hold",
        "--basis", "The record's abstract belongs to an esketamine trial.",
        "--reviewer", "curator",
    ]
    before = inputs["decisions_path"].read_text(encoding="utf-8")

    assert main([*common, "--dry-run"]) == 0
    assert inputs["decisions_path"].read_text(encoding="utf-8") == before
    assert main(common) == 0
    assert json.loads(inputs["decisions_path"].read_text(encoding="utf-8").splitlines()[-1])["verdict"] == "hold"
    assert main([*common[:-4], "--basis", "x", "--reviewer", ""]) == 1
    assert "reviewer is missing" in capsys.readouterr().out


def test_a_preprint_without_a_doi_needs_no_related_doi_and_adds_no_registry_record(tmp_path: Path) -> None:
    decision = make_decision(
        doi="10.1000/paper",
        target={"kind": "fulltext", "sha256": "a" * 64},
        verdict="version_of",
        relation="preprint",
        basis="The first page states it is a pre-print copy.",
        reviewer="curator",
    )
    registry = tmp_path / "registry.json"
    registry.write_text('{"records": []}', encoding="utf-8")

    assert decision_errors(decision) == []
    assert registry_additions([decision], registry) == ([], [])
