#!/usr/bin/env python3
"""Build a provider-verified, high-confidence manual PDF recovery queue."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[2]
AUDITS = ROOT / "data" / "processed" / "corpus" / "audits"
DEFAULT_QUEUE = AUDITS / "manual_pdf_recovery_priority_queue.csv"
DEFAULT_PROGRESS = AUDITS / "manual_pdf_pattern_scout_browser_progress_20260720.csv"
DEFAULT_CANDIDATES = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_OUTPUT = AUDITS / "manual_pdf_recovery_high_confidence_remaining_20260720.csv"
DEFAULT_URLS = AUDITS / "manual_pdf_recovery_high_confidence_remaining_20260720_urls.txt"
DEFAULT_REPORT = AUDITS / "manual_pdf_recovery_high_confidence_remaining_20260720.json"
OPENALEX_ENDPOINT = "https://api.openalex.org/works"


def clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def load_excluded_dois(paths: list[str]) -> set[str]:
    dois: set[str] = set()
    for raw in paths:
        path = Path(raw).resolve()
        if not path.is_file():
            continue
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        if "doi" in frame:
            dois.update(clean(value).lower() for value in frame["doi"] if clean(value))
    return dois


def local_candidates(queue: pd.DataFrame, progress: pd.DataFrame) -> pd.DataFrame:
    seen = {clean(value).lower() for value in progress.get("doi", []) if clean(value)}
    unseen = queue[~queue["doi"].astype(str).str.lower().isin(seen)].copy()
    return unseen[
        unseen["open_access_status"].isin(["gold", "hybrid", "green"])
        & unseen["route_host_class"].isin(["publisher_platform", "repository_or_institutional"])
        & unseen["publication_format_review_signal"].astype(str).str.strip().eq("")
        & unseen["language_audit_decision"].eq("retain_language_eligible")
        & unseen["prior_download_failure"].ne("source_identity_mismatch")
    ].copy()


def fetch_openalex(openalex_ids: list[str], *, batch_size: int, api_key: str) -> dict[str, dict]:
    works: dict[str, dict] = {}
    headers = {"User-Agent": "psychedelics-kg-high-confidence-recovery/1.0"}
    for start in range(0, len(openalex_ids), batch_size):
        chunk = openalex_ids[start : start + batch_size]
        params = {
            "filter": "openalex_id:" + "|".join(chunk),
            "per-page": 100,
            "select": (
                "id,doi,display_name,publication_year,type,language,is_retracted,cited_by_count,"
                "open_access,best_oa_location,primary_location,ids"
            ),
        }
        if api_key:
            params["api_key"] = api_key
        response = requests.get(OPENALEX_ENDPOINT, params=params, headers=headers, timeout=60)
        response.raise_for_status()
        for work in response.json().get("results", []):
            identifier = clean(work.get("id", "")).rstrip("/").rsplit("/", 1)[-1]
            if identifier:
                works[identifier] = work
    return works


def verified_rows(candidates: pd.DataFrame, works: dict[str, dict]) -> pd.DataFrame:
    rows: list[dict] = []
    for raw in candidates.fillna("").to_dict("records"):
        work = works.get(clean(raw.get("openalex_id", "")), {})
        oa = work.get("open_access") or {}
        best = work.get("best_oa_location") or {}
        primary = work.get("primary_location") or {}
        source = primary.get("source") or {}
        ids = work.get("ids") or {}
        work_type = clean(work.get("type", ""))
        version = clean(best.get("version", ""))
        is_journal = clean(source.get("type", "")).lower() == "journal"
        is_core = bool(source.get("is_core"))
        eligible = (
            work_type in {"article", "review"}
            and bool(oa.get("is_oa"))
            and not bool(work.get("is_retracted"))
            and version in {"publishedVersion", "acceptedVersion"}
            and (is_journal or is_core)
        )
        if not eligible:
            continue
        cited = int(work.get("cited_by_count") or 0)
        pdf_url = clean(best.get("pdf_url", ""))
        landing_url = clean(best.get("landing_page_url", "")) or clean(oa.get("oa_url", ""))
        launch_url = pdf_url or landing_url or clean(raw.get("primary_route_url", ""))
        if not launch_url:
            continue
        pmid = clean(ids.get("pmid", "")).replace("https://pubmed.ncbi.nlm.nih.gov/", "").rstrip("/")
        quality_score = (
            (50 if is_core else 0)
            + (25 if is_journal else 0)
            + (30 if version == "publishedVersion" else 18)
            + (15 if pdf_url else 0)
            + (8 if clean(best.get("license", "")) else 0)
            + min(40, math.log2(cited + 1) * 5)
            + (8 if pmid else 0)
        )
        rows.append(
            {
                "doi": clean(raw.get("doi", "")).lower(),
                "study_title": clean(raw.get("study_title", "")),
                "study_year": clean(raw.get("study_year", "")),
                "study_journal": clean(source.get("display_name", "")) or clean(raw.get("study_journal", "")),
                "source_family": clean(raw.get("source_family", "")),
                "source_type": clean(raw.get("source_type", "")),
                "openalex_work_type": work_type,
                "openalex_oa_status": clean(oa.get("oa_status", "")),
                "openalex_version": version,
                "openalex_license": clean(best.get("license", "")),
                "openalex_source_is_core": is_core,
                "openalex_source_type": clean(source.get("type", "")),
                "cited_by_count": cited,
                "pmid": pmid,
                "direct_pdf_url": pdf_url,
                "oa_landing_url": landing_url,
                "doi_url": clean(raw.get("doi_url", "")) or f"https://doi.org/{clean(raw.get('doi', '')).lower()}",
                "launch_url": launch_url,
                "quality_score": round(quality_score, 2),
                "verification_basis": (
                    "Current OpenAlex record: eligible article/review; OA; non-retracted; "
                    "published/accepted version; journal/core source."
                ),
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["quality_score", "cited_by_count", "doi"], ascending=[False, False, True]
    ).reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-csv", default=str(DEFAULT_QUEUE))
    parser.add_argument("--progress-csv", default=str(DEFAULT_PROGRESS))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--exclude-csv", action="append", default=[])
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-urls", default=str(DEFAULT_URLS))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT))
    parser.add_argument("--openalex-api-key", default="")
    parser.add_argument("--openalex-batch-size", type=int, default=45)
    args = parser.parse_args()

    queue = pd.read_csv(Path(args.queue_csv), dtype=str, keep_default_na=False)
    progress_path = Path(args.progress_csv)
    progress = (
        pd.read_csv(progress_path, dtype=str, keep_default_na=False)
        if progress_path.is_file()
        else pd.DataFrame()
    )
    local = local_candidates(queue, progress)
    candidate_columns = ["doi", "openalex_id", "pmid"]
    metadata = pd.read_parquet(Path(args.candidate_table), columns=candidate_columns).fillna("")
    local = local.merge(metadata, on="doi", how="left", validate="one_to_one")
    openalex_ids = [clean(value) for value in local["openalex_id"] if clean(value)]
    works = fetch_openalex(
        openalex_ids,
        batch_size=max(1, min(args.openalex_batch_size, 50)),
        api_key=clean(args.openalex_api_key),
    )
    verified = verified_rows(local, works)
    excluded_dois = load_excluded_dois(args.exclude_csv)
    remaining = verified[~verified["doi"].isin(excluded_dois)].copy() if len(verified) else verified
    if len(remaining):
        remaining.insert(0, "batch_order", range(1, len(remaining) + 1))

    output_csv = Path(args.output_csv).resolve()
    output_urls = Path(args.output_urls).resolve()
    report_path = Path(args.report_json).resolve()
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    remaining.to_csv(output_csv, index=False)
    output_urls.write_text(
        "\n".join(remaining.get("launch_url", pd.Series(dtype=str)).astype(str))
        + ("\n" if len(remaining) else ""),
        encoding="utf-8",
    )
    report = {
        "schema_version": "manual_pdf_recovery_high_confidence_v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_queue_rows": len(queue),
        "local_candidates": len(local),
        "openalex_ids_queried": len(openalex_ids),
        "openalex_records_retrieved": len(works),
        "provider_verified_before_exclusions": len(verified),
        "explicitly_excluded_reviewed_dois": len(set(verified.get("doi", [])) & excluded_dois),
        "remaining_rows": len(remaining),
        "output_csv": str(output_csv),
        "output_urls": str(output_urls),
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
