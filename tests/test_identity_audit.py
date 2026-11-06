import csv
import json
from pathlib import Path

from pipeline.identity.audit import run_audit
from pipeline.identity.evidence import title_abstract_agreement
from tests.identity_fixtures import REVIEW_ABSTRACT, REVIEW_TITLE, SPECT_TITLE, build_inputs, file_digest


def test_audit_queues_unverified_texts_and_records_and_writes_only_its_folder(tmp_path: Path) -> None:
    inputs = build_inputs(tmp_path)
    before = {path: file_digest(path) for path in tmp_path.rglob("*") if path.is_file()}

    summary = run_audit(**inputs, out_root=tmp_path / "audits", read_pdfs=False, audit_id="test")

    after = {path: file_digest(path) for path in tmp_path.rglob("*") if path.is_file()}
    audit_dir = tmp_path / "audits" / "test"
    assert set(after) - set(before) == {audit_dir / "review_queue.csv", audit_dir / "audit_summary.json"}
    assert all(after[path] == digest for path, digest in before.items())

    with (audit_dir / "review_queue.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    queue = {(row["check"], row["doi"]): row for row in rows}

    preprint = queue[("fulltext", "10.1000/preprinted")]
    assert (preprint["verdict"], preprint["rule"]) == ("conflict", "title_matches_identifier_differs")
    assert (preprint["suggested_verdict"], preprint["suggested_relation"], preprint["suggested_related_doi"]) == (
        "version_of",
        "preprint",
        "10.1101/2021.01.01.000001",
    )
    assert (preprint["scope"], preprint["release_findings_main"]) == ("release", "2")
    assert queue[("fulltext", "10.1000/supp")]["rule"] == "document_is_supplement"
    assert ("fulltext", "10.1000/good") not in queue
    assert ("fulltext", "10.1000/decided") not in queue
    # The text decision settles the oncology PDF; the title correction settles
    # the model's report that the title and text differ.
    assert summary["left_out_as_decided"] == {"fulltext": 1, "model_report": 1}

    wrong = queue[("shared_abstract", "10.1000/wrong")]
    assert (wrong["verdict"], wrong["suggested_verdict"], wrong["suggested_related_doi"]) == (
        "conflict",
        "not_this_work",
        "10.1000/owner",
    )
    assert json.loads(wrong["target"])["kind"] == "abstract"
    assert ("shared_abstract", "10.1000/owner") not in queue
    assert queue[("shared_abstract", "10.1000/untitled")]["rule"] == "shared_abstract_title_unusable"
    assert queue[("abstract_text", "10.1000/cookies")]["suggested_verdict"] == "wrong_kind"
    # A long review title shares under half its words with its abstract but
    # leads the other title clearly, so it owns the abstract.
    assert 0.3 <= title_abstract_agreement(REVIEW_TITLE, REVIEW_ABSTRACT) < 0.5
    assert title_abstract_agreement(SPECT_TITLE, REVIEW_ABSTRACT) <= 0.2
    assert ("shared_abstract", "10.1000/review") not in queue
    assert queue[("shared_abstract", "10.1000/spect")]["suggested_related_doi"] == "10.1000/review"
    # The record correction is applied before the text is checked.
    assert ("fulltext", "10.1000/retitled") not in queue
    assert summary["inputs"]["record_corrections_applied"] == {"fields_set": 1}

    assert queue[("record_doi", "10.13039/501100000780")]["suggested_verdict"] == "wrong_doi"
    assert queue[("record_title", "10.1000/pubmedconflict")]["suggested_verdict"] == "wrong_doi"
    collided = queue[("openalex_pmid_collision", "10.1000/collided")]
    assert (collided["rule"], collided["suggested_verdict"], collided["suggested_related_doi"]) == (
        "record_title_from_other_work",
        "wrong_doi",
        "10.1000/pubmedconflict",
    )
    report = queue[("model_report", "10.1000/good")]
    assert report["verdict"] == "model_reported"
    assert json.loads(report["target"])["kind"] == "fulltext"

    assert rows[0]["scope"] == "release"
    assert summary["queued"] == len(rows)
    assert ("record_doi", "10.1000/notretained.s001") not in queue
    assert summary["not_queued_corpus_scope"] == {"record_doi": 1}


def test_text_after_a_cover_sheet_is_checked_without_the_cover_sheet() -> None:
    from pipeline.identity.audit import after_cover_sheet_source
    from pipeline.identity.evidence import is_cover_sheet
    from pipeline.identity.verify import Paper, verify

    paper = Paper(
        "10.1016/j.jad.2026.121662",
        "The role of therapeutic alliance in psilocybin treatment for treatment-resistant depression",
    )
    cover = (
        f"Citation for published version (APA): {paper.title}\nhttps://doi.org/{paper.doi}\n"
        "General rights\nTake down policy"
    )
    attached = "European Journal of Integrative Medicine\nhttps://doi.org/10.1016/j.eujim.2026.102652\nIntegrative oncology care"
    assert is_cover_sheet(cover)

    verdict = verify(paper, after_cover_sheet_source([cover, attached], paper))

    assert (verdict.verdict, verdict.related_doi) == ("conflict", "10.1016/j.eujim.2026.102652")
