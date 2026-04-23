#!/usr/bin/env python3
"""Promote curated-ready stubs into curated datasets with strict validation."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
DISORDER_CANON_PATH = ROOT / "schema" / "disorder_canonicalization.json"

DATASET_CONFIG = {
    "mechanistic": {
        "stubs_json": ROOT / "data" / "processed" / "mechanistic_claim_stubs.json",
        "stubs_csv": ROOT / "data" / "processed" / "mechanistic_claim_stubs.csv",
        "curated_json": ROOT / "data" / "curated" / "claims.json",
        "curated_csv": ROOT / "data" / "curated" / "claims.csv",
        "triage_report_json": ROOT / "data" / "processed" / "triage_report_mechanistic.json",
        "schema": ROOT / "schema" / "claims.schema.json",
        "entity_key": "target",
        "id_fields": [
            "compound",
            "target",
            "study_doi",
            "openalex_id",
            "assay_type",
            "affinity_type",
            "affinity_value",
            "affinity_unit",
        ],
        "csv_order": [
            "compound",
            "target",
            "assay_type",
            "affinity_type",
            "affinity_value",
            "affinity_unit",
            "species",
            "system",
            "study_doi",
            "openalex_id",
            "study_title",
            "authors",
            "study_year",
            "paper_type",
            "evidence_level",
            "source",
            "source_type",
            "access_level",
            "evidence_location",
            "evidence_locator",
            "study_design",
            "notes",
        ],
    },
    "disorder": {
        "stubs_json": ROOT / "data" / "processed" / "disorder_claim_stubs.json",
        "stubs_csv": ROOT / "data" / "processed" / "disorder_claim_stubs.csv",
        "curated_json": ROOT / "data" / "curated" / "disorder_claims.json",
        "curated_csv": ROOT / "data" / "curated" / "disorder_claims.csv",
        "triage_report_json": ROOT / "data" / "processed" / "triage_report_disorder.json",
        "schema": ROOT / "schema" / "disorder_claims.schema.json",
        "entity_key": "disorder",
        "id_fields": [
            "compound",
            "disorder",
            "study_doi",
            "openalex_id",
            "outcome_type",
            "outcome_measure",
        ],
        "csv_order": [
            "compound",
            "disorder",
            "outcome_type",
            "result_direction",
            "outcome_measure",
            "population",
            "system",
            "study_doi",
            "openalex_id",
            "study_title",
            "authors",
            "study_year",
            "paper_type",
            "evidence_level",
            "source",
            "source_type",
            "access_level",
            "evidence_location",
            "evidence_locator",
            "study_design",
            "notes",
        ],
    },
}

NUMERIC_SIGNATURE_FIELDS = {"affinity_value"}
PROMOTION_DIFF_FIELDS = [
    "compound",
    "target",
    "disorder",
    "assay_type",
    "affinity_type",
    "affinity_value",
    "affinity_unit",
    "outcome_type",
    "outcome_measure",
    "result_direction",
    "population",
    "system",
    "paper_type",
    "source_type",
    "access_level",
    "evidence_location",
    "evidence_locator",
    "study_design",
    "evidence_level",
    "notes",
]
PROMOTION_BLOCKED_TITLE_PATTERNS = [
    ("review record", re.compile(r"^\s*review for\b", re.IGNORECASE)),
    ("author correction", re.compile(r"\bauthor correction\b", re.IGNORECASE)),
    ("retraction note", re.compile(r"\bretraction note\b", re.IGNORECASE)),
    ("recommendation record", re.compile(r"\bfaculty opinions recommendation\b", re.IGNORECASE)),
    (
        "opinion/research-direction article",
        re.compile(
            r"\b(is there a place for|future directions|research directions|where do we go from here|commentary|editorial)\b",
            re.IGNORECASE,
        ),
    ),
]
TRUNCATE_REPORT_VALUE_AT = 260
HEALTHY_VOLUNTEER_RE = re.compile(r"\bhealthy (?:volunteers?|participants?|adults?|subjects?|controls?)\b", re.IGNORECASE)


def normalize(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_text(raw: str) -> str:
    lowered = normalize(raw).lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def disorder_context_terms(disorder: str) -> Set[str]:
    text = normalize_text(disorder)
    terms = {text} if text else set()
    if "major depressive disorder" in text:
        terms.update({"depression", "mdd", "unipolar depression"})
    if "treatment resistant depression" in text:
        terms.update({"treatment resistant depression", "trd", "depression"})
    if "post traumatic stress disorder" in text or "posttraumatic stress disorder" in text:
        terms.update({"ptsd", "post traumatic stress disorder", "posttraumatic stress disorder"})
    if "social anxiety disorder" in text:
        terms.update({"social anxiety", "social anxiety disorder"})
    if "substance use disorder" in text:
        terms.update({"substance use disorder", "addiction"})
    return {term for term in terms if term}


def has_disorder_sample_context(disorder: str, text_norm: str) -> bool:
    for term in disorder_context_terms(disorder):
        escaped = re.escape(term)
        if re.search(
            rf"\b(?:patients?|participants?|adults?|volunteers?|subjects?|individuals?|people) with [a-z0-9 ]{{0,80}}\b{escaped}\b",
            text_norm,
        ):
            return True
        if re.search(rf"\bhealthy (?:volunteers?|participants?|controls?|subjects?) and [a-z0-9 ]{{0,50}}\b{escaped}\b", text_norm):
            return True
        if re.search(
            rf"\b{escaped}\b [a-z0-9 ]{{0,60}}\b(?:patients?|participants?|adults?|volunteers?|subjects?|individuals?|people)\b",
            text_norm,
        ):
            return True
    return False


def looks_like_healthy_volunteer_only_disorder_row(row: dict) -> bool:
    disorder = normalize(row.get("disorder", ""))
    if not disorder:
        return False
    text_norm = normalize_text(
        " ".join(
            [
                normalize(row.get("study_title", "")),
                normalize(row.get("population", "")),
                normalize(row.get("evidence_locator", "")),
            ]
        )
    )
    return bool(HEALTHY_VOLUNTEER_RE.search(text_norm)) and not has_disorder_sample_context(disorder, text_norm)


def load_disorder_alias_map(path: Path = DISORDER_CANON_PATH) -> Dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {}

    alias_map: Dict[str, str] = {}
    for canonical, aliases in data.items():
        canonical_label = normalize(canonical)
        if not canonical_label:
            continue
        alias_map[normalize_text(canonical_label)] = canonical_label
        if not isinstance(aliases, list):
            continue
        for raw in aliases:
            alias = normalize(raw)
            if not alias:
                continue
            alias_map[normalize_text(alias)] = canonical_label
    return alias_map


DISORDER_ALIAS_MAP = load_disorder_alias_map()


def canonicalize_disorder_label(raw: str) -> str:
    text = normalize(raw)
    if not text:
        return ""
    normalized = normalize_text(text)
    return DISORDER_ALIAS_MAP.get(normalized, text)


def append_note(notes: str, message: str) -> str:
    base = normalize(notes)
    msg = normalize(message)
    if not msg:
        return base
    if base and msg.lower() in base.lower():
        return base
    if not base:
        return msg
    return f"{base}; {msg}"


def normalize_disorder_row(row: dict, note_suffix: str) -> dict:
    out = dict(row)
    raw_disorder = normalize(out.get("disorder", ""))
    canonical_disorder = canonicalize_disorder_label(raw_disorder)
    if raw_disorder and canonical_disorder and raw_disorder != canonical_disorder:
        out["disorder"] = canonical_disorder
        out["notes"] = append_note(
            out.get("notes", ""),
            f"Disorder normalized from `{raw_disorder}` {note_suffix}",
        )
    return out


def load_json_array(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return data


def load_schema(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: List[dict], preferred_order: List[str]) -> None:
    key_set = {k for row in rows for k in row.keys()}
    ordered = [k for k in preferred_order if k in key_set]
    tail = sorted(key_set - set(ordered))
    fieldnames = ordered + tail

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_schema(schema: dict) -> Tuple[List[str], Dict[str, set], Dict[str, str], List[set]]:
    item = schema["items"]
    required = list(item.get("required", []))
    properties = item.get("properties", {})

    enums: Dict[str, set] = {}
    types: Dict[str, str] = {}
    for key, prop in properties.items():
        if "enum" in prop:
            enums[key] = set(prop["enum"])
        if "type" in prop:
            types[key] = prop["type"]

    one_of_groups: List[set] = []
    for group in item.get("oneOf", []):
        if isinstance(group, dict) and "required" in group:
            one_of_groups.append(set(group["required"]))

    return required, enums, types, one_of_groups


def coerce_value(value, type_name: str):
    text = normalize(value)
    if text == "":
        return ""
    if type_name == "integer":
        return int(float(text))
    if type_name == "number":
        return float(text)
    return text


def validate_ready_row(
    row: dict,
    required: List[str],
    enums: Dict[str, set],
    types: Dict[str, str],
    one_of_groups: List[set],
    allowed_keys: set,
) -> Tuple[dict, List[str]]:
    errors: List[str] = []
    cleaned = {key: row.get(key, "") for key in allowed_keys}

    for field in required:
        if normalize(cleaned.get(field, "")) == "":
            errors.append(f"missing required field `{field}`")

    if one_of_groups:
        any_group_satisfied = any(
            any(normalize(cleaned.get(field, "")) for field in group)
            for group in one_of_groups
        )
        if not any_group_satisfied:
            alternatives = ["|".join(sorted(group)) for group in one_of_groups]
            errors.append(f"requires one of: {' OR '.join(alternatives)}")

    for field, allowed in enums.items():
        value = normalize(cleaned.get(field, ""))
        if value and value not in allowed:
            errors.append(f"invalid `{field}` value `{value}`")

    for field, type_name in types.items():
        if field not in cleaned:
            continue
        raw = cleaned.get(field, "")
        if normalize(raw) == "":
            continue
        try:
            cleaned[field] = coerce_value(raw, type_name)
        except Exception:
            errors.append(f"invalid `{field}` type for `{raw}` expected `{type_name}`")

    return cleaned, errors


def normalize_signature_value(field: str, value) -> str:
    text = normalize(value)
    if text == "":
        return ""
    if field in NUMERIC_SIGNATURE_FIELDS:
        try:
            return f"{float(text):.12g}"
        except ValueError:
            return text
    return text


def signature(row: dict, id_fields: List[str]) -> Tuple[str, ...]:
    return tuple(f"{field}={normalize_signature_value(field, row.get(field, ''))}" for field in id_fields)


def truncate_report_value(value) -> str:
    text = normalize(value)
    if len(text) <= TRUNCATE_REPORT_VALUE_AT:
        return text
    return text[: TRUNCATE_REPORT_VALUE_AT - 3].rstrip() + "..."


def row_diff(existing: dict, candidate: dict, fields: List[str] = PROMOTION_DIFF_FIELDS) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for field in fields:
        old = existing.get(field, "")
        new = candidate.get(field, "")
        if normalize(old) == normalize(new):
            continue
        out[field] = {
            "existing": truncate_report_value(old),
            "candidate": truncate_report_value(new),
        }
    return out


def promotion_evidence_errors(row: dict) -> List[str]:
    errors: List[str] = []
    access_level = normalize(row.get("access_level", ""))
    evidence_location = normalize(row.get("evidence_location", ""))
    evidence_locator = normalize(row.get("evidence_locator", ""))
    source_type = normalize(row.get("source_type", ""))
    study_title = normalize(row.get("study_title", ""))

    if source_type != "primary_study":
        errors.append(
            f"source_type `{source_type or 'missing'}` is not promotable; curated graph claims must come from primary studies"
        )

    if access_level == "secondary_summary":
        errors.append("access_level `secondary_summary` is not promotable into the primary evidence graph")

    if evidence_location == "unknown":
        errors.append("evidence_location `unknown` is not promotable; cite abstract, text, table, figure, supplement, or mixed evidence")

    locator_lower = evidence_locator.lower()
    if locator_lower.startswith("metadata/title snippet:"):
        errors.append("metadata/title-only evidence is not promotable; claim needs abstract or full-text support")

    if looks_like_healthy_volunteer_only_disorder_row(row):
        errors.append(
            "healthy-volunteer safety/subjective-effects study is not promotable as a disorder efficacy claim"
        )

    for label, pattern in PROMOTION_BLOCKED_TITLE_PATTERNS:
        if pattern.search(study_title):
            errors.append(f"study_title indicates a {label}, not a primary results paper")
            break

    return errors


def promotion_evidence_warnings(row: dict) -> List[str]:
    warnings: List[str] = []
    access_level = normalize(row.get("access_level", ""))
    evidence_locator = normalize(row.get("evidence_locator", ""))
    if access_level == "full_text_seen" and evidence_locator.lower().startswith("abstract snippet:"):
        warnings.append("full_text_seen row still uses an abstract snippet as the evidence locator")
    return warnings


def relevance_context_signature(dataset: str, row: dict, entity_key: str) -> Tuple[str, str, str]:
    doi = normalize(row.get("study_doi", "")).lower()
    compound = normalize(row.get("compound", "")).lower()
    entity = normalize(row.get(entity_key, ""))
    if dataset == "disorder":
        entity = canonicalize_disorder_label(entity)
    return doi, compound, normalize(entity).lower()


def _context_signature_from_ctx(dataset: str, doi: str, ctx: dict) -> Tuple[str, str, str]:
    compound = normalize(ctx.get("compound", "")).lower()
    entity = normalize(ctx.get("entity", ""))
    if dataset == "disorder":
        entity = canonicalize_disorder_label(entity)
    return doi, compound, normalize(entity).lower()


def load_triage_disallowed_context_signatures(
    dataset: str, cfg: dict
) -> Dict[Tuple[str, str, str], str]:
    path = cfg.get("triage_report_json")
    if not isinstance(path, Path) or not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        return {}
    data = payload.get("rows", [])
    if not isinstance(data, list):
        return {}

    # reason is one of: "irrelevant", "unmatched_context"
    out: Dict[Tuple[str, str, str], str] = {}
    for row in data:
        if not isinstance(row, dict):
            continue

        doi = normalize(row.get("study_doi", "")).lower()
        if not doi:
            continue

        all_contexts = row.get("contexts_all", row.get("contexts", []))
        if not isinstance(all_contexts, list):
            continue
        all_set: Set[Tuple[str, str, str]] = set()
        for ctx in all_contexts:
            if not isinstance(ctx, dict):
                continue
            sig = _context_signature_from_ctx(dataset, doi, ctx)
            if sig[1] and sig[2]:
                all_set.add(sig)
        if not all_set:
            continue

        matched_contexts = row.get("contexts", [])
        matched_set: Set[Tuple[str, str, str]] = set()
        if isinstance(matched_contexts, list):
            for ctx in matched_contexts:
                if not isinstance(ctx, dict):
                    continue
                sig = _context_signature_from_ctx(dataset, doi, ctx)
                if sig[1] and sig[2]:
                    matched_set.add(sig)

        relevance = normalize(row.get("relevance_suggested", ""))
        if relevance == "likely_irrelevant":
            disallowed = all_set
            reason = "irrelevant"
        else:
            disallowed = all_set - matched_set
            reason = "unmatched_context"

        for sig in disallowed:
            existing = out.get(sig, "")
            # Keep strongest reason if a signature appears multiple times.
            if reason == "irrelevant" or not existing:
                out[sig] = reason

    return out


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote ready stubs into curated datasets")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument("--ready-status", default="ready_for_promotion")
    parser.add_argument("--apply", action="store_true", help="Write changes to curated/stub files")
    parser.add_argument(
        "--upsert-duplicates",
        action="store_true",
        help="When signature already exists in curated rows, update curated row from ready stub instead of skipping",
    )
    parser.add_argument(
        "--report",
        default="",
        help="Optional report output path (defaults to data/processed/promotion_report_<dataset>.json)",
    )
    args = parser.parse_args()

    cfg = DATASET_CONFIG[args.dataset]
    report_path = (
        Path(args.report).resolve()
        if args.report
        else ROOT / "data" / "processed" / f"promotion_report_{args.dataset}.json"
    )

    stubs = load_json_array(cfg["stubs_json"])
    curated = load_json_array(cfg["curated_json"])
    curated_loaded = len(curated)
    curated_normalized_count = 0
    curated_deduped_count = 0
    triage_pruned_count = 0
    triage_pruned_samples: List[dict] = []
    if args.dataset == "disorder":
        normalized_curated = []
        for row in curated:
            normalized = normalize_disorder_row(row, note_suffix="during curated normalization")
            if normalize(normalized.get("disorder", "")) != normalize(row.get("disorder", "")):
                curated_normalized_count += 1
            normalized_curated.append(normalized)
        curated = normalized_curated

        deduped_curated = []
        seen_curated_sigs = set()
        for row in curated:
            sig = signature(row, cfg["id_fields"])
            if sig in seen_curated_sigs:
                curated_deduped_count += 1
                continue
            seen_curated_sigs.add(sig)
            deduped_curated.append(row)
        curated = deduped_curated

    disallowed_reasons = load_triage_disallowed_context_signatures(args.dataset, cfg)
    triage_pruned_from_irrelevant = 0
    triage_pruned_from_unmatched_context = 0
    if disallowed_reasons:
        filtered_curated = []
        for row in curated:
            sig = relevance_context_signature(args.dataset, row, cfg["entity_key"])
            reason = disallowed_reasons.get(sig, "")
            if reason:
                triage_pruned_count += 1
                if reason == "irrelevant":
                    triage_pruned_from_irrelevant += 1
                elif reason == "unmatched_context":
                    triage_pruned_from_unmatched_context += 1
                if len(triage_pruned_samples) < 25:
                    triage_pruned_samples.append(
                        {
                            "study_doi": normalize(row.get("study_doi", "")),
                            "compound": normalize(row.get("compound", "")),
                            cfg["entity_key"]: normalize(row.get(cfg["entity_key"], "")),
                        }
                    )
                continue
            filtered_curated.append(row)
        curated = filtered_curated

    schema = load_schema(cfg["schema"])
    required, enums, types, one_of_groups = parse_schema(schema)
    allowed_keys = set(schema["items"]["properties"].keys())

    ready_rows = []
    pending_rows = []
    for row in stubs:
        if normalize(row.get("stub_status", "")) == args.ready_status:
            ready_rows.append(row)
        else:
            pending_rows.append(row)

    report = {
        "generated_at": now_utc(),
        "dataset": args.dataset,
        "ready_status": args.ready_status,
        "apply": args.apply,
        "counts": {
            "stubs_total": len(stubs),
            "ready_rows": len(ready_rows),
            "curated_before": curated_loaded,
            "curated_normalized": curated_normalized_count,
            "curated_deduped": curated_deduped_count,
            "curated_pruned_by_triage": triage_pruned_count,
            "curated_pruned_from_irrelevant": triage_pruned_from_irrelevant,
            "curated_pruned_from_unmatched_context": triage_pruned_from_unmatched_context,
        },
        "errors": [],
        "warnings": [],
        "row_warnings": [],
        "promoted": [],
        "duplicates": [],
        "upserted": [],
        "triage_pruned_samples": triage_pruned_samples,
    }

    if curated_normalized_count > 0:
        report["warnings"].append(
            f"Canonicalized disorder labels for {curated_normalized_count} existing curated row(s)"
        )
    if curated_deduped_count > 0:
        report["warnings"].append(
            f"Removed {curated_deduped_count} duplicate curated row(s) after disorder normalization"
        )
    if triage_pruned_from_irrelevant > 0:
        report["warnings"].append(
            f"Pruned {triage_pruned_from_irrelevant} curated context row(s) from likely_irrelevant triage papers"
        )
    if triage_pruned_from_unmatched_context > 0:
        report["warnings"].append(
            f"Pruned {triage_pruned_from_unmatched_context} curated context row(s) not matched by triage context detection"
        )

    if not ready_rows:
        report["warnings"].append("No rows with the requested ready status")
        report["counts"]["curated_after"] = len(curated)
        if args.apply and (curated_normalized_count > 0 or curated_deduped_count > 0 or triage_pruned_count > 0):
            write_json(cfg["curated_json"], curated)
            write_csv(cfg["curated_csv"], curated, cfg["csv_order"])
            report["status"] = "applied_curated_normalization_only"
            report["warnings"].append("Applied curated cleanup without promoting new rows")
            print("No ready rows found, but curated cleanup was applied")
            print(f"Curated JSON: {cfg['curated_json']}")
            print(f"Curated CSV: {cfg['curated_csv']}")
        else:
            report["status"] = "no_ready_rows"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"No ready rows found for status `{args.ready_status}`")
        print(f"Report: {report_path}")
        return 0

    curated_signatures = {signature(row, cfg["id_fields"]) for row in curated}
    curated_signature_to_index = {
        signature(row, cfg["id_fields"]): idx for idx, row in enumerate(curated)
    }

    promotable_cleaned = []
    promoted_signatures = set()
    upserted_signatures = set()
    duplicate_signatures = set()
    for idx, row in enumerate(ready_rows, start=1):
        normalized_row = (
            normalize_disorder_row(row, note_suffix="during promotion")
            if args.dataset == "disorder"
            else dict(row)
        )

        cleaned, row_errors = validate_ready_row(
            row=normalized_row,
            required=required,
            enums=enums,
            types=types,
            one_of_groups=one_of_groups,
            allowed_keys=allowed_keys,
        )

        paper_type = normalize(cleaned.get("paper_type", ""))
        if paper_type != "primary_results":
            row_errors.append(
                f"paper_type `{paper_type or 'missing'}` is not promotable; only `primary_results` can enter curated claims"
            )
        row_errors.extend(promotion_evidence_errors(cleaned))

        row_warnings = promotion_evidence_warnings(cleaned)
        if row_warnings:
            report["row_warnings"].append(
                {
                    "row_index": idx,
                    "study_doi": normalize(cleaned.get("study_doi", "")),
                    "messages": row_warnings,
                }
            )

        if row_errors:
            report["errors"].append(
                {
                    "row_index": idx,
                    "study_doi": normalize(normalized_row.get("study_doi", "")),
                    "messages": row_errors,
                }
            )
            continue

        sig = signature(cleaned, cfg["id_fields"])
        if sig in curated_signatures:
            curated_idx = curated_signature_to_index.get(sig)
            existing_row = curated[curated_idx] if curated_idx is not None else {}
            changed_fields = row_diff(existing_row, cleaned) if existing_row else {}
            if args.upsert_duplicates:
                if curated_idx is not None and curated[curated_idx] != cleaned:
                    curated[curated_idx] = cleaned
                    upserted_signatures.add(sig)
                    report["upserted"].append(
                        {
                            "row_index": idx,
                            "existing_row_index": curated_idx + 1,
                            "study_doi": normalize(cleaned.get("study_doi", "")),
                            "signature": list(sig),
                            "changed_fields": changed_fields,
                        }
                    )
                    continue
            duplicate_signatures.add(sig)
            report["duplicates"].append(
                {
                    "row_index": idx,
                    "existing_row_index": curated_idx + 1 if curated_idx is not None else None,
                    "study_doi": normalize(cleaned.get("study_doi", "")),
                    "signature": list(sig),
                    "changed_fields": changed_fields,
                }
            )
            continue

        promotable_cleaned.append(cleaned)
        promoted_signatures.add(sig)
        curated_signatures.add(sig)
        report["promoted"].append(
            {
                "row_index": idx,
                "study_doi": normalize(cleaned.get("study_doi", "")),
                "compound": normalize(cleaned.get("compound", "")),
            }
        )

    report["counts"]["validated_ready_rows"] = len(ready_rows)
    report["counts"]["promotable_rows"] = len(promotable_cleaned)
    report["counts"]["upserted_rows"] = len(report["upserted"])
    report["counts"]["duplicate_rows"] = len(report["duplicates"])
    report["counts"]["duplicate_rows_with_diffs"] = sum(
        1 for row in report["duplicates"] if row.get("changed_fields")
    )
    report["counts"]["row_warning_count"] = len(report["row_warnings"])
    report["counts"]["error_rows"] = len(report["errors"])

    if report["errors"]:
        report["status"] = "failed"
        report["counts"]["curated_after"] = len(curated)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Promotion blocked with {len(report['errors'])} row(s) failing validation")
        print(f"Report: {report_path}")
        return 1

    report["status"] = "dry_run_ok" if not args.apply else "applied"

    curated_after = curated + promotable_cleaned
    report["counts"]["curated_after"] = len(curated_after)

    if args.apply:
        write_json(cfg["curated_json"], curated_after)
        write_csv(cfg["curated_csv"], curated_after, cfg["csv_order"])

        remaining_rows = pending_rows
        for row in ready_rows:
            normalized_row = (
                normalize_disorder_row(row, note_suffix="during promotion")
                if args.dataset == "disorder"
                else dict(row)
            )
            cleaned, row_errors = validate_ready_row(
                row=normalized_row,
                required=required,
                enums=enums,
                types=types,
                one_of_groups=one_of_groups,
                allowed_keys=allowed_keys,
            )
            if not row_errors:
                paper_type = normalize(cleaned.get("paper_type", ""))
                if paper_type != "primary_results":
                    row_errors.append(
                        f"paper_type `{paper_type or 'missing'}` is not promotable; only `primary_results` can enter curated claims"
                    )
                row_errors.extend(promotion_evidence_errors(cleaned))
            if row_errors:
                remaining_rows.append(normalized_row)
                continue
            sig = signature(cleaned, cfg["id_fields"])
            if sig in duplicate_signatures:
                updated = dict(normalized_row)
                updated["stub_status"] = "duplicate_existing"
                remaining_rows.append(updated)
            elif sig in upserted_signatures:
                updated = dict(normalized_row)
                updated["stub_status"] = "duplicate_existing"
                remaining_rows.append(updated)
            elif sig in promoted_signatures:
                continue
            else:
                remaining_rows.append(normalized_row)

        write_json(cfg["stubs_json"], remaining_rows)
        write_csv(cfg["stubs_csv"], remaining_rows, sorted({k for r in remaining_rows for k in r.keys()}))

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Dataset: {args.dataset}")
    print(f"Ready rows: {len(ready_rows)}")
    print(f"Promotable rows: {len(promotable_cleaned)}")
    print(f"Upserted rows: {len(report['upserted'])}")
    print(f"Duplicates: {len(report['duplicates'])}")
    print(f"Row warnings: {len(report['row_warnings'])}")
    print(f"Errors: {len(report['errors'])}")
    print(f"Status: {report['status']}")
    print(f"Report: {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
