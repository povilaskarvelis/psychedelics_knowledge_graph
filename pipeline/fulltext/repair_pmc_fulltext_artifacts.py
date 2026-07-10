#!/usr/bin/env python3
"""Replace invalid PMC-derived artifacts with DOI-verified JATS XML."""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import shutil
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.fulltext.fetch_pmc_fulltext_xml import (  # noqa: E402
    build_xml_artifact,
    fetch_europepmc_fulltext_xml,
    fetch_pmc_oai_xml,
)
from pipeline.fulltext.source_identity import clean, normalize_doi, normalize_pmcid  # noqa: E402
from pipeline.ingest.sync_paper_library import RateLimitedHttpClient  # noqa: E402


DEFAULT_INVENTORY = ROOT / "outputs" / "source_identity_repair_20260710" / "pmc_identity_inventory.csv"
DEFAULT_QUARANTINE = ROOT / "data" / "processed" / "fulltext" / "source_identity_quarantine_20260710"
DEFAULT_REPORT = ROOT / "data" / "processed" / "fulltext" / "pmc_source_identity_repair_report.json"
DEFAULT_MANUAL_REPAIRS = ROOT / "pipeline" / "fulltext" / "manual_source_identity_repairs.json"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def replacement_rows(path: Path, manual_repairs_path: Path | None = None) -> list[dict]:
    rows = pd.read_csv(path).fillna("").to_dict("records")
    selected = [
        row
        for row in rows
        if clean(row.get("correct_acquisition_method", "")).startswith(("refetch_europepmc_jats:", "refetch_pmc_oai_jats:"))
    ]
    if manual_repairs_path and manual_repairs_path.exists():
        manual = json.loads(manual_repairs_path.read_text(encoding="utf-8"))
        for row in manual if isinstance(manual, list) else []:
            if not isinstance(row, dict):
                continue
            artifact_path = Path(clean(row.get("artifact_path", "")))
            if artifact_path and not artifact_path.is_absolute():
                row = {**row, "artifact_path": str((ROOT / artifact_path).resolve())}
            doi = normalize_doi(row.get("doi", ""))
            matching_index = next(
                (
                    index
                    for index, existing in enumerate(selected)
                    if normalize_doi(existing.get("doi", "")) == doi
                ),
                None,
            )
            if matching_index is None:
                selected.append(row)
            else:
                # The explicit manual registry is the reproducible repair source
                # of truth when an older inventory contains the same DOI.
                selected[matching_index] = row
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", default=str(DEFAULT_INVENTORY))
    parser.add_argument("--quarantine-dir", default=str(DEFAULT_QUARANTINE))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--manual-repairs", default=str(DEFAULT_MANUAL_REPAIRS))
    parser.add_argument("--manual-only", action="store_true")
    parser.add_argument(
        "--doi",
        action="append",
        default=[],
        help="Limit the repair to this exact DOI; repeat the option for multiple DOIs.",
    )
    parser.add_argument("--rps", type=float, default=2.0)
    parser.add_argument("--timeout-sec", type=int, default=45)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--progress-every", type=int, default=10)
    args = parser.parse_args()

    inventory_path = Path(args.inventory).resolve()
    quarantine_dir = Path(args.quarantine_dir).resolve()
    report_path = Path(args.report).resolve()
    rows = replacement_rows(
        inventory_path,
        Path(args.manual_repairs).resolve() if clean(args.manual_repairs) else None,
    )
    if args.manual_only:
        manual_dois = {
            normalize_doi(row.get("doi", ""))
            for row in json.loads(Path(args.manual_repairs).resolve().read_text(encoding="utf-8"))
            if isinstance(row, dict)
        }
        rows = [row for row in rows if normalize_doi(row.get("doi", "")) in manual_dois]
    doi_filter = {normalize_doi(value) for value in args.doi if normalize_doi(value)}
    if doi_filter:
        rows = [row for row in rows if normalize_doi(row.get("doi", "")) in doi_filter]
        selected_dois = {normalize_doi(row.get("doi", "")) for row in rows}
        missing_dois = sorted(doi_filter - selected_dois)
        if missing_dois:
            parser.error(f"Requested DOI repair not found: {', '.join(missing_dois)}")
    if args.limit > 0:
        rows = rows[: args.limit]
    client = RateLimitedHttpClient(
        rps=max(0.1, args.rps),
        max_retries=max(0, args.max_retries),
        timeout_sec=max(1, args.timeout_sec),
        max_retry_after_sec=60,
        user_agent="kg-pmc-source-identity-repair",
    )

    records: list[dict] = []
    counts: Counter[str] = Counter()
    for position, row in enumerate(rows, start=1):
        doi = normalize_doi(row.get("doi", ""))
        title = clean(row.get("requested_title", ""))
        method = clean(row.get("correct_acquisition_method", ""))
        pmcid = normalize_pmcid(method.rsplit(":", 1)[-1])
        artifact_path = Path(clean(row.get("artifact_path", ""))).resolve()
        record = {
            "doi": doi,
            "title": title,
            "pmcid": pmcid,
            "method": method,
            "artifact_path": str(artifact_path),
            "status": "planned" if not args.apply else "",
            "error": "",
            "backup_path": "",
            "source_identity_status": "",
        }
        try:
            if method.startswith("refetch_europepmc_jats:"):
                endpoint, xml_text = fetch_europepmc_fulltext_xml(client, pmcid)
                source = "europepmc_fulltext_xml"
            else:
                endpoint, xml_text = fetch_pmc_oai_xml(client, pmcid)
                source = "pmc_oai_xml"
            artifact = build_xml_artifact(
                {"doi": doi, "study_title": title, "pmcid": pmcid},
                pmcid=pmcid,
                endpoint=endpoint,
                xml_text=xml_text,
                retrieval_source=source,
                retrieval_trace=[{"source": source, "endpoint": endpoint, "status": "ok", "error": ""}],
            )
            artifact["repair_run_id"] = "source_identity_repair_20260710"
            artifact["repaired_at_utc"] = now_utc()
            artifact["replaced_artifact_backend"] = clean(row.get("artifact_backend", ""))
            record["source_identity_status"] = clean((artifact.get("source_identity") or {}).get("status", ""))
            if args.apply:
                backup_path = quarantine_dir / "replaced_artifacts" / artifact_path.name
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                if artifact_path.exists() and not backup_path.exists():
                    shutil.copy2(artifact_path, backup_path)
                write_json(artifact_path, artifact)
                record["backup_path"] = str(backup_path)
                record["status"] = "replaced"
                counts["replaced"] += 1
            else:
                record["status"] = "validated_dry_run"
                counts["validated_dry_run"] += 1
        except Exception as err:
            record["status"] = "failed"
            record["error"] = f"{type(err).__name__}: {err}"
            counts["failed"] += 1
        records.append(record)
        if args.progress_every > 0 and (position % args.progress_every == 0 or position == len(rows)):
            print(
                f"PROGRESS: {position}/{len(rows)} replaced={counts['replaced']} "
                f"validated={counts['validated_dry_run']} failed={counts['failed']}",
                flush=True,
            )

    report = {
        "generated_at_utc": now_utc(),
        "inventory": str(inventory_path),
        "apply": bool(args.apply),
        "counts": {"targets": len(rows), **dict(counts)},
        "records": records,
    }
    write_json(report_path, report)
    print(json.dumps(report["counts"], indent=2))
    print(f"Report: {report_path}")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
