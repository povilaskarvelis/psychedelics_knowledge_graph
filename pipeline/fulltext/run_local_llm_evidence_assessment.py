#!/usr/bin/env python3
"""Run local Ollama-based full-text evidence assessment.

This is the preferred entry point. The older
run_local_llm_evidence_adjudication.py module remains importable so existing
checkpoints, tests, and scripts do not break during the terminology migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from pipeline.fulltext.run_local_llm_evidence_adjudication import main
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.run_local_llm_evidence_adjudication import main


if __name__ == "__main__":
    raise SystemExit(main())
