#!/usr/bin/env python3
"""Compare audited projections with a candidate KG; do not equate absence with a fix.

Matching uses DOI, compound and exact saved support text because generated IDs
can change when expansion changes. Ambiguous or missing matches stay explicit.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd


def evaluate(audit_path: Path, candidate_dir: Path, out_dir: Path):
    audit = pd.read_csv(audit_path).fillna("")
    candidate = pd.read_parquet(candidate_dir / "findings.parquet").fillna("")
    groups = defaultdict(list)
    for row in candidate[
        [
            "finding_id",
            "study_doi",
            "compound",
            "support",
            "domain",
            "entity_label",
            "kg_entity_kind_override",
            "graph_admission_status",
            "graph_admission_reason",
            "research_area_review_status",
            "research_area_review_reasons_json",
        ]
    ].to_dict("records"):
        groups[(row["study_doi"], row["compound"], row["support"])].append(row)
    rejected = defaultdict(list)
    queue_path = candidate_dir / "research_area_review_queue.parquet"
    if queue_path.exists():
        queue = pd.read_parquet(queue_path).fillna("")
        for row in queue.to_dict("records"):
            if row.get("record_type") == "normalization_audit":
                rejected[(row["study_doi"], row["compound"], row["support"])].append(
                    row
                )
    results = []
    for row in audit.to_dict("records"):
        candidates = groups[(row["study_doi"], row["compound"], row["support"])]
        same = [
            r
            for r in candidates
            if r["entity_label"] == row["entity_label"]
            and r["kg_entity_kind_override"] == row["kg_entity_kind_override"]
        ]
        if same:
            if all(r["graph_admission_status"] != "main_graph" for r in same):
                status = "old_projection_held_for_detail"
            elif any(r["research_area_review_status"] == "pending" for r in same):
                status = "remaining_flagged"
            else:
                status = "remaining_unflagged"
        elif candidates:
            status = "old_projection_absent_other_projection_present"
        else:
            candidates = rejected[(row["study_doi"], row["compound"], row["support"])]
            status = (
                "normalization_review_pending"
                if candidates
                else "no_exact_evidence_match"
            )
        results.append(
            {
                "baseline_finding_id": row["finding_id"],
                "study_doi": row["study_doi"],
                "compound": row["compound"],
                "old_entity": row["entity_label"],
                "old_kind": row["kg_entity_kind_override"],
                "audit_category": row["category"],
                "status": status,
                "support": row["support"],
                "candidate_projections": candidates,
            }
        )
    summary = {
        "audit_path": str(audit_path),
        "candidate_dir": str(candidate_dir),
        "audit_rows": len(results),
        "status_counts": dict(Counter(r["status"] for r in results)),
        "candidate_rows": len(candidate),
        "candidate_review_status_counts": candidate.research_area_review_status.value_counts().to_dict(),
        "limitations": [
            "Changed/absent projections require inspection before calling them corrected.",
            "Missing matches are not counted as fixes.",
            "A comparison to an older release does not isolate changes made by this patch.",
            "Counts refer to normalized rows, including repeated projections of a finding.",
        ],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "audit_comparison.json").write_text(json.dumps(results, indent=2) + "\n")
    (out_dir / "audit_comparison_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    pd.DataFrame(
        [
            {**r, "candidate_projections": json.dumps(r["candidate_projections"])}
            for r in results
        ]
    ).to_csv(out_dir / "audit_comparison.csv", index=False)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.audit, args.candidate_dir, args.out_dir), indent=2))
