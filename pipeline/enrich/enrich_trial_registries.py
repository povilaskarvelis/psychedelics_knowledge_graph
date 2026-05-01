#!/usr/bin/env python3
"""Enrich screened disorder papers with clinical trial registry metadata."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

try:
    from pipeline.ingest.sync_paper_library import (
        PAPER_METADATA_FIELDS,
        RateLimitedHttpClient,
        extract_trial_registry_ids,
        normalize,
        normalize_doi,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.ingest.sync_paper_library import (
        PAPER_METADATA_FIELDS,
        RateLimitedHttpClient,
        extract_trial_registry_ids,
        normalize,
        normalize_doi,
    )

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "trial_registry_enrichment_v1"
DEFAULT_DATASET = "disorder"

PRIMARY_SOURCE_TYPES = {"primary_study"}
PRIMARY_SOURCE_FAMILIES = {"original_empirical"}
PRIMARY_PAPER_TYPES = {"primary_results", "case_report"}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json(path: Path) -> object:
    if not path.exists():
        return [] if path.suffix == ".json" else {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_json_array(path: Path) -> List[dict]:
    data = load_json(path)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        rows = data.get("rows", [])
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: List[dict]) -> None:
    fieldnames = sorted({key for row in rows for key in row}) if rows else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def join_unique(values: Iterable[object]) -> str:
    out: List[str] = []
    for value in values:
        text = normalize(value)
        if text and text not in out:
            out.append(text)
    return " | ".join(out)


def split_multi_value(value: object) -> List[str]:
    if isinstance(value, list):
        raw_values = value
    else:
        text = normalize(value)
        if not text:
            return []
        raw_values = text.split(" | ") if " | " in text else text.split("|")
    out: List[str] = []
    for item in raw_values:
        text = normalize(item)
        if text and text not in out:
            out.append(text)
    return out


def registry_kind(identifier: str) -> str:
    text = normalize(identifier).upper()
    if text.startswith("NCT") and len(text) == 11 and text[3:].isdigit():
        return "clinicaltrials_gov"
    if text.startswith("ISRCTN"):
        return "isrctn"
    if text.startswith("ACTRN"):
        return "anzctr"
    if text.startswith("DRKS"):
        return "drks"
    if text.startswith("IRCT"):
        return "irct"
    if text.startswith("RBR-"):
        return "rebec"
    if len(text) == 14 and text[4] == "-" and text[11] == "-":
        return "eudract"
    return "unknown"


def registry_ids_from_row(row: dict) -> List[str]:
    registry_text = normalize(row.get("trial_registry_ids", ""))
    ids = split_multi_value(registry_text)
    scanned = extract_trial_registry_ids(
        registry_text,
        row.get("study_title", ""),
        row.get("abstract", ""),
    )
    for identifier in split_multi_value(scanned):
        if identifier not in ids:
            ids.append(identifier)
    return ids


def parse_doi_queue(path: Path, relevance: str) -> List[dict]:
    if not path.exists():
        return []
    rows: List[dict] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for parts in csv.reader(handle):
            if not parts:
                continue
            first = normalize(parts[0])
            if not first or first.startswith("#"):
                continue
            parts = [normalize(part) for part in parts]
            row = {
                "study_doi": normalize_doi(parts[0] if len(parts) > 0 else ""),
                "compound": parts[1] if len(parts) > 1 else "",
                "disorder": parts[2] if len(parts) > 2 else "",
                "study_title": parts[3] if len(parts) > 3 else "",
                "study_year": parts[4] if len(parts) > 4 else "",
                "authors": parts[5] if len(parts) > 5 else "",
                "screening_relevance": relevance,
                "candidate_source": f"{relevance}_queue",
            }
            for field_idx, field in enumerate(PAPER_METADATA_FIELDS):
                row[field] = parts[6 + field_idx] if len(parts) > 6 + field_idx else ""
            rows.append(row)
    return rows


def rows_from_screening_report(path: Path, include_relevance: set[str]) -> List[dict]:
    if not path.exists():
        return []
    data = load_json(path)
    rows = data.get("rows", []) if isinstance(data, dict) else []
    out: List[dict] = []
    for result in rows if isinstance(rows, list) else []:
        if not isinstance(result, dict):
            continue
        input_row = result.get("input_row", {}) if isinstance(result.get("input_row", {}), dict) else {}
        adjudication = result.get("adjudication", {}) if isinstance(result.get("adjudication", {}), dict) else {}
        flat = result.get("flat", {}) if isinstance(result.get("flat", {}), dict) else {}
        relevance = normalize(adjudication.get("relevance", "")) or normalize(flat.get("llm_relevance", ""))
        if relevance not in include_relevance:
            continue
        row = dict(input_row)
        row["study_doi"] = normalize_doi(row.get("study_doi", ""))
        row["screening_relevance"] = relevance
        row["candidate_source"] = "screening_report"
        row["screening_path"] = normalize(flat.get("screening_path", ""))
        out.append(row)
    return out


def merge_candidate_rows(rows: Iterable[dict], paper_by_doi: Dict[str, dict]) -> List[dict]:
    merged: Dict[str, dict] = {}
    for row in rows:
        doi = normalize_doi(row.get("study_doi", ""))
        if not doi:
            continue
        key = doi.lower()
        paper = paper_by_doi.get(key, {})
        current = merged.setdefault(
            key,
            {
                "study_doi": doi,
                "study_title": "",
                "study_year": "",
                "authors": "",
                "compounds": [],
                "disorders": [],
                "screening_relevance_values": [],
                "candidate_sources": [],
            },
        )
        for field in ("study_title", "study_year", "authors", "abstract"):
            if not normalize(current.get(field, "")):
                current[field] = normalize(row.get(field, "")) or normalize(paper.get(field, ""))
        for field in PAPER_METADATA_FIELDS:
            if not normalize(current.get(field, "")):
                current[field] = normalize(row.get(field, "")) or normalize(paper.get(field, ""))
        for field, source in (
            ("compounds", row.get("compound", "")),
            ("disorders", row.get("disorder", "") or row.get("entity", "")),
            ("screening_relevance_values", row.get("screening_relevance", "")),
            ("candidate_sources", row.get("candidate_source", "")),
        ):
            value = normalize(source)
            if value and value not in current[field]:
                current[field].append(value)
    out = []
    for row in merged.values():
        registry_ids = registry_ids_from_row(row)
        if not registry_ids:
            continue
        row["registry_ids"] = registry_ids
        row["compounds"] = " | ".join(row["compounds"])
        row["disorders"] = " | ".join(row["disorders"])
        row["screening_relevance_values"] = " | ".join(row["screening_relevance_values"])
        row["candidate_sources"] = " | ".join(row["candidate_sources"])
        out.append(row)
    return sorted(out, key=lambda item: normalize(item.get("study_doi", "")))


def primary_source_dois(*row_sets: List[dict]) -> set[str]:
    out: set[str] = set()
    for rows in row_sets:
        for row in rows:
            doi = normalize_doi(row.get("study_doi", "")).lower()
            if not doi:
                continue
            source_type = normalize(row.get("source_type", ""))
            source_family = normalize(row.get("source_family", ""))
            paper_type = normalize(row.get("paper_type", ""))
            if source_family in PRIMARY_SOURCE_FAMILIES:
                out.add(doi)
            elif source_type in PRIMARY_SOURCE_TYPES and paper_type in PRIMARY_PAPER_TYPES:
                out.add(doi)
    return out


def group_candidates_by_registry(candidates: List[dict]) -> Dict[str, dict]:
    grouped: Dict[str, dict] = {}
    for candidate in candidates:
        for registry_id in candidate.get("registry_ids", []):
            key = normalize(registry_id).upper()
            entry = grouped.setdefault(
                key,
                {
                    "registry_id": key,
                    "registry_kind": registry_kind(key),
                    "candidate_dois": [],
                    "study_titles": [],
                    "compounds": [],
                    "disorders": [],
                    "screening_relevance_values": [],
                    "candidate_sources": [],
                },
            )
            for field, value in (
                ("candidate_dois", candidate.get("study_doi", "")),
                ("study_titles", candidate.get("study_title", "")),
                ("compounds", candidate.get("compounds", "")),
                ("disorders", candidate.get("disorders", "")),
                ("screening_relevance_values", candidate.get("screening_relevance_values", "")),
                ("candidate_sources", candidate.get("candidate_sources", "")),
            ):
                for item in split_multi_value(value):
                    if item and item not in entry[field]:
                        entry[field].append(item)
    return grouped


def get_nested(payload: dict, *keys: str) -> object:
    current: object = payload
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key, "")
    return current


def date_struct_value(value: object) -> str:
    if isinstance(value, dict):
        return normalize(value.get("date", ""))
    return ""


def outcome_values(outcomes: object) -> str:
    values: List[str] = []
    for outcome in outcomes if isinstance(outcomes, list) else []:
        if not isinstance(outcome, dict):
            continue
        measure = normalize(outcome.get("measure", ""))
        time_frame = normalize(outcome.get("timeFrame", ""))
        value = f"{measure} ({time_frame})" if measure and time_frame else measure
        if value and value not in values:
            values.append(value)
    return " | ".join(values)


def intervention_values(interventions: object) -> str:
    values: List[str] = []
    for intervention in interventions if isinstance(interventions, list) else []:
        if not isinstance(intervention, dict):
            continue
        name = normalize(intervention.get("name", ""))
        kind = normalize(intervention.get("type", ""))
        value = f"{kind}: {name}" if kind and name else name
        if value and value not in values:
            values.append(value)
    return " | ".join(values)


def sponsor_values(collaborators: object) -> str:
    values: List[str] = []
    for sponsor in collaborators if isinstance(collaborators, list) else []:
        if not isinstance(sponsor, dict):
            continue
        name = normalize(sponsor.get("name", ""))
        if name and name not in values:
            values.append(name)
    return " | ".join(values)


def normalize_clinicaltrials_study(payload: dict) -> dict:
    protocol = payload.get("protocolSection", {}) if isinstance(payload.get("protocolSection", {}), dict) else {}
    results = payload.get("resultsSection", {}) if isinstance(payload.get("resultsSection", {}), dict) else {}
    identification = protocol.get("identificationModule", {}) if isinstance(protocol.get("identificationModule", {}), dict) else {}
    status = protocol.get("statusModule", {}) if isinstance(protocol.get("statusModule", {}), dict) else {}
    design = protocol.get("designModule", {}) if isinstance(protocol.get("designModule", {}), dict) else {}
    design_info = design.get("designInfo", {}) if isinstance(design.get("designInfo", {}), dict) else {}
    enrollment = design.get("enrollmentInfo", {}) if isinstance(design.get("enrollmentInfo", {}), dict) else {}
    conditions = protocol.get("conditionsModule", {}) if isinstance(protocol.get("conditionsModule", {}), dict) else {}
    arms = protocol.get("armsInterventionsModule", {}) if isinstance(protocol.get("armsInterventionsModule", {}), dict) else {}
    outcomes = protocol.get("outcomesModule", {}) if isinstance(protocol.get("outcomesModule", {}), dict) else {}
    sponsors = protocol.get("sponsorCollaboratorsModule", {}) if isinstance(protocol.get("sponsorCollaboratorsModule", {}), dict) else {}
    eligibility = protocol.get("eligibilityModule", {}) if isinstance(protocol.get("eligibilityModule", {}), dict) else {}

    lead_sponsor = sponsors.get("leadSponsor", {}) if isinstance(sponsors.get("leadSponsor", {}), dict) else {}
    secondary_ids = []
    for entry in identification.get("secondaryIdInfos", []) if isinstance(identification.get("secondaryIdInfos", []), list) else []:
        if not isinstance(entry, dict):
            continue
        identifier = normalize(entry.get("id", ""))
        if identifier and identifier not in secondary_ids:
            secondary_ids.append(identifier)

    nct_id = normalize(identification.get("nctId", ""))
    return {
        "registry": "ClinicalTrials.gov",
        "registry_id": nct_id,
        "url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "",
        "brief_title": normalize(identification.get("briefTitle", "")),
        "official_title": normalize(identification.get("officialTitle", "")),
        "secondary_ids": " | ".join(secondary_ids),
        "overall_status": normalize(status.get("overallStatus", "")),
        "study_type": normalize(design.get("studyType", "")),
        "phases": join_unique(design.get("phases", []) if isinstance(design.get("phases", []), list) else []),
        "enrollment_count": normalize(enrollment.get("count", "")),
        "enrollment_type": normalize(enrollment.get("type", "")),
        "allocation": normalize(design_info.get("allocation", "")),
        "intervention_model": normalize(design_info.get("interventionModel", "")),
        "primary_purpose": normalize(design_info.get("primaryPurpose", "")),
        "masking": normalize(get_nested(design_info, "maskingInfo", "masking")),
        "start_date": date_struct_value(status.get("startDateStruct", {})),
        "primary_completion_date": date_struct_value(status.get("primaryCompletionDateStruct", {})),
        "completion_date": date_struct_value(status.get("completionDateStruct", {})),
        "study_first_submit_date": normalize(status.get("studyFirstSubmitDate", "")),
        "last_update_post_date": date_struct_value(status.get("lastUpdatePostDateStruct", {})),
        "conditions": join_unique(conditions.get("conditions", []) if isinstance(conditions.get("conditions", []), list) else []),
        "interventions": intervention_values(arms.get("interventions", [])),
        "arm_groups": join_unique(
            arm.get("label", "")
            for arm in arms.get("armGroups", []) if isinstance(arm, dict)
        ),
        "primary_outcomes": outcome_values(outcomes.get("primaryOutcomes", [])),
        "secondary_outcomes": outcome_values(outcomes.get("secondaryOutcomes", [])),
        "lead_sponsor": normalize(lead_sponsor.get("name", "")),
        "lead_sponsor_class": normalize(lead_sponsor.get("class", "")),
        "collaborators": sponsor_values(sponsors.get("collaborators", [])),
        "minimum_age": normalize(eligibility.get("minimumAge", "")),
        "maximum_age": normalize(eligibility.get("maximumAge", "")),
        "sex": normalize(eligibility.get("sex", "")),
        "healthy_volunteers": normalize(eligibility.get("healthyVolunteers", "")),
        "has_results": "true" if bool(results) else "false",
    }


def lookup_clinicaltrials_study(client: RateLimitedHttpClient, nct_id: str) -> Optional[dict]:
    payload = client.get_json(
        f"https://clinicaltrials.gov/api/v2/studies/{quote(nct_id, safe='')}",
        params={},
        headers={},
    )
    if not isinstance(payload, dict) or not payload.get("protocolSection"):
        return None
    return payload


def read_cache(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "registries": {}}
    data = load_json(path)
    if not isinstance(data, dict):
        return {"schema_version": SCHEMA_VERSION, "registries": {}}
    registries = data.get("registries", {})
    if not isinstance(registries, dict):
        registries = {}
    return {"schema_version": data.get("schema_version", SCHEMA_VERSION), "registries": registries}


def cache_entry_from_payload(registry_id: str, payload: dict, omit_raw: bool) -> dict:
    entry = {
        "registry": "ClinicalTrials.gov",
        "registry_id": registry_id,
        "registry_kind": "clinicaltrials_gov",
        "lookup_status": "ok",
        "fetched_at_utc": now_utc(),
        "normalized": normalize_clinicaltrials_study(payload),
    }
    if not omit_raw:
        entry["raw"] = payload
    return entry


def error_cache_entry(registry_id: str, registry: str, status: str, error: str = "") -> dict:
    return {
        "registry": registry,
        "registry_id": registry_id,
        "registry_kind": registry_kind(registry_id),
        "lookup_status": status,
        "lookup_error": error,
        "fetched_at_utc": now_utc(),
        "normalized": {},
    }


def enrich_registry_group(
    grouped: Dict[str, dict],
    cache: dict,
    client: RateLimitedHttpClient,
    refresh: bool,
    omit_raw: bool,
) -> Tuple[dict, List[dict]]:
    registries = cache.setdefault("registries", {})
    lookup_events: List[dict] = []
    for registry_id, group in grouped.items():
        kind = group.get("registry_kind", "")
        existing = registries.get(registry_id)
        if existing and not refresh:
            lookup_events.append({"registry_id": registry_id, "registry_kind": kind, "event": "cache_hit"})
            continue
        if kind != "clinicaltrials_gov":
            registries[registry_id] = error_cache_entry(registry_id, kind, "unsupported_registry")
            lookup_events.append({"registry_id": registry_id, "registry_kind": kind, "event": "unsupported_registry"})
            continue
        try:
            payload = lookup_clinicaltrials_study(client, registry_id)
            if payload:
                registries[registry_id] = cache_entry_from_payload(registry_id, payload, omit_raw=omit_raw)
                lookup_events.append({"registry_id": registry_id, "registry_kind": kind, "event": "fetched"})
            else:
                registries[registry_id] = error_cache_entry(registry_id, "ClinicalTrials.gov", "not_found")
                lookup_events.append({"registry_id": registry_id, "registry_kind": kind, "event": "not_found"})
        except Exception as err:
            registries[registry_id] = error_cache_entry(
                registry_id,
                "ClinicalTrials.gov",
                "lookup_error",
                f"{type(err).__name__}: {err}",
            )
            lookup_events.append({"registry_id": registry_id, "registry_kind": kind, "event": "lookup_error"})
    cache["schema_version"] = SCHEMA_VERSION
    cache["generated_at_utc"] = now_utc()
    return cache, lookup_events


def flat_enrichment_rows(grouped: Dict[str, dict], cache: dict) -> List[dict]:
    rows: List[dict] = []
    registries = cache.get("registries", {}) if isinstance(cache.get("registries", {}), dict) else {}
    for registry_id, group in sorted(grouped.items()):
        entry = registries.get(registry_id, {})
        normalized = entry.get("normalized", {}) if isinstance(entry.get("normalized", {}), dict) else {}
        rows.append(
            {
                "registry_id": registry_id,
                "registry_kind": group.get("registry_kind", ""),
                "lookup_status": normalize(entry.get("lookup_status", "")),
                "lookup_error": normalize(entry.get("lookup_error", "")),
                "candidate_dois": " | ".join(group.get("candidate_dois", [])),
                "study_titles": " | ".join(group.get("study_titles", [])),
                "compounds": " | ".join(group.get("compounds", [])),
                "disorders": " | ".join(group.get("disorders", [])),
                "screening_relevance_values": " | ".join(group.get("screening_relevance_values", [])),
                "candidate_sources": " | ".join(group.get("candidate_sources", [])),
                **{key: normalize(value) for key, value in normalized.items()},
            }
        )
    return rows


def build_candidates(
    paper_db_rows: List[dict],
    screening_rows: List[dict],
    queue_rows: List[dict],
    include_unscreened: bool,
    require_primary_source: bool,
    primary_dois: set[str],
) -> Tuple[List[dict], int]:
    paper_by_doi = {
        normalize_doi(row.get("study_doi", "")).lower(): row
        for row in paper_db_rows
        if normalize_doi(row.get("study_doi", ""))
    }
    source_rows = [*screening_rows, *queue_rows]
    if include_unscreened:
        source_rows.extend(paper_db_rows)
    candidates = merge_candidate_rows(source_rows, paper_by_doi)
    before_primary_filter = len(candidates)
    if require_primary_source:
        candidates = [
            candidate for candidate in candidates
            if normalize_doi(candidate.get("study_doi", "")).lower() in primary_dois
        ]
    return candidates, before_primary_filter


def parse_relevance_filter(raw: str) -> set[str]:
    values = {normalize(part) for part in raw.split(",") if normalize(part)}
    return values or {"relevant", "uncertain"}


def default_paths(dataset: str) -> dict[str, Path]:
    return {
        "paper_db_json": ROOT / "data" / "processed" / f"paper_library_{dataset}.json",
        "screening_json": ROOT / "data" / "processed" / f"llm_abstract_screening_report_{dataset}.json",
        "relevant_queue": ROOT / "data" / "raw" / f"doi_queue.{dataset}.llm_relevant.txt",
        "uncertain_queue": ROOT / "data" / "raw" / f"doi_queue.{dataset}.llm_uncertain.txt",
        "stubs_json": ROOT / "data" / "processed" / f"{dataset}_claim_stubs.json",
        "curated_json": ROOT / "data" / "curated" / ("disorder_claims.json" if dataset == "disorder" else "claims.json"),
        "cache_json": ROOT / "data" / "processed" / f"trial_registry_cache_{dataset}.json",
        "out_json": ROOT / "data" / "processed" / f"trial_registry_enrichment_{dataset}.json",
        "out_csv": ROOT / "data" / "processed" / f"trial_registry_enrichment_{dataset}.csv",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Enrich screened disorder papers with trial-registry records. "
            "Writes standalone cache/report files and does not modify the paper library."
        )
    )
    parser.add_argument("--dataset", default=DEFAULT_DATASET, choices=["disorder"])
    parser.add_argument("--paper-db-json", default="")
    parser.add_argument("--screening-json", default="")
    parser.add_argument("--relevant-queue", default="")
    parser.add_argument("--uncertain-queue", default="")
    parser.add_argument("--stubs-json", default="")
    parser.add_argument("--curated-json", default="")
    parser.add_argument("--cache-json", default="")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-csv", default="")
    parser.add_argument("--include-relevance", default="relevant,uncertain")
    parser.add_argument(
        "--include-unscreened",
        action="store_true",
        help="Also scan all paper-library rows with registry IDs. Off by default to avoid broad enrichment.",
    )
    parser.add_argument(
        "--require-primary-source",
        action="store_true",
        help="Only enrich DOIs that are primary/original empirical in stubs or curated rows.",
    )
    parser.add_argument("--refresh", action="store_true", help="Refresh registry records already present in cache")
    parser.add_argument("--omit-raw", action="store_true", help="Do not store raw ClinicalTrials.gov payloads in cache")
    parser.add_argument("--rps", type=float, default=2.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--timeout-sec", type=int, default=40)
    args = parser.parse_args()

    paths = default_paths(args.dataset)
    paper_db_json = Path(args.paper_db_json).resolve() if args.paper_db_json else paths["paper_db_json"]
    screening_json = Path(args.screening_json).resolve() if args.screening_json else paths["screening_json"]
    relevant_queue = Path(args.relevant_queue).resolve() if args.relevant_queue else paths["relevant_queue"]
    uncertain_queue = Path(args.uncertain_queue).resolve() if args.uncertain_queue else paths["uncertain_queue"]
    stubs_json = Path(args.stubs_json).resolve() if args.stubs_json else paths["stubs_json"]
    curated_json = Path(args.curated_json).resolve() if args.curated_json else paths["curated_json"]
    cache_json = Path(args.cache_json).resolve() if args.cache_json else paths["cache_json"]
    out_json = Path(args.out_json).resolve() if args.out_json else paths["out_json"]
    out_csv = Path(args.out_csv).resolve() if args.out_csv else paths["out_csv"]

    include_relevance = parse_relevance_filter(args.include_relevance)
    paper_db_rows = load_json_array(paper_db_json)
    screening_rows = rows_from_screening_report(screening_json, include_relevance=include_relevance)
    queue_rows = [
        *parse_doi_queue(relevant_queue, relevance="relevant"),
        *parse_doi_queue(uncertain_queue, relevance="uncertain"),
    ]
    stubs = load_json_array(stubs_json)
    curated = load_json_array(curated_json)
    primary_dois = primary_source_dois(stubs, curated)
    candidates, candidates_before_primary = build_candidates(
        paper_db_rows=paper_db_rows,
        screening_rows=screening_rows,
        queue_rows=queue_rows,
        include_unscreened=args.include_unscreened,
        require_primary_source=args.require_primary_source,
        primary_dois=primary_dois,
    )
    grouped = group_candidates_by_registry(candidates)
    cache = read_cache(cache_json)
    client = RateLimitedHttpClient(
        rps=args.rps,
        max_retries=args.max_retries,
        timeout_sec=max(1, args.timeout_sec),
        user_agent="kg-pipeline/trial-registry-enrichment",
    )
    cache, lookup_events = enrich_registry_group(
        grouped=grouped,
        cache=cache,
        client=client,
        refresh=args.refresh,
        omit_raw=args.omit_raw,
    )
    flat_rows = flat_enrichment_rows(grouped, cache)
    event_counts = Counter(event["event"] for event in lookup_events)
    kind_counts = Counter(group.get("registry_kind", "") for group in grouped.values())
    lookup_status_counts = Counter(row.get("lookup_status", "") for row in flat_rows)
    report = {
        "generated_at_utc": now_utc(),
        "schema_version": SCHEMA_VERSION,
        "dataset": args.dataset,
        "inputs": {
            "paper_db_json": str(paper_db_json),
            "screening_json": str(screening_json),
            "relevant_queue": str(relevant_queue),
            "uncertain_queue": str(uncertain_queue),
            "stubs_json": str(stubs_json),
            "curated_json": str(curated_json),
        },
        "outputs": {
            "cache_json": str(cache_json),
            "out_csv": str(out_csv),
        },
        "filters": {
            "include_relevance": sorted(include_relevance),
            "include_unscreened": bool(args.include_unscreened),
            "require_primary_source": bool(args.require_primary_source),
        },
        "counts": {
            "paper_db_rows": len(paper_db_rows),
            "screening_rows": len(screening_rows),
            "queue_rows": len(queue_rows),
            "candidate_dois_with_registry_ids": len(candidates),
            "candidate_dois_before_primary_filter": candidates_before_primary,
            "primary_source_dois": len(primary_dois),
            "registry_ids": len(grouped),
            "registry_kind_counts": dict(kind_counts),
            "lookup_event_counts": dict(event_counts),
            "lookup_status_counts": dict(lookup_status_counts),
        },
        "registries": flat_rows,
    }
    write_json(cache_json, cache)
    write_json(out_json, report)
    write_csv(out_csv, flat_rows)

    print(
        f"Trial registry enrichment ({args.dataset}): "
        f"candidates={len(candidates)} registry_ids={len(grouped)} "
        f"fetched={event_counts.get('fetched', 0)} cache_hit={event_counts.get('cache_hit', 0)} "
        f"unsupported={event_counts.get('unsupported_registry', 0)}"
    )
    print(f"Report: {out_json}")
    print(f"Cache: {cache_json}")
    print(f"CSV: {out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
