#!/usr/bin/env python3
"""Autofill stub fields using paper titles/abstracts and optionally mark ready."""

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

DATASET_CONFIG = {
    "mechanistic": {
        "stubs_json": ROOT / "data" / "processed" / "mechanistic_claim_stubs.json",
        "stubs_csv": ROOT / "data" / "processed" / "mechanistic_claim_stubs.csv",
        "paper_db_json": ROOT / "data" / "processed" / "paper_library_mechanistic.json",
        "schema": ROOT / "schema" / "claims.schema.json",
    },
    "disorder": {
        "stubs_json": ROOT / "data" / "processed" / "disorder_claim_stubs.json",
        "stubs_csv": ROOT / "data" / "processed" / "disorder_claim_stubs.csv",
        "paper_db_json": ROOT / "data" / "processed" / "paper_library_disorder.json",
        "schema": ROOT / "schema" / "disorder_claims.schema.json",
    },
}

OUTCOME_MEASURE_PATTERNS = [
    ("madrs", "MADRS"),
    ("hamd", "HAM-D"),
    ("ham d", "HAM-D"),
    ("phq 9", "PHQ-9"),
    ("bdi", "BDI"),
    ("caps 5", "CAPS-5"),
    ("caps-5", "CAPS-5"),
    ("pcl 5", "PCL-5"),
    ("pcl-5", "PCL-5"),
    ("heavy drinking days", "Percent heavy drinking days"),
    ("abstinence", "Abstinence rate"),
]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_doi(raw: str) -> str:
    text = normalize(raw)
    if not text:
        return ""
    if text.lower().startswith("doi:"):
        text = text[4:]
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
    ):
        if text.lower().startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip()


def normalize_text(raw: str) -> str:
    lowered = normalize(raw).lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


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


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: List[dict]) -> None:
    fieldnames = sorted({k for row in rows for k in row.keys()}) if rows else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_schema(schema: dict) -> Tuple[List[str], Dict[str, Set[str]], Dict[str, str], List[Set[str]], Set[str]]:
    item = schema["items"]
    required = list(item.get("required", []))
    properties = item.get("properties", {})

    enums: Dict[str, Set[str]] = {}
    types: Dict[str, str] = {}
    for key, prop in properties.items():
        if "enum" in prop:
            enums[key] = set(prop["enum"])
        if "type" in prop:
            types[key] = prop["type"]

    one_of_groups: List[Set[str]] = []
    for group in item.get("oneOf", []):
        if isinstance(group, dict) and "required" in group:
            one_of_groups.append(set(group["required"]))

    return required, enums, types, one_of_groups, set(properties.keys())


def is_valid_type(raw_value: str, expected_type: str) -> bool:
    if raw_value == "":
        return True
    if expected_type == "integer":
        try:
            int(float(raw_value))
            return True
        except Exception:
            return False
    if expected_type == "number":
        try:
            float(raw_value)
            return True
        except Exception:
            return False
    return True


def evaluate_row(
    row: dict,
    required: List[str],
    enums: Dict[str, Set[str]],
    types: Dict[str, str],
    one_of_groups: List[Set[str]],
    allowed_keys: Set[str],
) -> Tuple[List[str], List[dict]]:
    blocker_fields: Set[str] = set()
    blockers: List[dict] = []

    cleaned = {k: row.get(k, "") for k in allowed_keys}

    for field in required:
        if normalize(cleaned.get(field, "")) == "":
            blocker_fields.add(field)
            blockers.append({"field": field, "reason": "missing_required"})

    if one_of_groups:
        any_group_satisfied = any(
            any(normalize(cleaned.get(field, "")) for field in group)
            for group in one_of_groups
        )
        if not any_group_satisfied:
            merged = "|".join(sorted({field for group in one_of_groups for field in group}))
            blocker_fields.add(merged)
            blockers.append({"field": merged, "reason": "missing_one_of"})

    for field, allowed in enums.items():
        value = normalize(cleaned.get(field, ""))
        if value and value not in allowed:
            blocker_fields.add(field)
            blockers.append({"field": field, "reason": "invalid_enum", "value": value})

    for field, expected in types.items():
        value = normalize(cleaned.get(field, ""))
        if not is_valid_type(value, expected):
            blocker_fields.add(field)
            blockers.append({"field": field, "reason": "invalid_type", "value": value, "expected": expected})

    return sorted(blocker_fields), blockers


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


def is_weak_locator(value: str) -> bool:
    lowered = normalize(value).lower()
    return lowered in {"", "unspecified", "unknown", "n/a", "na", "not specified"}


