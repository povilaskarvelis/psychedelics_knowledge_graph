#!/usr/bin/env python3
"""Strict validator for curated mechanistic and disorder claim datasets."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
DISORDER_CANON_PATH = ROOT / "schema" / "disorder_canonicalization.json"
ENTITY_REGISTRY_PATH = ROOT / "data" / "curated" / "entity_registry.json"
TARGET_ALIASES = {
    "SERT": "SERT (SLC6A4)",
    "NET": "NET (SLC6A2)",
    "DAT": "DAT (SLC6A3)",
    "VMAT2": "VMAT2 (SLC18A2)",
    "TrkB": "TrkB (NTRK2)",
    "BDNF receptor": "TrkB (NTRK2)",
    "NTRK2": "TrkB (NTRK2)",
    "KOR": "kappa opioid receptor (OPRK1)",
    "MOR": "mu opioid receptor (OPRM1)",
    "DOR": "delta opioid receptor (OPRD1)",
    "SIGMA-1": "Sigma-1 receptor (SIGMAR1)",
    "SIGMA-2": "Sigma-2 receptor (TMEM97)",
    "CB1": "CB1 receptor (CNR1)",
    "CB2": "CB2 receptor (CNR2)",
}
DATASET_DEDUPE_KEYS = {
    "mechanistic": [
        "compound",
        "target",
        "study_doi",
        "openalex_id",
        "assay_type",
        "affinity_type",
        "affinity_value",
        "affinity_unit",
    ],
    "disorder": [
        "compound",
        "disorder",
        "study_doi",
        "openalex_id",
        "outcome_type",
        "outcome_measure",
    ],
}
TITLE_WARNING_PATTERNS = [
    ("review_record", re.compile(r"^\s*review for\b", re.IGNORECASE)),
    ("author_correction", re.compile(r"\bauthor correction\b", re.IGNORECASE)),
    ("retraction_note", re.compile(r"\bretraction note\b", re.IGNORECASE)),
    ("recommendation_record", re.compile(r"\bfaculty opinions recommendation\b", re.IGNORECASE)),
    (
        "opinion_research_direction_article",
        re.compile(
            r"\b(is there a place for|future directions|research directions|where do we go from here|commentary|editorial)\b",
            re.IGNORECASE,
        ),
    ),
]
NUMERIC_SIGNATURE_FIELDS = {"affinity_value"}


def load_json_array(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return data


def load_csv_rows(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_schema(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_entity_registry(path: Path) -> Dict[str, set]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {}

    out: Dict[str, set] = {}
    for section in ["compounds", "targets", "disorders"]:
        values = set()
        entries = data.get(section, [])
        if not isinstance(entries, list):
            out[section] = values
            continue
        for entry in entries:
            if isinstance(entry, str):
                label = normalize_value(entry)
                if label:
                    values.add(label)
                continue
            if not isinstance(entry, dict):
                continue
            label = normalize_value(entry.get("label", "") or entry.get("name", ""))
            if label:
                values.add(label)
            aliases = entry.get("aliases", [])
            if isinstance(aliases, list):
                for alias in aliases:
                    alias_text = normalize_value(alias)
                    if alias_text:
                        values.add(alias_text)
        out[section] = values
    return out


def parse_allowlists(path: Path) -> Dict[str, List[str]]:
    if not path.exists():
        return {}

    keys = {"allowed_compounds", "allowed_targets", "allowed_disorders"}
    allowlists = {key: [] for key in keys}
    current_key = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.endswith(":"):
            key = line[:-1]
            current_key = key if key in keys else None
            continue

        if current_key and line.startswith("- "):
            value = line[2:].strip().strip('"').strip("'")
            allowlists[current_key].append(value)
            continue

        # Any non-list line exits list mode for our simple parser.
        current_key = None

    return allowlists


def load_disorder_aliases_by_norm(path: Path = DISORDER_CANON_PATH) -> Dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {}

    out: Dict[str, str] = {}
    for canonical, aliases in data.items():
        canonical_label = normalize_value(canonical)
        if not canonical_label:
            continue
        out[normalize_text(canonical_label)] = canonical_label
        if isinstance(aliases, list):
            for alias in aliases:
                text = normalize_value(alias)
                if text:
                    out[normalize_text(text)] = canonical_label
    return out


def normalize_value(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_text(value: str) -> str:
    lowered = normalize_value(value).lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def canonicalize_disorder(value: str) -> str:
    raw = normalize_value(value)
    if not raw:
        return ""
    return DISORDER_ALIASES_BY_NORM.get(normalize_text(raw), raw)


DISORDER_ALIASES_BY_NORM = load_disorder_aliases_by_norm()


def build_enum_map(schema: dict) -> Dict[str, set]:
    props = schema["items"]["properties"]
    enum_map = {}
    for key, info in props.items():
        if isinstance(info, dict) and "enum" in info:
            enum_map[key] = set(info["enum"])
    return enum_map


def canonical_signature(row: dict, keys: Iterable[str]) -> Tuple[str, ...]:
    parts = []
    for key in keys:
        value = normalize_value(row.get(key, ""))
        if key in NUMERIC_SIGNATURE_FIELDS and value:
            try:
                value = f"{float(value):.12g}"
            except ValueError:
                pass
        parts.append(f"{key}={value}")
    return tuple(parts)


def warning_group(message: str) -> str:
    if "secondary_summary" in message:
        return "secondary_summary"
    if "metadata/title" in message:
        return "metadata_title_only"
    if "evidence_location is unknown" in message:
        return "unknown_evidence_location"
    if "full_text_seen row still uses abstract snippet locator" in message:
        return "full_text_uses_abstract_locator"
    if "source_type is primary_study but paper_type" in message:
        return "primary_study_with_nonprimary_paper_type"
    if "source_type is" in message and "not primary_study" in message:
        return "non_primary_source_type"
    if "study_title indicates" in message:
        return "non_primary_title_pattern"
    if "evidence_locator is weak" in message:
        return "weak_locator"
    if "authors missing" in message:
        return "authors_missing"
    if "potential duplicate claim signature" in message:
        return "duplicate_claim_signature"
    if "not in entity registry" in message:
        return "missing_entity_registry"
    if "high evidence claim sourced as review" in message:
        return "high_evidence_review"
    if "high evidence claim uses weak paper_type" in message:
        return "high_evidence_weak_paper_type"
    return "other"


def is_allowed_with_alias(value: str, allowed_values: set, aliases: Dict[str, str] | None = None) -> bool:
    if value in allowed_values:
        return True
    if not aliases:
        return False
    canonical = aliases.get(value)
    if canonical and canonical in allowed_values:
        return True
    return False


def validate_dataset(
    dataset_name: str,
    rows: List[dict],
    schema: dict,
    allowlists: Dict[str, List[str]],
    entity_registry: Dict[str, set],
) -> Tuple[List[str], List[str], Dict[str, object]]:
    errors: List[str] = []
    warnings: List[str] = []

    required_fields = list(schema["items"]["required"])
    enum_map = build_enum_map(schema)
    now_year = dt.date.today().year

    source_type_counter = Counter()
    paper_type_counter = Counter()
    access_counter = Counter()
    evidence_counter = Counter()
    design_counter = Counter()
    result_direction_counter = Counter()
    registry_missing_counter = Counter()

    dedupe_keys = DATASET_DEDUPE_KEYS[dataset_name]
    seen_signatures = set()

    for idx, row in enumerate(rows, start=1):
        row_label = f"{dataset_name} row {idx}"

        for field in required_fields:
            if normalize_value(row.get(field, "")) == "":
                errors.append(f"{row_label}: missing required field `{field}`")

        doi = normalize_value(row.get("study_doi", ""))
        openalex_id = normalize_value(row.get("openalex_id", ""))
        if not doi and not openalex_id:
            errors.append(f"{row_label}: must include `study_doi` or `openalex_id`")

        if doi and not DOI_RE.match(doi):
            errors.append(f"{row_label}: invalid DOI format `{doi}`")

        for field, allowed in enum_map.items():
            value = normalize_value(row.get(field, ""))
            if value and value not in allowed:
                errors.append(
                    f"{row_label}: invalid `{field}` value `{value}` (allowed: {sorted(allowed)})"
                )

        year_text = normalize_value(row.get("study_year", ""))
        try:
            year_val = int(year_text)
            if year_val < 1900 or year_val > now_year + 1:
                errors.append(f"{row_label}: study_year `{year_val}` outside expected range")
        except ValueError:
            errors.append(f"{row_label}: study_year `{year_text}` is not an integer")

        if dataset_name == "mechanistic":
            for field in ["affinity_value"]:
                value = normalize_value(row.get(field, ""))
                try:
                    float(value)
                except ValueError:
                    errors.append(f"{row_label}: `{field}` must be numeric, got `{value}`")

            target = normalize_value(row.get("target", ""))
            allowed_targets = set(allowlists.get("allowed_targets", []))
            if allowed_targets and not is_allowed_with_alias(target, allowed_targets, TARGET_ALIASES):
                errors.append(f"{row_label}: target `{target}` not in allowlist")
            registered_targets = entity_registry.get("targets", set())
            if registered_targets and target not in registered_targets:
                warnings.append(f"{row_label}: target `{target}` not in entity registry")
                registry_missing_counter["target"] += 1

        if dataset_name == "disorder":
            disorder = normalize_value(row.get("disorder", ""))
            disorder_canonical = canonicalize_disorder(disorder)
            allowed_disorders = set(allowlists.get("allowed_disorders", []))
            if allowed_disorders and disorder_canonical not in allowed_disorders:
                errors.append(f"{row_label}: disorder `{disorder}` not in allowlist")
            registered_disorders = entity_registry.get("disorders", set())
            if registered_disorders and disorder_canonical not in registered_disorders:
                warnings.append(f"{row_label}: disorder `{disorder_canonical or disorder}` not in entity registry")
                registry_missing_counter["disorder"] += 1

        compound = normalize_value(row.get("compound", ""))
        allowed_compounds = set(allowlists.get("allowed_compounds", []))
        if allowed_compounds and compound not in allowed_compounds:
            errors.append(f"{row_label}: compound `{compound}` not in allowlist")
        registered_compounds = entity_registry.get("compounds", set())
        if registered_compounds and compound not in registered_compounds:
            warnings.append(f"{row_label}: compound `{compound}` not in entity registry")
            registry_missing_counter["compound"] += 1

        access_level = normalize_value(row.get("access_level", ""))
        evidence_location = normalize_value(row.get("evidence_location", ""))
        source_type = normalize_value(row.get("source_type", ""))
        paper_type = normalize_value(row.get("paper_type", ""))
        evidence_locator = normalize_value(row.get("evidence_locator", ""))
        authors = normalize_value(row.get("authors", ""))

        if access_level == "abstract_only" and evidence_location != "abstract":
            warnings.append(
                f"{row_label}: access_level is abstract_only but evidence_location is `{evidence_location}`"
            )

        if access_level == "secondary_summary":
            warnings.append(f"{row_label}: secondary_summary row is weak evidence for the primary graph")

        if evidence_location == "unknown":
            warnings.append(f"{row_label}: evidence_location is unknown")

        if evidence_locator.lower() in {"", "unspecified", "unknown", "n/a"}:
            warnings.append(f"{row_label}: evidence_locator is weak (`{evidence_locator}`)")

        if evidence_locator.lower().startswith("metadata/title snippet:"):
            warnings.append(f"{row_label}: metadata/title-only evidence locator")

        if access_level == "full_text_seen" and evidence_locator.lower().startswith("abstract snippet:"):
            warnings.append(f"{row_label}: full_text_seen row still uses abstract snippet locator")

        if source_type and source_type != "primary_study":
            warnings.append(f"{row_label}: source_type is `{source_type}` not primary_study")

        if source_type == "review" and normalize_value(row.get("evidence_level", "")) == "high":
            warnings.append(f"{row_label}: high evidence claim sourced as review")

        if paper_type != "primary_results" and normalize_value(row.get("evidence_level", "")) == "high":
            warnings.append(f"{row_label}: high evidence claim uses weak paper_type `{paper_type}`")

        if paper_type != "primary_results" and source_type == "primary_study":
            warnings.append(f"{row_label}: source_type is primary_study but paper_type is `{paper_type}`")

        if not authors or authors.lower() in {"unknown", "not available", "tbd", "n/a"}:
            warnings.append(f"{row_label}: authors missing or unresolved (`{authors}`)")

        study_title = normalize_value(row.get("study_title", ""))
        for pattern_name, pattern in TITLE_WARNING_PATTERNS:
            if pattern.search(study_title):
                warnings.append(f"{row_label}: study_title indicates `{pattern_name}`")
                break

        if dataset_name == "disorder":
            result_direction = normalize_value(row.get("result_direction", ""))
            if paper_type == "protocol" and result_direction not in {"", "unclear"}:
                warnings.append(f"{row_label}: protocol row has result_direction `{result_direction}`")
            result_direction_counter[result_direction] += 1

        row_for_sig = dict(row)
        if dataset_name == "disorder":
            disorder_sig = normalize_value(row_for_sig.get("disorder", ""))
            canonical_disorder = canonicalize_disorder(disorder_sig)
            if canonical_disorder:
                row_for_sig["disorder"] = canonical_disorder
        signature = canonical_signature(row_for_sig, dedupe_keys)
        if signature in seen_signatures:
            warnings.append(f"{row_label}: potential duplicate claim signature")
        seen_signatures.add(signature)

        source_type_counter[source_type] += 1
        paper_type_counter[paper_type] += 1
        access_counter[access_level] += 1
        evidence_counter[normalize_value(row.get("evidence_level", ""))] += 1
        design_counter[normalize_value(row.get("study_design", ""))] += 1

    metrics = {
        "rows": len(rows),
        "source_type_counts": dict(source_type_counter),
        "paper_type_counts": dict(paper_type_counter),
        "access_level_counts": dict(access_counter),
        "evidence_level_counts": dict(evidence_counter),
        "study_design_counts": dict(design_counter),
        "result_direction_counts": dict(result_direction_counter) if dataset_name == "disorder" else {},
        "entity_registry_missing_counts": dict(registry_missing_counter),
        "warning_group_counts": dict(Counter(warning_group(warning) for warning in warnings)),
        "warnings_count": len(warnings),
        "errors_count": len(errors),
    }
    return errors, warnings, metrics


def compare_csv_json(csv_rows: List[dict], json_rows: List[dict], dataset_name: str) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    if len(csv_rows) != len(json_rows):
        errors.append(
            f"{dataset_name}: CSV row count ({len(csv_rows)}) != JSON row count ({len(json_rows)})"
        )

    csv_keys = {key for row in csv_rows for key in row.keys()}
    json_keys = {key for row in json_rows for key in row.keys()}
    all_keys = sorted(csv_keys | json_keys)
    required_presence = {"compound", "study_year", "evidence_level", "source"}
    for field in required_presence:
        if field not in csv_keys or field not in json_keys:
            errors.append(f"{dataset_name}: required key `{field}` missing in CSV or JSON")

    csv_sigs = Counter(canonical_signature(row, all_keys) for row in csv_rows)
    json_sigs = Counter(canonical_signature(row, all_keys) for row in json_rows)

    if csv_sigs != json_sigs:
        errors.append(f"{dataset_name}: CSV and JSON content mismatch")
        missing_in_json = list((csv_sigs - json_sigs).elements())[:3]
        missing_in_csv = list((json_sigs - csv_sigs).elements())[:3]
        if missing_in_json:
            warnings.append(f"{dataset_name}: sample missing in JSON: {missing_in_json}")
        if missing_in_csv:
            warnings.append(f"{dataset_name}: sample missing in CSV: {missing_in_csv}")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate curated KG claim datasets")
    parser.add_argument(
        "--config",
        default=str(ROOT / "pipeline" / "config.example.yaml"),
        help="Path to pipeline YAML config with allowlists",
    )
    parser.add_argument(
        "--report",
        default=str(ROOT / "data" / "processed" / "validation_report.json"),
        help="Output path for machine-readable validation report",
    )
    parser.add_argument(
        "--entity-registry",
        default=str(ENTITY_REGISTRY_PATH),
        help="Optional entity registry JSON used for warning-level coverage checks",
    )
    parser.add_argument(
        "--fail-on-warning-groups",
        default="",
        help=(
            "Comma-separated warning groups that should fail validation; use `all` to fail on any warning. "
            "Useful groups include secondary_summary, metadata_title_only, unknown_evidence_location, "
            "full_text_uses_abstract_locator, non_primary_title_pattern, and duplicate_claim_signature."
        ),
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    report_path = Path(args.report)
    entity_registry_path = Path(args.entity_registry)

    mechanistic_json_path = ROOT / "data" / "curated" / "claims.json"
    mechanistic_csv_path = ROOT / "data" / "curated" / "claims.csv"
    disorder_json_path = ROOT / "data" / "curated" / "disorder_claims.json"
    disorder_csv_path = ROOT / "data" / "curated" / "disorder_claims.csv"

    mechanistic_schema = load_schema(ROOT / "schema" / "claims.schema.json")
    disorder_schema = load_schema(ROOT / "schema" / "disorder_claims.schema.json")
    allowlists = parse_allowlists(config_path)
    entity_registry = load_entity_registry(entity_registry_path)

    mech_json_rows = load_json_array(mechanistic_json_path)
    mech_csv_rows = load_csv_rows(mechanistic_csv_path)
    dis_json_rows = load_json_array(disorder_json_path)
    dis_csv_rows = load_csv_rows(disorder_csv_path)

    mech_errors, mech_warnings, mech_metrics = validate_dataset(
        "mechanistic", mech_json_rows, mechanistic_schema, allowlists, entity_registry
    )
    dis_errors, dis_warnings, dis_metrics = validate_dataset(
        "disorder", dis_json_rows, disorder_schema, allowlists, entity_registry
    )

    mech_cross_errors, mech_cross_warnings = compare_csv_json(
        mech_csv_rows, mech_json_rows, "mechanistic"
    )
    dis_cross_errors, dis_cross_warnings = compare_csv_json(
        dis_csv_rows, dis_json_rows, "disorder"
    )

    all_errors = mech_errors + dis_errors + mech_cross_errors + dis_cross_errors
    all_warnings = mech_warnings + dis_warnings + mech_cross_warnings + dis_cross_warnings
    fail_warning_groups = {
        value.strip()
        for value in args.fail_on_warning_groups.split(",")
        if value.strip()
    }
    strict_warning_failures = []
    if fail_warning_groups:
        strict_warning_failures = [
            warning
            for warning in all_warnings
            if "all" in fail_warning_groups or warning_group(warning) in fail_warning_groups
        ]

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "ok" if not all_errors and not strict_warning_failures else "failed",
        "inputs": {
            "config": str(config_path),
            "entity_registry": str(entity_registry_path),
            "fail_on_warning_groups": sorted(fail_warning_groups),
        },
        "datasets": {
            "mechanistic": {
                "metrics": mech_metrics,
                "errors": mech_errors,
                "warnings": mech_warnings,
            },
            "disorder": {
                "metrics": dis_metrics,
                "errors": dis_errors,
                "warnings": dis_warnings,
            },
        },
        "cross_checks": {
            "mechanistic": {
                "errors": mech_cross_errors,
                "warnings": mech_cross_warnings,
            },
            "disorder": {
                "errors": dis_cross_errors,
                "warnings": dis_cross_warnings,
            },
        },
        "totals": {
            "errors": len(all_errors),
            "warnings": len(all_warnings),
            "strict_warning_failures": len(strict_warning_failures),
            "warning_group_counts": dict(Counter(warning_group(warning) for warning in all_warnings)),
        },
        "strict_warning_failures": strict_warning_failures,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Validation report written:", report_path)
    print("Mechanistic rows:", mech_metrics["rows"])
    print("Disorder rows:", dis_metrics["rows"])
    print("Errors:", len(all_errors))
    print("Warnings:", len(all_warnings))
    if fail_warning_groups:
        print("Strict warning failures:", len(strict_warning_failures))

    if all_errors:
        print("\nTop errors:")
        for line in all_errors[:20]:
            print("-", line)

    if all_warnings:
        print("\nTop warnings:")
        for line in all_warnings[:20]:
            print("-", line)

    if strict_warning_failures:
        print("\nTop strict warning failures:")
        for line in strict_warning_failures[:20]:
            print("-", line)

    return 1 if all_errors or strict_warning_failures else 0


if __name__ == "__main__":
    sys.exit(main())
