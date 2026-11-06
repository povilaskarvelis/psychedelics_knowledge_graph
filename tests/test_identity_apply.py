import csv
import json
from pathlib import Path

import pandas as pd

from pipeline.fulltext.convert_pdfs import doi_to_slug
from pipeline.identity.apply import run_apply
from pipeline.identity.bindings import IdentityVerdicts, usable_for
from pipeline.identity.decide import Texts, make_decision, record_decisions
from pipeline.identity.evidence import text_sha256
from tests.identity_fixtures import RECORDS, build_inputs, file_digest, write_gate_audit


EXTRACTED = ("10.1000/good", "10.1000/preprinted", "10.1000/supp", "10.1000/decided", "10.1000/wrong", "10.1000/retitled")


def apply_inputs(tmp_path: Path) -> dict:
    inputs = build_inputs(tmp_path)
    # The current gate accepted the preprint and the supplement.
    gate = write_gate_audit(
        tmp_path, inputs["artifact_dir"], {"10.1000/good", "10.1000/preprinted", "10.1000/supp", "10.1000/retitled"}
    )
    outputs = tmp_path / "base_outputs.jsonl"
    outputs.write_text("".join(json.dumps({"study_doi": doi}) + "\n" for doi in EXTRACTED), encoding="utf-8")
    routes = tmp_path / "routes.parquet"
    pd.DataFrame([{"doi": "10.1000/owner", "route_action": "hold_source_review"}]).to_parquet(routes, index=False)
    return {
        "outputs": [outputs],
        "kg_dir": inputs["kg_dir"],
        "ledger_path": inputs["ledger_path"],
        "artifact_dir": inputs["artifact_dir"],
        "decisions_path": inputs["decisions_path"],
        "work_registry": inputs["work_registry"],
        "route_table": routes,
        "source_identity_audit": gate,
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
    # The current gate accepted both texts; the rule does not.
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
