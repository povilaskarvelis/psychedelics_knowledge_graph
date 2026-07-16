#!/usr/bin/env python3
"""Finalize a fully retrieved search run after interrupted materialization."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.discovery.run_literature_search import DEFAULT_RUN_ROOT
from pipeline.discovery.runner import finalize_completed_retrieval


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-root", default=str(DEFAULT_RUN_ROOT))
    args = parser.parse_args()
    manifest = finalize_completed_retrieval(Path(args.run_root) / args.run_id)
    print(f"Run ID: {manifest['run_id']}")
    print(f"Status: {manifest['status']}")
    print(f"Completion gate passed: {manifest['completion_gate_passed']}")
    print(f"Provider hits: {manifest['counts']['provider_hits']}")
    print(f"Provider records: {manifest['counts']['provider_records']}")
    return 0 if manifest["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
