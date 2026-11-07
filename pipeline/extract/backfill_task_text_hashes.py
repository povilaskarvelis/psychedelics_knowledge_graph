"""Add text hashes to extraction tasks built before tasks recorded them.

Since 7 November 2026 every task records the texts it sends
(``source_text_hashes`` in ``io_utils.py``): the SHA-256 of the full-text file
its packet was built from and of the record's abstract as stored. Finding rows
carry these hashes, and the KG build holds a row whose text it cannot check.
Outputs extracted earlier belong to tasks without hashes. This command adds the
hashes to those task files where the text the task sent can be shown to be a
text stored now. A task that fails the rule gets an empty hash, so its findings
are held until the paper is re-extracted.

The rule:

- full text: the packet the task names (its packet file and packet ID) gives the
  source fingerprint the task recorded, so it holds the text that was sent, and
  the full-text file that packet was built from has not changed since the
  packet was built. Primary tasks have fingerprinted packets by three rules
  (``primary_fingerprints``); any of them may reproduce the recorded one;
- abstract: the record's abstract as stored now, with whitespace collapsed, is
  the abstract the task sent.

Usage:

    python -m pipeline.extract.backfill_task_text_hashes \\
      --tasks-jsonl <old tasks> [--tasks-jsonl ...] --out-jsonl <tasks with hashes> \\
      --report-json <report>
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd

from pipeline.extract.build_extraction_tasks import canonical_sha256, source_fingerprint_for_task, stable_packet_payload
from pipeline.extract.build_review_relationship_tasks import packet_text_fingerprint
from pipeline.extract.io_utils import normalize, read_jsonl, write_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"


def compact(value: object) -> str:
    return re.sub(r"\s+", " ", normalize(value)).strip()


def timestamp(value: object) -> float | None:
    try:
        return dt.datetime.fromisoformat(normalize(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def is_secondary(task: dict) -> bool:
    return isinstance(task.get("source"), dict)


def text_holder(task: dict) -> dict:
    return task["source"] if is_secondary(task) else task.get("text_source", {})


def reads_article_text(task: dict) -> bool:
    holder = text_holder(task)
    return holder.get("kind") == "article_text" if is_secondary(task) else holder.get("mode") == "full_text_packet"


def packet_location(task: dict) -> tuple[str, str]:
    holder = text_holder(task)
    path = holder.get("packet_path", "") if is_secondary(task) else holder.get("packet_source_path", "")
    return normalize(path), normalize(task.get("study_doi", "")).lower()


def load_packets(tasks: list[dict], extra_packet_files: list[Path] = ()) -> dict[tuple[str, str], list[dict]]:
    """The packets each task may have read, keyed by the task's packet file and paper.

    A task names its packet file, but that file may have been rebuilt since.
    Copies kept elsewhere (``extra_packet_files``) are searched as well; the
    task's fingerprint decides which packet, if any, it read.
    """
    wanted: dict[str, set[str]] = {}
    for task in tasks:
        if reads_article_text(task) and not {"artifact_sha256", "abstract_sha256"} <= set(text_holder(task)):
            path, doi = packet_location(task)
            wanted.setdefault(path, set()).add(doi)
    all_dois = set().union(*wanted.values()) if wanted else set()
    by_file: dict[tuple[str, str], list[dict]] = {}
    extra: dict[str, list[dict]] = {}
    for path in sorted(set(wanted) | {str(path) for path in extra_packet_files}):
        named_here = wanted.get(path, set())
        for packet in read_jsonl(Path(path)) if path else []:
            doi = normalize(packet.get("study_doi", "")).lower()
            if doi in named_here:
                by_file.setdefault((path, doi), []).append(packet)
            if path in {str(p) for p in extra_packet_files} and doi in all_dois:
                extra.setdefault(doi, []).append(packet)
    return {
        (path, doi): by_file.get((path, doi), []) + extra.get(doi, [])
        for path, dois in wanted.items()
        for doi in dois
    }


def primary_fingerprints(task: dict, packet: dict) -> set[str]:
    """The source fingerprints the packet gives a primary task under each rule tasks have used.

    Until 1 November 2026 the fingerprint covered the packet with its build
    time; from then until 7 November it also covered the task's title and
    abstract; since 7 November it leaves out the packet's build time and file
    hash (``source_fingerprint_for_task``).
    """
    metadata = task.get("paper_metadata", {})
    with_build_time = {"mode": "full_text_packet", "packet": stable_packet_payload(packet, frozenset({"_packet_source_path", "generated_at_utc"}))}
    return {
        canonical_sha256(with_build_time),
        canonical_sha256({
            **with_build_time,
            "task_title": normalize(metadata.get("study_title", "")),
            "task_abstract": normalize(metadata.get("abstract", "")),
        }),
        source_fingerprint_for_task(text_source=task.get("text_source", {}), metadata=metadata, packet=packet),
    }


def task_fingerprints(task: dict, packet: dict) -> set[str]:
    """The source fingerprints the packet gives the task."""
    if is_secondary(task):
        return {packet_text_fingerprint(packet)[0]}
    return primary_fingerprints(task, packet)


def artifact_hash(task: dict, packets: list[dict], counts: Counter) -> str:
    recorded = normalize(text_holder(task).get("source_fingerprint", ""))
    for packet in packets:
        if not recorded or recorded not in task_fingerprints(task, packet):
            continue
        path = Path(normalize(packet.get("fulltext_provenance", {}).get("artifact_path", "")))
        built = timestamp(packet.get("created_at_utc"))
        if not path.is_file() or built is None or path.stat().st_mtime >= built:
            counts["full_text_file_changed_after_packet"] += 1
            return ""
        return hashlib.sha256(path.read_bytes()).hexdigest()
    counts["named_packet_not_found" if not packets else "named_packet_fingerprint_differs"] += 1
    return ""


def stored_abstracts(ledger_path: Path) -> dict[str, str]:
    ledger = pd.read_parquet(ledger_path, columns=["doi", "abstract"])
    return {
        normalize(doi).lower(): "" if abstract is None or pd.isna(abstract) else normalize(abstract)
        for doi, abstract in zip(ledger["doi"], ledger["abstract"])
    }


def abstract_hash(sent: object, stored: str) -> str:
    return hashlib.sha256(stored.encode("utf-8")).hexdigest() if stored and compact(stored) == compact(sent) else ""


def backfill_task(
    task: dict, packets: dict[tuple[str, str], list[dict]], abstracts: dict[str, str], counts: Counter
) -> dict:
    """The task with text hashes added; a task that already has them is returned unchanged."""
    holder = text_holder(task)
    if {"artifact_sha256", "abstract_sha256"} <= set(holder):
        counts["already_recorded"] += 1
        return task
    article = reads_article_text(task)
    _, doi = packet_location(task)
    hashes = {
        "artifact_sha256": artifact_hash(task, packets.get(packet_location(task), []), counts) if article else "",
        "abstract_sha256": abstract_hash((task.get("paper_metadata") or {}).get("abstract", ""), abstracts.get(doi, "")),
    }
    named = hashes["artifact_sha256"] if article else hashes["abstract_sha256"]
    counts[f"{'article_text' if article else 'abstract_only'}_{'named' if named else 'not_named'}"] += 1
    return {**task, ("source" if is_secondary(task) else "text_source"): {**holder, **hashes}}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tasks-jsonl", type=Path, action="append", required=True)
    parser.add_argument(
        "--extra-packets-jsonl", type=Path, action="append", default=[],
        help="Other copies of packet files, searched when a task's own packet file has been rebuilt.",
    )
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--out-jsonl", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tasks: list[dict] = []
    seen: set[str] = set()
    counts: Counter = Counter()
    for path in args.tasks_jsonl:
        for task in read_jsonl(path):
            task_id = normalize(task.get("task_id", ""))
            if not task_id or task_id in seen:
                counts["duplicate_or_missing_task_id"] += 1
                continue
            seen.add(task_id)
            tasks.append(task)
    packets = load_packets(tasks, [path.resolve() for path in args.extra_packets_jsonl])
    abstracts = stored_abstracts(args.ledger)
    args.out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.out_jsonl.open("w", encoding="utf-8") as handle:
        for task in tasks:
            handle.write(json.dumps(backfill_task(task, packets, abstracts, counts), ensure_ascii=False) + "\n")
    write_json(
        args.report_json,
        {
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "inputs": {
                "tasks_jsonl": [str(path.resolve()) for path in args.tasks_jsonl],
                "extra_packets_jsonl": [str(path.resolve()) for path in args.extra_packets_jsonl],
                "ledger": str(args.ledger.resolve()),
            },
            "counts": dict(sorted(counts.items())),
        },
    )
    print(json.dumps(dict(sorted(counts.items())), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
