#!/usr/bin/env python3
"""Apply confirmed post-retrieval eligibility decisions without rewriting prescreen history.

Landing pages and retrieved documents expose evidence that did not exist at
title/abstract prescreening time.  This stage owns that later evidence.  It
updates dedicated candidate columns, invalidates downstream active views for
confirmed exclusions, and deliberately ignores access or technical failures.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.candidate_status import normalize_doi  # noqa: E402
from pipeline.workflow.decision_state import (  # noqa: E402
    ActiveArtifact,
    reconcile_workflow_decision,
    truthy,
    write_parquet_atomic,
)


DEFAULT_LEDGER = ROOT / "data" / "curated" / "post_retrieval_eligibility_decisions.json"
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_DECISIONS_TABLE = (
    ROOT / "data" / "processed" / "corpus" / "paper_post_retrieval_eligibility_decisions.parquet"
)
DEFAULT_DOMAIN_ROUTING_TABLE = (
    ROOT / "data" / "processed" / "corpus" / "paper_domain_routing_gemini.parquet"
)
DEFAULT_EXTRACTION_ROUTES_TABLE = (
    ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes.parquet"
)
DEFAULT_EXTRACTION_TASKS_JSONL = (
    ROOT / "data" / "processed" / "extraction" / "route_extraction_tasks.jsonl"
)
DEFAULT_REPORT = (
    ROOT
    / "data"
    / "processed"
    / "corpus"
    / "audits"
    / "post_retrieval_eligibility_reconciliation.json"
)

TABLE_VERSION = "1.0"
STAGE_NAME = "post_retrieval_eligibility"
ALLOWED_DECISIONS = {"retain", "exclude"}
CANDIDATE_DEFAULTS = {
    "post_retrieval_decision": "",
    "post_retrieval_reason": "",
    "post_retrieval_reason_code": "",
    "post_retrieval_publication_format": "",
    "post_retrieval_evidence": "",
    "post_retrieval_decision_method": "",
    "post_retrieval_reviewer": "",
    "post_retrieval_source_artifact": "",
    "post_retrieval_run_id": "",
    "post_retrieval_updated_at_utc": "",
    "pipeline_exclusion_stage": "",
    "pipeline_exclusion_reason": "",
    "pipeline_exclusion_decision_source": "",
}


def clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_decision_ledger(path: Path) -> dict[str, dict]:
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    records: dict[str, dict] = {}
    for raw in payload.get("records", []):
        if not isinstance(raw, dict):
            continue
        doi = normalize_doi(raw.get("doi", ""))
        decision = clean(raw.get("decision", "")).lower()
        if not doi:
            continue
        if decision not in ALLOWED_DECISIONS:
            raise ValueError(f"Unsupported post-retrieval decision for {doi}: {decision!r}")
        record = dict(raw)
        record["doi"] = doi
        record["decision"] = decision
        records[doi] = record
    return records


def select_format_screen_scope(
    candidate_df: pd.DataFrame,
    decisions: dict[str, dict],
    *,
    requested_dois: set[str] | None = None,
) -> dict[str, object]:
    candidate_dois = {
        normalize_doi(value)
        for value in candidate_df.get("doi", pd.Series(dtype=str))
        if normalize_doi(value)
    }
    confirmed = set(decisions)
    requested = {
        normalize_doi(value) for value in (requested_dois if requested_dois is not None else confirmed)
    }
    requested.discard("")
    unconfirmed = sorted(requested - confirmed)
    missing = sorted((requested & confirmed) - candidate_dois)
    present = sorted(requested & confirmed & candidate_dois)
    already_applied: list[str] = []
    pending: list[str] = []
    current = candidate_df.copy()
    if "post_retrieval_decision" not in current.columns:
        current["post_retrieval_decision"] = ""
    current["_doi_key"] = current["doi"].map(normalize_doi)
    current_by_doi = current.drop_duplicates("_doi_key", keep="last").set_index("_doi_key")
    for doi in present:
        prior = clean(current_by_doi.at[doi, "post_retrieval_decision"]).lower()
        if prior == clean(decisions[doi].get("decision", "")).lower():
            already_applied.append(doi)
        else:
            pending.append(doi)
    return {
        "requested_dois": sorted(requested),
        "present_dois": present,
        "pending_dois": pending,
        "already_applied_dois": already_applied,
        "missing_candidate_dois": missing,
        "unconfirmed_dois": unconfirmed,
    }


def format_counts(dois: list[str], decisions: dict[str, dict]) -> dict[str, int]:
    return dict(
        sorted(
            Counter(
                clean(decisions[doi].get("publication_format", "")) or "unspecified"
                for doi in dois
            ).items()
        )
    )


def decision_frame(records: list[dict], *, generated_at_utc: str, run_id: str) -> pd.DataFrame:
    rows: list[dict] = []
    for record in records:
        decision = clean(record.get("decision", "")).lower()
        reason = clean(record.get("reason", ""))
        rows.append(
            {
                "table_version": TABLE_VERSION,
                "doi": normalize_doi(record.get("doi", "")),
                "decision": decision,
                "reason_code": clean(record.get("reason_code", "")),
                "publication_format": clean(record.get("publication_format", "")),
                "reason": reason,
                "evidence": clean(record.get("evidence", record.get("evidence_basis", ""))),
                "decision_method": clean(record.get("decision_method", "post_retrieval_document_review")),
                "reviewer": clean(record.get("reviewer", "curated_pipeline_review")),
                "source_artifact": clean(record.get("source_artifact", "")),
                "run_id": clean(record.get("run_id", "")) or run_id,
                "decided_at_utc": clean(record.get("decided_at_utc", "")) or generated_at_utc,
            }
        )
    return pd.DataFrame(rows)


def candidate_updates(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for row in frame.fillna("").to_dict("records"):
        excluded = clean(row.get("decision", "")).lower() == "exclude"
        rows.append(
            {
                "doi": normalize_doi(row.get("doi", "")),
                "post_retrieval_decision": clean(row.get("decision", "")).lower(),
                "post_retrieval_reason": clean(row.get("reason", "")),
                "post_retrieval_reason_code": clean(row.get("reason_code", "")),
                "post_retrieval_publication_format": clean(row.get("publication_format", "")),
                "post_retrieval_evidence": clean(row.get("evidence", "")),
                "post_retrieval_decision_method": clean(row.get("decision_method", "")),
                "post_retrieval_reviewer": clean(row.get("reviewer", "")),
                "post_retrieval_source_artifact": clean(row.get("source_artifact", "")),
                "post_retrieval_run_id": clean(row.get("run_id", "")),
                "post_retrieval_updated_at_utc": clean(row.get("decided_at_utc", "")),
                "pipeline_exclusion_stage": STAGE_NAME if excluded else "",
                "pipeline_exclusion_reason": clean(row.get("reason", "")) if excluded else "",
                "pipeline_exclusion_decision_source": "post_retrieval_decision_ledger" if excluded else "",
            }
        )
    return pd.DataFrame(rows)


def downstream_eligible_dois(candidate_df: pd.DataFrame, decisions: dict[str, dict]) -> set[str]:
    if "doi" not in candidate_df.columns:
        return set()
    if "retained_for_extraction_candidate" in candidate_df.columns:
        base_mask = candidate_df["retained_for_extraction_candidate"].map(truthy)
    else:
        base_mask = pd.Series(True, index=candidate_df.index)
    allowed = {
        normalize_doi(value)
        for value in candidate_df.loc[base_mask, "doi"]
        if normalize_doi(value)
    }
    excluded = {
        doi for doi, row in decisions.items() if clean(row.get("decision", "")).lower() == "exclude"
    }
    return allowed - excluded


def run(args: argparse.Namespace) -> dict[str, object]:
    candidate_path = Path(args.candidate_table).resolve()
    decisions_path = Path(args.decisions_table).resolve()
    ledger_path = Path(args.ledger).resolve()
    candidate_df = pd.read_parquet(candidate_path)
    decisions = load_decision_ledger(ledger_path)
    requested = {normalize_doi(value) for value in args.doi if normalize_doi(value)} or None
    scope = select_format_screen_scope(candidate_df, decisions, requested_dois=requested)
    if scope["unconfirmed_dois"]:
        raise SystemExit(
            "Requested DOI(s) lack an authoritative post-retrieval decision: "
            f"{scope['unconfirmed_dois'][:20]}"
        )

    present = list(scope["present_dois"])
    generated_at = now_utc()
    run_id = clean(args.run_id) or "post_retrieval_eligibility_" + dt.datetime.now(
        dt.timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")
    current_frame = decision_frame(
        [decisions[doi] for doi in present], generated_at_utc=generated_at, run_id=run_id
    )
    complete_decision_frame = decision_frame(
        [decisions[doi] for doi in sorted(decisions)],
        generated_at_utc=generated_at,
        run_id=run_id,
    )
    result: dict[str, object] = {
        **scope,
        "decision_counts": dict(Counter(current_frame.get("decision", []))),
        "format_counts": format_counts(present, decisions),
        "candidate_table": str(candidate_path),
        "decisions_table": str(decisions_path),
        "ledger": str(ledger_path),
        "apply": bool(args.apply),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not args.apply:
        print("Dry run only; pass --apply to update the dedicated decision stage and candidate view.")
        return result

    decisions_path.parent.mkdir(parents=True, exist_ok=True)
    # A DOI-scoped reconciliation must not truncate the authoritative table to
    # only the requested subset. Candidate/downstream mutations remain scoped,
    # while the materialized decision table always mirrors the complete ledger.
    write_parquet_atomic(complete_decision_frame, decisions_path)

    previous_included = {
        doi
        for doi in present
        if clean(
            candidate_df.loc[
                candidate_df["doi"].map(normalize_doi).eq(doi),
                "post_retrieval_decision",
            ].iloc[-1]
            if "post_retrieval_decision" in candidate_df.columns
            else ""
        ).lower()
        != "exclude"
    }
    current_included = {
        doi
        for doi in present
        if clean(decisions[doi].get("decision", "")).lower() == "retain"
    }
    active_artifacts: list[ActiveArtifact] = []
    for raw_path, kind in (
        (args.domain_routing_table, "parquet"),
        (args.extraction_routes_table, "parquet"),
        (args.extraction_tasks_jsonl, "jsonl"),
    ):
        if clean(raw_path):
            active_artifacts.append(ActiveArtifact(Path(raw_path), kind=kind))

    reconciliation = reconcile_workflow_decision(
        candidate_table=candidate_path,
        decision_updates=candidate_updates(current_frame),
        update_defaults=CANDIDATE_DEFAULTS,
        stage="post_retrieval",
        previous_included_dois=previous_included,
        current_included_dois=current_included,
        active_artifacts=active_artifacts,
        active_artifact_allowed_dois=downstream_eligible_dois(candidate_df, decisions),
        pending_status="post_retrieval_retained_pending_extraction",
        excluded_status="post_retrieval_excluded",
        report_path=Path(args.report).resolve(),
        context={
            "stage_name": STAGE_NAME,
            "decision_ledger": str(ledger_path),
            "decisions_table": str(decisions_path),
            "run_id": run_id,
            "technical_failure_policy": "retrieval_attempt_ledger_only_not_candidate_decision",
        },
    )
    result["reconciliation"] = reconciliation
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--decisions-table", default=str(DEFAULT_DECISIONS_TABLE))
    parser.add_argument("--domain-routing-table", default=str(DEFAULT_DOMAIN_ROUTING_TABLE))
    parser.add_argument("--extraction-routes-table", default=str(DEFAULT_EXTRACTION_ROUTES_TABLE))
    parser.add_argument("--extraction-tasks-jsonl", default=str(DEFAULT_EXTRACTION_TASKS_JSONL))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--run-id", default="")
    parser.add_argument("--doi", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    run(build_arg_parser().parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
