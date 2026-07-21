#!/usr/bin/env python3
"""Build a clean DOI-browser retry queue from technical browser failures."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
AUDITS = ROOT / "data" / "processed" / "corpus" / "audits"
DEFAULT_RANKED = AUDITS / "manual_pdf_download_ranked.csv"
DEFAULT_BROWSER_REPORT = AUDITS / "doi_browser_pdf_recovery_new_doi_full_20260719_v1.json"
DEFAULT_OUTPUT_CSV = AUDITS / "doi_browser_technical_retry_queue_20260719.csv"
DEFAULT_OUTPUT_TXT = AUDITS / "doi_browser_technical_retry_queue_20260719.txt"
DEFAULT_REPORT = AUDITS / "doi_browser_technical_retry_queue_20260719_report.json"

ELIGIBLE_HINTS = {
    "open DOI landing page; require a matching journal-article page before following full-text/PDF/download controls",
    "Zenodo deposit",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ranked-csv", default=str(DEFAULT_RANKED))
    parser.add_argument("--browser-report", default=str(DEFAULT_BROWSER_REPORT))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--output-txt", default=str(DEFAULT_OUTPUT_TXT))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    ranked = pd.read_csv(Path(args.ranked_csv).resolve()).fillna("")
    payload = json.loads(Path(args.browser_report).resolve().read_text(encoding="utf-8"))
    outcomes = pd.DataFrame(payload.get("records", [])).fillna("")
    latest = outcomes.drop_duplicates("doi", keep="last")
    merged = ranked.merge(
        latest[["doi", "status", "reason", "error", "trail"]],
        on="doi",
        how="left",
        suffixes=("", "_browser"),
    )
    eligible_hint = merged["manual_doi_article_recovery_hint"].isin(ELIGIBLE_HINTS)
    retry = merged[(merged["status"] == "browser_error") & eligible_hint].copy()
    retry.insert(0, "retry_index", range(1, len(retry) + 1))

    output_csv = Path(args.output_csv).resolve()
    output_txt = Path(args.output_txt).resolve()
    report_path = Path(args.report).resolve()
    for output in (output_csv, output_txt, report_path):
        output.parent.mkdir(parents=True, exist_ok=True)
    retry.to_csv(output_csv, index=False)
    output_txt.write_text(
        "\n".join(retry["doi"].astype(str)) + ("\n" if len(retry) else ""),
        encoding="utf-8",
    )

    report = {
        "schema_version": "doi_browser_technical_retry_queue_v1",
        "ranked_rows": int(len(ranked)),
        "prior_browser_errors": int((merged["status"] == "browser_error").sum()),
        "excluded_nonarticle_or_invalid_hints": int(
            ((merged["status"] == "browser_error") & ~eligible_hint).sum()
        ),
        "retry_rows": int(len(retry)),
        "failure_category_counts": dict(Counter(retry["pdf_download_failure_category"].astype(str))),
        "oa_status_counts": dict(Counter(retry["open_access_status"].astype(str))),
        "output_csv": str(output_csv),
        "output_txt": str(output_txt),
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
