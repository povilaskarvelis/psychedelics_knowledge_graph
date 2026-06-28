#!/usr/bin/env python3
"""Run the standard routed PDF retrieval stage."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys

try:
    from pipeline.fulltext.download_routed_pdfs import (
        DEFAULT_CANDIDATE_TABLE,
        DEFAULT_DOMAIN_ROUTING_TABLE,
        DEFAULT_FULLTEXT_DIR,
        DEFAULT_METADATA_TABLE,
        DEFAULT_PDF_DIR,
        DEFAULT_PRESCREEN_TABLE,
        DEFAULT_ROUTE_COUNTS_CSV,
        DEFAULT_ROUTE_SUMMARY_JSON,
        DEFAULT_ROUTE_TABLE,
        download_routed_pdfs,
        parse_csv_values,
        parse_statuses,
    )
    from pipeline.fulltext.export_manual_pdf_queue import (
        DEFAULT_OUTPUT_CSV as DEFAULT_MANUAL_QUEUE_CSV,
        DEFAULT_OUTPUT_TXT as DEFAULT_MANUAL_QUEUE_TXT,
        export_manual_pdf_queue,
    )
    from pipeline.fulltext.recover_pdf_landing_pages import recover_pdf_landing_pages
    from pipeline.ingest.sync_paper_library import normalize_doi
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.download_routed_pdfs import (
        DEFAULT_CANDIDATE_TABLE,
        DEFAULT_DOMAIN_ROUTING_TABLE,
        DEFAULT_FULLTEXT_DIR,
        DEFAULT_METADATA_TABLE,
        DEFAULT_PDF_DIR,
        DEFAULT_PRESCREEN_TABLE,
        DEFAULT_ROUTE_COUNTS_CSV,
        DEFAULT_ROUTE_SUMMARY_JSON,
        DEFAULT_ROUTE_TABLE,
        download_routed_pdfs,
        parse_csv_values,
        parse_statuses,
    )
    from pipeline.fulltext.export_manual_pdf_queue import (
        DEFAULT_OUTPUT_CSV as DEFAULT_MANUAL_QUEUE_CSV,
        DEFAULT_OUTPUT_TXT as DEFAULT_MANUAL_QUEUE_TXT,
        export_manual_pdf_queue,
    )
    from pipeline.fulltext.recover_pdf_landing_pages import recover_pdf_landing_pages
    from pipeline.ingest.sync_paper_library import normalize_doi


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIRECT_REPORT = ROOT / "data" / "processed" / "corpus" / "audits" / "routed_pdf_download_report.json"
DEFAULT_RECOVERY_REPORT = ROOT / "data" / "processed" / "corpus" / "audits" / "standard_pdf_recovery_report.json"
DEFAULT_REPORT = ROOT / "data" / "processed" / "corpus" / "audits" / "pdf_retrieval_pipeline_report.json"
DEFAULT_STANDARD_RECOVERY_CATEGORIES = (
    "forbidden,non_pdf_response,provider_error,timeout,other_download_failure,not_found"
)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_pdf_retrieval_pipeline(
    *,
    route_table: Path = DEFAULT_ROUTE_TABLE,
    metadata_table: Path = DEFAULT_METADATA_TABLE,
    candidate_table: Path = DEFAULT_CANDIDATE_TABLE,
    pdf_dir: Path = DEFAULT_PDF_DIR,
    prescreen_table: Path = DEFAULT_PRESCREEN_TABLE,
    domain_routing_table: Path | None = DEFAULT_DOMAIN_ROUTING_TABLE,
    fulltext_dir: Path = DEFAULT_FULLTEXT_DIR,
    route_summary_json: Path = DEFAULT_ROUTE_SUMMARY_JSON,
    route_counts_csv: Path = DEFAULT_ROUTE_COUNTS_CSV,
    manual_queue_csv: Path = DEFAULT_MANUAL_QUEUE_CSV,
    manual_queue_txt: Path = DEFAULT_MANUAL_QUEUE_TXT,
    direct_report_path: Path = DEFAULT_DIRECT_REPORT,
    recovery_report_path: Path = DEFAULT_RECOVERY_REPORT,
    report_path: Path = DEFAULT_REPORT,
    doi_filter: set[str] | None = None,
    limit: int = 0,
    dry_run: bool = False,
    skip_standard_recovery: bool = False,
    direct_rps: float = 1.0,
    direct_timeout_sec: int = 45,
    direct_max_retries: int = 1,
    direct_rate_limit_cooldown_sec: float = 0.0,
    direct_skip_candidate_statuses: set[str] | None = None,
    direct_only_failure_categories: set[str] | None = None,
    alternate_pdf_sources: set[str] | None = None,
    alternate_pdf_min_title_score: float = 0.5,
    recovery_categories: set[str] | None = None,
    recovery_rps: float = 0.8,
    recovery_timeout_sec: int = 30,
    attempt_log_every: int = 1,
    candidate_log_every: int = 1,
    progress_every: int = 25,
    write_every: int = 25,
) -> dict:
    print("PDF_RETRIEVAL: starting direct PDF download stage", flush=True)
    direct_report = download_routed_pdfs(
        route_table=route_table,
        metadata_table=metadata_table,
        candidate_table=candidate_table,
        pdf_dir=pdf_dir,
        report_path=direct_report_path,
        doi_filter=doi_filter,
        limit=limit,
        dry_run=dry_run,
        rps=direct_rps,
        timeout_sec=direct_timeout_sec,
        max_retries=direct_max_retries,
        skip_candidate_statuses=direct_skip_candidate_statuses or {"downloaded", "already_present", "manual_import"},
        only_failure_categories=direct_only_failure_categories,
        rate_limit_cooldown_sec=direct_rate_limit_cooldown_sec,
        write_every=write_every,
        progress_every=progress_every,
        attempt_log_every=attempt_log_every,
        candidate_log_every=candidate_log_every,
        alternate_pdf_sources=alternate_pdf_sources,
        alternate_pdf_min_title_score=alternate_pdf_min_title_score,
        rebuild_routes_after=True,
        prescreen_table=prescreen_table,
        domain_routing_table=domain_routing_table,
        fulltext_dir=fulltext_dir,
        route_summary_json=route_summary_json,
        route_counts_csv=route_counts_csv,
    )

    queue_after_direct = export_manual_pdf_queue(
        route_table=route_table,
        metadata_table=metadata_table,
        candidate_table=candidate_table,
        pdf_dir=pdf_dir,
        output_csv=manual_queue_csv,
        output_txt=manual_queue_txt,
    )

    recovery_report: dict | None = None
    queue_after_recovery = queue_after_direct
    if dry_run:
        print("PDF_RETRIEVAL: dry run, skipping standard repository recovery", flush=True)
    elif skip_standard_recovery:
        print("PDF_RETRIEVAL: standard repository recovery skipped by request", flush=True)
    else:
        print("PDF_RETRIEVAL: starting standard repository recovery stage", flush=True)
        recovery_report = recover_pdf_landing_pages(
            manual_csv=manual_queue_csv,
            candidate_table=candidate_table,
            pdf_dir=pdf_dir,
            report_path=recovery_report_path,
            doi_filter=doi_filter,
            hosts=set(),
            categories=recovery_categories or parse_csv_values(DEFAULT_STANDARD_RECOVERY_CATEGORIES),
            standard_recovery_only=True,
            limit=limit,
            timeout_sec=recovery_timeout_sec,
            rps=recovery_rps,
            apply=True,
            rebuild_routes_after=True,
            route_table=route_table,
            metadata_table=metadata_table,
            prescreen_table=prescreen_table,
            domain_routing_table=domain_routing_table,
            fulltext_dir=fulltext_dir,
            route_summary_json=route_summary_json,
            route_counts_csv=route_counts_csv,
        )
        queue_after_recovery = export_manual_pdf_queue(
            route_table=route_table,
            metadata_table=metadata_table,
            candidate_table=candidate_table,
            pdf_dir=pdf_dir,
            output_csv=manual_queue_csv,
            output_txt=manual_queue_txt,
        )

    report = {
        "generated_at_utc": now_utc(),
        "dry_run": dry_run,
        "standard_recovery_enabled": not dry_run and not skip_standard_recovery,
        "route_table": str(route_table.resolve()),
        "candidate_table": str(candidate_table.resolve()),
        "pdf_dir": str(pdf_dir.resolve()),
        "direct_report_path": str(direct_report_path.resolve()),
        "recovery_report_path": str(recovery_report_path.resolve()) if recovery_report is not None else "",
        "manual_queue_csv": str(manual_queue_csv.resolve()),
        "alternate_pdf_sources": sorted(alternate_pdf_sources or set()),
        "alternate_pdf_min_title_score": alternate_pdf_min_title_score,
        "direct": {
            "status": direct_report.get("counts", {}).get("status", {}),
            "candidate_rows_changed": direct_report.get("counts", {}).get("candidate_rows_changed", 0),
            "route_rebuild": direct_report.get("route_rebuild", {}),
        },
        "standard_recovery": {
            "status": (recovery_report or {}).get("counts", {}).get("status", {}),
            "candidate_rows_changed": (recovery_report or {}).get("counts", {}).get(
                "candidate_rows_changed",
                0,
            ),
            "route_rebuild": (recovery_report or {}).get("route_rebuild", {}),
        },
        "manual_queue_after_direct": queue_after_direct,
        "manual_queue_final": queue_after_recovery,
    }
    write_json(report_path, report)
    print(
        "PDF_RETRIEVAL: complete "
        f"manual_queue_rows={queue_after_recovery.get('rows', 0):,} "
        f"report={report_path}",
        flush=True,
    )
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route-table", default=str(DEFAULT_ROUTE_TABLE))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--pdf-dir", default=str(DEFAULT_PDF_DIR))
    parser.add_argument("--prescreen-table", default=str(DEFAULT_PRESCREEN_TABLE))
    parser.add_argument("--domain-routing-table", default=str(DEFAULT_DOMAIN_ROUTING_TABLE))
    parser.add_argument("--fulltext-dir", default=str(DEFAULT_FULLTEXT_DIR))
    parser.add_argument("--route-summary-json", default=str(DEFAULT_ROUTE_SUMMARY_JSON))
    parser.add_argument("--route-counts-csv", default=str(DEFAULT_ROUTE_COUNTS_CSV))
    parser.add_argument("--manual-queue-csv", default=str(DEFAULT_MANUAL_QUEUE_CSV))
    parser.add_argument("--manual-queue-txt", default=str(DEFAULT_MANUAL_QUEUE_TXT))
    parser.add_argument("--direct-report", default=str(DEFAULT_DIRECT_REPORT))
    parser.add_argument("--recovery-report", default=str(DEFAULT_RECOVERY_REPORT))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--doi-file", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-standard-recovery", action="store_true")
    parser.add_argument("--direct-rps", type=float, default=1.0)
    parser.add_argument("--direct-timeout-sec", type=int, default=45)
    parser.add_argument("--direct-max-retries", type=int, default=1)
    parser.add_argument("--direct-rate-limit-cooldown-sec", type=float, default=0.0)
    parser.add_argument(
        "--direct-skip-candidate-statuses",
        default="downloaded,already_present,manual_import",
    )
    parser.add_argument("--direct-only-failure-categories", default="")
    parser.add_argument(
        "--alternate-pdf-sources",
        default="",
        help=(
            "Optional comma-separated alternate source strategies to try after direct PDF URLs fail. "
            "Supported values: pmc,openalex,semantic_scholar."
        ),
    )
    parser.add_argument(
        "--alternate-pdf-min-title-score",
        type=float,
        default=0.5,
        help="Minimum token title-match score for alternate-source PDFs when extractable text is available.",
    )
    parser.add_argument("--recovery-categories", default=DEFAULT_STANDARD_RECOVERY_CATEGORIES)
    parser.add_argument("--recovery-rps", type=float, default=0.8)
    parser.add_argument("--recovery-timeout-sec", type=int, default=30)
    parser.add_argument("--attempt-log-every", type=int, default=1)
    parser.add_argument("--candidate-log-every", type=int, default=1)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--write-every", type=int, default=25)
    return parser


def read_doi_file(path: Path) -> set[str]:
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.add(normalize_doi(line.split(",", 1)[0].strip()).lower())
    return {doi for doi in out if doi}


def main() -> int:
    args = build_arg_parser().parse_args()
    doi_filter = read_doi_file(Path(args.doi_file).resolve()) if args.doi_file.strip() else None
    run_pdf_retrieval_pipeline(
        route_table=Path(args.route_table).resolve(),
        metadata_table=Path(args.metadata_table).resolve(),
        candidate_table=Path(args.candidate_table).resolve(),
        pdf_dir=Path(args.pdf_dir).resolve(),
        prescreen_table=Path(args.prescreen_table).resolve(),
        domain_routing_table=Path(args.domain_routing_table).resolve() if args.domain_routing_table.strip() else None,
        fulltext_dir=Path(args.fulltext_dir).resolve(),
        route_summary_json=Path(args.route_summary_json).resolve(),
        route_counts_csv=Path(args.route_counts_csv).resolve(),
        manual_queue_csv=Path(args.manual_queue_csv).resolve(),
        manual_queue_txt=Path(args.manual_queue_txt).resolve(),
        direct_report_path=Path(args.direct_report).resolve(),
        recovery_report_path=Path(args.recovery_report).resolve(),
        report_path=Path(args.report).resolve(),
        doi_filter=doi_filter,
        limit=max(0, args.limit),
        dry_run=bool(args.dry_run),
        skip_standard_recovery=bool(args.skip_standard_recovery),
        direct_rps=args.direct_rps,
        direct_timeout_sec=args.direct_timeout_sec,
        direct_max_retries=args.direct_max_retries,
        direct_rate_limit_cooldown_sec=max(0.0, args.direct_rate_limit_cooldown_sec),
        direct_skip_candidate_statuses=parse_statuses(args.direct_skip_candidate_statuses),
        direct_only_failure_categories=parse_csv_values(args.direct_only_failure_categories) or None,
        alternate_pdf_sources=parse_csv_values(args.alternate_pdf_sources),
        alternate_pdf_min_title_score=args.alternate_pdf_min_title_score,
        recovery_categories=parse_csv_values(args.recovery_categories),
        recovery_rps=args.recovery_rps,
        recovery_timeout_sec=args.recovery_timeout_sec,
        attempt_log_every=args.attempt_log_every,
        candidate_log_every=args.candidate_log_every,
        progress_every=args.progress_every,
        write_every=args.write_every,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
