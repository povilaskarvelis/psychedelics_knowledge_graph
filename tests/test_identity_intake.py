"""Every path that stores a full text checks it with verify() and records it in the verdict table."""
import json
from pathlib import Path

from pipeline.fulltext.convert_pdfs import doi_to_slug, should_write_artifact
from pipeline.identity.apply import run_apply
from pipeline.identity.intake import KEPT_USABLE_TEXT, NO_EXTRACTION, STORED_FOR_REVIEW, STORED_VERIFIED, FulltextIntake
from tests.identity_fixtures import build_inputs


def artifact(doi: str, text: str, backend: str = "test") -> dict:
    return {
        "study_doi": doi,
        "best_backend": backend,
        "extractions": [{"status": "ok", "backend": "test", "text": text, "metadata": {"format": "markdown"}}],
    }


def intake_for(tmp_path: Path) -> tuple[FulltextIntake, Path]:
    inputs = build_inputs(tmp_path)
    verdicts = tmp_path / "verdicts.parquet"
    outputs = tmp_path / "outputs.jsonl"
    outputs.write_text("", encoding="utf-8")
    (tmp_path / "overrides.json").write_text(json.dumps({"records": []}), encoding="utf-8")
    run_apply(
        outputs=[outputs], kg_dir=inputs["kg_dir"], ledger_path=inputs["ledger_path"], artifact_dir=inputs["artifact_dir"],
        decisions_path=inputs["decisions_path"], work_registry=inputs["work_registry"], update_id="u",
        out_root=tmp_path / "updates", install=True, verdicts_path=verdicts, read_pdfs=False,
        metadata_overrides=tmp_path / "overrides.json", discovery_runs=inputs["discovery_runs"],
        provider_records_dir=inputs["provider_records_dir"],
    )
    intake = FulltextIntake(
        verdicts_path=verdicts, artifact_dir=inputs["artifact_dir"], ledger_path=inputs["ledger_path"],
        decisions_path=inputs["decisions_path"], work_registry=inputs["work_registry"],
    )
    return intake, inputs["artifact_dir"]


def test_a_text_is_stored_and_used_only_as_verify_decides(tmp_path: Path) -> None:
    intake, articles = intake_for(tmp_path)
    good = articles / f"{doi_to_slug('10.1000/good')}.json"
    supp = articles / f"{doi_to_slug('10.1000/supp')}.json"
    title_only = articles / f"{doi_to_slug('10.1000/collided')}.json"
    good_text = "# Ketamine infusion for suicidal ideation in emergency care\n\nhttps://doi.org/10.1000/good\n\nResults."
    other_paper = "# Cost of CAR-T therapy in multiple myeloma\n\ndoi: 10.1000/good\n\nMethods."

    # Identifier and title agree, or the title alone agrees closely: stored and used.
    assert intake.may_store(good, artifact("10.1000/good", good_text))[:2] == (True, STORED_VERIFIED)
    titled = "# Cost-effectiveness of CAR-T cell therapy in multiple myeloma\n\nMethods."
    assert intake.may_store(title_only, artifact("10.1000/collided", titled))[2].rule == "title_only_close_match"
    # A text that is not verified never replaces one the table allows ...
    assert intake.may_store(good, artifact("10.1000/good", other_paper))[:2] == (False, KEPT_USABLE_TEXT)
    # ... and is otherwise stored for review, unused until decided.
    supp_text = "# Supplementary Information for the phase 3 trial\n\ndoi: 10.1000/supp\n\nTable S2."
    store, reason, _ = intake.may_store(supp, artifact("10.1000/supp", supp_text))
    assert (store, reason) == (True, STORED_FOR_REVIEW)
    assert intake.may_store(supp, artifact("10.1000/supp", "", backend=""))[:2] == (False, NO_EXTRACTION)

    supp.write_text(json.dumps(artifact("10.1000/supp", supp_text)), encoding="utf-8")
    assert intake.record([supp]) == [str(supp.resolve())]


def test_converters_write_what_the_intake_allows(tmp_path: Path) -> None:
    intake, articles = intake_for(tmp_path)
    good = articles / f"{doi_to_slug('10.1000/good')}.json"
    other_paper = "# Cost of CAR-T therapy in multiple myeloma\n\ndoi: 10.1000/good\n\nMethods."
    assert should_write_artifact(good, artifact("10.1000/good", other_paper), False, intake) == (False, KEPT_USABLE_TEXT)
    # A failed conversion keeps the stored text, as before.
    write, reason = should_write_artifact(good, {"best_backend": ""}, False, intake)
    assert not write and "preserved existing successful" in reason
