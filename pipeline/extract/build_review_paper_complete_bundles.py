#!/usr/bin/env python3
"""Combine paper-complete review outputs into paper-centered QA bundles."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    from pipeline.extract.io_utils import normalize, read_jsonl, write_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.io_utils import normalize, read_jsonl, write_json


ROOT = Path(__file__).resolve().parents[2]
GRAPHABLE_FOCUS = {"main_focus", "substantial_topic"}
PERIPHERAL_COVERAGE_TYPES = {"mentions", "methodological_context"}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalized_doi(value: object) -> str:
    return normalize(value).lower()


def result_for_output(row: dict) -> dict:
    result = row.get("result")
    return result if isinstance(result, dict) else {}


def domain_for_output(row: dict, result: dict) -> str:
    return normalize(result.get("domain_route", "")) or normalize(row.get("domain_route", ""))


def audit_inventory(result: dict) -> list[str]:
    issues: list[str] = []
    items = [item for item in result.get("coverage_items", []) if isinstance(item, dict)]
    item_ids = {normalize(item.get("item_id", "")) for item in items if normalize(item.get("item_id", ""))}
    assessment = result.get("review_assessment", {})
    if not isinstance(assessment, dict):
        assessment = {}
    inventory = assessment.get("substantive_coverage_inventory")
    if normalize(result.get("extraction_status", "")) == "extracted" and not isinstance(inventory, list):
        issues.append("missing_substantive_coverage_inventory")
        inventory = []
    for entry in inventory if isinstance(inventory, list) else []:
        if not isinstance(entry, dict):
            issues.append("invalid_inventory_entry")
            continue
        inventory_id = normalize(entry.get("inventory_id", "")) or "unknown_inventory_item"
        linked_ids = {
            normalize(item_id)
            for item_id in entry.get("coverage_item_ids", [])
            if normalize(item_id)
        }
        has_item = bool(entry.get("has_coverage_item"))
        if has_item and not linked_ids:
            issues.append(f"inventory_has_item_without_ids:{inventory_id}")
        for missing_id in sorted(linked_ids - item_ids):
            issues.append(f"inventory_missing_coverage_item:{inventory_id}:{missing_id}")
        if not has_item and not normalize(entry.get("reason_if_no_coverage_item", "")):
            issues.append(f"inventory_missing_no_item_reason:{inventory_id}")

    linked_item_ids = {
        normalize(item_id)
        for entry in inventory if isinstance(inventory, list)
        for item_id in (entry.get("coverage_item_ids", []) if isinstance(entry, dict) else [])
        if normalize(item_id)
    }
    for unlinked_id in sorted(item_ids - linked_item_ids):
        issues.append(f"coverage_item_not_in_inventory:{unlinked_id}")
    return issues


def item_flags(item: dict) -> list[str]:
    flags: list[str] = []
    focus = normalize(item.get("coverage_focus", ""))
    coverage_type = normalize(item.get("coverage_type", ""))
    if focus not in GRAPHABLE_FOCUS:
        flags.append(f"non_graphable_focus:{focus or 'missing'}")
    if coverage_type in PERIPHERAL_COVERAGE_TYPES:
        flags.append(f"non_graphable_coverage_type:{coverage_type}")
    if not normalize(item.get("compound_or_class", "")):
        flags.append("missing_compound_or_class")
    if not normalize(item.get("entity", "")):
        flags.append("missing_entity")
    if not normalize(item.get("summary_statement", "")):
        flags.append("missing_summary_statement")
    return flags


def build_bundles(cohort_rows: list[dict], output_rows: list[dict]) -> tuple[list[dict], dict]:
    outputs_by_doi: dict[str, list[dict]] = defaultdict(list)
    for output in output_rows:
        result = result_for_output(output)
        doi = normalized_doi(result.get("study_doi", "")) or normalized_doi(output.get("study_doi", ""))
        if doi:
            outputs_by_doi[doi].append(output)

    bundles: list[dict] = []
    report_counts: Counter = Counter()
    issue_counts: Counter = Counter()
    for cohort in cohort_rows:
        doi = normalized_doi(cohort.get("doi", ""))
        expected_domains = [normalize(domain) for domain in cohort.get("routed_domains", []) if normalize(domain)]
        outputs = outputs_by_doi.get(doi, [])
        domain_outputs = []
        completed_domains = []
        paper_issues: list[str] = []
        seen_domains: Counter = Counter()

        for output in sorted(outputs, key=lambda row: domain_for_output(row, result_for_output(row))):
            result = result_for_output(output)
            domain = domain_for_output(output, result)
            if domain:
                completed_domains.append(domain)
                seen_domains[domain] += 1
            inventory_issues = audit_inventory(result)
            for issue in inventory_issues:
                issue_counts[issue.split(":", 1)[0]] += 1
            items = []
            for item in result.get("coverage_items", []) if isinstance(result.get("coverage_items"), list) else []:
                if not isinstance(item, dict):
                    continue
                flags = item_flags(item)
                for flag in flags:
                    issue_counts[flag.split(":", 1)[0]] += 1
                items.append({**item, "qa_flags": flags})
            domain_outputs.append(
                {
                    "domain_route": domain,
                    "task_id": normalize(result.get("task_id", "")) or normalize(output.get("task_id", "")),
                    "route_id": normalize(result.get("route_id", "")) or normalize(output.get("route_id", "")),
                    "output_status": normalize(output.get("status", "")),
                    "extraction_status": normalize(result.get("extraction_status", "")),
                    "review_assessment": result.get("review_assessment", {}),
                    "coverage_items": items,
                    "extraction_warnings": result.get("extraction_warnings", []),
                    "inventory_qa_issues": inventory_issues,
                }
            )

        expected_set = set(expected_domains)
        completed_set = set(completed_domains)
        missing_domains = sorted(expected_set - completed_set)
        unexpected_domains = sorted(completed_set - expected_set)
        duplicate_domains = sorted(domain for domain, count in seen_domains.items() if count > 1)
        if missing_domains:
            paper_issues.append("missing_domain_outputs")
        if unexpected_domains:
            paper_issues.append("unexpected_domain_outputs")
        if duplicate_domains:
            paper_issues.append("duplicate_domain_outputs")
        if not any(
            normalize(item.get("coverage_focus", "")) == "main_focus"
            for domain_output in domain_outputs
            for item in domain_output["coverage_items"]
        ):
            paper_issues.append("no_main_focus_item_across_paper")

        coverage_item_count = sum(len(domain_output["coverage_items"]) for domain_output in domain_outputs)
        report_counts["papers"] += 1
        report_counts["expected_domain_tasks"] += len(expected_domains)
        report_counts["completed_domain_outputs"] += len(outputs)
        report_counts["coverage_items"] += coverage_item_count
        for issue in paper_issues:
            issue_counts[issue] += 1
        bundles.append(
            {
                **cohort,
                "expected_domains": expected_domains,
                "completed_domains": sorted(completed_set),
                "missing_domains": missing_domains,
                "unexpected_domains": unexpected_domains,
                "duplicate_domains": duplicate_domains,
                "paper_qa_issues": paper_issues,
                "coverage_item_count": coverage_item_count,
                "domain_outputs": domain_outputs,
            }
        )

    report = {
        "schema_version": "review_paper_complete_bundle_report_v1",
        "generated_at_utc": now_utc(),
        "counts": dict(report_counts),
        "issue_counts": dict(issue_counts),
        "paper_complete": report_counts["expected_domain_tasks"] == report_counts["completed_domain_outputs"]
        and not issue_counts["missing_domain_outputs"]
        and not issue_counts["unexpected_domain_outputs"]
        and not issue_counts["duplicate_domain_outputs"],
    }
    return bundles, report


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_flat_csvs(out_dir: Path, bundles: list[dict]) -> None:
    summary_fields = [
        "doi",
        "study_title",
        "review_type",
        "text_depth",
        "expected_domains",
        "completed_domains",
        "missing_domains",
        "coverage_item_count",
        "paper_qa_issues",
    ]
    item_fields = [
        "doi",
        "study_title",
        "text_depth",
        "domain_route",
        "extraction_status",
        "item_id",
        "coverage_focus",
        "coverage_type",
        "compound_or_class",
        "entity_type",
        "entity",
        "summary_statement",
        "evidence_location",
        "evidence_locator",
        "confidence",
        "qa_flags",
    ]
    summary_rows = []
    item_rows = []
    for bundle in bundles:
        summary_rows.append(
            {
                "doi": bundle.get("doi", ""),
                "study_title": bundle.get("study_title", ""),
                "review_type": bundle.get("review_type", ""),
                "text_depth": bundle.get("text_depth", ""),
                "expected_domains": "|".join(bundle.get("expected_domains", [])),
                "completed_domains": "|".join(bundle.get("completed_domains", [])),
                "missing_domains": "|".join(bundle.get("missing_domains", [])),
                "coverage_item_count": bundle.get("coverage_item_count", 0),
                "paper_qa_issues": "|".join(bundle.get("paper_qa_issues", [])),
            }
        )
        for domain_output in bundle.get("domain_outputs", []):
            for item in domain_output.get("coverage_items", []):
                item_rows.append(
                    {
                        "doi": bundle.get("doi", ""),
                        "study_title": bundle.get("study_title", ""),
                        "text_depth": bundle.get("text_depth", ""),
                        "domain_route": domain_output.get("domain_route", ""),
                        "extraction_status": domain_output.get("extraction_status", ""),
                        "item_id": item.get("item_id", ""),
                        "coverage_focus": item.get("coverage_focus", ""),
                        "coverage_type": item.get("coverage_type", ""),
                        "compound_or_class": item.get("compound_or_class", ""),
                        "entity_type": item.get("entity_type", ""),
                        "entity": item.get("entity", ""),
                        "summary_statement": item.get("summary_statement", ""),
                        "evidence_location": item.get("evidence_location", ""),
                        "evidence_locator": item.get("evidence_locator", ""),
                        "confidence": item.get("confidence", ""),
                        "qa_flags": "|".join(item.get("qa_flags", [])),
                    }
                )

    for path, fieldnames, rows in (
        (out_dir / "paper_bundle_summary.csv", summary_fields, summary_rows),
        (out_dir / "paper_bundle_items.csv", item_fields, item_rows),
    ):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-jsonl", type=Path, required=True)
    parser.add_argument("--outputs-jsonl", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cohort_rows = read_jsonl(args.cohort_jsonl)
    output_rows = read_jsonl(args.outputs_jsonl)
    bundles, report = build_bundles(cohort_rows, output_rows)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out_dir / "paper_bundles.jsonl", bundles)
    write_flat_csvs(args.out_dir, bundles)
    report["inputs"] = {
        "cohort_jsonl": str(args.cohort_jsonl.resolve()),
        "outputs_jsonl": str(args.outputs_jsonl.resolve()),
    }
    report["outputs"] = {
        "paper_bundles_jsonl": str((args.out_dir / "paper_bundles.jsonl").resolve()),
        "paper_bundle_summary_csv": str((args.out_dir / "paper_bundle_summary.csv").resolve()),
        "paper_bundle_items_csv": str((args.out_dir / "paper_bundle_items.csv").resolve()),
    }
    write_json(args.out_dir / "paper_bundle_report.json", report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
