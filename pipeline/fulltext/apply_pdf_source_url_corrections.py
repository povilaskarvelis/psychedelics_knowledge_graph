#!/usr/bin/env python3
"""Apply curated DOI-specific PDF source URL identity corrections."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import re
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.metadata_utils import normalize_doi  # noqa: E402
from pipeline.workflow.decision_state import write_parquet_atomic  # noqa: E402

DEFAULT_CANDIDATE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_CORRECTIONS = ROOT / "data" / "curated" / "pdf_source_url_corrections.json"
DEFAULT_REPORT = ROOT / "data" / "processed" / "corpus" / "audits" / "pdf_source_url_corrections.json"
URL_LIST_COLUMNS = ("pdf_url_candidates", "probable_pdf_url_candidates", "other_url_candidates")


def clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def split_urls(value: object) -> list[str]:
    return [part.strip() for part in re.split(r"\s*\|\s*", clean(value)) if part.strip()]


def join_urls(values: list[str]) -> str:
    return " | ".join(dict.fromkeys(value for value in values if value))


def apply_corrections(candidate: pd.DataFrame, records: list[dict]) -> tuple[pd.DataFrame, dict]:
    out = candidate.copy()
    for column in ("best_pdf_url", "open_access_url", *URL_LIST_COLUMNS):
        if column not in out.columns:
            out[column] = ""
    for column, default in (
        ("pdf_download_status", ""),
        ("pdf_download_error", ""),
        ("pdf_download_failure_category", ""),
        ("pdf_download_failure_categories", ""),
        ("pdf_download_retry_recommended", False),
    ):
        if column not in out.columns:
            out[column] = default

    doi_keys = out["doi"].map(normalize_doi)
    changed_rows = 0
    missing_dois: list[str] = []
    applied: list[dict] = []
    for record in records:
        doi = normalize_doi(record.get("doi", ""))
        rejected = clean(record.get("rejected_url", ""))
        replacement_pdf = clean(record.get("replacement_pdf_url", ""))
        replacement_landing = clean(record.get("replacement_landing_url", ""))
        mask = doi_keys.eq(doi)
        if not mask.any():
            missing_dois.append(doi)
            continue
        for index in out.index[mask]:
            before = out.loc[index].copy()
            if clean(out.at[index, "best_pdf_url"]) == rejected:
                out.at[index, "best_pdf_url"] = replacement_pdf or replacement_landing
            if clean(out.at[index, "open_access_url"]) == rejected:
                out.at[index, "open_access_url"] = replacement_landing or f"https://doi.org/{doi}"
            for column in URL_LIST_COLUMNS:
                urls = [url for url in split_urls(out.at[index, column]) if url != rejected]
                preferred = []
                if column == "pdf_url_candidates" and replacement_pdf:
                    preferred.append(replacement_pdf)
                if replacement_landing:
                    preferred.append(replacement_landing)
                out.at[index, column] = join_urls([*preferred, *urls])
            out.at[index, "pdf_download_status"] = "download_failed"
            out.at[index, "pdf_download_failure_category"] = "source_identity_mismatch"
            out.at[index, "pdf_download_failure_categories"] = "source_identity_mismatch"
            out.at[index, "pdf_download_retry_recommended"] = True
            evidence = clean(record.get("evidence", ""))
            out.at[index, "pdf_download_error"] = (
                f"source_identity_mismatch: rejected {rejected}; replacement {replacement_pdf or replacement_landing}; "
                f"{evidence}"
            ).rstrip("; ")
            if not out.loc[index].equals(before):
                changed_rows += 1
        applied.append({"doi": doi, "rejected_url": rejected, "replacement_pdf_url": replacement_pdf})

    return out, {
        "schema_version": "pdf_source_url_corrections_v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "correction_records": len(records),
        "changed_candidate_rows": changed_rows,
        "missing_candidate_dois": sorted(set(missing_dois)),
        "applied": applied,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE))
    parser.add_argument("--corrections", default=str(DEFAULT_CORRECTIONS))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    candidate_path = Path(args.candidate_table).resolve()
    payload = json.loads(Path(args.corrections).resolve().read_text(encoding="utf-8"))
    updated, report = apply_corrections(pd.read_parquet(candidate_path), payload.get("records", []))
    report["candidate_table"] = str(candidate_path)
    report["corrections"] = str(Path(args.corrections).resolve())
    report["apply"] = bool(args.apply)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.apply:
        write_parquet_atomic(updated, candidate_path)
        report_path = Path(args.report).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
