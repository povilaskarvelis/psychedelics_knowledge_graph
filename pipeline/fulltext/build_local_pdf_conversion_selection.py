#!/usr/bin/env python3
"""Build one current, eligibility-gated local-PDF conversion selection."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
from difflib import SequenceMatcher
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.extract.build_extraction_routes import file_is_valid_pdf
from pipeline.fulltext.convert_pdfs import normalize_doi
from pipeline.fulltext.convert_routed_local_pdfs import current_prescreen_retained_dois
from pipeline.validate.doi_aliases import DEFAULT_DOI_ALIAS_REGISTRY, load_doi_aliases


CORPUS_DIR = ROOT / "data" / "processed" / "corpus"
DEFAULT_CANDIDATE_TABLE = CORPUS_DIR / "candidate_papers.parquet"
DEFAULT_PRESCREEN_TABLE = CORPUS_DIR / "paper_prescreen_decisions.parquet"
DEFAULT_NEW_WORKLIST = CORPUS_DIR / "fulltext_enrichment_worklist.parquet"
DEFAULT_HISTORICAL_WORKLIST = (
    CORPUS_DIR / "historical_fulltext_backfill" / "historical_fulltext_backfill_worklist.parquet"
)
DEFAULT_ROUTE_TABLE = CORPUS_DIR / "paper_extraction_routes.parquet"
DEFAULT_OUTPUT_TABLE = CORPUS_DIR / "local_pdf_conversion_selection.parquet"
DEFAULT_OUTPUT_DOIS = CORPUS_DIR / "local_pdf_conversion_selection_dois.txt"
DEFAULT_REPORT = CORPUS_DIR / "local_pdf_conversion_selection_report.json"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).lower() in {"1", "true", "yes", "y", "include", "retain"}


def split_paths(value: object) -> list[str]:
    values: list[str] = []
    for raw in clean(value).split("|"):
        path = raw.strip()
        if path and path not in values:
            values.append(path)
    return values


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_rows_by_doi(frame: pd.DataFrame) -> dict[str, dict]:
    return {
        doi: row
        for row in frame.fillna("").to_dict("records")
        if (doi := normalize_doi(row.get("doi", "")).lower())
    }


def candidate_is_downstream_eligible(row: dict) -> bool:
    if not truthy(row.get("prescreen_retained_for_extraction_candidate", False)):
        return False
    if not truthy(row.get("retained_for_extraction_candidate", False)):
        return False
    if clean(row.get("pipeline_exclusion_stage", "")):
        return False
    if clean(row.get("post_retrieval_decision", "")).lower() == "exclude":
        return False
    return True


def normalized_identity_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", clean(value)).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def pdf_identity_group_is_compatible(dois: list[str], candidate_by_doi: dict[str, dict]) -> bool:
    """Require corroborating metadata before treating a shared PDF as one paper."""

    rows = [candidate_by_doi.get(doi, {}) for doi in dois]
    titles = [normalized_identity_text(row.get("study_title", "")) for row in rows]
    nonblank_titles = [title for title in titles if title]
    if nonblank_titles and len(set(nonblank_titles)) == 1:
        return True
    if len(nonblank_titles) == len(dois):
        similarities = [
            SequenceMatcher(None, left, right).ratio()
            for index, left in enumerate(nonblank_titles)
            for right in nonblank_titles[index + 1 :]
        ]
        if similarities and min(similarities) >= 0.9:
            return True
    authors = [normalized_identity_text(row.get("authors", "")) for row in rows]
    years = [clean(row.get("study_year", "")) for row in rows]
    if authors and all(authors) and len(set(authors)) == 1 and all(years) and len(set(years)) == 1:
        return True
    journals = [normalized_identity_text(row.get("study_journal", "")) for row in rows]
    if (
        len(dois) == 2
        and all(authors)
        and all(years)
        and len(set(years)) == 1
        and all(journals)
        and len(set(journals)) == 1
        and SequenceMatcher(None, authors[0], authors[1]).ratio() >= 0.9
    ):
        # This covers translated-title or DOI-migration records without accepting
        # a shared file merely because its year or venue happens to match.
        return True
    return False


def preferred_pdf_identity_canonical(
    dois: list[str],
    candidate_by_doi: dict[str, dict],
    registered_canonicals: set[str],
) -> str:
    repository_prefixes = ("10.5281/zenodo.", "10.17613/", "10.25316/")

    def rank(doi: str) -> tuple:
        row = candidate_by_doi.get(doi, {})
        processed = any(
            clean(row.get(field, ""))
            for field in ("graph_inclusion_status", "extraction_route_status", "has_converted_full_text")
        )
        repository = doi.startswith(repository_prefixes)
        zenodo_number = int(doi.rsplit(".", 1)[-1]) if doi.startswith("10.5281/zenodo.") else 10**30
        return (
            0 if doi in registered_canonicals else 1,
            0 if processed else 1,
            1 if repository else 0,
            zenodo_number,
            len(doi),
            doi,
        )

    return min(dois, key=rank)


def selected_conversion_rows(frame: pd.DataFrame, cohort: str) -> list[dict]:
    if frame.empty:
        return []
    required = {
        "doi",
        "selected_for_downstream",
        "fulltext_enrichment_needed",
        "fulltext_enrichment_action",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{cohort} worklist is missing required columns: {missing}")
    selected = frame[
        frame["selected_for_downstream"].map(truthy)
        & frame["fulltext_enrichment_needed"].map(truthy)
        & frame["fulltext_enrichment_action"].fillna("").astype(str).eq("convert_local_pdf")
    ]
    rows: list[dict] = []
    for row in selected.fillna("").to_dict("records"):
        doi = normalize_doi(row.get("doi", "")).lower()
        if doi:
            row["doi"] = doi
            row["selection_cohort"] = cohort
            rows.append(row)
    return rows


def selected_route_conversion_rows(frame: pd.DataFrame) -> list[dict]:
    """Reconcile retained local-PDF routes that predate the explicit worklists."""
    if frame.empty:
        return []
    required = {"doi", "retained_for_extraction_candidate", "route_action", "local_pdf_paths"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"current route table is missing required columns: {missing}")
    selected = frame[
        frame["retained_for_extraction_candidate"].map(truthy)
        & frame["route_action"].fillna("").astype(str).eq("convert_local_pdf_then_extract")
        & frame["local_pdf_paths"].fillna("").astype(str).str.strip().ne("")
    ]
    rows: list[dict] = []
    seen: set[str] = set()
    for row in selected.fillna("").to_dict("records"):
        doi = normalize_doi(row.get("doi", "")).lower()
        if not doi or doi in seen:
            continue
        seen.add(doi)
        rows.append(
            {
                **row,
                "doi": doi,
                "selected_for_downstream": True,
                "fulltext_enrichment_needed": True,
                "fulltext_enrichment_action": "convert_local_pdf",
                "selection_cohort": "current_route_reconciliation",
            }
        )
    return rows


def preferred_canonical_doi(
    doi: str,
    aliases: dict[str, str],
    eligible_candidate_dois: set[str],
) -> str:
    seen: set[str] = set()
    current = doi
    while current in aliases and current not in seen:
        seen.add(current)
        target = normalize_doi(aliases[current]).lower()
        if not target or target not in eligible_candidate_dois:
            break
        current = target
    return current


def atomic_write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        frame.to_parquet(temporary, engine="pyarrow", index=False)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build(args: argparse.Namespace) -> dict:
    candidate_path = Path(args.candidate_table).resolve()
    prescreen_path = Path(args.prescreen_table).resolve()
    new_path = Path(args.new_worklist).resolve()
    historical_path = Path(args.historical_worklist).resolve()
    route_value = clean(getattr(args, "route_table", ""))
    route_path = Path(route_value).resolve() if route_value else None
    alias_path = Path(args.doi_alias_registry).resolve()
    output_path = Path(args.output_table).resolve()
    doi_path = Path(args.output_dois).resolve()
    report_path = Path(args.report_json).resolve()

    candidate_df = pd.read_parquet(candidate_path)
    prescreen_df = pd.read_parquet(prescreen_path)
    retained_prescreen = current_prescreen_retained_dois(prescreen_df)
    candidate_by_doi = candidate_rows_by_doi(candidate_df)
    eligible_candidate_dois = {
        doi for doi, row in candidate_by_doi.items() if candidate_is_downstream_eligible(row)
    }
    aliases = load_doi_aliases(alias_path)

    source_rows = [
        *selected_conversion_rows(pd.read_parquet(new_path), "new_postscreen"),
        *selected_conversion_rows(pd.read_parquet(historical_path), "historical_backfill"),
        *(
            selected_route_conversion_rows(pd.read_parquet(route_path))
            if route_path is not None and route_path.is_file()
            else []
        ),
    ]
    counts: Counter[str] = Counter()
    grouped: dict[str, list[dict]] = defaultdict(list)
    alias_suppressions: dict[str, str] = {}
    for row in source_rows:
        doi = clean(row.get("doi", "")).lower()
        if doi not in retained_prescreen:
            counts["blocked_current_prescreen"] += 1
            continue
        if doi not in eligible_candidate_dois:
            counts["blocked_current_downstream_state"] += 1
            continue
        canonical = preferred_canonical_doi(doi, aliases, eligible_candidate_dois)
        if canonical != doi:
            alias_suppressions[doi] = canonical
        grouped[canonical].append(row)

    output_rows: list[dict] = []
    missing_pdf_dois: list[str] = []
    multiple_pdf_hashes: dict[str, list[str]] = {}
    for doi, rows in sorted(grouped.items()):
        paths: list[Path] = []
        cohorts: list[str] = []
        for row in rows:
            cohort = clean(row.get("selection_cohort", ""))
            if cohort and cohort not in cohorts:
                cohorts.append(cohort)
            for field in ("pdf_local_path", "local_pdf_paths"):
                for raw_path in split_paths(row.get(field, "")):
                    path = resolve_path(raw_path)
                    if path not in paths and path.is_file() and file_is_valid_pdf(path):
                        paths.append(path)
        if not paths:
            missing_pdf_dois.append(doi)
            continue
        hashes = {sha256(path): path for path in paths}
        if len(hashes) > 1:
            multiple_pdf_hashes[doi] = sorted(hashes)
        chosen_hash, chosen_path = next(iter(hashes.items()))
        candidate = candidate_by_doi.get(doi, {})
        output_rows.append(
            {
                "table_version": "local_pdf_conversion_selection_v2",
                "generated_at_utc": now_utc(),
                "doi": doi,
                "selected_for_downstream": True,
                "fulltext_enrichment_needed": True,
                "fulltext_enrichment_action": "convert_local_pdf",
                "selection_cohorts": "|".join(cohorts),
                "study_title": clean(candidate.get("study_title", ""))
                or clean(rows[0].get("study_title", "")),
                "study_year": clean(candidate.get("study_year", ""))
                or clean(rows[0].get("study_year", "")),
                "pdf_local_path": str(chosen_path),
                "local_pdf_paths": str(chosen_path),
                "pdf_sha256": chosen_hash,
                "source_row_count": len(rows),
                "source_dois": "|".join(sorted({clean(row.get("doi", "")) for row in rows})),
            }
        )

    hash_to_dois: dict[str, list[str]] = defaultdict(list)
    for row in output_rows:
        hash_to_dois[row["pdf_sha256"]].append(row["doi"])
    shared_pdf_groups = {
        digest: sorted(dois) for digest, dois in hash_to_dois.items() if len(dois) > 1
    }
    registered_canonicals = {normalize_doi(value).lower() for value in aliases.values()}
    inferred_pdf_identity_aliases: dict[str, str] = {}
    unresolved_hash_conflicts: dict[str, list[str]] = {}
    rows_by_doi = {row["doi"]: row for row in output_rows}
    for digest, dois in shared_pdf_groups.items():
        if not pdf_identity_group_is_compatible(dois, candidate_by_doi):
            unresolved_hash_conflicts[digest] = dois
            continue
        canonical = preferred_pdf_identity_canonical(dois, candidate_by_doi, registered_canonicals)
        canonical_row = rows_by_doi[canonical]
        cohorts: list[str] = []
        source_dois: set[str] = set()
        source_row_count = 0
        for doi in dois:
            row = rows_by_doi[doi]
            cohorts.extend(value for value in clean(row.get("selection_cohorts", "")).split("|") if value)
            source_dois.update(value for value in clean(row.get("source_dois", "")).split("|") if value)
            source_row_count += int(row.get("source_row_count", 0) or 0)
            if doi != canonical:
                inferred_pdf_identity_aliases[doi] = canonical
                rows_by_doi.pop(doi, None)
        canonical_row["selection_cohorts"] = "|".join(dict.fromkeys(cohorts))
        canonical_row["source_dois"] = "|".join(sorted(source_dois))
        canonical_row["source_row_count"] = source_row_count
        canonical_row["pdf_identity_deduplicated_dois"] = "|".join(dois)

    if unresolved_hash_conflicts:
        preview = list(unresolved_hash_conflicts.items())[:10]
        raise ValueError(
            "Byte-identical PDFs remain assigned to metadata-incompatible DOIs; repair the PDF "
            f"assignment or curate the DOI alias registry before conversion. Conflicts={preview}"
        )

    output_rows = sorted(rows_by_doi.values(), key=lambda row: row["doi"])

    frame = pd.DataFrame(output_rows)
    atomic_write_parquet(frame, output_path)
    atomic_write_text("".join(f"{doi}\n" for doi in frame.get("doi", [])), doi_path)
    report = {
        "schema_version": "local_pdf_conversion_selection_report_v2",
        "generated_at_utc": now_utc(),
        "inputs": {
            "candidate_table": str(candidate_path),
            "prescreen_table": str(prescreen_path),
            "new_worklist": str(new_path),
            "historical_worklist": str(historical_path),
            "route_table": str(route_path) if route_path is not None else "",
            "doi_alias_registry": str(alias_path),
        },
        "outputs": {
            "selection_table": str(output_path),
            "doi_file": str(doi_path),
            "report_json": str(report_path),
        },
        "counts": {
            "source_conversion_rows": len(source_rows),
            "source_unique_dois": len({clean(row.get("doi", "")) for row in source_rows}),
            "selected_unique_dois": len(frame),
            "registered_alias_dois_suppressed": len(alias_suppressions),
            "pdf_identity_alias_dois_suppressed": len(inferred_pdf_identity_aliases),
            "shared_pdf_identity_groups": len(shared_pdf_groups),
            "missing_valid_pdf_dois": len(missing_pdf_dois),
            **dict(counts),
        },
        "alias_suppressions": alias_suppressions,
        "inferred_pdf_identity_aliases": inferred_pdf_identity_aliases,
        "missing_valid_pdf_dois": missing_pdf_dois,
        "multiple_pdf_hashes_within_doi": multiple_pdf_hashes,
        "shared_pdf_identity_groups": shared_pdf_groups,
        "unresolved_cross_doi_pdf_hash_conflicts": unresolved_hash_conflicts,
        "eligibility_contract": {
            "current_prescreen_retain_required": True,
            "current_model_or_historical_downstream_retain_required": True,
            "current_pipeline_exclusion_must_be_blank": True,
            "post_retrieval_exclusion_blocked": True,
        },
    }
    atomic_write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", report_path)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--prescreen-table", default=str(DEFAULT_PRESCREEN_TABLE))
    parser.add_argument("--new-worklist", default=str(DEFAULT_NEW_WORKLIST))
    parser.add_argument("--historical-worklist", default=str(DEFAULT_HISTORICAL_WORKLIST))
    parser.add_argument("--route-table", default=str(DEFAULT_ROUTE_TABLE))
    parser.add_argument("--doi-alias-registry", default=str(DEFAULT_DOI_ALIAS_REGISTRY))
    parser.add_argument("--output-table", default=str(DEFAULT_OUTPUT_TABLE))
    parser.add_argument("--output-dois", default=str(DEFAULT_OUTPUT_DOIS))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT))
    return parser.parse_args()


if __name__ == "__main__":
    print(json.dumps(build(parse_args())["counts"], indent=2))
