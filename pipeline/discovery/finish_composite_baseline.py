#!/usr/bin/env python3
"""Wait for a historical gap, compose the full baseline, and optionally promote it."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.discovery.composite import compose_search_runs
from pipeline.discovery.promote_search_run import promote
from pipeline.discovery.run_literature_search import DEFAULT_RUN_ROOT
from pipeline.discovery.runner import read_json


def wait_for_complete(run_dir: Path, poll_seconds: int) -> dict:
    manifest_path = Path(run_dir) / "run_manifest.json"
    terminal_failures = {"failed", "paused_budget", "incomplete", "calibration_failed"}
    while True:
        manifest = read_json(manifest_path)
        status = str(manifest.get("status", ""))
        if status == "complete" and manifest.get("completion_gate_passed"):
            return manifest
        if status in terminal_failures:
            raise RuntimeError(
                f"Historical-gap run stopped with status={status}; refusing composition and promotion"
            )
        print(f"Waiting for {manifest.get('run_id')}: status={status}", flush=True)
        time.sleep(max(5, poll_seconds))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="Composite full-baseline run ID")
    parser.add_argument("--update-run-id", required=True)
    parser.add_argument("--historical-gap-run-id", required=True)
    parser.add_argument("--run-root", default=str(DEFAULT_RUN_ROOT))
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--promote", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.run_root).resolve()
    update_dir = root / args.update_run_id
    gap_dir = root / args.historical_gap_run_id
    composite_dir = root / args.run_id
    wait_for_complete(gap_dir, args.poll_seconds)
    if (composite_dir / "run_manifest.json").exists():
        manifest = read_json(composite_dir / "run_manifest.json")
        if manifest.get("status") != "complete" or not manifest.get("completion_gate_passed"):
            raise RuntimeError("Existing composite run is not complete")
    else:
        manifest = compose_search_runs(
            run_dir=composite_dir,
            run_id=args.run_id,
            update_run_dir=update_dir,
            historical_gap_run_dir=gap_dir,
        )
    print(
        f"Composite {manifest['run_id']}: status={manifest['status']} "
        f"records={manifest['counts']['provider_records']}",
        flush=True,
    )
    if args.promote:
        report = promote(run_dir=composite_dir)
        print(
            f"Promoted {report['run_id']}: new_dois={report['counts']['new_candidate_dois']} "
            f"rediscovered_dois={report['counts']['rediscovered_candidate_dois']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
