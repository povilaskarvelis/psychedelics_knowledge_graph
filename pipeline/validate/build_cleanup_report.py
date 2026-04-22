#!/usr/bin/env python3
"""Generate a short cleanup report for weak curated evidence rows."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[2]

DATASETS = {
    "mechanistic": {
        "input_json": ROOT / "data" / "curated" / "claims.json",
        "relation_key": "target",
        "relation_label": "target",
    },
    "disorder": {
        "input_json": ROOT / "data" / "curated" / "disorder_claims.json",
        "relation_key": "disorder",
        "relation_label": "disorder",
    },
}

PRIMARY_GRAPH_PAPER_TYPE = "primary_results"
PRIMARY_GRAPH_SOURCE_TYPE = "primary_study"
AUTO_DEMOTE_PAPER_TYPES = {"review", "protocol", "conference_or_poster_abstract", "other"}
AUTO_DEMOTE_SOURCE_TYPES = {"review", "meta_analysis"}
AUTO_DEMOTE_OTHER_TITLE_PATTERNS = [
    r"cost[- ]utility",
    r"cost[- ]effectiveness",
    r"model-based",
    r"medical malpractice risk",
    r"physicians[’'] concerns",
    r"who will staff",
    r"\brats?\b",
    r"\bmice\b",
    r"mouse model",
    r"experimental pain model",
    r"\bwistar\b",
    r"blast exposure",
]


def normalize(value: object) -> str:
    return str(value or "").strip()


def slug(value: object) -> str:
    return normalize(value).lower()


def pretty_label(value: str) -> str:
    text = normalize(value)
    if not text:
        return "missing"
    if text == "conference_or_poster_abstract":
        return "conference/poster"
    return text.replace("_", " ")


def truncate(text: object, limit: int = 96) -> str:
    raw = normalize(text)
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 3)].rstrip() + "..."


def title_matches(patterns: Iterable[str], title: object) -> bool:
    text = slug(title)
    return any(re.search(pattern, text) for pattern in patterns)


def build_candidate(dataset: str, row: Dict[str, object], row_index: int) -> Dict[str, object] | None:
    paper_type = slug(row.get("paper_type"))
    source_type = slug(row.get("source_type"))
    access_level = slug(row.get("access_level"))
    evidence_level = slug(row.get("evidence_level"))
    locator = normalize(row.get("evidence_locator"))
    title = normalize(row.get("study_title"))

    issues: List[str] = []
    priority = 0
    action = ""

    if paper_type in AUTO_DEMOTE_PAPER_TYPES:
        issues.append(f"paper_type is {pretty_label(paper_type)}")
        action = "demote_from_main_kg"
        priority += 100
    elif source_type in AUTO_DEMOTE_SOURCE_TYPES:
        issues.append(f"source_type is {pretty_label(source_type)}")
        action = "demote_from_main_kg"
        priority += 90
    elif source_type and source_type != PRIMARY_GRAPH_SOURCE_TYPE:
        issues.append(f"source_type is {pretty_label(source_type)}")
        action = "demote_from_main_kg"
        priority += 85
    elif paper_type == "other" and title_matches(AUTO_DEMOTE_OTHER_TITLE_PATTERNS, title):
        issues.append("title matched obvious non-countable pattern")
        action = "demote_from_main_kg"
        priority += 80
    elif paper_type and paper_type != PRIMARY_GRAPH_PAPER_TYPE:
        issues.append(f"paper_type is {pretty_label(paper_type)}")
        action = "demote_from_main_kg"
        priority += 75
    elif access_level == "secondary_summary":
        issues.append("secondary_summary")
        action = "demote_from_main_kg"
        priority += 70

    if source_type == PRIMARY_GRAPH_SOURCE_TYPE and paper_type != PRIMARY_GRAPH_PAPER_TYPE:
        issues.append("source_type says primary_study but paper_type is weak")
        priority += 25

    if evidence_level == "high" and paper_type != PRIMARY_GRAPH_PAPER_TYPE:
        issues.append("high evidence attached to weak paper_type")
        priority += 20

    if access_level == "abstract_only":
        issues.append("abstract_only")
        priority += 12
    elif access_level == "secondary_summary":
        issues.append("secondary_summary")
        priority += 8

    if access_level == "full_text_seen" and "abstract snippet" in locator.lower():
        issues.append("full_text_seen still points to abstract snippet")
        priority += 18
        if action == "":
            action = "fix_provenance"

    if action == "":
        return None

    relation_key = DATASETS[dataset]["relation_key"]
    return {
        "dataset": dataset,
        "row_index": row_index,
        "compound": normalize(row.get("compound")),
        relation_key: normalize(row.get(relation_key)),
        "study_title": normalize(row.get("study_title")),
        "study_doi": normalize(row.get("study_doi")),
        "paper_type": paper_type or "missing",
        "source_type": source_type or "missing",
        "evidence_level": evidence_level or "missing",
        "access_level": access_level or "missing",
        "result_direction": slug(row.get("result_direction")) or "",
        "issues": issues,
        "recommended_action": action,
        "priority_score": priority,
    }


def summarize_candidates(candidates: Iterable[Dict[str, object]]) -> Dict[str, object]:
    rows = list(candidates)
    return {
        "candidate_count": len(rows),
        "by_action": dict(Counter(row["recommended_action"] for row in rows)),
        "by_paper_type": dict(Counter(row["paper_type"] for row in rows)),
        "by_access_level": dict(Counter(row["access_level"] for row in rows)),
        "by_evidence_level": dict(Counter(row["evidence_level"] for row in rows)),
    }


def render_table(dataset: str, rows: List[Dict[str, object]]) -> List[str]:
    if not rows:
        return ["No rows in this bucket."]

    relation_key = DATASETS[dataset]["relation_key"]
    relation_label = DATASETS[dataset]["relation_label"]
    lines = [
        f"| row | compound | {relation_label} | paper_type | evidence | access | issues | study |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        relation_value = truncate(row.get(relation_key, ""), 28)
        study_label = truncate(row.get("study_title", ""), 80)
        issues = truncate("; ".join(row.get("issues", [])), 70)
        lines.append(
            "| {row_index} | {compound} | {relation_value} | {paper_type} | {evidence_level} | {access_level} | {issues} | {study_label} |".format(
                row_index=row["row_index"],
                compound=truncate(row.get("compound", ""), 22),
                relation_value=relation_value,
                paper_type=pretty_label(str(row.get("paper_type", ""))),
                evidence_level=pretty_label(str(row.get("evidence_level", ""))),
                access_level=pretty_label(str(row.get("access_level", ""))),
                issues=issues,
                study_label=study_label,
            )
        )
    return lines


def dataset_report(dataset: str, rows: List[Dict[str, object]], limit: int) -> Dict[str, object]:
    candidates = []
    for idx, row in enumerate(rows, start=1):
        candidate = build_candidate(dataset, row, idx)
        if candidate:
            candidates.append(candidate)

    candidates.sort(key=lambda row: (-int(row["priority_score"]), int(row["row_index"])))

    auto_demote = [row for row in candidates if row["recommended_action"] == "demote_from_main_kg"]
    manual_review = [row for row in candidates if row["recommended_action"] == "manual_review"]
    provenance_fix = [row for row in candidates if row["recommended_action"] == "fix_provenance"]

    return {
        "row_count": len(rows),
        "paper_type_counts": dict(Counter(slug(row.get("paper_type")) or "missing" for row in rows)),
        "candidate_summary": summarize_candidates(candidates),
        "auto_demote": auto_demote,
        "manual_review": manual_review,
        "provenance_fix": provenance_fix,
        "preview": {
            "auto_demote": auto_demote[:limit],
            "manual_review": manual_review[:limit],
            "provenance_fix": provenance_fix[:limit],
        },
    }


def render_markdown(report: Dict[str, object], limit: int) -> str:
    lines = [
        "# Cleanup Report",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "Purpose: identify weak curated rows that should be demoted from the main evidence set, reviewed manually, or fixed for provenance.",
        "",
    ]

    for dataset in ("mechanistic", "disorder"):
        dataset_data = report["datasets"][dataset]
        summary = dataset_data["candidate_summary"]
        lines.extend(
            [
                f"## {dataset.title()}",
                "",
                f"- Curated rows: {dataset_data['row_count']}",
                f"- Cleanup candidates: {summary['candidate_count']}",
                f"- Auto-demote: {summary['by_action'].get('demote_from_main_kg', 0)}",
                f"- Manual review: {summary['by_action'].get('manual_review', 0)}",
                f"- Provenance fix: {summary['by_action'].get('fix_provenance', 0)}",
                f"- Paper types: {json.dumps(dataset_data['paper_type_counts'], sort_keys=True)}",
                "",
                "### Auto-demote preview",
                "",
            ]
        )
        lines.extend(render_table(dataset, dataset_data["preview"]["auto_demote"]))
        lines.extend(["", "### Manual-review preview", ""])
        lines.extend(render_table(dataset, dataset_data["preview"]["manual_review"]))
        lines.extend(["", "### Provenance-fix preview", ""])
        lines.extend(render_table(dataset, dataset_data["preview"]["provenance_fix"]))
        lines.extend(["", f"Preview limited to top {limit} rows per section.", ""])

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-json",
        type=Path,
        default=ROOT / "data" / "processed" / "cleanup_candidates.json",
        help="Path to write the full cleanup candidate JSON.",
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=ROOT / "data" / "processed" / "cleanup_report.md",
        help="Path to write the short markdown report.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=12,
        help="Rows to preview per section in the markdown report.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "datasets": {},
    }

    for dataset, config in DATASETS.items():
        rows = json.loads(config["input_json"].read_text())
        report["datasets"][dataset] = dataset_report(dataset, rows, args.limit)

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2) + "\n")
    args.out_md.write_text(render_markdown(report, args.limit) + "\n")

    for dataset in ("mechanistic", "disorder"):
        summary = report["datasets"][dataset]["candidate_summary"]
        print(
            f"{dataset}: {summary['candidate_count']} candidates "
            f"({summary['by_action'].get('demote_from_main_kg', 0)} auto-demote, "
            f"{summary['by_action'].get('manual_review', 0)} manual, "
            f"{summary['by_action'].get('fix_provenance', 0)} provenance)"
        )
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
