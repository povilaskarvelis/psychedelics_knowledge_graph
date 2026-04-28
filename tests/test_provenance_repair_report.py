import json
import tempfile
import unittest
from pathlib import Path

from pipeline.fulltext.build_provenance_repair_report import (
    build_report,
    candidate_terms,
    evidence_section_status,
    has_review_signal,
    infer_evidence_location,
    is_non_primary_triaged,
    is_stale_fulltext_locator,
    relation_context_matched,
    score_section,
)
from pipeline.fulltext.convert_pdfs import doi_to_slug


class ProvenanceRepairReportTest(unittest.TestCase):
    def test_is_stale_fulltext_locator_requires_full_text_seen_and_abstract_snippet(self) -> None:
        self.assertTrue(
            is_stale_fulltext_locator(
                {"access_level": "full_text_seen", "evidence_locator": "Abstract snippet: trial result"}
            )
        )
        self.assertFalse(
            is_stale_fulltext_locator(
                {"access_level": "abstract_only", "evidence_locator": "Abstract snippet: trial result"}
            )
        )
        self.assertFalse(
            is_stale_fulltext_locator(
                {"access_level": "full_text_seen", "evidence_locator": "Results section snippet: trial result"}
            )
        )

    def test_is_non_primary_triaged_uses_source_and_paper_type(self) -> None:
        self.assertTrue(is_non_primary_triaged({"source_type": "secondary_evidence"}))
        self.assertTrue(is_non_primary_triaged({"paper_type": "commentary"}))
        self.assertFalse(is_non_primary_triaged({"source_type": "primary_study", "paper_type": "case_report"}))
        self.assertFalse(is_non_primary_triaged({"source_type": "primary_study", "paper_type": "primary_results"}))

    def test_candidate_terms_include_disorder_synonyms_and_outcome_fields(self) -> None:
        terms = candidate_terms(
            "disorder",
            {
                "compound": "Psilocybin",
                "disorder": "Major depressive disorder",
                "outcome_type": "reduces depressive symptoms",
                "outcome_measure": "MADRS",
            },
            "disorder",
        )

        self.assertEqual(terms["psilocybin"], 4)
        self.assertEqual(terms["major depressive disorder"], 4)
        self.assertIn("depression", terms)
        self.assertEqual(terms["madrs"], 4)

    def test_score_section_prefers_results_with_matching_terms(self) -> None:
        terms = {"psilocybin": 4, "madrs": 4}

        score, reasons = score_section(
            {"heading": "Results", "snippet": "MADRS scores improved after psilocybin therapy."},
            terms,
        )

        self.assertGreaterEqual(score, 13)
        self.assertTrue(any("heading contains `results`" in reason for reason in reasons))

    def test_relation_context_requires_compound_and_entity(self) -> None:
        matched, reasons = relation_context_matched(
            "disorder",
            {"compound": "Ketamine", "disorder": "Major depressive disorder"},
            {"heading": "KeyPoints", "snippet": "Ketamine improved postoperative sleep disturbance."},
            "disorder",
        )

        self.assertFalse(matched)
        self.assertEqual(reasons, ["compound context matched"])

    def test_review_signal_detects_systematic_review_artifact(self) -> None:
        self.assertTrue(
            has_review_signal(
                {"study_title": "Acute Adverse Effects of Psilocybin A Systematic Review and Meta-Analysis"},
                {"sections": [{"heading": "Methods", "snippet": "This review followed PRISMA guidance."}]},
            )
        )

    def test_review_signal_ignores_background_mentions(self) -> None:
        self.assertFalse(
            has_review_signal(
                {"study_title": "Psychedelic effects of psilocybin correlate with receptor occupancy"},
                {
                    "sections": [
                        {
                            "heading": "Introduction",
                            "snippet": "A previous systematic review summarized adverse events in related trials.",
                        }
                    ]
                },
            )
        )

    def test_review_signal_detects_fused_meta_analysis_heading(self) -> None:
        self.assertTrue(
            has_review_signal(
                {"study_title": "Control Group Outcomes in Trials of Psilocybin"},
                {
                    "sections": [
                        {
                            "heading": "Control Group Outcomes in Trials of Psilocybin AMeta-Analysis",
                            "snippet": "authors",
                        }
                    ]
                },
            )
        )

    def test_infer_evidence_location_from_heading(self) -> None:
        self.assertEqual(infer_evidence_location("Table 2"), "table")
        self.assertEqual(infer_evidence_location("Figure 1"), "figure")
        self.assertEqual(infer_evidence_location("Abstract"), "abstract")
        self.assertEqual(infer_evidence_location("Results"), "text")

    def test_evidence_section_status_rejects_abstract_and_boilerplate(self) -> None:
        self.assertFalse(evidence_section_status("disorder", {"heading": "Abstract", "snippet": "Result"})[0])
        self.assertFalse(evidence_section_status("mechanistic", {"heading": "KEYWORDS", "snippet": "LSD 5-HT2A"})[0])
        self.assertFalse(evidence_section_status("mechanistic", {"heading": "ACCESS", "snippet": "LSD 5-HT2A"})[0])
        self.assertFalse(evidence_section_status("mechanistic", {"heading": "Discussion", "snippet": "LSD 5-HT2A"})[0])
        self.assertTrue(evidence_section_status("mechanistic", {"heading": "Receptor binding", "snippet": "LSD 5-HT2A Ki"})[0])

    def test_evidence_section_status_rejects_article_title_heading(self) -> None:
        ok, reasons = evidence_section_status(
            "disorder",
            {
                "heading": "Treating Bipolar Depression Using Psilocybin-Validity Threats Regarding Efficacy and Safety",
                "snippet": "authors",
            },
            study_title="Treating Bipolar Depression Using Psilocybin-Validity Threats Regarding Efficacy and Safety",
        )

        self.assertFalse(ok)
        self.assertIn("article title", reasons[0])

    def test_evidence_section_status_rejects_markup_variant_of_article_title(self) -> None:
        ok, reasons = evidence_section_status(
            "mechanistic",
            {
                "heading": (
                    "Synergistic depression of NMDA receptor-mediated transmission by ketamine, "
                    "ketoprofen and L-NAME combinations in neonatal rat spinal cords in vitro"
                ),
                "snippet": "authors",
            },
            study_title=(
                "Synergistic depression of NMDA receptor-mediated transmission by ketamine, "
                "ketoprofen and<scp>L</scp>-NAME combinations in neonatal rat spinal cords<i>in vitro</i>"
            ),
        )

        self.assertFalse(ok)
        self.assertIn("article title", reasons[0])

    def test_build_report_proposes_locator_when_artifact_has_matching_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            doi = "10.1000/example"
            artifact_path = artifact_dir / f"{doi_to_slug(doi)}.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "best_backend": "docling",
                        "extractions": [
                            {
                                "backend": "docling",
                                "status": "ok",
                                "sections": [
                                    {
                                        "heading": "Results",
                                        "char_count": 80,
                                        "snippet": "Psilocybin improved MADRS depressive symptoms in participants.",
                                    }
                                ],
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            curated_rows = [
                {
                    "study_doi": doi,
                    "compound": "Psilocybin",
                    "disorder": "Major depressive disorder",
                    "outcome_measure": "MADRS",
                    "outcome_type": "reduces depressive symptoms",
                    "access_level": "full_text_seen",
                    "evidence_location": "abstract",
                    "evidence_locator": "Abstract snippet: trial result",
                    "study_title": "Example trial",
                }
            ]

            report = build_report("disorder", curated_rows, artifact_dir=artifact_dir, min_score=7)

        self.assertEqual(report["counts"]["propose_locator_repair"], 1)
        self.assertEqual(report["rows"][0]["action"], "propose_locator_repair")
        self.assertEqual(report["rows"][0]["proposed_evidence_location"], "text")
        self.assertIn("Full text section `Results`", report["rows"][0]["proposed_evidence_locator"])

    def test_build_report_does_not_repair_from_abstract_only_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            doi = "10.1000/abstract-only"
            artifact_path = artifact_dir / f"{doi_to_slug(doi)}.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "best_backend": "docling",
                        "extractions": [
                            {
                                "backend": "docling",
                                "status": "ok",
                                "sections": [
                                    {
                                        "heading": "Abstract",
                                        "char_count": 80,
                                        "snippet": "Psilocybin improved MADRS depressive symptoms in participants.",
                                    }
                                ],
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = build_report(
                "disorder",
                [
                    {
                        "study_doi": doi,
                        "compound": "Psilocybin",
                        "disorder": "Major depressive disorder",
                        "outcome_measure": "MADRS",
                        "access_level": "full_text_seen",
                        "evidence_locator": "Abstract snippet: trial result",
                    }
                ],
                artifact_dir=artifact_dir,
                min_score=7,
            )

        self.assertEqual(report["counts"]["propose_locator_repair"], 0)
        self.assertEqual(report["rows"][0]["action"], "needs_manual_review")
        self.assertIn("abstract section cannot repair", report["rows"][0]["reason"])

    def test_build_report_prefers_results_over_keyword_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            doi = "10.1000/results-over-keywords"
            artifact_path = artifact_dir / f"{doi_to_slug(doi)}.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "best_backend": "docling",
                        "extractions": [
                            {
                                "backend": "docling",
                                "status": "ok",
                                "sections": [
                                    {
                                        "heading": "KEYWORDS",
                                        "char_count": 30,
                                        "snippet": "Psilocybin major depressive disorder MADRS",
                                    },
                                    {
                                        "heading": "Results",
                                        "char_count": 80,
                                        "snippet": "Psilocybin improved MADRS scores in major depressive disorder.",
                                    },
                                ],
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = build_report(
                "disorder",
                [
                    {
                        "study_doi": doi,
                        "compound": "Psilocybin",
                        "disorder": "Major depressive disorder",
                        "outcome_measure": "MADRS",
                        "access_level": "full_text_seen",
                        "evidence_locator": "Abstract snippet: trial result",
                    }
                ],
                artifact_dir=artifact_dir,
                min_score=7,
            )

        self.assertEqual(report["rows"][0]["action"], "propose_locator_repair")
        self.assertEqual(report["rows"][0]["section_heading"], "Results")

    def test_build_report_marks_missing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report = build_report(
                "mechanistic",
                [
                    {
                        "study_doi": "10.1000/missing",
                        "compound": "LSD",
                        "target": "5-HT2A",
                        "access_level": "full_text_seen",
                        "evidence_locator": "Abstract snippet: binding",
                    }
                ],
                artifact_dir=Path(tmpdir),
                min_score=7,
            )

        self.assertEqual(report["counts"]["needs_fulltext_artifact"], 1)
        self.assertEqual(report["rows"][0]["action"], "needs_fulltext_artifact")

    def test_build_report_marks_failed_artifact_as_still_needing_fulltext(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            doi = "10.1000/failed"
            artifact_path = artifact_dir / f"{doi_to_slug(doi)}.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "best_backend": "",
                        "extractions": [
                            {"backend": "grobid", "status": "unavailable", "error": "connection reset"}
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = build_report(
                "mechanistic",
                [
                    {
                        "study_doi": doi,
                        "compound": "LSD",
                        "target": "5-HT2A",
                        "access_level": "full_text_seen",
                        "evidence_locator": "Abstract snippet: binding",
                    }
                ],
                artifact_dir=artifact_dir,
                min_score=7,
            )

        self.assertEqual(report["counts"]["needs_fulltext_artifact"], 1)
        self.assertEqual(report["rows"][0]["action"], "needs_fulltext_artifact")
        self.assertIn("no successful extraction", report["rows"][0]["reason"])

    def test_build_report_flags_review_signal_for_demotion_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            doi = "10.1000/review"
            artifact_path = artifact_dir / f"{doi_to_slug(doi)}.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "best_backend": "docling",
                        "extractions": [
                            {
                                "backend": "docling",
                                "status": "ok",
                                "sections": [
                                    {
                                        "heading": "Methods",
                                        "char_count": 80,
                                        "snippet": "This systematic review followed PRISMA reporting guidance.",
                                    }
                                ],
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = build_report(
                "disorder",
                [
                    {
                        "study_doi": doi,
                        "compound": "Psilocybin",
                        "disorder": "Major depressive disorder",
                        "access_level": "full_text_seen",
                        "evidence_locator": "Abstract snippet: review result",
                        "study_title": "Psilocybin for Depression: A Systematic Review",
                    }
                ],
                artifact_dir=artifact_dir,
                min_score=7,
            )

        self.assertEqual(report["counts"]["needs_demotion_review"], 1)
        self.assertEqual(report["rows"][0]["action"], "needs_demotion_review")

    def test_build_report_skips_already_non_primary_triaged_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            doi = "10.1000/review"
            artifact_path = artifact_dir / f"{doi_to_slug(doi)}.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "best_backend": "grobid",
                        "extractions": [
                            {
                                "backend": "grobid",
                                "status": "ok",
                                "sections": [
                                    {
                                        "heading": "Methods",
                                        "char_count": 80,
                                        "snippet": "This systematic review followed PRISMA reporting guidance.",
                                    }
                                ],
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = build_report(
                "disorder",
                [
                    {
                        "study_doi": doi,
                        "compound": "Psilocybin",
                        "disorder": "Major depressive disorder",
                        "source_type": "secondary_evidence",
                        "paper_type": "systematic_review",
                        "access_level": "full_text_seen",
                        "evidence_locator": "Abstract snippet: review result",
                        "study_title": "Psilocybin for Depression: A Systematic Review",
                    }
                ],
                artifact_dir=artifact_dir,
                min_score=7,
            )

        self.assertEqual(report["counts"]["already_non_primary_triaged"], 1)
        self.assertEqual(report["counts"]["needs_demotion_review"], 0)
        self.assertEqual(report["rows"][0]["action"], "already_non_primary_triaged")


if __name__ == "__main__":
    unittest.main()
