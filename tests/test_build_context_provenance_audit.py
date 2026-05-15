import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.validate.build_context_provenance_audit import build_audit


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class BuildContextProvenanceAuditTest(unittest.TestCase):
    def test_merges_paper_sources_and_context_provenance(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw = root / "data" / "raw"
            processed = root / "data" / "processed"
            curated = root / "data" / "curated"
            raw.mkdir(parents=True)

            (raw / "doi_queue.disorder.discovered.txt").write_text(
                "10.example/dmt,DMT,Major depressive disorder,DMT depression trial,2024,A. Author\n",
                encoding="utf-8",
            )
            write_json(
                processed / "paper_library_disorder.json",
                [
                    {
                        "study_doi": "https://doi.org/10.example/dmt",
                        "study_title": "The antidepressant effects of N,N-Dimethyltryptamine",
                        "study_year": "2024",
                        "contexts": [
                            {
                                "compound": "DMT",
                                "entity": "Major depressive disorder",
                            }
                        ],
                    }
                ],
            )
            write_json(
                curated / "disorder_claims.json",
                [
                    {
                        "study_doi": "10.example/dmt",
                        "compound": "DMT",
                        "disorder": "Major depressive disorder",
                        "study_title": "The antidepressant effects of N,N-Dimethyltryptamine",
                        "paper_type": "primary_results",
                        "source_type": "primary_study",
                        "access_level": "abstract_only",
                    }
                ],
            )

            audit = build_audit(root=root, datasets=["disorder"])

            self.assertEqual(audit["summary"]["paper_count"], 1)
            paper = audit["papers"][0]
            self.assertEqual(paper["doi"], "10.example/dmt")
            self.assertIn("discovery_queue", paper["source_types"])
            self.assertIn("paper_library", paper["source_types"])
            self.assertIn("curated_claim", paper["source_types"])

            context = audit["contexts"][0]
            self.assertEqual(context["verification_layer"], "verified_evidence")
            self.assertEqual(context["revalidation_status"], "verified_existing")
            self.assertFalse(context["flags"]["needs_revalidation"])
            self.assertIn("queue_discovered_context", context["context_sources"])
            self.assertIn("paper_library_context", context["context_sources"])
            self.assertIn("curated_claim", context["context_sources"])

    def test_flags_short_acronym_contexts_without_disambiguating_text(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            curated = root / "data" / "curated"
            write_json(
                curated / "disorder_claims.json",
                [
                    {
                        "study_doi": "10.example/noisy",
                        "compound": "DMT",
                        "disorder": "Major depressive disorder",
                        "study_title": "A 2-year observational study of disease-modifying therapies",
                        "paper_type": "primary_results",
                        "source_type": "primary_study",
                    }
                ],
            )

            audit = build_audit(root=root, datasets=["disorder"])

            context = audit["contexts"][0]
            self.assertTrue(context["flags"]["possible_acronym_collision"])
            self.assertTrue(context["flags"]["needs_revalidation"])
            self.assertEqual(context["revalidation_status"], "possible_noise")


if __name__ == "__main__":
    unittest.main()
