#!/usr/bin/env python3
"""Reconcile a supervised browser-recovery batch with imported PDFs and format findings."""

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

from pipeline.ingest.metadata_utils import normalize_doi
from pipeline.validate.doi_aliases import DEFAULT_DOI_ALIAS_REGISTRY, load_doi_aliases


DEFAULT_ACCESS_OVERRIDES = ROOT / "pipeline" / "fulltext" / "manual_fulltext_access_overrides.json"
DEFAULT_FORMAT_EXCLUSIONS = ROOT / "data" / "curated" / "prescreen_publication_format_exclusions.json"
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"


def clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def doi_set_from_import_report(payload: dict) -> set[str]:
    # A conflict means the newly downloaded bytes differed, but the importer
    # only emits that status when a canonical PDF for the DOI already exists.
    # The browser-recovery objective is therefore already satisfied even
    # though the alternate file remains quarantined for review.
    accepted = {"matched", "already_present", "replaced_existing_pdf", "conflict_existing_pdf"}
    return {
        normalize_doi(row.get("doi", ""))
        for row in [*payload.get("imported", []), *payload.get("review", [])]
        if clean(row.get("status", "")) in accepted and normalize_doi(row.get("doi", ""))
    }


def merge_import_reports(payloads: list[dict]) -> dict:
    """Combine importer audits from interrupted or multi-pass browser batches."""
    return {
        "imported": [row for payload in payloads for row in payload.get("imported", [])],
        "review": [row for payload in payloads for row in payload.get("review", [])],
    }


def reconcile(
    batch: pd.DataFrame,
    import_report: dict,
    format_payload: dict,
    doi_aliases: dict[str, str] | None = None,
    *,
    finalize_partial_review: bool = False,
) -> tuple[pd.DataFrame, dict]:
    imported = doi_set_from_import_report(import_report)
    aliases = doi_aliases or {}
    exclusions = {
        normalize_doi(row.get("doi", "")): row
        for row in format_payload.get("records", [])
        if normalize_doi(row.get("doi", ""))
    }
    batch_dois = {normalize_doi(value) for value in batch["doi"] if normalize_doi(value)}
    rows: list[dict] = []
    for row in batch.fillna("").to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        if doi in imported:
            status = "article_pdf_recovered"
            detail = "Validated PDF imported or already present."
        elif doi in aliases and aliases[doi] in imported:
            status = "duplicate_of_canonical"
            detail = f"Alias/repository DOI duplicates canonical DOI {aliases[doi]}, whose PDF is already present."
        elif doi in exclusions:
            status = "excluded_publication_format"
            detail = clean(exclusions[doi].get("publication_format", ""))
        elif clean(row.get("manual_status", "")).lower() == "closed_access":
            status = "confirmed_closed_access"
            detail = "Manual DOI-page review explicitly confirmed that the article is closed access."
        elif clean(row.get("manual_status", "")).lower() == "batch_closed_access":
            status = "batch_closed_access"
            detail = clean(row.get("manual_notes", "")) or (
                "User-directed closeout of the remaining manual-recovery queue; "
                "no accessible article PDF will be pursued further."
            )
        elif clean(row.get("manual_status", "")).lower() in {
            "partial_review_rate_limited",
            "opened_for_manual_review",
            "reviewed_pending_pdf_reconciliation",
            "",
        }:
            status = "pending_manual_review"
            detail = (
                "No validated PDF or explicit terminal access outcome is recorded. "
                "Do not infer closed access from an absent download."
            )
        else:
            status = "technical_or_unresolved_retrieval"
            detail = (
                f"Retrieval outcome {clean(row.get('manual_status', ''))!r} is not an eligibility or "
                "terminal access decision; retain it in the retry/progress ledger."
            )
        rows.append({**row, "browser_recovery_status": status, "browser_recovery_detail": detail})

    outcome = pd.DataFrame(rows)
    extra_imports = sorted(imported - batch_dois)
    report = {
        "schema_version": "browser_recovery_batch_reconciliation_v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "batch_rows": len(outcome),
        "status_counts": dict(Counter(outcome["browser_recovery_status"])),
        "extra_imported_dois_not_in_batch": extra_imports,
    }
    return outcome, report


