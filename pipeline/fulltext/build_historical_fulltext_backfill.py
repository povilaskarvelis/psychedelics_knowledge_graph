#!/usr/bin/env python3
"""Build a safe OA/full-text backfill cohort from active abstract-only extractions.

The worklist is retrieval-only. It never mutates the active extraction run or
graph. Recovered full texts must later pass normal conversion, identity audit,
full-text extraction, and DOI-scoped update finalization before promotion.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.extract.build_extraction_routes import (  # noqa: E402
    DEFAULT_CANDIDATE_TABLE,
    DEFAULT_METADATA_TABLE,
    apply_fulltext_access_override,
    load_manual_fulltext_access_overrides,
    merged_extraction_metadata,
    metadata_other_url_candidates,
    metadata_pdf_url_candidates,
    metadata_probable_pdf_url_candidates,
)
from pipeline.fulltext.build_fulltext_enrichment_worklist import clean, truthy  # noqa: E402
from pipeline.ingest.metadata_utils import normalize_doi, status_is_open  # noqa: E402
from pipeline.validate.doi_aliases import (  # noqa: E402
    DEFAULT_DOI_ALIAS_REGISTRY,
    load_doi_aliases,
)


DEFAULT_ACTIVE_EXTRACTION_POINTER = ROOT / "data" / "processed" / "extraction" / "active_routed_run.json"
DEFAULT_ACCESS_OVERRIDES = ROOT / "pipeline" / "fulltext" / "manual_fulltext_access_overrides.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "processed" / "corpus" / "historical_fulltext_backfill"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def resolve_project_path(value: object) -> Path:
    path = Path(clean(value))
    return path if path.is_absolute() else ROOT / path


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def active_abstract_only_outputs(pointer_path: Path, aliases: dict[str, str]) -> tuple[dict[str, dict], Path]:
    pointer = load_json(pointer_path)
    outputs_path = resolve_project_path(pointer.get("outputs_jsonl", ""))
    if not outputs_path.is_file():
        raise FileNotFoundError(f"Active extraction outputs not found: {outputs_path}")
    by_doi: dict[str, dict] = defaultdict(lambda: {"task_count": 0, "item_count": 0, "route_ids": []})
    with outputs_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            result = row.get("result") if isinstance(row.get("result"), dict) else {}
            if clean(result.get("text_depth", "")) != "abstract_only" or clean(row.get("status", "")) != "ok":
                continue
            raw_doi = normalize_doi(result.get("study_doi", "") or row.get("doi", ""))
            doi = aliases.get(raw_doi, raw_doi)
            if not doi:
                continue
            entry = by_doi[doi]
            entry["task_count"] += 1
            items = result.get("items")
            entry["item_count"] += len(items) if isinstance(items, list) else 0
            route_id = clean(row.get("route_id", "") or result.get("route_id", ""))
            if route_id and route_id not in entry["route_ids"]:
                entry["route_ids"].append(route_id)
    return dict(by_doi), outputs_path


def refreshed_open_access_evidence_from_report(path: Path | None) -> dict[str, bool]:
    if path is None or not path.is_file():
        return {}
    payload = load_json(path)
    if payload.get("complete") is not True:
        raise RuntimeError(
            f"OA refresh report is incomplete; refusing to build a retrieval cohort: {path}"
        )
    records = [row for row in payload.get("records", []) if isinstance(row, dict)]
    missing_evidence = [
        normalize_doi(row.get("doi", ""))
        for row in records
        if "fresh_open_access_positive" not in row
    ]
    if missing_evidence:
        raise RuntimeError(
            "OA refresh report lacks per-run OA evidence; rerun with the current refresh script "
            f"before building a historical retrieval cohort: {path}"
        )
    return {
        normalize_doi(row.get("doi", "")): row.get("fresh_open_access_positive") is True
        for row in records
        if normalize_doi(row.get("doi", ""))
    }


def local_pdf_available(row: dict) -> bool:
    for field in ("pdf_local_path", "local_pdf_paths"):
        for raw in clean(row.get(field, "")).split("|"):
            if raw and Path(raw).is_file():
                return True
    return False


def local_pdf_paths(row: dict) -> list[str]:
    paths: list[str] = []
    for field in ("pdf_local_path", "local_pdf_paths"):
        for raw in clean(row.get(field, "")).split("|"):
            value = raw.strip()
            if value and value not in paths:
                paths.append(value)
    return paths


def classify_action(
    row: dict,
    *,
    refreshed: bool,
    fresh_oa_positive: bool | None = None,
    access_override: dict,
) -> tuple[str, bool, str]:
    if not truthy(row.get("retained_for_extraction_candidate", False)):
        return "not_currently_retained", False, "Current screening/routing no longer retains this DOI."
    manual_action = clean(access_override.get("manual_access_action", ""))
    if manual_action == "abstract_only":
        return "manual_abstract_only", False, "A curated override requires abstract-only extraction."
    if manual_action == "suppress_pdf_download":
        return "manual_no_usable_pdf", False, "Manual review already found no usable article PDF."
    if truthy(row.get("has_converted_full_text", False)):
        return "reextract_existing_fulltext", False, "Converted article text is already available."
    if local_pdf_available(row):
        return "convert_local_pdf", True, "A local PDF was recovered after the active abstract-only extraction."
    if not refreshed:
        return "refresh_oa_status", False, "OA status has not yet been refreshed for this backfill run."

    access_row = apply_fulltext_access_override(row, access_override)
    if fresh_oa_positive is None:
        fresh_oa_positive = truthy(access_row.get("open_access_is_oa", False)) or status_is_open(
            clean(access_row.get("open_access_status", ""))
        )
    if not fresh_oa_positive:
        return "no_open_access_route", False, "No provider returned positive OA evidence in this refresh run."
    probable_pdf_candidates = metadata_probable_pdf_url_candidates(access_row)
    if probable_pdf_candidates:
        return "download_known_pdf", True, "Fresh OA metadata identifies an open-access PDF candidate."
    return "resolve_oa_landing_page", True, "Fresh OA metadata is positive but exposes only a landing page."


def build(args: argparse.Namespace) -> dict:
    pointer_path = Path(args.active_extraction_pointer).resolve()
    candidate_path = Path(args.candidate_table).resolve()
    metadata_path = Path(args.metadata_table).resolve()
    alias_path = Path(args.doi_alias_registry).resolve()
    access_path = Path(args.manual_fulltext_access_overrides).resolve()
    refresh_report_path = Path(args.oa_refresh_report).resolve() if clean(args.oa_refresh_report) else None
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    aliases = load_doi_aliases(alias_path)
    active, outputs_path = active_abstract_only_outputs(pointer_path, aliases)
    active_pointer = load_json(pointer_path)
    evidence_path = resolve_project_path(active_pointer.get("evidence_rows_json", ""))
    candidate_df = pd.read_parquet(candidate_path)
    metadata_df = merged_extraction_metadata(candidate_df, pd.read_parquet(metadata_path))
    metadata_by_doi = {
        normalize_doi(row.get("doi", "")): row
        for row in metadata_df.fillna("").to_dict("records")
        if normalize_doi(row.get("doi", ""))
    }
    access_overrides = load_manual_fulltext_access_overrides(access_path)
    refreshed_oa = refreshed_open_access_evidence_from_report(refresh_report_path)
    generated_at = now_utc()

    rows: list[dict] = []
    for doi, active_state in sorted(active.items()):
        metadata = metadata_by_doi.get(doi, {})
        access_override = access_overrides.get(doi, {})
        action, enrichment_needed, reason = classify_action(
            metadata,
            refreshed=doi in refreshed_oa,
            fresh_oa_positive=refreshed_oa.get(doi),
            access_override=access_override,
        )
        access_metadata = apply_fulltext_access_override(metadata, access_override)
        pdf_candidates = metadata_pdf_url_candidates(access_metadata)
        probable = metadata_probable_pdf_url_candidates(access_metadata)
        local_paths = local_pdf_paths(metadata)
        rows.append(
            {
                "table_version": "historical_fulltext_backfill_v1",
                "generated_at_utc": generated_at,
                "doi": doi,
                "selected_for_downstream": action not in {
                    "not_currently_retained",
                    "manual_abstract_only",
                    "manual_no_usable_pdf",
                    "no_open_access_route",
                },
                "fulltext_enrichment_needed": enrichment_needed,
                "fulltext_enrichment_action": action,
                "fulltext_enrichment_reason": reason,
                "active_extraction_text_depth": "abstract_only",
                "active_abstract_task_count": active_state["task_count"],
                "active_abstract_item_count": active_state["item_count"],
                "active_route_ids": "|".join(active_state["route_ids"]),
                "replacement_contract": "replace_only_after_validated_fulltext_extraction",
                "oa_refresh_completed": doi in refreshed_oa,
                "oa_refresh_fresh_positive": refreshed_oa.get(doi, False),
                "study_title": clean(metadata.get("study_title", "")),
                "study_year": clean(metadata.get("study_year", "")),
                "abstract": clean(metadata.get("abstract", "")),
                "source_family": clean(metadata.get("literature_source_family", "")),
                "source_type": clean(metadata.get("literature_source_type", "")),
                "open_access_is_oa": clean(access_metadata.get("open_access_is_oa", "")),
                "open_access_status": clean(access_metadata.get("open_access_status", "")),
                "open_access_url": clean(access_metadata.get("open_access_url", "")),
                "best_pdf_url": probable[0] if probable else pdf_candidates[0] if pdf_candidates else "",
                "pdf_url_candidates": "|".join(pdf_candidates),
                "probable_pdf_url_candidates": "|".join(probable),
                "other_url_candidates": "|".join(metadata_other_url_candidates(access_metadata)),
                "has_converted_full_text": truthy(metadata.get("has_converted_full_text", False)),
                "has_local_pdf": local_pdf_available(metadata),
                "pdf_local_path": local_paths[0] if local_paths else "",
                "local_pdf_paths": "|".join(local_paths),
                "manual_fulltext_access_action": clean(access_override.get("manual_access_action", "")),
            }
        )

    frame = pd.DataFrame(rows)
    table_path = output_dir / "historical_fulltext_backfill_worklist.parquet"
    csv_path = output_dir / "historical_fulltext_backfill_worklist.csv"
    frame.to_parquet(table_path, engine="pyarrow", index=False)
    frame.to_csv(csv_path, index=False)

    def write_dois(name: str, actions: set[str]) -> tuple[Path, int]:
        path = output_dir / name
        values = frame.loc[frame["fulltext_enrichment_action"].isin(actions), "doi"].tolist()
        path.write_text("".join(f"{doi}\n" for doi in values), encoding="utf-8")
        return path, len(values)

    refresh_path, refresh_count = write_dois("oa_refresh_dois.txt", {"refresh_oa_status"})
    retrieval_path, retrieval_count = write_dois(
        "oa_retrieval_dois.txt", {"download_known_pdf", "resolve_oa_landing_page"}
    )
    conversion_path, conversion_count = write_dois("local_pdf_conversion_dois.txt", {"convert_local_pdf"})
    reextract_path, reextract_count = write_dois(
        "fulltext_reextraction_ready_dois.txt", {"reextract_existing_fulltext"}
    )
    report = {
        "schema_version": "historical_fulltext_backfill_report_v1",
        "generated_at_utc": generated_at,
        "inputs": {
            "active_extraction_pointer": str(pointer_path),
            "active_extraction_run_id": clean(active_pointer.get("run_id", "")),
            "active_outputs_jsonl": str(outputs_path),
            "active_outputs_sha256": file_sha256(outputs_path),
            "active_evidence_rows_json": str(evidence_path) if evidence_path.is_file() else "",
            "active_evidence_rows_sha256": file_sha256(evidence_path) if evidence_path.is_file() else "",
            "candidate_table": str(candidate_path),
            "metadata_table": str(metadata_path),
            "doi_alias_registry": str(alias_path),
            "manual_fulltext_access_overrides": str(access_path),
            "oa_refresh_report": str(refresh_report_path) if refresh_report_path else "",
        },
        "counts": {
            "active_abstract_only_dois": len(frame),
            "active_abstract_only_tasks": int(frame["active_abstract_task_count"].sum()),
            "active_abstract_only_items": int(frame["active_abstract_item_count"].sum()),
            "oa_refresh_dois": refresh_count,
            "oa_retrieval_dois": retrieval_count,
            "local_pdf_conversion_dois": conversion_count,
            "fulltext_reextraction_ready_dois": reextract_count,
            "fresh_oa_positive_dois": sum(refreshed_oa.values()),
            "fresh_oa_negative_dois": len(refreshed_oa) - sum(refreshed_oa.values()),
        },
        "by_fulltext_enrichment_action": dict(Counter(frame["fulltext_enrichment_action"])),
        "outputs": {
            "worklist_parquet": str(table_path),
            "worklist_csv": str(csv_path),
            "oa_refresh_dois": str(refresh_path),
            "oa_retrieval_dois": str(retrieval_path),
            "local_pdf_conversion_dois": str(conversion_path),
            "fulltext_reextraction_ready_dois": str(reextract_path),
        },
        "replacement_safety": {
            "active_graph_modified": False,
            "promotion_allowed_before_fulltext_extraction": False,
            "required_update_workflow": "run_scoped_paper_update.py prepare -> fulltext extraction -> finalize -> promote",
            "scope_semantics": "remove old abstract-derived DOI evidence and add validated current fulltext-derived DOI evidence atomically",
        },
    }
    report_path = output_dir / "historical_fulltext_backfill_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--active-extraction-pointer", default=str(DEFAULT_ACTIVE_EXTRACTION_POINTER))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--doi-alias-registry", default=str(DEFAULT_DOI_ALIAS_REGISTRY))
    parser.add_argument("--manual-fulltext-access-overrides", default=str(DEFAULT_ACCESS_OVERRIDES))
    parser.add_argument("--oa-refresh-report", default="")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


if __name__ == "__main__":
    print(json.dumps(build(parse_args())["counts"], indent=2))
