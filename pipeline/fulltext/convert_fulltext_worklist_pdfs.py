#!/usr/bin/env python3
"""Convert local PDFs selected by the route-independent full-text worklist."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.fulltext.convert_routed_local_pdfs import main as convert_main  # noqa: E402


DEFAULT_SELECTION_TABLE = (
    ROOT / "data" / "processed" / "corpus" / "fulltext_enrichment_worklist.parquet"
)


def main() -> int:
    if not any(arg == "--selection-table" or arg.startswith("--selection-table=") for arg in sys.argv[1:]):
        sys.argv[1:1] = ["--selection-table", str(DEFAULT_SELECTION_TABLE)]
    return convert_main()


if __name__ == "__main__":
    raise SystemExit(main())
