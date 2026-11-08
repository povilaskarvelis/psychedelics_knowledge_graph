"""A small synthetic corpus for the source-identity tests: ledger, stored
full texts, discovery records, release findings and outputs, decisions and an
empty work registry."""

import hashlib
import json
from pathlib import Path

import pandas as pd

from pipeline.fulltext.convert_pdfs import doi_to_slug
from pipeline.identity.register import append_decisions, decision_id
from pipeline.ingest.candidate_status import normalize_doi


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
            "best_backend": "test",
            "best_char_count": len(text),
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
        "provider_records_dir": root / "provider_records",
        "outputs": [outputs],
        "kg_dir": kg_dir,
        "decisions_path": decisions,
        "work_registry": registry,
    }


def write_gate_table(root: Path, rows: list[dict]) -> Path:
    """A verdict table for the full-text gate, from (requested_doi, artifact_path, identity_verified) rows."""
    table = []
    for row in rows:
        path = Path(row["artifact_path"]) if row.get("artifact_path") else None
        table.append(
            {
                "doi": normalize_doi(row["requested_doi"]),
                "target_kind": "fulltext",
                "artifact": path.name if path else "",
                "artifact_sha256": row.get("artifact_sha256") or (file_digest(path) if path and path.is_file() else ""),
                "usable": bool(row.get("identity_verified")),
                "reason": row.get("reason", ""),
                "carried_from": row.get("carried_from", ""),
            }
        )
    verdicts = root / "verdicts.parquet"
    columns = ["doi", "target_kind", "artifact", "artifact_sha256", "usable", "reason", "carried_from"]
    pd.DataFrame(table, columns=columns).astype({"usable": bool}).to_parquet(verdicts, index=False)
    return verdicts
