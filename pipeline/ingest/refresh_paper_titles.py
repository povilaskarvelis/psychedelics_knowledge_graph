#!/usr/bin/env python3
"""Refresh stored paper titles without touching other metadata fields."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.enrich_paper_metadata import DEFAULT_OUTPUT_TABLE, clean
from pipeline.ingest.metadata_utils import (
    RateLimitedHttpClient,
    crossref_title_with_subtitle,
    first_list_value,
    load_config,
    normalize_doi,
    read_float,
    read_int,
    strip_dangling_title_colon,
    strip_markup,
)

DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_PRESCREEN_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_prescreen_decisions.parquet"
TITLE_RISK_PROVIDERS = {"", "crossref", "unpaywall", "openalex", "semantic_scholar"}
HTMLISH_TITLE_RE = re.compile(r"&lt;|&gt;|&amp;|<[^>]+>", re.I)


def comparable_title(value: object) -> str:
    text = strip_markup(value)
    text = text.casefold()
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def read_doi_file(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"DOI file does not exist: {path}")
    dois: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        doi = normalize_doi(clean(line).split(",", 1)[0])
        if doi and not doi.startswith("#"):
            dois.add(doi.lower())
    return dois


def retained_dois(prescreen_table: Path) -> set[str]:
    if not prescreen_table.exists():
        return set()
    df = pd.read_parquet(prescreen_table)
    if "doi" not in df.columns:
        return set()
    retained_mask = pd.Series(False, index=df.index)
    if "prescreen_decision" in df.columns:
        retained_mask = retained_mask | df["prescreen_decision"].fillna("").astype(str).eq("retain")
    if "retained_for_extraction_candidate" in df.columns:
        retained_mask = retained_mask | df["retained_for_extraction_candidate"].fillna(False).astype(bool)
    return {
        normalize_doi(clean(value)).lower()
        for value in df.loc[retained_mask, "doi"].tolist()
        if normalize_doi(clean(value))
    }


def title_scope_mask(df: pd.DataFrame, *, provider_scope: str) -> pd.Series:
    if provider_scope == "all":
        return pd.Series(True, index=df.index)
    provider = df.get("metadata_provider", pd.Series("", index=df.index)).fillna("").astype(str).str.lower()
    chain = df.get("metadata_provider_chain", pd.Series("", index=df.index)).fillna("").astype(str).str.lower()
    title = df.get("study_title", pd.Series("", index=df.index)).fillna("").astype(str)
    return (
        provider.isin(TITLE_RISK_PROVIDERS)
        | chain.str.contains("crossref", regex=False)
        | title.str.contains(HTMLISH_TITLE_RE, regex=True)
        | title.str.contains(r":\s*$", regex=True)
    )


def candidate_rows(
    df: pd.DataFrame,
    *,
    doi_file: str,
    prescreen_table: str,
    only_retained: bool,
    provider_scope: str,
    limit: int,
) -> pd.DataFrame:
    out = df.copy()
    scoped_dois: set[str] = set()
    if clean(doi_file):
        scoped_dois.update(read_doi_file(Path(doi_file).resolve()))
    if only_retained:
        scoped_dois.update(retained_dois(Path(prescreen_table).resolve()))
    if scoped_dois:
        doi_values = out["doi"].map(lambda value: normalize_doi(clean(value)).lower())
        out = out[doi_values.isin(scoped_dois)].copy()
    out = out[title_scope_mask(out, provider_scope=provider_scope)].copy()
    if limit > 0:
        out = out.head(limit).copy()
    return out


def lookup_crossref_title(
    client: RateLimitedHttpClient,
    doi: str,
    *,
    email: str,
) -> tuple[str, bool]:
    from urllib.parse import quote

    params = {"mailto": email} if email else {}
    payload = client.get_json(f"https://api.crossref.org/works/{quote(doi, safe='')}", params=params, headers={})
    item = payload.get("message", {}) if isinstance(payload, dict) else {}
    if not isinstance(item, dict) or normalize_doi(item.get("DOI", "")).lower() != normalize_doi(doi).lower():
        return "", False
    subtitle_present = bool(first_list_value(item.get("subtitle", "")))
    return crossref_title_with_subtitle(item), subtitle_present


def preferred_title(current_title: object, crossref_title: object, *, crossref_has_subtitle: bool) -> tuple[str, str]:
    current = clean(current_title)
    cleaned_current = strip_markup(current)
    candidate = strip_markup(crossref_title)
    if not current and candidate:
        return candidate, "filled_from_crossref"
    if cleaned_current and cleaned_current != current:
        current = cleaned_current
    current_cmp = comparable_title(current)
    candidate_cmp = comparable_title(candidate)
    if not candidate_cmp:
        cleaned_colon = strip_dangling_title_colon(current)
        if cleaned_colon != current:
            return cleaned_colon, "removed_dangling_title_colon"
        return current, "cleaned_current_title" if current != clean(current_title) else ""
    if current_cmp == candidate_cmp:
        cleaned_colon = strip_dangling_title_colon(current)
        if cleaned_colon != current and not crossref_has_subtitle:
            return cleaned_colon, "removed_dangling_title_colon"
        return current, "cleaned_current_title" if current != clean(current_title) else ""
    if crossref_has_subtitle and current_cmp and candidate_cmp.startswith(current_cmp):
        return candidate, "added_crossref_subtitle"
    if current.rstrip().endswith(":") and candidate_cmp.startswith(comparable_title(current.rstrip(":"))):
        return candidate, "completed_trailing_colon_title"
    return current, "cleaned_current_title" if current != clean(current_title) else ""


def apply_title_updates(df: pd.DataFrame, updates_by_doi: dict[str, str]) -> tuple[pd.DataFrame, int]:
    out = df.copy()
    updated = 0
    if "doi" not in out.columns or "study_title" not in out.columns:
        return out, 0
    for index, row in out.iterrows():
        doi = normalize_doi(clean(row.get("doi", ""))).lower()
        title = updates_by_doi.get(doi, "")
        if not title:
            continue
        current = clean(row.get("study_title", ""))
        if current == title:
            continue
        out.at[index, "study_title"] = title
        updated += 1
    return out, updated


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh paper titles from Crossref title/subtitle metadata.")
    parser.add_argument("--metadata-table", default=str(DEFAULT_OUTPUT_TABLE))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--prescreen-table", default=str(DEFAULT_PRESCREEN_TABLE))
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.example.yaml"))
    parser.add_argument("--doi-file", default="")
    parser.add_argument("--only-retained", action="store_true")
    parser.add_argument("--provider-scope", choices=["risk", "all"], default="risk")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--write-every", type=int, default=100)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--timeout-sec", type=int, default=40)
    parser.add_argument("--max-retry-after-sec", type=int, default=120)
    parser.add_argument("--max-retries", type=int, default=None)
    parser.add_argument("--crossref-email", default="")
    parser.add_argument("--crossref-rps", type=float, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    metadata_table = Path(args.metadata_table).resolve()
    candidate_table = Path(args.candidate_table).resolve()
    df = pd.read_parquet(metadata_table)
    selected = candidate_rows(
        df,
        doi_file=args.doi_file,
        prescreen_table=args.prescreen_table,
        only_retained=bool(args.only_retained),
        provider_scope=args.provider_scope,
        limit=args.limit,
    )

    config = load_config(Path(args.config).resolve())
    crossref_cfg = config.get("crossref", {}) if isinstance(config.get("crossref", {}), dict) else {}
    email = args.crossref_email or str(crossref_cfg.get("email", ""))
    max_retries = args.max_retries if args.max_retries is not None else read_int(crossref_cfg.get("max_retries"), 3)
    client = RateLimitedHttpClient(
        rps=args.crossref_rps if args.crossref_rps is not None else read_float(crossref_cfg.get("rate_limit_per_sec"), 5.0),
        max_retries=max_retries,
        timeout_sec=max(1, args.timeout_sec),
        max_retry_after_sec=max(0, args.max_retry_after_sec),
        user_agent="kg-pipeline/title-refresh-crossref",
    )

    print(
        "START: Crossref title refresh "
        f"rows={len(selected):,} only_retained={bool(args.only_retained)} provider_scope={args.provider_scope}",
        flush=True,
    )
    updates_by_doi: dict[str, str] = {}
    reason_counts: dict[str, int] = {}
    errors = 0
    no_crossref_title = 0
    checked = 0
    working_df = df.copy()

    for row_number, (index, row) in enumerate(selected.iterrows(), start=1):
        doi = normalize_doi(clean(row.get("doi", ""))).lower()
        if not doi:
            continue
        checked += 1
        try:
            crossref_title, crossref_has_subtitle = lookup_crossref_title(client, doi, email=email)
        except Exception as err:
            errors += 1
            if args.progress_every > 0:
                print(f"WARN: title refresh failed for {doi}: {type(err).__name__}: {err}", flush=True)
            continue
        if not crossref_title:
            no_crossref_title += 1
        title, reason = preferred_title(
            row.get("study_title", ""),
            crossref_title,
            crossref_has_subtitle=crossref_has_subtitle,
        )
        if reason:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        if title and title != clean(row.get("study_title", "")):
            updates_by_doi[doi] = title
            working_df.at[index, "study_title"] = title

        if not args.dry_run and args.write_every > 0 and row_number % args.write_every == 0:
            working_df.to_parquet(metadata_table, engine="pyarrow", index=False)
        if args.progress_every > 0 and (row_number % args.progress_every == 0 or row_number == len(selected)):
            print(
                "PROGRESS: Crossref title refresh "
                f"{row_number:,}/{len(selected):,} updates={len(updates_by_doi):,} errors={errors:,}",
                flush=True,
            )

    if not args.dry_run:
        working_df.to_parquet(metadata_table, engine="pyarrow", index=False)
        candidate_updates = 0
        if candidate_table.exists() and updates_by_doi:
            candidate_df = pd.read_parquet(candidate_table)
            candidate_df, candidate_updates = apply_title_updates(candidate_df, updates_by_doi)
            candidate_df.to_parquet(candidate_table, engine="pyarrow", index=False)
    else:
        candidate_updates = 0

    print(f"Rows checked: {checked:,}")
    print(f"Titles updated: {len(updates_by_doi):,}")
    print(f"Candidate table rows updated: {candidate_updates:,}")
    print(f"No Crossref title: {no_crossref_title:,}")
    print(f"Errors: {errors:,}")
    print(f"Reason counts: {reason_counts}")
    print(f"Dry run: {bool(args.dry_run)}")
    print(f"Metadata table: {metadata_table}")
    print(f"Candidate table: {candidate_table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
