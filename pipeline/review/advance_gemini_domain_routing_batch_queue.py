#!/usr/bin/env python3
"""Advance a Gemini domain-routing batch queue one submitted part at a time."""

from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys

import pandas as pd

try:
    from pipeline.review.run_gemini_domain_routing import (
        DEFAULT_COUNTS_CSV,
        DEFAULT_ENV,
        DEFAULT_LITERATURE_TYPE_TABLE,
        DEFAULT_METADATA_TABLE,
        DEFAULT_OUTPUT_TABLE,
        DEFAULT_PRESCREEN_TABLE,
        DEFAULT_RAW_JSONL,
        DEFAULT_SUMMARY_JSON,
        build_summary,
        clean,
        prescreen_row_is_extraction_candidate,
        read_table,
        write_counts_csv,
        write_json,
    )
    from pipeline.fulltext.convert_pdfs import normalize_doi
    from pipeline.review.run_gemini_domain_routing_batch import (
        TERMINAL_STATES,
        check_status,
        download_results,
        parse_batch_results,
        submit_batch,
    )
    from pipeline.review.build_gemini_domain_routing_batch_queue import DEFAULT_QUEUE_JSON
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.review.run_gemini_domain_routing import (
        DEFAULT_COUNTS_CSV,
        DEFAULT_ENV,
        DEFAULT_LITERATURE_TYPE_TABLE,
        DEFAULT_METADATA_TABLE,
        DEFAULT_OUTPUT_TABLE,
        DEFAULT_PRESCREEN_TABLE,
        DEFAULT_RAW_JSONL,
        DEFAULT_SUMMARY_JSON,
        build_summary,
        clean,
        prescreen_row_is_extraction_candidate,
        read_table,
        write_counts_csv,
        write_json,
    )
    from pipeline.fulltext.convert_pdfs import normalize_doi
    from pipeline.review.run_gemini_domain_routing_batch import (
        TERMINAL_STATES,
        check_status,
        download_results,
        parse_batch_results,
        submit_batch,
    )
    from pipeline.review.build_gemini_domain_routing_batch_queue import DEFAULT_QUEUE_JSON


ACTIVE_STATES = {"JOB_STATE_PENDING", "JOB_STATE_RUNNING", "JOB_STATE_QUEUED"}
DEFAULT_MANUAL_REVIEW_JSON = (
    DEFAULT_METADATA_TABLE.parent / "paper_domain_routing_manual_review_20260530.json"
)


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def part_tag(queue: dict, part: dict) -> str:
    return f"{clean(queue.get('name', 'domain_routing'))}_part{int(part['part']):03d}"


def part_output_paths(queue: dict, part: dict) -> dict[str, Path]:
    out_dir = Path(part["raw_jsonl"]).resolve().parent
    tag = part_tag(queue, part)
    return {
        "route_table": out_dir / f"paper_domain_routing_gemini.{tag}.parquet",
        "summary_json": out_dir / f"paper_domain_routing_gemini_summary.{tag}.json",
        "counts_csv": out_dir / f"paper_domain_routing_gemini_counts.{tag}.csv",
    }


def part_is_parsed(queue: dict, part: dict) -> bool:
    report = read_json(Path(part["report_json"]).resolve())
    paths = part_output_paths(queue, part)
    return report.get("status") == "ok" and paths["route_table"].exists()


def submitted_part_state(part: dict, args: argparse.Namespace) -> str:
    payload = check_status(
        argparse.Namespace(
            job_json=str(Path(part["job_json"]).resolve()),
            job_name="",
            env_file=str(Path(args.env_file).resolve()),
        )
    )
    return clean(payload.get("state", ""))


