#!/usr/bin/env python3
"""Replay audit DOI scope with a saved Git builder and the working-tree builder.

No extraction, model calls, promotion or publication. Both builds use identical
source rows and the current registries; only the builder implementation differs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    from pipeline.kg import build_evidence_tables as candidate
    from pipeline.validate.evaluate_research_area_routing import evaluate

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.work_dir.exists() and any(args.work_dir.iterdir()):
        parser.error(
            "--work-dir must be new or empty; replay never replaces an existing build"
        )
    audit = pd.read_csv(args.audit).fillna("")
    dois = set(audit.study_doi)
    rows = json.loads(args.evidence.read_text())
    scoped = [r for r in rows if (r.get("study_doi") or r.get("doi")) in dois]
    del rows
    args.work_dir.mkdir(parents=True, exist_ok=True)
    source = args.work_dir / "audit_scope.json"
    source.write_text(json.dumps(scoped))
    revision = subprocess.check_output(
        ["git", "rev-parse", "--verify", args.baseline_ref], cwd=ROOT, text=True
    ).strip()
    code = subprocess.check_output(
        ["git", "show", f"{revision}:pipeline/kg/build_evidence_tables.py"], cwd=ROOT
    )
    baseline = types.ModuleType("research_area_baseline_builder")
    # Keep defaults relative to the real repository, not a temporary directory.
    baseline.__file__ = str(ROOT / "pipeline/kg/build_evidence_tables.py")
    exec(compile(code, baseline.__file__, "exec"), baseline.__dict__)
    config = candidate.graph_sources_for_preset("routed")
    for source_config in config.values():
        source_config["path"] = source
    for name, module in [("baseline", baseline), ("candidate", candidate)]:
        module.build_tables(
            graph_sources=config, out_dir=args.work_dir / name, write_duckdb=False
        )
    b = pd.read_parquet(args.work_dir / "baseline/findings.parquet").fillna("")
    c = pd.read_parquet(args.work_dir / "candidate/findings.parquet").fillna("")
    keys = [
        "study_doi",
        "compound",
        "support",
        "entity_label",
        "kg_entity_kind_override",
        "graph_admission_status",
    ]
    before = set(b[keys].itertuples(index=False, name=None))
    after = set(c[keys].itertuples(index=False, name=None))
    affected = sum(
        tuple(row[k] for k in keys[:-1]) + ("main_graph",) in before - after
        for row in audit.to_dict("records")
    )
    report = {
        "baseline_builder_git_revision": revision,
        "baseline_builder_sha256": hashlib.sha256(code).hexdigest(),
        "source_rows_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "scoped_source_rows": len(scoped),
        "baseline_rows": len(b),
        "candidate_rows": len(c),
        "audited_bad_main_projections_removed_by_patch": affected,
        "removed_projection_keys": len(before - after),
        "added_projection_keys": len(after - before),
        "removed": [dict(zip(keys, r)) for r in sorted(before - after)],
        "added": [dict(zip(keys, r)) for r in sorted(after - before)],
    }
    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / "isolated_patch_changes.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    summary = evaluate(
        args.audit, args.work_dir / "candidate", args.report_dir / "scoped"
    )
    print(
        json.dumps(
            {"isolated_patch_affected_audit_rows": affected, "comparison": summary},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
