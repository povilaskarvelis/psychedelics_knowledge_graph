#!/usr/bin/env python3
"""Route papers by primary vs secondary literature type."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
from pathlib import Path
import re
import sys
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.review.run_deterministic_prescreen import (
    DEFAULT_DECISIONS_TABLE,
    DEFAULT_METADATA_TABLE,
    clean,
    clean_bool,
    join_values,
    normalize_doi,
    read_doi_file,
)


DEFAULT_OUTPUT_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_literature_type_routing.parquet"
TABLE_VERSION = "0.1"

SECONDARY_PRIORITY = (
    "network_meta_analysis",
    "meta_analysis",
    "umbrella_review",
    "systematic_review",
    "scoping_review",
    "narrative_review",
    "literature_review",
    "review",
    "guideline",
    "consensus_statement",
)
SPECIFIC_SECONDARY_PATTERNS = (
    ("network_meta_analysis", re.compile(r"\bnetwork meta[- ]analys(?:is|es)\b", re.I)),
    ("meta_analysis", re.compile(r"\bmeta[- ]analys(?:is|es)\b|\bmeta[- ]analytic\b|\bmeta[- ]regression\b", re.I)),
    ("umbrella_review", re.compile(r"\bumbrella review\b", re.I)),
    ("systematic_review", re.compile(r"\bsystematic review\b", re.I)),
    ("scoping_review", re.compile(r"\bscoping review\b", re.I)),
    ("narrative_review", re.compile(r"\bnarrative review\b", re.I)),
    ("literature_review", re.compile(r"\bliterature review\b", re.I)),
)
GENERIC_REVIEW_PATTERN = re.compile(r"\breview\b", re.I)
GUIDELINE_PATTERN = re.compile(r"\b(guideline|guidelines|practice guideline|recommendations?)\b", re.I)
CONSENSUS_PATTERN = re.compile(r"\b(consensus statement|consensus recommendations?|expert consensus)\b", re.I)
REVIEW_PROTOCOL_PATTERN = re.compile(
    r"\b(protocol for|study protocol|review protocol|systematic review protocol|"
    r"meta[- ]analysis protocol|protocol for a systematic review|registered report for)\b",
    re.I,
)
NON_PRIMARY_PUBLICATION_TYPE_PATTERN = re.compile(
    r"\b(editorial|letter|comment|commentary|reply|response|erratum|correction|corrigendum|"
    r"retraction|publisher'?s note|expression of concern|news)\b",
    re.I,
)
NON_PAPER_CONTAINER_PUBLICATION_TYPE_PATTERN = re.compile(
    r"\b(book|book chapter|chapter)\b",
    re.I,
)
NON_PRIMARY_TITLE_PATTERN = re.compile(
    r"\b(editorial|letter|commentary|erratum|correction|corrigendum|retraction|"
    r"publisher'?s note|expression of concern|news)\b|"
    r"^\s*(comment on|reply to|response to|in response to)\b|"
    r"\b(author reply|authors'? reply)\b",
    re.I,
)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def write_table(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, engine="pyarrow", index=False)


def split_publication_types(value: object) -> list[str]:
    out: list[str] = []
    for part in re.split(r"\s*\|\s*", clean(value)):
        text = clean(part)
        if text and text not in out:
            out.append(text)
    return out


def add_type(types: list[str], value: str) -> None:
    if value and value not in types:
        types.append(value)


def metadata_secondary_types(publication_type: object) -> tuple[list[str], list[str]]:
    types: list[str] = []
    matched: list[str] = []
    for raw in split_publication_types(publication_type):
        label = raw.lower().strip()
        label_norm = re.sub(r"[^a-z0-9]+", " ", label).strip()
        if label_norm == "peer review":
            continue
        if label_norm == "network meta analysis":
            add_type(types, "network_meta_analysis")
            add_type(types, "meta_analysis")
            matched.append(raw)
        elif label_norm == "meta analysis":
            add_type(types, "meta_analysis")
            matched.append(raw)
        elif label_norm == "systematic review":
            add_type(types, "systematic_review")
            matched.append(raw)
        elif label_norm == "scoping review":
            add_type(types, "scoping_review")
            matched.append(raw)
        elif label_norm == "review":
            add_type(types, "review")
            matched.append(raw)
        elif label_norm in {"practice guideline", "guideline"}:
            add_type(types, "guideline")
            matched.append(raw)
        elif "consensus" in label_norm:
            add_type(types, "consensus_statement")
            matched.append(raw)
    return normalize_secondary_types(types), matched


def text_secondary_types(title: object, abstract: object) -> tuple[list[str], list[str], list[str]]:
    title_text = clean(title)
    abstract_text = clean(abstract)
    types: list[str] = []
    title_terms: list[str] = []
    abstract_terms: list[str] = []

    for secondary_type, pattern in SPECIFIC_SECONDARY_PATTERNS:
        if pattern.search(title_text):
            add_type(types, secondary_type)
            title_terms.append(pattern.pattern)
        elif pattern.search(abstract_text):
            add_type(types, secondary_type)
            abstract_terms.append(pattern.pattern)
    if GENERIC_REVIEW_PATTERN.search(title_text) and not re.search(r"\b(peer review|reviewed by|book review)\b", title_text, re.I):
        add_type(types, "review")
        title_terms.append(GENERIC_REVIEW_PATTERN.pattern)
    if GUIDELINE_PATTERN.search(title_text):
        add_type(types, "guideline")
        title_terms.append(GUIDELINE_PATTERN.pattern)
    if CONSENSUS_PATTERN.search(title_text):
        add_type(types, "consensus_statement")
        title_terms.append(CONSENSUS_PATTERN.pattern)
    return normalize_secondary_types(types), title_terms, abstract_terms


def normalize_secondary_types(types: Iterable[str]) -> list[str]:
    requested = set(types)
    out: list[str] = []
    for secondary_type in SECONDARY_PRIORITY:
        if secondary_type in requested:
            out.append(secondary_type)
    return out


def primary_secondary_type(types: list[str]) -> str:
    return types[0] if types else ""


def non_primary_flags(publication_type: object, title: object) -> list[str]:
    flags: list[str] = []
    publication_text = " | ".join(split_publication_types(publication_type))
    title_text = clean(title)
    if REVIEW_PROTOCOL_PATTERN.search(title_text) and re.search(
        r"\b(systematic review|meta[- ]analysis|scoping review)\b", title_text, re.I
    ):
        flags.append("review_protocol")
    if NON_PRIMARY_PUBLICATION_TYPE_PATTERN.search(publication_text):
        flags.append("non_primary_publication_type")
    if NON_PAPER_CONTAINER_PUBLICATION_TYPE_PATTERN.search(publication_text):
        flags.append("non_paper_container_publication_type")
    if NON_PRIMARY_TITLE_PATTERN.search(title_text):
        flags.append("non_primary_title")
    return sorted(set(flags))


def classify_literature_type(row: dict) -> dict:
    metadata_types, metadata_terms = metadata_secondary_types(row.get("publication_type", ""))
    text_types, title_terms, abstract_terms = text_secondary_types(row.get("study_title", ""), row.get("abstract", ""))
    secondary_types = normalize_secondary_types([*metadata_types, *text_types])
    flags = non_primary_flags(row.get("publication_type", ""), row.get("study_title", ""))
    is_review_protocol = "review_protocol" in flags
    is_non_paper_container = "non_paper_container_publication_type" in flags

    if is_non_paper_container:
        source_family = "non_primary_publication"
        route = "non_primary_context_or_skip"
        confidence = "high"
    elif secondary_types and not is_review_protocol:
        source_family = "secondary_literature"
        route = "secondary_literature_extraction"
        if metadata_types and title_terms:
            confidence = "high"
        elif primary_secondary_type(secondary_types) in {
            "network_meta_analysis",
            "meta_analysis",
            "systematic_review",
            "scoping_review",
            "umbrella_review",
        }:
            confidence = "high"
        else:
            confidence = "medium"
    elif flags:
        source_family = "non_primary_publication"
        route = "non_primary_context_or_skip"
        confidence = "medium"
    else:
        source_family = "primary_or_unclear"
        route = "primary_literature_extraction"
        confidence = "medium"

    return {
        "source_family": source_family,
        "literature_route": route,
        "secondary_source_types": "|".join(secondary_types),
        "primary_secondary_source_type": primary_secondary_type(secondary_types),
        "metadata_secondary_types": "|".join(metadata_types),
        "title_abstract_secondary_types": "|".join(text_types),
        "non_primary_flags": "|".join(flags),
        "literature_type_confidence": confidence,
        "matched_metadata_terms": join_values(metadata_terms),
        "matched_title_terms": join_values(title_terms),
        "matched_abstract_terms": join_values(abstract_terms),
    }


def retained_decision_context(decisions_df: pd.DataFrame) -> dict[str, dict]:
    out: dict[str, dict] = defaultdict(lambda: {"datasets": [], "prescreen_actions": [], "retained": False})
    if decisions_df.empty or "doi" not in decisions_df.columns:
        return out
    for row in decisions_df.to_dict("records"):
        doi = normalize_doi(clean(row.get("doi", "")))
        if not doi:
            continue
        entry = out[doi]
        dataset = clean(row.get("dataset", ""))
        action = clean(row.get("prescreen_action", ""))
        if dataset and dataset not in entry["datasets"]:
            entry["datasets"].append(dataset)
        if action and action not in entry["prescreen_actions"]:
            entry["prescreen_actions"].append(action)
        if "retained_for_extraction_candidate" in row:
            if clean_bool(row.get("retained_for_extraction_candidate", False)):
                entry["retained"] = True
        elif clean(row.get("prescreen_decision", "")) == "retain":
            entry["retained"] = True
    return out


def build_rows(
    metadata_df: pd.DataFrame,
    decisions_df: pd.DataFrame,
    *,
    generated_at_utc: str,
    only_retained: bool = False,
    scoped_dois: set[str] | None = None,
) -> list[dict]:
    decision_context = retained_decision_context(decisions_df)
    rows: list[dict] = []
    scoped_dois = scoped_dois or set()
    for row in metadata_df.to_dict("records"):
        doi = normalize_doi(clean(row.get("doi", "")))
        if not doi:
            continue
        if scoped_dois and doi not in scoped_dois:
            continue
        context = decision_context.get(doi, {"datasets": [], "prescreen_actions": [], "retained": False})
        if only_retained and not context["retained"]:
            continue
        classification = classify_literature_type(row)
        rows.append(
            {
                "table_version": TABLE_VERSION,
                "generated_at_utc": generated_at_utc,
                "doi": doi,
                "datasets": "|".join(context["datasets"]) or clean(row.get("datasets", "")),
                "retained_for_extraction_candidate": bool(context["retained"]),
                "prescreen_actions": "|".join(context["prescreen_actions"]),
                "study_title": clean(row.get("study_title", "")),
                "study_year": clean(row.get("study_year", "")),
                "publication_type": clean(row.get("publication_type", "")),
                "metadata_provider": clean(row.get("metadata_provider", "")),
                "has_abstract": bool(clean(row.get("abstract", ""))),
                **classification,
            }
        )
    return rows


def build_summary(rows: list[dict]) -> None:
    print(f"Routing rows: {len(rows):,}")
    print(f"Retained candidates: {sum(bool(row.get('retained_for_extraction_candidate')) for row in rows):,}")
    print(f"Source families: {dict(Counter(row.get('source_family', '') for row in rows))}")
    type_counts: Counter[str] = Counter()
    for row in rows:
        for secondary_type in clean(row.get("secondary_source_types", "")).split("|"):
            if secondary_type:
                type_counts[secondary_type] += 1
    print(f"Secondary source types: {dict(type_counts)}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build deterministic primary/secondary literature routing table.")
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--prescreen-decisions-table", default=str(DEFAULT_DECISIONS_TABLE))
    parser.add_argument("--output-table", default=str(DEFAULT_OUTPUT_TABLE))
    parser.add_argument("--doi-file", default="", help="Optional DOI list for scoped routing.")
    parser.add_argument("--only-retained", action="store_true", help="Only route retained deterministic pre-screen candidates.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    metadata_df = read_table(Path(args.metadata_table).resolve())
    decisions_df = read_table(Path(args.prescreen_decisions_table).resolve())
    scoped_dois = read_doi_file(Path(args.doi_file).resolve()) if clean(args.doi_file) else set()
    rows = build_rows(
        metadata_df,
        decisions_df,
        generated_at_utc=now_utc(),
        only_retained=bool(args.only_retained),
        scoped_dois=scoped_dois,
    )
    output_table = Path(args.output_table).resolve()
    write_table(output_table, rows)
    build_summary(rows)
    print(f"Literature type routing table: {output_table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
