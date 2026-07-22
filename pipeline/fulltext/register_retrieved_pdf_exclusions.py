#!/usr/bin/env python3
"""Register confirmed post-retrieval publication-format exclusions.

Only positive eligibility evidence is promoted.  Paywalls, absent downloads,
timeouts, WAF responses, and other retrieval failures are intentionally not
accepted by this command and remain in retrieval attempt logs/queues.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIT = (
    ROOT / "data" / "processed" / "corpus" / "audits" / "doi_browser_pdf_publication_format_audit.csv"
)
DEFAULT_LEDGER = ROOT / "data" / "curated" / "post_retrieval_eligibility_decisions.json"
ALLOWED_FORMATS = {
    "conference_abstract",
    "conference_poster",
    "dissertation_or_thesis",
    "non_english_article",
    "correspondence_or_letter",
    "out_of_scope_article",
    "book_or_monograph",
    "dataset_or_data_deposit",
    "commentary_or_editorial",
    "preprint_or_unpublished",
}
def clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def normalize_doi(value: object) -> str:
    text = clean(value).lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    return text.rstrip(".,; ")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def reason_for(publication_format: str) -> str:
    return {
        "conference_abstract": (
            "The retrieved record is a conference, congress, meeting, or poster abstract rather "
            "than an eligible source article, review, or meta-analysis."
        ),
        "conference_poster": (
            "The retrieved record is a conference poster rather than an eligible source article, "
            "review, or meta-analysis."
        ),
        "dissertation_or_thesis": (
            "The retrieved record is a dissertation or thesis rather than an eligible published "
            "article, review, or meta-analysis."
        ),
        "non_english_article": (
            "The retrieved article is not in English and is outside the project's eligible "
            "publication-language scope."
        ),
        "correspondence_or_letter": (
            "The retrieved record is correspondence or a letter to the editor rather than an "
            "eligible source article, review, or meta-analysis."
        ),
        "out_of_scope_article": (
            "The retrieved article is outside the project's substantive eligibility scope."
        ),
        "book_or_monograph": (
            "The retrieved record is a book or monograph rather than an eligible source article, "
            "review, or meta-analysis."
        ),
        "dataset_or_data_deposit": (
            "The retrieved record is a dataset or data deposit rather than an eligible source "
            "article, review, or meta-analysis."
        ),
        "commentary_or_editorial": (
            "The retrieved record is a commentary, response, or editorial rather than an eligible "
            "source article, review, or meta-analysis."
        ),
        "preprint_or_unpublished": (
            "The retrieved record is a preprint or unpublished posted-content record rather than "
            "an eligible published article, review, or meta-analysis."
        ),
    }[publication_format]


def audit_exclusions(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    audit = pd.read_csv(path).fillna("")
    required = {"doi", "recommended_action", "publication_format"}
    if not required.issubset(audit.columns):
        raise ValueError(f"Audit is missing required columns {sorted(required - set(audit.columns))}: {path}")
    selected = audit[
        audit["recommended_action"].eq("exclude_publication_format")
        & audit["publication_format"].isin(ALLOWED_FORMATS)
        & audit["doi"].astype(str).str.strip().ne("")
    ].drop_duplicates("doi", keep="last")
    rows: list[dict] = []
    for row in selected.to_dict("records"):
        publication_format = clean(row.get("publication_format", ""))
        rows.append(
            {
                "doi": normalize_doi(row.get("doi", "")),
                "decision": "exclude",
                "reason_code": publication_format,
                "publication_format": publication_format,
                "reason": reason_for(publication_format),
                "evidence": clean(row.get("format_evidence", ""))
                or clean(row.get("evidence_excerpt", ""))
                or "Direct retrieved-document inspection",
                "decision_method": clean(row.get("decision_method", ""))
                or "post_retrieval_document_audit",
                "reviewer": clean(row.get("reviewer", "")) or "curated_pipeline_review",
                "source_artifact": str(path.resolve()),
            }
        )
    return rows


def legacy_post_retrieval_exclusions(path: Path) -> list[dict]:
    """Migrate every DOI-specific legacy decision out of deterministic prescreen.

    Deterministic prescreen owns reusable rules over canonical metadata. A
    reviewed DOI-level exception remains a valid eligibility decision, but its
    provenance belongs in the dedicated later eligibility ledger regardless of
    whether the evidence came from a provider record, landing page, or document.
    """

    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for raw in payload.get("records", []):
        if not isinstance(raw, dict):
            continue
        doi = normalize_doi(raw.get("doi", ""))
        evidence = clean(raw.get("evidence_basis", ""))
        publication_format = clean(raw.get("publication_format", ""))
        if not doi or not evidence:
            continue
        rows.append(
            {
                "doi": doi,
                "decision": "exclude",
                "reason_code": publication_format,
                "publication_format": publication_format,
                "reason": clean(raw.get("reason", ""))
                or f"The later document/landing-page review identified an ineligible {publication_format} record.",
                "evidence": evidence,
                "decision_method": "legacy_curated_post_retrieval_evidence_migration",
                "reviewer": "curated_pipeline_review",
                "source_artifact": str(path.resolve()),
            }
        )
    return rows


def annotate_legacy_migrations(path: Path, migrated_dois: set[str], target_ledger: Path) -> int:
    if not path.is_file() or not migrated_dois:
        return 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    for record in payload.get("records", []):
        if not isinstance(record, dict) or normalize_doi(record.get("doi", "")) not in migrated_dois:
            continue
        if record.get("decision_stage") != "post_retrieval_eligibility":
            record["decision_stage"] = "post_retrieval_eligibility"
            changed += 1
        record["current_decision_ledger"] = str(target_ledger.resolve())
    if changed:
        payload["updated_at_utc"] = now_utc()
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return changed


def browser_url_exclusions(payloads: list[dict], *, source_paths: list[Path] | None = None) -> list[dict]:
    """Select only deterministic poster URL outcomes emitted by the DOI browser."""

    selected: dict[str, dict] = {}
    paths: list[Path | None] = list(source_paths) if source_paths is not None else [None for _ in payloads]
    for payload, source_path in zip(payloads, paths):
        for row in payload.get("records", []):
            doi = normalize_doi(row.get("doi", ""))
            publication_format = clean(row.get("publication_format", ""))
            evidence_url = clean(row.get("evidence_url", ""))
            if (
                doi
                and clean(row.get("status", "")) == "excluded_publication_format"
                and publication_format == "conference_poster"
                and evidence_url
            ):
                selected[doi] = {
                    "doi": doi,
                    "decision": "exclude",
                    "reason_code": publication_format,
                    "publication_format": publication_format,
                    "reason": reason_for(publication_format),
                    "evidence": (
                        "DOI landing-page URL deterministically identifies a poster record: "
                        f"{evidence_url} ({clean(row.get('reason', '')) or 'explicit poster path'})"
                    ),
                    "decision_method": "deterministic_landing_url_format_rule",
                    "reviewer": "pipeline_rule",
                    "source_artifact": str(source_path.resolve()) if source_path is not None else "",
                }
    return [selected[doi] for doi in sorted(selected)]


def load_ledger(path: Path) -> dict:
    if not path.is_file():
        return {
            "schema_version": "post_retrieval_eligibility_decisions_v1",
            "policy": (
                "Confirmed DOI-level eligibility decisions based on landing pages or retrieved documents. "
                "Retrieval failures and access outcomes are excluded from this ledger."
            ),
            "records": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-csv", action="append", default=[])
    parser.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    parser.add_argument("--browser-report", action="append", default=[])
    parser.add_argument(
        "--legacy-prescreen-ledger",
        default="",
        help=(
            "Optional mixed-provenance legacy ledger. Confirmed landing/document-review rows are "
            "migrated and annotated so future prescreen runs ignore them."
        ),
    )
    parser.add_argument("--run-id", default="")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    audit_paths = [Path(value).resolve() for value in args.audit_csv] or [DEFAULT_AUDIT.resolve()]
    browser_paths = [Path(value).resolve() for value in args.browser_report]
    selected: dict[str, dict] = {}
    for path in audit_paths:
        for row in audit_exclusions(path):
            selected[row["doi"]] = row
    browser_rows = browser_url_exclusions(
        [json.loads(path.read_text(encoding="utf-8")) for path in browser_paths],
        source_paths=browser_paths,
    )
    for row in browser_rows:
        selected[row["doi"]] = row
    legacy_path = Path(args.legacy_prescreen_ledger).resolve() if clean(args.legacy_prescreen_ledger) else None
    legacy_rows = legacy_post_retrieval_exclusions(legacy_path) if legacy_path is not None else []
    legacy_only_dois: set[str] = set()
    for row in legacy_rows:
        if row["doi"] not in selected:
            selected[row["doi"]] = row
            legacy_only_dois.add(row["doi"])

    ledger_path = Path(args.ledger).resolve()
    payload = load_ledger(ledger_path)
    existing = {
        normalize_doi(record.get("doi", "")): dict(record)
        for record in payload.get("records", [])
        if isinstance(record, dict) and normalize_doi(record.get("doi", ""))
    }
    decided_at = now_utc()
    run_id = clean(args.run_id) or "post_retrieval_registration_" + dt.datetime.now(
        dt.timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")
    added = updated = unchanged = 0
    for doi, raw in selected.items():
        record = {**raw, "run_id": run_id, "decided_at_utc": decided_at}
        previous = existing.get(doi)
        # Migration fills gaps but never replaces a richer current decision
        # that is already present in the dedicated eligibility ledger.
        if previous is not None and doi in legacy_only_dois:
            unchanged += 1
            continue
        # Generated run/timestamp fields should not turn an otherwise
        # idempotent registration into a new decision revision.
        comparable_previous = {
            key: value for key, value in (previous or {}).items() if key not in {"run_id", "decided_at_utc"}
        }
        comparable_record = {
            key: value for key, value in record.items() if key not in {"run_id", "decided_at_utc"}
        }
        if previous is None:
            existing[doi] = record
            added += 1
        elif comparable_previous == comparable_record:
            unchanged += 1
        else:
            existing[doi] = record
            updated += 1

    report = {
        "audit_files": [str(path) for path in audit_paths],
        "audit_exclusions": sum(len(audit_exclusions(path)) for path in audit_paths),
        "browser_url_exclusions": len(browser_rows),
        "legacy_post_retrieval_exclusions": len(legacy_rows),
        "ledger_records_before": len(payload.get("records", [])),
        "added": added,
        "updated": updated,
        "unchanged": unchanged,
        "ledger_records_after": len(existing),
        "technical_or_access_failures_registered": 0,
        "apply": bool(args.apply),
    }
    print(json.dumps(report, indent=2))
    if not args.apply:
        print("Dry run only; pass --apply to update the post-retrieval decision ledger.")
        return 0

    payload["schema_version"] = "post_retrieval_eligibility_decisions_v1"
    payload["policy"] = (
        "Confirmed DOI-level eligibility decisions based on landing pages or retrieved documents. "
        "Retrieval failures and access outcomes are excluded from this ledger."
    )
    payload["updated_at_utc"] = decided_at
    payload["records"] = [existing[doi] for doi in sorted(existing)]
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if legacy_path is not None:
        report["legacy_records_annotated"] = annotate_legacy_migrations(
            legacy_path,
            {row["doi"] for row in legacy_rows},
            ledger_path,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