def submit_part(queue: dict, part: dict, args: argparse.Namespace) -> dict:
    model = clean(args.model) or clean(queue.get("inputs", {}).get("model", ""))
    display_name = f"psychedelics-kg-domain-routing-20260530-part{int(part['part']):03d}"
    return submit_batch(
        argparse.Namespace(
            batch_input_jsonl=str(Path(part["batch_requests_jsonl"]).resolve()),
            manifest_json=str(Path(part["manifest_json"]).resolve()),
            job_json=str(Path(part["job_json"]).resolve()),
            env_file=str(Path(args.env_file).resolve()),
            model=model,
            display_name=display_name,
        )
    )


def download_part(part: dict, args: argparse.Namespace) -> dict:
    return download_results(
        argparse.Namespace(
            job_json=str(Path(part["job_json"]).resolve()),
            job_name="",
            env_file=str(Path(args.env_file).resolve()),
            batch_output_jsonl=str(Path(part["batch_results_jsonl"]).resolve()),
        )
    )


def parse_part(queue: dict, part: dict, args: argparse.Namespace) -> dict:
    paths = part_output_paths(queue, part)
    model = clean(args.model) or clean(queue.get("inputs", {}).get("model", ""))
    return parse_batch_results(
        argparse.Namespace(
            metadata_table=str(Path(args.metadata_table).resolve()),
            prescreen_decisions_table=str(Path(args.prescreen_decisions_table).resolve()),
            literature_type_table=str(Path(args.literature_type_table).resolve()),
            batch_output_jsonl=str(Path(part["batch_results_jsonl"]).resolve()),
            manifest_json=str(Path(part["manifest_json"]).resolve()),
            raw_jsonl=str(Path(part["raw_jsonl"]).resolve()),
            output_table=str(paths["route_table"]),
            summary_json=str(paths["summary_json"]),
            counts_csv=str(paths["counts_csv"]),
            report_json=str(Path(part["report_json"]).resolve()),
            env_file=str(Path(args.env_file).resolve()),
            model=model,
        )
    )


def write_combined_raw_jsonl(queue: dict, output: Path) -> int:
    rows = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as out:
        for part in queue.get("parts", []):
            if not part_is_parsed(queue, part):
                continue
            raw_jsonl = Path(part["raw_jsonl"]).resolve()
            if not raw_jsonl.exists():
                continue
            with raw_jsonl.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        out.write(line)
                        rows += 1
    return rows


def current_prescreen_candidate_dois(path: Path) -> set[str]:
    df = read_table(path)
    out: set[str] = set()
    if df.empty or "doi" not in df.columns:
        return out
    for row in df.to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        if doi and prescreen_row_is_extraction_candidate(row):
            out.add(doi)
    return out


def load_manual_reviews(path: Path) -> dict[str, dict]:
    payload = read_json(path)
    out: dict[str, dict] = {}
    for row in payload.get("records", []) if isinstance(payload.get("records", []), list) else []:
        doi = normalize_doi(row.get("doi", ""))
        if doi:
            out[doi] = row
    return out


def apply_manual_reviews(df: pd.DataFrame, reviews: dict[str, dict]) -> tuple[pd.DataFrame, int]:
    if not reviews or df.empty or "doi" not in df.columns:
        return df, 0
    out = df.copy()
    changed = 0
    for doi, review in reviews.items():
        mask = out["doi"].map(normalize_doi).eq(doi)
        changed += int(mask.sum())
        if not mask.any():
            continue
        decision = clean(review.get("manual_decision", "")) or "exclude_out_of_scope"
        primary = clean(review.get("manual_primary_domain", "")) or "general_topic"
        tags = clean(review.get("manual_domain_tags", ""))
        reason = clean(review.get("manual_reason", "")) or "Manual review decision."
        out.loc[mask, "retained_for_extraction_candidate"] = decision != "exclude_out_of_scope"
        out.loc[mask, "all_domain_tags"] = tags
        out.loc[mask, "primary_domain"] = primary
        out.loc[mask, "screening_decision"] = decision
        out.loc[mask, "screening_reason"] = reason
        out.loc[mask, "methodological_validity_tags"] = clean(review.get("manual_methodological_validity_tags", ""))
        if decision == "exclude_out_of_scope":
            out.loc[mask, "domain_route"] = "general_topic"
            out.loc[mask, "domain_tag"] = ""
        out.loc[mask, "domain_route_basis"] = reason
        out.loc[mask, "tag_source_fields"] = "manual_review_after_gemini_title_abstract"
        out.loc[mask, "model"] = "manual_review_after_gemini-3-flash-preview"
    return out, changed


