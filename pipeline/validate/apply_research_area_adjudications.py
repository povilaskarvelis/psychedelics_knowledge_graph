#!/usr/bin/env python3
"""Materialize the reviewed research-area queue as a versioned KG overlay."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

# Allow direct execution from the repository root (``python pipeline/...``).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.kg.research_area_adjudication import (
    VERSION,
    apply_adjudications,
    adjudicate_queue,
)


def _write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, engine="pyarrow", index=False)


def materialize(
    *,
    candidate_dir: Path,
    out_dir: Path,
    queue_path: Path | None = None,
    audit_path: Path | None = None,
    reviewed_at: str = "2026-09-06",
) -> dict:
    queue_path = queue_path or candidate_dir / "research_area_review_queue.parquet"
    audit = pd.read_csv(audit_path).fillna("") if audit_path and audit_path.is_file() else None
    queue = pd.read_parquet(queue_path).fillna("")
    adjudications = adjudicate_queue(queue, audit_df=audit, reviewed_at=reviewed_at)
    # Preserve the source dtypes (notably numeric affinity/effect columns) so
    # the overlay can be written back to Parquet without coercion errors.
    findings = pd.read_parquet(candidate_dir / "findings.parquet")
    edges = pd.read_parquet(candidate_dir / "evidence_edges.parquet")
    findings, edges, summary = apply_adjudications(findings, edges, adjudications)

    out_dir.mkdir(parents=True, exist_ok=True)
    for source in candidate_dir.glob("*.parquet"):
        if source.name in {"findings.parquet", "evidence_edges.parquet", "research_area_review_queue.parquet"}:
            continue
        shutil.copy2(source, out_dir / source.name)
    _write(findings, out_dir / "findings.parquet")
    _write(edges, out_dir / "evidence_edges.parquet")
    _write(queue, out_dir / "research_area_review_queue.parquet")
    _write(adjudications, out_dir / "research_area_adjudications.parquet")
    adjudications.to_csv(out_dir / "research_area_adjudications.csv", index=False)
    # Assign by key instead of merging: normalization-audit rows can share a
    # fingerprint, and a merge would duplicate queue rows.
    decision_by_key = {}
    for record in adjudications.to_dict("records"):
        decision_by_key.setdefault(record["adjudication_key"], record)
    queue_with_decisions = queue.copy()
    queue_keys = queue_with_decisions["finding_id"].where(
        queue_with_decisions["finding_id"].astype(bool),
        queue_with_decisions["research_area_evidence_fingerprint"],
    )
    for column in (
        "adjudication_key",
        "adjudication_status",
        "adjudication_action",
        "adjudication_rationale",
        "adjudication_id",
        "reviewed_at",
        "reviewer",
    ):
        if column == "adjudication_key":
            queue_with_decisions[column] = queue_keys.tolist()
        else:
            queue_with_decisions[column] = [
                decision_by_key.get(key, {}).get(column, "") for key in queue_keys
            ]
    _write(queue_with_decisions, out_dir / "research_area_review_queue_adjudicated.parquet")
    queue_with_decisions.to_csv(out_dir / "research_area_review_queue_adjudicated.csv", index=False)

    source_manifest = {}
    manifest_path = candidate_dir / "manifest.json"
    if manifest_path.is_file():
        source_manifest = json.loads(manifest_path.read_text())
    manifest = {
        "status": "ok",
        "adjudication_version": VERSION,
        "source_candidate_dir": str(candidate_dir.resolve()),
        "out_dir": str(out_dir.resolve()),
        "queue_path": str(queue_path.resolve()),
        "legacy_audit_path": str(audit_path.resolve()) if audit_path else "",
        "queue_rows": int(len(queue)),
        "adjudications": summary,
        "source_manifest_run_id": source_manifest.get("run_id", ""),
        "tables": {
            "findings": {"path": str((out_dir / "findings.parquet").resolve()), "rows": int(len(findings))},
            "evidence_edges": {"path": str((out_dir / "evidence_edges.parquet").resolve()), "rows": int(len(edges))},
            "research_area_review_queue": {"path": str((out_dir / "research_area_review_queue.parquet").resolve()), "rows": int(len(queue))},
            "research_area_adjudications": {"path": str((out_dir / "research_area_adjudications.parquet").resolve()), "rows": int(len(adjudications))},
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--queue", type=Path, default=None)
    parser.add_argument("--audit", type=Path, default=None)
    parser.add_argument("--reviewed-at", default="2026-09-06")
    args = parser.parse_args()
    print(json.dumps(materialize(
        candidate_dir=args.candidate_dir,
        out_dir=args.out_dir,
        queue_path=args.queue,
        audit_path=args.audit,
        reviewed_at=args.reviewed_at,
    ), indent=2))


if __name__ == "__main__":
    main()
