import argparse
import csv
import tempfile
import unittest
from pathlib import Path

from pipeline.ingest.run_standard_metadata_enrichment import (
    CORE_METADATA_PROVIDER_ORDER,
    OPEN_ACCESS_PROVIDER_ORDER,
    build_commands,
    combine_doi_files,
)


def args(**overrides):
    defaults = {
        "run_id": "test_run",
        "papers_table": "data/processed/corpus/candidate_papers.parquet",
        "metadata_table": "data/processed/corpus/paper_metadata_enrichment.parquet",
        "config": "pipeline/config.example.yaml",
        "core_provider_order": CORE_METADATA_PROVIDER_ORDER,
        "open_access_provider_order": OPEN_ACCESS_PROVIDER_ORDER,
        "skip_core_metadata": False,
        "skip_publication_types": False,
        "skip_open_access": False,
        "refresh_existing_core": False,
        "refresh_all_open_access": False,
        "limit": 0,
        "write_every": 100,
        "progress_every": 0,
        "timeout_sec": 40,
        "max_retry_after_sec": 120,
        "max_retries": None,
        "dry_run": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class StandardMetadataEnrichmentTest(unittest.TestCase):
    def test_combine_doi_files_normalizes_and_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "first.txt"
            second = root / "second.csv"
            out = root / "scope.txt"
            first.write_text("# comment\nhttps://doi.org/10.1000/ABC\n10.1000/def\n", encoding="utf-8")
            with second.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["doi", "title"])
                writer.writerow(["10.1000/abc", "duplicate"])
                writer.writerow(["doi:10.1000/ghi", "prefixed"])

            path, count = combine_doi_files([first, second], out)

            lines = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            ]

        self.assertEqual(count, 3)
        self.assertEqual(lines, ["10.1000/abc", "10.1000/def", "10.1000/ghi"])

    def test_build_commands_uses_role_specific_provider_orders(self) -> None:
        doi_file = Path("/tmp/doi_scope.txt")
        commands = build_commands(args(), doi_file)

        by_label = {label: command for label, command in commands}

        core = by_label["enrich core bibliographic metadata and abstracts"]
        self.assertIn("--metadata-provider-order", core)
        self.assertIn(CORE_METADATA_PROVIDER_ORDER, core)
        self.assertNotIn("unpaywall", core[core.index("--metadata-provider-order") + 1].split(","))
        self.assertIn("--retry-missing-metadata", core)
        self.assertIn(str(doi_file), core)

        publication_types = by_label["refresh PubMed publication-type labels"]
        self.assertIn("refresh_pubmed_publication_types.py", " ".join(publication_types))
        self.assertIn("--candidate-table", publication_types)
        self.assertIn(str(Path(args().papers_table).resolve()), publication_types)
        self.assertIn(str(doi_file), publication_types)

        open_access = by_label["refresh open-access status and PDF URLs"]
        self.assertIn("--provider-order", open_access)
        self.assertIn(OPEN_ACCESS_PROVIDER_ORDER, open_access)
        self.assertIn("--only-missing-pdf-url", open_access)
        self.assertIn(str(doi_file), open_access)


if __name__ == "__main__":
    unittest.main()
