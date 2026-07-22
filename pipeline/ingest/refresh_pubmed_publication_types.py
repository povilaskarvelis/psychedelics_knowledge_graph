#!/usr/bin/env python3
"""Refresh PubMed publication-type labels in the corpus metadata table."""

from __future__ import annotations

import argparse
import datetime as dt
from http.client import IncompleteRead
from pathlib import Path
import sys
import time
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.enrich_paper_metadata import DEFAULT_OUTPUT_TABLE, DEFAULT_PAPERS_TABLE, clean
from pipeline.ingest.materialize_candidate_metadata import materialize_candidate_metadata
from pipeline.ingest.metadata_utils import (
    PAPER_METADATA_SCHEMA_VERSION,
    RateLimitedHttpClient,
    load_config,
    normalize,
    normalize_doi,
    publication_types_from_pubmed_article,
    read_float,
    read_int,
)


def read_doi_file(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"DOI file does not exist: {path}")
    dois: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        doi = clean(line).removeprefix("https://doi.org/").removeprefix("http://doi.org/")
        if doi and not doi.startswith("#"):
            dois.add(doi.lower())
    return dois


def unique_pmids(values: pd.Series) -> list[str]:
    pmids: list[str] = []
    seen: set[str] = set()
    for value in values:
        pmid = clean(value)
        if not pmid or pmid in seen:
            continue
        seen.add(pmid)
        pmids.append(pmid)
    return pmids


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def pubmed_common_params(email: str, api_key: str) -> dict[str, object]:
    return {
        "tool": "psychedelics_kg",
        "email": email or None,
        "api_key": api_key or None,
    }


def fetch_pubmed_publication_types(
    client: RateLimitedHttpClient,
    pmids: list[str],
    *,
    email: str,
    api_key: str,
) -> dict[str, str]:
    if not pmids:
        return {}
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    raw = client.get_bytes(
        f"{base}/efetch.fcgi?"
        + urlencode(
            {
                **pubmed_common_params(email, api_key),
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "xml",
            }
        ),
        headers={},
    )
    root = ET.fromstring(raw)
    out: dict[str, str] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid = normalize(article.findtext(".//MedlineCitation/PMID"))
        publication_type = publication_types_from_pubmed_article(article)
        if pmid and publication_type:
            out[pmid] = publication_type
    return out


