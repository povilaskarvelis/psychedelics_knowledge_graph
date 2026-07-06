#!/usr/bin/env python3
"""Export citation-focused bibliography payloads for the web UI.

The current source is the abstract-screening report's relevant papers. Once the
pipeline has a final paper bibliography, this module should be the adapter that
switches sources while keeping the browser contract stable.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ("mechanistic", "disorder")
DEFAULT_PRESCREEN_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_prescreen_decisions.parquet"


def normalize(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def compact_json(payload: dict) -> str:
    """Return compact JSON for static-site payloads."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n"


TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def clean_text(value: object) -> str:
    text = normalize(value)
    if not text:
        return ""
    text = TAG_RE.sub(" ", text)
    return SPACE_RE.sub(" ", text).strip()


def parse_year(value: object) -> int | str:
    text = normalize(value)
    if not text:
        return ""
    match = re.search(r"\b(18|19|20)\d{2}\b", text)
    if match:
        return int(match.group(0))
    try:
        year = int(float(text))
    except ValueError:
        return ""
    if 1800 <= year <= 3000:
        return year
    return ""


def clean_doi(value: object) -> str:
    text = normalize(value)
    text = re.sub(r"^doi:\s*", "", text, flags=re.I)
    text = re.sub(r"^https?://doi\.org/", "", text, flags=re.I)
    return text.strip()


def as_bool(value: object) -> bool:
    if value is True:
        return True
    return normalize(value).lower() == "true"


