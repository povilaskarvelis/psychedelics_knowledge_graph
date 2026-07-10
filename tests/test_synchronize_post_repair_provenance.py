import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from pipeline.fulltext.synchronize_post_repair_provenance import RUN_ID, run_sync
from pipeline.ingest.sync_paper_library import pdf_filename_for_doi


def write_artifact(path: Path, *, doi: str, pdf_path: str, backend: str = "grobid", exact: bool = False) -> None:
    payload = {
        "study_doi": doi,
        "pdf_local_path": pdf_path,
        "best_backend": backend,
        "best_char_count": 1234,
        "source_identity": {"status": "verified_exact_doi" if exact else "verified_title_only"},
    }
    if exact:
        payload["repair_run_id"] = RUN_ID
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def base_candidate(doi: str, artifact_path: str, pdf_path: str) -> dict:
    return {
        "doi": doi,
        "pdf_local_path": pdf_path,
        "local_pdf_paths": pdf_path,
        "local_pdf_count": 1 if pdf_path else 0,
        "pdf_sha256": "stale-hash" if pdf_path else "",
        "pdf_download_status": "downloaded" if pdf_path else "",
        "flag_has_local_pdf": bool(pdf_path),
        "best_extraction_access_tier": "abstract_only",
        "has_converted_full_text": False,
        "fulltext_artifact_paths": artifact_path,
        "fulltext_char_count": 0,
        "unrelated_field": f"keep:{doi}",
    }


def load_artifact_pdf_path(path: Path) -> str:
    return str(json.loads(path.read_text(encoding="utf-8")).get("pdf_local_path", ""))


