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
        "paper_db_json": ROOT / "data" / "processed" / "paper_library_disorder.json",
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
NON_COUNTABLE_ARTICLE_PATTERNS = [
    r"\bis there a place for\b",
    r"\bcommentary\b",
    r"\beditorial\b",
    r"\bfuture directions\b",
    r"\bresearch directions\b",
    r"\bwhere do we go from here\b",
]
NUMBERED_ABSTRACT_TITLE_RE = re.compile(r"^\s*\d{2,5}\s+[A-Za-z]")
ABSTRACT_RECORD_CUE_PATTERNS = [
    r"\bobjectives goals\b",
    r"\bobjectives specific aims\b",
    r"\bmethods study population\b",
    r"\bresults anticipated results\b",
    r"\bdiscussion significance\b",
]
HEALTHY_VOLUNTEER_RE = re.compile(r"\bhealthy (?:volunteers?|participants?|adults?|subjects?|controls?)\b")


def normalize(value: object) -> str:
    return str(value or "").strip()


def slug(value: object) -> str:
    return normalize(value).lower()


def normalized_phrase_text(value: object) -> str:
    text = slug(value)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_doi(value: object) -> str:
    text = normalize(value)
    if text.lower().startswith("doi:"):
        text = text[4:]
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
    ):
        if text.lower().startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.lower().strip()


def disorder_context_terms(disorder: object) -> List[str]:
    text = normalized_phrase_text(disorder)
    terms = {text} if text else set()
    if "major depressive disorder" in text:
        terms.update({"depression", "mdd", "unipolar depression"})
    if "treatment resistant depression" in text:
        terms.update({"treatment resistant depression", "trd", "depression"})
    if "post traumatic stress disorder" in text or "posttraumatic stress disorder" in text:
        terms.update({"ptsd", "post traumatic stress disorder", "posttraumatic stress disorder"})
    if "social anxiety disorder" in text:
        terms.update({"social anxiety", "social anxiety disorder"})
    if "substance use disorder" in text:
        terms.update({"substance use disorder", "addiction"})
    return sorted(term for term in terms if term)


def has_disorder_sample_context(disorder: object, text: object) -> bool:
    text_norm = normalized_phrase_text(text)
    for term in disorder_context_terms(disorder):
        escaped = re.escape(term)
        if re.search(
            rf"\b(?:patients?|participants?|adults?|volunteers?|subjects?|individuals?|people) with [a-z0-9 ]{{0,80}}\b{escaped}\b",
            text_norm,
        ):
            return True
        if re.search(rf"\bhealthy (?:volunteers?|participants?|controls?|subjects?) and [a-z0-9 ]{{0,50}}\b{escaped}\b", text_norm):
            return True
        if re.search(
            rf"\b{escaped}\b [a-z0-9 ]{{0,60}}\b(?:patients?|participants?|adults?|volunteers?|subjects?|individuals?|people)\b",
            text_norm,
        ):
            return True
    return False


def load_paper_context_by_doi(dataset: str) -> Dict[str, str]:
    path = DATASETS[dataset].get("paper_db_json")
    if not path or not Path(path).exists():
        return {}
    rows = json.loads(Path(path).read_text())
    context: Dict[str, str] = {}
    for row in rows if isinstance(rows, list) else []:
        doi = normalize_doi(row.get("study_doi"))
        if not doi:
            continue
        context[doi] = " ".join(
            [
                normalize(row.get("study_title")),
                normalize(row.get("abstract")),
            ]
        )
    return context


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


def looks_like_abstract_record(title: object, locator: object) -> bool:
    raw_title = normalize(title)
    text = slug(f"{title} {locator}")
    if NUMBERED_ABSTRACT_TITLE_RE.match(raw_title):
        return True
    return any(re.search(pattern, text) for pattern in ABSTRACT_RECORD_CUE_PATTERNS)


def looks_like_non_countable_article(title: object, locator: object) -> bool:
    text = normalized_phrase_text(f"{title} {locator}")
    return any(re.search(pattern, text) for pattern in NON_COUNTABLE_ARTICLE_PATTERNS)


def looks_like_healthy_volunteer_only_disorder_row(row: Dict[str, object], paper_context: object = "") -> bool:
    if not normalize(row.get("disorder")):
        return False
    row_text = normalized_phrase_text(
        " ".join(
            [
                normalize(row.get("study_title")),
                normalize(row.get("population")),
                normalize(row.get("evidence_locator")),
            ]
        )
    )
    paper_text = normalized_phrase_text(paper_context)
    title_text = normalized_phrase_text(row.get("study_title"))
    evidence_text = normalized_phrase_text(
        " ".join(
            [
                normalize(row.get("study_title")),
                normalize(row.get("evidence_locator")),
                normalize(paper_context),
            ]
        )
    )
    has_direct_row_signal = bool(HEALTHY_VOLUNTEER_RE.search(row_text))
    has_phase1_paper_signal = (
        bool(HEALTHY_VOLUNTEER_RE.search(paper_text))
        and ("phase 1" in title_text or "phase 1" in paper_text)
    )
    return (has_direct_row_signal or has_phase1_paper_signal) and not has_disorder_sample_context(
        row.get("disorder"), evidence_text
    )


def build_candidate(
    dataset: str,
    row: Dict[str, object],
    row_index: int,
    paper_context_by_doi: Dict[str, str] | None = None,
) -> Dict[str, object] | None:
    paper_type = slug(row.get("paper_type"))
    source_type = slug(row.get("source_type"))
    access_level = slug(row.get("access_level"))
    evidence_level = slug(row.get("evidence_level"))
    locator = normalize(row.get("evidence_locator"))
    title = normalize(row.get("study_title"))
    paper_context = (paper_context_by_doi or {}).get(normalize_doi(row.get("study_doi")), "")

    issues: List[str] = []
    priority = 0
    action = ""

    if paper_type in AUTO_DEMOTE_PAPER_TYPES:
        issues.append(f"paper_type is {pretty_label(paper_type)}")
        action = "demote_from_main_kg"
        priority += 100
    elif looks_like_abstract_record(title, locator):
        issues.append("numbered or structured abstract record")
        action = "demote_from_main_kg"
        priority += 95
    elif looks_like_non_countable_article(title, locator):
        issues.append("non-countable opinion/research-direction article")
        action = "demote_from_main_kg"
        priority += 95
    elif dataset == "disorder" and looks_like_healthy_volunteer_only_disorder_row(row, paper_context):
        issues.append("healthy-volunteer-only study used as disorder efficacy evidence")
        action = "demote_from_main_kg"
        priority += 95
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


def dataset_report(
    dataset: str,
    rows: List[Dict[str, object]],
    limit: int,
    paper_context_by_doi: Dict[str, str] | None = None,
) -> Dict[str, object]:
    candidates = []
    for idx, row in enumerate(rows, start=1):
        candidate = build_candidate(dataset, row, idx, paper_context_by_doi=paper_context_by_doi)
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
        report["datasets"][dataset] = dataset_report(
            dataset,
            rows,
            args.limit,
            paper_context_by_doi=load_paper_context_by_doi(dataset),
        )

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
