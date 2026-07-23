#!/usr/bin/env python3
"""Audit ClinicalTrials.gov data sharing and public research artifacts.

The input links already exist in ``candidate_papers.trial_registry_ids``. This
script resolves NCT identifiers in bounded batches and writes standalone audit
tables. It does not modify candidate papers or integrate anything into the KG.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import re
import sys
import time
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.http_safety import (  # noqa: E402
    build_public_http_opener,
    read_bounded_response,
    validate_public_http_url,
)
from pipeline.ingest.metadata_utils import normalize_doi  # noqa: E402


DEFAULT_CANDIDATES = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_OUTPUT_DIR = (
    ROOT / "data" / "processed" / "corpus" / "trial_data_sharing_census_20260723"
)
API_URL = "https://clinicaltrials.gov/api/v2/studies"
USER_AGENT = "psychedelics-knowledge-graph-trial-sharing-audit/0.1"
NCT_RE = re.compile(r"\bNCT\d{8}\b", re.IGNORECASE)
FIELDS = ",".join(
    (
        "NCTId",
        "NCTIdAlias",
        "BriefTitle",
        "OverallStatus",
        "StudyType",
        "Phase",
        "EnrollmentCount",
        "EnrollmentType",
        "LeadSponsorName",
        "HasResults",
        "IPDSharing",
        "IPDSharingDescription",
        "IPDSharingInfoType",
        "IPDSharingTimeFrame",
        "IPDSharingAccessCriteria",
        "IPDSharingURL",
        "AvailIPDId",
        "AvailIPDType",
        "AvailIPDURL",
        "AvailIPDComment",
        "LargeDocHasProtocol",
        "LargeDocHasSAP",
        "LargeDocHasICF",
        "LargeDocLabel",
        "LargeDocDate",
        "LargeDocUploadDate",
        "LargeDocFilename",
        "LargeDocSize",
        "StartDate",
        "PrimaryCompletionDate",
        "CompletionDate",
        "StudyFirstPostDate",
        "LastUpdatePostDate",
    )
)
MAX_RESPONSE_BYTES = 64 * 1024 * 1024


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def normalize_doi_value(value: object) -> str:
    return normalize_doi(clean(value)).lower()


def percent(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 2) if denominator else 0.0


def chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def date_value(module: dict[str, Any], field: str) -> str:
    return clean((module.get(field) or {}).get("date"))


def pipe(values: Iterable[object]) -> str:
    return " | ".join(sorted({clean(value) for value in values if clean(value)}))


def extract_paper_trial_links(candidates: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for doi, registry_ids in candidates[["doi", "trial_registry_ids"]].itertuples(
        index=False, name=None
    ):
        paper_doi = normalize_doi_value(doi)
        for nct_id in sorted(set(NCT_RE.findall(clean(registry_ids).upper()))):
            rows.append(
                {
                    "paper_doi": paper_doi,
                    "nct_id": nct_id,
                    "source_column": "candidate_papers.trial_registry_ids",
                    "link_confidence": "provider_metadata_candidate",
                }
            )
    return pd.DataFrame(rows).drop_duplicates(["paper_doi", "nct_id"]).reset_index(drop=True)


def fetch_batch(
    opener,
    nct_ids: list[str],
    *,
    retrieved_at_utc: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    params = [
        ("filter.ids", "|".join(nct_ids)),
        ("pageSize", str(max(1, len(nct_ids)))),
        ("format", "json"),
        ("fields", FIELDS),
    ]
    request_url = f"{API_URL}?{urlencode(params)}"
    validate_public_http_url(request_url)
    started = time.monotonic()
    error = ""
    status = 0
    payload: dict[str, Any] = {}
    for attempt in range(1, 5):
        request = Request(
            request_url,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with opener.open(request, timeout=60) as response:
                status = int(getattr(response, "status", 200))
                body = read_bounded_response(response, MAX_RESPONSE_BYTES)
            payload = json.loads(body.decode("utf-8"))
            error = ""
            break
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            status = int(exc.code) if isinstance(exc, HTTPError) else 0
            error = f"{type(exc).__name__}: {exc}"
            if status and status not in {429, 500, 502, 503, 504}:
                break
            time.sleep(min(8.0, 0.75 * (2 ** (attempt - 1))))
    log = {
        "provider": "clinicaltrials_gov",
        "endpoint": API_URL,
        "requested_ids": len(nct_ids),
        "returned_studies": len(payload.get("studies") or []),
        "http_status": status,
        "result": "ok" if payload and not error else "error",
        "error": error,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "retrieved_at_utc": retrieved_at_utc,
    }
    if error:
        raise RuntimeError(error)
    return payload, log


def sharing_category(
    *,
    ipd_sharing: str,
    available_ipds: list[dict[str, Any]],
) -> str:
    if any(clean(item.get("url")) or clean(item.get("id")) for item in available_ipds):
        return "available_ipd_resource_listed"
    value = ipd_sharing.upper()
    if value == "YES":
        return "plans_to_share_ipd"
    if value == "NO":
        return "does_not_plan_to_share_ipd"
    if value == "UNDECIDED":
        return "ipd_sharing_undecided"
    return "no_ipd_sharing_statement"


def normalize_study(
    study: dict[str, Any],
    *,
    paper_links: dict[str, set[str]],
    retrieved_at_utc: str,
) -> dict[str, Any]:
    protocol = study.get("protocolSection") or {}
    identification = protocol.get("identificationModule") or {}
    status = protocol.get("statusModule") or {}
    design = protocol.get("designModule") or {}
    sponsor = protocol.get("sponsorCollaboratorsModule") or {}
    references = protocol.get("referencesModule") or {}
    ipd = protocol.get("ipdSharingStatementModule") or {}
    document = study.get("documentSection") or {}
    large_document = document.get("largeDocumentModule") or {}
    large_docs = large_document.get("largeDocs") or []
    available_ipds = references.get("availIpds") or []
    nct_id = clean(identification.get("nctId")).upper()
    nct_id_aliases = {
        clean(value).upper()
        for value in identification.get("nctIdAliases") or []
        if clean(value)
    }
    source_nct_ids = ({nct_id} | nct_id_aliases) & set(paper_links)
    linked_papers = set().union(
        *(paper_links.get(value, set()) for value in source_nct_ids)
    )
    phases = design.get("phases") or []
    enrollment = design.get("enrollmentInfo") or {}
    lead_sponsor = sponsor.get("leadSponsor") or {}
    ipd_sharing = clean(ipd.get("ipdSharing")).upper()
    doc_filenames = [clean(item.get("filename")) for item in large_docs]
    return {
        "nct_id": nct_id,
        "nct_id_aliases": pipe(nct_id_aliases),
        "source_nct_ids": pipe(source_nct_ids),
        "clinicaltrials_url": f"https://clinicaltrials.gov/study/{nct_id}",
        "brief_title": clean(identification.get("briefTitle")),
        "overall_status": clean(status.get("overallStatus")),
        "study_type": clean(design.get("studyType")),
        "phases": pipe(phases),
        "enrollment_count": enrollment.get("count"),
        "enrollment_type": clean(enrollment.get("type")),
        "lead_sponsor_name": clean(lead_sponsor.get("name")),
        "lead_sponsor_class": clean(lead_sponsor.get("class")),
        "has_results": bool(study.get("hasResults")),
        "ipd_sharing": ipd_sharing,
        "ipd_sharing_category": sharing_category(
            ipd_sharing=ipd_sharing,
            available_ipds=available_ipds,
        ),
        "ipd_sharing_description": clean(ipd.get("description")),
        "ipd_sharing_info_types": pipe(ipd.get("infoTypes") or []),
        "ipd_sharing_time_frame": clean(ipd.get("timeFrame")),
        "ipd_sharing_access_criteria": clean(ipd.get("accessCriteria")),
        "ipd_sharing_url": clean(ipd.get("url")),
        "available_ipd_count": len(available_ipds),
        "available_ipd_ids": pipe(item.get("id") for item in available_ipds),
        "available_ipd_types": pipe(item.get("type") for item in available_ipds),
        "available_ipd_urls": pipe(item.get("url") for item in available_ipds),
        "available_ipd_comments": pipe(item.get("comment") for item in available_ipds),
        "large_document_count": len(large_docs),
        "has_protocol_document": any(bool(item.get("hasProtocol")) for item in large_docs),
        "has_sap_document": any(bool(item.get("hasSap")) for item in large_docs),
        "has_icf_document": any(bool(item.get("hasIcf")) for item in large_docs),
        "large_document_labels": pipe(item.get("label") for item in large_docs),
        "large_document_filenames": pipe(doc_filenames),
        "start_date": date_value(status, "startDateStruct"),
        "primary_completion_date": date_value(status, "primaryCompletionDateStruct"),
        "completion_date": date_value(status, "completionDateStruct"),
        "study_first_post_date": date_value(status, "studyFirstPostDateStruct"),
        "last_update_post_date": date_value(status, "lastUpdatePostDateStruct"),
        "linked_paper_count": len(linked_papers),
        "linked_paper_dois": pipe(linked_papers),
        "provider": "clinicaltrials_gov",
        "retrieved_at_utc": retrieved_at_utc,
    }


def report(
    *,
    links: pd.DataFrame,
    trials: pd.DataFrame,
    requested_ids: set[str],
    request_log: pd.DataFrame,
    run_started_at_utc: str,
) -> dict[str, Any]:
    returned_ids = set(trials["nct_id"]) if not trials.empty else set()
    returned_aliases: set[str] = set()
    if not trials.empty and "nct_id_aliases" in trials.columns:
        for value in trials["nct_id_aliases"]:
            returned_aliases.update(item for item in clean(value).split(" | ") if item)
    resolved_requested_ids = requested_ids & (returned_ids | returned_aliases)
    missing_ids = requested_ids - resolved_requested_ids
    unexpected_canonical_ids = returned_ids - requested_ids
    canonical_ids_returned_via_alias: list[str] = []
    if not trials.empty and unexpected_canonical_ids:
        for nct_id, aliases in trials.loc[
            trials["nct_id"].isin(unexpected_canonical_ids),
            ["nct_id", "nct_id_aliases"],
        ].itertuples(index=False, name=None):
            alias_set = {item for item in clean(aliases).split(" | ") if item}
            if alias_set & requested_ids:
                canonical_ids_returned_via_alias.append(nct_id)
    sharing_counts = Counter(trials["ipd_sharing"].replace("", "MISSING"))
    category_counts = Counter(trials["ipd_sharing_category"])

    def boolean_count(column: str) -> int:
        return int(trials[column].fillna(False).astype(bool).sum())

    denominator = len(trials)
    return {
        "audit": "clinicaltrials_data_sharing_census",
        "schema_version": "clinicaltrials_data_sharing_v0.1",
        "run_started_at_utc": run_started_at_utc,
        "run_completed_at_utc": now_utc(),
        "scope": {
            "paper_trial_link_rows": len(links),
            "papers_with_nct_link": int(links["paper_doi"].nunique()),
            "unique_nct_ids_requested": len(requested_ids),
            "registry_records_returned": denominator,
            "requested_ids_resolved": len(resolved_requested_ids),
            "registry_record_retrieval_percent": percent(
                len(resolved_requested_ids), len(requested_ids)
            ),
            "missing_nct_ids": sorted(missing_ids),
            "canonical_ids_returned_via_requested_alias": sorted(
                canonical_ids_returned_via_alias
            ),
        },
        "public_aggregate_results": {
            "studies_with_results_posted": boolean_count("has_results"),
            "percent": percent(boolean_count("has_results"), denominator),
        },
        "individual_participant_data": {
            "ipd_sharing_values": dict(sorted(sharing_counts.items())),
            "sharing_categories": dict(sorted(category_counts.items())),
            "studies_with_ipd_sharing_url": int(trials["ipd_sharing_url"].map(bool).sum()),
            "studies_with_available_ipd_resource": int(
                trials["available_ipd_count"].fillna(0).gt(0).sum()
            ),
            "studies_with_available_ipd_url": int(
                trials["available_ipd_urls"].map(bool).sum()
            ),
        },
        "public_documents": {
            "studies_with_any_uploaded_document": int(
                trials["large_document_count"].fillna(0).gt(0).sum()
            ),
            "studies_with_protocol_document": boolean_count("has_protocol_document"),
            "studies_with_statistical_analysis_plan": boolean_count("has_sap_document"),
            "studies_with_informed_consent_form": boolean_count("has_icf_document"),
        },
        "metadata_completeness": {
            "studies_with_lead_sponsor": int(trials["lead_sponsor_name"].map(bool).sum()),
            "studies_with_phase": int(trials["phases"].map(bool).sum()),
            "studies_with_enrollment": int(trials["enrollment_count"].notna().sum()),
            "studies_with_completion_date": int(trials["completion_date"].map(bool).sum()),
        },
        "network": {
            "request_count": len(request_log),
            "successful_requests": int(request_log["result"].eq("ok").sum()),
            "failed_requests": int(request_log["result"].eq("error").sum()),
            "requested_ids_sum": int(request_log["requested_ids"].sum()),
            "returned_studies_sum": int(request_log["returned_studies"].sum()),
        },
        "count_reconciliation": {
            "resolved_requested_plus_missing": len(resolved_requested_ids)
            + len(missing_ids),
            "requested_ids": len(requested_ids),
            "request_log_requested_ids_sum": int(request_log["requested_ids"].sum()),
        },
        "interpretation_guards": [
            "Has results means structured aggregate results are public in the registry; "
            "it does not mean participant-level data are downloadable.",
            "IPDSharing=YES records an intention or policy. Access may be delayed, "
            "proposal-reviewed, controlled, or unavailable until specified milestones.",
            "Available IPD links and uploaded protocols/SAPs/consent forms are distinct "
            "resource types and should receive distinct graph relations.",
            "A paper-to-NCT link inherited from provider metadata can represent a cited "
            "trial rather than the focal study and should be identity-validated before "
            "promotion into the graph.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--request-cap", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_started_at_utc = now_utc()
    candidates = pd.read_parquet(
        args.candidates,
        columns=(
            "doi",
            "retained_for_extraction_candidate",
            "trial_registry_ids",
        ),
    )
    candidates = candidates.loc[
        candidates["retained_for_extraction_candidate"].fillna(False).astype(bool)
    ].copy()
    links = extract_paper_trial_links(candidates)
    requested_ids = set(links["nct_id"])
    batch_count = (len(requested_ids) + args.batch_size - 1) // args.batch_size
    if batch_count > args.request_cap:
        raise ValueError(
            f"Configured batch size requires {batch_count} requests; cap is {args.request_cap}"
        )
    paper_links: dict[str, set[str]] = {}
    for nct_id, group in links.groupby("nct_id"):
        paper_links[nct_id] = set(group["paper_doi"])

    opener = build_public_http_opener()
    retrieved_at_utc = now_utc()
    normalized_rows: list[dict[str, Any]] = []
    logs: list[dict[str, Any]] = []
    for index, batch in enumerate(chunks(sorted(requested_ids), args.batch_size), start=1):
        payload, log = fetch_batch(
            opener,
            batch,
            retrieved_at_utc=retrieved_at_utc,
        )
        logs.append(log)
        for study in payload.get("studies") or []:
            normalized_rows.append(
                normalize_study(
                    study,
                    paper_links=paper_links,
                    retrieved_at_utc=retrieved_at_utc,
                )
            )
        print(
            f"ClinicalTrials.gov batch {index}/{batch_count}: "
            f"{len(batch)} requested, {log['returned_studies']} returned",
            flush=True,
        )
        time.sleep(0.15)

    trials = pd.DataFrame(normalized_rows).sort_values("nct_id").reset_index(drop=True)
    request_log = pd.DataFrame(logs)
    audit_report = report(
        links=links,
        trials=trials,
        requested_ids=requested_ids,
        request_log=request_log,
        run_started_at_utc=run_started_at_utc,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    links.to_parquet(args.output_dir / "paper_trial_links.parquet", index=False)
    trials.to_parquet(args.output_dir / "trial_registry_metadata.parquet", index=False)
    request_log.to_parquet(args.output_dir / "request_log.parquet", index=False)
    (args.output_dir / "report.json").write_text(
        json.dumps(audit_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(audit_report, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
