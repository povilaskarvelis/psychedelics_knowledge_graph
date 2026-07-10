#!/usr/bin/env python3
"""Audit every canonical full-text artifact against document-level identity."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.fulltext.source_identity import (  # noqa: E402
    DEFAULT_PDF_HASH_ATTESTATION_REGISTRY,
    augment_pdf_artifact_identity,
    clean,
    evaluate_artifact_identity,
    load_pdf_hash_attestation_registry,
    normalize_doi,
    split_dois,
    strip_markup,
    title_similarity,
    title_tokens,
)


DEFAULT_ARTIFACT_DIR = ROOT / "data" / "processed" / "fulltext" / "articles"
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_METADATA_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"
DEFAULT_REPORT_JSON = ROOT / "data" / "processed" / "fulltext" / "source_identity_audit.json"
DEFAULT_REPORT_CSV = ROOT / "data" / "processed" / "fulltext" / "source_identity_audit.csv"
DEFAULT_UNVERIFIED_DOIS = ROOT / "data" / "processed" / "fulltext" / "source_identity_unverified_dois.txt"
DEFAULT_IDENTITY_REGISTRY = ROOT / "pipeline" / "fulltext" / "source_identity_registry.json"

REGISTRY_ACTIONS = {
    "accept_correction_original_doi",
    "accept_related_document_doi",
    "ignore_incorrect_extracted_document_doi",
    "no_override_required",
}
RELATIONSHIP_TYPES = {
    "article_version",
    "preprint_repository_version",
    "publisher_doi_alias",
    "publisher_language_alias",
}
IDENTIFIER_OVERRIDE_TYPES = {
    "doi_parse_truncation_or_suffix",
    "grobid_related_doi_misidentification",
}
CORRECTION_RELATIONSHIP_TYPE = "correction_record_to_original_doi"
REGISTRY_RECORD_GROUPS = {
    "benign_conflict",
    "correction_record",
    "pmc_valid_exact",
    "pmc_valid_known_alias",
}
CORRECTION_TITLE_RE = re.compile(
    r"(?:^(?:corrections?\s*(?:&|and)\s*amendments?\s+)?"
    r"(?:author\s+)?(?:correction|corrigendum|erratum)\b|"
    r"\b(?:correction|corrigendum|erratum)\s*\.?$)",
    flags=re.IGNORECASE,
)


def load_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def correction_title_signal(value: object) -> bool:
    return bool(CORRECTION_TITLE_RE.search(strip_markup(value).lstrip("'\"‘’“”")))


def correction_title_core(value: object) -> str:
    text = strip_markup(value).lstrip("'\"‘’“”")
    text = re.sub(
        r"^(?:corrections?\s*(?:&|and)\s*amendments?\s+)?"
        r"(?:author\s+)?(?:correction|corrigendum|erratum)"
        r"(?:\s+to)?\s*[:\-–—]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\s*[:\-–—]?\s*(?:correction|corrigendum|erratum)\s*\.?$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip("'\"‘’“” ")


def correction_title_similarity(left: object, right: object) -> float | None:
    left_core = correction_title_core(left)
    right_core = correction_title_core(right)
    similarity = title_similarity(left_core, right_core)
    left_tokens = set(title_tokens(left_core))
    right_tokens = set(title_tokens(right_core))
    shorter_containment = (
        len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
        if left_tokens and right_tokens
        else 0.0
    )
    return round(max(similarity or 0.0, shorter_containment), 4) if left_tokens and right_tokens else similarity


def artifact_has_full_article_body(artifact: dict) -> bool:
    """Detect full primary/review article bodies despite correction-like titles."""
    required_headings = {"abstract", "introduction", "results", "discussion"}
    for extraction in artifact.get("extractions", []) or []:
        if not isinstance(extraction, dict):
            continue
        try:
            char_count = int(extraction.get("char_count", 0) or 0)
            section_count = int(extraction.get("section_count", 0) or 0)
        except (TypeError, ValueError):
            char_count = section_count = 0
        headings = {
            strip_markup(section.get("heading", "")).casefold()
            for section in extraction.get("sections", []) or []
            if isinstance(section, dict)
        }
        normalized = {
            re.sub(r"[^a-z0-9]+", " ", heading).strip()
            for heading in headings
            if heading
        }
        if (
            char_count >= 15000
            and section_count >= 8
            and all(
                any(required in heading.split() or required == heading for heading in normalized)
                for required in required_headings
            )
        ):
            return True
    return False


def reject_correction_artifact_for_main_record(identity: dict, artifact: dict | None = None) -> dict:
    """Do not let a related-DOI rule substitute a correction for its article."""
    requested_title = clean(identity.get("requested_title", ""))
    document_title = clean(identity.get("document_title", ""))
    if correction_title_signal(requested_title) or not correction_title_signal(document_title):
        return identity
    if artifact is not None and artifact_has_full_article_body(artifact):
        result = dict(identity)
        result["correction_title_full_article_body_evidence"] = True
        return result
    result = dict(identity)
    result.update(
        {
            "status": "main_article_points_to_correction",
            "verified": False,
            "basis": (
                "requested record is a main article but the available document "
                "identifies itself as a correction, corrigendum, or erratum"
            ),
        }
    )
    return result


def load_identity_registry(path: Path) -> dict:
    """Load and validate the curated source-identity registry.

    Registry records are deliberately inert on their own.  The audit applies a
    record only when the artifact exposes the recorded document DOI *and* the
    target title is corroborated in document front matter.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError(f"Unsupported source-identity registry: {path}")
    policy = payload.get("acceptance_policy")
    if not isinstance(policy, dict):
        raise ValueError("Source-identity registry is missing acceptance_policy")
    minimum_title_similarity = float(policy.get("minimum_front_title_similarity", 0))
    if not 0.8 <= minimum_title_similarity <= 1.0:
        raise ValueError("minimum_front_title_similarity must be between 0.8 and 1.0")

    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise ValueError("Source-identity registry records must be a list")
    expected_count = int(payload.get("record_count", len(raw_records)))
    if expected_count != len(raw_records):
        raise ValueError(
            f"Source-identity registry count mismatch: declared={expected_count} actual={len(raw_records)}"
        )

    records: dict[str, dict] = {}
    for index, raw in enumerate(raw_records):
        if not isinstance(raw, dict):
            raise ValueError(f"Registry record {index} must be an object")
        requested = normalize_doi(raw.get("requested_doi", ""))
        observed = normalize_doi(raw.get("observed_document_doi", ""))
        relationship_type = clean(raw.get("relationship_type", ""))
        action = clean(raw.get("identity_action", ""))
        record_group = clean(raw.get("record_group", "benign_conflict"))
        if not requested or not observed:
            raise ValueError(f"Registry record {index} is missing a valid DOI pair")
        if requested in records:
            raise ValueError(f"Duplicate requested DOI in source-identity registry: {requested}")
        if action not in REGISTRY_ACTIONS:
            raise ValueError(f"Unsupported identity_action for {requested}: {action}")
        if action == "accept_related_document_doi" and relationship_type not in RELATIONSHIP_TYPES:
            raise ValueError(f"Unsupported document relationship for {requested}: {relationship_type}")
        if action == "accept_correction_original_doi" and relationship_type != CORRECTION_RELATIONSHIP_TYPE:
            raise ValueError(f"Unsupported correction relationship for {requested}: {relationship_type}")
        if action == "ignore_incorrect_extracted_document_doi" and relationship_type not in IDENTIFIER_OVERRIDE_TYPES:
            raise ValueError(f"Unsupported identifier override for {requested}: {relationship_type}")
        if record_group not in REGISTRY_RECORD_GROUPS:
            raise ValueError(f"Unsupported registry record_group for {requested}: {record_group}")
        if action == "no_override_required" and requested != observed:
            raise ValueError(f"no_override_required DOI pair differs for {requested}")
        if action != "no_override_required" and requested == observed:
            raise ValueError(f"Registry action {action} has no DOI conflict for {requested}")
        records[requested] = {
            "requested_doi": requested,
            "observed_document_doi": observed,
            "relationship_type": relationship_type,
            "identity_action": action,
            "record_group": record_group,
        }

    return {
        "path": str(path.resolve()),
        "version": 1,
        "minimum_front_title_similarity": minimum_title_similarity,
        "records": records,
    }


