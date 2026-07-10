#!/usr/bin/env python3
"""Convert selected local PDFs into canonical full-text article artifacts."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

import pandas as pd

try:
    from pipeline.extract.build_extraction_routes import (
        DEFAULT_COUNTS_CSV,
        DEFAULT_CANDIDATE_TABLE,
        DEFAULT_FULLTEXT_DIR,
        DEFAULT_MANUAL_ROUTE_OVERRIDES,
        DEFAULT_METADATA_TABLE,
        DEFAULT_OUTPUT_TABLE,
        DEFAULT_PAPER_ROOT,
        DEFAULT_PRESCREEN_TABLE,
        build_extraction_routes,
        file_is_valid_pdf,
    )
    from pipeline.fulltext.convert_pdfs import (
        DEFAULT_GROBID_URL,
        build_artifact,
        convert_pdf,
        doi_to_slug,
        grobid_is_available,
        normalize,
        normalize_doi,
        now_utc,
        should_write_artifact,
        write_json,
    )
    from pipeline.fulltext.source_identity_audit_gate import (
        DEFAULT_IDENTITY_REGISTRY,
        DEFAULT_PDF_HASH_ATTESTATION_REGISTRY,
        DEFAULT_SOURCE_IDENTITY_AUDIT,
        DEFAULT_SOURCE_IDENTITY_AUDIT_CSV,
        DEFAULT_SOURCE_IDENTITY_UNVERIFIED_DOIS,
        refresh_source_identity_audit,
    )
    from pipeline.review.pdf_runtime import ensure_pdf_runtime
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.build_extraction_routes import (
        DEFAULT_COUNTS_CSV,
        DEFAULT_CANDIDATE_TABLE,
        DEFAULT_FULLTEXT_DIR,
        DEFAULT_MANUAL_ROUTE_OVERRIDES,
        DEFAULT_METADATA_TABLE,
        DEFAULT_OUTPUT_TABLE,
        DEFAULT_PAPER_ROOT,
        DEFAULT_PRESCREEN_TABLE,
        build_extraction_routes,
        file_is_valid_pdf,
    )
    from pipeline.fulltext.convert_pdfs import (
        DEFAULT_GROBID_URL,
        build_artifact,
        convert_pdf,
        doi_to_slug,
        grobid_is_available,
        normalize,
        normalize_doi,
        now_utc,
        should_write_artifact,
        write_json,
    )
    from pipeline.fulltext.source_identity_audit_gate import (
        DEFAULT_IDENTITY_REGISTRY,
        DEFAULT_PDF_HASH_ATTESTATION_REGISTRY,
        DEFAULT_SOURCE_IDENTITY_AUDIT,
        DEFAULT_SOURCE_IDENTITY_AUDIT_CSV,
        DEFAULT_SOURCE_IDENTITY_UNVERIFIED_DOIS,
        refresh_source_identity_audit,
    )
    from pipeline.review.pdf_runtime import ensure_pdf_runtime


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOMAIN_ROUTING_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_domain_routing_gemini.parquet"
DEFAULT_OUT_DIR = DEFAULT_FULLTEXT_DIR / "articles"
DEFAULT_REPORT = DEFAULT_FULLTEXT_DIR / "local_pdf_conversion_report.json"
DEFAULT_SUMMARY_JSON = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes_summary.json"
DEFAULT_ROUTE_ACTION = "convert_local_pdf_then_extract"


def clean(value: object) -> str:
    return normalize(value)


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).lower() in {"1", "true", "yes", "y"}


def split_values(value: object) -> list[str]:
    text = clean(value)
    if not text:
        return []
    separator = "|" if "|" in text else " | "
    return [part.strip() for part in text.split(separator) if part.strip()]


def read_doi_file(path: Path) -> set[str]:
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        doi = normalize_doi(line.split(",", 1)[0])
        if doi:
            out.add(doi)
    return out


def metadata_by_doi(metadata_df: pd.DataFrame) -> dict[str, dict]:
    if metadata_df.empty or "doi" not in metadata_df.columns:
        return {}
    out: dict[str, dict] = {}
    for row in metadata_df.to_dict("records"):
        doi = normalize_doi(row.get("doi", "")).lower()
        if doi and doi not in out:
            out[doi] = row
    return out


def valid_pdf_from_paths(paths: list[str]) -> Path | None:
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = ROOT / path
        if path.exists() and path.is_file() and file_is_valid_pdf(path):
            return path
    return None


def selected_pdf_rows(
    *,
    routes_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    out_dir: Path,
    doi_filter: set[str] | None,
    route_action: str,
    only_missing_artifacts: bool,
) -> tuple[list[dict], Counter[str]]:
    metadata_map = metadata_by_doi(metadata_df)
    selected = routes_df.copy()
    if "retained_for_extraction_candidate" in selected.columns:
        selected = selected[selected["retained_for_extraction_candidate"].map(truthy)].copy()
    selected = selected[selected["route_action"].fillna("").astype(str).eq(route_action)].copy()
    grouped: dict[str, list[dict]] = {}
    for row in selected.to_dict("records"):
        doi = normalize_doi(row.get("doi", "")).lower()
        if doi:
            grouped.setdefault(doi, []).append(row)

    rows: list[dict] = []
    skipped: Counter[str] = Counter()
    for doi in sorted(grouped):
        if doi_filter is not None and doi not in doi_filter:
            skipped["doi_filter"] += 1
            continue
        artifact_path = out_dir / f"{doi_to_slug(doi)}.json"
        if only_missing_artifacts and artifact_path.exists():
            skipped["existing_artifact"] += 1
            continue
        route_rows = grouped[doi]
        pdf_paths: list[str] = []
        for route_row in route_rows:
            pdf_paths.extend(split_values(route_row.get("local_pdf_paths", "")))
        pdf_path = valid_pdf_from_paths(pdf_paths)
        if pdf_path is None:
            skipped["missing_valid_pdf"] += 1
            continue
        metadata = metadata_map.get(doi, {})
        first_route = route_rows[0]
        rows.append(
            {
                "study_doi": doi,
                "study_title": clean(first_route.get("study_title", "")) or clean(metadata.get("study_title", "")),
                "study_year": clean(first_route.get("study_year", "")) or clean(metadata.get("study_year", "")),
                "openalex_id": clean(metadata.get("openalex_id", "")),
                "pdf_path": pdf_path,
                "artifact_path": artifact_path,
                "route_count": len(route_rows),
            }
        )
    return rows, skipped


def rebuild_routes(
    *,
    route_table: Path,
    metadata_table: Path,
    candidate_table: Path,
    prescreen_table: Path,
    domain_routing_table: Path | None,
    fulltext_dir: Path,
    paper_root: Path,
    summary_json: Path,
    counts_csv: Path,
    manual_route_overrides: Path | None,
    source_identity_audit: Path,
) -> dict:
    domain_table = domain_routing_table if domain_routing_table is not None and domain_routing_table.exists() else None
    return build_extraction_routes(
        metadata_table=metadata_table,
        candidate_table=candidate_table,
        prescreen_table=prescreen_table,
        domain_table=domain_table,
        manual_overrides_path=manual_route_overrides if manual_route_overrides and manual_route_overrides.exists() else None,
        fulltext_dir=fulltext_dir,
        source_identity_audit=source_identity_audit,
        paper_root=paper_root,
        output_table=route_table,
        summary_json=summary_json,
        counts_csv=counts_csv,
        include_non_retained=False,
    )


def backend_requires_live_grobid(backend: str) -> bool:
    return backend in {"auto", "grobid"}


def failed_record(row: dict, pdf_path: Path, artifact_path: Path, write_status: str) -> dict:
    return {
        "study_doi": row["study_doi"],
        "pdf_path": str(pdf_path),
        "artifact_path": str(artifact_path),
        "best_backend": "",
        "best_char_count": 0,
        "best_section_count": 0,
        "write_status": write_status,
    }


def convert_routed_local_pdfs(
    *,
    route_table: Path = DEFAULT_OUTPUT_TABLE,
    metadata_table: Path = DEFAULT_METADATA_TABLE,
    candidate_table: Path = DEFAULT_CANDIDATE_TABLE,
    prescreen_table: Path = DEFAULT_PRESCREEN_TABLE,
    domain_routing_table: Path | None = DEFAULT_DOMAIN_ROUTING_TABLE,
    fulltext_dir: Path = DEFAULT_FULLTEXT_DIR,
    out_dir: Path = DEFAULT_OUT_DIR,
    paper_root: Path = DEFAULT_PAPER_ROOT,
    report_path: Path = DEFAULT_REPORT,
    summary_json: Path = DEFAULT_SUMMARY_JSON,
    counts_csv: Path = DEFAULT_COUNTS_CSV,
    manual_route_overrides: Path | None = DEFAULT_MANUAL_ROUTE_OVERRIDES,
    doi_filter: set[str] | None = None,
    route_action: str = DEFAULT_ROUTE_ACTION,
    backend: str = "grobid",
    grobid_url: str = DEFAULT_GROBID_URL,
    grobid_retries: int = 2,
    grobid_retry_wait_sec: int = 5,
    grobid_consolidate_header: str = "0",
    grobid_consolidate_citations: str = "0",
    timeout_sec: int = 120,
    limit: int = 0,
    only_missing_artifacts: bool = True,
    write_failed_artifacts: bool = False,
    rebuild_routes_after: bool = True,
    source_identity_audit: Path = DEFAULT_SOURCE_IDENTITY_AUDIT,
    source_identity_audit_csv: Path = DEFAULT_SOURCE_IDENTITY_AUDIT_CSV,
    source_identity_unverified_dois: Path = DEFAULT_SOURCE_IDENTITY_UNVERIFIED_DOIS,
    identity_registry: Path = DEFAULT_IDENTITY_REGISTRY,
    pdf_hash_attestation_registry: Path = DEFAULT_PDF_HASH_ATTESTATION_REGISTRY,
) -> dict:
    if backend == "grobid" and not grobid_is_available(grobid_url):
        raise RuntimeError(f"GROBID service is not available: {grobid_url}")

    routes_df = pd.read_parquet(route_table)
    metadata_df = pd.read_parquet(metadata_table) if metadata_table.exists() else pd.DataFrame()
    rows, skipped = selected_pdf_rows(
        routes_df=routes_df,
        metadata_df=metadata_df,
        out_dir=out_dir,
        doi_filter=doi_filter,
        route_action=route_action,
        only_missing_artifacts=only_missing_artifacts,
    )
    all_candidate_count = len(rows)
    if limit > 0:
        rows = rows[:limit]

    counts: Counter[str] = Counter()
    records: list[dict] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    print(
        "LOCAL_PDF_CONVERSION: "
        f"selected={len(rows):,} candidates={all_candidate_count:,} "
        f"backend={backend} out_dir={out_dir}",
        flush=True,
    )

    for index, row in enumerate(rows, start=1):
        pdf_path = Path(row["pdf_path"])
        artifact_path = Path(row["artifact_path"])
        if backend_requires_live_grobid(backend) and not grobid_is_available(grobid_url):
            for pending_index, pending_row in enumerate(rows[index - 1 :], start=index):
                pending_pdf_path = Path(pending_row["pdf_path"])
                pending_artifact_path = Path(pending_row["artifact_path"])
                write_reason = "grobid unavailable before conversion"
                counts["without_success"] += 1
                counts["grobid_unavailable_before_conversion"] += 1
                records.append(failed_record(pending_row, pending_pdf_path, pending_artifact_path, write_reason))
                print(
                    "RESULT: local PDF conversion "
                    f"{pending_index:,}/{len(rows):,} doi={pending_row['study_doi']} "
                    "backend=<none> chars=0 "
                    f"write={write_reason}",
                    flush=True,
                )
            break

        extractions = convert_pdf(
            pdf_path=pdf_path,
            backend=backend,
            grobid_url=grobid_url,
            timeout_sec=max(1, timeout_sec),
            grobid_retries=max(0, grobid_retries),
            grobid_retry_wait_sec=max(0, grobid_retry_wait_sec),
            grobid_consolidate_header=grobid_consolidate_header,
            grobid_consolidate_citations=grobid_consolidate_citations,
        )
        artifact = build_artifact("articles", row, pdf_path, extractions)
        artifact["fulltext_artifact_layout"] = "canonical_articles_v1"
        artifact["route_conversion_source"] = "paper_extraction_routes"
        write_artifact, write_reason = should_write_artifact(
            artifact_path,
            artifact,
            write_failed_artifacts=write_failed_artifacts,
        )
        artifact["_write_status"] = write_reason
        if write_artifact:
            write_json(artifact_path, artifact)
            counts["written"] += 1
        else:
            counts["not_written"] += 1
        if artifact.get("best_backend"):
            counts["with_success"] += 1
        else:
            counts["without_success"] += 1
        records.append(
            {
                "study_doi": row["study_doi"],
                "pdf_path": str(pdf_path),
                "artifact_path": str(artifact_path),
                "best_backend": artifact.get("best_backend", ""),
                "best_char_count": artifact.get("best_char_count", 0),
                "best_section_count": artifact.get("best_section_count", 0),
                "write_status": write_reason,
            }
        )
        print(
            "RESULT: local PDF conversion "
            f"{index:,}/{len(rows):,} doi={row['study_doi']} "
            f"backend={artifact.get('best_backend', '') or '<none>'} "
            f"chars={artifact.get('best_char_count', 0)} "
            f"write={write_reason}",
            flush=True,
        )

    source_identity_audit_refresh: dict | None = None
    route_rebuild_summary: dict | None = None
    if rebuild_routes_after and counts.get("written", 0) > 0:
        source_identity_audit_refresh = refresh_source_identity_audit(
            artifact_dir=out_dir,
            candidate_table=candidate_table,
            metadata_table=metadata_table,
            report_json=source_identity_audit,
            report_csv=source_identity_audit_csv,
            unverified_doi_file=source_identity_unverified_dois,
            identity_registry_path=identity_registry,
            pdf_hash_attestation_registry_path=pdf_hash_attestation_registry,
        )
        route_rebuild_summary = rebuild_routes(
            route_table=route_table,
            metadata_table=metadata_table,
            candidate_table=candidate_table,
            prescreen_table=prescreen_table,
            domain_routing_table=domain_routing_table,
            fulltext_dir=fulltext_dir,
            paper_root=paper_root,
            summary_json=summary_json,
            counts_csv=counts_csv,
            manual_route_overrides=manual_route_overrides,
            source_identity_audit=source_identity_audit,
        )

    report = {
        "generated_at_utc": now_utc(),
        "route_table": str(route_table.resolve()),
        "metadata_table": str(metadata_table.resolve()),
        "candidate_table": str(candidate_table.resolve()),
        "fulltext_dir": str(fulltext_dir.resolve()),
        "out_dir": str(out_dir.resolve()),
        "route_action": route_action,
        "backend": backend,
        "only_missing_artifacts": only_missing_artifacts,
        "limit": limit,
        "counts": {
            "selected_before_limit": all_candidate_count,
            "selected": len(rows),
            "skipped": dict(skipped),
            **dict(counts),
        },
        "route_rebuild": {
            "performed": route_rebuild_summary is not None,
            "summary": route_rebuild_summary or {},
        },
        "source_identity_audit": {
            "refreshed": source_identity_audit_refresh is not None,
            "report_json": str(Path(source_identity_audit).resolve()),
        },
        "records": records,
    }
    write_json(report_path, report)
    print(f"LOCAL_PDF_CONVERSION: report={report_path}", flush=True)
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route-table", default=str(DEFAULT_OUTPUT_TABLE))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--prescreen-table", default=str(DEFAULT_PRESCREEN_TABLE))
    parser.add_argument("--domain-routing-table", default=str(DEFAULT_DOMAIN_ROUTING_TABLE))
    parser.add_argument("--fulltext-dir", default=str(DEFAULT_FULLTEXT_DIR))
    parser.add_argument("--source-identity-audit", default=str(DEFAULT_SOURCE_IDENTITY_AUDIT))
    parser.add_argument(
        "--source-identity-audit-csv",
        default=str(DEFAULT_SOURCE_IDENTITY_AUDIT_CSV),
    )
    parser.add_argument(
        "--source-identity-unverified-dois",
        default=str(DEFAULT_SOURCE_IDENTITY_UNVERIFIED_DOIS),
    )
    parser.add_argument("--identity-registry", default=str(DEFAULT_IDENTITY_REGISTRY))
    parser.add_argument(
        "--pdf-hash-attestation-registry",
        default=str(DEFAULT_PDF_HASH_ATTESTATION_REGISTRY),
    )
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--paper-root", default=str(DEFAULT_PAPER_ROOT))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--route-summary-json", default=str(DEFAULT_SUMMARY_JSON))
    parser.add_argument("--route-counts-csv", default=str(DEFAULT_COUNTS_CSV))
    parser.add_argument("--manual-route-overrides", default=str(DEFAULT_MANUAL_ROUTE_OVERRIDES))
    parser.add_argument("--doi-file", default="")
    parser.add_argument("--route-action", default=DEFAULT_ROUTE_ACTION)
    parser.add_argument("--backend", choices=["auto", "all", "docling", "grobid", "pdftotext"], default="grobid")
    parser.add_argument("--grobid-url", default=DEFAULT_GROBID_URL)
    parser.add_argument("--grobid-retries", type=int, default=2)
    parser.add_argument("--grobid-retry-wait-sec", type=int, default=5)
    parser.add_argument("--grobid-consolidate-header", choices=["0", "1", "2", "3"], default="0")
    parser.add_argument("--grobid-consolidate-citations", choices=["0", "1", "2"], default="0")
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--include-existing-artifacts", action="store_true")
    parser.add_argument("--write-failed-artifacts", action="store_true")
    parser.add_argument("--no-rebuild-routes-after", action="store_true")
    parser.add_argument("--no-pdf-env-bootstrap", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    if not args.no_pdf_env_bootstrap:
        ensure_pdf_runtime()
    doi_filter = read_doi_file(Path(args.doi_file).resolve()) if args.doi_file.strip() else None
    convert_routed_local_pdfs(
        route_table=Path(args.route_table).resolve(),
        metadata_table=Path(args.metadata_table).resolve(),
        candidate_table=Path(args.candidate_table).resolve(),
        prescreen_table=Path(args.prescreen_table).resolve(),
        domain_routing_table=Path(args.domain_routing_table).resolve() if args.domain_routing_table.strip() else None,
        fulltext_dir=Path(args.fulltext_dir).resolve(),
        out_dir=Path(args.out_dir).resolve(),
        paper_root=Path(args.paper_root).resolve(),
        report_path=Path(args.report).resolve(),
        summary_json=Path(args.route_summary_json).resolve(),
        counts_csv=Path(args.route_counts_csv).resolve(),
        manual_route_overrides=Path(args.manual_route_overrides).resolve()
        if args.manual_route_overrides.strip()
        else None,
        doi_filter=doi_filter,
        route_action=args.route_action,
        backend=args.backend,
        grobid_url=args.grobid_url,
        grobid_retries=args.grobid_retries,
        grobid_retry_wait_sec=args.grobid_retry_wait_sec,
        grobid_consolidate_header=args.grobid_consolidate_header,
        grobid_consolidate_citations=args.grobid_consolidate_citations,
        timeout_sec=args.timeout_sec,
        limit=max(0, args.limit),
        only_missing_artifacts=not bool(args.include_existing_artifacts),
        write_failed_artifacts=bool(args.write_failed_artifacts),
        rebuild_routes_after=not bool(args.no_rebuild_routes_after),
        source_identity_audit=Path(args.source_identity_audit).resolve(),
        source_identity_audit_csv=Path(args.source_identity_audit_csv).resolve(),
        source_identity_unverified_dois=Path(args.source_identity_unverified_dois).resolve(),
        identity_registry=Path(args.identity_registry).resolve(),
        pdf_hash_attestation_registry=Path(args.pdf_hash_attestation_registry).resolve(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
