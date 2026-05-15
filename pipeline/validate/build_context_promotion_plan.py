#!/usr/bin/env python3
"""Build actionable promotion queues from the context provenance audit."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
VERSION = "0.1"

DEFAULT_CONTEXT_AUDIT = ROOT / "data" / "processed" / "context_provenance_audit.json"
DEFAULT_PAPER_CORPUS = ROOT / "data" / "processed" / "candidate_paper_corpus.json"
DEFAULT_PLAN_OUT = ROOT / "data" / "processed" / "context_promotion_plan.json"
DEFAULT_WORKLIST_OUT = ROOT / "data" / "processed" / "context_promotion_worklist.csv"
DEFAULT_EDGE_OUT = ROOT / "data" / "processed" / "context_edge_rollup.json"
DEFAULT_SUMMARY_OUT = ROOT / "data" / "processed" / "context_promotion_summary.json"

CSV_FIELDS = [
    "priority_score",
    "queue_family",
    "promotion_stage",
    "recommended_action",
    "public_kg_ready",
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

STAGE_BASE_PRIORITY = {
    "noise_review": 95,
    "curation_review": 90,
    "exploratory_claim_review": 86,
    "full_text_extraction_ready": 80,
    "screened_needs_pdf_or_abstract_extraction": 70,
    "abstract_screening_needed": 45,
    "verified_evidence": 20,
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_doi(raw: object) -> str:
    text = normalize(raw)
    if not text:
        return ""
    lowered = text.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip().lower()


def key_text(raw: object) -> str:
    text = normalize(raw).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_records(path: Path, required: bool = True) -> list[dict]:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Missing required input: {path}")
        return []
    payload = load_json(path)
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        records = payload.get("records", [])
        if isinstance(records, list):
            return [row for row in records if isinstance(row, dict)]
    raise ValueError(f"Expected JSON list or object with records[] at {path}")


def papers_by_doi(papers: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for paper in papers:
        doi = normalize_doi(paper.get("doi") or paper.get("study_doi"))
        if doi:
            out[doi] = paper
    return out


def paper_has_local_pdf(paper: dict | None) -> bool:
    if not paper:
        return False
    flags = paper.get("flags", {}) if isinstance(paper.get("flags"), dict) else {}
    return bool(flags.get("has_local_pdf") or paper.get("local_pdf_paths"))


def paper_metadata(paper: dict | None, field: str) -> str:
    if not paper:
        return ""
    direct = normalize(paper.get(field))
    if direct:
        return direct
    metadata = paper.get("metadata", {}) if isinstance(paper.get("metadata"), dict) else {}
    return normalize(metadata.get(field))


def context_source_artifacts(context: dict) -> list[str]:
    artifacts = []
    for item in context.get("provenance", []):
        if not isinstance(item, dict):
            continue
        artifact = normalize(item.get("source_artifact"))
        if artifact:
            artifacts.append(artifact)
    return sorted(set(artifacts))


def classify_context(context: dict, paper: dict | None) -> dict:
    flags = context.get("flags", {}) if isinstance(context.get("flags"), dict) else {}
    layer = normalize(context.get("verification_layer"))
    has_pdf = paper_has_local_pdf(paper)
    blocking_flags: list[str] = []

    if flags.get("possible_acronym_collision"):
        blocking_flags.append("possible_acronym_collision")
        return {
            "promotion_stage": "noise_review",
            "queue_family": "noise_review",
            "recommended_action": "review_possible_acronym_or_entity_collision",
            "public_kg_ready": False,
            "blocking_flags": blocking_flags,
        }

    if flags.get("has_curated_claim") or layer == "verified_evidence":
        return {
            "promotion_stage": "verified_evidence",
            "queue_family": "verified",
            "recommended_action": "retain_in_curated_kg",
            "public_kg_ready": True,
            "blocking_flags": blocking_flags,
        }

    if flags.get("has_claim_stub"):
        blocking_flags.append("claim_stub_not_curated")
        return {
            "promotion_stage": "curation_review",
            "queue_family": "curation",
            "recommended_action": "curate_existing_claim_stub",
            "public_kg_ready": False,
            "blocking_flags": blocking_flags,
        }

    if flags.get("has_exploratory_claim"):
        blocking_flags.append("exploratory_claim_not_public")
        return {
            "promotion_stage": "exploratory_claim_review",
            "queue_family": "curation",
            "recommended_action": "review_exploratory_claim_before_public_kg",
            "public_kg_ready": False,
            "blocking_flags": blocking_flags,
        }

    if layer == "screened_context":
        blocking_flags.append("no_structured_claim")
        if has_pdf:
            return {
                "promotion_stage": "full_text_extraction_ready",
                "queue_family": "evidence_extraction",
                "recommended_action": "extract_structured_claim_from_full_text",
                "public_kg_ready": False,
                "blocking_flags": blocking_flags,
            }
        blocking_flags.append("no_local_pdf")
        return {
            "promotion_stage": "screened_needs_pdf_or_abstract_extraction",
            "queue_family": "evidence_extraction",
            "recommended_action": "obtain_full_text_or_extract_abstract_only_claim",
            "public_kg_ready": False,
            "blocking_flags": blocking_flags,
        }

    blocking_flags.append("not_screened")
    return {
        "promotion_stage": "abstract_screening_needed",
        "queue_family": "screening",
        "recommended_action": "screen_candidate_context",
        "public_kg_ready": False,
        "blocking_flags": blocking_flags,
    }


def priority_score(context: dict, paper: dict | None, stage: str) -> int:
    flags = context.get("flags", {}) if isinstance(context.get("flags"), dict) else {}
    score = STAGE_BASE_PRIORITY.get(stage, 0)
    if flags.get("has_known_study_context"):
        score += 12
    if paper_has_local_pdf(paper):
        score += 8
    if flags.get("has_llm_verified_context"):
        score += 8
    if flags.get("has_triage_matched_context"):
        score += 5
    if flags.get("has_triage_synthesized_context"):
        score += 3
    if flags.get("has_seed_or_discovery_context"):
        score += 2
    score += min(len(context.get("context_sources", [])), 5)
    return score


def worklist_record(context: dict, paper: dict | None) -> dict:
    classification = classify_context(context, paper)
    stage = classification["promotion_stage"]
    record = {
        "context_id": normalize(context.get("context_id")),
        "dataset": normalize(context.get("dataset")),
        "doi": normalize_doi(context.get("doi")),
        "compound": normalize(context.get("compound")),
        "entity": normalize(context.get("entity")),
        "entity_type": normalize(context.get("entity_type")),
        "verification_layer": normalize(context.get("verification_layer")),
        "revalidation_status": normalize(context.get("revalidation_status")),
        "context_sources": sorted(normalize(source) for source in context.get("context_sources", []) if normalize(source)),
        "source_artifacts": context_source_artifacts(context),
        "has_local_pdf": paper_has_local_pdf(paper),
        "library_status": paper_metadata(paper, "library_status"),
        "pdf_download_status": paper_metadata(paper, "pdf_download_status"),
        "study_title": paper_metadata(paper, "study_title"),
        "study_year": paper_metadata(paper, "study_year"),
        **classification,
    }
    record["priority_score"] = priority_score(context, paper, stage)
    return record


def edge_key(record: dict) -> str:
    return "|".join(
        [
            normalize(record.get("dataset")),
            key_text(record.get("compound")),
            key_text(record.get("entity")),
        ]
    )


def edge_status(records: list[dict]) -> str:
    clean = [row for row in records if row.get("promotion_stage") != "noise_review"]
    if not clean:
        return "needs_noise_review"
    if any(row.get("public_kg_ready") for row in clean):
        return "verified_edge"
    if any(row.get("promotion_stage") in {"curation_review", "exploratory_claim_review"} for row in clean):
        return "curation_ready_edge_candidate"
    if any(
        row.get("promotion_stage")
        in {"full_text_extraction_ready", "screened_needs_pdf_or_abstract_extraction"}
        for row in clean
    ):
        return "screened_edge_candidate"
    return "candidate_edge"


def build_edge_rollup(worklist: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in worklist:
        grouped[edge_key(row)].append(row)

    rollups = []
    for rows in grouped.values():
        rows_sorted = sorted(rows, key=lambda row: (-int(row.get("priority_score", 0)), row.get("doi", "")))
        best = rows_sorted[0]
        stage_counts = Counter(row.get("promotion_stage", "") for row in rows)
        queue_counts = Counter(row.get("queue_family", "") for row in rows)
        status = edge_status(rows)
        rollups.append(
            {
                "edge_id": edge_key(best),
                "dataset": best.get("dataset", ""),
                "compound": best.get("compound", ""),
                "entity": best.get("entity", ""),
                "entity_type": best.get("entity_type", ""),
                "edge_status": status,
                "recommended_action": best.get("recommended_action", ""),
                "context_count": len(rows),
                "verified_contexts": sum(1 for row in rows if row.get("public_kg_ready")),
                "screened_contexts": sum(
                    1
                    for row in rows
                    if row.get("promotion_stage")
                    in {"full_text_extraction_ready", "screened_needs_pdf_or_abstract_extraction"}
                ),
                "candidate_contexts": stage_counts.get("abstract_screening_needed", 0),
                "possible_noise_contexts": stage_counts.get("noise_review", 0),
                "stage_counts": dict(sorted(stage_counts.items())),
                "queue_counts": dict(sorted(queue_counts.items())),
                "top_contexts": [
                    {
                        "context_id": row.get("context_id", ""),
                        "doi": row.get("doi", ""),
                        "promotion_stage": row.get("promotion_stage", ""),
                        "recommended_action": row.get("recommended_action", ""),
                        "priority_score": row.get("priority_score", 0),
                    }
                    for row in rows_sorted[:10]
                ],
            }
        )

    return sorted(
        rollups,
        key=lambda row: (
            row.get("dataset", ""),
            row.get("compound", "").lower(),
            row.get("entity", "").lower(),
        ),
    )


def build_summary(worklist: list[dict], edge_rollup: list[dict]) -> dict:
    stage_counts = Counter(row.get("promotion_stage", "") for row in worklist)
    action_counts = Counter(row.get("recommended_action", "") for row in worklist)
    queue_counts = Counter(row.get("queue_family", "") for row in worklist)
    dataset_counts = Counter(row.get("dataset", "") for row in worklist)
    edge_status_counts = Counter(row.get("edge_status", "") for row in edge_rollup)

    samples: dict[str, list[dict]] = {}
    for queue in sorted(queue_counts):
        queue_rows = [
            row
            for row in sorted(worklist, key=lambda item: (-int(item.get("priority_score", 0)), item.get("doi", "")))
            if row.get("queue_family") == queue
        ]
        samples[queue] = [
            {
                "priority_score": row.get("priority_score", 0),
                "promotion_stage": row.get("promotion_stage", ""),
                "dataset": row.get("dataset", ""),
                "doi": row.get("doi", ""),
                "compound": row.get("compound", ""),
                "entity": row.get("entity", ""),
                "recommended_action": row.get("recommended_action", ""),
            }
            for row in queue_rows[:10]
        ]

    return {
        "context_count": len(worklist),
        "edge_count": len(edge_rollup),
        "public_kg_ready_contexts": sum(1 for row in worklist if row.get("public_kg_ready")),
        "contexts_requiring_work": sum(1 for row in worklist if not row.get("public_kg_ready")),
        "promotion_stage_counts": dict(sorted(stage_counts.items())),
        "recommended_action_counts": dict(sorted(action_counts.items())),
        "queue_family_counts": dict(sorted(queue_counts.items())),
        "dataset_counts": dict(sorted(dataset_counts.items())),
        "edge_status_counts": dict(sorted(edge_status_counts.items())),
        "queue_samples": samples,
    }


def build_promotion_plan(contexts: list[dict], papers: list[dict]) -> dict:
    paper_lookup = papers_by_doi(papers)
    worklist = [
        worklist_record(context, paper_lookup.get(normalize_doi(context.get("doi"))))
        for context in contexts
    ]
    worklist = sorted(
        worklist,
        key=lambda row: (
            row.get("queue_family") == "verified",
            -int(row.get("priority_score", 0)),
            row.get("dataset", ""),
            row.get("doi", ""),
            row.get("compound", ""),
            row.get("entity", ""),
        ),
    )
    edge_rollup = build_edge_rollup(worklist)
    return {
        "version": VERSION,
        "generated_at_utc": now_utc(),
        "summary": build_summary(worklist, edge_rollup),
        "records": worklist,
        "edge_rollup": edge_rollup,
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_worklist_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            csv_row = dict(row)
            csv_row["context_sources"] = " | ".join(row.get("context_sources", []))
            csv_row["source_artifacts"] = " | ".join(row.get("source_artifacts", []))
            csv_row["blocking_flags"] = " | ".join(row.get("blocking_flags", []))
            writer.writerow({field: csv_row.get(field, "") for field in CSV_FIELDS})


def main() -> int:
    parser = argparse.ArgumentParser(description="Build KG context promotion queues from provenance audit outputs")
    parser.add_argument("--context-audit", default=str(DEFAULT_CONTEXT_AUDIT))
    parser.add_argument("--paper-corpus", default=str(DEFAULT_PAPER_CORPUS))
    parser.add_argument("--dataset", choices=["all", "mechanistic", "disorder"], default="all")
    parser.add_argument("--plan-out", default=str(DEFAULT_PLAN_OUT))
    parser.add_argument("--worklist-out", default=str(DEFAULT_WORKLIST_OUT))
    parser.add_argument("--edge-out", default=str(DEFAULT_EDGE_OUT))
    parser.add_argument("--summary-out", default=str(DEFAULT_SUMMARY_OUT))
    args = parser.parse_args()

    context_path = Path(args.context_audit).resolve()
    paper_path = Path(args.paper_corpus).resolve()
    contexts = load_records(context_path, required=True)
    papers = load_records(paper_path, required=False)
    if args.dataset != "all":
        contexts = [row for row in contexts if normalize(row.get("dataset")) == args.dataset]

    plan = build_promotion_plan(contexts, papers)
    plan["input_artifacts"] = [str(context_path), str(paper_path)]

    summary_payload = {
        "version": plan["version"],
        "generated_at_utc": plan["generated_at_utc"],
        "input_artifacts": plan["input_artifacts"],
        "summary": plan["summary"],
    }
    edge_payload = {
        "version": plan["version"],
        "generated_at_utc": plan["generated_at_utc"],
        "input_artifacts": plan["input_artifacts"],
        "records": plan["edge_rollup"],
    }

    write_json(Path(args.plan_out).resolve(), plan)
    write_worklist_csv(Path(args.worklist_out).resolve(), plan["records"])
    write_json(Path(args.edge_out).resolve(), edge_payload)
    write_json(Path(args.summary_out).resolve(), summary_payload)

    summary = plan["summary"]
    print(f"Contexts: {summary['context_count']}")
    print(f"Edges: {summary['edge_count']}")
    print(f"Public KG ready contexts: {summary['public_kg_ready_contexts']}")
    print(f"Contexts requiring work: {summary['contexts_requiring_work']}")
    print(f"Plan: {Path(args.plan_out).resolve()}")
    print(f"Worklist CSV: {Path(args.worklist_out).resolve()}")
    print(f"Edge rollup: {Path(args.edge_out).resolve()}")
    print(f"Summary: {Path(args.summary_out).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
