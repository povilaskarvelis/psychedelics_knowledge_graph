import csv
import json
from pathlib import Path

import pandas as pd

from pipeline.fulltext.convert_pdfs import doi_to_slug
from pipeline.identity.apply import curated_changes, refresh_fulltext_rows, run_apply, write_curated_changes
from pipeline.identity.bindings import IdentityVerdicts, usable_for
from pipeline.identity.decide import Texts, make_decision, record_decisions
from pipeline.identity.evidence import text_sha256
from tests.identity_fixtures import RECORDS, build_inputs, file_digest


EXTRACTED = ("10.1000/good", "10.1000/preprinted", "10.1000/supp", "10.1000/decided", "10.1000/wrong", "10.1000/retitled")


def apply_inputs(tmp_path: Path) -> dict:
    inputs = build_inputs(tmp_path)
    overrides = tmp_path / "metadata_overrides.json"
    overrides.write_text(json.dumps({"records": []}), encoding="utf-8")
    outputs = tmp_path / "base_outputs.jsonl"
    outputs.write_text("".join(json.dumps({"study_doi": doi}) + "\n" for doi in EXTRACTED), encoding="utf-8")
    routes = tmp_path / "routes.parquet"
    # The release read the full text of the preprint and the supplement.
    pd.DataFrame(
        [{"doi": "10.1000/owner", "route_action": "hold_source_review", "manual_fulltext_access_action": ""}]
        + [
            {"doi": doi, "route_action": "extract_from_full_text", "manual_fulltext_access_action": ""}
            for doi in ("10.1000/good", "10.1000/preprinted", "10.1000/supp", "10.1000/retitled")
        ]
    ).to_parquet(routes, index=False)
    return {
        "outputs": [outputs],
        "kg_dir": inputs["kg_dir"],
        "ledger_path": inputs["ledger_path"],
        "artifact_dir": inputs["artifact_dir"],
        "decisions_path": inputs["decisions_path"],
        "work_registry": inputs["work_registry"],
        "route_table": routes,
        "metadata_overrides": overrides,
    }


def changes_of(update_dir: Path) -> dict[str, dict]:
    with (update_dir / "changes.csv").open(encoding="utf-8") as handle:
        return {row["doi"]: row for row in csv.DictReader(handle)}


def decide(inputs: dict, decisions: list[dict]) -> None:
    record_decisions(
        decisions,
        decisions_path=inputs["decisions_path"],
        work_registry=inputs["work_registry"],
        texts=Texts(inputs["artifact_dir"], inputs["ledger_path"], inputs["decisions_path"]),
    )


def test_apply_lists_papers_whose_text_changes_and_writes_only_its_folder(tmp_path: Path) -> None:
    inputs = apply_inputs(tmp_path)
    before = {path: file_digest(path) for path in tmp_path.rglob("*") if path.is_file()}

    summary = run_apply(
        **inputs,
        update_id="first",
        out_root=tmp_path / "updates",
        verdicts_path=tmp_path / "active" / "verdicts.parquet",
        read_pdfs=False,
    )

    update_dir = tmp_path / "updates" / "first"
    after = {path: file_digest(path) for path in tmp_path.rglob("*") if path.is_file()}
    assert set(after) - set(before) == {
        update_dir / name for name in ("verdicts.parquet", "changes.csv", "scope_dois.txt", "apply_summary.json")
    }
    assert all(after[path] == digest for path, digest in before.items())

    changes = changes_of(update_dir)
    # The release read both texts; the rule does not allow them.
    assert {doi: (c["action"], c["text_now"], c["text_after"]) for doi, c in changes.items()} == {
        "10.1000/preprinted": ("re-extract", "fulltext", "abstract"),
        "10.1000/supp": ("re-extract", "fulltext", "abstract"),
    }
    assert changes["10.1000/preprinted"]["reason"] == "full text not usable: conflict: title_matches_identifier_differs"
    assert changes["10.1000/preprinted"]["release_findings_main"] == "2"
    assert (update_dir / "scope_dois.txt").read_text(encoding="utf-8").split() == ["10.1000/preprinted", "10.1000/supp"]
    assert summary["changes"] == {"fulltext_to_abstract": 2, "re-extract": 2}
    assert summary["papers_extracted"] == len(EXTRACTED)

    table = IdentityVerdicts(pd.read_parquet(update_dir / "verdicts.parquet"))
    decided = table.fulltext("10.1000/decided", inputs["artifact_dir"] / f"{doi_to_slug('10.1000/decided')}.json")
    assert (decided["verdict"], decided["computed_verdict"], decided["usable"]) == ("not_this_work", "conflict", False)
    retitled = table.fulltext("10.1000/retitled", inputs["artifact_dir"] / f"{doi_to_slug('10.1000/retitled')}.json")
    assert (retitled["verdict"], retitled["usable"]) == ("verified", True)


