#!/usr/bin/env python3
"""Backfill provider-asserted funding metadata for screened-in papers.

The stage is intentionally independent of general metadata completeness and
never reads historical KG/LLM funding fields as evidence.  OpenAlex, PubMed,
and Crossref are all queried as complementary sources rather than fallbacks.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
import xml.etree.ElementTree as ET

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.funding_metadata import (  # noqa: E402
    ASSERTION_COLUMNS,
    ATTEMPT_COLUMNS,
    FUNDING_ATTEMPT_SCHEMA_VERSION,
    TERMINAL_ATTEMPT_STATUSES,
    canonical_json,
    crossref_funding_fragment,
    finalize_assertions,
    funding_rows_from_crossref,
    funding_rows_from_openalex,
    funding_rows_from_pubmed,
    openalex_funding_fragment,
    payload_sha256,
    pubmed_funding_fragment,
)
from pipeline.ingest.metadata_utils import (  # noqa: E402
    RateLimitedHttpClient,
    load_config,
    lookup_openalex_work,
    lookup_openalex_work_by_id,
    ncbi_common_params,
    normalize,
    normalize_doi,
    pubmed_article_id,
    read_float,
    read_int,
)


DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_SCREENING_TABLE = (
    ROOT / "data" / "processed" / "corpus" / "paper_domain_routing_gemini.parquet"
)
DEFAULT_SCREENING_OVERRIDES = ROOT / "data" / "curated" / "screening_decision_overrides.json"
DEFAULT_OUTPUT_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_funding.parquet"
DEFAULT_ATTEMPTS_TABLE = (
    ROOT / "data" / "processed" / "corpus" / "paper_funding_provider_attempts.parquet"
)
DEFAULT_RUNS_DIR = ROOT / "data" / "processed" / "corpus" / "funding_enrichment_runs"
DEFAULT_CONFIG = ROOT / "pipeline" / "config.example.yaml"
DEFAULT_PROVIDERS = ("openalex", "pubmed", "crossref")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def default_run_id() -> str:
    return "funding_enrichment_" + dt.datetime.now(dt.timezone.utc).strftime("%Y_%m_%d_%H%M%S")


def clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).lower() in {"1", "true", "yes", "y", "include", "retain"}


def atomic_write_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}.", suffix=".parquet", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        frame.to_parquet(temporary, engine="pyarrow", index=False)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_table(path: Path, columns: tuple[str, ...]) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame(columns=list(columns))
    frame = pd.read_parquet(path)
    for column in columns:
        if column not in frame.columns:
            frame[column] = ""
    return frame.loc[:, list(columns)].copy()


def normalized_doi_series(values: pd.Series) -> pd.Series:
    return values.map(lambda value: normalize_doi(clean(value)).lower())


def load_screening_exclusions(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    excluded: set[str] = set()
    for group in payload.get("overrides", []) if isinstance(payload, dict) else []:
        if not isinstance(group, dict) or clean(group.get("decision", "")) != "exclude_out_of_scope":
            continue
        for value in group.get("dois", []):
            doi = normalize_doi(value).lower()
            if doi:
                excluded.add(doi)
    return excluded


def read_doi_file(path: Path) -> set[str]:
    if not path.is_file():
        raise FileNotFoundError(f"DOI file not found: {path}")
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        first = line.split(",", 1)[0].strip()
        if not first or first.startswith("#") or first.lower() in {"doi", "study_doi"}:
            continue
        doi = normalize_doi(first).lower()
        if doi:
            out.add(doi)
    return out


def build_scope(
    *,
    candidate_table: Path,
    screening_table: Path,
    screening_overrides: Path,
    scope_mode: str,
    doi_file: Path | None = None,
    limit: int = 0,
) -> tuple[pd.DataFrame, dict]:
    candidates = pd.read_parquet(candidate_table)
    if "doi" not in candidates.columns:
        raise ValueError("Candidate table has no DOI column")
    candidates = candidates.copy()
    candidates["doi"] = normalized_doi_series(candidates["doi"])
    candidates = candidates[candidates["doi"].astype(bool)].copy()
    if candidates["doi"].duplicated().any():
        duplicates = candidates.loc[candidates["doi"].duplicated(False), "doi"].unique().tolist()
        raise ValueError(f"Candidate table has duplicate normalized DOIs: {duplicates[:10]}")

    if scope_mode == "screened-in":
        screening = pd.read_parquet(screening_table)
        if not {"doi", "screening_decision"}.issubset(screening.columns):
            raise ValueError("Screening table must contain doi and screening_decision")
        screening_dois = {
            normalize_doi(row["doi"]).lower()
            for row in screening.loc[
                screening["screening_decision"].fillna("").astype(str).str.strip().eq("include_in_scope")
            ].to_dict("records")
            if normalize_doi(row.get("doi", ""))
        }
    elif scope_mode == "retained":
        field = "retained_for_extraction_candidate"
        if field not in candidates.columns:
            raise ValueError(f"Candidate table has no {field} column")
        screening_dois = set(candidates.loc[candidates[field].map(truthy), "doi"])
    else:  # pragma: no cover - argparse prevents this path
        raise ValueError(f"Unsupported scope mode: {scope_mode}")

    exclusions = load_screening_exclusions(screening_overrides)
    selected = screening_dois - exclusions
    file_scope: set[str] | None = None
    if doi_file is not None:
        file_scope = read_doi_file(doi_file)
        selected &= file_scope

    candidate_dois = set(candidates["doi"])
    missing_candidates = sorted(selected - candidate_dois)
    if missing_candidates:
        raise ValueError(
            "Screened funding scope contains DOIs absent from candidate_papers: "
            f"{len(missing_candidates)} ({missing_candidates[:10]})"
        )

    alias_mask = pd.Series(False, index=candidates.index)
    if "doi_alias_of" in candidates.columns:
        alias_mask |= candidates["doi_alias_of"].map(lambda value: bool(normalize_doi(clean(value))))
    if "doi_alias_status" in candidates.columns:
        alias_mask |= candidates["doi_alias_status"].fillna("").astype(str).str.lower().isin(
            {"alias", "duplicate", "duplicate_doi_alias"}
        )
    suppressed_aliases = set(candidates.loc[alias_mask, "doi"]) & selected
    selected -= suppressed_aliases

    keep_columns = [column for column in ("doi", "pmid", "openalex_id") if column in candidates.columns]
    scope = candidates.loc[candidates["doi"].isin(selected), keep_columns].copy()
    for column in ("pmid", "openalex_id"):
        if column not in scope.columns:
            scope[column] = ""
        scope[column] = scope[column].map(clean)
    scope = scope[["doi", "pmid", "openalex_id"]].sort_values("doi", kind="stable")
    if limit > 0:
        scope = scope.head(limit).copy()
    scope = scope.reset_index(drop=True)
    report = {
        "scope_mode": scope_mode,
        "screened_or_retained_dois": len(screening_dois),
        "curated_screening_exclusions": len(screening_dois & exclusions),
        "doi_file_dois": len(file_scope) if file_scope is not None else None,
        "duplicate_aliases_suppressed": len(suppressed_aliases),
        "selected_dois": len(scope),
    }
    return scope, report


def parse_providers(raw: str) -> tuple[str, ...]:
    providers: list[str] = []
    for value in raw.split(","):
        provider = clean(value).lower()
        if not provider:
            continue
        if provider not in DEFAULT_PROVIDERS:
            raise ValueError(f"Unsupported funding provider: {provider}")
        if provider not in providers:
            providers.append(provider)
    if not providers:
        raise ValueError("At least one funding provider is required")
    return tuple(providers)


def load_provider_settings(args: argparse.Namespace) -> tuple[dict[str, RateLimitedHttpClient], dict[str, str]]:
    config = load_config(Path(args.config).resolve())
    openalex = config.get("openalex", {}) if isinstance(config.get("openalex", {}), dict) else {}
    pubmed = config.get("pubmed", {}) if isinstance(config.get("pubmed", {}), dict) else {}
    crossref = config.get("crossref", {}) if isinstance(config.get("crossref", {}), dict) else {}
    max_retries = args.max_retries if args.max_retries is not None else read_int(
        openalex.get("max_retries"), 4
    )
    settings = {
        "openalex_email": clean(args.openalex_email or openalex.get("email", "") or os.getenv("OPENALEX_EMAIL", "")),
        "openalex_api_key": clean(args.openalex_api_key or openalex.get("api_key", "") or os.getenv("OPENALEX_API_KEY", "")),
        "ncbi_email": clean(args.ncbi_email or pubmed.get("email", "") or os.getenv("NCBI_EMAIL", "")),
        "ncbi_api_key": clean(args.ncbi_api_key or pubmed.get("api_key", "") or os.getenv("NCBI_API_KEY", "")),
        "crossref_email": clean(args.crossref_email or crossref.get("email", "") or os.getenv("CROSSREF_EMAIL", "")),
    }
    common = {
        "max_retries": max_retries,
        "timeout_sec": max(1, args.timeout_sec),
        "max_retry_after_sec": max(0, args.max_retry_after_sec),
    }
    clients = {
        "openalex": RateLimitedHttpClient(
            rps=args.openalex_rps
            if args.openalex_rps is not None
            else read_float(openalex.get("rate_limit_per_sec"), 2.0),
            user_agent="kg-pipeline/funding-enrichment-openalex",
            **common,
        ),
        "pubmed": RateLimitedHttpClient(
            rps=args.pubmed_rps
            if args.pubmed_rps is not None
            else read_float(pubmed.get("rate_limit_per_sec"), 2.5),
            user_agent="kg-pipeline/funding-enrichment-pubmed",
            **common,
        ),
        "crossref": RateLimitedHttpClient(
            rps=args.crossref_rps
            if args.crossref_rps is not None
            else read_float(crossref.get("rate_limit_per_sec"), 5.0),
            user_agent="kg-pipeline/funding-enrichment-crossref",
            **common,
        ),
    }
    return clients, settings


def lookup_openalex_funding(
    client: RateLimitedHttpClient,
    *,
    doi: str,
    openalex_id: str,
    email: str,
    api_key: str,
) -> tuple[str, dict, list[dict]] | None:
    work = None
    wanted = normalize_doi(doi).lower()
    if clean(openalex_id):
        hinted = lookup_openalex_work_by_id(client, openalex_id, email, api_key)
        hinted_doi = normalize_doi(hinted.get("doi", "")).lower() if hinted else ""
        if hinted_doi == wanted:
            work = hinted
    if work is None:
        work = lookup_openalex_work(client, doi, email, api_key)
    if work is None:
        return None
    returned_doi = normalize_doi(work.get("doi", "")).lower()
    if returned_doi != wanted:
        raise ValueError(
            f"OpenAlex DOI mismatch: expected {doi}, received {returned_doi or '<blank>'}"
        )
    ids = work.get("ids", {}) if isinstance(work.get("ids", {}), dict) else {}
    record_id = clean(ids.get("openalex", "") or work.get("id", "") or openalex_id)
    fragment = openalex_funding_fragment(work)
    return record_id, fragment, funding_rows_from_openalex(work)


def fetch_pubmed_articles(
    client: RateLimitedHttpClient,
    *,
    ids: list[str],
    email: str,
    api_key: str,
) -> list[ET.Element]:
    if not ids:
        return []
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    raw = client.get_bytes(
        f"{base}/efetch.fcgi?"
        + urlencode(
            {
                **ncbi_common_params(email, api_key),
                "db": "pubmed",
                "id": ",".join(ids),
                "retmode": "xml",
            }
        ),
        headers={},
    )
    return ET.fromstring(raw).findall(".//PubmedArticle")


def lookup_pubmed_funding(
    client: RateLimitedHttpClient,
    *,
    doi: str,
    pmid: str,
    email: str,
    api_key: str,
) -> tuple[str, dict, list[dict]] | None:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    wanted = normalize_doi(doi).lower()

    def doi_search_ids() -> list[str]:
        payload = client.get_json(
            f"{base}/esearch.fcgi",
            params={
                **ncbi_common_params(email, api_key),
                "db": "pubmed",
                "term": f'"{normalize_doi(doi)}"[AID]',
                "retmode": "json",
                "retmax": 5,
            },
            headers={},
        )
        raw_ids = payload.get("esearchresult", {}).get("idlist", []) if isinstance(payload, dict) else []
        return [clean(value) for value in raw_ids if clean(value)]

    ids = [clean(pmid)] if clean(pmid) else doi_search_ids()
    articles = fetch_pubmed_articles(client, ids=ids, email=email, api_key=api_key)
    exact = [
        article
        for article in articles
        if normalize_doi(pubmed_article_id(article, "doi")).lower() == wanted
    ]
    if not exact and clean(pmid):
        # Candidate identifiers are lookup hints, not identity evidence.  If a
        # hinted PMID does not explicitly carry the requested DOI, repeat the
        # lookup by DOI and require an exact provider-record match.
        searched_ids = doi_search_ids()
        articles = fetch_pubmed_articles(
            client, ids=searched_ids, email=email, api_key=api_key
        )
        exact = [
            article
            for article in articles
            if normalize_doi(pubmed_article_id(article, "doi")).lower() == wanted
        ]
    if not exact:
        return None
    article = exact[0]
    record_id = normalize(article.findtext(".//MedlineCitation/PMID")) or clean(pmid)
    fragment = pubmed_funding_fragment(article)
    return record_id, fragment, funding_rows_from_pubmed(article)


def lookup_crossref_funding(
    client: RateLimitedHttpClient,
    *,
    doi: str,
    email: str,
) -> tuple[str, dict, list[dict]] | None:
    try:
        payload = client.get_json(
            f"https://api.crossref.org/works/{quote(normalize_doi(doi), safe='')}",
            params={"mailto": email} if email else {},
            headers={},
        )
    except HTTPError as err:
        if err.code == 404:
            return None
        raise
    item = payload.get("message", {}) if isinstance(payload, dict) else {}
    if not isinstance(item, dict):
        return None
    returned_doi = normalize_doi(item.get("DOI", "")).lower()
    if not returned_doi:
        return None
    # Crossref resolves some publisher-era DOI aliases (notably legacy JAMA
    # identifiers) to a newer canonical DOI.  The requested DOI remains our
    # paper key while ``provider_record_id`` preserves Crossref's returned ID.
    fragment = crossref_funding_fragment(item)
    return returned_doi, fragment, funding_rows_from_crossref(item)


def replace_provider_assertions(
    assertions: pd.DataFrame,
    *,
    doi: str,
    provider: str,
    rows: list[dict],
) -> pd.DataFrame:
    if not assertions.empty:
        keep = ~(
            assertions["doi"].map(lambda value: normalize_doi(clean(value)).lower()).eq(doi)
            & assertions["provider"].fillna("").astype(str).str.lower().eq(provider)
        )
        assertions = assertions.loc[keep].copy()
    if rows:
        assertions = pd.concat(
            [assertions, pd.DataFrame(rows, columns=list(ASSERTION_COLUMNS))], ignore_index=True
        )
    return assertions.loc[:, list(ASSERTION_COLUMNS)]


def append_attempt(attempts: pd.DataFrame, row: dict) -> pd.DataFrame:
    return pd.concat(
        [attempts, pd.DataFrame([row], columns=list(ATTEMPT_COLUMNS))], ignore_index=True
    ).loc[:, list(ATTEMPT_COLUMNS)]


def terminal_provider_pairs(attempts: pd.DataFrame) -> set[tuple[str, str]]:
    if attempts.empty:
        return set()
    return {
        (normalize_doi(row["doi"]).lower(), clean(row["provider"]).lower())
        for row in attempts.to_dict("records")
        if clean(row.get("result_status", "")) in TERMINAL_ATTEMPT_STATUSES
    }


def terminal_provider_pairs_for_run(
    attempts: pd.DataFrame, retrieval_run_id: str
) -> set[tuple[str, str]]:
    if attempts.empty:
        return set()
    current = attempts.loc[
        attempts["retrieval_run_id"].fillna("").astype(str).eq(retrieval_run_id)
    ]
    return terminal_provider_pairs(current)


def sorted_assertions(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=list(ASSERTION_COLUMNS))
    return frame.sort_values(
        ["doi", "provider", "funder_name", "award_id", "assertion_key"], kind="stable"
    ).reset_index(drop=True)


def sorted_attempts(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=list(ATTEMPT_COLUMNS))
    return frame.sort_values(
        ["doi", "provider", "retrieved_at_utc", "retrieval_run_id"], kind="stable"
    ).reset_index(drop=True)


def assertion_records_by_provider_pair(frame: pd.DataFrame) -> dict[tuple[str, str], list[dict]]:
    indexed: dict[tuple[str, str], list[dict]] = {}
    for row in frame.to_dict("records"):
        pair = (
            normalize_doi(row.get("doi", "")).lower(),
            clean(row.get("provider", "")).lower(),
        )
        if pair[0] and pair[1]:
            indexed.setdefault(pair, []).append(row)
    return indexed


def build_fetchers(
    clients: dict[str, RateLimitedHttpClient], settings: dict[str, str]
) -> dict[str, Callable[[dict], tuple[str, dict, list[dict]] | None]]:
    return {
        "openalex": lambda paper: lookup_openalex_funding(
            clients["openalex"],
            doi=paper["doi"],
            openalex_id=paper.get("openalex_id", ""),
            email=settings["openalex_email"],
            api_key=settings["openalex_api_key"],
        ),
        "pubmed": lambda paper: lookup_pubmed_funding(
            clients["pubmed"],
            doi=paper["doi"],
            pmid=paper.get("pmid", ""),
            email=settings["ncbi_email"],
            api_key=settings["ncbi_api_key"],
        ),
        "crossref": lambda paper: lookup_crossref_funding(
            clients["crossref"],
            doi=paper["doi"],
            email=settings["crossref_email"],
        ),
    }


def fetch_funding_observation(
    *,
    provider: str,
    paper: dict,
    fetcher: Callable[[dict], tuple[str, dict, list[dict]] | None],
    run_id: str,
) -> dict:
    doi = paper["doi"]
    retrieved_at = now_utc()
    provider_record_id = ""
    source_fragment: dict = {}
    normalized_rows: list[dict] = []
    error_type = ""
    error_message = ""
    provider_record_found = False
    try:
        result = fetcher(paper)
        if result is None:
            status = "provider_record_not_found"
        else:
            provider_record_found = True
            provider_record_id, source_fragment, normalized_rows = result
            status = "no_funding_metadata"
    except Exception as err:  # provider failures are recorded and resumable
        status = "error"
        error_type = type(err).__name__
        error_message = str(err)
    source_json = canonical_json(source_fragment)
    source_hash = payload_sha256(source_fragment)
    finalized = finalize_assertions(
        normalized_rows,
        doi=doi,
        provider=provider,
        provider_record_id=provider_record_id,
        retrieval_run_id=run_id,
        retrieved_at_utc=retrieved_at,
        source_payload_sha256=source_hash,
    )
    if provider_record_found:
        status = "funding_found" if finalized else "no_funding_metadata"
    attempt = {column: "" for column in ATTEMPT_COLUMNS}
    attempt.update(
        {
            "schema_version": FUNDING_ATTEMPT_SCHEMA_VERSION,
            "doi": doi,
            "provider": provider,
            "provider_record_id": provider_record_id,
            "lookup_identifier": clean(
                paper.get("openalex_id", "")
                if provider == "openalex"
                else paper.get("pmid", "")
                if provider == "pubmed"
                else doi
            )
            or doi,
            "result_status": status,
            "funding_assertion_count": str(len(finalized)),
            "retrieval_run_id": run_id,
            "retrieved_at_utc": retrieved_at,
            "source_payload_sha256": source_hash,
            "source_payload_json": source_json,
            "error_type": error_type,
            "error_message": error_message,
        }
    )
    return {
        "doi": doi,
        "provider": provider,
        "status": status,
        "assertions": finalized,
        "attempt": attempt,
    }


def validate_or_write_run_scope(
    *,
    run_dir: Path,
    scope: pd.DataFrame,
    providers: tuple[str, ...],
    scope_mode: str,
    refresh_existing: bool,
) -> None:
    scope_path = run_dir / "scope.parquet"
    manifest_path = run_dir / "manifest.json"
    settings = {
        "scope_mode": scope_mode,
        "providers": list(providers),
        "refresh_existing": refresh_existing,
    }
    if scope_path.is_file() or manifest_path.is_file():
        if not scope_path.is_file() or not manifest_path.is_file():
            raise ValueError(f"Incomplete funding run checkpoint: {run_dir}")
        previous = pd.read_parquet(scope_path)
        previous_dois = previous.get("doi", pd.Series(dtype=str)).fillna("").astype(str).tolist()
        current_dois = scope["doi"].fillna("").astype(str).tolist()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if previous_dois != current_dois or manifest.get("settings") != settings:
            raise ValueError(
                f"Run ID {run_dir.name} already exists with a different scope or provider configuration"
            )
        return
    run_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_parquet(scope_path, scope)
    atomic_write_text(run_dir / "doi_scope.txt", "".join(f"{doi}\n" for doi in scope["doi"]))
    atomic_write_json(
        manifest_path,
        {
            "schema_version": "funding_enrichment_run_manifest_v1",
            "run_id": run_dir.name,
            "created_at_utc": now_utc(),
            "settings": settings,
            "scope_dois": len(scope),
        },
    )


def run(args: argparse.Namespace) -> dict:
    providers = parse_providers(args.providers)
    candidate_table = Path(args.candidate_table).resolve()
    screening_table = Path(args.screening_table).resolve()
    screening_overrides = Path(args.screening_overrides).resolve()
    doi_file = Path(args.doi_file).resolve() if clean(args.doi_file) else None
    scope, scope_report = build_scope(
        candidate_table=candidate_table,
        screening_table=screening_table,
        screening_overrides=screening_overrides,
        scope_mode=args.scope,
        doi_file=doi_file,
        limit=max(0, args.limit),
    )
    report = {
        "schema_version": "funding_enrichment_report_v1",
        "run_id": args.run_id,
        "started_at_utc": now_utc(),
        "inputs": {
            "candidate_table": str(candidate_table),
            "screening_table": str(screening_table),
            "screening_overrides": str(screening_overrides),
            "doi_file": str(doi_file) if doi_file else "",
        },
        "outputs": {
            "funding_table": str(Path(args.output_table).resolve()),
            "attempts_table": str(Path(args.attempts_table).resolve()),
        },
        "providers": list(providers),
        "scope": scope_report,
        "dry_run": bool(args.dry_run),
    }
    if args.dry_run:
        report["counts"] = {
            "scope_dois": len(scope),
            "provider_lookups_planned": len(scope) * len(providers),
        }
        return report

    run_dir = Path(args.runs_dir).resolve() / args.run_id
    validate_or_write_run_scope(
        run_dir=run_dir,
        scope=scope,
        providers=providers,
        scope_mode=args.scope,
        refresh_existing=bool(args.refresh_existing),
    )
    output_table = Path(args.output_table).resolve()
    attempts_table = Path(args.attempts_table).resolve()
    existing_assertions = read_table(output_table, ASSERTION_COLUMNS)
    existing_attempts = read_table(attempts_table, ATTEMPT_COLUMNS)
    assertions_by_pair = assertion_records_by_provider_pair(existing_assertions)
    attempt_rows = existing_attempts.to_dict("records")
    assertion_count = sum(len(rows) for rows in assertions_by_pair.values())
    completed = terminal_provider_pairs(existing_attempts)
    completed_this_run = terminal_provider_pairs_for_run(existing_attempts, args.run_id)
    clients, settings = load_provider_settings(args)
    fetchers = build_fetchers(clients, settings)
    status_counts: Counter[str] = Counter()
    provider_status_counts: Counter[str] = Counter()
    lookups = 0
    skipped = 0

    def checkpoint() -> None:
        assertion_rows = [
            row for pair_rows in assertions_by_pair.values() for row in pair_rows
        ]
        atomic_write_parquet(
            output_table,
            sorted_assertions(pd.DataFrame(assertion_rows, columns=list(ASSERTION_COLUMNS))),
        )
        atomic_write_parquet(
            attempts_table,
            sorted_attempts(
                pd.DataFrame(attempt_rows, columns=list(ATTEMPT_COLUMNS))
            ),
        )

    paper_records = scope.to_dict("records")
    for provider in providers:
        pending: list[dict] = []
        for paper in paper_records:
            doi = paper["doi"]
            pair = (doi, provider)
            if pair in completed_this_run or (not args.refresh_existing and pair in completed):
                skipped += 1
                continue
            pending.append(paper)

        def fetch_one(paper: dict) -> dict:
            return fetch_funding_observation(
                provider=provider,
                paper=paper,
                fetcher=fetchers[provider],
                run_id=args.run_id,
            )

        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            observations = executor.map(fetch_one, pending)
            for observation in observations:
                doi = observation["doi"]
                pair = (doi, provider)
                status = observation["status"]
                finalized = observation["assertions"]
                attempt = observation["attempt"]
                if status in TERMINAL_ATTEMPT_STATUSES:
                    assertion_count -= len(assertions_by_pair.get(pair, []))
                    assertions_by_pair[pair] = finalized
                    assertion_count += len(finalized)
                    completed.add(pair)
                    completed_this_run.add(pair)
                attempt_rows.append(attempt)
                lookups += 1
                status_counts[status] += 1
                provider_status_counts[f"{provider}:{status}"] += 1
                if args.write_every > 0 and lookups % args.write_every == 0:
                    checkpoint()
                if args.progress_every > 0 and lookups % args.progress_every == 0:
                    print(
                        f"PROGRESS funding lookups={lookups} skipped={skipped} "
                        f"assertions={assertion_count} statuses={dict(status_counts)}",
                        flush=True,
                    )

    checkpoint()
    report.update(
        {
            "completed_at_utc": now_utc(),
            "counts": {
                "scope_dois": len(scope),
                "provider_lookups_completed": lookups,
                "provider_lookups_reused": skipped,
                "current_funding_assertions": assertion_count,
                "attempt_log_rows": len(attempt_rows),
                "by_status_this_run": dict(status_counts),
                "by_provider_and_status_this_run": dict(provider_status_counts),
            },
        }
    )
    atomic_write_json(run_dir / "report.json", report)
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=default_run_id())
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--screening-table", default=str(DEFAULT_SCREENING_TABLE))
    parser.add_argument("--screening-overrides", default=str(DEFAULT_SCREENING_OVERRIDES))
    parser.add_argument("--output-table", default=str(DEFAULT_OUTPUT_TABLE))
    parser.add_argument("--attempts-table", default=str(DEFAULT_ATTEMPTS_TABLE))
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument(
        "--scope",
        choices=("screened-in", "retained"),
        default="screened-in",
        help=(
            "screened-in queries reports included by title/abstract screening; retained uses the "
            "later extraction-eligibility flag from candidate_papers."
        ),
    )
    parser.add_argument("--doi-file", default="", help="Optional DOI file intersecting the selected scope.")
    parser.add_argument("--providers", default=",".join(DEFAULT_PROVIDERS))
    parser.add_argument("--refresh-existing", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--write-every", type=int, default=100)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--timeout-sec", type=int, default=40)
    parser.add_argument("--max-retry-after-sec", type=int, default=120)
    parser.add_argument("--max-retries", type=int, default=None)
    parser.add_argument(
        "--workers",
        type=int,
        default=12,
        help="Concurrent requests; provider rate limiters still enforce the configured request rates.",
    )
    parser.add_argument("--openalex-email", default="")
    parser.add_argument("--openalex-api-key", default="")
    parser.add_argument("--openalex-rps", type=float, default=None)
    parser.add_argument("--ncbi-email", default="")
    parser.add_argument("--ncbi-api-key", default="")
    parser.add_argument("--pubmed-rps", type=float, default=None)
    parser.add_argument("--crossref-email", default="")
    parser.add_argument("--crossref-rps", type=float, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    report = run(args)
    print(json.dumps(report.get("counts", {}), indent=2))
    if args.dry_run:
        print("Dry run only; no provider requests or files were written.")
    else:
        print(f"Funding table: {Path(args.output_table).resolve()}")
        print(f"Provider attempts: {Path(args.attempts_table).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