class SynchronizePostRepairProvenanceTest(unittest.TestCase):
    def paths(self, root: Path) -> dict[str, Path]:
        return {
            "artifacts": root / "data/processed/fulltext/articles",
            "candidates": root / "data/processed/corpus/candidate_papers.parquet",
            "pdfs": root / "data/raw/papers/pdfs",
            "raw": root / "data/raw/papers",
            "replaced": root / "quarantine/replaced_artifacts",
            "quarantine": root / "quarantine",
            "report": root / "report.json",
        }

    def test_dry_run_repoints_stale_artifact_and_updates_candidate_hash(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = self.paths(root)
            doi = "10.1000/ordinary"
            artifact_path = paths["artifacts"] / "ordinary.json"
            stale = paths["raw"] / "legacy" / "ordinary.pdf"
            canonical = paths["pdfs"] / pdf_filename_for_doi(doi)
            canonical.parent.mkdir(parents=True, exist_ok=True)
            canonical.write_bytes(b"%PDF-1.7\ncanonical\n%%EOF")
            write_artifact(artifact_path, doi=doi, pdf_path=str(stale))
            candidates = pd.DataFrame([base_candidate(doi, str(artifact_path), str(stale))])
            paths["candidates"].parent.mkdir(parents=True, exist_ok=True)
            candidates.to_parquet(paths["candidates"], index=False)
            before_artifact = artifact_path.read_bytes()
            before_candidates = paths["candidates"].read_bytes()

            report = run_sync(
                artifact_dir=paths["artifacts"],
                candidate_path=paths["candidates"],
                pdf_dir=paths["pdfs"],
                raw_root=paths["raw"],
                replaced_artifacts_dir=paths["replaced"],
                quarantine_dir=paths["quarantine"],
                report_path=paths["report"],
                workspace_root=root,
                apply=False,
            )

            change = report["candidate_updates"]["changes"][doi]
            self.assertEqual(change["pdf_local_path"]["after"], str(canonical.resolve()))
            self.assertEqual(
                change["pdf_sha256"]["after"],
                hashlib.sha256(canonical.read_bytes()).hexdigest(),
            )
            self.assertEqual(report["counts"]["artifact_json_updates"], 1)
            self.assertEqual(artifact_path.read_bytes(), before_artifact)
            self.assertEqual(paths["candidates"].read_bytes(), before_candidates)

    def test_apply_moves_unreferenced_exact_repair_pdf_and_preserves_xml_fulltext(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = self.paths(root)
            doi = "10.1000/exact"
            artifact_path = paths["artifacts"] / "exact.json"
            canonical = paths["pdfs"] / pdf_filename_for_doi(doi)
            canonical.parent.mkdir(parents=True, exist_ok=True)
            canonical.write_bytes(b"%PDF-1.7\nwrong paper\n%%EOF")
            write_artifact(
                artifact_path,
                doi=doi,
                pdf_path="",
                backend="europepmc_fulltext_xml",
                exact=True,
            )
            backup_path = paths["replaced"] / artifact_path.name
            write_artifact(backup_path, doi=doi, pdf_path=str(canonical), backend="grobid")
            candidates = pd.DataFrame([base_candidate(doi, str(artifact_path), str(canonical))])
            paths["candidates"].parent.mkdir(parents=True, exist_ok=True)
            candidates.to_parquet(paths["candidates"], index=False)

            report = run_sync(
                artifact_dir=paths["artifacts"],
                candidate_path=paths["candidates"],
                pdf_dir=paths["pdfs"],
                raw_root=paths["raw"],
                replaced_artifacts_dir=paths["replaced"],
                quarantine_dir=paths["quarantine"],
                report_path=paths["report"],
                workspace_root=root,
                apply=True,
            )

            self.assertEqual(report["status"], "applied")
            self.assertFalse(canonical.exists())
            moved = [row for row in report["wrong_pdf_actions"] if row["action"] == "moved"]
            self.assertEqual(len(moved), 1)
            self.assertTrue(Path(moved[0]["destination"]).exists())
            candidate = pd.read_parquet(paths["candidates"]).iloc[0]
            self.assertEqual(candidate["pdf_local_path"], "")
            self.assertEqual(candidate["pdf_sha256"], "")
            self.assertFalse(bool(candidate["flag_has_local_pdf"]))
            self.assertTrue(bool(candidate["has_converted_full_text"]))
            self.assertEqual(candidate["fulltext_artifact_paths"], str(artifact_path.resolve()))
            self.assertEqual(candidate["fulltext_char_count"], 1234)
            self.assertEqual(candidate["unrelated_field"], f"keep:{doi}")
            self.assertTrue(Path(report["backups"]["candidate_backup"]).exists())

    def test_apply_repoints_artifact_and_backs_up_previous_json(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = self.paths(root)
            doi = "10.1000/repoint"
            artifact_path = paths["artifacts"] / "repoint.json"
            stale = paths["raw"] / "legacy" / "repoint.pdf"
            canonical = paths["pdfs"] / pdf_filename_for_doi(doi)
            canonical.parent.mkdir(parents=True, exist_ok=True)
            canonical.write_bytes(b"%PDF-1.7\ncanonical\n%%EOF")
            write_artifact(artifact_path, doi=doi, pdf_path=str(stale))
            candidates = pd.DataFrame([base_candidate(doi, str(artifact_path), str(stale))])
            paths["candidates"].parent.mkdir(parents=True, exist_ok=True)
            candidates.to_parquet(paths["candidates"], index=False)

            report = run_sync(
                artifact_dir=paths["artifacts"],
                candidate_path=paths["candidates"],
                pdf_dir=paths["pdfs"],
                raw_root=paths["raw"],
                replaced_artifacts_dir=paths["replaced"],
                quarantine_dir=paths["quarantine"],
                report_path=paths["report"],
                workspace_root=root,
                apply=True,
            )

            self.assertEqual(load_artifact_pdf_path(artifact_path), str(canonical.resolve()))
            artifact_backup = Path(report["backups"]["artifact_backups"][str(artifact_path.resolve())])
            self.assertEqual(load_artifact_pdf_path(artifact_backup), str(stale))

    def test_wrong_pdf_is_retained_when_another_artifact_references_it(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = self.paths(root)
            exact_doi = "10.1000/exact-shared"
            other_doi = "10.1000/other"
            shared = paths["raw"] / "legacy" / "shared.pdf"
            shared.parent.mkdir(parents=True, exist_ok=True)
            shared.write_bytes(b"%PDF-1.7\nshared\n%%EOF")
            exact_artifact = paths["artifacts"] / "exact.json"
            other_artifact = paths["artifacts"] / "other.json"
            write_artifact(
                exact_artifact,
                doi=exact_doi,
                pdf_path="",
                backend="pmc_oai_xml",
                exact=True,
            )
            write_artifact(other_artifact, doi=other_doi, pdf_path=str(shared))
            write_artifact(paths["replaced"] / exact_artifact.name, doi=exact_doi, pdf_path=str(shared))
            candidates = pd.DataFrame(
                [
                    base_candidate(exact_doi, str(exact_artifact), str(shared)),
                    base_candidate(other_doi, str(other_artifact), str(shared)),
                ]
            )
            paths["candidates"].parent.mkdir(parents=True, exist_ok=True)
            candidates.to_parquet(paths["candidates"], index=False)

            report = run_sync(
                artifact_dir=paths["artifacts"],
                candidate_path=paths["candidates"],
                pdf_dir=paths["pdfs"],
                raw_root=paths["raw"],
                replaced_artifacts_dir=paths["replaced"],
                quarantine_dir=paths["quarantine"],
                report_path=paths["report"],
                workspace_root=root,
                apply=False,
            )

            action = next(row for row in report["wrong_pdf_actions"] if row["source"] == str(shared.resolve()))
            self.assertEqual(action["action"], "retained_referenced")
            self.assertEqual(action["remaining_artifact_references"], [other_doi])

    def test_alias_collision_clears_only_alias_row(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = self.paths(root)
            canonical_doi = "10.1000/canonical"
            alias_doi = "10.1000/malformed-alias"
            artifact_path = paths["artifacts"] / "canonical.json"
            canonical_pdf = paths["pdfs"] / pdf_filename_for_doi(canonical_doi)
            canonical_pdf.parent.mkdir(parents=True, exist_ok=True)
            canonical_pdf.write_bytes(b"%PDF-1.7\ncanonical\n%%EOF")
            write_artifact(artifact_path, doi=canonical_doi, pdf_path=str(canonical_pdf))
            candidates = pd.DataFrame(
                [
                    base_candidate(canonical_doi, str(artifact_path), str(canonical_pdf)),
                    base_candidate(alias_doi, str(artifact_path), str(canonical_pdf)),
                ]
            )
            paths["candidates"].parent.mkdir(parents=True, exist_ok=True)
            candidates.to_parquet(paths["candidates"], index=False)

            report = run_sync(
                artifact_dir=paths["artifacts"],
                candidate_path=paths["candidates"],
                pdf_dir=paths["pdfs"],
                raw_root=paths["raw"],
                replaced_artifacts_dir=paths["replaced"],
                quarantine_dir=paths["quarantine"],
                report_path=paths["report"],
                workspace_root=root,
                apply=False,
            )

            self.assertEqual(report["counts"]["alias_collisions"], 1)
            collision = report["alias_artifact_collisions"][0]
            self.assertEqual(collision["canonical_doi"], canonical_doi)
            self.assertEqual(collision["alias_dois"], [alias_doi])
            alias_changes = report["candidate_updates"]["changes"][alias_doi]
            self.assertEqual(alias_changes["fulltext_artifact_paths"]["after"], "")
            self.assertEqual(alias_changes["pdf_local_path"]["after"], "")
            self.assertEqual(alias_changes["pdf_download_status"]["after"], "source_identity_alias_collision")
            self.assertNotIn(canonical_doi, report["candidate_updates"]["missing_artifact_dois"])


if __name__ == "__main__":
    unittest.main()