def test_decisions_change_the_scope_and_install_makes_the_table_active(tmp_path: Path) -> None:
    inputs = apply_inputs(tmp_path)
    preprint = inputs["artifact_dir"] / f"{doi_to_slug('10.1000/preprinted')}.json"
    supp = inputs["artifact_dir"] / f"{doi_to_slug('10.1000/supp')}.json"
    abstracts = {doi: abstract for doi, _title, abstract in RECORDS}
    decide(
        inputs,
        [
            make_decision(
                doi="10.1000/preprinted",
                target={"kind": "fulltext", "sha256": file_digest(preprint)},
                verdict="version_of",
                relation="preprint",
                related_doi="10.1101/2021.01.01.000001",
                basis="The preprint of the paper.",
                reviewer="curator",
            ),
            make_decision(
                doi="10.1000/supp",
                target={"kind": "fulltext", "sha256": file_digest(supp)},
                verdict="verified",
                basis="The article with its supplement appended.",
                reviewer="curator",
            ),
            make_decision(
                doi="10.1000/decided",
                target={"kind": "abstract", "sha256": text_sha256(abstracts["10.1000/decided"])},
                verdict="not_this_work",
                basis="The abstract describes another study.",
                reviewer="curator",
            ),
            make_decision(
                doi="10.1000/wrong", target={"kind": "record"}, verdict="hold", basis="Source unresolved.", reviewer="curator"
            ),
        ],
    )
    active = tmp_path / "active" / "verdicts.parquet"
    options = {**inputs, "out_root": tmp_path / "updates", "verdicts_path": active, "read_pdfs": False}

    planned = run_apply(**options, update_id="plan")
    assert not active.exists()
    installed = run_apply(**options, update_id="install", install=True)

    changes = changes_of(tmp_path / "updates" / "plan")
    assert {doi: c["action"] for doi, c in changes.items()} == {
        "10.1000/preprinted": "re-extract",
        "10.1000/decided": "remove",
        "10.1000/wrong": "remove",
    }
    assert changes["10.1000/wrong"]["reason"] == "withheld: hold: Source unresolved."
    assert changes["10.1000/decided"]["reason"] == "abstract not usable: not_this_work"
    assert not planned["installed"] and installed["installed"]
    assert active.is_file() and json.loads(active.with_suffix(".json").read_text(encoding="utf-8"))["update_id"] == "install"
    assert IdentityVerdicts(active).withheld("10.1000/wrong")["verdict"] == "hold"


def test_a_published_paper_does_not_read_a_preprint() -> None:
    published, preprint = "10.1000/journal", "10.1101/2020.01.01.1"
    assert usable_for("fulltext", "verified", "", published) == (True, "verified")
    assert usable_for("fulltext", "version_of", "preprint", published)[0] is False
    assert usable_for("fulltext", "version_of", "preprint_or_repository_copy", published)[0] is False
    assert usable_for("fulltext", "version_of", "accepted_manuscript", published)[0] is True
    assert usable_for("fulltext", "version_of", "repository_copy", published)[0] is True
    assert usable_for("abstract", "version_of", "preprint", published)[0] is True
    assert usable_for("fulltext", "version_of", "preprint_or_repository_copy", preprint)[0] is True
    for verdict in ("unconfirmed", "conflict", "wrong_kind", "not_this_work"):
        assert usable_for("fulltext", verdict, "", published) == (False, verdict)


