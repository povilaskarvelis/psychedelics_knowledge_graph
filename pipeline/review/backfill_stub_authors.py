#!/usr/bin/env python3
"""Backfill missing stub authors from paper DB, OpenAlex, and Crossref."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]


DATASET_CONFIG = {
    "mechanistic": {
        "stubs_json": ROOT / "data" / "processed" / "mechanistic_claim_stubs.json",
        "stubs_csv": ROOT / "data" / "processed" / "mechanistic_claim_stubs.csv",
        "paper_db_json": ROOT / "data" / "processed" / "paper_library_mechanistic.json",
        "paper_db_csv": ROOT / "data" / "processed" / "paper_library_mechanistic.csv",
        "schema": ROOT / "schema" / "claims.schema.json",
    },
    "disorder": {
        "stubs_json": ROOT / "data" / "processed" / "disorder_claim_stubs.json",
        "stubs_csv": ROOT / "data" / "processed" / "disorder_claim_stubs.csv",
        "paper_db_json": ROOT / "data" / "processed" / "paper_library_disorder.json",
        "paper_db_csv": ROOT / "data" / "processed" / "paper_library_disorder.csv",
        "schema": ROOT / "schema" / "disorder_claims.schema.json",
    },
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_doi(raw: str) -> str:
    text = normalize(raw)
    if not text:
        return ""
    if text.lower().startswith("doi:"):
        text = text[4:]
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
    ):
        if text.lower().startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip()


def load_json_array(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return data


def load_schema(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: List[dict]) -> None:
    fieldnames = sorted({k for row in rows for k in row.keys()}) if rows else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def flatten_paper_db_row(row: dict) -> dict:
    out = dict(row)
    contexts = out.get("contexts", [])
    if isinstance(contexts, list):
        out["contexts"] = json.dumps(contexts, ensure_ascii=False)
    return out


def parse_simple_yaml(path: Path) -> dict:
    if not path.exists():
        return {}

    out: Dict[str, dict] = {}
    current = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" ") and stripped.endswith(":"):
            current = stripped[:-1]
            out[current] = {}
            continue
        if current and line.startswith("  ") and ":" in stripped:
            key, value = stripped.split(":", 1)
            value = value.strip().strip('"').strip("'")
            parsed: object = value
            if value == "":
                parsed = ""
            else:
                try:
                    parsed = float(value) if "." in value else int(value)
                except ValueError:
                    parsed = value
            out[current][key.strip()] = parsed
    return out


def merge_simple_config(base: dict, override: dict) -> dict:
    merged: Dict[str, dict] = {
        section: values.copy() if isinstance(values, dict) else values
        for section, values in base.items()
    }
    for section, values in override.items():
        if not isinstance(values, dict):
            if values != "":
                merged[section] = values
            continue
        current = merged.setdefault(section, {})
        if not isinstance(current, dict):
            current = {}
            merged[section] = current
        for key, value in values.items():
            if value != "":
                current[key] = value
    return merged


def load_config(path: Path) -> dict:
    config = parse_simple_yaml(path)
    local_path = path.parent / "config.local.yaml"
    if path.name == "config.example.yaml" and local_path.exists():
        config = merge_simple_config(config, parse_simple_yaml(local_path))
    return config


def read_float(maybe_value: object, default: float) -> float:
    if maybe_value is None:
        return default
    try:
        return float(maybe_value)
    except Exception:
        return default


def read_int(maybe_value: object, default: int) -> int:
    if maybe_value is None:
        return default
    try:
        return int(maybe_value)
    except Exception:
        return default


class RateLimitedHttpClient:
    def __init__(self, rps: float, max_retries: int, timeout_sec: int = 35, user_agent: str = "kg-pipeline/0.1"):
        self.rps = max(0.01, rps)
        self.min_interval = 1.0 / self.rps
        self.max_retries = max_retries
        self.timeout_sec = timeout_sec
        self.user_agent = user_agent
        self._last_request_ts = 0.0

    def _wait_for_slot(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_ts
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def _request_bytes(self, url: str, headers: Optional[Dict[str, str]] = None) -> bytes:
        req_headers = {"User-Agent": self.user_agent}
        if headers:
            req_headers.update(headers)
        req = Request(url, headers=req_headers)
        with urlopen(req, timeout=self.timeout_sec) as response:
            self._last_request_ts = time.monotonic()
            return response.read()

    def get_bytes(self, url: str, headers: Optional[Dict[str, str]] = None) -> bytes:
        backoff = 2.0
        for attempt in range(self.max_retries + 1):
            self._wait_for_slot()
            try:
                return self._request_bytes(url=url, headers=headers)
            except HTTPError as err:
                self._last_request_ts = time.monotonic()
                retryable = err.code in {429, 500, 502, 503, 504}
                if attempt >= self.max_retries or not retryable:
                    raise
                retry_after = err.headers.get("Retry-After") if err.headers else None
                if retry_after and retry_after.isdigit():
                    delay = max(backoff, float(retry_after))
                else:
                    delay = backoff
                time.sleep(delay + random.uniform(0.0, 0.35))
                backoff *= 1.7
            except URLError:
                self._last_request_ts = time.monotonic()
                if attempt >= self.max_retries:
                    raise
                time.sleep(backoff + random.uniform(0.0, 0.35))
                backoff *= 1.7
        raise RuntimeError("Unreachable retry state")

    def get_json(self, url: str, params: Optional[Dict[str, object]] = None, headers: Optional[Dict[str, str]] = None) -> dict:
        query = urlencode({k: v for k, v in (params or {}).items() if v is not None}, doseq=True)
        full_url = f"{url}?{query}" if query else url
        body = self.get_bytes(url=full_url, headers=headers)
        return json.loads(body.decode("utf-8"))


def authors_from_openalex(authorships: Iterable[dict], max_names: int = 10) -> str:
    names = []
    for authorship in authorships:
        author_obj = authorship.get("author") if isinstance(authorship, dict) else None
        if isinstance(author_obj, dict):
            name = normalize(author_obj.get("display_name", ""))
            if name:
                names.append(name)
        if len(names) >= max_names:
            break
    return "; ".join(names)


def lookup_openalex_authors(client: RateLimitedHttpClient, doi: str, email: str, api_key: str) -> str:
    endpoint = "https://api.openalex.org/works"
    params = {
        "filter": f"doi:https://doi.org/{doi}",
        "per-page": 1,
        "select": "authorships",
    }
    if api_key:
        params["api_key"] = api_key
    if email:
        params["mailto"] = email
    payload = client.get_json(endpoint, params=params, headers={})
    results = payload.get("results", []) if isinstance(payload, dict) else []
    if not results:
        return ""
    return authors_from_openalex(results[0].get("authorships", []) if isinstance(results[0], dict) else [])


def authors_from_crossref(author_list: Iterable[dict], max_names: int = 10) -> str:
    names = []
    for author in author_list:
        if not isinstance(author, dict):
            continue
        name = normalize(author.get("name", ""))
        if not name:
            given = normalize(author.get("given", ""))
            family = normalize(author.get("family", ""))
            name = " ".join(part for part in [given, family] if part).strip()
        if name:
            names.append(name)
        if len(names) >= max_names:
            break
    return "; ".join(names)


def lookup_crossref_authors(client: RateLimitedHttpClient, doi: str, mailto: str) -> str:
    endpoint = f"https://api.crossref.org/works/{quote(doi, safe='')}"
    params = {"mailto": mailto} if mailto else None
    payload = client.get_json(endpoint, params=params, headers={"Accept": "application/json"})
    message = payload.get("message", {}) if isinstance(payload, dict) else {}
    return authors_from_crossref(message.get("author", []) if isinstance(message, dict) else [])


def parse_schema(schema: dict) -> Tuple[List[str], Dict[str, Set[str]], Dict[str, str], List[Set[str]], Set[str]]:
    item = schema["items"]
    required = list(item.get("required", []))
    properties = item.get("properties", {})

    enums: Dict[str, Set[str]] = {}
    types: Dict[str, str] = {}
    for key, prop in properties.items():
        if "enum" in prop:
            enums[key] = set(prop["enum"])
        if "type" in prop:
            types[key] = prop["type"]

    one_of_groups: List[Set[str]] = []
    for group in item.get("oneOf", []):
        if isinstance(group, dict) and "required" in group:
            one_of_groups.append(set(group["required"]))

    return required, enums, types, one_of_groups, set(properties.keys())


def is_valid_type(raw_value: str, expected_type: str) -> bool:
    if raw_value == "":
        return True
    if expected_type == "integer":
        try:
            int(float(raw_value))
            return True
        except Exception:
            return False
    if expected_type == "number":
        try:
            float(raw_value)
            return True
        except Exception:
            return False
    return True


def evaluate_row(
    row: dict,
    required: List[str],
    enums: Dict[str, Set[str]],
    types: Dict[str, str],
    one_of_groups: List[Set[str]],
    allowed_keys: Set[str],
) -> Tuple[List[str], List[dict]]:
    blocker_fields: Set[str] = set()
    blockers: List[dict] = []

    cleaned = {k: row.get(k, "") for k in allowed_keys}

    for field in required:
        if normalize(cleaned.get(field, "")) == "":
            blocker_fields.add(field)
            blockers.append({"field": field, "reason": "missing_required"})

    if one_of_groups:
        any_group_satisfied = any(
            any(normalize(cleaned.get(field, "")) for field in group)
            for group in one_of_groups
        )
        if not any_group_satisfied:
            merged = "|".join(sorted({field for group in one_of_groups for field in group}))
            blocker_fields.add(merged)
            blockers.append({"field": merged, "reason": "missing_one_of"})

    for field, allowed in enums.items():
        value = normalize(cleaned.get(field, ""))
        if value and value not in allowed:
            blocker_fields.add(field)
            blockers.append({"field": field, "reason": "invalid_enum", "value": value})

    for field, expected in types.items():
        value = normalize(cleaned.get(field, ""))
        if not is_valid_type(value, expected):
            blocker_fields.add(field)
            blockers.append({"field": field, "reason": "invalid_type", "value": value, "expected": expected})

    return sorted(blocker_fields), blockers


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill missing stub authors from metadata APIs")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument("--status-filter", default="pending_curation", help="Only process rows with this status")
    parser.add_argument("--all-statuses", action="store_true", help="Ignore status filter")
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.example.yaml"))
    parser.add_argument("--openalex-email", default="")
    parser.add_argument("--openalex-api-key", default="")
    parser.add_argument("--crossref-mailto", default="")
    parser.add_argument("--openalex-rps", type=float, default=None)
    parser.add_argument("--max-retries", type=int, default=None)
    parser.add_argument("--skip-openalex", action="store_true")
    parser.add_argument("--skip-crossref", action="store_true")
    parser.add_argument(
        "--fallback-unknown",
        action="store_true",
        help="Set authors=Unknown if all lookups fail",
    )
    parser.add_argument("--mark-ready", action="store_true", help="Set clean rows to ready_for_promotion")
    parser.add_argument("--apply", action="store_true", help="Write updates to files")
    parser.add_argument("--progress-every", type=int, default=20)
    parser.add_argument(
        "--report",
        default="",
        help="Optional report path (defaults to data/processed/authors_backfill_report_<dataset>.json)",
    )
    args = parser.parse_args()

    cfg = DATASET_CONFIG[args.dataset]
    report_path = (
        Path(args.report).resolve()
        if args.report
        else ROOT / "data" / "processed" / f"authors_backfill_report_{args.dataset}.json"
    )

    stubs = load_json_array(cfg["stubs_json"])
    paper_db = load_json_array(cfg["paper_db_json"])

    schema = load_schema(cfg["schema"])
    required, enums, types, one_of_groups, allowed_keys = parse_schema(schema)

    config = load_config(Path(args.config).resolve())
    oa_cfg = config.get("openalex", {}) if isinstance(config.get("openalex", {}), dict) else {}
    s2_cfg = config.get("semantic_scholar", {}) if isinstance(config.get("semantic_scholar", {}), dict) else {}

    openalex_email = args.openalex_email or str(oa_cfg.get("email", "")) or os.getenv("OPENALEX_EMAIL", "")
    openalex_api_key = args.openalex_api_key or str(oa_cfg.get("api_key", "")) or os.getenv("OPENALEX_API_KEY", "")
    crossref_mailto = args.crossref_mailto or openalex_email
    openalex_rps = args.openalex_rps if args.openalex_rps is not None else read_float(oa_cfg.get("rate_limit_per_sec"), 2.0)
    max_retries = args.max_retries if args.max_retries is not None else read_int(s2_cfg.get("max_retries"), 4)
    client = RateLimitedHttpClient(
        rps=openalex_rps,
        max_retries=max_retries,
        user_agent="kg-pipeline/authors-backfill",
    )

    paper_by_doi: Dict[str, dict] = {}
    for row in paper_db:
        doi = normalize_doi(row.get("study_doi", "")).lower()
        if doi:
            paper_by_doi[doi] = row

    candidates: List[int] = []
    for idx, row in enumerate(stubs):
        status = normalize(row.get("stub_status", ""))
        if not args.all_statuses and status != args.status_filter:
            continue
        if status == "excluded_not_relevant":
            continue
        if normalize(row.get("authors", "")):
            continue
        candidates.append(idx)

    counts = {
        "stubs_total": len(stubs),
        "candidates": len(candidates),
        "updated_rows": 0,
        "ready_marked": 0,
        "resolved_from_paper_db": 0,
        "resolved_from_openalex": 0,
        "resolved_from_crossref": 0,
        "resolved_from_fallback_unknown": 0,
        "unresolved": 0,
        "paper_db_rows_updated": 0,
        "openalex_attempted": 0,
        "openalex_errors": 0,
        "crossref_attempted": 0,
        "crossref_errors": 0,
    }
    row_reports: List[dict] = []

    for seq, idx in enumerate(candidates, start=1):
        stub = stubs[idx]
        new_row = dict(stub)
        doi = normalize_doi(stub.get("study_doi", "")).lower()
        paper_row = paper_by_doi.get(doi)

        source_used = ""
        authors = ""
        changed_fields: List[str] = []
        openalex_error = ""
        crossref_error = ""

        if paper_row:
            authors = normalize(paper_row.get("authors", ""))
            if authors:
                source_used = "paper_db"
                counts["resolved_from_paper_db"] += 1

        if not authors and doi and not args.skip_openalex:
            counts["openalex_attempted"] += 1
            try:
                authors = lookup_openalex_authors(
                    client=client,
                    doi=doi,
                    email=openalex_email,
                    api_key=openalex_api_key,
                )
                authors = normalize(authors)
                if authors:
                    source_used = "openalex"
                    counts["resolved_from_openalex"] += 1
            except Exception as err:
                openalex_error = f"{type(err).__name__}: {err}"
                counts["openalex_errors"] += 1

        if not authors and doi and not args.skip_crossref:
            counts["crossref_attempted"] += 1
            try:
                authors = lookup_crossref_authors(client=client, doi=doi, mailto=crossref_mailto)
                authors = normalize(authors)
                if authors:
                    source_used = "crossref"
                    counts["resolved_from_crossref"] += 1
            except Exception as err:
                crossref_error = f"{type(err).__name__}: {err}"
                counts["crossref_errors"] += 1

        if not authors and args.fallback_unknown:
            authors = "Unknown"
            source_used = "fallback_unknown"
            counts["resolved_from_fallback_unknown"] += 1

        if authors:
            new_row["authors"] = authors
            changed_fields.append("authors")
            if paper_row is not None and normalize(paper_row.get("authors", "")) != authors:
                paper_row["authors"] = authors
                counts["paper_db_rows_updated"] += 1
        else:
            counts["unresolved"] += 1

        blocker_fields_after: List[str] = []
        if args.mark_ready:
            blocker_fields_after, blockers = evaluate_row(
                row=new_row,
                required=required,
                enums=enums,
                types=types,
                one_of_groups=one_of_groups,
                allowed_keys=allowed_keys,
            )
            if not blockers and normalize(new_row.get("stub_status", "")) != "ready_for_promotion":
                new_row["stub_status"] = "ready_for_promotion"
                changed_fields.append("stub_status")
                counts["ready_marked"] += 1

        if changed_fields:
            counts["updated_rows"] += 1

        stubs[idx] = new_row
        row_reports.append(
            {
                "stub_index": idx + 1,
                "study_doi": normalize(stub.get("study_doi", "")),
                "source_used": source_used or "none",
                "authors_after": normalize(new_row.get("authors", "")),
                "changed_fields": sorted(set(changed_fields)),
                "openalex_error": openalex_error,
                "crossref_error": crossref_error,
                "blocker_fields_after": blocker_fields_after,
            }
        )

        should_print_progress = (
            args.progress_every > 0
            and (seq % args.progress_every == 0 or seq == len(candidates))
        )
        if should_print_progress:
            pct = seq / max(1, len(candidates)) * 100.0
            print(
                "PROGRESS: authors_backfill "
                f"{seq}/{len(candidates)} ({pct:.1f}%) "
                f"updated={counts['updated_rows']} unresolved={counts['unresolved']} "
                f"ready_marked={counts['ready_marked']}",
                flush=True,
            )

    report = {
        "generated_at": now_utc(),
        "dataset": args.dataset,
        "status_filter": "*" if args.all_statuses else args.status_filter,
        "mark_ready": args.mark_ready,
        "fallback_unknown": args.fallback_unknown,
        "apply": args.apply,
        "counts": counts,
        "rows": row_reports,
    }

    if args.apply:
        write_json(cfg["stubs_json"], stubs)
        write_csv(cfg["stubs_csv"], stubs)
        write_json(cfg["paper_db_json"], paper_db)
        write_csv(cfg["paper_db_csv"], [flatten_paper_db_row(row) for row in paper_db])

    write_json(report_path, report)

    print(f"Dataset: {args.dataset}")
    print(f"Candidates: {counts['candidates']}")
    print(f"Updated rows: {counts['updated_rows']}")
    print(f"Ready marked: {counts['ready_marked']}")
    print(f"Resolved from paper DB: {counts['resolved_from_paper_db']}")
    print(f"Resolved from OpenAlex: {counts['resolved_from_openalex']}")
    print(f"Resolved from Crossref: {counts['resolved_from_crossref']}")
    if args.fallback_unknown:
        print(f"Resolved from fallback Unknown: {counts['resolved_from_fallback_unknown']}")
    print(f"Unresolved: {counts['unresolved']}")
    if args.apply:
        print(f"Stubs JSON: {cfg['stubs_json']}")
        print(f"Stubs CSV: {cfg['stubs_csv']}")
        print(f"Paper DB JSON: {cfg['paper_db_json']}")
        print(f"Paper DB CSV: {cfg['paper_db_csv']}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
