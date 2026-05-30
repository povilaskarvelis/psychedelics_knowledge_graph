import tempfile
from pathlib import Path
import unittest

import pandas as pd

from pipeline.fulltext.migrate_pdf_store import canonical_pdf_name, migrate_pdf_store


class TestMigratePdfStore(unittest.TestCase):
    def test_dry_run_plans_canonical_migration_without_moving_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            doi = "10.1000/example"
            source_root = root / "data" / "raw" / "papers"
            legacy_dir = source_root / "mechanistic" / "pdfs"
            target_dir = source_root / "pdfs"
            legacy_dir.mkdir(parents=True)
            source = legacy_dir / canonical_pdf_name(doi)
            source.write_bytes(b"%PDF-1.4\nexample")
            candidate_table = root / "candidate_papers.parquet"
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "pdf_local_path": str(source),
                        "local_pdf_paths": str(source),
                        "local_pdf_count": 1,
                    }
                ]
            ).to_parquet(candidate_table, engine="pyarrow", index=False)

            report = migrate_pdf_store(
                source_root=source_root,
                target_dir=target_dir,
                invalid_dir=source_root / "invalid",
                candidate_table=candidate_table,
                legacy_library_jsons=[],
                report_path=root / "report.json",
                apply=False,
                mode="move",
            )

            self.assertTrue(source.exists())
            self.assertFalse((target_dir / canonical_pdf_name(doi)).exists())
            self.assertEqual(report["counts"]["planned_or_completed_valid_migrations"], 1)
            self.assertEqual(report["records"][0]["action"], "move")

    def test_apply_move_updates_candidate_table_to_canonical_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            doi = "10.1000/example"
            source_root = root / "data" / "raw" / "papers"
            legacy_dir = source_root / "disorder" / "pdfs"
            target_dir = source_root / "pdfs"
            legacy_dir.mkdir(parents=True)
            source = legacy_dir / canonical_pdf_name(doi)
            source.write_bytes(b"%PDF-1.7\nexample")
            candidate_table = root / "candidate_papers.parquet"
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "pdf_local_path": str(source),
                        "local_pdf_paths": str(source),
                        "local_pdf_count": 1,
                    }
                ]
            ).to_parquet(candidate_table, engine="pyarrow", index=False)

            report = migrate_pdf_store(
                source_root=source_root,
                target_dir=target_dir,
                invalid_dir=source_root / "invalid",
                candidate_table=candidate_table,
                legacy_library_jsons=[],
                report_path=root / "report.json",
                apply=True,
                mode="move",
            )

            dest = target_dir / canonical_pdf_name(doi)
            updated = pd.read_parquet(candidate_table)
            self.assertFalse(source.exists())
            self.assertTrue(dest.exists())
            self.assertEqual(updated.loc[0, "pdf_local_path"], str(dest.resolve()))
            self.assertEqual(updated.loc[0, "local_pdf_paths"], str(dest.resolve()))
            self.assertEqual(int(updated.loc[0, "local_pdf_count"]), 1)
            self.assertTrue(bool(updated.loc[0, "flag_has_local_pdf"]))
            self.assertTrue(str(updated.loc[0, "pdf_sha256"]))
            self.assertEqual(report["candidate_rows_updated"], 1)

    def test_invalid_pdf_is_reported_and_not_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            doi = "10.1000/bad"
            source_root = root / "data" / "raw" / "papers"
            legacy_dir = source_root / "disorder" / "excluded"
            target_dir = source_root / "pdfs"
            legacy_dir.mkdir(parents=True)
            source = legacy_dir / canonical_pdf_name(doi)
            source.write_text("<html>not a pdf</html>", encoding="utf-8")
            candidate_table = root / "candidate_papers.parquet"
            pd.DataFrame([{"doi": doi, "pdf_local_path": str(source)}]).to_parquet(
                candidate_table,
                engine="pyarrow",
                index=False,
            )

            report = migrate_pdf_store(
                source_root=source_root,
                target_dir=target_dir,
                invalid_dir=source_root / "invalid",
                candidate_table=candidate_table,
                legacy_library_jsons=[],
                report_path=root / "report.json",
                apply=True,
                mode="move",
            )

            self.assertTrue(source.exists())
            self.assertFalse((target_dir / canonical_pdf_name(doi)).exists())
            self.assertEqual(report["counts"]["invalid_pdf_files"], 1)

    def test_same_doi_content_conflict_can_be_moved_to_conflict_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            doi = "10.1000/conflict"
            source_root = root / "data" / "raw" / "papers"
            legacy_dir = source_root / "mechanistic" / "pdfs"
            target_dir = source_root / "pdfs"
            conflict_dir = source_root / "pdf_conflicts"
            legacy_dir.mkdir(parents=True)
            source = legacy_dir / canonical_pdf_name(doi)
            dest = target_dir / canonical_pdf_name(doi)
            target_dir.mkdir(parents=True)
            source.write_bytes(b"%PDF-1.4\nalternate")
            dest.write_bytes(b"%PDF-1.4\nprimary")
            candidate_table = root / "candidate_papers.parquet"
            pd.DataFrame([{"doi": doi}]).to_parquet(candidate_table, engine="pyarrow", index=False)

            report = migrate_pdf_store(
                source_root=source_root,
                target_dir=target_dir,
                invalid_dir=source_root / "invalid",
                conflict_dir=conflict_dir,
                candidate_table=candidate_table,
                legacy_library_jsons=[],
                report_path=root / "report.json",
                apply=True,
                mode="move",
                move_conflicts=True,
            )

            self.assertFalse(source.exists())
            self.assertTrue(dest.exists())
            self.assertEqual(report["counts"]["content_conflicts"], 1)
            self.assertEqual(report["counts"]["unhandled_content_conflicts"], 0)
            self.assertTrue(Path(report["conflicts"][0]["conflict_path"]).exists())

    def test_reconcile_clears_stale_local_pdf_markers_without_canonical_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_root = root / "data" / "raw" / "papers"
            target_dir = source_root / "pdfs"
            candidate_table = root / "candidate_papers.parquet"
            pd.DataFrame(
                [
                    {
                        "doi": "10.1000/stale",
                        "pdf_local_path": "",
                        "local_pdf_paths": "",
                        "local_pdf_count": 0,
                        "pdf_sha256": "deadbeef",
                        "flag_has_local_pdf": True,
                        "pdf_download_status": "downloaded",
                    }
                ]
            ).to_parquet(candidate_table, engine="pyarrow", index=False)

            report = migrate_pdf_store(
                source_root=source_root,
                target_dir=target_dir,
                invalid_dir=source_root / "invalid",
                candidate_table=candidate_table,
                legacy_library_jsons=[],
                report_path=root / "report.json",
                apply=True,
                mode="move",
            )

            updated = pd.read_parquet(candidate_table)
            self.assertEqual(report["candidate_rows_cleared"], 1)
            self.assertFalse(bool(updated.loc[0, "flag_has_local_pdf"]))
            self.assertEqual(updated.loc[0, "pdf_sha256"], "")
            self.assertEqual(updated.loc[0, "pdf_download_status"], "not_downloaded")


if __name__ == "__main__":
    unittest.main()