def apply_access_overrides(path: Path, outcome: pd.DataFrame) -> int:
    payload = load_json(path) if path.is_file() else {
        "schema_version": "manual_fulltext_access_overrides_v1",
        "notes": [],
        "records": [],
    }
    records = {
        normalize_doi(row.get("doi", "")): row
        for row in payload.get("records", [])
        if normalize_doi(row.get("doi", ""))
    }
    changed = 0
    for row in outcome.to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        status = clean(row.get("browser_recovery_status", ""))
        if status in {"article_pdf_recovered", "duplicate_of_canonical"}:
            # Positive recovery evidence supersedes an older suppression.
            if doi in records:
                del records[doi]
                changed += 1
            continue
        if status not in {"confirmed_closed_access", "batch_closed_access"}:
            # Pending and technical outcomes do not overwrite or erase a
            # previously curated access decision.
            continue
        if status == "batch_closed_access":
            reason = (
                clean(row.get("browser_recovery_detail", ""))
                + " Suppress repeated PDF retrieval and use abstract-level extraction when available."
            ).strip()
        else:
            reason = (
                "Manual DOI-page review explicitly confirmed that no openly accessible article PDF is available. "
                "Suppress repeated PDF retrieval and use abstract-level extraction when available."
            )
        replacement = {
            "doi": doi,
            "manual_access_action": "suppress_pdf_download",
            "open_access_status": "closed",
            "open_access_is_oa": False,
            "manual_reason": reason,
        }
        if records.get(doi) != replacement:
            records[doi] = replacement
            changed += 1
    payload["records"] = [records[doi] for doi in sorted(records)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return changed


def project_access_overrides_to_candidate(
    override_path: Path,
    candidate_path: Path,
    outcome: pd.DataFrame,
) -> int:
    """Project only explicit terminal access outcomes into candidate_papers."""

    if not candidate_path.is_file():
        return 0
    payload = load_json(override_path)
    overrides = {
        normalize_doi(row.get("doi", "")): row
        for row in payload.get("records", [])
        if normalize_doi(row.get("doi", ""))
    }
    terminal = {
        normalize_doi(row.get("doi", ""))
        for row in outcome.to_dict("records")
        if clean(row.get("browser_recovery_status", ""))
        in {
            "article_pdf_recovered",
            "duplicate_of_canonical",
            "confirmed_closed_access",
            "batch_closed_access",
        }
        and normalize_doi(row.get("doi", ""))
    }
    if not terminal:
        return 0
    candidate = pd.read_parquet(candidate_path)
    for column in ("manual_fulltext_access_action", "manual_fulltext_access_reason"):
        if column not in candidate.columns:
            candidate[column] = ""
    changed = 0
    for index, raw_doi in candidate["doi"].items():
        doi = normalize_doi(raw_doi)
        if doi not in terminal:
            continue
        record = overrides.get(doi, {})
        action = clean(record.get("manual_access_action", ""))
        reason = clean(record.get("manual_reason", ""))
        if (
            clean(candidate.at[index, "manual_fulltext_access_action"]) != action
            or clean(candidate.at[index, "manual_fulltext_access_reason"]) != reason
        ):
            candidate.at[index, "manual_fulltext_access_action"] = action
            candidate.at[index, "manual_fulltext_access_reason"] = reason
            changed += 1
    if changed:
        candidate.to_parquet(candidate_path, engine="pyarrow", index=False)
    return changed


def apply_progress_updates(path: Path, outcome: pd.DataFrame) -> int:
    """Write reconciled terminal outcomes back to the browser progress ledger."""
    if not path.is_file():
        return 0
    progress = pd.read_csv(path).fillna("")
    if "doi" not in progress.columns:
        return 0
    outcome_by_doi = {
        normalize_doi(row.get("doi", "")): row
        for row in outcome.fillna("").to_dict("records")
        if normalize_doi(row.get("doi", ""))
    }
    status_map = {
        "article_pdf_recovered": "article_pdf_recovered",
        "duplicate_of_canonical": "duplicate_of_canonical",
        "excluded_publication_format": "excluded_publication_format",
        "confirmed_closed_access": "closed_access",
        "batch_closed_access": "closed_access",
        "pending_manual_review": "partial_review_rate_limited",
        "technical_or_unresolved_retrieval": "technical_failure_retryable",
    }
    changed = 0
    for index, row in progress.iterrows():
        reconciled = outcome_by_doi.get(normalize_doi(row.get("doi", "")))
        if not reconciled:
            continue
        status = status_map[clean(reconciled.get("browser_recovery_status", ""))]
        notes = clean(reconciled.get("browser_recovery_detail", ""))
        if clean(progress.at[index, "manual_status"]) != status or clean(progress.at[index, "manual_notes"]) != notes:
            progress.at[index, "manual_status"] = status
            progress.at[index, "manual_notes"] = notes
            changed += 1
    if changed:
        progress.to_csv(path, index=False)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-csv", required=True)
    parser.add_argument(
        "--import-report",
        required=True,
        action="append",
        help="Importer audit JSON; repeat for late downloads or multi-pass imports.",
    )
    parser.add_argument("--format-exclusions", default=str(DEFAULT_FORMAT_EXCLUSIONS))
    parser.add_argument("--access-overrides", default=str(DEFAULT_ACCESS_OVERRIDES))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--doi-alias-registry", default=str(DEFAULT_DOI_ALIAS_REGISTRY))
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--apply-access-overrides", action="store_true")
    parser.add_argument(
        "--finalize-partial-review",
        action="store_true",
        help=(
            "Deprecated compatibility flag. Interrupted rows remain pending unless their "
            "per-record manual_status explicitly confirms a terminal outcome."
        ),
    )
    parser.add_argument(
        "--update-progress-ledger",
        default="",
        help="Optional browser progress CSV whose matching DOI statuses should be reconciled in place.",
    )
    args = parser.parse_args()

    outcome, report = reconcile(
        pd.read_csv(Path(args.batch_csv).resolve()),
        merge_import_reports(
            [load_json(Path(report_path).resolve()) for report_path in args.import_report]
        ),
        load_json(Path(args.format_exclusions).resolve()),
        load_doi_aliases(Path(args.doi_alias_registry).resolve()),
        finalize_partial_review=bool(args.finalize_partial_review),
    )
    output_csv = Path(args.output_csv).resolve()
    report_json = Path(args.report_json).resolve()
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    report_json.parent.mkdir(parents=True, exist_ok=True)
    outcome.to_csv(output_csv, index=False)
    changed = 0
    if args.apply_access_overrides:
        changed = apply_access_overrides(Path(args.access_overrides).resolve(), outcome)
    report["access_overrides_changed"] = changed
    candidate_changed = 0
    if args.apply_access_overrides:
        candidate_changed = project_access_overrides_to_candidate(
            Path(args.access_overrides).resolve(),
            Path(args.candidate_table).resolve(),
            outcome,
        )
    report["candidate_access_rows_changed"] = candidate_changed
    progress_changed = 0
    if args.update_progress_ledger.strip():
        progress_changed = apply_progress_updates(Path(args.update_progress_ledger).resolve(), outcome)
    report["progress_rows_updated"] = progress_changed
    report["output_csv"] = str(output_csv)
    report_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