def text_snippet(text: str, max_chars: int = 180) -> str:
    cleaned = normalize(" ".join(normalize(text).split()))
    if not cleaned:
        return ""
    return cleaned[:max_chars].rstrip()


def infer_study_design(source_type: str, text_norm: str) -> str:
    if source_type == "meta_analysis":
        return "meta_analysis"
    if source_type == "review":
        return "systematic_review" if "systematic review" in text_norm else "review"
    if "randomized" in text_norm or "double blind" in text_norm or "double blind" in text_norm:
        return "randomized_controlled_trial"
    if "phase 3" in text_norm:
        return "phase_3_trial"
    if "phase 2" in text_norm:
        return "phase_2_trial"
    if "open label" in text_norm or "open-label" in text_norm:
        return "open_label_trial"
    if "pilot" in text_norm:
        return "pilot_trial"
    if "cohort" in text_norm or "cross sectional" in text_norm or "observational" in text_norm:
        return "observational_study"
    if "rat" in text_norm or "mice" in text_norm or "mouse" in text_norm:
        return "preclinical_study"
    return "pending_curation"


def infer_evidence_level(source_type: str, study_design: str, text_norm: str, current: str) -> str:
    cur = normalize(current)
    if cur in {"high", "medium", "low"} and cur != "low":
        return cur
    if source_type in {"review", "meta_analysis"}:
        return "medium"
    if study_design in {"randomized_controlled_trial", "phase_3_trial"}:
        return "high"
    if study_design in {"phase_2_trial", "open_label_trial", "pilot_trial"}:
        return "medium"
    if "case report" in text_norm or "retrospective" in text_norm:
        return "low"
    return cur if cur in {"high", "medium", "low"} else "low"


def infer_system(text_norm: str, current: str) -> str:
    cur = normalize(current)
    if cur and cur != "unknown":
        return cur
    if "rat" in text_norm or "mouse" in text_norm or "mice" in text_norm or "rodent" in text_norm:
        return "preclinical"
    if "cohort" in text_norm or "cross sectional" in text_norm or "observational" in text_norm:
        return "observational"
    if "trial" in text_norm or "patients" in text_norm or "participants" in text_norm or "adults" in text_norm:
        return "clinical"
    return "unknown"


def infer_outcome_type(disorder: str, text_norm: str, current: str) -> str:
    cur = normalize(current)
    if cur:
        return cur

    d = normalize(disorder).lower()
    negative = any(phrase in text_norm for phrase in {"no significant", "not significant", "did not improve"})

    if "post-traumatic stress disorder" in d or "ptsd" in d:
        return "no significant change in PTSD severity" if negative else "reduces PTSD severity"
    if "treatment-resistant depression" in d or "major depressive disorder" in d or "depression" in d:
        return "no significant change in depressive symptoms" if negative else "reduces depressive symptoms"
    if "alcohol use disorder" in d:
        return "no significant change in alcohol use outcomes" if negative else "reduces heavy drinking outcomes"
    if "tobacco use disorder" in d:
        return "no significant change in tobacco outcomes" if negative else "supports smoking abstinence"
    if "anxiety" in d or "distress associated with life-threatening disease" in d or "life-threatening disease" in d:
        return "no significant change in anxiety/depression symptoms" if negative else "reduces anxiety/depression symptoms"
    return "no significant clinical change" if negative else "improves clinical symptoms"


def infer_outcome_measure(text_norm: str, current: str) -> str:
    cur = normalize(current)
    if cur:
        return cur
    for token, label in OUTCOME_MEASURE_PATTERNS:
        if token in text_norm:
            return label
    return ""


def infer_population(disorder: str, text_norm: str, current: str) -> str:
    cur = normalize(current)
    if cur:
        return cur
    disorder_text = normalize(disorder).lower()
    if "adolescent" in text_norm or "children" in text_norm:
        return f"adolescents with {disorder_text}"
    if "adult" in text_norm or "participants" in text_norm or "patients" in text_norm:
        return f"adults with {disorder_text}"
    return ""


def infer_mechanistic_assay_type(text_norm: str, current: str) -> str:
    cur = normalize(current)
    if cur:
        return cur
    if "radioligand" in text_norm or "binding" in text_norm:
        return "radioligand binding"
    if "uptake" in text_norm or "transporter" in text_norm:
        return "uptake inhibition"
    if "agonist" in text_norm or "antagonist" in text_norm or "activation" in text_norm:
        return "functional assay"
    return ""


