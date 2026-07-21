#!/usr/bin/env python3
"""Stage audited browser-retrieved PDFs before canonical import.

Validated article PDFs remain in the manual inbox. Definite format exclusions,
identity-review files, and wrong documents are moved into separate quarantine
folders with a durable manifest. The command is a dry run unless ``--apply`` is
provided.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIT = (
    ROOT
    / "data"
    / "processed"
    / "corpus"
    / "audits"
    / "doi_browser_pdf_publication_format_audit.csv"
)
DEFAULT_QUARANTINE = ROOT / "data" / "raw" / "papers" / "pdf_conflicts" / "doi_browser_20260719"
DEFAULT_REPORT = (
    ROOT
    / "data"
    / "processed"
    / "corpus"
    / "audits"
    / "doi_browser_pdf_audit_staging_20260719.json"
)

DESTINATION_BY_ACTION = {
    "exclude_publication_format": "excluded_publication_format",
    "quarantine_identity_review": "identity_review",
    "quarantine_wrong_document": "wrong_document",
    "quarantine_invalid_pdf": "invalid_pdf",
    "review_publication_format": "publication_format_review",
}


def normalized_staging_rows(audit_path: Path, document_audits: list[Path]) -> list[dict]:
    """Combine legacy format audits with richer document audits by file path."""

    by_file: dict[str, dict] = {}
    if audit_path.is_file():
        for row in pd.read_csv(audit_path).fillna("").to_dict("records"):
            source = str(Path(str(row.get("file", ""))).resolve())
            if source:
                by_file[source] = row
    action_map = {
        "eligible_for_import": "import_validated_article_pdf",
        "identity_review": "quarantine_identity_review",
        "do_not_import_as_article_pdf": "quarantine_wrong_document",
        # These records are suspicious but not authoritative exclusions.  Keep
        # them out of the importer while preserving them for human review.
        "format_exclusion_candidate": "review_publication_format",
    }
    for path in document_audits:
        for row in pd.read_csv(path).fillna("").to_dict("records"):
            source = str(Path(str(row.get("file_path", ""))).resolve())
            if not source:
                continue
            final_outcome = str(row.get("final_outcome", "")).strip()
            title_score = float(row.get("front_title_score", 0) or 0)
            action = action_map.get(str(row.get("recommended_staging_action", "")).strip(), "")
            if final_outcome == "alias_or_foreign_doi_mismatch" and title_score >= 0.999:
                action = "import_registered_alias_pdf"
            by_file[source] = {
                **row,
                "file": source,
                "doi": str(row.get("requested_doi", "")).strip(),
                "publication_format": str(row.get("artifact_class", "")).strip(),
                "recommended_action": action,
            }
    return [by_file[key] for key in sorted(by_file)]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collision_safe_destination(source: Path, directory: Path) -> Path:
    target = directory / source.name
    if not target.exists() or sha256(target) == sha256(source):
        return target
    return directory / f"{source.stem}__{sha256(source)[:12]}{source.suffix}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-csv", default=str(DEFAULT_AUDIT))
    parser.add_argument(
        "--document-audit-csv",
        action="append",
        default=[],
        help="Richer browser-recovery document audit; repeat for multiple passes.",
    )
    parser.add_argument("--quarantine-dir", default=str(DEFAULT_QUARANTINE))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    audit_path = Path(args.audit_csv).resolve()
    quarantine = Path(args.quarantine_dir).resolve()
    report_path = Path(args.report).resolve()
    rows = normalized_staging_rows(
        audit_path,
        [Path(value).resolve() for value in args.document_audit_csv],
    )
    manifest: list[dict] = []
    counts: Counter[str] = Counter()

    for row in rows:
        source = Path(str(row.get("file", ""))).resolve()
        action = str(row.get("recommended_action", "")).strip()
        subdir = DESTINATION_BY_ACTION.get(action)
        item = {
            "doi": str(row.get("doi", "")).strip(),
            "publication_format": str(row.get("publication_format", "")).strip(),
            "recommended_action": action,
            "source": str(source),
            "status": (
                "leave_for_registered_alias_import"
                if action == "import_registered_alias_pdf"
                else "leave_for_validated_import"
                if not subdir
                else "planned_move"
            ),
        }
        if subdir:
            destination = collision_safe_destination(source, quarantine / subdir)
            item["destination"] = str(destination)
            if not source.exists():
                item["status"] = "source_missing"
            elif args.apply:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists() and sha256(destination) == sha256(source):
                    source.unlink()
                    item["status"] = "duplicate_removed_from_inbox"
                else:
                    shutil.move(str(source), str(destination))
                    item["status"] = "moved"
        counts[item["status"]] += 1
        manifest.append(item)

    payload = {
        "schema_version": "retrieved_pdf_audit_staging_v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "apply": args.apply,
        "audit_csv": str(audit_path),
        "quarantine_dir": str(quarantine),
        "counts": dict(sorted(counts.items())),
        "records": manifest,
    }
    print(json.dumps({"apply": args.apply, "counts": payload["counts"]}, indent=2))
    if args.apply:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Report: {report_path}")
    else:
        print("Dry run only; pass --apply to stage quarantine files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
