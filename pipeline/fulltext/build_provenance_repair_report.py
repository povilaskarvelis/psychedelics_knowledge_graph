#!/usr/bin/env python3
"""Build review candidates for stale full-text evidence locators.

This report uses full-text artifacts from convert_pdfs.py to suggest stronger
section-level locators, but it does not edit curated rows.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

try:
    from pipeline.fulltext.convert_pdfs import doi_to_slug, normalize, normalize_doi
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.convert_pdfs import doi_to_slug, normalize, normalize_doi

ROOT = Path(__file__).resolve().parents[2]

DATASET_CONFIG = {
    "mechanistic": {
        "curated_json": ROOT / "data" / "curated" / "claims.json",
        "artifact_dir": ROOT / "data" / "processed" / "fulltext" / "mechanistic",
        "report_json": ROOT / "data" / "processed" / "fulltext" / "provenance_repair_report_mechanistic.json",
        "report_csv": ROOT / "data" / "processed" / "fulltext" / "provenance_repair_report_mechanistic.csv",
        "entity_key": "target",
    },
    "disorder": {
        "curated_json": ROOT / "data" / "curated" / "disorder_claims.json",
        "artifact_dir": ROOT / "data" / "processed" / "fulltext" / "disorder",
        "report_json": ROOT / "data" / "processed" / "fulltext" / "provenance_repair_report_disorder.json",
        "report_csv": ROOT / "data" / "processed" / "fulltext" / "provenance_repair_report_disorder.csv",
        "entity_key": "disorder",
    },
}

LOW_VALUE_HEADINGS = {
    "abstract",
    "access",
    "abbreviations",
    "abbreviations used",
    "references",
    "keywords",
    "article information",
    "supplemental content",
    "supplementary material",
    "acknowledgments",
    "author contributions",
    "conflict of interest disclosures",
    "funding support",
    "data availability",
    "introduction",
}
INTERPRETIVE_ONLY_HEADINGS = {
    "discussion",
    "conclusion",
    "conclusions",
    "conclusions and outlook",
    "significance",
}

HIGH_VALUE_HEADING_TERMS = {
    "results": 5,
    "findings": 5,
    "outcomes": 4,
    "keypoints": 4,
    "key points": 4,
    "discussion": 2,
    "abstract": 2,
    "methods": 1,
}
EVIDENCE_HEADING_TERMS = {
    "results",
    "findings",
    "outcome",
    "outcomes",
    "table",
    "figure",
    "efficacy",
    "safety",
    "adverse event",
    "adverse events",
    "response",
    "remission",
}
MECHANISTIC_EVIDENCE_TERMS = {
    "binding",
    "affinity",
    "radioligand",
    "competition",
    "inhibition",
    "functional",
    "activity",
    "agonist",
    "antagonist",
    "ec50",
    "ic50",
    "ki",
    "kd",
    "occupancy",
    "receptor",
    "transporter",
    "uptake",
    "membrane response",
    "membrane responses",
}
TITLE_REVIEW_SIGNAL_RE = re.compile(
    r"\b(systematic review|a ?meta analysis|meta analysis|scoping review|umbrella review|pooled analysis|"
    r"validity threats|commentary|editorial|letter|viewpoint|perspective)\b"
)
SELF_DESCRIBED_REVIEW_RE = re.compile(
    r"\b(this|the|our|in this) (systematic review|a ?meta analysis|meta analysis|scoping review|"
    r"umbrella review|pooled analysis|review)\b"
    r"|\bwe (conducted|performed|undertook|searched) (a )?"
    r"(systematic review|a ?meta analysis|meta analysis|scoping review|umbrella review|pooled analysis)\b"
    r"|\bprisma\b"
)
NON_PRIMARY_SOURCE_TYPES = {
    "secondary_evidence",
    "commentary",
    "study_protocol",
    "correction",
    "conference_abstract",
    "case_report",
}
NON_PRIMARY_PAPER_TYPES = {
    "systematic_review",
    "meta_analysis",
    "review",
    "commentary",
    "protocol",
    "erratum",
    "conference_abstract",
    "case_report",
}


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
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "row_index",
        "study_doi",
        "compound",
        "entity",
        "study_title",
        "action",
        "score",
        "proposed_evidence_location",
        "proposed_evidence_locator",
        "artifact_path",
        "reason",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def is_stale_fulltext_locator(row: dict) -> bool:
    return normalize(row.get("access_level", "")) == "full_text_seen" and normalize(
        row.get("evidence_locator", "")
    ).lower().startswith("abstract snippet:")


def is_non_primary_triaged(row: dict) -> bool:
    source_type = normalize(row.get("source_type", "")).lower()
    paper_type = normalize(row.get("paper_type", "")).lower()
    study_design = normalize(row.get("study_design", "")).lower()
    return (
        source_type in NON_PRIMARY_SOURCE_TYPES
        or paper_type in NON_PRIMARY_PAPER_TYPES
        or study_design in NON_PRIMARY_PAPER_TYPES
    )


def best_extraction(artifact: dict) -> dict:
    backend = normalize(artifact.get("best_backend", ""))
    for extraction in artifact.get("extractions", []):
        if isinstance(extraction, dict) and normalize(extraction.get("backend", "")) == backend:
            return extraction
    for extraction in artifact.get("extractions", []):
        if isinstance(extraction, dict) and normalize(extraction.get("status", "")) == "ok":
            return extraction
    return {}


def artifact_path_for_doi(artifact_dir: Path, doi: str) -> Path:
    return artifact_dir / f"{doi_to_slug(doi)}.json"


def candidate_terms(dataset: str, row: dict, entity_key: str) -> Dict[str, int]:
    terms: Dict[str, int] = {}

    def add(raw: object, weight: int) -> None:
        text = normalize_text(raw)
        if len(text) < 3:
            return
        terms[text] = max(terms.get(text, 0), weight)

    add(row.get("compound", ""), 4)
    add(row.get(entity_key, ""), 4)
    add(row.get("outcome_measure", ""), 4)
    add(row.get("outcome_type", ""), 3)
    add(row.get("assay_type", ""), 3)
    add(row.get("affinity_type", ""), 2)

    if dataset == "disorder":
        disorder = normalize_text(row.get("disorder", ""))
        if "depression" in disorder or "depressive" in disorder:
            add("depression", 2)
            add("depressive symptoms", 2)
        if "post traumatic stress disorder" in disorder or "ptsd" in disorder:
            add("ptsd", 2)
        if "alcohol use disorder" in disorder:
            add("alcohol", 2)
            add("drinking", 2)
        if "anxiety" in disorder:
            add("anxiety", 2)
    else:
        add("binding", 2)
        add("affinity", 2)
        add("ki", 2)
        add("ic50", 2)
        add("ec50", 2)

    return terms


def infer_evidence_location(heading: str) -> str:
    text = normalize_text(heading)
    if "table" in text:
        return "table"
    if "figure" in text:
        return "figure"
    if text == "abstract" or text.startswith("abstract "):
        return "abstract"
    if "supplement" in text:
        return "supplement"
    return "text"


def score_section(section: dict, terms: Dict[str, int]) -> Tuple[int, List[str]]:
    heading = normalize(section.get("heading", ""))
    heading_norm = normalize_text(heading)
    snippet_norm = normalize_text(section.get("snippet", ""))
    haystack = f"{heading_norm} {snippet_norm}".strip()
    score = 0
    reasons: List[str] = []

    if heading_norm in LOW_VALUE_HEADINGS:
        score -= 5
        reasons.append(f"low-value heading `{heading}`")

    for term, weight in HIGH_VALUE_HEADING_TERMS.items():
        if term in heading_norm:
            score += weight
            reasons.append(f"heading contains `{term}`")
            break

    for term, weight in terms.items():
        if term and term in haystack:
            score += weight
            reasons.append(f"matched `{term}`")

    return score, reasons


def evidence_section_status(dataset: str, section: dict, study_title: object = "") -> Tuple[bool, List[str]]:
    """Return whether a section is strong enough for automatic locator repair."""
    heading = normalize(section.get("heading", ""))
    heading_norm = normalize_text(heading)
    title_norm = normalize_text(study_title)
    snippet_norm = normalize_text(section.get("snippet", ""))
    haystack = f"{heading_norm} {snippet_norm}".strip()
    reasons: List[str] = []

    if infer_evidence_location(heading) == "abstract":
        return False, ["abstract section cannot repair a stale abstract locator"]
    if title_norm and len(heading_norm) > 25 and (heading_norm.startswith(title_norm) or title_norm.startswith(heading_norm)):
        return False, [f"heading `{heading}` appears to be the article title, not an evidence section"]
    if heading_norm in LOW_VALUE_HEADINGS:
        return False, [f"heading `{heading}` is not an evidence section"]
    if any(term in heading_norm for term in LOW_VALUE_HEADINGS):
        return False, [f"heading `{heading}` looks like article metadata or boilerplate"]
    if heading_norm in INTERPRETIVE_ONLY_HEADINGS:
        return False, [f"heading `{heading}` is interpretive rather than primary evidence"]

    if any(term in heading_norm for term in EVIDENCE_HEADING_TERMS):
        reasons.append("heading is evidence-bearing")
    if dataset == "mechanistic" and any(term in heading_norm for term in MECHANISTIC_EVIDENCE_TERMS):
        reasons.append("mechanistic assay context present")

    if reasons:
        return True, reasons
    return False, [f"heading `{heading}` is not specific enough for automatic repair"]


def has_review_signal(row: dict, extraction: dict) -> bool:
    title = normalize_text(row.get("study_title", ""))
    if TITLE_REVIEW_SIGNAL_RE.search(title):
        return True

    for section in extraction.get("sections", [])[:8]:
        if not isinstance(section, dict):
            continue
        heading_norm = normalize_text(section.get("heading", ""))
        snippet_norm = normalize_text(section.get("snippet", ""))
        if TITLE_REVIEW_SIGNAL_RE.search(heading_norm):
            return True
        is_self_description_area = (
            heading_norm == "abstract"
            or heading_norm.startswith("abstract ")
            or heading_norm == "keypoints"
            or "method" in heading_norm
            or "data acquisition" in heading_norm
            or "data extraction" in heading_norm
            or "statistical analysis" in heading_norm
            or "search strategy" in heading_norm
            or "selection criteria" in heading_norm
        )
        if is_self_description_area and SELF_DESCRIBED_REVIEW_RE.search(snippet_norm):
            return True
    return False


def relation_context_matched(dataset: str, row: dict, section: dict, entity_key: str) -> Tuple[bool, List[str]]:
    haystack = normalize_text(f"{section.get('heading', '')} {section.get('snippet', '')}")
    compound = normalize_text(row.get("compound", ""))
    entity = normalize_text(row.get(entity_key, ""))
    reasons: List[str] = []

    compound_matched = bool(compound and compound in haystack)
    if not compound_matched and compound == "s ketamine" and "esketamine" in haystack:
        compound_matched = True
    if not compound_matched and compound == "r ketamine" and "arketamine" in haystack:
        compound_matched = True
    if not compound_matched and "ketamine" in compound and "ketamine" in haystack:
        compound_matched = True
    if compound_matched:
        reasons.append("compound context matched")

    entity_matched = bool(entity and entity in haystack)
    if dataset == "disorder" and not entity_matched:
        if "depression" in entity or "depressive" in entity:
            entity_matched = "depression" in haystack or "depressive" in haystack
        elif "post traumatic stress disorder" in entity or "ptsd" in entity:
            entity_matched = "ptsd" in haystack or "post traumatic stress" in haystack
        elif "alcohol use disorder" in entity:
            entity_matched = "alcohol" in haystack or "drinking" in haystack
        elif "anxiety" in entity:
            entity_matched = "anxiety" in haystack
    if entity_matched:
        reasons.append("relation context matched")

    return compound_matched and entity_matched, reasons


RankedSection = Tuple[dict, int, List[str], bool, List[str], bool, List[str]]


def ranked_sections(dataset: str, row: dict, extraction: dict, entity_key: str) -> List[RankedSection]:
    sections = [section for section in extraction.get("sections", []) if isinstance(section, dict)]
    terms = candidate_terms(dataset, row, entity_key)
    ranked: List[RankedSection] = []
    for section in sections:
        score, score_reasons = score_section(section, terms)
        evidence_ok, evidence_reasons = evidence_section_status(dataset, section, study_title=row.get("study_title", ""))
        relation_matched, relation_reasons = relation_context_matched(dataset, row, section, entity_key)
        ranked.append((section, score, score_reasons, evidence_ok, evidence_reasons, relation_matched, relation_reasons))
    ranked.sort(key=lambda item: (item[3] and item[5], item[1]), reverse=True)
    return ranked


def choose_section(dataset: str, row: dict, extraction: dict, entity_key: str) -> RankedSection:
    ranked = ranked_sections(dataset, row, extraction, entity_key)
    if not ranked:
        return {}, -999, [], False, [], False, []
    return ranked[0]


def combined_candidate_reasons(
    score_reasons: List[str],
    evidence_ok: bool,
    evidence_reasons: List[str],
    relation_matched: bool,
    relation_reasons: List[str],
    score: int,
    min_score: int,
) -> List[str]:
    reasons: List[str] = []
    if not evidence_ok:
        reasons.append("proposed section is not strong enough full-text evidence")
    reasons.extend(evidence_reasons)
    if not relation_matched:
        reasons.append("missing compound or relation context in proposed section")
    else:
        reasons.extend(relation_reasons)
    if score < min_score:
        reasons.append(f"score below threshold {min_score}")
    reasons.extend(score_reasons)
    return reasons


def proposed_locator(section: dict) -> str:
    heading = normalize(section.get("heading", "")) or "Full text"
    snippet = normalize(section.get("snippet", ""))
    snippet = re.sub(r"\s+", " ", snippet).strip()
    if len(snippet) > 220:
        snippet = snippet[:217].rstrip() + "..."
    if snippet:
        return f"Full text section `{heading}` snippet: {snippet}"
    return f"Full text section `{heading}`"


def build_candidate(
    dataset: str,
    row: dict,
    row_index: int,
    artifact_dir: Path,
    min_score: int,
    entity_key: str,
) -> dict:
    doi = normalize_doi(row.get("study_doi", ""))
    artifact_path = artifact_path_for_doi(artifact_dir, doi) if doi else Path("")
    base = {
        "row_index": row_index,
        "study_doi": doi,
        "compound": normalize(row.get("compound", "")),
        "entity": normalize(row.get(entity_key, "")),
        "study_title": normalize(row.get("study_title", "")),
        "current_evidence_location": normalize(row.get("evidence_location", "")),
        "current_evidence_locator": normalize(row.get("evidence_locator", "")),
        "artifact_path": str(artifact_path) if artifact_path else "",
    }

    if not doi:
        return {**base, "action": "needs_manual_review", "score": 0, "reason": "missing DOI"}
    if is_non_primary_triaged(row):
        return {
            **base,
            "action": "already_non_primary_triaged",
            "score": 0,
            "reason": (
                "source already triaged as non-primary evidence "
                f"({normalize(row.get('source_type', '')) or normalize(row.get('paper_type', ''))})"
            ),
        }
    if not artifact_path.exists():
        return {**base, "action": "needs_fulltext_artifact", "score": 0, "reason": "missing full-text artifact"}

    artifact = load_json_object(artifact_path)
    extraction = best_extraction(artifact)
    if not extraction:
        return {
            **base,
            "action": "needs_fulltext_artifact",
            "score": 0,
            "reason": "artifact exists but has no successful extraction",
            "best_backend": normalize(artifact.get("best_backend", "")),
        }
    if has_review_signal(row, extraction):
        return {
            **base,
            "action": "needs_demotion_review",
            "score": 0,
            "reason": "full-text/title signals secondary evidence or commentary",
            "best_backend": normalize(artifact.get("best_backend", "")),
        }

    section, score, score_reasons, evidence_ok, evidence_reasons, relation_matched, relation_reasons = choose_section(
        dataset, row, extraction, entity_key
    )
    if not section:
        return {**base, "action": "needs_manual_review", "score": 0, "reason": "no sections in artifact"}

    action = (
        "propose_locator_repair"
        if score >= min_score and relation_matched and evidence_ok
        else "needs_manual_review"
    )
    reasons = combined_candidate_reasons(
        score_reasons=score_reasons,
        evidence_ok=evidence_ok,
        evidence_reasons=evidence_reasons,
        relation_matched=relation_matched,
        relation_reasons=relation_reasons,
        score=score,
        min_score=min_score,
    )
    return {
        **base,
        "action": action,
        "score": score,
        "reason": " | ".join(reasons),
        "best_backend": normalize(artifact.get("best_backend", "")),
        "proposed_evidence_location": infer_evidence_location(normalize(section.get("heading", ""))),
        "proposed_evidence_locator": proposed_locator(section),
        "section_heading": normalize(section.get("heading", "")),
        "section_char_count": section.get("char_count", 0),
    }


def build_report(dataset: str, curated_rows: List[dict], artifact_dir: Path, min_score: int, limit: int = 0) -> dict:
    cfg = DATASET_CONFIG[dataset]
    entity_key = cfg["entity_key"]
    stale_rows = [(idx, row) for idx, row in enumerate(curated_rows, start=1) if is_stale_fulltext_locator(row)]
    if limit > 0:
        stale_rows = stale_rows[:limit]

    candidates = [
        build_candidate(dataset, row, idx, artifact_dir=artifact_dir, min_score=min_score, entity_key=entity_key)
        for idx, row in stale_rows
    ]
    counts = {
        "curated_rows": len(curated_rows),
        "stale_fulltext_locator_rows": sum(1 for row in curated_rows if is_stale_fulltext_locator(row)),
        "rows_considered": len(stale_rows),
        "propose_locator_repair": sum(1 for row in candidates if row.get("action") == "propose_locator_repair"),
        "needs_fulltext_artifact": sum(1 for row in candidates if row.get("action") == "needs_fulltext_artifact"),
        "needs_demotion_review": sum(1 for row in candidates if row.get("action") == "needs_demotion_review"),
        "already_non_primary_triaged": sum(
            1 for row in candidates if row.get("action") == "already_non_primary_triaged"
        ),
        "needs_manual_review": sum(1 for row in candidates if row.get("action") == "needs_manual_review"),
    }
    return {
        "generated_at_utc": now_utc(),
        "dataset": dataset,
        "artifact_dir": str(artifact_dir),
        "min_score": min_score,
        "limit": limit,
        "counts": counts,
        "rows": candidates,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=sorted(DATASET_CONFIG), required=True)
    parser.add_argument("--curated-json", default="", help="Override curated claims JSON")
    parser.add_argument("--artifact-dir", default="", help="Override full-text artifact directory")
    parser.add_argument("--out-json", default="", help="Override JSON report path")
    parser.add_argument("--out-csv", default="", help="Override CSV report path")
    parser.add_argument("--min-score", type=int, default=7)
    parser.add_argument("--limit", type=int, default=0, help="Maximum stale rows to consider; 0 means all")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = DATASET_CONFIG[args.dataset]
    curated_json = Path(args.curated_json).resolve() if args.curated_json else cfg["curated_json"]
    artifact_dir = Path(args.artifact_dir).resolve() if args.artifact_dir else cfg["artifact_dir"]
    out_json = Path(args.out_json).resolve() if args.out_json else cfg["report_json"]
    out_csv = Path(args.out_csv).resolve() if args.out_csv else cfg["report_csv"]

    report = build_report(
        dataset=args.dataset,
        curated_rows=load_json_array(curated_json),
        artifact_dir=artifact_dir,
        min_score=max(0, args.min_score),
        limit=max(0, args.limit),
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
    print(f"Proposed locator repairs: {counts['propose_locator_repair']}")
    print(f"Need full-text artifact: {counts['needs_fulltext_artifact']}")
    print(f"Need demotion review: {counts['needs_demotion_review']}")
    print(f"Already non-primary triaged: {counts['already_non_primary_triaged']}")
    print(f"Report: {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
