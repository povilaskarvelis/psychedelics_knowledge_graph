import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from pipeline.review.run_deterministic_prescreen import (
    build_prescreen_decisions,
    build_summary_rows,
    run,
)


class TableDeterministicPrescreenTest(unittest.TestCase):
    def test_builds_one_decision_per_doi_and_uses_metadata_abstract(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/psilo",
                    "datasets": "disorder",
                    "study_title": "Metadata title should win",
                    "abstract": "",
                    "current_pipeline_status": "metadata_enriched",
                    "source_types": "metadata_enrichment",
                },
                {
                    "doi": "10.example/exercise",
                    "datasets": "disorder",
                    "study_title": "Exercise intervention for depression",
                    "abstract": "This randomized trial tested exercise for depression.",
                    "current_pipeline_status": "metadata_enriched",
                    "source_types": "metadata_enrichment",
                },
            ]
        )
        metadata = pd.DataFrame(
            [
                {
                    "doi": "10.example/psilo",
                    "study_title": "Psilocybin therapy for depression",
                    "abstract": "Psilocybin therapy reduced depression symptoms.",
                    "metadata_enrichment_status": "enriched",
                    "metadata_enrichment_run_id": "test_metadata",
                }
            ]
        )
        contexts = pd.DataFrame(
            [
                {
                    "doi": "10.example/psilo",
                    "dataset": "disorder",
                    "compound": "Psilocybin",
                    "entity": "Major depressive disorder",
                    "entity_type": "indication",
                }
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            metadata,
            contexts,
            run_id="test_run",
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )
        by_doi = {row["doi"]: row for row in rows}

        self.assertEqual(len(rows), 2)
        self.assertTrue(all("dataset" not in row and "datasets" not in row for row in rows))
        self.assertEqual(by_doi["10.example/psilo"]["study_title"], "Psilocybin therapy for depression")
        self.assertEqual(by_doi["10.example/psilo"]["prescreen_decision"], "retain")
        self.assertEqual(by_doi["10.example/psilo"]["metadata_enrichment_run_id"], "test_metadata")
        self.assertEqual(by_doi["10.example/exercise"]["prescreen_action"], "exclude_obvious_irrelevant")
        self.assertFalse(by_doi["10.example/exercise"]["retained_for_extraction_candidate"])

    def test_old_pipeline_status_does_not_affect_prescreen_exclusion(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/missing",
                    "datasets": "mechanistic",
                    "study_title": "Psilocybin and default mode network",
                    "abstract": "",
                    "current_pipeline_status": "metadata_enriched",
                    "source_types": "metadata_enrichment",
                },
                {
                    "doi": "10.example/protected",
                    "datasets": "mechanistic",
                    "study_title": "Curated paper without abstract",
                    "abstract": "",
                    "current_pipeline_status": "curated_claim",
                    "source_types": "curated_claim",
                },
            ]
        )
        contexts = pd.DataFrame(
            [
                {
                    "doi": "10.example/protected",
                    "dataset": "mechanistic",
                    "compound": "Psilocybin",
                    "entity": "Default mode network",
                    "entity_type": "brain_region_or_network",
                }
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            contexts,
            run_id="test_run",
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )
        by_doi = {row["doi"]: row for row in rows}

        self.assertEqual(by_doi["10.example/missing"]["prescreen_action"], "exclude_missing_abstract")
        self.assertEqual(by_doi["10.example/missing"]["prescreen_decision"], "exclude")
        self.assertEqual(by_doi["10.example/protected"]["deterministic_action"], "exclude_missing_abstract")
        self.assertEqual(by_doi["10.example/protected"]["prescreen_action"], "exclude_missing_abstract")
        self.assertEqual(by_doi["10.example/protected"]["prescreen_decision"], "exclude")
        self.assertFalse(by_doi["10.example/protected"]["retained_for_extraction_candidate"])
        self.assertIn("brain_system", by_doi["10.example/protected"]["routing_tags"])

    def test_placeholder_and_citation_only_abstracts_are_treated_as_missing(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/placeholder",
                    "datasets": "disorder",
                    "study_title": "Esketamine for Treatment-Resistant Depression",
                    "abstract": "International audience",
                    "current_pipeline_status": "metadata_enriched",
                    "source_types": "metadata_enrichment",
                },
                {
                    "doi": "10.example/citation-parenthetical",
                    "datasets": "mechanistic",
                    "study_title": "Cultural Therapy - A New Conception of Treatment",
                    "abstract": (
                        "(1974). Cultural Therapy - A New Conception of Treatment. "
                        "Journal of Psychedelic Drugs: Vol. 6, No. 2, pp. 173-177."
                    ),
                    "current_pipeline_status": "metadata_enriched",
                    "source_types": "metadata_enrichment",
                },
                {
                    "doi": "10.example/citation-journal",
                    "datasets": "disorder",
                    "study_title": "S.7.3 - KETAMINE AND NMDA RECEPTOR MODULATION",
                    "abstract": (
                        "Behavioural Pharmacology: October 2013 - Volume 24 - Issue - "
                        "p e8-e9 doi: 10.example/citation-journal"
                    ),
                    "current_pipeline_status": "metadata_enriched",
                    "source_types": "metadata_enrichment",
                },
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-05-30T00:00:00+00:00",
        )
        by_doi = {row["doi"]: row for row in rows}

        for doi in by_doi:
            self.assertEqual(by_doi[doi]["prescreen_action"], "exclude_missing_abstract")
            self.assertEqual(by_doi[doi]["prescreen_decision"], "exclude")
            self.assertFalse(by_doi[doi]["has_abstract"])
            self.assertFalse(by_doi[doi]["retained_for_extraction_candidate"])

    def test_no_title_container_record_excluded_even_with_matching_abstract(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/issue",
                    "datasets": "mechanistic",
                    "study_title": "",
                    "abstract": "Psilocybin was discussed in a neuroscience context.",
                    "publication_type": "journal-issue",
                }
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(rows[0]["prescreen_decision"], "exclude")
        self.assertEqual(rows[0]["prescreen_action"], "exclude_non_paper_container")
        self.assertFalse(rows[0]["retained_for_extraction_candidate"])

    def test_non_evidence_artifacts_are_excluded_before_routing(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/correction",
                    "datasets": "disorder",
                    "study_title": "Author Correction: MDMA-assisted therapy for PTSD",
                    "abstract": "MDMA-assisted therapy reduced PTSD symptoms.",
                    "publication_type": "Published Erratum",
                },
                {
                    "doi": "10.example/protocol",
                    "datasets": "disorder",
                    "study_title": "Ketamine-Assisted Recovery: protocol for an open-label pilot trial",
                    "abstract": "This protocol describes ketamine-assisted psychotherapy for addiction.",
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.1002/jmv.26681",
                    "datasets": "disorder",
                    "study_title": "Ketamine in COVID-19 patients: Thinking out of the box",
                    "abstract": "This letter speculates about ketamine use in COVID-19 patients.",
                    "publication_type": "Letter",
                },
                {
                    "doi": "10.1371/journal.pmed.1004519.g001",
                    "datasets": "disorder",
                    "study_title": "Study flow chart.",
                    "abstract": "Psilocybin and MBSR were studied in health care workers.",
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.1021/acsptsci.5c00324.s001",
                    "datasets": "mechanistic",
                    "study_title": "The Medial Prefrontal Cortex Modulates Psychedelic-like Effects of Psilocin",
                    "abstract": "Psilocin effects were tested in medial prefrontal cortex.",
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.6084/m9.figshare.24531073",
                    "datasets": "mechanistic",
                    "study_title": "Spinogenesis Data - Prism file",
                    "abstract": "Psilocybin and ketamine spinogenesis data are provided.",
                    "publication_type": "Dataset",
                },
                {
                    "doi": "10.20944/preprints202305.2222.v1",
                    "datasets": "mechanistic",
                    "study_title": "Microbiome: The Next Frontier in Psychedelic Renaissance",
                    "abstract": "This review discusses psychedelics and the microbiome.",
                    "publication_type": "posted-content",
                },
                {
                    "doi": "10.31219/osf.io/dy5cu_v1",
                    "datasets": "disorder",
                    "study_title": "Legal and Regulatory Barriers to Medical Psilocybin Use",
                    "abstract": "This overview discusses medical psilocybin regulation.",
                    "publication_type": "article",
                },
                {
                    "doi": "10.3389/fnins.2025.1554049.s002",
                    "datasets": "mechanistic",
                    "study_title": "Table 2_Dose-dependent changes in global brain activity following psilocybin.xlsx",
                    "abstract": "Dose-dependent brain activity and functional connectivity are reported.",
                    "publication_type": "dataset",
                },
                {
                    "doi": "10.64898/2026.04.16.718915",
                    "datasets": "mechanistic",
                    "study_title": "Serotonergic Polypharmacology of 2-Halogenated Tryptamines",
                    "abstract": "Novel tryptamines were tested at serotonin receptors.",
                    "publication_type": "Journal Article | Preprint",
                },
                {
                    "doi": "10.example/case-letter",
                    "datasets": "disorder",
                    "study_title": "MDMA intoxication: Acute psychosis caused by a designer drug",
                    "abstract": "This case report describes acute psychosis after MDMA exposure.",
                    "publication_type": "Case Reports | Letter",
                },
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-05-30T00:00:00+00:00",
        )
        by_doi = {row["doi"]: row for row in rows}

        self.assertEqual(by_doi["10.example/correction"]["prescreen_decision"], "exclude")
        self.assertEqual(by_doi["10.example/correction"]["prescreen_action"], "exclude_non_evidence_artifact")
        self.assertEqual(by_doi["10.example/protocol"]["prescreen_decision"], "exclude")
        self.assertEqual(by_doi["10.example/protocol"]["prescreen_action"], "exclude_non_evidence_artifact")
        self.assertEqual(by_doi["10.1002/jmv.26681"]["prescreen_decision"], "exclude")
        self.assertEqual(by_doi["10.1002/jmv.26681"]["prescreen_action"], "exclude_non_evidence_artifact")
        self.assertEqual(by_doi["10.1371/journal.pmed.1004519.g001"]["prescreen_action"], "exclude_non_evidence_artifact")
        self.assertEqual(by_doi["10.1021/acsptsci.5c00324.s001"]["prescreen_action"], "exclude_non_evidence_artifact")
        self.assertEqual(by_doi["10.6084/m9.figshare.24531073"]["prescreen_action"], "exclude_non_evidence_artifact")
        self.assertEqual(by_doi["10.20944/preprints202305.2222.v1"]["prescreen_action"], "exclude_preprint_or_unpublished")
        self.assertEqual(by_doi["10.31219/osf.io/dy5cu_v1"]["prescreen_action"], "exclude_preprint_or_unpublished")
        self.assertEqual(by_doi["10.3389/fnins.2025.1554049.s002"]["prescreen_action"], "exclude_non_evidence_artifact")
        self.assertEqual(by_doi["10.64898/2026.04.16.718915"]["prescreen_action"], "exclude_preprint_or_unpublished")
        self.assertFalse(by_doi["10.example/correction"]["retained_for_extraction_candidate"])
        self.assertFalse(by_doi["10.example/protocol"]["retained_for_extraction_candidate"])
        self.assertFalse(by_doi["10.1002/jmv.26681"]["retained_for_extraction_candidate"])
        self.assertFalse(by_doi["10.1371/journal.pmed.1004519.g001"]["retained_for_extraction_candidate"])
        self.assertFalse(by_doi["10.1021/acsptsci.5c00324.s001"]["retained_for_extraction_candidate"])
        self.assertFalse(by_doi["10.6084/m9.figshare.24531073"]["retained_for_extraction_candidate"])
        self.assertFalse(by_doi["10.20944/preprints202305.2222.v1"]["retained_for_extraction_candidate"])
        self.assertFalse(by_doi["10.31219/osf.io/dy5cu_v1"]["retained_for_extraction_candidate"])
        self.assertFalse(by_doi["10.3389/fnins.2025.1554049.s002"]["retained_for_extraction_candidate"])
        self.assertFalse(by_doi["10.64898/2026.04.16.718915"]["retained_for_extraction_candidate"])
        self.assertEqual(by_doi["10.example/case-letter"]["prescreen_decision"], "exclude")
        self.assertEqual(by_doi["10.example/case-letter"]["prescreen_action"], "exclude_non_evidence_artifact")
        self.assertFalse(by_doi["10.example/case-letter"]["retained_for_extraction_candidate"])

    def test_lumpy_skin_disease_lsd_acronym_is_excluded(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.3389/fvets.2026.1818746",
                    "datasets": "mechanistic",
                    "study_title": (
                        "Clinical study and the diagnosis of lumpy skin disease in cattle "
                        "using genomic, immunological, and pathological indicators."
                    ),
                    "abstract": (
                        "Lumpy skin disease (LSD) is a transboundary animal disease. "
                        "This study identified biomarkers in vaccinated cattle."
                    ),
                    "publication_type": "Journal Article",
                }
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-06-28T00:00:00+00:00",
        )

        self.assertEqual(rows[0]["prescreen_decision"], "exclude")
        self.assertEqual(rows[0]["prescreen_action"], "exclude_obvious_irrelevant")
        self.assertFalse(rows[0]["retained_for_extraction_candidate"])
        self.assertIn("lumpy-skin-disease", rows[0]["prescreen_reason"])

    def test_bioproduction_method_paper_is_excluded_before_routing(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.1002/bit.28480",
                    "datasets": "mechanistic",
                    "study_title": (
                        "Biosynthesis of psilocybin and its nonnatural derivatives by a promiscuous "
                        "psilocybin synthesis pathway in Escherichia coli"
                    ),
                    "abstract": (
                        "This synthetic biology study engineered Escherichia coli strains for the "
                        "sustainable microbial production of psilocybin derivatives."
                    ),
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.example/receptor-pharmacology",
                    "datasets": "mechanistic",
                    "study_title": "Novel psilocybin derivatives as serotonin 5-HT2A receptor agonists",
                    "abstract": (
                        "This study synthesized psilocybin derivatives and measured 5-HT2A receptor "
                        "binding affinity and functional signaling."
                    ),
                    "publication_type": "Journal Article",
                },
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-06-28T00:00:00+00:00",
        )
        by_doi = {row["doi"]: row for row in rows}

        self.assertEqual(by_doi["10.1002/bit.28480"]["prescreen_decision"], "exclude")
        self.assertEqual(by_doi["10.1002/bit.28480"]["prescreen_action"], "exclude_obvious_irrelevant")
        self.assertFalse(by_doi["10.1002/bit.28480"]["retained_for_extraction_candidate"])
        self.assertIn("bioproduction", by_doi["10.1002/bit.28480"]["prescreen_reason"])
        self.assertEqual(by_doi["10.example/receptor-pharmacology"]["prescreen_decision"], "retain")
        self.assertTrue(by_doi["10.example/receptor-pharmacology"]["retained_for_extraction_candidate"])

    def test_broad_nps_history_background_is_excluded_without_dropping_nps_pharmacology(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.1002/dta.319",
                    "datasets": "mechanistic",
                    "study_title": "A brief history of ‘new psychoactive substances’",
                    "abstract": (
                        "This editorial introduces a special issue about legal highs and the adoption "
                        "of the term new psychoactive substances."
                    ),
                    "publication_type": "Editorial | Historical Article",
                },
                {
                    "doi": "10.example/nps-pharmacology",
                    "datasets": "mechanistic",
                    "study_title": "Pharmacology of MDMA- and amphetamine-like new psychoactive substances",
                    "abstract": (
                        "This review summarizes monoamine transporter activity, receptor interactions, "
                        "and toxicity for MDMA-like new psychoactive substances."
                    ),
                    "publication_type": "Journal Article | Review",
                },
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-06-28T00:00:00+00:00",
        )
        by_doi = {row["doi"]: row for row in rows}

        self.assertEqual(by_doi["10.1002/dta.319"]["prescreen_decision"], "exclude")
        self.assertEqual(by_doi["10.1002/dta.319"]["prescreen_action"], "exclude_non_evidence_artifact")
        self.assertFalse(by_doi["10.1002/dta.319"]["retained_for_extraction_candidate"])
        self.assertIn("pure letter/editorial/comment/news", by_doi["10.1002/dta.319"]["prescreen_reason"])
        self.assertEqual(by_doi["10.example/nps-pharmacology"]["prescreen_decision"], "retain")
        self.assertTrue(by_doi["10.example/nps-pharmacology"]["retained_for_extraction_candidate"])

    def test_patent_highlight_is_excluded_without_blanket_patent_review_exclusion(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.1021/acsmedchemlett.5c00484",
                    "datasets": "mechanistic",
                    "study_title": (
                        "Novel Serotonergic Psychedelic Agents as 5-HT2A Agonists for Treating "
                        "Psychosis, Mental Illness, and CNS Disorders"
                    ),
                    "abstract": (
                        "ADVERTISEMENT RETURN TO ISSUE PREV Patent Highlight NEXT. Provided herein "
                        "are novel serotonergic psychedelic agents as 5-HT2A agonists."
                    ),
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.example/patent-review",
                    "datasets": "mechanistic",
                    "study_title": "NMDA receptor modulators: an updated patent review",
                    "abstract": (
                        "This review discusses ketamine and other NMDA receptor modulators, including "
                        "receptor mechanisms and clinical development."
                    ),
                    "publication_type": "Journal Article | Review",
                },
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-06-28T00:00:00+00:00",
        )
        by_doi = {row["doi"]: row for row in rows}

        self.assertEqual(by_doi["10.1021/acsmedchemlett.5c00484"]["prescreen_decision"], "exclude")
        self.assertEqual(by_doi["10.1021/acsmedchemlett.5c00484"]["prescreen_action"], "exclude_non_evidence_artifact")
        self.assertFalse(by_doi["10.1021/acsmedchemlett.5c00484"]["retained_for_extraction_candidate"])
        self.assertEqual(by_doi["10.example/patent-review"]["prescreen_decision"], "retain")
        self.assertTrue(by_doi["10.example/patent-review"]["retained_for_extraction_candidate"])

    def test_brown_psychopharmacology_update_newsletter_items_are_excluded(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.1002/pu.31440",
                    "datasets": "disorder",
                    "study_title": "Ketamine shows long-term benefit in patients with treatment-resistant depression",
                    "abstract": (
                        "Patients with treatment-resistant depression who received ketamine or esketamine "
                        "showed reduced emergency department visits, a study has found."
                    ),
                    "study_journal": "The Brown University Psychopharmacology Update",
                    "publication_type": "journal-article",
                },
                {
                    "doi": "10.1002/cpu30817",
                    "datasets": "disorder",
                    "study_title": "Esketamine has no effect on cognition compared to midazolam",
                    "abstract": (
                        "Researchers conducted a randomized controlled trial and found that cognition "
                        "was not harmed by esketamine."
                    ),
                    "study_journal": "The Brown University Child & Adolescent Psychopharmacology Update",
                    "publication_type": "journal-article",
                },
                {
                    "doi": "10.example/jop",
                    "datasets": "mechanistic",
                    "study_title": "Psilocybin changes default mode network connectivity",
                    "abstract": "This study reports psilocybin effects on default mode network connectivity.",
                    "study_journal": "Journal of Psychopharmacology",
                    "publication_type": "Journal Article",
                },
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-07-05T00:00:00+00:00",
        )
        by_doi = {row["doi"]: row for row in rows}

        self.assertEqual(by_doi["10.1002/pu.31440"]["prescreen_decision"], "exclude")
        self.assertEqual(by_doi["10.1002/pu.31440"]["prescreen_action"], "exclude_non_evidence_artifact")
        self.assertIn("newsletter/update summary", by_doi["10.1002/pu.31440"]["prescreen_reason"])
        self.assertFalse(by_doi["10.1002/pu.31440"]["retained_for_extraction_candidate"])
        self.assertEqual(by_doi["10.1002/cpu30817"]["prescreen_decision"], "exclude")
        self.assertEqual(by_doi["10.1002/cpu30817"]["prescreen_action"], "exclude_non_evidence_artifact")
        self.assertFalse(by_doi["10.1002/cpu30817"]["retained_for_extraction_candidate"])
        self.assertEqual(by_doi["10.example/jop"]["prescreen_decision"], "retain")
        self.assertTrue(by_doi["10.example/jop"]["retained_for_extraction_candidate"])

    def test_numbered_conference_abstracts_are_excluded_without_blanket_numeric_title_exclusion(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.1093/ijnp/pyaf052.166",
                    "datasets": "disorder",
                    "study_title": (
                        "155. EXPLORING LSD MICRODOSING IN AN OPEN-LABEL PILOT FOR "
                        "MAJOR DEPRESSIVE DISORDER"
                    ),
                    "abstract": "This numbered congress abstract reports LSD microdosing outcomes.",
                    "study_journal": "International Journal of Neuropsychopharmacology",
                    "publication_type": "journal-article",
                },
                {
                    "doi": "10.1017/s1092852920000589",
                    "datasets": "disorder",
                    "study_title": (
                        "142 Withdrawal Symptom Assessment in an Esketamine Safety Study "
                        "in Patients with Treatment-resistant Depression"
                    ),
                    "abstract": "This meeting abstract reports withdrawal symptoms in an esketamine safety study.",
                    "study_journal": "CNS Spectrums",
                    "publication_type": "journal-article",
                },
                {
                    "doi": "10.3109/15563650.2013.817658",
                    "datasets": "disorder",
                    "study_title": "2013 Annual Meeting of the North American Congress of Clinical Toxicology (NACCT)",
                    "abstract": "This annual meeting record includes ketamine-related abstracts.",
                    "study_journal": "Clinical Toxicology",
                    "publication_type": "article",
                },
                {
                    "doi": "10.example/5ht",
                    "datasets": "mechanistic",
                    "study_title": "5-HT2A receptor signaling after psilocybin exposure",
                    "abstract": "This study reports psilocybin effects on 5-HT2A receptor signaling.",
                    "study_journal": "Journal of Psychopharmacology",
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.example/40hz",
                    "datasets": "mechanistic",
                    "study_title": "40 Hz Auditory Steady-State Response Is a Pharmacodynamic Biomarker",
                    "abstract": "This study reports ketamine effects on 40 Hz auditory steady-state response.",
                    "study_journal": "Neuropsychopharmacology",
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.example/years",
                    "datasets": "disorder",
                    "study_title": "5 Years of bipolar disorder conversations on Reddit: Methods and key topics",
                    "abstract": "This study reports ketamine discussions in bipolar disorder conversations.",
                    "study_journal": "PLoS ONE",
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.example/guideline",
                    "datasets": "disorder",
                    "study_title": "2025 guideline update to acute treatment of migraine for adults",
                    "abstract": "This guideline discusses ketamine among acute treatment options.",
                    "study_journal": "Headache",
                    "publication_type": "Journal Article | Practice Guideline",
                },
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-07-07T00:00:00+00:00",
        )
        by_doi = {row["doi"]: row for row in rows}

        for doi in ("10.1093/ijnp/pyaf052.166", "10.1017/s1092852920000589", "10.3109/15563650.2013.817658"):
            self.assertEqual(by_doi[doi]["prescreen_decision"], "exclude")
            self.assertEqual(by_doi[doi]["prescreen_action"], "exclude_non_evidence_artifact")
            self.assertIn("numbered conference", by_doi[doi]["prescreen_reason"])
            self.assertFalse(by_doi[doi]["retained_for_extraction_candidate"])

        for doi in ("10.example/5ht", "10.example/40hz", "10.example/years", "10.example/guideline"):
            self.assertEqual(by_doi[doi]["prescreen_decision"], "retain")
            self.assertTrue(by_doi[doi]["retained_for_extraction_candidate"])

    def test_writes_parquet_decisions_and_summary_without_json_outputs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            papers_path = root / "candidate_papers.parquet"
            metadata_path = root / "paper_metadata_enrichment.parquet"
            contexts_path = root / "candidate_contexts.parquet"
            decisions_path = root / "paper_prescreen_decisions.parquet"
            summary_path = root / "paper_prescreen_summary.parquet"
            pd.DataFrame(
                [
                    {
                        "doi": "10.example/psilo",
                        "datasets": "disorder",
                        "study_title": "Psilocybin therapy for depression",
                        "abstract": "Psilocybin therapy reduced depression symptoms.",
                    }
                ]
            ).to_parquet(papers_path, index=False)
            pd.DataFrame([]).to_parquet(metadata_path, index=False)
            pd.DataFrame([]).to_parquet(contexts_path, index=False)

            args = type(
                "Args",
                (),
                {
                    "papers_table": str(papers_path),
                    "metadata_table": str(metadata_path),
                    "contexts_table": str(contexts_path),
                    "decisions_table": str(decisions_path),
                    "summary_table": str(summary_path),
                    "run_id": "test_run",
                    "dataset": "all",
                    "doi_file": "",
                    "doi": [],
                    "retain_missing_abstract": False,
                    "progress_every": 0,
                },
            )()
            decisions, summary = run(args)

            self.assertEqual(len(decisions), 1)
            self.assertTrue(summary)
            self.assertTrue(decisions_path.exists())
            self.assertTrue(summary_path.exists())
            self.assertEqual(list(root.glob("*.json")), [])
            written = pd.read_parquet(decisions_path)
            self.assertEqual(written.loc[0, "prescreen_decision"], "retain")
            self.assertNotIn("dataset", written.columns)
            self.assertNotIn("datasets", written.columns)
            written_summary = pd.read_parquet(summary_path)
            self.assertIn("scope", written_summary.columns)
            self.assertNotIn("dataset", written_summary.columns)

    def test_scoped_update_replaces_only_requested_doi_rows_and_reuses_existing_run_id(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            papers_path = root / "candidate_papers.parquet"
            metadata_path = root / "paper_metadata_enrichment.parquet"
            contexts_path = root / "candidate_contexts.parquet"
            decisions_path = root / "paper_prescreen_decisions.parquet"
            summary_path = root / "paper_prescreen_summary.parquet"
            doi_file = root / "update_dois.txt"

            pd.DataFrame(
                [
                    {
                        "doi": "10.example/psilo",
                        "datasets": "disorder",
                        "study_title": "Psilocybin therapy for depression",
                        "abstract": "",
                    },
                    {
                        "doi": "10.example/exercise",
                        "datasets": "disorder",
                        "study_title": "Exercise intervention for depression",
                        "abstract": "This randomized trial tested exercise for depression.",
                    },
                ]
            ).to_parquet(papers_path, index=False)
            pd.DataFrame(
                [
                    {
                        "doi": "10.example/psilo",
                        "study_title": "Psilocybin therapy for depression",
                        "abstract": "Psilocybin therapy reduced depression symptoms.",
                        "metadata_enrichment_status": "enriched",
                    }
                ]
            ).to_parquet(metadata_path, index=False)
            pd.DataFrame([]).to_parquet(contexts_path, index=False)
            pd.DataFrame(
                [
                    {
                        "table_version": "0.1",
                        "run_id": "existing_prescreen_run",
                        "generated_at_utc": "old",
                        "prescreen_decision_id": "old-psilo",
                        "doi": "10.example/psilo",
                        "dataset": "disorder",
                        "has_abstract": False,
                        "prescreen_decision": "exclude",
                        "prescreen_action": "exclude_missing_abstract",
                        "deterministic_action": "exclude_missing_abstract",
                        "routing_tags": "",
                    },
                    {
                        "table_version": "0.1",
                        "run_id": "existing_prescreen_run",
                        "generated_at_utc": "old",
                        "prescreen_decision_id": "old-exercise",
                        "doi": "10.example/exercise",
                        "dataset": "disorder",
                        "has_abstract": True,
                        "prescreen_decision": "retain",
                        "prescreen_action": "retain_for_extraction_candidate",
                        "deterministic_action": "escalate",
                        "routing_tags": "",
                    },
                ]
            ).to_parquet(decisions_path, index=False)
            doi_file.write_text("10.example/psilo\n", encoding="utf-8")

            args = type(
                "Args",
                (),
                {
                    "papers_table": str(papers_path),
                    "metadata_table": str(metadata_path),
                    "contexts_table": str(contexts_path),
                    "decisions_table": str(decisions_path),
                    "summary_table": str(summary_path),
                    "run_id": "",
                    "dataset": "all",
                    "doi_file": str(doi_file),
                    "doi": [],
                    "retain_missing_abstract": False,
                    "progress_every": 0,
                },
            )()
            decisions, summary = run(args)
            written = pd.read_parquet(decisions_path)
            by_doi = {row["doi"]: row for row in written.to_dict("records")}

        self.assertEqual(len(decisions), 2)
        self.assertTrue(summary)
        self.assertEqual(by_doi["10.example/psilo"]["run_id"], "existing_prescreen_run")
        self.assertEqual(by_doi["10.example/psilo"]["prescreen_action"], "retain_for_extraction_candidate")
        self.assertEqual(by_doi["10.example/exercise"]["prescreen_decision_id"], "old-exercise")
        self.assertEqual(by_doi["10.example/exercise"]["prescreen_action"], "retain_for_extraction_candidate")
        self.assertNotIn("dataset", written.columns)
        self.assertNotIn("datasets", written.columns)

    def test_scoped_update_adds_new_doi_rows(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            papers_path = root / "candidate_papers.parquet"
            metadata_path = root / "paper_metadata_enrichment.parquet"
            contexts_path = root / "candidate_contexts.parquet"
            decisions_path = root / "paper_prescreen_decisions.parquet"
            summary_path = root / "paper_prescreen_summary.parquet"
            doi_file = root / "new_dois.txt"

            pd.DataFrame(
                [
                    {
                        "doi": "10.example/existing",
                        "datasets": "disorder",
                        "study_title": "Existing paper",
                        "abstract": "Psilocybin therapy reduced depression symptoms.",
                    },
                    {
                        "doi": "10.example/new",
                        "datasets": "disorder",
                        "study_title": "New psilocybin paper",
                        "abstract": "Psilocybin therapy was evaluated for depression symptoms.",
                    },
                ]
            ).to_parquet(papers_path, index=False)
            pd.DataFrame([]).to_parquet(metadata_path, index=False)
            pd.DataFrame([]).to_parquet(contexts_path, index=False)
            pd.DataFrame(
                [
                    {
                        "table_version": "0.1",
                        "run_id": "existing_prescreen_run",
                        "generated_at_utc": "old",
                        "prescreen_decision_id": "old-existing",
                        "doi": "10.example/existing",
                        "dataset": "disorder",
                        "has_abstract": True,
                        "prescreen_decision": "retain",
                        "prescreen_action": "retain_for_extraction_candidate",
                        "deterministic_action": "escalate",
                        "routing_tags": "",
                    },
                ]
            ).to_parquet(decisions_path, index=False)
            doi_file.write_text("10.example/new\n", encoding="utf-8")

            args = type(
                "Args",
                (),
                {
                    "papers_table": str(papers_path),
                    "metadata_table": str(metadata_path),
                    "contexts_table": str(contexts_path),
                    "decisions_table": str(decisions_path),
                    "summary_table": str(summary_path),
                    "run_id": "",
                    "dataset": "all",
                    "doi_file": str(doi_file),
                    "doi": [],
                    "retain_missing_abstract": False,
                    "progress_every": 0,
                },
            )()
            decisions, summary = run(args)
            written = pd.read_parquet(decisions_path)
            by_doi = {row["doi"]: row for row in written.to_dict("records")}

        self.assertEqual(len(decisions), 2)
        self.assertTrue(summary)
        self.assertEqual(by_doi["10.example/existing"]["prescreen_decision_id"], "old-existing")
        self.assertEqual(by_doi["10.example/new"]["run_id"], "existing_prescreen_run")
        self.assertEqual(by_doi["10.example/new"]["prescreen_action"], "retain_for_extraction_candidate")
        self.assertNotIn("dataset", written.columns)
        self.assertNotIn("datasets", written.columns)

    def test_summary_counts_actions_and_routing_tags(self) -> None:
        decisions = [
            {
                "doi": "10.example/a",
                "has_abstract": True,
                "prescreen_decision": "retain",
                "prescreen_action": "retain_for_extraction_candidate",
                "deterministic_action": "escalate",
                "routing_tags": "brain_system|molecular_target",
            },
            {
                "doi": "10.example/b",
                "has_abstract": False,
                "prescreen_decision": "exclude",
                "prescreen_action": "exclude_missing_abstract",
                "deterministic_action": "exclude_missing_abstract",
                "routing_tags": "",
            },
        ]

        summary = build_summary_rows(decisions, run_id="test_run", generated_at_utc="now")
        keyed = {(row["scope"], row["metric"], row["label"]): row["count"] for row in summary}

        self.assertTrue(all("dataset" not in row for row in summary))
        self.assertEqual(keyed[("all_papers", "prescreen_decision", "retain")], 1)
        self.assertEqual(keyed[("all_papers", "prescreen_action", "exclude_missing_abstract")], 1)
        self.assertEqual(keyed[("all_papers", "routing_tag", "brain_system")], 1)
        self.assertEqual(keyed[("all_papers", "abstract", "missing")], 1)


if __name__ == "__main__":
    unittest.main()
