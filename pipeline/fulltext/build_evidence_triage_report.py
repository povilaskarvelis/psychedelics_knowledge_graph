#!/usr/bin/env python3
"""Build automated evidence-type triage proposals from full-text artifacts.

This stage separates source/evidence-type QA from locator repair. A row can have
`access_level=full_text_seen` and still be the wrong kind of evidence for a
primary-study claim, e.g. a review, protocol, commentary, erratum, or conference
abstract. The report is deterministic and non-destructive; use
apply_evidence_triage.py to apply high-confidence proposals.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Iterable, List

try:
    from pipeline.fulltext.build_provenance_repair_report import DATASET_CONFIG, artifact_path_for_doi, best_extraction
    from pipeline.fulltext.convert_pdfs import compact_text, normalize, normalize_doi
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.build_provenance_repair_report import DATASET_CONFIG, artifact_path_for_doi, best_extraction
    from pipeline.fulltext.convert_pdfs import compact_text, normalize, normalize_doi

ROOT = Path(__file__).resolve().parents[2]

TRIAGE_CONFIG = {
    dataset: {
        **cfg,
        "report_json": ROOT / "data" / "processed" / "fulltext" / f"evidence_triage_report_{dataset}.json",
        "report_csv": ROOT / "data" / "processed" / "fulltext" / f"evidence_triage_report_{dataset}.csv",
    }
    for dataset, cfg in DATASET_CONFIG.items()
}

TARGET_FIELDS = {
    "systematic_review": {
        "source_type": "secondary_evidence",
        "paper_type": "systematic_review",
        "study_design": "systematic_review",
    },
    "meta_analysis": {
        "source_type": "secondary_evidence",
        "paper_type": "meta_analysis",
        "study_design": "meta_analysis",
    },
    "review": {
        "source_type": "secondary_evidence",
        "paper_type": "review",
        "study_design": "review",
    },
    "commentary": {
        "source_type": "commentary",
        "paper_type": "commentary",
        "study_design": "commentary",
    },
    "protocol": {
        "source_type": "study_protocol",
        "paper_type": "protocol",
        "study_design": "protocol",
    },
    "correction": {
        "source_type": "correction",
        "paper_type": "erratum",
        "study_design": "correction",
    },
    "conference_abstract": {
        "source_type": "conference_abstract",
        "paper_type": "conference_abstract",
        "study_design": "conference_abstract",
    },
    "case_report": {
        "source_type": "case_report",
        "paper_type": "case_report",
        "study_design": "case_report",
    },
    "primary_study": {
        "source_type": "primary_study",
        "paper_type": "primary_results",
    },
}

SECONDARY_CLASSES = set(TARGET_FIELDS) - {"primary_study"}

CORRECTION_RE = re.compile(r"\b(erratum|corrigendum|correction|retraction|withdrawn)\b")
PROTOCOL_RE = re.compile(r"\b(study protocol|trial protocol|protocol for|rationale and design|design and rationale)\b")
COMMENTARY_RE = re.compile(
    r"\b(commentary|editorial|letter to the editor|viewpoint|perspective|reply|response to|validity threats)\b"
)
META_RE = re.compile(r"\b(meta-analysis|meta analysis|metaanalysis|pooled analysis)\b")
SYSTEMATIC_RE = re.compile(r"\b(systematic review|scoping review|umbrella review)\b")
REVIEW_RE = re.compile(r"\b(review|overview|historical overview|state of the art|current perspectives)\b")
REVIEW_METHOD_RE = re.compile(
    r"\b("
    r"searched (pubmed|medline|embase|psycinfo|web of science|scopus|databases)|"
    r"literature search|database search|included studies|study selection|selection criteria|"
    r"data extraction|risk of bias|quality assessment|prisma (reporting|guideline|statement|flow)"
    r")\b"
)
CONFERENCE_RE = re.compile(
    r"\b(conference abstract|poster|conference proceedings|annual meeting|scientific meeting|symposium abstract)\b"
)
CASE_REPORT_RE = re.compile(r"\b(case report|case series|case study)\b")
PRIMARY_CLINICAL_RE = re.compile(
    r"\b("
    r"randomi[sz]ed|double blind|single blind|placebo controlled|phase [123]|clinical trial|"
    r"open label|cohort|observational|participants|patients were|we enrolled"
    r")\b"
)
PRIMARY_MECHANISTIC_RE = re.compile(
    r"\b("
    r"binding assay|radioligand|competition binding|functional assay|in vitro|ex vivo|"
    r"cell line|transporter uptake|ec50|ic50|ki|kd|receptor occupancy|we examined|we investigated"
    r")\b"
)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize_text(value: object) -> str:
    lowered = re.sub(r"<[^>]+>", " ", normalize(value).lower())
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def load_json_array(path: Path) -> List[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return [row for row in data if isinstance(row, dict)]


def load_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "row_index",
        "study_doi",
        "compound",
        "entity",
        "study_title",
        "action",
        "automation_status",
        "classification",
        "confidence",
        "current_source_type",
        "target_source_type",
        "current_paper_type",
        "target_paper_type",
        "current_study_design",
        "target_study_design",
        "signals",
        "artifact_path",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def element_text(element: ET.Element) -> str:
    return compact_text(" ".join(text for text in element.itertext() if normalize(text)))


def text_from_tei(tei_xml: str, max_chars: int = 60000) -> str:
    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError:
        return ""

    chunks: List[str] = []
    for parent in root.iter():
        parent_name = local_name(parent.tag)
        if parent_name not in {"front", "body"}:
            continue
        for element in parent.iter():
            name = local_name(element.tag)
            if name not in {"abstract", "head", "p"}:
                continue
            text = element_text(element)
            if text:
                chunks.append(text)
            if sum(len(chunk) for chunk in chunks) >= max_chars:
                break
    return compact_text(" ".join(chunks))[:max_chars]


def evidence_text(row: dict, extraction: dict) -> str:
    pieces = [normalize(row.get("study_title", ""))]
    sections = extraction.get("sections", [])
    if isinstance(sections, list):
        for section in sections[:18]:
            if not isinstance(section, dict):
                continue
            pieces.append(normalize(section.get("heading", "")))
            pieces.append(normalize(section.get("snippet", "")))
    raw_text = normalize(extraction.get("text", ""))
    if raw_text:
        pieces.append(text_from_tei(raw_text) if raw_text.lstrip().startswith("<") else raw_text[:60000])
    return normalize_text(" ".join(piece for piece in pieces if piece))


def add_signal(signals: list[tuple[str, str, float]], key: str, reason: str, weight: float) -> None:
    signals.append((key, reason, weight))


def classify_evidence(row: dict, extraction: dict) -> dict:
    title = normalize_text(row.get("study_title", ""))
    text = evidence_text(row, extraction)
    signals: list[tuple[str, str, float]] = []

    def title_or_text(pattern: re.Pattern[str], label: str, title_weight: float, text_weight: float) -> None:
        if pattern.search(title):
            add_signal(signals, label, f"title matches {label}", title_weight)
        if pattern.search(text):
            add_signal(signals, label, f"full text matches {label}", text_weight)

    title_or_text(CORRECTION_RE, "correction", 1.0, 0.8)
    title_or_text(PROTOCOL_RE, "protocol", 0.95, 0.75)
    title_or_text(COMMENTARY_RE, "commentary", 0.9, 0.65)
    title_or_text(META_RE, "meta_analysis", 0.95, 0.7)
    title_or_text(SYSTEMATIC_RE, "systematic_review", 0.95, 0.75)
    title_or_text(REVIEW_RE, "review", 0.75, 0.45)
    title_or_text(CONFERENCE_RE, "conference_abstract", 0.8, 0.55)
    title_or_text(CASE_REPORT_RE, "case_report", 0.8, 0.55)

    if REVIEW_METHOD_RE.search(text):
        add_signal(signals, "systematic_review", "review-methods language in full text", 0.8)
    if PRIMARY_CLINICAL_RE.search(text):
        add_signal(signals, "primary_study", "clinical primary-study language in full text", 0.5)
    if PRIMARY_MECHANISTIC_RE.search(text):
        add_signal(signals, "primary_study", "mechanistic primary-study language in full text", 0.5)

    by_class: dict[str, float] = {}
    reasons_by_class: dict[str, list[str]] = {}
    for key, reason, weight in signals:
        by_class[key] = by_class.get(key, 0.0) + weight
        reasons_by_class.setdefault(key, []).append(reason)

    priority = [
        "correction",
        "protocol",
        "meta_analysis",
        "systematic_review",
        "commentary",
        "conference_abstract",
        "case_report",
        "review",
        "primary_study",
    ]
    best_class = "primary_study"
    best_score = by_class.get("primary_study", 0.35)
    for key in priority:
        score = by_class.get(key, 0.0)
        if score > best_score or (score == best_score and key in SECONDARY_CLASSES and best_class == "primary_study"):
            best_class = key
            best_score = score

    if best_class in SECONDARY_CLASSES:
        primary_score = by_class.get("primary_study", 0.0)
        confidence = min(0.99, 0.55 + (best_score * 0.25) - min(primary_score, 1.0) * 0.08)
    else:
        confidence = min(0.9, 0.65 + best_score * 0.25)

    return {
        "classification": best_class,
        "confidence": round(max(0.0, confidence), 3),
        "signals": reasons_by_class.get(best_class, []) or ["no stronger non-primary evidence-type signal"],
        "all_signal_scores": {key: round(value, 3) for key, value in sorted(by_class.items())},
    }


def target_fields_for_classification(classification: str) -> dict:
    return TARGET_FIELDS.get(classification, TARGET_FIELDS["primary_study"])


def build_row(dataset: str, row: dict, row_index: int, artifact_dir: Path, auto_confidence: float) -> dict:
    cfg = TRIAGE_CONFIG[dataset]
    entity_key = cfg["entity_key"]
    doi = normalize_doi(row.get("study_doi", ""))
    artifact_path = artifact_path_for_doi(artifact_dir, doi) if doi else Path("")
    base = {
        "row_index": row_index,
        "study_doi": doi,
        "compound": normalize(row.get("compound", "")),
        "entity": normalize(row.get(entity_key, "")),
        "study_title": normalize(row.get("study_title", "")),
        "current_source_type": normalize(row.get("source_type", "")),
        "current_paper_type": normalize(row.get("paper_type", "")),
        "current_study_design": normalize(row.get("study_design", "")),
        "artifact_path": str(artifact_path) if artifact_path else "",
    }
    if not doi:
        return {**base, "action": "needs_targeted_qa", "automation_status": "not_eligible", "reason": "missing DOI"}
    if not artifact_path.exists():
        return {
            **base,
            "action": "needs_fulltext_artifact",
            "automation_status": "not_eligible",
            "reason": "missing full-text artifact",
        }

    artifact = load_json_object(artifact_path)
    extraction = best_extraction(artifact)
    if not extraction:
        return {
            **base,
            "action": "needs_fulltext_artifact",
            "automation_status": "not_eligible",
            "reason": "artifact exists but has no successful extraction",
        }

    classification = classify_evidence(row, extraction)
    target = target_fields_for_classification(classification["classification"])
    current_source_type = base["current_source_type"]
    current_paper_type = base["current_paper_type"]
    current_study_design = base["current_study_design"]
    target_source_type = target.get("source_type", current_source_type)
    target_paper_type = target.get("paper_type", current_paper_type)
    target_study_design = target.get("study_design", current_study_design)

    needs_change = (
        current_source_type != target_source_type
        or current_paper_type != target_paper_type
        or (target_study_design and current_study_design != target_study_design)
    )
    is_non_primary = classification["classification"] in SECONDARY_CLASSES
    confidence = float(classification["confidence"])

    if is_non_primary and needs_change:
        action = "propose_source_reclassification"
        automation_status = "auto_apply_eligible" if confidence >= auto_confidence else "needs_targeted_qa"
    elif is_non_primary:
        action = "keep_non_primary"
        automation_status = "already_classified"
    else:
        action = "keep_primary"
        automation_status = "no_change"

    return {
        **base,
        "action": action,
        "automation_status": automation_status,
        "classification": classification["classification"],
        "confidence": confidence,
        "target_source_type": target_source_type,
        "target_paper_type": target_paper_type,
        "target_study_design": target_study_design,
        "signals": " | ".join(classification["signals"]),
        "signal_scores": classification["all_signal_scores"],
        "best_backend": normalize(artifact.get("best_backend", "")),
    }


def row_in_scope(row: dict, artifact_dir: Path, scope: str) -> bool:
    doi = normalize_doi(row.get("study_doi", ""))
    if not doi:
        return False
    if scope == "all":
        return True
    artifact_exists = artifact_path_for_doi(artifact_dir, doi).exists()
    if scope == "artifacts":
        return artifact_exists
    return normalize(row.get("access_level", "")) == "full_text_seen"


def build_report(
    dataset: str,
    curated_rows: List[dict],
    artifact_dir: Path,
    auto_confidence: float,
    limit: int = 0,
    scope: str = "full_text_seen",
) -> dict:
    rows_with_doi = [
        (idx, row)
        for idx, row in enumerate(curated_rows, start=1)
        if row_in_scope(row, artifact_dir=artifact_dir, scope=scope)
    ]
    if limit > 0:
        rows_with_doi = rows_with_doi[:limit]

    rows = [
        build_row(dataset, row, idx, artifact_dir=artifact_dir, auto_confidence=auto_confidence)
        for idx, row in rows_with_doi
    ]
    action_counts = Counter(row.get("action", "") for row in rows)
    automation_counts = Counter(row.get("automation_status", "") for row in rows)
    classification_counts = Counter(row.get("classification", "") for row in rows)
    counts = {
        "curated_rows": len(curated_rows),
        "rows_considered": len(rows),
        "auto_apply_eligible": automation_counts.get("auto_apply_eligible", 0),
        "needs_targeted_qa": automation_counts.get("needs_targeted_qa", 0),
        "needs_fulltext_artifact": action_counts.get("needs_fulltext_artifact", 0),
        "propose_source_reclassification": action_counts.get("propose_source_reclassification", 0),
        "keep_primary": action_counts.get("keep_primary", 0),
        "keep_non_primary": action_counts.get("keep_non_primary", 0),
    }
    return {
        "generated_at_utc": now_utc(),
        "dataset": dataset,
        "artifact_dir": str(artifact_dir),
        "auto_confidence": auto_confidence,
        "scope": scope,
        "limit": limit,
        "counts": counts,
        "action_counts": dict(action_counts),
        "automation_counts": dict(automation_counts),
        "classification_counts": dict(classification_counts),
        "rows": rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=sorted(TRIAGE_CONFIG), required=True)
    parser.add_argument("--curated-json", default="", help="Override curated claims JSON")
    parser.add_argument("--artifact-dir", default="", help="Override full-text artifact directory")
    parser.add_argument("--out-json", default="", help="Override JSON report path")
    parser.add_argument("--out-csv", default="", help="Override CSV report path")
    parser.add_argument("--auto-confidence", type=float, default=0.85)
    parser.add_argument(
        "--scope",
        choices=["full_text_seen", "artifacts", "all"],
        default="full_text_seen",
        help="Rows to triage; default focuses on rows whose full text was seen",
    )
    parser.add_argument("--limit", type=int, default=0, help="Maximum rows to consider; 0 means all")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = TRIAGE_CONFIG[args.dataset]
    curated_json = Path(args.curated_json).resolve() if args.curated_json else cfg["curated_json"]
    artifact_dir = Path(args.artifact_dir).resolve() if args.artifact_dir else cfg["artifact_dir"]
    out_json = Path(args.out_json).resolve() if args.out_json else cfg["report_json"]
    out_csv = Path(args.out_csv).resolve() if args.out_csv else cfg["report_csv"]

    report = build_report(
        dataset=args.dataset,
        curated_rows=load_json_array(curated_json),
        artifact_dir=artifact_dir,
        auto_confidence=max(0.0, min(1.0, args.auto_confidence)),
        limit=max(0, args.limit),
        scope=args.scope,
    )
    report["inputs"] = {
        "curated_json": str(curated_json),
        "artifact_dir": str(artifact_dir),
        "out_json": str(out_json),
        "out_csv": str(out_csv),
    }
    write_json(out_json, report)
    write_csv(out_csv, report["rows"])

    counts = report["counts"]
    print(f"Dataset: {args.dataset}")
    print(f"Rows considered: {counts['rows_considered']}")
    print(f"Proposed source reclassifications: {counts['propose_source_reclassification']}")
    print(f"Auto-apply eligible: {counts['auto_apply_eligible']}")
    print(f"Needs targeted QA: {counts['needs_targeted_qa']}")
    print(f"Report: {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
