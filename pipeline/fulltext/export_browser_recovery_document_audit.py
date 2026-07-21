#!/usr/bin/env python3
"""Export a staged browser-recovery document audit CSV as valid JSON.

The browser-recovery audit is intentionally staging-only: it records document
identity and format evidence without moving PDFs or updating candidate records.
This small exporter keeps the JSON sidecar reproducible from the canonical CSV.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()

    input_csv = Path(args.input_csv).resolve()
    output_json = Path(args.output_json).resolve()
    with input_csv.open("r", encoding="utf-8", newline="") as handle:
        records = list(csv.DictReader(handle))

    by_pass = Counter(str(row.get("recovery_pass", "")) for row in records)
    by_outcome = Counter(str(row.get("final_outcome", "")) for row in records)
    payload = {
        "schema_version": "browser_recovery_document_audit_v2",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "staging_only": True,
        "input_csv": str(input_csv),
        "counts": {
            "records": len(records),
            "by_recovery_pass": dict(sorted(by_pass.items())),
            "by_final_outcome": dict(sorted(by_outcome.items())),
        },
        "records": records,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
