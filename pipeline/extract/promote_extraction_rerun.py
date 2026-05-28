#!/usr/bin/env python3
"""Promote a successful extraction rerun into the active extraction JSONL.

The active graph is regenerated from the active extraction output JSONL. Reruns
therefore need to replace DOI-level source records before projection and
normalization, rather than appending projected graph rows directly.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

try:
    from pipeline.extract.extraction_v1_utils import normalize, normalize_doi, read_jsonl, write_json, write_jsonl
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.extraction_v1_utils import normalize, normalize_doi, read_jsonl, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXTRACTION_DIR = ROOT / "data" / "processed" / "extraction"
DEFAULT_PROJECTION_REPORT = DEFAULT_EXTRACTION_DIR / "projection_report.json"
DEFAULT_BACKUP_DIR = DEFAULT_EXTRACTION_DIR / "backups"


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def default_active_paths(projection_report: Path = DEFAULT_PROJECTION_REPORT) -> tuple[Path, Path]:
    report = load_json_object(projection_report)
    inputs = report.get("inputs", {}) if isinstance(report.get("inputs"), dict) else {}
    output_jsonl = normalize(inputs.get("input_jsonl", ""))
    pilot_jsonl = normalize(inputs.get("pilot_input_jsonl", ""))
    if not output_jsonl or not pilot_jsonl:
        raise SystemExit(
            "Could not infer active extraction JSONLs from projection_report.json; "
            "pass --active-output-jsonl and --active-pilot-input-jsonl."
        )
    return Path(output_jsonl), Path(pilot_jsonl)


def record_key(row: dict) -> tuple[str, str, str]:
    dataset = normalize(row.get("dataset", "")).casefold()
    doi = normalize_doi(row.get("study_doi", ""))
    if doi:
        return ("doi", dataset, doi)
    openalex_id = normalize(row.get("openalex_id", "")).casefold()
    if openalex_id:
        return ("openalex", dataset, openalex_id)
    record_id = normalize(row.get("input_record_id", "")) or normalize(row.get("pilot_record_id", ""))
    if record_id:
        return ("record_id", dataset, record_id)
    title = normalize(row.get("study_title", "")).casefold()
    return ("title", dataset, title)


def key_label(key: tuple[str, str, str]) -> str:
    key_type, dataset, value = key
    return f"{key_type}:{dataset}:{value}"


def indexed_rows(rows: list[dict]) -> tuple[dict[tuple[str, str, str], dict], list[str]]:
    index: dict[tuple[str, str, str], dict] = {}
    duplicate_keys: list[str] = []
    for row in rows:
        key = record_key(row)
        if key in index:
            duplicate_keys.append(key_label(key))
        index[key] = row
    return index, duplicate_keys


def merge_rows(active_rows: list[dict], replacement_rows: list[dict]) -> tuple[list[dict], dict]:
    replacement_by_key, replacement_duplicate_keys = indexed_rows(replacement_rows)
    replaced_keys: list[str] = []
    retained_keys: list[str] = []
    merged: list[dict] = []

    for row in active_rows:
        key = record_key(row)
        replacement = replacement_by_key.pop(key, None)
        if replacement is None:
            merged.append(row)
            retained_keys.append(key_label(key))
        else:
            merged.append(replacement)
            replaced_keys.append(key_label(key))

    appended_keys = [key_label(key) for key in replacement_by_key]
    merged.extend(replacement_by_key.values())

    return merged, {
        "active_rows": len(active_rows),
        "replacement_rows": len(replacement_rows),
        "merged_rows": len(merged),
        "replaced_rows": len(replaced_keys),
        "appended_rows": len(appended_keys),
        "retained_active_rows": len(retained_keys),
        "replacement_duplicate_keys": sorted(replacement_duplicate_keys),
        "replaced_keys": sorted(replaced_keys),
        "appended_keys": sorted(appended_keys),
    }


def filter_inputs_for_successful_outputs(input_rows: list[dict], successful_output_rows: list[dict]) -> tuple[list[dict], dict]:
    wanted_keys = {record_key(row) for row in successful_output_rows}
    filtered: list[dict] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for row in input_rows:
        key = record_key(row)
        if key not in wanted_keys:
            continue
        filtered.append(row)
        seen_keys.add(key)
    missing_input_keys = sorted(key_label(key) for key in wanted_keys - seen_keys)
    return filtered, {
        "successful_output_keys": len(wanted_keys),
        "matching_input_rows": len(filtered),
        "missing_input_keys": missing_input_keys,
    }


def backup_file(path: Path, backup_dir: Path, stamp: str) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{path.name}.{stamp}.bak"
    shutil.copy2(path, backup_path)
    return backup_path


def promote(
    *,
    active_output_jsonl: Path,
    active_pilot_input_jsonl: Path,
    rerun_output_jsonl: Path,
    rerun_pilot_input_jsonl: Path,
    report_json: Path,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    apply: bool = False,
) -> dict:
    active_outputs = read_jsonl(active_output_jsonl)
    active_inputs = read_jsonl(active_pilot_input_jsonl)
    rerun_outputs = read_jsonl(rerun_output_jsonl)
    rerun_inputs_all = read_jsonl(rerun_pilot_input_jsonl)
    rerun_inputs, input_filter_summary = filter_inputs_for_successful_outputs(rerun_inputs_all, rerun_outputs)

    merged_outputs, output_summary = merge_rows(active_outputs, rerun_outputs)
    merged_inputs, input_summary = merge_rows(active_inputs, rerun_inputs)

    stamp = now_stamp()
    report = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "apply": apply,
        "inputs": {
            "active_output_jsonl": str(active_output_jsonl),
            "active_pilot_input_jsonl": str(active_pilot_input_jsonl),
            "rerun_output_jsonl": str(rerun_output_jsonl),
            "rerun_pilot_input_jsonl": str(rerun_pilot_input_jsonl),
        },
        "output_merge": output_summary,
        "pilot_input_filter": input_filter_summary,
        "pilot_input_merge": input_summary,
        "backups": {},
    }

    if apply:
        report["backups"] = {
            "active_output_jsonl": str(backup_file(active_output_jsonl, backup_dir, stamp)),
            "active_pilot_input_jsonl": str(backup_file(active_pilot_input_jsonl, backup_dir, stamp)),
        }
        write_jsonl(active_output_jsonl, merged_outputs)
        write_jsonl(active_pilot_input_jsonl, merged_inputs)

    write_json(report_json, report)
    return report


def parse_args() -> argparse.Namespace:
    active_output, active_pilot = default_active_paths()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--active-output-jsonl", type=Path, default=active_output)
    parser.add_argument("--active-pilot-input-jsonl", type=Path, default=active_pilot)
    parser.add_argument("--rerun-output-jsonl", type=Path, required=True)
    parser.add_argument("--rerun-pilot-input-jsonl", type=Path, required=True)
    parser.add_argument(
        "--report-json",
        type=Path,
        default=DEFAULT_EXTRACTION_DIR / f"extraction_v1_promote_rerun_report.{now_stamp()}.json",
    )
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = promote(
        active_output_jsonl=args.active_output_jsonl.resolve(),
        active_pilot_input_jsonl=args.active_pilot_input_jsonl.resolve(),
        rerun_output_jsonl=args.rerun_output_jsonl.resolve(),
        rerun_pilot_input_jsonl=args.rerun_pilot_input_jsonl.resolve(),
        report_json=args.report_json.resolve(),
        backup_dir=args.backup_dir.resolve(),
        apply=args.apply,
    )
    mode = "applied" if args.apply else "dry-run"
    output = report["output_merge"]
    inputs = report["pilot_input_merge"]
    print(
        f"{mode}: outputs replace {output['replaced_rows']} and append {output['appended_rows']}; "
        f"pilot inputs replace {inputs['replaced_rows']} and append {inputs['appended_rows']}"
    )
    print(f"report: {args.report_json.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
