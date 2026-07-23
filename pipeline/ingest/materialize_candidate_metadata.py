#!/usr/bin/env python3
"""Materialize enriched bibliographic metadata into the candidate ledger.

``paper_metadata_enrichment.parquet`` is a provider/provenance cache. The
candidate ledger is the canonical input to screening and later workflow
stages, so enrichment values must be written there before those stages run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Iterable, Sequence

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.candidate_status import clean, normalize_doi
from pipeline.ingest.enrich_paper_metadata import OUTPUT_COLUMNS


DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_METADATA_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"
DEFAULT_CURATED_OVERRIDES = ROOT / "data" / "curated" / "paper_metadata_overrides.json"

# Provider/provenance fields are materialized alongside bibliographic values so
# every canonical value remains attributable to its enrichment run.
MATERIALIZED_METADATA_FIELDS = tuple(column for column in OUTPUT_COLUMNS if column != "doi")
MATERIALIZATION_COLUMNS = (
    "metadata_materialization_run_id",
    "metadata_materialized_at_utc",
)
YEAR_FIELDS = frozenset({"study_year", "publication_date"})
YEAR_PATTERN = re.compile(r"(?<!\d)(1[5-9]\d{2}|20\d{2}|21\d{2})(?!\d)")


def normalized_value(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return clean(value)


def bibliographic_year(value: object) -> int | None:
    match = YEAR_PATTERN.search(normalized_value(value))
    return int(match.group(1)) if match else None


def validate_year_date_consistency(candidates: pd.DataFrame, row_indices: set[int]) -> None:
    """Reject newly materialized year/date contradictions before they reach releases."""

    if not row_indices or not YEAR_FIELDS.issubset(candidates.columns):
        return
    conflicts: list[dict[str, object]] = []
    for index in sorted(row_indices):
        study_year = bibliographic_year(candidates.at[index, "study_year"])
        date_year = bibliographic_year(candidates.at[index, "publication_date"])
        if study_year is None or date_year is None or abs(study_year - date_year) <= 1:
            continue
        conflicts.append(
            {
                "doi": candidates.at[index, "_doi_key"],
                "study_year": study_year,
                "publication_date_year": date_year,
            }
        )
    if conflicts:
        raise ValueError(
            "Refusing to materialize inconsistent bibliographic timing: "
            f"{len(conflicts)} row(s), examples={conflicts[:10]}"
        )


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def default_run_id() -> str:
    return "candidate_metadata_materialization_" + dt.datetime.now(dt.timezone.utc).strftime(
        "%Y_%m_%d_%H%M%S"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        frame.to_parquet(temporary, engine="pyarrow", index=False)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def normalized_unique_frame(
    frame: pd.DataFrame, *, label: str, collapse_alias_duplicates: bool = False
) -> pd.DataFrame:
    if "doi" not in frame.columns:
        raise ValueError(f"{label} table has no DOI column")
    out = frame.copy()
    out["_doi_key"] = out["doi"].map(normalize_doi)
    out = out[out["_doi_key"].astype(bool)].copy()
    duplicates = out.loc[out.duplicated("_doi_key", keep=False), "_doi_key"].unique().tolist()
    if duplicates:
        if not collapse_alias_duplicates:
            raise ValueError(f"{label} table has duplicate normalized DOIs: {duplicates[:10]}")
        out["_canonical_doi_form"] = out.apply(
            lambda row: clean(row["doi"]).lower() == row["_doi_key"], axis=1
        )
        out = out.sort_values(
            ["_doi_key", "_canonical_doi_form"], ascending=[True, False], kind="stable"
        ).drop_duplicates("_doi_key", keep="first")
        out = out.drop(columns=["_canonical_doi_form"])
    return out


def read_curated_overrides(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records", []) if isinstance(payload, dict) else []
    out: dict[str, dict[str, str]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        doi = normalize_doi(record.get("doi", ""))
        fields = record.get("fields", {})
        if not doi or not isinstance(fields, dict):
            continue
        kept = {
            field: clean(value)
            for field, value in fields.items()
            if field in MATERIALIZED_METADATA_FIELDS and clean(value)
        }
        if kept:
            out[doi] = kept
    return out


def materialize_candidate_metadata(
    *,
    candidate_table: Path = DEFAULT_CANDIDATE_TABLE,
    metadata_table: Path = DEFAULT_METADATA_TABLE,
    run_id: str,
    fields: Sequence[str] = MATERIALIZED_METADATA_FIELDS,
    scoped_dois: Iterable[str] | None = None,
    overwrite_existing: bool = False,
    clear_blank_fields: Sequence[str] = (),
    curated_overrides_path: Path | None = DEFAULT_CURATED_OVERRIDES,
    dry_run: bool = False,
) -> dict:
    """Write enrichment values into matching candidate rows.

    The default migration policy only fills blank candidate cells. A caller
    that has just produced fresh enrichment values can set
    ``overwrite_existing=True`` for its DOI/field scope. Curated corrections
    are always applied last and therefore cannot be undone by provider data.
    """

    candidate_table = Path(candidate_table).resolve()
    metadata_table = Path(metadata_table).resolve()
    candidates = normalized_unique_frame(pd.read_parquet(candidate_table), label="candidate")
    raw_metadata = pd.read_parquet(metadata_table)
    metadata = normalized_unique_frame(
        raw_metadata, label="metadata", collapse_alias_duplicates=True
    )
    normalized_metadata_duplicates = int(len(raw_metadata) - len(metadata))
    requested_fields = [field for field in fields if field != "doi"]
    unknown = sorted(set(requested_fields) - set(MATERIALIZED_METADATA_FIELDS))
    if unknown:
        raise ValueError(f"Unsupported candidate metadata fields: {unknown}")
    clear_blank_fields = tuple(clear_blank_fields)
    unknown_blank_fields = sorted(set(clear_blank_fields) - set(requested_fields))
    if unknown_blank_fields:
        raise ValueError(f"Blank-clearing fields are not materialized fields: {unknown_blank_fields}")
    if clear_blank_fields and not overwrite_existing:
        raise ValueError("clear_blank_fields requires overwrite_existing=True")

    scope = {
        normalize_doi(value) for value in (scoped_dois or []) if normalize_doi(value)
    }
    if scope:
        metadata = metadata[metadata["_doi_key"].isin(scope)].copy()

    candidate_keys = set(candidates["_doi_key"])
    metadata_keys = set(metadata["_doi_key"])
    missing_candidate_dois = sorted(metadata_keys - candidate_keys)
    if missing_candidate_dois and scope:
        raise ValueError(
            "Enrichment rows are missing from the canonical candidate ledger: "
            f"{len(missing_candidate_dois)} ({missing_candidate_dois[:10]})"
        )
    if missing_candidate_dois:
        metadata = metadata[metadata["_doi_key"].isin(candidate_keys)].copy()
        metadata_keys = set(metadata["_doi_key"])

    metadata = metadata.set_index("_doi_key", drop=False)
    changed_rows: set[int] = set()
    year_date_changed_rows: set[int] = set()
    filled_cells = 0
    overwritten_cells = 0
    cleared_cells = 0
    field_updates: dict[str, int] = {}
    field_fills: dict[str, int] = {}
    field_overwrites: dict[str, int] = {}
    field_clears: dict[str, int] = {}

    for field in requested_fields:
        if field not in candidates.columns:
            candidates[field] = ""
        if field not in metadata.columns:
            continue
        mapped = candidates["_doi_key"].map(metadata[field])
        incoming_present = mapped.map(lambda value: bool(normalized_value(value)))
        current_present = candidates[field].map(lambda value: bool(normalized_value(value)))
        matched = candidates["_doi_key"].isin(metadata_keys)
        clear_blank = bool(field in clear_blank_fields)
        eligible = matched & (
            (incoming_present & (~current_present | overwrite_existing))
            | (clear_blank & current_present & ~incoming_present)
        )
        changed = eligible & candidates[field].map(normalized_value).ne(mapped.map(normalized_value))
        if not changed.any():
            continue
        fills = changed & ~current_present
        overwrites = changed & current_present & incoming_present
        clears = changed & current_present & ~incoming_present
        candidates.loc[changed, field] = mapped.loc[changed].map(normalized_value).to_numpy()
        count = int(changed.sum())
        fill_count = int(fills.sum())
        overwrite_count = int(overwrites.sum())
        clear_count = int(clears.sum())
        field_updates[field] = count
        if fill_count:
            field_fills[field] = fill_count
        if overwrite_count:
            field_overwrites[field] = overwrite_count
        if clear_count:
            field_clears[field] = clear_count
        filled_cells += fill_count
        overwritten_cells += overwrite_count
        cleared_cells += clear_count
        changed_rows.update(int(index) for index in candidates.index[changed])
        if field in YEAR_FIELDS:
            year_date_changed_rows.update(int(index) for index in candidates.index[changed])

    curated_overrides = read_curated_overrides(
        Path(curated_overrides_path).resolve() if curated_overrides_path is not None else None
    )
    curated_scope = set(curated_overrides) if not scope else set(curated_overrides) & scope
    curated_cells = 0
    curated_rows: set[int] = set()
    for index, row in candidates.iterrows():
        if row["_doi_key"] not in curated_scope:
            continue
        fields_for_doi = curated_overrides.get(row["_doi_key"], {})
        for field, value in fields_for_doi.items():
            if field not in requested_fields:
                continue
            if field not in candidates.columns:
                candidates[field] = ""
            if normalized_value(candidates.at[index, field]) == value:
                continue
            candidates.at[index, field] = value
            curated_cells += 1
            curated_rows.add(int(index))
            changed_rows.add(int(index))
            if field in YEAR_FIELDS:
                year_date_changed_rows.add(int(index))

    validate_year_date_consistency(candidates, year_date_changed_rows)

    timestamp = now_utc()
    for column in MATERIALIZATION_COLUMNS:
        if column not in candidates.columns:
            candidates[column] = ""
    materialized_mask = candidates["_doi_key"].isin(metadata_keys | curated_scope)
    if materialized_mask.any():
        candidates.loc[materialized_mask, "metadata_materialization_run_id"] = run_id
        candidates.loc[materialized_mask, "metadata_materialized_at_utc"] = timestamp

    candidates = candidates.drop(columns=["_doi_key"])
    if not dry_run:
        atomic_write_parquet(candidate_table, candidates)

    return {
        "schema_version": "candidate_metadata_materialization_report_v1",
        "run_id": run_id,
        "generated_at_utc": timestamp,
        "dry_run": bool(dry_run),
        "candidate_table": str(candidate_table),
        "metadata_table": str(metadata_table),
        "candidate_rows": int(len(candidates)),
        "metadata_rows_in_scope": int(len(metadata)),
        "normalized_metadata_alias_duplicates_collapsed": normalized_metadata_duplicates,
        "metadata_rows_without_candidate": len(missing_candidate_dois),
        "metadata_rows_without_candidate_examples": missing_candidate_dois[:100],
        "materialized_candidate_rows": int(materialized_mask.sum()),
        "changed_candidate_rows": len(changed_rows),
        "filled_cells": filled_cells,
        "overwritten_cells": overwritten_cells,
        "cleared_cells": cleared_cells,
        "curated_override_rows": len(curated_rows),
        "curated_override_cells": curated_cells,
        "year_date_consistency_checked_rows": len(year_date_changed_rows),
        "field_updates": field_updates,
        "field_fills": field_fills,
        "field_overwrites": field_overwrites,
        "field_clears": field_clears,
        "overwrite_existing": bool(overwrite_existing),
        "clear_blank_fields": list(clear_blank_fields),
        "candidate_sha256": sha256_file(candidate_table) if not dry_run else "",
    }


def read_doi_file(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(path)
    return {
        doi
        for line in path.read_text(encoding="utf-8").splitlines()
        if (doi := normalize_doi(line)) and not line.lstrip().startswith("#")
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--curated-overrides", default=str(DEFAULT_CURATED_OVERRIDES))
    parser.add_argument("--run-id", default=default_run_id())
    parser.add_argument("--doi-file", default="")
    parser.add_argument("--fields", default=",".join(MATERIALIZED_METADATA_FIELDS))
    parser.add_argument("--overwrite-existing", action="store_true")
    parser.add_argument("--report-json", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    scope = read_doi_file(Path(args.doi_file).resolve()) if clean(args.doi_file) else None
    fields = [part.strip() for part in args.fields.split(",") if part.strip()]
    report = materialize_candidate_metadata(
        candidate_table=Path(args.candidate_table),
        metadata_table=Path(args.metadata_table),
        run_id=args.run_id,
        fields=fields,
        scoped_dois=scope,
        overwrite_existing=bool(args.overwrite_existing),
        curated_overrides_path=Path(args.curated_overrides) if clean(args.curated_overrides) else None,
        dry_run=bool(args.dry_run),
    )
    if clean(args.report_json):
        atomic_write_json(Path(args.report_json).resolve(), report)
    print(f"Candidate rows materialized: {report['materialized_candidate_rows']:,}")
    print(f"Candidate rows changed: {report['changed_candidate_rows']:,}")
    print(f"Cells filled: {report['filled_cells']:,}")
    print(f"Cells overwritten: {report['overwritten_cells']:,}")
    print(f"Curated override cells: {report['curated_override_cells']:,}")
    print(f"Candidate table: {report['candidate_table']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
