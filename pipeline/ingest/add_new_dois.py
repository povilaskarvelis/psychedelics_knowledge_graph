#!/usr/bin/env python3
"""Write a DOI queue containing only papers not already known to the corpus."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
VERSION = "0.1"
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)

DATASET_ARTIFACTS = {
    "mechanistic": {
        "paper_library": "data/processed/paper_library_mechanistic.json",
        "stubs": "data/processed/mechanistic_claim_stubs.json",
        "curated": "data/curated/claims.json",
        "exploratory": "data/curated/exploratory_claims.json",
    },
    "disorder": {
        "paper_library": "data/processed/paper_library_disorder.json",
        "stubs": "data/processed/disorder_claim_stubs.json",
        "curated": "data/curated/disorder_claims.json",
        "exploratory": "data/curated/exploratory_disorder_claims.json",
    },
}

DISCOVERY_LEDGER_ARTIFACTS = {
    "mechanistic": "data/processed/discovery_ledger_mechanistic.json",
    "disorder": "data/processed/discovery_ledger_disorder.json",
}

GLOBAL_ARTIFACTS = {
    "candidate_paper_corpus": "data/processed/candidate_paper_corpus.json",
    "benchmark_manifest": "data/raw/benchmark_manifest.json",
}

QUEUE_FIELDS = ["doi", "compound", "entity", "title", "year", "authors"]
REPORT_FIELDS = ["line_no", "doi", "compound", "entity", "title", "year", "authors", "existing_sources"]
INVALID_FIELDS = ["line_no", "raw_doi", "reason", "raw_row"]
DUPLICATE_FIELDS = ["line_no", "doi", "first_line_no", "compound", "entity", "title", "year", "authors"]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_doi(raw: object) -> str:
    text = normalize(raw)
    if not text:
        return ""
    lowered = text.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip().lower()


def valid_doi(raw: object) -> bool:
    return bool(DOI_RE.match(normalize_doi(raw)))


def source_artifact(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def rows_from_json_payload(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("records", "entries", "rows", "results"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def add_existing_doi(existing: dict[str, set[str]], doi: object, source: str) -> None:
    normalized = normalize_doi(doi)
    if normalized:
        existing[normalized].add(source)


def collect_dois_from_artifact(root: Path, path: Path, source_name: str, existing: dict[str, set[str]]) -> int:
    payload = read_json(path)
    if payload is None:
        return 0

    rows = rows_from_json_payload(payload)
    count_before = len(existing)
    for row in rows:
        add_existing_doi(existing, row.get("doi") or row.get("study_doi"), source_name)
    return len(existing) - count_before


def load_existing_dois(
    root: Path,
    dataset: str,
    existing_scope: str = "global",
    include_discovery_ledger: bool = False,
) -> tuple[dict[str, set[str]], list[str]]:
    root = root.resolve()
    existing: dict[str, set[str]] = defaultdict(set)
    input_artifacts: list[str] = []

    for source_name, rel_path in GLOBAL_ARTIFACTS.items():
        path = root / rel_path
        if path.exists():
            input_artifacts.append(source_artifact(root, path))
            collect_dois_from_artifact(root, path, source_name, existing)

    selected_datasets = [dataset] if existing_scope == "dataset" else list(DATASET_ARTIFACTS)
    for selected in selected_datasets:
        for source_name, rel_path in DATASET_ARTIFACTS[selected].items():
            path = root / rel_path
            if not path.exists():
                continue
            input_artifacts.append(source_artifact(root, path))
            collect_dois_from_artifact(root, path, f"{selected}:{source_name}", existing)
        if include_discovery_ledger:
            path = root / DISCOVERY_LEDGER_ARTIFACTS[selected]
            if path.exists():
                input_artifacts.append(source_artifact(root, path))
                collect_dois_from_artifact(root, path, f"{selected}:discovery_ledger", existing)

    return existing, sorted(set(input_artifacts))


def parse_input_queue(path: Path) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    invalid: list[dict] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for line_no, parts in enumerate(reader, start=1):
            if not parts:
                continue
            first = normalize(parts[0])
            if not first or first.startswith("#"):
                continue
            if first.lower() in {"doi", "study_doi"}:
                continue

            padded = [normalize(part) for part in parts] + [""] * 6
            raw_doi = padded[0]
            doi = normalize_doi(raw_doi)
            if not doi:
                invalid.append(
                    {
                        "line_no": line_no,
                        "raw_doi": raw_doi,
                        "reason": "missing_doi",
                        "raw_row": ",".join(parts),
                    }
                )
                continue
            if not valid_doi(doi):
                invalid.append(
                    {
                        "line_no": line_no,
                        "raw_doi": raw_doi,
                        "reason": "invalid_doi",
                        "raw_row": ",".join(parts),
                    }
                )
                continue

            rows.append(
                {
                    "line_no": line_no,
                    "doi": doi,
                    "compound": padded[1],
                    "entity": padded[2],
                    "title": padded[3],
                    "year": padded[4],
                    "authors": padded[5],
                }
            )
    return rows, invalid


def split_new_dois(
    input_rows: list[dict],
    existing: dict[str, set[str]],
) -> tuple[list[dict], list[dict], list[dict]]:
    new_rows: list[dict] = []
    rediscovered_rows: list[dict] = []
    duplicate_input_rows: list[dict] = []
    first_seen_line: dict[str, int] = {}
    seen_input: set[str] = set()

    for row in input_rows:
        doi = normalize_doi(row.get("doi"))
        if doi in seen_input:
            duplicate = dict(row)
            duplicate["first_line_no"] = first_seen_line.get(doi, "")
            duplicate_input_rows.append(duplicate)
            continue

        seen_input.add(doi)
        first_seen_line[doi] = int(row.get("line_no") or 0)
        if doi in existing:
            rediscovered = dict(row)
            rediscovered["existing_sources"] = " | ".join(sorted(existing[doi]))
            rediscovered_rows.append(rediscovered)
            continue

        new_rows.append(dict(row))

    return new_rows, rediscovered_rows, duplicate_input_rows


def write_doi_queue(path: Path, rows: Iterable[dict], dataset: str) -> None:
    entity_name = "target" if dataset == "mechanistic" else "disorder"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# new DOI queue ({dataset}) generated at {now_utc()}\n")
        handle.write(f"# doi,compound,{entity_name},optional_study_title,optional_study_year,optional_authors\n")
        writer = csv.writer(handle)
        for row in rows:
            writer.writerow([row.get(field, "") for field in QUEUE_FIELDS])


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def default_paths(root: Path, dataset: str) -> dict[str, Path]:
    return {
        "queue_out": root / "data" / "raw" / f"doi_queue.{dataset}.new.txt",
        "report_out": root / "data" / "processed" / f"add_new_dois_report_{dataset}.json",
        "rediscovered_out": root / "data" / "processed" / f"rediscovered_dois_{dataset}.csv",
        "invalid_out": root / "data" / "processed" / f"missing_or_invalid_dois_{dataset}.csv",
        "duplicates_out": root / "data" / "processed" / f"input_duplicate_dois_{dataset}.csv",
    }


def build_source_counts(existing: dict[str, set[str]]) -> dict[str, int]:
    counts = Counter(source for sources in existing.values() for source in sources)
    return dict(sorted(counts.items()))


def add_new_dois(
    *,
    root: Path,
    dataset: str,
    input_path: Path,
    queue_out: Path,
    report_out: Path,
    rediscovered_out: Path,
    invalid_out: Path,
    duplicates_out: Path,
    existing_scope: str = "global",
    include_discovery_ledger: bool = False,
) -> dict:
    existing, input_artifacts = load_existing_dois(
        root=root,
        dataset=dataset,
        existing_scope=existing_scope,
        include_discovery_ledger=include_discovery_ledger,
    )
    input_rows, invalid_rows = parse_input_queue(input_path)
    new_rows, rediscovered_rows, duplicate_input_rows = split_new_dois(input_rows, existing)

    write_doi_queue(queue_out, new_rows, dataset=dataset)
    write_csv(rediscovered_out, rediscovered_rows, REPORT_FIELDS)
    write_csv(invalid_out, invalid_rows, INVALID_FIELDS)
    write_csv(duplicates_out, duplicate_input_rows, DUPLICATE_FIELDS)

    report = {
        "version": VERSION,
        "generated_at_utc": now_utc(),
        "dataset": dataset,
        "existing_scope": existing_scope,
        "include_discovery_ledger": include_discovery_ledger,
        "input": str(input_path),
        "input_artifacts": input_artifacts,
        "outputs": {
            "new_doi_queue": str(queue_out),
            "rediscovered_dois_csv": str(rediscovered_out),
            "missing_or_invalid_dois_csv": str(invalid_out),
            "input_duplicate_dois_csv": str(duplicates_out),
            "report_json": str(report_out),
        },
        "counts": {
            "existing_doi_universe": len(existing),
            "input_rows_valid_doi": len(input_rows),
            "new_dois": len(new_rows),
            "rediscovered_existing_dois": len(rediscovered_rows),
            "missing_or_invalid_dois": len(invalid_rows),
            "duplicate_dois_within_input": len(duplicate_input_rows),
        },
        "existing_source_counts": build_source_counts(existing),
        "new_doi_samples": [
            {
                "doi": row.get("doi", ""),
                "compound": row.get("compound", ""),
                "entity": row.get("entity", ""),
                "title": row.get("title", ""),
            }
            for row in new_rows[:25]
        ],
    }
    write_json(report_out, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Add only DOI rows that are not already known")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument("--input", required=True, help="Newly discovered DOI queue to check")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument(
        "--existing-scope",
        choices=["global", "dataset"],
        default="global",
        help="global checks both KG datasets; dataset checks only the selected dataset plus global corpus files",
    )
    parser.add_argument(
        "--include-discovery-ledger",
        action="store_true",
        help=(
            "Also treat discovery-ledger DOIs as existing. Off by default because "
            "the ledger may already include the current discovery run."
        ),
    )
    parser.add_argument("--queue-out", default="")
    parser.add_argument("--report-out", default="")
    parser.add_argument("--rediscovered-out", default="")
    parser.add_argument("--invalid-out", default="")
    parser.add_argument("--duplicates-out", default="")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    input_path = Path(args.input).resolve()
    if not input_path.exists():
        raise SystemExit(f"Input DOI queue not found: {input_path}")

    defaults = default_paths(root, args.dataset)
    report = add_new_dois(
        root=root,
        dataset=args.dataset,
        input_path=input_path,
        queue_out=Path(args.queue_out).resolve() if args.queue_out else defaults["queue_out"],
        report_out=Path(args.report_out).resolve() if args.report_out else defaults["report_out"],
        rediscovered_out=Path(args.rediscovered_out).resolve() if args.rediscovered_out else defaults["rediscovered_out"],
        invalid_out=Path(args.invalid_out).resolve() if args.invalid_out else defaults["invalid_out"],
        duplicates_out=Path(args.duplicates_out).resolve() if args.duplicates_out else defaults["duplicates_out"],
        existing_scope=args.existing_scope,
        include_discovery_ledger=args.include_discovery_ledger,
    )

    counts = report["counts"]
    print(f"Dataset: {args.dataset}")
    print(f"Existing DOI universe: {counts['existing_doi_universe']}")
    print(f"Input valid DOI rows: {counts['input_rows_valid_doi']}")
    print(f"New DOIs: {counts['new_dois']}")
    print(f"Rediscovered existing DOIs: {counts['rediscovered_existing_dois']}")
    print(f"Missing/invalid DOIs: {counts['missing_or_invalid_dois']}")
    print(f"Duplicate DOIs within input: {counts['duplicate_dois_within_input']}")
    print(f"New DOI queue: {report['outputs']['new_doi_queue']}")
    print(f"Report: {report['outputs']['report_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
