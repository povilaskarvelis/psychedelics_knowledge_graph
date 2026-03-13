#!/usr/bin/env python3
"""Resolve obvious disorder manual-review rows with conservative title rules."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional


ROOT = Path(__file__).resolve().parents[2]

CURATED_JSON = ROOT / "data" / "curated" / "disorder_claims.json"
CURATED_CSV = ROOT / "data" / "curated" / "disorder_claims.csv"
PAPER_DB_JSON = ROOT / "data" / "processed" / "paper_library_disorder.json"
CLEANUP_JSON = ROOT / "data" / "processed" / "cleanup_candidates.json"


REVIEW_TITLE_PATTERNS = [
    r"\breview\b",
    r"review paper",
    r"review of literature",
    r"current understanding",
    r"current molecular knowledge",
    r"in clinical practice",
    r"history, neurobiology, and therapeutic potential",
    r"new era",
    r"current state",
    r"transitioning from",
    r"summary of research",
    r"adis summary",
    r"rationale and design",
    r"design considerations",
    r"\bconsensus\b",
    r"\bviewpoint\b",
    r"personalized use",
    r"may reshape",
    r"hallucinogenic potential",
    r"facts and myths",
    r"regulatory perspectives",
    r"real-world challenges",
    r"spravato .*sexual side effect profile",
    r"mdma to treat ptsd in adults$",
    r"psychedelic drugs.*psychiatry",
]

REVIEW_ABSTRACT_PATTERNS = [
    r"\bthis review\b",
    r"\bthis article covers\b",
    r"\bstrong evidence supports\b",
    r"\breview explores\b",
    r"\breview focuses\b",
]

PROTOCOL_TITLE_PATTERNS = [
    r"\bprotocol\b",
    r"rationale and design",
    r"design considerations",
]

OTHER_LOW_TITLE_PATTERNS = [
    r"cost[- ]utility",
    r"cost[- ]effectiveness",
    r"model-based",
    r"medical malpractice risk",
    r"physicians[’'] concerns",
    r"who will staff",
    r"therapeutic emergence of dissociated traumatic memories",
]

PRECLINICAL_OTHER_TITLE_PATTERNS = [
    r"\brats?\b",
    r"\bmice\b",
    r"mouse model",
    r"experimental pain model",
    r"\bwistar\b",
    r"blast exposure",
]

PRIMARY_HIGH_TITLE_PATTERNS = [
    r"esketamine nasal spray plus oral antidepressant",
    r"rapid reduction .* suicidal ideation",
    r"\bfmri\b",
    r"functional connectivity",
    r"eeg biomarkers",
    r"rapid neuroplasticity",
    r"blinded extension phase",
    r"six month follow up",
    r"six-month follow-up",
    r"interim results",
    r"randomized crossover study",
    r"time to remission",
    r"safety and tolerability",
    r"efficacy and safety",
    r"shows effectiveness",
    r"processing of musical surprises",
    r"comparison study",
    r"effect of naltrexone pretreatment",
    r"concomitant ssri",
    r"thalamocortical functional connectivity",
    r"effects of ketamine on individual symptoms",
]

PRIMARY_MEDIUM_TITLE_PATTERNS = [
    r"post hoc analysis",
    r"post-hoc analysis",
    r"secondary analysis",
    r"mechanism of action",
    r"health related quality of life",
    r"quality of life",
    r"predicting outcome",
    r"analysis of the ongoing sustain 3 study",
    r"long term safety and maintenance of response",
    r"long-term safety and maintenance of response",
    r"dissociable effects of",
]

PRIMARY_LOW_TITLE_PATTERNS = [
    r"case report",
    r"single-case",
    r"case series",
    r"retrospective case study",
    r"clinical case report",
    r"qualitative study",
    r"phenomenological analysis",
    r"patient.?s perspective",
    r"patient perspectives and experiences",
    r"survey study",
    r"population based survey study",
    r"population-based survey study",
    r"nationally representative sample",
    r"real world approach",
    r"real-world approach",
    r"real-world",
    r"\bretrospective\b",
    r"\bcohort\b",
    r"demographic and clinical profiles",
    r"use patterns",
    r"resource use",
    r"expanded use",
    r"single-arm",
    r"pilot randomized controlled trial",
    r"\bpilot study\b",
    r"treatment patterns",
    r"acute healthcare resource use",
    r"machine learning",
    r"machine-learning",
    r"preliminary report",
]


def normalize(value: object) -> str:
    return str(value or "").strip()


def normalize_doi(raw: object) -> str:
    text = normalize(raw)
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


def append_note(notes: object, message: str) -> str:
    base = normalize(notes)
    msg = normalize(message)
    if not msg:
        return base
    if base and msg.lower() in base.lower():
        return base
    if not base:
        return msg
    return f"{base}; {msg}"


def load_json_array(path: Path) -> List[dict]:
    return json.loads(path.read_text()) if path.exists() else []


def write_json(path: Path, rows: List[dict]) -> None:
    path.write_text(json.dumps(rows, indent=2) + "\n")


def write_csv(path: Path, rows: List[dict], fieldnames: List[str]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def row_matches_candidate(row: dict, candidate: dict, fields: Iterable[str]) -> bool:
    return all(normalize(row.get(field, "")) == normalize(candidate.get(field, "")) for field in fields)


def select_target_rows(rows: List[dict], cleanup_rows: List[dict]) -> List[tuple[int, dict]]:
    fields = [
        "compound",
        "disorder",
        "study_title",
        "study_doi",
        "paper_type",
        "source_type",
        "evidence_level",
        "access_level",
        "result_direction",
    ]
    selected: List[tuple[int, dict]] = []
    for candidate in cleanup_rows:
        row_index = int(candidate["row_index"]) - 1
        matches: List[int] = []
        if 0 <= row_index < len(rows) and row_matches_candidate(rows[row_index], candidate, fields):
            matches = [row_index]
        else:
            for idx, row in enumerate(rows):
                if row_matches_candidate(row, candidate, fields):
                    matches.append(idx)
        if not matches:
            continue
        if len(matches) > 1:
            raise RuntimeError(
                f"Ambiguous manual-review candidate match for row {candidate['row_index']}: {candidate.get('study_title', '')}"
            )
        selected.append((matches[0], candidate))
    return selected


def matches_any(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def classify_row(title: str, abstract: str) -> Optional[Dict[str, str]]:
    title_norm = normalize(title).lower()
    abstract_norm = normalize(abstract).lower()

    if matches_any(title_norm, PROTOCOL_TITLE_PATTERNS):
        return {
            "paper_type": "protocol",
            "source_type": "other",
            "evidence_level": "low",
            "reason": "title matched protocol pattern",
        }

    if matches_any(title_norm, REVIEW_TITLE_PATTERNS) or matches_any(abstract_norm, REVIEW_ABSTRACT_PATTERNS):
        return {
            "paper_type": "review",
            "source_type": "review",
            "evidence_level": "medium",
            "reason": "title/abstract matched review pattern",
        }

    if matches_any(title_norm, OTHER_LOW_TITLE_PATTERNS):
        return {
            "paper_type": "other",
            "source_type": "other",
            "evidence_level": "low",
            "reason": "title matched non-countable analysis/editorial pattern",
        }

    if matches_any(title_norm, PRECLINICAL_OTHER_TITLE_PATTERNS):
        return {
            "paper_type": "other",
            "source_type": "other",
            "evidence_level": "low",
            "reason": "title matched preclinical/animal-model pattern",
        }

    if matches_any(title_norm, PRIMARY_LOW_TITLE_PATTERNS):
        return {
            "paper_type": "primary_results",
            "source_type": "primary_study",
            "evidence_level": "low",
            "reason": "title matched low-evidence primary-study pattern",
        }

    if matches_any(title_norm, PRIMARY_MEDIUM_TITLE_PATTERNS):
        return {
            "paper_type": "primary_results",
            "source_type": "primary_study",
            "evidence_level": "medium",
            "reason": "title matched medium-evidence primary-study pattern",
        }

    if matches_any(title_norm, PRIMARY_HIGH_TITLE_PATTERNS):
        return {
            "paper_type": "primary_results",
            "source_type": "primary_study",
            "evidence_level": "high",
            "reason": "title matched high-evidence primary-study pattern",
        }

    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cleanup-json",
        type=Path,
        default=CLEANUP_JSON,
        help="Cleanup candidate JSON generated by build_cleanup_report.py",
    )
    parser.add_argument("--apply", action="store_true", help="Write changes to curated disorder claims")
    parser.add_argument(
        "--report-json",
        type=Path,
        default=ROOT / "data" / "processed" / "manual_review_resolution_report.json",
        help="Where to write the resolution report when --apply is used",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    curated = load_json_array(CURATED_JSON)
    papers = load_json_array(PAPER_DB_JSON)
    cleanup = json.loads(args.cleanup_json.read_text())
    manual_rows = [
        row
        for row in cleanup["datasets"]["disorder"]["manual_review"]
    ]
    selected = select_target_rows(curated, manual_rows)
    paper_by_doi = {
        normalize_doi(row.get("study_doi", "")).lower(): row
        for row in papers
        if normalize_doi(row.get("study_doi", ""))
    }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cleanup_json": str(args.cleanup_json),
        "target_count": len(selected),
        "resolved_count": 0,
        "unresolved_count": 0,
        "by_decision": {},
        "resolved_rows": [],
        "unresolved_rows": [],
    }
    decision_counter: Counter[str] = Counter()

    for row_idx, candidate in selected:
        row = curated[row_idx]
        doi = normalize_doi(row.get("study_doi", "")).lower()
        abstract = normalize(paper_by_doi.get(doi, {}).get("abstract", ""))
        decision = classify_row(normalize(row.get("study_title", "")), abstract)

        if not decision:
            report["unresolved_rows"].append(
                {
                    "row_index": row_idx + 1,
                    "study_title": normalize(row.get("study_title", "")),
                    "study_doi": normalize(row.get("study_doi", "")),
                }
            )
            continue

        before = {
            "paper_type": normalize(row.get("paper_type", "")),
            "source_type": normalize(row.get("source_type", "")),
            "evidence_level": normalize(row.get("evidence_level", "")),
        }
        row["paper_type"] = decision["paper_type"]
        row["source_type"] = decision["source_type"]
        row["evidence_level"] = decision["evidence_level"]
        row["notes"] = append_note(
            row.get("notes", ""),
            f"Manual-review title resolver: {decision['reason']}",
        )
        after = {
            "paper_type": normalize(row.get("paper_type", "")),
            "source_type": normalize(row.get("source_type", "")),
            "evidence_level": normalize(row.get("evidence_level", "")),
        }
        decision_key = f"{after['paper_type']}|{after['source_type']}|{after['evidence_level']}"
        decision_counter[decision_key] += 1
        report["resolved_rows"].append(
            {
                "row_index": row_idx + 1,
                "study_title": normalize(row.get("study_title", "")),
                "study_doi": normalize(row.get("study_doi", "")),
                "before": before,
                "after": after,
                "reason": decision["reason"],
            }
        )

    report["resolved_count"] = len(report["resolved_rows"])
    report["unresolved_count"] = len(report["unresolved_rows"])
    report["by_decision"] = dict(decision_counter)

    print(
        f"target_count={report['target_count']} "
        f"resolved={report['resolved_count']} "
        f"unresolved={report['unresolved_count']}"
    )
    print(f"decisions={dict(decision_counter)}")

    if args.apply:
        fieldnames = list(curated[0].keys()) if curated else []
        write_json(CURATED_JSON, curated)
        write_csv(CURATED_CSV, curated, fieldnames)
        args.report_json.write_text(json.dumps(report, indent=2) + "\n")
        print(f"wrote {args.report_json}")


if __name__ == "__main__":
    main()
