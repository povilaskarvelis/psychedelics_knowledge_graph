"""Preserve reviewed decisions in an append-only candidate graph build.

Changed or missing reviewed evidence fails closed before any candidate writes.
This command must run before query/browser exports and release promotion.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

IDENTITY_FIELDS = (
    "research_area_evidence_fingerprint", "study_doi", "domain", "compound",
    "entity_label", "kg_entity_kind_override", "graph_subject_label",
    "graph_subject_kind", "research_area_routing_version",
)


def carry_forward(baseline, candidate, baseline_edges, candidate_edges):
    for frame in (baseline, candidate):
        if frame.finding_id.duplicated().any():
            raise ValueError("Duplicate finding IDs; cannot safely carry reviews")
    reviewed = baseline.loc[
        baseline.get("research_area_adjudication_status", pd.Series("", index=baseline.index))
        .fillna("").ne("")
        | baseline.research_area_classification_origin.eq("agent_reviewed")
    ].set_index("finding_id", drop=False)
    current = candidate.set_index("finding_id", drop=False).copy()
    missing = reviewed.index.difference(current.index)
    if len(missing):
        raise ValueError(f"Missing {len(missing)} reviewed findings; explicit reconciliation required")
    for field in IDENTITY_FIELDS:
        if field not in reviewed or field not in current:
            raise ValueError(f"Missing identity field: {field}")
        if not reviewed[field].fillna("").equals(current.loc[reviewed.index, field].fillna("")):
            raise ValueError(f"Reviewed evidence/projection changed: {field}")
    if reviewed.research_area_evidence_fingerprint.fillna("").eq("").any():
        raise ValueError("Reviewed evidence lacks source fingerprints")
    review_fields = [c for c in baseline if c.startswith((
        "research_area_adjudication_", "research_area_second_pass_", "research_area_release_qa_"
    ))] + ["research_area_classification_origin", "graph_admission_status", "graph_admission_reason"]
    for field in review_fields:
        if field not in current:
            current[field] = ""
        current.loc[reviewed.index, field] = reviewed[field]
    # Retain the rebuilt edge values, but enforce the reviewed projection set.
    expected = baseline_edges.loc[baseline_edges.finding_id.isin(reviewed.index)]
    edge_keys = ["finding_id", "projection_type", "entity_id", "compound_id"]
    expected_keys = set(expected[edge_keys].itertuples(index=False, name=None))
    available_keys = set(candidate_edges[edge_keys].itertuples(index=False, name=None))
    if expected_keys - available_keys:
        raise ValueError("A previously reviewed edge projection is missing")
    keep = [fid not in reviewed.index or key in expected_keys for fid, key in zip(
        candidate_edges.finding_id, candidate_edges[edge_keys].itertuples(index=False, name=None)
    )]
    edges = candidate_edges.loc[keep].copy()
    for field in ("graph_admission_status", "graph_admission_reason"):
        mask = edges.finding_id.isin(reviewed.index)
        edges.loc[mask, field] = edges.loc[mask, "finding_id"].map(reviewed[field])
    return current.reset_index(drop=True), edges, {
        "reviewed_findings_preserved": len(reviewed),
        "reviewed_edge_projections_preserved": len(expected_keys),
        "previously_held_edges_removed_from_rebuild": len(candidate_edges) - len(edges),
        "identity_fields_checked": list(IDENTITY_FIELDS),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", required=True, type=Path)
    parser.add_argument("--candidate-dir", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    pointer = json.loads((root / "data/processed/extraction/active_routed_run.json").read_text())
    if args.candidate_dir.resolve() in {args.baseline_dir.resolve(), (root / pointer["kg_dir"]).resolve()}:
        raise ValueError("Refusing to alter the baseline or active release")
    frames = [pd.read_parquet(directory / name) for directory, name in (
        (args.baseline_dir, "findings.parquet"), (args.candidate_dir, "findings.parquet"),
        (args.baseline_dir, "evidence_edges.parquet"), (args.candidate_dir, "evidence_edges.parquet"),
    )]
    findings, edges, report = carry_forward(*frames)
    manifest_path = args.candidate_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for name, frame in (("findings", findings), ("evidence_edges", edges)):
        frame.to_parquet(args.candidate_dir / f"{name}.parquet", index=False)
        manifest["tables"][name].update(rows=len(frame), columns=list(frame.columns))
    manifest["graph_admission_counts"] = findings.graph_admission_status.value_counts().to_dict()
    manifest["edge_counts_by_domain_kind_evidence"] = edges.groupby(
        ["domain", "entity_kind", "evidence_type"], dropna=False
    ).size().reset_index(name="count").to_dict("records")
    report["baseline_dir"] = str(args.baseline_dir.resolve())
    report["candidate_dir"] = str(args.candidate_dir.resolve())
    manifest["review_carry_forward"] = report
    provenance = args.candidate_dir / "carried_forward_review_provenance"
    provenance.mkdir(exist_ok=True)
    for path in args.baseline_dir.glob("research_area_*.parquet"):
        shutil.copy2(path, provenance / path.name)
    qa_manifest = args.baseline_dir / "release_qa_manifest.json"
    if qa_manifest.exists():
        shutil.copy2(qa_manifest, provenance / qa_manifest.name)
    if manifest.get("duckdb", {}).get("status") == "ok":
        sys.path.insert(0, str(root))
        from pipeline.kg.build_evidence_tables import write_duckdb_database
        manifest["duckdb"] = write_duckdb_database(args.candidate_dir, manifest["tables"].keys())
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    (args.candidate_dir / "review_carry_forward_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
