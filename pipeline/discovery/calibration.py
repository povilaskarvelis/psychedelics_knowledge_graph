"""Search-yield and known-relevant-record calibration for discovery runs."""

from __future__ import annotations

from collections import defaultdict
import datetime as dt
import json
from pathlib import Path
import re
from typing import Iterable

import pandas as pd

from .providers import normalize_doi, normalize_openalex_id, normalize_pmid


CALIBRATION_REPORT_NAME = "search_calibration_report.json"
CALIBRATION_GROUPS_NAME = "search_calibration_groups.csv"
KNOWN_COVERAGE_NAME = "known_relevant_coverage.csv"


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return _clean(value).lower() in {"1", "true", "yes", "y"}


def _record_key(row: dict) -> str:
    doi = normalize_doi(row.get("doi"))
    if doi:
        return f"doi:{doi}"
    pmid = normalize_pmid(row.get("pmid"))
    if pmid:
        return f"pmid:{pmid}"
    openalex_id = normalize_openalex_id(row.get("openalex_id"))
    if openalex_id:
        return f"openalex:{openalex_id.upper()}"
    provider_record_id = _clean(row.get("provider_record_id"))
    return f"provider:{provider_record_id}" if provider_record_id else ""


def _write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _date_year(value: object) -> int | None:
    match = re.search(r"\b(?:18|19|20|21)\d{2}\b", _clean(value))
    return int(match.group(0)) if match else None


def _in_publication_window(row: dict, start_date: str, end_date: str) -> bool:
    publication_date = _clean(row.get("publication_date"))
    try:
        exact = dt.date.fromisoformat(publication_date)
        return dt.date.fromisoformat(start_date) <= exact <= dt.date.fromisoformat(end_date)
    except ValueError:
        pass
    start_year = int(start_date[:4])
    end_year = int(end_date[:4])
    year = _date_year(publication_date) or _date_year(row.get("study_year"))
    return year is not None and start_year <= year <= end_year


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() in {".csv", ".tsv"}:
        return pd.read_csv(path, sep="\t" if path.suffix.lower() == ".tsv" else ",")
    raise ValueError(f"Unsupported known-relevant source format: {path}")


def _accepted_exceptions(path: Path) -> dict[tuple[str, str], str]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("exceptions", []) if isinstance(payload, dict) else []
    out: dict[tuple[str, str], str] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or _clean(row.get("status")).lower() != "accepted":
            continue
        record_id = _clean(row.get("record_id")).lower()
        provider = _clean(row.get("provider")).lower()
        reason = _clean(row.get("reason"))
        if record_id and provider and reason:
            out[(record_id, provider)] = reason
    return out