def test_a_newly_written_text_gets_a_new_row_and_other_rows_stay(tmp_path: Path) -> None:
    inputs = apply_inputs(tmp_path)
    run_apply(update_id="u", out_root=tmp_path / "updates", install=True, verdicts_path=tmp_path / "v.parquet", **inputs)
    before = pd.read_parquet(tmp_path / "v.parquet")
    good = inputs["artifact_dir"] / f"{doi_to_slug('10.1000/good')}.json"
    supp = inputs["artifact_dir"] / f"{doi_to_slug('10.1000/supp')}.json"

    unusable = refresh_fulltext_rows(
        [good, supp],
        artifact_dir=inputs["artifact_dir"],
        verdicts_path=tmp_path / "v.parquet",
        ledger_path=inputs["ledger_path"],
        decisions_path=inputs["decisions_path"],
        work_registry=inputs["work_registry"],
    )

    after = pd.read_parquet(tmp_path / "v.parquet")
    assert unusable == [str(supp.resolve())]
    assert len(after) == len(before)
    assert after.equals(before)


def test_record_corrections_and_unusable_abstracts_reach_the_curated_overrides(tmp_path: Path) -> None:
    decisions = {
        "10.1000/titled": [
            {"decision_id": "sid-1", "basis": "title", "verdict": "record_corrected", "target": {"kind": "record"}, "fields": {"study_title": "Right"}},
        ],
        "10.1000/wrong": [
            {"decision_id": "sid-2", "basis": "other paper", "verdict": "not_this_work", "target": {"kind": "abstract", "sha256": text_sha256("Another paper.")}},
        ],
        "10.1000/replaced": [
            {"decision_id": "sid-3", "basis": "old", "verdict": "wrong_kind", "target": {"kind": "abstract", "sha256": text_sha256("Old text.")}},
        ],
        "10.1000/legacy": [
            {"decision_id": "sid-4", "basis": "file", "verdict": "record_corrected", "target": {"kind": "record"}, "fields": {"study_title": "Kept"}, "origin": {"source": "metadata_overrides"}},
        ],
    }
    ledger = pd.DataFrame(
        {"abstract": ["", "Another paper.", "The right text.", ""]},
        index=["10.1000/titled", "10.1000/wrong", "10.1000/replaced", "10.1000/legacy"],
    )
    overrides = tmp_path / "overrides.json"
    existing = {"doi": "10.1000/legacy", "evidence_basis": "file", "fields": {"study_title": "Kept"}}
    overrides.write_text(json.dumps({"records": [existing]}), encoding="utf-8")

    changes = curated_changes(decisions, ledger)

    assert set(changes) == {"10.1000/titled", "10.1000/wrong"}
    assert write_curated_changes(changes, overrides) == 2
    records = {record["doi"]: record for record in json.loads(overrides.read_text(encoding="utf-8"))["records"]}
    assert records["10.1000/legacy"] == existing
    assert records["10.1000/titled"]["fields"] == {"study_title": "Right"}
    assert records["10.1000/titled"]["source_decision"] == "sid-1"
    assert records["10.1000/wrong"]["clear_fields"] == ["abstract"]
    # A second run changes nothing.
    assert write_curated_changes(changes, overrides) == 0


def test_an_access_override_keeps_a_paper_on_its_abstract(tmp_path: Path) -> None:
    inputs = apply_inputs(tmp_path)
    routes = pd.read_parquet(inputs["route_table"])
    routes.loc[routes["doi"] == "10.1000/good", ["route_action", "manual_fulltext_access_action"]] = [
        "extract_from_abstract_only",
        "abstract_only",
    ]
    routes.to_parquet(inputs["route_table"], index=False)

    run_apply(update_id="u", out_root=tmp_path / "updates", **inputs)

    assert "10.1000/good" not in changes_of(tmp_path / "updates" / "u")
