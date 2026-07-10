#!/usr/bin/env python3
"""Build a paper-level source-identity review dataset for routed extraction outputs."""

from __future__ import annotations

import html
import json
import math
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent
RUN_DIR = ROOT / "data/processed/extraction/routed_runs/gemini3_flash_20260628_primary_extraction"
TASKS_PATH = ROOT / "data/processed/extraction/route_extraction_tasks.jsonl"
OUTPUTS_PATH = RUN_DIR / "route_extraction_outputs.jsonl"
ARTICLES_DIR = ROOT / "data/processed/fulltext/articles"
FINDINGS_PATH = ROOT / "data/processed/kg_routed_runs/gemini3_flash_20260628_primary_extraction/findings.parquet"

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "these", "those",
    "study", "studies", "paper", "article", "review", "effects", "effect", "using", "among",
    "between", "after", "before", "during", "through", "their", "there", "which", "were",
    "was", "are", "has", "have", "had", "its", "our", "but", "not", "than", "over", "under",
}

STRONG_WARNING_RE = re.compile(
    r"does not match|do not match|mismatch|unrelated|different (?:paper|study)|wrong source|"
    r"contradict(?:s|ed|ory)?|metadata title|entirely unrelated|completely unrelated|"
    r"appears to be from a different|different from the metadata",
    re.I,
)
CONTAINER_WARNING_RE = re.compile(
    r"multiple unrelated|two (?:distinct|different|unrelated)|collection of conference abstracts|"
    r"conference proceedings|abstract book|adjacent abstracts|different study abstracts|"
    r"fragments (?:from|of) multiple|multiple different stud|combined report|multiple speakers",
    re.I,
)


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def norm(value: object) -> str:
    return " ".join(str(value or "").split())


def normalize_doi(value: object) -> str:
    text = norm(value).lower()
    text = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", text)
    match = DOI_RE.search(text)
    if not match:
        return ""
    return match.group(0).rstrip(".,;:)]}").lower()


def doi_equivalent(a: object, b: object) -> bool:
    """Treat publisher punctuation variants and obvious parser suffixes as the same DOI."""
    aa, bb = normalize_doi(a), normalize_doi(b)
    if not aa or not bb:
        return False
    if aa == bb:
        return True
    compact_a = re.sub(r"[^a-z0-9]", "", aa)
    compact_b = re.sub(r"[^a-z0-9]", "", bb)
    if compact_a == compact_b:
        return True
    # Some malformed XML concatenates the next heading directly onto the DOI.
    shorter, longer = (compact_a, compact_b) if len(compact_a) <= len(compact_b) else (compact_b, compact_a)
    suffix = longer[len(shorter):] if longer.startswith(shorter) else ""
    return bool(suffix and suffix.isalpha())


