#!/usr/bin/env python3
"""Build article text inputs for model extraction from extracted text artifacts.

The PDF conversion stage preserves raw GROBID TEI. The helpers in this module
turn those artifacts and routed paper metadata into stable records containing
the sections, tables, figures, and references needed for downstream extraction.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

try:
    from pipeline.fulltext.convert_pdfs import (
        compact_text,
        element_text,
        local_name,
        normalize,
        normalize_doi,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.convert_pdfs import (
        compact_text,
        element_text,
        local_name,
        normalize,
        normalize_doi,
    )

PACKET_SCHEMA_VERSION = "llm_evidence_packet_v1"
RECONSTRUCTED_TEXT_SEPARATOR = "\n\n"
XML_ID_ATTR = "{http://www.w3.org/XML/1998/namespace}id"
PACKET_PROFILE_FULL = "full"
PACKET_PROFILE_PRIMARY_EMPIRICAL = "primary_empirical"
PACKET_PROFILE_SECONDARY_SYNTHESIS = "secondary_synthesis"
PACKET_PROFILE_REVIEW_COVERAGE = "review_coverage"
SECTION_STRATEGY_ALL_SECTIONS_ALIAS = "all_sections"
SECTION_STRATEGY_PRIMARY_STUDY_ALIAS = "primary_study"
SECTION_STRATEGY_META_ANALYSIS_ALIAS = "meta_analysis"
SECTION_STRATEGY_REVIEW_ALIAS = "review"
SECTION_SELECTION_STRATEGY_ALIASES = {
    SECTION_STRATEGY_ALL_SECTIONS_ALIAS: PACKET_PROFILE_FULL,
    SECTION_STRATEGY_PRIMARY_STUDY_ALIAS: PACKET_PROFILE_PRIMARY_EMPIRICAL,
    SECTION_STRATEGY_META_ANALYSIS_ALIAS: PACKET_PROFILE_SECONDARY_SYNTHESIS,
    SECTION_STRATEGY_REVIEW_ALIAS: PACKET_PROFILE_REVIEW_COVERAGE,
}
PRIMARY_EMPIRICAL_EXCLUDED_SECTION_TYPES = {
    "introduction",
    "discussion",
    "conclusion",
    "limitations",
    "funding",
    "conflicts",
    "ethics",
    "data_availability",
    "supplement",
}

PRIMARY_EMPIRICAL_EXCLUDED_HEADING_MARKERS = (
    "introduction",
    "background",
    "discussion",
    "comment",
    "commentary",
    "conclusion",
    "limitations",
    "acknowledg",
    "funding",
    "conflict",
    "ethics",
    "data availability",
    "supplement",
)

PRIMARY_EMPIRICAL_COMMON_MARKERS = (
    "method",
    "material",
    "participant",
    "patient",
    "subject",
    "animal",
    "sample",
    "procedure",
    "protocol",
    "intervention",
    "exposure",
    "dose",
    "dosage",
    "administration",
    "treatment",
    "randomi",
    "blinding",
    "measure",
    "assessment",
    "statistical",
    "analysis",
    "result",
    "finding",
    "outcome",
    "efficacy",
    "safety",
    "adverse",
    "response",
    "remission",
    "follow-up",
    "table",
)

PRIMARY_EMPIRICAL_TOPIC_MARKERS = (
    "assay",
    "binding",
    "affinity",
    "receptor",
    "transporter",
    "enzyme",
    "protein",
    "pharmacolog",
    "radioligand",
    "autoradiograph",
    "functional",
    "activity",
    "agonist",
    "antagonist",
    "inhib",
    "uptake",
    "release",
    "calcium",
    "camp",
    "inositol",
    "electrophysiolog",
    "western blot",
    "pcr",
    "clinical",
    "symptom",
    "depression",
    "anxiety",
    "ptsd",
    "pain",
    "craving",
    "withdrawal",
    "relapse",
    "reinstatement",
    "abstinence",
    "functioning",
    "quality of life",
    "scale",
    "score",
)

NON_EVIDENCE_SECTION_TYPES = {
    "funding",
    "conflicts",
    "ethics",
    "data_availability",
    "supplement",
}

SECONDARY_SYNTHESIS_CORE_SECTION_TYPES = {
    "abstract",
    "methods",
    "results",
    "discussion",
    "conclusion",
    "limitations",
}

SECONDARY_SYNTHESIS_MARKERS = (
    "systematic review",
    "meta-analysis",
    "metaanalysis",
    "network meta",
    "evidence synthesis",
    "search strateg",
    "database search",
    "eligib",
    "inclusion criter",
    "exclusion criter",
    "study selection",
    "screening",
    "prisma",
    "included stud",
    "excluded stud",
    "study characteristics",
    "data extraction",
    "risk of bias",
    "quality assessment",
    "grade",
    "certainty",
    "pooled",
    "forest plot",
    "funnel plot",
    "publication bias",
    "heterogeneity",
    "i2",
    "tau",
    "random-effect",
    "fixed-effect",
    "meta-regression",
    "subgroup",
    "sensitivity",
    "effect size",
    "standardized mean difference",
    "mean difference",
    "odds ratio",
    "risk ratio",
    "confidence interval",
    "credible interval",
    "league table",
)

REVIEW_COVERAGE_CORE_SECTION_TYPES = {
    "abstract",
    "methods",
    "results",
    "discussion",
    "conclusion",
    "limitations",
}

REVIEW_COVERAGE_MARKERS = (
    "review",
    "scope",
    "objective",
    "aim",
    "overview",
    "background",
    "evidence",
    "coverage",
    "clinical",
    "mechanism",
    "safety",
    "tolerability",
    "adverse",
    "therapeutic",
    "psychedelic",
    "psilocybin",
    "lsd",
    "mdma",
    "ketamine",
    "ayahuasca",
    "dmt",
    "mescaline",
    "5-ht2a",
    "serotonin",
    "model",
    "preclinical",
    "human",
    "limitation",
    "gap",
    "future",
    "uncertain",
    "conclusion",
    "summary",
)

SECONDARY_SOURCE_FAMILIES = {
    "evidence_synthesis",
    "opinion_or_commentary",
    "protocol",
    "correction",
    "conference_abstract",
}

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


def best_extraction(artifact: dict) -> dict:
    backend = normalize(artifact.get("best_backend", ""))
    for extraction in artifact.get("extractions", []):
        if isinstance(extraction, dict) and normalize(extraction.get("backend", "")) == backend:
            return extraction
    for extraction in artifact.get("extractions", []):
        if isinstance(extraction, dict) and extraction.get("status") == "ok":
            return extraction
    return {}


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
        if local_name(child.tag) in {"head", "title"}:
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


def element_is_section(element: ET.Element) -> bool:
    return local_name(element.tag) in {"div", "sec"}


def walk_div(div: ET.Element, sections: List[dict], level: int = 1) -> None:
    heading = direct_heading(div)
    text_parts = []
    for child in list(div):
        name = local_name(child.tag)
        if name in {"head", "title", "div", "sec", "figure", "fig", "table", "table-wrap"}:
            continue
        if name in {"p", "ab", "list", "quote", "disp-quote"}:
            text = element_text(child)
            if text:
                text_parts.append(text)
    add_section(sections, heading=heading, text=" ".join(text_parts), level=level, xml_identifier=xml_id(div))

    for child in list(div):
        if element_is_section(child):
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
            if element_is_section(child):
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


def canonical_packet_profile(profile: str) -> str:
    profile = normalize(profile) or PACKET_PROFILE_FULL
    if profile in SECTION_SELECTION_STRATEGY_ALIASES:
        return SECTION_SELECTION_STRATEGY_ALIASES[profile]
    return profile


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


def text_matches_any_marker(text: str, markers: tuple[str, ...]) -> bool:
    norm = normalize(text).lower()
    return any(marker in norm for marker in markers)


def section_matches_primary_empirical_profile(section: dict) -> bool:
    section_type = normalize(section.get("section_type", ""))
    if section_type == "abstract":
        return True
    if section_type in {"methods", "results"}:
        return True
    if section_type in PRIMARY_EMPIRICAL_EXCLUDED_SECTION_TYPES:
        return False
    heading = normalize(section.get("heading", "")).lower()
    if text_matches_any_marker(heading, PRIMARY_EMPIRICAL_EXCLUDED_HEADING_MARKERS):
        return False
    haystack = " ".join(
        [
            heading,
            section_type,
            normalize(section.get("text", ""))[:2500],
        ]
    )
    return text_matches_any_marker(haystack, PRIMARY_EMPIRICAL_COMMON_MARKERS + PRIMARY_EMPIRICAL_TOPIC_MARKERS)


def section_matches_secondary_synthesis_profile(section: dict) -> bool:
    section_type = normalize(section.get("section_type", ""))
    if section_type in SECONDARY_SYNTHESIS_CORE_SECTION_TYPES:
        return True
    if section_type in NON_EVIDENCE_SECTION_TYPES:
        return False
    haystack = " ".join(
        [
            normalize(section.get("heading", "")),
            section_type,
            normalize(section.get("text", ""))[:3500],
        ]
    )
    return text_matches_any_marker(haystack, SECONDARY_SYNTHESIS_MARKERS)


def section_matches_review_coverage_profile(section: dict) -> bool:
    section_type = normalize(section.get("section_type", ""))
    if section_type in REVIEW_COVERAGE_CORE_SECTION_TYPES:
        return True
    if section_type in NON_EVIDENCE_SECTION_TYPES:
        return False
    haystack = " ".join(
        [
            normalize(section.get("heading", "")),
            section_type,
            normalize(section.get("text", ""))[:3000],
        ]
    )
    return text_matches_any_marker(haystack, REVIEW_COVERAGE_MARKERS)


def secondary_or_context_hint(hints: dict) -> bool:
    return normalize(hints.get("source_family_hint", "")) in SECONDARY_SOURCE_FAMILIES


def unique_by_identity(items: list[dict]) -> list[dict]:
    out = []
    seen: set[int] = set()
    for item in items:
        key = id(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def first_non_excluded_sections(sections: list[dict], limit: int = 3) -> list[dict]:
    out = []
    for section in sections:
        section_type = normalize(section.get("section_type", ""))
        if section_type == "abstract" or section_type in PRIMARY_EMPIRICAL_EXCLUDED_SECTION_TYPES:
            continue
        out.append(section)
        if len(out) >= limit:
            break
    return out


def first_non_admin_sections(sections: list[dict], limit: int = 4) -> list[dict]:
    out = []
    for section in sections:
        section_type = normalize(section.get("section_type", ""))
        if section_type == "abstract" or section_type in NON_EVIDENCE_SECTION_TYPES:
            continue
        out.append(section)
        if len(out) >= limit:
            break
    return out


def profile_selection_summary(
    *,
    selection_name: str,
    fallback_used: bool,
    source_section_count: int,
    selected_section_count: int,
) -> dict:
    return {
        "section_selection": selection_name,
        "fallback_used": fallback_used,
        "source_section_count": source_section_count,
        "selected_section_count": selected_section_count,
        "excluded_section_count": max(0, source_section_count - selected_section_count),
    }


def select_secondary_sections(
    sections: list[dict],
    *,
    selection_name: str,
    matcher,
) -> tuple[list[dict], dict]:
    selected = [section for section in sections if matcher(section)]
    selected_ids = {id(section) for section in selected}
    body_selected = any(normalize(section.get("section_type", "")) != "abstract" for section in selected)
    fallback_used = False
    if not body_selected:
        fallback_used = True
        for section in first_non_admin_sections(sections):
            if id(section) not in selected_ids:
                selected.append(section)
                selected_ids.add(id(section))
    selected = unique_by_identity(selected)
    return selected, profile_selection_summary(
        selection_name=selection_name,
        fallback_used=fallback_used,
        source_section_count=len(sections),
        selected_section_count=len(selected),
    )


def select_sections_for_profile(
    sections: list[dict],
    *,
    profile: str,
    hints: dict,
) -> tuple[list[dict], dict]:
    profile = canonical_packet_profile(profile)
    if profile == PACKET_PROFILE_FULL:
        return sections, {"section_selection": "full", "fallback_used": False}
    if profile == PACKET_PROFILE_SECONDARY_SYNTHESIS:
        return select_secondary_sections(
            sections,
            selection_name="secondary_synthesis",
            matcher=section_matches_secondary_synthesis_profile,
        )
    if profile == PACKET_PROFILE_REVIEW_COVERAGE:
        return select_secondary_sections(
            sections,
            selection_name="review_coverage",
            matcher=section_matches_review_coverage_profile,
        )
    if profile != PACKET_PROFILE_PRIMARY_EMPIRICAL:
        raise ValueError(f"Unsupported section selection strategy `{profile}`")

    abstracts = [section for section in sections if normalize(section.get("section_type", "")) == "abstract"]
    if secondary_or_context_hint(hints):
        selected = abstracts or sections[:1]
        selected_unique = unique_by_identity(selected)
        return selected_unique, {
            "section_selection": "secondary_or_context_abstract_only",
            "fallback_used": not bool(abstracts),
        }

    selected = [section for section in sections if section_matches_primary_empirical_profile(section)]
    selected_ids = {id(section) for section in selected}
    body_selected = any(normalize(section.get("section_type", "")) != "abstract" for section in selected)
    fallback_used = False
    if not body_selected:
        fallback_used = True
        for section in first_non_excluded_sections(sections):
            if id(section) not in selected_ids:
                selected.append(section)
                selected_ids.add(id(section))

    return selected, profile_selection_summary(
        selection_name=PACKET_PROFILE_PRIMARY_EMPIRICAL,
        fallback_used=fallback_used,
        source_section_count=len(sections),
        selected_section_count=len(selected),
    )


def table_or_figure_matches_primary_empirical_profile(item: dict) -> bool:
    haystack = " ".join(
        [
            normalize(item.get("caption", "")),
            normalize(item.get("section_heading", "")),
            normalize(item.get("text", ""))[:2000],
        ]
    )
    return text_matches_any_marker(haystack, PRIMARY_EMPIRICAL_COMMON_MARKERS + PRIMARY_EMPIRICAL_TOPIC_MARKERS)


def select_tables_figures_references_for_profile(
    tables: list[dict],
    figures: list[dict],
    references: list[dict],
    *,
    profile: str,
    hints: dict,
) -> tuple[list[dict], list[dict], list[dict], dict]:
    profile = canonical_packet_profile(profile)
    if profile == PACKET_PROFILE_FULL:
        return tables, figures, references, {
            "table_selection": "full",
            "figure_selection": "full",
            "reference_selection": "full",
        }
    if profile == PACKET_PROFILE_SECONDARY_SYNTHESIS:
        return tables, figures, references, {
            "table_selection": "all_tables",
            "figure_selection": "all_figures",
            "reference_selection": "all_references",
            "source_figure_count": len(figures),
            "selected_figure_count": len(figures),
        }
    if profile == PACKET_PROFILE_REVIEW_COVERAGE:
        selected_figures = [
            figure
            for figure in figures
            if text_matches_any_marker(
                " ".join(
                    [
                        normalize(figure.get("caption", "")),
                        normalize(figure.get("section_heading", "")),
                        normalize(figure.get("text", ""))[:2000],
                    ]
                ),
                REVIEW_COVERAGE_MARKERS,
            )
        ]
        return tables, selected_figures, [], {
            "table_selection": "all_tables",
            "figure_selection": "review_coverage_marker_filtered",
            "reference_selection": "omitted",
            "source_figure_count": len(figures),
            "selected_figure_count": len(selected_figures),
        }
    if profile != PACKET_PROFILE_PRIMARY_EMPIRICAL:
        raise ValueError(f"Unsupported section selection strategy `{profile}`")
    if secondary_or_context_hint(hints):
        return [], [], [], {
            "table_selection": "secondary_or_context_omitted",
            "figure_selection": "secondary_or_context_omitted",
            "reference_selection": "omitted",
        }
    selected_figures = [figure for figure in figures if table_or_figure_matches_primary_empirical_profile(figure)]
    return tables, selected_figures, [], {
        "table_selection": "all_tables",
        "figure_selection": "lean_marker_filtered",
        "reference_selection": "omitted",
        "source_figure_count": len(figures),
        "selected_figure_count": len(selected_figures),
    }


def source_hints(row: dict) -> dict:
    routed_source_family = normalize(row.get("source_family", "")).lower()
    prompt_profiles = normalize(row.get("prompt_profiles", row.get("prompt_profile", ""))).lower()
    if routed_source_family in {"primary", "primary_study"} or any(
        token.strip().startswith("primary_") for token in prompt_profiles.split("|")
    ):
        return {
            "source_family_hint": "original_empirical",
            "paper_type_hint": "primary_study",
            "source_hint_reason": "explicit extraction route classifies the paper as primary evidence",
        }
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
    include_candidate_contexts: bool = True,
    packet_profile: str = "full",
) -> dict:
    requested_packet_profile = normalize(packet_profile) or PACKET_PROFILE_FULL
    packet_profile = canonical_packet_profile(requested_packet_profile)
    extraction = best_extraction(artifact)
    raw_text = normalize(extraction.get("text", ""))
    source_sections = sections_from_tei_full(raw_text)
    source_tables, source_figures = extract_tables_and_figures(raw_text)
    source_references = extract_references(raw_text, max_references=max_references)
    metadata = paper_metadata(paper_row, artifact)
    hints = source_hints(
        {
            **metadata,
            "source_family": paper_row.get("source_family", ""),
            "prompt_profile": paper_row.get("prompt_profile", ""),
            "prompt_profiles": paper_row.get("prompt_profiles", ""),
        }
    )
    sections, section_profile_summary = select_sections_for_profile(
        source_sections,
        profile=packet_profile,
        hints=hints,
    )
    tables, figures, references, item_profile_summary = select_tables_figures_references_for_profile(
        source_tables,
        source_figures,
        source_references,
        profile=packet_profile,
        hints=hints,
    )
    chunks = build_llm_chunks(
        sections,
        max_chunk_chars=max_chunk_chars,
        overlap_chars=overlap_chars,
        max_chunks_per_paper=max_chunks_per_paper,
    )
    source_chunks = build_llm_chunks(
        source_sections,
        max_chunk_chars=max_chunk_chars,
        overlap_chars=overlap_chars,
        max_chunks_per_paper=0,
    )
    reconstructed_text = RECONSTRUCTED_TEXT_SEPARATOR.join(section.get("text", "") for section in source_sections)
    selected_reconstructed_text = RECONSTRUCTED_TEXT_SEPARATOR.join(section.get("text", "") for section in sections)
    sections_out = sections if include_section_text else [{k: v for k, v in section.items() if k != "text"} for section in sections]
    doi = normalize_doi(metadata.get("study_doi", "")) or normalize_doi(artifact.get("study_doi", ""))
    source_chunk_token_estimate = sum(int(chunk.get("token_estimate", 0) or 0) for chunk in source_chunks)
    chunk_token_estimate = sum(int(chunk.get("token_estimate", 0) or 0) for chunk in chunks)

    return {
        "schema_version": PACKET_SCHEMA_VERSION,
        "created_at_utc": now_utc(),
        "packet_id": f"{dataset}:{doi}",
        "packet_profile": packet_profile,
        "requested_packet_profile": requested_packet_profile,
        "dataset": dataset,
        "study_doi": doi,
        "paper_metadata": metadata,
        "candidate_contexts": compact_contexts(paper_row) if include_candidate_contexts else [],
        "source_hints": hints,
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
            "packet_profile": packet_profile,
            "requested_packet_profile": requested_packet_profile,
            "profile_summary": {
                **section_profile_summary,
                **item_profile_summary,
            },
            "source_section_count": len(source_sections),
            "section_count": len(sections),
            "source_chunk_count": len(source_chunks),
            "chunk_count": len(chunks),
            "source_table_count": len(source_tables),
            "table_count": len(tables),
            "source_figure_count": len(source_figures),
            "figure_count": len(figures),
            "source_reference_count": len(source_references),
            "reference_count": len(references),
            "source_reconstructed_char_count": len(reconstructed_text),
            "reconstructed_char_count": len(reconstructed_text),
            "selected_reconstructed_char_count": len(selected_reconstructed_text),
            "source_chunk_token_estimate": source_chunk_token_estimate,
            "chunk_token_estimate": chunk_token_estimate,
            "chunk_token_reduction_estimate": max(0, source_chunk_token_estimate - chunk_token_estimate),
        },
        "sections": sections_out,
        "tables": tables,
        "figures": figures,
        "references": references,
        "llm_chunks": chunks,
    }