def apply_identity_registry(identity: dict, record: dict | None, *, minimum_title_similarity: float) -> dict:
    """Apply one registry decision only after exact DOI and front-title checks."""
    result = dict(identity)
    result.update(
        {
            "registry_record_present": bool(record),
            "registry_applied": False,
            "registry_disposition": "not_listed",
            "registry_record_group": "",
            "registry_relationship_type": "",
            "registry_identity_action": "",
            "registry_observed_document_doi": "",
            "registry_title_similarity": None,
            "registry_correction_title_similarity": None,
            "registry_front_title_phrase_match": False,
        }
    )
    if not record:
        return result

    action = clean(record.get("identity_action", ""))
    observed = normalize_doi(record.get("observed_document_doi", ""))
    result.update(
        {
            "registry_relationship_type": clean(record.get("relationship_type", "")),
            "registry_record_group": clean(record.get("record_group", "benign_conflict")),
            "registry_identity_action": action,
            "registry_observed_document_doi": observed,
        }
    )
    if clean(identity.get("status", "")) == "verified_exact_doi":
        result["registry_disposition"] = "not_needed_exact_identity"
        return result
    if action == "no_override_required":
        result["registry_disposition"] = "unresolved_exact_identity_not_verified"
        return result

    matching_rows = [
        row
        for row in identity.get("evidence", []) or []
        if normalize_doi(row.get("document_doi", "")) == observed
    ]
    if not matching_rows:
        result["registry_disposition"] = "unresolved_recorded_document_doi_not_observed"
        return result
    selected = max(
        matching_rows,
        key=lambda row: (
            bool(row.get("front_title_phrase_match")),
            row.get("title_similarity") or 0,
        ),
    )
    similarity = selected.get("title_similarity")
    phrase_match = bool(selected.get("front_title_phrase_match"))
    result["registry_title_similarity"] = similarity
    result["registry_front_title_phrase_match"] = phrase_match
    corroboration_similarity = similarity
    if action == "accept_correction_original_doi":
        if not correction_title_signal(identity.get("requested_title", "")):
            result["registry_disposition"] = "unresolved_requested_title_is_not_correction"
            return result
        corroboration_similarity = correction_title_similarity(
            identity.get("requested_title", ""),
            selected.get("document_title", ""),
        )
        result["registry_correction_title_similarity"] = corroboration_similarity
    if not phrase_match and (corroboration_similarity or 0) < minimum_title_similarity:
        result["registry_disposition"] = "unresolved_insufficient_front_title_evidence"
        return result

    if action == "accept_correction_original_doi":
        status = "verified_related_doi"
        decision_label = "curated correction-to-original relationship"
    elif action == "accept_related_document_doi":
        status = "verified_related_doi"
        decision_label = "curated document relationship"
    elif action == "ignore_incorrect_extracted_document_doi":
        status = "verified_identity_override"
        decision_label = "curated extracted-identifier override"
    else:  # Guarded by registry validation; kept defensive for direct callers.
        result["registry_disposition"] = "unresolved_unsupported_registry_action"
        return result

    result.update(
        {
            "status": status,
            "verified": True,
            "basis": (
                f"{decision_label} matches the observed document DOI and the "
                "requested title is corroborated by front-matter evidence"
            ),
            "document_doi": observed,
            "document_title": clean(selected.get("document_title", "")),
            "document_pmid": clean(selected.get("document_pmid", "")),
            "document_pmcid": clean(selected.get("document_pmcid", "")),
            "title_similarity": similarity,
            "title_coverage": selected.get("title_coverage"),
            "title_phrase_match": bool(selected.get("title_phrase_match", False)),
            "front_title_phrase_match": phrase_match,
            "backend": clean(selected.get("backend", result.get("backend", ""))),
            "format": clean(selected.get("format", result.get("format", ""))),
            "registry_applied": True,
            "registry_disposition": "applied_front_title_corroborated",
        }
    )
    return result


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def apply_validated_pdf_repair_attestation(identity: dict, artifact: dict) -> dict:
    """Accept a PDF repair only when its stored independent checks still verify.

    Normal identity evaluation remains the primary path.  This narrow fallback
    exists for accepted manuscripts and repositories whose GROBID header omits
    the DOI even though the requested title was independently validated on PDF
    page one at repair time.  The PDF hash is rechecked on every audit.
    """
    result = dict(identity)
    result["repair_attestation_applied"] = False
    if bool(identity.get("verified")):
        return result
    attested = artifact.get("source_identity")
    if not isinstance(attested, dict):
        return result
    validation = attested.get("pdf_front_page_validation")
    if not isinstance(validation, dict):
        return result
    if clean(artifact.get("repair_run_id", "")) != "source_identity_repair_20260710":
        return result
    if clean(artifact.get("fulltext_source", "")) != "validated_pdf_source_identity_repair":
        return result
    if clean(attested.get("status", "")) != "verified_title_only" or not bool(attested.get("verified")):
        return result
    if not bool(validation.get("accepted")) or clean(validation.get("reason", "")) != "verified_front_page":
        return result
    if float(validation.get("title_score", 0) or 0) < 0.86:
        return result
    if int(validation.get("front_page_char_count", 0) or 0) < 300:
        return result
    requested = normalize_doi(artifact.get("study_doi", ""))
    if normalize_doi(attested.get("requested_doi", "")) != requested:
        return result
    pdf_raw = clean(artifact.get("pdf_local_path", ""))
    pdf_path = Path(pdf_raw).expanduser() if pdf_raw else None
    if pdf_path is None or not pdf_path.exists() or not pdf_path.is_file():
        return result
    expected_hash = clean(artifact.get("pdf_sha256", "")).lower()
    if not expected_hash or file_sha256(pdf_path).lower() != expected_hash:
        return result

    preserved_registry = {
        key: value
        for key, value in result.items()
        if key.startswith("registry_")
    }
    return {
        **result,
        **attested,
        **preserved_registry,
        "status": "verified_title_only",
        "verified": True,
        "basis": "validated replacement PDF title matched on page one and its stored SHA-256 still matches",
        "repair_attestation_applied": True,
    }


