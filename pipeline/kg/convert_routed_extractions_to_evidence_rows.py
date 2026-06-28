#!/usr/bin/env python3
"""Convert routed extraction outputs into KG evidence rows.

The route extraction runner writes one parsed JSON object per paper task. This
script turns those paper-level objects into one flat row per extracted evidence
item so `pipeline/kg/build_evidence_tables.py` can build the normalized KG
tables from them.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

try:
    from pipeline.extract.extraction_v1_utils import normalize, read_jsonl, write_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.extraction_v1_utils import normalize, read_jsonl, write_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXTRACTION_DIR = ROOT / "data" / "processed" / "extraction"
DEFAULT_INPUT_JSONL = DEFAULT_EXTRACTION_DIR / "route_extraction_outputs.jsonl"
DEFAULT_TASKS_JSONL = DEFAULT_EXTRACTION_DIR / "route_extraction_tasks.jsonl"
DEFAULT_OUT_JSON = DEFAULT_EXTRACTION_DIR / "routed_evidence_rows.json"
DEFAULT_REPORT_JSON = DEFAULT_EXTRACTION_DIR / "routed_evidence_rows_report.json"
DEFAULT_ROUTED_RUN_ROOT = DEFAULT_EXTRACTION_DIR / "routed_runs"

ROUTE_OUTPUT_SCHEMA_VERSION = "routed_evidence_rows_v1"
EXTRACTABLE_STATUSES = {"extracted"}
MISSING_VALUES = {
    "",
    "not_reported",
    "not reported",
    "not_applicable",
    "not applicable",
    "none",
    "n/a",
    "na",
    "unknown",
    "uncertain",
}

PAPER_METADATA_FIELDS = (
    "study_doi",
    "doi",
    "pmid",
    "pmcid",
    "openalex_id",
    "study_title",
    "title",
    "study_year",
    "year",
    "authors",
    "study_journal",
    "journal",
    "publication_type",
    "publication_date",
    "publisher",
    "journal_issn",
    "journal_eissn",
    "language",
    "mesh_terms",
    "keywords",
    "funders",
    "grant_ids",
    "trial_registry_ids",
    "funding",
    "conflicts_of_interest",
    "risk_of_bias_summary",
    "open_access_status",
    "open_access_url",
)

COMPOUND_FIELDS = (
    "compound",
    "canonical_compound",
    "compound_or_class",
    "compound_or_exposure",
    "compound_or_intervention",
    "compound_or_analyte",
    "intervention_or_exposure",
    "exposure_or_intervention",
    "exposure_or_policy",
)

ENTITY_KIND_ALIASES = {
    "condition": "condition_indication",
    "disorder": "condition_indication",
    "clinical_condition": "condition_indication",
    "clinical_indication": "condition_indication",
    "symptom": "symptom_problem",
    "symptom_or_outcome": "symptom_problem",
    "safety_event": "safety_adverse_event",
    "adverse_event": "safety_adverse_event",
    "molecular_readout": "biomarker_readout",
    "brain_readout": "biomarker_readout",
    "neural_readout": "biomarker_readout",
    "pk_parameter": "pharmacokinetic_parameter",
    "pk_or_exposure_parameter": "pharmacokinetic_parameter",
}

DOMAIN_DEFAULT_ENTITY_KIND = {
    "clinical_outcome": "condition_indication",
    "safety_tolerability": "safety_adverse_event",
    "molecular_target": "target",
    "molecular_pathway_readout": "pathway_process",
    "brain_system": "brain_network",
    "cognitive_behavioral": "cognitive_behavioral_construct",
    "subjective_experience": "subjective_experience_construct",
    "pharmacokinetics_exposure": "pharmacokinetic_parameter",
    "intervention_context": "intervention_component",
    "real_world_public_health": "public_health_measure",
}

ENTITY_LABEL_FIELDS_BY_KIND = {
    "condition_indication": ("entity", "condition_or_population", "population_or_system"),
    "symptom_problem": ("entity", "clinical_endpoint", "outcome_or_endpoint"),
    "safety_adverse_event": ("entity", "safety_event_or_measure", "safety_category"),
    "outcome_scale": ("entity", "outcome_measure", "outcome_measure_or_instrument"),
    "target": ("target", "metabolic_or_transport_target", "entity"),
    "pathway_process": ("pathway_or_process", "pathway_or_readout", "metabolic_or_transport_pathway", "entity"),
    "biomarker_readout": ("readout_or_biomarker", "readout_or_measure", "readout", "outcome_measure", "entity"),
    "brain_region": ("brain_region", "entity"),
    "brain_network": ("brain_network", "entity"),
    "neural_circuit": ("neural_circuit", "connectivity_or_circuit_relationship", "entity"),
    "cognitive_behavioral_construct": ("construct_or_behavior", "behavior_or_task", "task_or_measure", "entity"),
    "subjective_experience_construct": ("subjective_construct", "subjective_construct_category", "entity"),
    "pharmacokinetic_parameter": ("pk_or_exposure_parameter", "entity"),
    "compound": ("metabolite_or_analyte", "compound_or_analyte", "entity"),
    "intervention_component": ("context_component", "component_type", "intervention_model_or_orientation", "entity"),
    "public_health_measure": ("public_health_measure", "public_health_topic_category", "entity"),
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def safe_run_id(value: object) -> str:
    text = normalize(value)
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._-")
    return text


def resolve_run_dir(run_id: str, run_dir: str) -> Path | None:
    if normalize(run_dir):
        return Path(run_dir)
    resolved_run_id = safe_run_id(run_id)
    if resolved_run_id:
        return DEFAULT_ROUTED_RUN_ROOT / resolved_run_id
    return None


def resolve_output_paths(args: argparse.Namespace) -> argparse.Namespace:
    run_dir = resolve_run_dir(args.run_id, args.run_dir)
    if run_dir is not None:
        args.run_dir = str(run_dir)
        args.run_id = safe_run_id(args.run_id) or run_dir.name
        args.out_json = Path(args.out_json) if args.out_json else run_dir / "routed_evidence_rows.json"
        args.report_json = Path(args.report_json) if args.report_json else run_dir / "routed_evidence_rows_report.json"
        return args
    args.run_dir = ""
    args.run_id = safe_run_id(args.run_id)
    args.out_json = Path(args.out_json) if args.out_json else DEFAULT_OUT_JSON
    args.report_json = Path(args.report_json) if args.report_json else DEFAULT_REPORT_JSON
    return args


def meaningful(value: object) -> bool:
    return normalize(value).casefold() not in MISSING_VALUES


def cleaned_value(value: object) -> object:
    if isinstance(value, str) and not meaningful(value):
        return ""
    return value


def first_meaningful(row: dict, fields: Iterable[str]) -> str:
    for field in fields:
        value = normalize(row.get(field, ""))
        if meaningful(value):
            return value
    return ""


def normalized_entity_kind(value: object) -> str:
    key = normalize(value).casefold().replace("-", "_").replace(" ", "_")
    return ENTITY_KIND_ALIASES.get(key, key)


def compact_flat_fields(source: dict) -> dict:
    out = {}
    for key, value in source.items():
        if isinstance(value, (dict, list)):
            continue
        out[key] = cleaned_value(value)
    return out


def merge_prefer_meaningful(target: dict, source: dict) -> None:
    for key, value in compact_flat_fields(source).items():
        if meaningful(value) or key not in target:
            target[key] = value


def normalized_metadata(metadata: dict) -> dict:
    out = {}
    for field in PAPER_METADATA_FIELDS:
        value = cleaned_value(metadata.get(field, ""))
        if meaningful(value):
            out[field] = value
    if "study_doi" not in out and meaningful(out.get("doi", "")):
        out["study_doi"] = out["doi"]
    if "study_title" not in out and meaningful(out.get("title", "")):
        out["study_title"] = out["title"]
    if "study_year" not in out and meaningful(out.get("year", "")):
        out["study_year"] = out["year"]
    if "study_journal" not in out and meaningful(out.get("journal", "")):
        out["study_journal"] = out["journal"]
    return out


def task_lookup(tasks_jsonl: Path) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for task in read_jsonl(tasks_jsonl):
        metadata = task.get("paper_metadata", {}) if isinstance(task.get("paper_metadata"), dict) else {}
        values = normalized_metadata(metadata)
        if meaningful(task.get("study_doi", "")):
            values.setdefault("study_doi", normalize(task.get("study_doi", "")))
        keys = {
            normalize(task.get("task_id", "")),
            normalize(task.get("route_id", "")),
            normalize(task.get("study_doi", "")),
            normalize(metadata.get("doi", "")),
        }
        for key in keys:
            if key:
                lookup.setdefault(key, values)
    return lookup


def metadata_for_output_row(output_row: dict, result: dict, tasks: dict[str, dict]) -> dict:
    keys = (
        normalize(output_row.get("task_id", "")),
        normalize(output_row.get("route_id", "")),
        normalize(result.get("task_id", "")),
        normalize(result.get("route_id", "")),
        normalize(result.get("study_doi", "")),
    )
    for key in keys:
        if key and key in tasks:
            return dict(tasks[key])
    return {}


def result_items(result: dict) -> tuple[str, list[dict]]:
    if isinstance(result.get("items"), list):
        return "primary_item", [item for item in result["items"] if isinstance(item, dict)]
    if isinstance(result.get("synthesis_results"), list):
        return "synthesis_result", [item for item in result["synthesis_results"] if isinstance(item, dict)]
    if isinstance(result.get("coverage_items"), list):
        return "review_coverage_item", [item for item in result["coverage_items"] if isinstance(item, dict)]
    if isinstance(result.get("evidence_items"), list):
        return "primary_item", [item for item in result["evidence_items"] if isinstance(item, dict)]
    return "unknown", []


def source_family_for(item_kind: str) -> str:
    if item_kind == "primary_item":
        return "primary_study"
    return "secondary_literature"


def paper_assessment_route_for(item_kind: str) -> str:
    if item_kind == "primary_item":
        return "primary_evidence"
    return "secondary_literature"


def paper_type_for(result: dict, item_kind: str) -> str:
    if item_kind == "primary_item":
        return normalize(result.get("paper_type", "")) or "primary_study"
    source_type = normalize(result.get("source_type", ""))
    if item_kind == "synthesis_result":
        return source_type or "meta_analysis"
    return source_type or "review"


def infer_entity_kind(row: dict, domain: str) -> str:
    for field in ("primary_graph_anchor_kind", "kg_entity_kind_override", "graph_candidate_type", "graph_entity_type", "entity_type"):
        kind = normalized_entity_kind(row.get(field, ""))
        if meaningful(kind) and kind not in {"not_applicable", "uncertain"}:
            return kind
    if domain == "clinical_outcome" and not meaningful(row.get("condition_or_population", "")) and meaningful(row.get("clinical_endpoint", "")):
        return "symptom_problem"
    return DOMAIN_DEFAULT_ENTITY_KIND.get(domain, "condition_indication")


def infer_entity_label(row: dict, entity_kind: str) -> str:
    label = first_meaningful(row, ("graph_entity_label", "entity_label"))
    if label:
        return label
    label = first_meaningful(row, ENTITY_LABEL_FIELDS_BY_KIND.get(entity_kind, ()))
    if label:
        return label
    return first_meaningful(row, ("entity", "target", "disorder", "entity_or_endpoint", "outcome_or_endpoint"))


def add_common_field_aliases(row: dict) -> None:
    compound = first_meaningful(row, COMPOUND_FIELDS)
    if compound:
        row["compound"] = compound

    if not meaningful(row.get("supporting_quote", "")) and meaningful(row.get("evidence_quote", "")):
        row["supporting_quote"] = row["evidence_quote"]
    if not meaningful(row.get("support", "")):
        row["support"] = first_meaningful(
            row,
            (
                "finding_summary",
                "summary_statement",
                "authors_interpretation",
                "synthesis_interpretation",
                "review_interpretation",
            ),
        )
    if not meaningful(row.get("sample_size_total", "")):
        row["sample_size_total"] = first_meaningful(
            row,
            ("sample_size_total", "sample_size", "participant_count", "included_participant_count", "participant_or_sample_summary"),
        )
    if not meaningful(row.get("effect_size", "")):
        row["effect_size"] = first_meaningful(row, ("effect_size", "effect_or_statistic", "statistic_or_value", "value", "estimate_value"))
    if not meaningful(row.get("outcome_measure", "")):
        row["outcome_measure"] = first_meaningful(row, ("outcome_measure", "outcome_measure_or_instrument", "instrument_or_measure", "task_or_measure"))
    if not meaningful(row.get("result_direction", "")):
        row["result_direction"] = first_meaningful(row, ("result_direction", "direction_or_tone", "direction_or_change", "association_or_trend"))
    assessment_timepoint = first_meaningful(row, ("assessment_timepoint", "timepoint", "timepoint_or_window"))
    if assessment_timepoint:
        row["assessment_timepoint"] = assessment_timepoint
        row.setdefault("timepoint", assessment_timepoint)


def evidence_row_for_item(
    *,
    output_row: dict,
    result: dict,
    item: dict,
    item_kind: str,
    item_index: int,
    tasks: dict[str, dict],
) -> dict | None:
    domain = normalize(result.get("domain_route", "")) or normalize(item.get("relationship_domain", ""))
    if not domain:
        return None

    row = metadata_for_output_row(output_row, result, tasks)
    row.update(
        {
            "route_output_schema_version": ROUTE_OUTPUT_SCHEMA_VERSION,
            "task_id": normalize(result.get("task_id", "")) or normalize(output_row.get("task_id", "")),
            "route_id": normalize(result.get("route_id", "")) or normalize(output_row.get("route_id", "")),
            "study_doi": normalize(result.get("study_doi", "")) or normalize(row.get("study_doi", "")),
            "domain": domain,
            "domain_route": domain,
            "dataset": domain,
            "source_type": normalize(result.get("source_type", "")),
            "source_family": source_family_for(item_kind),
            "paper_type": paper_type_for(result, item_kind),
            "paper_assessment_route": paper_assessment_route_for(item_kind),
            "access_level": normalize(result.get("text_depth", "")),
            "text_depth": normalize(result.get("text_depth", "")),
            "source_item_type": item_kind,
            "source_item_index": item_index,
            "source_result_status": normalize(result.get("extraction_status", "")),
        }
    )
    merge_prefer_meaningful(row, item)
    domain_result = item.get("domain_result", {}) if isinstance(item.get("domain_result"), dict) else {}
    merge_prefer_meaningful(row, domain_result)
    add_common_field_aliases(row)

    entity_kind = infer_entity_kind(row, domain)
    entity_label = infer_entity_label(row, entity_kind)
    if not meaningful(row.get("compound", "")) or not meaningful(entity_label):
        return None
    row["kg_entity_kind_override"] = entity_kind
    row["graph_entity_label"] = entity_label
    return {key: cleaned_value(value) for key, value in row.items()}


def convert_outputs(
    *,
    input_jsonl: Path,
    tasks_jsonl: Path = DEFAULT_TASKS_JSONL,
    include_schema_errors: bool = False,
) -> tuple[list[dict], dict]:
    tasks = task_lookup(tasks_jsonl)
    out: list[dict] = []
    report_counts: Counter = Counter()
    skipped: Counter = Counter()

    for output_row in read_jsonl(input_jsonl):
        report_counts["output_rows_read"] += 1
        status = normalize(output_row.get("status", ""))
        if status != "ok" and not (include_schema_errors and status == "schema_error"):
            skipped[f"runner_status:{status or 'missing'}"] += 1
            continue
        result = output_row.get("result", {}) if isinstance(output_row.get("result"), dict) else {}
        if not result:
            skipped["missing_result"] += 1
            continue
        extraction_status = normalize(result.get("extraction_status", ""))
        if extraction_status not in EXTRACTABLE_STATUSES:
            skipped[f"extraction_status:{extraction_status or 'missing'}"] += 1
            continue

        item_kind, items = result_items(result)
        report_counts[f"{item_kind}_objects_seen"] += len(items)
        for item_index, item in enumerate(items, start=1):
            row = evidence_row_for_item(
                output_row=output_row,
                result=result,
                item=item,
                item_kind=item_kind,
                item_index=item_index,
                tasks=tasks,
            )
            if row:
                out.append(row)
            else:
                skipped["missing_compound_or_entity_label"] += 1

    report = {
        "generated_at_utc": now_utc(),
        "schema_version": "routed_evidence_rows_report_v1",
        "inputs": {
            "input_jsonl": str(input_jsonl),
            "tasks_jsonl": str(tasks_jsonl),
            "include_schema_errors": include_schema_errors,
        },
        "rows_written": len(out),
        "counts": dict(report_counts),
        "skipped": dict(skipped),
        "rows_by_domain": dict(Counter(row.get("domain_route", "") for row in out)),
        "rows_by_source_item_type": dict(Counter(row.get("source_item_type", "") for row in out)),
        "rows_by_entity_kind": dict(Counter(row.get("kg_entity_kind_override", "") for row in out)),
    }
    return out, report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-jsonl", type=Path, default=DEFAULT_INPUT_JSONL)
    parser.add_argument("--tasks-jsonl", type=Path, default=DEFAULT_TASKS_JSONL)
    parser.add_argument("--run-id", default="", help="Version label for routed extraction outputs.")
    parser.add_argument("--run-dir", default="", help="Explicit routed extraction run directory.")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--report-json", default="")
    parser.add_argument(
        "--include-schema-errors",
        action="store_true",
        help="Also convert parsed rows whose runner status was schema_error.",
    )
    return resolve_output_paths(parser.parse_args())


def main() -> int:
    args = parse_args()
    rows, report = convert_outputs(
        input_jsonl=args.input_jsonl,
        tasks_jsonl=args.tasks_jsonl,
        include_schema_errors=args.include_schema_errors,
    )
    report["run_id"] = args.run_id
    report["run_dir"] = args.run_dir
    report["outputs"] = {
        "out_json": str(args.out_json),
        "report_json": str(args.report_json),
    }
    write_json(args.out_json, rows)
    write_json(args.report_json, report)
    print(f"wrote {len(rows)} evidence rows -> {args.out_json}")
    print(f"report -> {args.report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
