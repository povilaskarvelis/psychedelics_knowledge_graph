import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from pipeline.extract.build_extraction_routes import fulltext_status_for_doi
from pipeline.fulltext.convert_pdfs import doi_to_slug
from pipeline.identity.bindings import carried_rows
from pipeline.identity.gate import (
    GATE_ARTIFACT_CHANGED,
    GATE_IDENTITY_UNVERIFIED,
    GATE_NOT_AUDITED,
    GATE_VERIFIED,
    IdentityGate,
)
from tests.identity_fixtures import write_gate_table


def artifact_at(root: Path, name: str = "article.json") -> Path:
    path = root / name
    path.write_text('{"best_char_count": 100}\n', encoding="utf-8")
    return path


def make_newer_than(path: Path, reference: Path) -> None:
    newer = reference.stat().st_mtime_ns + 1_000_000_000
    os.utime(path, ns=(newer, newer))


def row(doi: str, path: Path, usable: bool = True, **extra: object) -> dict:
    return {"requested_doi": doi, "artifact_path": str(path.resolve()), "identity_verified": usable, **extra}


def test_gate_requires_the_doi_and_the_text_of_one_row(tmp_path: Path) -> None:
    artifact = artifact_at(tmp_path)
    other = artifact_at(tmp_path, "other.json")
    gate = IdentityGate(write_gate_table(tmp_path, [row("10.1234/example", artifact)]))

    assert gate.is_verified("10.1234/example", artifact)
    assert not gate.is_verified("10.1234/other", artifact)
    assert gate.status("10.1234/example", other) == GATE_NOT_AUDITED


def test_a_text_the_table_does_not_allow_is_rejected_with_its_reason(tmp_path: Path) -> None:
    artifact = artifact_at(tmp_path)
    gate = IdentityGate(write_gate_table(tmp_path, [row("10.1234/example", artifact, usable=False)]))

    assert gate.status("10.1234/example", artifact) == GATE_IDENTITY_UNVERIFIED


def test_a_changed_text_is_rejected_alone(tmp_path: Path) -> None:
    first, second = artifact_at(tmp_path, "first.json"), artifact_at(tmp_path, "second.json")
    table = write_gate_table(tmp_path, [row("10.1234/first", first), row("10.1234/second", second)])
    gate = IdentityGate(table)
    first.write_text('{"best_char_count": 999}\n', encoding="utf-8")
    make_newer_than(first, table)

    assert gate.status("10.1234/first", first) == GATE_ARTIFACT_CHANGED
    assert gate.status("10.1234/second", second) == GATE_VERIFIED
    assert gate.rejection_counts() == {GATE_ARTIFACT_CHANGED: 1}


def test_a_newer_file_time_with_the_same_content_stays_verified(tmp_path: Path) -> None:
    artifact = artifact_at(tmp_path)
    table = write_gate_table(tmp_path, [row("10.1234/example", artifact)])
    make_newer_than(artifact, table)

    assert IdentityGate(table).is_verified("10.1234/example", artifact)


@pytest.mark.parametrize("changed", ["decisions", "work_registry"])
def test_the_gate_stops_when_the_inputs_of_the_table_changed(tmp_path: Path, changed: str) -> None:
    table = write_gate_table(tmp_path, [row("10.1234/example", artifact_at(tmp_path))])
    inputs: dict[str, str] = {}
    paths = {}
    for name in ("decisions", "work_registry"):
        paths[name] = tmp_path / f"{name}.txt"
        paths[name].write_text("before\n", encoding="utf-8")
        inputs[name] = str(paths[name])
        inputs[f"{name}_sha256"] = hashlib.sha256(b"before\n").hexdigest()
    table.with_suffix(".json").write_text(json.dumps({"inputs": inputs}), encoding="utf-8")
    IdentityGate(table)

    paths[changed].write_text("after\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="apply --install"):
        IdentityGate(table)


def text_row(doi: str, usable: bool = True, relation: str = "") -> dict:
    return {"doi": doi, "artifact": f"{doi_to_slug(doi)}.json", "usable": usable, "relation": relation}


def test_a_kept_doi_without_text_reads_the_text_of_the_doi_merged_into_it() -> None:
    rows, _ = carried_rows(
        [text_row("10.17615/copy", relation="repository_copy")],
        {"10.17615/copy": "10.1000/journal"},
        {frozenset({"10.17615/copy", "10.1000/journal"}): "repository_copy"},
    )

    assert [(item["doi"], item["artifact"], item["carried_from"]) for item in rows] == [
        ("10.1000/journal", f"{doi_to_slug('10.17615/copy')}.json", "10.17615/copy")
    ]


def test_a_preprint_is_not_carried_to_the_published_paper() -> None:
    by_prefix, _ = carried_rows([text_row("10.1101/2024.01.01.1")], {"10.1101/2024.01.01.1": "10.1000/journal"}, {})
    by_relation, _ = carried_rows(
        [text_row("10.5281/deposit")],
        {"10.5281/deposit": "10.1000/journal"},
        {frozenset({"10.5281/deposit", "10.1000/journal"}): "preprint"},
    )

    assert by_prefix == [] and by_relation == []


def test_a_kept_doi_with_its_own_usable_text_keeps_it() -> None:
    rows, _ = carried_rows(
        [text_row("10.1000/journal"), text_row("10.17615/copy")],
        {"10.17615/copy": "10.1000/journal"},
        {},
    )

    assert rows == []


def test_the_route_uses_a_carried_text_when_the_paper_has_none(tmp_path: Path) -> None:
    articles = tmp_path / "articles"
    articles.mkdir()
    alias, kept = "10.17615/copy", "10.1000/journal"
    carried = articles / f"{doi_to_slug(alias)}.json"
    carried.write_text(
        json.dumps(
            {
                "best_char_count": 2000,
                "best_backend": "pdftotext",
                "extractions": [{"backend": "pdftotext", "metadata": {}, "text": "body " * 400}],
            }
        ),
        encoding="utf-8",
    )
    table = write_gate_table(tmp_path, [row(kept, carried, carried_from=alias)])

    status = fulltext_status_for_doi(kept, tmp_path, source_identity_gate=IdentityGate(table))

    assert status["has_converted_full_text"]
    assert status["fulltext_artifact_paths"] == str(carried)
    assert status["fulltext_identity_status"] == GATE_VERIFIED


def test_a_record_decision_withholds_the_paper(tmp_path: Path) -> None:
    table = write_gate_table(tmp_path, [row("10.1234/kept", artifact_at(tmp_path))])
    frame = pd.read_parquet(table)
    frame = pd.concat(
        [frame, pd.DataFrame([{"doi": "10.1234/held", "target_kind": "record", "artifact": "", "artifact_sha256": "", "usable": False, "reason": "hold: unresolved", "carried_from": ""}])]
    )
    frame.to_parquet(table, index=False)
    gate = IdentityGate(table)

    assert gate.withheld("10.1234/held") == "hold: unresolved"
    assert gate.withheld("10.1234/kept") == ""
