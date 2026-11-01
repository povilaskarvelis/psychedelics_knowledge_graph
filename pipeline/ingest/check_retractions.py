#!/usr/bin/env python3
"""Check whether the papers of an evidence run have been retracted.

Each paper is looked up in two registries:

- Crossref, by DOI. A work's ``updated-by`` list holds the notices that
  publishers deposit and the Retraction Watch records that Crossref
  distributes.
- PubMed, by PMID. NLM gives a retracted article the publication type
  "Retracted Publication" and links it to its notice ("Retraction in").

A notice counts only when the registry record is the paper itself. A Crossref
record is found by the paper's DOI and must not carry a different title. A
PubMed record must carry the paper's DOI, or the paper's title when it carries
no DOI. A notice found on a conflicting record is listed for review and changes
nothing.

The current status is written to ``data/curated/retraction_status.json``. The
KG build holds every row of a retracted paper, and the corpus ledger records the
paper as ``retracted``. Expressions of concern, partial retractions,
retract-and-replace notices and publisher withdrawal records are recorded for
review; their papers stay in the graph. Only a check that reached both registries for every paper replaces the
status file, and records for papers outside the checked scope are kept.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError
from urllib.parse import quote, unquote

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.fulltext.source_identity import title_similarity
from pipeline.ingest.materialize_candidate_funding import resolve_registered_doi
from pipeline.ingest.materialize_candidate_metadata import atomic_write_json
from pipeline.ingest.metadata_utils import RateLimitedHttpClient, load_config, normalize, read_float, read_int
from pipeline.ingest.refresh_pubmed_publication_types import chunks, pubmed_common_params
from pipeline.validate.doi_aliases import DEFAULT_DOI_ALIAS_REGISTRY, load_doi_aliases


DEFAULT_STATUS_PATH = ROOT / "data" / "curated" / "retraction_status.json"
DEFAULT_REPORT_ROOT = ROOT / "data" / "processed" / "retraction_checks"
DEFAULT_ROUTED_RUNS_DIR = ROOT / "data" / "processed" / "extraction" / "routed_runs"
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_PAPER_METADATA_OVERRIDES = ROOT / "data" / "curated" / "paper_metadata_overrides.json"
STATUS_SCHEMA_VERSION = "retraction_status_v1"

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
CROSSREF_SELECT = "DOI,title,updated-by,update-to"
PUBMED_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
# The threshold the full-text identity audit uses for front-matter titles.
MINIMUM_TITLE_SIMILARITY = 0.8
RETRY_DELAY_SEC = 5.0

# Crossref update types and PubMed link types, by the paper status they record.
# A publisher's "withdrawal" or "removal" record does not by itself mean that the
# article was retracted: Elsevier withdraws in-press versions, and has registered
# the withdrawal of a duplicate corrigendum against the corrected article. Such a
# record is listed for review; a retraction of the article is also recorded by
# Retraction Watch (as a retraction) or by PubMed.
CROSSREF_UPDATE_STATUSES = {
    "retraction": "retracted",
    "withdrawal": "withdrawn",
    "removal": "withdrawn",
    "partial_retraction": "partially_retracted",
    "expression_of_concern": "expression_of_concern",
    "reinstatement": "reinstated",
}
PUBMED_LINK_STATUSES = {
    "retraction in": "retracted",
    "partial retraction in": "partially_retracted",
    "retraction and replacement in": "retracted_and_replaced",
    "expression of concern in": "expression_of_concern",
}
PUBMED_RETRACTED_TYPE = "retracted publication"
# Types that make the paper itself a retraction notice or expression of concern.
CROSSREF_NOTICE_TYPES = {"retraction", "withdrawal", "removal", "partial_retraction", "expression_of_concern"}
PUBMED_NOTICE_TYPES = {"retraction of publication", "expression of concern"}
# A paper takes the first status that a verified registry record supports. A
# reinstatement is only recorded after a retraction, so it comes first.
STATUS_ORDER = (
    "reinstated",
    "retracted",
    "retracted_and_replaced",
    "partially_retracted",
    "withdrawn",
    "expression_of_concern",
    "notice",
)
VERIFIED_IDENTITIES = {"doi_match", "title_match"}
NOTICE_TITLE_PREFIX_RE = re.compile(r"^\W*(?:retracted|retraction|withdrawn|expression of concern)\b\W*", re.I)


def clean(value: object) -> str:
    text = normalize(value)
    return "" if text.lower() in {"nan", "none", "nat"} else text


def relative_path(path: Path) -> str:
    resolved = path.resolve()
    return str(resolved.relative_to(ROOT)) if resolved.is_relative_to(ROOT) else str(resolved)


def evidence_run_dois(run_dir: Path, aliases: dict[str, str]) -> set[str]:
    """DOIs of every paper with an extraction output in the run (a superset of its graph papers)."""
    path = run_dir / "route_extraction_outputs.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"Missing route extraction outputs: {path}")
    dois: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            result = row.get("result") if isinstance(row.get("result"), dict) else {}
            doi = resolve_registered_doi(row.get("study_doi") or result.get("study_doi"), aliases)
            if doi:
                dois.add(doi)
    return dois


def kg_dois(kg_dir: Path, aliases: dict[str, str]) -> set[str]:
    papers = pd.read_parquet(kg_dir / "papers.parquet", columns=["study_doi"])
    return {doi for doi in (resolve_registered_doi(value, aliases) for value in papers["study_doi"]) if doi}


def paper_identities(
    dois: set[str],
    candidate_table: Path,
    metadata_overrides: Path | None,
    aliases: dict[str, str],
) -> dict[str, dict[str, str]]:
    """PMID and title of each paper from the corpus ledger; curated titles replace provider titles."""
    papers = {doi: {"doi": doi, "pmid": "", "title": ""} for doi in dois}
    ledger = pd.read_parquet(candidate_table, columns=["doi", "pmid", "study_title"])
    for raw_doi, raw_pmid, raw_title in ledger.itertuples(index=False, name=None):
        doi = resolve_registered_doi(raw_doi, aliases)
        paper = papers.get(doi)
        if paper is None:
            continue
        # The ledger row of the canonical DOI wins over rows of its aliases.
        canonical_row = resolve_registered_doi(raw_doi, {}) == doi
        pmid = re.sub(r"\.0$", "", clean(raw_pmid))
        title = clean(raw_title)
        if pmid.isdigit() and (canonical_row or not paper["pmid"]):
            paper["pmid"] = pmid
        if title and (canonical_row or not paper["title"]):
            paper["title"] = title
    if metadata_overrides is not None and metadata_overrides.is_file():
        payload = json.loads(metadata_overrides.read_text(encoding="utf-8"))
        for record in payload.get("records", []):
            doi = resolve_registered_doi(record.get("doi", ""), aliases)
            title = clean((record.get("fields") or {}).get("study_title", ""))
            if doi in papers and title:
                papers[doi]["title"] = title
    return papers


def crossref_filter_doi(doi: object) -> str:
    """The DOI as Crossref matches it: lower case, percent escapes decoded."""
    return unquote(clean(doi)).strip().lower()


def fetch_crossref_works(
    client: RateLimitedHttpClient,
    dois: list[str],
    *,
    email: str,
    batch_size: int,
    progress_every: int = 25,
) -> tuple[dict[str, dict], dict[str, str]]:
    """Return Crossref records by DOI, and the DOIs whose lookup failed.

    DOIs are queried in batches first. A batch query returns only works
    registered under the queried DOI, so every DOI it does not return is looked
    up on its own: Crossref redirects an alias DOI to the work's primary record,
    and answers 404 for a DOI it does not register (for example a DataCite DOI),
    which is not an error.
    """
    keys_by_query: dict[str, list[str]] = defaultdict(list)
    for doi in dois:
        if doi.startswith("10."):
            keys_by_query[crossref_filter_doi(doi)].append(doi)
    records: dict[str, dict] = {}
    errors: dict[str, str] = {}

    # A comma separates Crossref filters, so DOIs containing one are only looked up singly.
    batches = chunks([query for query in sorted(keys_by_query) if "," not in query], max(1, batch_size))
    for index, batch in enumerate(batches, start=1):
        params = {
            "filter": ",".join(f"doi:{query}" for query in batch),
            "rows": len(batch),
            "select": CROSSREF_SELECT,
            "mailto": email or None,
        }
        try:
            items = client.get_json(CROSSREF_WORKS_URL, params=params)["message"]["items"]
        except Exception:
            items = []
        for item in items:
            for key in keys_by_query.get(crossref_filter_doi(item.get("DOI")), []):
                records[key] = item
        if progress_every > 0 and (index % progress_every == 0 or index == len(batches)):
            print(f"PROGRESS: Crossref batches={index:,}/{len(batches):,} records={len(records):,}", flush=True)

    def lookup(query: str) -> None:
        try:
            payload = client.get_json(f"{CROSSREF_WORKS_URL}/{quote(query, safe='')}", params={"mailto": email or None})
        except HTTPError as err:
            if err.code != 404:
                for key in keys_by_query[query]:
                    errors[key] = f"HTTP {err.code}"
            return
        except Exception as err:
            for key in keys_by_query[query]:
                errors[key] = f"{type(err).__name__}: {err}"
            return
        item = payload.get("message") if isinstance(payload, dict) else None
        if isinstance(item, dict):
            for key in keys_by_query[query]:
                records[key] = item

    single = [query for query in sorted(keys_by_query) if not any(key in records for key in keys_by_query[query])]
    print(f"Crossref single lookups: {len(single):,}", flush=True)
    # Crossref's polite pool allows three concurrent requests; the client keeps the rate limit.
    with ThreadPoolExecutor(max_workers=3) as pool:
        for index, _ in enumerate(pool.map(lookup, single), start=1):
            if progress_every > 0 and (index % (progress_every * 20) == 0 or index == len(single)):
                print(f"PROGRESS: Crossref single lookups={index:,}/{len(single):,}", flush=True)
    # The client does not retry a connection reset or timeout during a read, so
    # failed lookups are repeated once before they are reported.
    if errors:
        retry = sorted({crossref_filter_doi(key) for key in errors})
        errors.clear()
        time.sleep(RETRY_DELAY_SEC)
        for query in retry:
            lookup(query)
    return records, errors


def fetch_pubmed_summaries(
    client: RateLimitedHttpClient,
    pmids: list[str],
    *,
    email: str,
    api_key: str,
    batch_size: int,
    progress_every: int = 25,
) -> tuple[dict[str, dict], dict[str, str]]:
    """Return PubMed document summaries by PMID, and the PMIDs whose lookup failed.

    Failed batches are requested once more before their PMIDs are reported.
    """
    records: dict[str, dict] = {}
    errors: dict[str, str] = {}

    def fetch(batch: list[str]) -> None:
        params = {**pubmed_common_params(email, api_key), "db": "pubmed", "retmode": "json", "id": ",".join(batch)}
        try:
            result = client.get_json(PUBMED_ESUMMARY_URL, params=params)["result"]
        except Exception as err:
            for pmid in batch:
                errors[pmid] = f"{type(err).__name__}: {err}"
            return
        for pmid in batch:
            record = result.get(pmid)
            # NLM returns an error entry for a PMID that does not exist.
            if isinstance(record, dict) and not record.get("error"):
                records[pmid] = record

    batches = chunks(sorted(set(pmids)), max(1, batch_size))
    for index, batch in enumerate(batches, start=1):
        fetch(batch)
        if progress_every > 0 and (index % progress_every == 0 or index == len(batches)):
            print(f"PROGRESS: PubMed batches={index:,}/{len(batches):,} records={len(records):,}", flush=True)
    if errors:
        retry = sorted(errors)
        errors.clear()
        time.sleep(RETRY_DELAY_SEC)
        for batch in chunks(retry, max(1, batch_size)):
            fetch(batch)
    return records, errors


def comparable_title(value: object) -> str:
    return NOTICE_TITLE_PREFIX_RE.sub("", clean(value))


def title_agreement(ours: str, theirs: str) -> tuple[bool, float | None]:
    similarity = title_similarity(comparable_title(ours), comparable_title(theirs))
    # A title missing on either side gives no reason to doubt a DOI match.
    return similarity is None or similarity >= MINIMUM_TITLE_SIMILARITY, similarity


def crossref_evidence(paper: dict[str, str], item: dict) -> dict:
    title = clean((item.get("title") or [""])[0])
    agree, similarity = title_agreement(paper["title"], title)
    notices = []
    for update in item.get("updated-by") or []:
        update_type = clean(update.get("type")).lower()
        status = CROSSREF_UPDATE_STATUSES.get(update_type)
        if status:
            notices.append({
                "source": "crossref",
                "provider": clean(update.get("source")),
                "type": update_type,
                "status": status,
                "notice_doi": crossref_filter_doi(update.get("DOI")),
                "date": clean((update.get("updated") or {}).get("date-time"))[:10],
            })
    registered_doi = crossref_filter_doi(item.get("DOI"))
    return {
        "identity": "doi_match" if agree else "title_conflict",
        # Set when Crossref resolved the paper's DOI as an alias of another DOI.
        "registered_doi": registered_doi if registered_doi != crossref_filter_doi(paper["doi"]) else "",
        "title": title,
        "title_similarity": similarity,
        "is_notice": any(
            clean(update.get("type")).lower() in CROSSREF_NOTICE_TYPES for update in item.get("update-to") or []
        ),
        "notices": notices,
    }


def pubmed_evidence(paper: dict[str, str], record: dict, aliases: dict[str, str]) -> dict:
    title = clean(record.get("title"))
    agree, similarity = title_agreement(paper["title"], title)
    record_dois = {
        resolve_registered_doi(item.get("value"), aliases)
        for item in record.get("articleids") or []
        if clean(item.get("idtype")).lower() == "doi"
    } - {""}
    if record_dois:
        identity = "doi_match" if paper["doi"] in record_dois else "doi_conflict"
    elif paper["title"] and title:
        identity = "title_match" if agree else "title_conflict"
    else:
        identity = "unverified"
    publication_types = [clean(value) for value in record.get("pubtype") or []]
    notices = []
    if any(value.lower() == PUBMED_RETRACTED_TYPE for value in publication_types):
        notices.append({"source": "pubmed", "type": "Retracted Publication", "status": "retracted"})
    for link in record.get("references") or []:
        link_type = clean(link.get("reftype"))
        status = PUBMED_LINK_STATUSES.get(link_type.lower())
        if status:
            notices.append({
                "source": "pubmed",
                "type": link_type,
                "status": status,
                "notice_pmid": clean(link.get("pmid")),
                "citation": clean(link.get("refsource")),
            })
    return {
        "identity": identity,
        "pmid": clean(record.get("uid")),
        "title": title,
        "title_similarity": similarity,
        "dois": sorted(record_dois),
        "is_notice": any(value.lower() in PUBMED_NOTICE_TYPES for value in publication_types),
        "notices": notices,
    }


def source_statuses(evidence: dict) -> set[str]:
    """Statuses one registry record supports; a later reinstatement reverses a retraction."""
    notices = evidence["notices"]
    statuses = {notice["status"] for notice in notices}
    retracted_dates = [notice.get("date", "") for notice in notices if notice["status"] == "retracted"]
    reinstated_dates = [notice.get("date", "") for notice in notices if notice["status"] == "reinstated"]
    if reinstated_dates and retracted_dates and max(reinstated_dates) <= max(retracted_dates):
        statuses.discard("reinstated")
    if evidence["is_notice"]:
        statuses.add("notice")
    return statuses


def notice_label(notice: dict) -> str:
    if notice["source"] == "crossref":
        provider = "Retraction Watch" if notice.get("provider") == "retraction-watch" else "the publisher"
        parts = [f"Crossref ({provider}): {notice['type'].replace('_', ' ')}"]
        if notice.get("notice_doi"):
            parts.append(f"notice {notice['notice_doi']}")
        if notice.get("date"):
            parts.append(notice["date"])
        return ", ".join(parts)
    if notice.get("notice_pmid"):
        return f"PubMed: {notice['type']} PMID {notice['notice_pmid']}"
    return f"PubMed: {notice['type']}"


def classify_paper(
    paper: dict[str, str],
    crossref_item: dict | None,
    pubmed_record: dict | None,
    aliases: dict[str, str],
) -> dict | None:
    """Return the paper's retraction record, or None when no registry records a notice."""
    sources: dict[str, dict] = {}
    if crossref_item is not None:
        sources["crossref"] = crossref_evidence(paper, crossref_item)
    if pubmed_record is not None:
        sources["pubmed"] = pubmed_evidence(paper, pubmed_record, aliases)
    verified: set[str] = set()
    conflicting: set[str] = set()
    for evidence in sources.values():
        (verified if evidence["identity"] in VERIFIED_IDENTITIES else conflicting).update(source_statuses(evidence))
    status = next((value for value in STATUS_ORDER if value in verified), "")
    if not status and conflicting:
        status = "identity_conflict"
    if not status:
        return None
    if status == "notice":
        reason = "The paper is itself a retraction notice or an expression of concern."
    else:
        wanted = conflicting if status == "identity_conflict" else {status}
        labels = [
            notice_label(notice)
            for name, evidence in sources.items()
            for notice in evidence["notices"]
            if notice["status"] in wanted
            and (status == "identity_conflict") != (evidence["identity"] in VERIFIED_IDENTITIES)
        ]
        prefix = (
            "A notice was found on a registry record whose identifiers or title do not match the paper"
            if status == "identity_conflict"
            else status.replace("_", " ").capitalize()
        )
        reason = f"{prefix}: " + "; ".join(dict.fromkeys(labels)) + "."
    return {
        "doi": paper["doi"],
        "pmid": paper["pmid"],
        "title": paper["title"],
        "status": status,
        "reason": reason,
        "sources": {
            name: {
                key: value for key, value in evidence.items()
                if value is not None and value != "" and value != [] and not (key == "is_notice" and not value)
            }
            for name, evidence in sources.items()
        },
    }


