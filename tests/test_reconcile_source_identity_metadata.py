import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from pipeline.ingest.reconcile_source_identity_metadata import (
    DEFAULT_RUN_ID,
    build_reconciled_tables,
    run_reconciliation,
)


class ReconcileSourceIdentityMetadataTest(unittest.TestCase):
    def fixture_frames(self) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, dict[str, str]]]:
        metadata = pd.DataFrame(
            [
                {
                    "doi": "10.1000/invalid",
                    "study_title": "Refreshed invalid paper",
                    "pmid": "111",
                    "pmcid": "",
                    "metadata_enrichment_run_id": DEFAULT_RUN_ID,
                    "open_access_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC111111/",
                    "best_pdf_url": "https://europepmc.org/api/getPdf?pmcid=PMC111111",
                    "pdf_url_candidates": (
                        "https://europepmc.org/api/getPdf?pmcid=PMC111111 | "
                        "https://publisher.example/invalid.pdf"
                    ),
                    "custom_metadata_column": "keep-invalid",
                },
                {
                    "doi": "10.1000/conflict",
                    "study_title": "Refreshed conflict paper",
                    "pmid": "222-old",
                    "pmcid": "PMC222222",
                    "metadata_enrichment_run_id": DEFAULT_RUN_ID,
                    "open_access_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC222222/",
                    "best_pdf_url": "https://publisher.example/conflict.pdf",
                    "pdf_url_candidates": (
                        "https://pmc.ncbi.nlm.nih.gov/articles/PMC222222/pdf/ | "
                        "https://pmc.ncbi.nlm.nih.gov/articles/PMC999999/pdf/"
                    ),
                    "custom_metadata_column": "keep-conflict",
                },
                {
                    "doi": "10.1000/unrelated",
                    "study_title": "Metadata title should not merge",
                    "pmid": "333",
                    "pmcid": "PMC333333",
                    "metadata_enrichment_run_id": "another_run",
                    "open_access_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC333333/",
                    "best_pdf_url": "",
                    "pdf_url_candidates": "",
                    "custom_metadata_column": "keep-unrelated",
                },
            ]
        )
        candidates = pd.DataFrame(
            [
                {
                    "doi": "10.1000/invalid",
                    "study_title": "Old invalid paper",
                    "pmid": "111",
                    "pmcid": "PMC111111",
                    "metadata_enrichment_run_id": "old_run",
                    "open_access_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC111111/",
                    "best_pdf_url": "https://europepmc.org/api/getPdf?pmcid=PMC111111",
                    "pdf_url_candidates": (
                        "https://europepmc.org/api/getPdf?pmcid=PMC111111 | "
                        "https://publisher.example/invalid.pdf"
                    ),
                    "extraction_route_status": "preserve-invalid",
                },
                {
                    "doi": "10.1000/conflict",
                    "study_title": "Old conflict paper",
                    "pmid": "222-old",
                    "pmcid": "PMC222222",
                    "metadata_enrichment_run_id": "old_run",
                    "open_access_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC222222/",
                    "best_pdf_url": "https://publisher.example/conflict.pdf",
                    "pdf_url_candidates": (
                        "https://pmc.ncbi.nlm.nih.gov/articles/PMC222222/pdf/ | "
                        "https://pmc.ncbi.nlm.nih.gov/articles/PMC999999/pdf/"
                    ),
                    "extraction_route_status": "preserve-conflict",
                },
                {
                    "doi": "10.1000/unrelated",
                    "study_title": "Candidate title must stay",
                    "pmid": "333",
                    "pmcid": "PMC333333",
                    "metadata_enrichment_run_id": "old_run",
                    "open_access_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC333333/",
                    "best_pdf_url": "",
                    "pdf_url_candidates": "",
                    "extraction_route_status": "preserve-unrelated",
                },
            ]
        )
        resolution = {
            "10.1000/invalid": {
                "doi": "10.1000/invalid",
                "mapping_status": "stored_pmcid_not_verified_for_doi",
                "current_pmid": "111",
                "verified_pmid": "",
                "current_pmcid": "PMC111111",
                "verified_pmcid": "",
            },
            "10.1000/conflict": {
                "doi": "10.1000/conflict",
                "mapping_status": "pmcid_conflict",
                "current_pmid": "222-old",
                "verified_pmid": "222-new",
                "current_pmcid": "PMC222222",
                "verified_pmcid": "PMC999999",
            },
        }
        return metadata, candidates, resolution

    def test_reconciliation_is_targeted_and_removes_only_bad_pmc_urls(self) -> None:
        metadata, candidates, resolution = self.fixture_frames()

        metadata_out, candidate_out, report = build_reconciled_tables(
            metadata,
            candidates,
            resolution,
            run_id=DEFAULT_RUN_ID,
        )

        invalid = candidate_out.set_index("doi").loc["10.1000/invalid"]
        self.assertEqual(invalid["study_title"], "Refreshed invalid paper")
        self.assertEqual(invalid["pmcid"], "")
        self.assertEqual(invalid["open_access_url"], "")
        self.assertEqual(invalid["best_pdf_url"], "")
        self.assertEqual(invalid["pdf_url_candidates"], "https://publisher.example/invalid.pdf")
        self.assertEqual(invalid["extraction_route_status"], "preserve-invalid")

        conflict = candidate_out.set_index("doi").loc["10.1000/conflict"]
        self.assertEqual(conflict["pmid"], "222-new")
        self.assertEqual(conflict["pmcid"], "PMC999999")
        self.assertEqual(conflict["open_access_url"], "")
        self.assertEqual(conflict["best_pdf_url"], "https://publisher.example/conflict.pdf")
        self.assertEqual(
            conflict["pdf_url_candidates"],
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC999999/pdf/",
        )
        self.assertEqual(conflict["extraction_route_status"], "preserve-conflict")

        unrelated = candidate_out.set_index("doi").loc["10.1000/unrelated"]
        self.assertEqual(unrelated["study_title"], "Candidate title must stay")
        self.assertEqual(unrelated["extraction_route_status"], "preserve-unrelated")
        self.assertEqual(metadata_out["custom_metadata_column"].tolist(), metadata["custom_metadata_column"].tolist())
        self.assertEqual(report["refresh_merge"]["refreshed_metadata_rows"], 2)

    def write_fixture_files(self, root: Path) -> tuple[Path, Path, Path]:
        metadata, candidates, resolution = self.fixture_frames()
        metadata_path = root / "paper_metadata_enrichment.parquet"
        candidate_path = root / "candidate_papers.parquet"
        resolution_path = root / "artifact_pmcid_resolution.csv"
        metadata.to_parquet(metadata_path, index=False)
        candidates.to_parquet(candidate_path, index=False)
        pd.DataFrame(resolution.values()).to_csv(resolution_path, index=False)
        return metadata_path, candidate_path, resolution_path

    def test_dry_run_writes_report_but_not_tables_or_backups(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            metadata_path, candidate_path, resolution_path = self.write_fixture_files(root)
            original_metadata = metadata_path.read_bytes()
            original_candidates = candidate_path.read_bytes()
            report_path = root / "dry_run_report.json"
            backup_root = root / "backups"

            report = run_reconciliation(
                metadata_path=metadata_path,
                candidate_path=candidate_path,
                resolution_path=resolution_path,
                report_path=report_path,
                backup_root=backup_root,
                apply=False,
            )

            self.assertEqual(report["status"], "dry_run_complete")
            self.assertEqual(metadata_path.read_bytes(), original_metadata)
            self.assertEqual(candidate_path.read_bytes(), original_candidates)
            self.assertFalse(backup_root.exists())
            self.assertEqual(json.loads(report_path.read_text())["status"], "dry_run_complete")

    def test_apply_creates_backups_and_preserves_table_schema(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            metadata_path, candidate_path, resolution_path = self.write_fixture_files(root)
            original_metadata = pd.read_parquet(metadata_path)
            original_candidates = pd.read_parquet(candidate_path)
            report_path = root / "apply_report.json"
            backup_root = root / "backups"

            report = run_reconciliation(
                metadata_path=metadata_path,
                candidate_path=candidate_path,
                resolution_path=resolution_path,
                report_path=report_path,
                backup_root=backup_root,
                apply=True,
            )

            self.assertEqual(report["status"], "applied")
            metadata_after = pd.read_parquet(metadata_path)
            candidates_after = pd.read_parquet(candidate_path)
            self.assertEqual(list(metadata_after.columns), list(original_metadata.columns))
            self.assertEqual(list(candidates_after.columns), list(original_candidates.columns))
            self.assertEqual(len(metadata_after), len(original_metadata))
            self.assertEqual(len(candidates_after), len(original_candidates))

            metadata_backup = pd.read_parquet(report["backups"]["metadata_backup"])
            candidate_backup = pd.read_parquet(report["backups"]["candidate_backup"])
            pd.testing.assert_frame_equal(metadata_backup, original_metadata)
            pd.testing.assert_frame_equal(candidate_backup, original_candidates)
            self.assertEqual(
                candidates_after.set_index("doi").loc["10.1000/unrelated", "extraction_route_status"],
                "preserve-unrelated",
            )

    def test_apply_refuses_when_repair_run_has_no_rows(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            metadata_path, candidate_path, resolution_path = self.write_fixture_files(root)
            original_metadata = metadata_path.read_bytes()
            original_candidates = candidate_path.read_bytes()
            backup_root = root / "backups"

            with self.assertRaisesRegex(RuntimeError, "No metadata rows found"):
                run_reconciliation(
                    metadata_path=metadata_path,
                    candidate_path=candidate_path,
                    resolution_path=resolution_path,
                    report_path=root / "should_not_exist.json",
                    backup_root=backup_root,
                    run_id="missing_run",
                    apply=True,
                )

            self.assertEqual(metadata_path.read_bytes(), original_metadata)
            self.assertEqual(candidate_path.read_bytes(), original_candidates)
            self.assertFalse(backup_root.exists())


if __name__ == "__main__":
    unittest.main()
