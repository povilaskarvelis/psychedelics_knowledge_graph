#!/usr/bin/env python3
"""Export stage-specific queues from the context promotion plan."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
VERSION = "0.1"

DEFAULT_PLAN = ROOT / "data" / "processed" / "context_promotion_plan.json"
DEFAULT_QUEUE_DIR = ROOT / "data" / "processed" / "context_queues"
DEFAULT_DOI_DIR = ROOT / "data" / "raw"
DEFAULT_MANIFEST = ROOT / "data" / "processed" / "context_queue_manifest.json"

QUEUE_STAGES = [
    "noise_review",
    "curation_review",
    "exploratory_claim_review",
    "full_text_extraction_ready",
    "screened_needs_pdf_or_abstract_extraction",
    "abstract_screening_needed",
    "verified_evidence",
]

QUEUE_ACTION_HINTS = {
    "noise_review": "Review possible acronym/entity collisions before using these contexts as evidence.",
    "curation_review": "Open existing claim stubs, fix blockers, then mark ready_for_promotion.",
    "exploratory_claim_review": "Review exploratory evidence before promoting to the public KG.",
    "full_text_extraction_ready": "Run full-text extraction or LLM evidence assessment against local PDFs.",
    "screened_needs_pdf_or_abstract_extraction": "Acquire full text when possible; otherwise create explicit abstract-only evidence.",
    "abstract_screening_needed": "Run abstract/title screening before attempting evidence extraction.",
    "verified_evidence": "Retain as current public-KG evidence unless a future audit flag changes.",
}

CSV_FIELDS = [
    "priority_score",
    "promotion_stage",
    "recommended_action",
    "dataset",
    "doi",
    "compound",
    "entity",
    "entity_type",
    "verification_layer",
    "revalidation_status",
    "has_local_pdf",
    "library_status",
    "pdf_download_status",
    "study_title",
    "study_year",
    "context_sources",
    "blocking_flags",
    "source_artifacts",
    "context_id",
]

DOI_FIELDS = ["doi", "compound", "entity", "study_title", "study_year"]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def load_plan(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    records = payload.get("records", [])
    if not isinstance(records, list):
        raise ValueError(f"Expected records[] in {path}")
    return [row for row in records if isinstance(row, dict)]


def select_rows(
    records: Iterable[dict],
    dataset: str = "all",
    include_verified: bool = False,
    limit_per_stage: int = 0,
) -> dict[str, list[dict]]:
    selected: dict[str, list[dict]] = {stage: [] for stage in QUEUE_STAGES}
    for row in records:
        if dataset != "all" and normalize(row.get("dataset")) != dataset:
            continue
        stage = normalize(row.get("promotion_stage"))
        if stage == "verified_evidence" and not include_verified:
            continue
        if stage not in selected:
            continue
        selected[stage].append(row)

    for stage, rows in selected.items():
        rows.sort(
            key=lambda item: (
                -int(item.get("priority_score") or 0),
                normalize(item.get("dataset")),
                normalize(item.get("doi")),
                normalize(item.get("compound")),
                normalize(item.get("entity")),
            )
        )
        if limit_per_stage > 0:
            selected[stage] = rows[:limit_per_stage]
    return selected


def csv_value(row: dict, field: str) -> object:
    value = row.get(field, "")
    if isinstance(value, list):
        return " | ".join(normalize(item) for item in value if normalize(item))
    return value


def write_queue_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row, field) for field in CSV_FIELDS})


def write_doi_queue(path: Path, rows: list[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    seen: set[tuple[str, str, str]] = set()
    written = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("# doi,compound,entity,study_title,study_year\n")
        writer = csv.DictWriter(handle, fieldnames=DOI_FIELDS)
        for row in rows:
            key = (
                normalize(row.get("doi")).lower(),
                normalize(row.get("compound")).lower(),
                normalize(row.get("entity")).lower(),
            )
            if not all(key) or key in seen:
                continue
            seen.add(key)
            writer.writerow(
                {
                    "doi": normalize(row.get("doi")),
                    "compound": normalize(row.get("compound")),
                    "entity": normalize(row.get("entity")),
                    "study_title": normalize(row.get("study_title")),
                    "study_year": normalize(row.get("study_year")),
                }
            )
            written += 1
    return written


def build_manifest(
    queues: dict[str, list[dict]],
    queue_dir: Path,
    doi_dir: Path,
    queue_files: dict[str, str],
    doi_files: dict[str, dict[str, object]],
    dataset: str,
    include_verified: bool,
    limit_per_stage: int,
) -> dict:
    stage_counts = {stage: len(rows) for stage, rows in queues.items() if rows}
    dataset_counts = Counter(row.get("dataset", "") for rows in queues.values() for row in rows)
    stage_dataset_counts: dict[str, dict[str, int]] = {}
    for stage, rows in queues.items():
        counts = Counter(row.get("dataset", "") for row in rows)
        if counts:
            stage_dataset_counts[stage] = dict(sorted(counts.items()))

    top_examples = {}
    for stage, rows in queues.items():
        if not rows:
            continue
        top_examples[stage] = [
            {
                "priority_score": row.get("priority_score", 0),
                "dataset": row.get("dataset", ""),
                "doi": row.get("doi", ""),
                "compound": row.get("compound", ""),
                "entity": row.get("entity", ""),
                "recommended_action": row.get("recommended_action", ""),
            }
            for row in rows[:10]
        ]

    return {
        "version": VERSION,
        "generated_at_utc": now_utc(),
        "input_plan": str(DEFAULT_PLAN),
        "dataset_filter": dataset,
        "include_verified": include_verified,
        "limit_per_stage": limit_per_stage,
        "queue_dir": str(queue_dir),
        "doi_queue_dir": str(doi_dir),
        "summary": {
            "stage_counts": stage_counts,
            "dataset_counts": dict(sorted(dataset_counts.items())),
            "stage_dataset_counts": stage_dataset_counts,
            "exported_contexts": sum(stage_counts.values()),
            "queue_file_count": len(queue_files),
            "doi_queue_file_count": sum(len(files) for files in doi_files.values()),
        },
        "action_hints": {stage: QUEUE_ACTION_HINTS[stage] for stage in stage_counts},
        "queue_files": queue_files,
        "doi_queue_files": doi_files,
        "top_examples": top_examples,
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def export_queues(
    records: list[dict],
    queue_dir: Path,
    doi_dir: Path,
    dataset: str = "all",
    include_verified: bool = False,
    limit_per_stage: int = 0,
) -> dict:
    queues = select_rows(
        records,
        dataset=dataset,
        include_verified=include_verified,
        limit_per_stage=limit_per_stage,
    )

    queue_files: dict[str, str] = {}
    doi_files: dict[str, dict[str, object]] = defaultdict(dict)
    for stage, rows in queues.items():
        if not rows:
            continue

        csv_path = queue_dir / f"{stage}.csv"
        write_queue_csv(csv_path, rows)
        queue_files[stage] = str(csv_path)

        by_dataset: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            by_dataset[normalize(row.get("dataset"))].append(row)

        for row_dataset, dataset_rows in sorted(by_dataset.items()):
            if not row_dataset:
                continue
            doi_path = doi_dir / f"doi_queue.{row_dataset}.context_{stage}.txt"
            written = write_doi_queue(doi_path, dataset_rows)
            doi_files[stage][row_dataset] = {
                "path": str(doi_path),
                "context_rows": len(dataset_rows),
                "unique_doi_context_rows": written,
            }

    return build_manifest(
        queues=queues,
        queue_dir=queue_dir,
        doi_dir=doi_dir,
        queue_files=queue_files,
        doi_files=dict(doi_files),
        dataset=dataset,
        include_verified=include_verified,
        limit_per_stage=limit_per_stage,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Export actionable context promotion queues")
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--queue-dir", default=str(DEFAULT_QUEUE_DIR))
    parser.add_argument("--doi-queue-dir", default=str(DEFAULT_DOI_DIR))
    parser.add_argument("--manifest-out", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--dataset", choices=["all", "mechanistic", "disorder"], default="all")
    parser.add_argument("--include-verified", action="store_true")
    parser.add_argument("--limit-per-stage", type=int, default=0)
    args = parser.parse_args()

    plan_path = Path(args.plan).resolve()
    records = load_plan(plan_path)
    queue_dir = Path(args.queue_dir).resolve()
    doi_dir = Path(args.doi_queue_dir).resolve()
    manifest = export_queues(
        records=records,
        queue_dir=queue_dir,
        doi_dir=doi_dir,
        dataset=args.dataset,
        include_verified=args.include_verified,
        limit_per_stage=args.limit_per_stage,
    )
    manifest["input_plan"] = str(plan_path)
    write_json(Path(args.manifest_out).resolve(), manifest)

    summary = manifest["summary"]
    print(f"Exported contexts: {summary['exported_contexts']}")
    print(f"Queue files: {summary['queue_file_count']}")
    print(f"DOI queue files: {summary['doi_queue_file_count']}")
    print(f"Manifest: {Path(args.manifest_out).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
