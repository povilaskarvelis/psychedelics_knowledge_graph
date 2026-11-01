import csv
import hashlib
import json
from pathlib import Path

import pandas as pd

from pipeline.fulltext.convert_pdfs import doi_to_slug
from pipeline.identity.audit import run_audit
from pipeline.identity.evidence import title_abstract_agreement
from pipeline.identity.register import append_decisions, decision_id


ESKETAMINE_ABSTRACT = " ".join(
    [
        "Esketamine nasal spray combined with a newly initiated oral antidepressant was compared with placebo",
        "nasal spray in adults with treatment-resistant depression. Depressive symptoms measured with the",
        "Montgomery-Asberg Depression Rating Scale improved more with esketamine at day 28, and response and",
        "remission rates were higher. Dissociation and blood pressure increases were transient and resolved",
        "on the day of dosing. Esketamine nasal spray was effective in treatment-resistant depression.",
    ]
)
REVIEW_TITLE = (
    "Ketamine for psychotic depression: an overview of the glutamatergic system and receptor mechanisms "
    "associated with antidepressant and psychotomimetic effects"
)
SPECT_TITLE = "Dopamine receptor binding before and after treatment in SPECT imaging"
REVIEW_ABSTRACT = ESKETAMINE_ABSTRACT.replace("Esketamine", "Ketamine").replace("treatment-resistant", "psychotic")
RECORDS = [
    ("10.1000/good", "Ketamine infusion for suicidal ideation in emergency care", "Ketamine reduced suicidal ideation."),
    ("10.1000/preprinted", "Psilocybin and emotional processing in healthy volunteers", "Psilocybin altered emotion recognition."),
    ("10.1000/supp", "MDMA-assisted therapy for PTSD: a phase 3 trial", "MDMA-assisted therapy reduced PTSD symptoms."),
    ("10.1000/decided", "Ayahuasca and grief in bereaved adults", "Ayahuasca use was associated with lower grief."),
    ("10.1000/owner", "Esketamine nasal spray in treatment-resistant depression", ESKETAMINE_ABSTRACT),
    ("10.1000/wrong", "Wastewater surveillance of cocaine use in European cities", ESKETAMINE_ABSTRACT),
    ("10.13039/501100000780", "Ketamine and esketamine in depression", "Ketamine and esketamine were reviewed."),
    ("10.1000/pubmedconflict", "Ketamine connectivity in healthy volunteers", "Ketamine changed resting connectivity in healthy volunteers."),
    ("10.1000/collided", "Cost-effectiveness of CAR-T cell therapy in multiple myeloma", "CAR-T cell therapy for multiple myeloma was cost-effective."),
    ("10.1000/notretained.s001", "Figure 1 of a ketamine study", "Dose-response curve."),
    ("10.1000/retitled", "Pengaruh latihan sirkuit terhadap daya tahan", "Ketamine restored synaptic tuning in mice."),
    ("10.1000/untitled", "", ESKETAMINE_ABSTRACT),
    ("10.1000/cookies", "Mescaline use in ritual contexts", "Our website uses cookies. By continuing to use our site, you agree. Log in or register."),
    ("10.1000/review", REVIEW_TITLE, REVIEW_ABSTRACT),
    ("10.1000/spect", SPECT_TITLE, REVIEW_ABSTRACT),
]
ARTIFACT_TEXTS = {
    "10.1000/good": "# Ketamine infusion for suicidal ideation in emergency care\n\nhttps://doi.org/10.1000/good\n\nMethods.",
    "10.1000/preprinted": "# Psilocybin and emotional processing in healthy volunteers\n\ndoi: 10.1101/2021.01.01.000001\n\nMethods.",
    "10.1000/supp": "# Supplementary Information for the phase 3 trial\n\ndoi: 10.1000/supp\n\nTable S1.",
    "10.1000/decided": "# Integrative oncology for breast cancer survivors\n\ndoi: 10.2000/oncology.1\n\nMethods.",
    "10.1000/retitled": "# The effect of ketamine on synaptic mistuning in mice\n\ndoi: 10.1000/retitled\n\nMethods.",
}


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_inputs(root: Path) -> dict:
    ledger = root / "candidate_papers.parquet"
    pd.DataFrame(
        [
            {
                "doi": doi,
                "study_title": title,
                "study_journal": "",
                "abstract": abstract,
                "pmid": "",
                "pmcid": "",
                "openalex_id": "https://openalex.org/W37597153" if doi == "10.1000/collided" else "",
                "retained_for_extraction_candidate": doi != "10.1000/notretained.s001",
            }
            for doi, title, abstract in RECORDS
        ]
    ).to_parquet(ledger, index=False)

    artifacts = root / "articles"
    artifacts.mkdir()
    for doi, text in ARTIFACT_TEXTS.items():
        artifact = {
            "study_doi": doi,
            "extractions": [{"status": "ok", "backend": "test", "text": text, "metadata": {"format": "markdown"}}],
        }
        (artifacts / f"{doi_to_slug(doi)}.json").write_text(json.dumps(artifact), encoding="utf-8")

    discovery = root / "discovery" / "run1"
    discovery.mkdir(parents=True)
    pd.DataFrame(
        [
            {"provider": "pubmed", "doi": "10.1000/good", "pmid": "111", "title": RECORDS[0][1]},
            {
                "provider": "pubmed",
                "doi": "10.1000/pubmedconflict",
                "pmid": "37597153",
                "title": "Cost-effectiveness of CAR-T cell therapy in multiple myeloma",
            },
        ]
    ).to_parquet(discovery / "retrieved_records.parquet", index=False)

    kg_dir = root / "kg"
    kg_dir.mkdir()
    pd.DataFrame(
        [
            {"study_doi": "10.1000/preprinted", "graph_admission_status": "main_graph", "access_level": "article_text"},
            {"study_doi": "10.1000/preprinted", "graph_admission_status": "main_graph", "access_level": "article_text"},
            {"study_doi": "10.1000/wrong", "graph_admission_status": "main_graph", "access_level": "abstract_only"},
            {"study_doi": "10.1000/good", "graph_admission_status": "paper_detail", "access_level": "article_text"},
        ]
    ).to_parquet(kg_dir / "findings.parquet", index=False)

    outputs = root / "outputs.jsonl"
    statement = "The title and metadata do not match the supplied text, which describes a different study."
    outputs.write_text(
        "".join(
            json.dumps({"study_doi": doi, "result": {"warnings": [statement]}}) + "\n"
            for doi in ("10.1000/good", "10.1000/retitled")
        ),
        encoding="utf-8",
    )

    decisions = root / "decisions.jsonl"
    append_decisions(
        [
            {
                "decision_id": decision_id("test", "10.1000/retitled", "record_corrected"),
                "doi": "10.1000/retitled",
                "target": {"kind": "record"},
                "verdict": "record_corrected",
                "fields": {"study_title": "The effect of ketamine on synaptic mistuning in mice"},
                "basis": "The ledger title belongs to a thesis; the DOI's registered title is the ketamine article.",
                "evidence": [],
                "reviewer": "curator",
                "decided_at": "2026-11-01",
            },
            {
                "decision_id": decision_id("test", "10.1000/decided", "not_this_work"),
                "doi": "10.1000/decided",
                "target": {"kind": "fulltext", "document_doi": "10.2000/oncology.1"},
                "verdict": "not_this_work",
                "basis": "The PDF is an oncology article.",
                "evidence": [],
                "reviewer": "curator",
                "decided_at": "2026-11-01",
            }
        ],
        decisions,
    )
    registry = root / "doi_alias_registry.json"
    registry.write_text(json.dumps({"records": []}), encoding="utf-8")
    return {
        "ledger_path": ledger,
        "artifact_dir": artifacts,
        "discovery_runs": root / "discovery",
        "outputs": [outputs],
        "kg_dir": kg_dir,
        "decisions_path": decisions,
        "work_registry": registry,
    }


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
