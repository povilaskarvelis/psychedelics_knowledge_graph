import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh_public_release.sh"


class RefreshPublicReleaseScriptTest(unittest.TestCase):
    def run_script(
        self,
        *,
        frozen_keys: bool,
        publish: bool = False,
        allow_ledger: bool = False,
    ) -> tuple[list[str], subprocess.CompletedProcess[str]]:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp = Path(tmpdir)
            bin_dir = temp / "bin"
            bin_dir.mkdir()
            call_log = temp / "calls.log"
            fake_python = bin_dir / "python3"
            fake_python.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$CALL_LOG\"\n", encoding="utf-8")
            fake_python.chmod(0o755)
            payload = temp / "payload"
            payload.mkdir()
            if frozen_keys:
                (payload / "selected_candidate_keys.json").write_text("{}", encoding="utf-8")
            env = dict(os.environ)
            env.update(
                {
                    "PATH": f"{bin_dir}:{env['PATH']}",
                    "CALL_LOG": str(call_log),
                    "ENV_FILE": str(temp / "missing.env"),
                    "KG_DIR": str(temp / "kg"),
                    "PAYLOAD_DIR": str(payload),
                    "QUERY_DIR": str(temp / "query"),
                    "NO_R2_PUBLISH": "0" if publish else "1",
                    "ALLOW_CURRENT_LEDGER_DENOMINATOR": "1" if allow_ledger else "0",
                }
            )
            result = subprocess.run(
                ["bash", str(SCRIPT), "test_run"], cwd=ROOT, env=env, capture_output=True, text=True
            )
            calls = call_log.read_text(encoding="utf-8").splitlines() if call_log.exists() else []
            return calls, result

    def test_refresh_reuses_the_release_paper_denominator(self) -> None:
        calls, result = self.run_script(frozen_keys=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        export = next(call for call in calls if "export_evidence_payload.py" in call)
        self.assertIn("--candidate-keys", export)
        self.assertIn("selected_candidate_keys.json", export)
        self.assertFalse(any("release_archive.py" in call for call in calls))

    def test_refresh_without_frozen_keys_stops_before_rebuilding(self) -> None:
        calls, result = self.run_script(frozen_keys=False)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [])
        self.assertIn("no frozen selected-paper keys", result.stderr)

    def test_ledger_denominator_needs_an_explicit_override(self) -> None:
        calls, result = self.run_script(frozen_keys=False, allow_ledger=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        export = next(call for call in calls if "export_evidence_payload.py" in call)
        self.assertNotIn("--candidate-keys", export)

    def test_publishing_checks_the_live_archive_first(self) -> None:
        calls, result = self.run_script(frozen_keys=True, publish=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("release_archive.py --check-live", calls[0])
        self.assertIn("export_query_api.py", calls[1])
        self.assertTrue(any("prune_release_history.py --remote --local --execute" in call for call in calls))


if __name__ == "__main__":
    unittest.main()
