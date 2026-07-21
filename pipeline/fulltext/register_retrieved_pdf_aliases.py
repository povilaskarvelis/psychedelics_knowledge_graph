#!/usr/bin/env python3
"""Register high-confidence DOI aliases from PDF or identity audits."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.candidate_status import apply_candidate_updates, normalize_doi  # noqa: E402
from pipeline.validate.doi_aliases import DEFAULT_DOI_ALIAS_REGISTRY  # noqa: E402

DEFAULT_CANDIDATES = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"


def clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def split_dois(value: object) -> list[str]:
    output: list[str] = []
    for part in clean(value).split("|"):
        doi = normalize_doi(part.rstrip(".,;) "))
        if doi and doi not in output:
            output.append(doi)
    return output


def select_aliases(audits: list[Path], candidate_dois: set[str]) -> list[dict]:
    selected: dict[str, dict] = {}
    for path in audits:
        frame = pd.read_csv(path).fillna("")
        required = {"requested_doi", "foreign_front_dois", "front_title_score", "final_outcome"}
        if not required.issubset(frame.columns):
            raise ValueError(f"Alias audit is missing columns {sorted(required - set(frame.columns))}: {path}")
        for row in frame.to_dict("records"):
            alias = normalize_doi(row.get("requested_doi", ""))
            if (
                not alias
                or clean(row.get("final_outcome", "")) != "alias_or_foreign_doi_mismatch"
                or float(row.get("front_title_score", 0) or 0) < 0.999
            ):
                continue
            observed = [doi for doi in split_dois(row.get("foreign_front_dois", "")) if doi in candidate_dois]
            if len(observed) != 1 or observed[0] == alias:
                continue
            relationship_type = (
                clean(row.get("relationship_type", ""))
                or "repository_or_preprint_wrapper_doi"
            )
            selected[alias] = {
                "alias_doi": alias,
                "canonical_doi": observed[0],
                "relationship_type": relationship_type,
                "evidence_basis": clean(row.get("artifact_evidence", ""))
                or "Matching title and published DOI on the retrieved document front page.",
                "source_artifact": str(path.resolve()),
            }
    return [selected[doi] for doi in sorted(selected)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-csv", action="append", required=True)
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--alias-registry", default=str(DEFAULT_DOI_ALIAS_REGISTRY))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    candidate_path = Path(args.candidate_table).resolve()
    candidate = pd.read_parquet(candidate_path, columns=["doi"])
    candidate_dois = {normalize_doi(value) for value in candidate["doi"] if normalize_doi(value)}
    audit_paths = [Path(value).resolve() for value in args.audit_csv]
    selected = select_aliases(audit_paths, candidate_dois)

    registry_path = Path(args.alias_registry).resolve()
    payload = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.is_file() else {
        "schema_version": "doi_alias_registry_v1",
        "records": [],
    }
    existing = {
        normalize_doi(row.get("alias_doi", "")): dict(row)
        for row in payload.get("records", [])
        if isinstance(row, dict) and normalize_doi(row.get("alias_doi", ""))
    }
    added = updated = unchanged = 0
    reviewed_at = dt.datetime.now(dt.timezone.utc).isoformat()
    for row in selected:
        alias = row["alias_doi"]
        record = {**row, "reviewed_at_utc": reviewed_at}
        previous = existing.get(alias)
        comparable_previous = {k: v for k, v in (previous or {}).items() if k != "reviewed_at_utc"}
        comparable_record = {k: v for k, v in record.items() if k != "reviewed_at_utc"}
        if previous is None:
            existing[alias] = record
            added += 1
        elif comparable_previous == comparable_record:
            unchanged += 1
        else:
            existing[alias] = record
            updated += 1

    candidate_update = apply_candidate_updates(
        candidate_table=candidate_path,
        updates=pd.DataFrame(
            [
                {
                    "doi": row["alias_doi"],
                    "doi_alias_status": "alias_suppressed",
                    "doi_alias_of": row["canonical_doi"],
                }
                for row in selected
            ]
        ),
        column_defaults={"doi_alias_status": "", "doi_alias_of": ""},
        dry_run=not bool(args.apply),
    )
    report = {
        "selected_aliases": len(selected),
        "added": added,
        "updated": updated,
        "unchanged": unchanged,
        "registry_records_after": len(existing),
        "candidate_update": candidate_update,
        "apply": bool(args.apply),
    }
    print(json.dumps(report, indent=2))
    if not args.apply:
        print("Dry run only; pass --apply to update the alias registry and candidate alias projection.")
        return 0

    payload["schema_version"] = payload.get("schema_version", "doi_alias_registry_v1")
    payload["checked_at"] = reviewed_at
    payload["records"] = [existing[doi] for doi in sorted(existing)]
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
