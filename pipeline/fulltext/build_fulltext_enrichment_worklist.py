#!/usr/bin/env python3
"""Build the route-independent post-screen full-text enrichment worklist."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.extract.build_extraction_routes import (  # noqa: E402
    CANONICAL_FULLTEXT_ARTICLE_DIR,
    DEFAULT_CANDIDATE_TABLE,
    DEFAULT_DOMAIN_ROUTING_TABLE,
    DEFAULT_FULLTEXT_DIR,
    DEFAULT_MANUAL_FULLTEXT_ACCESS_OVERRIDES,
    DEFAULT_MANUAL_ROUTE_OVERRIDES,
    DEFAULT_METADATA_TABLE,
    DEFAULT_PAPER_ROOT,
    DEFAULT_SCREENING_DECISION_OVERRIDES,
    apply_fulltext_access_override,
    build_local_pdf_index,
    fulltext_status_for_doi,
    load_manual_fulltext_access_overrides,
    load_manual_route_overrides,
    load_screening_decision_overrides,
    local_pdf_status_for_doi,
    merged_extraction_metadata,
    metadata_other_url_candidates,
    metadata_pdf_url_candidates,
    metadata_probable_pdf_url_candidates,
    source_status_from_domain_rows,
)
from pipeline.fulltext.convert_pdfs import normalize_doi  # noqa: E402
from pipeline.fulltext.source_identity_audit_gate import (  # noqa: E402
    DEFAULT_SOURCE_IDENTITY_AUDIT,
    SourceIdentityAuditGate,
)
from pipeline.ingest.metadata_utils import (  # noqa: E402
    extract_pmcid_from_url,
    split_candidates,
    status_is_open,
)
from pipeline.validate.doi_aliases import (  # noqa: E402
    DEFAULT_DOI_ALIAS_REGISTRY,
    active_doi_aliases,
    load_doi_aliases,
)


DEFAULT_QUEUE = ROOT / "data" / "processed" / "corpus" / "paper_domain_routing_gemini_batch_queue.json"
DEFAULT_ACTIVE_GRAPH = ROOT / "data" / "processed" / "graph_payload_active.json"
DEFAULT_SELECTED_DOIS = ROOT / "data" / "processed" / "corpus" / "postscreen_selected_dois.txt"
DEFAULT_ENRICHMENT_DOIS = ROOT / "data" / "processed" / "corpus" / "fulltext_enrichment_dois.txt"
DEFAULT_DISCOVERY_DOIS = ROOT / "data" / "processed" / "corpus" / "fulltext_link_discovery_dois.txt"
DEFAULT_OA_LANDING_DOIS = ROOT / "data" / "processed" / "corpus" / "fulltext_oa_landing_dois.txt"
DEFAULT_WORKLIST = ROOT / "data" / "processed" / "corpus" / "fulltext_enrichment_worklist.parquet"
DEFAULT_REPORT = ROOT / "data" / "processed" / "corpus" / "fulltext_enrichment_worklist_report.json"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).lower() in {"1", "true", "yes", "y", "include", "retain"}


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def newly_included_dois(queue: dict) -> set[str]:
    out: set[str] = set()
    for part in queue.get("parts", []):
        raw_path = Path(part["raw_jsonl"]).resolve()
        with raw_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                if clean(row.get("parsed", {}).get("screening_decision", "")) != "include_in_scope":
                    continue
                doi = normalize_doi(row.get("doi", ""))
                if doi:
                    out.add(doi)
    return out


def previously_processed_dois(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    frame = pd.read_parquet(path)
    if frame.empty or "doi" not in frame.columns:
        return set()
    processed = pd.Series(False, index=frame.index)
    if "retained_for_extraction_candidate" in frame.columns:
        processed |= frame["retained_for_extraction_candidate"].map(truthy)
    if "retained_extraction_route_count" in frame.columns:
        processed |= pd.to_numeric(frame["retained_extraction_route_count"], errors="coerce").fillna(0).gt(0)
    if "graph_inclusion_status" in frame.columns:
        processed |= ~frame["graph_inclusion_status"].fillna("").astype(str).str.strip().isin({"", "not_reached"})
    return {normalize_doi(value) for value in frame.loc[processed, "doi"] if normalize_doi(value)}


def active_graph_dois(pointer: Path) -> set[str]:
    if not pointer.is_file():
        return set()
    payload = read_json(pointer)
    kg_dir = Path(clean(payload.get("kg_dir", "")))
    if not kg_dir.is_absolute():
        kg_dir = ROOT / kg_dir
    papers = kg_dir / "papers.parquet"
    if not papers.is_file():
        return set()
    frame = pd.read_parquet(papers)
    field = "doi" if "doi" in frame.columns else "study_doi"
    return {normalize_doi(value) for value in frame[field] if normalize_doi(value)}


def pmcid_from_metadata(row: dict) -> str:
    pmcid = clean(row.get("pmcid", "")).upper()
    if pmcid:
        return pmcid
    for field in ("best_pdf_url", "pdf_url_candidates", "open_access_url"):
        for candidate in split_candidates(row.get(field, "")):
            pmcid = extract_pmcid_from_url(candidate)
            if pmcid:
                return pmcid.upper()
    return ""


def load_pmc_outcomes(paths: Path | Iterable[Path] | None) -> dict[str, str]:
    """Load ordered PMC outcomes; later reports override earlier reports."""
    if paths is None:
        return {}
    report_paths = [paths] if isinstance(paths, Path) else list(paths)
    out: dict[str, str] = {}
    for path in report_paths:
        if not path.is_file():
            continue
        payload = read_json(path)
        for row in payload.get("records", []):
            if not isinstance(row, dict):
                continue
            doi = normalize_doi(row.get("doi", ""))
            status = clean(row.get("status", ""))
            if not doi:
                continue
            if status in {"not_available", "failed"}:
                out[doi] = status
            elif status.startswith("written"):
                out.pop(doi, None)
    return out


def screening_rows_by_doi(screening_df: pd.DataFrame) -> dict[str, list[dict]]:
    """Group model screening rows without requiring any topic-route fields."""
    out: dict[str, list[dict]] = defaultdict(list)
    if screening_df.empty or "doi" not in screening_df.columns:
        return {}
    for row in screening_df.to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        if doi:
            out[doi].append(row)
    return dict(out)


def extraction_eligibility_by_doi(
    screening_df: pd.DataFrame,
    metadata_by_doi: dict[str, dict],
    manual_overrides: dict[str, dict],
    screening_overrides: dict[str, dict],
) -> tuple[dict[str, dict], Counter[str]]:
    screening = screening_rows_by_doi(screening_df)
    decisions: dict[str, dict] = {}
    counts: Counter[str] = Counter()
    for doi, domain_rows in screening.items():
        first = domain_rows[0]
        if clean(first.get("screening_decision", "")) != "include_in_scope":
            continue
        manual = manual_overrides.get(doi, {})
        candidate_metadata = metadata_by_doi.get(doi, {})
        reason = ""
        selected = True
        if clean(candidate_metadata.get("post_retrieval_decision", "")).lower() == "exclude":
            selected = False
            reason = "post_retrieval_eligibility_exclusion"
        elif clean(screening_overrides.get(doi, {}).get("decision", "")) == "exclude_out_of_scope":
            selected = False
            reason = "curated_screening_exclusion"
        elif clean(manual.get("manual_action", "")) == "context_only":
            selected = False
            reason = "manual_context_only"
        else:
            source = source_status_from_domain_rows(
                domain_rows,
                metadata=metadata_by_doi.get(doi, {}),
                manual_override=manual,
            )
            if clean(source.get("source_family", "")) == "non_primary_publication":
                selected = False
                reason = "non_primary_publication"
        source = source_status_from_domain_rows(
            domain_rows,
            metadata=metadata_by_doi.get(doi, {}),
            manual_override=manual,
        )
        decisions[doi] = {
            "selected_for_downstream": selected,
            "selection_reason": reason or "screened_in_and_extraction_eligible",
            "screening_decision": clean(first.get("screening_decision", "")),
            "screening_reason": clean(first.get("screening_reason", "")),
            "screening_model": clean(first.get("model", "")),
            "source_family": clean(source.get("source_family", "")),
            "source_type": clean(source.get("source_type", "")),
            "paper_type": clean(first.get("paper_type", "")),
            "paper_type_group": clean(first.get("paper_type_group", "")),
        }
        counts[reason or "selected"] += 1
    return decisions, counts


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_parquet_atomic(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".parquet", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        frame.to_parquet(temporary, engine="pyarrow", index=False)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build(args: argparse.Namespace) -> dict:
    queue_path = Path(args.queue_json).resolve()
    queue = read_json(queue_path)
    candidate_path = Path(args.candidate_table).resolve()
    metadata_path = Path(args.metadata_table).resolve()
    screening_path = Path(args.screening_table).resolve()
    candidate_df = pd.read_parquet(candidate_path)
    metadata_df = merged_extraction_metadata(candidate_df, pd.read_parquet(metadata_path))
    metadata_map = {
        normalize_doi(row.get("doi", "")): row
        for row in metadata_df.to_dict("records")
        if normalize_doi(row.get("doi", ""))
    }
    manual_overrides = load_manual_route_overrides(Path(args.manual_eligibility_overrides).resolve())
    screening_overrides = load_screening_decision_overrides(Path(args.screening_decision_overrides).resolve())
    access_overrides = load_manual_fulltext_access_overrides(Path(args.manual_fulltext_access_overrides).resolve())
    raw_pmc_reports = getattr(args, "pmc_report", []) or []
    if isinstance(raw_pmc_reports, str):
        raw_pmc_reports = [raw_pmc_reports] if clean(raw_pmc_reports) else []
    pmc_report_paths = [Path(value).resolve() for value in raw_pmc_reports if clean(value)]
    pmc_outcomes = load_pmc_outcomes(pmc_report_paths)
    eligibility, eligibility_counts = extraction_eligibility_by_doi(
        pd.read_parquet(screening_path), metadata_map, manual_overrides, screening_overrides
    )

    new_included = newly_included_dois(queue)
    eligible = {doi for doi, row in eligibility.items() if row["selected_for_downstream"]}
    previous_path = Path(args.previous_candidate_table).resolve() if args.previous_candidate_table else Path(
        queue.get("inputs", {}).get("previous_candidate_table", "")
    ).resolve()
    processed = previously_processed_dois(previous_path) | active_graph_dois(Path(args.active_graph_pointer).resolve())
    selected_before_alias_dedup = new_included & eligible - processed
    alias_registry_path = Path(
        getattr(args, "doi_alias_registry", DEFAULT_DOI_ALIAS_REGISTRY)
    ).resolve()
    corpus_dois = set(metadata_map) | new_included | processed
    doi_aliases = active_doi_aliases(load_doi_aliases(alias_registry_path), corpus_dois)
    suppressed_aliases = {
        alias: canonical
        for alias, canonical in doi_aliases.items()
        if alias in selected_before_alias_dedup
    }
    selected = sorted(selected_before_alias_dedup - set(suppressed_aliases))

    fulltext_dir = Path(args.fulltext_dir).resolve()
    article_dir = fulltext_dir / CANONICAL_FULLTEXT_ARTICLE_DIR
    source_identity_audit = Path(args.source_identity_audit).resolve()
    source_gate = (
        SourceIdentityAuditGate(source_identity_audit)
        if article_dir.is_dir() and next(article_dir.glob("*.json"), None)
        else None
    )
    local_pdf_index = build_local_pdf_index(Path(args.paper_root).resolve())
    generated_at_utc = now_utc()
    rows: list[dict] = []
    for doi in selected:
        metadata = metadata_map.get(doi, {})
        access_override = access_overrides.get(doi, {})
        access_metadata = apply_fulltext_access_override(metadata, access_override)
        fulltext = fulltext_status_for_doi(
            doi,
            fulltext_dir,
            source_identity_gate=source_gate,
            source_identity_audit=source_identity_audit,
        )
        local_pdf = local_pdf_status_for_doi(doi, local_pdf_index)
        pmcid = pmcid_from_metadata(access_metadata)
        pmc_outcome = pmc_outcomes.get(doi, "")
        pdf_candidates = metadata_pdf_url_candidates(access_metadata)
        probable = metadata_probable_pdf_url_candidates(access_metadata)
        open_access_status = clean(access_metadata.get("open_access_status", ""))
        open_access_is_oa = clean(access_metadata.get("open_access_is_oa", ""))
        open_access_positive = truthy(open_access_is_oa) or status_is_open(open_access_status)
        pdf_url_quality = clean(access_metadata.get("pdf_url_quality", ""))
        manual_access_action = clean(access_override.get("manual_access_action", ""))
        if fulltext.get("has_converted_full_text"):
            action = "reuse_existing_fulltext"
            needed = False
        elif manual_access_action in {"abstract_only", "suppress_pdf_download"}:
            action = "use_abstract_only"
            needed = False
        elif local_pdf.get("has_local_pdf"):
            action = "convert_local_pdf"
            needed = True
        elif pmcid and not pmc_outcome:
            action = "fetch_pmc_xml"
            needed = True
        elif pdf_candidates:
            action = "download_known_pdf"
            needed = True
        elif open_access_positive:
            # OA metadata is useful retrieval evidence even when the provider
            # exposes only a landing page. Keep this tier separate from truly
            # route-less/closed records so DOI resolution can be scoped safely.
            action = "resolve_oa_landing_page"
            needed = True
        else:
            action = "discover_fulltext"
            needed = True
        decision = eligibility[doi]
        rows.append(
            {
                "table_version": "fulltext_enrichment_worklist_v1",
                "generated_at_utc": generated_at_utc,
                "doi": doi,
                "selected_for_downstream": True,
                "fulltext_enrichment_needed": needed,
                "fulltext_enrichment_action": action,
                **decision,
                "study_title": clean(metadata.get("study_title", "")),
                "study_year": clean(metadata.get("study_year", "")),
                "abstract": clean(metadata.get("abstract", "")),
                "pmid": clean(metadata.get("pmid", "")),
                "pmcid": pmcid,
                "pmc_fulltext_status": pmc_outcome,
                "open_access_is_oa": open_access_is_oa,
                "open_access_status": open_access_status,
                "open_access_url": clean(access_metadata.get("open_access_url", "")),
                "best_pdf_url": probable[0] if probable else pdf_candidates[0] if pdf_candidates else "",
                "pdf_url_candidates": "|".join(pdf_candidates),
                "probable_pdf_url_candidates": "|".join(probable),
                "other_url_candidates": "|".join(metadata_other_url_candidates(access_metadata)),
                "pdf_url_quality": pdf_url_quality,
                "has_converted_full_text": bool(fulltext.get("has_converted_full_text")),
                "fulltext_artifact_paths": clean(fulltext.get("fulltext_artifact_paths", "")),
                "has_local_pdf": bool(local_pdf.get("has_local_pdf")),
                "local_pdf_paths": clean(local_pdf.get("local_pdf_paths", "")),
                "manual_fulltext_access_action": manual_access_action,
                "manual_fulltext_access_reason": clean(access_override.get("manual_reason", "")),
            }
        )

    frame = pd.DataFrame(rows)
    selected_path = Path(args.output_selected_dois).resolve()
    enrichment_path = Path(args.output_enrichment_dois).resolve()
    discovery_path = Path(getattr(args, "output_discovery_dois", DEFAULT_DISCOVERY_DOIS)).resolve()
    oa_landing_path = Path(getattr(args, "output_oa_landing_dois", DEFAULT_OA_LANDING_DOIS)).resolve()
    table_path = Path(args.output_table).resolve()
    report_path = Path(args.report_json).resolve()
    enrichment_dois = frame.loc[frame["fulltext_enrichment_needed"], "doi"].tolist() if not frame.empty else []
    discovery_dois = (
        frame.loc[
            frame["fulltext_enrichment_action"].isin({"resolve_oa_landing_page", "discover_fulltext"}),
            "doi",
        ].tolist()
        if not frame.empty
        else []
    )
    oa_landing_dois = (
        frame.loc[frame["fulltext_enrichment_action"].eq("resolve_oa_landing_page"), "doi"].tolist()
        if not frame.empty
        else []
    )
    write_text_atomic(selected_path, "".join(f"{doi}\n" for doi in selected))
    write_text_atomic(enrichment_path, "".join(f"{doi}\n" for doi in enrichment_dois))
    write_text_atomic(discovery_path, "".join(f"{doi}\n" for doi in discovery_dois))
    write_text_atomic(oa_landing_path, "".join(f"{doi}\n" for doi in oa_landing_dois))
    write_parquet_atomic(table_path, frame)
    report = {
        "schema_version": "fulltext_enrichment_worklist_report_v1",
        "generated_at_utc": generated_at_utc,
        "inputs": {
            "queue_json": str(queue_path),
            "screening_table": str(screening_path),
            "candidate_table": str(candidate_path),
            "metadata_table": str(metadata_path),
            "previous_candidate_table": str(previous_path),
            "active_graph_pointer": str(Path(args.active_graph_pointer).resolve()),
            "manual_eligibility_overrides": str(Path(args.manual_eligibility_overrides).resolve()),
            "screening_decision_overrides": str(Path(args.screening_decision_overrides).resolve()),
            "doi_alias_registry": str(alias_registry_path),
            "pmc_reports": [str(path) for path in pmc_report_paths],
        },
        "outputs": {
            "selected_dois": str(selected_path),
            "enrichment_dois": str(enrichment_path),
            "link_discovery_dois": str(discovery_path),
            "oa_landing_dois": str(oa_landing_path),
            "worklist_table": str(table_path),
            "report_json": str(report_path),
        },
        "counts": {
            "newly_screened_included_dois": len(new_included),
            "newly_included_not_extraction_eligible": len(new_included - eligible),
            "newly_included_previously_processed": len(new_included & processed),
            "newly_selected_unprocessed_dois": len(selected),
            "newly_selected_duplicate_doi_aliases_suppressed": len(suppressed_aliases),
            "fulltext_enrichment_needed_dois": len(enrichment_dois),
            "fulltext_link_discovery_dois": len(discovery_dois),
            "fulltext_oa_landing_dois": len(oa_landing_dois),
            "fulltext_already_available_dois": int((frame["fulltext_enrichment_action"] == "reuse_existing_fulltext").sum()) if not frame.empty else 0,
        },
        "eligibility_counts_all_screened_in": dict(eligibility_counts),
        "by_fulltext_enrichment_action": dict(Counter(frame["fulltext_enrichment_action"])) if not frame.empty else {},
        "by_source_family": dict(Counter(frame["source_family"])) if not frame.empty else {},
        "previously_processed_examples": sorted(new_included & processed)[:50],
        "not_eligible_examples": sorted(new_included - eligible)[:50],
        "suppressed_doi_aliases": suppressed_aliases,
    }
    write_text_atomic(report_path, json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-json", default=str(DEFAULT_QUEUE))
    parser.add_argument("--screening-table", default=str(DEFAULT_DOMAIN_ROUTING_TABLE))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--previous-candidate-table", default="")
    parser.add_argument("--active-graph-pointer", default=str(DEFAULT_ACTIVE_GRAPH))
    parser.add_argument("--manual-eligibility-overrides", default=str(DEFAULT_MANUAL_ROUTE_OVERRIDES))
    parser.add_argument("--screening-decision-overrides", default=str(DEFAULT_SCREENING_DECISION_OVERRIDES))
    parser.add_argument("--manual-fulltext-access-overrides", default=str(DEFAULT_MANUAL_FULLTEXT_ACCESS_OVERRIDES))
    parser.add_argument("--doi-alias-registry", default=str(DEFAULT_DOI_ALIAS_REGISTRY))
    parser.add_argument(
        "--pmc-report",
        action="append",
        default=[],
        help="Completed PMC XML report. Repeat in chronological order for incremental runs.",
    )
    parser.add_argument("--fulltext-dir", default=str(DEFAULT_FULLTEXT_DIR))
    parser.add_argument("--source-identity-audit", default=str(DEFAULT_SOURCE_IDENTITY_AUDIT))
    parser.add_argument("--paper-root", default=str(DEFAULT_PAPER_ROOT))
    parser.add_argument("--output-selected-dois", default=str(DEFAULT_SELECTED_DOIS))
    parser.add_argument("--output-enrichment-dois", default=str(DEFAULT_ENRICHMENT_DOIS))
    parser.add_argument("--output-discovery-dois", default=str(DEFAULT_DISCOVERY_DOIS))
    parser.add_argument("--output-oa-landing-dois", default=str(DEFAULT_OA_LANDING_DOIS))
    parser.add_argument("--output-table", default=str(DEFAULT_WORKLIST))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT))
    return parser.parse_args()


if __name__ == "__main__":
    result = build(parse_args())
    print(json.dumps(result["counts"], indent=2))
