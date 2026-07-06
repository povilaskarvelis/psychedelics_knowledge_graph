#!/usr/bin/env python3
"""Build deterministic domain routing from retained pre-screen decisions."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
import datetime as dt
import json
from pathlib import Path
import re
import sys
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.review.run_deterministic_prescreen import (  # noqa: E402
    DEFAULT_DECISIONS_TABLE,
    DEFAULT_METADATA_TABLE,
    clean,
    join_values,
    normalize_doi,
    read_doi_file,
)


DEFAULT_OUTPUT_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_domain_routing.parquet"
DEFAULT_SUMMARY_JSON = ROOT / "data" / "processed" / "corpus" / "paper_domain_routing_summary.json"
DEFAULT_COUNTS_CSV = ROOT / "data" / "processed" / "corpus" / "paper_domain_routing_counts.csv"
TABLE_VERSION = "0.1"
GENERAL_DOMAIN_ROUTE = "general_topic"

DOMAIN_TAG_TO_ROUTE = {
    "clinical_outcome": "clinical_outcome",
    "safety": "safety_tolerability",
    "molecular_target": "molecular_target",
    "molecular_pathway": "molecular_pathway_readout",
    "brain_system": "brain_system",
    "cognitive_behavioral": "cognitive_behavioral",
    "subjective_experience": "subjective_experience",
    "pharmacokinetics_exposure": "pharmacokinetics_exposure",
    "intervention_context": "intervention_context",
    "real_world_use_public_health": "real_world_public_health",
}
DOMAIN_TAG_ORDER = (
    "clinical_outcome",
    "safety",
    "molecular_target",
    "molecular_pathway",
    "brain_system",
    "cognitive_behavioral",
    "subjective_experience",
    "pharmacokinetics_exposure",
    "intervention_context",
    "real_world_use_public_health",
    "bridge_clinical_mechanism",
    "uncertain",
)
DOMAIN_ROUTE_ORDER = tuple(DOMAIN_TAG_TO_ROUTE[tag] for tag in DOMAIN_TAG_ORDER if tag in DOMAIN_TAG_TO_ROUTE) + (
    GENERAL_DOMAIN_ROUTE,
)
DOMAIN_TAG_ALIASES = {
    "pathway_biomarker": "molecular_pathway",
    "clinical": "clinical_outcome",
    "clinical_evidence": "clinical_outcome",
    "public_health": "real_world_use_public_health",
}
TAG_SOURCE_FIELDS = (
    "deterministic_routing_tags",
    "routing_tags",
    "context_routing_tags",
)
STRICT_DOMAIN_SUPPORT_PATTERNS = {
    "subjective_experience": re.compile(
        r"\b(?:subjective(?: drug)? effects?|mystical(?:-type)? experience|MEQ(?:-?30)?|"
        r"challenging experience|ego[-\s]?dissolution|altered states?(?: of consciousness)?|"
        r"hallucinat\w+|visual analog(?:ue)? scale|VAS|5D[-\s]?ASC|11D[-\s]?ASC|5D[-\s]?OAV|"
        r"hallucinogen rating scale|drug effects questionnaire|emotional breakthrough|"
        r"psychological insight|connectedness|oceanic boundlessness|peak experience|"
        r"phenomenolog\w+|perceptual effects?|visual effects?)\b",
        re.I,
    ),
    "pharmacokinetics_exposure": re.compile(
        r"\b(?:pharmacokinetic\w*|pharmacodynamic\w*|PK/PD|ADME|AUC|Cmax|Tmax|half[-\s]?life|"
        r"bioavailability|plasma (?:concentration|level)|serum (?:concentration|level)|"
        r"blood (?:concentration|level)|concentration[-\s]?time|metabolite\w*|metabolism of|"
        r"drug metabolism|metabolic profile|clearance|dose[-\s]?response|exposure[-\s]?response|urinary excretion|"
        r"route of administration)\b",
        re.I,
    ),
    "intervention_context": re.compile(
        r"\b(?:psychedelic[-\s]?assisted|MDMA[-\s]?assisted|ketamine[-\s]?assisted|"
        r"psychotherapy|preparation session|preparation and integration|integration (?:session|therapy)|"
        r"set and setting|set setting|therapist\w*|facilitator\w*|dosing session|"
        r"group therapy|psychological support|supportive therapy|manuali[sz]ed therapy|"
        r"treatment manual|music playlist|eye ?shades|therapeutic alliance|"
        r"therapeutic relationship)\b",
        re.I,
    ),
    "real_world_use_public_health": re.compile(
        r"\b(?:survey|epidemiolog\w*|prevalence|lifetime use|past[-\s]?year use|"
        r"non[-\s]?medical use|nonmedical use|recreational use|harm reduction|"
        r"drug checking|poison (?:center|control)|emergency department|emergency room|"
        r"hospitali[sz]ation|retreat|naturalistic|real[-\s]?world|self[-\s]?medication|"
        r"microdos(?:e|ing)|use patterns|public health|adverse experiences|ceremonial|"
        r"misuse|diversion)\b",
        re.I,
    ),
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def write_table(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, engine="pyarrow", index=False)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_counts_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["count_type", "value", "count"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def split_values(value: object) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for part in re.split(r"\s*[|,;]\s*", clean(value)):
        if part and part not in seen:
            seen.add(part)
            out.append(part)
    return out


def metadata_context_by_doi(metadata_df: pd.DataFrame) -> dict[str, str]:
    if metadata_df.empty or "doi" not in metadata_df.columns:
        return {}
    out: dict[str, str] = {}
    for row in metadata_df.to_dict("records"):
        doi = normalize_doi(clean(row.get("doi", "")))
        if not doi:
            continue
        text = " ".join(
            clean(row.get(field, ""))
            for field in ("study_title", "abstract", "mesh_terms", "keywords", "publication_type")
        )
        out[doi] = text
    return out


def normalize_domain_tag(value: object) -> str:
    tag = clean(value).lower().replace("-", "_").replace(" ", "_")
    return DOMAIN_TAG_ALIASES.get(tag, tag)


def normalize_domain_tags(values: Iterable[object]) -> list[str]:
    requested = {normalize_domain_tag(value) for value in values}
    out = [tag for tag in DOMAIN_TAG_ORDER if tag in requested]
    out.extend(sorted(tag for tag in requested if tag and tag not in DOMAIN_TAG_ORDER))
    return out


def retained(row: dict) -> bool:
    if clean(row.get("prescreen_decision", "")) == "retain":
        return True
    value = row.get("retained_for_extraction_candidate", False)
    if isinstance(value, bool):
        return value
    return clean(value).lower() in {"1", "true", "yes", "y"}


def source_confidence(source_fields: Iterable[str], fallback: bool = False) -> str:
    sources = set(source_fields)
    if fallback:
        return "low"
    if "deterministic_routing_tags" in sources or "routing_tags" in sources:
        return "medium"
    if "context_routing_tags" in sources:
        return "low"
    return "low"


def source_basis(tag: str, source_fields: Iterable[str], fallback: bool = False) -> str:
    if fallback:
        return "no domain-specific title/abstract tag; use general extraction coverage"
    sources = sorted(set(source_fields))
    if not sources:
        return f"domain tag:{tag}"
    return f"domain tag:{tag} | source fields:{'|'.join(sources)}"


def domain_tag_supported(tag: str, metadata_context: str) -> bool:
    pattern = STRICT_DOMAIN_SUPPORT_PATTERNS.get(tag)
    if pattern is None or not clean(metadata_context):
        return True
    return bool(pattern.search(metadata_context))


def aggregate_decision_context(decisions_df: pd.DataFrame, *, scoped_dois: set[str] | None = None) -> dict[str, dict]:
    out: dict[str, dict] = defaultdict(
        lambda: {
            "prescreen_actions": [],
            "run_ids": [],
            "study_title": "",
            "study_year": "",
            "source_row_count": 0,
            "all_tags": [],
            "tag_sources": defaultdict(list),
        }
    )
    scoped_dois = scoped_dois or set()
    if decisions_df.empty or "doi" not in decisions_df.columns:
        return {}

    for row in decisions_df.to_dict("records"):
        doi = normalize_doi(clean(row.get("doi", "")))
        if not doi or (scoped_dois and doi not in scoped_dois):
            continue
        if not retained(row):
            continue

        entry = out[doi]
        entry["source_row_count"] += 1
        for source_field, target in (
            ("prescreen_action", "prescreen_actions"),
            ("run_id", "run_ids"),
        ):
            value = clean(row.get(source_field, ""))
            if value and value not in entry[target]:
                entry[target].append(value)
        if not entry["study_title"]:
            entry["study_title"] = clean(row.get("study_title", ""))
        if not entry["study_year"]:
            entry["study_year"] = clean(row.get("study_year", ""))

        for source_field in TAG_SOURCE_FIELDS:
            for tag in normalize_domain_tags(split_values(row.get(source_field, ""))):
                if tag not in DOMAIN_TAG_ORDER:
                    continue
                if tag not in entry["all_tags"]:
                    entry["all_tags"].append(tag)
                if source_field not in entry["tag_sources"][tag]:
                    entry["tag_sources"][tag].append(source_field)

    return dict(out)


def build_rows(
    decisions_df: pd.DataFrame,
    metadata_df: pd.DataFrame | None = None,
    *,
    generated_at_utc: str,
    scoped_dois: set[str] | None = None,
) -> list[dict]:
    contexts = aggregate_decision_context(decisions_df, scoped_dois=scoped_dois)
    metadata_contexts = metadata_context_by_doi(metadata_df if metadata_df is not None else pd.DataFrame())
    rows: list[dict] = []
    for doi, context in contexts.items():
        all_tags = normalize_domain_tags(context["all_tags"])
        metadata_context = metadata_contexts.get(doi, "")
        route_tags = [
            tag
            for tag in all_tags
            if tag in DOMAIN_TAG_TO_ROUTE and domain_tag_supported(tag, metadata_context)
        ]
        bridge = "bridge_clinical_mechanism" in all_tags
        row_common = {
            "table_version": TABLE_VERSION,
            "generated_at_utc": generated_at_utc,
            "doi": doi,
            "retained_for_extraction_candidate": True,
            "study_title": clean(context["study_title"]),
            "study_year": clean(context["study_year"]),
            "prescreen_actions": join_values(context["prescreen_actions"]),
            "prescreen_run_ids": join_values(context["run_ids"]),
            "all_domain_tags": join_values(all_tags),
            "bridge_clinical_mechanism": bridge,
            "source_row_count": int(context["source_row_count"]),
        }
        if not route_tags:
            rows.append(
                {
                    **row_common,
                    "domain_route": GENERAL_DOMAIN_ROUTE,
                    "domain_tag": "",
                    "domain_route_confidence": source_confidence([], fallback=True),
                    "domain_route_basis": source_basis("", [], fallback=True),
                    "tag_source_fields": "",
                }
            )
            continue
        for tag in route_tags:
            sources = context["tag_sources"].get(tag, [])
            rows.append(
                {
                    **row_common,
                    "domain_route": DOMAIN_TAG_TO_ROUTE[tag],
                    "domain_tag": tag,
                    "domain_route_confidence": source_confidence(sources),
                    "domain_route_basis": source_basis(tag, sources),
                    "tag_source_fields": join_values(sources),
                }
            )

    route_rank = {route: rank for rank, route in enumerate(DOMAIN_ROUTE_ORDER)}
    rows.sort(key=lambda row: (row["doi"], route_rank.get(row["domain_route"], 999), row["domain_route"]))
    return rows


def count_rows(rows: list[dict], field: str) -> Counter:
    return Counter(clean(row.get(field, "")) or "<blank>" for row in rows)


def build_summary(rows: list[dict], *, inputs: dict) -> tuple[dict, list[dict]]:
    routed_dois = {row["doi"] for row in rows}
    fallback_dois = {row["doi"] for row in rows if row.get("domain_route") == GENERAL_DOMAIN_ROUTE}
    summary = {
        "generated_at_utc": now_utc(),
        "table_version": TABLE_VERSION,
        "inputs": inputs,
        "route_rows": len(rows),
        "routed_dois": len(routed_dois),
        "fallback_general_topic_dois": len(fallback_dois),
        "by_domain_route": dict(count_rows(rows, "domain_route")),
        "by_domain_tag": dict(count_rows(rows, "domain_tag")),
        "by_confidence": dict(count_rows(rows, "domain_route_confidence")),
    }
    counts: list[dict] = []
    for count_type, values in (
        ("domain_route", summary["by_domain_route"]),
        ("domain_tag", summary["by_domain_tag"]),
        ("domain_route_confidence", summary["by_confidence"]),
    ):
        for value, count in sorted(values.items()):
            counts.append({"count_type": count_type, "value": value, "count": count})
    return summary, counts


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build deterministic domain routing from retained pre-screen rows.")
    parser.add_argument("--prescreen-decisions-table", default=str(DEFAULT_DECISIONS_TABLE))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--output-table", default=str(DEFAULT_OUTPUT_TABLE))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY_JSON))
    parser.add_argument("--counts-csv", default=str(DEFAULT_COUNTS_CSV))
    parser.add_argument("--doi-file", default="", help="Optional DOI list for scoped domain routing.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    prescreen_table = Path(args.prescreen_decisions_table).resolve()
    metadata_table = Path(args.metadata_table).resolve()
    scoped_dois = read_doi_file(Path(args.doi_file).resolve()) if clean(args.doi_file) else set()
    decisions_df = read_table(prescreen_table)
    metadata_df = read_table(metadata_table)
    generated_at_utc = now_utc()
    rows = build_rows(decisions_df, metadata_df, generated_at_utc=generated_at_utc, scoped_dois=scoped_dois)

    output_table = Path(args.output_table).resolve()
    summary_json = Path(args.summary_json).resolve()
    counts_csv = Path(args.counts_csv).resolve()
    write_table(output_table, rows)
    summary, counts = build_summary(
        rows,
        inputs={
            "prescreen_decisions_table": str(prescreen_table),
            "metadata_table": str(metadata_table),
            "doi_file": str(Path(args.doi_file).resolve()) if clean(args.doi_file) else "",
            "scoped_dois": len(scoped_dois),
        },
    )
    write_json(summary_json, summary)
    write_counts_csv(counts_csv, counts)

    print(f"Domain route rows: {summary['route_rows']:,}")
    print(f"Routed DOIs: {summary['routed_dois']:,}")
    print(f"Fallback general-topic DOIs: {summary['fallback_general_topic_dois']:,}")
    print(f"By domain route: {summary['by_domain_route']}")
    print(f"Domain routing table: {output_table}")
    print(f"Summary: {summary_json}")
    print(f"Counts: {counts_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
