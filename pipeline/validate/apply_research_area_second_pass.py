#!/usr/bin/env python3
"""Apply the second semantic pass to unresolved main-graph findings."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.kg.research_area_second_pass import VERSION, review_second_pass, summary


def _write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, engine="pyarrow", index=False)


def materialize(*, first_pass_dir: Path, out_dir: Path, reviewed_at: str = "2026-09-06") -> dict:
    first_adjudications = pd.read_parquet(first_pass_dir / "research_area_adjudications.parquet").fillna("")
    findings = pd.read_parquet(first_pass_dir / "findings.parquet")
    edges = pd.read_parquet(first_pass_dir / "evidence_edges.parquet")
    edge_rows_before = len(edges)
    decisions = review_second_pass(findings, first_adjudications, reviewed_at)

    adjudications = first_adjudications.copy()
    decision_by_id = decisions.set_index("finding_id").to_dict("index") if not decisions.empty else {}
    for index, row in adjudications.iterrows():
        decision = decision_by_id.get(str(row.get("finding_id", "")))
        if not decision:
            continue
        adjudications.at[index, "adjudication_status_before_second_pass"] = row.get("adjudication_status", "")
        adjudications.at[index, "adjudication_status"] = decision["second_pass_status"]
        adjudications.at[index, "adjudication_action"] = decision["second_pass_action"]
        adjudications.at[index, "adjudication_rationale"] = decision["second_pass_rationale"]
        adjudications.at[index, "adjudication_version"] = VERSION
        adjudications.at[index, "reviewed_at"] = decision["second_pass_reviewed_at"]
        adjudications.at[index, "reviewer"] = decision["second_pass_reviewer"]
        adjudications.at[index, "second_pass_status"] = decision["second_pass_status"]
        adjudications.at[index, "second_pass_action"] = decision["second_pass_action"]
        adjudications.at[index, "second_pass_rationale"] = decision["second_pass_rationale"]
        adjudications.at[index, "second_pass_group_key"] = decision["second_pass_group_key"]
        adjudications.at[index, "second_pass_reviewed_at"] = decision["second_pass_reviewed_at"]
        adjudications.at[index, "second_pass_reviewer"] = decision["second_pass_reviewer"]

    decision_fields = (
        "research_area_second_pass_version",
        "research_area_second_pass_status",
        "research_area_second_pass_action",
        "research_area_second_pass_rationale",
        "research_area_second_pass_reviewed_at",
        "research_area_second_pass_reviewer",
    )
    for field in decision_fields:
        findings[field] = ""
    corrected_ids = set()
    for index, row in findings.iterrows():
        decision = decision_by_id.get(str(row.get("finding_id", "")))
        if not decision:
            continue
        findings.at[index, "research_area_second_pass_version"] = VERSION
        findings.at[index, "research_area_second_pass_status"] = decision["second_pass_status"]
        findings.at[index, "research_area_second_pass_action"] = decision["second_pass_action"]
        findings.at[index, "research_area_second_pass_rationale"] = decision["second_pass_rationale"]
        findings.at[index, "research_area_second_pass_reviewed_at"] = decision["second_pass_reviewed_at"]
        findings.at[index, "research_area_second_pass_reviewer"] = decision["second_pass_reviewer"]
        findings.at[index, "research_area_adjudication_status"] = decision["second_pass_status"]
        findings.at[index, "research_area_adjudication_action"] = decision["second_pass_action"]
        findings.at[index, "research_area_adjudication_rationale"] = decision["second_pass_rationale"]
        findings.at[index, "research_area_adjudication_reviewed_at"] = decision["second_pass_reviewed_at"]
        findings.at[index, "research_area_adjudication_reviewer"] = decision["second_pass_reviewer"]
        findings.at[index, "research_area_classification_origin"] = "agent_reviewed"
        if decision["second_pass_status"] == "corrected" and decision["second_pass_action"].startswith("hold_"):
            corrected_ids.add(str(row.get("finding_id", "")))
            findings.at[index, "graph_admission_status"] = "paper_detail"
            findings.at[index, "graph_admission_reason"] = "research_area_second_pass_hold_graph_edge"
    if corrected_ids and "finding_id" in edges.columns:
        edges = edges.loc[~edges["finding_id"].astype(str).isin(corrected_ids)].copy()

    out_dir.mkdir(parents=True, exist_ok=True)
    for source in first_pass_dir.glob("*.parquet"):
        if source.name in {"findings.parquet", "evidence_edges.parquet", "research_area_adjudications.parquet"}:
            continue
        shutil.copy2(source, out_dir / source.name)
    _write(findings, out_dir / "findings.parquet")
    _write(edges, out_dir / "evidence_edges.parquet")
    _write(adjudications, out_dir / "research_area_adjudications.parquet")
    adjudications.to_csv(out_dir / "research_area_adjudications.csv", index=False)
    _write(decisions, out_dir / "research_area_second_pass_decisions.parquet")
    decisions.to_csv(out_dir / "research_area_second_pass_decisions.csv", index=False)

    edge_ids = set(edges["finding_id"].astype(str)) if "finding_id" in edges.columns else set()
    corrected_decision_ids = set(
        decisions.loc[decisions["second_pass_status"].eq("corrected"), "finding_id"].astype(str)
    )
    confirmed_decision_ids = set(
        decisions.loc[decisions["second_pass_status"].eq("confirmed_current"), "finding_id"].astype(str)
    )

    queue_path = first_pass_dir / "research_area_review_queue_adjudicated.parquet"
    if queue_path.exists():
        queue = pd.read_parquet(queue_path)
        queue_decisions = decisions[
            ["finding_id", "second_pass_status", "second_pass_action", "second_pass_rationale", "second_pass_reviewed_at", "second_pass_reviewer"]
        ]
        queue = queue.merge(queue_decisions, on="finding_id", how="left")
        _write(queue, out_dir / "research_area_review_queue_adjudicated.parquet")
        queue.to_csv(out_dir / "research_area_review_queue_adjudicated.csv", index=False)

    result = {
        "status": "ok",
        "second_pass_version": VERSION,
        "source_first_pass_dir": str(first_pass_dir.resolve()),
        "out_dir": str(out_dir.resolve()),
        "decisions": summary(decisions),
        "held_finding_ids": len(corrected_ids),
        "held_edges": int(edge_rows_before - len(edges)),
        "findings_rows": int(len(findings)),
        "evidence_edge_rows": int(len(edges)),
        "adjudication_rows": int(len(adjudications)),
        "combined_adjudication_status_counts": adjudications["adjudication_status"].value_counts().to_dict(),
        "combined_finding_status_counts": adjudications.loc[
            adjudications["record_type"].eq("finding"), "adjudication_status"
        ].value_counts().to_dict(),
        "combined_unresolved_finding_count": int(
            (
                adjudications["record_type"].eq("finding")
                & adjudications["adjudication_status"].eq("unresolved")
            ).sum()
        ),
        "second_pass_unresolved_finding_ids": decisions.loc[
            decisions["second_pass_status"].eq("unresolved"), "finding_id"
        ].astype(str).tolist(),
        "integrity": {
            "second_pass_corrected_edges_remaining": len(corrected_decision_ids & edge_ids),
            "second_pass_confirmed_edges_missing": len(confirmed_decision_ids - edge_ids),
        },
        "active_release_changed": False,
    }
    (out_dir / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-pass-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--reviewed-at", default="2026-09-06")
    args = parser.parse_args()
    print(json.dumps(materialize(first_pass_dir=args.first_pass_dir, out_dir=args.out_dir, reviewed_at=args.reviewed_at), indent=2))


if __name__ == "__main__":
    main()
