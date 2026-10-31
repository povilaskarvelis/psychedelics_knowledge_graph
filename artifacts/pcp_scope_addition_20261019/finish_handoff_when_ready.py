"""Continuous final handoff after the existing scoped controller; no model calls."""
from pathlib import Path
import fcntl
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline import llm

D = ROOT / "data/processed/discovery/runs/pcp_scope_addition_20261019/downstream"


def main():
    lock = (D / "handoff.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    llm.atomic_json(D / "handoff_process.json", {"pid": os.getpid(), "command": [sys.executable, str(Path(__file__).resolve())],
        "started_at_utc": datetime.now(timezone.utc).isoformat()})
    last_progress = None
    while True:
        state = json.loads((D / "controller_state.json").read_text())
        batch_file = D / "screening/main/latest_status.json"
        batch = json.loads(batch_file.read_text()) if batch_file.exists() else {}
        progress = (state.get("stage"), state.get("status"), json.dumps(batch.get("request_counts"), sort_keys=True))
        if progress != last_progress:
            subprocess.run([sys.executable, str(Path(__file__).with_name("build_report.py"))], cwd=ROOT, check=True)
            last_progress = progress
        if state["status"] == "failed":
            raise RuntimeError("Scoped controller needs attention: " + state.get("error", "unknown error"))
        if state["status"] == "complete_at_source_recovery_checkpoint":
            break
        time.sleep(30)
    subprocess.run([sys.executable, str(Path(__file__).with_name("finalize_input_handoff.py"))], cwd=ROOT, check=True)
    llm.atomic_json(D / "handoff_status.json", {"status": "complete_at_current_pipeline_checkpoint", "report": str(D / "report.html"),
        "completed_at_utc": datetime.now(timezone.utc).isoformat(), "extraction_model_calls": 0, "graph_publication": False})
    subprocess.run([sys.executable, str(Path(__file__).with_name("build_report.py"))], cwd=ROOT, check=True)
    report = json.loads((D / "report.json").read_text())
    note = "\n\n### 19 October 2026 — PCP increment completed through the current checkpoint\n\n"
    note += "Source discovery, deterministic cleanup, Luna title/abstract screening, automated source recovery and provisional canonical extraction-input preparation are complete. "
    note += "Current counts and per-record outcomes are saved at `data/processed/discovery/runs/pcp_scope_addition_20261019/downstream/report.json` and `record_dispositions.csv`. "
    note += "Canonical pending task inventories include the PCP increment, while both published-release pointers remain unchanged. "
    note += f"Luna decisions: {report['screening_decisions']}. Saved-usage screening charge: ${report['model_cost_usd_from_saved_usage']:.4f}. "
    note += "Manual source recovery remains a separate queue; no extraction model jobs or graph release were submitted.\n"
    journal = ROOT / "pipeline/luna_v5_rerun_2026-10-17.md"
    if "### 19 October 2026 — PCP increment completed through the current checkpoint" not in journal.read_text():
        with journal.open("a") as handle:
            handle.write(note)
    print(json.dumps(json.loads((D / "handoff_status.json").read_text())), flush=True)


if __name__ == "__main__":
    try:
        main()
    except BlockingIOError:
        raise SystemExit("Existing handoff process owns this run.")
    except Exception as exc:
        llm.atomic_json(D / "handoff_status.json", {"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        subprocess.run([sys.executable, str(Path(__file__).with_name("build_report.py"))], cwd=ROOT)
        raise
