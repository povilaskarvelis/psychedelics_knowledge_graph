#!/usr/bin/env python3
"""Normalize projected extraction-v1 claims against the local entity registry."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import difflib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

try:
    from pipeline.extract.extraction_v1_utils import normalize, write_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.extraction_v1_utils import normalize, write_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_DIR = ROOT / "data" / "processed" / "extraction"
DEFAULT_REGISTRY_PATH = ROOT / "data" / "curated" / "entity_registry.json"
DEFAULT_DISORDER_ALIASES_PATH = ROOT / "schema" / "disorder_canonicalization.json"

GRAPH_TRUE_VALUES = {"true", "1", "yes", "y"}
EMPTY_ENTITY_VALUES = {"", "none", "not applicable", "not_applicable", "not reported", "not_reported", "uncertain"}
CLASS_LEVEL_COMPOUND_RE = re.compile(
    r"\b("
    r"classic(?:al)?\s+psychedelics?|"
    r"serotonergic\s+psychedelics?|"
    r"psychedelic(?:[- ]assisted)?\s+(?:medicines?|drugs?|substances?|compounds?|therap(?:y|ies))|"
    r"psychedelics?|"
    r"hallucinogenic\s+drugs?|"
    r"hallucinogens?|"
    r"arylcyclohexylamines?|"
    r"synthetic\s+cathinones?|"
    r"iboga\s+alkaloids?|"
    r"nbome\s+drugs?|"
    r"5[-\s]*ht2a?r?\s+agonists?"
    r")\b",
    re.IGNORECASE,
)
REFERENCE_CONTROL_COMPOUND_KEYS = {
    "5 ht",
    "5 hydroxytryptamine",
    "8 oh dpat",
    "clozapine",
    "d serine",
    "ifenprodil",
    "ketanserin",
    "m100907",
    "memantine",
    "methysergide",
    "mk 801",
    "pcp",
    "phencyclidine",
    "phencyclidine pcp",
    "ritanserin",
    "serotonin",
    "way100635",
}
NON_GRAPH_ENTITY_ROLES = {
    "physiological_measure",
    "safety_or_adverse_event",
    "biomarker",
    "population_or_context",
    "gene_or_variant",
    "pathway_or_process",
    "brain_region_or_circuit",
    "assay_readout",
    "compound_or_class",
}
DISORDER_GRAPH_ROLES = {
    "therapeutic_indication",
    "symptom_or_problem",
    "outcome_measure",
    "functional_outcome",
    "patient_reported_outcome",
    "uncertain",
    "",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json_array(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return [row for row in data if isinstance(row, dict)]


def load_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def ascii_fold(value: object) -> str:
    text = normalize(value)
    text = unicodedata.normalize("NFKD", text)
    return text.encode("ascii", "ignore").decode("ascii")


def label_key(value: object) -> str:
    text = ascii_fold(value).casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compact_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", label_key(value))


def clean_ids(ids: object) -> dict:
    if not isinstance(ids, dict):
        return {}
    return {normalize(key): normalize(value) for key, value in ids.items() if normalize(key) and normalize(value)}


def registry_entries(registry: dict, disorder_aliases: dict) -> dict[str, list[dict]]:
    entries: dict[str, list[dict]] = {"compounds": [], "targets": [], "disorders": []}
    for category in entries:
        for item in registry.get(category, []):
            if not isinstance(item, dict):
                continue
            label = normalize(item.get("label", ""))
            if not label:
                continue
            aliases = [normalize(alias) for alias in item.get("aliases", []) if normalize(alias)]
            if category == "disorders":
                aliases.extend(normalize(alias) for alias in disorder_aliases.get(label, []) if normalize(alias))
            entries[category].append(
                {
                    "category": category,
                    "label": label,
                    "aliases": sorted(set(aliases)),
                    "ids": clean_ids(item.get("ids", {})),
                    "registry_status": normalize(item.get("status", "")),
                }
            )
    return entries


def target_variants(label: str) -> list[str]:
    variants = []
    if re.fullmatch(r"5-HT\d[A-Z]?", label, flags=re.IGNORECASE):
        variants.append(f"{label} receptor")
    match = re.match(r"^(.+?)\s*\((.+?)\)$", label)
    if match:
        variants.extend([match.group(1), match.group(2), f"{match.group(1)} {match.group(2)}"])
    return variants


def key_variants(value: object, category: str = "") -> list[tuple[str, str]]:
    text = normalize(value)
    if not text:
        return []
    variants: list[tuple[str, str]] = [(text, "label")]
    no_parenthetical = re.sub(r"\([^)]*\)", " ", text)
    if normalize(no_parenthetical) and label_key(no_parenthetical) != label_key(text):
        variants.append((no_parenthetical, "without_parenthetical"))
    for inside in re.findall(r"\(([^)]*)\)", text):
        if normalize(inside):
            variants.append((inside, "parenthetical"))
    if category == "targets":
        variants.extend((variant, "target_variant") for variant in target_variants(text))

    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for variant, variant_type in variants:
        key = label_key(variant)
        compact = compact_key(variant)
        for candidate_key, key_type in ((key, variant_type), (compact, f"{variant_type}_compact")):
            if candidate_key and (candidate_key, key_type) not in seen:
                seen.add((candidate_key, key_type))
                out.append((candidate_key, key_type))
    return out


def build_index(entries_by_category: dict[str, list[dict]]) -> dict:
    index: dict[str, dict] = {}
    for category, entries in entries_by_category.items():
        key_to_entries: dict[str, list[dict]] = defaultdict(list)
        key_sources: dict[tuple[str, str], str] = {}
        for entry in entries:
            labels = [(entry["label"], "label")] + [(alias, "alias") for alias in entry.get("aliases", [])]
            if category == "targets":
                labels.extend((variant, "target_variant") for variant in target_variants(entry["label"]))
            for value, source in labels:
                for key, key_type in key_variants(value, category):
                    key_to_entries[key].append(entry)
                    key_sources[(key, entry["label"])] = source if key_type.startswith("label") else key_type
        index[category] = {
            "entries": entries,
            "key_to_entries": key_to_entries,
            "key_sources": key_sources,
        }
    return index


def unique_key_match(category_index: dict, key: str) -> dict | None:
    matches = category_index["key_to_entries"].get(key, [])
    labels = {match["label"] for match in matches}
    if len(labels) != 1:
        return None
    return matches[0]


def exact_registry_match(value: object, category_index: dict) -> tuple[dict | None, str]:
    key = label_key(value)
    label_matches = [entry for entry in category_index["entries"] if label_key(entry["label"]) == key]
    label_names = {entry["label"] for entry in label_matches}
    if len(label_names) == 1:
        return label_matches[0], "label"

    alias_matches = [
        entry
        for entry in category_index["entries"]
        if any(label_key(alias) == key for alias in entry.get("aliases", []))
    ]
    alias_names = {entry["label"] for entry in alias_matches}
    if len(alias_names) == 1:
        return alias_matches[0], "alias"
    return None, ""


def fuzzy_match(value: object, category: str, category_index: dict) -> tuple[dict | None, float, str]:
    if category in {"compounds", "targets"}:
        return None, 0.0, ""
    key = label_key(value)
    if len(key) < 8:
        return None, 0.0, ""
    best_entry = None
    best_score = 0.0
    best_value = ""
    for entry in category_index["entries"]:
        for candidate in [entry["label"], *entry.get("aliases", [])]:
            candidate_key = label_key(candidate)
            if len(candidate_key) < 8:
                continue
            score = difflib.SequenceMatcher(None, key, candidate_key).ratio()
            if score > best_score:
                best_entry = entry
                best_score = score
                best_value = candidate
    if best_entry is not None and best_score >= 0.94:
        return best_entry, best_score, best_value
    return None, best_score, best_value


def empty_entity(value: object) -> bool:
    return label_key(value) in EMPTY_ENTITY_VALUES


def class_level_compound_label(value: object) -> bool:
    return bool(CLASS_LEVEL_COMPOUND_RE.search(ascii_fold(value)))


def reference_control_compound_label(value: object) -> bool:
    key = label_key(value)
    compact = compact_key(value)
    return key in REFERENCE_CONTROL_COMPOUND_KEYS or compact in {
        compact_key(item) for item in REFERENCE_CONTROL_COMPOUND_KEYS
    }


def compound_combo_label(value: object, compound_index: dict) -> bool:
    text = normalize(value)
    matched_labels = set()
    for entry in compound_index["entries"]:
        for candidate in [entry["label"], *entry.get("aliases", [])]:
            key = label_key(candidate)
            if key and re.search(rf"\b{re.escape(key)}\b", label_key(text)):
                matched_labels.add(entry["label"])
    return len(matched_labels) > 1


def resolve_entity(value: object, category: str, index: dict) -> dict:
    text = normalize(value)
    if empty_entity(text):
        return {
            "matched": False,
            "status": "not_applicable",
            "label": "",
            "ids": {},
            "registry_status": "",
            "match_type": "",
            "match_value": text,
            "candidate_label": "",
            "candidate_score": 0.0,
        }
    category_index = index[category]
    exact_match, exact_match_type = exact_registry_match(text, category_index)
    if exact_match:
        return {
            "matched": True,
            "status": "matched",
            "label": exact_match["label"],
            "ids": exact_match["ids"],
            "registry_status": exact_match["registry_status"],
            "match_type": exact_match_type,
            "match_value": text,
            "candidate_label": exact_match["label"],
            "candidate_score": 1.0,
        }
    for key, key_type in key_variants(text, category):
        match = unique_key_match(category_index, key)
        if match:
            source = category_index["key_sources"].get((key, match["label"]), key_type)
            return {
                "matched": True,
                "status": "matched",
                "label": match["label"],
                "ids": match["ids"],
                "registry_status": match["registry_status"],
                "match_type": source,
                "match_value": text,
                "candidate_label": match["label"],
                "candidate_score": 1.0,
            }

    match, score, candidate_value = fuzzy_match(text, category, category_index)
    if match:
        return {
            "matched": True,
            "status": "matched",
            "label": match["label"],
            "ids": match["ids"],
            "registry_status": match["registry_status"],
            "match_type": "fuzzy_high_confidence",
            "match_value": text,
            "candidate_label": match["label"],
            "candidate_score": round(score, 4),
        }

    return {
        "matched": False,
        "status": "unmatched",
        "label": "",
        "ids": {},
        "registry_status": "",
        "match_type": "",
        "match_value": text,
        "candidate_label": candidate_value,
        "candidate_score": round(score, 4),
    }


def bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return normalize(value).casefold() in GRAPH_TRUE_VALUES


def graph_label_for_row(row: dict, dataset: str) -> str:
    graph_label = normalize(row.get("graph_entity_label", ""))
    if not empty_entity(graph_label):
        return graph_label
    return normalize(row.get("target" if dataset == "mechanistic" else "disorder", ""))


def graph_label_candidates_for_row(row: dict, dataset: str) -> list[str]:
    candidates = []
    for value in [
        row.get("graph_entity_label", ""),
        row.get("target" if dataset == "mechanistic" else "disorder", ""),
    ]:
        text = normalize(value)
        if text and not empty_entity(text) and text not in candidates:
            candidates.append(text)
    return candidates


def expected_graph_type(dataset: str) -> str:
    return "target" if dataset == "mechanistic" else "indication"


def entity_category_for_dataset(dataset: str) -> str:
    return "targets" if dataset == "mechanistic" else "disorders"


def graph_role_allowed(row: dict, dataset: str) -> bool:
    role = normalize(row.get("entity_role", ""))
    if role in NON_GRAPH_ENTITY_ROLES:
        return False
    if dataset == "mechanistic":
        return role in {"molecular_target", "uncertain", "not_applicable", ""}
    return role in DISORDER_GRAPH_ROLES


def json_cell(value: object) -> object:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return value


def normalize_claim_row(row: dict, dataset: str, index: dict) -> tuple[dict, dict | None]:
    audit = dict(row)
    audit["normalization_dataset"] = dataset
    audit["normalization_entity_category"] = entity_category_for_dataset(dataset)
    audit["normalization_status"] = ""
    audit["normalization_notes"] = ""

    compound_match = resolve_entity(row.get("compound", ""), "compounds", index)
    entity_labels = graph_label_candidates_for_row(row, dataset)
    entity_label = entity_labels[0] if entity_labels else graph_label_for_row(row, dataset)
    entity_match = resolve_entity(entity_label, entity_category_for_dataset(dataset), index)
    for fallback_label in entity_labels[1:]:
        if entity_match["matched"]:
            break
        fallback_match = resolve_entity(fallback_label, entity_category_for_dataset(dataset), index)
        if fallback_match["matched"]:
            entity_label = fallback_label
            entity_match = fallback_match
    graph_type = normalize(row.get("graph_entity_type", ""))
    compound_policy_status = ""
    if not compound_match["matched"]:
        if class_level_compound_label(row.get("compound", "")):
            compound_policy_status = "compound_class_not_graphable"
        elif reference_control_compound_label(row.get("compound", "")):
            compound_policy_status = "compound_reference_not_graphable"
        elif compound_combo_label(row.get("compound", ""), index["compounds"]):
            compound_policy_status = "compound_combo_not_graphable"

    audit.update(
        {
            "canonical_compound": compound_match["label"],
            "canonical_entity": entity_match["label"],
            "compound_match_type": compound_match["match_type"],
            "entity_match_type": entity_match["match_type"],
            "compound_match_value": compound_match["match_value"],
            "entity_match_value": entity_match["match_value"],
            "compound_registry_status": compound_match["registry_status"],
            "entity_registry_status": entity_match["registry_status"],
            "compound_ids": compound_match["ids"],
            "entity_ids": entity_match["ids"],
            "entity_candidate_label": entity_match["candidate_label"],
            "entity_candidate_score": entity_match["candidate_score"],
        }
    )

    notes = []
    if not bool_value(row.get("graph_include_candidate", False)):
        audit["normalization_status"] = "not_graph_candidate"
        notes.append("graph_include_candidate is false")
    elif graph_type and graph_type != expected_graph_type(dataset):
        audit["normalization_status"] = "wrong_graph_entity_type"
        notes.append(f"expected graph_entity_type={expected_graph_type(dataset)}, got {graph_type}")
    elif not graph_role_allowed(row, dataset):
        audit["normalization_status"] = "non_graph_entity_role"
        notes.append(f"entity_role={normalize(row.get('entity_role', ''))} is not graph-normalizable")
    elif compound_policy_status:
        audit["normalization_status"] = compound_policy_status
        if compound_policy_status == "compound_reference_not_graphable":
            notes.append("compound is a reference/control compound; v1 graph focuses on psychedelics")
        else:
            notes.append(
                "compound is a broad class or multi-compound label; v1 graph uses specific compound nodes only"
            )
    elif not compound_match["matched"]:
        audit["normalization_status"] = "compound_unmapped"
        notes.append(f"compound `{normalize(row.get('compound', ''))}` did not match registry")
    elif not entity_match["matched"]:
        audit["normalization_status"] = "entity_unmapped"
        notes.append(f"graph entity `{entity_label}` did not match registry")
    else:
        audit["normalization_status"] = "normalized"
        notes.append("compound and graph entity matched local registry")

    audit["normalization_notes"] = "; ".join(notes)
    if audit["normalization_status"] != "normalized":
        return audit, None

    graph_row = dict(row)
    graph_row["compound_original"] = normalize(row.get("compound", ""))
    graph_row["graph_entity_original"] = entity_label
    graph_row["compound"] = compound_match["label"]
    if dataset == "mechanistic":
        graph_row["target_original"] = normalize(row.get("target", ""))
        graph_row["target"] = entity_match["label"]
    else:
        graph_row["disorder_original"] = normalize(row.get("disorder", ""))
        graph_row["disorder"] = entity_match["label"]
    graph_row.update(
        {
            "graph_entity_label": entity_match["label"],
            "graph_entity_type": expected_graph_type(dataset),
            "graph_include_candidate": True,
            "normalization_status": audit["normalization_status"],
            "normalization_notes": audit["normalization_notes"],
            "canonical_compound": compound_match["label"],
            "canonical_entity": entity_match["label"],
            "compound_match_type": compound_match["match_type"],
            "entity_match_type": entity_match["match_type"],
            "compound_registry_status": compound_match["registry_status"],
            "entity_registry_status": entity_match["registry_status"],
            "compound_ids": compound_match["ids"],
            "entity_ids": entity_match["ids"],
        }
    )
    return audit, graph_row


def normalize_claims(
    mechanistic_rows: list[dict],
    disorder_rows: list[dict],
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    disorder_aliases_path: Path = DEFAULT_DISORDER_ALIASES_PATH,
) -> tuple[dict[str, list[dict]], dict[str, list[dict]], dict]:
    registry = load_json_object(registry_path)
    disorder_aliases = load_json_object(disorder_aliases_path)
    entries = registry_entries(registry, disorder_aliases)
    index = build_index(entries)

    graph_rows = {"mechanistic": [], "disorder": []}
    audit_rows = {"mechanistic": [], "disorder": []}
    source_rows = {"mechanistic": mechanistic_rows, "disorder": disorder_rows}
    status_counts: dict[str, Counter] = {"mechanistic": Counter(), "disorder": Counter()}
    entity_counts: dict[str, Counter] = {"mechanistic": Counter(), "disorder": Counter()}

    for dataset, rows in source_rows.items():
        for row in rows:
            audit, graph_row = normalize_claim_row(row, dataset, index)
            audit_rows[dataset].append(audit)
            status_counts[dataset][audit["normalization_status"]] += 1
            if audit.get("canonical_entity"):
                entity_counts[dataset][audit["canonical_entity"]] += 1
            if graph_row is not None:
                graph_rows[dataset].append(graph_row)

    report = {
        "generated_at_utc": now_utc(),
        "schema_version": "extraction_claim_normalization_report",
        "status": "ok",
        "registry": {
            "path": str(registry_path),
            "disorder_aliases_path": str(disorder_aliases_path),
            "entry_counts": {category: len(values) for category, values in entries.items()},
        },
        "summary": {
            dataset: {
                "input_rows": len(source_rows[dataset]),
                "graph_rows": len(graph_rows[dataset]),
                "status_counts": dict(status_counts[dataset]),
                "top_normalized_entities": entity_counts[dataset].most_common(20),
            }
            for dataset in ("mechanistic", "disorder")
        },
    }
    return graph_rows, audit_rows, report


def csv_fieldnames(rows: Iterable[dict]) -> list[str]:
    seen: set[str] = set()
    fieldnames: list[str] = []
    preferred = [
        "normalization_status",
        "normalization_notes",
        "compound",
        "target",
        "disorder",
        "canonical_compound",
        "canonical_entity",
        "compound_original",
        "target_original",
        "disorder_original",
        "graph_entity_original",
        "raw_entity_label",
        "entity_role",
        "graph_entity_label",
        "graph_entity_type",
        "graph_include_candidate",
        "study_doi",
        "study_title",
    ]
    for key in preferred:
        fieldnames.append(key)
        seen.add(key)
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    return fieldnames


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = csv_fieldnames(rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json_cell(value) for key, value in row.items()})


def output_name(prefix: str, dataset: str, suffix: str) -> str:
    clean_prefix = normalize(prefix)
    return f"{clean_prefix}_{dataset}_{suffix}" if clean_prefix else f"{dataset}_{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize projected extraction-v1 claims against the entity registry")
    parser.add_argument(
        "--mechanistic-json",
        default=str(DEFAULT_INPUT_DIR / "mechanistic_claims.json"),
        help="Projected mechanistic claims JSON array",
    )
    parser.add_argument(
        "--disorder-json",
        default=str(DEFAULT_INPUT_DIR / "disorder_claims.json"),
        help="Projected disorder claims JSON array",
    )
    parser.add_argument(
        "--mechanistic-secondary-json",
        default=str(DEFAULT_INPUT_DIR / "mechanistic_secondary_claims.json"),
        help="Projected mechanistic secondary-literature coverage JSON array",
    )
    parser.add_argument(
        "--disorder-secondary-json",
        default=str(DEFAULT_INPUT_DIR / "disorder_secondary_claims.json"),
        help="Projected disorder secondary-literature coverage JSON array",
    )
    parser.add_argument("--registry-json", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--disorder-aliases-json", default=str(DEFAULT_DISORDER_ALIASES_PATH))
    parser.add_argument("--out-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--prefix", default="", help="Optional output filename prefix for calibration runs")
    args = parser.parse_args()

    mechanistic_path = Path(args.mechanistic_json).resolve()
    disorder_path = Path(args.disorder_json).resolve()
    mechanistic_secondary_path = Path(args.mechanistic_secondary_json).resolve()
    disorder_secondary_path = Path(args.disorder_secondary_json).resolve()
    out_dir = Path(args.out_dir).resolve()
    graph_rows, audit_rows, report = normalize_claims(
        load_json_array(mechanistic_path),
        load_json_array(disorder_path),
        Path(args.registry_json).resolve(),
        Path(args.disorder_aliases_json).resolve(),
    )
    secondary_graph_rows, secondary_audit_rows, secondary_report = normalize_claims(
        load_json_array(mechanistic_secondary_path),
        load_json_array(disorder_secondary_path),
        Path(args.registry_json).resolve(),
        Path(args.disorder_aliases_json).resolve(),
    )

    outputs = {}
    for dataset in ("mechanistic", "disorder"):
        graph_stem = output_name(args.prefix, dataset, "graph_claims")
        audit_stem = output_name(args.prefix, dataset, "normalization_audit")
        graph_json = out_dir / f"{graph_stem}.json"
        graph_csv = out_dir / f"{graph_stem}.csv"
        audit_json = out_dir / f"{audit_stem}.json"
        audit_csv = out_dir / f"{audit_stem}.csv"
        write_json(graph_json, graph_rows[dataset])
        write_csv(graph_csv, graph_rows[dataset])
        write_json(audit_json, audit_rows[dataset])
        write_csv(audit_csv, audit_rows[dataset])
        outputs[dataset] = {
            "graph_json": str(graph_json),
            "graph_csv": str(graph_csv),
            "audit_json": str(audit_json),
            "audit_csv": str(audit_csv),
            "graph_rows": len(graph_rows[dataset]),
            "audit_rows": len(audit_rows[dataset]),
        }
        secondary_graph_stem = output_name(args.prefix, dataset, "secondary_graph_claims")
        secondary_audit_stem = output_name(args.prefix, dataset, "secondary_normalization_audit")
        secondary_graph_json = out_dir / f"{secondary_graph_stem}.json"
        secondary_graph_csv = out_dir / f"{secondary_graph_stem}.csv"
        secondary_audit_json = out_dir / f"{secondary_audit_stem}.json"
        secondary_audit_csv = out_dir / f"{secondary_audit_stem}.csv"
        write_json(secondary_graph_json, secondary_graph_rows[dataset])
        write_csv(secondary_graph_csv, secondary_graph_rows[dataset])
        write_json(secondary_audit_json, secondary_audit_rows[dataset])
        write_csv(secondary_audit_csv, secondary_audit_rows[dataset])
        outputs[dataset].update(
            {
                "secondary_graph_json": str(secondary_graph_json),
                "secondary_graph_csv": str(secondary_graph_csv),
                "secondary_audit_json": str(secondary_audit_json),
                "secondary_audit_csv": str(secondary_audit_csv),
                "secondary_graph_rows": len(secondary_graph_rows[dataset]),
                "secondary_audit_rows": len(secondary_audit_rows[dataset]),
            }
        )

    report["inputs"] = {
        "mechanistic_json": str(mechanistic_path),
        "disorder_json": str(disorder_path),
        "mechanistic_secondary_json": str(mechanistic_secondary_path),
        "disorder_secondary_json": str(disorder_secondary_path),
    }
    report["outputs"] = outputs
    report["secondary_summary"] = secondary_report["summary"]
    report_path = out_dir / (f"{normalize(args.prefix)}_normalization_report.json" if normalize(args.prefix) else "normalization_report.json")
    write_json(report_path, report)

    print(f"wrote {report_path}")
    for dataset, output in outputs.items():
        print(f"{dataset}: {output['graph_rows']} graph rows from {output['audit_rows']} projected rows")
        print(
            f"{dataset} secondary: {output['secondary_graph_rows']} graph rows "
            f"from {output['secondary_audit_rows']} projected rows"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