def infer_mechanistic_system(text_norm: str, current: str) -> str:
    cur = normalize(current)
    if cur and cur != "unknown":
        return cur
    if "in vitro" in text_norm or "cloned" in text_norm or "cell line" in text_norm:
        return "in_vitro"
    if "in vivo" in text_norm:
        return "in_vivo"
    if "ex vivo" in text_norm:
        return "ex_vivo"
    return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description="Autofill stubs from paper-library abstracts")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument("--status-filter", default="pending_curation", help="Only process rows with this status")
    parser.add_argument("--all-statuses", action="store_true", help="Ignore status filter")
    parser.add_argument("--apply", action="store_true", help="Write updates to stub files")
    parser.add_argument("--mark-ready", action="store_true", help="Set clean rows to ready_for_promotion")
    parser.add_argument(
        "--report",
        default="",
        help="Optional report path (defaults to data/processed/abstract_autofill_report_<dataset>.json)",
    )
    args = parser.parse_args()

    cfg = DATASET_CONFIG[args.dataset]
    report_path = (
        Path(args.report).resolve()
        if args.report
        else ROOT / "data" / "processed" / f"abstract_autofill_report_{args.dataset}.json"
    )

    stubs = load_json_array(cfg["stubs_json"])
    paper_db = load_json_array(cfg["paper_db_json"])
    schema = load_schema(cfg["schema"])
    required, enums, types, one_of_groups, allowed_keys = parse_schema(schema)

    paper_by_doi: Dict[str, dict] = {}
    for row in paper_db:
        doi = normalize_doi(row.get("study_doi", "")).lower()
        if doi:
            paper_by_doi[doi] = row

    considered = 0
    matched = 0
    updated = 0
    ready = 0
    rows_report = []
    out_rows = []

    for idx, stub in enumerate(stubs, start=1):
        status = normalize(stub.get("stub_status", ""))
        if not args.all_statuses and status != args.status_filter:
            out_rows.append(stub)
            continue

        # Skip explicit exclusions by default.
        if status == "excluded_not_relevant":
            out_rows.append(stub)
            continue

        considered += 1
        doi = normalize_doi(stub.get("study_doi", "")).lower()
        paper = paper_by_doi.get(doi)
        if not paper:
            out_rows.append(stub)
            rows_report.append(
                {
                    "stub_index": idx,
                    "study_doi": normalize(stub.get("study_doi", "")),
                    "matched_paper": False,
                    "changed_fields": [],
                    "blockers_after": ["paper_not_found"],
                }
            )
            continue

        matched += 1
        new_row = dict(stub)
        changed_fields: List[str] = []

        title = normalize(paper.get("study_title", ""))
        abstract = normalize(paper.get("abstract", ""))
        text_norm = normalize_text(f"{title} {abstract}")
        source_type = normalize(new_row.get("source_type", ""))

        # Generic metadata backfill.
        for key_stub, key_paper in (
            ("study_title", "study_title"),
            ("authors", "authors"),
            ("study_year", "study_year"),
        ):
            if not normalize(new_row.get(key_stub, "")) and normalize(paper.get(key_paper, "")):
                new_row[key_stub] = paper.get(key_paper, "")
                changed_fields.append(key_stub)

        # Abstract-first provenance.
        if abstract:
            if normalize(new_row.get("access_level", "")) != "full_text_seen":
                if normalize(new_row.get("access_level", "")) != "abstract_only":
                    new_row["access_level"] = "abstract_only"
                    changed_fields.append("access_level")
            if normalize(new_row.get("evidence_location", "")) != "abstract":
                new_row["evidence_location"] = "abstract"
                changed_fields.append("evidence_location")
            if is_weak_locator(new_row.get("evidence_locator", "")):
                snippet = text_snippet(abstract, max_chars=170)
                new_row["evidence_locator"] = f"Abstract snippet: {snippet}" if snippet else "Abstract"
                changed_fields.append("evidence_locator")
            new_notes = append_note(new_row.get("notes", ""), "Abstract-first autofill from paper metadata")
            if normalize(new_notes) != normalize(new_row.get("notes", "")):
                new_row["notes"] = new_notes
                changed_fields.append("notes")
        else:
            if is_weak_locator(new_row.get("evidence_locator", "")):
                title_snippet = text_snippet(title, max_chars=150)
                if title_snippet:
                    new_row["evidence_locator"] = f"Metadata/title snippet: {title_snippet}"
                else:
                    new_row["evidence_locator"] = "Metadata record (no abstract text available)"
                changed_fields.append("evidence_locator")

        if args.dataset == "disorder":
            inferred_outcome_type = infer_outcome_type(new_row.get("disorder", ""), text_norm, new_row.get("outcome_type", ""))
            if inferred_outcome_type and normalize(new_row.get("outcome_type", "")) != inferred_outcome_type:
                new_row["outcome_type"] = inferred_outcome_type
                changed_fields.append("outcome_type")

            inferred_measure = infer_outcome_measure(text_norm, new_row.get("outcome_measure", ""))
            if inferred_measure and normalize(new_row.get("outcome_measure", "")) != inferred_measure:
                new_row["outcome_measure"] = inferred_measure
                changed_fields.append("outcome_measure")

            inferred_population = infer_population(new_row.get("disorder", ""), text_norm, new_row.get("population", ""))
            if inferred_population and normalize(new_row.get("population", "")) != inferred_population:
                new_row["population"] = inferred_population
                changed_fields.append("population")

            inferred_design = infer_study_design(source_type, text_norm)
            if normalize(new_row.get("study_design", "")).lower() in {"", "pending_curation", "unknown", "unspecified"}:
                if inferred_design and normalize(new_row.get("study_design", "")) != inferred_design:
                    new_row["study_design"] = inferred_design
                    changed_fields.append("study_design")

            inferred_system = infer_system(text_norm, new_row.get("system", ""))
            if inferred_system and normalize(new_row.get("system", "")) != inferred_system:
                new_row["system"] = inferred_system
                changed_fields.append("system")

            inferred_level = infer_evidence_level(
                source_type=source_type,
                study_design=normalize(new_row.get("study_design", "")),
                text_norm=text_norm,
                current=normalize(new_row.get("evidence_level", "")),
            )
            if inferred_level and normalize(new_row.get("evidence_level", "")) != inferred_level:
                new_row["evidence_level"] = inferred_level
                changed_fields.append("evidence_level")
        else:
            inferred_assay = infer_mechanistic_assay_type(text_norm, new_row.get("assay_type", ""))
            if inferred_assay and normalize(new_row.get("assay_type", "")) != inferred_assay:
                new_row["assay_type"] = inferred_assay
                changed_fields.append("assay_type")

            inferred_design = infer_study_design(source_type, text_norm)
            if normalize(new_row.get("study_design", "")).lower() in {"", "pending_curation", "unknown", "unspecified"}:
                if inferred_design and normalize(new_row.get("study_design", "")) != inferred_design:
                    new_row["study_design"] = inferred_design
                    changed_fields.append("study_design")

            inferred_system = infer_mechanistic_system(text_norm, new_row.get("system", ""))
            if inferred_system and normalize(new_row.get("system", "")) != inferred_system:
                new_row["system"] = inferred_system
                changed_fields.append("system")

            inferred_level = infer_evidence_level(
                source_type=source_type,
                study_design=normalize(new_row.get("study_design", "")),
                text_norm=text_norm,
                current=normalize(new_row.get("evidence_level", "")),
            )
            if inferred_level and normalize(new_row.get("evidence_level", "")) != inferred_level:
                new_row["evidence_level"] = inferred_level
                changed_fields.append("evidence_level")

        blocker_fields, blockers = evaluate_row(
            row=new_row,
            required=required,
            enums=enums,
            types=types,
            one_of_groups=one_of_groups,
            allowed_keys=allowed_keys,
        )

        if args.mark_ready and not blockers:
            if normalize(new_row.get("stub_status", "")) != "ready_for_promotion":
                new_row["stub_status"] = "ready_for_promotion"
                changed_fields.append("stub_status")
                ready += 1

        if changed_fields:
            updated += 1

        rows_report.append(
            {
                "stub_index": idx,
                "study_doi": normalize(stub.get("study_doi", "")),
                "matched_paper": True,
                "changed_fields": sorted(set(changed_fields)),
                "blocker_count_after": len(blockers),
                "blocker_fields_after": blocker_fields,
            }
        )
        out_rows.append(new_row)

    report = {
        "generated_at": now_utc(),
        "dataset": args.dataset,
        "status_filter": "*" if args.all_statuses else args.status_filter,
        "mark_ready": args.mark_ready,
        "apply": args.apply,
        "counts": {
            "stubs_total": len(stubs),
            "considered": considered,
            "matched_paper": matched,
            "updated_rows": updated,
            "marked_ready": ready,
        },
        "rows": rows_report,
    }

    if args.apply:
        write_json(cfg["stubs_json"], out_rows)
        write_csv(cfg["stubs_csv"], out_rows)

    write_json(report_path, report)
    print(f"Dataset: {args.dataset}")
    print(f"Considered rows: {considered}")
    print(f"Matched paper rows: {matched}")
    print(f"Updated rows: {updated}")
    if args.mark_ready:
        print(f"Marked ready: {ready}")
    if args.apply:
        print(f"Stubs JSON: {cfg['stubs_json']}")
        print(f"Stubs CSV: {cfg['stubs_csv']}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
