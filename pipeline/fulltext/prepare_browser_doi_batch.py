#!/usr/bin/env python3
"""Select the next unseen manual-recovery DOIs and optionally reserve them."""

from __future__ import annotations

import argparse
from collections import OrderedDict, deque
from pathlib import Path
import re
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.metadata_utils import normalize_doi


PROGRESS_COLUMNS = ["doi", "study_title", "browser_batch", "manual_status", "manual_notes"]
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)


def doi_key(value: object) -> str:
    return normalize_doi("" if value is None else str(value)).lower()


def valid_doi(value: object) -> bool:
    return bool(DOI_RE.fullmatch(doi_key(value)))


def host_balanced_head(frame: pd.DataFrame, limit: int) -> pd.DataFrame:
    """Round-robin DOI registrant prefixes to avoid publisher throttling."""
    queues: OrderedDict[str, deque[dict]] = OrderedDict()
    for row in frame.to_dict("records"):
        doi = doi_key(row.get("doi", ""))
        prefix = doi.split("/", 1)[0] if "/" in doi else "unknown"
        queues.setdefault(prefix, deque()).append(row)
    selected: list[dict] = []
    while queues and len(selected) < max(0, limit):
        for prefix in list(queues):
            queue = queues[prefix]
            if queue and len(selected) < limit:
                selected.append(queue.popleft())
            if not queue:
                del queues[prefix]
    return pd.DataFrame(selected, columns=frame.columns)


def prepare_batch(
    queue: pd.DataFrame,
    progress: pd.DataFrame,
    *,
    batch_size: int,
    batch_number: int | None = None,
    skip_unseen: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    seen = {doi_key(value) for value in progress.get("doi", pd.Series(dtype=str)) if doi_key(value)}
    eligible = queue.copy()
    eligible["_doi_key"] = eligible.get("doi", pd.Series(dtype=str)).map(doi_key)
    eligible = eligible[
        eligible["_doi_key"].map(valid_doi) & ~eligible["_doi_key"].isin(seen)
    ].copy()
    if skip_unseen:
        eligible = eligible.iloc[max(0, skip_unseen) :].copy()
    batch = host_balanced_head(eligible.drop(columns="_doi_key"), batch_size)
    if batch_number is None:
        prior = pd.to_numeric(progress.get("browser_batch", pd.Series(dtype=float)), errors="coerce")
        batch_number = int(prior.max()) + 1 if prior.notna().any() else 1
    reservations = pd.DataFrame(
        [
            {
                "doi": doi_key(row.get("doi", "")),
                "study_title": str(row.get("study_title", "") or ""),
                "browser_batch": batch_number,
                "manual_status": "opened_for_manual_review",
                "manual_notes": "DOI landing page opened in Chrome for supervised article-PDF recovery.",
            }
            for row in batch.fillna("").to_dict("records")
        ],
        columns=PROGRESS_COLUMNS,
    )
    return batch, reservations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-csv", required=True)
    parser.add_argument("--progress-csv", required=True)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--batch-number", type=int)
    parser.add_argument(
        "--skip-unseen",
        type=int,
        default=0,
        help="Skip this many currently unseen queue rows before host-balanced selection.",
    )
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--output-txt", required=True)
    parser.add_argument("--apply-progress", action="store_true")
    parser.add_argument(
        "--replace-batch",
        action="store_true",
        help="Remove an existing reservation for --batch-number before selecting its replacement.",
    )
    args = parser.parse_args()

    queue_path = Path(args.queue_csv).resolve()
    progress_path = Path(args.progress_csv).resolve()
    progress = pd.read_csv(progress_path).fillna("") if progress_path.exists() else pd.DataFrame(columns=PROGRESS_COLUMNS)
    if args.replace_batch:
        if args.batch_number is None:
            parser.error("--replace-batch requires --batch-number")
        existing_batch = pd.to_numeric(progress.get("browser_batch", pd.Series(dtype=float)), errors="coerce")
        progress = progress[~existing_batch.eq(args.batch_number)].copy()
    batch, reservations = prepare_batch(
        pd.read_csv(queue_path).fillna(""),
        progress,
        batch_size=args.batch_size,
        batch_number=args.batch_number,
        skip_unseen=args.skip_unseen,
    )
    output_csv = Path(args.output_csv).resolve()
    output_txt = Path(args.output_txt).resolve()
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_txt.parent.mkdir(parents=True, exist_ok=True)
    batch.to_csv(output_csv, index=False)
    output_txt.write_text("\n".join(f"https://doi.org/{doi_key(value)}" for value in batch.get("doi", [])) + ("\n" if len(batch) else ""), encoding="utf-8")
    if args.apply_progress and not reservations.empty:
        combined = pd.concat([progress.reindex(columns=PROGRESS_COLUMNS), reservations], ignore_index=True)
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(progress_path, index=False)
    batch_number = int(reservations.iloc[0]["browser_batch"]) if not reservations.empty else (args.batch_number or 0)
    print(f"BROWSER_DOI_BATCH: batch={batch_number} rows={len(batch):,} reserved={bool(args.apply_progress)} csv={output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
