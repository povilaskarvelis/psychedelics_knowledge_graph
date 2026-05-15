import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.ingest.add_new_dois import add_new_dois, load_existing_dois


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_queue(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [row for row in csv.reader(handle) if row and not row[0].startswith("#")]


class AddNewDoisTest(unittest.TestCase):
    def test_adds_only_dois_not_already_known_globally(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_json(
                root / "data" / "processed" / "candidate_paper_corpus.json",
                {"records": [{"doi": "10.1000/existing-corpus"}]},
            )
            write_json(
                root / "data" / "processed" / "discovery_ledger_mechanistic.json",
                {"dataset": "mechanistic", "entries": [{"doi": "10.1000/existing-ledger"}]},
            )
            write_json(
                root / "data" / "processed" / "paper_library_disorder.json",
                [{"study_doi": "10.1000/existing-other-dataset"}],
            )

            input_path = root / "incoming.csv"
            input_path.write_text(
                "\n".join(
                    [
                        "# doi,compound,target,title,year",
                        "doi,compound,target,title,year",
                        "https://doi.org/10.1000/existing-corpus,Psilocybin,5-HT2A,Known corpus,2020",
                        "10.1000/existing-other-dataset,LSD,5-HT2A,Known elsewhere,2021",
                        "10.1000/new-one,MDMA,SERT,New paper,2022",
                        "10.1000/new-one,MDMA,SERT,Duplicate new paper,2022",
                        "not-a-doi,DMT,Sigma-1,Broken paper,2023",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = add_new_dois(
                root=root,
                dataset="mechanistic",
                input_path=input_path,
                queue_out=root / "data" / "raw" / "doi_queue.mechanistic.new.txt",
                report_out=root / "data" / "processed" / "add_new_dois_report_mechanistic.json",
                rediscovered_out=root / "data" / "processed" / "rediscovered.csv",
                invalid_out=root / "data" / "processed" / "invalid.csv",
                duplicates_out=root / "data" / "processed" / "duplicates.csv",
            )

            self.assertEqual(report["counts"]["new_dois"], 1)
            self.assertEqual(report["counts"]["rediscovered_existing_dois"], 2)
            self.assertEqual(report["counts"]["missing_or_invalid_dois"], 1)
            self.assertEqual(report["counts"]["duplicate_dois_within_input"], 1)

            queue_rows = read_queue(root / "data" / "raw" / "doi_queue.mechanistic.new.txt")
            self.assertEqual(len(queue_rows), 1)
            self.assertEqual(queue_rows[0][0], "10.1000/new-one")

            with (root / "data" / "processed" / "rediscovered.csv").open("r", encoding="utf-8", newline="") as handle:
                rediscovered_rows = list(csv.DictReader(handle))
            self.assertEqual({row["doi"] for row in rediscovered_rows}, {"10.1000/existing-corpus", "10.1000/existing-other-dataset"})

    def test_dataset_scope_does_not_consider_other_dataset_specific_artifacts(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_json(
                root / "data" / "processed" / "paper_library_disorder.json",
                [{"study_doi": "10.1000/known-only-in-disorder"}],
            )

            global_existing, _ = load_existing_dois(root=root, dataset="mechanistic", existing_scope="global")
            dataset_existing, _ = load_existing_dois(root=root, dataset="mechanistic", existing_scope="dataset")

            self.assertIn("10.1000/known-only-in-disorder", global_existing)
            self.assertNotIn("10.1000/known-only-in-disorder", dataset_existing)

    def test_discovery_ledger_is_optional_because_current_run_updates_it(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_json(
                root / "data" / "processed" / "discovery_ledger_mechanistic.json",
                {"dataset": "mechanistic", "entries": [{"doi": "10.1000/ledger-only"}]},
            )

            default_existing, _ = load_existing_dois(root=root, dataset="mechanistic")
            ledger_existing, _ = load_existing_dois(
                root=root,
                dataset="mechanistic",
                include_discovery_ledger=True,
            )

            self.assertNotIn("10.1000/ledger-only", default_existing)
            self.assertIn("10.1000/ledger-only", ledger_existing)


if __name__ == "__main__":
    unittest.main()
