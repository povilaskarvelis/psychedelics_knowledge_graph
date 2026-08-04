#!/usr/bin/env python3
"""Build route-aware extraction task records from the route table.

The extraction route table is one row per DOI plus extraction route. This
script turns those route rows into stable task records for downstream prompt
selection, model calls, retry bookkeeping, and provenance. It does not call a
model.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    from pipeline.fulltext.convert_pdfs import compact_text, normalize, normalize_doi
    from pipeline.extract.extraction_profile_matrix import text_depth_from_access
    from pipeline.extract.route_extraction_profiles import (
        domain_prompt_path,
        is_legacy_v1_secondary_profile,
        profile_for_key,
        prompt_path_for_depth,
        schema_path_for_profile,
        should_append_domain_addendum,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.convert_pdfs import compact_text, normalize, normalize_doi
    from pipeline.extract.extraction_profile_matrix import text_depth_from_access
    from pipeline.extract.route_extraction_profiles import (
        domain_prompt_path,
        is_legacy_v1_secondary_profile,
        profile_for_key,
        prompt_path_for_depth,
        schema_path_for_profile,
        should_append_domain_addendum,
    )


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROUTE_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes.parquet"
DEFAULT_METADATA_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"
DEFAULT_OUT_JSONL = ROOT / "data" / "processed" / "extraction" / "route_extraction_tasks.jsonl"
DEFAULT_REPORT_JSON = ROOT / "data" / "processed" / "extraction" / "route_extraction_tasks_report.json"
DEFAULT_SCHEMA = ROOT / "schema" / "extraction_task.schema.json"
DEFAULT_FULLTEXT_PACKET_PATHS = (
    ROOT / "data" / "processed" / "extraction" / "fulltext_packets.jsonl",
)

TASK_SCHEMA_VERSION = "route_extraction_task_v2"
PACKET_PROFILE_FULL = "full"
PACKET_PROFILE_PRIMARY = "primary_empirical"
PACKET_PROFILE_SECONDARY_SYNTHESIS = "secondary_synthesis"
PACKET_PROFILE_REVIEW_COVERAGE = "review_coverage"
PACKET_PROFILE_NOT_APPLICABLE = "not_applicable"
READY_ROUTE_ACTIONS = {
    "extract_from_full_text",
    "extract_from_abstract_only",
}
TERMINAL_SCHEMA_PROFILES = {
    "context_only_schema",
    "no_extraction_schema",
}
TERMINAL_PROMPT_PROFILES = {
    "context_only_or_skip",
    "no_extraction",
}
COMPATIBLE_PACKET_PROFILES = {
    PACKET_PROFILE_PRIMARY: {PACKET_PROFILE_PRIMARY, PACKET_PROFILE_FULL, ""},
    PACKET_PROFILE_SECONDARY_SYNTHESIS: {PACKET_PROFILE_SECONDARY_SYNTHESIS, PACKET_PROFILE_FULL, ""},
    PACKET_PROFILE_REVIEW_COVERAGE: {PACKET_PROFILE_REVIEW_COVERAGE, PACKET_PROFILE_FULL, ""},
    PACKET_PROFILE_FULL: {PACKET_PROFILE_FULL, ""},
    PACKET_PROFILE_NOT_APPLICABLE: {PACKET_PROFILE_NOT_APPLICABLE, ""},
}

PAPER_METADATA_FIELDS = [
    "doi",
    "openalex_id",
    "pmid",
    "pmcid",
    "study_title",
    "study_year",
    "authors",
    "study_journal",
    "publication_type",
    "trial_registry_ids",
    "publication_date",
    "journal_issn",
    "journal_eissn",
    "publisher",
    "mesh_terms",
    "keywords",
    "funders",
    "grant_ids",
    "related_dois",
    "publication_relations",
    "is_retracted",
    "has_correction",
    "language",
    "semantic_scholar_id",
    "open_access_is_oa",
    "open_access_status",
    "open_access_url",
    "best_pdf_url",
    "abstract",
]

ROUTE_CONTEXT_FIELDS = [
    "route_id",
    "doi",
    "source_family",
    "source_type",
    "secondary_source_types",
    "primary_secondary_source_type",
    "literature_type_confidence",
    "domain_route",
    "domain_tags",
    "domain_routing_primary_domain",
    "methodological_validity_tags",
    "domain_screening_decision",
    "domain_screening_reason",
    "domain_routing_model",
    "domain_needs_human_review",
    "domain_route_confidence",
    "bridge_clinical_mechanism",
    "study_system_hint",
    "access_tier",
    "source_text_state",
    "source_text_state_reason",
    "source_identity_verified",
    "has_abstract",
    "has_pdf_url",
    "has_converted_full_text",
    "fulltext_artifact_paths",
    "fulltext_char_count",
    "has_local_pdf",
    "local_pdf_paths",
    "local_pdf_count",
    "open_access_status",
    "best_pdf_url",
    "route_action",
    "prompt_profile",
    "schema_profile",
    "route_priority",
    "route_confidence",
    "route_basis",
]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return normalize(value).lower() in {"1", "true", "yes", "y"}


def split_values(value: object) -> list[str]:
    text = normalize(value)
    if not text:
        return []
    return [part.strip() for part in text.split("|") if part.strip()]


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def canonical_sha256(payload: object) -> str:
    body = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def stable_packet_payload(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: stable_packet_payload(item)
            for key, item in sorted(value.items())
            if key not in {"_packet_source_path", "generated_at_utc"}
        }
    if isinstance(value, list):
        return [stable_packet_payload(item) for item in value]
    return value


def artifact_file_fingerprints(paths: Iterable[str]) -> list[dict]:
    records: list[dict] = []
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_file():
            records.append({"path": str(path), "status": "missing"})
            continue
        records.append(
            {
                "path": str(path),
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return records


def source_fingerprint_for_task(
    *,
    text_source: dict,
    metadata: dict,
    packet: dict | None,
) -> str:
    mode = normalize(text_source.get("mode", ""))
    payload: dict = {"mode": mode}
    if mode == "abstract":
        payload.update(
            {
                "title": normalize(metadata.get("study_title", "")),
                "abstract": normalize(metadata.get("abstract", "")),
            }
        )
    elif mode == "full_text_packet" and packet:
        payload["packet"] = stable_packet_payload(packet)
    elif mode == "full_text_artifact":
        payload["artifacts"] = artifact_file_fingerprints(
            text_source.get("fulltext_artifact_paths", [])
        )
    else:
        payload.update(
            {
                "title": normalize(metadata.get("study_title", "")),
                "abstract": normalize(metadata.get("abstract", "")),
                "route_action": normalize(text_source.get("route_action", "")),
            }
        )
    return canonical_sha256(payload)


def contract_assets_fingerprint_for_task(contract: dict) -> str:
    """Fingerprint the prompt, domain addendum, and schema actually selected.

    Task identity must change when the extraction instructions change, not
    only when the paper text changes. Terminal routes have no model assets but
    still receive a stable fingerprint of that empty contract.
    """
    prompt_profile = normalize(contract.get("prompt_profile", ""))
    schema_profile = normalize(contract.get("schema_profile", ""))
    domain_route = normalize(contract.get("domain_route", ""))
    profile = profile_for_key(prompt_profile, schema_profile)
    assets: list[dict] = []
    if profile.has_model_contract:
        text_depth = text_depth_from_access(normalize(contract.get("access_level", "")))
        prompt_path = prompt_path_for_depth(profile, text_depth)
        schema_path = schema_path_for_profile(profile, domain_route)
        selected_paths = [("paper_type_prompt", prompt_path), ("schema", schema_path)]
        addendum_path = domain_prompt_path(domain_route)
        if should_append_domain_addendum(profile) and addendum_path is not None and addendum_path.exists():
            selected_paths.append(("domain_addendum", addendum_path))
        for role, path in selected_paths:
            if path is None or not path.is_file():
                raise FileNotFoundError(f"Missing {role} asset for {prompt_profile}/{schema_profile}: {path}")
            assets.append(
                {
                    "role": role,
                    "path": str(path.resolve().relative_to(ROOT.resolve())),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    return canonical_sha256(
        {
            "prompt_profile": prompt_profile,
            "schema_profile": schema_profile,
            "domain_route": domain_route,
            "assets": assets,
        }
    )


def input_fingerprint_for_task(
    *,
    route_id: str,
    route_context: dict,
    contract: dict,
    source_fingerprint: str,
) -> str:
    return canonical_sha256(
        {
            "route_id": route_id,
            "domain_route": normalize(route_context.get("domain_route", "")),
            "route_action": normalize(route_context.get("route_action", "")),
            "prompt_profile": normalize(contract.get("prompt_profile", "")),
            "schema_profile": normalize(contract.get("schema_profile", "")),
            "contract_version": normalize(contract.get("contract_version", "")),
            "contract_assets_fingerprint": normalize(contract.get("contract_assets_fingerprint", "")),
            "source_fingerprint": source_fingerprint,
        }
    )


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            item = json.loads(text)
            if isinstance(item, dict):
                rows.append(item)
    return rows


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def read_doi_file(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"DOI file not found: {path}")
    out: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if not row:
                continue
            doi = normalize_doi(row[0])
            if doi:
                out.add(doi)
    return out


def rows_by_doi(df: pd.DataFrame) -> dict[str, dict]:
    if df.empty or "doi" not in df.columns:
        return {}
    out: dict[str, dict] = {}
    for row in df.to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        if doi and doi not in out:
            out[doi] = row
    return out


def packet_doi(packet: dict) -> str:
    return normalize_doi(packet.get("study_doi", "") or packet.get("doi", ""))


def packet_profile(packet: dict | None) -> str:
    if not packet:
        return ""
    profile = normalize(packet.get("packet_profile", ""))
    if profile:
        return profile
    summary = packet.get("document_summary", {})
    if isinstance(summary, dict):
        return normalize(summary.get("packet_profile", ""))
    return ""


def load_packet_index(paths: Iterable[Path]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for path in paths:
        if not path.exists():
            continue
        for packet in read_jsonl(path):
            doi = packet_doi(packet)
            if not doi:
                continue
            packet_copy = dict(packet)
            packet_copy["_packet_source_path"] = str(path)
            out.setdefault(doi, []).append(packet_copy)
    return out


def expected_packet_profile_for_route(route_row: dict) -> str:
    prompt_profile = normalize(route_row.get("prompt_profile", ""))
    schema_profile = normalize(route_row.get("schema_profile", ""))
    if prompt_profile in TERMINAL_PROMPT_PROFILES or schema_profile in TERMINAL_SCHEMA_PROFILES:
        return PACKET_PROFILE_NOT_APPLICABLE
    if prompt_profile == "secondary_meta_analysis" or schema_profile == "meta_analysis_evidence_schema":
        return PACKET_PROFILE_SECONDARY_SYNTHESIS
    if schema_profile == "review_coverage_schema" or prompt_profile in {
        "secondary_structured_review",
        "secondary_narrative_review",
        "secondary_review_coverage",
    }:
        return PACKET_PROFILE_REVIEW_COVERAGE
    if schema_profile == "primary_evidence_schema" or prompt_profile.startswith("primary_"):
        return PACKET_PROFILE_PRIMARY
    return PACKET_PROFILE_FULL


def packet_profile_status(expected_profile: str, actual_profile: str, has_packet: bool) -> str:
    expected = normalize(expected_profile)
    actual = normalize(actual_profile)
    if expected == PACKET_PROFILE_NOT_APPLICABLE:
        return "not_applicable"
    if not has_packet:
        return "no_packet"
    if actual == expected:
        return "matches_expected"
    if actual == PACKET_PROFILE_FULL and expected in {
        PACKET_PROFILE_PRIMARY,
        PACKET_PROFILE_SECONDARY_SYNTHESIS,
        PACKET_PROFILE_REVIEW_COVERAGE,
    }:
        return "compatible_full_packet"
    if not actual:
        return "missing_packet_profile"
    return "profile_mismatch"


def packet_profile_is_compatible(expected_profile: str, actual_profile: str) -> bool:
    expected = normalize(expected_profile)
    actual = normalize(actual_profile)
    if expected == PACKET_PROFILE_NOT_APPLICABLE:
        return True
    return actual in COMPATIBLE_PACKET_PROFILES.get(expected, {expected, PACKET_PROFILE_FULL, ""})


def choose_packet(route_row: dict, packets_by_doi: dict[str, list[dict]]) -> tuple[dict | None, str]:
    doi = normalize_doi(route_row.get("doi", ""))
    packets = packets_by_doi.get(doi, [])
    if not packets:
        return None, "no_packet_for_doi"
    expected_profile = expected_packet_profile_for_route(route_row)
    preferred_profiles = [expected_profile]
    if expected_profile != PACKET_PROFILE_FULL:
        preferred_profiles.append(PACKET_PROFILE_FULL)
    preferred_profiles.append("")

    for profile in preferred_profiles:
        for packet in packets:
            actual_profile = packet_profile(packet)
            if actual_profile == profile:
                basis = "matched_doi"
                if profile:
                    basis += f"_and_packet_profile:{profile}"
                else:
                    basis += "_with_missing_packet_profile"
                return packet, basis

    return packets[0], f"matched_doi_with_profile_mismatch:{packet_profile(packets[0]) or 'missing'}"

def metadata_for_task(route_row: dict, metadata_by_doi: dict[str, dict]) -> dict:
    doi = normalize_doi(route_row.get("doi", ""))
    metadata = metadata_by_doi.get(doi, {})
    out = {}
    for field in PAPER_METADATA_FIELDS:
        source_field = "doi" if field == "doi" else field
        value = metadata.get(source_field, "")
        if field in {"is_retracted", "has_correction", "open_access_is_oa"}:
            out[field] = clean_bool(value)
        else:
            out[field] = compact_text(value)
    out["doi"] = doi
    if not out["study_title"]:
        out["study_title"] = compact_text(route_row.get("study_title", ""))
    if not out["study_year"]:
        out["study_year"] = compact_text(route_row.get("study_year", ""))
    if not out["publication_type"]:
        out["publication_type"] = compact_text(route_row.get("publication_type", ""))
    if not out["best_pdf_url"]:
        out["best_pdf_url"] = compact_text(route_row.get("best_pdf_url", ""))
    if not out["open_access_status"]:
        out["open_access_status"] = compact_text(route_row.get("open_access_status", ""))
    return out


def route_context_for_task(route_row: dict) -> dict:
    out = {}
    for field in ROUTE_CONTEXT_FIELDS:
        value = route_row.get(field, "")
        if field in {
            "domain_needs_human_review",
            "bridge_clinical_mechanism",
            "has_abstract",
            "has_pdf_url",
            "has_converted_full_text",
            "has_local_pdf",
            "source_identity_verified",
        }:
            out[field] = clean_bool(value)
        elif field in {"fulltext_char_count", "local_pdf_count", "route_priority"}:
            try:
                out[field] = int(value or 0)
            except (TypeError, ValueError):
                out[field] = 0
        else:
            out[field] = compact_text(value)
    out["doi"] = normalize_doi(out.get("doi", ""))
    out["schema_profile"] = normalize(out.get("schema_profile", ""))
    return out


def access_level_for_route(route_row: dict) -> str:
    access = normalize(route_row.get("access_tier", ""))
    if access == "full_text_available":
        return "full_text_seen"
    if access == "abstract_only":
        return "abstract_only"
    return access or "unknown"


def output_family_for_route(route_row: dict) -> str:
    schema_profile = normalize(route_row.get("schema_profile", ""))
    if schema_profile == "meta_analysis_evidence_schema":
        return "meta_analysis_evidence"
    if schema_profile == "review_coverage_schema":
        return "review_coverage"
    if schema_profile == "recommendation_consensus_schema":
        return "recommendation_consensus"
    if schema_profile == "context_only_schema":
        return "context_only"
    return "primary_evidence"


def text_source_for_task(route_row: dict, metadata: dict, packet: dict | None, packet_basis: str) -> dict:
    action = normalize(route_row.get("route_action", ""))
    expected_profile = expected_packet_profile_for_route(route_row)
    actual_profile = packet_profile(packet)
    profile_status = packet_profile_status(expected_profile, actual_profile, bool(packet))
    if expected_profile == PACKET_PROFILE_NOT_APPLICABLE:
        mode = "not_applicable"
        status = "not_model_ready"
    elif action == "extract_from_full_text":
        if packet and packet_profile_is_compatible(expected_profile, actual_profile):
            mode = "full_text_packet"
            status = "ready_for_model"
        elif packet:
            mode = "full_text_packet"
            status = "needs_expected_fulltext_packet"
        else:
            mode = "full_text_artifact"
            status = "needs_fulltext_packet"
    elif action == "extract_from_abstract_only":
        mode = "abstract"
        status = "ready_for_model" if normalize(metadata.get("abstract", "")) else "missing_abstract"
    else:
        mode = "not_ready"
        status = "not_model_ready"

    packet_id = ""
    packet_source = ""
    if packet:
        packet_id = normalize(packet.get("packet_id", ""))
        packet_source = normalize(packet.get("_packet_source_path", ""))

    return {
        "mode": mode,
        "status": status,
        "access_level": access_level_for_route(route_row),
        "route_action": action,
        "packet_id": packet_id,
        "packet_source_path": packet_source,
        "packet_selection_basis": packet_basis,
        "expected_packet_profile": expected_profile,
        "packet_profile": actual_profile,
        "packet_profile_status": profile_status,
        "fulltext_artifact_paths": split_values(route_row.get("fulltext_artifact_paths", "")),
        "local_pdf_paths": split_values(route_row.get("local_pdf_paths", "")),
        "abstract_available": bool(normalize(metadata.get("abstract", ""))),
    }


def content_for_task(metadata: dict, packet: dict | None, *, include_packet_content: bool) -> dict:
    content = {
        "title": normalize(metadata.get("study_title", "")),
        "abstract": normalize(metadata.get("abstract", "")),
    }
    if packet:
        if include_packet_content:
            content["packet"] = {key: value for key, value in packet.items() if key != "_packet_source_path"}
        else:
            content["packet_summary"] = {
                "packet_id": normalize(packet.get("packet_id", "")),
                "document_summary": packet.get("document_summary", {}) if isinstance(packet.get("document_summary"), dict) else {},
            }
    return content


def extraction_contract_for_task(route_row: dict) -> dict:
    route_id = normalize(route_row.get("route_id", ""))
    prompt_profile = normalize(route_row.get("prompt_profile", ""))
    schema_profile = normalize(route_row.get("schema_profile", ""))
    return {
        "contract_version": TASK_SCHEMA_VERSION,
        "route_id": route_id,
        "prompt_profile": prompt_profile,
        "schema_profile": schema_profile,
        "domain_route": normalize(route_row.get("domain_route", "")),
        "output_family": output_family_for_route(route_row),
        "source_family": normalize(route_row.get("source_family", "")),
        "source_type": normalize(route_row.get("source_type", "")),
        "access_level": access_level_for_route(route_row),
        "expected_packet_profile": expected_packet_profile_for_route(route_row),
    }


def task_from_route(
    route_row: dict,
    *,
    metadata_by_doi: dict[str, dict],
    packets_by_doi: dict[str, list[dict]],
    generated_at_utc: str,
    include_packet_content: bool,
) -> dict:
    route_id = normalize(route_row.get("route_id", ""))
    metadata = metadata_for_task(route_row, metadata_by_doi)
    packet, packet_basis = choose_packet(route_row, packets_by_doi)
    text_source = text_source_for_task(route_row, metadata, packet, packet_basis)
    route_context = route_context_for_task(route_row)
    contract = extraction_contract_for_task(route_row)
    contract["contract_assets_fingerprint"] = contract_assets_fingerprint_for_task(contract)
    source_fingerprint = source_fingerprint_for_task(
        text_source=text_source,
        metadata=metadata,
        packet=packet,
    )
    text_source["source_fingerprint"] = source_fingerprint
    input_fingerprint = input_fingerprint_for_task(
        route_id=route_id,
        route_context=route_context,
        contract=contract,
        source_fingerprint=source_fingerprint,
    )
    task_id = hashlib.sha256(f"{route_id}\0{input_fingerprint}".encode("utf-8")).hexdigest()[:20]
    return {
        "schema_version": TASK_SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc,
        "task_id": task_id,
        "route_id": route_id,
        "input_fingerprint": input_fingerprint,
        "study_doi": normalize_doi(route_row.get("doi", "")),
        "task_status": text_source["status"],
        "paper_metadata": metadata,
        "route_context": route_context,
        "extraction_contract": contract,
        "text_source": text_source,
        "content": content_for_task(metadata, packet, include_packet_content=include_packet_content),
    }


def route_row_matches_requested_scope(route_row: dict, args: argparse.Namespace, doi_filter: set[str]) -> bool:
    doi = normalize_doi(route_row.get("doi", ""))
    if doi_filter and doi not in doi_filter:
        return False
    if args.only_retained and not clean_bool(route_row.get("retained_for_extraction_candidate", False)):
        return False
    action = normalize(route_row.get("route_action", ""))
    if args.route_action and action not in args.route_action:
        return False
    if not args.route_action and action not in READY_ROUTE_ACTIONS:
        return False
    if args.prompt_profile and normalize(route_row.get("prompt_profile", "")) not in args.prompt_profile:
        return False
    schema_profile = normalize(route_row.get("schema_profile", ""))
    if args.schema_profile and schema_profile not in args.schema_profile:
        return False
    if args.domain_route and normalize(route_row.get("domain_route", "")) not in args.domain_route:
        return False
    return True


def route_row_is_selected(route_row: dict, args: argparse.Namespace, doi_filter: set[str]) -> bool:
    return route_row_matches_requested_scope(route_row, args, doi_filter) and not is_legacy_v1_secondary_profile(
        route_row.get("prompt_profile", ""),
        route_row.get("schema_profile", ""),
    )


def build_tasks(args: argparse.Namespace) -> tuple[list[dict], dict]:
    route_table = Path(args.route_table).resolve()
    metadata_table = Path(args.metadata_table).resolve()
    generated_at_utc = now_utc()

    if not route_table.exists():
        raise FileNotFoundError(f"Route table not found: {route_table}")
    if not metadata_table.exists():
        raise FileNotFoundError(f"Metadata table not found: {metadata_table}")

    route_df = pd.read_parquet(route_table)
    metadata_df = pd.read_parquet(metadata_table)
    metadata_by_doi = rows_by_doi(metadata_df)
    doi_filter = read_doi_file(Path(args.doi_file).resolve()) if args.doi_file else set()
    packet_paths = [Path(path).resolve() for path in args.fulltext_packets_jsonl]
    packets_by_doi = load_packet_index(packet_paths)

    route_rows = route_df.to_dict("records")
    legacy_v1_secondary_route_rows = [
        row
        for row in route_rows
        if is_legacy_v1_secondary_profile(
            row.get("prompt_profile", ""),
            row.get("schema_profile", ""),
        )
        and route_row_matches_requested_scope(row, args, doi_filter)
    ]
    selected_rows = [
        row
        for row in route_rows
        if route_row_is_selected(row, args, doi_filter)
    ]
    tasks = [
        task_from_route(
            row,
            metadata_by_doi=metadata_by_doi,
            packets_by_doi=packets_by_doi,
            generated_at_utc=generated_at_utc,
            include_packet_content=args.include_packet_content,
        )
        for row in selected_rows
    ]
    if args.only_ready:
        tasks = [task for task in tasks if task["task_status"] == "ready_for_model"]
    if args.limit:
        tasks = tasks[: args.limit]

    report = {
        "generated_at_utc": generated_at_utc,
        "schema_version": TASK_SCHEMA_VERSION,
        "inputs": {
            "route_table": str(route_table),
            "metadata_table": str(metadata_table),
            "fulltext_packets_jsonl": [str(path) for path in packet_paths if path.exists()],
            "doi_file": str(Path(args.doi_file).resolve()) if args.doi_file else "",
            "only_retained": bool(args.only_retained),
            "only_ready": bool(args.only_ready),
            "include_packet_content": bool(args.include_packet_content),
        },
        "route_rows_read": len(route_df),
        "legacy_v1_secondary_route_rows_hard_disabled": len(legacy_v1_secondary_route_rows),
        "legacy_v1_secondary_profile_counts": dict(
            Counter(
                f"{normalize(row.get('prompt_profile', ''))}/{normalize(row.get('schema_profile', ''))}"
                for row in legacy_v1_secondary_route_rows
            )
        ),
        "route_rows_selected_before_limit": len(selected_rows),
        "tasks_written": len(tasks),
        "unique_dois": len({task["study_doi"] for task in tasks}),
        "by_task_status": dict(Counter(task["task_status"] for task in tasks)),
        "by_route_action": dict(Counter(task["route_context"]["route_action"] for task in tasks)),
        "by_prompt_profile": dict(Counter(task["extraction_contract"]["prompt_profile"] for task in tasks)),
        "by_schema_profile": dict(Counter(task["extraction_contract"]["schema_profile"] for task in tasks)),
        "by_output_family": dict(Counter(task["extraction_contract"]["output_family"] for task in tasks)),
        "by_text_mode": dict(Counter(task["text_source"]["mode"] for task in tasks)),
        "by_expected_packet_profile": dict(Counter(task["extraction_contract"]["expected_packet_profile"] for task in tasks)),
        "by_packet_profile_status": dict(Counter(task["text_source"]["packet_profile_status"] for task in tasks)),
    }
    return tasks, report


def existing_default_packet_paths() -> list[Path]:
    return [path for path in DEFAULT_FULLTEXT_PACKET_PATHS if path.exists()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route-table", default=str(DEFAULT_ROUTE_TABLE))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--out-jsonl", default=str(DEFAULT_OUT_JSONL))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="Schema path to record in reports; not used for validation yet")
    parser.add_argument("--doi-file", default="")
    parser.add_argument(
        "--article-text-inputs-jsonl",
        "--fulltext-packets-jsonl",
        dest="fulltext_packets_jsonl",
        action="append",
        default=[],
        help="JSONL article text input files. --fulltext-packets-jsonl is a compatibility alias.",
    )
    parser.add_argument(
        "--no-default-article-text-inputs",
        "--no-default-fulltext-packets",
        dest="no_default_fulltext_packets",
        action="store_true",
        help="Do not load the default neutral article text input file.",
    )
    parser.add_argument("--route-action", action="append", default=[])
    parser.add_argument("--prompt-profile", action="append", default=[])
    parser.add_argument("--schema-profile", action="append", default=[])
    parser.add_argument("--domain-route", action="append", default=[])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--include-article-text-content",
        "--include-packet-content",
        dest="include_packet_content",
        action="store_true",
        help="Embed article text input content in task records. The packet wording is kept as a compatibility alias.",
    )
    parser.add_argument("--only-ready", action="store_true", help="Keep only tasks with model-ready text content")
    parser.add_argument("--include-unretained", action="store_true", help="Include rows not retained for extraction")
    args = parser.parse_args()
    args.only_retained = not args.include_unretained
    default_packet_paths = [] if args.no_default_fulltext_packets else [str(path) for path in existing_default_packet_paths()]
    args.fulltext_packets_jsonl = [
        path
        for path in [*default_packet_paths, *args.fulltext_packets_jsonl]
        if normalize(path)
    ]
    return args


def main() -> int:
    args = parse_args()
    tasks, report = build_tasks(args)
    out_jsonl = Path(args.out_jsonl).resolve()
    report_json = Path(args.report_json).resolve()
    write_jsonl(out_jsonl, tasks)
    report["outputs"] = {
        "tasks_jsonl": str(out_jsonl),
        "report_json": str(report_json),
        "task_schema": str(Path(args.schema).resolve()),
    }
    write_json(report_json, report)
    print(f"Tasks: {out_jsonl}")
    print(f"Task rows: {report['tasks_written']}")
    print(f"Task status: {report['by_task_status']}")
    print(f"Prompt profiles: {report['by_prompt_profile']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
