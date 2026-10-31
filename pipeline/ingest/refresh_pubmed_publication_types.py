#!/usr/bin/env python3
"""Refresh PubMed publication-type labels in the corpus metadata table."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import datetime as dt
from difflib import SequenceMatcher
import hashlib
from http.client import IncompleteRead
from pathlib import Path
import re
import sys
import time
import unicodedata
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.enrich_paper_metadata import DEFAULT_OUTPUT_TABLE, DEFAULT_PAPERS_TABLE, clean
from pipeline.ingest.materialize_candidate_metadata import (
    atomic_write_json,
    atomic_write_parquet,
    materialize_candidate_metadata,
)
from pipeline.ingest.metadata_utils import (
    PAPER_METADATA_SCHEMA_VERSION,
    RateLimitedHttpClient,
    load_config,
    normalize,
    normalize_doi,
    publication_types_from_pubmed_article,
    read_float,
    read_int,
    strip_markup,
)
from pipeline.validate.doi_aliases import DEFAULT_DOI_ALIAS_REGISTRY, load_doi_aliases


@dataclass(frozen=True)
class PubmedPublicationRecord:
    pmid: str
    title: str
    dois: tuple[str, ...]
    publication_type: str
    abstract: str = ""
    year: str = ""
    languages: tuple[str, ...] = ()
    source_xml_sha256: str = ""


def identity_text(value: object) -> str:
    text = strip_markup(value)
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.findall(r"[^\W_]+", text, flags=re.UNICODE))


def canonical_doi(value: object, aliases: dict[str, str]) -> str:
    doi = normalize_doi(clean(value)).lower()
    seen: set[str] = set()
    while doi in aliases:
        if doi in seen:
            return ""
        seen.add(doi)
        doi = aliases[doi]
    return doi


def publication_identity_issue(
    row: pd.Series,
    source: PubmedPublicationRecord,
    aliases: dict[str, str],
) -> str:
    """Conservatively gate a label refresh; a skipped row is never excluded.

    A cached PMID, even with a matching DOI, cannot resolve a conflicting
    report. Shortened subtitles are allowed, while distinct numbered parts
    and unrelated abstracts remain separate. Text agreement is a refresh
    safeguard, not an eligibility classifier or a source-accuracy score.
    """
    if clean(row.get("pmid")) != source.pmid:
        return "pmid_mismatch"
    doi = canonical_doi(row.get("doi"), aliases)
    native_dois = {canonical_doi(value, aliases) for value in source.dois} - {""}
    if not doi or not native_dois:
        return "missing_source_doi_identity"
    if doi not in native_dois:
        return "source_doi_mismatch"
    title = identity_text(row.get("study_title", row.get("title", "")))
    native_title = identity_text(source.title)
    if not title or not native_title or native_title in {"not available", "unavailable"}:
        return "missing_source_title_identity"
    if title != native_title:
        shorter, longer = sorted((title.split(), native_title.split()), key=len)
        if len(shorter) < 4 or longer[:len(shorter)] != shorter:
            return "source_title_conflict"
    current_year = re.search(r"\b(?:19|20)\d{2}\b", clean(row.get("study_year")))
    native_year = re.search(r"\b(?:19|20)\d{2}\b", source.year)
    if current_year and native_year and abs(int(current_year[0]) - int(native_year[0])) > 1:
        return "source_year_conflict"
    abstract = identity_text(row.get("abstract"))
    native_abstract = identity_text(source.abstract)
    # Clear disagreements are held for source repair. Missing/truncated text
    # alone does not reject a consistent native DOI/title observation.
    if min(len(abstract), len(native_abstract)) >= 100:
        if SequenceMatcher(None, abstract.split(), native_abstract.split(), autojunk=False).ratio() < 0.65:
            return "source_abstract_conflict"
    current_language = clean(row.get("language")).lower()
    if current_language in {"en", "eng", "english"} and source.languages and "eng" not in source.languages:
        return "source_language_conflict_requires_version_review"
    # A registry label alone must not undo a publisher-observed format or
    # silently substitute a preprint for a published version with the same DOI.
    format_pattern = re.compile(
        r"preprint|conference|meeting abstract|poster|book[ _-]?chapter|thesis|dissertation|correction|erratum|retraction|protocol",
        re.I,
    )
    current_formats = set(format_pattern.findall(clean(row.get("publication_type")).lower()))
    native_formats = set(format_pattern.findall(source.publication_type.lower()))
    if current_formats != native_formats:
        return "source_publication_format_conflict"
    return ""


def parse_pubmed_publication_types(raw: bytes) -> dict[str, PubmedPublicationRecord]:
    root = ET.fromstring(raw)
    fingerprint = hashlib.sha256(raw).hexdigest()
    out: dict[str, PubmedPublicationRecord] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid = normalize(article.findtext("MedlineCitation/PMID"))
        title = article.find("MedlineCitation/Article/ArticleTitle")
        if not pmid:
            continue
        out[pmid] = PubmedPublicationRecord(
            pmid=pmid,
            title="".join(title.itertext()) if title is not None else "",
            dois=tuple(normalize_doi(node.text).lower() for node in article.findall(
                "PubmedData/ArticleIdList/ArticleId[@IdType='doi']") if node.text),
            publication_type=publication_types_from_pubmed_article(article),
            abstract=" ".join("".join(node.itertext()) for node in article.findall(
                "MedlineCitation/Article/Abstract/AbstractText")),
            year=article.findtext("MedlineCitation/Article/Journal/JournalIssue/PubDate/Year")
                or article.findtext("MedlineCitation/Article/Journal/JournalIssue/PubDate/MedlineDate")
                or "",
            languages=tuple(node.text for node in article.findall(
                "MedlineCitation/Article/Language") if node.text),
            source_xml_sha256=fingerprint,
        )
    return out


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
) -> dict[str, PubmedPublicationRecord]:
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
    return parse_pubmed_publication_types(raw)


def update_publication_types(
    df: pd.DataFrame,
    pubmed_types_by_pmid: dict[str, PubmedPublicationRecord],
    *,
    scoped_indices: set[object] | None = None,
    doi_aliases: dict[str, str] | None = None,
    audit_rows: list[dict] | None = None,
) -> tuple[pd.DataFrame, int]:
    if not df.index.is_unique:
        raise ValueError("Publication-type refresh requires unique row indices to preserve its scope")
    out = df.copy()
    updated = 0
    aliases = {normalize_doi(key).lower(): normalize_doi(value).lower()
               for key, value in (doi_aliases or {}).items()}
    for index, row in out.iterrows():
        if scoped_indices is not None and index not in scoped_indices:
            continue
        pmid = normalize(row.get("pmid", ""))
        if not pmid:
            continue
        source = pubmed_types_by_pmid.get(pmid)
        issue = "native_record_not_returned" if source is None else publication_identity_issue(row, source, aliases)
        if source is not None and not source.publication_type and not issue:
            issue = "missing_native_publication_type"
        current = clean(row.get("publication_type", ""))
        publication_type = source.publication_type if source else ""
        if audit_rows is not None:
            audit_rows.append({
                "doi": clean(row.get("doi")), "pmid": pmid,
                "status": "skipped" if issue else "identity_verified",
                "issue": issue, "previous_publication_type": current,
                "native_publication_type": publication_type,
                "native_title": source.title if source else "",
                "native_dois": list(source.dois) if source else [],
                "native_languages": list(source.languages) if source else [],
                "source_xml_sha256": source.source_xml_sha256 if source else "",
            })
        if issue:
            continue
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
    parser.add_argument("--doi-alias-registry", default=str(DEFAULT_DOI_ALIAS_REGISTRY))
    parser.add_argument("--report-json", default="", help="Source-identity audit report; defaults beside the output table on a real run.")
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
    pubmed_types_by_pmid: dict[str, PubmedPublicationRecord] = {}
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

    # Restrict both metadata writes and candidate materialization to requested,
    # identity-verified rows. A shared cached PMID cannot expand --doi-file.
    selected = scoped.loc[scoped["pmid"].map(normalize).isin(pmids)]
    audit_rows: list[dict] = []
    refreshed, updated = update_publication_types(
        df, pubmed_types_by_pmid, scoped_indices=set(selected.index),
        doi_aliases=load_doi_aliases(Path(args.doi_alias_registry)), audit_rows=audit_rows,
    )
    verified_dois = {row["doi"] for row in audit_rows if row["status"] == "identity_verified"}
    report = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "prepared", "dry_run": bool(args.dry_run), "requested_pmids": len(pmids),
        "native_records_returned": len(pubmed_types_by_pmid),
        "identity_verified_rows": sum(row["status"] == "identity_verified" for row in audit_rows),
        "identity_verified_dois": len(verified_dois),
        "would_update_rows": updated, "metadata_rows_written": 0,
        "skipped_issues": dict(Counter(row["issue"] for row in audit_rows if row["issue"])),
        "rows": audit_rows,
        "note": "Identity checks gate label refresh only; skips do not exclude papers. Language is observed, not overwritten; preserve verified publisher English versions.",
    }
    report_path = None
    if clean(args.report_json) or not args.dry_run:
        report_path = Path(args.report_json).resolve() if clean(args.report_json) else output_table.with_suffix(".pubmed_type_refresh_report.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        # Preserve the gate's evidence even if later candidate materialization fails.
        atomic_write_json(report_path, report)
    candidate_materialization: dict = {}
    if not args.dry_run:
        output_table.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_parquet(output_table, refreshed)
        report["metadata_rows_written"] = updated
        if report_path is not None:
            atomic_write_json(report_path, report)
        if not args.no_update_candidate_table and verified_dois:
            candidate_materialization = materialize_candidate_metadata(
                candidate_table=Path(args.candidate_table).resolve(),
                metadata_table=output_table,
                run_id="pubmed_publication_type_refresh_"
                + dt.datetime.now(dt.timezone.utc).strftime("%Y_%m_%d_%H%M%S"),
                fields=("publication_type", "paper_metadata_schema_version"),
                scoped_dois=verified_dois,
                overwrite_existing=True,
            )

    report["status"] = "dry_run" if args.dry_run else "completed"
    if report_path is not None:
        atomic_write_json(report_path, report)
        print(f"Source identity report: {report_path}")
    print(f"Native PubMed records returned: {len(pubmed_types_by_pmid):,}")
    print(f"Identity-verified rows: {len(verified_dois):,}")
    print(f"Rows {'that would change' if args.dry_run else 'updated'}: {updated:,}")
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