def doi_slug(doi: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", doi.lower()).strip("_")


def strip_markup(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return norm(text)


def tokens(value: object) -> list[str]:
    words = re.findall(r"[a-z0-9]+", str(value or "").lower())
    return [word for word in words if len(word) > 2 and word not in STOPWORDS]


def title_similarity(a: object, b: object) -> float | None:
    aa, bb = norm(a), norm(b)
    if not aa or not bb:
        return None
    seq = SequenceMatcher(None, aa.casefold(), bb.casefold()).ratio()
    aset, bset = set(tokens(aa)), set(tokens(bb))
    jac = len(aset & bset) / len(aset | bset) if aset and bset else 0.0
    return round(max(seq, jac), 4)


def cosine_similarity(a: object, b: object) -> float | None:
    aa, bb = Counter(tokens(a)), Counter(tokens(b))
    if not aa or not bb:
        return None
    common = set(aa) & set(bb)
    numerator = sum(aa[key] * bb[key] for key in common)
    denom = math.sqrt(sum(value * value for value in aa.values())) * math.sqrt(
        sum(value * value for value in bb.values())
    )
    return round(numerator / denom, 4) if denom else None


def first_regex(text: str, patterns: list[tuple[str, str]]) -> tuple[str, str]:
    for label, pattern in patterns:
        match = re.search(pattern, text, re.I | re.S)
        if match:
            value = strip_markup(match.group(1))
            if value:
                return value, label
    return "", ""


def best_extraction(artifact: dict) -> dict:
    extractions = [row for row in artifact.get("extractions", []) if isinstance(row, dict)]
    ok = [row for row in extractions if norm(row.get("status")).casefold() == "ok"]
    candidates = ok or extractions
    if not candidates:
        return {}
    preferred_backend = norm(artifact.get("best_backend"))
    preferred = [row for row in candidates if norm(row.get("backend")) == preferred_backend]
    candidates = preferred or candidates
    return max(candidates, key=lambda row: int(row.get("char_count") or len(str(row.get("text") or ""))))


def header_identity(artifact: dict) -> dict:
    extraction = best_extraction(artifact)
    text = str(extraction.get("text") or "")
    metadata = extraction.get("metadata") if isinstance(extraction.get("metadata"), dict) else {}

    doi, doi_method = first_regex(
        text[:120000],
        [
            ("JATS article-id", r"<article-id\b[^>]*pub-id-type\s*=\s*['\"]doi['\"][^>]*>(.*?)</article-id>"),
            ("citation meta", r"<meta\b[^>]*(?:name|property)\s*=\s*['\"]citation_doi['\"][^>]*content\s*=\s*['\"]([^'\"]+)"),
        ],
    )
    # GROBID emits DOI idno elements for bibliography entries too. Only trust a DOI
    # found inside the TEI header, never the first DOI in the full document.
    if not doi and "<teiHeader" in text:
        tei_header = text.split("</teiHeader>", 1)[0]
        doi, doi_method = first_regex(
            tei_header,
            [("TEI header idno", r"<idno\b[^>]*type\s*=\s*['\"]doi['\"][^>]*>(.*?)</idno>")],
        )
    doi = normalize_doi(doi or metadata.get("doi") or metadata.get("document_doi"))
    if doi and not doi_method:
        doi_method = "extraction metadata"

    title, title_method = first_regex(
        text[:120000],
        [
            ("JATS article-title", r"<article-title\b[^>]*>(.*?)</article-title>"),
            ("TEI analytic title", r"<title\b(?=[^>]*(?:level\s*=\s*['\"]a['\"]|type\s*=\s*['\"]main['\"]))[^>]*>(.*?)</title>"),
            ("citation meta", r"<meta\b[^>]*(?:name|property)\s*=\s*['\"]citation_title['\"][^>]*content\s*=\s*['\"]([^'\"]+)"),
        ],
    )
    if not title:
        title = norm(metadata.get("title") or metadata.get("document_title"))
        if title:
            title_method = "extraction metadata"

    abstract, _ = first_regex(text[:250000], [("JATS abstract", r"<abstract\b[^>]*>(.*?)</abstract>")])
    if not abstract:
        for section in extraction.get("sections", []) or []:
            if isinstance(section, dict) and "abstract" in norm(section.get("heading")).casefold():
                abstract = norm(section.get("text") or section.get("snippet"))
                break

    pmid, _ = first_regex(
        text[:120000],
        [("JATS PMID", r"<article-id\b[^>]*pub-id-type\s*=\s*['\"]pmid['\"][^>]*>(.*?)</article-id>")],
    )
    pmcid, _ = first_regex(
        text[:120000],
        [("JATS PMCID", r"<article-id\b[^>]*pub-id-type\s*=\s*['\"]pmcid['\"][^>]*>(.*?)</article-id>")],
    )
    return {
        "artifact_header_doi": doi,
        "artifact_header_doi_method": doi_method,
        "artifact_header_title": title,
        "artifact_header_title_method": title_method,
        "artifact_abstract": abstract,
        "artifact_header_pmid": norm(pmid),
        "artifact_header_pmcid": norm(pmcid),
        "artifact_backend": norm(extraction.get("backend") or artifact.get("best_backend")),
        "artifact_char_count": int(extraction.get("char_count") or artifact.get("best_char_count") or 0),
    }


def warning_list(result: dict) -> list[str]:
    out: list[str] = []
    for key in ("warnings", "extraction_warnings"):
        values = result.get(key, [])
        if isinstance(values, list):
            out.extend(norm(value) for value in values if norm(value))
    return out


def item_count(result: dict) -> int:
    for key in ("items", "coverage_items", "synthesis_results"):
        values = result.get(key)
        if isinstance(values, list):
            return len(values)
    return 0


def main() -> None:
    tasks: dict[str, dict] = {}
    for row in read_jsonl(TASKS_PATH):
        task_id = norm(row.get("task_id"))
        if task_id:
            tasks[task_id] = row

    papers: dict[str, dict] = {}
    for output in read_jsonl(OUTPUTS_PATH):
        if norm(output.get("status")) != "ok":
            continue
        result = output.get("result") if isinstance(output.get("result"), dict) else {}
        if norm(result.get("text_depth")) != "article_text":
            continue
        doi = normalize_doi(result.get("study_doi"))
        if not doi:
            continue
        task_id = norm(result.get("task_id") or output.get("task_id"))
        task = tasks.get(task_id, {})
        metadata = task.get("paper_metadata") if isinstance(task.get("paper_metadata"), dict) else {}
        content = task.get("content") if isinstance(task.get("content"), dict) else {}
        route = task.get("route_context") if isinstance(task.get("route_context"), dict) else {}
        text_source = task.get("text_source") if isinstance(task.get("text_source"), dict) else {}
        record = papers.setdefault(
            doi,
            {
                "requested_doi": doi,
                "requested_title": norm(metadata.get("study_title") or content.get("title")),
                "requested_abstract": norm(metadata.get("abstract") or content.get("abstract")),
                "requested_year": norm(metadata.get("study_year")),
                "requested_authors": norm(metadata.get("authors")),
                "requested_journal": norm(metadata.get("study_journal")),
                "requested_pmid": norm(metadata.get("pmid")),
                "requested_pmcid": norm(metadata.get("pmcid")),
                "open_access_url": norm(metadata.get("open_access_url")),
                "source_families": set(),
                "domains": set(),
                "task_ids": set(),
                "extraction_statuses": set(),
                "warnings": set(),
                "route_basis_notes": set(),
                "artifact_paths": set(),
                "output_count": 0,
                "raw_item_count": 0,
            },
        )
        # Prefer populated metadata from any route for this DOI.
        for field, value in (
            ("requested_title", metadata.get("study_title") or content.get("title")),
            ("requested_abstract", metadata.get("abstract") or content.get("abstract")),
            ("requested_year", metadata.get("study_year")),
            ("requested_authors", metadata.get("authors")),
            ("requested_journal", metadata.get("study_journal")),
            ("requested_pmid", metadata.get("pmid")),
            ("requested_pmcid", metadata.get("pmcid")),
            ("open_access_url", metadata.get("open_access_url")),
        ):
            if not record.get(field) and norm(value):
                record[field] = norm(value)
        record["source_families"].add(norm(route.get("source_family") or result.get("paper_type") or "unknown"))
        record["domains"].add(norm(result.get("domain_route")))
        record["task_ids"].add(task_id)
        record["extraction_statuses"].add(norm(result.get("extraction_status")))
        record["warnings"].update(warning_list(result))
        route_basis = norm(route.get("route_basis"))
        if route_basis and STRONG_WARNING_RE.search(route_basis):
            record["route_basis_notes"].add(route_basis)
        for path in text_source.get("fulltext_artifact_paths", []) or []:
            if norm(path):
                record["artifact_paths"].add(norm(path))
        record["output_count"] += 1
        record["raw_item_count"] += item_count(result)

    findings: dict[str, dict] = defaultdict(lambda: {"count": 0, "relations": [], "domains": set()})
    if FINDINGS_PATH.exists():
        connection = duckdb.connect(database=":memory:")
        rows = connection.execute(
            "SELECT study_doi, domain, compound, entity_label FROM read_parquet(?)",
            [str(FINDINGS_PATH)],
        ).fetchall()
        for study_doi, domain, compound, entity_label in rows:
            doi = normalize_doi(study_doi)
            if not doi:
                continue
            finding = findings[doi]
            finding["count"] += 1
            if norm(domain):
                finding["domains"].add(norm(domain))
            relation = f"{norm(compound)} -> {norm(entity_label)}".strip(" ->")
            if relation and relation not in finding["relations"] and len(finding["relations"]) < 6:
                finding["relations"].append(relation)
        connection.close()

    candidates: list[dict] = []
    scan_stats = Counter()
    for doi, record in papers.items():
        paths = [Path(path) for path in sorted(record["artifact_paths"]) if Path(path).exists()]
        if not paths:
            fallback = ARTICLES_DIR / f"{doi_slug(doi)}.json"
            if fallback.exists():
                paths = [fallback]
        artifact_path = paths[0] if paths else Path("")
        artifact: dict = {}
        if artifact_path:
            try:
                artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                artifact = {}
        identity = header_identity(artifact) if artifact else {
            "artifact_header_doi": "", "artifact_header_doi_method": "", "artifact_header_title": "",
            "artifact_header_title_method": "", "artifact_abstract": "", "artifact_header_pmid": "",
            "artifact_header_pmcid": "", "artifact_backend": "", "artifact_char_count": 0,
        }
        task_title = record["requested_title"]
        task_abstract = record["requested_abstract"]
        header_doi = identity["artifact_header_doi"]
        title_sim = title_similarity(task_title, identity["artifact_header_title"])
        abstract_sim = cosine_similarity(task_abstract, identity["artifact_abstract"])
        header_mismatch = bool(header_doi and not doi_equivalent(header_doi, doi))
        warnings = sorted(record["warnings"])
        warning_text = " | ".join(warnings)
        strong_warning = bool(STRONG_WARNING_RE.search(warning_text))
        container_warning = bool(CONTAINER_WARNING_RE.search(warning_text))
        route_warning = bool(record["route_basis_notes"])
        dual_text_mismatch = bool(
            title_sim is not None and abstract_sim is not None and title_sim < 0.45 and abstract_sim < 0.18
        )

        scan_stats["article_text_papers"] += 1
        if header_doi:
            scan_stats["header_doi_recovered"] += 1
        if header_mismatch:
            scan_stats["header_doi_mismatch"] += 1
        if strong_warning:
            scan_stats["strong_warning"] += 1
        if container_warning:
            scan_stats["container_warning"] += 1
        if dual_text_mismatch:
            scan_stats["dual_text_mismatch"] += 1

        if not (header_mismatch or strong_warning or container_warning or route_warning or dual_text_mismatch):
            continue

        flags: list[str] = []
        if header_mismatch:
            flags.append("Artifact header DOI differs")
        if strong_warning:
            flags.append("Extraction warning indicates identity mismatch")
        if container_warning:
            flags.append("Merged/multi-study source warning")
        if route_warning:
            flags.append("Routing metadata notes a mismatch")
        if dual_text_mismatch:
            flags.append("Low task-vs-artifact title and abstract similarity")

        kg = findings.get(doi, {"count": 0, "relations": [], "domains": set()})
        kg_count = int(kg["count"])
        possible_version = bool(header_mismatch and title_sim is not None and title_sim >= 0.75 and not strong_warning)
        if (strong_warning or container_warning or route_warning or (header_mismatch and not possible_version)) and kg_count > 0:
            tier = "High"
        elif strong_warning or container_warning or route_warning or header_mismatch:
            tier = "Medium"
        else:
            tier = "Screening"

        if container_warning:
            action = "Identify the target article/abstract and rebuild a single-study packet if the source is mixed."
        elif possible_version:
            action = "Check whether this is a legitimate preprint/version DOI or a wrongly linked artifact."
        elif header_mismatch:
            action = "Verify the DOI/title against the artifact; quarantine and replace the artifact if confirmed."
        elif strong_warning or route_warning:
            action = "Inspect the supplied text and metadata; block or rebuild extraction if the warning is correct."
        else:
            action = "Compare the task abstract with the artifact abstract before deciding whether to retain it."

        candidates.append(
            {
                "priority": tier,
                "problem_type": " | ".join(flags),
                "requested_doi": doi,
                "requested_title": task_title,
                "requested_year": record["requested_year"],
                "requested_authors": record["requested_authors"],
                "requested_journal": record["requested_journal"],
                "requested_pmid": record["requested_pmid"],
                "requested_pmcid": record["requested_pmcid"],
                "requested_abstract_snippet": task_abstract[:900],
                "artifact_header_doi": header_doi,
                "artifact_header_title": identity["artifact_header_title"],
                "artifact_header_pmid": identity["artifact_header_pmid"],
                "artifact_header_pmcid": identity["artifact_header_pmcid"],
                "artifact_header_doi_method": identity["artifact_header_doi_method"],
                "artifact_header_title_method": identity["artifact_header_title_method"],
                "artifact_abstract_snippet": identity["artifact_abstract"][:900],
                "title_similarity": title_sim,
                "abstract_similarity": abstract_sim,
                "possible_version_alias": possible_version,
                "source_family": " | ".join(sorted(value for value in record["source_families"] if value)),
                "domains_extracted": " | ".join(sorted(value for value in record["domains"] if value)),
                "route_output_count": record["output_count"],
                "raw_extracted_item_count": record["raw_item_count"],
                "extraction_statuses": " | ".join(sorted(value for value in record["extraction_statuses"] if value)),
                "extraction_warnings": warning_text[:4000],
                "routing_mismatch_notes": " | ".join(sorted(record["route_basis_notes"]))[:2500],
                "artifact_backend": identity["artifact_backend"],
                "artifact_char_count": identity["artifact_char_count"],
                "artifact_path": str(artifact_path) if artifact_path else "",
                "open_access_url": record["open_access_url"],
                "current_kg_finding_count": kg_count,
                "current_kg_domains": " | ".join(sorted(kg["domains"])),
                "current_kg_relation_sample": " | ".join(kg["relations"]),
                "recommended_action": action,
                "manual_review_status": "Not reviewed",
                "manual_notes": "",
                "task_ids": " | ".join(sorted(value for value in record["task_ids"] if value)),
            }
        )

    tier_rank = {"High": 0, "Medium": 1, "Screening": 2}
    candidates.sort(
        key=lambda row: (
            tier_rank.get(row["priority"], 9),
            -int(row["current_kg_finding_count"]),
            row["requested_doi"],
        )
    )
    for index, row in enumerate(candidates, start=1):
        row["candidate_id"] = f"SRC-{index:04d}"

    summary = {
        "generated_date": "2026-07-09",
        "scope_note": "Article-text records used by the routed extraction run; candidates are not confirmed errors.",
        "scan_stats": dict(scan_stats),
        "candidate_count": len(candidates),
        "priority_counts": dict(Counter(row["priority"] for row in candidates)),
        "candidate_with_kg_findings": sum(1 for row in candidates if row["current_kg_finding_count"] > 0),
        "kg_findings_on_candidates": sum(row["current_kg_finding_count"] for row in candidates),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "source_identity_candidates.json").write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "source_identity_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
