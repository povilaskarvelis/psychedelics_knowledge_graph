"""Shared helpers for DOI-keyed updates to ``candidate_papers.parquet``."""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
import tempfile
from typing import Mapping

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def normalize_doi(value: object) -> str:
    doi = clean(value).lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix) :]
    return doi.strip().rstrip(".")


def values_equal(left: object, right: object) -> bool:
    if pd.isna(left) and pd.isna(right):
        return True
    if isinstance(left, bool) or isinstance(right, bool):
        return bool(left) == bool(right)
    return clean(left) == clean(right)


def apply_candidate_updates(
    *,
    candidate_table: Path = DEFAULT_CANDIDATE_TABLE,
    updates: pd.DataFrame,
    column_defaults: Mapping[str, object] | None = None,
    dry_run: bool = False,
) -> dict:
    """Merge an update frame into the candidate table by normalized DOI.

    ``updates`` must contain a ``doi`` column. All other columns are written to
    matching candidate rows, adding missing columns with explicit defaults.
    """

    candidate_table = Path(candidate_table)
    summary = {
        "candidate_table": str(candidate_table.resolve()),
        "dry_run": dry_run,
        "update_rows": int(len(updates)),
        "matched_candidate_rows": 0,
        "updated_candidate_rows": 0,
        "updated_cells": 0,
        "missing_update_dois": [],
        "updated_columns": [],
        "skipped_reason": "",
    }
    if updates.empty:
        summary["skipped_reason"] = "no_updates"
        return summary
    if "doi" not in updates.columns:
        raise ValueError("candidate status updates must include a doi column")
    if not candidate_table.exists():
        summary["skipped_reason"] = "candidate_table_missing"
        return summary

    df = pd.read_parquet(candidate_table)
    if "doi" not in df.columns:
        summary["skipped_reason"] = "candidate_table_missing_doi"
        return summary

    defaults = dict(column_defaults or {})
    update_df = updates.copy()
    update_df["_doi_key"] = update_df["doi"].map(normalize_doi)
    update_df = update_df[update_df["_doi_key"].astype(bool)].copy()
    update_df = update_df.drop_duplicates("_doi_key", keep="last")
    if update_df.empty:
        summary["skipped_reason"] = "no_update_dois"
        return summary

    df = df.copy()
    df["_doi_key"] = df["doi"].map(normalize_doi)
    update_keys = set(update_df["_doi_key"])
    matched_mask = df["_doi_key"].isin(update_keys)
    summary["matched_candidate_rows"] = int(matched_mask.sum())
    missing = sorted(update_keys - set(df["_doi_key"]))
    summary["missing_update_dois"] = missing[:100]

    columns = [column for column in update_df.columns if column not in {"doi", "_doi_key"}]
    summary["updated_columns"] = columns
    for column in columns:
        if column not in df.columns:
            df[column] = defaults.get(column, "")

    update_df = update_df.set_index("_doi_key", drop=True)
    changed_rows: set[int] = set()
    changed = False
    for column in columns:
        mapped = df["_doi_key"].map(update_df[column])
        mapped = mapped.where(mapped.notna(), defaults.get(column, ""))
        equal = df[column].eq(mapped)
        if hasattr(equal, "fillna"):
            equal = equal.fillna(False)
        equal = equal | (df[column].isna() & mapped.isna())
        column_changed = matched_mask & ~equal
        if not column_changed.any():
            continue
        df.loc[column_changed, column] = mapped.loc[column_changed].to_numpy()
        summary["updated_cells"] += int(column_changed.sum())
        changed_rows.update(int(index) for index in df.index[column_changed])
        changed = True

    summary["updated_candidate_rows"] = len(changed_rows)
    df = df.drop(columns=["_doi_key"])
    if changed and not dry_run:
        candidate_table.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{candidate_table.name}.",
            suffix=".tmp",
            dir=candidate_table.parent,
        )
        os.close(file_descriptor)
        temporary_path = Path(temporary_name)
        try:
            df.to_parquet(temporary_path, engine="pyarrow", index=False)
            os.replace(temporary_path, candidate_table)
        finally:
            temporary_path.unlink(missing_ok=True)
    return summary