def rebuild_combined_outputs(queue: dict, args: argparse.Namespace) -> dict:
    frames = []
    parsed_parts = []
    for part in queue.get("parts", []):
        paths = part_output_paths(queue, part)
        if paths["route_table"].exists() and part_is_parsed(queue, part):
            frames.append(pd.read_parquet(paths["route_table"]))
            parsed_parts.append(int(part["part"]))

    output_table = Path(args.output_table).resolve()
    summary_json = Path(args.summary_json).resolve()
    counts_csv = Path(args.counts_csv).resolve()
    raw_jsonl = Path(args.raw_jsonl).resolve()
    if not frames:
        return {
            "parsed_parts": 0,
            "parts_total": len(queue.get("parts", [])),
            "route_rows": 0,
            "routed_dois": 0,
            "raw_rows": 0,
            "output_table": str(output_table),
            "summary_json": str(summary_json),
            "written": False,
        }

    combined = pd.concat(frames, ignore_index=True)
    input_dois = set(combined["doi"].map(normalize_doi)) if "doi" in combined.columns else set()
    candidate_dois = current_prescreen_candidate_dois(Path(args.prescreen_decisions_table).resolve())
    if candidate_dois and "doi" in combined.columns:
        combined = combined[combined["doi"].map(normalize_doi).isin(candidate_dois)].copy()
    output_dois = set(combined["doi"].map(normalize_doi)) if "doi" in combined.columns else set()
    prescreen_filtered_dois = sorted(input_dois - output_dois)
    manual_reviews = load_manual_reviews(Path(args.manual_review_json).resolve()) if clean(args.manual_review_json) else {}
    combined, manual_reviewed_rows = apply_manual_reviews(combined, manual_reviews)
    combined = combined.sort_values(["doi", "domain_route"]).reset_index(drop=True)
    output_table.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(output_table, engine="pyarrow", index=False)
    route_rows = combined.to_dict("records")

    raw_rows = write_combined_raw_jsonl(queue, raw_jsonl)
    summary, counts = build_summary(
        route_rows,
        inputs={
            "queue_json": str(Path(args.queue_json).resolve()),
            "metadata_table": str(Path(args.metadata_table).resolve()),
            "prescreen_decisions_table": str(Path(args.prescreen_decisions_table).resolve()),
            "literature_type_table": str(Path(args.literature_type_table).resolve()),
            "raw_jsonl": str(raw_jsonl),
            "batch_queue_combined": True,
            "parsed_parts": parsed_parts,
        },
    )
    summary["batch_queue"] = {
        "parts_total": len(queue.get("parts", [])),
        "parts_parsed": len(parsed_parts),
        "parsed_part_numbers": parsed_parts,
        "combined_raw_rows": raw_rows,
        "prescreen_filtered_dois": len(prescreen_filtered_dois),
        "prescreen_filtered_doi_examples": prescreen_filtered_dois[:20],
    }
    if manual_reviews:
        summary["manual_review"] = {
            "reviewed_dois": len(manual_reviews),
            "changed_route_rows": manual_reviewed_rows,
            "decision": "manual_domain_routing_reviews_applied",
            "manual_review_json": str(Path(args.manual_review_json).resolve()),
        }
    write_json(summary_json, summary)
    write_counts_csv(counts_csv, counts)
    return {
        "parsed_parts": len(parsed_parts),
        "parts_total": len(queue.get("parts", [])),
        "route_rows": len(route_rows),
        "routed_dois": summary["routed_dois"],
        "raw_rows": raw_rows,
        "output_table": str(output_table),
        "summary_json": str(summary_json),
        "written": True,
    }


