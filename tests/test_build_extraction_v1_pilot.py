import json
import tempfile
import unittest
from pathlib import Path

from pipeline.extract.build_extraction_v1_pilot import (
    PILOT_SCHEMA_VERSION,
    build_dataset_records,
    excluded_dataset_dois,
    fulltext_packets_path_for_dataset,
    is_non_article_artifact,
    route_hint_for_metadata,
    sample_sort_key,
    select_per_bucket,
)


class BuildExtractionV1PilotTest(unittest.TestCase):
    def test_fulltext_packets_path_for_dataset_uses_dataset_specific_override(self) -> None:
        args = type(
            "Args",
            (),
            {
                "mechanistic_fulltext_packets_jsonl": "/tmp/mech.jsonl",
                "disorder_fulltext_packets_jsonl": "/tmp/disorder.jsonl",
            },
        )()

        self.assertEqual(fulltext_packets_path_for_dataset(args, "mechanistic"), Path("/tmp/mech.jsonl").resolve())
        self.assertEqual(fulltext_packets_path_for_dataset(args, "disorder"), Path("/tmp/disorder.jsonl").resolve())

    def test_build_dataset_records_excludes_irrelevant_controls_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_jsonl = root / "disorder_extraction_candidates.jsonl"
            fulltext_jsonl = root / "disorder_fulltext_packets.jsonl"
            paper_library = root / "paper_library_disorder.json"
            manifest = root / "corpus_manifest.json"
            screening_report = root / "screening.json"

            candidates = [
                {
                    "study_doi": "10.1000/full",
                    "screening_summary": {"best_llm_relevance": "relevant", "screening_record_count": 1},
                    "readiness": {"status": "full_text_ready"},
                    "paper_metadata": {
                        "study_doi": "10.1000/full",
                        "study_title": "Full text trial",
                        "abstract": "Full abstract.",
                    },
                    "screening_records": [],
                },
                {
                    "study_doi": "10.1000/abstract",
                    "screening_summary": {"best_llm_relevance": "uncertain", "screening_record_count": 1},
                    "readiness": {"status": "abstract_only_needs_pdf_access"},
                    "paper_metadata": {
                        "study_doi": "10.1000/abstract",
                        "study_title": "Abstract trial",
                        "abstract": "Abstract only.",
                    },
                    "screening_records": [],
                },
                {
                    "study_doi": "10.1000/decision-letter",
                    "screening_summary": {"best_llm_relevance": "relevant", "screening_record_count": 1},
                    "readiness": {"status": "abstract_only_needs_pdf_access"},
                    "paper_metadata": {
                        "study_doi": "10.1000/decision-letter",
                        "study_title": "Decision letter: A trial",
                        "publication_type": "peer-review",
                        "abstract": "Peer review material.",
                    },
                    "screening_records": [],
                },
            ]
            candidate_jsonl.write_text("\n".join(json.dumps(row) for row in candidates) + "\n", encoding="utf-8")
            fulltext_jsonl.write_text(
                json.dumps(
                    {
                        "packet_id": "disorder:10.1000/full",
                        "dataset": "disorder",
                        "study_doi": "10.1000/full",
                        "paper_metadata": {"study_doi": "10.1000/full", "study_title": "Full text trial"},
                        "document_summary": {"chunk_count": 1},
                        "llm_chunks": [{"chunk_id": "C001", "text": "Psilocybin improved symptoms."}],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            paper_library.write_text(
                json.dumps(
                    [
                        {
                            "study_doi": "10.1000/nope",
                            "study_title": "Irrelevant abstract",
                            "abstract": "This paper is not about psychedelics.",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            screening_report.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "input_row": {
                                    "study_doi": "10.1000/nope",
                                    "study_title": "Irrelevant abstract",
                                    "abstract": "This paper is not about psychedelics.",
                                },
                                "adjudication": {"relevance": "irrelevant"},
                                "flat": {"status": "ok", "dataset": "disorder"},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            manifest.write_text(
                json.dumps(
                    {
                        "datasets": {
                            "disorder": {
                                "screening_reports": [
                                    {
                                        "run_id": "pilot_negative",
                                        "path": str(screening_report),
                                        "include": True,
                                    }
                                ]
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            records, summary = build_dataset_records(
                "disorder",
                candidate_jsonl=candidate_jsonl,
                fulltext_packets_jsonl=fulltext_jsonl,
                paper_library=paper_library,
                manifest_path=manifest,
                include_packet_content=False,
            )

        buckets = {row["bucket"] for row in records}
        self.assertEqual(summary["available_records"], 2)
        self.assertIn("full_text_relevant", buckets)
        self.assertIn("abstract_uncertain", buckets)
        self.assertNotIn("abstract_irrelevant", buckets)
        self.assertFalse(summary["inputs"]["include_irrelevant_controls"])
        self.assertTrue(all(row["schema_version"] == PILOT_SCHEMA_VERSION for row in records))
        self.assertTrue(all(row["extraction_contract"]["prompt_template"] == "docs/extraction_v1_prompt.md" for row in records))
        self.assertTrue(
            all(
                row["extraction_contract"]["dataset_prompt_templates"]["mechanistic"]
                == "docs/extraction_v1_mechanistic_prompt.md"
                for row in records
            )
        )
        self.assertTrue(
            all(
                row["extraction_contract"]["dataset_prompt_templates"]["disorder"]
                == "docs/extraction_v1_disorder_prompt.md"
                for row in records
            )
        )
        self.assertTrue(all("route_hint" in row for row in records))
        self.assertIn("available_by_route_hint", summary)
        self.assertNotIn("10.1000/decision-letter", {row["study_doi"] for row in records})

    def test_build_dataset_records_can_include_irrelevant_controls_for_calibration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_jsonl = root / "disorder_extraction_candidates.jsonl"
            fulltext_jsonl = root / "disorder_fulltext_packets.jsonl"
            paper_library = root / "paper_library_disorder.json"
            manifest = root / "corpus_manifest.json"
            screening_report = root / "screening.json"

            candidate_jsonl.write_text("", encoding="utf-8")
            fulltext_jsonl.write_text("", encoding="utf-8")
            paper_library.write_text(
                json.dumps(
                    [
                        {
                            "study_doi": "10.1000/nope",
                            "study_title": "Irrelevant abstract",
                            "abstract": "This paper is not about psychedelics.",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            screening_report.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "input_row": {
                                    "study_doi": "10.1000/nope",
                                    "study_title": "Irrelevant abstract",
                                    "abstract": "This paper is not about psychedelics.",
                                },
                                "adjudication": {"relevance": "irrelevant"},
                                "flat": {"status": "ok", "dataset": "disorder"},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            manifest.write_text(
                json.dumps(
                    {
                        "datasets": {
                            "disorder": {
                                "screening_reports": [
                                    {
                                        "run_id": "pilot_negative",
                                        "path": str(screening_report),
                                        "include": True,
                                    }
                                ]
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            records, summary = build_dataset_records(
                "disorder",
                candidate_jsonl=candidate_jsonl,
                fulltext_packets_jsonl=fulltext_jsonl,
                paper_library=paper_library,
                manifest_path=manifest,
                include_packet_content=False,
                include_irrelevant_controls=True,
            )

        self.assertEqual(summary["available_records"], 1)
        self.assertTrue(summary["inputs"]["include_irrelevant_controls"])
        self.assertEqual(records[0]["bucket"], "abstract_irrelevant")
        self.assertEqual(records[0]["expected_screening_relevance"], "irrelevant")

    def test_select_per_bucket_is_deterministic_and_deduplicates_dataset_doi(self) -> None:
        rows = [
            {"dataset": "disorder", "bucket": "abstract_relevant", "study_doi": "10.2", "paper_metadata": {"study_title": "B"}},
            {"dataset": "disorder", "bucket": "abstract_relevant", "study_doi": "10.1", "paper_metadata": {"study_title": "A"}},
            {"dataset": "disorder", "bucket": "full_text_relevant", "study_doi": "10.1", "paper_metadata": {"study_title": "A"}},
        ]

        selected, summary = select_per_bucket(rows, per_bucket=2)

        self.assertEqual([row["bucket"] for row in selected], ["full_text_relevant", "abstract_relevant"])
        self.assertEqual([row["study_doi"] for row in selected], ["10.1", "10.2"])
        self.assertEqual(summary["selected_records"], 2)

    def test_select_per_bucket_uses_stable_hash_sampling_within_bucket(self) -> None:
        rows = [
            {
                "dataset": "disorder",
                "bucket": "abstract_relevant",
                "study_doi": f"10.{idx}",
                "paper_metadata": {"study_title": f"Title {idx}"},
            }
            for idx in range(5)
        ]

        selected, summary = select_per_bucket(rows, per_bucket=1)
        expected = min(rows, key=sample_sort_key)

        self.assertEqual(selected, [expected])
        self.assertEqual(summary["selection_strategy"], "stable_hash_by_dataset_bucket")

    def test_excluded_dataset_dois_loads_pilot_jsonl_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "previous.jsonl"
            path.write_text(
                "\n".join(
                    json.dumps(row)
                    for row in [
                        {"dataset": "disorder", "study_doi": "https://doi.org/10.1000/A"},
                        {"dataset": "mechanistic", "study_doi": "10.1000/b"},
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            self.assertEqual(
                excluded_dataset_dois([path]),
                {("disorder", "10.1000/a"), ("mechanistic", "10.1000/b")},
            )

    def test_route_hint_uses_specific_metadata_before_title_fallback(self) -> None:
        self.assertEqual(
            route_hint_for_metadata({"publication_type": "Journal Article | Review", "study_title": "A trial"})["hint"],
            "likely_secondary",
        )
        self.assertEqual(
            route_hint_for_metadata({"publication_type": "Clinical Trial Protocol | Journal Article"})["hint"],
            "likely_context_only",
        )
        self.assertEqual(
            route_hint_for_metadata({"publication_type": "journal-article", "study_title": "A narrative review of psilocybin"})["hint"],
            "likely_secondary",
        )
        self.assertEqual(
            route_hint_for_metadata({"publication_type": "journal-article", "trial_registry_ids": "NCT123"})["hint"],
            "likely_primary",
        )
        peer_review = {"publication_type": "peer-review", "study_title": "Decision letter: A trial"}
        self.assertEqual(route_hint_for_metadata(peer_review)["hint"], "likely_context_only")
        self.assertTrue(is_non_article_artifact(peer_review))


if __name__ == "__main__":
    unittest.main()
