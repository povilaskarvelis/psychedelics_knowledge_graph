#!/usr/bin/env python3
"""Build a reconciled, host-balanced queue for publisher-specific DOI recovery."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict, deque
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
AUDITS = ROOT / "data" / "processed" / "corpus" / "audits"
DEFAULT_RANKED = AUDITS / "manual_pdf_download_ranked.csv"
DEFAULT_OUTPUT_CSV = AUDITS / "doi_browser_host_pass_queue_20260719.csv"
DEFAULT_OUTPUT_TXT = AUDITS / "doi_browser_host_pass_queue_20260719.txt"
DEFAULT_REPORT = AUDITS / "doi_browser_host_pass_queue_20260719_report.json"
ELIGIBLE_HINTS = {
    "open DOI landing page; require a matching journal-article page before following full-text/PDF/download controls",
    "Zenodo deposit",
}


def balanced(rows: list[dict]) -> list[dict]:
    queues: dict[str, deque[dict]] = defaultdict(deque)
    for row in rows:
        queues[row["browser_host"] or "unknown"].append(row)
    hosts = sorted(queues, key=lambda host: (-len(queues[host]), host))
    output: list[dict] = []
    while hosts:
        remaining: list[str] = []
        for host in hosts:
            if queues[host]:
                output.append(queues[host].popleft())
            if queues[host]:
                remaining.append(host)
        hosts = remaining
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ranked-csv", default=str(DEFAULT_RANKED))
    parser.add_argument("--browser-report", action="append", required=True)
    parser.add_argument("--staging-report", action="append", default=[])
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--output-txt", default=str(DEFAULT_OUTPUT_TXT))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    latest: dict[str, dict] = {}
    for value in args.browser_report:
        for row in json.loads(Path(value).resolve().read_text(encoding="utf-8")).get("records", []):
            latest[str(row.get("doi", "")).lower()] = row
    quarantined: set[str] = set()
    for value in args.staging_report:
        for row in json.loads(Path(value).resolve().read_text(encoding="utf-8")).get("records", []):
            if row.get("recommended_action") == "quarantine_identity_review":
                quarantined.add(str(row.get("doi", "")).lower())

    ranked = pd.read_csv(Path(args.ranked_csv).resolve()).fillna("")
    selected: list[dict] = []
    for row in ranked.to_dict("records"):
        doi = str(row.get("doi", "")).lower()
        outcome = latest.get(doi, {})
        trail = outcome.get("trail") or []
        last_url = trail[-1] if trail else ""
        host = urlparse(last_url).netloc.lower().removeprefix("www.")
        if doi in quarantined:
            continue
        if row.get("manual_doi_article_recovery_hint") not in ELIGIBLE_HINTS:
            continue
        if outcome.get("status") != "not_recovered" or outcome.get("reason") != "no_pdf_control_found":
            continue
        selected.append({
            **row,
            "browser_host": host,
            "browser_last_url": last_url,
            "prior_browser_status": outcome.get("status", ""),
            "prior_browser_reason": outcome.get("reason", ""),
        })
    ordered = balanced(selected)
    for index, row in enumerate(ordered, start=1):
        row["host_pass_index"] = index
    output = pd.DataFrame(ordered)

    output_csv = Path(args.output_csv).resolve()
    output_txt = Path(args.output_txt).resolve()
    report_path = Path(args.report).resolve()
    for path in (output_csv, output_txt, report_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_csv, index=False)
    output_txt.write_text("\n".join(output.get("doi", pd.Series(dtype=str)).astype(str)) + ("\n" if len(output) else ""), encoding="utf-8")
    report = {
        "schema_version": "doi_browser_host_pass_queue_v1",
        "queue_rows": len(output),
        "host_counts": dict(Counter(output.get("browser_host", pd.Series(dtype=str)))),
        "output_csv": str(output_csv),
        "output_txt": str(output_txt),
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
