import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.ingest.build_domain_reprocessing_queue import (
    build_domain_reprocessing_queue,
    module_scopes_to_tags,
)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def queue_dois(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [row[0] for row in csv.reader(handle) if row and not row[0].startswith("#")]


class BuildDomainReprocessingQueueTest(unittest.TestCase):
    def test_module_scope_maps_to_routing_tags(self) -> None:
        self.assertEqual(
            module_scopes_to_tags(["molecular_pathway", "clinical_safety"]),
            {"molecular_pathway", "safety", "clinical_outcome"},
        )

    def test_builds_ready_and_metadata_queues_for_rediscovered_dois(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rediscovered_csv = root / "rediscovered.csv"
            rediscovered_csv.write_text(
                "\n".join(
                    [
                        "line_no,doi,compound,entity,title,year,authors,existing_sources",
                        "1,10.5555/already,Psilocybin,Brain,Already,2020,A,mechanistic:paper_library",
                        "2,10.5555/reprocess,Psilocybin,Brain,Needs,2021,B,mechanistic:paper_library",
                        "3,10.5555/no-abstract,Psilocybin,Brain,No abstract,2022,C,mechanistic:paper_library",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            report_path = root / "screening.json"
            write_json(
                report_path,
                {
                    "rows": [
                        {
                            "flat": {
                                "study_doi": "10.5555/already",
                                "llm_relevance": "relevant",
                                "llm_routing_tags": "brain_system",
                            }
                        },
                        {
                            "flat": {
                                "study_doi": "10.5555/reprocess",
                                "llm_relevance": "relevant",
                            },
                            "adjudication": {"routing_tags": []},
                        },
                    ]
                },
            )
            manifest = root / "corpus_manifest.json"
            write_json(
                manifest,
                {
                    "datasets": {
                        "mechanistic": {
                            "screening_reports": [
                                {"run_id": "prior", "path": str(report_path), "include": True},
                            ]
                        }
                    }
                },
            )
            paper_db = root / "paper_library.json"
            write_json(
                paper_db,
                [
                    {
                        "study_doi": "10.5555/reprocess",
                        "study_title": "Needs reprocessing",
                        "study_year": "2021",
                        "authors": "B",
                        "abstract": "Psilocybin altered functional connectivity.",
                    },
                    {
                        "study_doi": "10.5555/no-abstract",
                        "study_title": "No abstract",
                        "study_year": "2022",
                        "authors": "C",
                        "abstract": "",
                    },
                ],
            )

            report = build_domain_reprocessing_queue(
                dataset="mechanistic",
                rediscovered_csvs=[rediscovered_csv],
                target_tags={"brain_system"},
                output_dir=root / "out",
                corpus_manifest=manifest,
                extra_paper_db_jsons=[paper_db],
                include_default_paper_sources=False,
            )

            self.assertEqual(report["counts"]["rediscovered_unique_dois"], 3)
            self.assertEqual(report["counts"]["already_domain_screened"], 1)
            self.assertEqual(report["counts"]["needs_domain_reprocessing"], 2)
            self.assertEqual(report["counts"]["ready_for_domain_screening"], 1)
            self.assertEqual(report["counts"]["needs_metadata_or_abstract"], 1)
            self.assertEqual(queue_dois(Path(report["outputs"]["ready_for_screening_queue"])), ["10.5555/reprocess"])
            self.assertEqual(queue_dois(Path(report["outputs"]["needs_metadata_or_abstract_queue"])), ["10.5555/no-abstract"])


if __name__ == "__main__":
    unittest.main()
