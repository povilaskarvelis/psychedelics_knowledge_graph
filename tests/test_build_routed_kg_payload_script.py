import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_routed_kg_payload.sh"


class BuildRoutedKgPayloadScriptTest(unittest.TestCase):
    def run_with_fake_python(self, *, activate_default: str, fail_methods: bool = False) -> list[str]:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp = Path(tmpdir)
            bin_dir = temp / "bin"
            bin_dir.mkdir()
            call_log = temp / "calls.log"
            fake_python = bin_dir / "python3"
            fake_python.write_text(
                """#!/bin/sh
printf '%s\n' "$*" >> "$CALL_LOG"
case "$*" in
  *pipeline/kg/build_methods_flow.py*)
    if [ "${FAIL_METHODS:-0}" = "1" ]; then
      exit 9
    fi
    previous=""
    out_dir=""
    for argument in "$@"; do
      if [ "$previous" = "--out-dir" ]; then
        out_dir="$argument"
        break
      fi
      previous="$argument"
    done
    mkdir -p "$out_dir/schema" "$out_dir/views" "$out_dir/manifests"
    : > "$out_dir/schema/methods_flow.schema.json"
    : > "$out_dir/views/pipeline_status_graph.json"
    : > "$out_dir/views/methods_bibliography.json"
    : > "$out_dir/manifests/build_manifest.json"
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
                    "ACTIVATE_DEFAULT": activate_default,
                    "FAIL_METHODS": "1" if fail_methods else "0",
                    "KG_DIR": str(temp / "kg"),
                    "PAYLOAD_DIR": str(temp / "payload"),
                    "METHODS_OUT_DIR": str(temp / "methods"),
                }
            )
            result = subprocess.run(
                [str(SCRIPT), "test_run", "--offline"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
            )
            if fail_methods:
                self.assertNotEqual(result.returncode, 0)
            else:
                self.assertEqual(result.returncode, 0, result.stderr)
            return call_log.read_text(encoding="utf-8").splitlines()

    def test_activating_build_stages_methods_before_payload_activation(self) -> None:
        calls = self.run_with_fake_python(activate_default="1")

        self.assertEqual(len(calls), 4)
        self.assertIn("pipeline/kg/build_methods_flow.py", calls[2])
        self.assertIn("--kg-dir", calls[2])
        self.assertIn("--out-dir", calls[2])
        self.assertIn("pipeline/publish/export_evidence_payload.py", calls[3])
        self.assertIn("--activate-default", calls[3])

    def test_staged_build_leaves_live_methods_unchanged(self) -> None:
        calls = self.run_with_fake_python(activate_default="0")

        self.assertEqual(len(calls), 3)
        self.assertNotIn("--activate-default", calls[2])
        self.assertFalse(any("build_methods_flow.py" in call for call in calls))

    def test_methods_failure_prevents_graph_activation(self) -> None:
        calls = self.run_with_fake_python(activate_default="1", fail_methods=True)

        self.assertEqual(len(calls), 3)
        self.assertIn("pipeline/kg/build_methods_flow.py", calls[2])
        self.assertFalse(any("export_evidence_payload.py" in call for call in calls))


if __name__ == "__main__":
    unittest.main()
