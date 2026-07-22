import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from pipeline.review.run_deterministic_prescreen import (
    MINIMUM_ABSTRACT_WORD_COUNT,
    RULE_VERSION,
    TABLE_VERSION,
    abstract_word_count,
    before_model_exclusion_decision,
    build_prescreen_decisions,
    build_summary_rows,
    candidate_prescreen_updates,
    run,
)


def qualifying_abstract(text: str) -> str:
    """Pad a focused fixture to the production minimum without adding scope terms."""

    filler = (
        "The paper describes its background objectives methods participants measurements "
        "analysis results limitations interpretation and conclusions in sufficient detail."
    )
    while abstract_word_count(text) < MINIMUM_ABSTRACT_WORD_COUNT:
        text = f"{text} {filler}"
    return text


class TableDeterministicPrescreenTest(unittest.TestCase):
    def test_candidate_updates_promote_prescreen_exclusions_and_preserve_later_exclusions(self) -> None:
        decisions = [
            {
                "doi": "10.example/new-prescreen-exclude",
                "prescreen_decision": "exclude",
                "prescreen_action": "exclude_non_evidence_artifact",
                "prescreen_reason": "Conference abstract.",
                "retained_for_extraction_candidate": False,
            },
            {
                "doi": "10.example/later-exclude",
                "prescreen_decision": "retain",
                "prescreen_action": "retain_for_screening",
                "prescreen_reason": "In-scope intervention.",
                "retained_for_extraction_candidate": True,
            },
            {
                "doi": "10.example/old-prescreen-exclude",
                "prescreen_decision": "retain",
                "prescreen_action": "retain_for_screening",
                "prescreen_reason": "In-scope intervention.",
                "retained_for_extraction_candidate": True,
            },
        ]
        candidates = pd.DataFrame(
            [
                {"doi": "10.example/new-prescreen-exclude", "pipeline_exclusion_stage": "post_retrieval_eligibility"},
                {"doi": "10.example/later-exclude", "pipeline_exclusion_stage": "post_retrieval_eligibility"},
                {"doi": "10.example/old-prescreen-exclude", "pipeline_exclusion_stage": "prescreen"},
            ]
        )

        updates = candidate_prescreen_updates(decisions, candidates).set_index("doi")

        self.assertEqual(updates.loc["10.example/new-prescreen-exclude", "pipeline_exclusion_stage"], "prescreen")
        self.assertEqual(
            updates.loc["10.example/new-prescreen-exclude", "pipeline_exclusion_decision_source"],
            RULE_VERSION,
        )
        self.assertTrue(pd.isna(updates.loc["10.example/later-exclude", "pipeline_exclusion_stage"]))
        self.assertEqual(updates.loc["10.example/old-prescreen-exclude", "pipeline_exclusion_stage"], "")

    def test_repository_and_dataset_identifiers_are_non_evidence_formats(self) -> None:
        for doi, expected in (
            ("10.25772/1zzj-vn14", "dissertation"),
            ("10.14288/1.0379503", "dissertation"),
            ("10.17632/5yhxtvcgyy.1", "dataset_or_data_deposit"),
            ("10.5281/zenodo.17849521", "repository_deposit"),
            ("10.1037/e496472006-010", "bibliographic_repository_record"),
            ("10.26226/morressier.5d1a038457558b317a140d4f", "conference_abstract"),
        ):
            decision = before_model_exclusion_decision(
                {
                    "study_doi": doi,
                    "study_title": "Psychedelic research record",
                    "abstract": "This record discusses psilocybin.",
                    "publication_type": "article",
                }
            )
            self.assertIsNotNone(decision)
            self.assertIn(expected, decision["matched_terms"])

    def test_software_deposits_and_quick_take_summaries_are_non_evidence_formats(self) -> None:
        cases = (
            (
                {
                    "study_doi": "10.5281/zenodo.17622101",
                    "study_title": "metapsy-project/data-depression-psiloctr: Version 25.1.0",
                    "abstract": "A deposited analysis package for a psychedelic meta-analysis.",
                    "publication_type": "software",
                },
                "dataset_or_data_deposit",
            ),
            (
                {
                    "study_doi": "10.64239/pi-qt4702",
                    "study_title": "Efficacy and Safety of Ketamine vs Electroconvulsive Therapy",
                    "abstract": "An educational summary of a separately published meta-analysis.",
                    "publication_type": "report",
                },
                "commentary",
            ),
        )
        for paper, expected_format in cases:
            with self.subTest(doi=paper["study_doi"]):
                decision = before_model_exclusion_decision(paper)
                self.assertIsNotNone(decision)
                self.assertIn(expected_format, decision["matched_terms"])

    def test_exact_conference_namespaces_and_event_dois_are_excluded(self) -> None:
        cases = (
            ("10.3389/conf.fnins.2017.94.00109", "conference_abstract"),
            ("10.7490/f1000research.1111967.1", "conference_poster"),
            ("10.1186/1940-0640-10-s1-a33", "conference_abstract"),
            ("10.1186/1753-6561-8-s4-p10", "conference_abstract"),
            ("10.1136/annrheumdis-2021-eular.610", "conference_abstract"),
            ("10.1136/rapm-2022-esra.31", "conference_abstract"),
            ("10.1136/ejhpharm-2025-eahp.154", "conference_abstract"),
            ("10.1136/sextrans-2019-sti.42", "conference_abstract"),
            ("10.1136/sextrans-2015-052270.508", "conference_abstract"),
            ("10.17579/sepd2020p137", "conference_abstract"),
            ("10.1254/jpssuppl.95.0_1-o-011", "conference_abstract"),
            ("10.1096/fasebj.20.5.a1134-a", "conference_abstract"),
            ("10.1096/fasebj.2020.34.s1.05528", "conference_abstract"),
            ("10.1051/matecconf/202134205008", "conference_paper"),
            ("10.1088/1742-6596/1294/6/062029", "conference_paper"),
            ("10.1088/1757-899x/440/1/012045", "conference_paper"),
            ("10.30955/gnc2021.00473", "conference_paper"),
            ("10.32470/ccn.2019.1095-0", "conference_paper"),
            ("10.1016/s0924-9338(02)80848-3", "conference_abstract"),
            ("10.1016/s0924-9338(12)74024-5", "conference_abstract"),
            ("10.1016/s0924-9338(15)30016-x", "conference_abstract"),
        )
        for doi, expected_format in cases:
            with self.subTest(doi=doi):
                decision = before_model_exclusion_decision(
                    {
                        "study_doi": doi,
                        "study_title": "Psilocybin or ketamine research",
                        "abstract": "This provider-mislabeled record discusses an in-scope compound.",
                        "publication_type": "article",
                    }
                )
                self.assertIsNotNone(decision)
                self.assertIn(expected_format, decision["matched_terms"])

    def test_isbn_addressed_elsevier_entries_are_book_chapters(self) -> None:
        decision = before_model_exclusion_decision(
            {
                "study_doi": "10.1016/b978-0-12-420118-7.00012-3",
                "study_title": "Salvinorin A Analogs as Treatments for Cocaine Abuse",
                "abstract": qualifying_abstract(
                    "This book entry reviews otherwise in-scope salvinorin pharmacology."
                ),
                "publication_type": "Journal Article | Review",
            }
        )

        self.assertIsNotNone(decision)
        self.assertIn("book_chapter", decision["matched_terms"])

    def test_shared_publisher_conference_dois_require_venue_corroboration(self) -> None:
        cases = (
            (
                "10.1063/1.5091378",
                "AIP conference proceedings",
                "conference_paper",
            ),
            (
                "10.1109/ehb50910.2020.9280111",
                "2020 International Conference on e-Health and Bioengineering (EHB)",
                "conference_paper",
            ),
        )
        for doi, journal, expected_format in cases:
            with self.subTest(doi=doi):
                decision = before_model_exclusion_decision(
                    {
                        "study_doi": doi,
                        "study_title": "An otherwise in-scope conference study",
                        "abstract": qualifying_abstract(
                            "This proceedings contribution reports an in-scope compound."
                        ),
                        "publication_type": "article",
                        "study_journal": journal,
                    }
                )
                self.assertIsNotNone(decision)
                self.assertIn(expected_format, decision["matched_terms"])

        ordinary_aip = before_model_exclusion_decision(
            {
                "study_doi": "10.1063/1.5123456",
                "study_title": "Psilocybin receptor pharmacology",
                "abstract": qualifying_abstract(
                    "This journal article reports psilocybin receptor pharmacology."
                ),
                "publication_type": "journal-article",
                "study_journal": "The Journal of Chemical Physics",
            }
        )
        self.assertIsNone(ordinary_aip)

        ordinary_ieee = before_model_exclusion_decision(
            {
                "study_doi": "10.1109/jrproc.1931.222508",
                "study_title": "The Propagation of Short Radio Waves over the North Atlantic",
                "abstract": qualifying_abstract(
                    "This ordinary journal article appears in a periodical whose title contains Proceedings."
                ),
                "publication_type": "journal-article",
                "study_journal": "Proceedings of the IRE",
            }
        )
        self.assertIsNone(ordinary_ieee)

    def test_interconf_collection_namespace_requires_collection_venue(self) -> None:
        decision = before_model_exclusion_decision(
            {
                "study_doi": "10.51582/interconf.19-20.11.2022.023",
                "study_title": "A contribution to a dated scientific collection",
                "abstract": qualifying_abstract(
                    "This collection contribution discusses sedative medications."
                ),
                "publication_type": "journal-article",
                "study_journal": "InterConf",
            }
        )
        self.assertIsNotNone(decision)
        self.assertIn("conference_paper", decision["matched_terms"])

        unrelated_venue = before_model_exclusion_decision(
            {
                "study_doi": "10.51582/interconf.19-20.11.2022.023",
                "study_title": "A regular journal article",
                "abstract": qualifying_abstract("This article reports a ketamine experiment."),
                "publication_type": "journal-article",
                "study_journal": "Journal of Experimental Pharmacology",
            }
        )
        self.assertIsNone(unrelated_venue)

    def test_european_psychiatry_supplement_metadata_excludes_conference_abstracts(self) -> None:
        decision = before_model_exclusion_decision(
            {
                "study_doi": "10.1192/j.eurpsy.2025.414",
                "study_title": "Detection of dissociative states during esketamine administration",
                "abstract": qualifying_abstract(
                    "This meeting abstract reports outcomes during esketamine administration."
                ),
                "publication_type": "journal-article",
                "study_journal": "European Psychiatry",
                "journal_issue": "S1",
                "journal_pages": "S165-S165",
            }
        )
        self.assertIsNotNone(decision)
        self.assertIn("conference_abstract", decision["matched_terms"])

    def test_european_psychiatry_regular_issue_is_not_excluded_by_doi_suffix(self) -> None:
        for doi in ("10.1192/j.eurpsy.2025.10", "10.1192/j.eurpsy.2025.10096"):
            with self.subTest(doi=doi):
                decision = before_model_exclusion_decision(
                    {
                        "study_doi": doi,
                        "study_title": "A regular European Psychiatry research article",
                        "abstract": qualifying_abstract(
                            "This journal article reports a controlled ketamine study."
                        ),
                        "publication_type": "journal-article",
                        "study_journal": "European Psychiatry",
                        "journal_issue": "1",
                        "journal_pages": "",
                    }
                )
                self.assertIsNone(decision)

        for doi, issue, pages in (
            ("10.1016/j.eurpsy.2013.10.005", "7", "419-423"),
            ("10.1016/s0924-9338(01)00551-x", "2", "127-130"),
            ("10.1016/s0924-9338(99)00222-9", "8", "451-457"),
        ):
            with self.subTest(doi=doi):
                decision = before_model_exclusion_decision(
                    {
                        "study_doi": doi,
                        "study_title": "A regular European Psychiatry empirical article",
                        "abstract": qualifying_abstract(
                            "This full journal article reports an empirical ketamine experiment."
                        ),
                        "publication_type": "article",
                        "study_journal": "European Psychiatry",
                        "journal_issue": issue,
                        "journal_pages": pages,
                    }
                )
                self.assertIsNone(decision)

    def test_single_page_supplement_contribution_is_excluded_but_multi_page_article_is_not(self) -> None:
        supplement = before_model_exclusion_decision(
            {
                "study_doi": "10.1016/j.urols.2016.05.278",
                "study_title": "Ketamine cystitis conference contribution",
                "abstract": qualifying_abstract(
                    "This supplement contribution discusses ketamine cystitis."
                ),
                "publication_type": "journal-article",
                "study_journal": "Urological Science",
                "journal_issue": "2",
                "journal_pages": "S74",
            }
        )
        self.assertIsNotNone(supplement)
        self.assertIn("supplement_issue_contribution", supplement["matched_terms"])

        full_article = before_model_exclusion_decision(
            {
                "study_doi": "10.example/multipage-article",
                "study_title": "A full research article in a journal supplement",
                "abstract": qualifying_abstract(
                    "This controlled study reports a ketamine intervention and outcomes."
                ),
                "publication_type": "journal-article",
                "study_journal": "Journal of Clinical Research",
                "journal_issue": "S1",
                "journal_pages": "S74-S82",
            }
        )
        self.assertIsNone(full_article)

    def test_proceedings_publication_types_are_excluded(self) -> None:
        for publication_type in ("Conference Proceedings", "proceedings-article"):
            with self.subTest(publication_type=publication_type):
                decision = before_model_exclusion_decision(
                    {
                        "study_doi": "10.example/proceedings-item",
                        "study_title": "Ketamine conference contribution",
                        "abstract": qualifying_abstract(
                            "This proceedings contribution reports ketamine findings."
                        ),
                        "publication_type": publication_type,
                    }
                )
                self.assertIsNotNone(decision)
                self.assertIn("conference_paper", decision["matched_terms"])

    def test_conference_paper_publication_type_is_excluded(self) -> None:
        decision = before_model_exclusion_decision(
            {
                "study_doi": "10.52340/9789941519109.17",
                "study_title": "Psychedelic research presented at a conference",
                "abstract": qualifying_abstract(
                    "This conference paper reports an otherwise in-scope psychedelic study."
                ),
                "publication_type": "conference-paper",
            }
        )

        self.assertIsNotNone(decision)
        self.assertIn("conference_paper", decision["matched_terms"])

    def test_explicit_supplement_doi_tokens_are_excluded(self) -> None:
        cases = (
            "10.1096/fasebj.2019.33.1_supplement.666.1",
            "10.1200/jco.2022.40.16_suppl.12097",
            "10.1212/wnl.84.14_supplement.p3.013",
        )
        for doi in cases:
            with self.subTest(doi=doi):
                decision = before_model_exclusion_decision(
                    {
                        "study_doi": doi,
                        "study_title": "An otherwise in-scope psychedelic report",
                        "abstract": qualifying_abstract(
                            "This supplement contribution reports an in-scope psychedelic study."
                        ),
                        "publication_type": "article",
                    }
                )
                self.assertIsNotNone(decision)
                self.assertIn("supplement_issue_contribution", decision["matched_terms"])

    def test_literal_supplementary_objects_are_excluded(self) -> None:
        cases = (
            (
                "10.1158/1078-0432.22462848",
                "Supplementary Figures from an otherwise eligible article",
            ),
            (
                "10.16889/isomerdesign-1-supp",
                "PeakAL: Protons I Have Known and Loved. Supplementary Data",
            ),
        )
        for doi, title in cases:
            with self.subTest(doi=doi):
                decision = before_model_exclusion_decision(
                    {
                        "study_doi": doi,
                        "study_title": title,
                        "abstract": qualifying_abstract(
                            "This record contains figure captions and supporting data from another article."
                        ),
                        "publication_type": "supplementary-materials",
                    }
                )

                self.assertIsNotNone(decision)
                self.assertEqual(decision["action"], "exclude_non_evidence_artifact")

    def test_bad_supplementary_material_type_does_not_exclude_a_real_article(self) -> None:
        decision = before_model_exclusion_decision(
            {
                "study_doi": "10.30802/aalas-jaalas-25-142",
                "study_title": (
                    "Supplemental Oxygen Prevents Hypoxemia in Pigs Chemically Restrained "
                    "with Ketamine"
                ),
                "abstract": qualifying_abstract(
                    "This controlled animal study evaluated oxygen during ketamine restraint."
                ),
                "publication_type": "supplementary-materials",
            }
        )

        self.assertIsNone(decision)

    def test_numbered_title_with_meeting_proceedings_metadata_is_excluded(self) -> None:
        decision = before_model_exclusion_decision(
            {
                "study_doi": "10.example/meeting-item",
                "study_title": "31 - Ketamine treatment in resistant depression",
                "abstract": qualifying_abstract(
                    "This meeting item reports ketamine outcomes in resistant depression."
                ),
                "publication_type": "article",
                "study_journal": "Proceedings of the Annual Scientific Meeting",
            }
        )

        self.assertIsNotNone(decision)
        self.assertIn("numbered_title:31", decision["matched_terms"])

    def test_abstract_number_with_proceedings_metadata_is_excluded(self) -> None:
        decision = before_model_exclusion_decision(
            {
                "study_doi": "10.example/abstract-2437",
                "study_title": (
                    "Abstract 2437 Neuroplasticity in Alzheimer's Treatment: "
                    "The Impact of Psychedelic-Induced TrkB Activation"
                ),
                "abstract": qualifying_abstract(
                    "This conference contribution discusses a psychedelic mechanism."
                ),
                "publication_type": "article",
                "study_journal": "Proceedings of the Annual Scientific Meeting",
            }
        )

        self.assertIsNotNone(decision)
        self.assertIn("numbered_title:2437", decision["matched_terms"])

    def test_coded_title_with_conference_journal_metadata_is_excluded(self) -> None:
        decision = before_model_exclusion_decision(
            {
                "study_doi": "10.example/coded-poster",
                "study_title": "P.2.031 - Light potentiation of antidepressant medication",
                "abstract": qualifying_abstract(
                    "This poster contribution reports preclinical antidepressant evidence."
                ),
                "publication_type": "article",
                "study_journal": "European Psychiatry",
            }
        )

        self.assertIsNotNone(decision)
        self.assertIn("coded_conference_title:P.2.031", decision["matched_terms"])

    def test_epa_coded_title_with_conference_journal_metadata_is_excluded(self) -> None:
        decision = before_model_exclusion_decision(
            {
                "study_doi": "10.1016/s0924-9338(14)78251-3",
                "study_title": (
                    "EPA-0931 - Acute ketamine challenge effects on visual information processing"
                ),
                "abstract": qualifying_abstract(
                    "This meeting contribution reports acute ketamine effects."
                ),
                "publication_type": "journal-article",
                "study_journal": "European Psychiatry",
            }
        )

        self.assertIsNotNone(decision)
        self.assertIn("coded_conference_title:EPA-0931", decision["matched_terms"])

    def test_self_identified_theoretical_article_is_non_source_evidence(self) -> None:
        decision = before_model_exclusion_decision(
            {
                "study_doi": "10.example/theoretical-commentary",
                "study_title": "A new theoretical perspective",
                "abstract": qualifying_abstract(
                    "This theoretical article proposes a conceptual model without source data."
                ),
                "publication_type": "journal-article",
                "study_journal": "European Psychiatry",
            }
        )

        self.assertIsNotNone(decision)
        self.assertEqual(decision["action"], "exclude_non_evidence_artifact")

    def test_verified_elsevier_conference_collection_blocks_are_excluded(self) -> None:
        conference_dois = (
            "10.1016/j.nsa.2022.100152",
            "10.1016/j.nsa.2023.102939",
            "10.1016/j.nsa.2024.104280",
            "10.1016/j.nsa.2025.106728",
            "10.1016/j.ibneur.2023.08.531",
            "10.1016/j.etdah.2023.100092",
            "10.1016/j.etdah.2025.100242",
        )
        for doi in conference_dois:
            with self.subTest(doi=doi):
                decision = before_model_exclusion_decision(
                    {
                        "study_doi": doi,
                        "study_title": "In-scope conference contribution",
                        "abstract": "Psilocybin or ketamine was investigated.",
                        "publication_type": "article",
                    }
                )
                self.assertIsNotNone(decision)
                self.assertIn("conference_abstract", decision["matched_terms"])

    def test_conference_rules_do_not_blanket_exclude_same_publisher_articles(self) -> None:
        ordinary_articles = (
            "10.3389/fnins.2025.1554049",
            "10.12688/f1000research.12345.1",
            "10.1186/s12888-025-07000-1",
            "10.1136/annrheumdis-2021-220884",
            "10.1016/j.nsa.2022.101012",
            "10.1016/j.ibneur.2023.07.003",
            "10.1016/j.etdah.2025.100178",
            "10.1016/j.etdah.2025.100267",
        )
        for doi in ordinary_articles:
            with self.subTest(doi=doi):
                decision = before_model_exclusion_decision(
                    {
                        "study_doi": doi,
                        "study_title": "Psilocybin effects in a controlled study",
                        "abstract": "This full article reports psilocybin effects.",
                        "publication_type": "journal-article",
                    }
                )
                self.assertIsNone(decision)

    def test_book_metadata_is_excluded(self) -> None:
        decision = before_model_exclusion_decision(
            {
                "study_doi": "10.6027/tn2008-606",
                "study_title": "Occurrence and use of hallucinogenic mushrooms",
                "abstract": "A book-length report about psilocybin.",
                "publication_type": "book",
            }
        )
        self.assertIsNotNone(decision)
        self.assertIn("book_or_monograph", decision["matched_terms"])

    def test_bmj_coded_supplement_title_is_conference_abstract(self) -> None:
        decision = before_model_exclusion_decision(
            {
                "study_doi": "10.1136/sextrans-2015-052270.508",
                "study_title": "P13.10 Club drug use in sexual health clinic attendees",
                "abstract": "This abstract discusses drug use.",
                "publication_type": "article",
                "study_journal": "Sexually Transmitted Infections",
            }
        )
        self.assertIsNotNone(decision)
        self.assertIn("conference_abstract", decision["matched_terms"])

    def test_prescreen_uses_materialized_candidate_abstract_only(self) -> None:
        doi = "10.example/mismatched"
        papers = pd.DataFrame(
            [
                {
                    "doi": doi,
                    "study_title": "Prostate cancer review",
                    "abstract": qualifying_abstract("Correct prostate cancer biomarker abstract."),
                }
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-07-13T00:00:00+00:00",
        )

        self.assertEqual(rows[0]["prescreen_action"], "exclude_obvious_irrelevant")
        self.assertNotIn("MDMA", rows[0]["deterministic_supporting_quote"])

    def test_builds_one_decision_per_doi_from_materialized_candidate_metadata(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/psilo",
                    "study_title": "Psilocybin therapy for depression",
                    "abstract": qualifying_abstract("Psilocybin therapy reduced depression symptoms."),
                    "current_pipeline_status": "metadata_enriched",
                    "source_types": "metadata_enrichment",
                    "metadata_enrichment_status": "enriched",
                    "metadata_enrichment_run_id": "test_metadata",
                },
                {
                    "doi": "10.example/exercise",
                    "study_title": "Exercise intervention for depression",
                    "abstract": qualifying_abstract("This randomized trial tested exercise for depression."),
                    "current_pipeline_status": "metadata_enriched",
                    "source_types": "metadata_enrichment",
                },
            ]
        )
        contexts = pd.DataFrame(
            [
                {
                    "doi": "10.example/psilo",
                    "compound": "Psilocybin",
                    "entity": "Major depressive disorder",
                    "entity_type": "indication",
                }
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            contexts,
            run_id="test_run",
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )
        by_doi = {row["doi"]: row for row in rows}

        self.assertEqual(len(rows), 2)
        self.assertEqual(by_doi["10.example/psilo"]["study_title"], "Psilocybin therapy for depression")
        self.assertEqual(by_doi["10.example/psilo"]["prescreen_decision"], "retain")
        self.assertEqual(by_doi["10.example/psilo"]["metadata_enrichment_run_id"], "test_metadata")
        self.assertEqual(by_doi["10.example/exercise"]["prescreen_action"], "exclude_obvious_irrelevant")
        self.assertFalse(by_doi["10.example/exercise"]["retained_for_extraction_candidate"])


    def test_unusable_abstracts_use_conservative_title_only_rescue(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/placeholder",
                    "study_title": "Esketamine for Treatment-Resistant Depression",
                    "abstract": "International audience",
                    "current_pipeline_status": "metadata_enriched",
                    "source_types": "metadata_enrichment",
                },
                {
                    "doi": "10.example/citation-parenthetical",
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
            run_id="test_run",
            generated_at_utc="2026-05-30T00:00:00+00:00",
        )
        by_doi = {row["doi"]: row for row in rows}

        for doi in by_doi:
            self.assertFalse(by_doi[doi]["has_abstract"])

        for doi, row in by_doi.items():
            self.assertEqual(row["prescreen_decision"], "exclude", doi)
            self.assertEqual(row["prescreen_action"], "exclude_no_usable_abstract", doi)
            self.assertEqual(row["deterministic_action"], "exclude_no_usable_abstract", doi)
            self.assertFalse(row["retained_for_screening"], doi)
            self.assertFalse(row["retained_for_extraction_candidate"], doi)
            self.assertIn("title alone", row["prescreen_reason"], doi)

    def test_no_title_container_record_excluded_even_with_matching_abstract(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/issue",
                    "study_title": "",
                    "abstract": "Psilocybin was discussed in a neuroscience context.",
                    "publication_type": "journal-issue",
                }
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(rows[0]["prescreen_decision"], "exclude")
        self.assertEqual(rows[0]["prescreen_action"], "exclude_non_paper_container")
        self.assertFalse(rows[0]["retained_for_extraction_candidate"])

    def test_abstract_only_paper_is_screened_normally(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/abstract-only",
                    "study_title": "",
                    "abstract": qualifying_abstract(
                        "This study examined psilocybin effects in healthy participants."
                    ),
                    "publication_type": "Journal Article",
                }
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-07-16T00:00:00+00:00",
        )

        self.assertEqual(rows[0]["prescreen_action"], "retain_for_screening")
        self.assertTrue(rows[0]["has_abstract"])
        self.assertTrue(rows[0]["retained_for_screening"])

    def test_record_with_neither_title_nor_abstract_uses_no_usable_abstract_reason(self) -> None:
        papers = pd.DataFrame(
            [{"doi": "10.example/no-text", "study_title": "", "abstract": ""}]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-07-16T00:00:00+00:00",
        )

        self.assertEqual(rows[0]["prescreen_action"], "exclude_no_usable_abstract")
        self.assertIn("No usable title or abstract", rows[0]["prescreen_reason"])

    def test_abstract_below_50_words_is_excluded_as_unusable(self) -> None:
        abstract = " ".join(["psilocybin"] * (MINIMUM_ABSTRACT_WORD_COUNT - 1))
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/short-abstract",
                    "study_title": "Psilocybin effects in healthy participants",
                    "abstract": abstract,
                }
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-07-21T00:00:00+00:00",
        )

        self.assertEqual(abstract_word_count(abstract), 49)
        self.assertEqual(rows[0]["abstract_word_count"], 49)
        self.assertFalse(rows[0]["has_abstract"])
        self.assertEqual(rows[0]["prescreen_action"], "exclude_no_usable_abstract")
        self.assertIn("below the 50-word minimum", rows[0]["prescreen_reason"])

    def test_abstract_with_exactly_50_words_remains_eligible(self) -> None:
        abstract = " ".join(["psilocybin"] * MINIMUM_ABSTRACT_WORD_COUNT)
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/minimum-abstract",
                    "study_title": "Psilocybin effects in healthy participants",
                    "abstract": abstract,
                }
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-07-21T00:00:00+00:00",
        )

        self.assertEqual(rows[0]["abstract_word_count"], 50)
        self.assertTrue(rows[0]["has_abstract"])
        self.assertEqual(rows[0]["prescreen_action"], "retain_for_screening")

    def test_explicit_non_english_language_is_excluded_before_routing(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/non-english",
                    "study_title": "Ein deutschsprachiger Fachartikel",
                    "abstract": " ".join(["ketamin"] * MINIMUM_ABSTRACT_WORD_COUNT),
                    "language": "de",
                }
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-07-22T00:00:00+00:00",
        )

        self.assertEqual(rows[0]["prescreen_action"], "exclude_non_english_language")
        self.assertEqual(rows[0]["deterministic_matched_terms"], "de")
        self.assertFalse(rows[0]["retained_for_screening"])

    def test_english_or_missing_language_is_not_excluded_by_language_rule(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/english",
                    "study_title": "An English source",
                    "abstract": " ".join(["psilocybin"] * MINIMUM_ABSTRACT_WORD_COUNT),
                    "language": "eng",
                },
                {
                    "doi": "10.example/language-missing",
                    "study_title": "A source without language metadata",
                    "abstract": " ".join(["psilocybin"] * MINIMUM_ABSTRACT_WORD_COUNT),
                    "language": "",
                },
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-07-22T00:00:00+00:00",
        )

        self.assertEqual([row["prescreen_action"] for row in rows], ["retain_for_screening"] * 2)

    def test_non_evidence_artifacts_are_excluded_before_routing(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/correction",
                    "study_title": "Author Correction: MDMA-assisted therapy for PTSD",
                    "abstract": "MDMA-assisted therapy reduced PTSD symptoms.",
                    "publication_type": "Published Erratum",
                },
                {
                    "doi": "10.example/protocol",
                    "study_title": "Ketamine-Assisted Recovery: protocol for an open-label pilot trial",
                    "abstract": "This protocol describes ketamine-assisted psychotherapy for addiction.",
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.1002/jmv.26681",
                    "study_title": "Ketamine in COVID-19 patients: Thinking out of the box",
                    "abstract": "This letter speculates about ketamine use in COVID-19 patients.",
                    "publication_type": "Letter",
                },
                {
                    "doi": "10.1371/journal.pmed.1004519.g001",
                    "study_title": "Study flow chart.",
                    "abstract": "Psilocybin and MBSR were studied in health care workers.",
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.1021/acsptsci.5c00324.s001",
                    "study_title": "The Medial Prefrontal Cortex Modulates Psychedelic-like Effects of Psilocin",
                    "abstract": "Psilocin effects were tested in medial prefrontal cortex.",
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.6084/m9.figshare.24531073",
                    "study_title": "Spinogenesis Data - Prism file",
                    "abstract": "Psilocybin and ketamine spinogenesis data are provided.",
                    "publication_type": "Dataset",
                },
                {
                    "doi": "10.20944/preprints202305.2222.v1",
                    "study_title": "Microbiome: The Next Frontier in Psychedelic Renaissance",
                    "abstract": "This review discusses psychedelics and the microbiome.",
                    "publication_type": "posted-content",
                },
                {
                    "doi": "10.31219/osf.io/dy5cu_v1",
                    "study_title": "Legal and Regulatory Barriers to Medical Psilocybin Use",
                    "abstract": "This overview discusses medical psilocybin regulation.",
                    "publication_type": "article",
                },
                {
                    "doi": "10.3389/fnins.2025.1554049.s002",
                    "study_title": "Table 2_Dose-dependent changes in global brain activity following psilocybin.xlsx",
                    "abstract": "Dose-dependent brain activity and functional connectivity are reported.",
                    "publication_type": "dataset",
                },
                {
                    "doi": "10.64898/2026.04.16.718915",
                    "study_title": "Serotonergic Polypharmacology of 2-Halogenated Tryptamines",
                    "abstract": "Novel tryptamines were tested at serotonin receptors.",
                    "publication_type": "Journal Article | Preprint",
                },
                {
                    "doi": "10.example/case-letter",
                    "study_title": "MDMA intoxication: Acute psychosis caused by a designer drug",
                    "abstract": "This case report describes acute psychosis after MDMA exposure.",
                    "publication_type": "Case Reports | Letter",
                },
            ]
        )

        rows = build_prescreen_decisions(
            papers,
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
                    "study_title": "Novel psilocybin derivatives as serotonin 5-HT2A receptor agonists",
                    "abstract": qualifying_abstract(
                        "This study synthesized psilocybin derivatives and measured 5-HT2A receptor "
                        "binding affinity and functional signaling."
                    ),
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.example/production-mentioned-in-abstract",
                    "study_title": "Receptor pharmacology of biosynthesized psilocybin derivatives",
                    "abstract": qualifying_abstract(
                        "Compounds produced in engineered Escherichia coli were tested for 5-HT2A "
                        "binding affinity and functional signaling."
                    ),
                    "publication_type": "Journal Article",
                },
            ]
        )

        rows = build_prescreen_decisions(
            papers,
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
        self.assertEqual(
            by_doi["10.example/production-mentioned-in-abstract"]["prescreen_action"],
            "retain_for_screening",
        )

    def test_broad_nps_history_background_is_excluded_without_dropping_nps_pharmacology(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.1002/dta.319",
                    "study_title": "A brief history of ‘new psychoactive substances’",
                    "abstract": (
                        "This editorial introduces a special issue about legal highs and the adoption "
                        "of the term new psychoactive substances."
                    ),
                    "publication_type": "Editorial | Historical Article",
                },
                {
                    "doi": "10.example/nps-pharmacology",
                    "study_title": "Pharmacology of MDMA- and amphetamine-like new psychoactive substances",
                    "abstract": qualifying_abstract(
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
                    "study_title": "NMDA receptor modulators: an updated patent review",
                    "abstract": qualifying_abstract(
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
                    "study_title": "Psilocybin changes default mode network connectivity",
                    "abstract": qualifying_abstract(
                        "This study reports psilocybin effects on default mode network connectivity."
                    ),
                    "study_journal": "Journal of Psychopharmacology",
                    "publication_type": "Journal Article",
                },
            ]
        )

        rows = build_prescreen_decisions(
            papers,
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
                    "study_title": "2013 Annual Meeting of the North American Congress of Clinical Toxicology (NACCT)",
                    "abstract": "This annual meeting record includes ketamine-related abstracts.",
                    "study_journal": "Clinical Toxicology",
                    "publication_type": "article",
                },
                {
                    "doi": "10.example/5ht",
                    "study_title": "5-HT2A receptor signaling after psilocybin exposure",
                    "abstract": qualifying_abstract(
                        "This study reports psilocybin effects on 5-HT2A receptor signaling."
                    ),
                    "study_journal": "Journal of Psychopharmacology",
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.example/40hz",
                    "study_title": "40 Hz Auditory Steady-State Response Is a Pharmacodynamic Biomarker",
                    "abstract": qualifying_abstract(
                        "This study reports ketamine effects on 40 Hz auditory steady-state response."
                    ),
                    "study_journal": "Neuropsychopharmacology",
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.example/years",
                    "study_title": "5 Years of bipolar disorder conversations on Reddit: Methods and key topics",
                    "abstract": qualifying_abstract(
                        "This study reports ketamine discussions in bipolar disorder conversations."
                    ),
                    "study_journal": "PLoS ONE",
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.example/guideline",
                    "study_title": "2025 guideline update to acute treatment of migraine for adults",
                    "abstract": qualifying_abstract(
                        "This guideline discusses ketamine among acute treatment options."
                    ),
                    "study_journal": "Headache",
                    "publication_type": "Journal Article | Practice Guideline",
                },
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-07-07T00:00:00+00:00",
        )
        by_doi = {row["doi"]: row for row in rows}

        for doi in ("10.1093/ijnp/pyaf052.166", "10.1017/s1092852920000589", "10.3109/15563650.2013.817658"):
            self.assertEqual(by_doi[doi]["prescreen_decision"], "exclude")
            self.assertEqual(by_doi[doi]["prescreen_action"], "exclude_non_evidence_artifact")
            self.assertIn("conference", by_doi[doi]["prescreen_reason"])
            self.assertFalse(by_doi[doi]["retained_for_extraction_candidate"])

        for doi in ("10.example/5ht", "10.example/40hz", "10.example/years", "10.example/guideline"):
            self.assertEqual(by_doi[doi]["prescreen_decision"], "retain")
            self.assertTrue(by_doi[doi]["retained_for_extraction_candidate"])

    def test_publication_format_rules_exclude_unnumbered_abstracts_chapters_and_dissertations(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.1093/ijnp/pyae059.031",
                    "study_title": "SUBGROUP ANALYSIS OF ESKETAMINE OUTCOMES",
                    "abstract": "This conference abstract reports subgroup results.",
                    "study_journal": "International Journal of Neuropsychopharmacology",
                    "publication_type": "article",
                },
                {
                    "doi": "10.1007/7854_2023_453",
                    "study_title": "Ketamine for Major Depressive Disorder",
                    "abstract": "This chapter reviews ketamine for depression.",
                    "study_journal": "Current Topics in Behavioral Neurosciences",
                    "publication_type": "review",
                },
                {
                    "doi": "10.example/thesis",
                    "study_title": "Psilocybin and cortical plasticity",
                    "abstract": "This dissertation reports original experiments.",
                    "study_journal": "Institutional repository",
                    "publication_type": "dissertation",
                },
                {
                    "doi": "10.example/peer-object",
                    "study_title": "Author response for a ketamine treatment article",
                    "abstract": "The authors respond to reviewer comments.",
                    "study_journal": "Open peer review",
                    "publication_type": "peer-review",
                },
                {
                    "doi": "10.1017/dep.2025.10001.pr2",
                    "study_title": "Review: Real-world esketamine treatment",
                    "abstract": "This document contains a reviewer's comments.",
                    "study_journal": "Open peer review",
                    "publication_type": "journal-article",
                },
                {
                    "doi": "10.1093/sleep/32.11.1513",
                    "study_title": "Effects of acute MDMA on sleep and daytime sleepiness in MDMA users",
                    "abstract": qualifying_abstract(
                        "This full journal article reports original MDMA sleep outcomes across multiple pages."
                    ),
                    "study_journal": "SLEEP",
                    "publication_type": "journal-article",
                },
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-07-10T00:00:00+00:00",
        )
        by_doi = {row["doi"]: row for row in rows}

        for doi in (
            "10.1093/ijnp/pyae059.031",
            "10.1007/7854_2023_453",
            "10.example/thesis",
            "10.example/peer-object",
            "10.1017/dep.2025.10001.pr2",
        ):
            self.assertEqual(by_doi[doi]["prescreen_decision"], "exclude")
            self.assertEqual(by_doi[doi]["prescreen_action"], "exclude_non_evidence_artifact")
            self.assertFalse(by_doi[doi]["retained_for_extraction_candidate"])

        self.assertEqual(by_doi["10.1093/sleep/32.11.1513"]["prescreen_decision"], "retain")

    def test_commentary_dispatch_insight_and_conference_abstract_formats_are_excluded(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "doi": "10.example/dispatch",
                    "study_title": "Neuroimaging: a scanner, colourfully",
                    "abstract": "A dispatch discussing two recently published studies.",
                    "publication_type": "Dispatch",
                },
                {
                    "doi": "10.example/insight",
                    "study_title": "Serotonin, psychedelics and psychiatry",
                    "abstract": "An expert insight article proposing a conceptual position.",
                    "publication_type": "Insight Article",
                },
                {
                    "doi": "10.example/conference",
                    "study_title": "(417) Oral ketamine for chronic pain",
                    "abstract": "A meeting abstract reporting preliminary results.",
                    "publication_type": "Conference Abstract",
                },
                {
                    "doi": "10.example/review",
                    "study_title": "Ketamine and chronic pain: a systematic review",
                    "abstract": qualifying_abstract(
                        "This systematic review searched databases and synthesized eligible studies."
                    ),
                    "publication_type": "Journal Article | Review",
                },
            ]
        )

        rows = build_prescreen_decisions(
            papers,
            pd.DataFrame(),
            run_id="test_run",
            generated_at_utc="2026-07-10T00:00:00+00:00",
        )
        by_doi = {row["doi"]: row for row in rows}

        for doi in ("10.example/dispatch", "10.example/insight", "10.example/conference"):
            self.assertEqual(by_doi[doi]["prescreen_action"], "exclude_non_evidence_artifact")
            self.assertFalse(by_doi[doi]["retained_for_extraction_candidate"])
        self.assertTrue(by_doi["10.example/review"]["retained_for_extraction_candidate"])

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
                        "study_title": "Psilocybin therapy for depression",
                        "abstract": qualifying_abstract("Psilocybin therapy reduced depression symptoms."),
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
            written_summary = pd.read_parquet(summary_path)
            self.assertIn("scope", written_summary.columns)

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
                        "study_title": "Psilocybin therapy for depression",
                        "abstract": qualifying_abstract("Psilocybin therapy reduced depression symptoms."),
                    },
                    {
                        "doi": "10.example/exercise",
                        "study_title": "Exercise intervention for depression",
                        "abstract": qualifying_abstract("This randomized trial tested exercise for depression."),
                    },
                ]
            ).to_parquet(papers_path, index=False)
            pd.DataFrame(
                [
                    {
                        "doi": "10.example/psilo",
                        "study_title": "Psilocybin therapy for depression",
                        "abstract": qualifying_abstract("Psilocybin therapy reduced depression symptoms."),
                        "metadata_enrichment_status": "enriched",
                    }
                ]
            ).to_parquet(metadata_path, index=False)
            pd.DataFrame([]).to_parquet(contexts_path, index=False)
            pd.DataFrame(
                [
                    {
                        "table_version": TABLE_VERSION,
                        "run_id": "existing_prescreen_run",
                        "generated_at_utc": "old",
                        "prescreen_decision_id": "old-psilo",
                        "doi": "10.example/psilo",
                        "has_abstract": False,
                        "prescreen_decision": "exclude",
                        "prescreen_action": "exclude_missing_abstract",
                        "deterministic_action": "exclude_missing_abstract",
                        "routing_tags": "",
                    },
                    {
                        "table_version": TABLE_VERSION,
                        "run_id": "existing_prescreen_run",
                        "generated_at_utc": "old",
                        "prescreen_decision_id": "old-exercise",
                        "doi": "10.example/exercise",
                        "has_abstract": True,
                        "prescreen_decision": "retain",
                        "prescreen_action": "retain_for_screening",
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
        self.assertEqual(by_doi["10.example/psilo"]["prescreen_action"], "retain_for_screening")
        self.assertEqual(by_doi["10.example/exercise"]["prescreen_decision_id"], "old-exercise")
        self.assertEqual(by_doi["10.example/exercise"]["prescreen_action"], "retain_for_screening")

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
                        "study_title": "Existing paper",
                        "abstract": qualifying_abstract("Psilocybin therapy reduced depression symptoms."),
                    },
                    {
                        "doi": "10.example/new",
                        "study_title": "New psilocybin paper",
                        "abstract": qualifying_abstract(
                            "Psilocybin therapy was evaluated for depression symptoms."
                        ),
                    },
                ]
            ).to_parquet(papers_path, index=False)
            pd.DataFrame([]).to_parquet(metadata_path, index=False)
            pd.DataFrame([]).to_parquet(contexts_path, index=False)
            pd.DataFrame(
                [
                    {
                        "table_version": TABLE_VERSION,
                        "run_id": "existing_prescreen_run",
                        "generated_at_utc": "old",
                        "prescreen_decision_id": "old-existing",
                        "doi": "10.example/existing",
                        "has_abstract": True,
                        "prescreen_decision": "retain",
                        "prescreen_action": "retain_for_screening",
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
        self.assertEqual(by_doi["10.example/new"]["prescreen_action"], "retain_for_screening")

    def test_scoped_update_does_not_reset_unrequested_excluded_candidates(self) -> None:
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
                        "doi": "10.example/update",
                        "study_title": "Psilocybin conference record",
                        "abstract": "",
                        "prescreen_retained_for_extraction_candidate": True,
                        "extraction_route_status": "ready",
                    },
                    {
                        "doi": "10.example/unrequested",
                        "study_title": "Previously excluded record",
                        "abstract": "",
                        "prescreen_retained_for_extraction_candidate": False,
                        "extraction_route_status": "historical_value_must_remain",
                    },
                ]
            ).to_parquet(papers_path, index=False)
            pd.DataFrame([]).to_parquet(metadata_path, index=False)
            pd.DataFrame([]).to_parquet(contexts_path, index=False)
            pd.DataFrame(
                [
                    {
                        "table_version": TABLE_VERSION,
                        "run_id": "existing_prescreen_run",
                        "generated_at_utc": "old",
                        "prescreen_decision_id": "old-update",
                        "doi": "10.example/update",
                        "has_abstract": True,
                        "prescreen_decision": "retain",
                        "prescreen_action": "retain_for_screening",
                        "deterministic_action": "escalate",
                    },
                    {
                        "table_version": TABLE_VERSION,
                        "run_id": "existing_prescreen_run",
                        "generated_at_utc": "old",
                        "prescreen_decision_id": "old-unrequested",
                        "doi": "10.example/unrequested",
                        "has_abstract": False,
                        "prescreen_decision": "exclude",
                        "prescreen_action": "exclude_no_usable_abstract",
                        "deterministic_action": "exclude_no_usable_abstract",
                    },
                ]
            ).to_parquet(decisions_path, index=False)

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
                    "doi_file": "",
                    "doi": ["10.example/update"],
                    "progress_every": 0,
                },
            )()

            run(args)
            candidates = pd.read_parquet(papers_path).set_index("doi")

        self.assertEqual(candidates.loc["10.example/update", "extraction_route_status"], "")
        self.assertEqual(
            candidates.loc["10.example/unrequested", "extraction_route_status"],
            "historical_value_must_remain",
        )

    def test_scoped_update_rejects_an_older_prescreen_schema(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            papers_path = root / "candidate_papers.parquet"
            metadata_path = root / "paper_metadata_enrichment.parquet"
            contexts_path = root / "candidate_contexts.parquet"
            decisions_path = root / "paper_prescreen_decisions.parquet"
            summary_path = root / "paper_prescreen_summary.parquet"

            pd.DataFrame(
                [{"doi": "10.example/paper", "study_title": "Psilocybin study", "abstract": ""}]
            ).to_parquet(papers_path, index=False)
            pd.DataFrame([]).to_parquet(metadata_path, index=False)
            pd.DataFrame([]).to_parquet(contexts_path, index=False)
            pd.DataFrame(
                [
                    {
                        "table_version": "0.1",
                        "run_id": "old_run",
                        "doi": "10.example/paper",
                        "prescreen_decision": "exclude",
                    }
                ]
            ).to_parquet(decisions_path, index=False)

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
                    "doi_file": "",
                    "doi": ["10.example/paper"],
                    "progress_every": 0,
                },
            )()

            with self.assertRaisesRegex(SystemExit, "Run one full deterministic pre-screen pass first"):
                run(args)

    def test_summary_counts_screening_actions_without_routing_metrics(self) -> None:
        decisions = [
            {
                "doi": "10.example/a",
                "has_abstract": True,
                "prescreen_decision": "retain",
                "prescreen_action": "retain_for_screening",
                "deterministic_action": "escalate",
            },
            {
                "doi": "10.example/b",
                "has_abstract": False,
                "prescreen_decision": "exclude",
                "prescreen_action": "exclude_no_usable_abstract",
                "deterministic_action": "exclude_no_usable_abstract",
            },
        ]

        summary = build_summary_rows(decisions, run_id="test_run", generated_at_utc="now")
        keyed = {(row["scope"], row["metric"], row["label"]): row["count"] for row in summary}

        self.assertEqual(keyed[("all_papers", "prescreen_decision", "retain")], 1)
        self.assertEqual(keyed[("all_papers", "prescreen_action", "exclude_no_usable_abstract")], 1)
        self.assertFalse(any(metric == "routing_tag" for _, metric, _ in keyed))
        self.assertEqual(keyed[("all_papers", "abstract", "missing")], 1)

    def test_run_reconciles_candidate_and_declared_active_downstream_views(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            papers_path = root / "candidate_papers.parquet"
            metadata_path = root / "paper_metadata_enrichment.parquet"
            contexts_path = root / "candidate_contexts.parquet"
            decisions_path = root / "paper_prescreen_decisions.parquet"
            summary_path = root / "paper_prescreen_summary.parquet"
            routing_path = root / "paper_domain_routing_gemini.parquet"
            extraction_path = root / "paper_extraction_routes.parquet"
            tasks_path = root / "route_extraction_tasks.jsonl"
            report_path = root / "reconciliation.json"
            pd.DataFrame(
                [
                    {
                        "doi": "10.example/retain",
                        "study_title": "Psilocybin trial",
                        "abstract": qualifying_abstract("Psilocybin therapy reduced depression symptoms."),
                        "prescreen_retained_for_extraction_candidate": True,
                        "extraction_route_status": "ready",
                        "graph_inclusion_status": "represented",
                    },
                    {
                        "doi": "10.example/exclude",
                        "study_title": "Exercise intervention",
                        "abstract": qualifying_abstract(
                            "This randomized trial evaluated exercise for depression symptoms."
                        ),
                        "prescreen_retained_for_extraction_candidate": True,
                        "extraction_route_status": "ready",
                        "graph_inclusion_status": "represented",
                    },
                ]
            ).to_parquet(papers_path, index=False)
            pd.DataFrame([]).to_parquet(metadata_path, index=False)
            pd.DataFrame([]).to_parquet(contexts_path, index=False)
            pd.DataFrame(
                [
                    {"doi": "10.example/retain", "screening_decision": "include_in_scope"},
                    {"doi": "10.example/exclude", "screening_decision": "include_in_scope"},
                ]
            ).to_parquet(routing_path, index=False)
            pd.DataFrame(
                [
                    {"doi": "10.example/retain", "route_action": "extract"},
                    {"doi": "10.example/exclude", "route_action": "extract"},
                ]
            ).to_parquet(extraction_path, index=False)
            tasks_path.write_text(
                '{"study_doi":"10.example/retain"}\n'
                '{"study_doi":"10.example/exclude"}\n',
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "papers_table": str(papers_path),
                    "metadata_table": str(metadata_path),
                    "contexts_table": str(contexts_path),
                    "decisions_table": str(decisions_path),
                    "summary_table": str(summary_path),
                    "previous_candidate_table": "",
                    "domain_routing_table": str(routing_path),
                    "extraction_routes_table": str(extraction_path),
                    "extraction_tasks_jsonl": str(tasks_path),
                    "reconciliation_report": str(report_path),
                    "run_id": "test_reconciliation",
                    "doi_file": "",
                    "doi": [],
                    "progress_every": 0,
                },
            )()

            run(args)
            candidates = pd.read_parquet(papers_path).set_index("doi")
            routes = pd.read_parquet(routing_path)
            extraction = pd.read_parquet(extraction_path)
            tasks_text = tasks_path.read_text(encoding="utf-8")
            report_exists = report_path.exists()

        self.assertEqual(candidates.loc["10.example/retain", "extraction_route_status"], "ready")
        self.assertEqual(candidates.loc["10.example/retain", "graph_inclusion_status"], "represented")
        self.assertEqual(candidates.loc["10.example/exclude", "extraction_route_status"], "")
        self.assertEqual(candidates.loc["10.example/exclude", "graph_inclusion_status"], "")
        self.assertEqual(routes["doi"].tolist(), ["10.example/retain"])
        self.assertEqual(extraction["doi"].tolist(), ["10.example/retain"])
        self.assertEqual(tasks_text, '{"study_doi":"10.example/retain"}\n')
        self.assertTrue(report_exists)


if __name__ == "__main__":
    unittest.main()
