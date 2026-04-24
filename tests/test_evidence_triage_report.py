import json
import tempfile
import unittest
from pathlib import Path

from pipeline.fulltext.build_evidence_triage_report import build_report, classify_evidence, text_from_tei
from pipeline.fulltext.convert_pdfs import doi_to_slug


class EvidenceTriageReportTest(unittest.TestCase):
    def test_classify_systematic_review_from_title_and_methods(self) -> None:
        classification = classify_evidence(
            {"study_title": "Acute Adverse Effects of Psilocybin: A Systematic Review and Meta-Analysis"},
            {
                "text": "",
                "sections": [
                    {
                        "heading": "Methods",
                        "snippet": "We searched PubMed and Embase, followed PRISMA, and extracted data from included studies.",
                    }
                ],
            },
        )

        self.assertIn(classification["classification"], {"systematic_review", "meta_analysis"})
        self.assertGreaterEqual(classification["confidence"], 0.85)

    def test_classify_primary_trial_when_no_secondary_signal(self) -> None:
        classification = classify_evidence(
            {"study_title": "Randomized placebo controlled trial of psilocybin for depression"},
            {
                "text": "",
                "sections": [
                    {
                        "heading": "Results",
                        "snippet": "Participants were randomized to psilocybin or placebo and depression scores improved.",
                    }
                ],
            },
        )

        self.assertEqual(classification["classification"], "primary_study")

    def test_prisma_scanner_does_not_imply_systematic_review(self) -> None:
        classification = classify_evidence(
            {"study_title": "Psilocybin receptor occupancy imaging study"},
            {
                "text": "",
                "sections": [
                    {
                        "heading": "Methods",
                        "snippet": "High resolution images were acquired on a 3T Prisma scanner before PET analysis.",
                    },
                    {
                        "heading": "Results",
                        "snippet": "Receptor occupancy correlated with psilocin levels in participants.",
                    },
                ],
            },
        )

        self.assertEqual(classification["classification"], "primary_study")

    def test_text_from_tei_ignores_reference_back_matter(self) -> None:
        tei = """
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <text>
            <front><abstract><p>Primary trial abstract.</p></abstract></front>
            <body><div><head>Results</head><p>Participants improved.</p></div></body>
            <back><listBibl><biblStruct><analytic><title>A systematic review</title></analytic></biblStruct></listBibl></back>
          </text>
        </TEI>
        """

        text = text_from_tei(tei)

        self.assertIn("Primary trial abstract", text)
        self.assertNotIn("systematic review", text)

    def test_build_report_proposes_high_confidence_reclassification(self) -> None:
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
                                "text": "",
                                "sections": [
                                    {
                                        "heading": "Methods",
                                        "snippet": "This systematic review followed PRISMA guidance and included studies from PubMed.",
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
                        "study_title": "Psilocybin for Depression: A Systematic Review",
                        "compound": "Psilocybin",
                        "disorder": "Major depressive disorder",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "study_design": "randomized_controlled_trial",
                        "access_level": "full_text_seen",
                    }
                ],
                artifact_dir=artifact_dir,
                auto_confidence=0.85,
            )

        row = report["rows"][0]
        self.assertEqual(row["action"], "propose_source_reclassification")
        self.assertEqual(row["automation_status"], "auto_apply_eligible")
        self.assertEqual(row["target_source_type"], "secondary_evidence")

    def test_build_report_keeps_primary_study(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            doi = "10.1000/trial"
            artifact_path = artifact_dir / f"{doi_to_slug(doi)}.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "best_backend": "grobid",
                        "extractions": [
                            {
                                "backend": "grobid",
                                "status": "ok",
                                "text": "",
                                "sections": [
                                    {
                                        "heading": "Results",
                                        "snippet": "Participants were randomized to placebo controlled treatment.",
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
                        "study_title": "Randomized trial of psilocybin for depression",
                        "compound": "Psilocybin",
                        "disorder": "Major depressive disorder",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "study_design": "randomized_controlled_trial",
                        "access_level": "full_text_seen",
                    }
                ],
                artifact_dir=artifact_dir,
                auto_confidence=0.85,
            )

        self.assertEqual(report["rows"][0]["action"], "keep_primary")


if __name__ == "__main__":
    unittest.main()
