#!/usr/bin/env python3
"""Build frontier-LLM-ready evidence packets from full-text artifacts.

The PDF conversion stage preserves raw GROBID TEI. This script turns that raw
TEI plus paper-library metadata into stable JSONL packets for downstream LLM
evidence assessment and data extraction.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, List

try:
    from pipeline.fulltext.convert_pdfs import (
        DATASET_CONFIG,
        compact_text,
        doi_to_slug,
        element_text,
        load_json_array,
        load_json_object,
        local_name,
        normalize,
        normalize_doi,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.convert_pdfs import (
        DATASET_CONFIG,
        compact_text,
        doi_to_slug,
        element_text,
        load_json_array,
        load_json_object,
        local_name,
        normalize,
        normalize_doi,
    )

ROOT = Path(__file__).resolve().parents[2]
FULLTEXT_DIR = ROOT / "data" / "processed" / "fulltext"
PACKET_SCHEMA_VERSION = "llm_evidence_packet_v1"
RECONSTRUCTED_TEXT_SEPARATOR = "\n\n"
XML_ID_ATTR = "{http://www.w3.org/XML/1998/namespace}id"

PAPER_METADATA_FIELDS = [
    "study_doi",
    "openalex_id",
    "pmid",
    "pmcid",
    "study_title",
    "study_year",
    "authors",
    "study_journal",
    "publication_type",
    "trial_registry_ids",
    "publication_date",
    "journal_issn",
    "journal_eissn",
    "publisher",
    "mesh_terms",
    "keywords",
    "funders",
    "grant_ids",
    "related_dois",
    "publication_relations",
    "is_retracted",
    "has_correction",
    "language",
    "semantic_scholar_id",
    "open_access_is_oa",
    "open_access_status",
    "best_pdf_url",
    "pdf_local_path",
    "pdf_download_status",
    "library_status",
    "abstract",
]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def rows_by_doi(rows: Iterable[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in rows:
        doi = normalize_doi(row.get("study_doi", ""))
        if doi:
            out[doi] = row
    return out


def best_extraction(artifact: dict) -> dict:
    backend = normalize(artifact.get("best_backend", ""))
    for extraction in artifact.get("extractions", []):
        if isinstance(extraction, dict) and normalize(extraction.get("backend", "")) == backend:
            return extraction
    for extraction in artifact.get("extractions", []):
        if isinstance(extraction, dict) and extraction.get("status") == "ok":
            return extraction
    return {}


def parse_doi_file(path: Path) -> set[str]:
    dois: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if not row:
                continue
            first = normalize(row[0])
            if not first or first.startswith("#"):
                continue
            doi = normalize_doi(first)
            if doi:
                dois.add(doi)
    return dois


def parse_tei(raw: str) -> ET.Element | None:
    if not normalize(raw).lstrip().startswith("<"):
        return None
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        return None


def direct_child_text(element: ET.Element, names: set[str]) -> str:
    parts = []
    for child in list(element):
        name = local_name(child.tag)
        if name in names:
            text = element_text(child)
            if text:
                parts.append(text)
    return compact_text(" ".join(parts))


def direct_heading(element: ET.Element, default: str = "Section") -> str:
    for child in list(element):
        if local_name(child.tag) == "head":
            heading = element_text(child)
            if heading:
                return heading
    return default


def xml_id(element: ET.Element) -> str:
    return normalize(element.attrib.get(XML_ID_ATTR, "") or element.attrib.get("xml:id", "") or element.attrib.get("id", ""))


def section_type_for_heading(heading: str) -> str:
    text = normalize(heading).lower()
    if "abstract" in text:
        return "abstract"
    if "introduction" in text or text in {"background", "overview"}:
        return "introduction"
    if any(marker in text for marker in ["method", "materials", "participants", "procedure", "statistical analysis"]):
        return "methods"
    if any(marker in text for marker in ["result", "finding", "outcome", "efficacy", "safety"]):
        return "results"
    if "discussion" in text:
        return "discussion"
    if any(marker in text for marker in ["conclusion", "summary"]):
        return "conclusion"
    if "limitation" in text:
        return "limitations"
    if any(marker in text for marker in ["funding", "financial support"]):
        return "funding"
    if any(marker in text for marker in ["conflict", "competing interest", "declaration"]):
        return "conflicts"
    if any(marker in text for marker in ["ethic", "consent", "institutional review"]):
        return "ethics"
    if "data availability" in text:
        return "data_availability"
    if "supplement" in text:
        return "supplement"
    return "other"


def add_section(sections: List[dict], heading: str, text: str, level: int = 1, xml_identifier: str = "") -> None:
    body = compact_text(text)
    if not body:
        return
    sections.append(
        {
            "heading": normalize(heading) or "Section",
            "section_type": section_type_for_heading(heading),
            "level": level,
            "xml_id": xml_identifier,
            "text": body,
        }
    )


def walk_div(div: ET.Element, sections: List[dict], level: int = 1) -> None:
    heading = direct_heading(div)
    text_parts = []
    for child in list(div):
        name = local_name(child.tag)
        if name in {"head", "div", "figure", "table"}:
            continue
        if name in {"p", "ab", "list", "quote"}:
            text = element_text(child)
            if text:
                text_parts.append(text)
    add_section(sections, heading=heading, text=" ".join(text_parts), level=level, xml_identifier=xml_id(div))

    for child in list(div):
        if local_name(child.tag) == "div":
            walk_div(child, sections=sections, level=level + 1)


def sections_from_tei_full(tei_xml: str) -> List[dict]:
    root = parse_tei(tei_xml)
    if root is None:
        text = compact_text(tei_xml)
        return with_section_offsets([{"heading": "Document", "section_type": "document", "level": 0, "xml_id": "", "text": text}]) if text else []

    sections: List[dict] = []
    for element in root.iter():
        if local_name(element.tag) != "abstract":
            continue
        text = direct_child_text(element, {"p", "ab"}) or element_text(element)
        add_section(sections, heading="Abstract", text=text, level=1, xml_identifier=xml_id(element))

    for body in [element for element in root.iter() if local_name(element.tag) == "body"]:
        body_direct = direct_child_text(body, {"p", "ab", "list"})
        add_section(sections, heading="Body", text=body_direct, level=1, xml_identifier=xml_id(body))
        for child in list(body):
            if local_name(child.tag) == "div":
                walk_div(child, sections=sections, level=1)

    if not sections:
        text = element_text(root)
        add_section(sections, heading="Document", text=text, level=0, xml_identifier=xml_id(root))
    return with_section_offsets(sections)


def with_section_offsets(sections: List[dict]) -> List[dict]:
    offset = 0
    out = []
    for idx, section in enumerate(sections, start=1):
        text = normalize(section.get("text", ""))
        if not text:
            continue
        start = offset
        end = start + len(text)
        item = dict(section)
        item["section_id"] = f"S{idx:03d}"
        item["char_start"] = start
        item["char_end"] = end
        item["char_count"] = len(text)
        out.append(item)
        offset = end + len(RECONSTRUCTED_TEXT_SEPARATOR)
    return out


def parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in list(parent)}


def nearest_section_heading(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> str:
    current = element
    while current in parents:
        current = parents[current]
        if local_name(current.tag) == "div":
            return direct_heading(current)
    return ""


def child_text(element: ET.Element, child_names: set[str]) -> str:
    for child in list(element):
        if local_name(child.tag) in child_names:
            text = element_text(child)
            if text:
                return text
    return ""


def extract_tables_and_figures(tei_xml: str) -> tuple[list[dict], list[dict]]:
    root = parse_tei(tei_xml)
    if root is None:
        return [], []
    parents = parent_map(root)
    tables: list[dict] = []
    figures: list[dict] = []
    seen_tables: set[int] = set()

    for element in root.iter():
        if local_name(element.tag) != "figure":
            continue
        figure_type = normalize(element.attrib.get("type", "")).lower()
        has_table = any(local_name(child.tag) == "table" for child in element.iter())
        payload = {
            "xml_id": xml_id(element),
            "label": child_text(element, {"label"}),
            "caption": child_text(element, {"figDesc"}) or child_text(element, {"head"}),
            "section_heading": nearest_section_heading(element, parents),
            "text": element_text(element),
        }
        if figure_type == "table" or has_table:
            payload["table_id"] = f"T{len(tables) + 1:03d}"
            tables.append(payload)
            for child in element.iter():
                if local_name(child.tag) == "table":
                    seen_tables.add(id(child))
        else:
            payload["figure_id"] = f"F{len(figures) + 1:03d}"
            figures.append(payload)

    for element in root.iter():
        if local_name(element.tag) != "table" or id(element) in seen_tables:
            continue
        payload = {
            "table_id": f"T{len(tables) + 1:03d}",
            "xml_id": xml_id(element),
            "label": "",
            "caption": "",
            "section_heading": nearest_section_heading(element, parents),
            "text": element_text(element),
        }
        tables.append(payload)

    return tables, figures


def first_descendant_text(element: ET.Element, tag_name: str) -> str:
    for child in element.iter():
        if local_name(child.tag) == tag_name:
            text = element_text(child)
            if text:
                return text
    return ""


def first_idno(element: ET.Element, id_type: str) -> str:
    wanted = id_type.lower()
    for child in element.iter():
        if local_name(child.tag) != "idno":
            continue
        if normalize(child.attrib.get("type", "")).lower() == wanted:
            return element_text(child)
    return ""


def first_date(element: ET.Element) -> str:
    for child in element.iter():
        if local_name(child.tag) == "date":
            return normalize(child.attrib.get("when", "")) or element_text(child)
    return ""


def extract_references(tei_xml: str, max_references: int = 200) -> list[dict]:
    root = parse_tei(tei_xml)
    if root is None or max_references == 0:
        return []
    refs = []
    for element in root.iter():
        if local_name(element.tag) != "biblStruct":
            continue
        refs.append(
            {
                "reference_id": f"R{len(refs) + 1:03d}",
                "xml_id": xml_id(element),
                "title": first_descendant_text(element, "title"),
                "doi": normalize_doi(first_idno(element, "doi")),
                "pmid": first_idno(element, "pmid"),
                "year": first_date(element),
                "text": element_text(element),
            }
        )
        if max_references > 0 and len(refs) >= max_references:
            break
    return refs


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / 4))


def chunk_text(text: str, max_chars: int, overlap_chars: int) -> list[tuple[int, int, str]]:
    text = normalize(text)
    if not text:
        return []
    max_chars = max(500, max_chars)
    overlap = max(0, min(overlap_chars, max_chars // 3))
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            split_at = max(text.rfind(". ", start, end), text.rfind("\n", start, end))
            if split_at > start + max_chars // 2:
                end = split_at + 1
        chunks.append((start, end, text[start:end].strip()))
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def build_llm_chunks(
    sections: list[dict],
    max_chunk_chars: int,
    overlap_chars: int,
    max_chunks_per_paper: int = 0,
) -> list[dict]:
    chunks = []
    for section in sections:
        for start, end, text in chunk_text(section.get("text", ""), max_chars=max_chunk_chars, overlap_chars=overlap_chars):
            if not text:
                continue
            chunks.append(
                {
                    "chunk_id": f"C{len(chunks) + 1:03d}",
                    "section_id": section.get("section_id", ""),
                    "section_type": section.get("section_type", ""),
                    "heading": section.get("heading", ""),
                    "section_char_start": start,
                    "section_char_end": end,
                    "document_char_start": int(section.get("char_start", 0)) + start,
                    "document_char_end": int(section.get("char_start", 0)) + end,
                    "char_count": len(text),
                    "token_estimate": estimate_tokens(text),
                    "text": text,
                }
            )
            if max_chunks_per_paper > 0 and len(chunks) >= max_chunks_per_paper:
                return chunks
    return chunks


def source_hints(row: dict) -> dict:
    publication_type = normalize(row.get("publication_type", ""))
    title = normalize(row.get("study_title", ""))
    text = f"{publication_type} {title}".lower()
    if re.search(r"meta[- ]analysis|metaanalysis", text):
        return {"source_family_hint": "evidence_synthesis", "paper_type_hint": "meta_analysis", "source_hint_reason": "publication metadata contains meta-analysis"}
    if "systematic review" in text:
        return {"source_family_hint": "evidence_synthesis", "paper_type_hint": "systematic_review", "source_hint_reason": "publication metadata contains systematic review"}
    if re.search(r"\breview\b", text):
        return {"source_family_hint": "evidence_synthesis", "paper_type_hint": "review", "source_hint_reason": "publication metadata contains review"}
    if "protocol" in text:
        return {"source_family_hint": "protocol", "paper_type_hint": "protocol", "source_hint_reason": "publication metadata contains protocol"}
    if re.search(r"editorial|comment|letter|viewpoint|perspective", text):
        return {"source_family_hint": "opinion_or_commentary", "paper_type_hint": "commentary", "source_hint_reason": "publication metadata contains commentary-like type"}
    if re.search(r"correction|erratum|corrigendum|retraction", text):
        return {"source_family_hint": "correction", "paper_type_hint": "correction", "source_hint_reason": "publication metadata contains correction-like type"}
    if re.search(r"conference|meeting abstract", text):
        return {"source_family_hint": "conference_abstract", "paper_type_hint": "conference_abstract", "source_hint_reason": "publication metadata contains conference abstract"}
    if re.search(r"case report|case series", text):
        return {"source_family_hint": "original_empirical", "paper_type_hint": "case_report", "source_hint_reason": "publication metadata contains case report/series"}
    return {"source_family_hint": "uncertain", "paper_type_hint": "uncertain", "source_hint_reason": "no strong publication-type hint"}


def compact_contexts(row: dict) -> list[dict]:
    contexts = row.get("contexts", [])
    if not isinstance(contexts, list):
        return []
    out = []
    seen = set()
    for context in contexts:
        if not isinstance(context, dict):
            continue
        compact = {
            "compound": normalize(context.get("compound", "")),
            "entity": normalize(context.get("entity", "")),
            "study_title": normalize(context.get("study_title", "")),
            "study_year": normalize(context.get("study_year", "")),
        }
        key = tuple(compact.items())
        if key in seen:
            continue
        seen.add(key)
        out.append(compact)
    return out


def paper_metadata(row: dict, artifact: dict) -> dict:
    metadata = {field: normalize(row.get(field, "")) for field in PAPER_METADATA_FIELDS}
    metadata["study_doi"] = normalize_doi(metadata.get("study_doi", "")) or normalize_doi(artifact.get("study_doi", ""))
    metadata["openalex_id"] = metadata.get("openalex_id", "") or normalize(artifact.get("openalex_id", ""))
    metadata["study_title"] = metadata.get("study_title", "") or normalize(artifact.get("study_title", ""))
    metadata["study_year"] = metadata.get("study_year", "") or normalize(artifact.get("study_year", ""))
    return metadata


def build_packet(
    dataset: str,
    artifact_path: Path,
    artifact: dict,
    paper_row: dict,
    *,
    max_chunk_chars: int,
    overlap_chars: int,
    max_chunks_per_paper: int,
    max_references: int,
    include_section_text: bool = True,
) -> dict:
    extraction = best_extraction(artifact)
    raw_text = normalize(extraction.get("text", ""))
    sections = sections_from_tei_full(raw_text)
    tables, figures = extract_tables_and_figures(raw_text)
    references = extract_references(raw_text, max_references=max_references)
    chunks = build_llm_chunks(
        sections,
        max_chunk_chars=max_chunk_chars,
        overlap_chars=overlap_chars,
        max_chunks_per_paper=max_chunks_per_paper,
    )
    reconstructed_text = RECONSTRUCTED_TEXT_SEPARATOR.join(section.get("text", "") for section in sections)
    sections_out = sections if include_section_text else [{k: v for k, v in section.items() if k != "text"} for section in sections]
    metadata = paper_metadata(paper_row, artifact)
    doi = normalize_doi(metadata.get("study_doi", "")) or normalize_doi(artifact.get("study_doi", ""))

    return {
        "schema_version": PACKET_SCHEMA_VERSION,
        "created_at_utc": now_utc(),
        "packet_id": f"{dataset}:{doi}",
        "dataset": dataset,
        "study_doi": doi,
        "paper_metadata": metadata,
        "candidate_contexts": compact_contexts(paper_row),
        "source_hints": source_hints(metadata),
        "fulltext_provenance": {
            "artifact_path": str(artifact_path),
            "pdf_local_path": normalize(artifact.get("pdf_local_path", "")) or normalize(metadata.get("pdf_local_path", "")),
            "best_backend": normalize(artifact.get("best_backend", "")),
            "best_char_count": int(artifact.get("best_char_count", 0) or 0),
            "best_section_count": int(artifact.get("best_section_count", 0) or 0),
            "extraction_format": normalize(extraction.get("metadata", {}).get("format", "")),
            "reconstructed_text_separator": RECONSTRUCTED_TEXT_SEPARATOR,
            "reconstructed_text_sha256": hashlib.sha256(reconstructed_text.encode("utf-8")).hexdigest(),
        },
        "document_summary": {
            "section_count": len(sections),
            "chunk_count": len(chunks),
            "table_count": len(tables),
            "figure_count": len(figures),
            "reference_count": len(references),
            "reconstructed_char_count": len(reconstructed_text),
            "chunk_token_estimate": sum(int(chunk.get("token_estimate", 0) or 0) for chunk in chunks),
        },
        "sections": sections_out,
        "tables": tables,
        "figures": figures,
        "references": references,
        "llm_chunks": chunks,
    }


def default_out_jsonl(dataset: str) -> Path:
    return FULLTEXT_DIR / f"llm_packets_{dataset}.jsonl"


def default_report_json(dataset: str) -> Path:
    return FULLTEXT_DIR / f"llm_packets_{dataset}_report.json"


def iter_artifact_paths(dataset: str, artifact_dir: Path, doi_filter: set[str] | None = None) -> Iterable[Path]:
    for path in sorted(artifact_dir.glob("*.json")):
        if doi_filter is not None:
            doi = normalize_doi(path.stem.replace("_", "/"))
            artifact = load_json_object(path)
            doi = normalize_doi(artifact.get("study_doi", "")) or doi
            if doi not in doi_filter:
                continue
        yield path


def build_dataset_packets(
    dataset: str,
    *,
    paper_library: Path,
    artifact_dir: Path,
    out_jsonl: Path,
    report_json: Path,
    doi_filter: set[str] | None,
    limit: int,
    max_chunk_chars: int,
    overlap_chars: int,
    max_chunks_per_paper: int,
    max_references: int,
    include_section_text: bool,
) -> dict:
    paper_rows = rows_by_doi(load_json_array(paper_library))
    artifact_paths = list(iter_artifact_paths(dataset, artifact_dir=artifact_dir, doi_filter=doi_filter))
    if limit > 0:
        artifact_paths = artifact_paths[:limit]

    counts = {
        "artifact_files_selected": len(artifact_paths),
        "packets_written": 0,
        "missing_paper_library_rows": 0,
        "missing_successful_extraction": 0,
        "missing_sections": 0,
        "total_chunks": 0,
        "total_tables": 0,
        "total_figures": 0,
        "total_references": 0,
    }
    missing_library_dois = []
    skipped = []

    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w", encoding="utf-8") as handle:
        for artifact_path in artifact_paths:
            artifact = load_json_object(artifact_path)
            extraction = best_extraction(artifact)
            doi = normalize_doi(artifact.get("study_doi", ""))
            if not doi:
                doi = normalize_doi(artifact_path.stem.replace("_", "/"))
            if not extraction:
                counts["missing_successful_extraction"] += 1
                skipped.append({"artifact_path": str(artifact_path), "study_doi": doi, "reason": "missing_successful_extraction"})
                continue
            paper_row = paper_rows.get(doi, {})
            if not paper_row:
                counts["missing_paper_library_rows"] += 1
                missing_library_dois.append(doi)
            packet = build_packet(
                dataset,
                artifact_path=artifact_path,
                artifact=artifact,
                paper_row=paper_row,
                max_chunk_chars=max_chunk_chars,
                overlap_chars=overlap_chars,
                max_chunks_per_paper=max_chunks_per_paper,
                max_references=max_references,
                include_section_text=include_section_text,
            )
            if not packet["sections"]:
                counts["missing_sections"] += 1
            counts["packets_written"] += 1
            counts["total_chunks"] += len(packet["llm_chunks"])
            counts["total_tables"] += len(packet["tables"])
            counts["total_figures"] += len(packet["figures"])
            counts["total_references"] += len(packet["references"])
            handle.write(json.dumps(packet, ensure_ascii=False) + "\n")

    report = {
        "generated_at_utc": now_utc(),
        "schema_version": PACKET_SCHEMA_VERSION,
        "dataset": dataset,
        "inputs": {
            "paper_library": str(paper_library),
            "artifact_dir": str(artifact_dir),
            "doi_filter_count": len(doi_filter) if doi_filter is not None else None,
            "limit": limit,
            "max_chunk_chars": max_chunk_chars,
            "overlap_chars": overlap_chars,
            "max_chunks_per_paper": max_chunks_per_paper,
            "max_references": max_references,
            "include_section_text": include_section_text,
        },
        "outputs": {
            "jsonl": str(out_jsonl),
            "report_json": str(report_json),
        },
        "counts": counts,
        "missing_paper_library_dois": missing_library_dois[:200],
        "skipped": skipped[:200],
    }
    write_json(report_json, report)
    return report


def dataset_names(raw: str) -> list[str]:
    if raw == "all":
        return ["disorder", "mechanistic"]
    return [raw]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build JSONL LLM evidence packets from full-text artifacts")
    parser.add_argument("--dataset", choices=["all", "disorder", "mechanistic"], default="all")
    parser.add_argument("--paper-library", default="", help="Override paper library JSON path; only valid for one dataset")
    parser.add_argument("--artifact-dir", default="", help="Override artifact directory; only valid for one dataset")
    parser.add_argument("--out-jsonl", default="", help="Override JSONL output path; only valid for one dataset")
    parser.add_argument("--report-json", default="", help="Override report JSON path; only valid for one dataset")
    parser.add_argument("--doi-file", default="", help="Optional DOI queue/list limiting packet generation")
    parser.add_argument("--limit", type=int, default=0, help="Maximum artifacts per dataset; 0 means all")
    parser.add_argument("--max-chunk-chars", type=int, default=6000)
    parser.add_argument("--chunk-overlap-chars", type=int, default=300)
    parser.add_argument("--max-chunks-per-paper", type=int, default=0, help="0 means all chunks")
    parser.add_argument("--max-references", type=int, default=200, help="Maximum references per packet; negative means all")
    parser.add_argument("--omit-section-text", action="store_true", help="Keep chunk text but omit full section text from packets")
    args = parser.parse_args()

    selected_datasets = dataset_names(args.dataset)
    if len(selected_datasets) > 1 and any([args.paper_library, args.artifact_dir, args.out_jsonl, args.report_json]):
        raise SystemExit("--paper-library/--artifact-dir/--out-jsonl/--report-json overrides require a single dataset")

    doi_filter = parse_doi_file(Path(args.doi_file).resolve()) if args.doi_file else None
    reports = []
    for dataset in selected_datasets:
        cfg = DATASET_CONFIG[dataset]
        paper_library = Path(args.paper_library).resolve() if args.paper_library else cfg["paper_db_json"]
        artifact_dir = Path(args.artifact_dir).resolve() if args.artifact_dir else cfg["out_dir"]
        out_jsonl = Path(args.out_jsonl).resolve() if args.out_jsonl else default_out_jsonl(dataset)
        report_json = Path(args.report_json).resolve() if args.report_json else default_report_json(dataset)
        report = build_dataset_packets(
            dataset,
            paper_library=paper_library,
            artifact_dir=artifact_dir,
            out_jsonl=out_jsonl,
            report_json=report_json,
            doi_filter=doi_filter,
            limit=max(0, args.limit),
            max_chunk_chars=max(500, args.max_chunk_chars),
            overlap_chars=max(0, args.chunk_overlap_chars),
            max_chunks_per_paper=max(0, args.max_chunks_per_paper),
            max_references=args.max_references,
            include_section_text=not args.omit_section_text,
        )
        reports.append(report)
        counts = report["counts"]
        print(f"Dataset: {dataset}")
        print(f"Artifacts selected: {counts['artifact_files_selected']}")
        print(f"Packets written: {counts['packets_written']}")
        print(f"Total chunks: {counts['total_chunks']}")
        print(f"JSONL: {report['outputs']['jsonl']}")
        print(f"Report: {report['outputs']['report_json']}")

    if len(reports) > 1:
        run_report = {
            "generated_at_utc": now_utc(),
            "schema_version": PACKET_SCHEMA_VERSION,
            "status": "ok",
            "datasets": selected_datasets,
            "reports": reports,
        }
        run_report_path = FULLTEXT_DIR / "llm_packets_run_report.json"
        write_json(run_report_path, run_report)
        print(f"Run report: {run_report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
