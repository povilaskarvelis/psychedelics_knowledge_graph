import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.sanitize_public_json import sanitize_files


class SanitizePublicJsonTest(unittest.TestCase):
    def test_skips_json_parse_when_project_root_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "project"
            payload = Path(tmpdir) / "payload.json"
            payload.write_text('{"path":"data/processed/file.json"}\n', encoding="utf-8")

            with mock.patch("scripts.sanitize_public_json.json.loads") as loads:
                changed = sanitize_files([payload], root)

            self.assertEqual(changed, [])
            loads.assert_not_called()

    def test_scrubs_machine_local_project_root_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "project"
            payload = Path(tmpdir) / "payload.json"
            payload.write_text(
                json.dumps({"path": str(root / "data" / "processed" / "file.json")}),
                encoding="utf-8",
            )

            changed = sanitize_files([payload], root)

            self.assertEqual(changed, [payload])
            self.assertEqual(
                json.loads(payload.read_text(encoding="utf-8")),
                {"path": "data/processed/file.json"},
            )


if __name__ == "__main__":
    unittest.main()
