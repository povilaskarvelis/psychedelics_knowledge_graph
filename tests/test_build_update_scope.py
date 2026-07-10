import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pipeline.update.build_update_scope import build_scope


class BuildUpdateScopeTest(unittest.TestCase):
    def test_combines_selected_manifest_records_and_doi_files_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "records": [
                            {"doi": "10.1000/repaired", "action": "repair"},
                            {"doi": "10.1000/ignored", "action": "keep"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            doi_file = root / "manual.txt"
            doi_file.write_text("https://doi.org/10.1000/repaired\n10.1000/manual\n", encoding="utf-8")
            args = SimpleNamespace(
                manifest=[str(manifest)],
                doi_file=[str(doi_file)],
                records_field="records",
                doi_field="doi",
                include=[("action", "repair")],
                out=str(root / "out.txt"),
            )

            dois, report = build_scope(args)

        self.assertEqual(dois, ["10.1000/manual", "10.1000/repaired"])
        self.assertEqual(report["doi_count"], 2)
        self.assertEqual(report["selected_rows_by_selector"], {"action=repair": 1})


if __name__ == "__main__":
    unittest.main()
