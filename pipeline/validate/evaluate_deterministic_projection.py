#!/usr/bin/env python3
"""Compare a deterministic KG rebuild with an existing normalized baseline."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import Counter
from pathlib import Path

import pandas as pd


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def counts_by(df: pd.DataFrame, column: str) -> dict[str, int]:
    if df.empty or column not in df.columns:
        return {}
    return {str(key): int(value) for key, value in df[column].fillna("").value_counts().items()}


def paper_counts(df: pd.DataFrame) -> Counter[str]:
    if df.empty or "study_doi" not in df.columns:
        return Counter()
    return Counter(str(value).strip().lower() for value in df["study_doi"] if str(value).strip())


def source_item_key(record: dict) -> tuple[str, str, str, str, str] | None:
    raw_value = record.get("raw_row_json", "")
    try:
        raw = raw_value if isinstance(raw_value, dict) else json.loads(str(raw_value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    doi = str(raw.get("study_doi") or record.get("study_doi") or "").strip().lower()
    route_id = str(raw.get("route_id") or raw.get("task_id") or "").strip()
    item_type = str(raw.get("source_item_type") or "").strip()
    item_index = str(raw.get("source_item_index") or "").strip()
    domain = str(raw.get("domain") or raw.get("domain_route") or record.get("domain") or "").strip()
    if not doi or not route_id or not item_index:
        return None
    return doi, route_id, item_type, item_index, domain


def audit_transition_summary(
    baseline_audit: pd.DataFrame,
    candidate_findings: pd.DataFrame,
    candidate_audit: pd.DataFrame,
) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    finding_keys = {
        key
        for record in candidate_findings.to_dict(orient="records")
        if (key := source_item_key(record)) is not None
    }
    audit_keys = {
        key
        for record in candidate_audit.to_dict(orient="records")
        if (key := source_item_key(record)) is not None
    }
    by_status: dict[str, Counter[str]] = {}
    total: Counter[str] = Counter()
    for record in baseline_audit.to_dict(orient="records"):
        status = str(record.get("normalization_status") or "").strip()
        key = source_item_key(record)
        if key in finding_keys:
            transition = "recovered_to_finding"
        elif key in audit_keys:
            transition = "still_held"
        else:
            transition = "not_matched"
        by_status.setdefault(status, Counter())[transition] += 1
        total[transition] += 1
    return (
        {status: dict(counts) for status, counts in sorted(by_status.items())},
        dict(total),
    )


def load_tables(directory: Path) -> dict[str, pd.DataFrame]:
    return {
        name: pd.read_parquet(directory / f"{name}.parquet")
        for name in ("findings", "evidence_edges", "normalization_audit")
    }


def compare(
    baseline_dir: Path,
    candidate_dir: Path,
    manual_assessment: Path | None = None,
) -> tuple[dict, pd.DataFrame]:
    baseline = load_tables(baseline_dir)
    candidate = load_tables(candidate_dir)
    old_findings = baseline["findings"]
    new_findings = candidate["findings"]
    old_audit = baseline["normalization_audit"]
    new_audit = candidate["normalization_audit"]
    old_counts = paper_counts(old_findings)
    new_counts = paper_counts(new_findings)
    old_audit_counts = paper_counts(old_audit)
    new_audit_counts = paper_counts(new_audit)

    non_atomic_kinds = {"compound_class", "compound_combination", "exposure_context", "treatment_regimen"}
    non_atomic = new_findings[
        new_findings.get("graph_subject_kind", pd.Series(index=new_findings.index, dtype=str)).fillna("").isin(non_atomic_kinds)
    ]
    non_atomic_counts = paper_counts(non_atomic)
    all_dois = sorted(set(old_counts) | set(new_counts) | set(old_audit_counts) | set(new_audit_counts))
    paper_rows = []
    for doi in all_dois:
        old_count = old_counts[doi]
        new_count = new_counts[doi]
        if old_count == 0 and new_count > 0:
            change = "recovered_from_zero"
        elif non_atomic_counts[doi] > 0 and new_count > old_count:
            change = "gained_non_atomic_relationships"
        elif new_count > old_count:
            change = "more_normalized_findings"
        elif new_count < old_count:
            change = "fewer_normalized_findings"
        else:
            change = "unchanged_count"
        paper_rows.append(
            {
                "doi": doi,
                "baseline_findings": old_count,
                "candidate_findings": new_count,
                "finding_delta": new_count - old_count,
                "candidate_non_atomic_findings": non_atomic_counts[doi],
                "baseline_held_rows": old_audit_counts[doi],
                "candidate_held_rows": new_audit_counts[doi],
                "held_delta": new_audit_counts[doi] - old_audit_counts[doi],
                "representation_change": change,
            }
        )
    paper_df = pd.DataFrame(paper_rows)
    if manual_assessment and manual_assessment.exists():
        manual = pd.read_csv(manual_assessment)
        doi_column = "doi" if "doi" in manual.columns else "study_doi"
        manual[doi_column] = manual[doi_column].fillna("").astype(str).str.lower()
        paper_df = manual.merge(paper_df, left_on=doi_column, right_on="doi", how="left")

    old_status = counts_by(old_audit, "normalization_status")
    new_status = counts_by(new_audit, "normalization_status")
    status_delta = {
        status: new_status.get(status, 0) - old_status.get(status, 0)
        for status in sorted(set(old_status) | set(new_status))
    }
    audit_transitions, audit_transition_totals = audit_transition_summary(old_audit, new_findings, new_audit)
    report = {
        "schema_version": "deterministic_projection_evaluation_v1",
        "generated_at_utc": now_utc(),
        "baseline_dir": str(baseline_dir.resolve()),
        "candidate_dir": str(candidate_dir.resolve()),
        "counts": {
            "baseline_findings": int(len(old_findings)),
            "candidate_findings": int(len(new_findings)),
            "finding_delta": int(len(new_findings) - len(old_findings)),
            "baseline_papers_with_findings": len(old_counts),
            "candidate_papers_with_findings": len(new_counts),
            "papers_recovered_from_zero": int(
                (paper_df["representation_change"] == "recovered_from_zero").sum()
            ),
            "baseline_audit_rows": int(len(old_audit)),
            "candidate_audit_rows": int(len(new_audit)),
            "audit_delta": int(len(new_audit) - len(old_audit)),
            "candidate_non_atomic_findings": int(len(non_atomic)),
            "candidate_unique_proposition_groups": int(
                new_findings["proposition_group_id"].nunique()
                if "proposition_group_id" in new_findings.columns
                else len(new_findings)
            ),
            "candidate_duplicate_finding_rows": int(
                len(new_findings) - new_findings["proposition_group_id"].nunique()
                if "proposition_group_id" in new_findings.columns
                else 0
            ),
            "candidate_direction_conflict_rows": int(
                (new_findings.get("direction_consistency", "") == "conflict").sum()
                if "direction_consistency" in new_findings.columns
                else 0
            ),
            "candidate_paper_detail_rows": int(
                (new_findings.get("graph_admission_status", "") == "paper_detail").sum()
                if "graph_admission_status" in new_findings.columns
                else 0
            ),
        },
        "baseline_audit_status_counts": old_status,
        "candidate_audit_status_counts": new_status,
        "audit_status_delta": status_delta,
        "baseline_audit_transitions": audit_transitions,
        "baseline_audit_transition_totals": audit_transition_totals,
        "candidate_graph_subject_kind_counts": counts_by(new_findings, "graph_subject_kind"),
        "candidate_evidence_design_counts": counts_by(new_findings, "evidence_design"),
        "candidate_graph_admission_counts": counts_by(new_findings, "graph_admission_status"),
    }
    return report, paper_df


def markdown_report(report: dict) -> str:
    counts = report["counts"]
    lines = [
        "# Deterministic projection evaluation",
        "",
        f"Generated: {report['generated_at_utc']}",
        "",
        "No extraction or evaluator model calls were used. The candidate was rebuilt from saved routed evidence rows.",
        "",
        "## Overall",
        "",
        "| Metric | Baseline | Candidate | Delta |",
        "|---|---:|---:|---:|",
        f"| Normalized findings | {counts['baseline_findings']} | {counts['candidate_findings']} | {counts['finding_delta']:+d} |",
        f"| Papers with findings | {counts['baseline_papers_with_findings']} | {counts['candidate_papers_with_findings']} | {counts['candidate_papers_with_findings'] - counts['baseline_papers_with_findings']:+d} |",
        f"| Held normalization rows | {counts['baseline_audit_rows']} | {counts['candidate_audit_rows']} | {counts['audit_delta']:+d} |",
        "",
        f"The candidate contains {counts['candidate_non_atomic_findings']} preserved class, combination, contextual-exposure, or regimen findings and recovered {counts['papers_recovered_from_zero']} papers that previously had no normalized finding.",
        f"It groups the candidate into {counts['candidate_unique_proposition_groups']} structural propositions, identifying {counts['candidate_duplicate_finding_rows']} duplicate rows and {counts['candidate_direction_conflict_rows']} direction-conflict rows.",
        f"At the same saved source-item level, {report['baseline_audit_transition_totals'].get('recovered_to_finding', 0)} baseline held rows became findings, {report['baseline_audit_transition_totals'].get('still_held', 0)} remained held, and {report['baseline_audit_transition_totals'].get('not_matched', 0)} could not be matched after row expansion or filtering.",
        "",
        "## Audit status changes",
        "",
        "| Status | Baseline | Candidate | Delta |",
        "|---|---:|---:|---:|",
    ]
    old = report["baseline_audit_status_counts"]
    new = report["candidate_audit_status_counts"]
    delta = report["audit_status_delta"]
    for status in sorted(delta, key=lambda value: (delta[value], value)):
        lines.append(f"| `{status}` | {old.get(status, 0)} | {new.get(status, 0)} | {delta[status]:+d} |")
    lines.extend(
        [
            "",
            "Counts measure representation recovery and conservative filtering. They do not by themselves prove that paper-level centrality improved; that requires direct comparison with the manual paper judgments.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--manual-assessment", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report, paper_df = compare(args.baseline_dir, args.candidate_dir, args.manual_assessment)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "evaluation_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.out_dir / "evaluation_report.md").write_text(markdown_report(report), encoding="utf-8")
    paper_df.to_csv(args.out_dir / "paper_comparison.csv", index=False)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
