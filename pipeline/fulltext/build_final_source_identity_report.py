#!/usr/bin/env python3
"""Build final source-identity repair and manual-recovery reports.

The fixed reporting universe is the 8,885 artifacts present in the pre-repair
audit. Current artifacts are re-audited live. The script only writes reports;
it never changes artifacts, PDFs, extraction outputs, KG tables, or corpus
tables.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Iterable
from urllib.parse import quote

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.fulltext.audit_fulltext_source_identity import (  # noqa: E402
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_CANDIDATE_TABLE,
    DEFAULT_IDENTITY_REGISTRY,
    DEFAULT_METADATA_TABLE,
    DEFAULT_PDF_HASH_ATTESTATION_REGISTRY,
    audit_artifacts,
    load_identity_registry,
    load_pdf_hash_attestation_registry,
    metadata_map,
)
from pipeline.fulltext.source_identity import clean, normalize_doi, title_similarity  # noqa: E402


REPORT_DIR = ROOT / "outputs" / "source_identity_repair_20260710"
DEFAULT_PRE_AUDIT = REPORT_DIR / "pre_repair_audit_v2.csv"
DEFAULT_SPECIAL = REPORT_DIR / "source_identity_special_classes.csv"
DEFAULT_PMC_INVENTORY = REPORT_DIR / "pmc_identity_inventory.csv"
DEFAULT_PMCID_RESOLUTION = REPORT_DIR / "artifact_pmcid_resolution.csv"
DEFAULT_QUARANTINE_REPORT = REPORT_DIR / "artifact_quarantine_applied.json"
DEFAULT_STRICT_FRONT_QUARANTINE_REPORT = REPORT_DIR / "artifact_quarantine_strict_front_applied.json"
DEFAULT_RESIDUAL_QUARANTINE_REPORT = REPORT_DIR / "residual_pdf_quarantine_applied.json"
DEFAULT_PDF_REPAIR_REPORT = REPORT_DIR / "pdf_artifact_repair_applied.json"
DEFAULT_PDF_RESTORATION_REPORT = REPORT_DIR / "validated_pdf_restoration_applied.json"
DEFAULT_MANUAL_URLS = ROOT / "pipeline" / "fulltext" / "manual_pdf_source_identity_repairs.json"
DEFAULT_MANUAL_ACCESS_OVERRIDES = ROOT / "pipeline" / "fulltext" / "manual_fulltext_access_overrides.json"
DEFAULT_ROUTE_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes.parquet"
DEFAULT_ACTIVE_POINTER = ROOT / "data" / "processed" / "graph_payload_active.json"
DEFAULT_MANIFEST_CSV = REPORT_DIR / "final_source_identity_repair_manifest.csv"
DEFAULT_MANIFEST_JSON = DEFAULT_MANIFEST_CSV.with_suffix(".json")
DEFAULT_QUEUE_CSV = REPORT_DIR / "manual_download_queue_all.csv"
DEFAULT_QUEUE_JSON = DEFAULT_QUEUE_CSV.with_suffix(".json")
DEFAULT_PRIORITY_CSV = REPORT_DIR / "manual_download_queue_priority.csv"
DEFAULT_PRIORITY_JSON = DEFAULT_PRIORITY_CSV.with_suffix(".json")

JATS_REPORTS = [
    REPORT_DIR / "pmc_repair_applied.json",
    REPORT_DIR / "manual_jats_repair_applied.json",
    REPORT_DIR / "manual_10_2196_46281_applied.json",
]

ANCILLARY_URL_RE = re.compile(
    r"(?:supp(?:lement|lementary)?|supporting[_ -]?(?:information|material)|"
    r"appendix|checklist|figure[_ -]?\d|fig[_ -]?\d|treatment[_ -]?manual|"
    r"merit[_ -]?review|grant[_ -]?review|meeting[_ -]?minutes)",
    flags=re.IGNORECASE,
)
PMCID_RE = re.compile(r"PMC\d+", flags=re.IGNORECASE)


ACTION_TEXT = {
    "retained_verified_active_artifact": "Keep the active verified artifact; no source-identity repair is required.",
    "repaired_exact_jats_active": "Keep the active exact JATS replacement and its quarantined predecessor for audit history.",
    "repaired_validated_pdf_active": "Keep the active independently validated PDF conversion and its repair history.",
    "verified_curated_identifier_override": "Keep the active artifact under the corroborated curated identifier override.",
    "verified_curated_related_document": "Keep the active related/version DOI artifact under the corroborated registry relationship.",
    "verified_curated_correction_relationship": "Keep the requested correction record linked to its original DOI under the correction registry rule.",
    "verified_curated_pdf_hash": "Keep the active PDF because its exact file hash matches the curator-reviewed identity attestation; the attestation does not authorize replacement files.",
    "verified_pdf_front_title_validation": "Keep the active PDF because direct first-page title validation corroborates the requested document identity.",
    "verified_after_identity_reaudit": "Keep the active artifact; the final identity evaluator now verifies it although the pre-repair audit did not.",
    "excluded_prescreen_no_artifact_repair": "Do not reacquire this artifact; the canonical prescreen excludes the record from evidence extraction.",
    "abstract_only_no_fulltext_repair": "Keep the paper and its abstract-derived KG evidence; the active route uses the public abstract and requires no full-text artifact.",
    "not_retained_no_artifact_repair": "Do not reacquire this artifact while the record is not retained for extraction.",
    "manual_exact_item_from_proceedings": "Retain the search record, but acquire an item-specific PDF/JATS record or slice the exact DOI/title item from the proceedings container.",
    "manual_exact_nested_repository_item": "Acquire the DOI-bearing paper or chapter itself, not a repository wrapper, thesis, or neighboring nested document.",
    "manual_replace_wrong_or_ancillary_document": "Acquire the main requested record and reject supplements, checklists, manuals, review forms, or unrelated documents.",
    "manual_replace_known_wrong_pdf": "Replace the known wrong PDF with the independently identified exact article PDF.",
    "manual_resolve_ambiguous_document_identity": "Resolve the DOI/version relationship manually before accepting any replacement.",
    "manual_benign_relation_needs_front_title_proof": "The relationship may be benign, but current front-title evidence is insufficient; obtain independently verifiable title/DOI evidence.",
    "manual_main_article_not_correction": "Acquire the requested main article; do not accept its correction, corrigendum, or erratum as a substitute.",
    "manual_identity_mismatch": "Acquire a replacement because the quarantined artifact belongs to a different document.",
    "manual_identity_unverified": "Acquire an independently verifiable source because the prior artifact lacked sufficient document-level identity evidence.",
    "manual_conflicting_doi_needs_resolution": "Confirm a registered version/alias relationship or acquire the exact requested DOI; do not accept a merely similar title.",
    "manual_strict_front_identity_failure": "Acquire an exact item whose requested title and DOI are in the document front matter; a target title found only later in a multi-item document is not sufficient.",
    "manual_other_recovery": "Acquire and validate an exact replacement before restoring full-text availability.",
}

FULLTEXT_REPAIR_ROUTE_STATUSES = {
    "needs_pdf_download",
    "needs_pdf_conversion",
}
FULLTEXT_REPAIR_ROUTE_ACTIONS = {
    "download_pdf_then_extract",
    "convert_local_pdf_then_extract",
}


MANIFEST_COLUMNS = [
    "original_artifact_ordinal",
    "doi",
    "original_audit_doi",
    "title",
    "final_action_category",
    "final_action",
    "current_artifact_state",
    "current_identity_verified",
    "current_identity_status",
    "current_identity_basis",
    "current_backend",
    "current_artifact_path",
    "pre_identity_verified",
    "pre_identity_status",
    "pre_document_doi",
    "pre_document_title",
    "pre_backend",
    "special_classification",
    "pmc_identity_class",
    "quarantine_reasons",
    "repair_history",
    "repair_source_reports",
    "registry_applied",
    "registry_record_group",
    "registry_relationship_type",
    "pdf_front_title_validation_applied",
    "pdf_front_title_validation_score",
    "pdf_hash_attestation_applied",
    "pdf_hash_attestation_disposition",
    "source_family",
    "source_type",
    "paper_type",
    "publication_type",
    "study_year",
    "study_journal",
    "retained_for_extraction_candidate",
    "prescreen_retained_for_extraction_candidate",
    "repair_eligible",
    "repair_eligibility_reason",
    "relevance_flags",
    "kg_finding_count",
    "priority_eligible",
    "priority_tier",
    "priority_score",
    "priority_reason",
    "doi_landing_url",
    "verified_pmcid",
    "verified_pmc_landing_url",
    "curated_exact_pdf_urls",
    "candidate_urls_requiring_validation",
    "candidate_url_evidence_json",
    "curated_access_status",
    "curated_access_checked_at",
    "recommended_acquisition_route",
    "excluded_candidate_url_count",
    "excluded_candidate_url_reasons",
    "known_attempted_url_count",
    "acceptance_guidance",
    "manual_queue_reason",
    "quarantined_artifact_path",
    "quarantined_pdf_path",
]


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def csv_map(path: Path, key: str = "doi") -> dict[str, dict]:
    return {
        doi: row
        for row in csv_rows(path)
        if (doi := normalize_doi(row.get(key, "") or row.get("requested_doi", "")))
    }


def table_map(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {
        doi: row
        for row in pd.read_parquet(path).fillna("").to_dict("records")
        if (doi := normalize_doi(row.get("doi", "") or row.get("study_doi", "")))
    }


def aggregate_routes(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in pd.read_parquet(path).fillna("").to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        if doi:
            grouped[doi].append(row)
    out: dict[str, dict] = {}
    for doi, rows in grouped.items():
        out[doi] = {
            "source_family": next((clean(row.get("source_family", "")) for row in rows if clean(row.get("source_family", ""))), ""),
            "source_type": next((clean(row.get("source_type", "")) for row in rows if clean(row.get("source_type", ""))), ""),
            "domain_routes": " | ".join(sorted({clean(row.get("domain_route", "")) for row in rows if clean(row.get("domain_route", ""))})),
            "route_actions": " | ".join(sorted({clean(row.get("route_action", "")) for row in rows if clean(row.get("route_action", ""))})),
            "best_pdf_url": next((clean(row.get("best_pdf_url", "")) for row in rows if clean(row.get("best_pdf_url", ""))), ""),
            "pdf_url_candidates": " | ".join(
                clean(row.get("pdf_url_candidates", ""))
                for row in rows
                if clean(row.get("pdf_url_candidates", ""))
            ),
            "probable_pdf_url_candidates": " | ".join(
                clean(row.get("probable_pdf_url_candidates", ""))
                for row in rows
                if clean(row.get("probable_pdf_url_candidates", ""))
            ),
        }
    return out


def bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).casefold() in {"1", "true", "yes"}


def fulltext_repair_requirement(candidate: dict, route: dict) -> tuple[bool, str]:
    """Return whether the active extraction route actually needs article text."""

    status = clean(candidate.get("extraction_route_status", "")).casefold()
    actions = {
        value.strip().casefold()
        for value in clean(route.get("route_actions", "")).split("|")
        if value.strip()
    }
    if status in FULLTEXT_REPAIR_ROUTE_STATUSES or actions & FULLTEXT_REPAIR_ROUTE_ACTIONS:
        return True, "active extraction route requires a public full-text artifact"
    if status == "ready_for_abstract_extraction" or actions == {"extract_from_abstract_only"}:
        return False, "active extraction route uses the public abstract; no full-text artifact is required"
    return False, "active extraction route does not request full-text acquisition or conversion"


def int_value(value: object) -> int:
    try:
        return int(float(clean(value) or 0))
    except ValueError:
        return 0


def split_urls(value: object) -> list[str]:
    if isinstance(value, list):
        return [clean(item) for item in value if clean(item)]
    text = clean(value)
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [clean(item) for item in parsed if clean(item)]
    return [part.strip() for part in re.split(r"\s*\|\s*", text) if part.strip()]


def manual_url_map(path: Path) -> dict[str, list[str]]:
    payload = load_json(path)
    out: dict[str, list[str]] = {}
    if not isinstance(payload, list):
        return out
    for row in payload:
        if not isinstance(row, dict):
            continue
        doi = normalize_doi(row.get("doi", ""))
        urls = split_urls(row.get("urls", []))
        if doi and urls:
            out[doi] = urls
    return out


def report_records(path: Path) -> list[dict]:
    payload = load_json(path)
    return payload.get("records", []) if isinstance(payload, dict) else []


def reconcile_original_doi(
    original_doi: str,
    title: str,
    current_dois: set[str],
    candidate_rows: dict[str, dict],
) -> str:
    if original_doi in current_dois or original_doi in candidate_rows:
        return original_doi
    # The pre-repair audit used the historical DOI regex that truncated Wiley
    # SICI identifiers at ``<...>``. Reconcile only a unique prefix-and-title
    # match; never guess across ordinary DOI differences.
    if "(sici)" in original_doi.casefold():
        matches = [
            doi
            for doi, row in candidate_rows.items()
            if doi.startswith(original_doi + "<")
            and (title_similarity(title, row.get("study_title", "")) or 0) >= 0.9
        ]
        current_matches = [doi for doi in matches if doi in current_dois]
        if len(current_matches) == 1:
            return current_matches[0]
        if len(matches) == 1:
            return matches[0]
    return original_doi


def active_kg_finding_counts(pointer_path: Path) -> tuple[Counter[str], str]:
    pointer = load_json(pointer_path)
    if not isinstance(pointer, dict) or not clean(pointer.get("kg_dir", "")):
        return Counter(), ""
    kg_dir = (ROOT / clean(pointer["kg_dir"])).resolve()
    findings_path = kg_dir / "findings.parquet"
    if not findings_path.exists():
        return Counter(), str(findings_path)
    frame = pd.read_parquet(findings_path, columns=["study_doi"]).fillna("")
    counts = Counter(
        doi
        for value in frame["study_doi"]
        if (doi := normalize_doi(value))
    )
    return counts, str(findings_path)


def repair_history_maps(
    pdf_repair_path: Path,
    restoration_path: Path,
    residual_path: Path,
) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, dict[str, str]], set[str], set[str]]:
    history: dict[str, list[str]] = defaultdict(list)
    sources: dict[str, list[str]] = defaultdict(list)
    attempted: dict[str, dict[str, str]] = defaultdict(dict)
    jats_replaced: set[str] = set()
    pdf_replaced: set[str] = set()
    for path in JATS_REPORTS:
        for row in report_records(path):
            doi = normalize_doi(row.get("doi", ""))
            if not doi or clean(row.get("status", "")) != "replaced":
                continue
            jats_replaced.add(doi)
            history[doi].append(f"exact_jats_replaced:{clean(row.get('method', ''))}")
            sources[doi].append(path.name)
    for row in report_records(pdf_repair_path):
        doi = normalize_doi(row.get("doi", ""))
        if not doi:
            continue
        sources[doi].append(pdf_repair_path.name)
        status = clean(row.get("status", ""))
        if status == "replaced_validated_pdf":
            pdf_replaced.add(doi)
            history[doi].append("validated_pdf_replaced")
        else:
            history[doi].append("automated_pdf_repair_not_successful")
        for attempt in row.get("attempts", []) or []:
            if not isinstance(attempt, dict):
                continue
            url = clean(attempt.get("url", ""))
            if not url:
                continue
            reason = clean(attempt.get("error", "")) or clean(
                (attempt.get("validation") or {}).get("reason", "")
            ) or clean(attempt.get("status", ""))
            attempted[doi][url] = reason
    for row in report_records(restoration_path):
        doi = normalize_doi(row.get("doi", ""))
        if doi and clean(row.get("status", "")) == "restored":
            history[doi].append("validated_pdf_restored_during_repair_sequence")
            sources[doi].append(restoration_path.name)
    for row in report_records(residual_path):
        doi = normalize_doi(row.get("doi", ""))
        if doi and clean(row.get("status", "")) == "moved":
            if "residual_pdf_quarantined" not in history[doi]:
                history[doi].append("residual_pdf_quarantined")
            sources[doi].append(residual_path.name)
    return history, sources, attempted, jats_replaced, pdf_replaced


def safe_candidate_urls(
    doi: str,
    verified_pmcid: str,
    rows: Iterable[tuple[str, dict]],
    known_attempts: dict[str, str],
) -> tuple[list[dict], Counter[str]]:
    candidates: list[dict] = []
    seen: set[str] = set()
    excluded: Counter[str] = Counter()
    fields = (
        "best_pdf_url",
        "pdf_url_candidates",
        "probable_pdf_url_candidates",
        "open_access_url",
    )
    for source, row in rows:
        for field in fields:
            for url in split_urls(row.get(field, "")):
                if url in seen:
                    continue
                seen.add(url)
                lowered = url.casefold()
                reason = ""
                if not lowered.startswith(("http://", "https://")):
                    reason = "not_http"
                elif url in known_attempts:
                    reason = f"known_attempt:{known_attempts[url]}"
                elif ANCILLARY_URL_RE.search(lowered):
                    reason = "ancillary_url_pattern"
                else:
                    url_pmcids = {match.upper() for match in PMCID_RE.findall(url)}
                    if url_pmcids and (not verified_pmcid or url_pmcids != {verified_pmcid.upper()}):
                        reason = "unverified_or_stale_pmcid"
                if reason:
                    excluded[reason] += 1
                    continue
                candidates.append({"url": url, "source": f"{source}.{field}"})
    return candidates[:8], excluded


def manual_action_category(special_class: str, quarantine_reasons: list[str]) -> str:
    if special_class == "proceedings_container":
        return "manual_exact_item_from_proceedings"
    if special_class == "repository_or_nested_document":
        return "manual_exact_nested_repository_item"
    if special_class == "no_header_wrong_or_ancillary":
        return "manual_replace_wrong_or_ancillary_document"
    if special_class == "manual_wrong_pdf":
        return "manual_replace_known_wrong_pdf"
    if special_class == "ambiguous_non_pmc_conflict":
        return "manual_resolve_ambiguous_document_identity"
    if special_class == "benign_conflict":
        return "manual_benign_relation_needs_front_title_proof"
    if "main_article_points_to_correction" in quarantine_reasons:
        return "manual_main_article_not_correction"
    if "identity_mismatch" in quarantine_reasons:
        return "manual_identity_mismatch"
    if "identity_unverified" in quarantine_reasons:
        return "manual_identity_unverified"
    if "target_text_with_conflicting_doi" in quarantine_reasons:
        return "manual_conflicting_doi_needs_resolution"
    return "manual_other_recovery"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_set_fingerprint(path: Path) -> dict[str, object]:
    """Return a content-based, path-sensitive fingerprint of the live artifacts."""

    digest = hashlib.sha256()
    count = 0
    total_bytes = 0
    for artifact in sorted(path.glob("*.json"), key=lambda item: item.name):
        file_hash = sha256_file(artifact)
        size = artifact.stat().st_size
        digest.update(artifact.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
        count += 1
        total_bytes += size
    return {
        "algorithm": "sha256(relative_filename + NUL + file_sha256 + newline)",
        "sha256": digest.hexdigest(),
        "file_count": count,
        "total_bytes": total_bytes,
    }


def input_file_fingerprints(paths: Iterable[Path]) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for path in paths:
        resolved = path.resolve()
        if not resolved.exists() or not resolved.is_file():
            continue
        out[str(resolved)] = {
            "sha256": sha256_file(resolved),
            "size_bytes": resolved.stat().st_size,
        }
    return out


def priority_fields(candidate: dict, kg_count: int) -> tuple[bool, str, int, str, str]:
    retained = bool_value(candidate.get("retained_for_extraction_candidate", False))
    flag_names = [
        "flag_in_curated_claims",
        "flag_in_claim_stubs",
        "flag_in_known_study_set",
    ]
    true_flags = [name for name in flag_names if bool_value(candidate.get(name, False))]
    if not retained:
        reasons = ["not currently retained_for_extraction_candidate"]
        if kg_count:
            reasons.append(f"{kg_count} stale active KG findings require downstream rebuild, not PDF reacquisition")
        reasons.extend(true_flags)
        return False, "not_in_priority_queue", 0, " | ".join(reasons), " | ".join(true_flags)
    eligible = retained or kg_count > 0 or bool(true_flags)
    if kg_count > 0 and retained:
        tier = "P0_existing_kg_and_retained"
    elif kg_count > 0 or true_flags:
        tier = "P1_existing_kg_or_curated_signal"
    elif retained:
        tier = "P2_retained_candidate"
    else:
        tier = "not_in_priority_queue"
    score = (
        (1000 if kg_count > 0 else 0)
        + min(kg_count, 200)
        + (300 if retained else 0)
        + (120 if "flag_in_curated_claims" in true_flags else 0)
        + (80 if "flag_in_claim_stubs" in true_flags else 0)
        + (60 if "flag_in_known_study_set" in true_flags else 0)
    )
    reasons = []
    if kg_count:
        reasons.append(f"{kg_count} active KG findings")
    if retained:
        reasons.append("retained_for_extraction_candidate")
    reasons.extend(true_flags)
    return eligible, tier, score, " | ".join(reasons), " | ".join(true_flags)


def acceptance_guidance(category: str, title: str) -> str:
    specific = ACTION_TEXT.get(category, ACTION_TEXT["manual_other_recovery"])
    if not category.startswith("manual_"):
        return specific
    short_title = len(re.findall(r"[A-Za-z0-9]+", title)) < 5
    title_rule = (
        "Because the title is short, require both an exact DOI and a front-page title match."
        if short_title
        else "Require an exact requested DOI in document metadata/front matter and a normalized front-title match or title similarity >=0.90."
    )
    return (
        f"{specific} {title_rule} Reject supplements, appendices, checklists, manuals, neighboring items, "
        "and whole containers unless the exact item is sliced. After import/conversion, accept only when the "
        "source-identity audit returns identity_verified=true; a curated registry relationship may substitute "
        "for exact DOI only when its recorded DOI and front-title gate both pass."
    )


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pre-audit", default=str(DEFAULT_PRE_AUDIT))
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--route-table", default=str(DEFAULT_ROUTE_TABLE))
    parser.add_argument("--identity-registry", default=str(DEFAULT_IDENTITY_REGISTRY))
    parser.add_argument(
        "--pdf-hash-attestation-registry",
        default=str(DEFAULT_PDF_HASH_ATTESTATION_REGISTRY),
    )
    parser.add_argument("--special-classes", default=str(DEFAULT_SPECIAL))
    parser.add_argument("--pmc-inventory", default=str(DEFAULT_PMC_INVENTORY))
    parser.add_argument("--pmcid-resolution", default=str(DEFAULT_PMCID_RESOLUTION))
    parser.add_argument("--quarantine-report", default=str(DEFAULT_QUARANTINE_REPORT))
    parser.add_argument(
        "--strict-front-quarantine-report",
        default=str(DEFAULT_STRICT_FRONT_QUARANTINE_REPORT),
    )
    parser.add_argument("--residual-quarantine-report", default=str(DEFAULT_RESIDUAL_QUARANTINE_REPORT))
    parser.add_argument("--pdf-repair-report", default=str(DEFAULT_PDF_REPAIR_REPORT))
    parser.add_argument("--pdf-restoration-report", default=str(DEFAULT_PDF_RESTORATION_REPORT))
    parser.add_argument("--manual-urls", default=str(DEFAULT_MANUAL_URLS))
    parser.add_argument("--manual-access-overrides", default=str(DEFAULT_MANUAL_ACCESS_OVERRIDES))
    parser.add_argument("--active-pointer", default=str(DEFAULT_ACTIVE_POINTER))
    parser.add_argument("--manifest-csv", default=str(DEFAULT_MANIFEST_CSV))
    parser.add_argument("--manifest-json", default=str(DEFAULT_MANIFEST_JSON))
    parser.add_argument("--queue-csv", default=str(DEFAULT_QUEUE_CSV))
    parser.add_argument("--queue-json", default=str(DEFAULT_QUEUE_JSON))
    parser.add_argument("--priority-csv", default=str(DEFAULT_PRIORITY_CSV))
    parser.add_argument("--priority-json", default=str(DEFAULT_PRIORITY_JSON))
    args = parser.parse_args()

    pre_rows = csv_rows(Path(args.pre_audit).resolve())
    if len(pre_rows) != 8885:
        raise ValueError(f"Expected fixed 8,885-row original audit universe, found {len(pre_rows)}")
    candidates = table_map(Path(args.candidate_table).resolve())
    metadata = table_map(Path(args.metadata_table).resolve())
    routes = aggregate_routes(Path(args.route_table).resolve())
    registry = load_identity_registry(Path(args.identity_registry).resolve())
    pdf_hash_registry = load_pdf_hash_attestation_registry(
        Path(args.pdf_hash_attestation_registry).resolve()
    )
    artifact_dir = Path(args.artifact_dir).resolve()
    artifact_snapshot_before = artifact_set_fingerprint(artifact_dir)
    current_report = audit_artifacts(
        artifact_dir,
        metadata_map(Path(args.metadata_table).resolve(), Path(args.candidate_table).resolve()),
        identity_registry=registry,
        pdf_hash_registry=pdf_hash_registry,
    )
    current = {row["requested_doi"]: row for row in current_report["rows"]}
    current_dois = set(current)
    special = csv_map(Path(args.special_classes).resolve())
    pmc_inventory = csv_map(Path(args.pmc_inventory).resolve())
    pmcid_resolution = csv_map(Path(args.pmcid_resolution).resolve())
    quarantine_records: dict[str, dict] = {}
    quarantine_report_names: dict[str, list[str]] = defaultdict(list)
    strict_front_dois: set[str] = set()
    for quarantine_path, is_strict_front in [
        (Path(args.quarantine_report).resolve(), False),
        (Path(args.strict_front_quarantine_report).resolve(), True),
    ]:
        quarantine_payload = load_json(quarantine_path)
        for quarantine_row in (
            quarantine_payload.get("records", []) if isinstance(quarantine_payload, dict) else []
        ):
            doi = normalize_doi(quarantine_row.get("doi", ""))
            if not doi:
                continue
            quarantine_records[doi] = quarantine_row
            quarantine_report_names[doi].append(quarantine_path.name)
            if is_strict_front:
                strict_front_dois.add(doi)
    manual_urls = manual_url_map(Path(args.manual_urls).resolve())
    access_payload = load_json(Path(args.manual_access_overrides).resolve())
    access_overrides = {
        normalize_doi(record.get("doi", "")): record
        for record in (
            access_payload.get("records", []) if isinstance(access_payload, dict) else []
        )
        if normalize_doi(record.get("doi", ""))
    }
    history, repair_sources, attempts, jats_replaced, pdf_replaced = repair_history_maps(
        Path(args.pdf_repair_report).resolve(),
        Path(args.pdf_restoration_report).resolve(),
        Path(args.residual_quarantine_report).resolve(),
    )
    kg_counts, kg_findings_path = active_kg_finding_counts(Path(args.active_pointer).resolve())

    manifest: list[dict] = []
    for ordinal, pre in enumerate(pre_rows, start=1):
        original_doi = clean(pre.get("requested_doi", ""))
        canonical_doi = reconcile_original_doi(
            original_doi,
            clean(pre.get("requested_title", "")),
            current_dois,
            candidates,
        )
        candidate = candidates.get(canonical_doi, {})
        meta = metadata.get(canonical_doi, {})
        route = routes.get(canonical_doi, {})
        final = current.get(canonical_doi)
        special_row = special.get(canonical_doi, {})
        pmc_row = pmc_inventory.get(canonical_doi, {})
        pmcid_row = pmcid_resolution.get(canonical_doi, {})
        quarantine = quarantine_records.get(canonical_doi, {})
        title = clean(
            candidate.get("study_title", "")
            or meta.get("study_title", "")
            or pre.get("requested_title", "")
        )
        quarantine_reasons = [clean(value) for value in quarantine.get("reasons", []) if clean(value)]
        if final and not bool(final.get("identity_verified")):
            current_failure = clean(final.get("identity_status", ""))
            if current_failure and current_failure not in quarantine_reasons:
                quarantine_reasons.append(current_failure)
        if final and bool(final.get("identity_verified")):
            if canonical_doi in jats_replaced:
                action_category = "repaired_exact_jats_active"
            elif bool(final.get("pdf_hash_attestation_applied")):
                action_category = "verified_curated_pdf_hash"
            elif bool(final.get("pdf_front_title_validation_applied")):
                action_category = "verified_pdf_front_title_validation"
            elif canonical_doi in pdf_replaced:
                action_category = "repaired_validated_pdf_active"
            elif bool(final.get("registry_applied")):
                registry_action = clean(final.get("registry_identity_action", ""))
                if registry_action == "ignore_incorrect_extracted_document_doi":
                    action_category = "verified_curated_identifier_override"
                elif registry_action == "accept_correction_original_doi":
                    action_category = "verified_curated_correction_relationship"
                else:
                    action_category = "verified_curated_related_document"
            elif not bool_value(pre.get("identity_verified", False)):
                action_category = "verified_after_identity_reaudit"
            else:
                action_category = "retained_verified_active_artifact"
            current_state = "active_verified"
        else:
            if canonical_doi in strict_front_dois:
                action_category = "manual_strict_front_identity_failure"
            else:
                action_category = manual_action_category(
                    clean(special_row.get("classification", "")),
                    quarantine_reasons,
                )
            current_state = "active_unverified" if final else "quarantined_no_active_artifact"

        verified_pmcid = ""
        if clean(pmcid_row.get("mapping_status", "")) == "pmcid_verified":
            verified_pmcid = clean(pmcid_row.get("verified_pmcid", "")).upper()
        candidate_url_rows = [
            ("candidate", candidate),
            ("metadata", meta),
            ("route", route),
        ]
        url_records, excluded_urls = safe_candidate_urls(
            canonical_doi,
            verified_pmcid,
            candidate_url_rows,
            attempts.get(canonical_doi, {}),
        )
        kg_count = int(kg_counts.get(canonical_doi, 0))
        access_override = access_overrides.get(canonical_doi, {})
        curated_access_status = clean(access_override.get("access_status", ""))
        if (
            not curated_access_status
            and clean(access_override.get("manual_access_action", ""))
            in {"suppress_pdf_download", "abstract_only"}
        ):
            curated_access_status = "no_verified_public_full_text"
        retained_for_extraction = bool_value(candidate.get("retained_for_extraction_candidate", False))
        fulltext_required, fulltext_requirement_reason = fulltext_repair_requirement(candidate, route)
        repair_eligible = retained_for_extraction and fulltext_required
        if not repair_eligible:
            recommended_acquisition_route = "none_active_route_does_not_require_full_text"
        elif url_records:
            recommended_acquisition_route = "automated_url_validation"
        else:
            recommended_acquisition_route = "public_source_discovery"
        prescreen_retained = bool_value(
            candidate.get("prescreen_retained_for_extraction_candidate", False)
        )
        if not bool(final and final.get("identity_verified")) and not repair_eligible:
            if clean(candidate.get("prescreen_decisions", "")).lower() == "exclude" or not prescreen_retained:
                action_category = "excluded_prescreen_no_artifact_repair"
                repair_eligibility_reason = "canonical prescreen excludes this record"
            elif retained_for_extraction and not fulltext_required:
                action_category = "abstract_only_no_fulltext_repair"
                repair_eligibility_reason = fulltext_requirement_reason
            else:
                action_category = "not_retained_no_artifact_repair"
                repair_eligibility_reason = "record is not currently retained after downstream screening/routing"
        else:
            repair_eligibility_reason = (
                fulltext_requirement_reason
                if repair_eligible
                else "active verified artifact requires no reacquisition"
            )
        priority_eligible, priority_tier, priority_score, priority_reason, relevance_flags = priority_fields(
            candidate,
            kg_count,
        )
        publication_type = clean(
            candidate.get("publication_type", "") or meta.get("publication_type", "")
        )
        source_family = clean(
            candidate.get("literature_source_family", "") or route.get("source_family", "")
        ) or "unknown"
        source_type = clean(
            candidate.get("literature_source_type", "")
            or route.get("source_type", "")
            or publication_type
        ) or "unknown"
        paper_type = clean(
            candidate.get("primary_secondary_source_type", "")
            or candidate.get("literature_source_type", "")
            or route.get("source_type", "")
            or publication_type
        ) or "unknown"
        row = {
            "original_artifact_ordinal": ordinal,
            "doi": canonical_doi,
            "original_audit_doi": original_doi,
            "title": title,
            "final_action_category": action_category,
            "final_action": ACTION_TEXT[action_category],
            "current_artifact_state": current_state,
            "current_identity_verified": bool(final and final.get("identity_verified")),
            "current_identity_status": clean((final or {}).get("identity_status", "")),
            "current_identity_basis": clean((final or {}).get("identity_basis", "")),
            "current_backend": clean((final or {}).get("best_backend", "")),
            "current_artifact_path": clean((final or {}).get("artifact_path", "")),
            "pre_identity_verified": bool_value(pre.get("identity_verified", False)),
            "pre_identity_status": clean(pre.get("identity_status", "")),
            "pre_document_doi": normalize_doi(pre.get("document_doi", "")),
            "pre_document_title": clean(pre.get("document_title", "")),
            "pre_backend": clean(pre.get("best_backend", "")),
            "special_classification": clean(special_row.get("classification", "")),
            "pmc_identity_class": clean(pmc_row.get("identity_class", "")),
            "quarantine_reasons": " | ".join(quarantine_reasons),
            "repair_history": " | ".join(dict.fromkeys(history.get(canonical_doi, []))),
            "repair_source_reports": " | ".join(
                dict.fromkeys(
                    repair_sources.get(canonical_doi, [])
                    + quarantine_report_names.get(canonical_doi, [])
                )
            ),
            "registry_applied": bool((final or {}).get("registry_applied", False)),
            "registry_record_group": clean((final or {}).get("registry_record_group", "")),
            "registry_relationship_type": clean((final or {}).get("registry_relationship_type", "")),
            "pdf_front_title_validation_applied": bool(
                (final or {}).get("pdf_front_title_validation_applied", False)
            ),
            "pdf_front_title_validation_score": (final or {}).get(
                "pdf_front_title_validation_score"
            ),
            "pdf_hash_attestation_applied": bool(
                (final or {}).get("pdf_hash_attestation_applied", False)
            ),
            "pdf_hash_attestation_disposition": clean(
                (final or {}).get("pdf_hash_attestation_disposition", "")
            ),
            "source_family": source_family,
            "source_type": source_type,
            "paper_type": paper_type,
            "publication_type": publication_type,
            "study_year": clean(candidate.get("study_year", "") or meta.get("study_year", "")),
            "study_journal": clean(candidate.get("study_journal", "") or meta.get("study_journal", "")),
            "retained_for_extraction_candidate": retained_for_extraction,
            "prescreen_retained_for_extraction_candidate": prescreen_retained,
            "repair_eligible": repair_eligible,
            "repair_eligibility_reason": repair_eligibility_reason,
            "relevance_flags": relevance_flags,
            "kg_finding_count": kg_count,
            "priority_eligible": priority_eligible,
            "priority_tier": priority_tier,
            "priority_score": priority_score,
            "priority_reason": priority_reason,
            "doi_landing_url": f"https://doi.org/{quote(canonical_doi, safe='/:;()._-')}",
            "verified_pmcid": verified_pmcid,
            "verified_pmc_landing_url": (
                f"https://pmc.ncbi.nlm.nih.gov/articles/{verified_pmcid}/" if verified_pmcid else ""
            ),
            "curated_exact_pdf_urls": " | ".join(manual_urls.get(canonical_doi, [])),
            "candidate_urls_requiring_validation": " | ".join(item["url"] for item in url_records),
            "candidate_url_evidence_json": json.dumps(url_records, ensure_ascii=False),
            "curated_access_status": curated_access_status,
            "curated_access_checked_at": clean(access_override.get("checked_at", "")),
            "recommended_acquisition_route": recommended_acquisition_route,
            "excluded_candidate_url_count": sum(excluded_urls.values()),
            "excluded_candidate_url_reasons": " | ".join(
                f"{reason}:{count}" for reason, count in sorted(excluded_urls.items())
            ),
            "known_attempted_url_count": len(attempts.get(canonical_doi, {})),
            "acceptance_guidance": acceptance_guidance(action_category, title),
            "manual_queue_reason": ACTION_TEXT[action_category] if action_category.startswith("manual_") else "",
            "quarantined_artifact_path": clean(quarantine.get("quarantined_artifact_path", "")),
            "quarantined_pdf_path": clean(quarantine.get("quarantined_pdf_path", "")),
        }
        manifest.append(row)

    if len(manifest) != 8885 or len({row["doi"] for row in manifest}) != 8885:
        raise ValueError("Final manifest must contain exactly 8,885 unique reconciled artifact DOIs")
    manual_queue = [
        row
        for row in manifest
        if not row["current_identity_verified"] and row["repair_eligible"]
    ]
    priority_queue = [row for row in manual_queue if row["priority_eligible"]]
    tier_order = {
        "P0_existing_kg_and_retained": 0,
        "P1_existing_kg_or_curated_signal": 1,
        "P2_retained_candidate": 2,
    }
    manual_queue.sort(key=lambda row: (row["final_action_category"], row["doi"]))
    priority_queue.sort(
        key=lambda row: (
            tier_order.get(row["priority_tier"], 9),
            -int_value(row["priority_score"]),
            -int_value(row["kg_finding_count"]),
            row["doi"],
        )
    )

    current_verified = sum(bool(row["current_identity_verified"]) for row in manifest)
    current_active = sum(row["current_artifact_state"].startswith("active_") for row in manifest)
    current_active_unverified = sum(row["current_artifact_state"] == "active_unverified" for row in manifest)
    no_active_artifact = sum(
        row["current_artifact_state"] == "quarantined_no_active_artifact" for row in manifest
    )
    current_unverified = sum(not bool(row["current_identity_verified"]) for row in manifest)
    deferred_no_repair = current_unverified - len(manual_queue)
    if current_verified + current_unverified != 8885:
        raise ValueError("Active verified plus current unverified does not cover original universe")
    if any(not row["current_identity_verified"] for row in manifest if row["current_artifact_state"] == "active_verified"):
        raise ValueError("Active-verified state contains an unverified row")
    if not set(row["doi"] for row in priority_queue).issubset({row["doi"] for row in manual_queue}):
        raise ValueError("Priority queue is not a subset of the full manual queue")

    generated_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "original_artifact_count": len(manifest),
        "current_active_artifact_count": current_active,
        "current_active_verified_count": current_verified,
        "current_active_unverified_count": current_active_unverified,
        "quarantined_no_active_artifact_count": no_active_artifact,
        "manual_download_queue_count": len(manual_queue),
        "unverified_not_repair_eligible_count": deferred_no_repair,
        "priority_queue_count": len(priority_queue),
        "action_category_counts": dict(Counter(row["final_action_category"] for row in manifest)),
        "manual_category_counts": dict(Counter(row["final_action_category"] for row in manual_queue)),
        "priority_tier_counts": dict(Counter(row["priority_tier"] for row in priority_queue)),
        "queue_source_family_counts": dict(Counter(row["source_family"] or "missing" for row in manual_queue)),
        "queue_paper_type_counts": dict(Counter(row["paper_type"] or "missing" for row in manual_queue)),
        "queue_with_candidate_url_count": sum(bool(row["candidate_urls_requiring_validation"]) for row in manual_queue),
        "queue_with_verified_pmcid_count": sum(bool(row["verified_pmcid"]) for row in manual_queue),
        "queue_with_curated_exact_url_count": sum(bool(row["curated_exact_pdf_urls"]) for row in manual_queue),
        "queue_active_kg_finding_count": sum(int_value(row["kg_finding_count"]) for row in manual_queue),
        "queue_active_kg_paper_count": sum(int_value(row["kg_finding_count"]) > 0 for row in manual_queue),
    }
    inputs = {
        "pre_repair_audit": str(Path(args.pre_audit).resolve()),
        "live_artifact_dir": str(Path(args.artifact_dir).resolve()),
        "identity_registry": str(Path(args.identity_registry).resolve()),
        "pdf_hash_attestation_registry": str(
            Path(args.pdf_hash_attestation_registry).resolve()
        ),
        "candidate_table": str(Path(args.candidate_table).resolve()),
        "metadata_table": str(Path(args.metadata_table).resolve()),
        "route_table": str(Path(args.route_table).resolve()),
        "active_kg_findings": kg_findings_path,
    }
    input_paths = [
        Path(args.pre_audit),
        Path(args.candidate_table),
        Path(args.metadata_table),
        Path(args.route_table),
        Path(args.identity_registry),
        Path(args.pdf_hash_attestation_registry),
        Path(args.special_classes),
        Path(args.pmc_inventory),
        Path(args.pmcid_resolution),
        Path(args.quarantine_report),
        Path(args.strict_front_quarantine_report),
        Path(args.residual_quarantine_report),
        Path(args.pdf_repair_report),
        Path(args.pdf_restoration_report),
        Path(args.manual_urls),
        Path(args.manual_access_overrides),
        Path(args.active_pointer),
        *JATS_REPORTS,
    ]
    if kg_findings_path:
        input_paths.append(Path(kg_findings_path))
    artifact_snapshot_after = artifact_set_fingerprint(artifact_dir)
    if artifact_snapshot_after != artifact_snapshot_before:
        raise RuntimeError("Live artifact set changed while the report was being built; rerun on a stable snapshot")
    if artifact_snapshot_after["file_count"] != len(current_report["rows"]):
        raise RuntimeError("Artifact fingerprint count does not match the audited artifact count")
    snapshot_fingerprints = {
        "input_files": input_file_fingerprints(input_paths),
        "live_artifact_set": artifact_snapshot_after,
    }
    common = {
        "generated_at_utc": generated_at,
        "schema_version": "source_identity_final_reporting_v1",
        "inputs": inputs,
        "snapshot_fingerprints": snapshot_fingerprints,
        "summary": summary,
        "priority_policy": (
            "Source reacquisition requires both current retained_for_extraction_candidate=true and an "
            "active extraction route that requires public full text. Abstract-only routes remain eligible "
            "for KG extraction but never enter the full-text repair queue. "
            "Within that eligible set, active KG findings and curated-claim/claim-stub/known-study flags "
            "raise priority. Stale KG findings never override a current exclusion."
        ),
        "url_policy": (
            "Candidate URLs exclude known attempted failures, ancillary filename patterns, and PMC URLs whose "
            "PMCID is not independently verified for the DOI. Every candidate still requires the row-specific "
            "front-page DOI/title acceptance test."
        ),
    }

    manifest_csv = Path(args.manifest_csv).resolve()
    manifest_json = Path(args.manifest_json).resolve()
    queue_csv = Path(args.queue_csv).resolve()
    queue_json = Path(args.queue_json).resolve()
    priority_csv = Path(args.priority_csv).resolve()
    priority_json = Path(args.priority_json).resolve()
    write_csv(manifest_csv, manifest)
    write_csv(queue_csv, manual_queue)
    write_csv(priority_csv, priority_queue)
    write_json(manifest_json, {**common, "report": "final_repair_manifest", "records": manifest})
    write_json(queue_json, {**common, "report": "full_manual_download_queue", "records": manual_queue})
    write_json(priority_json, {**common, "report": "priority_manual_download_queue", "records": priority_queue})
    print(
        json.dumps(
            {
                "outputs": [
                    str(manifest_csv),
                    str(manifest_json),
                    str(queue_csv),
                    str(queue_json),
                    str(priority_csv),
                    str(priority_json),
                ],
                "summary": summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