def metadata_map(*paths: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in paths:
        if not path.exists():
            continue
        for row in pd.read_parquet(path).fillna("").to_dict("records"):
            doi = normalize_doi(row.get("doi", "") or row.get("study_doi", ""))
            if not doi:
                continue
            current = out.setdefault(doi, {"doi": doi})
            for key, value in row.items():
                if clean(value) and not clean(current.get(key, "")):
                    current[key] = value
    return out


def related_dois(row: dict) -> set[str]:
    return split_dois(
        row.get("related_dois", ""),
        row.get("publication_relations", ""),
        row.get("published_version_doi", ""),
    )


def audit_artifacts(
    artifact_dir: Path,
    metadata: dict[str, dict],
    doi_filter: set[str] | None = None,
    identity_registry: dict | None = None,
    pdf_hash_registry: dict | None = None,
) -> dict:
    rows: list[dict] = []
    counts: Counter[str] = Counter()
    backend_counts: dict[str, Counter[str]] = defaultdict(Counter)
    registry = identity_registry or {
        "path": "",
        "version": 1,
        "minimum_front_title_similarity": 0.9,
        "records": {},
    }
    registry_records = registry.get("records", {})
    hash_registry = pdf_hash_registry or {"path": "", "version": 1, "records": {}}
    hash_registry_records = hash_registry.get("records", {})
    minimum_title_similarity = float(registry.get("minimum_front_title_similarity", 0.9))
    for path in sorted(artifact_dir.glob("*.json")):
        artifact = load_json(path)
        requested = normalize_doi(artifact.get("study_doi", ""))
        if not requested:
            requested = normalize_doi(path.stem.replace("_", "/"))
        if doi_filter is not None and requested not in doi_filter:
            continue
        meta = metadata.get(requested, {})
        requested_title = clean(meta.get("study_title", "") or artifact.get("study_title", ""))
        identity = augment_pdf_artifact_identity(
            apply_validated_pdf_repair_attestation(
                apply_identity_registry(
                    reject_correction_artifact_for_main_record(
                        evaluate_artifact_identity(
                            artifact,
                            requested_doi=requested,
                            requested_title=requested_title,
                            # Metadata relations include CommentOn, errata, and other
                            # records that are not interchangeable source documents.
                            # Only the curated registry can promote a related DOI in
                            # this audit.
                            related_dois=(),
                        ),
                        artifact,
                    ),
                    registry_records.get(requested),
                    minimum_title_similarity=minimum_title_similarity,
                ),
                artifact,
            ),
            artifact,
            requested_title=requested_title,
            pdf_hash_attestations=hash_registry_records,
        )
        status = clean(identity.get("status", "identity_unverified"))
        backend = clean(artifact.get("best_backend", "")) or "missing"
        counts["artifacts"] += 1
        counts[status] += 1
        if identity.get("registry_record_present"):
            counts["registry_records_in_scope"] += 1
            counts[f"registry_{clean(identity.get('registry_disposition', 'unknown'))}"] += 1
            group = clean(identity.get("registry_record_group", "")) or "unclassified"
            counts[f"registry_group_{group}_records_in_scope"] += 1
            counts[
                f"registry_group_{group}_{clean(identity.get('registry_disposition', 'unknown'))}"
            ] += 1
        if identity.get("registry_applied"):
            counts["registry_applied"] += 1
        if identity.get("repair_attestation_applied"):
            counts["repair_attestation_applied"] += 1
        if identity.get("pdf_front_title_validation_applied"):
            counts["pdf_front_title_validation_applied"] += 1
        if identity.get("pdf_hash_attestation_applied"):
            counts["pdf_hash_attestation_applied"] += 1
        if identity.get("verified"):
            counts["verified"] += 1
        else:
            counts["not_verified"] += 1
        backend_counts[backend]["artifacts"] += 1
        backend_counts[backend][status] += 1
        if identity.get("verified"):
            backend_counts[backend]["verified"] += 1
        else:
            backend_counts[backend]["not_verified"] += 1
        pdf_path = Path(clean(artifact.get("pdf_local_path", ""))).expanduser() if clean(artifact.get("pdf_local_path", "")) else None
        rows.append(
            {
                "requested_doi": requested,
                "requested_title": requested_title,
                "requested_pmid": clean(meta.get("pmid", "")),
                "requested_pmcid": clean(meta.get("pmcid", "")),
                "related_dois": " | ".join(sorted(related_dois(meta))),
                "identity_status": status,
                "identity_verified": bool(identity.get("verified")),
                "identity_basis": clean(identity.get("basis", "")),
                "document_doi": clean(identity.get("document_doi", "")),
                "document_title": clean(identity.get("document_title", "")),
                "document_pmid": clean(identity.get("document_pmid", "")),
                "document_pmcid": clean(identity.get("document_pmcid", "")),
                "title_similarity": identity.get("title_similarity"),
                "title_coverage": identity.get("title_coverage"),
                "title_phrase_match": bool(identity.get("title_phrase_match", False)),
                "front_title_phrase_match": bool(identity.get("front_title_phrase_match", False)),
                "registry_record_present": bool(identity.get("registry_record_present", False)),
                "registry_applied": bool(identity.get("registry_applied", False)),
                "registry_disposition": clean(identity.get("registry_disposition", "")),
                "registry_record_group": clean(identity.get("registry_record_group", "")),
                "registry_relationship_type": clean(identity.get("registry_relationship_type", "")),
                "registry_identity_action": clean(identity.get("registry_identity_action", "")),
                "registry_observed_document_doi": clean(identity.get("registry_observed_document_doi", "")),
                "registry_title_similarity": identity.get("registry_title_similarity"),
                "registry_correction_title_similarity": identity.get(
                    "registry_correction_title_similarity"
                ),
                "registry_front_title_phrase_match": bool(
                    identity.get("registry_front_title_phrase_match", False)
                ),
                "repair_attestation_applied": bool(identity.get("repair_attestation_applied", False)),
                "pdf_front_title_validation_applied": bool(
                    identity.get("pdf_front_title_validation_applied", False)
                ),
                "pdf_front_title_validation_score": (
                    identity.get("pdf_front_title_validation") or {}
                ).get("title_score"),
                "pdf_hash_attestation_present": bool(
                    identity.get("pdf_hash_attestation_present", False)
                ),
                "pdf_hash_attestation_applied": bool(
                    identity.get("pdf_hash_attestation_applied", False)
                ),
                "pdf_hash_attestation_disposition": clean(
                    identity.get("pdf_hash_attestation_disposition", "")
                ),
                "best_backend": backend,
                "fulltext_source": clean(artifact.get("fulltext_source", "") or artifact.get("source_artifact_dataset", "")),
                "best_char_count": int(artifact.get("best_char_count", 0) or 0),
                "artifact_path": str(path.resolve()),
                "pdf_local_path": str(pdf_path) if pdf_path else "",
                "pdf_exists": bool(pdf_path and pdf_path.exists()),
            }
        )
    return {
        "artifact_dir": str(artifact_dir.resolve()),
        "identity_registry": {
            "path": clean(registry.get("path", "")),
            "version": registry.get("version", 1),
            "record_count": len(registry_records),
            "minimum_front_title_similarity": minimum_title_similarity,
        },
        "pdf_hash_attestation_registry": {
            "path": clean(hash_registry.get("path", "")),
            "version": hash_registry.get("version", 1),
            "record_count": len(hash_registry_records),
        },
        "counts": dict(counts),
        "backend_counts": {backend: dict(values) for backend, values in sorted(backend_counts.items())},
        "rows": rows,
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(rows[0]) if rows else ["requested_doi", "identity_status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def read_doi_file(path: Path) -> set[str]:
    return {
        doi
        for line in path.read_text(encoding="utf-8").splitlines()
        if (doi := normalize_doi(line))
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    parser.add_argument("--report-csv", default=str(DEFAULT_REPORT_CSV))
    parser.add_argument("--unverified-doi-file", default=str(DEFAULT_UNVERIFIED_DOIS))
    parser.add_argument(
        "--identity-registry",
        default=str(DEFAULT_IDENTITY_REGISTRY),
        help="Curated DOI relationship/override registry; pass an empty string to disable it",
    )
    parser.add_argument(
        "--pdf-hash-attestation-registry",
        default=str(DEFAULT_PDF_HASH_ATTESTATION_REGISTRY),
        help="Hash-bound curator decisions for exceptional single-article PDFs",
    )
    parser.add_argument("--doi-file", default="")
    parser.add_argument("--fail-on-unverified", action="store_true")
    args = parser.parse_args()

    report_json = Path(args.report_json).resolve()
    report_csv = Path(args.report_csv).resolve()
    registry = (
        load_identity_registry(Path(args.identity_registry).resolve())
        if clean(args.identity_registry)
        else None
    )
    hash_registry = (
        load_pdf_hash_attestation_registry(
            Path(args.pdf_hash_attestation_registry).resolve()
        )
        if clean(args.pdf_hash_attestation_registry)
        else None
    )
    report = audit_artifacts(
        Path(args.artifact_dir).resolve(),
        metadata_map(Path(args.metadata_table).resolve(), Path(args.candidate_table).resolve()),
        read_doi_file(Path(args.doi_file).resolve()) if clean(args.doi_file) else None,
        registry,
        hash_registry,
    )
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(report_csv, report["rows"])
    unverified_path = Path(args.unverified_doi_file).resolve()
    unverified_path.parent.mkdir(parents=True, exist_ok=True)
    unverified_path.write_text(
        "".join(
            f"{row['requested_doi']}\n"
            for row in report["rows"]
            if not row.get("identity_verified") and row.get("requested_doi")
        ),
        encoding="utf-8",
    )
    print(json.dumps({key: report[key] for key in ("artifact_dir", "counts", "backend_counts")}, indent=2))
    print(f"JSON report: {report_json}")
    print(f"CSV report: {report_csv}")
    print(f"Unverified DOI file: {unverified_path}")
    return 1 if args.fail_on_unverified and report["counts"].get("not_verified", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
