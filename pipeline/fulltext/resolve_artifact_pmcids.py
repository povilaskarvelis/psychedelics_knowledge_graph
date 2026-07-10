#!/usr/bin/env python3
"""Resolve DOI-to-PMID/PMCID mappings for canonical full-text artifacts."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.fulltext.source_identity import clean, normalize_doi, normalize_pmcid  # noqa: E402
from pipeline.ingest.sync_paper_library import RateLimitedHttpClient  # noqa: E402


IDCONV_URL = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"
DEFAULT_ARTIFACT_DIR = ROOT / "data" / "processed" / "fulltext" / "articles"
DEFAULT_METADATA_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"
DEFAULT_REPORT_JSON = ROOT / "data" / "processed" / "fulltext" / "artifact_pmcid_resolution.json"
DEFAULT_REPORT_CSV = ROOT / "data" / "processed" / "fulltext" / "artifact_pmcid_resolution.csv"


def artifact_dois(path: Path) -> list[str]:
    out: list[str] = []
    for artifact_path in sorted(path.glob("*.json")):
        try:
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        doi = normalize_doi(artifact.get("study_doi", ""))
        if doi and doi not in out:
            out.append(doi)
    return out


def read_doi_file(path: Path) -> list[str]:
    return sorted({doi for line in path.read_text(encoding="utf-8").splitlines() if (doi := normalize_doi(line))})


def metadata_by_doi(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {
        normalize_doi(row.get("doi", "")): row
        for row in pd.read_parquet(path).fillna("").to_dict("records")
        if normalize_doi(row.get("doi", ""))
    }


def resolve_batch(client: RateLimitedHttpClient, dois: list[str], email: str) -> dict[str, dict]:
    payload = client.get_json(
        IDCONV_URL,
        params={
            "ids": ",".join(dois),
            "idtype": "doi",
            "format": "json",
            "tool": "psychedelics_kg_artifact_repair",
            "email": email or None,
        },
        headers={"Accept": "application/json,*/*;q=0.1"},
    )
    out: dict[str, dict] = {}
    for record in payload.get("records", []) if isinstance(payload, dict) else []:
        if not isinstance(record, dict):
            continue
        requested = normalize_doi(record.get("requested-id", "") or record.get("doi", ""))
        if requested:
            out[requested] = record
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(rows[0]) if rows else ["doi", "mapping_status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    parser.add_argument("--report-csv", default=str(DEFAULT_REPORT_CSV))
    parser.add_argument("--doi-file", default="")
    parser.add_argument("--email", default="")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--rps", type=float, default=2.0)
    parser.add_argument("--timeout-sec", type=int, default=45)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--progress-every", type=int, default=10)
    args = parser.parse_args()

    dois = read_doi_file(Path(args.doi_file).resolve()) if clean(args.doi_file) else artifact_dois(Path(args.artifact_dir).resolve())
    metadata = metadata_by_doi(Path(args.metadata_table).resolve())
    client = RateLimitedHttpClient(
        rps=max(0.1, args.rps),
        max_retries=max(0, args.max_retries),
        timeout_sec=max(1, args.timeout_sec),
        max_retry_after_sec=60,
        user_agent="kg-artifact-pmcid-repair",
    )
    resolved: dict[str, dict] = {}
    errors: list[dict] = []
    batch_size = max(1, min(100, args.batch_size))
    batches = [dois[index : index + batch_size] for index in range(0, len(dois), batch_size)]
    for index, batch in enumerate(batches, start=1):
        try:
            resolved.update(resolve_batch(client, batch, args.email))
        except Exception as err:
            errors.append({"batch": index, "dois": batch, "error": f"{type(err).__name__}: {err}"})
        if args.progress_every > 0 and (index % args.progress_every == 0 or index == len(batches)):
            print(f"PROGRESS: {index}/{len(batches)} batches; resolved={len(resolved)} errors={len(errors)}", flush=True)

    rows: list[dict] = []
    counts: Counter[str] = Counter()
    for doi in dois:
        current = metadata.get(doi, {})
        record = resolved.get(doi, {})
        verified_doi = normalize_doi(record.get("doi", ""))
        verified_pmcid = normalize_pmcid(record.get("pmcid", ""))
        current_pmcid = normalize_pmcid(current.get("pmcid", ""))
        if verified_pmcid and current_pmcid == verified_pmcid:
            status = "pmcid_verified"
        elif verified_pmcid and current_pmcid and current_pmcid != verified_pmcid:
            status = "pmcid_conflict"
        elif verified_pmcid:
            status = "pmcid_missing_locally"
        elif current_pmcid:
            status = "stored_pmcid_not_verified_for_doi"
        else:
            status = "no_pmcid"
        counts[status] += 1
        rows.append(
            {
                "doi": doi,
                "mapping_status": status,
                "current_pmid": clean(current.get("pmid", "")),
                "verified_pmid": clean(record.get("pmid", "")),
                "current_pmcid": current_pmcid,
                "verified_pmcid": verified_pmcid,
                "verified_doi": verified_doi,
                "idconv_status": clean(record.get("status", "")),
                "idconv_error": clean(record.get("errmsg", "")),
            }
        )

    report = {
        "artifact_dir": str(Path(args.artifact_dir).resolve()),
        "metadata_table": str(Path(args.metadata_table).resolve()),
        "doi_count": len(dois),
        "counts": dict(counts),
        "request_errors": errors,
        "rows": rows,
    }
    report_json = Path(args.report_json).resolve()
    report_csv = Path(args.report_csv).resolve()
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(report_csv, rows)
    print(json.dumps({"doi_count": len(dois), "counts": dict(counts), "request_error_count": len(errors)}, indent=2))
    print(f"JSON report: {report_json}")
    print(f"CSV report: {report_csv}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
