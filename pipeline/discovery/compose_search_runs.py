#!/usr/bin/env python3
"""Compose a completed recent update and historical gap into one promotable baseline."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.discovery.composite import compose_search_runs
from pipeline.discovery.run_literature_search import DEFAULT_RUN_ROOT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--update-run-id", required=True)
    parser.add_argument("--historical-gap-run-id", required=True)
    parser.add_argument("--run-root", default=str(DEFAULT_RUN_ROOT))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.run_root).resolve()
    manifest = compose_search_runs(
        run_dir=root / args.run_id,
        run_id=args.run_id,
        update_run_dir=root / args.update_run_id,
        historical_gap_run_dir=root / args.historical_gap_run_id,
    )
    print(f"Run ID: {manifest['run_id']}")
    print(f"Status: {manifest['status']}")
    print(f"Completion gate passed: {manifest['completion_gate_passed']}")
    print(f"Component runs: {', '.join(manifest['component_run_ids'])}")
    print(f"Provider records: {manifest['counts']['provider_records']}")
    return 0 if manifest["completion_gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
