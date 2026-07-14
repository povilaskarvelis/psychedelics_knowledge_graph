#!/usr/bin/env python3
"""Write final graph decisions into the canonical one-row-per-DOI corpus ledger.

This is the only step allowed to reconcile a routed KG release with
``candidate_papers.parquet``. Public Methods outputs must read the resulting
corpus fields directly; they must not join graph tables or decision overrides.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_DISPOSITION_OVERRIDES = ROOT / "data" / "curated" / "graph_inclusion_disposition_overrides.json"

GRAPH_STATUS_COLUMNS = {
    "graph_inclusion_status": "",
    "graph_inclusion_disposition": "",
    "graph_inclusion_reason": "",
    "graph_inclusion_next_action": "",
    "graph_inclusion_decision_source": "",
    "graph_inclusion_run_id": "",
    "graph_inclusion_release_id": "",
    "graph_inclusion_updated_at_utc": "",
}

FINAL_DISPOSITIONS = {
    "represented",
    "not_reached",
    "adjudicated_outside_scope",
    "no_extractable_finding",
    "insufficient_source_text",
    "source_not_verified",
    "not_results_report",
    "unsupported_finding_detail",
}

AUDIT_NOT_GRAPHABLE_SUFFIXES = ("_not_graphable",)
AUDIT_UNMAPPED_SUFFIXES = ("_unmapped",)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = " ".join(str(value).split())
    return "" if text.lower() in {"nan", "none", "nat"} else text


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).lower() in {"1", "true", "yes", "y"}


def normalize_doi(value: object) -> str:
    doi = clean(value).lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix) :]
    return doi.strip()


def load_disposition_overrides(path: Path) -> dict[str, dict]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing final-disposition input: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("overrides"), list):
        raise ValueError(f"Invalid final-disposition input: {path}")
    out: dict[str, dict] = {}
    for group in payload["overrides"]:
        if not isinstance(group, dict):
            raise ValueError(f"Invalid final-disposition group in {path}")
        disposition = clean(group.get("disposition"))
        if disposition not in FINAL_DISPOSITIONS - {"represented", "not_reached"}:
            raise ValueError(f"Unsupported final disposition {disposition!r} in {path}")
        reason = clean(group.get("reason"))
        next_action = clean(group.get("next_action"))
        if not reason or not next_action:
            raise ValueError(f"Disposition {disposition!r} must have a reason and next action")
        for raw_doi in group.get("dois", []):
            doi = normalize_doi(raw_doi)
            if not doi:
                raise ValueError(f"Blank DOI in final-disposition input: {path}")
            if doi in out:
                raise ValueError(f"Duplicate final disposition for DOI {doi}")
            out[doi] = {
                "disposition": disposition,
                "reason": reason,
                "next_action": next_action,
            }
    return out


def load_represented_dois(kg_dir: Path) -> set[str]:
    findings_path = kg_dir / "findings.parquet"
    if not findings_path.is_file():
        raise FileNotFoundError(f"Missing routed findings table: {findings_path}")
    findings = pd.read_parquet(findings_path, columns=["study_doi"])
    return {
        doi
        for doi in (normalize_doi(value) for value in findings["study_doi"].tolist())
        if doi
    }


def load_audit_statuses(kg_dir: Path) -> dict[str, set[str]]:
    audit_path = kg_dir / "normalization_audit.parquet"
    if not audit_path.is_file():
        raise FileNotFoundError(f"Missing routed normalization audit: {audit_path}")
    audit = pd.read_parquet(audit_path, columns=["study_doi", "normalization_status"])
    out: dict[str, set[str]] = defaultdict(set)
    for row in audit.to_dict("records"):
        doi = normalize_doi(row.get("study_doi"))
        status = clean(row.get("normalization_status")).lower()
        if doi and status:
            out[doi].add(status)
    return dict(out)


def decision_from_audit(statuses: set[str]) -> dict:
    if any(status.endswith(AUDIT_UNMAPPED_SUFFIXES) for status in statuses):
        return {
            "disposition": "unsupported_finding_detail",
            "reason": (
                "The extraction produced a subject or entity label that could not be mapped "
                "consistently to a stable evidence concept."
            ),
            "next_action": "Retain the extraction for audit without adding an unstable graph concept.",
        }
    if any(status.endswith(AUDIT_NOT_GRAPHABLE_SUFFIXES) for status in statuses) or (
        "compound_out_of_scope_nonpsychedelic" in statuses
    ):
        return {
            "disposition": "no_extractable_finding",
            "reason": (
                "The completed extraction did not identify a sufficiently specific in-scope "
                "finding that can be represented in the evidence graph."
            ),
            "next_action": "Retain the report and its completed evidence-assessment result.",
        }
    raise ValueError(f"No final graph disposition is defined for audit statuses: {sorted(statuses)}")


def validate_candidate_ledger(df: pd.DataFrame) -> None:
    required = {
        "doi",
        "prescreen_retained_for_extraction_candidate",
        "retained_for_extraction_candidate",
        "extraction_route_status",
        *GRAPH_STATUS_COLUMNS,
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Canonical corpus is missing required decision columns: {missing}")

    normalized_dois = df["doi"].map(normalize_doi)
    if (normalized_dois == "").any():
        raise ValueError("Canonical corpus contains a blank DOI")
    duplicates = sorted(normalized_dois[normalized_dois.duplicated(keep=False)].unique())
    if duplicates:
        raise ValueError(f"Canonical corpus contains duplicate DOI rows: {duplicates[:10]}")

    errors: list[str] = []
    release_ids: set[str] = set()
    run_ids: set[str] = set()
    for row in df.to_dict("records"):
        doi = normalize_doi(row.get("doi"))
        prescreen_retained = truthy(row.get("prescreen_retained_for_extraction_candidate"))
        selected = truthy(row.get("retained_for_extraction_candidate"))
        route_status = clean(row.get("extraction_route_status"))
        graph_status = clean(row.get("graph_inclusion_status"))
        disposition = clean(row.get("graph_inclusion_disposition"))
        reason = clean(row.get("graph_inclusion_reason"))
        source = clean(row.get("graph_inclusion_decision_source"))
        run_id = clean(row.get("graph_inclusion_run_id"))
        release_id = clean(row.get("graph_inclusion_release_id"))
        updated_at = clean(row.get("graph_inclusion_updated_at_utc"))

        if run_id:
            run_ids.add(run_id)
        if release_id:
            release_ids.add(release_id)

        if selected and not prescreen_retained:
            errors.append(f"{doi}: selected without passing initial screening")
        if selected and not route_status.startswith(("ready_", "needs_pdf_", "hold_until_", "retained_")):
            errors.append(f"{doi}: selected with non-extraction route status {route_status!r}")
        if not selected and route_status.startswith(("ready_", "needs_pdf_", "hold_until_", "retained_")):
            errors.append(f"{doi}: not selected but has extraction-ready route status {route_status!r}")
        if disposition not in FINAL_DISPOSITIONS:
            errors.append(f"{doi}: invalid or missing graph disposition {disposition!r}")
        if not reason or not source or not run_id or not release_id or not updated_at:
            errors.append(f"{doi}: graph decision lacks a reason, release, timestamp, or provenance source")
        if selected and graph_status not in {"represented", "not_represented"}:
            errors.append(f"{doi}: selected report has graph status {graph_status!r}")
        if not selected and (graph_status != "not_reached" or disposition != "not_reached"):
            errors.append(f"{doi}: unselected report must have graph status/disposition not_reached")
        if graph_status == "represented" and disposition != "represented":
            errors.append(f"{doi}: represented status conflicts with disposition {disposition!r}")
        if graph_status == "not_represented" and disposition in {"represented", "not_reached"}:
            errors.append(f"{doi}: missing final non-representation disposition")
        if selected and disposition in {"adjudicated_outside_scope", "not_results_report"}:
            errors.append(f"{doi}: screening exclusion was left in the extraction-selected set")

    if len(run_ids) != 1:
        errors.append(f"canonical corpus must name exactly one graph run; found {sorted(run_ids)}")
    if len(release_ids) != 1:
        errors.append(f"canonical corpus must name exactly one graph release; found {sorted(release_ids)}")

    if errors:
        preview = "\n".join(errors[:25])
        suffix = f"\n... and {len(errors) - 25} more" if len(errors) > 25 else ""
        raise ValueError(f"Canonical corpus decision invariants failed:\n{preview}{suffix}")


def build_updated_corpus(
    candidate_df: pd.DataFrame,
    *,
    represented_dois: set[str],
    audit_statuses: dict[str, set[str]],
    disposition_overrides: dict[str, dict],
    run_id: str,
    release_id: str,
    updated_at_utc: str,
) -> pd.DataFrame:
    df = candidate_df.copy()
    for column, default in GRAPH_STATUS_COLUMNS.items():
        if column not in df.columns:
            df[column] = default

    records: list[dict] = []
    unused_overrides = set(disposition_overrides)
    for row in df.to_dict("records"):
        doi = normalize_doi(row.get("doi"))
        selected = truthy(row.get("retained_for_extraction_candidate"))
        if not selected:
            decision = {
                "status": "not_reached",
                "disposition": "not_reached",
                "reason": "The report was not selected for evidence extraction.",
                "next_action": "No graph-inclusion action is required.",
                "source": "canonical_screening_and_routing_decision",
            }
        elif doi in represented_dois:
            decision = {
                "status": "represented",
                "disposition": "represented",
                "reason": "At least one normalized finding from this report is present in the evidence graph.",
                "next_action": "No action needed.",
                "source": "routed_kg_findings",
            }
        elif doi in disposition_overrides:
            override = disposition_overrides[doi]
            unused_overrides.discard(doi)
            decision = {
                "status": "not_represented",
                **override,
                "source": "curated_final_disposition",
            }
        elif doi in audit_statuses:
            decision = {
                "status": "not_represented",
                **decision_from_audit(audit_statuses[doi]),
                "source": "routed_normalization_audit",
            }
        else:
            raise ValueError(
                f"Selected report {doi} is not represented and has neither an explicit final "
                "disposition nor a recognized normalization-audit decision"
            )

        row.update(
            {
                "graph_inclusion_status": decision["status"],
                "graph_inclusion_disposition": decision["disposition"],
                "graph_inclusion_reason": decision["reason"],
                "graph_inclusion_next_action": decision["next_action"],
                "graph_inclusion_decision_source": decision["source"],
                "graph_inclusion_run_id": run_id,
                "graph_inclusion_release_id": release_id,
                "graph_inclusion_updated_at_utc": updated_at_utc,
            }
        )
        records.append(row)

    if unused_overrides:
        preview = sorted(unused_overrides)[:20]
        raise ValueError(
            "Final-disposition input contains reports that are not selected-and-missing in this release: "
            f"{preview}"
        )

    out = pd.DataFrame(records)
    validate_candidate_ledger(out)
    return out


def write_parquet_atomic(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        df.to_parquet(temp_path, index=False)
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def update_corpus_graph_status(
    *,
    candidate_table: Path,
    output_table: Path,
    kg_dir: Path,
    disposition_overrides: Path,
    run_id: str,
    release_id: str,
) -> dict:
    if not candidate_table.is_file():
        raise FileNotFoundError(f"Missing canonical corpus table: {candidate_table}")
    if not clean(run_id) or not clean(release_id):
        raise ValueError("run_id and release_id are required")
    candidate_df = pd.read_parquet(candidate_table)
    updated_at = now_utc()
    out = build_updated_corpus(
        candidate_df,
        represented_dois=load_represented_dois(kg_dir),
        audit_statuses=load_audit_statuses(kg_dir),
        disposition_overrides=load_disposition_overrides(disposition_overrides),
        run_id=clean(run_id),
        release_id=clean(release_id),
        updated_at_utc=updated_at,
    )
    write_parquet_atomic(out, output_table)
    counts = out["graph_inclusion_disposition"].value_counts().to_dict()
    return {
        "rows": len(out),
        "output_table": str(output_table),
        "run_id": clean(run_id),
        "release_id": clean(release_id),
        "by_disposition": counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--output-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--kg-dir", required=True)
    parser.add_argument("--disposition-overrides", default=str(DEFAULT_DISPOSITION_OVERRIDES))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--release-id", required=True)
    args = parser.parse_args()
    result = update_corpus_graph_status(
        candidate_table=Path(args.candidate_table).resolve(),
        output_table=Path(args.output_table).resolve(),
        kg_dir=Path(args.kg_dir).resolve(),
        disposition_overrides=Path(args.disposition_overrides).resolve(),
        run_id=args.run_id,
        release_id=args.release_id,
    )
    print(f"Canonical corpus rows: {result['rows']:,}")
    print(f"Final graph decisions: {result['by_disposition']}")
    print(f"Corpus table: {result['output_table']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
