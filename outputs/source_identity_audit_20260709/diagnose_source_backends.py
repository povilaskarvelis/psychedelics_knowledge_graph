#!/usr/bin/env python3
"""Quantify source-identity candidates by acquisition/conversion backend."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUN_OUTPUTS = ROOT / "data/processed/extraction/routed_runs/gemini3_flash_20260628_primary_extraction/route_extraction_outputs.jsonl"
ARTICLES = ROOT / "data/processed/fulltext/articles"
CANDIDATES = OUT / "source_identity_candidates.json"


def norm(value: object) -> str:
    return " ".join(str(value or "").split())


def doi(value: object) -> str:
    text = norm(value).lower()
    text = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", text)
    return text.rstrip(".,;:)]}")


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def classify(artifact: dict) -> tuple[str, str, str]:
    backend = norm(artifact.get("best_backend")).lower()
    source = norm(artifact.get("fulltext_source")).lower()
    dataset = norm(artifact.get("source_artifact_dataset")).lower()
    extraction_format = ""
    for extraction in artifact.get("extractions", []) or []:
        if not isinstance(extraction, dict):
            continue
        if norm(extraction.get("backend")).lower() == backend or not extraction_format:
            metadata = extraction.get("metadata") if isinstance(extraction.get("metadata"), dict) else {}
            extraction_format = norm(metadata.get("format")).lower()
            if norm(extraction.get("backend")).lower() == backend:
                break
    xml_markers = " ".join((backend, source, dataset, extraction_format))
    if any(marker in xml_markers for marker in ("jats_xml", "pmc_oai_xml", "europepmc_fulltext_xml", "europepmc_xml", "pmc_xml")):
        channel = "Direct article XML"
    elif backend == "grobid" or extraction_format == "tei_xml":
        channel = "PDF converted with GROBID"
    elif any(marker in backend for marker in ("ocr", "pdftotext", "pymupdf")):
        channel = "Other PDF/OCR conversion"
    else:
        channel = "Other/unknown"
    return channel, backend or "missing", source or dataset or "missing"


def main() -> None:
    candidates = {doi(row.get("requested_doi")): row for row in json.loads(CANDIDATES.read_text(encoding="utf-8"))}
    used_dois: set[str] = set()
    for row in read_jsonl(RUN_OUTPUTS):
        result = row.get("result") if isinstance(row.get("result"), dict) else {}
        if norm(row.get("status")) == "ok" and norm(result.get("text_depth")) == "article_text":
            key = doi(result.get("study_doi"))
            if key:
                used_dois.add(key)

    by_channel: dict[str, Counter] = defaultdict(Counter)
    by_backend: dict[str, Counter] = defaultdict(Counter)
    examples: dict[str, list[dict]] = defaultdict(list)
    missing_artifacts = 0
    for key in sorted(used_dois):
        path = ARTICLES / f"{slug(key)}.json"
        if not path.exists():
            missing_artifacts += 1
            continue
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            missing_artifacts += 1
            continue
        channel, backend, source = classify(artifact)
        candidate = candidates.get(key)
        for bucket in (by_channel[channel], by_backend[backend]):
            bucket["used_article_text_records"] += 1
            if candidate:
                bucket["candidate_records"] += 1
                bucket[f"priority_{candidate.get('priority', 'unknown').lower()}"] += 1
                bucket["current_kg_findings"] += int(candidate.get("current_kg_finding_count", 0) or 0)
                if int(candidate.get("current_kg_finding_count", 0) or 0) > 0:
                    bucket["candidate_records_with_kg"] += 1
                problem = norm(candidate.get("problem_type"))
                if "Artifact header DOI differs" in problem:
                    bucket["explicit_header_doi_conflict"] += 1
                if "Extraction warning indicates identity mismatch" in problem:
                    bucket["model_identity_warning"] += 1
                if "Merged/multi-study source warning" in problem:
                    bucket["mixed_container_warning"] += 1
        if candidate and len(examples[channel]) < 12:
            examples[channel].append(
                {
                    "doi": key,
                    "priority": candidate.get("priority"),
                    "problem_type": candidate.get("problem_type"),
                    "requested_title": candidate.get("requested_title"),
                    "artifact_header_doi": candidate.get("artifact_header_doi"),
                    "artifact_header_title": candidate.get("artifact_header_title"),
                    "kg_findings": candidate.get("current_kg_finding_count"),
                    "backend": backend,
                    "source": source,
                }
            )

    def rows(mapping: dict[str, Counter]) -> list[dict]:
        out = []
        for name, counts in sorted(mapping.items(), key=lambda item: -item[1]["used_article_text_records"]):
            row = {"name": name, **dict(counts)}
            denominator = counts["used_article_text_records"]
            row["candidate_rate"] = round(counts["candidate_records"] / denominator, 4) if denominator else 0
            row["explicit_conflict_rate"] = round(counts["explicit_header_doi_conflict"] / denominator, 4) if denominator else 0
            out.append(row)
        return out

    report = {
        "used_article_text_dois": len(used_dois),
        "missing_or_unreadable_artifacts": missing_artifacts,
        "candidate_dois": len(candidates),
        "by_channel": rows(by_channel),
        "by_backend": rows(by_backend),
        "examples": examples,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