def load_report(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def default_report_paths(dataset: str) -> list[Path]:
    processed = ROOT / "data" / "processed"
    main = processed / f"llm_abstract_screening_report_{dataset}.json"
    suffix_reports = sorted(processed.glob(f"llm_abstract_screening_report_{dataset}.*.json"))
    paths = []
    if main.exists():
        paths.append(main)
    paths.extend(path for path in suffix_reports if path != main)
    return paths


def row_flat(row: dict) -> dict:
    flat = {}
    input_row = row.get("input_row")
    if isinstance(input_row, dict):
        flat.update(input_row)
    flat_row = row.get("flat")
    if isinstance(flat_row, dict):
        flat.update(flat_row)
    return flat


def row_is_relevant(row: dict) -> bool:
    flat = row_flat(row)
    status = normalize(flat.get("status")).lower()
    if status and status != "ok":
        return False
    adjudication = row.get("adjudication") if isinstance(row.get("adjudication"), dict) else {}
    relevance = normalize(flat.get("llm_relevance") or adjudication.get("relevance")).lower()
    return relevance == "relevant"


def split_supported_contexts(value: object) -> list[dict]:
    text = normalize(value)
    if not text:
        return []
    contexts = []
    for part in re.split(r"\s*\|\s*", text):
        if "->" not in part:
            continue
        compound, entity = part.split("->", 1)
        compound = clean_text(compound)
        entity = clean_text(entity)
        if compound or entity:
            contexts.append({"compound": compound, "entity": entity})
    return contexts


def contexts_from_row(row: dict, flat: dict) -> list[dict]:
    contexts: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add_context(compound: object, entity: object) -> None:
        compound_text = clean_text(compound)
        entity_text = clean_text(entity)
        if not compound_text and not entity_text:
            return
        key = (compound_text.lower(), entity_text.lower())
        if key in seen:
            return
        seen.add(key)
        contexts.append({"compound": compound_text, "entity": entity_text})

    for source_key in ("verification", "adjudication"):
        source = row.get(source_key)
        if not isinstance(source, dict):
            continue
        supported = source.get("verified_supported_contexts") or source.get("supported_contexts") or []
        if not isinstance(supported, list):
            continue
        for context in supported:
            if not isinstance(context, dict):
                continue
            support = normalize(context.get("support")).lower()
            if support and support != "supported":
                continue
            add_context(
                context.get("compound"),
                context.get("entity") or context.get("target") or context.get("disorder"),
            )

    for context in split_supported_contexts(flat.get("llm_supported_contexts")):
        add_context(context.get("compound"), context.get("entity"))

    return contexts


def paper_identity(paper: dict) -> str:
    doi = normalize(paper.get("doi")).lower()
    if doi:
        return f"doi:{doi}"
    openalex_id = normalize(paper.get("openalex_id")).lower()
    if openalex_id:
        return f"openalex:{openalex_id}"
    title = normalize(paper.get("title")).lower()
    year = normalize(paper.get("year"))
    if title or year:
        return f"title:{title}|{year}"
    return ""


def paper_from_row(dataset: str, row: dict, report_path: Path) -> dict:
    flat = row_flat(row)
    verification = row.get("verification") if isinstance(row.get("verification"), dict) else {}
    return {
        "id": "",
        "dataset": dataset,
        "doi": clean_doi(flat.get("study_doi")),
        "openalex_id": normalize(flat.get("openalex_id")),
        "title": clean_text(flat.get("study_title")),
        "authors": clean_text(flat.get("authors")),
        "year": parse_year(flat.get("study_year")),
        "journal": clean_text(flat.get("study_journal") or flat.get("journal")),
        "publication_date": normalize(flat.get("publication_date")),
        "publication_type": clean_text(flat.get("publication_type")),
        "publisher": clean_text(flat.get("publisher")),
        "trial_registry_ids": normalize(flat.get("trial_registry_ids")),
        "journal_issn": normalize(flat.get("journal_issn")),
        "journal_eissn": normalize(flat.get("journal_eissn")),
        "language": normalize(flat.get("language")),
        "keywords": clean_text(flat.get("keywords")),
        "mesh_terms": clean_text(flat.get("mesh_terms")),
        "screening": {
            "source": "abstract_screening",
            "relevance": "relevant",
            "llm_confidence": normalize(flat.get("llm_confidence")),
            "quote_verified": as_bool(verification.get("quote_verified")) or as_bool(flat.get("quote_verified")),
        },
        "contexts": contexts_from_row(row, flat),
        "source_reports": [str(report_path)],
    }


def merge_paper(existing: dict, incoming: dict) -> dict:
    for key, value in incoming.items():
        if key in {"contexts", "source_reports", "screening"}:
            continue
        if not existing.get(key) and value not in ("", [], {}, None):
            existing[key] = value

    report_paths = list(existing.get("source_reports") or [])
    for path in incoming.get("source_reports") or []:
        if path not in report_paths:
            report_paths.append(path)
    existing["source_reports"] = report_paths

    seen_contexts = {
        (normalize(context.get("compound")).lower(), normalize(context.get("entity")).lower())
        for context in existing.get("contexts") or []
        if isinstance(context, dict)
    }
    for context in incoming.get("contexts") or []:
        key = (normalize(context.get("compound")).lower(), normalize(context.get("entity")).lower())
        if key in seen_contexts:
            continue
        seen_contexts.add(key)
        existing.setdefault("contexts", []).append(context)

    return existing


def prescreen_retained_dois(dataset: str, prescreen_table: Path | None = DEFAULT_PRESCREEN_TABLE) -> set[str] | None:
    if prescreen_table is None or not prescreen_table.exists():
        return None
    df = pd.read_parquet(prescreen_table)
    if df.empty or "doi" not in df.columns or "dataset" not in df.columns:
        return None
    decision = df["prescreen_decision"].astype(str) if "prescreen_decision" in df.columns else pd.Series("", index=df.index)
    if "retained_for_extraction_candidate" in df.columns:
        retained_flag = df["retained_for_extraction_candidate"].map(lambda value: str(value).strip().lower() in {"1", "true", "yes"})
    else:
        retained_flag = pd.Series(False, index=df.index)
    retained = df[
        (df["dataset"].astype(str) == dataset)
        & ((decision == "retain") | retained_flag)
    ]
    return {clean_doi(value).lower() for value in retained["doi"].tolist() if clean_doi(value)}


def papers_from_reports(
    dataset: str,
    report_paths: Iterable[Path],
    *,
    retained_dois: set[str] | None = None,
) -> list[dict]:
    papers_by_id: dict[str, dict] = {}
    for report_path in report_paths:
        if not report_path.exists():
            continue
        report = load_report(report_path)
        rows = report.get("rows") or []
        if not isinstance(rows, list):
            raise ValueError(f"Expected `rows` array at {report_path}")
        for row in rows:
            if not isinstance(row, dict) or not row_is_relevant(row):
                continue
            paper = paper_from_row(dataset=dataset, row=row, report_path=report_path)
            doi = clean_doi(paper.get("doi")).lower()
            if retained_dois is not None and doi and doi not in retained_dois:
                continue
            identity = paper_identity(paper)
            if not identity:
                continue
            paper["id"] = identity
            if identity in papers_by_id:
                papers_by_id[identity] = merge_paper(papers_by_id[identity], paper)
            else:
                papers_by_id[identity] = paper

    return sorted(
        papers_by_id.values(),
        key=lambda paper: (
            -(paper.get("year") if isinstance(paper.get("year"), int) else 0),
            normalize(paper.get("authors")).lower(),
            normalize(paper.get("title")).lower(),
        ),
    )


def export_dataset(
    dataset: str,
    out_dir: Path,
    report_paths: Iterable[Path] | None = None,
    *,
    prescreen_table: Path | None = DEFAULT_PRESCREEN_TABLE,
) -> dict:
    paths = list(report_paths or default_report_paths(dataset))
    retained_dois = prescreen_retained_dois(dataset, prescreen_table=prescreen_table)
    papers = papers_from_reports(dataset=dataset, report_paths=paths, retained_dois=retained_dois)
    payload = {
        "contract_version": "1.0",
        "dataset": dataset,
        "source": "abstract_screening_relevant",
        "source_reports": [str(path) for path in paths if path.exists()],
        "prescreen_filter": str(prescreen_table) if retained_dois is not None and prescreen_table else "",
        "generated_at_utc": now_utc(),
        "paper_count": len(papers),
        "papers": papers,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"bibliography_payload_{dataset}.json"
    out_file.write_text(compact_json(payload), encoding="utf-8")
    return {"output_file": str(out_file), "paper_count": len(papers), "source_reports": payload["source_reports"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Export citation-focused bibliography payloads")
    parser.add_argument("--dataset", choices=[*DATASETS, "all"], default="all")
    parser.add_argument("--out-dir", default=str(ROOT / "data" / "processed"))
    parser.add_argument(
        "--legacy-split-output",
        action="store_true",
        help="Write the retired split bibliography payloads. The public site uses data/kg/views/methods_bibliography.json.",
    )
    parser.add_argument(
        "--no-prescreen-filter",
        action="store_true",
        help="Do not filter bibliography papers by current deterministic prescreen decisions.",
    )
    args = parser.parse_args()

    if not args.legacy_split_output:
        raise SystemExit(
            "The split bibliography payloads are retired. Run "
            "`python pipeline/kg/build_methods_flow.py` to build data/kg/views/methods_bibliography.json. "
            "Pass --legacy-split-output only if you intentionally need the old compatibility payloads."
        )

    datasets = DATASETS if args.dataset == "all" else (args.dataset,)
    manifest = {
        "generated_at_utc": now_utc(),
        "datasets": {},
    }
    out_dir = Path(args.out_dir)
    for dataset in datasets:
        manifest["datasets"][dataset] = export_dataset(
            dataset,
            out_dir=out_dir,
            prescreen_table=None if args.no_prescreen_filter else DEFAULT_PRESCREEN_TABLE,
        )

    manifest_path = out_dir / "bibliography_payload_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
