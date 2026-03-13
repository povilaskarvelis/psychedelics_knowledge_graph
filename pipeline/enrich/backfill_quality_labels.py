#!/usr/bin/env python3
"""Backfill paper_type and disorder result_direction for stubs and curated rows."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[2]

DATASET_CONFIG = {
    "mechanistic": {
        "paper_db_json": ROOT / "data" / "processed" / "paper_library_mechanistic.json",
        "stubs_json": ROOT / "data" / "processed" / "mechanistic_claim_stubs.json",
        "stubs_csv": ROOT / "data" / "processed" / "mechanistic_claim_stubs.csv",
        "curated_json": ROOT / "data" / "curated" / "claims.json",
        "curated_csv": ROOT / "data" / "curated" / "claims.csv",
    },
    "disorder": {
        "paper_db_json": ROOT / "data" / "processed" / "paper_library_disorder.json",
        "stubs_json": ROOT / "data" / "processed" / "disorder_claim_stubs.json",
        "stubs_csv": ROOT / "data" / "processed" / "disorder_claim_stubs.csv",
        "curated_json": ROOT / "data" / "curated" / "disorder_claims.json",
        "curated_csv": ROOT / "data" / "curated" / "disorder_claims.csv",
    },
}

PROTOCOL_KEYWORDS = {
    "study protocol",
    "trial protocol",
    "protocol for",
    "protocol:",
    "study design",
}

CONFERENCE_OR_POSTER_KEYWORDS = {
    "poster abstract",
    "poster abstracts",
    "meeting abstract",
    "meeting abstracts",
    "annual meeting",
    "scientific meeting",
    "conference abstract",
    "conference proceedings",
    "psychopharmacology congress",
    "supplement",
}

REVIEWISH_KEYWORDS = {
    "systematic review",
    "narrative review",
    "scoping review",
    "umbrella review",
    "literature review",
    "review article",
    "rapid review",
    "meta analysis",
    "meta-analysis",
    "pooled analysis",
}


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


def normalize_text(raw: str) -> str:
    lowered = normalize(raw).lower()
    cleaned = []
    for ch in lowered:
        cleaned.append(ch if ch.isalnum() else " ")
    return " ".join("".join(cleaned).split())


def load_json_array(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return data


def write_json(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: List[dict]) -> None:
    ordered: List[str] = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key in seen:
                continue
            seen.add(key)
            ordered.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ordered)
        writer.writeheader()
        writer.writerows(rows)


def detect_paper_type(text_norm: str, dataset: str) -> str:
    if any(normalize_text(kw) in text_norm for kw in CONFERENCE_OR_POSTER_KEYWORDS):
        return "conference_or_poster_abstract"
    if any(normalize_text(kw) in text_norm for kw in PROTOCOL_KEYWORDS):
        return "protocol"
    if any(normalize_text(kw) in text_norm for kw in REVIEWISH_KEYWORDS):
        return "review"

    primary_keywords = {
        "randomized",
        "placebo",
        "double blind",
        "double-blind",
        "phase 2",
        "phase 3",
        "clinical trial",
        "open label",
        "open-label",
        "participants",
        "patients",
    }
    if dataset == "mechanistic":
        primary_keywords = {
            "binding",
            "affinity",
            "radioligand",
            "assay",
            "ic50",
            "ec50",
            "ki",
            "kd",
            "agonist",
            "antagonist",
            "receptor",
            "transporter",
            "in vitro",
            "in vivo",
        }

    hits = [kw for kw in primary_keywords if normalize_text(kw) in text_norm]
    if len(hits) >= 2:
        return "primary_results"
    return "other"


def infer_result_direction(text_norm: str, outcome_type: str, current: str) -> str:
    cur = normalize(current).lower()
    if cur in {"positive", "null", "negative", "mixed"}:
        return cur

    text = normalize_text(f"{normalize(outcome_type)} {normalize(text_norm)}")
    has_null = any(
        token in text
        for token in {
            "no significant",
            "not significant",
            "no difference",
            "did not improve",
            "did not reduce",
            "not associated",
            "no association",
            "failed to show",
        }
    )
    has_negative = any(
        token in text
        for token in {
            "worsened",
            "worsening",
            "increased symptoms",
            "greater severity",
            "adverse effect",
            "adverse effects",
            "harmful",
            "poorer outcome",
            "poorer outcomes",
        }
    )
    has_positive = any(
        token in text
        for token in {
            "reduced symptoms",
            "reduces",
            "reduction",
            "improved",
            "improves",
            "improvement",
            "response",
            "remission",
            "abstinence",
            "reduced drinking",
            "reduced craving",
            "decreased severity",
            "supports smoking abstinence",
        }
    )

    if sum([has_positive, has_null, has_negative]) >= 2:
        return "mixed"
    if has_null:
        return "null"
    if has_negative:
        return "negative"
    if has_positive:
        return "positive"
    return "unclear"


def paper_by_doi(rows: List[dict]) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for row in rows:
        doi = normalize_doi(row.get("study_doi", "")).lower()
        if doi:
            out[doi] = row
    return out


def should_replace_paper_type(current: str, detected: str) -> bool:
    cur = normalize(current)
    if not cur or cur == "other":
        return True
    return cur != detected and detected in {"review", "protocol", "conference_or_poster_abstract"}


def backfill_rows(dataset: str, rows: List[dict], paper_lookup: Dict[str, dict]) -> Dict[str, int]:
    counts = {
        "rows": len(rows),
        "paper_type_updates": 0,
        "result_direction_updates": 0,
    }
    for row in rows:
        doi = normalize_doi(row.get("study_doi", "")).lower()
        paper = paper_lookup.get(doi, {})
        text_norm = normalize_text(
            " ".join(
                [
                    normalize(row.get("study_title", "")),
                    normalize(paper.get("study_title", "")),
                    normalize(paper.get("abstract", "")),
                    normalize(row.get("notes", "")),
                ]
            )
        )

        detected_paper_type = detect_paper_type(text_norm, dataset)
        if should_replace_paper_type(row.get("paper_type", ""), detected_paper_type):
            row["paper_type"] = detected_paper_type
            counts["paper_type_updates"] += 1

        if dataset == "disorder":
            current_direction = normalize(row.get("result_direction", ""))
            if normalize(row.get("paper_type", "")) != "primary_results":
                detected_direction = "unclear"
            else:
                detected_direction = infer_result_direction(
                    text_norm=text_norm,
                    outcome_type=normalize(row.get("outcome_type", "")),
                    current=current_direction,
                )
            if current_direction in {"", "unclear"} and detected_direction != current_direction:
                row["result_direction"] = detected_direction
                counts["result_direction_updates"] += 1

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill paper_type and disorder result_direction labels")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder", "all"], default="all")
    parser.add_argument("--apply", action="store_true", help="Write backfilled values to JSON/CSV files")
    args = parser.parse_args()

    datasets = ["mechanistic", "disorder"] if args.dataset == "all" else [args.dataset]

    for dataset in datasets:
        cfg = DATASET_CONFIG[dataset]
        papers = load_json_array(cfg["paper_db_json"])
        lookup = paper_by_doi(papers)

        stubs = load_json_array(cfg["stubs_json"])
        curated = load_json_array(cfg["curated_json"])

        stub_counts = backfill_rows(dataset, stubs, lookup)
        curated_counts = backfill_rows(dataset, curated, lookup)

        if args.apply:
            write_json(cfg["stubs_json"], stubs)
            write_csv(cfg["stubs_csv"], stubs)
            write_json(cfg["curated_json"], curated)
            write_csv(cfg["curated_csv"], curated)

        print(f"Dataset: {dataset}")
        print(
            "Stubs: "
            f"rows={stub_counts['rows']} "
            f"paper_type_updates={stub_counts['paper_type_updates']} "
            f"result_direction_updates={stub_counts['result_direction_updates']}"
        )
        print(
            "Curated: "
            f"rows={curated_counts['rows']} "
            f"paper_type_updates={curated_counts['paper_type_updates']} "
            f"result_direction_updates={curated_counts['result_direction_updates']}"
        )
        if args.apply:
            print(f"Updated: {cfg['stubs_json']}")
            print(f"Updated: {cfg['curated_json']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
