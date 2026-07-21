#!/usr/bin/env python3
"""Build a host-balanced browser recovery pilot from scoped retrieval reports."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict, deque
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
AUDIT_DIR = ROOT / "data" / "processed" / "corpus" / "audits"
DEFAULT_RANKED_CSV = AUDIT_DIR / "manual_pdf_download_ranked.csv"
DEFAULT_OUTPUT_CSV = AUDIT_DIR / "manual_pdf_browser_independent_candidates.csv"
DEFAULT_PILOT_CSV = AUDIT_DIR / "manual_pdf_browser_independent_pilot.csv"
DEFAULT_REPORT_JSON = AUDIT_DIR / "manual_pdf_browser_independent_pilot_report.json"

RESOLVER_OR_INDEX_HOSTS = {
    "api.openalex.org",
    "doi.org",
    "dx.doi.org",
    "openalex.org",
    "pubmed.ncbi.nlm.nih.gov",
}
UNTRUSTED_BROWSER_HOSTS = {"scholarhub.ui.ac.id"}
TIER_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}


def clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def normalize_doi(value: object) -> str:
    doi = clean(value).lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix) :]
            break
    return doi.rstrip(".,; ")


def split_urls(value: object) -> list[str]:
    return [part.strip() for part in clean(value).split("|") if part.strip()]


def url_host(value: object) -> str:
    host = urlparse(clean(value)).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def independent_browser_urls(row: dict) -> list[str]:
    urls: list[str] = []
    for field in ("open_access_url", "best_pdf_url", "pdf_url_candidates"):
        for url in split_urls(row.get(field, "")):
            host = url_host(url)
            if not host or host in RESOLVER_OR_INDEX_HOSTS or host in UNTRUSTED_BROWSER_HOSTS:
                continue
            if url not in urls:
                urls.append(url)
    return urls


def load_latest_scoped_results(report_paths: list[Path]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for path in report_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("records") or payload.get("results") or []
        for row in rows:
            doi = normalize_doi(row.get("doi", ""))
            if doi:
                latest[doi] = {**row, "scope_report": str(path.resolve())}
    return latest


def bool_value(value: object) -> bool:
    return clean(value).lower() in {"1", "true", "yes"}


def build_candidates(ranked: pd.DataFrame, scoped_results: dict[str, dict]) -> pd.DataFrame:
    rows: list[dict] = []
    for rank, row in enumerate(ranked.fillna("").to_dict("records"), start=1):
        doi = normalize_doi(row.get("doi", ""))
        result = scoped_results.get(doi)
        if not result or clean(result.get("status", "")) == "downloaded":
            continue
        if not bool_value(row.get("manual_browser_recovery_candidate", False)):
            continue
        urls = independent_browser_urls(row)
        if not urls:
            continue
        primary = clean(row.get("manual_doi_landing_url", "")) or f"https://doi.org/{doi}"
        rows.append(
            {
                **row,
                "browser_scope_rank": rank,
                "browser_preferred_url": primary,
                "browser_primary_strategy": "doi_landing_only_stop_on_closed_access",
                "browser_doi_prefix": doi.split("/", 1)[0],
                "browser_oa_evidence_urls": "|".join(urls),
                "browser_scope_status": clean(result.get("status", "")),
                "browser_scope_failure_category": clean(result.get("failure_category", "")),
                "browser_scope_report": clean(result.get("scope_report", "")),
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["_tier_order"] = out["manual_priority_tier"].map(TIER_ORDER).fillna(99).astype(int)
    out = out.sort_values(
        ["_tier_order", "manual_priority_score", "manual_recoverability_score", "doi"],
        ascending=[True, False, False, True],
    ).drop(columns="_tier_order")
    return out.reset_index(drop=True)


def host_balanced_pilot(candidates: pd.DataFrame, limit: int) -> pd.DataFrame:
    if candidates.empty or limit <= 0:
        return candidates.iloc[0:0].copy()
    selected: list[dict] = []
    records = candidates.fillna("").to_dict("records")
    for phase_tiers in (("A", "B", "C"), ("D",)):
        host_queues: dict[str, deque[dict]] = defaultdict(deque)
        host_order: list[str] = []
        for row in records:
            if clean(row.get("manual_priority_tier", "")) not in phase_tiers:
                continue
            # DOI prefixes are a useful proxy for publisher/registration
            # agency and keep a supervised pilot from hammering one platform.
            prefix = clean(row.get("browser_doi_prefix", "")) or "unknown"
            if prefix not in host_queues:
                host_order.append(prefix)
            host_queues[prefix].append(row)
        while host_order and len(selected) < limit:
            next_hosts: list[str] = []
            for host in host_order:
                queue = host_queues[host]
                if queue and len(selected) < limit:
                    selected.append(queue.popleft())
                if queue:
                    next_hosts.append(host)
            host_order = next_hosts
        if len(selected) >= limit:
            break
    pilot = pd.DataFrame(selected)
    if not pilot.empty:
        pilot.insert(0, "browser_pilot_index", range(1, len(pilot) + 1))
    return pilot


def write_outputs(
    candidates: pd.DataFrame,
    pilot: pd.DataFrame,
    *,
    output_csv: Path,
    pilot_csv: Path,
    report_json: Path,
    report_paths: list[Path],
) -> dict:
    for path in (output_csv, pilot_csv, report_json):
        path.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(output_csv, index=False)
    pilot.to_csv(pilot_csv, index=False)
    report = {
        "scope_reports": [str(path.resolve()) for path in report_paths],
        "candidate_rows": int(len(candidates)),
        "pilot_rows": int(len(pilot)),
        "candidate_tier_counts": dict(Counter(candidates.get("manual_priority_tier", pd.Series(dtype=str)))),
        "candidate_failure_counts": dict(
            Counter(candidates.get("browser_scope_failure_category", pd.Series(dtype=str)))
        ),
        "candidate_doi_prefix_counts": dict(
            Counter(candidates.get("browser_doi_prefix", pd.Series(dtype=str)))
        ),
        "pilot_tier_counts": dict(Counter(pilot.get("manual_priority_tier", pd.Series(dtype=str)))),
        "pilot_failure_counts": dict(Counter(pilot.get("browser_scope_failure_category", pd.Series(dtype=str)))),
        "pilot_doi_prefix_counts": dict(Counter(pilot.get("browser_doi_prefix", pd.Series(dtype=str)))),
        "output_csv": str(output_csv.resolve()),
        "pilot_csv": str(pilot_csv.resolve()),
    }
    report_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ranked-csv", default=str(DEFAULT_RANKED_CSV))
    parser.add_argument(
        "--scope-report",
        action="append",
        required=True,
        help="Retrieval report in chronological order; repeat for retry reports so later results override earlier ones.",
    )
    parser.add_argument("--pilot-limit", type=int, default=50)
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--pilot-csv", default=str(DEFAULT_PILOT_CSV))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    report_paths = [Path(value).resolve() for value in args.scope_report]
    for path in report_paths:
        if not path.exists():
            raise FileNotFoundError(f"Scope report not found: {path}")
    ranked = pd.read_csv(Path(args.ranked_csv).resolve())
    candidates = build_candidates(ranked, load_latest_scoped_results(report_paths))
    pilot = host_balanced_pilot(candidates, args.pilot_limit)
    report = write_outputs(
        candidates,
        pilot,
        output_csv=Path(args.output_csv).resolve(),
        pilot_csv=Path(args.pilot_csv).resolve(),
        report_json=Path(args.report_json).resolve(),
        report_paths=report_paths,
    )
    print(
        f"BROWSER_RECOVERY_PILOT: candidates={report['candidate_rows']:,} "
        f"pilot={report['pilot_rows']:,} doi_prefixes={len(report['pilot_doi_prefix_counts']):,}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