def update_publication_types(
    df: pd.DataFrame,
    pubmed_types_by_pmid: dict[str, str],
) -> tuple[pd.DataFrame, int]:
    out = df.copy()
    updated = 0
    if "paper_metadata_schema_version" not in out.columns:
        out["paper_metadata_schema_version"] = PAPER_METADATA_SCHEMA_VERSION
    for index, row in out.iterrows():
        pmid = normalize(row.get("pmid", ""))
        publication_type = pubmed_types_by_pmid.get(pmid, "")
        if not publication_type:
            continue
        current = clean(row.get("publication_type", ""))
        if current == publication_type:
            continue
        out.at[index, "publication_type"] = publication_type
        out.at[index, "paper_metadata_schema_version"] = PAPER_METADATA_SCHEMA_VERSION
        updated += 1
    return out, updated


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh corpus publication_type values from PubMed by PMID.")
    parser.add_argument("--metadata-table", default=str(DEFAULT_OUTPUT_TABLE))
    parser.add_argument("--candidate-table", default=str(DEFAULT_PAPERS_TABLE))
    parser.add_argument(
        "--no-update-candidate-table",
        action="store_true",
        help="Do not materialize refreshed publication types into the candidate ledger.",
    )
    parser.add_argument("--output-table", default="")
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.example.yaml"))
    parser.add_argument("--doi-file", default="", help="Optional DOI list limiting rows to refresh.")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--pubmed-rps", type=float, default=None)
    parser.add_argument("--max-retries", type=int, default=None)
    parser.add_argument("--timeout-sec", type=int, default=40)
    parser.add_argument("--max-retry-after-sec", type=int, default=120)
    parser.add_argument("--batch-retries", type=int, default=2)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    metadata_table = Path(args.metadata_table).resolve()
    output_table = Path(args.output_table).resolve() if clean(args.output_table) else metadata_table
    df = pd.read_parquet(metadata_table)
    if "pmid" not in df.columns:
        raise SystemExit(f"Metadata table has no pmid column: {metadata_table}")

    scoped = df.copy()
    if clean(args.doi_file):
        allowed_dois = read_doi_file(Path(args.doi_file).resolve())
        scoped = scoped[scoped["doi"].fillna("").astype(str).str.lower().isin(allowed_dois)].copy()
    scoped = scoped[scoped["pmid"].fillna("").astype(str).str.strip().ne("")]
    pmids = unique_pmids(scoped["pmid"])
    if args.limit > 0:
        pmids = pmids[: args.limit]

    config = load_config(Path(args.config).resolve())
    pubmed_cfg = config.get("pubmed", {}) if isinstance(config.get("pubmed", {}), dict) else {}
    email = str(pubmed_cfg.get("email", ""))
    api_key = str(pubmed_cfg.get("api_key", ""))
    max_retries = args.max_retries if args.max_retries is not None else read_int(pubmed_cfg.get("max_retries"), 4)
    client = RateLimitedHttpClient(
        rps=args.pubmed_rps if args.pubmed_rps is not None else read_float(pubmed_cfg.get("rate_limit_per_sec"), 2.5),
        max_retries=max_retries,
        timeout_sec=max(1, args.timeout_sec),
        max_retry_after_sec=max(0, args.max_retry_after_sec),
        user_agent="kg-pipeline/pubmed-publication-type-refresh",
    )

    print(f"START: PubMed publication type refresh pmids={len(pmids):,} output={output_table}", flush=True)
    pubmed_types_by_pmid: dict[str, str] = {}
    batches = chunks(pmids, max(1, args.batch_size))
    for batch_index, batch in enumerate(batches, start=1):
        for attempt in range(max(0, args.batch_retries) + 1):
            try:
                pubmed_types_by_pmid.update(fetch_pubmed_publication_types(client, batch, email=email, api_key=api_key))
                break
            except IncompleteRead:
                if attempt >= max(0, args.batch_retries):
                    raise
                time.sleep(2.5 * (attempt + 1))
        if args.progress_every > 0 and (batch_index % args.progress_every == 0 or batch_index == len(batches)):
            print(
                "PROGRESS: PubMed publication type refresh "
                f"batches={batch_index:,}/{len(batches):,} labels={len(pubmed_types_by_pmid):,}",
                flush=True,
            )

    refreshed, updated = update_publication_types(df, pubmed_types_by_pmid)
    candidate_materialization: dict = {}
    if not args.dry_run:
        output_table.parent.mkdir(parents=True, exist_ok=True)
        refreshed.to_parquet(output_table, engine="pyarrow", index=False)
        if not args.no_update_candidate_table and pubmed_types_by_pmid:
            updated_dois = {
                normalize_doi(value).lower()
                for value in refreshed.loc[
                    refreshed["pmid"].map(normalize).isin(pubmed_types_by_pmid), "doi"
                ].tolist()
                if normalize_doi(value)
            }
            candidate_materialization = materialize_candidate_metadata(
                candidate_table=Path(args.candidate_table).resolve(),
                metadata_table=output_table,
                run_id="pubmed_publication_type_refresh_"
                + dt.datetime.now(dt.timezone.utc).strftime("%Y_%m_%d_%H%M%S"),
                fields=("publication_type", "paper_metadata_schema_version"),
                scoped_dois=updated_dois,
                overwrite_existing=True,
            )

    print(f"Rows with PubMed publication type labels: {len(pubmed_types_by_pmid):,}")
    print(f"Rows updated: {updated:,}")
    print(f"Dry run: {bool(args.dry_run)}")
    print(f"Metadata table: {output_table}")
    if candidate_materialization:
        print(
            "Candidate metadata materialization: "
            f"matched={candidate_materialization['materialized_candidate_rows']:,} "
            f"changed={candidate_materialization['changed_candidate_rows']:,}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
