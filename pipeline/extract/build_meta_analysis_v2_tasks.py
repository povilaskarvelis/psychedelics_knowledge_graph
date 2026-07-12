#!/usr/bin/env python3
"""Build one paper-level v2 extraction task per retained meta-analysis."""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

try:
    from pipeline.extract.io_utils import read_jsonl, text_parts_from_packet, write_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.io_utils import read_jsonl, text_parts_from_packet, write_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATES = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_PACKETS = ROOT / "data" / "processed" / "extraction" / "fulltext_packets.jsonl"
DEFAULT_OUT_DIR = ROOT / "data" / "processed" / "extraction" / "meta_analysis_v2_tasks"
TASK_SCHEMA_VERSION = "meta_analysis_v2_task_v1"

META_ANALYSIS_TYPES = {"meta_analysis", "network_meta_analysis"}
READY_DEPTH_BY_STATUS = {
    "ready_for_article_text_extraction": "article_text",
    "ready_for_abstract_extraction": "abstract_only",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def normalized_doi(value: object) -> str:
    return clean(value).lower()


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).lower() in {"1", "true", "yes", "y"}


def fingerprint(*parts: object) -> str:
    joined = "\n\n".join(clean(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def packet_text_fingerprint(packet: dict) -> tuple[str, int]:
    text = "\n\n".join(text_parts_from_packet(packet))
    return fingerprint(text), len(text)


def candidate_index(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in rows:
        doi = normalized_doi(row.get("doi", ""))
        if doi and doi not in out:
            out[doi] = row
    return out


def packet_index(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in rows:
        doi = normalized_doi(row.get("study_doi", "") or row.get("doi", ""))
        if doi and doi not in out:
            out[doi] = row
    return out


def production_cohort(candidate_rows: list[dict]) -> tuple[list[dict], dict]:
    selected: list[dict] = []
    skipped: Counter = Counter()
    seen: set[str] = set()
    for candidate in candidate_rows:
        if not truthy(candidate.get("retained_for_extraction_candidate", False)):
            continue
        source_type = clean(candidate.get("primary_secondary_source_type", ""))
        if source_type not in META_ANALYSIS_TYPES:
            continue
        doi = normalized_doi(candidate.get("doi", ""))
        if not doi:
            skipped["missing_doi"] += 1
            continue
        if doi in seen:
            skipped["duplicate_doi"] += 1
            continue
        route_status = clean(candidate.get("extraction_route_status", ""))
        text_depth = READY_DEPTH_BY_STATUS.get(route_status, "")
        if not text_depth:
            skipped[route_status or "source_not_ready"] += 1
            continue
        seen.add(doi)
        selected.append(
            {
                "doi": doi,
                "study_title": clean(candidate.get("study_title", "")),
                "study_year": clean(candidate.get("study_year", "")),
                "meta_analysis_type": source_type,
                "text_depth": text_depth,
            }
        )
    selected.sort(key=lambda row: row["doi"])
    return selected, {
        "selection": "retained_ready_meta_analyses",
        "included_source_types": sorted(META_ANALYSIS_TYPES),
        "selected": len(selected),
        "skipped": dict(skipped),
    }


def compact_metadata(cohort: dict, candidate: dict) -> dict:
    return {
        "doi": normalized_doi(cohort.get("doi", "")),
        "study_title": clean(candidate.get("study_title", "")) or clean(cohort.get("study_title", "")),
        "study_year": clean(candidate.get("study_year", "")) or clean(cohort.get("study_year", "")),
        "abstract": clean(candidate.get("abstract", "")),
        "publication_type": clean(candidate.get("publication_type", "")),
        "study_journal": clean(candidate.get("study_journal", "")),
        "meta_analysis_type": clean(cohort.get("meta_analysis_type", "")) or "meta_analysis",
    }


def build_task(cohort: dict, candidate: dict, packet: dict | None, packets_path: Path) -> dict:
    doi = normalized_doi(cohort.get("doi", ""))
    text_depth = clean(cohort.get("text_depth", ""))
    metadata = compact_metadata(cohort, candidate)
    warnings: list[str] = []

    if text_depth == "article_text":
        if packet is None:
            source_status = "missing_article_packet"
            source_fingerprint = ""
            source_chars = 0
            warnings.append("article_text_packet_missing")
        else:
            source_fingerprint, source_chars = packet_text_fingerprint(packet)
            source_status = "ready"
        source = {
            "kind": "article_text",
            "status": source_status,
            "packet_id": clean((packet or {}).get("packet_id", "")),
            "packet_path": str(packets_path.resolve()),
            "source_fingerprint": source_fingerprint,
            "source_chars": source_chars,
        }
    elif text_depth == "abstract_only":
        abstract = clean(metadata.get("abstract", ""))
        source_status = "ready" if abstract else "missing_abstract"
        if not abstract:
            warnings.append("abstract_missing")
        source_fingerprint = fingerprint(metadata.get("study_title", ""), abstract)
        source = {
            "kind": "abstract_only",
            "status": source_status,
            "packet_id": "",
            "packet_path": "",
            "source_fingerprint": source_fingerprint,
            "source_chars": len(abstract),
        }
    else:
        raise ValueError(f"Unsupported text depth `{text_depth}` for {doi}")

    task_id = "metav2:" + fingerprint(TASK_SCHEMA_VERSION, doi, text_depth, source_fingerprint)[:20]
    return {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task_id,
        "study_doi": doi,
        "text_depth": text_depth,
        "paper_metadata": metadata,
        "source": source,
        "task_status": "ready_for_model" if source["status"] == "ready" else "source_not_ready",
        "warnings": warnings,
    }


def build_tasks(
    cohort_rows: list[dict],
    candidate_rows: list[dict],
    packet_rows: list[dict],
    *,
    packets_path: Path,
) -> tuple[list[dict], dict]:
    candidates = candidate_index(candidate_rows)
    packets = packet_index(packet_rows)
    tasks: list[dict] = []
    seen: set[str] = set()
    for cohort in cohort_rows:
        doi = normalized_doi(cohort.get("doi", ""))
        if not doi or doi in seen:
            raise ValueError(f"Missing or duplicate cohort DOI `{doi}`")
        seen.add(doi)
        tasks.append(build_task(cohort, candidates.get(doi, {}), packets.get(doi), packets_path))

    report = {
        "schema_version": "meta_analysis_v2_task_build_report_v1",
        "generated_at_utc": now_utc(),
        "counts": {
            "papers_selected": len(cohort_rows),
            "tasks": len(tasks),
            "unique_dois": len({task["study_doi"] for task in tasks}),
            "ready_for_model": sum(task["task_status"] == "ready_for_model" for task in tasks),
            "source_not_ready": sum(task["task_status"] != "ready_for_model" for task in tasks),
        },
        "by_text_depth": dict(Counter(task["text_depth"] for task in tasks)),
        "by_meta_analysis_type": dict(
            Counter(task["paper_metadata"]["meta_analysis_type"] for task in tasks)
        ),
        "by_source_status": dict(Counter(task["source"]["status"] for task in tasks)),
    }
    return tasks, report


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-jsonl", type=Path, default=None)
    parser.add_argument("--candidate-parquet", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--packets-jsonl", type=Path, default=DEFAULT_PACKETS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidate_rows = pd.read_parquet(args.candidate_parquet).to_dict("records")
    if args.cohort_jsonl:
        cohort_rows = read_jsonl(args.cohort_jsonl)
        selection_report = {
            "selection": "explicit_cohort",
            "cohort_jsonl": str(args.cohort_jsonl.resolve()),
            "selected": len(cohort_rows),
        }
    else:
        cohort_rows, selection_report = production_cohort(candidate_rows)
    packet_rows = read_jsonl(args.packets_jsonl)
    tasks, report = build_tasks(cohort_rows, candidate_rows, packet_rows, packets_path=args.packets_jsonl)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    tasks_path = args.out_dir / "meta_analysis_v2_tasks.jsonl"
    report_path = args.out_dir / "task_build_report.json"
    write_jsonl(tasks_path, tasks)
    report["selection"] = selection_report
    report["inputs"] = {
        "candidate_parquet": str(args.candidate_parquet.resolve()),
        "packets_jsonl": str(args.packets_jsonl.resolve()),
    }
    report["outputs"] = {
        "tasks_jsonl": str(tasks_path.resolve()),
        "report_json": str(report_path.resolve()),
    }
    write_json(report_path, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
