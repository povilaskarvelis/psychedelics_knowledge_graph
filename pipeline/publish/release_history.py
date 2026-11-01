"""Append-only local record of promoted releases.

Promotion and public refreshes append one JSON line each. History pruning reads
the record to tell runs that were published (and later replaced) from runs that
were never published, and to find the release published before the active one.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RELEASE_HISTORY = ROOT / "data" / "processed" / "release_history.jsonl"
PROMOTION_KINDS = frozenset({"promotion", "seed"})


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_release_history(path: Path = RELEASE_HISTORY) -> list[dict]:
    if not path.is_file():
        return []
    records: list[dict] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict) or not str(value.get("run_id") or "").strip():
            raise ValueError(f"Invalid release history record on line {number}: {path}")
        records.append(value)
    return records


def append_release_history(record: dict, path: Path = RELEASE_HISTORY) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def record_release(
    *,
    kind: str,
    run_id: str,
    evidence_release_id: str,
    public_release_id: str,
    replaced_extraction_pointer: dict | None = None,
    path: Path = RELEASE_HISTORY,
) -> None:
    """Record a promotion or public refresh.

    The first promotion after this record was introduced also records the run
    it replaced (``seed``), using that run's own promotion time, so the
    replaced release is recognised as the previous release.
    """
    recorded_at = now_utc()
    history = read_release_history(path)
    recorded_runs = {str(record.get("run_id")) for record in history}
    replaced = replaced_extraction_pointer or {}
    replaced_run_id = str(replaced.get("run_id") or "").strip()
    if replaced_run_id and replaced_run_id != run_id and replaced_run_id not in recorded_runs:
        append_release_history(
            {
                "kind": "seed",
                "run_id": replaced_run_id,
                "evidence_release_id": str(replaced.get("release_id") or "").strip(),
                "public_release_id": "",
                "promoted_at": str(replaced.get("updated_at_utc") or "").strip(),
                "recorded_at": recorded_at,
            },
            path,
        )
    append_release_history(
        {
            "kind": kind,
            "run_id": run_id,
            "evidence_release_id": evidence_release_id,
            "public_release_id": public_release_id,
            "promoted_at": recorded_at,
            "recorded_at": recorded_at,
        },
        path,
    )


def previous_run_id(history: list[dict], active_run_id: str) -> str:
    """Return the most recently recorded run other than the active one."""
    for record in reversed(history):
        run_id = str(record.get("run_id") or "").strip()
        if run_id and run_id != active_run_id:
            return run_id
    return ""


def promotion_time(history: list[dict], run_id: str) -> str:
    """Return when ``run_id`` was last promoted, if the history records it."""
    for record in reversed(history):
        if record.get("run_id") == run_id and record.get("kind") in PROMOTION_KINDS:
            return str(record.get("promoted_at") or "").strip()
    return ""