def advance_queue(args: argparse.Namespace) -> dict:
    queue_path = Path(args.queue_json).resolve()
    queue = read_json(queue_path)
    if not queue:
        raise SystemExit(f"Queue JSON does not exist or is empty: {queue_path}")
    parts = queue.get("parts", [])
    if not parts:
        raise SystemExit(f"Queue has no parts: {queue_path}")

    for part in parts:
        part_number = int(part["part"])
        if part_is_parsed(queue, part):
            continue

        job_json = Path(part["job_json"]).resolve()
        if not job_json.exists():
            if args.no_submit:
                combined = rebuild_combined_outputs(queue, args)
                return {"action": "ready_to_submit", "part": part_number, "combined": combined}
            try:
                payload = submit_part(queue, part, args)
            except Exception as exc:  # pragma: no cover - API quota/transient behavior
                combined = rebuild_combined_outputs(queue, args)
                return {
                    "action": "submit_deferred",
                    "part": part_number,
                    "error_type": type(exc).__name__,
                    "error": clean(exc),
                    "combined": combined,
                }
            combined = rebuild_combined_outputs(queue, args)
            return {
                "action": "submitted",
                "part": part_number,
                "job_name": payload.get("job_name", ""),
                "combined": combined,
            }

        state = submitted_part_state(part, args)
        if state == "JOB_STATE_SUCCEEDED":
            if not Path(part["batch_results_jsonl"]).resolve().exists():
                download_part(part, args)
            report = parse_part(queue, part, args)
            combined = rebuild_combined_outputs(queue, args)
            if report.get("status") != "ok":
                return {
                    "action": "parse_issues",
                    "part": part_number,
                    "state": state,
                    "report": report,
                    "combined": combined,
                }
            next_unparsed = next((later for later in parts if not part_is_parsed(queue, later)), None)
            if next_unparsed and not Path(next_unparsed["job_json"]).resolve().exists() and not args.no_submit:
                try:
                    payload = submit_part(queue, next_unparsed, args)
                except Exception as exc:  # pragma: no cover - API quota/transient behavior
                    return {
                        "action": "parsed_submit_deferred",
                        "part": part_number,
                        "next_part": int(next_unparsed["part"]),
                        "error_type": type(exc).__name__,
                        "error": clean(exc),
                        "combined": combined,
                    }
                return {
                    "action": "parsed_and_submitted_next",
                    "part": part_number,
                    "next_part": int(next_unparsed["part"]),
                    "next_job_name": payload.get("job_name", ""),
                    "combined": combined,
                }
            return {"action": "parsed", "part": part_number, "combined": combined}
        if state in TERMINAL_STATES:
            combined = rebuild_combined_outputs(queue, args)
            return {"action": "terminal_failure", "part": part_number, "state": state, "combined": combined}
        combined = rebuild_combined_outputs(queue, args)
        return {"action": "waiting", "part": part_number, "state": state, "combined": combined}

    combined = rebuild_combined_outputs(queue, args)
    return {"action": "complete", "combined": combined}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-json", default=str(DEFAULT_QUEUE_JSON))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--prescreen-decisions-table", default=str(DEFAULT_PRESCREEN_TABLE))
    parser.add_argument("--literature-type-table", default=str(DEFAULT_LITERATURE_TYPE_TABLE))
    parser.add_argument("--output-table", default=str(DEFAULT_OUTPUT_TABLE))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY_JSON))
    parser.add_argument("--counts-csv", default=str(DEFAULT_COUNTS_CSV))
    parser.add_argument("--raw-jsonl", default=str(DEFAULT_RAW_JSONL))
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    parser.add_argument("--model", default="")
    parser.add_argument("--manual-review-json", default=str(DEFAULT_MANUAL_REVIEW_JSON))
    parser.add_argument("--no-submit", action="store_true")
    return parser.parse_args()


def main() -> int:
    result = advance_queue(parse_args())
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result.get("action") in {"terminal_failure", "parse_issues"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
