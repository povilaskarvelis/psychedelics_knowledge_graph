#!/usr/bin/env python3
"""Export the remaining routed PDF-download queue for manual retrieval."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

try:
    from pipeline.ingest.sync_paper_library import normalize_doi, pdf_filename_for_doi
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.ingest.sync_paper_library import normalize_doi, pdf_filename_for_doi


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROUTE_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes.parquet"
DEFAULT_METADATA_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_PDF_DIR = ROOT / "data" / "raw" / "papers" / "pdfs"
DEFAULT_OUTPUT_CSV = ROOT / "data" / "processed" / "corpus" / "audits" / "manual_pdf_download_dois.csv"
DEFAULT_OUTPUT_TXT = ROOT / "data" / "processed" / "corpus" / "audits" / "manual_pdf_download_dois.txt"
DEFAULT_ROUTE_ACTION = "download_pdf_then_extract"
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


def selected_route_rows(routes_df: pd.DataFrame, route_action: str) -> pd.DataFrame:
    if routes_df.empty:
        return routes_df.copy()
    selected = routes_df.copy()
    if "retained_for_extraction_candidate" in selected.columns:
        selected = selected[selected["retained_for_extraction_candidate"].map(truthy)].copy()
    if "route_action" in selected.columns:
        selected = selected[selected["route_action"].fillna("").astype(str).eq(route_action)].copy()
    return selected


def export_manual_pdf_queue(
    *,
    route_table: Path = DEFAULT_ROUTE_TABLE,
    metadata_table: Path = DEFAULT_METADATA_TABLE,
    candidate_table: Path = DEFAULT_CANDIDATE_TABLE,
    pdf_dir: Path = DEFAULT_PDF_DIR,
    output_csv: Path = DEFAULT_OUTPUT_CSV,
    output_txt: Path = DEFAULT_OUTPUT_TXT,
    route_action: str = DEFAULT_ROUTE_ACTION,
) -> dict:
    routes_df = pd.read_parquet(route_table)
    metadata_df = pd.read_parquet(metadata_table) if metadata_table.exists() else pd.DataFrame()
    candidate_df = pd.read_parquet(candidate_table) if candidate_table.exists() else pd.DataFrame()
    metadata_by_doi = records_by_doi(metadata_df)
    candidate_by_doi = records_by_doi(candidate_df)
    selected = selected_route_rows(routes_df, route_action)

    rows: list[dict] = []
    if not selected.empty:
        selected = selected.assign(_doi_key=selected["doi"].map(doi_key))
        for doi, group in selected.groupby("_doi_key", sort=True):
            if not doi:
                continue
            first = group.iloc[0].to_dict()
            candidate = candidate_by_doi.get(doi, {})
            metadata = metadata_by_doi.get(doi, {})
            filename = pdf_filename_for_doi(doi)
            rows.append(
                {
                    "doi": doi,
                    "suggested_pdf_filename": filename,
                    "canonical_pdf_path": str((pdf_dir / filename).resolve()),
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
                    "manual_status": "",
                    "manual_notes": "",
                }
            )

    output_df = pd.DataFrame(rows, columns=QUEUE_COLUMNS)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(output_csv, index=False)
    output_txt.parent.mkdir(parents=True, exist_ok=True)
    output_txt.write_text("\n".join(output_df.get("doi", pd.Series(dtype=str)).tolist()) + ("\n" if rows else ""))
    summary = {
        "route_table": str(route_table.resolve()),
        "candidate_table": str(candidate_table.resolve()),
        "output_csv": str(output_csv.resolve()),
        "output_txt": str(output_txt.resolve()),
        "route_action": route_action,
        "rows": len(output_df),
    }
    print(f"MANUAL_PDF_QUEUE: exported rows={len(output_df):,} csv={output_csv}", flush=True)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route-table", default=str(DEFAULT_ROUTE_TABLE))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--pdf-dir", default=str(DEFAULT_PDF_DIR))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--output-txt", default=str(DEFAULT_OUTPUT_TXT))
    parser.add_argument("--route-action", default=DEFAULT_ROUTE_ACTION)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    export_manual_pdf_queue(
        route_table=Path(args.route_table).resolve(),
        metadata_table=Path(args.metadata_table).resolve(),
        candidate_table=Path(args.candidate_table).resolve(),
        pdf_dir=Path(args.pdf_dir).resolve(),
        output_csv=Path(args.output_csv).resolve(),
        output_txt=Path(args.output_txt).resolve(),
        route_action=args.route_action,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
