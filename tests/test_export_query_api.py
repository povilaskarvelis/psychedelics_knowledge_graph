import tempfile
import unittest
from pathlib import Path

import duckdb

from pipeline.publish.export_query_api import (
    PUBLIC_QUERY_MANIFEST_VERSION,
    materialize_query_artifacts,
    validate_query_artifact,
)
from tests.query_api_fixtures import write_minimal_kg


class ExportQueryApiTest(unittest.TestCase):
    def test_materializes_sanitized_database_and_bulk_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            kg_dir = root / "kg" / "test_run"
            out_dir = root / "query" / "test_run"
            write_minimal_kg(kg_dir)
            manifest = materialize_query_artifacts(
                kg_dir=kg_dir,
                out_dir=out_dir,
                run_id="test_run",
                generated_at="2026-07-17T00:00:00+00:00",
            )
            con = duckdb.connect(str(out_dir / "public_api.duckdb"), read_only=True)
            try:
                tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
                finding_columns = {
                    row[0] for row in con.execute("DESCRIBE findings").fetchall()
                }
                sources = dict(
                    con.execute(
                        "SELECT literature_source, count(*) FROM findings GROUP BY 1"
                    ).fetchall()
                )
            finally:
                con.close()

            self.assertEqual(manifest["schema_version"], PUBLIC_QUERY_MANIFEST_VERSION)
            self.assertEqual(manifest["row_counts"]["findings"], 3)
            self.assertEqual(
                tables,
                {"findings", "evidence_edges", "entities", "papers"},
            )
            self.assertFalse(
                {"raw_row_json", "normalization_notes", "extraction_warnings"}
                & finding_columns
            )
            self.assertEqual(sources, {"primary": 2, "reviews": 1})
            self.assertTrue((out_dir / "tables" / "findings.parquet").is_file())
            self.assertTrue(manifest["files"]["database"]["sha256"])

            checked = validate_query_artifact(
                kg_dir=kg_dir,
                out_dir=out_dir,
                run_id="test_run",
            )
            self.assertEqual(checked["row_counts"]["evidence_edges"], 3)


if __name__ == "__main__":
    unittest.main()
