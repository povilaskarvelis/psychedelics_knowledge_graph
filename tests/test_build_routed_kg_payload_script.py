import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_routed_kg_payload.sh"


class BuildRoutedKgPayloadScriptTest(unittest.TestCase):
    def run_with_fake_python(
        self,
        *,
        activate_default: str | None,
        publish_r2: str = "0",
        fail_promotion: bool = False,
        expect_success: bool = True,
    ) -> tuple[list[str], subprocess.CompletedProcess[str]]:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp = Path(tmpdir)
            bin_dir = temp / "bin"
            bin_dir.mkdir()
            kg_dir = temp / "kg"
            kg_dir.mkdir()
            author_cache_seed = temp / "author-cache-seed.json"
            author_cache_seed.write_text('{"works_by_doi": {}}\n', encoding="utf-8")
            call_log = temp / "calls.log"
            fake_python = bin_dir / "python3"
            fake_python.write_text(
                """#!/bin/sh
printf '%s\n' "$*" >> "$CALL_LOG"
case "$*" in
  *pipeline/publish/promote_routed_run.py*)
    if [ "${FAIL_PROMOTION:-0}" = "1" ]; then
      exit 9
    fi
    ;;
esac
""",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            env = dict(os.environ)
            env.update(
                {
                    "PATH": f"{bin_dir}:{env['PATH']}",
                    "CALL_LOG": str(call_log),
                    "FAIL_PROMOTION": "1" if fail_promotion else "0",
                    "KG_DIR": str(kg_dir),
                    "PAYLOAD_DIR": str(temp / "payload"),
                    "QUERY_DIR": str(temp / "query"),
                    "PUBLISH_QUERY_API_R2": publish_r2,
                    "AUTHOR_CACHE_SEED": str(author_cache_seed),
                }
            )
            if activate_default is None:
                env.pop("ACTIVATE_DEFAULT", None)
            else:
                env["ACTIVATE_DEFAULT"] = activate_default
            result = subprocess.run(
                [str(SCRIPT), "test_run", "--offline"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
            )
            if expect_success and not fail_promotion:
                self.assertEqual(result.returncode, 0, result.stderr)
            else:
                self.assertNotEqual(result.returncode, 0)
            calls = (
                call_log.read_text(encoding="utf-8").splitlines()
                if call_log.exists()
                else []
            )
            return calls, result

    def test_activating_build_exports_then_uses_guarded_promotion(self) -> None:
        calls, _result = self.run_with_fake_python(activate_default="1")

        self.assertEqual(len(calls), 5)
        self.assertIn("pipeline/publish/export_query_api.py", calls[2])
        self.assertIn("pipeline/publish/export_evidence_payload.py", calls[3])
        self.assertNotIn("--activate-default", calls[3])
        self.assertIn("pipeline/publish/promote_routed_run.py", calls[4])
        self.assertIn("--run-id test_run", calls[4])

    def test_staged_build_leaves_live_methods_unchanged(self) -> None:
        calls, _result = self.run_with_fake_python(activate_default="0")

        self.assertEqual(len(calls), 4)
        self.assertIn("pipeline/publish/export_query_api.py", calls[2])
        self.assertNotIn("--activate-default", calls[3])
        self.assertFalse(any("build_methods_flow.py" in call for call in calls))

    def test_build_is_non_activating_when_flag_is_unset(self) -> None:
        calls, _result = self.run_with_fake_python(activate_default=None)

        self.assertEqual(len(calls), 4)
        self.assertIn("pipeline/publish/export_query_api.py", calls[2])
        self.assertNotIn("--activate-default", calls[3])
        self.assertFalse(any("build_methods_flow.py" in call for call in calls))

    def test_promotion_failure_is_reported_after_versioned_export(self) -> None:
        calls, _result = self.run_with_fake_python(
            activate_default="1", fail_promotion=True
        )

        self.assertEqual(len(calls), 5)
        self.assertIn("pipeline/publish/export_query_api.py", calls[2])
        self.assertIn("pipeline/publish/export_evidence_payload.py", calls[3])
        self.assertIn("pipeline/publish/promote_routed_run.py", calls[4])

    def test_r2_publish_runs_only_after_successful_promotion(self) -> None:
        calls, _result = self.run_with_fake_python(
            activate_default="1",
            publish_r2="1",
        )

        self.assertEqual(len(calls), 8)
        self.assertIn("pipeline/publish/promote_routed_run.py", calls[4])
        self.assertIn("pipeline/publish/publish_browser_payload_r2.py", calls[5])
        self.assertIn("pipeline/publish/publish_query_api_r2.py", calls[6])
        self.assertIn("pipeline/publish/prune_release_history.py", calls[7])
        self.assertIn("--run-id test_run", calls[5])
        self.assertIn("--run-id test_run", calls[6])
        self.assertIn("--remote --local --execute", calls[7])

    def test_r2_publish_requires_promotion(self) -> None:
        calls, result = self.run_with_fake_python(
            activate_default="0",
            publish_r2="1",
            expect_success=False,
        )

        self.assertEqual(calls, [])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires ACTIVATE_DEFAULT=1", result.stderr)


if __name__ == "__main__":
    unittest.main()