def _group_metrics(executions: pd.DataFrame, hits: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "provider", "layer", "search_type", "executions", "complete_executions",
        "zero_result_executions", "zero_result_rate", "expected_hits", "retrieved_hits",
        "count_requests", "result_pages", "unique_records", "unique_dois", "exclusive_records",
    ]
    if executions.empty:
        return pd.DataFrame(columns=columns)

    group_columns = ["provider", "layer", "search_type"]
    group_keys: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    group_dois: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    key_groups: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    if not hits.empty:
        for row in hits.to_dict("records"):
            group = tuple(_clean(row.get(column)) for column in group_columns)
            key = _record_key(row)
            if key:
                group_keys[group].add(key)
                key_groups[key].add(group)
            doi = normalize_doi(row.get("doi"))
            if doi:
                group_dois[group].add(doi)

    rows: list[dict] = []
    for group, frame in executions.groupby(group_columns, dropna=False, sort=True):
        complete = frame[frame["status"].astype(str).eq("complete")]
        zero = int((complete["expected_total"].fillna(0).astype(int) == 0).sum())
        keys = group_keys.get(tuple(str(value) for value in group), set())
        rows.append(
            {
                "provider": group[0],
                "layer": group[1],
                "search_type": group[2],
                "executions": int(len(frame)),
                "complete_executions": int(len(complete)),
                "zero_result_executions": zero,
                "zero_result_rate": round(zero / len(complete), 6) if len(complete) else None,
                "expected_hits": int(frame["expected_total"].fillna(0).astype(int).sum()),
                "retrieved_hits": int(frame["retrieved_total"].fillna(0).astype(int).sum()),
                "count_requests": int(frame["count_request_count"].fillna(0).astype(int).sum()),
                "result_pages": int(frame["page_count"].fillna(0).astype(int).sum()),
                "unique_records": len(keys),
                "unique_dois": len(group_dois.get(tuple(str(value) for value in group), set())),
                "exclusive_records": sum(len(key_groups[key]) == 1 for key in keys),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _known_coverage(
    *,
    manifest: dict,
    hits: pd.DataFrame,
    retrieval_complete: bool,
) -> tuple[pd.DataFrame, dict, bool]:
    config = manifest.get("calibration", {}) if isinstance(manifest.get("calibration"), dict) else {}
    required = bool(config.get("required_for_promotion", False))
    columns = [
        "record_id", "doi", "pmid", "openalex_id", "title", "publication_year",
        "provider", "found", "exception_accepted", "exception_reason", "disposition",
    ]
    if not config:
        return pd.DataFrame(columns=columns), {"status": "not_required", "required": False}, True
    if config.get("known_relevant_check_enabled") is False:
        return (
            pd.DataFrame(columns=columns),
            {
                "status": "disabled_by_operator",
                "required": False,
                "reason": _clean(config.get("disabled_reason")),
            },
            True,
        )
    if "core" not in set(manifest.get("layers", [])):
        return (
            pd.DataFrame(columns=columns),
            {"status": "not_applicable_without_core", "required": required},
            True,
        )

    source_path = Path(_clean(config.get("known_relevant_source")))
    flag_column = _clean(config.get("known_relevant_flag_column")) or "flag_in_known_study_set"
    exceptions_path = Path(_clean(config.get("exceptions_path")))
    if not source_path.exists():
        summary = {"status": "missing_source", "required": required, "source": str(source_path)}
        return pd.DataFrame(columns=columns), summary, not required
    known = _read_table(source_path)
    if flag_column not in known.columns:
        summary = {"status": "missing_flag_column", "required": required, "flag_column": flag_column}
        return pd.DataFrame(columns=columns), summary, not required
    known = known[known[flag_column].map(_truthy)].copy()
    start_date = _clean(manifest.get("coverage_start_date"))
    end_date = _clean(manifest.get("coverage_end_date"))
    known = known[
        known.apply(lambda row: _in_publication_window(row.to_dict(), start_date, end_date), axis=1)
    ]

    provider_identifiers: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    if not hits.empty:
        for row in hits.to_dict("records"):
            provider = _clean(row.get("provider")).lower()
            doi = normalize_doi(row.get("doi"))
            pmid = normalize_pmid(row.get("pmid"))
            openalex_id = normalize_openalex_id(row.get("openalex_id")).upper()
            if doi:
                provider_identifiers[provider]["doi"].add(doi)
            if pmid:
                provider_identifiers[provider]["pmid"].add(pmid)
            if openalex_id:
                provider_identifiers[provider]["openalex"].add(openalex_id)

    accepted = _accepted_exceptions(exceptions_path)
    rows: list[dict] = []
    selected_providers = set(manifest.get("providers", []))
    for item in known.to_dict("records"):
        doi = normalize_doi(item.get("doi"))
        pmid = normalize_pmid(item.get("pmid"))
        openalex_id = normalize_openalex_id(item.get("openalex_id")).upper()
        record_id = f"doi:{doi}" if doi else (f"pmid:{pmid}" if pmid else f"openalex:{openalex_id}")
        expected_providers: list[str] = []
        if "pubmed" in selected_providers and pmid:
            expected_providers.append("pubmed")
        if "openalex" in selected_providers and openalex_id:
            expected_providers.append("openalex")
        for provider in expected_providers:
            found = bool(
                (doi and doi in provider_identifiers[provider]["doi"])
                or (provider == "pubmed" and pmid in provider_identifiers[provider]["pmid"])
                or (provider == "openalex" and openalex_id in provider_identifiers[provider]["openalex"])
            )
            reason = accepted.get((record_id.lower(), provider), "")
            disposition = "found" if found else ("explained_miss" if reason else "unexplained_miss")
            rows.append(
                {
                    "record_id": record_id,
                    "doi": doi,
                    "pmid": pmid,
                    "openalex_id": openalex_id,
                    "title": _clean(item.get("study_title") or item.get("title")),
                    "publication_year": _date_year(item.get("study_year") or item.get("publication_date")),
                    "provider": provider,
                    "found": found,
                    "exception_accepted": bool(reason),
                    "exception_reason": reason,
                    "disposition": disposition,
                }
            )
    coverage = pd.DataFrame(rows, columns=columns)
    unexplained = int((coverage["disposition"] == "unexplained_miss").sum()) if not coverage.empty else 0
    found = int((coverage["disposition"] == "found").sum()) if not coverage.empty else 0
    explained = int((coverage["disposition"] == "explained_miss").sum()) if not coverage.empty else 0
    if not retrieval_complete:
        status = "pending_retrieval"
        gate = not required
    elif unexplained:
        status = "failed"
        gate = not required
    elif coverage.empty:
        status = "no_expected_records_in_window"
        gate = True
    else:
        status = "passed"
        gate = True
    summary = {
        "status": status,
        "required": required,
        "source": str(source_path),
        "flag_column": flag_column,
        "known_records_in_window": int(len(known)),
        "expected_provider_record_checks": int(len(coverage)),
        "found": found,
        "explained_misses": explained,
        "unexplained_misses": unexplained,
    }
    return coverage, summary, gate


def build_calibration_report(
    *,
    run_dir: Path,
    manifest: dict,
    execution_rows: Iterable[dict],
    hits: pd.DataFrame,
    retrieval_complete: bool,
    group_metrics: pd.DataFrame | None = None,
) -> tuple[dict, bool]:
    """Materialize query-yield and known-record coverage reports."""

    run_dir = Path(run_dir)
    executions = pd.DataFrame(list(execution_rows))
    groups = group_metrics.copy() if group_metrics is not None else _group_metrics(executions, hits)
    groups.to_csv(run_dir / CALIBRATION_GROUPS_NAME, index=False)
    coverage, coverage_summary, gate = _known_coverage(
        manifest=manifest,
        hits=hits,
        retrieval_complete=retrieval_complete,
    )
    coverage.to_csv(run_dir / KNOWN_COVERAGE_NAME, index=False)
    report = {
        "schema_version": "search_calibration_report_v1",
        "run_id": _clean(manifest.get("run_id")),
        "retrieval_complete": bool(retrieval_complete),
        "calibration_gate_passed": bool(gate),
        "known_relevant_coverage": coverage_summary,
        "query_group_count": int(len(groups)),
        "outputs": {
            "query_groups": str((run_dir / CALIBRATION_GROUPS_NAME).resolve()),
            "known_relevant_coverage": str((run_dir / KNOWN_COVERAGE_NAME).resolve()),
        },
    }
    _write_json(run_dir / CALIBRATION_REPORT_NAME, report)
    return report, bool(gate)
