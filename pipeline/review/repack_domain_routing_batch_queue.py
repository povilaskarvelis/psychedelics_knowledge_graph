"""Consolidate only unsubmitted screening requests without changing their contents."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from pathlib import Path

from pipeline import llm
from pipeline.review.build_domain_routing_batch_queue import part_paths


def repack_pending_queue(queue_path, out_dir, *, max_bytes=150_000_000, max_requests=50_000):
    """Caller must hold the controller lock. Any existing job file is preserved."""
    if not 1 <= max_bytes <= 200_000_000 or not 1 <= max_requests <= 50_000:
        raise ValueError("Repacked batches must respect the Batch API file/request limits")
    queue_path, out_dir = Path(queue_path), Path(out_dir)
    if out_dir.exists():
        raise FileExistsError(f"Repack destination already exists: {out_dir}")
    queue = json.loads(queue_path.read_text())
    kept, pending = [], []
    seen_keys, seen_dois = set(), set()
    source_hash = hashlib.sha256()
    pending_count = 0
    # Validate the entire old queue before publishing any replacement.
    for part in queue["parts"]:
        manifest = json.loads(Path(part["manifest_json"]).read_text())
        records = manifest["records"]
        keys = []
        with Path(part["batch_requests_jsonl"]).open("rb") as handle:
            for line in handle:
                request = json.loads(line)
                key = request["custom_id"]
                if key in seen_keys:
                    raise ValueError(f"Duplicate screening request: {key}")
                llm.require_luna(request["body"]["model"])
                seen_keys.add(key)
                keys.append(key)
                source_hash.update(line)
        if keys != [r["key"] for r in records] or len(keys) != part["requests"]:
            raise ValueError("Screening request/manifest mismatch")
        for record in records:
            doi = record["doi"]
            if not doi or doi in seen_dois:
                raise ValueError("Missing or duplicate screening DOI")
            seen_dois.add(doi)
        if Path(part["job_json"]).exists():
            kept.append(part)
        else:
            pending.append(part)
            pending_count += len(keys)
    if len(seen_keys) != queue["summary"]["records"]:
        raise ValueError("Screening queue does not cover its expected request count")
    if not pending:
        return dict(action="nothing_to_repack", submitted_parts_preserved=len(kept))

    out_dir.mkdir(parents=True)
    llm.atomic_json(out_dir / "queue.before.json", queue)
    next_number = max((p["part"] for p in kept), default=0) + 1
    new_parts, current_records = [], []
    current_bytes = current_tokens = 0
    paths = None
    handle = None
    template = None
    pending_source_hash = hashlib.sha256()

    def finish():
        nonlocal handle, current_records, current_bytes, current_tokens, next_number
        if handle is None:
            return
        handle.close()
        handle = None
        manifest = copy.deepcopy(template)
        manifest["generated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        manifest["records"] = current_records
        manifest["inputs"].update(start_index=current_records[0]["input_row_index"],
                                  limit=len(current_records), raw_jsonl=paths["raw_jsonl"])
        manifest["outputs"].update(batch_input_jsonl=paths["batch_requests_jsonl"], manifest_json=paths["manifest_json"])
        manifest["summary"]["prepared_requests"] = len(current_records)
        llm.atomic_json(paths["manifest_json"], manifest)
        new_parts.append(dict(part=next_number, requests=len(current_records),
                              start_index=current_records[0]["input_row_index"], limit=len(current_records),
                              approx_input_tokens_char4=current_tokens, input_file_bytes=current_bytes,
                              prepared_requests=len(current_records), **paths))
        next_number += 1
        current_records, current_bytes, current_tokens = [], 0, 0

    try:
        for part in pending:
            template = json.loads(Path(part["manifest_json"]).read_text())
            with Path(part["batch_requests_jsonl"]).open("rb") as source:
                for line, record in zip(source, template["records"], strict=True):
                    if len(line) > max_bytes:
                        raise ValueError("One screening request exceeds the batch byte limit")
                    if handle is not None and (current_bytes + len(line) > max_bytes or len(current_records) >= max_requests):
                        finish()
                    if handle is None:
                        paths = part_paths(queue["name"], next_number, out_dir.resolve())
                        handle = Path(paths["batch_requests_jsonl"]).open("xb")
                    handle.write(line)
                    current_records.append(record)
                    current_bytes += len(line)
                    # Counting the full wire request also includes schema and message overhead.
                    current_tokens += (len(line) + 3) // 4
                    pending_source_hash.update(line)
        finish()
    finally:
        if handle is not None:
            handle.close()

    # Re-read outputs: coverage and byte identity must hold before switching the queue.
    written_hash = hashlib.sha256()
    for part in new_parts:
        with Path(part["batch_requests_jsonl"]).open("rb") as source:
            for line in source:
                written_hash.update(line)
    if written_hash.hexdigest() != pending_source_hash.hexdigest() or sum(p["requests"] for p in new_parts) != pending_count:
        raise ValueError("Repacked requests changed or lost records")
    queue["parts"] = kept + new_parts
    queue["summary"].update(parts=len(queue["parts"]), max_requests=max_requests, max_batch_bytes=max_bytes,
                             max_approx_input_tokens=max(p["approx_input_tokens_char4"] for p in new_parts))
    report = dict(action="repacked", old_parts=len(kept) + len(pending), new_parts=len(queue["parts"]),
                  submitted_parts_preserved=len(kept), pending_parts_before=len(pending),
                  pending_parts_after=len(new_parts), pending_papers=pending_count,
                  total_papers=len(seen_keys), all_source_requests_sha256=source_hash.hexdigest(),
                  pending_requests_sha256=written_hash.hexdigest(),
                  unchanged_request_bytes=True, original_queue=str(out_dir / "queue.before.json"),
                  repacked_at_utc=dt.datetime.now(dt.timezone.utc).isoformat())
    queue["repack"] = report
    llm.atomic_json(out_dir / "repack_report.json", report)
    llm.atomic_json(queue_path, queue)
    return report
