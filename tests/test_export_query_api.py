import json
import tempfile
import unittest
from pathlib import Path

import duckdb
import pandas as pd

from pipeline.publish.export_query_api import (
    PUBLIC_QUERY_MANIFEST_VERSION,
    materialize_query_artifacts,
    validate_query_artifact,
)
from tests.query_api_fixtures import write_minimal_kg


class ExportQueryApiTest(unittest.TestCase):
    def test_materializes_private_query_runtime_without_bulk_tables(self) -> None:
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
                relationship_columns = {
                    row[0] for row in con.execute("DESCRIBE relationships").fetchall()
                }
                paper_types = dict(
                    con.execute(
                        "SELECT paper_type, count(*) FROM papers GROUP BY 1"
                    ).fetchall()
                )
                funding_row = con.execute(
                    """
                    SELECT funders, grant_ids, funding_metadata_status,
                           funding_providers, funding_assertion_count,
                           funding_funder_count, funding_award_count
                    FROM papers WHERE doi = '10.1000/primary'
                    """
                ).fetchone()
            finally:
                con.close()

            self.assertEqual(manifest["schema_version"], PUBLIC_QUERY_MANIFEST_VERSION)
            self.assertEqual(manifest["row_counts"]["papers"], 3)
            self.assertEqual(manifest["row_counts"]["relationships"], 2)
            self.assertEqual(
                tables,
                {"papers", "concepts", "authors", "paper_authors", "relationships"},
            )
            self.assertFalse(
                {
                    "finding_id",
                    "p_value",
                    "effect_size",
                    "supporting_quote",
                    "direction_normalized",
                }
                & relationship_columns
            )
            self.assertEqual(paper_types, {"primary_study": 2, "review": 1})
            self.assertEqual(
                funding_row,
                (
                    "Example Foundation",
                    "EF-001",
                    "reported",
                    "openalex|crossref",
                    2,
                    1,
                    1,
                ),
            )
            self.assertFalse((out_dir / "tables").exists())
            self.assertEqual(set(manifest["files"]), {"database", "schema"})
            self.assertTrue(manifest["quality"]["query_only"])
            self.assertTrue(manifest["quality"]["bulk_artifacts_excluded"])
            self.assertTrue(manifest["files"]["database"]["sha256"])

            schema = json.loads((out_dir / "schema.json").read_text(encoding="utf-8"))
            for table in schema["tables"].values():
                self.assertTrue(table["description"])
                self.assertTrue(table["grain"])
                self.assertTrue(table["primary_key"])
                self.assertTrue(all(field.get("description") for field in table["fields"]))
            self.assertEqual(
                schema["graph_views"]["schema_version"],
                "psychedelics_kg_graph_view_contract_v1",
            )
            target_view = next(
                view
                for view in schema["graph_views"]["views"]
                if view["value"] == "target_system"
            )
            self.assertEqual(
                target_view["filters"]["object_kinds"],
                ["target", "system_family"],
            )

            checked = validate_query_artifact(
                kg_dir=kg_dir,
                out_dir=out_dir,
                run_id="test_run",
            )
            self.assertEqual(checked["row_counts"]["relationships"], 2)

    def test_refuses_to_publish_name_only_author_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            kg_dir = root / "kg" / "test_run"
            out_dir = root / "query" / "test_run"
            write_minimal_kg(kg_dir)
            authors = pd.read_parquet(kg_dir / "authors.parquet")
            paper_authors = pd.read_parquet(kg_dir / "paper_authors.parquet")
            authors["author_id"] = [f"local_author:{index}" for index in range(len(authors))]
            paper_authors["author_id"] = [
                f"local_author:{index}" for index in range(len(paper_authors))
            ]
            authors.to_parquet(kg_dir / "authors.parquet", index=False)
            paper_authors.to_parquet(kg_dir / "paper_authors.parquet", index=False)

            with self.assertRaisesRegex(ValueError, "Refusing to publish unresolved or conflicting"):
                materialize_query_artifacts(
                    kg_dir=kg_dir,
                    out_dir=out_dir,
                    run_id="test_run",
                    generated_at="2026-07-17T00:00:00+00:00",
                )

            self.assertFalse(out_dir.exists())


if __name__ == "__main__":
    unittest.main()
