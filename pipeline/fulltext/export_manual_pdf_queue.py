#!/usr/bin/env python3
"""Export the remaining routed PDF-download queue for manual retrieval."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd
import pyarrow.parquet as pq

try:
    from pipeline.ingest.metadata_utils import normalize_doi, pdf_filename_for_doi
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.ingest.metadata_utils import normalize_doi, pdf_filename_for_doi


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROUTE_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes.parquet"
DEFAULT_SELECTION_TABLE = ROOT / "data" / "processed" / "corpus" / "fulltext_enrichment_worklist.parquet"
DEFAULT_METADATA_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_PDF_DIR = ROOT / "data" / "raw" / "papers" / "pdfs"
DEFAULT_OUTPUT_CSV = ROOT / "data" / "processed" / "corpus" / "audits" / "manual_pdf_download_dois.csv"
DEFAULT_OUTPUT_TXT = ROOT / "data" / "processed" / "corpus" / "audits" / "manual_pdf_download_dois.txt"
DEFAULT_ROUTE_ACTION = "download_pdf_then_extract"
TERMINAL_MANUAL_STATUSES = {
    "article_pdf_recovered",
    "closed_access",
    "duplicate_of_canonical",
    "excluded_publication_format",
    "reviewed_pending_pdf_reconciliation",
}
QUEUE_COLUMNS = [
    "doi",
    "suggested_pdf_filename",
    "canonical_pdf_path",
    "study_title",
    "study_year",
    "study_journal",
    "pmid",
    "pmcid",
    "open_access_status",
    "pdf_download_status",
    "pdf_download_failure_category",
    "pdf_download_retry_recommended",
    "pdf_download_error",
    "best_pdf_url",
    "pdf_url_candidates",
    "open_access_url",
    "route_count",
    "domain_routes",
    "prompt_profiles",
    "source_types",
    "manual_status",
    "manual_notes",
]
QUEUE_LOOKUP_COLUMNS = {
    "doi",
    "study_title",
    "study_year",
    "study_journal",
    "pmid",
    "pmcid",
    "open_access_status",
    "pdf_download_status",
    "pdf_download_failure_category",
    "pdf_download_retry_recommended",
    "pdf_download_error",
    "pdf_local_path",
    "best_pdf_url",
    "pdf_url_candidates",
    "open_access_url",
}


def clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).lower() in {"1", "true", "yes", "y"}


def doi_key(value: object) -> str:
    return normalize_doi(clean(value)).lower()


def first_nonempty(*values: object) -> str:
    for value in values:
        text = clean(value)
        if text:
            return text
    return ""


def join_pipe_unique(values: object) -> str:
    out: list[str] = []
    for value in values:
        text = clean(value)
        if not text:
            continue
        for part in text.split("|"):
            item = part.strip()
            if item and item not in out:
                out.append(item)
    return "|".join(out)


def records_by_doi(df: pd.DataFrame) -> dict[str, dict]:
    if df.empty or "doi" not in df.columns:
        return {}
    out: dict[str, dict] = {}
    for row in df.to_dict("records"):
        key = doi_key(row.get("doi", ""))
        if key and key not in out:
            out[key] = row
    return out


def read_lookup_rows(path: Path, doi_filter: set[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    available = set(pq.read_schema(path).names)
    columns = [column for column in QUEUE_LOOKUP_COLUMNS if column in available]
    frame = pd.read_parquet(path, columns=columns)
    if doi_filter and "doi" in frame.columns:
        frame = frame[frame["doi"].map(doi_key).isin(doi_filter)].copy()
    return frame


def selected_route_rows(routes_df: pd.DataFrame, route_action: str) -> pd.DataFrame:
    if routes_df.empty:
        return routes_df.copy()
    selected = routes_df.copy()
    if "retained_for_extraction_candidate" in selected.columns:
        selected = selected[selected["retained_for_extraction_candidate"].map(truthy)].copy()
    if "route_action" in selected.columns:
        selected = selected[selected["route_action"].fillna("").astype(str).eq(route_action)].copy()
    return selected


def selected_worklist_rows(selection_df: pd.DataFrame) -> pd.DataFrame:
    """Select unresolved known-URL or OA-landing records without extraction routes."""
    if selection_df.empty:
        return selection_df.copy()
    selected = selection_df.copy()
    if "selected_for_downstream" in selected.columns:
        selected = selected[selected["selected_for_downstream"].map(truthy)].copy()
    if "fulltext_enrichment_needed" in selected.columns:
        selected = selected[selected["fulltext_enrichment_needed"].map(truthy)].copy()
    if "fulltext_enrichment_action" in selected.columns:
        selected = selected[
            selected["fulltext_enrichment_action"]
            .fillna("")
            .astype(str)
            .isin({"download_known_pdf", "resolve_oa_landing_page"})
        ].copy()
    return selected


def export_manual_pdf_queue(
    *,
    route_table: Path = DEFAULT_ROUTE_TABLE,
    selection_table: Path | None = None,
    metadata_table: Path = DEFAULT_METADATA_TABLE,
    candidate_table: Path = DEFAULT_CANDIDATE_TABLE,
    pdf_dir: Path = DEFAULT_PDF_DIR,
    output_csv: Path = DEFAULT_OUTPUT_CSV,
    output_txt: Path = DEFAULT_OUTPUT_TXT,
    route_action: str = DEFAULT_ROUTE_ACTION,
    manual_progress_csv: Path | None = None,
) -> dict:
    if selection_table is not None:
        selected = selected_worklist_rows(pd.read_parquet(selection_table))
        source_table = selection_table
        source_kind = "fulltext_enrichment_worklist"
    else:
        selected = selected_route_rows(pd.read_parquet(route_table), route_action)
        source_table = route_table
        source_kind = "extraction_routes"
    selected_dois = {
        doi_key(value)
        for value in selected.get("doi", pd.Series(dtype="object"))
        if doi_key(value)
    }
    metadata_df = read_lookup_rows(metadata_table, selected_dois)
    candidate_df = read_lookup_rows(candidate_table, selected_dois)
    metadata_by_doi = records_by_doi(metadata_df)
    candidate_by_doi = records_by_doi(candidate_df)
    progress_by_doi: dict[str, dict] = {}
    if manual_progress_csv is not None and manual_progress_csv.exists():
        progress_by_doi = records_by_doi(pd.read_csv(manual_progress_csv).fillna(""))

    rows: list[dict] = []
    skipped_local_pdf = 0
    skipped_terminal_manual_status = 0
    if not selected.empty:
        selected = selected.assign(_doi_key=selected["doi"].map(doi_key))
        for doi, group in selected.groupby("_doi_key", sort=True):
            if not doi:
                continue
            first = group.iloc[0].to_dict()
            candidate = candidate_by_doi.get(doi, {})
            metadata = metadata_by_doi.get(doi, {})
            filename = pdf_filename_for_doi(doi)
            canonical_path = pdf_dir / filename
            recorded_path = clean(candidate.get("pdf_local_path", ""))
            local_pdf_exists = canonical_path.is_file() or bool(recorded_path and Path(recorded_path).is_file())
            if local_pdf_exists:
                skipped_local_pdf += 1
                continue
            progress = progress_by_doi.get(doi, {})
            manual_status = clean(progress.get("manual_status", "")).lower()
            if manual_status in TERMINAL_MANUAL_STATUSES:
                skipped_terminal_manual_status += 1
                continue
            rows.append(
                {
                    "doi": doi,
                    "suggested_pdf_filename": filename,
                    "canonical_pdf_path": str(canonical_path.resolve()),
                    "study_title": first_nonempty(
                        first.get("study_title", ""),
                        candidate.get("study_title", ""),
                        metadata.get("study_title", ""),
                    ),
                    "study_year": first_nonempty(
                        first.get("study_year", ""),
                        candidate.get("study_year", ""),
                        metadata.get("study_year", ""),
                    ),
                    "study_journal": first_nonempty(
                        candidate.get("study_journal", ""),
                        metadata.get("study_journal", ""),
                    ),
                    "pmid": first_nonempty(candidate.get("pmid", ""), metadata.get("pmid", "")),
                    "pmcid": first_nonempty(candidate.get("pmcid", ""), metadata.get("pmcid", "")),
                    "open_access_status": first_nonempty(
                        first.get("open_access_status", ""),
                        candidate.get("open_access_status", ""),
                        metadata.get("open_access_status", ""),
                    ),
                    "pdf_download_status": clean(candidate.get("pdf_download_status", "")),
                    "pdf_download_failure_category": clean(candidate.get("pdf_download_failure_category", "")),
                    "pdf_download_retry_recommended": clean(candidate.get("pdf_download_retry_recommended", "")),
                    "pdf_download_error": clean(candidate.get("pdf_download_error", "")),
                    "best_pdf_url": first_nonempty(
                        first.get("best_pdf_url", ""),
                        candidate.get("best_pdf_url", ""),
                        metadata.get("best_pdf_url", ""),
                    ),
                    "pdf_url_candidates": first_nonempty(
                        first.get("pdf_url_candidates", ""),
                        candidate.get("pdf_url_candidates", ""),
                        metadata.get("pdf_url_candidates", ""),
                    ),
                    "open_access_url": first_nonempty(
                        candidate.get("open_access_url", ""),
                        metadata.get("open_access_url", ""),
                    ),
                    "route_count": int(len(group)),
                    "domain_routes": join_pipe_unique(group.get("domain_route", [])),
                    "prompt_profiles": join_pipe_unique(group.get("prompt_profile", [])),
                    "source_types": join_pipe_unique(group.get("source_type", [])),
                    "manual_status": manual_status,
                    "manual_notes": clean(progress.get("manual_notes", "")),
                }
            )

    output_df = pd.DataFrame(rows, columns=QUEUE_COLUMNS)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(output_csv, index=False)
    output_txt.parent.mkdir(parents=True, exist_ok=True)
    output_txt.write_text("\n".join(output_df.get("doi", pd.Series(dtype=str)).tolist()) + ("\n" if rows else ""))
    summary = {
        "route_table": str(route_table.resolve()),
        "selection_table": str(selection_table.resolve()) if selection_table is not None else "",
        "source_table": str(source_table.resolve()),
        "source_kind": source_kind,
        "candidate_table": str(candidate_table.resolve()),
        "output_csv": str(output_csv.resolve()),
        "output_txt": str(output_txt.resolve()),
        "route_action": route_action,
        "manual_progress_csv": str(manual_progress_csv.resolve()) if manual_progress_csv is not None else "",
        "skipped_local_pdf": skipped_local_pdf,
        "skipped_terminal_manual_status": skipped_terminal_manual_status,
        "rows": len(output_df),
    }
    print(f"MANUAL_PDF_QUEUE: exported rows={len(output_df):,} csv={output_csv}", flush=True)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route-table", default=str(DEFAULT_ROUTE_TABLE))
    parser.add_argument(
        "--selection-table",
        default="",
        help="Route-independent worklist; exports unresolved known-PDF and OA-landing rows.",
    )
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--pdf-dir", default=str(DEFAULT_PDF_DIR))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--output-txt", default=str(DEFAULT_OUTPUT_TXT))
    parser.add_argument("--route-action", default=DEFAULT_ROUTE_ACTION)
    parser.add_argument(
        "--manual-progress-csv",
        default="",
        help="Optional DOI progress ledger; terminal manual outcomes are omitted and partial outcomes are preserved.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    export_manual_pdf_queue(
        route_table=Path(args.route_table).resolve(),
        selection_table=Path(args.selection_table).resolve() if args.selection_table.strip() else None,
        metadata_table=Path(args.metadata_table).resolve(),
        candidate_table=Path(args.candidate_table).resolve(),
        pdf_dir=Path(args.pdf_dir).resolve(),
        output_csv=Path(args.output_csv).resolve(),
        output_txt=Path(args.output_txt).resolve(),
        route_action=args.route_action,
        manual_progress_csv=Path(args.manual_progress_csv).resolve() if args.manual_progress_csv.strip() else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