def merge_status_records(
    previous: list[dict],
    current: list[dict],
    checked_dois: set[str],
    checked_at: str,
) -> list[dict]:
    """Replace the records of checked papers and keep the others unchanged."""
    previous_by_doi = {record["doi"]: record for record in previous}
    merged = {doi: record for doi, record in previous_by_doi.items() if doi not in checked_dois}
    for record in current:
        earlier = previous_by_doi.get(record["doi"])
        first = earlier.get("first_recorded_at_utc", "") if earlier and earlier.get("status") == record["status"] else ""
        merged[record["doi"]] = {**record, "first_recorded_at_utc": first or checked_at}
    return [merged[doi] for doi in sorted(merged)]


def read_status(path: Path) -> dict:
    if not path.is_file():
        return {"schema_version": STATUS_SCHEMA_VERSION, "records": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != STATUS_SCHEMA_VERSION or not isinstance(payload.get("records"), list):
        raise ValueError(f"Unsupported retraction status file: {path}")
    return payload


def lookup_outcome(found: bool, error: str, queried: bool, not_found: str, not_queried: str) -> str:
    if found:
        return "found"
    if error:
        return "error"
    return not_found if queried else not_queried


def check_papers(
    papers: dict[str, dict[str, str]],
    crossref: tuple[dict[str, dict], dict[str, str]],
    pubmed: tuple[dict[str, dict], dict[str, str]],
    aliases: dict[str, str],
) -> tuple[list[dict], list[dict]]:
    """Return the retraction records and one report row per paper."""
    (crossref_records, crossref_errors), (pubmed_records, pubmed_errors) = crossref, pubmed
    records: list[dict] = []
    rows: list[dict] = []
    for doi in sorted(papers):
        paper = papers[doi]
        crossref_item = crossref_records.get(doi)
        pubmed_record = pubmed_records.get(paper["pmid"]) if paper["pmid"] else None
        record = classify_paper(paper, crossref_item, pubmed_record, aliases)
        if record is not None:
            records.append(record)
        rows.append({
            "doi": doi,
            "pmid": paper["pmid"],
            "crossref": lookup_outcome(
                crossref_item is not None, crossref_errors.get(doi, ""), doi.startswith("10."),
                "not_registered", "not_a_doi",
            ),
            "pubmed": lookup_outcome(
                pubmed_record is not None, pubmed_errors.get(paper["pmid"], ""), bool(paper["pmid"]),
                "not_returned", "no_pmid",
            ),
            "status": record["status"] if record else "",
        })
    return records, rows


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check the papers of an evidence run against Crossref and PubMed retraction records.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--evidence-run-id", help="Check every paper with an extraction output in this routed run.")
    scope.add_argument("--kg-dir", help="Check every paper in this KG build.")
    parser.add_argument("--routed-runs-dir", default=str(DEFAULT_ROUTED_RUNS_DIR))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--paper-metadata-overrides", default=str(DEFAULT_PAPER_METADATA_OVERRIDES))
    parser.add_argument("--doi-alias-registry", default=str(DEFAULT_DOI_ALIAS_REGISTRY))
    parser.add_argument("--status-out", default=str(DEFAULT_STATUS_PATH))
    parser.add_argument("--report-root", default=str(DEFAULT_REPORT_ROOT))
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.example.yaml"))
    parser.add_argument("--crossref-batch-size", type=int, default=100)
    parser.add_argument("--pubmed-batch-size", type=int, default=200)
    parser.add_argument("--limit", type=int, default=0, help="Check only the first N papers (testing).")
    parser.add_argument("--dry-run", action="store_true", help="Write the report but not the status file.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    aliases = load_doi_aliases(Path(args.doi_alias_registry))
    if args.evidence_run_id:
        dois = evidence_run_dois(Path(args.routed_runs_dir) / args.evidence_run_id, aliases)
        scope = {"kind": "evidence_run", "id": args.evidence_run_id}
    else:
        dois = kg_dois(Path(args.kg_dir), aliases)
        scope = {"kind": "kg_dir", "id": relative_path(Path(args.kg_dir))}
    if args.limit > 0:
        dois = set(sorted(dois)[: args.limit])
    papers = paper_identities(dois, Path(args.candidate_table), Path(args.paper_metadata_overrides), aliases)
    pmids = sorted({paper["pmid"] for paper in papers.values() if paper["pmid"]})

    config = load_config(Path(args.config).resolve())
    crossref_cfg = config.get("crossref", {}) if isinstance(config.get("crossref"), dict) else {}
    pubmed_cfg = config.get("pubmed", {}) if isinstance(config.get("pubmed"), dict) else {}
    crossref_client = RateLimitedHttpClient(
        rps=read_float(crossref_cfg.get("rate_limit_per_sec"), 5.0),
        max_retries=read_int(crossref_cfg.get("max_retries"), 4),
        user_agent="kg-pipeline/retraction-check",
    )
    pubmed_client = RateLimitedHttpClient(
        rps=read_float(pubmed_cfg.get("rate_limit_per_sec"), 2.5),
        max_retries=read_int(pubmed_cfg.get("max_retries"), 4),
        user_agent="kg-pipeline/retraction-check",
    )
    print(f"START: retraction check {scope['kind']}={scope['id']} papers={len(papers):,} pmids={len(pmids):,}", flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        crossref_future = pool.submit(
            fetch_crossref_works, crossref_client, sorted(papers),
            email=str(crossref_cfg.get("email", "")), batch_size=args.crossref_batch_size,
        )
        pubmed_future = pool.submit(
            fetch_pubmed_summaries, pubmed_client, pmids,
            email=str(pubmed_cfg.get("email", "")), api_key=str(pubmed_cfg.get("api_key", "")),
            batch_size=args.pubmed_batch_size,
        )
        crossref_records, crossref_errors = crossref_future.result()
        pubmed_records, pubmed_errors = pubmed_future.result()
    records, rows = check_papers(
        papers, (crossref_records, crossref_errors), (pubmed_records, pubmed_errors), aliases
    )

    checked_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    report_path = Path(args.report_root) / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") / "retraction_check_report.json"
    last_check = {
        "checked_at_utc": checked_at,
        "scope": scope,
        "papers_checked": len(papers),
        "paper_dois_sha256": hashlib.sha256("\n".join(sorted(papers)).encode("utf-8")).hexdigest(),
        "crossref": {
            "dois_queried": sum(doi.startswith("10.") for doi in papers),
            "records_found": len(crossref_records),
            "lookup_errors": len(crossref_errors),
        },
        "pubmed": {"pmids_queried": len(pmids), "records_found": len(pubmed_records), "lookup_errors": len(pubmed_errors)},
        "status_counts": dict(sorted(Counter(record["status"] for record in records).items())),
        "report": relative_path(report_path),
    }
    atomic_write_json(report_path, {
        **last_check,
        "crossref_errors": crossref_errors,
        "pubmed_errors": pubmed_errors,
        "records": records,
        "rows": rows,
    })
    print(f"Report: {report_path}")
    print(f"Crossref records: {len(crossref_records):,}; PubMed records: {len(pubmed_records):,}")
    print(f"Statuses: {json.dumps(last_check['status_counts'])}")
    for record in records:
        if record["status"] in {"retracted", "identity_conflict"}:
            print(f"  {record['status']}: {record['doi']} | {record['title'][:90]}")
    if crossref_errors or pubmed_errors:
        print(
            f"FAILED: {len(crossref_errors):,} Crossref and {len(pubmed_errors):,} PubMed lookups failed; "
            f"the status file was not changed.",
            file=sys.stderr,
        )
        return 1
    if args.dry_run:
        print("Dry run: the status file was not changed.")
        return 0
    status_path = Path(args.status_out)
    previous = read_status(status_path)
    atomic_write_json(status_path, {
        "schema_version": STATUS_SCHEMA_VERSION,
        "description": (
            "Retraction status of papers checked against Crossref (publisher notices and Retraction Watch) "
            "and PubMed. Written by pipeline/ingest/check_retractions.py; the KG build holds retracted papers."
        ),
        "last_check": last_check,
        "records": merge_status_records(previous["records"], records, set(papers), checked_at),
    })
    print(f"Status file: {status_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
