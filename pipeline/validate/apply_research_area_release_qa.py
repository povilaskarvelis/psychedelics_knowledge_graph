#!/usr/bin/env python3
"""Apply reviewed release-QA overrides to a research-area second-pass run."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

import pandas as pd


def normalize(value: object) -> str:
    return " ".join(str(value or "").split())


def _write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, engine="pyarrow", index=False)


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _stable_sample(decisions: pd.DataFrame, quotas: dict[str, int]) -> pd.DataFrame:
    sampled: list[pd.DataFrame] = []
    for action, quota in quotas.items():
        rows = decisions.loc[
            decisions["second_pass_status"].eq("confirmed_current")
            & decisions["second_pass_action"].eq(action)
        ].copy()
        if len(rows) < int(quota):
            raise ValueError(f"Sample quota {quota} exceeds {len(rows)} rows for {action}")
        rows["_sample_hash"] = rows["finding_id"].astype(str).map(
            lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()
        )
        sampled.append(rows.sort_values("_sample_hash").head(int(quota)))
    if not sampled:
        return decisions.iloc[0:0].copy()
    return pd.concat(sampled, ignore_index=True).drop(columns=["_sample_hash"])


def _expanded_group_ids(decisions: pd.DataFrame, seed_ids: set[str]) -> set[str]:
    if not seed_ids:
        return set()
    indexed = decisions.set_index("finding_id", drop=False)
    missing = sorted(seed_ids - set(indexed.index.astype(str)))
    if missing:
        raise ValueError(f"Override finding IDs are absent from second-pass decisions: {missing[:10]}")
    group_keys = {
        normalize(indexed.loc[finding_id, "second_pass_group_key"])
        for finding_id in seed_ids
    }
    return set(
        decisions.loc[
            decisions["second_pass_group_key"].astype(str).isin(group_keys), "finding_id"
        ].astype(str)
    )


def _table_manifest(path: Path, root: Path) -> dict:
    frame = pd.read_parquet(path)
    try:
        table_path = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        table_path = str(path.resolve())
    return {"path": table_path, "rows": int(len(frame)), "columns": list(frame.columns)}


def materialize(
    *,
    second_pass_dir: Path,
    out_dir: Path,
    overrides_path: Path,
    run_id: str,
) -> dict:
    config = _read_json(overrides_path)
    if config.get("schema_version") != "research_area_release_qa_overrides_v1":
        raise ValueError(f"Unexpected override schema: {overrides_path}")

    second_manifest = _read_json(second_pass_dir / "manifest.json")
    first_pass_dir = Path(second_manifest["source_first_pass_dir"])
    first_manifest = _read_json(first_pass_dir / "manifest.json")
    source_candidate_dir = Path(first_manifest["source_candidate_dir"])
    source_manifest = _read_json(source_candidate_dir / "manifest.json")

    findings = pd.read_parquet(second_pass_dir / "findings.parquet")
    edges = pd.read_parquet(second_pass_dir / "evidence_edges.parquet")
    adjudications = pd.read_parquet(second_pass_dir / "research_area_adjudications.parquet").fillna("")
    decisions = pd.read_parquet(second_pass_dir / "research_area_second_pass_decisions.parquet").fillna("")
    first_findings = pd.read_parquet(first_pass_dir / "findings.parquet").fillna("")
    first_edges = pd.read_parquet(first_pass_dir / "evidence_edges.parquet")

    if decisions["finding_id"].duplicated().any():
        raise ValueError("Second-pass decisions must have unique finding IDs")
    decision_by_id = decisions.set_index("finding_id", drop=False)

    corrected = decisions.loc[decisions["second_pass_status"].eq("corrected")].copy()
    unresolved = decisions.loc[decisions["second_pass_status"].eq("unresolved")].copy()
    sample = _stable_sample(decisions, config.get("confirmation_sample_quotas") or {})
    sample_ids = set(sample["finding_id"].astype(str))

    restore_reasons: dict[str, str] = {}
    for rule in config.get("restore_action_rules") or []:
        action = normalize(rule.get("second_pass_action"))
        candidates = set(
            corrected.loc[corrected["second_pass_action"].eq(action), "finding_id"].astype(str)
        )
        if not candidates:
            raise ValueError(f"Restore action has no corrected rows: {action}")
        exceptions = {normalize(value) for value in rule.get("except_finding_ids") or []}
        if not exceptions <= candidates:
            raise ValueError(f"Restore-action exceptions are not members of {action}")
        for finding_id in candidates - exceptions:
            restore_reasons[finding_id] = normalize(rule.get("rationale"))

    for group in config.get("restore_groups") or []:
        seeds = {normalize(value) for value in group.get("finding_ids") or []}
        expanded = _expanded_group_ids(decisions, seeds)
        invalid = sorted(
            finding_id
            for finding_id in expanded
            if normalize(decision_by_id.loc[finding_id, "second_pass_status"]) != "corrected"
        )
        if invalid:
            raise ValueError(f"Restore group includes non-corrected rows: {invalid[:10]}")
        for finding_id in expanded:
            restore_reasons[finding_id] = normalize(group.get("rationale"))

    hold_reasons: dict[str, str] = {}
    for group in config.get("hold_confirmed_groups") or []:
        ids = {normalize(value) for value in group.get("finding_ids") or []}
        if not ids <= sample_ids:
            raise ValueError(
                "Confirmation holds must be members of the deterministic QA sample: "
                f"{sorted(ids - sample_ids)[:10]}"
            )
        for finding_id in ids:
            hold_reasons[finding_id] = normalize(group.get("rationale"))

    source_resolutions: dict[str, dict] = {}
    for resolution in config.get("resolve_unresolved") or []:
        finding_id = normalize(resolution.get("finding_id"))
        if finding_id not in set(unresolved["finding_id"].astype(str)):
            raise ValueError(f"Source resolution is not an unresolved second-pass row: {finding_id}")
        source_resolutions[finding_id] = resolution
    if set(unresolved["finding_id"].astype(str)) != set(source_resolutions):
        raise ValueError("Every unresolved second-pass row must have a source-level resolution")

    restore_ids = set(restore_reasons)
    newly_held_ids = set(hold_reasons) | set(source_resolutions)
    if restore_ids & newly_held_ids:
        raise ValueError("A finding cannot be both restored and newly held")

    qa_scope_ids = set(corrected["finding_id"].astype(str)) | sample_ids | set(source_resolutions)
    qa_rows: list[dict] = []
    final_status_by_id: dict[str, str] = {}
    final_action_by_id: dict[str, str] = {}
    final_rationale_by_id: dict[str, str] = {}
    for finding_id in sorted(qa_scope_ids):
        row = decision_by_id.loc[finding_id].to_dict()
        prior_status = normalize(row.get("second_pass_status"))
        prior_action = normalize(row.get("second_pass_action"))
        if finding_id in restore_ids:
            qa_decision = "restore_second_pass_correction"
            final_status = "confirmed_current"
            final_action = "restore_after_release_qa"
            rationale = restore_reasons[finding_id]
        elif finding_id in hold_reasons:
            qa_decision = "hold_after_confirmation_sample_review"
            final_status = "corrected"
            final_action = "hold_after_confirmation_sample_review"
            rationale = hold_reasons[finding_id]
        elif finding_id in source_resolutions:
            qa_decision = "hold_after_source_level_review"
            final_status = "corrected"
            final_action = normalize(source_resolutions[finding_id].get("action"))
            rationale = normalize(source_resolutions[finding_id].get("rationale"))
        elif prior_status == "corrected":
            qa_decision = "accept_second_pass_correction"
            final_status = prior_status
            final_action = prior_action
            rationale = normalize(row.get("second_pass_rationale"))
        elif finding_id in sample_ids:
            qa_decision = "accept_second_pass_confirmation"
            final_status = prior_status
            final_action = prior_action
            rationale = normalize(row.get("second_pass_rationale"))
        else:
            raise AssertionError(f"Unexpected QA row: {finding_id}")
        final_status_by_id[finding_id] = final_status
        final_action_by_id[finding_id] = final_action
        final_rationale_by_id[finding_id] = rationale
        qa_rows.append(
            {
                **row,
                "qa_version": config["qa_version"],
                "qa_decision": qa_decision,
                "qa_final_status": final_status,
                "qa_final_action": final_action,
                "qa_rationale": rationale,
                "qa_reviewed_at": config["reviewed_at"],
                "qa_reviewer": config["reviewer"],
                "qa_in_confirmation_sample": finding_id in sample_ids,
            }
        )
    qa = pd.DataFrame(qa_rows)

    final_decisions = decisions.copy()
    final_decisions["release_qa_version"] = config["qa_version"]
    final_decisions["release_qa_reviewed"] = final_decisions["finding_id"].isin(qa_scope_ids)
    final_decisions["release_qa_decision"] = "not_in_release_qa_sample"
    final_decisions["final_status"] = final_decisions["second_pass_status"]
    final_decisions["final_action"] = final_decisions["second_pass_action"]
    final_decisions["final_rationale"] = final_decisions["second_pass_rationale"]
    final_decisions["final_reviewed_at"] = final_decisions["second_pass_reviewed_at"]
    final_decisions["final_reviewer"] = final_decisions["second_pass_reviewer"]
    qa_by_id = qa.set_index("finding_id")
    for index, row in final_decisions.iterrows():
        finding_id = str(row["finding_id"])
        if finding_id not in qa_by_id.index:
            continue
        reviewed = qa_by_id.loc[finding_id]
        final_decisions.at[index, "release_qa_decision"] = reviewed["qa_decision"]
        final_decisions.at[index, "final_status"] = reviewed["qa_final_status"]
        final_decisions.at[index, "final_action"] = reviewed["qa_final_action"]
        final_decisions.at[index, "final_rationale"] = reviewed["qa_rationale"]
        final_decisions.at[index, "final_reviewed_at"] = reviewed["qa_reviewed_at"]
        final_decisions.at[index, "final_reviewer"] = reviewed["qa_reviewer"]

    first_findings_by_id = first_findings.set_index("finding_id", drop=False)
    qa_fields = {
        "research_area_release_qa_version": config["qa_version"],
        "research_area_release_qa_reviewed_at": config["reviewed_at"],
        "research_area_release_qa_reviewer": config["reviewer"],
    }
    for field in (*qa_fields, "research_area_release_qa_decision", "research_area_release_qa_rationale"):
        if field not in findings.columns:
            findings[field] = ""
    for index, row in findings.iterrows():
        finding_id = str(row.get("finding_id", ""))
        if finding_id not in qa_scope_ids:
            continue
        for field, value in qa_fields.items():
            findings.at[index, field] = value
        findings.at[index, "research_area_release_qa_decision"] = qa_by_id.loc[finding_id, "qa_decision"]
        findings.at[index, "research_area_release_qa_rationale"] = final_rationale_by_id[finding_id]
        findings.at[index, "research_area_adjudication_status"] = final_status_by_id[finding_id]
        findings.at[index, "research_area_adjudication_action"] = final_action_by_id[finding_id]
        findings.at[index, "research_area_adjudication_rationale"] = final_rationale_by_id[finding_id]
        findings.at[index, "research_area_adjudication_reviewed_at"] = config["reviewed_at"]
        findings.at[index, "research_area_adjudication_reviewer"] = config["reviewer"]
        findings.at[index, "research_area_classification_origin"] = "agent_reviewed"
        if finding_id in restore_ids:
            original = first_findings_by_id.loc[finding_id]
            findings.at[index, "graph_admission_status"] = normalize(original.get("graph_admission_status")) or "main_graph"
            findings.at[index, "graph_admission_reason"] = normalize(original.get("graph_admission_reason")) or "semantically_complete"
        elif finding_id in newly_held_ids:
            findings.at[index, "graph_admission_status"] = "paper_detail"
            findings.at[index, "graph_admission_reason"] = "research_area_release_qa_hold_graph_edge"

    for field in (
        "release_qa_version",
        "release_qa_decision",
        "release_qa_rationale",
        "release_qa_reviewed_at",
        "release_qa_reviewer",
    ):
        if field not in adjudications.columns:
            adjudications[field] = ""
    for index, row in adjudications.iterrows():
        finding_id = str(row.get("finding_id", ""))
        if finding_id not in qa_scope_ids:
            continue
        adjudications.at[index, "adjudication_status"] = final_status_by_id[finding_id]
        adjudications.at[index, "adjudication_action"] = final_action_by_id[finding_id]
        adjudications.at[index, "adjudication_rationale"] = final_rationale_by_id[finding_id]
        adjudications.at[index, "adjudication_version"] = config["qa_version"]
        adjudications.at[index, "reviewed_at"] = config["reviewed_at"]
        adjudications.at[index, "reviewer"] = config["reviewer"]
        adjudications.at[index, "release_qa_version"] = config["qa_version"]
        adjudications.at[index, "release_qa_decision"] = qa_by_id.loc[finding_id, "qa_decision"]
        adjudications.at[index, "release_qa_rationale"] = final_rationale_by_id[finding_id]
        adjudications.at[index, "release_qa_reviewed_at"] = config["reviewed_at"]
        adjudications.at[index, "release_qa_reviewer"] = config["reviewer"]

    edge_rows_before = len(edges)
    if newly_held_ids:
        edges = edges.loc[~edges["finding_id"].astype(str).isin(newly_held_ids)].copy()
    restore_edges = first_edges.loc[first_edges["finding_id"].astype(str).isin(restore_ids)].copy()
    restored_edge_ids = set(restore_edges["finding_id"].astype(str))
    if restored_edge_ids != restore_ids:
        raise ValueError(f"Missing original edges for restored findings: {sorted(restore_ids - restored_edge_ids)[:10]}")
    existing_evidence_ids = set(edges["evidence_id"].astype(str))
    restore_edges = restore_edges.loc[~restore_edges["evidence_id"].astype(str).isin(existing_evidence_ids)]
    edges = pd.concat([edges, restore_edges], ignore_index=True).sort_values("evidence_id").reset_index(drop=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    for source in second_pass_dir.glob("*.parquet"):
        if source.name in {
            "findings.parquet",
            "evidence_edges.parquet",
            "research_area_adjudications.parquet",
            "research_area_second_pass_decisions.parquet",
        }:
            continue
        shutil.copy2(source, out_dir / source.name)
    _write(findings, out_dir / "findings.parquet")
    _write(edges, out_dir / "evidence_edges.parquet")
    _write(adjudications, out_dir / "research_area_adjudications.parquet")
    adjudications.to_csv(out_dir / "research_area_adjudications.csv", index=False)
    _write(final_decisions, out_dir / "research_area_final_decisions.parquet")
    final_decisions.to_csv(out_dir / "research_area_final_decisions.csv", index=False)
    _write(qa, out_dir / "research_area_release_qa.parquet")
    qa.to_csv(out_dir / "research_area_release_qa.csv", index=False)

    edge_ids = set(edges["finding_id"].astype(str))
    final_corrected_ids = set(
        final_decisions.loc[final_decisions["final_status"].eq("corrected"), "finding_id"].astype(str)
    )
    final_confirmed_ids = set(
        final_decisions.loc[final_decisions["final_status"].eq("confirmed_current"), "finding_id"].astype(str)
    )
    final_unresolved_ids = set(
        final_decisions.loc[final_decisions["final_status"].eq("unresolved"), "finding_id"].astype(str)
    )

    manifest = dict(source_manifest)
    manifest["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest["out_dir"] = str(out_dir.resolve())
    manifest["run_id"] = run_id
    tables = dict(manifest.get("tables") or {})
    for name in (
        "papers",
        "paper_funding",
        "paper_open_science_assertions",
        "entities",
        "findings",
        "evidence_edges",
        "normalization_audit",
        "research_area_review_queue",
        "research_area_adjudications",
        "research_area_final_decisions",
        "research_area_release_qa",
    ):
        path = out_dir / f"{name}.parquet"
        if path.exists():
            tables[name] = _table_manifest(path, Path.cwd())
    manifest["tables"] = tables
    manifest["graph_admission_counts"] = dict(
        Counter(findings["graph_admission_status"].fillna("").astype(str))
    )
    manifest["research_area_release_qa"] = {
        "version": config["qa_version"],
        "override_registry": str(overrides_path.resolve()),
        "source_second_pass_dir": str(second_pass_dir.resolve()),
        "reviewed_rows": int(len(qa)),
        "reviewed_second_pass_corrections": int(len(corrected)),
        "reviewed_confirmation_sample": int(len(sample)),
        "source_level_resolutions": int(len(source_resolutions)),
        "restored_findings": int(len(restore_ids)),
        "newly_held_findings": int(len(newly_held_ids)),
        "qa_decision_counts": qa["qa_decision"].value_counts().to_dict(),
        "final_scope_status_counts": final_decisions["final_status"].value_counts().to_dict(),
    }
    manifest["edge_counts_by_domain_kind_evidence"] = (
        edges.fillna("")
        .groupby(["domain", "entity_kind", "evidence_type"], dropna=False)
        .size()
        .rename("count")
        .reset_index()
        .to_dict(orient="records")
    )
    manifest["duckdb"] = {
        "status": "skipped",
        "reason": "Release-QA overlay writes audited Parquet tables; public exports read Parquet directly.",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    result = {
        "status": "ok",
        "run_id": run_id,
        "qa_version": config["qa_version"],
        "source_second_pass_dir": str(second_pass_dir.resolve()),
        "out_dir": str(out_dir.resolve()),
        "qa_rows": int(len(qa)),
        "reviewed_second_pass_corrections": int(len(corrected)),
        "reviewed_confirmation_sample": int(len(sample)),
        "source_level_resolutions": int(len(source_resolutions)),
        "restored_finding_ids": int(len(restore_ids)),
        "newly_held_finding_ids": int(len(newly_held_ids)),
        "edge_rows_before_release_qa": int(edge_rows_before),
        "edge_rows_after_release_qa": int(len(edges)),
        "edge_row_delta": int(len(edges) - edge_rows_before),
        "final_scope_status_counts": final_decisions["final_status"].value_counts().to_dict(),
        "combined_finding_status_counts": adjudications.loc[
            adjudications["record_type"].eq("finding"), "adjudication_status"
        ].value_counts().to_dict(),
        "remaining_second_pass_unresolved_ids": sorted(final_unresolved_ids),
        "integrity": {
            "final_corrected_edges_remaining": len(final_corrected_ids & edge_ids),
            "final_confirmed_edges_missing": len(final_confirmed_ids - edge_ids),
            "restored_edges_present": len(restore_ids & edge_ids),
            "newly_held_edges_remaining": len(newly_held_ids & edge_ids),
        },
        "active_release_changed": False,
    }
    (out_dir / "release_qa_manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--second-pass-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            materialize(
                second_pass_dir=args.second_pass_dir,
                out_dir=args.out_dir,
                overrides_path=args.overrides,
                run_id=args.run_id,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
